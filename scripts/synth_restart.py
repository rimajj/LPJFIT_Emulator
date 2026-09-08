#!/usr/bin/env python
"""Emit a restart file from the emulator's prediction, for a contiguous block of cells.

    scripts/synth_restart.py --first-cell 42480 --ncell 20 --out-dir <dir>

THE DELIVERABLE. Everything upstream of this produces numbers; this produces the artifact the
project exists for -- a state file the real model will load, so its 1000-year spin-up can be
skipped. The validation ladder for it is cheapest-first:

    t0  the format round-trips byte-identically            -- passed (see the test suite)
    t1  the model's own config pre-flight accepts the file -- `lpjcheck`
    t2  the C loads it and runs a year without aborting    -- one task, one year
    t3  20 years with no drift beyond the two-seed spread
    t4  the state distribution matches
    t5  end to end: emulated restart -> transient vs real restart -> transient

WHY A CONTIGUOUS BLOCK. `openrestart.c` requires `config->startgrid >= header.firstcell` and
`config->nall <= header.ncell`, and the forcing files are read at an offset derived from
`startgrid`. So a restart file written with `firstcell = F, ncell = N` is loadable by a run with
`startgrid = F, endgrid = F+N-1`, and the global inputs line up without modification. A scattered
cell set would not.

⚠ A SUBSET RE-RUN IS NOT A PER-CELL REPLICA OF THE GLOBAL RUN. Same binary, same restart, same
forcing: one cell alone diverges at the FIRST step, a 21-cell block stays bit-identical for 15
years and then diverges. So t3 and t4 must compare a subset run against a SUBSET run -- our
synthesised restart against the real restart, both over the same block with the same task
decomposition -- never against the stored global output.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import polars as pl

from vegemu.binfmt.restart import RestartReader, RestartWriter, read_cell, write_cell
from vegemu.models.synth import MATCH_TRAITS, build_donor_pool, synthesise_cell
from vegemu.paths import path, paths
from vegemu.score import SCORED_CONJUNCTIVE

# Cells the donor stems come from, in two parts, and the split is the point.
#
# BIOME SPANNERS. The five biome reference cells plus the extremes of the record-size distribution.
# These keep the pool usable ANYWHERE: a boreal target cell needs boreal donors, and since the
# transplant is now restricted to the target cell's own admissible types, a temperate cell simply
# never selects one of these, so carrying them costs a temperate run nothing.
# ⚠ 42490 (Hainich) was in this list and has been REMOVED: it sits inside the default target block,
# so it made that block's synthesis partly a copy of itself. `_donor_cells` refuses any donor
# inside the block being written, which is what stops that reappearing.
BIOME_DONORS: tuple[int, ...] = (12045, 18371, 33335, 52059, 35599, 16447, 25000, 47721, 7216)

# PROXIMITY BAND. The measured reason this exists: with types constrained, the pool became the
# binding constraint. The twenty target cells need 983 temperate broadleaved summergreen stems
# above 12 m -- which is where the above-ground mass is -- and the nine biome cells supply 50, so
# every tall one was reused about twenty times and the upper tail of the mass distribution could
# not be reached. The file came out at 71 % of the true above-ground biomass for that reason alone.
#
# The band is chosen by PROXIMITY, not by score. Picking the cells that happen to be richest in
# what this particular block is short of would be selecting the donor set against the answer, and
# the resulting number would be a selected maximum. Proximity also generalises: it is what a
# production run would do, since a cell's neighbours are its closest climatic analogues on a 0.5
# grid, and it needs no knowledge of the target's state.
DONOR_BAND: int = 20


def _donor_cells(first_cell: int, ncell: int, band: int) -> list[int]:
    """Biome spanners plus a band either side of the block, excluding the block itself."""
    block = range(first_cell, first_cell + ncell)
    near = [c for c in range(first_cell - band, first_cell + ncell + band) if c not in block]
    cells = [c for c in (*BIOME_DONORS, *near) if c >= 0 and c not in block]
    inside = [c for c in cells if c in block]
    if inside:  # belt and braces: a donor from the block would score the synthesis against itself
        raise AssertionError(f"donor cells inside the synthesised block: {inside}")
    return sorted(set(cells))


# `par/pft_lpjmlfit.js` order. Named here only so the report reads as botany rather than as indices.
PFT_NAMES: dict[int, str] = {
    0: "tropical broadleaved evergreen",
    1: "temperate needleleaved evergreen",
    2: "temperate broadleaved evergreen",
    3: "temperate broadleaved summergreen",
    4: "boreal needleleaved evergreen",
    5: "boreal broadleaved summergreen",
    6: "boreal needleleaved summergreen",
}


def _pool_types(per_cell: list[dict[Any, int]]) -> dict[str, int]:
    """Sum per-cell type histograms into one. JSON keys are strings, so normalise them here."""
    out: dict[str, int] = {}
    for hist in per_cell:
        for pft_id, count in hist.items():
            out[str(pft_id)] = out.get(str(pft_id), 0) + int(count)
    return out


def main() -> int:  # noqa: PLR0915 -- one linear procedure, reported in one place
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--first-cell", type=int, default=42480)
    ap.add_argument("--ncell", type=int, default=20)
    ap.add_argument("--oof", default=None, help="oof_map.parquet with the per-cell prediction")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument(
        "--match-traits",
        default=",".join(MATCH_TRAITS),
        help="comma-separated traits the donor match targets (default: %(default)s)",
    )
    ap.add_argument(
        "--donor-band",
        type=int,
        default=DONOR_BAND,
        help="cells either side of the block to draw donors from (0 = biome spanners only)",
    )
    args = ap.parse_args()
    match_traits = tuple(t for t in args.match_traits.split(",") if t)

    exp = Path(str(paths()["scratch"]["exp"])) / "map-response-v0"
    oof = pl.read_parquet(Path(args.oof) if args.oof else exp / "oof_map.parquet")
    out_dir = (
        Path(args.out_dir) if args.out_dir else Path(str(paths()["scratch"]["runs"])) / "synth-v0"
    )
    (out_dir / "restart").mkdir(parents=True, exist_ok=True)

    cells = list(range(args.first_cell, args.first_cell + args.ncell))
    template_file = path("ground_truth.historical_seed1") / "restart/restart_1999.lpj"
    reader = RestartReader(template_file)
    print(f"template: {template_file.name}  ncell={reader.ncell}", flush=True)

    donor_cells = _donor_cells(args.first_cell, args.ncell, args.donor_band)
    print(
        f"donor pool from {len(donor_cells)} cells "
        f"({len(BIOME_DONORS)} biome + a band of {args.donor_band} either side, "
        f"the block itself excluded)...",
        flush=True,
    )
    pool = build_donor_pool(RestartReader(template_file), donor_cells)
    print(
        f"  {pool.n} donor stems, height {pool.trait('height').min():.2f}-"
        f"{pool.trait('height').max():.2f} m, wood density "
        f"{pool.trait('wooddens').min():.3g}-{pool.trait('wooddens').max():.3g} gC/m3",
        flush=True,
    )

    pred_lookup = {int(c): i for i, c in enumerate(oof["cell"].to_numpy())}
    needed = [f"pred_{q}" for q in SCORED_CONJUNCTIVE]
    pred_matrix = oof.select(needed).to_numpy()

    reports = []
    records: list[bytes] = []
    with reader:
        for cell in cells:
            template = reader.read(cell)
            if cell not in pred_lookup or template["skip"]:
                # A cell the emulator was not scored on (no forest in one of the seeds) keeps its
                # real record. Substituting a guess there would put a fabricated forest into the
                # deliverable, which is worse than passing the template through unchanged.
                records.append(reader.cell_bytes(cell))
                reports.append({"cell": cell, "status": "template passed through unchanged"})
                continue
            row = pred_matrix[pred_lookup[cell]]
            prediction = dict(zip(SCORED_CONJUNCTIVE, [float(v) for v in row], strict=True))
            rec, report = synthesise_cell(
                template,
                prediction,
                pool,
                reader.layout,
                cell=cell,
                template_cell=cell,
                seed=args.seed + cell,
                match_traits=match_traits,
            )
            records.append(write_cell(rec, reader.layout))
            reports.append({"cell": cell, "status": "synthesised", **asdict(report)})

    dest = out_dir / "restart" / "restart_1999_emulated.lpj"
    with RestartWriter(
        dest, reader.generic, reader.restart, ncell=len(cells), firstcell=args.first_cell
    ) as writer:
        for blob in records:
            writer.append(blob)

    # Read it straight back with our own reader: the framing must survive, and every record must
    # still decode. This is t0 applied to the SYNTHESISED file, not just to a copied one.
    back = RestartReader(dest)
    if back.ncell != len(cells) or back.generic.firstcell != args.first_cell:
        raise AssertionError("the emitted restart file does not describe the block it was given")
    with back:
        for i in range(back.ncell):
            blob = back.cell_bytes(i)
            if write_cell(read_cell(blob, back.layout), back.layout) != blob:
                raise AssertionError(f"emitted record {i} does not round-trip")

    synth = [r for r in reports if r["status"] == "synthesised"]
    summary = {
        "restart_file": str(dest),
        "bytes": dest.stat().st_size,
        "first_cell": args.first_cell,
        "ncell": len(cells),
        "synthesised_cells": len(synth),
        "passed_through": len(reports) - len(synth),
        "donor_cells": donor_cells,
        "donor_band": args.donor_band,
        "match_traits": list(match_traits),
        "donor_stems": pool.n,
        "template": str(template_file),
        "stems_requested_total": int(sum(r["stems_requested"] for r in synth)),
        "stems_placed_total": int(sum(r["stems_placed"] for r in synth)),
        "median_pool_shortfall": {
            trait: float(np.median([r["pool_shortfall"].get(trait, np.nan) for r in synth]))
            for trait in match_traits
        },
        # Must be zero. A stem of a type the target cell's own real state never contains is a stem
        # the model kills inside a year, however byte-consistent it is -- that is what halved the
        # first synthesised roster's carbon. Reported here so it cannot be discovered by a run.
        "inadmissible_stems_total": int(sum(r["inadmissible_placed"] for r in synth)),
        "type_fallbacks_total": int(sum(r["type_fallbacks"] for r in synth)),
        "type_composition": {
            "requested": _pool_types([r["type_requested"] for r in synth]),
            "placed": _pool_types([r["type_achieved"] for r in synth]),
        },
        "roundtrip_of_emitted_file": "BYTE-IDENTICAL on every record",
        "validation_ladder": {
            "t0_format_roundtrip": "passed",
            "t1_config_preflight": "run scripts/sbatch_cmodel.sh --check",
            "t2_one_year": "run scripts/sbatch_cmodel.sh",
        },
        "per_cell": reports,
    }
    (out_dir / "synth_report.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\nwrote {dest}  ({dest.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(synth)} cells synthesised, {len(reports) - len(synth)} passed through")
    print(
        f"  {summary['stems_placed_total']} stems placed of "
        f"{summary['stems_requested_total']} requested"
    )
    for trait, value in summary["median_pool_shortfall"].items():
        print(f"  median {trait} shortfall vs the prediction: {value:+.2%}")
    print("  every emitted record round-trips byte-identically")

    placed = summary["type_composition"]["placed"]
    wanted = summary["type_composition"]["requested"]
    total = max(sum(placed.values()), 1)
    print("\n  tree types, share of the roster (asked for -> placed):")
    for t in sorted(set(placed) | set(wanted)):
        print(
            f"    type {t}: {wanted.get(t, 0) / total:6.1%} -> {placed.get(t, 0) / total:6.1%}"
            f"   ({PFT_NAMES.get(int(t), '?')})"
        )
    print(
        f"  donor-type fallbacks (wanted type absent from the pool): "
        f"{summary['type_fallbacks_total']} of {summary['stems_placed_total']}"
    )
    bad = summary["inadmissible_stems_total"]
    verdict = "OK" if bad == 0 else "*** FAULT ***"
    print(f"  stems of a type this cell's own real state never holds: {bad}   {verdict}")
    if bad:
        print("    Those stems will be dead within a simulated year. Do not run this file; widen")
        print("    the donor pool so every admissible type is represented, and re-synthesise.")
    print(f"  report: {out_dir / 'synth_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
