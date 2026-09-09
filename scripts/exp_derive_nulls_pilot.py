#!/usr/bin/env python
"""Derive what every null MUST return for the response kill test, on the PILOT corpus.

    scripts/exp_derive_nulls_pilot.py --version pilot-v1 --out <dir>

WHY THIS DERIVATION IS DIFFERENT FROM `exp_derive_nulls.py`. That one derives the nulls of the
warming-response test on the two ground-truth legs, where every cell holds exactly ONE climate, so
climate and geography are collinear and the response is not separately identified -- which is the
diagnosis X1 came back with. The pilot corpus (line D, `docs/decisions/20260909-D-pilot-corpus-v1.md`)
spins the SAME cell up under 30 climates with the same config, the same forcing window and the same
random seed, so the only difference between an arm and its control is the climate. The response is
therefore identified BY CONSTRUCTION here, and the same-cell baseline null is free at every cell.

WHAT IS DERIVED, AND WHY BEFORE ANYTHING IS SEALED. Line X's own gotcha, learned the expensive way
on X4: derive the nulls before designing the statistic. X4's design collapsed on contact with its
own null values -- the statistic had no resolution at the cell count available and the four nulls
were mutually indistinguishable, so sealing it would have pre-registered a guaranteed `invalid`.
Nothing here fits a model and nothing here touches the emulator; what it pins down is the APPARATUS.

THE THREE THINGS THIS HAS TO ANSWER BEFORE A PRE-REGISTRATION CAN BE WRITTEN:

1. Are the nulls far enough apart to be told apart? If `level_mean` and `nearest_analogue` land on
   the same number, the test has no power to say which kind of skill the emulator has.
2. What does a level-averaged score hide? Line D measured a NON-MONOTONE response at the Amazon
   cell -- vegetation carbon -36 % at +2 K, -97 % at +4 K, back to ~35 % of control at +6 K, from
   three forcing files differing only in the temperature increment. A skill score averaged over
   levels hides exactly that, so every statistic here is reported per level as well as pooled.
3. How much of the corpus is treeless, and what does that do to a trait quantile? A trait median is
   undefined with no stems; a stem count of zero is a real and very large response. Those two facts
   pull in opposite directions and the handling rule has to be pre-registered, not improvised.

The response is a WITHIN-CELL PAIRED CONTRAST, which is the only thing the corpus licenses: line D's
record is explicit that the 1000-year spin-up is not converged (57.9 % of vegetated cells still
moving, median +6.8 %/century), so a claim about "the stationary forest a climate supports" is not
available. Both arms of a pair carry the same drift under the same protocol, so their difference is.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import multiprocessing as mp

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.restart import RestartReader
from vegemu.corpus.state import summarise_cell
from vegemu.nulls import nearest_analogue, nearest_geographic
from vegemu.paths import paths
from vegemu.score import (
    RESPONSE_QUANTITIES,
    blocked_spatial_folds,
    matrix,
    skill_vs_no_change,
    spatial_blocks,
)

SHUFFLE_SEED = 20260909
CONTROL_POINT = "control"

# The cells.csv columns that carry each cell's own baseline climate, already standardised by line D's
# design code. These are the analogue null's feature space: they are the five perturbation axes'
# baselines, so "climatically nearest cell" means nearest in the same coordinates the design varies.
ANALOGUE_FEATURES: tuple[str, ...] = (
    "z_tas_ann",
    "z_pr_ann",
    "z_pr_seasonality",
    "z_rsds_ann",
    "z_tas_iav",
)

# The pure-temperature ladder at unperturbed precipitation. Used only by the monotonicity diagnostic
# and the interpolation arm -- both of which are DIAGNOSTICS ON THE DESIGN, not nulls, because they
# read the truth at other levels of the same cell and no emulator is given that.
TEMP_LADDER: tuple[tuple[float, str], ...] = (
    (0.0, CONTROL_POINT),
    (2.0, "core_t+2_p10"),
    (4.0, "core_t+4_p10"),
    (6.0, "core_t+6_p10"),
)


# ------------------------------------------------------------------------------------------------
# Stage 1 -- decode. 6,000 single-cell restart files into one (cell, point) state table.
# ------------------------------------------------------------------------------------------------
def _decode_one(task: tuple[str, int, str]) -> dict[str, object] | None:
    """One single-cell restart file -> one state row, or None if the file is missing.

    A missing file is returned rather than raised: line D reports all 6,000 wrote a restart, and a
    derivation that dies on the first absent path would report nothing at all about the other 5,999.
    The count of missing files is reported, so "all present" is a measurement and not an assumption.

    `summarise_cell` directly rather than `state_table`, because `state_table` builds a polars frame
    and forks its own pool per call -- both wasted on a file that holds exactly one cell, and the
    second one nested inside this pool.
    """
    path, cell, point = task
    if not Path(path).is_file():
        return None
    reader = RestartReader(Path(path))
    if reader.ncell != 1:
        raise ValueError(f"{path}: expected a single-cell restart, got {reader.ncell} cells")
    with reader:
        row: dict[str, object] = dict(summarise_cell(reader.read(0), cell, reader.layout))
    row["point"] = point
    return row


def decode(version: str, nproc: int, limit: int | None) -> pl.DataFrame:
    """Every run's restart, decoded in parallel.

    ⚠ SPAWN, NOT FORK. polars' Rust thread pool is not fork-safe: forking after the parent has
    touched polars (reading runs.csv is enough) leaves every worker blocked on an inherited lock at
    zero CPU, with no error and no progress -- which is exactly how this script first behaved. Spawn
    costs one interpreter start per worker, once, and cannot deadlock this way.
    """
    runs_csv = Path(str(paths()["scratch"]["corpus"])) / version / "runs.csv"
    with runs_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if limit is not None:
        rows = rows[:limit]
    tasks = [
        (str(Path(r["run_dir"]) / "restart" / f"restart_{r['name']}.lpj"), int(r["cell"]), r["point"])
        for r in rows
    ]
    print(f"decoding {len(tasks)} restart files on {nproc} processes", flush=True)

    if nproc <= 1:
        decoded = [_decode_one(t) for t in tasks]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=nproc) as pool:
            decoded = list(pool.imap(_decode_one, tasks, chunksize=8))

    present = [r for r in decoded if r is not None]
    print(f"decoded {len(present)} of {len(tasks)}; {len(tasks) - len(present)} missing", flush=True)
    return pl.DataFrame(present)


# ------------------------------------------------------------------------------------------------
# Stage 2 -- the paired contrast, and every null against it.
# ------------------------------------------------------------------------------------------------
def build_deltas(
    state: pl.DataFrame, cells: pl.DataFrame, quantities: tuple[str, ...]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], list[int], list[str]]:
    """`(dtrue, control, cell_ids, point_names)`, dtrue shaped (n_cells, n_points, n_quantities).

    `control` is the (n_cells, n_quantities) unperturbed level, returned because the proportional
    null needs each cell's own standing state and recomputing it elsewhere would risk a different
    cell order.

    Only cells that decoded successfully under the control AND under every perturbed point are kept,
    so the same cell set backs every level and a per-level comparison is a comparison of the same
    cells rather than of two different subsets.
    """
    points = [p for p in state["point"].unique().sort().to_list() if p != CONTROL_POINT]
    per_cell = state.group_by("cell").len()
    complete = per_cell.filter(pl.col("len") == len(points) + 1)["cell"].to_list()
    cell_ids = sorted(set(complete) & set(cells["cell"].to_list()))
    print(f"{len(cell_ids)} cells complete over {len(points)} perturbed points + control")

    index = {(int(c), str(p)): i for i, (c, p) in enumerate(zip(state["cell"], state["point"]))}
    values = matrix(state, quantities)

    dtrue = np.full((len(cell_ids), len(points), len(quantities)), np.nan)
    control = np.full((len(cell_ids), len(quantities)), np.nan)
    for i, cell in enumerate(cell_ids):
        base = values[index[(cell, CONTROL_POINT)]]
        control[i] = base
        for j, point in enumerate(points):
            dtrue[i, j] = values[index[(cell, point)]] - base
    return dtrue, control, cell_ids, points


def _per_level_and_pooled(
    dpred: npt.NDArray[np.float64],
    dtrue: npt.NDArray[np.float64],
    points: list[str],
    quantities: tuple[str, ...],
) -> dict[str, object]:
    """The statistic pooled over all levels, per level, and per quantity.

    Pooled is reported WITH the per-level table, never instead of it: line D measured a response
    that is not monotone in temperature, and a pooled score is exactly the summary that hides it.
    """
    flat_pred = dpred.reshape(-1, dpred.shape[2])
    flat_true = dtrue.reshape(-1, dtrue.shape[2])
    per_quantity = skill_vs_no_change(flat_pred, flat_true)
    return {
        "pooled": float(np.nanmean(per_quantity)),
        "per_quantity": {q: float(v) for q, v in zip(quantities, per_quantity, strict=True)},
        "per_level": {
            point: float(np.nanmean(skill_vs_no_change(dpred[:, j], dtrue[:, j])))
            for j, point in enumerate(points)
        },
    }


def derive_nulls(
    dtrue: npt.NDArray[np.float64],
    control: npt.NDArray[np.float64],
    cells: pl.DataFrame,
    points: list[str],
    quantities: tuple[str, ...],
    k: int,
    degrees: float,
) -> dict[str, dict[str, object]]:
    """Every null, assembled OUT OF FOLD under whole-tile blocking, then scored once.

    Out of fold by construction: each cell is held out exactly once, so the statistic is computed on
    the assembled prediction rather than averaged over folds. The four borrowing nulls all take
    their donor from the TRAINING folds only -- a null that could copy its own cell would be
    measuring nothing.

    The proportional pair is the ADDITIVE null's obvious partner and was missing from the first
    derivation. The estimand is a difference of levels, and the cells run from Amazon to Sahel, so
    "every cell changes by the same fraction of what it already has" is the competitor a scientist
    would actually propose against "every cell changes by the same amount".

    ⚠ BOTH FORMS ARE REPORTED BECAUSE THE OBVIOUS ONE IS UNUSABLE. Aggregating the donor fractions
    with a MEAN scores -27.4 pooled and -173.8 on above-ground biomass: the fraction has a near-zero
    control in its denominator at the cells that go treeless, so a handful of enormous donor ratios
    are multiplied onto the standing state of large cells. The median is the estimator a heavy-tailed
    ratio requires, and the mean form is kept in the output so that "unusable" stays a measurement
    rather than a remark.
    """
    lon = cells["lon"].to_numpy().astype(np.float64)
    lat = cells["lat"].to_numpy().astype(np.float64)
    features = matrix(cells, ANALOGUE_FEATURES)
    folds = blocked_spatial_folds(lon, lat, k=k, degrees=degrees, seed=42)
    n_tiles = len(np.unique(spatial_blocks(lon, lat, degrees)))
    print(f"{len(np.unique(folds))} folds over {n_tiles} tiles of {degrees:g} deg, {len(lon)} cells")

    level_mean = np.full_like(dtrue, np.nan)
    prop_mean = np.full_like(dtrue, np.nan)
    prop_median = np.full_like(dtrue, np.nan)
    geographic = np.full_like(dtrue, np.nan)
    analogue = np.full_like(dtrue, np.nan)

    # The proportional null's own currency: each cell's response as a FRACTION of its own standing
    # state. A control level of zero (a cell treeless before any perturbation) makes the fraction
    # undefined rather than infinite, and it must stay undefined -- there is no proportional response
    # to a forest that is not there.
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(control[:, None, :] != 0.0, dtrue / control[:, None, :], np.nan)

    # An all-NaN column is legitimate here and must stay NaN: it is a quantity for which every
    # training cell at this level is treeless, so there is no donor value. numpy warns and returns
    # NaN, which is the wanted behaviour -- the warning would just make a real one harder to see.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "Mean of empty slice", RuntimeWarning)
        for fold in np.unique(folds):
            test = folds == fold
            train = ~test
            for j in range(dtrue.shape[1]):
                y_train = dtrue[train, j, :]
                level_mean[test, j, :] = np.nanmean(y_train, axis=0)[None, :]
                prop_mean[test, j, :] = np.nanmean(fraction[train, j, :], axis=0)[None, :] * (
                    control[test, :]
                )
                prop_median[test, j, :] = np.nanmedian(fraction[train, j, :], axis=0)[None, :] * (
                    control[test, :]
                )
                geographic[test, j, :] = nearest_geographic(
                    lon[train], lat[train], y_train, lon[test], lat[test]
                )
                analogue[test, j, :] = nearest_analogue(features[train], y_train, features[test])

    rng = np.random.default_rng(SHUFFLE_SEED)
    shuffled = np.empty_like(dtrue)
    for j in range(dtrue.shape[1]):
        shuffled[:, j, :] = dtrue[rng.permutation(dtrue.shape[0]), j, :]

    return {
        "no_response": _per_level_and_pooled(np.zeros_like(dtrue), dtrue, points, quantities),
        "level_mean_response": _per_level_and_pooled(level_mean, dtrue, points, quantities),
        "proportional_median_response": _per_level_and_pooled(
            prop_median, dtrue, points, quantities
        ),
        "proportional_mean_response": _per_level_and_pooled(prop_mean, dtrue, points, quantities),
        "nearest_cell_response": _per_level_and_pooled(geographic, dtrue, points, quantities),
        "nearest_analogue_response": _per_level_and_pooled(analogue, dtrue, points, quantities),
        "shuffled_cells": _per_level_and_pooled(shuffled, dtrue, points, quantities),
    }


# ------------------------------------------------------------------------------------------------
# Diagnostics on the design. NOT nulls: each reads the truth at other levels of the SAME cell, which
# no emulator is given, so neither is a competitor the emulator has to beat.
# ------------------------------------------------------------------------------------------------
def temperature_diagnostics(
    state: pl.DataFrame, cell_ids: list[int], quantities: tuple[str, ...]
) -> dict[str, object]:
    """Is the response smooth enough in temperature to interpolate between levels?

    Two measurements on the pure-temperature ladder at unperturbed precipitation:

    * the fraction of cells whose vegetation-carbon response is MONOTONE across 0 / +2 / +4 / +6 K;
    * how well the +4 K response is predicted by the mean of the +2 K and +6 K responses AT THE SAME
      CELL -- an arm with far more information than any emulator gets.

    If that arm scores poorly, a fold design that holds out a perturbation level and assumes
    interpolation between the neighbours is unsound, and the pre-registration has to say so.
    """
    index = {(int(c), str(p)): i for i, (c, p) in enumerate(zip(state["cell"], state["point"]))}
    values = matrix(state, quantities)
    agb = quantities.index("agb")

    rows = []
    for cell in cell_ids:
        if any((cell, point) not in index for _, point in TEMP_LADDER):
            continue
        rows.append([values[index[(cell, point)]] for _, point in TEMP_LADDER])
    ladder = np.asarray(rows)  # (cells, 4 levels, quantities)
    if ladder.size == 0:
        return {"n_cells": 0}

    steps = np.diff(ladder[:, :, agb], axis=1)
    monotone = np.all(steps <= 0, axis=1) | np.all(steps >= 0, axis=1)

    base = ladder[:, 0, :]
    d2, d4, d6 = ladder[:, 1, :] - base, ladder[:, 2, :] - base, ladder[:, 3, :] - base
    interpolated = skill_vs_no_change(0.5 * (d2 + d6), d4)

    return {
        "n_cells": int(ladder.shape[0]),
        "ladder": [f"+{k:g} K" for k, _ in TEMP_LADDER],
        "frac_agb_monotone_in_temperature": float(np.mean(monotone)),
        "interpolate_plus4_from_plus2_and_plus6": {
            "pooled": float(np.nanmean(interpolated)),
            "per_quantity": {
                q: float(v) for q, v in zip(quantities, interpolated, strict=True)
            },
        },
    }


def treeless_report(state: pl.DataFrame, quantities: tuple[str, ...]) -> dict[str, object]:
    """How many arms carry no stems, and what that does to each scored quantity.

    A treeless arm is not a failed run: it is the largest response in the corpus, and for a count or
    a stock its value is a legitimate zero. For a trait quantile it is a genuine missing value -- a
    wood density of zero is not "light wood", it is no wood. So the two classes cannot share a
    handling rule, and the per-quantity row counts that survive have to be stated with the score.
    """
    treeless = state.filter(pl.col("stems_total") <= 0)
    finite = {q: int(np.isfinite(matrix(state, (q,))[:, 0]).sum()) for q in quantities}
    return {
        "n_rows": int(state.height),
        "n_treeless_rows": int(treeless.height),
        "frac_treeless": float(treeless.height / state.height) if state.height else 0.0,
        "treeless_cells": int(treeless["cell"].n_unique()),
        "finite_rows_per_quantity": finite,
    }


def separation(nulls: dict[str, dict[str, object]]) -> dict[str, object]:
    """Are the nulls far enough apart to be told apart? The check X4 failed.

    Reported here so the pre-registration cannot be written without it. Two nulls that land on the
    same number cannot both inform a verdict: whichever the emulator beats, the test cannot say
    which kind of skill it demonstrated.
    """
    values = {name: float(entry["pooled"]) for name, entry in nulls.items()}  # type: ignore[arg-type]
    names = sorted(values, key=lambda n: -values[n])
    gaps = {
        f"{a} - {b}": round(values[a] - values[b], 6)
        for a, b in zip(names, names[1:], strict=False)
    }
    return {
        "ranked": {n: round(values[n], 6) for n in names},
        "adjacent_gaps": gaps,
        "best_null": names[0],
        "min_adjacent_gap": min(gaps.values()) if gaps else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nproc", type=int, default=1)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--limit", type=int, default=None, help="decode only the first N runs (smoke)")
    ap.add_argument("--cache", default=None, help="reuse/write a decoded state parquet")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version

    cache = Path(args.cache) if args.cache else out / f"state_{args.version}.parquet"
    if cache.is_file():
        print(f"reusing decoded state: {cache}")
        state = pl.read_parquet(cache)
    else:
        state = decode(args.version, args.nproc, args.limit)
        state.write_parquet(cache)
        print(f"wrote decoded state: {cache}")

    cells = pl.read_csv(corpus / "cells.csv")
    quantities = RESPONSE_QUANTITIES

    dtrue, control, cell_ids, points = build_deltas(state, cells, quantities)
    scored_cells = cells.filter(pl.col("cell").is_in(cell_ids)).sort("cell")

    nulls = derive_nulls(dtrue, control, scored_cells, points, quantities, args.k, args.degrees)
    report = {
        "version": args.version,
        "corpus": str(corpus),
        "quantities": list(quantities),
        "n_cells": len(cell_ids),
        "n_points": len(points),
        "n_pairs": int(dtrue.shape[0] * dtrue.shape[1]),
        "blocking_degrees": args.degrees,
        "k_folds": args.k,
        "nulls": nulls,
        "separation": separation(nulls),
        "treeless": treeless_report(state, quantities),
        "temperature_diagnostics": temperature_diagnostics(state, cell_ids, quantities),
    }
    (out / "nulls_pilot.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=== nulls, pooled over {report['n_pairs']} (cell, climate) pairs ===")
    for name, value in report["separation"]["ranked"].items():  # type: ignore[index]
        print(f"  {name:32s} {value:+.6f}")
    print(f"\nbest null: {report['separation']['best_null']}")  # type: ignore[index]
    print(f"min adjacent gap: {report['separation']['min_adjacent_gap']}")  # type: ignore[index]
    tl = report["treeless"]
    print(f"\ntreeless rows: {tl['n_treeless_rows']} of {tl['n_rows']}")  # type: ignore[index]
    td = report["temperature_diagnostics"]
    print(f"agb monotone in temperature: {td.get('frac_agb_monotone_in_temperature')}")  # type: ignore[union-attr]
    print(f"wrote {out / 'nulls_pilot.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
