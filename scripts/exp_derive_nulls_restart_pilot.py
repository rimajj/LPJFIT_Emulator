#!/usr/bin/env python
"""Derive what every null MUST return for the EMITTED-RESTART LEVEL experiment, on the PILOT corpus.

    scripts/exp_derive_nulls_restart_pilot.py --version pilot-v1 --out <dir>

WHY THIS EXISTS AND WHAT IT REPLACES. `exp_derive_nulls_restart.py` derived the same nulls on the
only cells a synthesised restart existed for: 42480-42499, twenty CONTIGUOUS half-degree cells, one
15-degree tile. On that set the four nulls landed within 0.786-0.845 of each other and the
conjunctive statistic was pinned at its 1/20 = 0.05 granularity floor for every arm, so no verdict
could have distinguished anything and X4 was deliberately NOT sealed
(`docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`). That record
named the first of three things X4 needed: a spatially dispersed cell set spanning enough
independent tiles that the nulls separate. The pilot corpus is that set -- 200 cells drawn across
the populated 15-degree tiles, each spun up under 30 climates -- so this re-derivation is the
measurement that decides whether X4 can be sealed at all, and at what bar.

THE ESTIMAND IS A LEVEL, NOT THE 20-YEAR DRIFT. t3-drift stayed a validation-ladder step recorded
in a decision record, which was line T's call and was endorsed. What X4 asks is the question the
restart deliverable actually rests on: **given a climate, is the state in the file the emulator
emits inside the acceptance band, conjunctively, on all 22 scored quantities at once?**

THE SCORED SET IS THE 29 PERTURBED POINTS, AND THE CONTROL POINT IS THE TEMPLATE, NOT A TARGET.
`models/synth.py` is template-conditioned: it is handed a real, valid restart for the same cell
under a nearby climate and edits it. On the pilot that template is the cell's own control spin-up.
Scoring the control point would therefore score the template against itself -- 1.0 by construction
for the decisive null -- so the control is the INPUT here and the 29 perturbed climates are the
targets. That is also the product as `PLAN.md` states it: the equilibrium forest under any climate,
including warmed ones.

THE SIX NULLS, AND WHY EACH IS A COMPETITOR RATHER THAN A STRAW MAN. Every one of them is a real,
valid, loadable restart file you could hand the model instead of the emulator's:

  same_cell_template          the cell's OWN control restart, unedited. THE DECISIVE ONE: it is
                              what the synthesiser starts from, so anything it scores is bought by
                              holding still. A synthesis that does not beat it has done nothing.
  nearest_analogue_any_climate  the nearest training (cell, climate) pair in the pre-registered
                              eight-feature climate space -- searched over the WHOLE perturbed
                              ensemble, not just the same design point. The strongest honest
                              space-for-time competitor the corpus admits, and the one a reviewer
                              would propose: "find the most similar climate anywhere and copy it".
  nearest_analogue_same_point the same search restricted to the same design point. Kept because it
                              is the arm comparable to the 20-cell derivation.
  geographic_address          the geographically nearest TRAINING cell at the same design point.
  climatological_mean         the mean state over the training cells at the same design point.
  shuffled_target             the truth permuted across cells within a point -- the chance rate.

THE BAND IS TRANSFERRED, AND THAT IS A DISCLOSURE, NOT A DETAIL. The pilot carries ONE seed, so it
cannot supply its own two-seed spread; line D owes a second seed for 20 pilot cells and until it
lands no spread measured on a PERTURBED state exists. The relative tolerance is therefore taken
per cell per quantity from the ssp126 leg's two genuine seeds (ssp370's are a bit-identical clone
and are never used for a band) and applied to the perturbed level, using
`acceptance_band_transferred`'s arithmetic. The historical leg's spread is reported beside it, never
instead of it. ⚠ The transfer is measured at each cell's PRESENT-DAY climate; a cell driven
low-density by +6 K has a larger spread there than here, so the transferred band is TOO TIGHT in
exactly the cells where the response is largest. That makes every arm harder, the nulls included,
and it is the reason the ceiling reported here is an estimate rather than a measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu import nulls as null_mod
from vegemu.dataset import load_leg
from vegemu.paths import paths
from vegemu.score import (
    FLOOR,
    SCORED_CONJUNCTIVE,
    band_frac_conjunctive,
    band_frac_per_quantity,
    band_hits,
    blocked_spatial_folds,
    matrix,
    relative_spread,
    spatial_blocks,
)

SHUFFLE_SEED = 20260915
CONTROL_POINT = "control"


# ------------------------------------------------------------------------------------------------
# Stage 1 -- the targets. Every (cell, perturbed point) pair, with its template and its truth.
# ------------------------------------------------------------------------------------------------
def build_targets(
    state: pl.DataFrame, cells: pl.DataFrame, quantities: tuple[str, ...]
) -> dict[str, object]:
    """Truth, template and climate for every (cell, perturbed point) target, on one cell order.

    Only cells complete over the control AND all 29 perturbed points are kept, so every design
    point is backed by the same cells and a per-level comparison compares the same cells rather
    than two different subsets.
    """
    points = [p for p in state["point"].unique().sort().to_list() if p != CONTROL_POINT]
    per_cell = state.group_by("cell").len()
    complete = per_cell.filter(pl.col("len") == len(points) + 1)["cell"].to_list()
    cell_ids = sorted(set(complete) & set(cells["cell"].to_list()))
    print(f"{len(cell_ids)} cells complete over {len(points)} perturbed points + control")

    index = {
        (int(c), str(p)): i
        for i, (c, p) in enumerate(zip(state["cell"], state["point"], strict=True))
    }
    values = matrix(state, quantities)
    climate = matrix(state, null_mod.ANALOGUE_FEATURES)
    stems = state["stems_total"].to_numpy().astype(np.float64)

    n_c, n_p, n_q = len(cell_ids), len(points), len(quantities)
    truth = np.full((n_c, n_p, n_q), np.nan)
    truth_climate = np.full((n_c, n_p, len(null_mod.ANALOGUE_FEATURES)), np.nan)
    truth_stems = np.full((n_c, n_p), np.nan)
    template = np.full((n_c, n_q), np.nan)
    template_climate = np.full((n_c, len(null_mod.ANALOGUE_FEATURES)), np.nan)
    for i, cell in enumerate(cell_ids):
        template[i] = values[index[(cell, CONTROL_POINT)]]
        template_climate[i] = climate[index[(cell, CONTROL_POINT)]]
        for j, point in enumerate(points):
            row = index[(cell, point)]
            truth[i, j] = values[row]
            truth_climate[i, j] = climate[row]
            truth_stems[i, j] = stems[row]
    return {
        "cell_ids": cell_ids,
        "points": points,
        "truth": truth,
        "truth_climate": truth_climate,
        "truth_stems": truth_stems,
        "template": template,
        "template_climate": template_climate,
    }


# ------------------------------------------------------------------------------------------------
# Stage 2 -- the band. Transferred, because the pilot has one seed.
# ------------------------------------------------------------------------------------------------
def transferred_spreads(
    cell_ids: list[int], version: str, quantities: tuple[str, ...], floor: float = FLOOR
) -> dict[str, object]:
    """The per-cell per-quantity RELATIVE two-seed spread of each donor leg, on the pilot's cells.

    Returned as relative spreads rather than as bands: the band is that spread times the level of
    whichever perturbed state is being scored, and the level differs per design point.

    A pilot cell absent from a donor leg, or with no defined spread there, falls back to the
    floor -- which is what `relative_spread` does for a zero mean anyway. The count of cells that
    fall back is reported, so "the transfer covers the cell set" is a measurement.
    """
    wanted = np.asarray(cell_ids, dtype=np.int64)
    out: dict[str, object] = {}
    coverage: dict[str, object] = {}
    for leg_name in ("ssp126", "historical"):
        leg = load_leg(leg_name, version)
        keep = np.isin(leg.cells, wanted)
        sel = pl.Series(keep)
        present = leg.cells[keep]
        s1 = matrix(leg.seed1.filter(sel), quantities)
        s2 = matrix(leg.seed2.filter(sel), quantities)
        spread = relative_spread(s1, s2, floor)

        # Re-index onto the pilot's own cell order; a missing cell gets the bare floor.
        full = np.full((len(cell_ids), len(quantities)), floor)
        pos = {int(c): i for i, c in enumerate(present)}
        found = 0
        for i, cell in enumerate(cell_ids):
            if cell in pos:
                full[i] = spread[pos[cell]]
                found += 1
        out[leg_name] = full
        coverage[leg_name] = {
            "cells_found_in_leg": found,
            "cells_missing_floored": len(cell_ids) - found,
            "median_relative_spread": float(np.nanmedian(full)),
            "frac_above_floor": float(np.mean(full > floor)),
        }
    out["coverage"] = coverage
    return out


def ceiling_estimate(
    cell_ids: list[int], version: str, quantities: tuple[str, ...], spread: npt.NDArray[np.float64]
) -> dict[str, object]:
    """What ONE real realisation scores against the two-seed mean, on these cells, this band.

    ⚠ AN ESTIMATE, AND IT IS TRANSFERRED TWICE OVER. It is measured on the historical leg at each
    cell's PRESENT-DAY climate, because that is the only place on this cell set where two genuine
    realisations exist; the perturbed states carry one seed each. It is reported because a
    conjunctive pass rate quoted without a ceiling arm overstates the shortfall -- line T measured
    exactly that on the 20-cell block, where a third control seed reached 25 % and not 100 %
    (`docs/decisions/20260909-T-t3-drift-fails-below-the-null.md`). It is NOT a bar and nothing
    here is scored against it. Line D's second pilot seed is what would turn it into a measurement.
    """
    leg = load_leg("historical", version)
    keep = np.isin(leg.cells, np.asarray(cell_ids, dtype=np.int64))
    sel = pl.Series(keep)
    present = [int(c) for c in leg.cells[keep]]
    h1 = matrix(leg.seed1.filter(sel), quantities)
    h2 = matrix(leg.seed2.filter(sel), quantities)
    mean = (h1 + h2) / 2.0
    rows = np.asarray([i for i, c in enumerate(cell_ids) if c in set(present)], dtype=np.int64)
    band = spread[rows] * np.abs(mean)
    hits = band_hits(h1, mean, band)
    return {
        "n_cells": len(present),
        "basis": "historical leg, present-day climate, seed 1 vs the two-seed mean, ssp126 band",
        "conjunctive": band_frac_conjunctive(h1, mean, band),
        "mean_per_quantity": float(hits.mean()) if hits.size else float("nan"),
        "is_a_measurement_on_the_perturbed_states": False,
    }


# ------------------------------------------------------------------------------------------------
# Stage 3 -- the nulls, out of fold under whole-tile blocking.
# ------------------------------------------------------------------------------------------------
def build_null_predictions(
    targets: dict[str, object], cells: pl.DataFrame, *, k: int, degrees: float
) -> tuple[dict[str, npt.NDArray[np.float64]], dict[str, object]]:
    """Every null's out-of-fold prediction, shaped like the truth.

    Blocked by whole 15-degree tile and by CELL, not by target: holding out a (cell, climate) pair
    while training on the same cell's other 28 climates would let every borrowing null copy the
    answer off the same forest under a slightly different climate, which is not a competitor, it is
    a leak. A held-out cell is held out at all 30 of its points.
    """
    truth: npt.NDArray[np.float64] = targets["truth"]  # type: ignore[assignment]
    truth_climate: npt.NDArray[np.float64] = targets["truth_climate"]  # type: ignore[assignment]
    template: npt.NDArray[np.float64] = targets["template"]  # type: ignore[assignment]
    template_climate: npt.NDArray[np.float64] = targets["template_climate"]  # type: ignore[assignment]

    lon = cells["lon"].to_numpy().astype(np.float64)
    lat = cells["lat"].to_numpy().astype(np.float64)
    folds = blocked_spatial_folds(lon, lat, k=k, degrees=degrees, seed=42)
    n_tiles = len(np.unique(spatial_blocks(lon, lat, degrees)))
    print(f"{len(np.unique(folds))} folds, {n_tiles} tiles of {degrees:g} deg, {len(lon)} cells")

    n_c, n_p, _ = truth.shape
    clim_mean = np.full_like(truth, np.nan)
    geographic = np.full_like(truth, np.nan)
    analogue_point = np.full_like(truth, np.nan)
    analogue_any = np.full_like(truth, np.nan)

    for fold in np.unique(folds):
        test = folds == fold
        train = ~test

        # The any-climate analogue searches over EVERY training (cell, point) pair, the training
        # cells' own control points included: the emulator is given those templates too, so a null
        # that may not use them would be weaker than the information actually on the table.
        pool_y = np.concatenate([truth[train].reshape(-1, truth.shape[2]), template[train]], axis=0)
        pool_x = np.concatenate(
            [truth_climate[train].reshape(-1, truth_climate.shape[2]), template_climate[train]],
            axis=0,
        )
        test_x = truth_climate[test].reshape(-1, truth_climate.shape[2])
        analogue_any[test] = null_mod.nearest_analogue(pool_x, pool_y, test_x).reshape(
            int(test.sum()), n_p, truth.shape[2]
        )

        for j in range(n_p):
            y_train = truth[train, j, :]
            clim_mean[test, j, :] = np.nanmean(y_train, axis=0)[None, :]
            geographic[test, j, :] = null_mod.nearest_geographic(
                lon[train], lat[train], y_train, lon[test], lat[test]
            )
            analogue_point[test, j, :] = null_mod.nearest_analogue(
                truth_climate[train, j, :], y_train, truth_climate[test, j, :]
            )

    rng = np.random.default_rng(SHUFFLE_SEED)
    shuffled = np.empty_like(truth)
    for j in range(n_p):
        shuffled[:, j, :] = truth[rng.permutation(n_c), j, :]

    predictions = {
        "same_cell_template": np.repeat(template[:, None, :], n_p, axis=1),
        "nearest_analogue_any_climate": analogue_any,
        "nearest_analogue_same_point": analogue_point,
        "geographic_address": geographic,
        "climatological_mean": clim_mean,
        "shuffled_target": shuffled,
    }
    basis = {
        "n_folds": len(np.unique(folds)),
        "n_tiles": int(n_tiles),
        "blocking_degrees": degrees,
        "cells_per_fold": [int((folds == f).sum()) for f in np.unique(folds)],
    }
    return predictions, basis


# ------------------------------------------------------------------------------------------------
# Stage 4 -- score, and ask whether the result could have separated anything.
# ------------------------------------------------------------------------------------------------
def score_arm(
    pred: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    band: npt.NDArray[np.float64],
    *,
    treed: npt.NDArray[np.bool_],
    points: list[str],
    quantities: tuple[str, ...],
) -> dict[str, object]:
    """One arm under one band: the conjunctive statistic pooled, per level, and per quantity.

    `conjunctive_treed` restricts to targets whose TRUTH still carries stems. A treeless truth has
    no trait median, `band_hits` counts a NaN as a miss, and so no arm can ever pass such a target
    -- including the ceiling. Both numbers are reported because the pooled one is the acceptance
    statistic and the treed one is the only one a trait claim can be read from.
    """
    flat_pred = pred.reshape(-1, pred.shape[2])
    flat_truth = truth.reshape(-1, truth.shape[2])
    flat_band = band.reshape(-1, band.shape[2])
    flat_treed = treed.reshape(-1)
    hits = band_hits(flat_pred, flat_truth, flat_band)
    return {
        "conjunctive": band_frac_conjunctive(flat_pred, flat_truth, flat_band),
        "conjunctive_treed": band_frac_conjunctive(
            flat_pred[flat_treed], flat_truth[flat_treed], flat_band[flat_treed]
        ),
        "mean_per_quantity": float(hits.mean()) if hits.size else float("nan"),
        "per_quantity": band_frac_per_quantity(flat_pred, flat_truth, flat_band, quantities),
        "per_level": {
            point: band_frac_conjunctive(pred[:, j], truth[:, j], band[:, j])
            for j, point in enumerate(points)
        },
    }


def separation(scores: dict[str, dict[str, object]], key: str) -> dict[str, object]:
    """Are the nulls far enough apart to be told apart? The check the 20-cell cell set failed.

    Two nulls on the same number cannot both inform a verdict: whichever the emulator beats, the
    test cannot say which kind of skill it demonstrated.
    """
    values = {name: float(entry[key]) for name, entry in scores.items()}  # type: ignore[arg-type]
    names = sorted(values, key=lambda n: -values[n])
    gaps = {f"{a} - {b}": round(values[a] - values[b], 6) for a, b in pairwise(names)}
    return {
        "ranked": {n: round(values[n], 6) for n in names},
        "adjacent_gaps": gaps,
        "best_null": names[0],
        "best_null_value": round(values[names[0]], 6),
        "min_adjacent_gap": min(gaps.values()) if gaps else None,
        "spread_best_to_worst": round(values[names[0]] - values[names[-1]], 6),
    }


def no_power_threshold(scores: dict[str, dict[str, object]], key: str) -> dict[str, object]:
    """The smallest margin at which NO null passes its own test. The X6 lesson, applied before seal.

    Under comparator `model_minus_best_null` the no-power rule scores each null on the model's own
    comparator, so a null's margin is its value minus the best of the REMAINING nulls. If the
    chosen threshold is below the largest of those, the best null clears the bar it sets and the
    experiment is `invalid` by construction on the day it is sealed -- which is exactly what a
    +0.080 margin would have done to X6.
    """
    values = {name: float(entry[key]) for name, entry in scores.items()}  # type: ignore[arg-type]
    margins = {}
    for name, value in values.items():
        rest = [v for n, v in values.items() if n != name]
        margins[name] = round(value - max(rest), 6)
    worst = max(margins.values())
    return {
        "margin_of_each_null_against_the_best_of_the_rest": margins,
        "largest_null_self_margin": round(worst, 6),
        "threshold_must_exceed": round(worst, 6),
        "a_0080_threshold_would_be_invalid": bool(worst >= 0.080),
        "a_0160_threshold_would_be_invalid": bool(worst >= 0.160),
    }


def floor_sweep(
    predictions: dict[str, npt.NDArray[np.float64]],
    targets: dict[str, object],
    *,
    cell_ids: list[int],
    points: list[str],
    treed: npt.NDArray[np.bool_],
    quantities: tuple[str, ...],
    floors: list[float],
    gt_version: str,
) -> dict[str, object]:
    """Every arm's conjunctive score at each candidate band floor.

    ⚠ DIAGNOSTIC ONLY, AND IT MUST NEVER BE READ AS A RESULT -- which is why the key it lands under
    in the output says so. The acceptance floor is 10 % and this does not move it. What it asks is
    the question the 10 % column cannot answer on its own: is the conjunctive statistic pinned
    because the emitted state is wrong, or because a tolerance measured at each cell's PRESENT-DAY
    climate is too tight for a state driven far outside it? If the arms separate as the floor
    widens, the blocker is a missing measurement -- the model's own two-seed spread on a PERTURBED
    state, which line D owes -- and X4 becomes sealable when that lands. If they stay pinned at
    every floor, no band rescues a 22-way conjunction on a level and the statistic is the wrong
    instrument.
    """
    truth: npt.NDArray[np.float64] = targets["truth"]  # type: ignore[assignment]
    sweep: dict[str, object] = {}
    for floor in floors:
        sp = transferred_spreads(cell_ids, gt_version, quantities, floor)
        spread: npt.NDArray[np.float64] = sp["ssp126"]  # type: ignore[assignment]
        band = spread[:, None, :] * np.abs(truth)
        scores = {
            name: score_arm(pred, truth, band, treed=treed, points=points, quantities=quantities)
            for name, pred in predictions.items()
        }
        entry = {
            "separation_conjunctive": separation(scores, "conjunctive"),
            "no_power_conjunctive": no_power_threshold(scores, "conjunctive"),
            "conjunctive": {n: s["conjunctive"] for n, s in scores.items()},
            "mean_per_quantity": {n: s["mean_per_quantity"] for n, s in scores.items()},
            "ceiling_estimate": ceiling_estimate(cell_ids, gt_version, quantities, spread),
        }
        sweep[f"{floor:g}"] = entry

        sep: dict[str, object] = entry["separation_conjunctive"]  # type: ignore[assignment]
        ceil: dict[str, object] = entry["ceiling_estimate"]  # type: ignore[assignment]
        print(
            f"\nfloor {floor:4.2f}: best null {sep['best_null']} = "
            f"{sep['best_null_value']:.6f}, min gap {sep['min_adjacent_gap']}, "  # type: ignore[str-format]
            f"ceiling est {ceil['conjunctive']:.4f}"  # type: ignore[str-format]
        )
        for name, value in sep["ranked"].items():  # type: ignore[union-attr]
            print(f"    {name:30s} {value:8.6f}")
    return sweep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--gt-version", default="v0", help="corpus version holding the donor legs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument(
        "--floors",
        default="0.10",
        help=(
            "comma-separated band floors to score under. 0.10 is the acceptance floor; anything "
            "above it is a DIAGNOSTIC that asks whether a too-tight band is what pins the "
            "conjunctive statistic, and is never an acceptance number."
        ),
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version
    quantities = SCORED_CONJUNCTIVE

    state = pl.read_parquet(corpus / "corpus.parquet")
    cells_all = pl.read_csv(corpus / "cells.csv")
    targets = build_targets(state, cells_all, quantities)
    cell_ids: list[int] = targets["cell_ids"]  # type: ignore[assignment]
    points: list[str] = targets["points"]  # type: ignore[assignment]
    truth: npt.NDArray[np.float64] = targets["truth"]  # type: ignore[assignment]
    treed = np.asarray(targets["truth_stems"]) > 0  # type: ignore[arg-type]
    cells = cells_all.filter(pl.col("cell").is_in(cell_ids)).sort("cell")

    floors = [float(f) for f in str(args.floors).split(",")]
    spreads = transferred_spreads(cell_ids, args.gt_version, quantities, floors[0])
    predictions, fold_basis = build_null_predictions(
        targets, cells, k=args.k, degrees=args.degrees
    )

    report: dict[str, object] = {
        "version": args.version,
        "ground_truth_version": args.gt_version,
        "corpus": str(corpus),
        "estimand": "band_frac_conjunctive of the state decoded from the emitted restart file",
        "quantities": list(quantities),
        "n_cells": len(cell_ids),
        "n_points": len(points),
        "n_targets": int(truth.shape[0] * truth.shape[1]),
        "n_targets_treed": int(treed.sum()),
        "frac_targets_treeless": float(1.0 - treed.mean()),
        "shuffle_seed": SHUFFLE_SEED,
        "folds": fold_basis,
        "band_transfer_coverage": spreads["coverage"],
        "shape_note": "control point is the TEMPLATE and is excluded from the scored targets",
    }

    results: dict[str, object] = {}
    for band_name in ("ssp126", "historical"):
        spread: npt.NDArray[np.float64] = spreads[band_name]  # type: ignore[assignment]
        band = spread[:, None, :] * np.abs(truth)
        scores = {
            name: score_arm(pred, truth, band, treed=treed, points=points, quantities=quantities)
            for name, pred in predictions.items()
        }
        results[band_name] = {
            "nulls": scores,
            "separation_conjunctive": separation(scores, "conjunctive"),
            "separation_mean_per_quantity": separation(scores, "mean_per_quantity"),
            "no_power_conjunctive": no_power_threshold(scores, "conjunctive"),
            "ceiling_estimate": ceiling_estimate(cell_ids, args.gt_version, quantities, spread),
        }

        sep = results[band_name]["separation_conjunctive"]  # type: ignore[index]
        npw = results[band_name]["no_power_conjunctive"]  # type: ignore[index]
        print(f"\n=== {band_name} band, {report['n_targets']} targets, conjunctive ===")
        for name, value in sep["ranked"].items():  # type: ignore[index]
            mpq = scores[name]["mean_per_quantity"]
            treed_v = scores[name]["conjunctive_treed"]
            print(f"  {name:30s} {value:8.6f}   treed {treed_v:8.6f}   per-quantity {mpq:8.6f}")
        print(f"  best null: {sep['best_null']} at {sep['best_null_value']}")  # type: ignore[index]
        print(f"  min adjacent gap: {sep['min_adjacent_gap']}")  # type: ignore[index]
        print(f"  threshold must exceed: {npw['threshold_must_exceed']}")  # type: ignore[index]
        ceil = results[band_name]["ceiling_estimate"]  # type: ignore[index]
        print(f"  ceiling ESTIMATE (present-day, transferred): {ceil['conjunctive']}")  # type: ignore[index]

    report["floor_sweep_DIAGNOSTIC_NOT_AN_ACCEPTANCE_NUMBER"] = floor_sweep(
        predictions,
        targets,
        cell_ids=cell_ids,
        points=points,
        treed=treed,
        quantities=quantities,
        floors=floors,
        gt_version=args.gt_version,
    )
    report["results"] = results
    dest = out / "nulls_restart_pilot.json"
    dest.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
