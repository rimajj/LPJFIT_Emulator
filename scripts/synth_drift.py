#!/usr/bin/env python
"""t3: does a synthesised restart DRIFT away from the real one over 20 years of the real model?

    scripts/synth_drift.py --emulated <run-dir> --control <run-dir> --control-seed2 <run-dir> \\
        --initial <restart_1999_real.lpj> --ceiling <run-dir> --year 2019 --out <json>

t2 asked whether the model accepts the state at all (it does) and t4 whether the state matches at
year one (carbon does, the conjunctive test does not). This asks the different question that only
becomes meaningful once a state survives its first year: after twenty years, is the emulated arm
still no further from the control than TWO RUNS OF THE CONTROL ARE FROM EACH OTHER?

FOUR ARMS, and only one of them is the emulator: the emulated state, two control seeds that supply
the tolerance, and a third control seed that supplies the ceiling. Plus one null read off a file
that already exists. The three extra arms cost about two minutes of one core each, and without them
the emulated arm's number cannot be read at all.

⚠ WHY TWO CONTROL SEEDS AND NOT ONE. The tolerance is `max(10 %, the model's own two-seed
spread)`, and that spread is a property of THIS block over THESE years. The published figure
(`MEMORY.md:noise-floor-measured`) is an end-of-spin-up, global one and does not transfer to a
20-year transient over 20 temperate cells, so the second control arm is not a luxury: it is
where the tolerance comes from. Both controls start from the SAME restart file and differ only
in the random number stream (`new_seed`/`random_seed`; `newgrid.c:520` seeds each cell from
`random_seed` when `new_seed` is true, and from the restart record's own bytes when it is false).

⚠ AND WHY THE EMULATED ARM IS SEED-PAIRED WITH CONTROL SEED 1. The synthesiser copies the target
cell's own template record and never touches its seed bytes, so the emulated arm and control seed 1
run the same stream. The emulated-minus-control difference therefore contains no seed component,
which is the conservative direction: none of the gap can be excused as noise.

THE NULL, and it is the one that decides whether this test has any power at all: the TRUE 1999
state -- the initial condition itself -- scored against the year-2019 band. That is "predict that
twenty years change nothing". If it passes, the state barely moves in twenty years, and the
emulated arm sitting inside the band says nothing about the emulator (invariant 3: the verdict is
then `invalid`, never `pass`). Reported in the same table as the result, per invariant 1.

THE CEILING is the other half of that: a band leg is inside its own band by construction, so the
100 % those two arms score is arithmetic, not attainment. A THIRD control seed is a run of the real
model that is NOT a band leg, so what it scores is what a perfect emulator would score, and the
emulated arm can only be judged against that. See `--ceiling` in the body for the measured reason.

Every number here rests on a subset re-run compared against a subset re-run over the same block with
the same task count, never against stored global output (`MEMORY.md:subset-diverges`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.restart import RestartReader
from vegemu.corpus.state import state_table
from vegemu.score import (
    FLOOR,
    SCORED_CONJUNCTIVE,
    acceptance_band,
    band_frac_per_quantity,
    band_hits,
    matrix,
)

# Reported beside the 22 but not part of them: vegetation carbon is the headline number every
# earlier rung quoted, and `agb` is the part of it the transplant actually targets.
EXTRA_REPORTED: tuple[str, ...] = ("vegc", "stems_total", "litterc", "crown_cover")


def _one(pattern: str, where: Path) -> Path:
    """Exactly one match, or say which. A glob that silently took the first of two files here would
    mean scoring one arm against a stale restart from a previous run of the same directory."""
    hits = sorted(where.glob(pattern))
    if len(hits) != 1:
        raise FileNotFoundError(f"{where}/{pattern} matched {len(hits)} files: {hits}")
    return hits[0]


def _table(restart: Path, first_cell: int) -> pl.DataFrame:
    """The state table of a subset restart file, labelled with ABSOLUTE cell ids.

    `RestartReader.read` indexes a file 0..ncell-1, so a subset file's rows come back numbered from
    zero. The absolute id is what every other table in this project is keyed on.
    """
    reader = RestartReader(restart)
    if reader.generic.firstcell != first_cell:
        raise ValueError(
            f"{restart} declares firstcell={reader.generic.firstcell}, expected {first_cell}"
        )
    frame = state_table(restart)
    return frame.with_columns((pl.col("cell") + first_cell).cast(pl.Int32))


def _vegc_trajectory(run_dir: Path, tag: str) -> npt.NDArray[np.float64]:
    """(nyear, ncell) vegetation carbon from the arm's annual NetCDF output, in cell order."""
    with netCDF4.Dataset(_one(f"grid__{tag}.nc", run_dir / "output")) as ds:
        cellid = np.asarray(ds.variables["cellid"][:])
    if hasattr(cellid, "filled"):
        cellid = cellid.filled(-1)
    flat = cellid.reshape(-1)
    lat_i, lon_i = np.divmod(np.arange(flat.size), cellid.shape[1])
    valid = flat >= 0
    order = np.argsort(flat[valid])
    lat_i, lon_i = lat_i[valid][order], lon_i[valid][order]

    with netCDF4.Dataset(_one(f"vegc__{tag}.nc", run_dir / "output")) as ds:
        block = np.asarray(ds.variables["VegC"][:])
    if hasattr(block, "filled"):
        block = block.filled(np.nan)
    out: npt.NDArray[np.float64] = block[:, lat_i, lon_i].astype(np.float64)
    return out


def _median_relative(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> list[float]:
    """Per-quantity median over cells of |a-b| / |b| — the statistic t2 and t4 were quoted in."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(np.abs(b) > 0, np.abs(a - b) / np.abs(b), np.nan)
    return [float(v) for v in np.nanmedian(rel, axis=0)]


def main() -> int:  # noqa: PLR0915 -- one linear procedure, reported in one place
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emulated", required=True, help="run dir of the emulated arm")
    ap.add_argument("--control", required=True, help="run dir of control seed 1")
    ap.add_argument("--control-seed2", required=True, help="run dir of control seed 2")
    ap.add_argument(
        "--initial", required=True, help="the TRUE initial restart (the no-change null)"
    )
    ap.add_argument(
        "--ceiling",
        default=None,
        help="run dir of a THIRD control seed: what a perfect emulator would score here",
    )
    ap.add_argument("--first-cell", type=int, default=42480)
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--emulated-tag", default="emul")
    ap.add_argument("--control-tag", default="control")
    ap.add_argument("--control-seed2-tag", default="control_s2")
    ap.add_argument("--ceiling-tag", default="control_s3")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    arms = {
        "emulated": (Path(args.emulated), args.emulated_tag),
        "control": (Path(args.control), args.control_tag),
        "control_seed2": (Path(args.control_seed2), args.control_seed2_tag),
    }
    # THE CEILING, and it is not optional decoration. The band's two legs sit inside their own band
    # by construction (`score.py:acceptance_band_transferred` documents the circularity and measures
    # it: a single realisation scores 1.000 against its own band and 0.538 against a transferred
    # one). So "the emulated arm gets 0 of 20" is uninterpretable until a THIRD run of the real
    # model -- the same physics, a new seed, nothing emulated about it -- is scored the same way.
    # Whatever it scores is the most any emulator could score here.
    if args.ceiling:
        arms["ceiling"] = (Path(args.ceiling), args.ceiling_tag)
    end_state = {
        name: _one(f"restart_{args.year}_*.lpj", d / "restart") for name, (d, _) in arms.items()
    }

    print(f"t3 — {args.year} state, cells {args.first_cell}..{args.first_cell + 19}", flush=True)
    tables = {n: _table(f, args.first_cell) for n, f in end_state.items()}
    tables["initial"] = _table(Path(args.initial), args.first_cell)
    for name, frame in tables.items():
        src = end_state.get(name, Path(args.initial))
        print(f"  {name:14s} {frame.height:3d} cells  {src.name}", flush=True)

    cells = tables["control"]["cell"].to_list()
    for name, frame in tables.items():
        if frame["cell"].to_list() != cells:
            raise ValueError(f"{name} covers different cells than the control arm")

    columns = (*SCORED_CONJUNCTIVE, *EXTRA_REPORTED)
    mats = {n: matrix(f, columns) for n, f in tables.items()}
    n_scored = len(SCORED_CONJUNCTIVE)

    # The band. truth is the two controls' mean; the tolerance is max(10 %, their relative spread).
    truth, band = acceptance_band(mats["control"], mats["control_seed2"])
    rel_band = np.where(np.abs(truth) > 0, band / np.abs(truth), np.nan)

    hits = {n: band_hits(m, truth, band) for n, m in mats.items()}
    per_cell = {n: h[:, :n_scored].sum(axis=1) for n, h in hits.items()}
    conjunctive = {n: float(h[:, :n_scored].all(axis=1).mean()) for n, h in hits.items()}
    per_quantity = {n: band_frac_per_quantity(m, truth, band, columns) for n, m in mats.items()}

    gap_emul = _median_relative(mats["emulated"], mats["control"])
    gap_seed = _median_relative(mats["control_seed2"], mats["control"])
    gap_null = _median_relative(mats["initial"], mats["control"])

    ceil_col = "ceil in" if "ceiling" in mats else "  --   "
    print(
        f"\n{'quantity':16s} {'|em-ct|/ct':>11s} {'|s2-s1|/s1':>11s} {'band':>7s} "
        f"{'em in':>6s} {'null in':>8s} {ceil_col:>8s}"
    )
    print("-" * 73)
    for j, q in enumerate(columns):
        mark = " " if j < n_scored else "*"
        ceiling = f"{per_quantity['ceiling'][q]:8.0%}" if "ceiling" in mats else " " * 8
        print(
            f"{mark}{q:15s} {gap_emul[j]:11.3f} {gap_seed[j]:11.3f} "
            f"{float(np.nanmedian(rel_band[:, j])):7.3f} "
            f"{per_quantity['emulated'][q]:6.0%} {per_quantity['initial'][q]:8.0%} {ceiling}"
        )
    print("-" * 73)
    print("* below the line: reported, NOT part of the 22 the acceptance criterion names.")

    print(f"\nconjunctive over the {n_scored} scored quantities, {len(cells)} cells:")
    notes = {
        "emulated": "the result",
        "ceiling": "THE CEILING — a third run of the REAL model. No emulator can beat this.",
        "initial": "THE NULL — 'twenty years change nothing'. If this passes, no power.",
        "control": "arithmetic self-check: a band leg is inside its own band by construction",
        "control_seed2": "arithmetic self-check, as above",
    }
    for name in ("emulated", "ceiling", "initial", "control", "control_seed2"):
        if name not in per_cell:
            continue
        med = int(np.median(per_cell[name]))
        print(
            f"  {name:14s} {conjunctive[name]:6.1%} of cells on all {n_scored}"
            f"   median {med}/{n_scored}   ({notes[name]})"
        )

    # The drift curve. A gap that is flat over twenty years is a different finding from one that
    # grows, and the end state alone cannot tell them apart.
    traj = {n: _vegc_trajectory(d, t) for n, (d, t) in arms.items()}
    years = list(range(args.year - traj["control"].shape[0] + 1, args.year + 1))
    curve = {
        "years": years,
        "median_gap_emulated": _median_relative_by_year(traj["emulated"], traj["control"]),
        "median_gap_seed": _median_relative_by_year(traj["control_seed2"], traj["control"]),
        "block_total_vegc": {n: [float(v) for v in m.sum(axis=1)] for n, m in traj.items()},
    }
    print(
        "\nvegetation carbon, median relative gap per year (emulated vs control | seed2 vs seed1):"
    )
    for i, y in enumerate(years):
        if y % 5 == 0 or i in (0, len(years) - 1):
            print(
                f"  {y}  {curve['median_gap_emulated'][i]:6.3f}   "
                f"{curve['median_gap_seed'][i]:6.3f}"
            )

    summary: dict[str, Any] = {
        "basis": {
            "cells": cells,
            "ncell": len(cells),
            "of_total_tree_bearing_cells": 54020,
            "region": "temperate Europe, present-day climate, historical leg",
            "state_year": args.year,
            "years_simulated": len(years),
            "tasks_per_arm": 1,
            "npatch": int(tables["control"]["npatch"][0]),
            "restart_files": {n: str(f) for n, f in end_state.items()},
            "initial_restart": str(args.initial),
            "band": f"max({FLOOR:.0%}, |seed1-seed2|/mean), measured on THIS block, THESE years",
            "seed_pairing": (
                "emulated shares control seed 1's stream; seed 2 is new_seed=true, random_seed=2"
            ),
            "not_the_acceptance_test": "20 cells of 54020, one region, one climate, one seed pair",
        },
        "quantities": list(columns),
        "n_scored_conjunctive": n_scored,
        "median_relative_gap": {
            "emulated_vs_control": dict(zip(columns, gap_emul, strict=True)),
            "seed2_vs_seed1": dict(zip(columns, gap_seed, strict=True)),
            "null_initial_vs_control": dict(zip(columns, gap_null, strict=True)),
            **(
                {
                    "ceiling_seed3_vs_control": dict(
                        zip(
                            columns, _median_relative(mats["ceiling"], mats["control"]), strict=True
                        )
                    )
                }
                if "ceiling" in mats
                else {}
            ),
        },
        "median_relative_band": dict(
            zip(columns, [float(v) for v in np.nanmedian(rel_band, axis=0)], strict=True)
        ),
        "band_frac_per_quantity": per_quantity,
        "conjunctive": conjunctive,
        "per_cell_hits": {n: [int(v) for v in h] for n, h in per_cell.items()},
        "vegc_trajectory": curve,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2, sort_keys=True))
        print(f"\nwrote {args.out}")
    return 0


def _median_relative_by_year(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> list[float]:
    """Median over cells of |a-b|/|b|, one value per year."""
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(np.abs(b) > 0, np.abs(a - b) / np.abs(b), np.nan)
    return [float(v) for v in np.nanmedian(rel, axis=1)]


if __name__ == "__main__":
    raise SystemExit(main())
