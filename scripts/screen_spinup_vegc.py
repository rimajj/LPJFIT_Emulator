#!/usr/bin/env python
"""DEV SCREEN of recipes for vegetation carbon at the stored spin-up's equilibrium. NOT A CLAIM.

    NCPUS=64 PARTITION=priority TIME=12:00:00 scripts/sbatch_py.sh T-fea-spinscreen \\
        scripts/screen_spinup_vegc.py --workers 5 --threads 12 \\
        --out <scratch.exp>/T-screen-spinup-vegc

WHY. Both sealed tests of vegetation carbon at the stored global spin-up's constant-CO2
equilibrium failed the owner's rule, "as good as a rerun" (X-20260924-spinup-vegc-from-pilot and
-from-spinup): a second run of the model lands inside the band in 85.9 % of the 56,986 cells, the
pilot-trained emulator in 24.7 %, a map trained on the stored spin-up's own cells in 42.7 %. This
screen looks for the inputs and learner that could close that gap, so the NEXT pre-registration
has a recipe worth testing. Every number it prints is a DEV DIAGNOSTIC.

THE ESTIMAND IS IMPORTED, NOT RESTATED: `exp_spinup_vegc` supplies the inputs, the scored set
(truth, band, rerun reference), the folds and the scoring function, so D, frac, skill and the
flat-10 % rate are computed by the sealed code. On a subset of cells the rerun reference is
restricted to the same subset (`subset`), so D always compares like with like.

THE SELECTION RULE -- fixed in this docstring before the screen was first run:
  * DEV = the scored cells of folds 0, 1 and 2. Each is predicted by a model trained on the cells
    of the OTHER four folds (the sealed construction). The dev statistic is D on those cells.
  * HELD-OUT = the scored cells of folds 3 and 4, predicted the same way. PRINTED for every
    candidate, NEVER compared, never used to choose -- it is what a confirmation may score.
  * Greedy, in a fixed order (STEPS): feature set, target, two stages, objective, capacity,
    pooling the pilot, a zero floor, bagging. At each step every alternative is applied to the
    current recipe, the best by dev D is kept only if it beats the current recipe by more than
    MIN_GAIN; otherwise the simpler recipe stands.
  * Then a backward pass: each kept component is removed in turn, and dropped if the recipe
    without it is within MIN_GAIN of the recipe with it (dev D only).
  * Each alternative is ALSO run alone on the sealed baseline ("single"), so a change that only
    helps in combination, or only alone, is visible.
  ⚠ Tuning (capacity "tuned") selects the best of N trials ON the dev folds, so its dev number is
    optimistic by construction; its held-out number is the clean one. Early stopping uses an inner
    split of 15-degree tiles drawn from the TRAINING cells only.

⚠ NO LEAKAGE. No location column (cell, lon, lat, tile) and no CO2 is ever a feature -- the
sealed FORBIDDEN set is asserted against every feature list. A scored cell's own truth never
enters its prediction: its whole 15-degree tile is in the held-out fold. The two-stage gate's
tree-bearing flag is a TRAINING label only; a scored cell's own flag (which defines the scored
set) is never read by its prediction, which comes from its climate through the classifier.
The source of a pooled row (pilot or spin-up) is a sample weight only, never a feature.
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import sys
import time
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
from joblib import Parallel, delayed
from lightgbm import LGBMClassifier, LGBMRegressor, early_stopping

from exp_equilibrium_map import FEATURES, FORBIDDEN
from exp_model_pilot_response import PARAMS
from exp_spinup_vegc import STATISTIC, _inputs, global_folds, score, scored_set
from vegemu.corpus.features_v3 import V3_ALL, V3_ALLP, V3_FEATURES
from vegemu.paths import paths
from vegemu.score import blocked_spatial_folds, spatial_blocks

Array = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]

# sklearn's name check misfires on LightGBM 4.6 fitted and predicted on plain arrays alike.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

DEV_FOLDS: tuple[int, ...] = (0, 1, 2)
HELD_FOLDS: tuple[int, ...] = (3, 4)
MIN_GAIN = 0.005  # half a percentage point of cells inside the band
INNER_FRAC = 0.15  # share of training tiles held back for early stopping
PATIENCE = 200
FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "base": tuple(FEATURES),
    "v3": tuple(FEATURES) + V3_FEATURES,
    "v3x": tuple(FEATURES) + V3_ALL,
    "v3p": tuple(FEATURES) + V3_ALLP,  # only when the features_v3p tables are given (round 2)
}
TARGETS: tuple[str, ...] = ("win", "half2", "win_seeds", "half2_seeds")
BIG: dict[str, Any] = {
    "n_estimators": 8000,
    "learning_rate": 0.03,
    "num_leaves": 127,
    "min_child_samples": 20,
}
# Recipes the error-structure bins are cut on.
CARBON_BINS: tuple[float, ...] = (0.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0, np.inf)
SHARE_BINS: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 0.9, 1.01)
TREND_BINS: tuple[float, ...] = (0.0, 1.0, 2.5, 5.0, 10.0, np.inf)
SPREAD_BINS: tuple[float, ...] = (0.0, 0.10, 0.2, 0.5, np.inf)
LAT_BINS: tuple[float, ...] = (-60.0, -23.5, 0.0, 23.5, 50.0, 60.0, 90.0)


@dataclass(frozen=True)
class Recipe:
    name: str
    feats: str = "base"
    target: str = "win"
    gate: str = "none"  # none | hard | soft: tree-bearing or not, then carbon
    objective: str = "l2"  # l2 | huber (centred on the training mean) | l1, all on log1p
    capacity: str = "sealed"  # sealed | big | tuned
    params: tuple[tuple[str, Any], ...] = ()  # the tuned settings
    pool: str = "spinup"  # spinup | pilot | both
    pilot_weight: float = 1.0
    zero_floor: float = 0.0  # a prediction below this many gC/m2 becomes exactly 0
    bag: int = 1

    def lgbm(self, threads: int, seed: int | None) -> dict[str, Any]:
        p: dict[str, Any] = dict(PARAMS)
        if self.capacity == "big":
            p.update(BIG)
        p.update(dict(self.params))
        if self.objective in ("huber", "huber_centred"):
            # alpha is the Huber delta in log1p units AND caps each tree's step at lr * alpha
            # (LightGBM's Huber hessian is 1), so a small delta cannot converge in 600 trees.
            p.update(objective="huber", alpha=0.5)
        elif self.objective == "l1":
            p.update(objective="regression_l1")
        p["n_jobs"] = threads
        if seed is not None:
            p["random_state"] = seed
        return p

    @property
    def early_stops(self) -> bool:
        return self.capacity in ("big", "tuned")

    def key(self) -> str:
        d = dataclasses.asdict(self)
        d.pop("name")
        return json.dumps(d, sort_keys=True, default=str)


@dataclass
class Data:
    """Everything the screen fits on, aligned by construction and asserted."""

    xg: dict[str, Array]  # feature set -> (67420, F), the 1901-1930 window of every cell
    xp: dict[str, Array]  # feature set -> (200, 30, F), each pilot run's own climate
    yg: dict[str, Array]  # target -> (67420,) or (67420, 2) per seed
    yp: dict[str, Array]  # target -> (200, 30) or (200, 30, 2)
    tb_g: BoolArray  # (67420,) any stem in restart_1999: a TRAINING label for the gate
    tb_p: BoolArray  # (200, 30) any stem at the end of the pilot run
    folds_g: IntArray  # (67420,) the sealed tile -> fold map; -1 = a tile no pilot cell covers
    folds_p: IntArray  # (200,)
    tiles_g: IntArray  # (67420,) 15-degree tile ids
    tiles_p: IntArray  # (200,)
    sc: dict[str, Array]  # exp_spinup_vegc.scored_set
    extra: dict[str, Array]  # per scored cell: tree share, trend, spread (error structure only)


# --------------------------------------------------------------------------------------------
# Loading.
# --------------------------------------------------------------------------------------------


def _pilot_grid(table: pl.DataFrame, cells: IntArray, points: Sequence[str]) -> pl.DataFrame:
    t = table.sort(["cell", "point"])
    got_cells = t["cell"].unique().sort().to_numpy()
    assert np.array_equal(got_cells, cells), "the pilot table holds different cells"
    assert t.height == cells.size * len(points)
    assert (t["point"].to_numpy().reshape(cells.size, len(points)) == np.array(points)).all()
    return t


def load(v3x_dir: Path, v3p_dir: Path | None = None) -> Data:  # noqa: PLR0915 -- one flat pass
    inp = _inputs()
    corpus = Path(str(paths()["scratch"]["corpus"]))
    spin = corpus / "spinup-constco2"
    truth: pl.DataFrame = inp["truth"]  # type: ignore[assignment]
    points: list[str] = list(inp["points"])  # type: ignore[call-overload]
    traj = pl.read_parquet(spin / "pilot_trajectory_stats.parquet")
    cells_p = traj["cell"].unique().sort().to_numpy().astype(np.int64)
    assert cells_p.size == 200

    x_g = np.asarray(inp["x_g"])
    x_p = np.asarray(inp["x_p"])
    assert x_g.shape == (67420, len(FEATURES)) and x_p.shape == (200, len(points), len(FEATURES))
    # The pilot loader's cell order is the sorted cell ids; check it through the coordinates.
    lon_g, lat_g = np.asarray(inp["lon_g"]), np.asarray(inp["lat_g"])
    assert np.allclose(np.asarray(inp["lon_p"]), lon_g[cells_p])
    assert np.allclose(np.asarray(inp["lat_p"]), lat_g[cells_p])

    src, tag = (v3x_dir, "v3x") if v3p_dir is None else (v3p_dir, "v3p")
    v3_g = pl.read_parquet(src / f"features_{tag}_spinup.parquet").sort("cell")
    assert np.array_equal(v3_g["cell"].to_numpy(), np.arange(67420))
    v3_p = _pilot_grid(pl.read_parquet(src / f"features_{tag}_pilot.parquet"), cells_p, points)
    xg: dict[str, Array] = {}
    xp: dict[str, Array] = {}
    for name, cols in FEATURE_SETS.items():
        if name == "v3p" and v3p_dir is None:
            continue
        assert not FORBIDDEN & set(cols), f"a forbidden column is in feature set {name}"
        assert not any("co2" in c.lower() for c in cols), "CO2 is never a feature"
        extra = [c for c in cols if c not in FEATURES]
        eg = v3_g.select(extra).to_numpy().astype(np.float64) if extra else np.empty((67420, 0))
        ep = v3_p.select(extra).to_numpy().astype(np.float64) if extra else np.empty((6000, 0))
        xg[name] = np.concatenate([x_g, eg], axis=1)
        xp[name] = np.concatenate([x_p, ep.reshape(200, len(points), -1)], axis=2)

    def seeds(col: str) -> Array:
        return np.stack(
            [truth[f"{col}_s1"].to_numpy(), truth[f"{col}_s2"].to_numpy()], axis=1
        ).astype(np.float64)

    yg = {"win_seeds": seeds("vegc_win"), "half2_seeds": seeds("vegc_half2")}
    yg["win"] = yg["win_seeds"].mean(axis=1)
    yg["half2"] = yg["half2_seeds"].mean(axis=1)
    # The sealed target, as exp_spinup_vegc builds it: (s1 + s2) / 2 of the window mean.
    assert np.array_equal(
        yg["win"], ((truth["vegc_win_s1"] + truth["vegc_win_s2"]) / 2).to_numpy()
    ) or np.allclose(yg["win"], ((truth["vegc_win_s1"] + truth["vegc_win_s2"]) / 2).to_numpy())

    tr = _pilot_grid(traj.filter(pl.col("seed") == 1), cells_p, points)
    tr2 = _pilot_grid(traj.filter(pl.col("seed") == 2), cells_p, points)
    yp: dict[str, Array] = {}
    for col, tag in (("vegc_win", "win"), ("vegc_half2", "half2")):
        a = tr[col].to_numpy().reshape(200, -1)
        b = tr2[col].to_numpy().reshape(200, -1)
        yp[f"{tag}_seeds"] = np.stack([a, b], axis=2).astype(np.float64)
        yp[tag] = yp[f"{tag}_seeds"].mean(axis=2)
    assert np.allclose(yp["win"], np.asarray(inp["y_p"])), "pilot target differs from the sealed"

    stems = _pilot_grid(
        pl.read_parquet(corpus / "pilot-v2-constco2" / "corpus.parquet").select(
            "cell", "point", "stems_total"
        ),
        cells_p,
        points,
    )
    tb_p = stems["stems_total"].to_numpy().reshape(200, -1) > 0

    lon_p, lat_p = np.asarray(inp["lon_p"]), np.asarray(inp["lat_p"])
    folds_p = blocked_spatial_folds(lon_p, lat_p, k=5, degrees=15.0, seed=42).astype(np.int64)
    folds_g = global_folds(lon_p, lat_p, lon_g, lat_g)
    sc = scored_set(inp)
    mask = sc["mask"].astype(bool)
    sc["fold"] = folds_g[mask].astype(np.float64)
    bridge = pl.read_parquet(spin / "bridge_1999.parquet").sort("cell")
    g = {c: truth[c].to_numpy().astype(np.float64) for c in truth.columns if c != "vegetated"}
    h1, h2 = g["vegc_half1_s1"], g["vegc_half1_s2"]
    with np.errstate(divide="ignore", invalid="ignore"):
        spread = np.where((h1 + h2) / 2 > 1.0, np.abs(h1 - h2) / ((h1 + h2) / 2), 0.0)
    extra = {
        "tree_share": bridge["tree_share"].to_numpy().astype(np.float64)[mask],
        "trend": np.maximum(np.abs(g["trend_pct_century_s1"]), np.abs(g["trend_pct_century_s2"]))[
            mask
        ],
        "spread": spread[mask],
        "cell": np.arange(67420, dtype=np.float64)[mask],
    }
    return Data(
        xg=xg,
        xp=xp,
        yg=yg,
        yp=yp,
        tb_g=np.asarray(inp["tree_bearing"]).astype(bool),
        tb_p=tb_p,
        folds_g=folds_g,
        folds_p=folds_p,
        tiles_g=spatial_blocks(lon_g, lat_g, 15.0).astype(np.int64),
        tiles_p=spatial_blocks(lon_p, lat_p, 15.0).astype(np.int64),
        sc=sc,
        extra=extra,
    )


# --------------------------------------------------------------------------------------------
# The estimand on a subset of the scored cells.
# --------------------------------------------------------------------------------------------

_PER_CELL = ("t1", "t2", "tm", "w", "lat", "tile", "rerun_cell", "fold")


def subset(sc: dict[str, Array], sel: BoolArray) -> dict[str, Array]:
    """The scored set restricted to `sel` (over the scored cells), rerun reference included."""
    out = {k: np.asarray(sc[k])[sel] for k in _PER_CELL if k in sc}
    out["frac_rerun"] = float(np.asarray(out["rerun_cell"]).mean())  # type: ignore[assignment]
    out["band_is_floor"] = float((out["w"] == 0.10).mean())  # type: ignore[assignment]
    return out


def evaluate(pred_scored: Array, sc: dict[str, Array]) -> dict[str, dict[str, Any]]:
    """D, frac, skill and the flat-10 % rate on the dev and held-out folds, and on all cells."""
    fold = np.asarray(sc["fold"])
    out: dict[str, dict[str, Any]] = {}
    for name, folds in (("dev", DEV_FOLDS), ("held", HELD_FOLDS), ("all", (0, 1, 2, 3, 4))):
        sel = np.isin(fold, folds)
        sub = subset(sc, sel)
        r = score(pred_scored[sel], sub)
        out[name] = {
            "cells": int(sel.sum()),
            "D": r["D"],
            "frac": r["frac"],
            "frac_rerun": sub["frac_rerun"],
            "skill_log1p": r["skill_log1p"],
            "flat10": r["flat10_vs_two_seed_mean"],
            "D_p05_p95": r["D_tile_bootstrap_p05_p95"],
        }
    return out


# --------------------------------------------------------------------------------------------
# Fitting.
# --------------------------------------------------------------------------------------------


def training_rows(d: Data, r: Recipe, f: int) -> tuple[Array, Array, Array, IntArray, BoolArray]:
    """(X, log1p y, weight, tile, tree-bearing) of every training row for held-out fold `f`."""
    feats = r.feats
    xs: list[Array] = []
    ys: list[Array] = []
    ws: list[Array] = []
    ts: list[IntArray] = []
    bs: list[BoolArray] = []
    per_seed = r.target.endswith("_seeds")
    if r.pool in ("spinup", "both"):
        y = d.yg[r.target]
        ok = (d.folds_g != f) & (np.isfinite(y).all(axis=1) if per_seed else np.isfinite(y))
        x = d.xg[feats][ok]
        reps = 2 if per_seed else 1
        xs.append(np.concatenate([x] * reps))
        ys.append(np.concatenate([y[ok, 0], y[ok, 1]]) if per_seed else y[ok])
        ws.append(np.ones(x.shape[0] * reps))
        ts.append(np.concatenate([d.tiles_g[ok]] * reps))
        bs.append(np.concatenate([d.tb_g[ok]] * reps))
    if r.pool in ("pilot", "both"):
        trc = d.folds_p != f
        n_pt = d.xp[feats].shape[1]
        x = d.xp[feats][trc].reshape(-1, d.xp[feats].shape[2])
        y = d.yp[r.target][trc]
        reps = 2 if per_seed else 1
        xs.append(np.concatenate([x] * reps))
        if per_seed:
            ys.append(np.concatenate([y[..., 0].reshape(-1), y[..., 1].reshape(-1)]))
        else:
            ys.append(y.reshape(-1))
        ws.append(np.full(x.shape[0] * reps, r.pilot_weight))
        ts.append(np.concatenate([np.repeat(d.tiles_p[trc], n_pt)] * reps))
        bs.append(np.concatenate([d.tb_p[trc].reshape(-1)] * reps))
    ytr = np.concatenate(ys)
    assert np.isfinite(ytr).all()
    return (
        np.concatenate(xs),
        np.log1p(np.maximum(ytr, 0.0)),
        np.concatenate(ws),
        np.concatenate(ts),
        np.concatenate(bs),
    )


def _inner_split(tiles: IntArray, f: int, seed: int) -> BoolArray:
    """True for the rows of a random INNER_FRAC of the training tiles (early stopping only)."""
    uniq = np.unique(tiles)
    rng = np.random.default_rng(1000 * seed + f)
    k = max(1, round(INNER_FRAC * uniq.size))
    val = rng.choice(uniq, size=k, replace=False)
    return np.isin(tiles, val)


@dataclass(frozen=True)
class Offset:
    """A fitted regressor plus a constant, for the centred Huber fit."""

    model: LGBMRegressor
    mu: float

    def predict(self, x: Array) -> Array:
        out: Array = self.model.predict(x) + self.mu
        return out


def _fit_reg(
    r: Recipe,
    x: Array,
    y: Array,
    w: Array,
    tiles: IntArray,
    *,
    f: int,
    threads: int,
    seed: int | None,
) -> tuple[LGBMRegressor | Offset, int]:
    p = r.lgbm(threads, seed)
    if r.objective == "huber":
        # LightGBM's Huber loss does not start from the mean and clips each gradient at alpha, so
        # on log1p carbon (mean ~6) it would spend its whole budget walking up to the level. Fit
        # the deviations from the training mean instead; `Offset` adds it back.
        mu = float(np.average(y, weights=w))
        m, it = _fit_reg(
            dataclasses.replace(r, objective="huber_centred"),
            x,
            y - mu,
            w,
            tiles,
            f=f,
            threads=threads,
            seed=seed,
        )
        return Offset(m, mu), it
    if not r.early_stops:
        m = LGBMRegressor(**p)
        m.fit(x, y, sample_weight=w)
        return m, int(p["n_estimators"])
    val = _inner_split(tiles, f, 0 if seed is None else seed)
    m = LGBMRegressor(**p)
    m.fit(
        x[~val],
        y[~val],
        sample_weight=w[~val],
        eval_set=[(x[val], y[val])],
        eval_sample_weight=[w[val]],
        callbacks=[early_stopping(PATIENCE, verbose=False)],
    )
    best = max(50, int(m.best_iteration_ or p["n_estimators"]))
    full = LGBMRegressor(**{**p, "n_estimators": best})
    full.fit(x, y, sample_weight=w)
    return full, best


def fit_predict_fold(
    d: Data, r: Recipe, f: int, threads: int
) -> tuple[IntArray, Array, dict[str, Any]]:
    """Predictions (gC/m2) for every global cell of fold `f`, from a model that never saw it."""
    x, y, w, tiles, tb = training_rows(d, r, f)
    te = np.flatnonzero(d.folds_g == f)
    x_te = d.xg[r.feats][te]
    logs: list[Array] = []
    info: dict[str, Any] = {"rows": int(y.size), "iters": []}
    # An objective like "l1+l2" is an ensemble: one fit per loss, averaged in log space.
    members = [dataclasses.replace(r, objective=o) for o in r.objective.split("+")]
    for b in range(r.bag):
        seed = None if b == 0 else b  # b = 0 is the sealed settings' own (default) seed
        prob = None
        if not (r.gate == "none" or tb.all() or (~tb).sum() < 50):
            cp = {**PARAMS, "n_jobs": threads}
            if seed is not None:
                cp["random_state"] = seed
            clf = LGBMClassifier(**cp)
            clf.fit(x, tb.astype(np.int64), sample_weight=w)
            prob = clf.predict_proba(x_te)[:, 1]
        for rm in members:
            if prob is None:
                m, it = _fit_reg(rm, x, y, w, tiles, f=f, threads=threads, seed=seed)
                logs.append(m.predict(x_te))
                info["iters"].append(it)
                continue
            m1, it1 = _fit_reg(rm, x[tb], y[tb], w[tb], tiles[tb], f=f, threads=threads, seed=seed)
            m0, it0 = _fit_reg(
                rm, x[~tb], y[~tb], w[~tb], tiles[~tb], f=f, threads=threads, seed=seed
            )
            l1, l0 = m1.predict(x_te), m0.predict(x_te)
            logs.append(
                np.where(prob >= 0.5, l1, l0) if r.gate == "hard" else prob * l1 + (1 - prob) * l0
            )
            info["iters"].append([it1, it0])
    pred = np.clip(np.expm1(np.mean(logs, axis=0)), 0.0, None)
    if r.zero_floor > 0:
        pred = np.where(pred < r.zero_floor, 0.0, pred)
    return te, pred, info


def predict_all(
    d: Data, r: Recipe, folds: Sequence[int], workers: int, threads: int
) -> tuple[Array, dict[str, Any]]:
    """A prediction for every cell of the given folds (NaN elsewhere), one model per fold."""
    res = Parallel(n_jobs=min(workers, len(folds)), prefer="threads")(
        delayed(fit_predict_fold)(d, r, f, threads) for f in folds
    )
    out = np.full(d.folds_g.size, np.nan)
    info: dict[str, Any] = {}
    for f, (te, pred, inf) in zip(folds, res, strict=True):
        out[te] = pred
        info[str(f)] = inf
    return out, info


# --------------------------------------------------------------------------------------------
# Tuning (dev folds only).
# --------------------------------------------------------------------------------------------


def tune(d: Data, r: Recipe, trials: int, workers: int, threads: int) -> dict[str, Any]:
    import optuna  # noqa: PLC0415 -- only the tuning step needs it; CI does not install it

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    mask = d.sc["mask"].astype(bool)
    fold = np.asarray(d.sc["fold"])
    dev = np.isin(fold, DEV_FOLDS)
    sub = subset(d.sc, dev)

    def objective(trial: Any) -> float:
        params = (
            ("learning_rate", trial.suggest_float("learning_rate", 0.02, 0.12, log=True)),
            ("num_leaves", trial.suggest_int("num_leaves", 15, 255, log=True)),
            ("min_child_samples", trial.suggest_int("min_child_samples", 3, 100, log=True)),
            ("colsample_bytree", trial.suggest_float("colsample_bytree", 0.2, 1.0)),
            ("subsample", trial.suggest_float("subsample", 0.5, 1.0)),
            ("reg_lambda", trial.suggest_float("reg_lambda", 1e-3, 30.0, log=True)),
            ("min_split_gain", trial.suggest_float("min_split_gain", 1e-6, 0.05, log=True)),
            ("max_bin", trial.suggest_categorical("max_bin", [255, 1023])),
            ("n_estimators", BIG["n_estimators"]),
        )
        rt = dataclasses.replace(r, capacity="tuned", params=params, bag=1)
        # Three folds at a time: give each the threads the five-fold runs share.
        per_fit = max(1, workers * threads // len(DEV_FOLDS))
        pred, _ = predict_all(d, rt, DEV_FOLDS, len(DEV_FOLDS), per_fit)
        return float(score(pred[mask][dev], sub)["D"])

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=0))
    study.optimize(objective, n_trials=trials)
    best = dict(study.best_params)
    return {
        "best_params": best,
        "best_dev_D": float(study.best_value),
        "trials": [
            {"number": t.number, "value": t.value, "params": t.params} for t in study.trials
        ],
    }


# --------------------------------------------------------------------------------------------
# The screen.
# --------------------------------------------------------------------------------------------

STEPS: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = (
    ("features", ({"feats": "v3"}, {"feats": "v3x"})),
    ("target", ({"target": "half2"}, {"target": "win_seeds"}, {"target": "half2_seeds"})),
    ("two stages", ({"gate": "hard"}, {"gate": "soft"})),
    ("objective", ({"objective": "huber"}, {"objective": "l1"})),
    ("capacity", ({"capacity": "big"}, {"capacity": "tuned"})),
    ("pool", ({"pool": "both"}, {"pool": "both", "pilot_weight": 0.25})),
    ("zero floor", ({"zero_floor": 10.0},)),
    ("bagging", ({"bag": 5},)),
)


def _label(change: dict[str, Any]) -> str:
    return ",".join(f"{k}={v}" for k, v in change.items())


def choose(current: float, alternatives: dict[str, float]) -> str | None:
    """The alternative with the best DEV D, if it beats `current` by more than MIN_GAIN."""
    if not alternatives:
        return None
    best = max(alternatives, key=lambda k: alternatives[k])
    return best if alternatives[best] > current + MIN_GAIN else None


def error_structure(pred: Array, d: Data, folds: Sequence[int]) -> dict[str, Any]:
    """Where a recipe fails: per-cell pass rate against the rerun's, in bins of the truth."""
    sc = d.sc
    sel = np.isin(np.asarray(sc["fold"]), folds)
    p = pred[sel]
    t1, t2, w, tm = (np.asarray(sc[k])[sel] for k in ("t1", "t2", "w", "tm"))
    model = (
        (np.abs(p - t1) <= w * np.abs(t1)).astype(float)
        + (np.abs(p - t2) <= w * np.abs(t2)).astype(float)
    ) / 2
    rerun = np.asarray(sc["rerun_cell"])[sel]
    logerr = np.log1p(p) - np.log1p(tm)
    cuts: dict[str, tuple[Array, tuple[float, ...]]] = {
        "carbon_gC_m2": (tm, CARBON_BINS),
        "tree_share_1999": (d.extra["tree_share"][sel], SHARE_BINS),
        "trend_pct_century_max_seed": (d.extra["trend"][sel], TREND_BINS),
        "spread_earlier_half": (d.extra["spread"][sel], SPREAD_BINS),
        "latitude": (np.asarray(sc["lat"])[sel], LAT_BINS),
    }
    out: dict[str, Any] = {
        "cells": int(sel.sum()),
        "frac": float(model.mean()),
        "frac_rerun": float(rerun.mean()),
        "median_abs_log_error": float(np.nanmedian(np.abs(logerr))),
        "share_over_predicted": float((logerr > 0).mean()),
        "truth_exactly_zero_cells": int((tm == 0).sum()),
    }
    for name, (v, bins) in cuts.items():
        rows = []
        for lo, hi in itertools.pairwise(bins):
            m = (v >= lo) & (v < hi)
            if not m.any():
                continue
            rows.append(
                {
                    "bin": [lo, hi],
                    "cells": int(m.sum()),
                    "frac": float(model[m].mean()),
                    "frac_rerun": float(rerun[m].mean()),
                    "D": float(model[m].mean() - rerun[m].mean()),
                    "median_abs_log_error": float(np.nanmedian(np.abs(logerr[m]))),
                    "median_log_error": float(np.nanmedian(logerr[m])),
                }
            )
        nan = ~np.isfinite(v)
        if nan.any():
            rows.append({"bin": "nan", "cells": int(nan.sum()), "frac": float(model[nan].mean())})
        out[name] = rows
    # How far off the misses are: the rate inside k times the band, k = 1, 1.5, 2, 3.
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.fmin(np.abs(p - t1) / (w * np.abs(t1)), np.abs(p - t2) / (w * np.abs(t2)))
    out["inside_k_bands"] = {str(k): float((ratio <= k).mean()) for k in (1.0, 1.5, 2.0, 3.0, 5.0)}
    return out


class Screen:
    def __init__(self, d: Data, workers: int, threads: int, trials: int) -> None:
        self.d, self.workers, self.threads, self.trials = d, workers, threads, trials
        self.cache: dict[str, dict[str, Any]] = {}
        self.preds: dict[str, Array] = {}
        self.tuned: dict[str, Any] = {}

    def run(self, r: Recipe) -> dict[str, Any]:
        if r.capacity == "tuned" and not r.params:
            r = self.with_tuned(r)
        k = r.key()
        if k in self.cache:
            return self.cache[k]
        t0 = time.time()
        pred, info = predict_all(self.d, r, (0, 1, 2, 3, 4), self.workers, self.threads)
        mask = self.d.sc["mask"].astype(bool)
        ev = evaluate(pred[mask], self.d.sc)
        rec = {
            "recipe": dataclasses.asdict(r),
            "eval": ev,
            "fit": info,
            "seconds": time.time() - t0,
        }
        self.cache[k] = rec
        self.preds[k] = pred
        print(
            f"  {r.name:48s} dev D {ev['dev']['D']:+.4f} frac {ev['dev']['frac']:.4f} "
            f"skill {ev['dev']['skill_log1p']:.4f} flat10 {ev['dev']['flat10']:.4f} | held D "
            f"{ev['held']['D']:+.4f} frac {ev['held']['frac']:.4f}  ({time.time() - t0:.0f} s)",
            flush=True,
        )
        return rec

    def with_tuned(self, r: Recipe) -> Recipe:
        base = dataclasses.replace(r, capacity="sealed", params=(), bag=1, name="")
        k = base.key()
        if k not in self.tuned:
            print(f"  tuning on the dev folds: {self.trials} trials", flush=True)
            self.tuned[k] = tune(self.d, base, self.trials, self.workers, self.threads)
            print(f"  best dev D {self.tuned[k]['best_dev_D']:+.4f}", flush=True)
        bp = self.tuned[k]["best_params"]
        params = tuple(sorted({**bp, "n_estimators": BIG["n_estimators"]}.items()))
        return dataclasses.replace(r, capacity="tuned", params=params)


# Round 2, added after round 1 had run (disclosed in its output): candidates that did not exist
# when round 1's order was fixed, each applied to round 1's final recipe by the same rule.
ROUND2: tuple[tuple[str, tuple[dict[str, Any], ...]], ...] = (
    ("productivity features", ({"feats": "v3p"},)),
    ("objective ensemble", ({"objective": "l1+l2"}, {"objective": "l1+huber"})),
)


def recipe_of(spec: dict[str, Any]) -> Recipe:
    """A Recipe back from its `dataclasses.asdict` JSON form."""
    params = tuple((str(k), v) for k, v in spec.get("params") or ())
    return Recipe(**{**spec, "params": params})


def round2(scr: Screen, round1: Path, report: dict[str, Any], out: Path) -> int:
    r1 = json.loads(round1.read_text())
    current = recipe_of(r1["best"]["recipe"])
    base = Recipe("sealed-spinup")
    rec = scr.run(dataclasses.replace(current, name="round-1 best"))
    cur_d = float(rec["eval"]["dev"]["D"])
    report["round"] = 2
    report["round1"] = {"path": str(round1), "best": r1["best"]}
    singles: list[dict[str, Any]] = []
    path: list[dict[str, Any]] = []
    for step, changes in ROUND2:
        print(f"== round 2 step {step}", flush=True)
        alts: dict[str, float] = {}
        recs: dict[str, Recipe] = {}
        for ch in changes:
            lab = _label(ch)
            singles.append(
                {"change": lab, **scr.run(dataclasses.replace(base, name=f"single {lab}", **ch))}
            )
            combo = dataclasses.replace(current, name=f"round-1 best +{lab}", **ch)
            alts[lab] = float(scr.run(combo)["eval"]["dev"]["D"])
            recs[lab] = combo
        pick = choose(cur_d, alts)
        path.append(
            {"step": step, "current_dev_D": cur_d, "alternatives": alts, "kept": pick or "none"}
        )
        if pick is not None:
            current, cur_d = recs[pick], alts[pick]
        print(f"  kept: {pick or 'none'}; current dev D {cur_d:+.4f}", flush=True)
    report["singles"] = singles
    report["path"] = path
    finish(scr, current, report, out)
    return 0


def main() -> int:  # noqa: PLR0915 -- one flat sequence of screen stages
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--v3x", default="", help="directory of features_v3x_*.parquet")
    ap.add_argument("--workers", type=int, default=5, help="folds fitted at once")
    ap.add_argument("--threads", type=int, default=8, help="LightGBM threads per fit")
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--quick", action="store_true", help="plumbing smoke: 40 trees, 2 trials")
    ap.add_argument("--round2", default="", help="a round-1 screen.json: test ROUND2 from its best")
    ap.add_argument("--v3p", default="", help="directory of features_v3p_*.parquet (round 2)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    v3x = Path(args.v3x) if args.v3x else Path(str(paths()["scratch"]["exp"])) / "T-features-v3x"
    if args.quick:
        PARAMS["n_estimators"] = 40
        BIG["n_estimators"] = 200

    v3p = None
    if args.round2:
        v3p = (
            Path(args.v3p) if args.v3p else Path(str(paths()["scratch"]["exp"])) / "T-features-v3p"
        )
    d = load(v3x, v3p)
    fold = np.asarray(d.sc["fold"])
    print(
        f"scored cells {fold.size}: dev (folds 0-2) {int(np.isin(fold, DEV_FOLDS).sum())}, "
        f"held-out (folds 3-4) {int(np.isin(fold, HELD_FOLDS).sum())}; rerun frac all "
        f"{d.sc['frac_rerun']:.6f}",
        flush=True,
    )
    scr = Screen(d, args.workers, args.threads, 2 if args.quick else args.trials)
    report: dict[str, Any] = {
        "statistic": STATISTIC,
        "label": "DEV SCREEN -- diagnostics for choosing a recipe, not evidence about the emulator",
        "selection": "dev = scored cells of folds 0-2; held-out folds 3-4 printed, never compared",
        "min_gain": MIN_GAIN,
        "features": {k: len(v) for k, v in FEATURE_SETS.items()},
        "quick": bool(args.quick),
    }

    if args.round2:
        return round2(scr, Path(args.round2), report, out)

    # Step 0: the sealed recipes, re-derived by this engine, all five folds.
    print("== step 0: reproduce the two sealed model arms", flush=True)
    sealed_s = scr.run(Recipe("sealed-spinup"))
    sealed_p = scr.run(Recipe("sealed-pilot", pool="pilot"))
    report["reproduction"] = {
        "spinup": {"D_all": sealed_s["eval"]["all"]["D"], "sealed": -0.4316498789176289},
        "pilot": {"D_all": sealed_p["eval"]["all"]["D"], "sealed": -0.612168},
    }
    print(f"  reproduction: {json.dumps(report['reproduction'])}", flush=True)

    base = Recipe("sealed-spinup")
    singles: list[dict[str, Any]] = []
    path: list[dict[str, Any]] = []
    current = base
    cur_d = float(sealed_s["eval"]["dev"]["D"])
    for step, changes in STEPS:
        print(f"== step {step}", flush=True)
        alts: dict[str, float] = {}
        recs: dict[str, Recipe] = {}
        for ch in changes:
            lab = _label(ch)
            if ch.get("capacity") != "tuned":  # tuning is run once, on the current recipe
                single = dataclasses.replace(base, name=f"single {lab}", **ch)
                singles.append({"change": lab, **scr.run(single)})
            combo = dataclasses.replace(current, name=f"{current.name} +{lab}", **ch)
            rec = scr.run(combo)
            alts[lab] = float(rec["eval"]["dev"]["D"])
            recs[lab] = combo
        pick = choose(cur_d, alts)
        path.append(
            {"step": step, "current_dev_D": cur_d, "alternatives": alts, "kept": pick or "none"}
        )
        if pick is not None:
            current, cur_d = recs[pick], alts[pick]
            if current.capacity == "tuned" and not current.params:
                current = scr.with_tuned(current)
        print(f"  kept: {pick or 'none'}; current dev D {cur_d:+.4f}", flush=True)
        (out / "screen_partial.json").write_text(
            json.dumps({**report, "singles": singles, "path": path}, indent=2, default=str)
        )

    # The backward pass: each kept component removed in turn, in the order it was kept. It goes
    # if the recipe without it is within MIN_GAIN of the recipe with it -- the forward rule's
    # price, read the other way. Dev D only.
    backward: list[dict[str, Any]] = []
    for step in [p["step"] for p in path if p["kept"] != "none"]:
        fields = {
            "features": {"feats": base.feats},
            "target": {"target": base.target},
            "two stages": {"gate": base.gate},
            "objective": {"objective": base.objective},
            "capacity": {"capacity": base.capacity, "params": ()},
            "pool": {"pool": base.pool, "pilot_weight": base.pilot_weight},
            "zero floor": {"zero_floor": base.zero_floor},
            "bagging": {"bag": base.bag},
        }[step]
        without = dataclasses.replace(current, name=f"{current.name} -{step}", **fields)
        d_without = float(scr.run(without)["eval"]["dev"]["D"])
        drop = d_without > cur_d - MIN_GAIN
        backward.append(
            {"step": step, "dev_D_with": cur_d, "dev_D_without": d_without, "dropped": drop}
        )
        print(f"  backward: without {step} dev D {d_without:+.4f} -> dropped {drop}", flush=True)
        if drop:
            current, cur_d = without, d_without
    report["backward"] = backward

    report["singles"] = singles
    report["path"] = path
    finish(scr, current, report, out)
    return 0


def finish(scr: Screen, current: Recipe, report: dict[str, Any], out: Path) -> None:
    """The best recipe's error structure, its pilot-only twin, and the outputs."""
    d = scr.d
    best = scr.run(current)
    pred_best = scr.preds[current.key()]
    mask = d.sc["mask"].astype(bool)
    report["best"] = {"recipe": dataclasses.asdict(current), "eval": best["eval"]}
    report["error_structure"] = {
        "dev": error_structure(pred_best[mask], d, DEV_FOLDS),
        "held": error_structure(pred_best[mask], d, HELD_FOLDS),
    }

    # The emulator proper: the same recipe trained on the pilot alone.
    print("== the best recipe with the pilot as its only training pool", flush=True)
    pilot_same = dataclasses.replace(current, name="best, pool=pilot", pool="pilot")
    pilot_sealed_learner = dataclasses.replace(
        current,
        name="best inputs+target, pool=pilot, sealed learner",
        pool="pilot",
        capacity="sealed",
        params=(),
        objective="l2",
    )
    report["pilot_only"] = {
        "same_recipe": scr.run(pilot_same),
        "sealed_learner": scr.run(pilot_sealed_learner),
    }
    pp = scr.preds[pilot_same.key()]
    report["pilot_only"]["error_structure_dev"] = error_structure(pp[mask], d, DEV_FOLDS)
    report["tuning"] = scr.tuned
    report["all_candidates"] = list(scr.cache.values())

    scr.run(Recipe("sealed-spinup"))  # cached in round 1; round 2 fits it once for the table
    sealed_pred = scr.preds[Recipe("sealed-spinup").key()]
    cells = np.flatnonzero(mask)
    pl.DataFrame(
        {
            "cell": cells.astype(np.int32),
            "fold": np.asarray(d.sc["fold"]).astype(np.int8),
            "pred_best": pred_best[mask],
            "pred_pilot_same_recipe": pp[mask],
            "pred_sealed_spinup": sealed_pred[mask],
            "t1": d.sc["t1"],
            "t2": d.sc["t2"],
            "w": d.sc["w"],
        }
    ).write_parquet(out / "predictions.parquet")
    (out / "screen.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {out / 'screen.json'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
