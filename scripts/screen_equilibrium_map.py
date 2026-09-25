#!/usr/bin/env python
"""DEV SCREEN of recipes for the climate-only equilibrium map. EXPLORATORY: NOT A CLAIM.

    NCPUS=64 PARTITION=priority TIME=04:00:00 scripts/sbatch_py.sh T-fea-screen \\
        scripts/screen_equilibrium_map.py --workers 64 --out <scratch.exp>/T-screen-equilibrium

WHAT IT SCREENS. The sealed experiment `X-20260923-equilibrium-from-climate` fitted one LightGBM
head per quantity on 91 climate-and-soil features. Every number printed here is a DEV DIAGNOSTIC
for choosing what its successor should pre-register; none is evidence about the emulator.
Candidates: (a) + the daily-forcing features v3, (b) traits on logs, (c) each trait's median plus
log-gaps to its 10th and 90th percentiles, (d) hyperparameters tuned on the dev folds only,
(e) seed bagging, (f) two stages: out-of-fold predicted type shares and forest-scale quantities as
extra inputs to the trait heads, (g) a learning curve over the number of training cells, and
(h) the five soil-texture columns dropped.

THE BASELINE IS THE SEALED APPARATUS, IMPORTED, NOT RESTATED: its loader, its 22 quantities and
their transforms, its skill and band arithmetic, its folds (15-degree tiles, k=5, seed 42) and its
LightGBM settings. Step 0 re-derives the sealed per-quantity values with this script's own engine
(all five folds, the sealed recipe) and records whether they reproduce.

THE SELECTION RULE -- fixed in this docstring before the screen was first run:
  * DEV = the cells of folds 0, 1 and 2. Each dev fold is predicted by a model trained on the OTHER
    TWO dev folds only, so folds 3 and 4 never enter a fit that is compared. The dev statistic is
    the sealed statistic (mean variance explained over the 19 quantities that vary) on the
    assembled dev predictions.
  * HELD-OUT = the cells of folds 3 and 4, each predicted by a model trained on the other four
    folds -- the sealed experiment's own construction, restricted to those rows. It is PRINTED for
    every candidate and never enters a comparison or a choice.
  * Greedy, in a fixed order: feature set, then target form, then the two-stage inputs, then tuned
    hyperparameters, then bagging. A component is kept only if it raises the dev statistic by more
    than MIN_GAIN over the recipe without it; otherwise the simpler recipe stands. For the feature
    set, where two components (+v3, -soil) can combine, that holds for each component separately.
  ⚠ Tuning selects the best of N trials ON the dev folds, so a tuned recipe's dev number is
    optimistic by construction; only its held-out number is clean.

WHAT IS ALSO COMPUTED, FOR THE CONFIRMATION'S PRE-REGISTRATION: the four sealed nulls on the
held-out rows (they are deterministic functions of the corpus and the folds), the bar re-derived by
the sealed rule, and the noise ceiling on the held-out rows.

⚠ NO LEAKAGE. No state, restart or location column is ever a feature (the sealed FORBIDDEN set is
asserted against every feature list, v3 included). The two-stage inputs of a training row are
predicted by models that never saw that row's CELL; those of a test row by a model trained on the
training cells only.
"""

from __future__ import annotations

import os

# One thread per LightGBM fit: the parallelism is across fits, and one thread is what the sealed
# job ran with (NCPUS=1), which is what makes the reproduction bit-comparable.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import dataclasses
import json
import math
import sys
import time
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
from joblib import Parallel, delayed
from lightgbm import LGBMRegressor

from exp_equilibrium_map import (
    CONSTANT_QUANTITIES,
    FEATURES,
    FORBIDDEN,
    LOG_QUANTITIES,
    NULLS,
    QUANTITIES,
    SOIL_FEATURES,
    band_stats,
    ceiling,
    load,
    null_predictions,
    skill,
)
from exp_model_pilot_response import PARAMS
from vegemu.corpus.features_v3 import V3_FEATURES
from vegemu.paths import paths
from vegemu.score import blocked_spatial_folds

Array = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

DEV_FOLDS: tuple[int, ...] = (0, 1, 2)
HELD_FOLDS: tuple[int, ...] = (3, 4)
MIN_GAIN = 0.005
TRAITS: tuple[str, ...] = ("wooddens", "sla", "k_root", "D95max", "longevity", "height")
SHARES: tuple[str, ...] = tuple(f"pft_frac_{i}" for i in range(7))
FOREST: tuple[str, ...] = tuple(q for q in QUANTITIES if q in LOG_QUANTITIES)
# The sealed bar rule: the gap between the best null and the runner-up, plus the kill tests'
# headroom, rounded UP to the next multiple of BAR_STEP.
BAR_HEADROOM = 0.0118
BAR_STEP = 0.005
LOG_FLOOR = 1e-12


@dataclass(frozen=True)
class Recipe:
    name: str
    v3: bool = False
    soil: bool = True
    target: str = "sealed"  # sealed | log | gaps
    params: tuple[tuple[str, Any], ...] = ()
    bag: int = 1
    stage2: bool = False
    train_frac: float = 1.0
    subsample_seed: int = 0

    def lgbm(self) -> dict[str, Any]:
        return {**PARAMS, **dict(self.params)}


@dataclass
class Data:
    x_base: Array  # (cells, points, 91), the sealed features
    x_v3: Array  # (cells, points, len(V3_FEATURES))
    y: Array  # (cells, points, 22), the sealed scale
    raw: Array  # (cells, points, 22), raw levels, traits NaN where treeless
    shares: Array  # (cells, points, 7)
    folds: IntArray  # (cells,)
    lon: Array
    lat: Array
    points: list[str]
    soil_bin: Path
    extra: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------


def load_data(version: str, v3_table: Path, degrees: float) -> Data:
    root = Path(str(paths()["scratch"]["corpus"]))
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    frame, x, y, raw, points, lon, lat = load(
        pl.read_parquet(root / version / "corpus.parquet"), soil_bin
    )
    n_c, n_p = y.shape[:2]
    v3 = pl.read_parquet(v3_table).sort(["cell", "point"])
    keys = frame.select(["cell", "point"])
    if not (
        v3.height == frame.height
        and (v3["cell"].to_numpy() == keys["cell"].to_numpy()).all()
        and v3["point"].to_list() == keys["point"].to_list()
    ):
        raise AssertionError("the v3 table does not carry exactly the corpus's (cell, point) rows")
    assert not FORBIDDEN & set(V3_FEATURES), "a forbidden column is in the v3 feature set"
    x_v3 = v3.select(list(V3_FEATURES)).to_numpy().astype(np.float64).reshape(n_c, n_p, -1)
    shares = frame.select(list(SHARES)).to_numpy().astype(np.float64).reshape(n_c, n_p, -1)
    folds = blocked_spatial_folds(lon, lat, k=5, degrees=degrees, seed=42)
    return Data(x, x_v3, y, raw, shares, folds, lon, lat, points, soil_bin)


def features(d: Data, r: Recipe) -> tuple[Array, list[str]]:
    names = [f for f in FEATURES if r.soil or f not in SOIL_FEATURES]
    idx = [FEATURES.index(f) for f in names]
    parts = [d.x_base[:, :, idx]]
    if r.v3:
        parts.append(d.x_v3)
        names += list(V3_FEATURES)
    assert not FORBIDDEN & set(names)
    return np.concatenate(parts, axis=2), names


# ----------------------------------------------------------------------------------------------
# Target forms. Every form is decoded back to the SEALED scale before anything is scored.
# ----------------------------------------------------------------------------------------------


def encode(raw: Array, y: Array, mode: str) -> tuple[Array, list[str]]:
    """(cells, points, nZ) training targets for one target form, and their names."""
    if mode == "sealed":
        return y.copy(), list(QUANTITIES)
    cols, names = [], []
    for q in FOREST:
        cols.append(y[..., QUANTITIES.index(q)])
        names.append(q)
    if mode == "log":
        for q in QUANTITIES:
            if q not in LOG_QUANTITIES:
                cols.append(np.log(np.maximum(raw[..., QUANTITIES.index(q)], LOG_FLOOR)))
                names.append(q)
        return np.stack(cols, axis=-1), names
    if mode != "gaps":
        raise ValueError(mode)
    for t in TRAITS:
        lo, mid, hi = (
            np.log(np.maximum(raw[..., QUANTITIES.index(f"{t}_{p}")], LOG_FLOOR))
            for p in ("p10", "p50", "p90")
        )
        cols += [mid, mid - lo, hi - mid]
        names += [f"{t}_logp50", f"{t}_gap_lo", f"{t}_gap_hi"]
    return np.stack(cols, axis=-1), names


def decode(z: Array, mode: str) -> Array:
    """(rows, nZ) predictions of one form -> (rows, 22) on the sealed scale."""
    if mode == "sealed":
        return z
    out = np.full((z.shape[0], len(QUANTITIES)), np.nan)
    for k, q in enumerate(FOREST):
        out[:, QUANTITIES.index(q)] = z[:, k]
    if mode == "log":
        rest = [q for q in QUANTITIES if q not in LOG_QUANTITIES]
        for k, q in enumerate(rest, start=len(FOREST)):
            out[:, QUANTITIES.index(q)] = np.exp(z[:, k])
        return out
    for i, t in enumerate(TRAITS):
        k = len(FOREST) + 3 * i
        mid, glo, ghi = z[:, k], np.maximum(z[:, k + 1], 0.0), np.maximum(z[:, k + 2], 0.0)
        out[:, QUANTITIES.index(f"{t}_p50")] = np.exp(mid)
        out[:, QUANTITIES.index(f"{t}_p10")] = np.exp(mid - glo)
        out[:, QUANTITIES.index(f"{t}_p90")] = np.exp(mid + ghi)
    return out


# ----------------------------------------------------------------------------------------------
# The engine: one LightGBM head per target column per split, fitted in parallel.
# ----------------------------------------------------------------------------------------------


def _fit(  # noqa: PLR0917 -- a joblib task: positional by design
    x: Array, z: Array, tr: IntArray, te: IntArray, params: dict[str, Any], seed: int | None
) -> Array:
    """One head. Mirrors the sealed `fit_predict_oof` rule: fewer than 50 usable training rows,
    or no finite truth in the test block, predicts 0."""
    ok = tr[np.isfinite(z[tr])]
    if ok.size < 50 or not np.isfinite(z[te]).any():
        return np.zeros(te.size)
    # LightGBM names the columns of a numpy input and sklearn then warns that the numpy input to
    # predict has none: noise, once per fit, that would bury the log.
    warnings.filterwarnings("ignore", message="X does not have valid feature names")
    kw = {**params, "n_jobs": 1}
    if seed is not None:
        kw["random_state"] = seed
    model = LGBMRegressor(**kw)
    model.fit(x[ok], z[ok])
    out: Array = np.asarray(model.predict(x[te]), dtype=np.float64)
    return out


def _seeds(bag: int) -> list[int | None]:
    # The first member is the sealed default (no random_state), so bag=1 IS the sealed recipe.
    return [None, *range(1, bag)]


def splits(
    folds: IntArray, regime: str
) -> list[tuple[int, npt.NDArray[np.bool_], npt.NDArray[np.bool_]]]:
    """(fold, train cells, test cells) for a regime: dev, held, or full (all five folds)."""
    out = []
    if regime == "dev":
        pool = np.isin(folds, DEV_FOLDS)
        for f in DEV_FOLDS:
            out.append((f, pool & (folds != f), folds == f))
    elif regime == "held":
        for f in HELD_FOLDS:
            out.append((f, folds != f, folds == f))
    elif regime == "full":
        for f in np.unique(folds):
            out.append((int(f), folds != f, folds == f))
    else:
        raise ValueError(regime)
    return out


def _subsample(
    train: npt.NDArray[np.bool_], frac: float, seed: int, fold: int
) -> npt.NDArray[np.bool_]:
    """A random `frac` of the training CELLS (never rows: a cell's 30 climates stay together)."""
    if frac >= 1.0:
        return train
    idx = np.flatnonzero(train)
    rng = np.random.default_rng(1000 * seed + fold)
    keep = rng.choice(idx, size=max(2, round(frac * idx.size)), replace=False)
    out = np.zeros_like(train)
    out[keep] = True
    return out


def _rows(cells: npt.NDArray[np.bool_], n_p: int) -> IntArray:
    return np.flatnonzero(np.repeat(cells, n_p)).astype(np.int64)


class Engine:
    def __init__(self, d: Data, workers: int) -> None:
        self.d = d
        self.par = Parallel(n_jobs=workers, backend="loky", max_nbytes="1M")
        self.fits = 0

    def _run(self, tasks: list[tuple[Any, ...]]) -> list[Array]:
        self.fits += len(tasks)
        return list(self.par(delayed(_fit)(*t) for t in tasks))

    def _stage1(
        self, x: Array, train: npt.NDArray[np.bool_], test: npt.NDArray[np.bool_], r: Recipe
    ) -> Array:
        """Two-stage inputs for ONE outer split: (rows, 11), finite on train and test rows only.

        Training rows get inner out-of-fold predictions, the inner folds being the training cells'
        own spatial folds; test rows get a model fitted on all training cells.
        """
        d, n_p = self.d, len(self.d.points)
        targets = np.concatenate(
            [d.shares, d.y[..., [QUANTITIES.index(q) for q in FOREST]]], axis=2
        ).reshape(-1, len(SHARES) + len(FOREST))
        flat_x = x.reshape(-1, x.shape[2])
        params = r.lgbm()
        jobs, where = [], []
        for inner in np.unique(d.folds[train]):
            itr, ite = train & (d.folds != inner), train & (d.folds == inner)
            for j in range(targets.shape[1]):
                jobs.append((flat_x, targets[:, j], _rows(itr, n_p), _rows(ite, n_p), params, None))
                where.append((_rows(ite, n_p), j))
        for j in range(targets.shape[1]):
            jobs.append((flat_x, targets[:, j], _rows(train, n_p), _rows(test, n_p), params, None))
            where.append((_rows(test, n_p), j))
        out = np.full(targets.shape, np.nan)
        for (rows, j), pred in zip(where, self._run(jobs), strict=True):
            out[rows, j] = pred
        return out

    def predict(self, r: Recipe, regime: str) -> Array:
        """(cells, points, 22) on the sealed scale, finite on the regime's test cells only."""
        d, n_p = self.d, len(self.d.points)
        x, _ = features(d, r)
        z, _ = encode(d.raw, d.y, r.target)
        flat_z = z.reshape(-1, z.shape[2])
        trait_cols = [k for k in range(z.shape[2]) if k >= len(FOREST)]
        params = r.lgbm()
        jobs, where = [], []
        for f, train_all, test in splits(d.folds, regime):
            train = _subsample(train_all, r.train_frac, r.subsample_seed, f)
            flat_x = x.reshape(-1, x.shape[2])
            x_aug = flat_x
            if r.stage2:
                x_aug = np.concatenate([flat_x, self._stage1(x, train, test, r)], axis=1)
            tr, te = _rows(train, n_p), _rows(test, n_p)
            for k in range(z.shape[2]):
                xk = x_aug if (r.stage2 and k in trait_cols) else flat_x
                for s in _seeds(r.bag):
                    jobs.append((xk, flat_z[:, k], tr, te, params, s))
                    where.append((te, k))
        acc = np.zeros(flat_z.shape)
        cnt = np.zeros(flat_z.shape)
        for (te, k), pred in zip(where, self._run(jobs), strict=True):
            acc[te, k] += pred
            cnt[te, k] += 1
        with np.errstate(invalid="ignore"):
            zhat = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
        return decode(zhat, r.target).reshape(d.y.shape)


# ----------------------------------------------------------------------------------------------
# Scoring, on a subset of cells, with the sealed arithmetic.
# ----------------------------------------------------------------------------------------------


def score(d: Data, pred: Array, cells: npt.NDArray[np.bool_]) -> dict[str, Any]:
    p, y, raw = pred[cells], d.y[cells], d.raw[cells]
    per_q = skill(p, y)
    treed = np.isfinite(raw[:, :, QUANTITIES.index("wooddens_p50")])
    band = band_stats(p, raw, treed)
    return {
        "cells": int(cells.sum()),
        "rows": int(cells.sum() * y.shape[1]),
        "pooled": float(np.nanmean(per_q)),
        "per_quantity": {q: float(v) for q, v in zip(QUANTITIES, per_q, strict=True)},
        "band": band,
    }


def evaluate(eng: Engine, r: Recipe, log: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    t0 = time.time()
    d = eng.d
    row: dict[str, Any] = {"stage": stage, "recipe": dataclasses.asdict(r)}
    for regime, fold_set in (("dev", DEV_FOLDS), ("held", HELD_FOLDS)):
        pred = eng.predict(r, regime)
        row[regime] = score(d, pred, np.isin(d.folds, fold_set))
    row["seconds"] = time.time() - t0
    log.append(row)
    print(
        f"  [{stage}] {r.name:34s} dev {row['dev']['pooled']:+.4f}   "
        f"held {row['held']['pooled']:+.4f}   ({row['seconds']:.0f} s)",
        flush=True,
    )
    return row


def _accept(base: dict[str, Any], cand: dict[str, Any]) -> bool:
    return bool(cand["dev"]["pooled"] > base["dev"]["pooled"] + MIN_GAIN)


# ----------------------------------------------------------------------------------------------
# Tuning (d)
# ----------------------------------------------------------------------------------------------


def tune(eng: Engine, r: Recipe, trials: int, log: list[dict[str, Any]]) -> Recipe:
    import optuna  # noqa: PLC0415 -- optional: only the tuning stage needs it, and CI has none

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: Any) -> float:
        p = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 1500, log=True),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 7, 63, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 150, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.15, 0.9),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 30.0, log=True),
        }
        cand = dataclasses.replace(r, params=tuple(sorted(p.items())))
        pred = eng.predict(cand, "dev")
        val = score(eng.d, pred, np.isin(eng.d.folds, DEV_FOLDS))["pooled"]
        log.append({"trial": trial.number, "params": p, "dev_pooled": val})
        print(f"    trial {trial.number:3d}  dev {val:+.4f}", flush=True)
        return float(val)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=0))
    # The sealed settings are trial 0, so tuning can only report "no better" rather than worse.
    study.enqueue_trial(
        {
            k: PARAMS[k]
            for k in (
                "n_estimators",
                "learning_rate",
                "num_leaves",
                "min_child_samples",
                "subsample",
                "colsample_bytree",
                "reg_lambda",
            )
        }
    )
    study.optimize(objective, n_trials=trials)
    best = dict(study.best_params)
    return dataclasses.replace(r, name=r.name + "+tuned", params=tuple(sorted(best.items())))


# ----------------------------------------------------------------------------------------------
# Nulls, bar and ceiling on the held-out rows (for the confirmation's pre-registration)
# ----------------------------------------------------------------------------------------------


def nulls_on(d: Data, cells: npt.NDArray[np.bool_]) -> dict[str, Any]:
    preds = null_predictions(d.x_base, d.y, d.folds, d.lon, d.lat)
    return {n: score(d, preds[n], cells) for n in NULLS}


def bar_rule(nulls: dict[str, Any]) -> dict[str, float | str]:
    ranked = sorted(((v["pooled"], k) for k, v in nulls.items()), reverse=True)
    gap = ranked[0][0] - ranked[1][0]
    bar = math.ceil((gap + BAR_HEADROOM) / BAR_STEP - 1e-9) * BAR_STEP
    return {
        "best_null": ranked[0][1],
        "best_null_value": ranked[0][0],
        "runner_up": ranked[1][1],
        "gap": gap,
        "headroom": BAR_HEADROOM,
        "bar": round(bar, 6),
        "model_must_reach": ranked[0][0] + round(bar, 6),
    }


# ----------------------------------------------------------------------------------------------


def _summary(rows: Sequence[dict[str, Any]]) -> list[str]:
    keys = ("D95max_p10", "D95max_p50", "wooddens_p50", "sla_p10", "longevity_p50", "longevity_p90")
    out = [
        f"{'candidate':34s} {'dev':>7s} {'held':>7s} {'h.conj':>6s} {'h.band':>6s}  "
        + " ".join(f"{k[:11]:>11s}" for k in keys)
    ]
    for r in rows:
        h = r["held"]
        band_mean = float(np.mean([v for v in h["band"]["per_quantity"].values()]))
        out.append(
            f"{r['recipe']['name']:34s} {r['dev']['pooled']:+.4f} {h['pooled']:+.4f} "
            f"{h['band']['conjunctive']:6.4f} {band_mean:6.4f}  "
            + " ".join(f"{h['per_quantity'][k]:+11.4f}" for k in keys)
        )
    return out


def main() -> int:  # noqa: PLR0912, PLR0915 -- one screen, a fixed sequence of stages
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--v3", default="", help="features_v3_pilot.parquet (default: scratch.exp)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--bag", type=int, default=5)
    ap.add_argument("--curve-repeats", type=int, default=3)
    ap.add_argument("--smoke", action="store_true", help="tiny settings, to test the plumbing")
    ap.add_argument("--sealed-metrics", default="", help="the sealed metrics.json to reproduce")
    args = ap.parse_args()

    exp = Path(str(paths()["scratch"]["exp"]))
    v3_table = Path(args.v3) if args.v3 else exp / "T-features-v3" / "features_v3_pilot.parquet"
    sealed = (
        Path(args.sealed_metrics)
        if args.sealed_metrics
        else exp / "X-20260923-equilibrium-from-climate" / "metrics.json"
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    d = load_data(args.version, v3_table, 15.0)
    eng = Engine(d, args.workers)
    base_params: tuple[tuple[str, Any], ...] = ()
    if args.smoke:
        base_params = (("n_estimators", 40),)
        args.trials, args.bag, args.curve_repeats = 2, 2, 1
    report: dict[str, Any] = {
        "label": "DEV SCREEN -- exploratory, not a claim; selection on folds 0-2 only",
        "version": args.version,
        "v3_table": str(v3_table),
        "n_cells": int(d.y.shape[0]),
        "n_points": int(d.y.shape[1]),
        "folds": {"blocking_degrees": 15, "k": 5, "seed": 42},
        "cells_per_fold": {int(f): int((d.folds == f).sum()) for f in np.unique(d.folds)},
        "dev_folds": list(DEV_FOLDS),
        "held_folds": list(HELD_FOLDS),
        "min_gain": MIN_GAIN,
        "smoke": bool(args.smoke),
        "features_base": len(FEATURES),
        "features_v3": len(V3_FEATURES),
    }
    print(json.dumps({k: report[k] for k in ("cells_per_fold", "n_cells", "features_v3")}))
    t_start = time.time()

    # -- step 0: the sealed values, from this engine -------------------------------------------
    base = Recipe("base (sealed recipe)", params=base_params)
    full = eng.predict(base, "full")
    rep = score(d, full, np.ones(d.folds.size, dtype=bool))
    repro: dict[str, Any] = {"pooled": rep["pooled"], "per_quantity": rep["per_quantity"]}
    if sealed.exists() and not args.smoke:
        s = json.loads(sealed.read_text())["by_blocking"]["15deg"]["model"]
        diffs = {
            q: abs(rep["per_quantity"][q] - s["per_quantity"][q])
            for q in QUANTITIES
            if q not in CONSTANT_QUANTITIES
        }
        repro.update(
            {
                "sealed_pooled": s["pooled"],
                "max_abs_diff_per_quantity": max(diffs.values()),
                "pooled_abs_diff": abs(rep["pooled"] - s["pooled"]),
                "reproduced_to_1e-9": max(diffs.values()) < 1e-9,
            }
        )
    report["reproduction"] = repro
    print(f"step 0: sealed recipe, all 5 folds: {rep['pooled']:+.6f}  {repro}", flush=True)

    # -- the nulls, bar and ceiling on the held-out rows ---------------------------------------
    held = np.isin(d.folds, HELD_FOLDS)
    dev = np.isin(d.folds, DEV_FOLDS)
    nh = nulls_on(d, held)
    report["nulls_held"] = nh
    report["nulls_dev"] = nulls_on(d, dev)
    report["bar_held"] = bar_rule(nh)
    report["model_sealed_recipe_held"] = score(d, full, held)
    if not args.smoke:
        root = Path(str(paths()["scratch"]["corpus"]))
        report["ceiling_held"] = ceiling(
            d.soil_bin,
            root / "pilot-v1" / "corpus.parquet",
            root / "pilot-v1-s2" / "replicate_s2.parquet",
            d.y[held],
        )
    print(f"nulls on held-out folds: { {k: round(v['pooled'], 6) for k, v in nh.items()} }")
    print(f"bar on held-out folds: {report['bar_held']}", flush=True)

    # -- the screen -------------------------------------------------------------------------------
    rows: list[dict[str, Any]] = []
    b = evaluate(eng, base, rows, "A")
    # seed noise of the dev statistic: the sealed recipe under two other LightGBM seeds
    noise = [b["dev"]["pooled"]]
    for s in (11, 12):
        rr = dataclasses.replace(
            base, name=f"base seed {s}", params=(*base_params, ("random_state", s))
        )
        noise.append(evaluate(eng, rr, rows, "noise")["dev"]["pooled"])
    report["dev_seed_noise"] = {"values": noise, "sd": float(np.std(noise, ddof=1))}

    # 1. feature set: (a) +v3, (h) -soil, and both
    feats = {
        "base": b,
        "+v3": evaluate(eng, dataclasses.replace(base, name="a: +v3", v3=True), rows, "A"),
        "-soil": evaluate(eng, dataclasses.replace(base, name="h: -soil", soil=False), rows, "A"),
        "+v3-soil": evaluate(
            eng, dataclasses.replace(base, name="a+h: +v3 -soil", v3=True, soil=False), rows, "A"
        ),
    }
    # A feature set is admissible only if EACH of its components pays for itself: removing either
    # one costs more than MIN_GAIN. The best admissible set wins; the base is always admissible.
    without = {"+v3": ["base"], "-soil": ["base"], "+v3-soil": ["-soil", "+v3"], "base": []}
    admissible = [k for k in feats if all(_accept(feats[w], feats[k]) for w in without[k])]
    best_f = max(admissible, key=lambda k: feats[k]["dev"]["pooled"])
    cur = dataclasses.replace(
        base, v3="+v3" in best_f, soil="-soil" not in best_f, name=f"F[{best_f}]"
    )
    cur_row = feats[best_f]
    print(f"  -> feature set: {best_f}", flush=True)

    # 2. target form: (b) logs, (c) median + log-gaps
    tgt = {"sealed": cur_row}
    for mode, tag in (("log", "b"), ("gaps", "c")):
        tgt[mode] = evaluate(
            eng,
            dataclasses.replace(cur, target=mode, name=f"{tag}: {cur.name} T[{mode}]"),
            rows,
            "B",
        )
    best_t = max(tgt, key=lambda k: tgt[k]["dev"]["pooled"])
    if best_t != "sealed" and not _accept(cur_row, tgt[best_t]):
        best_t = "sealed"
    cur, cur_row = (
        dataclasses.replace(cur, target=best_t, name=f"{cur.name} T[{best_t}]"),
        tgt[best_t],
    )
    print(f"  -> target form: {best_t}", flush=True)

    # 3. two stages (f)
    s2 = evaluate(
        eng, dataclasses.replace(cur, stage2=True, name=f"f: {cur.name} +2stage"), rows, "C"
    )
    if _accept(cur_row, s2):
        cur, cur_row = dataclasses.replace(cur, stage2=True, name=f"{cur.name} +2stage"), s2
    print(f"  -> two-stage: {cur.stage2}", flush=True)

    # 4. tuning (d), on the dev folds only
    trial_log: list[dict[str, Any]] = []
    tuned = tune(eng, cur, args.trials, trial_log)
    report["tuning_trials"] = trial_log
    tr = evaluate(eng, dataclasses.replace(tuned, name=f"d: {tuned.name}"), rows, "D")
    if _accept(cur_row, tr):
        cur, cur_row = tuned, tr
    print(f"  -> tuned: {cur.params != base_params}", flush=True)

    # 5. bagging (e)
    bg = evaluate(
        eng, dataclasses.replace(cur, bag=args.bag, name=f"e: {cur.name} bag{args.bag}"), rows, "E"
    )
    if _accept(cur_row, bg):
        cur, cur_row = dataclasses.replace(cur, bag=args.bag, name=f"{cur.name} bag{args.bag}"), bg
    print(f"  -> bagged: {cur.bag > 1}", flush=True)
    # bagging of the sealed recipe alone, for the record
    evaluate(eng, dataclasses.replace(base, bag=args.bag, name=f"e: base bag{args.bag}"), rows, "E")

    report["recommended"] = {
        "recipe": dataclasses.asdict(cur),
        "dev": cur_row["dev"],
        "held": cur_row["held"],
    }
    print(f"RECOMMENDED (by the dev rule): {cur.name}", flush=True)

    # 6. learning curve (g): the sealed recipe and the recommended one
    curve: list[dict[str, Any]] = []
    for rec in (base, cur):
        for frac in (0.25, 0.5, 0.75, 1.0):
            reps = 1 if frac >= 1.0 else args.curve_repeats
            vals: dict[str, list[float]] = {"dev": [], "held": []}
            cells_used: dict[str, list[int]] = {"dev": [], "held": []}
            for k in range(reps):
                rr = dataclasses.replace(rec, train_frac=frac, subsample_seed=k)
                for regime, fold_set in (("dev", DEV_FOLDS), ("held", HELD_FOLDS)):
                    pred = eng.predict(rr, regime)
                    vals[regime].append(score(d, pred, np.isin(d.folds, fold_set))["pooled"])
                    n_train = [
                        int(_subsample(trn, frac, k, f).sum())
                        for f, trn, _ in splits(d.folds, regime)
                    ]
                    cells_used[regime].append(int(np.mean(n_train)))
            row = {
                "recipe": rec.name,
                "train_frac": frac,
                "repeats": reps,
                "dev_pooled_mean": float(np.mean(vals["dev"])),
                "held_pooled_mean": float(np.mean(vals["held"])),
                "dev_values": vals["dev"],
                "held_values": vals["held"],
                "train_cells_dev": int(np.mean(cells_used["dev"])),
                "train_cells_held": int(np.mean(cells_used["held"])),
            }
            curve.append(row)
            print(
                f"  curve {rec.name:30s} {frac:4.2f}  dev {row['dev_pooled_mean']:+.4f} "
                f"({row['train_cells_dev']} cells)  held {row['held_pooled_mean']:+.4f} "
                f"({row['train_cells_held']} cells)",
                flush=True,
            )
    report["learning_curve"] = curve
    report["candidates"] = rows
    report["fits"] = eng.fits
    report["seconds"] = time.time() - t_start
    print("\n".join(["", "HELD-OUT QUOTE (never used to choose):", *_summary(rows)]))
    dest = out / ("screen_smoke.json" if args.smoke else "screen.json")
    dest.write_text(json.dumps(report, indent=2, default=float))
    print(f"\nwrote {dest}  ({eng.fits} fits, {report['seconds']:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
