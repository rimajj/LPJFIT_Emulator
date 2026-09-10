#!/usr/bin/env python
"""Why the level model's rooting depth is wrong, and which fix actually moves the band test.

    NCPUS=16 TIME=03:00:00 scripts/sbatch_py.sh T-screen-d95max scripts/screen_d95max.py

WHY THIS RUN EXISTS. `20260909-T-imposing-rooting-depth-works-and-does-not-help.md` left one
action: predict `D95max` better. Three of the 22 scored quantities are its quantiles, and the
leave-one-out oracle says they are worth +0.0419 on a conjunctive score of 0.0361 -- more than
every other quantity combined. This script screens candidate fixes against that same score.

WHAT THE DIAGNOSTIC ALREADY SHOWED, and therefore what is screened here
  * NOT the noise floor. An out-of-fold prediction is independent of the held-out cell's own seed
    draw, so Var(pred-truth) = Var(pred-mu) + sigma^2/2 with sigma^2 estimated from the two seeds.
    For `D95max_p50`, 82 % of the error variance is on the reducible side (sd 0.319 of 0.353 in
    logs); for `D95max_p10`, 64 %. There is real room, so the question is what to spend it on.
  * The error is SHRINKAGE, not scatter. Mean log residual runs +0.576 in the lowest decile of
    `D95max_p50` to -0.294 in the highest; the lowest decile passes 16 % of cells. A squared-error
    loss in logs returns the conditional MEAN, and the conditional distribution near the trait's
    lower bound is a pile-up with a long upper tail -- so the mean sits far above the median, and
    the band test scores the median. Hence the L1 arms.
  * The trait is BOUNDED, not positive-unbounded. `par/pft.js` sets D95max to [51, 1800] mm and
    3.3 % of cells sit within 1 mm of the floor on `D95max_p10`. `exp()` of an unbounded fit
    respects neither end. Hence the logit arms.
  * SOIL TEXTURE IS MISSING FROM THE FEATURES. Rooting depth is selected by how much water the
    column holds, and the corpus carries soil DEPTH but not soil TYPE. Soil code explains only
    2.5-3.0 % of the `D95max` residual as a main effect, which is small but free; the arm here
    tests it with the derived plant-available water capacity as well, because depth x texture is
    the physical quantity and neither factor alone is. ⚠ `src/vegemu/corpus/**` is line D's, so
    this arm reads the soil file DIRECTLY as a probe. If it wins, the durable fix is an inbound
    request to D, not an edit here.

SELECTION DISCIPLINE. Choosing an arm by its held-out score is tuning on the test, which is what
`models/emulator.py` refuses to do for the hyperparameters. So the five blocked folds are split:
arms are compared on the SCREEN folds (0, 1, 2) only, and the winner is quoted on the CONFIRM
folds (3, 4), which no comparison here is allowed to look at. Both are printed, deliberately, so
that a later reader can see whether the choice would have differed -- but the number that may be
quoted is the confirm one. The fits are identical either way; the split costs nothing.

⚠ THIS SCRIPT MAKES NO SKILL CLAIM AND CARRIES NO EXPERIMENT ID. It reports a conjunctive score
computed by substituting one arm's three rooting-depth columns into the STORED out-of-fold
prediction matrix of `X-20260908-climate-state-map`, holding the other 19 quantities fixed. That
is a sensitivity of an existing result, not a new one. A number for the record requires re-running
the sealed experiment end to end with the winning recipe fixed in advance.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl
from lightgbm import LGBMRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.dataset import assemble, load_leg
from vegemu.models import EmulatorConfig
from vegemu.paths import paths
from vegemu.score import SCORED_CONJUNCTIVE, band_frac_conjunctive, band_hits

Array = npt.NDArray[np.float64]

# LightGBM names its own columns when fitted from an array, then sklearn's validator complains at
# predict time that the array it is handed has none. Harmless, and it drowns the arm table.
warnings.filterwarnings("ignore", message="X does not have valid feature names")

TARGETS: tuple[str, ...] = ("D95max_p10", "D95max_p50", "D95max_p90")
# par/pft.js, all four tree PFTs agree: "D95max": {"low": 51, "median": 900.255, "high": 1800.0}.
# The learner must not be able to leave this interval, and the pile-up at `LOW` is the failure.
LOW, HIGH = 51.0, 1800.0
SCREEN_FOLDS = (0, 1, 2)
CONFIRM_FOLDS = (3, 4)

# par/soil.js, indexed by the code stored in soil_code_test.soil.bin (1-based). Plant-available
# water is `w_fc - w_pwp`; sand and clay fractions come along because texture also sets how fast
# the column drains, which is a different selection pressure from how much it holds.
SOILPAR: dict[int, tuple[float, float, float]] = {
    # code: (w_fc - w_pwp, sand, clay)
    1: (0.398 - 0.284, 0.22, 0.58),  # clay
    2: (0.378 - 0.259, 0.06, 0.47),  # silty clay
    3: (0.295 - 0.205, 0.52, 0.42),  # sandy clay
    4: (0.345 - 0.214, 0.32, 0.34),  # clay loam
    5: (0.387 - 0.247, 0.10, 0.34),  # silty clay loam
    6: (0.256 - 0.143, 0.58, 0.27),  # sandy clay loam
    7: (0.292 - 0.139, 0.43, 0.18),  # loam
    8: (0.368 - 0.177, 0.17, 0.13),  # silt loam
    9: (0.228 - 0.100, 0.58, 0.10),  # sandy loam
    10: (0.368 - 0.177, 0.10, 0.30),  # silt
    11: (0.149 - 0.060, 0.82, 0.06),  # loamy sand
    12: (0.088 - 0.022, 0.92, 0.03),  # sand
    13: (0.398 - 0.284, 0.24, 0.48),  # clay (light)
}


# ------------------------------------------------------------------------------------------
# Target transforms. Each is a (forward, inverse) pair applied to the raw trait value.
# ------------------------------------------------------------------------------------------
def _log_fwd(y: Array) -> Array:
    return np.log(y)


def _log_inv(z: Array) -> Array:
    return np.exp(z)


def _logit_fwd(y: Array) -> Array:
    """log((y-LOW)/(HIGH-y)) -- the bounded interval mapped onto the whole line.

    Clipped a hair inside the bounds first: a value exactly at 51 is finite in the file but would
    be -inf here, and a single -inf poisons the whole fit.
    """
    eps = (HIGH - LOW) * 1e-4
    u = np.clip(y, LOW + eps, HIGH - eps)
    return np.log((u - LOW) / (HIGH - u))


def _logit_inv(z: Array) -> Array:
    return LOW + (HIGH - LOW) / (1.0 + np.exp(-np.clip(z, -40.0, 40.0)))


TRANSFORMS: dict[str, tuple[Callable[[Array], Array], Callable[[Array], Array]]] = {
    "log": (_log_fwd, _log_inv),
    "logit": (_logit_fwd, _logit_inv),
}


@dataclass(frozen=True)
class Arm:
    """One candidate recipe for the three rooting-depth heads."""

    name: str
    transform: str = "log"
    objective: str = "regression"  # "regression" is L2; "regression_l1" is L1
    soil: bool = False
    config: EmulatorConfig = field(default_factory=EmulatorConfig)
    note: str = ""


BASE = EmulatorConfig()
ARMS: tuple[Arm, ...] = (
    Arm("baseline", note="the shipped recipe, refitted here; the control"),
    Arm("l1", objective="regression_l1", note="conditional median instead of conditional mean"),
    Arm("logit", transform="logit", note="bounded target, still L2"),
    Arm("logit_l1", transform="logit", objective="regression_l1", note="bounded target, L1"),
    Arm("soil", soil=True, note="baseline + soil texture and water capacity"),
    Arm(
        "capacity",
        config=replace(BASE, n_estimators=3000, learning_rate=0.02, min_child_samples=10),
        note="6x the trees at 0.4x the rate: is the baseline simply underfitting?",
    ),
    Arm(
        "l1_soil_capacity",
        objective="regression_l1",
        soil=True,
        config=replace(BASE, n_estimators=3000, learning_rate=0.02, min_child_samples=10),
        note="every lever that helped, together",
    ),
)


def soil_columns(cells: npt.NDArray[np.int64], soil_bin: Path, soildepth: Array) -> Array:
    """(awc_mm, w_avail_frac, sand, clay) per cell, read straight from the model's own input.

    One unsigned byte per cell, no header, in grid order -- so a cell id indexes it directly. An
    unknown code (0, or anything outside par/soil.js) becomes NaN rather than a silent zero:
    LightGBM handles a missing value, whereas a zero would read as "holds no water at all".
    """
    codes = np.fromfile(soil_bin, dtype=np.uint8)
    sel = codes[cells].astype(np.int64)
    frac = np.array([SOILPAR.get(int(c), (np.nan,) * 3)[0] for c in sel], dtype=np.float64)
    sand = np.array([SOILPAR.get(int(c), (np.nan,) * 3)[1] for c in sel], dtype=np.float64)
    clay = np.array([SOILPAR.get(int(c), (np.nan,) * 3)[2] for c in sel], dtype=np.float64)
    # soildepth arrives in the units the .clm carries; awc is depth x available fraction, which is
    # monotone in the physical millimetres of storage whatever that unit turns out to be.
    return np.stack([soildepth * frac, frac, sand, clay], axis=1)


def fit_arm(
    arm: Arm,
    features: Array,
    truth: Array,
    folds: npt.NDArray[np.int64],
    soil: Array,
) -> tuple[Array, dict[str, float]]:
    """Out-of-fold predictions of the three rooting-depth quantiles under one recipe."""
    x = np.hstack([features, soil]) if arm.soil else features
    fwd, inv = TRANSFORMS[arm.transform]
    pred = np.full((x.shape[0], len(TARGETS)), np.nan)
    train_err: list[float] = []
    cfg = arm.config
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        for j in range(len(TARGETS)):
            z = fwd(truth[:, j])
            ok = tr & np.isfinite(z) & np.isfinite(x).all(axis=1)
            model = LGBMRegressor(
                objective=arm.objective,
                n_estimators=cfg.n_estimators,
                learning_rate=cfg.learning_rate,
                num_leaves=cfg.num_leaves,
                min_child_samples=cfg.min_child_samples,
                subsample=cfg.subsample,
                subsample_freq=cfg.subsample_freq,
                colsample_bytree=cfg.colsample_bytree,
                reg_lambda=cfg.reg_lambda,
                n_jobs=cfg.n_jobs,
                random_state=cfg.seed,
                verbose=-1,
            )
            model.fit(x[ok], z[ok])
            pred[te, j] = inv(np.asarray(model.predict(x[te])))
            # In-sample error of the same head, so an underfit is visible as train ~ test rather
            # than guessed at. Reported in logs for comparability across transforms.
            fit_in = inv(np.asarray(model.predict(x[ok])))
            train_err.append(float(np.std(np.log(fit_in) - np.log(truth[ok, j]))))
    return pred, {"train_sd_log": float(np.mean(train_err))}


def score_arm(
    pred: Array,
    truth: Array,
    band: Array,
    folds: npt.NDArray[np.int64],
    *,
    stored: Array,
    all_truth: Array,
    all_band: Array,
    idx: list[int],
) -> dict[str, object]:
    """Per-quantity band hits and the conjunctive score with only these columns swapped in."""
    swapped = stored.copy()
    swapped[:, idx] = pred
    out: dict[str, object] = {}
    for label, sel in (
        ("all", np.ones(len(folds), dtype=bool)),
        ("screen", np.isin(folds, SCREEN_FOLDS)),
        ("confirm", np.isin(folds, CONFIRM_FOLDS)),
    ):
        per = {}
        for j, q in enumerate(TARGETS):
            hit = band_hits(pred[sel, j : j + 1], truth[sel, j : j + 1], band[sel, j : j + 1])
            lerr = np.log(pred[sel, j]) - np.log(truth[sel, j])
            per[q] = {
                "pass": float(hit.mean()),
                "sd_log_err": float(np.std(lerr)),
                "median_abs_over_band": float(
                    np.median(np.abs(pred[sel, j] - truth[sel, j]) / band[sel, j])
                ),
            }
        out[label] = {
            "per_quantity": per,
            "conjunctive": band_frac_conjunctive(swapped[sel], all_truth[sel], all_band[sel]),
        }
    return out


def bias_profile(pred: Array, truth: Array, j: int) -> list[float]:
    """Mean log residual by decile of the truth -- the shrinkage signature, in one row."""
    t = truth[:, j]
    edges = np.percentile(t, np.arange(10, 100, 10))
    dec = np.clip(np.searchsorted(edges, t), 0, 9)
    r = np.log(pred[:, j]) - np.log(t)
    return [float(r[dec == d].mean()) for d in range(10)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0", help="corpus version")
    ap.add_argument("--out", type=Path, default=None, help="where the JSON report goes")
    ap.add_argument("--arms", default="", help="comma-separated subset of arm names")
    args = ap.parse_args()

    cfg = paths()
    out_dir = args.out or Path(str(cfg["scratch"]["exp"])) / "screen-d95max"
    out_dir.mkdir(parents=True, exist_ok=True)

    leg = load_leg("historical", args.version)
    a = assemble(leg, SCORED_CONJUNCTIVE, k=5, block_degrees=15.0)
    idx = [SCORED_CONJUNCTIVE.index(q) for q in TARGETS]
    truth, band = a.truth[:, idx], a.band[:, idx]

    stored_path = Path(str(cfg["scratch"]["exp"])) / "map-response-v0" / "oof_map.parquet"
    stored_df = pl.read_parquet(stored_path)
    if not np.array_equal(stored_df["cell"].to_numpy(), a.cells):
        raise SystemExit(f"{stored_path} does not cover the same cells as this assembly")
    stored = stored_df.select([f"pred_{q}" for q in SCORED_CONJUNCTIVE]).to_numpy().astype(float)
    base_conj = band_frac_conjunctive(stored, a.truth, a.band)

    depth = a.features[:, CLIMATE_FEATURES.index("soildepth")]
    soil = soil_columns(a.cells, Path(str(cfg["inputs"]["soil"])), depth)
    print(f"{a.n} cells, {len(CLIMATE_FEATURES)} climate features, soil probe adds 4", flush=True)
    print(f"stored conjunctive score of the shipped model: {base_conj:.4f}\n", flush=True)

    wanted = set(args.arms.split(",")) if args.arms else None
    report: dict[str, object] = {
        "basis": {
            "cells": int(a.n),
            "leg": "historical",
            "folds": "5 blocked, 15 deg",
            "stored_conjunctive": base_conj,
            "screen_folds": list(SCREEN_FOLDS),
            "confirm_folds": list(CONFIRM_FOLDS),
        },
        "arms": {},
    }
    for arm in ARMS:
        if wanted and arm.name not in wanted:
            continue
        t0 = time.time()
        pred, diag = fit_arm(arm, a.features, truth, a.folds, soil)
        s = score_arm(
            pred, truth, band, a.folds, stored=stored, all_truth=a.truth, all_band=a.band, idx=idx
        )
        secs = time.time() - t0
        entry = {
            "note": arm.note,
            "transform": arm.transform,
            "objective": arm.objective,
            "soil": arm.soil,
            "seconds": secs,
            **diag,
            "score": s,
            "bias_by_truth_decile": {
                q: bias_profile(pred, truth, j) for j, q in enumerate(TARGETS)
            },
        }
        if arm.name == "baseline":
            # THE CONTROL. This arm re-implements the shipped recipe, so it must land on the
            # predictions the sealed run already stored. If it does not, the harness differs from
            # the one that produced the reported score and every other arm here is measured
            # against the wrong thing -- so the discrepancy is printed, loudly, and kept.
            ref = stored[:, idx]
            rel = np.abs(pred - ref) / np.abs(ref)
            entry["reproduces_stored"] = {
                "max_rel_diff": float(np.nanmax(rel)),
                "median_rel_diff": float(np.nanmedian(rel)),
            }
            print(
                f"    CONTROL vs the stored sealed-run predictions: median rel diff "
                f"{np.nanmedian(rel):.2e}, max {np.nanmax(rel):.2e}",
                flush=True,
            )
        report["arms"][arm.name] = entry  # type: ignore[index]
        scr, con = s["screen"], s["confirm"]  # type: ignore[index]
        print(f"--- {arm.name}  ({arm.note}) -- {secs:.0f} s", flush=True)
        print(f"    train sd(log err) {diag['train_sd_log']:.4f}", flush=True)
        for q in TARGETS:
            p_s = scr["per_quantity"][q]  # type: ignore[index]
            p_c = con["per_quantity"][q]  # type: ignore[index]
            print(
                f"    {q:12s} pass screen {p_s['pass']:.4f} confirm {p_c['pass']:.4f}  "
                f"sd(log err) {p_s['sd_log_err']:.4f}",
                flush=True,
            )
        print(
            f"    conjunctive (this arm's D95max, the other 19 unchanged): "
            f"screen {scr['conjunctive']:.4f}  confirm {con['conjunctive']:.4f}  "
            f"all {s['all']['conjunctive']:.4f}\n",  # type: ignore[index]
            flush=True,
        )
        np.save(out_dir / f"pred_{arm.name}.npy", pred)

    dest = out_dir / "screen.json"
    dest.write_text(json.dumps(report, indent=2))
    print(f"wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
