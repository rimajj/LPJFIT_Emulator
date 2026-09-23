#!/usr/bin/env python
"""Fit, save and apply the climate-only equilibrium map, and write its out-of-fold predictions.

    NCPUS=16 TIME=01:00:00 scripts/sbatch_py.sh --exp X-20260923-equilibrium-from-climate \\
        T-eqm-build scripts/fit_equilibrium_map.py --out <scratch.models>/equimap-v1

WHAT IT WRITES, into --out:

    oof_pilot.parquet     every pilot row predicted by a model that never saw its cell -- the
                          interface the restart-synthesis work consumes. Schema: the module
                          docstring of `vegemu.models.equilibrium`
    manifest.json, heads/ the final map, fitted on all 6,000 pilot rows; `EquilibriumMap.load`
    pred_<leg>.parquet    the final map applied to every one of the 67,420 land cells, for each
                          leg whose 30-year climate table exists (corpus v0: historical 1970-1999,
                          ssp126 and ssp370 2071-2100), plus two per-cell extrapolation flags:
                            env_nn_dist    RMS distance, in pilot-standardised feature units, to
                                           the nearest pilot training row
                            env_n_outside  how many of the 91 features fall outside the pilot's
                                           training range
    envelope.json         where those predictions are extrapolations, per leg and latitude band
    report.json           every check below, and the basis

WHAT IT CHECKS, and refuses to continue past:
  * the feature matrix and the 22 sealed targets are bit-identical to what the sealed script's own
    `load()` builds from the same table, so "same inputs" is measured and not asserted by reading;
  * the state columns of `corpus.parquet` equal the 78-column decoded state table on every row;
  * the v0 historical climate table computes the 86 features exactly as the pilot did, on the 200
    pilot cells' unperturbed control runs (both come from `climate_columns`; this proves it).
And it MEASURES, and reports whatever it finds:
  * the sealed skill (0.607582 at 15 degrees, 0.610260 at 5) from this module's out-of-fold fit,
    per quantity, against the sealed `metrics.json`;
  * run-to-run determinism: the same out-of-fold fit twice;
  * thread-count sensitivity: the sealed script's own `fit_predict_oof`, which leaves LightGBM's
    thread count at its default -- one on the sealed job's one CPU, NCPUS here.

⚠ WHY THIS RUNS UNDER THE SEALED EXPERIMENT'S --exp, AND WHAT THAT DOES NOT MEAN. The login-node
guard refuses any submission whose command line contains "fit" without an `--exp`, and this file's
name contains it. The job's only skill numbers are the sealed experiment's own, re-derived from its
own recipe, corpus and folds, so that experiment is the one that governs them. It appends NOTHING
to that experiment's `result.jsonl`: the result on record stands and this is a reproduction of it.
The extra heads' out-of-fold skill is a development diagnostic (`diag_equilibrium_map.py`), never
a claim; no pre-registration covers it.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl

import exp_equilibrium_map as sealed
from screen_d95max import soil_columns
from vegemu.corpus.climate import CLIMATE_FEATURES, WINDOWS
from vegemu.models.equilibrium import (
    FEATURES,
    HEADS,
    SEALED_HEADS,
    EquilibriumMap,
    feature_matrix,
    fit_out_of_fold,
    natural,
    postprocess,
    targets_from_frame,
    transformed,
    treeless_threshold,
)
from vegemu.paths import paths, repo_root
from vegemu.score import blocked_spatial_folds, spatial_blocks

Array = npt.NDArray[np.float64]

SEALED_EXP = "X-20260923-equilibrium-from-climate"
LAT_BANDS: tuple[float, ...] = (-60.0, -45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0)
QUANTILES: tuple[float, ...] = (0.5, 0.9, 0.99, 1.0)


def soil_features(
    cells: npt.NDArray[np.int64], soildepth: Array, soil_bin: Path
) -> dict[str, Array]:
    """THE THIN ADAPTER over the sealed experiment's soil join, `screen_d95max.soil_columns`.

    Line D is moving a library version into `vegemu.corpus`. When it lands, this body is the only
    thing that changes -- and `check_inputs` below, which demands bit-equality with the sealed
    script's own `load()`, is what proves the swap changed nothing.
    """
    soil = soil_columns(cells, soil_bin, soildepth)
    codes = np.fromfile(soil_bin, dtype=np.uint8)[cells].astype(np.float64)
    return {
        "soil_code": codes,
        "soil_awc": soil[:, 0],
        "soil_w_avail": soil[:, 1],
        "soil_sand": soil[:, 2],
        "soil_clay": soil[:, 3],
    }


def with_soil(frame: pl.DataFrame, soil_bin: Path) -> pl.DataFrame:
    cols = soil_features(
        frame["cell"].to_numpy().astype(np.int64), frame["soildepth"].to_numpy(), soil_bin
    )
    return frame.with_columns(*(pl.Series(k, v) for k, v in cols.items()))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root()), *args], capture_output=True, text=True, check=False
    )
    return out.stdout.strip()


def same(a: Array, b: Array) -> dict[str, Any]:
    """Bitwise agreement of two arrays, NaN matching NaN, and the size of any disagreement."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    assert a.shape == b.shape, f"shapes differ: {a.shape} vs {b.shape}"
    both_nan = np.isnan(a) & np.isnan(b)
    differ = ~both_nan & (a != b)
    diff = np.abs(np.where(differ, a - b, 0.0))
    return {
        "identical": bool(not differ.any()),
        "n_values": int(a.size),
        "n_differ": int(differ.sum()),
        "max_abs_diff": float(np.nanmax(diff)) if diff.size else 0.0,
    }


def load_pilot(root: Path, version: str, state_table: Path, soil_bin: Path) -> dict[str, Any]:
    """Features from corpus.parquet BY NAME, targets from the 78-column decoded state table.

    The two tables are asserted to agree on every state column and every (cell, point) key, so the
    choice of which one supplies the targets cannot matter -- and is shown not to.
    """
    table = root / version / "corpus.parquet"
    corpus = pl.read_parquet(table).sort(["cell", "point"])
    state = pl.read_parquet(state_table).sort(["cell", "point"])
    assert corpus.height == state.height, "corpus and state table differ in row count"
    for key in ("cell", "point"):
        assert corpus[key].to_list() == state[key].to_list(), f"{key} order differs"
    mismatched = [
        c
        for c in state.columns
        if c != "point"
        and not same(corpus[c].cast(pl.Float64), state[c].cast(pl.Float64))["identical"]
    ]
    assert not mismatched, f"corpus.parquet disagrees with the state table on {mismatched}"

    cells = corpus["cell"].unique().sort().to_numpy()
    points = corpus.filter(pl.col("cell") == cells[0])["point"].to_list()
    n_c, n_p = len(cells), len(points)
    assert corpus.height == n_c * n_p, "every cell must carry the same climates"
    assert (corpus["point"].to_numpy().reshape(n_c, n_p) == np.array(points)[None, :]).all()

    frame = with_soil(corpus, soil_bin)
    first = frame.filter(pl.col("point") == points[0])
    return {
        "table": table,
        "frame": frame,
        "x": feature_matrix(frame),
        "y": targets_from_frame(state),
        "cells": cells,
        "points": points,
        "lon": first["lon"].to_numpy().astype(np.float64),
        "lat": first["lat"].to_numpy().astype(np.float64),
    }


def check_inputs(pilot: dict[str, Any], soil_bin: Path) -> dict[str, Any]:
    """This module's inputs against the sealed script's `load()` on the same table: bit-equal."""
    _, xs, ys, _, points, lon, lat = sealed.load(pl.read_parquet(pilot["table"]), soil_bin)
    n = pilot["x"].shape[0]
    out = {
        "features": same(xs.reshape(n, -1), pilot["x"]),
        "sealed_targets_fitted_scale": same(
            ys.reshape(n, -1), transformed(SEALED_HEADS, pilot["y"][:, : len(SEALED_HEADS)])
        ),
        "points": points == pilot["points"],
        "lon_lat": bool(np.array_equal(lon, pilot["lon"]) and np.array_equal(lat, pilot["lat"])),
    }
    assert out["features"]["identical"], (
        f"features differ from the sealed load(): {out['features']}"
    )
    assert out["sealed_targets_fitted_scale"]["identical"], "targets differ from the sealed load()"
    assert out["points"] and out["lon_lat"], "row order differs from the sealed load()"
    return out


def check_climate_tables(pilot: dict[str, Any], climate_root: Path) -> dict[str, Any]:
    """Do the v0 climate tables compute the 86 features exactly as the pilot does?

    Only the historical leg can be checked this way: the pilot's control run IS the unperturbed
    1970-1999 climate of its cell, so its features must equal the v0 historical table's row for
    that cell, bit for bit. The scenario legs have no pilot counterpart; they were built by the
    same function (`climate_columns`), whose only change since (c6ae702) is a no-op for global
    files, and their column set and order are checked here.
    """
    frame = pilot["frame"].filter(pl.col("point") == "control").sort("cell")
    hist = pl.read_parquet(climate_root / "climate_historical.parquet")
    sub = hist.filter(pl.col("cell").is_in(frame["cell"].implode())).sort("cell")
    assert sub["cell"].to_list() == frame["cell"].to_list(), "pilot cells missing from v0 table"
    per_feature = {
        f: same(frame[f].to_numpy(), sub[f].to_numpy())["n_differ"] for f in CLIMATE_FEATURES
    }
    out: dict[str, Any] = {
        "historical_vs_pilot_control": {
            "cells": int(frame.height),
            "features": len(CLIMATE_FEATURES),
            "identical": all(v == 0 for v in per_feature.values()),
            "features_with_any_difference": {k: v for k, v in per_feature.items() if v},
        },
        "columns": {},
    }
    for leg in WINDOWS:
        cols = pl.read_parquet_schema(climate_root / f"climate_{leg}.parquet")
        missing = [f for f in CLIMATE_FEATURES if f not in cols]
        out["columns"][leg] = {"missing_features": missing, "n_columns": len(cols)}
        assert not missing, f"climate_{leg}.parquet lacks {missing}"
    return out


def reproduce(
    z22: Array, pilot: dict[str, Any], soil_bin: Path, sealed_block: dict[str, Any]
) -> dict[str, Any]:
    """Score 22 fitted-scale out-of-fold heads with the SEALED scorer, against the sealed record."""
    _, _, ys, raw, points, _, _ = sealed.load(pl.read_parquet(pilot["table"]), soil_bin)
    arm = sealed.score_arm(z22.reshape(ys.shape), ys, raw, points)
    per_q = {}
    for q in SEALED_HEADS:
        mine, theirs = float(arm["per_quantity"][q]), float(sealed_block["per_quantity"][q])
        per_q[q] = {
            "reproduced": mine,
            "sealed": theirs,
            "abs_diff": 0.0 if (np.isnan(mine) and np.isnan(theirs)) else abs(mine - theirs),
        }
    return {
        "pooled_reproduced": float(arm["pooled"]),
        "pooled_sealed": float(sealed_block["pooled"]),
        "pooled_abs_diff": abs(float(arm["pooled"]) - float(sealed_block["pooled"])),
        "max_abs_diff_per_quantity": max(v["abs_diff"] for v in per_q.values()),
        "band_conjunctive_reproduced": float(arm["band"]["conjunctive"]),
        "band_conjunctive_sealed": float(sealed_block["band"]["conjunctive"]),
        "per_quantity": per_q,
    }


def oof_frame(
    pilot: dict[str, Any], row_folds: npt.NDArray[np.int64], z_oof: Array
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """The interface file, with each fold post-processed under ITS OWN training-row threshold."""
    raw = natural(HEADS, z_oof)
    pred = np.full_like(raw, np.nan)
    stems = pilot["y"][:, HEADS.index("stems_per_patch")]
    reports = {}
    for f in np.unique(row_folds):
        test = row_folds == f
        thr = treeless_threshold(stems[~test])
        pred[test], rep = postprocess(raw[test], HEADS, thr)
        reports[int(f)] = {"treeless_below": thr, **rep.as_dict()}
    frame = pilot["frame"]
    treeless = np.isnan(pred[:, HEADS.index("height_p50")])
    cols: dict[str, Any] = {
        "cell": frame["cell"].cast(pl.Int64),
        "point": frame["point"],
        "tile": pl.Series(
            "tile", spatial_blocks(frame["lon"].to_numpy(), frame["lat"].to_numpy(), 15.0)
        ),
        "fold": pl.Series("fold", row_folds.astype(np.int64)),
        "lon": frame["lon"],
        "lat": frame["lat"],
        "pred_treeless": pl.Series("pred_treeless", treeless),
    }
    cols |= {f"pred_{h}": pl.Series(f"pred_{h}", pred[:, j]) for j, h in enumerate(HEADS)}
    cols |= {f"raw_{h}": pl.Series(f"raw_{h}", raw[:, j]) for j, h in enumerate(HEADS)}
    return pl.DataFrame(cols), reports


# ------------------------------------------------------------------------------------------------
# The envelope: where a prediction is an interpolation among the pilot's climates, and where not.
# ------------------------------------------------------------------------------------------------
def _standardiser(stats: dict[str, dict[str, float]]) -> tuple[Array, Array, npt.NDArray[np.bool_]]:
    mu = np.array([stats[f]["mean"] for f in FEATURES])
    sd = np.array([stats[f]["sd"] for f in FEATURES])
    return mu, sd, np.isfinite(sd) & (sd > 0)


def _z(x: Array, mu: Array, sd: Array, use: npt.NDArray[np.bool_]) -> Array:
    z = (x[:, use] - mu[use]) / sd[use]
    # A missing feature (an unknown soil code) is placed AT the pilot mean, so it adds no distance
    # rather than an arbitrary one. The count of such rows is reported beside the distances.
    return np.where(np.isfinite(z), z, 0.0)


def nn_rms(query: Array, ref: Array, chunk: int = 2048) -> Array:
    """RMS-per-feature Euclidean distance from each query row to its nearest reference row."""
    rn = (ref**2).sum(axis=1)
    out = np.empty(query.shape[0])
    for s in range(0, query.shape[0], chunk):
        b = query[s : s + chunk]
        d2 = (b**2).sum(axis=1)[:, None] + rn[None, :] - 2.0 * (b @ ref.T)
        out[s : s + chunk] = np.sqrt(np.maximum(d2.min(axis=1), 0.0) / query.shape[1])
    return out


def outside(x: Array, lo: Array, hi: Array) -> npt.NDArray[np.bool_]:
    with np.errstate(invalid="ignore"):
        return np.asarray((x < lo) | (x > hi))


def _q(v: Array) -> dict[str, float]:
    v = v[np.isfinite(v)]
    return {f"p{round(q * 100)}": float(np.quantile(v, q)) for q in QUANTILES} if v.size else {}


def oof_reference(
    pilot: dict[str, Any], row_folds: npt.NDArray[np.int64], em: EquilibriumMap
) -> dict[str, Any]:
    """The distances at which the sealed skill was MEASURED: held-out row to its training folds.

    On the final map's scale (all-pilot mean and sd), so the legs' distances compare directly.
    """
    mu, sd, use = _standardiser(em.stats)
    x = pilot["x"]
    dist = np.empty(x.shape[0])
    n_out = np.empty(x.shape[0], dtype=np.int64)
    for f in np.unique(row_folds):
        te = row_folds == f
        dist[te] = nn_rms(_z(x[te], mu, sd, use), _z(x[~te], mu, sd, use))
        lo, hi = np.nanmin(x[~te], axis=0), np.nanmax(x[~te], axis=0)
        n_out[te] = outside(x[te], lo, hi).sum(axis=1)
    return {
        "dist": dist,
        "summary": {
            "basis": "each pilot row to the nearest row of the OTHER four sealed 15-degree folds",
            "nn_dist": _q(dist),
            "share_rows_any_feature_outside_training_folds": float((n_out > 0).mean()),
        },
    }


def leg_envelope(
    x: Array,
    *,
    lat: Array,
    treed: npt.NDArray[np.bool_],
    em: EquilibriumMap,
    ref: Array,
    pilot_x: Array,
    pilot_lat: Array,
) -> tuple[Array, npt.NDArray[np.int64], dict[str, Any]]:
    mu, sd, use = _standardiser(em.stats)
    dist = nn_rms(_z(x, mu, sd, use), _z(pilot_x, mu, sd, use))
    lo = np.array([em.stats[f]["min"] for f in FEATURES])
    hi = np.array([em.stats[f]["max"] for f in FEATURES])
    out = outside(x, lo, hi)
    n_out = out.sum(axis=1).astype(np.int64)
    ref_q = _q(ref)
    by_feature = {f: float(out[treed, j].mean()) for j, f in enumerate(FEATURES)}
    top = dict(sorted(by_feature.items(), key=lambda kv: -kv[1])[:12])

    def block(m: npt.NDArray[np.bool_]) -> dict[str, Any]:
        if not m.any():
            return {"cells": 0}
        return {
            "cells": int(m.sum()),
            "share_any_feature_outside": float((n_out[m] > 0).mean()),
            "nn_dist": _q(dist[m]),
            **{f"share_nn_beyond_oof_{k}": float((dist[m] > v).mean()) for k, v in ref_q.items()},
        }

    bands = {}
    for lo_b, hi_b in itertools.pairwise(LAT_BANDS):
        m = (lat >= lo_b) & (lat < hi_b)
        bands[f"{lo_b:+.0f}..{hi_b:+.0f}"] = {
            "all": block(m),
            "tree_bearing": block(m & treed),
            "pilot_cells": int(((pilot_lat >= lo_b) & (pilot_lat < hi_b)).sum()),
        }
    summary = {
        "all_cells": block(np.ones_like(treed)),
        "tree_bearing": block(treed),
        "rows_with_missing_feature": int((~np.isfinite(x)).any(axis=1).sum()),
        "top_features_outside_range_share_of_tree_bearing": top,
        "by_latitude_band": bands,
    }
    return dist, n_out, summary


def _parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--climate-version", default="v0")
    ap.add_argument("--legs", nargs="+", default=list(WINDOWS))
    ap.add_argument(
        "--state-table",
        default=None,
        help="the 78-column decoded state table; default exp/X-pilot-decode-v2corpus/state_<v>",
    )
    ap.add_argument("--workers", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
    ap.add_argument("--force", action="store_true", help="overwrite an existing saved map")
    return ap.parse_args()


def main() -> int:  # noqa: PLR0915 -- one linear build, every check reported in one place
    args = _parse()
    t0 = time.time()
    out = Path(args.out)
    if (out / "manifest.json").exists() and not args.force:
        raise SystemExit(f"{out} already holds a saved map; pass --force to replace it")
    out.mkdir(parents=True, exist_ok=True)
    cfg = paths()
    root = Path(str(cfg["scratch"]["corpus"]))
    exp_root = Path(str(cfg["scratch"]["exp"]))
    soil_bin = Path(str(cfg["inputs"]["soil"]))
    state_table = Path(
        args.state_table or exp_root / "X-pilot-decode-v2corpus" / f"state_{args.version}.parquet"
    )
    sealed_metrics = json.loads((exp_root / SEALED_EXP / "metrics.json").read_text("utf-8"))
    report: dict[str, Any] = {"workers": args.workers, "cpus_visible": len(os.sched_getaffinity(0))}

    pilot = load_pilot(root, args.version, state_table, soil_bin)
    x, y = pilot["x"], pilot["y"]
    print(f"x {x.shape}, y {y.shape}, {len(pilot['points'])} climates per cell", flush=True)
    report["inputs_vs_sealed_load"] = check_inputs(pilot, soil_bin)
    report["climate_tables"] = check_climate_tables(pilot, root / args.climate_version)
    print(
        "inputs bit-identical to the sealed load(); climate check "
        f"{report['climate_tables']['historical_vs_pilot_control']}",
        flush=True,
    )

    n_p = len(pilot["points"])
    folds = {
        d: np.repeat(
            blocked_spatial_folds(pilot["lon"], pilot["lat"], k=5, degrees=d, seed=42), n_p
        )
        for d in (15.0, 5.0)
    }
    n22 = len(SEALED_HEADS)

    # 1. The out-of-fold fit of every head, and the sealed number from its first 22.
    t = time.time()
    z_oof = fit_out_of_fold(x, y, folds[15.0], workers=args.workers)
    report["seconds_oof_all_heads"] = time.time() - t
    report["reproduction_15deg"] = reproduce(
        z_oof[:, :n22], pilot, soil_bin, sealed_metrics["by_blocking"]["15deg"]["model"]
    )
    print(
        f"15 deg: {report['reproduction_15deg']['pooled_reproduced']:.9f} vs sealed "
        f"{report['reproduction_15deg']['pooled_sealed']:.9f}",
        flush=True,
    )

    # 2. Determinism: the identical fit again.
    again = fit_out_of_fold(x, y[:, :n22], folds[15.0], heads=SEALED_HEADS, workers=args.workers)
    report["determinism_same_fit_twice"] = same(z_oof[:, :n22], again)
    print(f"same fit twice: {report['determinism_same_fit_twice']}", flush=True)

    # 3. The sensitivity blocking, 5 degrees.
    z5 = fit_out_of_fold(x, y[:, :n22], folds[5.0], heads=SEALED_HEADS, workers=args.workers)
    report["reproduction_5deg"] = reproduce(
        z5, pilot, soil_bin, sealed_metrics["by_blocking"]["5deg"]["model"]
    )
    print(
        f" 5 deg: {report['reproduction_5deg']['pooled_reproduced']:.9f} vs sealed "
        f"{report['reproduction_5deg']['pooled_sealed']:.9f}",
        flush=True,
    )

    # 4. The sealed script's own fit, at LightGBM's default thread count on THIS allocation.
    _, xs, ys, _, _, _, _ = sealed.load(pl.read_parquet(pilot["table"]), soil_bin)
    t = time.time()
    folds15_cells = folds[15.0][::n_p]
    z_sealed_code = sealed.fit_predict_oof(xs, ys, folds15_cells, sealed.QUANTITIES)
    report["sealed_code_default_threads"] = {
        "threads": "LightGBM default = OpenMP default on this allocation",
        "cpus_visible": len(os.sched_getaffinity(0)),
        "seconds": time.time() - t,
        "vs_this_module_one_thread": same(z_sealed_code.reshape(-1, n22), z_oof[:, :n22]),
        "skill": reproduce(
            z_sealed_code.reshape(-1, n22),
            pilot,
            soil_bin,
            sealed_metrics["by_blocking"]["15deg"]["model"],
        ),
    }
    print(
        "sealed code at default threads: "
        f"{report['sealed_code_default_threads']['vs_this_module_one_thread']}",
        flush=True,
    )

    # 5. The interface file.
    oof, post_reports = oof_frame(pilot, folds[15.0], z_oof)
    oof.write_parquet(out / "oof_pilot.parquet")
    report["oof_postprocess_per_fold"] = post_reports
    print(f"wrote {out / 'oof_pilot.parquet'} {oof.shape}", flush=True)

    # 6. The final map on all 6,000 rows, saved, reloaded, and checked against itself.
    t = time.time()
    em = EquilibriumMap().fit(x, y, workers=args.workers)
    report["seconds_final_fit"] = time.time() - t
    basis = {
        "what": "climate-only equilibrium map, fitted on every row of the pilot corpus",
        "corpus": args.version,
        "training_table": str(pilot["table"]),
        "training_table_sha256": _sha256(pilot["table"]),
        "state_table": str(state_table),
        "state_table_sha256": _sha256(state_table),
        "rows": int(x.shape[0]),
        "cells": len(pilot["cells"]),
        "climates_per_cell": n_p,
        "seeds": 1,
        "reference": "LPJmL-FIT 5.6.004 (binary 2026-08-12), 1000-yr single-cell spin-ups, "
        "npatch 25, tree PFTs only, CO2 constant at 276.59 ppm, end-of-spin-up restart",
        "soil": {"file": str(soil_bin), "adapter": "scripts/screen_d95max.py:soil_columns"},
        "recipe": f"the sealed recipe of {SEALED_EXP} for the 22 scored heads; extra heads dev",
        "code_commit": _git("rev-parse", "HEAD"),
        "code_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "prereg_sha256_stamped_by_launcher": os.environ.get("VEGEMU_PREREG_SHA256", ""),
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    em.save(out, basis=basis)
    back = EquilibriumMap.load(out)
    back.predict_threads = em.predict_threads = args.workers
    report["reload"] = {
        "text_roundtrip_max_abs": em.text_roundtrip_max_abs,
        "loaded_vs_fitted_on_pilot": same(back.predict_raw(x), em.predict_raw(x)),
        "treeless_below": back.treeless_below,
    }
    assert report["reload"]["loaded_vs_fitted_on_pilot"]["identical"], "reload changed predictions"
    print(f"saved and reloaded: {report['reload']}", flush=True)

    # 7. Every land cell, each leg, with the envelope beside it.
    ref = oof_reference(pilot, folds[15.0], back)
    envelope: dict[str, Any] = {"oof_reference": ref["summary"], "legs": {}}
    v0 = root / args.climate_version
    hist_state = pl.read_parquet(v0 / "state_historical_seed1.parquet").sort("cell")
    tall = sum(
        hist_state[c].to_numpy() for c in ("hbin_5_10", "hbin_10_20", "hbin_20_30", "hbin_30p")
    )
    treed_by_cell = dict(
        zip(hist_state["cell"].to_list(), (hist_state["stems_total"] > 0).to_list(), strict=True)
    )
    envelope["tree_bearing_basis"] = {
        "definition": "stems_total > 0 in corpus v0 state_historical_seed1 "
        "(restart_1999, transient-CO2 history)",
        "cells_any_stem": int((hist_state["stems_total"] > 0).sum()),
        "cells_any_stem_over_5m": int((tall > 0).sum()),
    }
    for leg in args.legs:
        t = time.time()
        clim = with_soil(pl.read_parquet(v0 / f"climate_{leg}.parquet").sort("cell"), soil_bin)
        xl = feature_matrix(clim)
        pred, rep = back.predict(xl)
        treed = np.array([treed_by_cell.get(int(c), False) for c in clim["cell"].to_list()])
        lat = clim["lat"].to_numpy().astype(np.float64)
        dist, n_out, env = leg_envelope(
            xl, lat=lat, treed=treed, em=back, ref=ref["dist"], pilot_x=x, pilot_lat=pilot["lat"]
        )
        treeless = np.isnan(pred[:, HEADS.index("height_p50")])
        env["predicted_treeless_share"] = {
            "all_cells": float(treeless.mean()),
            "tree_bearing": float(treeless[treed].mean()),
        }
        env["postprocess"] = rep.as_dict()
        frame = pl.DataFrame(
            {
                "cell": clim["cell"].cast(pl.Int64),
                "lon": clim["lon"],
                "lat": clim["lat"],
                "pred_treeless": treeless,
                **{f"pred_{h}": pred[:, j] for j, h in enumerate(HEADS)},
                "env_nn_dist": dist,
                "env_n_outside": n_out,
            }
        )
        frame.write_parquet(out / f"pred_{leg}.parquet")
        env["climate_table"] = str(v0 / f"climate_{leg}.parquet")
        env["climate_table_sha256"] = _sha256(v0 / f"climate_{leg}.parquet")
        env["window"] = WINDOWS[leg].describe()
        env["seconds"] = time.time() - t
        envelope["legs"][leg] = env
        print(
            f"{leg}: {frame.height} cells, treeless {treeless.mean():.3f}, "
            "any feature outside (tree-bearing) "
            f"{env['tree_bearing']['share_any_feature_outside']:.3f}, "
            f"nn p50 {env['tree_bearing']['nn_dist'].get('p50', float('nan')):.3f} vs oof p50 "
            f"{ref['summary']['nn_dist']['p50']:.3f}",
            flush=True,
        )

    (out / "envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    report["basis"] = basis
    report["seconds_total"] = time.time() - t0
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out / 'report.json'} in {report['seconds_total']:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
