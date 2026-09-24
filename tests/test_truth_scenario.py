"""The truth forcing slicer: same format, same labels, same bytes as the pilot's own forcing.

WHY THIS TEST EXISTS. The acceptance truth is only comparable to the training corpus if a truth run
and a corpus run at the same cell are THE SAME SIMULATION. For the historical leg that is checkable
to the byte: the pilot's control point is an unperturbed copy of the same 30 years, so the slicer
must reproduce the pilot's control forcing files exactly -- header and data. For the scenario legs
there is no pilot file to match, and the proof is the decode: every written value must be the
source's raw value times its scale, rounded once to float32, with the years relabelled 1970-1999.

Three ways this silently goes wrong, each pinned below:
  1. KEEPING THE SOURCE'S YEAR LABELS. A 2071-2100 file makes the model treat every stored year as
     a future year: the spin-up would not cycle it at all.
  2. KEEPING THE SOURCE'S FORMAT. A v2 int16 header with a float32 payload reads as garbage, and a
     v2 int16 file is a different input format from the one the corpus was generated with.
  3. DECODING AND RE-ENCODING A FLOAT SOURCE. float32 -> float64 -> float32 is exact for ordinary
     values, but it is not a byte copy, and a byte copy is what the identity claim rests on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from vegemu.binfmt.clm import LPJ_FLOAT, LPJ_SHORT, ClmHeader, ClmReader, write_clm
from vegemu.corpus import scenario
from vegemu.paths import paths

NCELL = 12
NB = scenario.NDAYYEAR


def _global(
    path: Path, *, datatype: int, version: int, scalar: float, first: int, nyear: int, seed: int
) -> np.ndarray:
    """A small synthetic 'global' forcing file; returns its raw (nyear, ncell, 365) block."""
    header = ClmHeader(
        name="LPJCLIM",
        version=version,
        order=1,
        firstyear=first,
        nyear=nyear,
        firstcell=0,
        ncell=NCELL,
        nbands=NB,
        scalar=scalar,
        datatype=datatype,
    )
    rng = np.random.default_rng(seed)
    if datatype == LPJ_SHORT:
        raw = rng.integers(-400, 400, size=(nyear, NCELL, NB)).astype("<i2")
    else:
        raw = rng.normal(10.0, 5.0, size=(nyear, NCELL, NB)).astype("<f4")
        raw[:, 3, 7] = np.nan  # a missing day must survive as bytes, not be "compared equal"
    write_clm(path, header, [raw[y] for y in range(nyear)])
    return raw


@pytest.fixture
def sources(tmp_path: Path) -> dict[str, dict[str, str]]:
    """A historical-shaped leg (v3 float, 1901-2019) and a scenario-shaped one (v2 int16 x0.1,
    2015-2100, with huss v3 float) -- the real input set's exact mix of formats."""
    hist: dict[str, str] = {}
    scen: dict[str, str] = {}
    for k, var in enumerate(scenario.VARS):
        hp = tmp_path / f"hist_{var}.clm"
        _global(hp, datatype=LPJ_FLOAT, version=3, scalar=1.0, first=1901, nyear=119, seed=k)
        hist[var] = str(hp)
        sp = tmp_path / f"ssp_{var}.clm"
        if var == "huss":
            _global(
                sp, datatype=LPJ_FLOAT, version=3, scalar=1.0, first=2015, nyear=86, seed=10 + k
            )
        else:
            _global(
                sp, datatype=LPJ_SHORT, version=2, scalar=0.1, first=2015, nyear=86, seed=10 + k
            )
        scen[var] = str(sp)
    return {"historical": hist, "ssp370": scen}


def test_historical_is_a_byte_copy_with_the_pilot_header(sources: dict, tmp_path: Path) -> None:
    cell = 3  # the synthetic source's NaN column
    scenario.write_cell_window("historical", cell, tmp_path / "out", files=sources["historical"])
    for var in scenario.VARS:
        out = tmp_path / "out" / scenario.FORCING_NAME[var]
        src = ClmReader(sources["historical"][var])
        h = ClmReader(out).header
        assert (h.version, h.datatype, h.scalar) == (3, LPJ_FLOAT, 1.0)
        assert (h.firstyear, h.nyear, h.firstcell, h.ncell) == (1970, 30, cell, 1)
        stride = NB * 4
        want = bytearray()
        with open(sources["historical"][var], "rb") as fh:
            for year in range(1970, 2000):
                fh.seek(src.header.year_offset(year) + cell * stride)
                want += fh.read(stride)
        assert out.read_bytes()[h.header_bytes :] == bytes(want)


def test_scenario_is_relabelled_float_and_equals_source_times_scale(
    sources: dict, tmp_path: Path
) -> None:
    cell = 9
    window = scenario.TRUTH_WINDOWS["ssp370"]
    scenario.write_cell_window("ssp370", cell, tmp_path / "s", files=sources["ssp370"])
    for var in scenario.VARS:
        out = tmp_path / "s" / scenario.FORCING_NAME[var]
        h = ClmReader(out).header
        assert (h.version, h.datatype, h.scalar, h.firstyear, h.nyear) == (
            3,
            LPJ_FLOAT,
            1.0,
            1970,
            30,
        )
        got = ClmReader(out).cell_years(cell, 1970, 1999)
        src = ClmReader(sources["ssp370"][var])
        raw = np.stack([src.raw_year(y)[cell] for y in range(window[0], window[1] + 1)])
        want = (raw.astype(np.float64) * float(src.header.scalar)).astype(np.float32)
        assert np.array_equal(got, want.astype(np.float64), equal_nan=True)
        assert scenario.decoded_matches_source(out, sources["ssp370"][var], cell, window, 1970)
    # And the int16 variables really were scaled: tenths of a unit, not raw counts.
    tas = ClmReader(tmp_path / "s" / "tas_pert.clm").cell_years(cell, 1970, 1999)
    assert np.abs(tas).max() < 41.0


def test_a_block_writes_the_same_bytes_as_single_cells(sources: dict, tmp_path: Path) -> None:
    """The build stage reads contiguous BLOCKS; the result must not depend on the block edges."""
    block = scenario.load_block("ssp370", range(2, 10), files=sources["ssp370"])
    scenario.write_block(block, lambda c: tmp_path / "blk" / f"c{c}")
    for cell in (2, 6, 9):
        scenario.write_cell_window(
            "ssp370", cell, tmp_path / "one" / f"c{cell}", files=sources["ssp370"]
        )
        for var in scenario.VARS:
            name = scenario.FORCING_NAME[var]
            assert (tmp_path / "blk" / f"c{cell}" / name).read_bytes() == (
                tmp_path / "one" / f"c{cell}" / name
            ).read_bytes()


def test_refuses_a_window_that_is_not_thirty_years(sources: dict, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="30"):
        scenario.load_block("ssp370", range(0, 1), window=(2071, 2099), files=sources["ssp370"])


def test_refuses_a_window_outside_the_source(sources: dict) -> None:
    with pytest.raises(ValueError, match="outside"):
        scenario.load_block(
            "historical", range(0, 1), window=(2000, 2029), files=sources["historical"]
        )


def test_filenames_are_the_ones_the_config_builder_binds() -> None:
    """`corpus_spinup_config.INPUT_KEY` names these files; renaming them breaks every config."""
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "corpus_spinup_config", root / "scripts" / "corpus_spinup_config.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("corpus_spinup_config", mod)
    spec.loader.exec_module(mod)
    assert set(mod.INPUT_KEY.values()) == set(scenario.FORCING_NAME.values())


# ------------------------------------------------------------------------------------------------
# the real files: the pilot's control forcing, and the real scenario legs
# ------------------------------------------------------------------------------------------------

PILOT_CELLS = (42490, 12045, 52059)


def _pilot_forcing(cell: int) -> Path:
    return (
        Path(str(paths()["scratch"]["root"]))
        / "forcing"
        / "pilot-v2-constco2"
        / f"c{cell}"
        / "control"
    )


def _have_real() -> bool:
    try:
        return (
            Path(str(paths()["inputs"]["historical"]["tas"])).exists()
            and _pilot_forcing(PILOT_CELLS[0]).is_dir()
        )
    except KeyError:
        return False


real = pytest.mark.skipif(not _have_real(), reason="needs the cluster inputs and the pilot forcing")


@real
@pytest.mark.needs_real_data
@pytest.mark.parametrize("cell", PILOT_CELLS)
def test_historical_reproduces_the_pilot_control_forcing_byte_identically(
    cell: int, tmp_path: Path
) -> None:
    rec = scenario.write_cell_window("historical", cell, tmp_path)
    for var in scenario.VARS:
        name = scenario.FORCING_NAME[var]
        assert (tmp_path / name).read_bytes() == (_pilot_forcing(cell) / name).read_bytes(), var
        assert rec[var]["verbatim"]


@real
@pytest.mark.needs_real_data
@pytest.mark.parametrize("leg", ["ssp126", "ssp370"])
def test_real_scenario_decodes_to_source_times_scale(leg: str, tmp_path: Path) -> None:
    src = scenario.source_files(leg)
    for cell in (42490, 12045):
        scenario.write_cell_window(leg, cell, tmp_path / f"c{cell}")
        for var in scenario.VARS:
            out = tmp_path / f"c{cell}" / scenario.FORCING_NAME[var]
            assert scenario.decoded_matches_source(
                out, src[var], cell, scenario.TRUTH_WINDOWS[leg], 1970
            ), (leg, var)
            assert (
                out.stat().st_size
                == (_pilot_forcing(cell) / scenario.FORCING_NAME[var]).stat().st_size
            )
