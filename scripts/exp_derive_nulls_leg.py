#!/usr/bin/env python
"""Derive what every null MUST return for the HELD-OUT FORCING LEG experiment.

    scripts/exp_derive_nulls_leg.py --out <dir> [--version v0] [--test-leg ssp126]

Companion to `exp_derive_nulls.py`, which does the same job for the two experiments scored on the
historical leg. Everything here is computed from the TRUTH ALONE -- no learner exists yet and none
is needed, because every null in this project is a deterministic function of the corpus and the fold
assignment. That is what lets a pre-registration record the value a null is REQUIRED to return
instead of a guess about how it might do.

THE QUESTION THIS APPARATUS SERVES. A map fitted on the 1970-1999 climate is asked for the year-2100
forest of a forcing leg it has never seen. The decisive competitor is not a learner but PERSISTENCE:
the same cell's own present-day forest. If a warmed climate cannot be told from the present one by
the acceptance band, then the band, not the model, is what has been measured.

TWO BANDS, BOTH REPORTED. `own` takes the tolerance from the scored leg's own two seeds, exactly as
the sealed map experiment does -- circular, because those same two seeds also define the truth.
`transferred` takes it from the HISTORICAL leg's two seeds for the same cell and quantity, which
breaks the circle: nothing about the scored realisation pair sets its own tolerance. The transfer is
licensed by measurement, not convenience -- the two legs' spread distributions agree to within 6 %
on every summary -- and this script prints that comparison so the claim travels with the number.

⚠ BUILD PROVENANCE. The historical leg came from the 2026-02-05 LPJmL-FIT build and the ssp126 leg
from the Aug-12 build, so any quantity crossing the two carries a build difference. That difference
is NOT unquantified any more: every behavioural change between the two builds is gated behind a
rung-2 environment variable that was unset in these runs, the two new struct fields are deliberately
absent from the restart serialisation, and the random-deviate generator changed only by hoisting a
static. See docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu import nulls as null_mod
from vegemu.dataset import assemble, load_leg, tree_bearing
from vegemu.score import (
    FLOOR,
    SCORED_CONJUNCTIVE,
    acceptance_band_transferred,
    band_frac_conjunctive,
    band_frac_per_quantity,
    matrix,
    relative_spread,
)

SHUFFLE_SEED = 20260908
NULL_IDS = (
    "same_cell_persistence",
    "nearest_analogue",
    "geographic_address",
    "climatological_mean",
    "shuffled_target",
)


def _analogue(scored: object) -> npt.NDArray[np.float64]:
    idx = [scored.feature_names.index(n) for n in null_mod.ANALOGUE_FEATURES]  # type: ignore[attr-defined]
    return scored.features[:, idx]  # type: ignore[attr-defined]


def oof_nulls(
    base: object,
    future: object,
    truth_future: npt.NDArray[np.float64],
) -> dict[str, npt.NDArray[np.float64]]:
    """Out-of-fold prediction of every null for the FUTURE state.

    The training pool is always the historical leg over the training folds -- that is the only state
    a model fitted on the historical leg could copy. What differs between the nulls is the key they
    look the neighbour up by:

      same_cell_persistence  no lookup at all: this cell's own historical state
      nearest_analogue       the training cell whose HISTORICAL climate is nearest this cell's
                             FUTURE climate -- space-for-time, the reviewer's null, in its natural
                             habitat rather than transplanted onto a within-leg comparison
      geographic_address     the geographically nearest training cell's historical state
      climatological_mean    the training folds' mean historical state
      shuffled_target        the future truth, permuted within the fold
    """
    folds = base.folds  # type: ignore[attr-defined]
    y_hist = base.truth  # type: ignore[attr-defined]
    lon, lat = base.lon, base.lat  # type: ignore[attr-defined]
    xa_hist = _analogue(base)
    xa_future = _analogue(future)

    out = {name: np.full_like(truth_future, np.nan) for name in NULL_IDS}
    out["same_cell_persistence"] = y_hist.copy()
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        out["climatological_mean"][te] = null_mod.training_mean(y_hist[tr], int(te.sum()))
        out["geographic_address"][te] = null_mod.nearest_geographic(
            lon[tr], lat[tr], y_hist[tr], lon[te], lat[te]
        )
        # The analogue is queried with the FUTURE climate against PRESENT climates. That asymmetry
        # is the whole point of a space-for-time null and is why it cannot be reused from the map
        # experiment's derivation.
        out["nearest_analogue"][te] = null_mod.nearest_analogue(
            xa_hist[tr], y_hist[tr], xa_future[te]
        )
        out["shuffled_target"][te] = null_mod.shuffled(truth_future[te], SHUFFLE_SEED + int(f))
    return out


def spread_summary(s1: npt.NDArray[np.float64], s2: npt.NDArray[np.float64]) -> dict[str, float]:
    """Summaries of the raw (unfloored) relative two-seed spread, for the transfer claim."""
    mean = (s1 + s2) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(np.abs(mean) > 0, np.abs(s1 - s2) / np.abs(mean), np.nan)
    ok = rel[np.isfinite(rel)]
    return {
        "median": float(np.median(ok)),
        "mean": float(ok.mean()),
        "p90": float(np.quantile(ok, 0.90)),
        "frac_above_floor": float((ok > FLOOR).mean()),
        "n_finite": int(ok.size),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0")
    ap.add_argument("--test-leg", default="ssp126")
    ap.add_argument("--out", default=None)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    hist = load_leg("historical", args.version)
    fut = load_leg(args.test_leg, args.version)

    # The scored set: tree-bearing in BOTH seeds of BOTH legs. A cell with no forest at one end has
    # no trait median there, so a conjunctive trait test is undefined for it.
    keep = tree_bearing(hist) & tree_bearing(fut)
    sel = pl.Series(keep)
    h1 = matrix(hist.seed1.filter(sel), SCORED_CONJUNCTIVE)
    h2 = matrix(hist.seed2.filter(sel), SCORED_CONJUNCTIVE)
    f1 = matrix(fut.seed1.filter(sel), SCORED_CONJUNCTIVE)
    f2 = matrix(fut.seed2.filter(sel), SCORED_CONJUNCTIVE)

    report: dict[str, object] = {
        "corpus_version": args.version,
        "test_leg": args.test_leg,
        "shuffle_seed": SHUFFLE_SEED,
        "n_cells": int(keep.sum()),
        "n_tree_bearing_historical": int(tree_bearing(hist).sum()),
        "n_tree_bearing_future": int(tree_bearing(fut).sum()),
        "quantities": list(SCORED_CONJUNCTIVE),
        "seed_pairs_are_distinct": {
            "historical": bool(not np.array_equal(h1, h2)),
            args.test_leg: bool(not np.array_equal(f1, f2)),
        },
        "spread": {
            "historical": spread_summary(h1, h2),
            args.test_leg: spread_summary(f1, f2),
        },
    }
    print(f"scored cells, tree-bearing in both seeds of both legs: {report['n_cells']}", flush=True)
    print(f"seed pairs distinct: {report['seed_pairs_are_distinct']}")
    for leg, s in report["spread"].items():  # type: ignore[union-attr]
        print(
            f"  relative two-seed spread, {leg:11s}: median {s['median']:.6f} "
            f"p90 {s['p90']:.6f} frac>floor {s['frac_above_floor']:.4f}"
        )

    truth_future, band_own = acceptance_band_transferred(f1, f2, f1, f2)
    _, band_transferred = acceptance_band_transferred(f1, f2, h1, h2)
    bands = {"own": band_own, "transferred": band_transferred}

    # How much actually changed. If the future state sits inside the band around the present one in
    # nearly every cell, persistence wins for arithmetic reasons and the leg cannot discriminate --
    # that is a property of the DATA and has to be known before the decision rule is written.
    truth_hist = (h1 + h2) / 2.0
    for bname, band in bands.items():
        moved = ~(np.abs(truth_hist - truth_future) <= band)
        report[f"changed_beyond_band_{bname}"] = {
            "frac_cells_any_quantity": float(moved.any(axis=1).mean()),
            "frac_cells_all_quantities": float(moved.all(axis=1).mean()),
            "mean_quantities_moved": float(moved.sum(axis=1).mean()),
        }
        print(
            f"  cells whose forest moved beyond the {bname} band in >=1 of "
            f"{len(SCORED_CONJUNCTIVE)} quantities: "
            f"{report[f'changed_beyond_band_{bname}']['frac_cells_any_quantity']:.4f}"
        )

    results: dict[str, object] = {}
    for degrees in (15.0, 5.0):
        base = assemble(hist, SCORED_CONJUNCTIVE, k=args.k, block_degrees=degrees, mask=keep)
        future = assemble(fut, SCORED_CONJUNCTIVE, k=args.k, block_degrees=degrees, mask=keep)
        preds = oof_nulls(base, future, truth_future)

        block: dict[str, object] = {
            "n_folds": int(np.unique(base.folds).size),
            "n_blocks": int(np.unique(base.folds).size),
        }
        for bname, band in bands.items():
            block[bname] = {
                "nulls": {
                    n: band_frac_conjunctive(p, truth_future, band) for n, p in preds.items()
                },
                # The CEILING, not a null: one realisation of the model scored against the two-seed
                # mean. Under the OWN band it sits at exactly half a band and passes by
                # construction; under the TRANSFERRED band it does not, which is the whole reason
                # the transferred band exists.
                "single_realisation_ceiling": band_frac_conjunctive(f1, truth_future, band),
                "band_median_relative": float(
                    np.nanmedian(np.abs(band) / np.maximum(np.abs(truth_future), 1e-12))
                ),
            }
            print(f"\n{degrees:g} deg blocking, {bname} band -- band_frac_conjunctive:")
            for n, v in sorted(block[bname]["nulls"].items(), key=lambda kv: -kv[1]):  # type: ignore[index]
                print(f"  {n:24s} {v:.6f}")
            print(f"  {'(ceiling: one seed)':24s} {block[bname]['single_realisation_ceiling']:.6f}")  # type: ignore[index]

        # Per-quantity pass rates for the two arms most likely to be the best null, reported beside
        # the conjunctive number and never instead of it.
        block["per_quantity_transferred"] = {
            n: band_frac_per_quantity(preds[n], truth_future, band_transferred, SCORED_CONJUNCTIVE)
            for n in ("same_cell_persistence", "nearest_analogue")
        }
        results[f"block_{degrees:g}deg"] = block

    report["results"] = results
    report["floored_spread_note"] = {
        "floor": FLOOR,
        "median_floored_relative_spread_historical": float(np.median(relative_spread(h1, h2))),
        "median_floored_relative_spread_future": float(np.median(relative_spread(f1, f2))),
    }

    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "derived_nulls_leg.json").write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"\nwrote {dest / 'derived_nulls_leg.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
