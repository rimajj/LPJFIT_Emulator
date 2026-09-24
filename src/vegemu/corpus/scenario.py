"""The acceptance truth's forcing: a 30-year window of a GLOBAL forcing leg, cut out per cell.

⚠ PARKED WITH ITS CAMPAIGN (owner, 2026-09-24): no new all-cell reference runs will be made; the
stored spin-up (pre-CO2-rise years only), ssp126 and ssp370 runs are the reference. The slicer stays
because it is correct and tested (it reproduces the pilot's control forcing byte for byte), and a
single-cell forcing window is useful beyond that campaign. The paragraph below is its ORIGINAL
rationale, superseded by that ruling.

WHAT THIS IS FOR. The owner's acceptance criterion is proof on all tree-bearing cells, under both
scenarios, and on the response between them. Nothing already on disk is that proof for the
equilibrium product: the stored spin-up carries a CO2 ramp in its last 300 years and the scenario
runs are transients from a 2019 state, not spin-ups. So the truth is a NEW set of single-cell
1000-year spin-ups -- and the only thing that makes it comparable to the training corpus is that it
is run with EXACTLY the pilot corpus's protocol. This module is the half of that protocol that is
the forcing: every file it writes has the same format, the same year labels and the same framing as
the pilot's own per-run forcing, so the spin-up config and the model's year loop are identical and
only the climate differs.

THE THREE THINGS THAT MUST BE THE SAME AS THE PILOT, and why each one matters

  * THE YEAR LABELS ARE 1970-1999, WHATEVER YEARS THE CLIMATE CAME FROM. The spin-up config is
    `firstyear 2000, lastyear 1999, nspinup 1000`, and the model draws a random stored year for
    every model year before the climate file's own first year (`corpus_spinup_config.py` header).
    With a file labelled 1970-1999 that is 970 shuffled years then the 30 file years in order. A
    2071-2100 file left with its real labels would make the model treat every one of its years as a
    FUTURE year -- a different protocol, silently. So 2071-2100 is cut and RELABELLED 1970-1999.
  * THE FORMAT IS v3 float32 WITH SCALAR 1.0. The historical leg already is; the scenario legs are
    v2 int16 tenths of a unit for tas/pr/rsds/lwnet and v3 float for huss (`binfmt.clm` header).
    They are decoded exactly as the C decodes them -- `raw * header.scalar`, with the header's
    float32 scalar widened to double (openclimate.c:198, readclimate) -- and stored as float32.
    ⚠ THAT FINAL float32 ROUNDING IS THE ONE PLACE A SCENARIO FILE HERE IS NOT BIT-FOR-BIT WHAT THE
    C WOULD HAVE COMPUTED FROM THE int16 SOURCE: the C keeps the product in double, this file keeps
    it to 24 bits (relative error under 6e-8, i.e. a thousandth of the source's own 0.1
    quantisation). It is disclosed, not hidden, and it is the price of one format for every leg.
  * THE FILENAMES ARE THE PILOT'S `*_pert.clm`. Nothing here is perturbed. The names are kept
    because the spin-up config builder binds each config key to exactly those names
    (`corpus_spinup_config.INPUT_KEY`) and it is not ours to change; a second naming scheme would
    need a second config builder, which is the unvalidated divergence the builder exists to avoid.

⚠ AN UNSCALED FLOAT SOURCE IS COPIED AS BYTES, NEVER DECODED AND RE-ENCODED. That is what makes the
historical leg reproduce the pilot's control forcing byte-identically -- the pilot's control point
is an unperturbed copy of the same slice -- and that byte identity is the proof that a truth run and
a corpus run at the same cell are the same simulation. It is asserted in the tests and in the
build stage of `scripts/corpus_truth.py`.

⚠ CO2 IS NOT HANDLED HERE, AND THE EMULATOR NEVER SEES IT. Which constant CO2 level the truth is
spun up under is an open owner question; it is a parameter of the campaign, recorded in its
provenance, and never a feature (`MEMORY.md:co2-closed`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import CELLYEAR, LPJ_DOUBLE, LPJ_FLOAT, ClmHeader, ClmReader, write_clm
from vegemu.paths import paths

VARS: tuple[str, ...] = ("tas", "pr", "rsds", "lwnet", "huss")
NDAYYEAR = 365

# The years every per-run forcing file is LABELLED with -- the pilot's `BASE_WINDOW`. Not a date:
# the label the spin-up protocol needs, whatever years the climate itself came from.
LABEL_FIRST = 1970
NYEAR = 30

# The source window of each leg. The historical one IS the pilot's baseline window; the two
# scenario ones are the last 30 years of the same MPI-ESM1-2-HR runs the stored transients used.
TRUTH_WINDOWS: dict[str, tuple[int, int]] = {
    "historical": (1970, 1999),
    "ssp126": (2071, 2100),
    "ssp370": (2071, 2100),
}

# The filenames the pilot's forcing uses, and therefore the ones its config builder binds to.
FORCING_NAME: dict[str, str] = {
    "tas": "tas_pert.clm",
    "pr": "pr_pert.clm",
    "rsds": "rsds_pert.clm",
    "lwnet": "lwnet_pert.clm",
    "huss": "huss_pert.clm",
}


def source_files(leg: str) -> dict[str, str]:
    """The five global forcing files of a leg, from `config/paths.yaml`."""
    cfg = paths()["inputs"]
    if leg not in cfg:
        raise KeyError(f"no forcing leg {leg!r} in config/paths.yaml inputs")
    return {v: str(cfg[leg][v]) for v in VARS}


def output_header(src: ClmHeader, cells: range, label_first: int, nyear: int) -> ClmHeader:
    """The header a per-run forcing file carries: v3 float32, scalar 1.0, relabelled years.

    Everything the model reads that is not the data -- name, order, cell size, band count -- is
    taken from the source, so for an unscaled v3 float source this is exactly the header the pilot
    writer produced (it copies the source header and changes only the year and cell fields).
    """
    return ClmHeader(
        name=src.name,
        version=3,
        order=CELLYEAR,
        firstyear=label_first,
        nyear=nyear,
        firstcell=cells.start,
        ncell=len(cells),
        nbands=src.nbands,
        cellsize_lon=src.cellsize_lon,
        scalar=1.0,
        cellsize_lat=src.cellsize_lat,
        datatype=LPJ_FLOAT,
        nstep=src.nstep,
        timestep=src.timestep,
    )


def is_verbatim(header: ClmHeader) -> bool:
    """True when the source's bytes ARE the output's bytes: unscaled float32."""
    return header.datatype == LPJ_FLOAT and header.scalar == 1.0


def _check_source(path: str, header: ClmHeader, cells: range, first: int, last: int) -> None:
    if header.order != CELLYEAR:
        raise ValueError(f"{path}: order {header.order}; the model accepts only cellyear (1)")
    if header.nbands != NDAYYEAR:
        raise ValueError(f"{path}: nbands={header.nbands}, expected {NDAYYEAR} (daily)")
    if header.datatype == LPJ_DOUBLE:
        raise ValueError(
            f"{path}: a double source would lose precision in a float32 file. No input in this "
            "set is double; refusing rather than rounding silently."
        )
    if not header.firstyear <= first <= last <= header.lastyear:
        raise ValueError(
            f"{path}: window {first}-{last} is outside the file's "
            f"{header.firstyear}-{header.lastyear}"
        )
    if cells.start < header.firstcell or cells.stop > header.firstcell + header.ncell:
        raise ValueError(
            f"{path}: cells {cells.start}..{cells.stop - 1} outside the file's "
            f"{header.firstcell}..{header.firstcell + header.ncell - 1}"
        )


def read_raw_window(
    path: str | Path, cells: range, first: int, last: int
) -> tuple[ClmHeader, npt.NDArray[Any]]:
    """(nyear, ncell, nbands) of a contiguous cell block, UNDECODED, in the source's own dtype.

    One contiguous read per year: the layout is `value[year][cell][band]`, so a contiguous cell
    range within a year is one seek and one read -- 30 reads for a window, not 30 per cell.
    """
    reader = ClmReader(path)
    h = reader.header
    _check_source(str(path), h, cells, first, last)
    stride = h.nbands * h.itemsize
    out = np.empty((last - first + 1, len(cells), h.nbands), dtype=h.dtype)
    with Path(path).open("rb") as fh:
        for i, year in enumerate(range(first, last + 1)):
            fh.seek(h.year_offset(year) + (cells.start - h.firstcell) * stride)
            blob = fh.read(len(cells) * stride)
            if len(blob) != len(cells) * stride:
                raise OSError(f"{path}: short read at year {year}")
            out[i] = np.frombuffer(blob, dtype=h.dtype).reshape(len(cells), h.nbands)
    return h, out


def to_float32(raw: npt.NDArray[Any], header: ClmHeader) -> npt.NDArray[np.float32]:
    """Physical values as float32, decoded exactly as the C decodes them.

    An unscaled float32 source is returned AS IS -- no arithmetic touches it, so its bits (every
    NaN payload and signed zero included) survive to the output. Anything else is `raw * scalar` in
    double, `scalar` being the header's float32 widened, then rounded once to float32.
    """
    if is_verbatim(header):
        return np.ascontiguousarray(raw, dtype=np.float32)
    return (raw.astype(np.float64) * float(header.scalar)).astype(np.float32)


@dataclass(frozen=True)
class WindowBlock:
    """One leg's five variables over one contiguous cell block, ready to be written per cell."""

    leg: str
    cells: range
    window: tuple[int, int]
    label_first: int
    src: dict[str, str]
    headers: dict[str, ClmHeader]
    values: dict[str, npt.NDArray[np.float32]] = field(repr=False)
    """Per variable, (nyear, ncell, nbands) float32."""


def load_block(
    leg: str,
    cells: range,
    *,
    window: tuple[int, int] | None = None,
    label_first: int = LABEL_FIRST,
    files: Mapping[str, str] | None = None,
) -> WindowBlock:
    """Read one leg's window for a contiguous block of cells, all five variables."""
    first, last = window or TRUTH_WINDOWS[leg]
    if last - first + 1 != NYEAR:
        raise ValueError(
            f"window {first}-{last} is {last - first + 1} years; the spin-up protocol cycles "
            f"exactly {NYEAR} (nspinyear), so any other length is a different protocol"
        )
    src = dict(files) if files is not None else source_files(leg)
    headers: dict[str, ClmHeader] = {}
    values: dict[str, npt.NDArray[np.float32]] = {}
    for var in VARS:
        header, raw = read_raw_window(src[var], cells, first, last)
        headers[var] = header
        values[var] = to_float32(raw, header)
    return WindowBlock(
        leg=leg,
        cells=cells,
        window=(first, last),
        label_first=label_first,
        src=src,
        headers=headers,
        values=values,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_cell(block: WindowBlock, cell: int, out_dir: Path) -> dict[str, Any]:
    """Write the five single-cell files for one cell of a loaded block, and verify each one.

    Verified by reading the file back through the reader the rest of the repo uses: the header must
    be the one intended and every year's bytes must be the block's bytes. The comparison is on
    BYTES, not values, because a NaN is never equal to itself and a value comparison would call a
    faithful copy of a missing day a mismatch.
    """
    if cell not in block.cells:
        raise IndexError(f"cell {cell} is not in the loaded block {block.cells}")
    i = cell - block.cells.start
    out_dir.mkdir(parents=True, exist_ok=True)
    one = range(cell, cell + 1)
    record: dict[str, Any] = {}
    for var in VARS:
        header = output_header(block.headers[var], one, block.label_first, NYEAR)
        data = np.ascontiguousarray(block.values[var][:, i : i + 1, :])
        dest = out_dir / FORCING_NAME[var]
        write_clm(dest, header, [data[y] for y in range(NYEAR)])
        back = ClmReader(dest)
        if back.header != header:
            raise AssertionError(f"{dest}: header read back as {back.header}, wrote {header}")
        with back:
            for y in range(NYEAR):
                if back.raw_year(block.label_first + y).tobytes() != data[y].tobytes():
                    raise AssertionError(f"{dest}: year {block.label_first + y} did not read back")
        record[var] = {
            "file": dest.name,
            "bytes": dest.stat().st_size,
            "sha256": _sha256(dest),
            "verbatim": is_verbatim(block.headers[var]),
        }
    return record


def write_block(
    block: WindowBlock, out_dir_for: Callable[[int], Path], cells: Sequence[int] | None = None
) -> dict[int, dict[str, Any]]:
    """Write every requested cell of a block (all of it by default) into its own directory."""
    wanted = list(block.cells) if cells is None else [int(c) for c in cells]
    return {cell: write_cell(block, cell, out_dir_for(cell)) for cell in wanted}


def write_cell_window(
    leg: str,
    cell: int,
    out_dir: Path,
    *,
    window: tuple[int, int] | None = None,
    label_first: int = LABEL_FIRST,
    files: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """One cell, one leg: read its window and write its five files. The convenience entry point."""
    block = load_block(
        leg, range(cell, cell + 1), window=window, label_first=label_first, files=files
    )
    return write_cell(block, cell, out_dir)


def describe(block: WindowBlock) -> dict[str, Any]:
    """The provenance of a block: which files, which window, how each was converted."""
    return {
        "leg": block.leg,
        "source_window": list(block.window),
        "label_window": [block.label_first, block.label_first + NYEAR - 1],
        "files": {
            var: {
                "path": block.src[var],
                "source_header": block.headers[var].describe(),
                "conversion": "verbatim float32 bytes"
                if is_verbatim(block.headers[var])
                else f"float32(raw * {block.headers[var].scalar!r}) -- the C's decode, rounded "
                "once to float32",
            }
            for var in VARS
        },
    }


def decoded_matches_source(
    written: Path, source: str | Path, cell: int, window: tuple[int, int], label_first: int
) -> bool:
    """The INDEPENDENT check: decode the written file and the source by a different code path.

    `ClmReader.cell_years` seeks one cell per year and decodes in float64 with the header's scalar;
    the writer read whole contiguous blocks. Agreement here means the written value is the source
    value times its scale, rounded once to float32 -- for every day of every year of the window.
    """
    got = ClmReader(written).cell_years(cell, label_first, label_first + NYEAR - 1)
    want = ClmReader(source).cell_years(cell, *window).astype(np.float32).astype(np.float64)
    return bool(np.array_equal(got, want, equal_nan=True))
