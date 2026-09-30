#!/usr/bin/env python
"""How far can ANY climate + soil map go on spin-up vegetation carbon? Near-twin cells. DEV ONLY.

    ALLOW_LOGIN_HEAVY=1 python scripts/diag_spinup_vegc_twins.py \\
        --pred <scratch.exp>/T-screen-spinup-vegc-r2/predictions.parquet

Read-only apart from two small LightGBM/ridge fits on pair differences (about a minute). It
produces no skill number for the emulator: every figure is a bound or a decomposition.

THE QUESTION. The best map (`screen_spinup_vegc.py` round 2) sits at 62 % of dev cells inside the
band where a rerun sits at 85 %, and its misses are shared by very different recipes. Is that the
learner, or do the inputs themselves not pin a cell's carbon down to 10 %? Adjacent 0.5-degree
cells on the same soil type are the natural experiment: their inputs are nearly identical, so
  1. TWIN TRUTH AS A PREDICTOR: how often does a near-twin's true carbon land in this cell's band?
     If near-identical inputs often give carbon more than 10 % apart, a map of these inputs must
     resolve differences finer than neighbours show.
  2. WHAT EXPLAINS A TWIN DIFFERENCE: the variance of log(carbon_i / carbon_j) over close pairs is
     split into the model's own seed noise (each twin's seed spread, known), what the INPUT
     differences explain (ridge and LightGBM fitted on pair differences, scored on pairs from
     held-out 15-degree tiles), and what the map's own predicted difference explains.
The two seeds of one cell share nothing except that cell's inputs, so whatever neither seed
noise nor the fitted difference models explain is still a function of the inputs -- a response
finer than these learners resolve -- not hidden state. That is why this is a bound on the
LEARNERS, not an information ceiling.

⚠ Truth-side quantities (the twin predictor) have seen the answer for the neighbour; they bound
what neighbourhood information is worth and are never emulator skill. Dev folds 0-2 for (1);
(2) pools all folds because it fits only pair DIFFERENCES and scores on held-out tiles.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import polars as pl
from sklearn.linear_model import RidgeCV

from exp_equilibrium_map import FEATURES
from vegemu.corpus.features_v3 import V3_ALLP
from vegemu.paths import paths

Array = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


def _grid_key(lon: Array, lat: Array) -> dict[tuple[int, int], int]:
    return {
        (int(np.floor(x * 2)), int(np.floor(y * 2))): i
        for i, (x, y) in enumerate(zip(lon, lat, strict=True))
    }


def pairs(
    lon: Array, lat: Array, ok: npt.NDArray[np.bool_], steps: tuple[tuple[int, int], ...]
) -> IntArray:
    key = _grid_key(lon, lat)
    out = []
    for i in np.flatnonzero(ok):
        gx, gy = int(np.floor(lon[i] * 2)), int(np.floor(lat[i] * 2))
        for dx, dy in steps:
            j = key.get((gx + dx, gy + dy))
            if j is not None and ok[j]:
                out.append((i, j))
    return np.array(out, dtype=np.int64)


def main() -> int:  # noqa: PLR0915 -- one flat read-and-print pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pred", required=True, help="the screen's predictions.parquet")
    ap.add_argument("--out", type=Path, default=None, help="also write the numbers as JSON here")
    args = ap.parse_args()
    exp = Path(str(paths()["scratch"]["exp"]))
    spin = Path(str(paths()["scratch"]["corpus"])) / "spinup-constco2"
    c = pl.read_parquet(spin / "climate_spinup.parquet").sort("cell")
    v = pl.read_parquet(exp / "T-features-v3p" / "features_v3p_spinup.parquet").sort("cell")
    assert np.array_equal(c["cell"].to_numpy(), np.arange(c.height))
    assert np.array_equal(v["cell"].to_numpy(), np.arange(c.height))
    p = pl.read_parquet(args.pred)
    cell = p["cell"].to_numpy()
    fold = p["fold"].to_numpy()
    t1, t2, w, pb = (p[k].to_numpy() for k in ("t1", "t2", "w", "pred_best"))
    tm = (t1 + t2) / 2
    lon, lat = c["lon"].to_numpy()[cell], c["lat"].to_numpy()[cell]
    soil = c["soil_code"].to_numpy()[cell]
    x = np.concatenate(
        [
            c.select(FEATURES).to_numpy().astype(np.float64),
            v.select(list(V3_ALLP)).to_numpy().astype(np.float64),
        ],
        axis=1,
    )[cell]
    x = np.nan_to_num((x - np.nanmean(x, 0)) / (np.nanstd(x, 0) + 1e-12))

    def passes(pred: Array, i: IntArray) -> Array:
        a = np.abs(pred - t1[i]) <= w[i] * np.abs(t1[i])
        b = np.abs(pred - t2[i]) <= w[i] * np.abs(t2[i])
        out: Array = (a.astype(np.float64) + b.astype(np.float64)) / 2
        return out

    # A rerun: each seed predicting the other, averaged -- the sealed reference.
    rerun = (
        (np.abs(t1 - t2) <= w * np.abs(t2)).astype(np.float64)
        + (np.abs(t2 - t1) <= w * np.abs(t1)).astype(np.float64)
    ) / 2

    # (1) The twin truth as a predictor, dev folds, 8-connected neighbours on the same soil.
    ring = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0))
    pr = pairs(lon, lat, tm > 0, ring)
    i, j = pr[:, 0], pr[:, 1]
    keep = (soil[i] == soil[j]) & (fold[i] <= 2)
    i, j = i[keep], j[keep]
    dist = np.linalg.norm(x[i] - x[j], axis=1) / np.sqrt(x.shape[1])
    print(
        f"(1) dev pairs, same soil: {i.size}; {x.shape[1]} inputs; rerun frac (dev) "
        f"{rerun[fold <= 2].mean():.3f}"
    )
    report: dict[str, object] = {
        "inputs": int(x.shape[1]),
        "rerun_dev": float(rerun[fold <= 2].mean()),
    }
    bins: list[dict[str, float]] = []
    q = np.quantile(dist, [0, 0.1, 0.25, 0.5, 0.75, 1])
    for lo, hi in itertools.pairwise(q):
        s = (dist >= lo) & (dist <= hi)
        med = np.median(np.abs(np.log(tm[i][s] / tm[j][s])))
        print(
            f"  input distance {lo:.3f}-{hi:.3f} ({s.sum():6d} pairs): twin truth in band "
            f"{passes(tm[j][s], i[s]).mean():.3f}, the map {passes(pb[i][s], i[s]).mean():.3f}, "
            f"rerun {rerun[i][s].mean():.3f}, median |log twin difference| {med:.3f}"
        )
        bins.append(
            {
                "lo": float(lo),
                "hi": float(hi),
                "pairs": int(s.sum()),
                "twin": float(passes(tm[j][s], i[s]).mean()),
                "map": float(passes(pb[i][s], i[s]).mean()),
                "rerun": float(rerun[i][s].mean()),
                "median_abs_log_twin_diff": float(med),
            }
        )
    report["by_distance"] = bins
    parts: list[dict[str, float]] = []

    # (2) What explains a twin difference: seed noise, input differences, the map.
    pr = pairs(lon, lat, tm > 0, ((1, 0), (0, 1), (1, 1), (1, -1)))
    i, j = pr[:, 0], pr[:, 1]
    same = soil[i] == soil[j]
    i, j = i[same], j[same]
    dx = x[i] - x[j]
    dy = np.log(tm[i] / tm[j])
    dp = np.log(np.maximum(pb[i], 1e-9) / np.maximum(pb[j], 1e-9))
    noise = np.log(t1[i] / t2[i]) ** 2 / 4 + np.log(t1[j] / t2[j]) ** 2 / 4
    dist = np.linalg.norm(dx, axis=1) / np.sqrt(x.shape[1])
    ok = np.isfinite(dy) & np.isfinite(noise) & (np.abs(dy) < 2)
    region = np.floor((lon[i] + 180) / 15) * 100 + np.floor((lat[i] + 90) / 15)
    print(f"(2) pairs, same soil, 4 directions: {int(ok.sum())}")
    for hi in (0.1, 0.2, np.inf):
        s = ok & (dist < hi)
        u = np.unique(region[s])
        held = np.random.default_rng(0).choice(u, u.size // 3, replace=False)
        te, tr = s & np.isin(region, held), s & ~np.isin(region, held)
        vy, vn = dy[te].var(), noise[te].mean()
        lin = RidgeCV(alphas=np.logspace(-2, 4, 13)).fit(dx[tr], dy[tr])
        r2_lin = 1 - ((lin.predict(dx[te]) - dy[te]) ** 2).mean() / vy
        g = lgb.LGBMRegressor(
            n_estimators=800, learning_rate=0.03, num_leaves=31, verbose=-1, n_jobs=8
        ).fit(np.c_[dx[tr], x[i][tr]], dy[tr])
        r2_gbm = 1 - ((g.predict(np.c_[dx[te], x[i][te]]) - dy[te]) ** 2).mean() / vy
        r2_map = 1 - ((dp[te] - dy[te]) ** 2).mean() / vy
        print(
            f"  distance < {hi:g}: {int(te.sum())} held-out pairs, var(log twin difference) "
            f"{vy:.4f}; seed noise {vn / vy:.0%}; explained by input differences: ridge "
            f"{r2_lin:.3f}, LightGBM {r2_gbm:.3f}; by the map's own difference {r2_map:.3f}"
        )
        parts.append(
            {
                "max_distance": float(hi),
                "pairs": int(te.sum()),
                "var": float(vy),
                "seed_noise_share": float(vn / vy),
                "ridge": float(r2_lin),
                "lightgbm": float(r2_gbm),
                "map": float(r2_map),
            }
        )
    report["difference_decomposition"] = parts
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
