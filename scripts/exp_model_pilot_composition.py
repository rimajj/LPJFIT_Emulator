#!/usr/bin/env python
"""THE MODEL ARM of the composition kill test, on the pilot ensemble.

    scripts/exp_model_pilot_composition.py --exp <id> --out <dir> --cache <state.parquet>

⚠ DO NOT RUN THIS UNTIL ITS PRE-REGISTRATION IS SEALED. Invariant 2, and `sbatch_py.sh --exp`
enforces it. The apparatus this arm is scored against -- every null's value, their separation, the
treeless bookkeeping and the ceiling -- was derived first by `exp_derive_nulls_composition.py` and
handed to line X, whose tree `experiments/**` is. Running the model before the seal would put the
answer in the room while the bar was still being written, which is the one ordering this repository
exists to prevent.

THE QUESTION. Shown a cell's real present-day forest and a perturbed climate, can the emulator
predict HOW THE MIX OF TREE TYPES CHANGES better than "every type's share changes by the same
fraction of what it already is"? This matters because the file-writing step cannot currently do it
at all: `models/synth.py` copies each tree's type from the target cell's own template roster, by
design and for a good reason -- letting type float put 31 % tropical evergreens into temperate cells
and the model killed them all inside a year -- so a warmed-climate restart carries present-day
composition. Whether that limit costs anything depends on whether the composition response is
learnable, and that is what this measures.

WHAT IS REUSED, AND WHY NOTHING IS RE-IMPLEMENTED. The features, the fold assignment, the leakage
assertions, the out-of-fold fit and the decision arithmetic all come from
`exp_model_pilot_response.py` unchanged. A second implementation of any of them could drift from the
one the nulls were derived under, and then the comparison in the decision rule would be between two
different quantities rather than between a model and its competitors. Only three things differ, and
each is a property of the estimand rather than of the model:

  * the targets are the seven tree-type stem shares, not the seven integrative quantities;
  * `pft_frac_*` is blanked wherever the cell has no stems, so a forest that DISAPPEARS is not
    scored as a forest that changed species -- that collapse is already scored in full by the stem
    count in the sealed response arm, and counting it twice would buy composition skill with a
    die-off prediction;
  * every arm is put on a common denominator before scoring, because `skill_vs_no_change` builds its
    denominator from the rows where the PREDICTION exists and 9.3 % of pairs here are undefined.
    Measured on the null derivation, the two nearest-neighbour competitors needed 2,296 and 1,253
    fills, so this is a live effect and not a precaution.

THE CONTROL COMPOSITION IS AN INPUT, deliberately and disclosed -- the same choice the response arm
made and for the same reason. In production a real restart for the cell under its present climate
always exists, so withholding it would test a task nobody has to solve, and it is exactly the
information the proportional null uses, which is what makes that null a fair competitor rather than
a handicap. For the 17 cells that are treeless under their own control the feature is NaN, which
LightGBM handles natively and which is the honest value: there is no mix to report.
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

from exp_derive_nulls_composition import impute_no_change
from exp_derive_nulls_pilot import _per_level_and_pooled, build_deltas, build_null_predictions
from exp_model_pilot_response import (
    assert_no_leakage,
    build_features,
    decide,
    fit_predict_oof,
)
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import (
    COMPOSITION_QUANTITIES,
    blank_treeless_composition,
    blocked_spatial_folds,
)

STATISTIC = "skill_composition_mean"


def scorable_pairs(dtrue: np.ndarray) -> dict[str, object]:
    """How many (cell, climate) pairs actually score, per tree type.

    Reported beside every number rather than in a footnote: a pair drops when the arm OR the control
    has no stems, so composition is scored where a forest existed at both ends, which selects toward
    the milder perturbations. Stating the count is what keeps that selection visible.
    """
    total = int(dtrue.shape[0] * dtrue.shape[1])
    per_q = {
        q: int(np.isfinite(dtrue[:, :, k]).sum()) for k, q in enumerate(COMPOSITION_QUANTITIES)
    }
    return {
        "total_pairs": total,
        "scorable_pairs_per_quantity": per_q,
        "dropped_pairs_per_quantity": {q: total - n for q, n in per_q.items()},
    }


def dry_run(
    x: np.ndarray,
    dtrue: np.ndarray,
    names: list[str],
    *,
    lon: np.ndarray,
    lat: np.ndarray,
    cell_ids: list[int],
    points: list[str],
    k: int,
    degrees: float,
) -> int:
    """Prove the plumbing and STOP, without fitting anything. Safe to run before the seal.

    ⚠ WHY THIS EXISTS. The first execution of a scored arm should not also be its first execution
    ever. Everything here is a shape, an alignment or an assertion -- it cannot produce the
    statistic and cannot leak the answer, so it is legitimate before the pre-registration is sealed,
    while running the real arm is not. A misalignment between the feature matrix and the targets
    would look exactly like a model with no skill, which is the one result this arm must never
    produce by accident.
    """
    folds = blocked_spatial_folds(lon, lat, k=k, degrees=degrees, seed=42)
    assert_no_leakage(names, folds, len(cell_ids))

    n_cells, n_points, n_q = dtrue.shape
    assert x.shape[:2] == (n_cells, n_points), f"features {x.shape} vs targets {dtrue.shape}"
    assert x.shape[2] == len(names), "feature count disagrees with the name list"
    assert n_q == len(COMPOSITION_QUANTITIES)
    assert len(points) == n_points and len(cell_ids) == n_cells

    # The control composition must be present as a feature, and must be MASKED for the cells that
    # have no forest to describe -- if it arrived as 0.0 the blanking silently did not happen.
    ctl_comp = [names.index(f"ctl_{q}") for q in COMPOSITION_QUANTITIES]
    ctl_block = x[:, 0, ctl_comp]
    treeless_ctl = int(np.isnan(ctl_block).all(axis=1).sum())

    # Every fold must hold out whole cells, and each cell exactly once.
    assert set(np.unique(folds)) == set(range(k)) or len(np.unique(folds)) <= k
    per_fold = {int(f): int((folds == f).sum()) for f in np.unique(folds)}

    print("\n=== DRY RUN: plumbing only, nothing fitted, no statistic computed ===")
    print(f"  features            {x.shape}  ({len(names)} named)")
    print(f"  targets             {dtrue.shape}")
    scorable = int(np.isfinite(dtrue[:, :, 0]).sum())
    print(f"  scorable pairs      {scorable} of {n_cells * n_points}")
    print(f"  cells per fold      {per_fold}")
    print(f"  control comp. NaN   {treeless_ctl} cells (expected 17: treeless under their control)")
    print(f"  non-finite features {int(np.isnan(x).sum())} of {x.size}")
    print("  leakage assertions  PASSED")
    print("\nplumbing is sound. The scored arm still needs a sealed pre-registration.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True, help="decoded pilot state parquet")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0, help="primary blocking radius")
    ap.add_argument("--also-degrees", type=float, default=5.0)
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.080,
        help="the pre-registered pass margin. MUST match the sealed decision rule.",
    )
    ap.add_argument("--exp-id", default="", help="stamped into the output for append_result.py")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="check the plumbing and STOP before fitting. Safe to run before the seal.",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version
    quantities = COMPOSITION_QUANTITIES

    state = blank_treeless_composition(pl.read_parquet(args.cache))
    cells = pl.read_csv(corpus / "cells.csv")
    design = pl.read_csv(corpus / "design.csv")

    dtrue, control, cell_ids, points = build_deltas(state, cells, quantities)
    scored_cells = cells.filter(pl.col("cell").is_in(cell_ids)).sort("cell")
    x, names = build_features(state, scored_cells, design, cell_ids, points)
    print(f"features: {len(names)} over {len(cell_ids)} cells x {len(points)} points", flush=True)

    lon = scored_cells["lon"].to_numpy().astype(np.float64)
    lat = scored_cells["lat"].to_numpy().astype(np.float64)

    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "arm": "model",
        "statistic": STATISTIC,
        "version": args.version,
        "corpus": str(corpus),
        "quantities": list(quantities),
        "n_cells": len(cell_ids),
        "n_points": len(points),
        "n_pairs": int(dtrue.shape[0] * dtrue.shape[1]),
        "n_features": len(names),
        "features": names,
        "treeless_bookkeeping": scorable_pairs(dtrue),
        "basis": (
            "Tree-type stem shares (share of INDIVIDUALS, not biomass-weighted) from the "
            "end-of-spin-up restart of pilot corpus v1: 200 cells x 30 climates x 1 seed, "
            "npatch=25, constant CO2 and CO2 never written. Within-cell paired contrast against "
            "the cell's own control climate. Dimensionless ratio of sums of squares, not a level."
        ),
        "by_blocking": {},
    }

    if args.dry_run:
        return dry_run(
            x,
            dtrue,
            names,
            lon=lon,
            lat=lat,
            cell_ids=cell_ids,
            points=points,
            k=args.k,
            degrees=args.degrees,
        )

    for degrees in (args.degrees, args.also_degrees):
        folds = blocked_spatial_folds(lon, lat, k=args.k, degrees=degrees, seed=42)
        assert_no_leakage(names, folds, len(cell_ids))
        print(f"\n=== blocking {degrees:g} deg ===", flush=True)

        dpred, _ = impute_no_change(fit_predict_oof(x, dtrue, folds, quantities), dtrue)
        model_score = _per_level_and_pooled(dpred, dtrue, points, quantities)

        nulls: dict[str, dict[str, object]] = {}
        imputed: dict[str, dict[str, int]] = {}
        for name, pred in build_null_predictions(
            dtrue, control, scored_cells, points, k=args.k, degrees=degrees
        ).items():
            filled, counts = impute_no_change(pred, dtrue)
            nulls[name] = _per_level_and_pooled(filled, dtrue, points, quantities)
            imputed[name] = counts

        decision = decide(model_score, nulls, threshold=args.threshold, statistic=STATISTIC)
        report["by_blocking"][f"{degrees:g}deg"] = {  # type: ignore[index]
            "blocking_degrees": degrees,
            "k_folds": args.k,
            "model": model_score,
            "nulls": nulls,
            "predictions_imputed_as_no_change": imputed,
            "decision": decision,
        }
        print(f"  model pooled      {decision['model_pooled']:+.6f}")
        print(f"  best null         {decision['best_null']} {decision['best_null_value']:+.6f}")
        print(f"  margin            {decision['margin_model_minus_best_null']:+.6f}")
        print(f"  needs             > {decision['required_model_value']:.6f}")
        print(f"  VERDICT           {decision['verdict']}")

    primary = report["by_blocking"][f"{args.degrees:g}deg"]  # type: ignore[index]
    report["decision"] = primary["decision"]
    # The flat block `tools/append_result.py` reads, from the PRIMARY blocking only: the 5-degree
    # arm is a pre-declared sensitivity check, reported beside it and never as the number of record.
    report.update(
        append_result_block(
            statistic=STATISTIC,
            arms={
                "model": float(primary["model"]["pooled"]),
                **{n: float(v["pooled"]) for n, v in primary["nulls"].items()},
            },
            n=int(report["n_pairs"]),  # type: ignore[arg-type]
        )
    )
    (out / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'metrics.json'}")

    print("\n=== per tree type (primary blocking) ===")
    for q, v in primary["model"]["per_quantity"].items():
        print(f"  {q:20s} {v:+.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
