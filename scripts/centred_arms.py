#!/usr/bin/env python
"""THE CENTRED KILL TESTS' ARMS -- one implementation, shared by both model scripts.

    imported by  exp_model_pilot_response.py --centred     (the warming response)
                 exp_model_pilot_composition.py --centred  (the species mix)

WHAT THE CENTRED TESTS ASK. Both kill tests pass, but a model that sees the cell's starting forest
and NOT the perturbation it is asked about scores 64.8 % (warming) and 69 % (species mix) of the
headline, so most of each headline is "knowing the starting forest lets you guess its typical
change". `vegemu.centred` subtracts each cell's own mean change before scoring, so every prediction
that is constant within a cell scores exactly 0 -- and the model is then scored only on how the
response DIFFERS between perturbations at one place. See that module for the disclosure that
travels with every centred number: it discards the response to the design-average perturbation.

WHY THE MODEL IS NOT RE-FITTED ON A CENTRED TARGET. The model arm here is the sealed kill tests'
model, unchanged -- same features, parameters, folds and seed -- and its predictions are re-READ by
the centred statistic. So the centred score is a property of the model both kill tests already
passed, not of a new model tuned to the new question, and the uncentred diagnostic printed beside
it must reproduce the sealed headline.

THE ARMS, ALL SCORED BY THE SAME CENTRED ARITHMETIC ON THE SAME PAIRS:

  model               the full model of the sealed kill test
  7 information-free  `build_null_predictions`, unchanged. no_response is constant within a cell
                      (exactly 0); the per-level mean and the two proportional nulls vary by design
                      point, so they remain REAL competitors under centring
  cell_mean_oracle    each pair gets the cell's TRUE mean change: the best any within-cell-constant
                      prediction can do. Reads the held-out truth by design; exactly 0
  blind_model         the full model with the eleven forcing columns removed: the competitor this
                      test exists to beat. Its 29 rows per cell have identical features, so its
                      prediction is constant within a cell and it scores exactly 0 -- asserted
  scrambled_forcing   the forcing columns re-paired by an independent permutation per cell (seed
                      20260914, as in both earlier blind-arm diagnostics). A PLACEBO: it sees
                      forcing that varies across a cell's rows, but paired with the wrong response

⚠ WHY THE MODEL SCRIPTS IMPORT THIS MODULE INSIDE A FUNCTION. It imports both of them (the learner
from one, the forcing columns from the other), so a top-level import from either would be circular.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl

from exp_derive_nulls_pilot import build_null_predictions
from exp_model_pilot_composition import forcing_index, scramble_forcing
from exp_model_pilot_response import assert_no_leakage, decide, fit_predict_oof
from vegemu.centred import cell_mean_oracle, centred_per_level_and_pooled
from vegemu.results import append_result_block
from vegemu.score import blocked_spatial_folds

Array = npt.NDArray[np.float64]
UncentredScorer = Callable[[Array, Array, list[str], tuple[str, ...]], dict[str, object]]

SCRAMBLE_SEED = 20260914
LEARNED_PLACEBOS: tuple[str, ...] = ("blind_model", "scrambled_forcing")
EXTRA_NULLS: tuple[str, ...] = ("cell_mean_oracle", *LEARNED_PLACEBOS)


@dataclass(frozen=True)
class Problem:
    """One kill test's arrays, aligned by the scripts' own `build_deltas` / `build_features`."""

    x: Array
    names: list[str]
    dtrue: Array
    control: Array
    scored_cells: pl.DataFrame
    points: list[str]
    quantities: tuple[str, ...]


def assert_constant_within_cell(pred: Array, label: str) -> None:
    """Refuse if a prediction that must be constant within each cell is not, bit for bit.

    The blind model's claim to score exactly 0 rests on this, so it is checked on the actual
    predictions rather than argued from the feature list.
    """
    finite = np.isfinite(pred)
    lo = np.where(finite, pred, np.inf).min(axis=1)
    hi = np.where(finite, pred, -np.inf).max(axis=1)
    bad = int((finite.any(axis=1) & (hi != lo)).sum())
    if bad:
        raise AssertionError(f"{label}: {bad} (cell, quantity) blocks vary within the cell")


def learned_placebos(p: Problem, folds: npt.NDArray[np.int64]) -> dict[str, Array]:
    """The blind and scrambled models' out-of-fold predictions: the same learner and folds as the
    model, and the same two constructions as the earlier blind-arm diagnostics, via the same
    functions."""
    idx = forcing_index(p.names)
    keep = [i for i in range(len(p.names)) if i not in set(idx)]
    print("  fitting blind_model", flush=True)
    blind = fit_predict_oof(p.x[:, :, keep], p.dtrue, folds, p.quantities)
    assert_constant_within_cell(blind, "blind_model")
    print("  fitting scrambled_forcing", flush=True)
    x_scrambled = scramble_forcing(p.x, idx, SCRAMBLE_SEED)
    scrambled = fit_predict_oof(x_scrambled, p.dtrue, folds, p.quantities)
    return {"blind_model": blind, "scrambled_forcing": scrambled}


def run_centred(
    p: Problem,
    *,
    k: int,
    degrees: float,
    threshold: float,
    statistic: str,
    uncentred: UncentredScorer,
    placebos_only: bool,
) -> dict[str, object]:
    """Every arm at one blocking radius, scored centred; the uncentred scores of the fitted models
    beside them as the apparatus check.

    `placebos_only` fits the blind and scrambled models and the information-free nulls but NOT the
    full model, so the placebo's value can be derived before the pre-registration is sealed without
    the answer being in the room.
    """
    lon = p.scored_cells["lon"].to_numpy().astype(np.float64)
    lat = p.scored_cells["lat"].to_numpy().astype(np.float64)
    folds = blocked_spatial_folds(lon, lat, k=k, degrees=degrees, seed=42)
    assert_no_leakage(p.names, folds, len(lon))
    print(f"\n=== centred, blocking {degrees:g} deg ===", flush=True)

    preds: dict[str, Array] = {}
    if not placebos_only:
        print("  fitting model", flush=True)
        preds["model"] = fit_predict_oof(p.x, p.dtrue, folds, p.quantities)
    preds.update(
        build_null_predictions(p.dtrue, p.control, p.scored_cells, p.points, k=k, degrees=degrees)
    )
    preds["cell_mean_oracle"] = cell_mean_oracle(p.dtrue)
    preds.update(learned_placebos(p, folds))

    arms = {
        n: centred_per_level_and_pooled(v, p.dtrue, p.points, p.quantities)
        for n, v in preds.items()
    }
    fitted = [n for n in ("model", *LEARNED_PLACEBOS) if n in preds]
    report: dict[str, object] = {
        "blocking_degrees": degrees,
        "k_folds": k,
        "arms": arms,
        "uncentred_diagnostics": {
            n: uncentred(preds[n], p.dtrue, p.points, p.quantities)["pooled"] for n in fitted
        },
    }
    for n, v in arms.items():
        print(f"  {n:32s} {v['pooled']:+.6f}", flush=True)
    if not placebos_only:
        nulls = {n: v for n, v in arms.items() if n != "model"}
        decision = decide(arms["model"], nulls, threshold, statistic)
        report["decision"] = decision
        print(f"  best null {decision['best_null']} {decision['best_null_value']:+.6f}")
        print(f"  margin    {decision['margin_model_minus_best_null']:+.6f}  needs > {threshold}")
    return report


def run_all_radii(
    p: Problem,
    *,
    k: int,
    radii: tuple[float, ...],
    threshold: float,
    statistic: str,
    uncentred: UncentredScorer,
    placebos_only: bool,
) -> dict[str, object]:
    """`run_centred` at every radius, plus -- unless `placebos_only` -- the decision and the flat
    block `tools/append_result.py` reads, built from the FIRST (primary) radius only: the others are
    pre-declared sensitivity checks, reported beside it and never as the number of record."""
    by = {
        f"{d:g}deg": run_centred(
            p,
            k=k,
            degrees=d,
            threshold=threshold,
            statistic=statistic,
            uncentred=uncentred,
            placebos_only=placebos_only,
        )
        for d in radii
    }
    out: dict[str, object] = {"statistic": statistic, "by_blocking": by}
    if not placebos_only:
        primary = by[f"{radii[0]:g}deg"]
        out["decision"] = primary["decision"]
        arms: dict[str, dict[str, object]] = primary["arms"]  # type: ignore[assignment]
        out.update(
            append_result_block(
                statistic=statistic,
                arms={n: float(v["pooled"]) for n, v in arms.items()},  # type: ignore[arg-type]
                n=int(p.dtrue.shape[0] * p.dtrue.shape[1]),
            )
        )
    return out
