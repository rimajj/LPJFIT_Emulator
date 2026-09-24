"""The soil-texture columns: the model's own numbers, the sealed experiment's own values, and NaN.

What each test protects, in order of what a break would cost:

* `test_climate_features_are_frozen` -- sealed pre-registrations name the 86 climate columns and
  their leakage assertions are written against that tuple. Soil goes in as NEW names; if anyone
  appends to `CLIMATE_FEATURES` instead, this fails before a sealed experiment silently changes.
* `test_library_equals_the_sealed_experiments_join` -- `X-20260923-equilibrium-from-climate` joins
  these columns at read time through `scripts/screen_d95max.py`. A library that disagreed with it
  by one bit would make a corpus-carried column a different input under the same name.
* `test_every_code_matches_the_model_files` -- the per-code values are a TRANSCRIPTION. This reads
  the model's own `par/soil.js` and `par/soil_20m.js` through `cpp -P` (they `#include` the id
  macros) and the ground truth's saved `soilmap`, and pins every value. It is what caught code 13:
  the screen transcribed it as "clay (light)"; the model maps it to "rock and ice".
* `test_unknown_and_rock_codes_are_nan_never_zero` -- a zero would read as "holds no water".
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from vegemu.corpus import climate
from vegemu.corpus.soil import (
    NOT_A_TEXTURE,
    SOIL_FEATURES,
    SOILMAP,
    SOILPAR,
    code_table,
    soil_codes,
    soil_columns,
)
from vegemu.paths import path, paths

ROOT = Path(__file__).resolve().parent.parent

# sha256 of "\n".join(CLIMATE_FEATURES) at commit cf11a5c, the tuple every sealed experiment names.
FROZEN_CLIMATE_FEATURES_SHA256 = "ee34635160336d6de8ca9c8ef5c02fc914a1bf26e24c9db370f690391f8d392a"


def test_climate_features_are_frozen() -> None:
    names = climate.CLIMATE_FEATURES
    assert len(names) == 86
    assert hashlib.sha256("\n".join(names).encode()).hexdigest() == FROZEN_CLIMATE_FEATURES_SHA256


def test_v3_features_are_the_frozen_86_then_the_five_soil_columns() -> None:
    assert (*climate.CLIMATE_FEATURES, *SOIL_FEATURES) == climate.CLIMATE_FEATURES_V3
    assert SOIL_FEATURES == ("soil_code", "soil_awc", "soil_w_avail", "soil_sand", "soil_clay")
    assert not set(SOIL_FEATURES) & set(climate.CLIMATE_FEATURES)


def test_features_follow_the_schema() -> None:
    assert climate.climate_features(2) == climate.CLIMATE_FEATURES
    assert climate.climate_features(3) == climate.CLIMATE_FEATURES_V3
    with pytest.raises(ValueError, match="unknown corpus schema"):
        climate.climate_features(7)


def test_unknown_and_rock_codes_are_nan_never_zero() -> None:
    table = code_table()
    assert table.shape == (256, 4)
    # code 0 is `null` in the soilmap (the model skips the cell); 14..255 are past its end
    for code in (0, 14, 200, 255):
        assert np.isnan(table[code, :3]).all()
        assert table[code, 3] == 0.0
    rock = SOILMAP.index("rock and ice")
    assert rock == 13
    assert np.isnan(table[rock, :3]).all(), "rock and ice is not a texture"
    assert table[rock, 3] == 1.0, "but it is a valid code, so the category survives"


def test_known_codes_carry_their_soilpar_row() -> None:
    table = code_table()
    for code, name in enumerate(SOILMAP):
        if name is None or name in NOT_A_TEXTURE:
            continue
        par = SOILPAR[name]
        assert table[code, 0] == par.w_fc - par.w_pwp
        assert (table[code, 1], table[code, 2]) == (par.sand, par.clay)


def test_soil_columns_on_a_synthetic_soil_file(tmp_path: Path) -> None:
    codes = np.array([0, 1, 12, 13, 7, 99], dtype=np.uint8)
    f = tmp_path / "soil.bin"
    codes.tofile(f)
    depth = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    cols = soil_columns(np.arange(6), depth, soil_bin=str(f))
    assert tuple(cols) == SOIL_FEATURES
    assert np.array_equal(cols["soil_code"], [np.nan, 1, 12, 13, 7, np.nan], equal_nan=True)
    clay, sand, loam = SOILPAR["clay"], SOILPAR["sand"], SOILPAR["loam"]
    want_avail = [np.nan, clay.w_avail, sand.w_avail, np.nan, loam.w_avail, np.nan]
    assert np.array_equal(cols["soil_w_avail"], want_avail, equal_nan=True)
    assert np.array_equal(cols["soil_awc"], depth * np.array(want_avail), equal_nan=True)
    assert np.isnan(cols["soil_sand"][[0, 3, 5]]).all()
    assert cols["soil_clay"][1] == clay.clay


def test_soil_columns_refuse_mismatched_or_out_of_range_input(tmp_path: Path) -> None:
    f = tmp_path / "soil.bin"
    np.array([1, 2, 3], dtype=np.uint8).tofile(f)
    with pytest.raises(ValueError, match="soil depths"):
        soil_columns([0, 1], np.array([1.0]), soil_bin=str(f))
    with pytest.raises(ValueError, match="soil file holds 3"):
        soil_columns([5], np.array([1.0]), soil_bin=str(f))


# ------------------------------------------------------------------------------------------------
# Real files
# ------------------------------------------------------------------------------------------------


def _lpjroot() -> Path | None:
    try:
        root = path("lpjml.lpjroot")
    except (KeyError, TypeError):
        return None
    return root if (root / "par" / "soil.js").is_file() else None


def _soilpar_from(par_file: Path) -> list[dict[str, object]]:
    """A `par/soil*.js` file's `soilpar` array, as the model's preprocessor sees it."""
    out = subprocess.run(
        ["cpp", "-P", f"-I{par_file.parent.parent / 'include'}", str(par_file)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # `200.` is a valid number to the model's parser and not to JSON.
    out = re.sub(r"(\d)\.(?!\d)", r"\1.0", out)
    rows = json.loads("{" + out.strip().rstrip(",") + "}")["soilpar"]
    assert isinstance(rows, list)
    return rows


@pytest.mark.needs_real_data
@pytest.mark.skipif(_lpjroot() is None or shutil.which("cpp") is None, reason="needs LPJROOT, cpp")
@pytest.mark.parametrize("par_name", ["soil.js", "soil_20m.js"])
def test_every_code_matches_the_model_files(par_name: str) -> None:
    root = _lpjroot()
    assert root is not None
    rows = {str(r["name"]): r for r in _soilpar_from(root / "par" / par_name)}
    assert set(rows) == set(SOILPAR), "a soil type was added or renamed in the model's table"
    for name, par in SOILPAR.items():
        r = rows[name]
        got = (r["w_pwp"], r["w_fc"], r["sand"], r["clay"])
        assert got == (par.w_pwp, par.w_fc, par.sand, par.clay), f"{par_name}: {name}"
    # ...and the id each row carries is its position, which is what `soilmap` indexes (+1).
    assert [int(str(r["id"])) for r in rows.values()] == list(range(len(rows)))


@pytest.mark.needs_real_data
def test_soilmap_is_the_ground_truths_own() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from corpus_spinup_config import SAVED_INPUT  # noqa: PLC0415 -- a script, on sys.path only here

    saved = path("ground_truth.historical_seed1") / SAVED_INPUT
    if not saved.is_file():
        pytest.skip("the ground truth's saved input list is not mounted")
    text = saved.read_text(encoding="utf-8")
    m = re.search(r'"soilmap"\s*:\s*\[(.*?)\]', text, re.S)
    assert m is not None
    entries = [e.strip() for e in m.group(1).split(",")]
    got = tuple(None if e == "null" else e.strip('"') for e in entries)
    assert got == SOILMAP


def _pilot_cells() -> np.ndarray | None:
    f = Path(str(paths()["scratch"]["corpus"])) / "pilot-v2-constco2" / "cells.csv"
    if not f.is_file():
        return None
    return np.asarray(pl.read_csv(f)["cell"].to_numpy(), dtype=np.int64)


@pytest.mark.needs_real_data
def test_library_equals_the_sealed_experiments_join() -> None:
    """The five columns, for the 200 pilot cells, exactly as `exp_equilibrium_map.load` built them.

    That function calls `screen_d95max.soil_columns` for four and reads the raw code for the fifth,
    so both are reproduced here and compared BITWISE, NaN for NaN.
    """
    cells = _pilot_cells()
    if cells is None:
        pytest.skip("pilot-v2-constco2 is not on disk")
    sys.path.insert(0, str(ROOT / "scripts"))
    from screen_d95max import soil_columns as screen_soil_columns  # noqa: PLC0415 -- pulls lightgbm

    soil_bin = Path(str(paths()["inputs"]["soil"]))
    depth, _ = climate._static_inputs(
        str(paths()["inputs"]["soildepth"]), str(paths()["inputs"]["coord"])
    )
    d = depth[cells]
    ref = screen_soil_columns(cells, soil_bin, d)
    lib = soil_columns(cells, d)
    for i, name in enumerate(SOIL_FEATURES[1:]):
        assert np.array_equal(lib[name], ref[:, i], equal_nan=True), name
    raw = np.fromfile(soil_bin, dtype=np.uint8)[cells].astype(np.float64)
    assert np.array_equal(lib["soil_code"], raw)
    assert not (soil_codes()[cells] == SOILMAP.index("rock and ice")).any(), (
        "a pilot cell carries code 13, where the screen and the library disagree"
    )
