#!/usr/bin/env python
"""Derive what every null MUST return, before any model exists.

    scripts/exp_derive_nulls.py --version v0 --out <dir>

WHY THIS SCRIPT EXISTS AT ALL. `expected.value` in a pre-registration is not a guess about how the
null will do -- it is the number the null is REQUIRED to produce, so that a null which silently
misbehaves is distinguishable from a null that agreed with you. Every null in this project is a
deterministic function of the corpus and the fold assignment (`src/vegemu/nulls.py`), so every
value below is computed from the TRUTH ALONE. No model is fitted here and none is needed.

That is the point: deriving these numbers is not peeking. The thing under test is the emulator,
and nothing about the emulator is touched. What the derivation pins down is the APPARATUS -- the
fold assignment, the band, the cell set, the quantity list -- so that when line T reports the same
numbers for the same nulls, the apparatus is proven to be the one that was blessed.

Out-of-fold by construction: every cell is held out exactly once across the five folds, so the
statistic is computed once over the assembled out-of-fold prediction rather than averaged over
folds. Averaging fold-level fractions would weight a fold containing the Amazon the same as one
containing Patagonia.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt

from vegemu import nulls as null_mod
from vegemu.dataset import assemble, load_leg, response_pair
from vegemu.score import (
    RESPONSE_QUANTITIES,
    SCORED_CONJUNCTIVE,
    band_frac_conjunctive,
    band_frac_per_quantity,
    matrix,
    skill_response_mean,
    skill_vs_no_change,
)

SHUFFLE_SEED = 20260908


def _analogue_features(scored: object, names: tuple[str, ...]) -> npt.NDArray[np.float64]:
    idx = [scored.feature_names.index(n) for n in names]  # type: ignore[attr-defined]
    return scored.features[:, idx]  # type: ignore[attr-defined]


def oof_nulls(scored: object, y: npt.NDArray[np.float64]) -> dict[str, npt.NDArray[np.float64]]:
    """Out-of-fold predictions of every null, for a target matrix `y`."""
    folds = scored.folds  # type: ignore[attr-defined]
    lon, lat = scored.lon, scored.lat  # type: ignore[attr-defined]
    xa = _analogue_features(scored, null_mod.ANALOGUE_FEATURES)
    out = {name: np.full_like(y, np.nan) for name in
           ("climatological_mean", "geographic_address", "nearest_analogue", "shuffled_target")}
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        out["climatological_mean"][te] = null_mod.training_mean(y[tr], int(te.sum()))
        out["geographic_address"][te] = null_mod.nearest_geographic(
            lon[tr], lat[tr], y[tr], lon[te], lat[te]
        )
        out["nearest_analogue"][te] = null_mod.nearest_analogue(xa[tr], y[tr], xa[te])
        out["shuffled_target"][te] = null_mod.shuffled(y[te], SHUFFLE_SEED + int(f))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0")
    ap.add_argument("--out", default=None)
    ap.add_argument("--block-degrees", type=float, default=15.0)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    report: dict[str, object] = {
        "corpus_version": args.version,
        "split": {"kind": "blocked_spatial", "k": args.k, "block_degrees": args.block_degrees,
                  "fold_seed": 42},
        "shuffle_seed": SHUFFLE_SEED,
    }

    # ---------------------------------------------------------------------------------------
    # Experiment A -- the climate -> state map, conjunctive acceptance band.
    # ---------------------------------------------------------------------------------------
    hist = load_leg("historical", args.version)
    a = assemble(hist, SCORED_CONJUNCTIVE, k=args.k, block_degrees=args.block_degrees)
    print(f"map: {a.n} tree-bearing cells, {len(SCORED_CONJUNCTIVE)} scored quantities, "
          f"{len(np.unique(a.folds))} folds", flush=True)

    preds = oof_nulls(a, a.truth)
    map_nulls = {
        name: band_frac_conjunctive(p, a.truth, a.band) for name, p in preds.items()
    }
    # The CEILING, not a null: one realisation of the model, scored against the two-seed mean.
    # It always passes by construction (it sits at exactly half a band), so quoting it as a null
    # would set an unbeatable bar. It is here to say what "perfect" means on this metric.
    seed1 = matrix(hist.seed1.filter(__import__("polars").Series(
        (hist.seed1["stems_per_patch"].to_numpy() >= 0.5)
        & (hist.seed2["stems_per_patch"].to_numpy() >= 0.5)
    )), SCORED_CONJUNCTIVE)
    ceiling = band_frac_conjunctive(seed1, a.truth, a.band)

    report["map"] = {
        "n_cells": a.n,
        "quantities": list(SCORED_CONJUNCTIVE),
        "nulls": map_nulls,
        "single_realisation_ceiling": ceiling,
        "per_quantity_best_null": {
            name: band_frac_per_quantity(p, a.truth, a.band, SCORED_CONJUNCTIVE)
            for name, p in preds.items()
        },
        "band_median_relative": float(
            np.nanmedian(np.abs(a.band) / np.maximum(np.abs(a.truth), 1e-12))
        ),
    }
    print("\nExperiment A -- band_frac_conjunctive of each null:")
    for name, v in sorted(map_nulls.items(), key=lambda kv: -kv[1]):
        print(f"  {name:22s} {v:.6f}")
    print(f"  {'(ceiling: one seed)':22s} {ceiling:.6f}")

    # ---------------------------------------------------------------------------------------
    # Experiment B -- the warming response. Same-cell contrast, so geography is held fixed.
    # ---------------------------------------------------------------------------------------
    ssp = load_leg("ssp370", args.version)
    base, _future, delta = response_pair(
        hist, ssp, RESPONSE_QUANTITIES, k=args.k, block_degrees=args.block_degrees
    )
    print(f"\nresponse: {base.n} cells tree-bearing in both legs, "
          f"{len(RESPONSE_QUANTITIES)} quantities", flush=True)

    dpred = oof_nulls(base, delta)
    resp_nulls: dict[str, float] = {
        "no_response": skill_response_mean(np.zeros_like(delta), delta),
        "mean_response": skill_response_mean(dpred["climatological_mean"], delta),
        "geographic_address_response": skill_response_mean(dpred["geographic_address"], delta),
        "shuffled_response": skill_response_mean(dpred["shuffled_target"], delta),
        "analogue_response": skill_response_mean(dpred["nearest_analogue"], delta),
    }
    report["response"] = {
        "n_cells": base.n,
        "quantities": list(RESPONSE_QUANTITIES),
        "nulls": resp_nulls,
        "true_delta_summary": {
            q: {
                "mean": float(np.nanmean(delta[:, j])),
                "sd": float(np.nanstd(delta[:, j])),
                "frac_positive": float(np.nanmean(delta[:, j] > 0)),
                "base_mean": float(np.nanmean(base.truth[:, j])),
            }
            for j, q in enumerate(RESPONSE_QUANTITIES)
        },
        "per_quantity_no_response": dict(
            zip(RESPONSE_QUANTITIES,
                [float(v) for v in skill_vs_no_change(np.zeros_like(delta), delta)],
                strict=True)
        ),
    }
    print("\nExperiment B -- skill_response_mean of each null:")
    for name, v in sorted(resp_nulls.items(), key=lambda kv: -kv[1]):
        print(f"  {name:30s} {v:+.6f}")
    print("\ntrue change, per quantity (historical 1999 -> ssp370 2100):")
    for q, s in report["response"]["true_delta_summary"].items():  # type: ignore[index]
        print(f"  {q:18s} mean {s['mean']:+11.4g}  sd {s['sd']:11.4g}  "
              f"on a level of {s['base_mean']:11.4g}  ({s['frac_positive'] * 100:.1f} % rise)")

    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "derived_nulls.json").write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"\nwrote {dest / 'derived_nulls.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
