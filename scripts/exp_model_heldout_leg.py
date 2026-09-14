#!/usr/bin/env python
"""THE MODEL ARM of the held-out forcing leg experiment.

    scripts/exp_model_heldout_leg.py --out <dir> [--version v0] [--test-leg ssp126]

`X-20260908-heldout-forcing-leg` was sealed on 2026-09-08 with every null derived and no model ever
fitted against it. This is that arm: a map fitted on the 1970-1999 climate and the 1999 forest,
handed the 2071-2100 climate of a leg whose state it has never seen, and asked for the year-2100
forest.

THE COMPETITOR THAT MATTERS IS PERSISTENCE -- handing back the cell's own present-day forest. The
emulator's whole claim is that it maps climate to state; if a changed climate cannot be told from
the present one on this metric, what has been measured is the band and not the model.

WHY THE SAME FITTED HEAD PREDICTS BOTH CLIMATES. `fit_out_of_fold` takes a LIST of feature
matrices and applies one fold's model to all of them, so the historical prediction and the ssp126
prediction come from identical parameters. Fitting two models would let fitting noise leak into
the difference between them, and that difference is the quantity under test.

THE BAND IS TRANSFERRED FROM THE HISTORICAL LEG, and that is the point of this experiment rather
than a detail. The map experiment took its tolerance from the same two seeds that defined its
truth, so a single realisation sat at exactly half a band and could not fail -- an apparent 1.0
ceiling that is an artefact. Here the tolerance comes from a DIFFERENT leg's two seeds, so nothing
about the scored realisation pair sets its own tolerance, and one draw of the real model scores
0.538490 rather than 1.000000. That 0.538490, not 1.0, is what perfect means on this metric. The
same-leg band is the pre-declared sensitivity arm: reported, never substituted.

RECIPES ARE DELIBERATELY EMPTY. `ROOTING_DEPTH_RECIPES` is measured and switched off, so this is
the shipped model byte for byte and the number it produces means what the other reported numbers
mean. Turning it on belongs to the next full refit, together with the soil columns requested from
line D -- the pair earned +0.0034 measured together and about half that apart.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

from exp_derive_nulls_leg import oof_nulls
from vegemu.dataset import assemble, load_leg, tree_bearing
from vegemu.models.emulator import EmulatorConfig, fit_out_of_fold
from vegemu.score import (
    SCORED_CONJUNCTIVE,
    acceptance_band_transferred,
    band_frac_conjunctive,
    band_frac_per_quantity,
    matrix,
)

THRESHOLD = 0.050


def assert_no_leakage(base: object, future: object, test_leg: str) -> None:
    """The pre-registration's leakage checks, asserted BEFORE anything is fitted.

    Pre-registered as "asserted in the fitting script", so they are assertions rather than prose.
    The one that matters most is the last: the two feature matrices are built from two separate
    climate tables and are never concatenated, so no scored cell's future climate can reach a
    training row.
    """
    names = tuple(base.feature_names)  # type: ignore[attr-defined]
    assert names == tuple(future.feature_names), (  # type: ignore[attr-defined]
        "the two legs must present identical feature columns in identical order"
    )
    for banned in ("lon", "lat", "cell"):
        assert banned not in names, f"coordinate/identity feature leaked in: {banned}"
    assert not any("co2" in n.lower() for n in names), "CO2 is never a feature (invariant 8)"
    # Same cells, same order, same folds -- otherwise a "held-out" row is not the row it scores.
    assert np.array_equal(base.cells, future.cells), "leg cell order diverged"  # type: ignore[attr-defined]
    assert np.array_equal(base.folds, future.folds), "leg fold assignment diverged"  # type: ignore[attr-defined]
    print(f"leakage assertions pass: {len(names)} features, {test_leg} state is never a target")


def decide(model_value: float, nulls: dict[str, float]) -> dict[str, object]:
    """The pre-registered decision rule, computed rather than eyeballed.

    Also names WHICH of the three pre-named outcomes this is. The pre-registration says the likely
    result is failure and that the informative part is the kind, so the script reports the kind
    rather than leaving it to a later reading of the numbers.
    """
    ranked = sorted(nulls.items(), key=lambda kv: -kv[1])
    best_name, best_value = ranked[0]
    margin = model_value - best_value
    persistence = nulls["same_cell_persistence"]

    if margin > THRESHOLD:
        kind = "pass"
    elif model_value > persistence:
        kind = "a_real_but_insufficient_response"
    elif abs(model_value - persistence) <= 0.002:
        kind = "b_matches_persistence_within_noise"
    else:
        kind = "c_below_persistence_actively_harmed"

    return {
        "statistic": "band_frac_conjunctive",
        "model": model_value,
        "best_null": best_name,
        "best_null_value": best_value,
        "same_cell_persistence": persistence,
        "margin_model_minus_best_null": margin,
        "threshold": THRESHOLD,
        "required_model_value": best_value + THRESHOLD,
        "verdict": "pass" if margin > THRESHOLD else "fail",
        "outcome_kind": kind,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0")
    ap.add_argument("--test-leg", default="ssp126")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--n-jobs", type=int, default=8)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    hist = load_leg("historical", args.version)
    fut = load_leg(args.test_leg, args.version)

    # Tree-bearing in BOTH seeds of BOTH legs: a cell with no forest at one end has no trait median
    # there, so a conjunctive trait test is undefined for it. Same rule as the null derivation.
    keep = tree_bearing(hist) & tree_bearing(fut)
    sel = pl.Series(keep)
    h1 = matrix(hist.seed1.filter(sel), SCORED_CONJUNCTIVE)
    h2 = matrix(hist.seed2.filter(sel), SCORED_CONJUNCTIVE)
    f1 = matrix(fut.seed1.filter(sel), SCORED_CONJUNCTIVE)
    f2 = matrix(fut.seed2.filter(sel), SCORED_CONJUNCTIVE)

    assert not np.array_equal(h1, h2), "the historical leg has no second realisation"
    assert not np.array_equal(f1, f2), f"the {args.test_leg} leg has no second realisation"

    truth_future, band_own = acceptance_band_transferred(f1, f2, f1, f2)
    _, band_transferred = acceptance_band_transferred(f1, f2, h1, h2)
    bands = {"transferred": band_transferred, "own": band_own}

    cfg = EmulatorConfig(n_jobs=args.n_jobs)
    report: dict[str, object] = {
        "exp_id": "X-20260908-heldout-forcing-leg",
        "arm": "model",
        "corpus_version": args.version,
        "test_leg": args.test_leg,
        "n_cells": int(keep.sum()),
        "quantities": list(SCORED_CONJUNCTIVE),
        "model": {"kind": "Emulator", "recipes": "EMPTY -- the shipped model", "config": vars(cfg)},
        "by_blocking": {},
    }
    print(f"scored cells, tree-bearing in both seeds of both legs: {report['n_cells']}", flush=True)

    for degrees in (15.0, 5.0):
        base = assemble(hist, SCORED_CONJUNCTIVE, k=args.k, block_degrees=degrees, mask=keep)
        future = assemble(fut, SCORED_CONJUNCTIVE, k=args.k, block_degrees=degrees, mask=keep)
        assert_no_leakage(base, future, args.test_leg)

        print(f"\n=== blocking {degrees:g} deg ===", flush=True)
        # Trained on the HISTORICAL leg only; `apply_to` gives both climates to the same head.
        (pred_hist, pred_future), _models = fit_out_of_fold(
            base.features,
            base.truth,
            base.folds,
            SCORED_CONJUNCTIVE,
            apply_to=[base.features, future.features],
            config=cfg,
        )
        nulls_pred = oof_nulls(base, future, truth_future)

        block: dict[str, object] = {"blocking_degrees": degrees, "k_folds": args.k}
        for bname, band in bands.items():
            null_scores = {
                n: float(band_frac_conjunctive(p, truth_future, band))
                for n, p in nulls_pred.items()
            }
            model_score = float(band_frac_conjunctive(pred_future, truth_future, band))
            decision = decide(model_score, null_scores)
            block[bname] = {
                "model": model_score,
                "nulls": null_scores,
                # The CEILING, not a null: one realisation of the real model against the two-seed
                # mean. Never quotable as skill -- it has seen the answer.
                "single_realisation_ceiling": float(band_frac_conjunctive(f1, truth_future, band)),
                "decision": decision,
                "model_per_quantity": band_frac_per_quantity(
                    pred_future, truth_future, band, SCORED_CONJUNCTIVE
                ),
            }
            print(f"\n  {bname} band:")
            print(f"    model                    {model_score:.6f}")
            for n, v in sorted(null_scores.items(), key=lambda kv: -kv[1]):
                print(f"    {n:24s} {v:.6f}")
            print(f"    (ceiling: one seed)      {block[bname]['single_realisation_ceiling']:.6f}")
            print(
                f"    margin {decision['margin_model_minus_best_null']:+.6f} "
                f"needs > {decision['required_model_value']:.6f} -> {decision['verdict']} "
                f"({decision['outcome_kind']})"
            )

        # DIAGNOSTIC, not an arm: the same model scored on the leg it was FITTED on, under that
        # leg's own band. This is the map experiment's number and belongs beside the held-out one,
        # labelled -- it is circular in exactly the way the transferred band exists to avoid.
        block["fitted_leg_own_band_diagnostic"] = float(
            band_frac_conjunctive(pred_hist, base.truth, base.band)
        )
        report["by_blocking"][f"{degrees:g}deg"] = block  # type: ignore[index]

    primary = report["by_blocking"]["15deg"]  # type: ignore[index]
    report["decision"] = primary["transferred"]["decision"]
    (out / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
