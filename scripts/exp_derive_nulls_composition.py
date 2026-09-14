#!/usr/bin/env python
"""THE APPARATUS for a composition kill test: what must each null return, and is the test readable?

    scripts/exp_derive_nulls_composition.py --out <dir> --cache <state.parquet>

WHAT THIS IS FOR. `models/synth.py` copies each tree's TYPE from the target cell's template roster,
so an emulated warmed forest is structurally forbidden from shifting its species mix; the
synthesiser's own docstring names the scored set as the thing that has to change first. The pilot
state table already carries `pft_frac_0..6` per (cell, climate), so the question is answerable today
without waiting for a new corpus. This script does NOT fit a model. It derives the apparatus -- the
nulls, their separation, the treeless bookkeeping and the ceiling -- which is what a
pre-registration needs before it can be written, and which line X's hard-won rule demands first:
X4's design collapsed on contact with its own null values, and sealing it would have pre-registered
a guaranteed `invalid`.

⚠ THIS IS A SEPARATE ESTIMAND, NOT AN EXTENSION OF THE SEALED ONE. The pilot response experiment
`X-20260909-pilot-warming-response` is sealed around "the unweighted mean of the seven"
`RESPONSE_QUANTITIES`, and its recorded model score of 0.5453 only reproduces while that tuple has
exactly seven members. Appending the seven composition columns to it would silently redefine a
sealed experiment and destroy the reproducibility of its own headline. So composition is its own arm
with its own nulls, and the two numbers are quoted separately and never summed.

THREE THINGS THIS FIXES THAT A NAIVE RUN WOULD GET WRONG.

1. TREELESS ROWS. `corpus/state.py` writes 0.0 into `pft_frac_*` for a cell with no stems, because
   it zeroes all of `STATE_COLUMNS` and then re-blanks only the trait quantiles. As a CHANGE that
   reads as "type 3's share fell from 0.81 to 0.00" -- which is not a shift in the mix, there is no
   mix, and it is the same collapse `stems_per_patch` already scores in full. Left in, it inflates
   the total squared change by 15-18 % on most types and would buy apparent composition skill with
   a collapse prediction. `blank_treeless_composition` restores the rule the trait medians already
   use, and the dropped-pair count is reported rather than absorbed.

2. THE DENOMINATOR HAS TO BE THE SAME FOR EVERY ARM. `score.skill_vs_no_change` computes its
   denominator over the rows where the PREDICTION is finite, so an arm that declines to answer on
   the hard rows is scored on an easier subset than its competitors. That asymmetry is harmless in
   the sealed response test, where the two nulls it can touch both scored negative -- but it is not
   harmless here, because 9.3 % of pairs are undefined and they cluster at the 17 cells that are
   already treeless under their own control. So every arm is scored on the identical set (the pairs
   where the TRUTH is defined) and a missing prediction is imputed as NO CHANGE -- the neutral
   filling, which is exactly what the `no_response` null says everywhere and keeps that null pinned
   analytically at 0.0. The imputation count is reported per arm, per quantity.

3. A BAR WITHOUT A CEILING CANNOT BE READ. The sealed response test was sealed with a bar of
   0.2257 and no statement of what perfect means, and its ceiling turned out to be 0.8697 rather
   than 1.0. The same derivation is run here so the composition bar arrives with its ceiling
   attached, from the same two ground-truth seeds and the same argument
   (`exp_derive_ceiling_pilot.py`): the target is a paired contrast of single stochastic runs, so a
   perfect emulator's residual is the model's own realisation noise.

WHAT THE NUMBER MEANS, AND THE LIMIT THAT TRAVELS WITH IT. `pft_frac_i` is the share of the cell's
STEMS of tree type i, counted per individual and NOT weighted by biomass. A type that is numerically
rare but holds the canopy therefore scores small. The seven shares sum to 1, so only six are free;
every arm is scored under the identical redundancy, but no single term is independent evidence.
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

from exp_derive_ceiling_pilot import ceiling, ground_truth_pair
from exp_derive_nulls_pilot import (
    CONTROL_POINT,
    _per_level_and_pooled,
    build_deltas,
    build_null_predictions,
    separation,
)
from vegemu.paths import paths
from vegemu.score import (
    COMPOSITION_QUANTITIES,
    blank_treeless_composition,
    matrix,
)

# "The mix shifted" in the plainest available terms: the type holding the most stems changed.
# Reported as a share of pairs, so the estimand's scale can be stated in a sentence a reader who has
# never opened this repository can check.
SHIFT_THRESHOLD = 0.05  # 5 percentage points of stem share


def impute_no_change(
    pred: npt.NDArray[np.float64], dtrue: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], dict[str, int]]:
    """Fill a non-finite prediction with 0.0 wherever the TRUTH is defined. See point 2 above.

    Returns the filled array and the per-quantity count of how many predictions had to be filled,
    because "this arm had nothing to say on 412 pairs" is a property of the arm that belongs beside
    its score. Filling with zero rather than dropping is what puts every arm on one denominator; it
    is also the least favourable honest filling, since no-change is the analytic floor.
    """
    scorable = np.isfinite(dtrue)
    need = scorable & ~np.isfinite(pred)
    filled = np.where(need, 0.0, pred)
    return filled, {q: int(need[:, :, j].sum()) for j, q in enumerate(COMPOSITION_QUANTITIES)}


def composition_scale(dtrue: npt.NDArray[np.float64]) -> dict[str, object]:
    """How much does the mix actually move? The go/no-go on whether this is worth scoring at all.

    A skill score on a quantity that never changes is unreadable however good it looks: the
    denominator SUM(dtrue^2) is then a sum of rounding noise. So the size of the target is measured
    and reported in the units a reader can judge -- percentage points of stem share -- before any
    null value is quoted.
    """
    out: dict[str, object] = {}
    for j, q in enumerate(COMPOSITION_QUANTITIES):
        v = dtrue[:, :, j]
        v = v[np.isfinite(v)]
        out[q] = {
            "scorable_pairs": int(v.size),
            "sum_squared_change": float((v**2).sum()),
            "rms_change": float(np.sqrt((v**2).mean())) if v.size else float("nan"),
            "p90_abs_change": float(np.percentile(np.abs(v), 90)) if v.size else float("nan"),
            "frac_pairs_moving_over_5pp": float((np.abs(v) > SHIFT_THRESHOLD).mean())
            if v.size
            else float("nan"),
        }
    return out


def row_index(state: pl.DataFrame) -> dict[tuple[int, str], int]:
    """`(cell, point) -> row`. Built once, so two diagnostics cannot disagree on row order."""
    return {
        (int(c), str(p)): i
        for i, (c, p) in enumerate(zip(state["cell"], state["point"], strict=True))
    }


def dominant_type_flip(
    state: pl.DataFrame, cell_ids: list[int], points: list[str]
) -> dict[str, object]:
    """In how many (cell, climate) pairs does the MOST ABUNDANT tree type change identity?

    The plain-language form of the whole question. A shift in the leading type is what a forester
    would call a change of forest, and it is precisely what a synthesiser that copies the roster can
    never produce, so this number is the one to quote when explaining why the arm exists.
    """
    index = row_index(state)
    frac = matrix(state, COMPOSITION_QUANTITIES)
    stems = state["stems_total"].to_numpy().astype(np.float64)

    flips = 0
    comparable = 0
    for cell in cell_ids:
        k0 = index[(cell, CONTROL_POINT)]
        if stems[k0] <= 0:
            continue
        lead0 = int(np.argmax(frac[k0]))
        for point in points:
            kj = index[(cell, point)]
            if stems[kj] <= 0:
                continue
            comparable += 1
            flips += int(np.argmax(frac[kj]) != lead0)
    return {
        "comparable_pairs": comparable,
        "pairs_with_a_different_leading_type": flips,
        "frac_pairs_with_a_different_leading_type": float(flips / comparable)
        if comparable
        else float("nan"),
    }


def treeless_bookkeeping(
    state: pl.DataFrame, cell_ids: list[int], points: list[str]
) -> dict[str, object]:
    """Which pairs lost their composition, and where the loss came from. Point 1, measured."""
    index = row_index(state)
    stems = state["stems_total"].to_numpy().astype(np.float64)
    ctl_treeless = [c for c in cell_ids if stems[index[(c, CONTROL_POINT)]] <= 0]
    arm_only = sum(
        1
        for c in cell_ids
        if stems[index[(c, CONTROL_POINT)]] > 0
        for p in points
        if stems[index[(c, p)]] <= 0
    )
    return {
        "total_pairs": len(cell_ids) * len(points),
        "cells_treeless_under_their_own_control": len(ctl_treeless),
        "pairs_dropped_because_the_control_has_no_mix": len(ctl_treeless) * len(points),
        "pairs_dropped_because_the_arm_went_treeless": arm_only,
        "note": (
            "A dropped pair is not a lost measurement: the collapse it represents is scored in "
            "full by stems_per_patch in the sealed response arm. Dropping it here only stops the "
            "same event being counted a second time as a shift in the species mix."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True, help="decoded pilot state parquet")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--also-degrees", type=float, default=5.0)
    ap.add_argument("--nproc", type=int, default=2, help="ground-truth seed reads")
    ap.add_argument("--skip-ceiling", action="store_true", help="smoke runs only")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version
    quantities = COMPOSITION_QUANTITIES

    raw = pl.read_parquet(args.cache)
    state = blank_treeless_composition(raw)
    cells = pl.read_csv(corpus / "cells.csv")

    dtrue, control, cell_ids, points = build_deltas(state, cells, quantities)
    scored_cells = cells.filter(pl.col("cell").is_in(cell_ids)).sort("cell")
    print(f"{len(cell_ids)} cells x {len(points)} points, {len(quantities)} composition columns")

    report: dict[str, object] = {
        "estimand": "skill_response_mean over the seven tree-type stem shares",
        "note": (
            "APPARATUS ONLY. No model is fitted here. Separate estimand from "
            "X-20260909-pilot-warming-response, whose seven quantities are unchanged."
        ),
        "version": args.version,
        "corpus": str(corpus),
        "quantities": list(quantities),
        "n_cells": len(cell_ids),
        "n_points": len(points),
        "n_pairs": int(dtrue.shape[0] * dtrue.shape[1]),
        "shift_threshold_stem_share": SHIFT_THRESHOLD,
        "target_scale": composition_scale(dtrue),
        "dominant_type_flip": dominant_type_flip(state, cell_ids, points),
        "treeless": treeless_bookkeeping(state, cell_ids, points),
        "by_blocking": {},
    }

    for degrees in (args.degrees, args.also_degrees):
        print(f"\n=== blocking {degrees:g} deg ===", flush=True)
        predictions = build_null_predictions(
            dtrue, control, scored_cells, points, k=args.k, degrees=degrees
        )
        nulls: dict[str, dict[str, object]] = {}
        imputed: dict[str, dict[str, int]] = {}
        for name, pred in predictions.items():
            filled, counts = impute_no_change(pred, dtrue)
            nulls[name] = _per_level_and_pooled(filled, dtrue, points, quantities)
            imputed[name] = counts
        sep = separation(nulls)
        report["by_blocking"][f"{degrees:g}deg"] = {  # type: ignore[index]
            "blocking_degrees": degrees,
            "k_folds": args.k,
            "nulls": nulls,
            "separation": sep,
            "predictions_imputed_as_no_change": imputed,
        }
        for name, value in sep["ranked"].items():  # type: ignore[index]
            print(f"  {name:32s} {value:+.6f}")
        print(f"  best null {sep['best_null']}, min adjacent gap {sep['min_adjacent_gap']}")

    if not args.skip_ceiling:
        print("\nreading both ground-truth seeds by seek for the ceiling...", flush=True)
        f1, f2 = ground_truth_pair(cell_ids, args.nproc)
        if f1["cell"].to_list() != cell_ids:
            raise ValueError("ground truth returned a different cell set than the pilot")
        # The same masking as the pilot: a treeless ground-truth cell has no mix either, so its
        # zeros would otherwise enter sigma as if they were a measured composition.
        s1 = matrix(blank_treeless_composition(f1), quantities)
        s2 = matrix(blank_treeless_composition(f2), quantities)
        # Var(s1 - s2) = 2 sigma^2. A cell treeless in either seed has no sigma and stays NaN; the
        # ceiling's own finite mask then drops it, which is the wanted behaviour.
        report["ceiling"] = ceiling(dtrue, (s1 - s2) ** 2 / 2.0, quantities)
        c0 = report["ceiling"]["rho0_independent"]  # type: ignore[index]
        print(f"\nCEILING, rho=0 (conservative lower bound): {c0['mean']:+.6f}")
        for q, v in c0["per_quantity"].items():
            print(f"    {q:16s} {v:+10.4f}")

    (out / "nulls_composition.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'nulls_composition.json'}")

    tl = report["treeless"]
    print(f"\ndropped pairs: control {tl['pairs_dropped_because_the_control_has_no_mix']}", end="")
    print(f" + arm {tl['pairs_dropped_because_the_arm_went_treeless']} of {tl['total_pairs']}")
    df = report["dominant_type_flip"]
    print(f"leading type changes in {df['frac_pairs_with_a_different_leading_type']:.4f} of pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
