"""Product A on the STORED constant-CO2 spin-up: equilibrium vegetation carbon on every cell.

THE QUESTION (owner, 2026-09-24: "for now make the emulator work for the spinup with constant co2";
pass rule chosen the same day: "as good as a rerun"). Shown only a cell's recycled 30-year climate
(1901-1930) and its soil, does the emulator predict that cell's equilibrium vegetation carbon in the
stored global spin-up's constant-CO2 stretch as well as a second run of the original model does?

WHY VEGETATION CARBON ONLY. It is the one per-cell quantity the stored spin-up kept for the
constant-CO2 years (`scripts/spinup_target.py`). Tree counts and traits at the end of that stretch
were never written, so they are tested on the pilot, never here.

TWO TRAINING POOLS, ONE EXPERIMENT EACH (`--pool`):
  pilot   the 200 pilot cells x 30 climates, constant CO2, total VegC window mean of their two
          seeds. The emulator proper: it has never seen the stored run, its protocol (single-cell
          spin-ups), or the 1901-1930 climate of any cell.
  spinup  the stored spin-up's own cells in the other folds, one climate per place. A level map on
          the reference's own protocol; says what the target allows, and nothing about warming.

FOLDS. The sealed pilot folds (5, whole 15-degree tiles, seed 42) define a tile -> fold map; every
global cell takes its tile's fold, so a predicted cell's tile never trains the prediction, under
either pool. A tile with no pilot cell has no fold: it is never scored (the scored set is asserted
to lie inside the map) and, under `spinup`, trains every fold.

THE ESTIMAND, per scored cell (the 56,986 cells with any stem in restart_1999, seed 1):
  truth    T_k = seed k's mean VegC over model years 1450-1699, k = 1, 2
  band     w = max(0.10, s) with s = |H_1 - H_2| / mean(H_1, H_2), H_k = seed k's 1200-1449 mean.
           The spread comes from an EARLIER, disjoint window, so the pair being scored never sets
           its own tolerance (the circularity of `band-test-ceiling.md` section 1).
  pass     |x - T_k| <= w * |T_k|, averaged over k
  frac(x)  the share of scored cells passing; frac(rerun) scores T_2 against T_1 and T_1 against T_2
  D(x)     frac(x) - frac(rerun): the decision statistic, higher is better, 0 = exactly as good as
           a rerun. The emulator is "as good as a rerun" if D >= -0.02 (pre-registered).
REPORTED BESIDE, with the same nulls: frac(x) itself; variance explained on log1p against the
two-seed mean; a flat 10 % band rate; D by latitude band; a 15-degree-tile bootstrap interval on D.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
from lightgbm import LGBMRegressor
from scipy.spatial import cKDTree

from exp_equilibrium_map import FEATURES, load
from exp_model_pilot_response import PARAMS
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import blocked_spatial_folds, spatial_blocks, unit_sphere

Array = npt.NDArray[np.float64]

STATISTIC = "asgood_vegc_spinup"
NULLS: tuple[str, ...] = ("training_mean", "nearest_analogue", "nearest_geographic", "shuffled")
FLOOR = 0.10
SHUFFLE_SEED = 20260924
BOOT = 1000
BOOT_SEED = 7
VEG_THRESHOLD = 1.0
LAT_BANDS: tuple[tuple[float, float], ...] = (
    (-60, -23.5),
    (-23.5, 0),
    (0, 23.5),
    (23.5, 50),
    (50, 90),
)


def _inputs() -> dict[str, object]:
    corpus = Path(str(paths()["scratch"]["corpus"]))
    spin = corpus / "spinup-constco2"
    soil_bin = Path(str(paths()["inputs"]["soil"]))

    clim = pl.read_parquet(spin / "climate_spinup.parquet").sort("cell")
    truth = pl.read_parquet(spin / "spinup_truth.parquet").sort("cell")
    bridge = pl.read_parquet(spin / "bridge_1999.parquet").sort("cell")
    assert (clim["cell"].to_numpy() == truth["cell"].to_numpy()).all()
    assert (bridge["cell"].to_numpy() == truth["cell"].to_numpy()).all()

    frame = pl.read_parquet(corpus / "pilot-v2-constco2" / "corpus.parquet")
    frame_s, x_p, _, _, points, lon_p, lat_p = load(frame, soil_bin)
    cells_p = frame_s["cell"].unique().sort().to_numpy()
    traj = pl.read_parquet(spin / "pilot_trajectory_stats.parquet")
    two = traj.group_by(["cell", "point"]).agg(
        pl.col("vegc_win").mean().alias("y"), pl.len().alias("n")
    )
    assert (two["n"] == 2).all(), "every pilot row must carry both seeds"
    lut = {(int(c), str(p)): float(v) for c, p, v in two.select("cell", "point", "y").iter_rows()}
    y_p = np.array([[lut[(int(c), p)] for p in points] for c in cells_p], dtype=np.float64)
    return {
        "x_g": clim.select(FEATURES).to_numpy().astype(np.float64),
        "lon_g": clim["lon"].to_numpy().astype(np.float64),
        "lat_g": clim["lat"].to_numpy().astype(np.float64),
        "truth": truth,
        "tree_bearing": bridge["tree_bearing"].to_numpy().astype(bool),
        "x_p": x_p,
        "y_p": y_p,
        "points": points,
        "lon_p": lon_p,
        "lat_p": lat_p,
    }


def global_folds(lon_p: Array, lat_p: Array, lon_g: Array, lat_g: Array) -> npt.NDArray[np.int64]:
    """Each global cell takes the sealed pilot fold of its 15-degree tile; -1 if it has none."""
    folds_p = blocked_spatial_folds(lon_p, lat_p, k=5, degrees=15.0, seed=42)
    blocks_p = spatial_blocks(lon_p, lat_p, 15.0)
    tile_fold: dict[int, int] = {}
    for b, f in zip(blocks_p, folds_p, strict=True):
        assert tile_fold.setdefault(int(b), int(f)) == int(f), "a tile split across folds"
    blocks_g = spatial_blocks(lon_g, lat_g, 15.0)
    return np.array([tile_fold.get(int(b), -1) for b in blocks_g], dtype=np.int64)


def _nearest(train: Array, values: Array, query: Array) -> Array:
    return values[cKDTree(train).query(query, k=1)[1]]


def predictions(inp: dict[str, object], pool: str, arm: str) -> dict[str, Array]:
    x_g, lon_g, lat_g = inp["x_g"], inp["lon_g"], inp["lat_g"]
    x_p, y_p, points = inp["x_p"], inp["y_p"], inp["points"]
    truth: pl.DataFrame = inp["truth"]  # type: ignore[assignment]
    assert (
        isinstance(x_g, np.ndarray) and isinstance(x_p, np.ndarray) and isinstance(y_p, np.ndarray)
    )
    n_f = x_p.shape[2]
    folds_p = blocked_spatial_folds(inp["lon_p"], inp["lat_p"], k=5, degrees=15.0, seed=42)  # type: ignore[arg-type]
    folds_g = global_folds(inp["lon_p"], inp["lat_p"], lon_g, lat_g)  # type: ignore[arg-type]
    y_g = ((truth["vegc_win_s1"] + truth["vegc_win_s2"]) / 2).to_numpy().astype(np.float64)
    t_mean = ((truth["vegc_half2_s1"] + truth["vegc_half2_s2"]) / 2).to_numpy().astype(np.float64)
    a_idx = [FEATURES.index(f) for f in ANALOGUE_FEATURES]
    xyz_g = unit_sphere(lon_g, lat_g)  # type: ignore[arg-type]
    xyz_p = unit_sphere(inp["lon_p"], inp["lat_p"])  # type: ignore[arg-type]
    control = points.index("control")  # type: ignore[union-attr]
    rng = np.random.default_rng(SHUFFLE_SEED)

    names = ("model",) if arm == "model" else NULLS
    out = {n: np.full(x_g.shape[0], np.nan) for n in names}
    for f in range(5):
        te = folds_g == f
        if pool == "pilot":
            tr_c = folds_p != f
            x_tr = x_p[tr_c].reshape(-1, n_f)
            y_tr = y_p[tr_c].reshape(-1)
            geo_tr, geo_y = xyz_p[tr_c], y_p[tr_c, control]
        else:
            tr = (folds_g != f) & np.isfinite(y_g)
            x_tr, y_tr = x_g[tr], y_g[tr]
            geo_tr, geo_y = xyz_g[tr], y_g[tr]
        if arm == "model":
            m = LGBMRegressor(**PARAMS)
            m.fit(x_tr, np.log1p(y_tr))
            out["model"][te] = np.clip(np.expm1(m.predict(x_g[te])), 0.0, None)
            print(f"  fold {f}: trained on {y_tr.size} rows, predicted {int(te.sum())}", flush=True)
            continue
        out["training_mean"][te] = np.expm1(np.log1p(y_tr).mean())
        a_tr = x_tr[:, a_idx]
        mu, sd = a_tr.mean(axis=0), a_tr.std(axis=0)
        out["nearest_analogue"][te] = _nearest(
            (a_tr - mu) / sd, y_tr, (x_g[te][:, a_idx] - mu) / sd
        )
        out["nearest_geographic"][te] = _nearest(geo_tr, geo_y, xyz_g[te])
        out["shuffled"][te] = rng.permutation(t_mean[te])
    return out


def _passes(x: Array, t: Array, w: Array) -> Array:
    return (np.abs(x - t) <= w * np.abs(t)).astype(np.float64)


def score(pred: Array, sc: dict[str, Array]) -> dict[str, object]:
    t1, t2, w, tm = sc["t1"], sc["t2"], sc["w"], sc["tm"]
    per_cell = (_passes(pred, t1, w) + _passes(pred, t2, w)) / 2
    frac = float(per_cell.mean())
    d = frac - sc["frac_rerun"]
    lt, lp = np.log1p(tm), np.log1p(pred)
    skill = float(1 - ((lp - lt) ** 2).sum() / ((lt - lt.mean()) ** 2).sum())
    flat = float((np.abs(pred - tm) <= FLOOR * np.abs(tm)).mean())
    bands: dict[str, dict[str, float]] = {}
    for lo, hi in LAT_BANDS:
        sel = (sc["lat"] >= lo) & (sc["lat"] < hi)
        if sel.any():
            bands[f"{lo:g}..{hi:g}"] = {
                "cells": int(sel.sum()),
                "frac": float(per_cell[sel].mean()),
                "D": float(per_cell[sel].mean() - sc["rerun_cell"][sel].mean()),
            }
    tiles = sc["tile"]
    uniq, inv = np.unique(tiles, return_inverse=True)
    rng = np.random.default_rng(BOOT_SEED)
    diff = per_cell - sc["rerun_cell"]
    sums = np.bincount(inv, weights=diff)
    counts = np.bincount(inv).astype(np.float64)
    boot = np.empty(BOOT)
    for b in range(BOOT):
        pick = rng.integers(0, uniq.size, uniq.size)
        boot[b] = sums[pick].sum() / counts[pick].sum()
    return {
        "D": d,
        "frac": frac,
        "skill_log1p": skill,
        "flat10_vs_two_seed_mean": flat,
        "D_tile_bootstrap_p05_p95": [
            float(np.quantile(boot, 0.05)),
            float(np.quantile(boot, 0.95)),
        ],
        "by_latitude": bands,
    }


def scored_set(inp: dict[str, object]) -> dict[str, Array]:
    truth: pl.DataFrame = inp["truth"]  # type: ignore[assignment]
    folds_g = global_folds(inp["lon_p"], inp["lat_p"], inp["lon_g"], inp["lat_g"])  # type: ignore[arg-type]
    g = {c: truth[c].to_numpy().astype(np.float64) for c in truth.columns if c != "vegetated"}
    t1, t2 = g["vegc_half2_s1"], g["vegc_half2_s2"]
    h1, h2 = g["vegc_half1_s1"], g["vegc_half1_s2"]
    sel = np.asarray(inp["tree_bearing"]) & np.isfinite(t1) & np.isfinite(t2)
    sel &= np.isfinite(h1) & np.isfinite(h2)
    outside = int((sel & (folds_g < 0)).sum())
    assert outside == 0, f"{outside} scored cells lie in a tile with no pilot fold"
    hm = (h1 + h2) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(hm > VEG_THRESHOLD, np.abs(h1 - h2) / hm, 0.0)
    w = np.maximum(FLOOR, s)
    rerun_cell = (_passes(t2, t1, w) + _passes(t1, t2, w)) / 2
    lon_g, lat_g = np.asarray(inp["lon_g"]), np.asarray(inp["lat_g"])
    return {
        "mask": sel,
        "t1": t1[sel],
        "t2": t2[sel],
        "tm": ((t1 + t2) / 2)[sel],
        "w": w[sel],
        "lat": lat_g[sel],
        "tile": spatial_blocks(lon_g[sel], lat_g[sel], 15.0),
        "rerun_cell": rerun_cell[sel],
        "frac_rerun": float(rerun_cell[sel].mean()),
        "band_is_floor": float((w[sel] == FLOOR).mean()),
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arm", required=True, choices=("nulls", "model"))
    ap.add_argument("--pool", required=True, choices=("pilot", "spinup"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--exp-id", default="")
    ap.add_argument("--threshold", type=float, default=None)
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    inp = _inputs()
    sc = scored_set(inp)
    mask = sc["mask"].astype(bool)
    preds = predictions(inp, args.pool, args.arm)
    arms = {n: score(p[mask], sc) for n, p in preds.items()}
    rerun_skill = float(
        1
        - ((np.log1p(sc["t2"]) - np.log1p(sc["t1"])) ** 2).sum()
        / ((np.log1p(sc["t1"]) - np.log1p(sc["t1"]).mean()) ** 2).sum()
    )
    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "arm": args.arm,
        "pool": args.pool,
        "statistic": STATISTIC,
        "scored_cells": int(mask.sum()),
        "frac_rerun": sc["frac_rerun"],
        "rerun_skill_log1p_seed2_vs_seed1": rerun_skill,
        "band_is_floor_share": sc["band_is_floor"],
        "features": list(FEATURES),
        # Not "arms": append_result_block writes that key with the bare decision values.
        "arm_details": arms,
    }
    for n, a in arms.items():
        print(f"  {n:20s} D {a['D']:+.6f}  frac {a['frac']:.4f}  skill {a['skill_log1p']:+.4f}")
    print(f"  rerun frac {sc['frac_rerun']:.6f}")
    if args.arm == "model":
        report["decision"] = {
            "D": arms["model"]["D"],
            "threshold": args.threshold,
            "verdict": "pass"
            if args.threshold is not None and arms["model"]["D"] >= args.threshold
            else "fail",
        }
        prior = json.loads((out / "nulls.json").read_text())
        nulls = prior.get("arm_details", prior["arms"])
        report.update(
            append_result_block(
                statistic=STATISTIC,
                arms={
                    "model": float(arms["model"]["D"]),
                    **{n: float(nulls[n]["D"]) for n in NULLS},
                },
                n=int(mask.sum()),
            )
        )
    name = "metrics.json" if args.arm == "model" else "nulls.json"
    (out / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
