#!/usr/bin/env python
"""Synthesise pilot restarts for climates the cell was never run under, and check them in the C.

    scripts/synth_pilot.py --stage bank      --workers 32   # stem bank, buffer check, type rules
    scripts/synth_pilot.py --stage synth     --arm oracle --workers 32
    scripts/synth_pilot.py --stage synth     --arm map    --workers 32
    scripts/synth_pilot.py --stage t2-prep                   # configs + manifests, 1 model year
    scripts/synth_pilot.py --stage t2-decode                  # decode year 1, the diagnostics
    scripts/synth_pilot.py --stage t3-prep                   # manifests for 30 years, NOT launched

THE QUESTION. The pilot spun every one of 200 cells up under 30 climates. Take a cell's CONTROL
restart as the template and ask the synthesiser for the forest of each of its 29 OTHER climates --
a climate that cell's template never saw -- then hand the file to the real model under that
climate's own forcing. This is Product A's hardest case, run where the answer is known.

TWO ARMS, and the difference between them is the point:
  oracle   the target state is the TRUE state of that (cell, climate). Whatever is lost here is
           the synthesiser's own loss: the prediction is perfect by construction.
  map      the target state is the climate-only equilibrium map's out-of-fold prediction
           (`models/equimap-v1/oof_pilot.parquet`, produced by another stream).
And the null every number is read against: the CONTROL forest, copied unchanged -- "the climate
changed and the forest did not". t2 also runs the TRUE restart of each target for the same year, so
year-1 numbers have a year-1 truth and the model's own one-year mortality as a baseline.

WHAT IS DERIVED FROM THE TARGET CLIMATE, never copied from the template:
  * the climate buffer, replayed from the target's own forcing (`vegemu.models.climbuf`), and
    checked exactly against every pilot restart in the bank stage;
  * the admissible tree types, from the model's own bioclimatic limits under that buffer;
  * the donors, by climate analogue from cells OUTSIDE the target's spatial fold.

⚠ EVERY NUMBER THIS WRITES IS A DEV DIAGNOSTIC, not a skill claim: no pre-registered null bar is
attached, the t2 sample is 40 of 200 cells at 3 of 29 climates, and the pilot is 200 of the
54,020 tree-bearing cells. The folds are the experiments' own (5 folds, 15-degree tiles, seed 42).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import sys
import time
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.spatial import cKDTree

from vegemu.binfmt.restart import (
    PFT_TREE_BYTES,
    RestartReader,
    RestartWriter,
    read_cell,
    trees_of,
    write_cell,
)
from vegemu.corpus.state import summarise_cell
from vegemu.models import climbuf as cb
from vegemu.models.synth import (
    NTREE_TYPES,
    choose_analogue_runs,
    pool_from_rows,
    synthesise_cell,
)
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths
from vegemu.score import blocked_spatial_folds

Array = npt.NDArray[np.float64]

VERSION = "pilot-v2-constco2"
SEED = 1
CONTROL = "control"
FOLDS_K, FOLDS_DEGREES, FOLDS_SEED = 5, 15.0, 42
FORCING_FILES: dict[str, str] = {
    "temp": "tas_pert.clm",
    "prec": "pr_pert.clm",
    "swdown": "rsds_pert.clm",
    "lwnet": "lwnet_pert.clm",
}
ARMS: tuple[str, ...] = ("oracle", "map")
MAP_OOF = ("equimap-v1", "oof_pilot.parquet")

# The quantities the synthesiser consumes; everything else in a prediction is only scored.
CONSUMED: tuple[str, ...] = (
    "stems_per_patch",
    "height_p10",
    "height_p50",
    "height_p90",
    "wooddens_p10",
    "wooddens_p50",
    "wooddens_p90",
    "soilc",
)
SHARE_COLUMNS: tuple[str, ...] = tuple(f"pft_frac_{t}" for t in range(NTREE_TYPES))
# Reported at year 0 and year 1. Levels, each compared with the truth of the same (cell, climate).
DIAG_QUANTITIES: tuple[str, ...] = (
    "stems_per_patch",
    "agb",
    "vegc",
    "lai",
    "soilc",
    "litterc",
    "height_p10",
    "height_p50",
    "height_p90",
    "wooddens_p10",
    "wooddens_p50",
    "wooddens_p90",
    "sla_p50",
    "D95max_p50",
    "longevity_p50",
)

# ⚠ THE TYPE RULE, CHOSEN ON THE BANK STAGE'S EVIDENCE (`evidence.json`, `rule_evidence`): survive()
# on the target's end-of-spin-up buffer AND establish() possible in at least one year of the
# replayed spin-up. Over all 6,000 pilot runs against their own true rosters it keeps 99.78 % of
# true stems and 97.6 % of true (run, type) pairs while admitting 4.0 % of the absent ones; the
# data alternative (any of the 10 climatically nearest training runs holds the type) keeps 99.93 %
# of stems but admits 24 % of absent types. Every stem it drops (6,345 of 2.92 M) is of a type
# whose survive() FAILS on that run's own buffer -- recruits the model kills in the next annual
# step (6,336 boreal needleleaved summergreen, whose 30 K warmest-minus-coldest range is not met).
# No temperature-stress cut: types ARE present at a mean stress mortality of 1.0 (recruits that
# die the next year, replaced every year), and a cut at 0.5 drops the type recall to 91.5 %.
ADMIT_MIN_ESTABLISH_FRAC = 1e-9  # "in at least one year"
ADMIT_MAX_MORT_TEMP = 1.0

# ⚠ THE LITTER RULE, CHOSEN ON THE BANK STAGE'S EVIDENCE (`evidence.json`, `litter_evidence`): scale
# the template's litter by predicted / template SOIL carbon. With the true ratio, over 5,362
# perturbed pilot runs with litter, it gives a median |relative error| of 0.217 and 27.6 % within
# 10 %, against 0.289 and 21.2 % for copying the litter unchanged. Scaling by vegetation carbon,
# above-ground biomass or leaf area is WORSE than copying (0.40, 0.41, 0.31), although litter
# correlates with each across the pilot (log-log r 0.85, 0.85; soil 0.83): across climates at one
# cell, litter follows the soil, not the standing forest. A modest gain, and it is disclosed so.
LITTER_RULE = "soilc"

# The t2 sample. Points by design value: the hottest and coldest perturbations, and pure +4 K.
T2_POINTS: tuple[str, ...] = ("lhs14", "lhs02", "core_t+4_p10")
T2_CELL_STRIDE = 5  # every 5th pilot cell by id -> 40 of 200
T3_SHARD = 250  # members per t3 manifest, i.e. per SLURM job -- the pilot's own shard size


# ------------------------------------------------------------------------------------------------
# Paths. Every one derived from config/paths.yaml; none written here.
# ------------------------------------------------------------------------------------------------
def _scratch(kind: str) -> Path:
    return Path(str(paths()["scratch"][kind]))


def pilot_run_dir(cell: int, point: str) -> Path:
    return _scratch("runs") / VERSION / f"c{cell}" / point


def pilot_restart(cell: int, point: str) -> Path:
    return pilot_run_dir(cell, point) / "restart" / f"restart_c{cell}-{point}-s{SEED}.lpj"


def pilot_config(cell: int, point: str) -> Path:
    return pilot_run_dir(cell, point) / f"lpjml_spinup_c{cell}-{point}-s{SEED}.js"


def forcing_files(cell: int, point: str) -> dict[str, Path]:
    base = _scratch("root") / "forcing" / VERSION / f"c{cell}" / point
    return {k: base / v for k, v in FORCING_FILES.items()}


def out_dir() -> Path:
    d = _scratch("exp") / "T-synth-pilot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bank_dir() -> Path:
    d = out_dir() / "bank"
    d.mkdir(parents=True, exist_ok=True)
    return d


def arm_dir(arm: str) -> Path:
    return _scratch("runs") / f"synth-pilot-{arm}"


def synth_restart_path(arm: str, cell: int, point: str) -> Path:
    return arm_dir(arm) / f"c{cell}" / point / "restart" / f"restart_c{cell}-{point}-{arm}.lpj"


def state_table() -> pl.DataFrame:
    return pl.read_parquet(
        _scratch("exp") / "X-pilot-decode-v2corpus" / f"state_{VERSION}.parquet"
    ).with_columns(pl.col("cell").cast(pl.Int64))


def corpus_features() -> pl.DataFrame:
    """Climate features and coordinates per (cell, point). The STATE comes from `state_table`."""
    frame = pl.read_parquet(_scratch("corpus") / VERSION / "corpus.parquet")
    return frame.select(["cell", "point", "lon", "lat", *ANALOGUE_FEATURES]).with_columns(
        pl.col("cell").cast(pl.Int64)
    )


def cell_table() -> pl.DataFrame:
    """One row per pilot cell with its fold, derived exactly as the experiments derive it."""
    first = corpus_features().filter(pl.col("point") == CONTROL).sort("cell")
    folds = blocked_spatial_folds(
        first["lon"].to_numpy().astype(np.float64),
        first["lat"].to_numpy().astype(np.float64),
        k=FOLDS_K,
        degrees=FOLDS_DEGREES,
        seed=FOLDS_SEED,
    )
    return first.select(["cell", "lon", "lat"]).with_columns(pl.Series("fold", folds))


def points_of() -> list[str]:
    pts = state_table().filter(pl.col("cell") == pl.col("cell").min())["point"].to_list()
    return [CONTROL, *sorted(p for p in pts if p != CONTROL)]


# ------------------------------------------------------------------------------------------------
# Stage: bank. One pass over all 6,000 pilot runs.
# ------------------------------------------------------------------------------------------------
def _tree_rows(rec: dict[str, Any]) -> npt.NDArray[np.uint8]:
    parts = []
    for patch in rec["stands"][0]["patches"]:
        pft = patch["pftlist"]
        offs = pft["tree_offsets"]
        if offs.size:
            buf = np.frombuffer(pft["raw"], dtype=np.uint8)
            parts.append(buf[offs[:, None] + np.arange(PFT_TREE_BYTES, dtype=np.int64)[None, :]])
    return np.concatenate(parts) if parts else np.zeros((0, PFT_TREE_BYTES), dtype=np.uint8)


def template_climate(cell: int, lat: float) -> tuple[dict[str, Any], Array, float, float]:
    """The control run's record, its effective albedo, its aetp_mean and its stand fraction."""
    rec = RestartReader(pilot_restart(cell, CONTROL)).read(0)
    frac = float(rec["stands"][0]["frac"])
    f = cb.read_forcing(forcing_files(cell, CONTROL), cell, lat)
    alb = cb.effective_albedo(rec["climbuf"], f, stand_frac=frac)
    return rec, alb, float(rec["climbuf"]["scalars"][3]), frac


def _bank_cell(args: tuple[int, float, list[str]]) -> list[dict[str, Any]]:
    cell, lat, points = args
    _, alb_ctrl, aetp_ctrl, _ = template_climate(cell, lat)
    rows: list[dict[str, Any]] = []
    raws: list[npt.NDArray[np.uint8]] = []
    start = 0
    for point in points:
        reader = RestartReader(pilot_restart(cell, point))
        rec = reader.read(0)
        real = rec["climbuf"]
        frac = float(rec["stands"][0]["frac"])
        f = cb.read_forcing(forcing_files(cell, point), cell, lat)
        own = cb.effective_albedo(real, f, stand_frac=frac)
        ours, trace = cb.climate_buffer_from_forcing(
            f, albedo=own, aetp_mean=float(real["scalars"][3]), stand_frac=frac
        )
        derived, _ = cb.climate_buffer_from_forcing(
            f, albedo=alb_ctrl, aetp_mean=aetp_ctrl, stand_frac=frac
        )
        verdict = cb.bioclimatic_verdict(f, trace)
        recent = {w: cb.bioclimatic_verdict(f, trace, window=w) for w in (30, 200)}
        stems = _tree_rows(rec)
        raws.append(stems)
        ids = stems[:, 0].astype(np.int64) if stems.size else np.zeros(0, dtype=np.int64)
        row: dict[str, Any] = {
            "cell": cell,
            "point": point,
            "start": start,
            "count": int(stems.shape[0]),
            "seed_match": bool(tuple(trace.seed_after) == tuple(reader.restart.seed)),
            "err_exact": cb.compare_climbuf(ours, real),
            "err_from_control": cb.compare_climbuf(derived, real),
            "tmin20": verdict.temp_min20,
            "tmax20": verdict.temp_max20,
        }
        for t in range(NTREE_TYPES):
            row[f"n_type_{t}"] = int(np.count_nonzero(ids == t))
            row[f"surv_{t}"] = bool(verdict.survive_final[t])
            row[f"est_{t}"] = float(verdict.establish_window_frac[t])
            for w, v in recent.items():
                row[f"est{w}_{t}"] = float(v.establish_window_frac[t])
            row[f"mort_{t}"] = float(verdict.mort_temp_mean[t])
        rows.append(row)
        start += int(stems.shape[0])
    blob = np.concatenate(raws) if raws else np.zeros((0, PFT_TREE_BYTES), dtype=np.uint8)
    np.save(bank_dir() / f"c{cell}.npy", blob)
    return rows


def _buffer_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Max absolute and relative residual per field, over every run, both derivations."""

    def worst(key: str, runs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        fields = runs[0][key].keys()
        return {
            f: {
                "max_abs": float(max(r[key][f]["max_abs"] for r in runs)),
                "max_rel": float(max(r[key][f]["max_rel"] for r in runs)),
                "median_rel": float(np.median([r[key][f]["max_rel"] for r in runs])),
            }
            for f in fields
        }

    perturbed = [r for r in rows if r["point"] != CONTROL]
    return {
        "basis": f"{VERSION}, {len(rows)} runs ({len({r['cell'] for r in rows})} cells x "
        f"{len({r['point'] for r in rows})} climates), seed {SEED}, end-of-spin-up buffer",
        "seed_state_matches_header": int(sum(r["seed_match"] for r in rows)),
        "n_runs": len(rows),
        "replayed_with_own_albedo": worst("err_exact", rows),
        "derived_for_perturbed_targets_from_control": {
            "what": "the synthesiser's buffer: target forcing, control albedo, control aetp_mean",
            "n_runs": len(perturbed),
            "fields": worst("err_from_control", perturbed),
        },
    }


def _data_rule(runs: pl.DataFrame, k: int = 10) -> npt.NDArray[np.bool_]:
    """A type is allowed if any of the k climatically nearest TRAINING runs holds it."""
    feats = corpus_features()
    frame = runs.join(feats, on=["cell", "point"], how="left")
    z = frame.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)
    fold = frame["fold"].to_numpy()
    counts = frame.select([f"n_type_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    out = np.zeros((frame.height, NTREE_TYPES), dtype=bool)
    for f in np.unique(fold):
        tr, te = fold != f, fold == f
        mu, sd = z[tr].mean(axis=0), z[tr].std(axis=0)
        tree = cKDTree((z[tr] - mu) / sd)
        _, idx = tree.query((z[te] - mu) / sd, k=k)
        near = counts[tr][np.asarray(idx, dtype=np.int64)]  # (n_te, k, 7)
        out[te] = (near > 0).any(axis=1)
    return out


def rule_evidence(runs: pl.DataFrame) -> dict[str, Any]:
    """Which admissibility rule to use, from all 6,000 pilot runs against their true rosters."""
    present = runs.select([f"n_type_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    surv = runs.select([f"surv_{t}" for t in range(NTREE_TYPES)]).to_numpy().astype(bool)
    est = runs.select([f"est_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    mort = runs.select([f"mort_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    has = present > 0

    def score(allowed: npt.NDArray[np.bool_]) -> dict[str, float]:
        stems_ok = float((present * allowed).sum() / present.sum())
        return {
            "stem_recall": stems_ok,
            "type_recall": float((allowed & has).sum() / has.sum()),
            "runs_losing_a_true_type": int((has & ~allowed).any(axis=1).sum()),
            "absent_types_allowed_frac": float((allowed & ~has).sum() / (~has).sum()),
            "mean_types_allowed": float(allowed.sum(axis=1).mean()),
            "mean_types_present": float(has.sum(axis=1).mean()),
        }

    est30 = runs.select([f"est30_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    est200 = runs.select([f"est200_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    data = _data_rule(runs)
    chosen = surv & (est >= ADMIT_MIN_ESTABLISH_FRAC) & (mort <= ADMIT_MAX_MORT_TEMP)
    rules: dict[str, npt.NDArray[np.bool_]] = {
        "template_free_everything": np.ones_like(has),
        "survive_only": surv,
        "survive_and_establish_last_30y": surv & (est30 > 0),
        "survive_and_establish_last_200y": surv & (est200 > 0),
        "survive_and_establish_spinup": surv & (est > 0),
        "survive_and_establish_spinup_and_mort_le_0.5": surv & (est > 0) & (mort <= 0.5),
        "chosen": chosen,
        "data_rule_10_nearest_training_runs": data,
        "chosen_or_data_rule": chosen | data,
    }
    per_type = {}
    for t in range(NTREE_TYPES):
        m = has[:, t]
        per_type[str(t)] = {
            "runs_holding": int(m.sum()),
            "min_establish_frac_where_present": float(est[m, t].min()) if m.any() else None,
            "stems_where_never_establishes": int(present[m & (est[:, t] <= 0), t].sum()),
            "stems_where_survive_fails": int(present[m & ~surv[:, t], t].sum()),
            "stems_total": int(present[:, t].sum()),
            "max_mort_temp_where_present": float(mort[m, t].max()) if m.any() else None,
            "survive_false_where_present": int((m & ~surv[:, t]).sum()),
        }
    return {
        "basis": f"{VERSION}, {runs.height} runs; truth = stems per type in each run's own "
        "end-of-spin-up restart; rule inputs = the buffer replayed from that run's forcing",
        "chosen": {
            "min_establish_frac": ADMIT_MIN_ESTABLISH_FRAC,
            "max_mort_temp": ADMIT_MAX_MORT_TEMP,
        },
        "rules": {name: score(a) for name, a in rules.items()},
        "per_type": per_type,
    }


def litter_evidence(state: pl.DataFrame) -> dict[str, Any]:
    """Which quantity, if any, a template's litter should be rescaled by for a new climate.

    Each rule predicts a perturbed point's litter carbon as the CONTROL's litter times the ratio of
    one TRUE quantity between the point and the control -- i.e. what the rule would deliver with a
    perfect prediction of that quantity. "copy" is the current behaviour (no rescale).
    """
    ctrl = state.filter(pl.col("point") == CONTROL).select(
        [
            "cell",
            *(pl.col(c).alias(f"{c}_ctrl") for c in ("litterc", "soilc", "vegc", "agb", "lai")),
        ]
    )
    pert = state.filter(pl.col("point") != CONTROL).join(ctrl, on="cell")
    pert = pert.filter((pl.col("litterc") > 0) & (pl.col("litterc_ctrl") > 0))
    true = pert["litterc"].to_numpy()
    out: dict[str, Any] = {"basis": f"{VERSION}, {pert.height} perturbed runs with litter > 0"}
    rules: dict[str, Array] = {"copy": pert["litterc_ctrl"].to_numpy()}
    for q in ("soilc", "vegc", "agb", "lai"):
        base = pert[f"{q}_ctrl"].to_numpy()
        ratio = np.where(base > 0, pert[q].to_numpy() / np.where(base > 0, base, 1.0), np.nan)
        rules[q] = pert["litterc_ctrl"].to_numpy() * ratio
    for name, pred in rules.items():
        ok = np.isfinite(pred) & (pred > 0)
        rel = np.abs(pred[ok] - true[ok]) / true[ok]
        out[name] = {
            "n": int(ok.sum()),
            "median_abs_rel_err": float(np.median(rel)),
            "frac_within_10pct": float((rel <= 0.10).mean()),
            "median_log_ratio": float(np.median(np.log(pred[ok] / true[ok]))),
        }
    s = state.filter((pl.col("litterc") > 0) & (pl.col("soilc") > 0))
    out["correlation_log"] = {
        q: float(np.corrcoef(np.log(s["litterc"].to_numpy()), np.log1p(s[q].to_numpy()))[0, 1])
        for q in ("soilc", "vegc", "agb")
    }
    return out


def stage_bank(workers: int) -> int:
    cells = cell_table()
    points = points_of()
    jobs = [(int(c), float(la), points) for c, la in zip(cells["cell"], cells["lat"], strict=True)]
    t0 = time.time()
    rows: list[dict[str, Any]] = []
    with mp.get_context("spawn").Pool(workers) as pool:
        for i, part in enumerate(pool.imap_unordered(_bank_cell, jobs)):
            rows.extend(part)
            if (i + 1) % 20 == 0:
                print(f"  banked {i + 1}/{len(jobs)} cells, {time.time() - t0:.0f} s", flush=True)
    check = _buffer_check(rows)
    (out_dir() / "climbuf_check.json").write_text(json.dumps(check, indent=2))
    flat = pl.DataFrame(
        [{k: v for k, v in r.items() if not k.startswith("err_")} for r in rows]
    ).join(cells.select(["cell", "fold"]), on="cell")
    flat = flat.sort(["cell", "point"])
    flat.write_parquet(bank_dir() / "runs.parquet")
    evidence = {"types": rule_evidence(flat), "litter": litter_evidence(state_table())}
    (out_dir() / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps({"climbuf": check, "evidence": evidence}, indent=2)[:6000])
    return 0


# ------------------------------------------------------------------------------------------------
# Stage: synth.
# ------------------------------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _bank_rows(cell: int) -> npt.NDArray[np.uint8]:
    out: npt.NDArray[np.uint8] = np.load(bank_dir() / f"c{cell}.npy", mmap_mode="r")
    return out


def load_predictions(arm: str) -> pl.DataFrame | None:
    """(cell, point, <quantity>...) on the natural scale, or None if the arm's source is absent."""
    if arm == "oracle":
        return state_table()
    p = _scratch("models").joinpath(*MAP_OOF)
    if not p.exists():
        return None
    frame = pl.read_parquet(p).with_columns(pl.col("cell").cast(pl.Int64))
    if "fold" in frame.columns:
        mine = cell_table().select(["cell", pl.col("fold").alias("fold_here")])
        check = frame.select(["cell", "fold"]).unique().join(mine, on="cell")
        if (check["fold"] != check["fold_here"]).any():
            raise AssertionError("the map's out-of-fold folds differ from the donor folds")
    frame = frame.rename({c: c[len("pred_") :] for c in frame.columns if c.startswith("pred_")})
    if "treeless" in frame.columns:
        # The map's own treeless call: below its threshold it writes NaN traits and shares, so
        # the forest it predicts there is no forest.
        frame = frame.with_columns(
            pl.when(pl.col("treeless") > 0.5)
            .then(0.0)
            .otherwise(pl.col("stems_per_patch"))
            .alias("stems_per_patch")
        )
    return frame


def prediction_row(frame: pl.DataFrame, cell: int, point: str) -> dict[str, float]:
    row = frame.filter((pl.col("cell") == cell) & (pl.col("point") == point))
    if row.height != 1:
        raise KeyError(f"{row.height} prediction rows for c{cell}/{point}")
    out = {}
    for k, v in row.row(0, named=True).items():
        if k in ("cell", "point") or v is None:
            continue
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def analogue_pool(
    runs: pl.DataFrame, target: tuple[int, str], fold: int, wanted: dict[int, int]
) -> tuple[Any, list[tuple[int, str]]]:
    """Donor stems of the wanted types from the climatically nearest runs OUTSIDE the fold."""
    cand = runs.filter(pl.col("fold") != fold)
    tgt = runs.filter((pl.col("cell") == target[0]) & (pl.col("point") == target[1]))
    zc = cand.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)
    mu, sd = zc.mean(axis=0), zc.std(axis=0)
    zt = (tgt.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)[0] - mu) / sd
    counts = cand.select([f"n_type_{t}" for t in range(NTREE_TYPES)]).to_numpy()
    chosen = choose_analogue_runs(zt, (zc - mu) / sd, counts, wanted)
    rows: list[npt.NDArray[np.uint8]] = []
    used: list[tuple[int, str]] = []
    cells = cand["cell"].to_numpy()
    points = cand["point"].to_list()
    starts, sizes = cand["start"].to_numpy(), cand["count"].to_numpy()
    for t, idx in chosen.items():
        for i in idx:
            c = int(cells[i])
            assert c != target[0], "a donor from the target cell itself"
            block = np.asarray(_bank_rows(c)[int(starts[i]) : int(starts[i]) + int(sizes[i])])
            rows.append(block[block[:, 0] == t])
            used.append((c, points[i]))
    if not rows or sum(r.shape[0] for r in rows) == 0:
        return None, used
    folds_used = set(runs.filter(pl.col("cell").is_in([u[0] for u in used]))["fold"].to_list())
    assert fold not in folds_used, "a donor from the target's own spatial fold"
    return pool_from_rows(np.concatenate(rows), tuple(sorted({u[0] for u in used}))), used


def _litter_target(
    rule: str, template_state: dict[str, float], prediction: dict[str, float]
) -> float | None:
    """The litter carbon to rescale to under `rule`, or None to leave the template's.

    `rule` names the quantity whose predicted/template ratio scales the template's litter
    ("soilc", "vegc", "agb", "lai"), or "predicted" (a litter prediction itself), or "none".
    """
    if rule == "none":
        return None
    if rule == "predicted":
        return prediction.get("litterc")
    base, want = template_state.get(rule), prediction.get(rule)
    if not base or want is None or not np.isfinite(want) or base <= 0:
        return None
    return float(template_state["litterc"] * want / base)


def analogue_shares(runs: pl.DataFrame, target: tuple[int, str], fold: int, k: int = 10) -> Array:
    """The species mix of the k climatically nearest runs outside the fold: a data estimate."""
    cand = runs.filter(pl.col("fold") != fold)
    tgt = runs.filter((pl.col("cell") == target[0]) & (pl.col("point") == target[1]))
    zc = cand.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)
    mu, sd = zc.mean(axis=0), zc.std(axis=0)
    zt = (tgt.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)[0] - mu) / sd
    near = np.argsort(np.sqrt((((zc - mu) / sd - zt[None, :]) ** 2).sum(axis=1)))[:k]
    counts = cand.select([f"n_type_{t}" for t in range(NTREE_TYPES)]).to_numpy()[near].sum(axis=0)
    out: Array = counts.astype(np.float64) / max(float(counts.sum()), 1.0)
    return out


def _plan(
    pred: dict[str, float],
    template: dict[str, Any],
    allowed: tuple[int, ...],
    *,
    runs: pl.DataFrame,
    target: tuple[int, str],
    fold: int,
) -> tuple[Array | None, str, dict[int, int]]:
    """The share vector handed to the synthesiser, where it came from, and the donors wanted.

    Shares come from the prediction when it carries all seven; else the template's own mix (the
    synthesiser restricts it to `allowed`); else, for a TREELESS template, the mix of the nearest
    climate analogues outside the fold -- never "anything in the pool".
    """
    shares: Array | None = None
    origin = "template"
    if all(c in pred and np.isfinite(pred[c]) for c in SHARE_COLUMNS):
        shares = np.array([pred[c] for c in SHARE_COLUMNS])
        origin = "prediction"
    ids = np.concatenate(
        [np.asarray(trees_of(p["pftlist"])["id"]) for p in template["stands"][0]["patches"]]
    ).astype(np.int64)
    basis = shares
    if basis is None or basis.sum() <= 0:
        basis = np.bincount(ids, minlength=NTREE_TYPES)[:NTREE_TYPES].astype(np.float64)
    if basis.sum() <= 0:
        shares = analogue_shares(runs, target, fold)
        basis, origin = shares, "analogue-10"
    keep = np.zeros(NTREE_TYPES, dtype=bool)
    keep[list(allowed)] = True
    basis = np.where(keep, basis, 0.0)
    n_cell = max(pred.get("stems_per_patch", 0.0), 0.0) * int(template["stands"][0]["npatch"])
    wanted = (
        {
            t: max(1, round(n_cell * basis[t] / basis.sum()))
            for t in range(NTREE_TYPES)
            if basis[t] > 0
        }
        if basis.sum() > 0
        else {}
    )
    return shares, origin, wanted


def _synth_cell(args: tuple[str, int, float, int, list[str]]) -> list[dict[str, Any]]:
    arm, cell, lat, fold, points = args
    runs = _runs_with_features()
    preds = load_predictions(arm)
    assert preds is not None
    reader = RestartReader(pilot_restart(cell, CONTROL))
    template, alb, aetp, frac = template_climate(cell, lat)
    t_state = summarise_cell(template, cell, reader.layout)
    empty = pool_from_rows(np.zeros((0, PFT_TREE_BYTES), dtype=np.uint8), ())
    out: list[dict[str, Any]] = []
    for point in points:
        t0 = time.time()
        row: dict[str, Any] = {"arm": arm, "cell": cell, "point": point, "fold": fold}
        try:
            pred = prediction_row(preds, cell, point)
            n_want = max(pred.get("stems_per_patch", 0.0), 0.0)
            missing = [q for q in CONSUMED if not np.isfinite(pred.get(q, np.nan))]
            if n_want > 0 and missing:
                raise KeyError(f"prediction lacks {missing}")
            f = cb.read_forcing(forcing_files(cell, point), cell, lat)
            buf, trace = cb.climate_buffer_from_forcing(
                f, albedo=alb, aetp_mean=aetp, stand_frac=frac
            )
            allowed = cb.bioclimatic_verdict(f, trace).admissible(
                min_establish_frac=ADMIT_MIN_ESTABLISH_FRAC, max_mort_temp=ADMIT_MAX_MORT_TEMP
            )
            shares, row["shares_origin"], wanted = _plan(
                pred, template, allowed, runs=runs, target=(cell, point), fold=fold
            )
            pool, used = analogue_pool(runs, (cell, point), fold, wanted) if wanted else (None, [])
            if pool is None and n_want > 0 and wanted:
                raise RuntimeError("no analogue donor of any admissible type outside the fold")
            pool = empty if pool is None else pool
            prediction = {q: pred[q] for q in CONSUMED if q in pred}
            lit = _litter_target(LITTER_RULE, t_state, pred)
            if lit is not None:
                prediction["litterc"] = lit
            rec, rep = synthesise_cell(
                template,
                prediction,
                pool,
                reader.layout,
                cell=cell,
                template_cell=cell,
                seed=20260923 + cell * 100 + points.index(point),
                type_shares=shares,
                allowed_types=allowed,
                climbuf=buf,
                rescale_litter=lit is not None,
            )
            dest = synth_restart_path(arm, cell, point)
            dest.parent.mkdir(parents=True, exist_ok=True)
            blob = write_cell(rec, reader.layout)
            with RestartWriter(dest, reader.generic, reader.restart, ncell=1, firstcell=cell) as w:
                w.append(blob)
            back = RestartReader(dest)
            again = back.cell_bytes(0)
            row["t0_roundtrip"] = bool(
                again == blob and write_cell(read_cell(again, back.layout), back.layout) == again
            )
            y0 = summarise_cell(rec, cell, reader.layout)
            row.update({f"y0_{k}": v for k, v in y0.items() if k not in ("cell",)})
            row.update(
                {
                    "status": "ok",
                    "restart": str(dest),
                    "allowed": ",".join(map(str, allowed)),
                    "stems_requested": rep.stems_requested,
                    "stems_placed": rep.stems_placed,
                    "inadmissible_placed": rep.inadmissible_placed,
                    "type_fallbacks": rep.type_fallbacks,
                    "shares_source": rep.shares_source,
                    "share_mass_removed": rep.share_mass_removed,
                    "types_unplaceable": ",".join(map(str, rep.types_unplaceable)),
                    "ladder_source": json.dumps(rep.ladder_source),
                    "soil_scale": rep.soil_scale,
                    "litter_scale": rep.litter_scale,
                    "donor_runs": len(used),
                    "donor_stems": int(pool.n),
                    "shape_source": json.dumps(rep.shape_source),
                    "report": json.dumps(asdict(rep), default=str),
                }
            )
        except Exception as exc:  # reported per target, never absorbed
            row.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        row["seconds"] = time.time() - t0
        row.update({f"ctrl_{k}": v for k, v in t_state.items() if k in DIAG_QUANTITIES})
        out.append(row)
    return out


@lru_cache(maxsize=1)
def _runs_with_features() -> pl.DataFrame:
    runs = pl.read_parquet(bank_dir() / "runs.parquet")
    return runs.join(corpus_features(), on=["cell", "point"], how="left")


def _suffixed(truth: pl.DataFrame) -> pl.DataFrame:
    """The truth with every non-key column renamed `<name>_true`, so no join can shadow it."""
    return truth.rename({c: f"{c}_true" for c in truth.columns if c not in ("cell", "point")})


def _rel_err_table(
    frame: pl.DataFrame, prefix: str, truth: pl.DataFrame, qs: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    """Median |rel err| and the fraction within 10 %, per quantity, on tree-bearing truth rows."""
    j = frame.join(_suffixed(truth), on=["cell", "point"])
    j = j.filter(pl.col("stems_total_true") > 0)
    out: dict[str, dict[str, float]] = {}
    for q in qs:
        col = f"{prefix}{q}"
        if col not in j.columns or f"{q}_true" not in j.columns:
            continue
        p = j[col].to_numpy().astype(np.float64)
        t = j[f"{q}_true"].to_numpy().astype(np.float64)
        ok = np.isfinite(t) & (np.abs(t) > 0)
        p = np.where(np.isfinite(p), p, 0.0)
        rel = np.abs(p[ok] - t[ok]) / np.abs(t[ok])
        out[q] = {
            "n": int(ok.sum()),
            "median_abs_rel_err": float(np.median(rel)) if rel.size else float("nan"),
            "frac_within_10pct": float((rel <= 0.10).mean()) if rel.size else float("nan"),
        }
    return out


def _share_error(frame: pl.DataFrame, prefix: str, truth: pl.DataFrame) -> dict[str, float]:
    """Total-variation distance between the written and the true species mix, tree-bearing rows."""
    cols = [f"{prefix}pft_frac_{t}" for t in range(NTREE_TYPES)]
    j = frame.join(_suffixed(truth), on=["cell", "point"]).filter(
        (pl.col("stems_total_true") > 0) & (pl.col(f"{prefix}stems_total") > 0)
    )
    if j.height == 0:
        return {"n": 0}
    p = j.select(cols).to_numpy().astype(np.float64)
    t = j.select([f"pft_frac_{i}_true" for i in range(NTREE_TYPES)]).to_numpy().astype(np.float64)
    tv = 0.5 * np.abs(np.nan_to_num(p) - np.nan_to_num(t)).sum(axis=1)
    return {"n": int(j.height), "median_tv": float(np.median(tv)), "mean_tv": float(tv.mean())}


def stage_synth(arm: str, workers: int, limit_cells: int | None) -> int:
    preds = load_predictions(arm)
    if preds is None:
        print(f"arm {arm}: prediction source absent ({'/'.join(MAP_OOF)}); nothing to do")
        return 3
    cells = cell_table().sort("cell")
    if limit_cells:
        cells = cells.head(limit_cells)
    points = [p for p in points_of() if p != CONTROL]
    jobs = [
        (arm, int(c), float(la), int(fo), points)
        for c, la, fo in zip(cells["cell"], cells["lat"], cells["fold"], strict=True)
    ]
    t0 = time.time()
    rows: list[dict[str, Any]] = []
    with mp.get_context("spawn").Pool(workers) as pool:
        for i, part in enumerate(pool.imap_unordered(_synth_cell, jobs)):
            rows.extend(part)
            if (i + 1) % 10 == 0:
                print(f"  {arm}: {i + 1}/{len(jobs)} cells, {time.time() - t0:.0f} s", flush=True)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    frame.write_parquet(out_dir() / f"synth_{arm}.parquet")
    return summarise_synth(arm, seconds=time.time() - t0)


def summarise_synth(arm: str, *, seconds: float | None = None) -> int:
    """The year-0 diagnostics of one arm, from its per-target table (re-runnable on its own)."""
    frame = pl.read_parquet(out_dir() / f"synth_{arm}.parquet")
    truth = state_table()
    ok = frame.filter(pl.col("status") == "ok")
    null = truth.filter(pl.col("point") == CONTROL).drop("point")
    null = null.rename({q: f"null_{q}" for q in null.columns if q != "cell"})
    null_rows = frame.select(["cell", "point"]).join(null, on="cell")
    summary = {
        "basis": f"{VERSION}: template = each cell's control restart, targets = its other "
        f"{frame['point'].n_unique()} climates; {frame['cell'].n_unique()} cells; truth = that "
        "(cell, climate)'s own end-of-spin-up state; tree-bearing truth rows only; "
        "DEV DIAGNOSTIC, no null bar",
        "arm": arm,
        "targets": frame.height,
        "synthesised": ok.height,
        "failed": frame.height - ok.height,
        "t0_roundtrip_ok": int(ok["t0_roundtrip"].sum()) if ok.height else 0,
        "inadmissible_stems_total": int(ok["inadmissible_placed"].sum()) if ok.height else 0,
        "type_fallbacks_total": int(ok["type_fallbacks"].sum()) if ok.height else 0,
        "stems_placed_total": int(ok["stems_placed"].sum()) if ok.height else 0,
        "stems_requested_total": int(ok["stems_requested"].sum()) if ok.height else 0,
        "share_mass_removed_mean": float(np.mean(ok["share_mass_removed"].to_numpy()))
        if ok.height
        else 0.0,
        "shares_origin": ok.group_by("shares_origin").len().to_dicts() if ok.height else [],
        "failures_by_error": frame.filter(pl.col("status") != "ok")
        .group_by("error")
        .len()
        .sort("len", descending=True)
        .head(10)
        .to_dicts()
        if "error" in frame.columns
        else [],
        "year0_vs_truth": _rel_err_table(ok, "y0_", truth, DIAG_QUANTITIES),
        "year0_null_copy_control_vs_truth": _rel_err_table(
            null_rows, "null_", truth, DIAG_QUANTITIES
        ),
        "type_share_tv_year0": _share_error(ok, "y0_", truth),
        "type_share_tv_null": _share_error(null_rows, "null_", truth),
        "seconds_total": seconds,
    }
    (out_dir() / f"synth_{arm}_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


# ------------------------------------------------------------------------------------------------
# Stages: t2 and t3 -- the real model from the synthesised file, under the TARGET's forcing.
# ------------------------------------------------------------------------------------------------
def _patch(text: str, pattern: str, repl: str, expect: int = 1) -> str:
    out, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
    if n != expect:
        raise AssertionError(f"pattern {pattern!r} matched {n} times, expected {expect}")
    return out


def from_restart_config(
    target: tuple[int, str],
    restart: Path,
    run_dir: Path,
    *,
    years: tuple[int, int],
    tag: str,
    link: bool = False,
) -> Path:
    """The TARGET run's own spin-up config, switched to its FROM_RESTART branch for `years`.

    Built from the target's config so the forcing, the constant CO2, the cell and every parameter
    are exactly those the target was spun up under; only the run-settings and output blocks of the
    `-DFROM_RESTART` branch change, and each replacement is asserted. The years are the forcing
    file's own (1970-...): the pilot's files cover 1970-1999, so a continuation reads them in
    order, which is also what the last 30 spin-up years did.
    """
    text = pilot_config(*target).read_text(encoding="utf-8")
    cut = text.index('"nspinup" : 0,')
    head, block = text[:cut], text[cut:]
    first, last = years
    block = _patch(block, r'^\s*"firstyear": \d+,.*$', f'  "firstyear": {first},')
    block = _patch(block, r'^\s*"lastyear" : \d+,.*$', f'  "lastyear" : {last},')
    block = _patch(block, r'^\s*"outputyear": \d+,.*$', f'  "outputyear": {first},')
    block = _patch(
        block,
        r'^\s*"restart_filename" : "restart/[^"]+",.*$',
        f'  "restart_filename" : "restart/{restart.name}",',
    )
    block = _patch(
        block,
        r'^\s*"write_restart_filename" : "restart/[^"]+",.*$',
        f'  "write_restart_filename" : "restart/restart_{last}_{tag}.lpj",',
    )
    block = _patch(block, r'^\s*"restart_year": \d+.*$', f'  "restart_year": {last}')
    # Outputs of the FROM_RESTART branch: the per-tree table and monthly NPP are dropped (the state
    # comes from the restart), the three small ones are named after this run.
    head = _patch(head, r'^\s*\{ "id" : "ind",.*$\n', "")
    head = _patch(head, r'^\s*\{ "id" : "npp",.*$\n', "")
    head = _patch(head, r'"output/grid_1999\.nc"', f'"output/grid_{tag}.nc"')
    head = _patch(head, r'"output/globalflux_2000_2019\.csv"', f'"output/globalflux_{tag}.csv"')
    head = _patch(head, r'"output/vegc_2000_2019\.nc"', f'"output/vegc_{tag}.nc"')
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    (run_dir / "restart").mkdir(parents=True, exist_ok=True)
    dest = run_dir / "restart" / restart.name
    if link:
        # t3 prepares 23,200 members: a symlink instead of a 23 GB copy. The model opens the
        # file by name and reads it once, so a link is indistinguishable to it.
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        dest.symlink_to(restart.resolve())
    elif not dest.exists() or dest.stat().st_size != restart.stat().st_size:
        dest.write_bytes(restart.read_bytes())
    cfg = run_dir / f"lpjml_{tag}.js"
    cfg.write_text(head + block, encoding="utf-8")
    return cfg


def _t2_sample() -> list[tuple[int, str]]:
    cells = cell_table().sort("cell")["cell"].to_list()[::T2_CELL_STRIDE]
    return [(int(c), p) for c in cells for p in T2_POINTS]


def _input_restart(arm: str, cell: int, point: str) -> Path:
    if arm == "truth":
        return pilot_restart(cell, point)
    if arm == "null":
        return pilot_restart(cell, CONTROL)
    return synth_restart_path(arm, cell, point)


def _prep(
    kind: str,
    years: tuple[int, int],
    targets: list[tuple[int, str]],
    *,
    shard: int | None = None,
    link: bool = False,
) -> dict[str, Any]:
    """Configs and manifests per arm; `shard` splits each arm's manifest into files of that size,
    because one manifest is one SLURM job with one task per member."""
    base = _scratch("runs") / f"synth-pilot-{kind}"
    manifests: dict[str, Any] = {}
    for arm in ("truth", "null", *ARMS):
        lines: list[str] = []
        skipped = 0
        for cell, point in targets:
            src = _input_restart(arm, cell, point)
            if not src.exists():
                skipped += 1
                continue
            tag = f"{kind}-{arm}"
            rdir = base / arm / f"c{cell}" / point
            cfg = from_restart_config((cell, point), src, rdir, years=years, tag=tag, link=link)
            lines.append(f"{arm}-c{cell}-{point}\t{cfg}\t{rdir}")
        if not lines:
            manifests[arm] = {"members": 0, "skipped": skipped}
            continue
        size = shard or len(lines)
        files = []
        for k in range(0, len(lines), size):
            suffix = f"_s{k // size:02d}" if shard else ""
            man = base / arm / f"manifest_{kind}_{arm}{suffix}.tsv"
            man.parent.mkdir(parents=True, exist_ok=True)
            man.write_text("\n".join(lines[k : k + size]) + "\n")
            files.append(str(man))
        manifests[arm] = {
            "manifest" if not shard else "manifests": files[0] if not shard else files,
            "members": len(lines),
            "skipped": skipped,
        }
    return manifests


def stage_t2_prep() -> int:
    out = _prep("t2", (1970, 1970), _t2_sample())
    (out_dir() / "t2_manifests.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


def stage_t3_prep(nyears: int) -> int:
    cells = cell_table().sort("cell")["cell"].to_list()
    targets = [(int(c), p) for c in cells for p in points_of() if p != CONTROL]
    out = _prep("t3", (1970, 1970 + nyears - 1), targets, shard=T3_SHARD, link=True)
    t2 = out_dir() / "t2_timing.json"
    one_year = json.loads(t2.read_text())["median_seconds_per_run"] if t2.exists() else None
    # The pilot spin-ups' own per-year cost, read off their logs: the marginal year.
    rates = []
    for cell in cells:
        log = pilot_run_dir(int(cell), CONTROL) / f"lpjml.c{cell}-{CONTROL}-s{SEED}.log"
        m = re.search(r"([0-9.]+) sec/cell/year", log.read_text(errors="replace"))
        if m:
            rates.append(float(m.group(1)))
    per_year = float(np.median(rates)) if rates else None
    members = sum(v.get("members", 0) for v in out.values() if isinstance(v, dict))
    out["cost"] = {
        "targets_per_arm": len(targets),
        "members_all_arms": members,
        "years": nyears,
        "t2_median_wall_seconds_one_year_run": one_year,
        "pilot_spinup_median_seconds_per_cell_year": per_year,
        "note": "one core per member; wall per member = (one-year run) + (years - 1) x per-year",
    }
    if one_year is not None and per_year is not None:
        wall = one_year + (nyears - 1) * per_year
        out["cost"]["wall_seconds_per_member"] = wall
        out["cost"]["core_hours"] = members * wall / 3600.0
    (out_dir() / "t3_manifests.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


def _survivors(y0: dict[str, Any], y1: dict[str, Any]) -> tuple[Array, Array]:
    """Per type, stems placed at year 0 and how many of them are alive at year 1.

    A survivor is the same (patch, index, type) one year older. `index` persists (`fread_tree.c`,
    `new_tree.c`), so a recruit can never be mistaken for a survivor.
    """
    placed = np.zeros(NTREE_TYPES)
    alive = np.zeros(NTREE_TYPES)
    p0, p1 = y0["stands"][0]["patches"], y1["stands"][0]["patches"]
    for a, b in zip(p0, p1, strict=True):
        s0, s1 = trees_of(a["pftlist"]), trees_of(b["pftlist"])
        if s0.size == 0:
            continue
        later = {
            (int(i), int(t)): int(g)
            for i, t, g in zip(s1["index"], s1["id"], s1["age"], strict=True)
        }
        for i, t, g in zip(s0["index"], s0["id"], s0["age"], strict=True):
            placed[int(t)] += 1
            if later.get((int(i), int(t))) == int(g) + 1:
                alive[int(t)] += 1
    return placed, alive


def _decode_one(args: tuple[str, int, str]) -> dict[str, Any]:
    arm, cell, point = args
    rdir = _scratch("runs") / "synth-pilot-t2" / arm / f"c{cell}" / point
    name = f"{arm}-c{cell}-{point}"
    log = rdir / f"lpjml.{name}.log"
    row: dict[str, Any] = {"arm": arm, "cell": cell, "point": point}
    text = log.read_text(errors="replace") if log.exists() else ""
    row["success"] = bool(re.search(r"^lpjml successfully terminated", text, flags=re.M))
    m = re.search(r"^Total wall clock time:\s+([0-9.]+)\s+sec", text, flags=re.M)
    row["log_seconds"] = float(m.group(1)) if m else None
    out = rdir / "restart" / f"restart_1970_t2-{arm}.lpj"
    if not (row["success"] and out.exists()):
        return row
    r1 = RestartReader(out)
    y1 = r1.read(0)
    y0 = RestartReader(_input_restart(arm, cell, point)).read(0)
    row.update(
        {f"y1_{k}": v for k, v in summarise_cell(y1, cell, r1.layout).items() if k != "cell"}
    )
    row.update(
        {f"y0_{k}": v for k, v in summarise_cell(y0, cell, r1.layout).items() if k != "cell"}
    )
    placed, alive = _survivors(y0, y1)
    for t in range(NTREE_TYPES):
        row[f"placed_{t}"] = float(placed[t])
        row[f"alive_{t}"] = float(alive[t])
    return row


def stage_t2_decode(workers: int) -> int:
    jobs = [(arm, c, p) for arm in ("truth", "null", *ARMS) for c, p in _t2_sample()]
    with mp.get_context("spawn").Pool(workers) as pool:
        rows = list(pool.imap_unordered(_decode_one, jobs))
    frame = pl.DataFrame(rows, infer_schema_length=None)
    frame.write_parquet(out_dir() / "t2_decoded.parquet")
    truth0 = state_table()
    truth1 = (
        frame.filter((pl.col("arm") == "truth") & pl.col("success"))
        .select(["cell", "point", *[c for c in frame.columns if c.startswith("y1_")]])
        .rename({c: c[3:] for c in frame.columns if c.startswith("y1_")})
    )
    summary: dict[str, Any] = {
        "basis": f"{VERSION}; {len(_t2_sample())} targets = every {T2_CELL_STRIDE}th pilot cell x "
        f"{list(T2_POINTS)}; one model year (1970 of the target's own forcing) from each arm's "
        "restart; year-0 truth = the target's end-of-spin-up state, year-1 truth = the truth arm "
        "after the same year; DEV DIAGNOSTIC, no null bar",
        "arms": {},
    }
    secs = [s for s in frame["log_seconds"].to_list() if s is not None]
    timing = {"median_seconds_per_run": float(np.median(secs)) if secs else None, "n": len(secs)}
    (out_dir() / "t2_timing.json").write_text(json.dumps(timing, indent=2))
    for arm in ("truth", "null", *ARMS):
        a = frame.filter(pl.col("arm") == arm)
        if a.height == 0:
            continue
        ok = a.filter(pl.col("success"))
        entry: dict[str, Any] = {
            "members": a.height,
            "success_line": int(a["success"].sum()),
        }
        if ok.height:
            placed = ok.select([f"placed_{t}" for t in range(NTREE_TYPES)]).to_numpy().sum(axis=0)
            alive = ok.select([f"alive_{t}" for t in range(NTREE_TYPES)]).to_numpy().sum(axis=0)
            entry["year1_death_fraction_by_type"] = {
                str(t): (float(1 - alive[t] / placed[t]) if placed[t] else None)
                for t in range(NTREE_TYPES)
            }
            entry["stems_by_type_year0"] = {str(t): float(placed[t]) for t in range(NTREE_TYPES)}
            entry["year1_death_fraction_all"] = float(1 - alive.sum() / max(placed.sum(), 1))
            entry["year0_vs_truth0"] = _rel_err_table(ok, "y0_", truth0, DIAG_QUANTITIES)
            entry["year1_vs_truth1"] = _rel_err_table(ok, "y1_", truth1, DIAG_QUANTITIES)
            entry["type_share_tv_year0"] = _share_error(ok, "y0_", truth0)
            entry["type_share_tv_year1"] = _share_error(ok, "y1_", truth1)
        summary["arms"][arm] = entry
    summary["timing"] = timing
    (out_dir() / "t2_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stage",
        required=True,
        choices=("bank", "synth", "synth-summary", "t2-prep", "t2-decode", "t3-prep"),
    )
    ap.add_argument("--arm", choices=ARMS, default="oracle")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit-cells", type=int, default=None, help="synth: first N cells only")
    ap.add_argument("--t3-years", type=int, default=30)
    args = ap.parse_args()
    if args.stage == "bank":
        return stage_bank(args.workers)
    if args.stage == "synth":
        return stage_synth(args.arm, args.workers, args.limit_cells)
    if args.stage == "synth-summary":
        return summarise_synth(args.arm)
    if args.stage == "t2-prep":
        return stage_t2_prep()
    if args.stage == "t2-decode":
        return stage_t2_decode(args.workers)
    return stage_t3_prep(args.t3_years)


if __name__ == "__main__":
    raise SystemExit(main())
