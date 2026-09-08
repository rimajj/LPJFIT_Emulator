#!/usr/bin/env python
"""Write a PERTURBED 30-year `.clm` forcing set for one cell (or one contiguous block of cells).

    scripts/corpus_perturb_clm.py --cell 42490 --point control  --out-dir <dir>
    scripts/corpus_perturb_clm.py --cell 42490 --point core_t+4_p10 --out-dir <dir>
    scripts/corpus_perturb_clm.py --cell 42490 --dtemp 4 --fprec 1.0 --name warm4 --out-dir <dir>
    scripts/corpus_perturb_clm.py --self-test --cell 42490          # neutral -> byte identity

WHAT MAKES A SUBSET FILE LEGAL, and it is not obvious from the format alone. The model reads a
climate year at `(startgrid - header.firstcell) * nbands * itemsize + headersize` and strides by
`header.ncell * nbands * itemsize` (openclimate.c:207-219). The only gate on the cell range is
`firstgrid >= header.firstcell && nall + firstgrid <= header.ncell + header.firstcell`
(openinputfile.c:145). So a file whose header declares `firstcell = <our cell>, ncell = <our block>`
is read correctly and validated correctly, while the grid and soil inputs stay global. That is why
a whole perturbed forcing set for one cell is 44 KB per variable instead of 11.7 GB, and why the
pilot corpus fits in about 1.3 GB rather than 450 GB.

⚠ THE SOURCE MUST BE FLOAT AND UNSCALED, AND THAT IS CHECKED. The historical leg is v3 float32 with
scalar 1.0. A v2 int16 leg with scalar 0.1 would quantise every perturbation to a tenth of a degree
-- a +0.05 K perturbation would round to zero and the run would look like an unexplained null. So
the writer refuses anything but an unscaled float source rather than quietly rounding.

⚠ EVERY WRITE IS VERIFIED BEFORE IT IS USED. The file is read back and compared against the
in-memory block; and when the perturbation is neutral, the file's data bytes are compared against
the very bytes of the source file's slice. That second check is the round-trip proof (invariant 7)
for the PERTURBED writer, not just for the reader.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.binfmt.clm import LPJ_FLOAT, ClmHeader, ClmReader, write_clm
from vegemu.corpus.perturb import (
    MONTH_LEN,
    MONTH_START,
    NDAYYEAR,
    VARS,
    CellPattern,
    Perturbation,
    apply_perturbation,
    calibrate_cell,
    design_by_name,
    model_relative_humidity,
)
from vegemu.paths import paths, scratch

# The base climate window. It is the same 30 years the emulator's climate summary is built from
# (`vegemu.corpus.climate.WINDOWS["historical"]`), which is what makes the corpus self-consistent:
# the state a run produces is in equilibrium with exactly the climate the features describe.
BASE_WINDOW = (1970, 1999)
# The calibration contrast, both terms from the same scenario leg and the same climate model.
CALIB_LEG = "ssp370"
CALIB_EARLY = (2015, 2044)
CALIB_LATE = (2071, 2100)

# The model reads these five under these config keys; the filenames are what the input config names.
OUT_NAME: dict[str, str] = {
    "tas": "tas_pert.clm",
    "pr": "pr_pert.clm",
    "rsds": "rsds_pert.clm",
    "lwnet": "lwnet_pert.clm",
    "huss": "huss_pert.clm",
}


def _source_header(path: str) -> ClmHeader:
    reader = ClmReader(path)
    header = reader.header
    if header.datatype != LPJ_FLOAT or header.scalar != 1.0:
        raise ValueError(
            f"{path}: source is {header.typename} with scalar={header.scalar:g}. The perturbation "
            "writer refuses anything but unscaled float, because an integer source would quantise "
            "every perturbed value and the run would silently look like a null result."
        )
    if header.nbands != NDAYYEAR:
        raise ValueError(f"{path}: nbands={header.nbands}, expected {NDAYYEAR} (daily)")
    return header


def _read_block(
    path: str, cells: range, first: int, last: int
) -> npt.NDArray[np.float64]:
    """(ncell, nyear, 365) of one variable, for a contiguous cell range and a year window."""
    reader = ClmReader(path)
    with reader:
        return np.stack([reader.cell_years(c, first, last) for c in cells])


def _source_slice_bytes(path: str, cells: range, first: int, last: int) -> bytes:
    """The exact bytes the source file holds for this block, in the layout a subset file uses.

    `value[year][cell][band]`, so a contiguous cell range within one year is one contiguous read.
    """
    header = ClmReader(path).header
    stride = header.nbands * header.itemsize
    out = bytearray()
    with Path(path).open("rb") as fh:
        for year in range(first, last + 1):
            fh.seek(header.year_offset(year) + (cells.start - header.firstcell) * stride)
            out += fh.read(len(cells) * stride)
    return bytes(out)


def _write_one(
    out_path: Path,
    src_header: ClmHeader,
    *,
    cells: range,
    first: int,
    last: int,
    values: npt.NDArray[np.float64],
) -> ClmHeader:
    """Write (ncell, nyear, 365) as a subset `.clm`, then read it back and check it matches."""
    header = ClmHeader(
        name=src_header.name,
        version=src_header.version,
        order=src_header.order,
        firstyear=first,
        nyear=last - first + 1,
        firstcell=cells.start,
        ncell=len(cells),
        nbands=src_header.nbands,
        cellsize_lon=src_header.cellsize_lon,
        scalar=src_header.scalar,
        cellsize_lat=src_header.cellsize_lat,
        datatype=src_header.datatype,
        nstep=src_header.nstep,
        timestep=src_header.timestep,
    )
    raw = np.ascontiguousarray(values.transpose(1, 0, 2), dtype=header.dtype)
    write_clm(out_path, header, [raw[i] for i in range(header.nyear)])

    back = ClmReader(out_path)
    with back:
        for i, year in enumerate(range(first, last + 1)):
            got = back.raw_year(year)
            if not np.array_equal(got, raw[i]):
                raise AssertionError(f"{out_path}: year {year} did not read back as written")
    return header


def build(
    cells: range,
    pert: Perturbation,
    out_dir: Path,
    window: tuple[int, int] = BASE_WINDOW,
) -> dict[str, Any]:
    """Write the five perturbed forcing files for `cells`, and return the provenance record."""
    cfg = paths()
    src = {v: str(cfg["inputs"]["historical"][v]) for v in VARS}
    calib = {v: str(cfg["inputs"][CALIB_LEG][v]) for v in ("tas", "pr", "lwnet")}
    first, last = window
    headers = {v: _source_header(src[v]) for v in VARS}
    out_dir.mkdir(parents=True, exist_ok=True)

    base = {v: _read_block(src[v], cells, first, last) for v in VARS}
    perturbed = {v: np.empty_like(base[v]) for v in VARS}
    patterns: list[CellPattern] = []
    for i, cell in enumerate(cells):
        cell_base = {v: base[v][i] for v in VARS}
        pr_clim = np.array(
            [
                cell_base["pr"][:, MONTH_START[m] : MONTH_START[m] + MONTH_LEN[m]]
                .sum(axis=1)
                .mean()
                for m in range(len(MONTH_LEN))
            ]
        )
        pattern = calibrate_cell(cell, pr_clim, calib, CALIB_EARLY, CALIB_LATE)
        patterns.append(pattern)
        out = apply_perturbation(cell_base, pattern, pert)
        for v in VARS:
            perturbed[v][i] = out[v]

    written: dict[str, Any] = {}
    for v in VARS:
        header = _write_one(
            out_dir / OUT_NAME[v],
            headers[v],
            cells=cells,
            first=first,
            last=last,
            values=perturbed[v],
        )
        path = out_dir / OUT_NAME[v]
        written[v] = {
            "file": OUT_NAME[v],
            "bytes": path.stat().st_size,
            "header": header.describe(),
            "source": src[v],
            "source_header": headers[v].describe(),
        }
        if pert.is_neutral:
            want = _source_slice_bytes(src[v], cells, first, last)
            got = path.read_bytes()[header.header_bytes :]
            if got != want:
                raise AssertionError(
                    f"{path}: a NEUTRAL perturbation did not reproduce the source bytes. The "
                    "writer is not a no-op on the identity design point, so no perturbed file it "
                    "produces can be trusted either."
                )
            written[v]["neutral_byte_identity"] = "PASS"

    record = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "cells": {"first": cells.start, "ncell": len(cells)},
        "window": [first, last],
        "base_leg": "historical",
        "perturbation": pert.as_dict(),
        "calibration": {
            "leg": CALIB_LEG,
            "contrast": f"{CALIB_LATE[0]}-{CALIB_LATE[1]} minus {CALIB_EARLY[0]}-{CALIB_EARLY[1]}",
            "why_within_leg": (
                "both terms are the same climate model and the same file, so the model's bias "
                "against the observational baseline cancels; scenario-minus-historical would be a "
                "model bias, not a climate change"
            ),
            "per_cell": [p.as_dict() for p in patterns],
        },
        "rules": {
            "relative_humidity": (
                "NOT held fixed -- hold-huss DIAGNOSTIC arm; rule 2 deliberately disabled; these "
                "files are for attribution only and must never enter the corpus"
                if pert.hold_huss_diagnostic
                else "held fixed under the MODEL's own definition (getvpd.c:38); verified to 1e-9 "
                "on every written value"
            ),
            "co2": "untouched and never written (MEMORY.md:co2-closed)",
            "wet_days": "invariant: precipitation is only ever multiplied, so a dry day stays dry",
        },
        "files": written,
        "diagnostics": _diagnostics(base, perturbed),
    }
    (out_dir / "perturbation.json").write_text(json.dumps(record, indent=2) + "\n", "utf-8")
    return record


def _diagnostics(
    base: dict[str, npt.NDArray[np.float64]], out: dict[str, npt.NDArray[np.float64]]
) -> dict[str, Any]:
    """What actually changed, per variable, in the units the number is quoted in."""
    return {
        "tas_ann_c": [float(base["tas"].mean()), float(out["tas"].mean())],
        "pr_ann_mm": [
            float(base["pr"].sum(axis=2).mean()),
            float(out["pr"].sum(axis=2).mean()),
        ],
        "rsds_ann_wm2": [float(base["rsds"].mean()), float(out["rsds"].mean())],
        "lwnet_ann_wm2": [float(base["lwnet"].mean()), float(out["lwnet"].mean())],
        "huss_ann_kgkg": [float(base["huss"].mean()), float(out["huss"].mean())],
        "model_rh_mean": [
            float(model_relative_humidity(base["tas"], base["huss"]).mean()),
            float(model_relative_humidity(out["tas"], out["huss"]).mean()),
        ],
        "wet_days_per_year": [
            float((base["pr"] > 0).sum(axis=2).mean()),
            float((out["pr"] > 0).sum(axis=2).mean()),
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", type=int, help="one cell; shorthand for --first-cell N --ncell 1")
    ap.add_argument("--first-cell", type=int)
    ap.add_argument("--ncell", type=int, default=1)
    ap.add_argument("--point", help="a named point of the pilot design, e.g. 'control'")
    ap.add_argument("--name", default="custom", help="name for an explicitly given perturbation")
    ap.add_argument("--dtemp", type=float, default=0.0)
    ap.add_argument("--fprec", type=float, default=1.0)
    ap.add_argument("--sprec", type=float, default=0.0)
    ap.add_argument("--frad", type=float, default=1.0)
    ap.add_argument("--fiav", type=float, default=1.0)
    ap.add_argument("--out-dir")
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="write a NEUTRAL set and prove it reproduces the source bytes exactly",
    )
    ap.add_argument(
        "--hold-huss-diagnostic",
        action="store_true",
        help="⚠ breaks rule 2 on purpose: leave humidity alone so relative humidity FALLS. For "
        "attribution beside a real arm only; never for corpus rows.",
    )
    args = ap.parse_args()

    first_cell = args.cell if args.cell is not None else args.first_cell
    if first_cell is None:
        ap.error("give --cell or --first-cell")
    cells = range(first_cell, first_cell + args.ncell)

    if args.self_test:
        pert = Perturbation.neutral()
    elif args.point:
        pert = design_by_name(args.point)
        if args.hold_huss_diagnostic:
            pert = replace(pert, name=f"{pert.name}_nofixrh", hold_huss_diagnostic=True)
    else:
        pert = Perturbation(
            args.name,
            args.dtemp,
            args.fprec,
            args.sprec,
            args.frad,
            args.fiav,
            hold_huss_diagnostic=args.hold_huss_diagnostic,
        )

    out_dir = (
        Path(args.out_dir) if args.out_dir else scratch("forcing", f"c{first_cell}", pert.name)
    )

    record = build(cells, pert, out_dir)
    print(pert.describe())
    print(f"cells {cells.start}..{cells.stop - 1}  window {record['window']}  -> {out_dir}")
    for v in VARS:
        info = record["files"][v]
        flag = "  [neutral byte identity PASS]" if "neutral_byte_identity" in info else ""
        print(f"  {v:6s} {info['bytes']:>8d} B  {info['header']}{flag}")
    diag = record["diagnostics"]
    print("  base -> perturbed:")
    for key, (before, after) in diag.items():
        print(f"    {key:20s} {before:12.5f} -> {after:12.5f}")
    for pat in record["calibration"]["per_cell"]:
        if pat["flags"]:
            print(f"  cell {pat['cell']} calibration guards fired: {'; '.join(pat['flags'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
