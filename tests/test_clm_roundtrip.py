"""The `.clm` round-trip: forcing, grid and soil-depth inputs.

Two real files in the input set are small enough to round-trip WHOLE and byte-for-byte -- the
coordinate file (539,411 B) and the soil-depth input (269,731 B). That is the strongest form of
invariant 7 available for this format, and it is free. For the 11.7 GB forcing files the same proof
is done piecewise: the header bytes must re-emit exactly, and one year's raw block must re-emit
exactly, which together cover every byte the framing describes.

The mixed-version trap is tested as a property of the real files rather than described in a comment:
`test_scenario_legs_are_mixed_versions` FAILS if someone "simplifies" the reader to one dtype.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vegemu.binfmt.clm import (
    LPJ_FLOAT,
    LPJ_SHORT,
    ClmHeader,
    ClmReader,
    read_grid,
    write_clm,
)
from vegemu.paths import paths

HAINICH = 42490
HAINICH_LON, HAINICH_LAT = 10.25, 51.25


def _inputs() -> dict[str, object]:
    return dict(paths()["inputs"])


def _exists(key: str, leg: str | None = None) -> bool:
    try:
        node = _inputs()
        value = node[leg][key] if leg else node[key]  # type: ignore[index]
    except (KeyError, TypeError):
        return False
    return Path(str(value)).exists()


real_data = pytest.mark.skipif(
    not _exists("coord"), reason="needs the LPJmL-FIT input files under /p"
)

SMALL_FILES = ("coord", "soildepth")
FORCING_VARS = ("tas", "pr", "rsds", "lwnet", "huss")


@real_data
@pytest.mark.needs_real_data
@pytest.mark.parametrize("key", SMALL_FILES)
def test_whole_small_file_byte_identical(tmp_path: Path, key: str) -> None:
    """Read a real .clm file entirely, write it back, compare every byte."""
    src = Path(str(_inputs()[key]))
    reader = ClmReader(src)
    h = reader.header
    with reader:
        blocks = [reader.raw_year(y) for y in range(h.firstyear, h.lastyear + 1)]
    out = tmp_path / f"{key}.clm"
    write_clm(out, h, blocks)
    assert out.read_bytes() == src.read_bytes(), f"{key}: {h.describe()}"


@real_data
@pytest.mark.needs_real_data
@pytest.mark.parametrize("leg", ("historical", "ssp370", "ssp126"))
@pytest.mark.parametrize("var", FORCING_VARS)
def test_forcing_header_and_one_year_byte_identical(leg: str, var: str) -> None:
    """The 11.7 GB files, proven piecewise: the header, and one year's raw block."""
    src = Path(str(_inputs()[leg][var]))  # type: ignore[index]
    reader = ClmReader(src)
    h = reader.header
    with src.open("rb") as fh:
        assert fh.read(h.header_bytes) == h.pack(), f"{leg}/{var} header"
        fh.seek(h.year_offset(h.firstyear))
        want = fh.read(h.year_bytes)
    with reader:
        got = np.ascontiguousarray(reader.raw_year(h.firstyear)).tobytes()
    assert got == want, f"{leg}/{var} year {h.firstyear} ({h.describe()})"


@real_data
@pytest.mark.needs_real_data
def test_scenario_legs_are_mixed_versions() -> None:
    """The trap, as an executable assertion.

    Historic is v3 float32 with scalar 1. In BOTH scenario legs tas/pr/rsds/lwnet are v2 int16 with
    scalar 0.1 -- tenths of a degree -- while huss is v3 float32. One hardcoded dtype reads four of
    the five wrong, and reads them as plausible numbers rather than as an error.
    """
    for var in FORCING_VARS:
        h = ClmReader(Path(str(_inputs()["historical"][var]))).header  # type: ignore[index]
        assert (h.version, h.datatype, h.scalar) == (3, LPJ_FLOAT, 1.0), f"historical/{var}"

    for leg in ("ssp370", "ssp126"):
        for var in ("tas", "pr", "rsds", "lwnet"):
            h = ClmReader(Path(str(_inputs()[leg][var]))).header  # type: ignore[index]
            assert (h.version, h.datatype) == (2, LPJ_SHORT), f"{leg}/{var} version"
            assert h.scalar == pytest.approx(0.1), f"{leg}/{var} scalar"
        h = ClmReader(Path(str(_inputs()[leg]["huss"]))).header  # type: ignore[index]
        assert (h.version, h.datatype, h.scalar) == (3, LPJ_FLOAT, 1.0), f"{leg}/huss"


@real_data
@pytest.mark.needs_real_data
def test_decoded_values_are_physical() -> None:
    """A v2 int16 file in tenths of a degree must come out in degrees, not in tenths.

    This is the assertion that catches a missing `scalar`: 129 degC at Hainich is not an error the
    reader raises, it is a number a model happily trains on.
    """
    tas = ClmReader(Path(str(_inputs()["historical"]["tas"])))  # type: ignore[index]
    with tas:
        year = tas.cell_years(HAINICH, 1999, 1999)[0]
    assert year.shape == (365,)
    assert 5.0 < year.mean() < 13.0, f"Hainich annual mean {year.mean():.2f} degC"
    assert year.min() > -35.0 and year.max() < 45.0

    scen = ClmReader(Path(str(_inputs()["ssp370"]["tas"])))  # type: ignore[index]
    with scen:
        year2100 = scen.cell_years(HAINICH, 2100, 2100)[0]
    assert 8.0 < year2100.mean() < 20.0, f"scaled wrong: {year2100.mean():.2f} degC"
    # ssp370 warms Hainich materially by 2100; ssp126 barely does. That contrast IS the held-out
    # forcing test, so it is worth asserting the data actually carries it.
    low = ClmReader(Path(str(_inputs()["ssp126"]["tas"])))  # type: ignore[index]
    with low:
        low2100 = low.cell_years(HAINICH, 2100, 2100)[0]
    assert year2100.mean() - year.mean() > 2.0, "ssp370 should warm this cell by >2 K"
    assert (low2100.mean() - year.mean()) < (year2100.mean() - year.mean()) / 2


@real_data
@pytest.mark.needs_real_data
def test_grid_is_ordera() -> None:
    """Cell 42490 must be Hainich. In a DIFFERENT 67,420-cell grid it is the Sonoran desert.

    Getting this wrong does not raise; it silently relabels every cell in the corpus.
    """
    grid = read_grid(Path(str(_inputs()["coord"])))
    assert grid.shape == (67420, 2)
    lon, lat = grid[HAINICH]
    assert (lon, lat) == pytest.approx((HAINICH_LON, HAINICH_LAT))
    assert grid[:, 0].min() > -180 and grid[:, 0].max() < 180
    assert grid[:, 1].min() > -90 and grid[:, 1].max() < 90


# ---------------------------------------------------------------------------------------------
# Synthetic: every version, every dtype, and the writer's own guards.
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("version", (1, 2, 3, 4))
def test_header_roundtrip_every_version(tmp_path: Path, version: int) -> None:
    h = ClmHeader(
        name="LPJCLIM",
        version=version,
        order=1,
        firstyear=1901,
        nyear=3,
        firstcell=0,
        ncell=5,
        nbands=12,
        cellsize_lon=0.5,
        scalar=0.1 if version >= 2 else 1.0,
        cellsize_lat=0.5,
        datatype=LPJ_SHORT if version < 3 else LPJ_FLOAT,
    )
    blob = h.pack()
    assert len(blob) == h.header_bytes
    out = tmp_path / "h.clm"
    out.write_bytes(blob)
    with out.open("rb") as fh:
        back = ClmHeader.read(fh, "LPJCLIM")
    assert back.pack() == blob
    assert (back.version, back.datatype, back.nyear, back.ncell) == (
        version,
        h.datatype,
        3,
        5,
    )


@pytest.mark.parametrize("datatype", (0, 1, 2, 3, 4))
def test_data_roundtrip_every_dtype(tmp_path: Path, datatype: int) -> None:
    """The dtype code is 0-based and every code must survive a write/read/write cycle."""
    h = ClmHeader(
        name="LPJCLIM",
        version=3,
        order=1,
        firstyear=2000,
        nyear=2,
        firstcell=0,
        ncell=4,
        nbands=3,
        scalar=0.25,
        datatype=datatype,
    )
    rng = np.random.default_rng(datatype)
    blocks = [rng.integers(0, 100, size=(4, 3)).astype(h.dtype) for _ in range(2)]
    out = tmp_path / "d.clm"
    write_clm(out, h, blocks)
    reader = ClmReader(out, name="LPJCLIM")
    with reader:
        for i, want in enumerate(blocks):
            assert np.array_equal(reader.raw_year(2000 + i), want)
            assert np.allclose(reader.year(2000 + i), want.astype(float) * 0.25)
    # and the whole file re-emits byte-identically
    with reader:
        again = [reader.raw_year(y) for y in (2000, 2001)]
    out2 = tmp_path / "d2.clm"
    write_clm(out2, h, again)
    assert out2.read_bytes() == out.read_bytes()


def test_size_mismatch_is_refused(tmp_path: Path) -> None:
    """The C only warns (WARNING032). A wrong dtype shifts every value, so we refuse."""
    h = ClmHeader("LPJCLIM", 3, 1, 1901, 2, 0, 4, 3, datatype=LPJ_FLOAT)
    out = tmp_path / "short.clm"
    out.write_bytes(h.pack() + b"\x00" * (h.year_bytes + 4))
    with pytest.raises(ValueError, match="but the file is"):
        ClmReader(out, name="LPJCLIM")


def test_non_cellyear_order_is_refused(tmp_path: Path) -> None:
    h = ClmHeader("LPJCLIM", 3, 2, 1901, 1, 0, 2, 2, datatype=LPJ_FLOAT)
    out = tmp_path / "order.clm"
    out.write_bytes(h.pack() + b"\x00" * h.year_bytes)
    with pytest.raises(ValueError, match="only cellyear"):
        ClmReader(out, name="LPJCLIM")


def test_year_outside_range_is_an_indexerror(tmp_path: Path) -> None:
    h = ClmHeader("LPJCLIM", 3, 1, 1901, 2, 0, 2, 2, datatype=LPJ_FLOAT)
    out = tmp_path / "y.clm"
    write_clm(out, h, [np.zeros((2, 2), "<f4"), np.zeros((2, 2), "<f4")])
    reader = ClmReader(out, name="LPJCLIM")
    with pytest.raises(IndexError, match="outside"):
        reader.raw_year(1903)


def test_writer_rejects_a_wrong_shape(tmp_path: Path) -> None:
    h = ClmHeader("LPJCLIM", 3, 1, 1901, 1, 0, 4, 3, datatype=LPJ_FLOAT)
    with pytest.raises(ValueError, match="shape"):
        write_clm(tmp_path / "bad.clm", h, [np.zeros((3, 4), "<f4")])
    with pytest.raises(ValueError, match="nyear"):
        write_clm(tmp_path / "bad2.clm", h, [])
