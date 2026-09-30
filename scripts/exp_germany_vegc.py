#!/usr/bin/env python
"""Germany: predict the settled vegetation carbon under a climate the model never trained on.

    NCPUS=16 scripts/sbatch_py.sh X-ger-nulls scripts/exp_germany_vegc.py --arm nulls --out <dir>
    NCPUS=32 scripts/sbatch_py.sh --exp X-20260930-germany-vegc-new-climate X-ger-model \\
        scripts/exp_germany_vegc.py --arm model \\
        --out <scratch.exp>/X-20260930-germany-vegc-new-climate

THE QUESTION. The Germany corpus (`scripts/germany_corpus.py`, decision
`20260930-INT-the-germany-equilibrium-runs-become-their-own-corpus.md`) holds every one of 9,067
cells settled under six climates (2 ESMs x ssp126/245/370, each the 2071-2100 window recycled for a
millennium), two seeds each. Hold out one climate at a time: for every cell, predict its settled
carbon under that climate from a model trained on the other five climates' rows (all cells). Is
that as good as a second run of the model?

ESTIMAND `asgood_vegc_germany_newclimate` (the owner's rule, `20260924-INT-*`, on this corpus):
  * a row is (cell, climate); scored where both seeds' truth is > 0;
  * truth T_k = seed k's mean VegC over 2821-3070; band w = max(0.10, s), s the two seeds' relative
    spread over 2571-2820;
  * per-row pass = mean over k of 1[|x - T_k| <= w T_k]; frac = mean over scored rows;
  * rerun reference: each seed predicting the other, same band, same rows;
  * D = frac(arm) - frac(rerun).

FOLDS: leave-one-climate-out, six folds, the fold of a row is its (ESM, SSP). No row of the held-out
climate trains its prediction. The SAME CELL under the other five climates does train it -- that is
the design (same place, new climate), and it is why the same-cell nulls below are the ones to beat.

THE MODEL ARM, fixed before any Germany number was seen: LightGBM with the settings the global
spin-up screen selected on the global dev folds (`screen_spinup_vegc.py` round 2, frozen here), L1
loss on log1p, one row per seed, 3000 trees, one fit. Inputs: the 258 columns of
`germany_climate.parquet` (85 forcing + soil depth + 5 soil + 167 derived). Never an input: cell,
lon, lat, ESM, SSP, seed, CO2.

THE NULLS (every one information-free about the held-out climate's truth):
  * same_cell_nearest_climate: the cell's own two-seed truth under the training climate nearest in
    the 85 forcing features (standardised on the training climates' rows);
  * same_cell_mean: the geometric mean of the cell's own truth under the five training climates;
  * nearest_analogue: the truth of the nearest training ROW (any cell) in the eight analogue
    features (`vegemu.nulls.ANALOGUE_FEATURES`);
  * training_mean: the mean of the training rows' log1p truth;
  * shuffled: the held-out climate's truth permuted across its own scored rows (seed 20260930).
REPORTED BESIDE, NEVER DECIDED ON: frac per held-out climate; frac without ssp245 (a different
build: its rows neither train nor are scored); the ceiling, the two-seed mean scored as a
predictor; a BLIND learned arm, the same learner on the six soil columns alone; variance explained
on log1p; the flat 10 % rate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.spatial import cKDTree

from vegemu.corpus import features_v3 as fv3
from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.corpus.soil import SOIL_FEATURES
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths

Array = npt.NDArray[np.float64]

STATISTIC = "asgood_vegc_germany_newclimate"
FLOOR = 0.10
FORCING = [c for c in CLIMATE_FEATURES if c != "soildepth"]  # 85
SOIL = ["soildepth", *SOIL_FEATURES]  # 6
FEATURES: list[str] = [*FORCING, *SOIL, *fv3.V3_ALLP]  # 258
FORBIDDEN = {"cell", "lon", "lat", "esm", "ssp", "seed", "co2", "fold"}
# screen_spinup_vegc.py round 2's selected settings, frozen (its screen.json, "best").
LEARNER: dict[str, Any] = {
    "objective": "regression_l1",
    "n_estimators": 3000,
    "learning_rate": 0.020343045376891144,
    "num_leaves": 48,
    "min_child_samples": 5,
    "colsample_bytree": 0.9322383049275373,
    "subsample": 0.5052887904508281,
    "subsample_freq": 1,
    "reg_lambda": 26.23514538217487,
    "min_split_gain": 0.042271448901565235,
    "max_bin": 255,
    "verbose": -1,
}
SHUFFLE_SEED = 20260930


def load() -> dict[str, Any]:
    corpus = Path(str(paths()["scratch"]["corpus"])) / "germany-eq-v1"
    t = pl.read_parquet(corpus / "germany_truth.parquet").sort(["esm", "ssp", "cell"])
    c = pl.read_parquet(corpus / "germany_climate.parquet").sort(["esm", "ssp", "cell"])
    for k in ("esm", "ssp", "cell"):
        assert (t[k] == c[k]).all(), k
    assert not FORBIDDEN & set(FEATURES)
    assert len(FEATURES) == 258
    clim = (t["esm"] + "/" + t["ssp"]).to_numpy()
    names = sorted(set(clim))
    assert len(names) == 6
    fold = np.array([names.index(x) for x in clim])
    t1, t2 = t["vegc_win_s1"].to_numpy(), t["vegc_win_s2"].to_numpy()
    return {
        "x": c.select(FEATURES).to_numpy().astype(np.float64),
        "t1": t1,
        "t2": t2,
        "w": np.maximum(FLOOR, t["two_seed_spread"].to_numpy()),
        "cell": t["cell"].to_numpy(),
        "fold": fold,
        "names": names,
        "ssp": t["ssp"].to_numpy(),
        "scored": (t1 > 0) & (t2 > 0) & np.isfinite(t1) & np.isfinite(t2),
        "sha": {
            "truth": json.loads((corpus / "germany_truth.json").read_text())["output_sha256"],
            "climate": json.loads((corpus / "germany_climate.json").read_text())["output_sha256"],
        },
    }


def passes(x: Array, t1: Array, t2: Array, w: Array) -> Array:
    a = (np.abs(x - t1) <= w * np.abs(t1)).astype(np.float64)
    b = (np.abs(x - t2) <= w * np.abs(t2)).astype(np.float64)
    out: Array = (a + b) / 2
    return out


def score(pred: Array, d: dict[str, Any], sel: npt.NDArray[np.bool_]) -> dict[str, Any]:
    t1, t2, w = d["t1"][sel], d["t2"][sel], d["w"][sel]
    # A rerun: seed 2 scored against seed 1's truth and seed 1 against seed 2's, averaged.
    rerun = (passes(t2, t1, t1, w) + passes(t1, t2, t2, w)) / 2
    p = pred[sel]
    fr = float(passes(p, t1, t2, w).mean())
    tm = (t1 + t2) / 2
    lt, lp = np.log1p(tm), np.log1p(np.maximum(p, 0.0))
    return {
        "rows": int(sel.sum()),
        "frac": fr,
        "frac_rerun": float(rerun.mean()),
        "D": fr - float(rerun.mean()),
        "skill_log1p": float(1 - ((lp - lt) ** 2).sum() / ((lt - lt.mean()) ** 2).sum()),
        "flat10": float((np.abs(p - tm) <= FLOOR * tm).mean()),
    }


def breakdown(pred: Array, d: dict[str, Any], base: npt.NDArray[np.bool_]) -> dict[str, Any]:
    out = {"all": score(pred, d, base)}
    for i, n in enumerate(d["names"]):
        out[n] = score(pred, d, base & (d["fold"] == i))
    return out


def nulls(d: dict[str, Any]) -> dict[str, Array]:
    x, fold, cell = d["x"], d["fold"], d["cell"]
    y = (d["t1"] + d["t2"]) / 2
    ly = np.log1p(np.maximum(y, 0.0))
    ncell = int(cell.max()) + 1
    # truth[c, f]: the cell's two-seed mean under climate f
    by = np.full((ncell, 6), np.nan)
    by[cell, fold] = y
    xf = np.full((ncell, 6, len(FORCING)), np.nan)
    xf[cell, fold] = x[:, : len(FORCING)]
    a_idx = [FEATURES.index(f) for f in ANALOGUE_FEATURES]
    out = {
        k: np.full(y.size, np.nan)
        for k in (
            "same_cell_nearest_climate",
            "same_cell_mean",
            "nearest_analogue",
            "training_mean",
            "shuffled",
        )
    }
    rng = np.random.default_rng(SHUFFLE_SEED)
    for f in range(6):
        te = fold == f
        tr = ~te & np.isfinite(y)
        mu, sd = x[tr].mean(axis=0), x[tr].std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        others = [g for g in range(6) if g != f]
        cells_te = cell[te]
        # same cell, nearest training climate in the 85 standardised forcing features
        q = (xf[cells_te, f] - mu[: len(FORCING)]) / sd[: len(FORCING)]
        dist = np.stack(
            [
                np.linalg.norm(
                    (xf[cells_te, g] - mu[: len(FORCING)]) / sd[: len(FORCING)] - q, axis=1
                )
                for g in others
            ],
            axis=1,
        )
        pick = np.array(others)[dist.argmin(axis=1)]
        out["same_cell_nearest_climate"][te] = by[cells_te, pick]
        with np.errstate(divide="ignore"):
            out["same_cell_mean"][te] = np.expm1(
                np.nanmean(np.log1p(np.maximum(by[cells_te][:, others], 0.0)), axis=1)
            )
        a_tr = (x[tr][:, a_idx] - mu[a_idx]) / sd[a_idx]
        a_te = (x[te][:, a_idx] - mu[a_idx]) / sd[a_idx]
        out["nearest_analogue"][te] = y[tr][cKDTree(a_tr).query(a_te, k=1)[1]]
        out["training_mean"][te] = np.expm1(ly[tr].mean())
        sc = te & d["scored"]
        out["shuffled"][sc] = rng.permutation(y[sc])
    return out


def fit_predict(
    d: dict[str, Any],
    cols: list[int],
    folds: list[int],
    keep: npt.NDArray[np.bool_] | None = None,
    threads: int = 8,
) -> Array:
    from lightgbm import LGBMRegressor  # noqa: PLC0415

    x = d["x"][:, cols]
    pred = np.full(x.shape[0], np.nan)
    keep = np.ones(x.shape[0], dtype=bool) if keep is None else keep
    for f in folds:
        tr = (d["fold"] != f) & keep & np.isfinite(d["t1"]) & np.isfinite(d["t2"])
        xt = np.concatenate([x[tr], x[tr]])
        yt = np.log1p(np.maximum(np.concatenate([d["t1"][tr], d["t2"][tr]]), 0.0))
        m = LGBMRegressor(**LEARNER, n_jobs=threads)
        m.fit(xt, yt)
        te = d["fold"] == f
        pred[te] = np.clip(np.expm1(m.predict(x[te])), 0.0, None)
        print(f"  fold {f} ({d['names'][f]}): trained on {yt.size} rows", flush=True)
    return pred


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = load()
    base = d["scored"]
    tm = (d["t1"] + d["t2"]) / 2
    report: dict[str, Any] = {
        "statistic": STATISTIC,
        "scored_rows": int(base.sum()),
        "rows": int(base.size),
        "climates": d["names"],
        "inputs_sha256": d["sha"],
        "band_is_floor_share": float((d["w"][base] == FLOOR).mean()),
        "ceiling_two_seed_mean": breakdown(tm, d, base),
    }
    nl = nulls(d)
    report["nulls"] = {k: breakdown(v, d, base) for k, v in nl.items()}
    # How different the six climates' truths are for one cell: the scale of the response.
    ncell = int(d["cell"].max()) + 1
    by = np.full((ncell, 6), np.nan)
    by[d["cell"], d["fold"]] = tm
    lr = np.log(np.where(by > 0, by, np.nan))
    report["response_scale"] = {
        "median_abs_log_range_across_climates": float(
            np.nanmedian(np.nanmax(lr, 1) - np.nanmin(lr, 1))
        ),
        "share_cells_range_over_10pct": float(
            np.nanmean((np.nanmax(lr, 1) - np.nanmin(lr, 1)) > np.log(1.1))
        ),
    }
    if a.arm == "nulls":
        (out / "nulls.json").write_text(json.dumps(report, indent=2))
        print(
            json.dumps(
                {
                    k: {"D": v["all"]["D"], "frac": v["all"]["frac"]}
                    for k, v in report["nulls"].items()
                },
                indent=2,
            ),
            flush=True,
        )
        print(
            json.dumps(
                {k: report[k] for k in ("scored_rows", "response_scale", "band_is_floor_share")},
                indent=2,
            )
        )
        print("ceiling", json.dumps(report["ceiling_two_seed_mean"]["all"]))
        return 0

    all_cols = list(range(len(FEATURES)))
    soil_cols = [FEATURES.index(c) for c in SOIL]
    pred = fit_predict(d, all_cols, list(range(6)), threads=a.threads)
    blind = fit_predict(d, soil_cols, list(range(6)), threads=a.threads)
    no245 = d["ssp"] != "ssp245"
    folds_same_build = [i for i, n in enumerate(d["names"]) if not n.endswith("ssp245")]
    pred_nb = fit_predict(d, all_cols, folds_same_build, keep=no245, threads=a.threads)
    report["arm"] = "model"
    report["learner"] = LEARNER
    report["features"] = len(FEATURES)
    report["arm_details"] = {
        "model": breakdown(pred, d, base),
        "blind_soil_only": breakdown(blind, d, base),
        "model_without_ssp245": score(pred_nb, d, base & no245),
    }
    arms = {"model": report["arm_details"]["model"]["all"]["D"]}
    arms.update({k: v["all"]["D"] for k, v in report["nulls"].items()})
    report["arms"] = arms
    report["n"] = int(base.sum())
    report["decision"] = {
        "D": arms["model"],
        "threshold": -0.02,
        "verdict": "pass" if arms["model"] >= -0.02 else "fail",
    }
    pl.DataFrame(
        {
            "cell": d["cell"],
            "fold": d["fold"],
            "t1": d["t1"],
            "t2": d["t2"],
            "w": d["w"],
            "scored": base,
            "pred": pred,
            "blind": blind,
            "pred_no245": pred_nb,
            **{f"null_{k}": v for k, v in nl.items()},
        }
    ).write_parquet(out / "predictions.parquet")
    (out / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"model": report["arm_details"]["model"]["all"], "arms": arms}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
