"""The LPJmL `.clm` format: the forcing files, the grid, and the soil-depth input.

WHY THE WRITER MATTERS AS MUCH AS THE READER. The reader gets us climate features. The WRITER is
what makes a designed climate-perturbation ensemble possible at all -- the same cell spun up under
many climates -- which is the one thing that decollinearises climate from place and the one thing
the predecessor could never do (`docs/reference/inherited.md` §2).

⚠ THE FORMAT IS VERSION-DEPENDENT AND THIS INPUT SET IS MIXED. Historic is v3 (float32, scalar 1.0);
in the scenario legs `tas`/`pr`/`rsds`/`lwnet` are v2 (int16, scalar 0.1, i.e. tenths of a degree)
while `huss` is v3 (float32). One hardcoded dtype reads four of the five wrong -- and reads them as
plausible numbers, not as an error. ALWAYS parse the header, which is what this module does.

⚠ THE v3 DATATYPE CODES ARE 0-BASED: 0=byte 1=short 2=int 3=float 4=double. An off-by-one there
once read temperatures as ~5.9e8 degrees.

FRAMING (openinputfile.c, freadanyheader.c, headersize.c)

    <name>          strlen(name) bytes, no terminator: "LPJCLIM", "LPJGRID", "LPJSOIL", ...
    int32 version
    version 1 -> Header_old  24 bytes   6 int32
    version 2 -> Header2     32 bytes   6 int32, 2 float32 (cellsize, scalar); datatype is SHORT
    version 3 -> Header3     40 bytes   6 int32, 3 float32, int32 datatype
    version 4 -> Header      48 bytes   Header3 + int32 nstep + int32 timestep

DATA ORDER is `CELLYEAR` and nothing else is accepted (openclimate.c). The bytes are laid out

    value[year][cell][band]

so one year is a contiguous `ncell * nbands` block -- which is why the model seeks
`year_index * ncell * nbands * itemsize + headersize` and never scans. A physical value is
`intercept + raw * scalar`; `intercept` is zero for every variable we read (it is 100 with a
negated scalar only for the cloudiness input, which this configuration does not use).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import numpy.typing as npt

CLM_MAX_VERSION = 4
CELLYEAR = 1

# include/header.h. The name length is part of the framing, so the pair is what identifies a file.
KNOWN_NAMES: tuple[str, ...] = (
    "LPJCLIM",
    "LPJGRID",
    "LPJSOIL",
    "LPJDRAI",
    "LPJLUSE",
    "LPJ_COW",
    "LPJELEV",
    "LPJ_SPH",
    "LPJSOWD",
)

# The v3 code -> numpy dtype. 0-BASED; see the module docstring.
_DTYPES: tuple[str, ...] = ("u1", "<i2", "<i4", "<f4", "<f8")
_TYPENAMES: tuple[str, ...] = ("byte", "short", "int", "float", "double")

LPJ_BYTE, LPJ_SHORT, LPJ_INT, LPJ_FLOAT, LPJ_DOUBLE = range(5)


@dataclass
class ClmHeader:
    """A `.clm` header, with every version's defaults already filled in as the C fills them."""

    name: str
    version: int
    order: int
    firstyear: int
    nyear: int
    firstcell: int
    ncell: int
    nbands: int
    cellsize_lon: float = 0.5
    scalar: float = 1.0
    cellsize_lat: float = 0.5
    datatype: int = LPJ_SHORT
    nstep: int = 1
    timestep: int = 1

    @property
    def itemsize(self) -> int:
        return int(np.dtype(_DTYPES[self.datatype]).itemsize)

    @property
    def dtype(self) -> str:
        return _DTYPES[self.datatype]

    @property
    def typename(self) -> str:
        return _TYPENAMES[self.datatype]

    @property
    def header_bytes(self) -> int:
        """`headersize()`: the name, the version word, and the version's own struct."""
        payload = {1: 24, 2: 32, 4: 48}.get(self.version, 40)
        return len(self.name) + 4 + payload

    @property
    def year_bytes(self) -> int:
        """One year is a contiguous `ncell * nbands` block."""
        return self.ncell * self.nbands * self.itemsize

    @property
    def lastyear(self) -> int:
        return self.firstyear + self.nyear - 1

    def year_offset(self, year: int) -> int:
        if not self.firstyear <= year <= self.lastyear:
            raise IndexError(f"year {year} outside [{self.firstyear},{self.lastyear}] of this file")
        return self.header_bytes + (year - self.firstyear) * self.year_bytes

    # -- framing ------------------------------------------------------------------------------
    @classmethod
    def read(cls, fh: BinaryIO, name: str | None = None) -> ClmHeader:
        """Parse a header. With `name=None` the id is discovered by trying the known names.

        Discovery matters because the name length changes where the version word sits, so a
        mismatched name does not merely mislabel the file -- it shifts every field.
        """
        start = fh.tell()
        candidates = (name,) if name is not None else KNOWN_NAMES
        for cand in candidates:
            assert cand is not None
            fh.seek(start)
            if fh.read(len(cand)).decode("latin-1") != cand:
                continue
            (version,) = struct.unpack("<i", fh.read(4))
            if version & 0xFF == 0:
                raise NotImplementedError(
                    f"{cand}: byte-swapped file (low byte of the version word is zero)"
                )
            if not 1 <= version <= CLM_MAX_VERSION:
                continue
            return cls._read_payload(fh, cand, version)
        fh.seek(start)
        head = fh.read(16)
        raise ValueError(f"not a recognised .clm file; first bytes are {head!r}")

    @classmethod
    def _read_payload(cls, fh: BinaryIO, name: str, version: int) -> ClmHeader:
        if version == 1:
            f = struct.unpack("<6i", fh.read(24))
            return cls(name, version, *f, datatype=LPJ_SHORT)
        if version == 2:
            f = struct.unpack("<6i2f", fh.read(32))
            return cls(
                name,
                version,
                *f[:6],
                cellsize_lon=f[6],
                scalar=f[7],
                cellsize_lat=f[6],  # v2 has one cellsize; the C copies it to both
                datatype=LPJ_SHORT,
            )
        if version == 3:
            f = struct.unpack("<6i3fi", fh.read(40))
            return cls(
                name,
                version,
                *f[:6],
                cellsize_lon=f[6],
                scalar=f[7],
                cellsize_lat=f[8],
                datatype=f[9],
            )
        f = struct.unpack("<6i3fi2i", fh.read(48))
        return cls(
            name,
            version,
            *f[:6],
            cellsize_lon=f[6],
            scalar=f[7],
            cellsize_lat=f[8],
            datatype=f[9],
            nstep=f[10],
            timestep=f[11],
        )

    def pack(self) -> bytes:
        """Re-emit the header bytes. Round-tripping these against a real file IS the proof."""
        out = self.name.encode("latin-1") + struct.pack("<i", self.version)
        common = (self.order, self.firstyear, self.nyear, self.firstcell, self.ncell, self.nbands)
        if self.version == 1:
            return out + struct.pack("<6i", *common)
        if self.version == 2:
            return out + struct.pack("<6i2f", *common, self.cellsize_lon, self.scalar)
        if self.version == 3:
            return out + struct.pack(
                "<6i3fi",
                *common,
                self.cellsize_lon,
                self.scalar,
                self.cellsize_lat,
                self.datatype,
            )
        return out + struct.pack(
            "<6i3fi2i",
            *common,
            self.cellsize_lon,
            self.scalar,
            self.cellsize_lat,
            self.datatype,
            self.nstep,
            self.timestep,
        )

    def describe(self) -> str:
        """One line naming the basis, so a number derived from this file can carry it."""
        return (
            f"{self.name} v{self.version} {self.typename} scalar={self.scalar:g} "
            f"years {self.firstyear}-{self.lastyear} ncell={self.ncell} nbands={self.nbands}"
        )


class ClmReader:
    """Seek-by-year access to a `.clm` file. Never scans; the framing is fully computable."""

    def __init__(self, path: Path | str, name: str | None = None) -> None:
        self.path = Path(path)
        self.filesize = self.path.stat().st_size
        with self.path.open("rb") as fh:
            self.header = ClmHeader.read(fh, name)
        if self.header.order != CELLYEAR:
            raise ValueError(
                f"{self.path}: order {self.header.order}, but the model accepts only cellyear (1)"
            )
        want = self.header.header_bytes + self.header.nyear * self.header.year_bytes
        if want != self.filesize:
            raise ValueError(
                f"{self.path}: header says {want} bytes "
                f"({self.header.describe()}) but the file is {self.filesize}. "
                "The C only WARNS here (WARNING032); we refuse, because a size mismatch means the "
                "dtype or the year count is wrong and every value read would be silently shifted."
            )
        self._fh: BinaryIO | None = None

    def __enter__(self) -> ClmReader:
        self._fh = self.path.open("rb")
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _read_at(self, offset: int, nbytes: int) -> bytes:
        if self._fh is not None:
            self._fh.seek(offset)
            return self._fh.read(nbytes)
        with self.path.open("rb") as fh:
            fh.seek(offset)
            return fh.read(nbytes)

    def raw_year(self, year: int) -> npt.NDArray[Any]:
        """One year, undecoded, shaped (ncell, nbands). The bytes exactly as stored."""
        h = self.header
        blob = self._read_at(h.year_offset(year), h.year_bytes)
        return np.frombuffer(blob, dtype=h.dtype).reshape(h.ncell, h.nbands)

    def year(
        self, year: int, cells: npt.NDArray[np.int64] | None = None
    ) -> npt.NDArray[np.float64]:
        """One year in physical units, shaped (ncell or len(cells), nbands).

        `scalar` comes from the header for v2 and above, so a v2 int16 file in tenths of a degree
        decodes correctly without the caller knowing it was int16.
        """
        raw = self.raw_year(year)
        if cells is not None:
            raw = raw[cells]
        return raw.astype(np.float64) * self.header.scalar

    def cell_years(self, cell: int, first: int, last: int) -> npt.NDArray[np.float64]:
        """One cell over a year range, shaped (nyear, nbands).

        Reads one cell's slice per year rather than a whole year, which for a 30-year window over
        67,420 cells is 30 small seeks instead of 3 GB. Use `year()` when you want every cell.
        """
        h = self.header
        out = np.empty((last - first + 1, h.nbands), dtype=np.float64)
        stride = h.nbands * h.itemsize
        for i, yr in enumerate(range(first, last + 1)):
            offset = h.year_offset(yr) + (cell - h.firstcell) * stride
            blob = self._read_at(offset, stride)
            out[i] = np.frombuffer(blob, dtype=h.dtype).astype(np.float64) * h.scalar
        return out


def write_clm(
    path: Path | str,
    header: ClmHeader,
    raw_years: list[npt.NDArray[Any]] | npt.NDArray[Any],
) -> None:
    """Write a `.clm` file from UNDECODED year blocks.

    Raw rather than physical on purpose: a perturbed forcing file must be byte-comparable against
    the file it was derived from wherever it was not perturbed, and a float32 -> physical -> float32
    trip is not guaranteed to be the identity for a v2 int16 file with scalar 0.1.
    """
    path = Path(path)
    blocks = (
        list(raw_years)
        if isinstance(raw_years, list)
        else [raw_years[i] for i in range(len(raw_years))]
    )
    if len(blocks) != header.nyear:
        raise ValueError(f"header says nyear={header.nyear} but {len(blocks)} year blocks given")
    with path.open("wb") as fh:
        fh.write(header.pack())
        for i, block in enumerate(blocks):
            arr = np.ascontiguousarray(block, dtype=header.dtype)
            if arr.shape != (header.ncell, header.nbands):
                raise ValueError(
                    f"year block {i} has shape {arr.shape}, expected "
                    f"({header.ncell},{header.nbands})"
                )
            fh.write(arr.tobytes())


def read_grid(path: Path | str) -> npt.NDArray[np.float64]:
    """The coordinate file, as (ncell, 2) of (lon, lat) in degrees.

    ⚠ A SECOND 67,420-cell coordinate file exists elsewhere on the cluster with a DIFFERENT
    ordering; pairing the two shifts every cell silently. Use the one in `config/paths.yaml`
    (`inputs.coord`), which is the orderA pair that every ground-truth leg was run with.
    """
    reader = ClmReader(path, name="LPJGRID")
    h = reader.header
    if h.nbands != 2:
        raise ValueError(f"{path}: grid file has nbands={h.nbands}, expected 2 (lon, lat)")
    if h.nyear != 1:
        raise ValueError(f"{path}: grid file has nyear={h.nyear}, expected 1")
    return reader.year(h.firstyear)
