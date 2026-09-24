"""Per-cell soil texture, read from the model's own soil input — five emulator inputs.

WHY THESE EXIST. The spin-up reads two soil inputs per cell and holds both fixed for all 1000
years: a depth (already the `soildepth` climate feature) and a TEXTURE CODE, which picks the row
of `soilpar` the model's water balance runs on. Rooting depth is selected by how much water the
column holds, and that is depth x texture; depth alone was measured to leave 2.5-3.0 % of the
rooting-depth residual on the table (`20260910-T-rooting-depth-route-2-is-small-*.md`). The sealed
equilibrium experiment (`X-20260923-equilibrium-from-climate`) joins these five columns at read
time through `scripts/screen_d95max.py`; this module is the library form of the same numbers, so a
corpus version can carry them.

    soil_code     the code stored in `soil_code_test.soil.bin`, as a float
    soil_awc      soildepth x (w_fc - w_pwp): plant-available water capacity, in METRES of water
    soil_w_avail  w_fc - w_pwp: the available fraction of the column's volume
    soil_sand     sand fraction
    soil_clay     clay fraction

⚠ `soil_awc` IS IN METRES, NOT MILLIMETRES. The soil-depth input is in metres (the model reads it
as `soildepth (m)`, `celldata.c:223`; the pilot's 200 cells span 0.26-50), and the sealed
experiment multiplies it by the fraction as it stands. The column keeps those units so it equals
the experiment's value to the last bit; x1000 is millimetres. A monotone rescaling is invisible to
a tree model, which is why nothing broke -- but a number quoted in "mm" from it would be 1000x off.

HOW A CODE BECOMES A ROW. Not by position. The model maps the file's code through the `soilmap` of
its input list (`fscansoilmap.c`: `soilmap[code] = index of that name in soilpar + 1`), and the
corpus runs use the ground truth's own saved input list, whose map is `SOILMAP` below. So code 12
is "sand" and code 13 is "rock and ice"; the soilpar row "clay (light)" is never used.

⚠ `screen_d95max.SOILPAR` TRANSCRIBES CODE 13 AS "clay (light)", and the model says "rock and
ice". It does not touch the sealed result -- none of the 200 pilot cells carries code 13 -- but
3,180 of the 67,420 grid cells do, so a corpus drawn wider than the pilot would inherit it. Here
code 13 is NaN in every physical column (below), and the test pins the transcription against the
model's own files read through `cpp -P`, both `par/soil.js` and the `par/soil_20m.js` the config
actually includes.

⚠ NaN, NEVER 0, FOR ANYTHING THAT IS NOT A SOIL. A code the map does not name (0, or past its end)
is NaN in all five columns: a zero would read as "holds no water at all", which is a claim about a
place, not the absence of one. Rock and ice is NaN in the four PHYSICAL columns but keeps its code,
13, so the category is not lost -- a tree model can still split on it. Its own soilpar row
(w_fc - w_pwp = 0.0049) is the model's placeholder for bare rock and is deliberately not passed on
as if it were a texture.

Fork-safe: numpy and file I/O only, like `vegemu.corpus.climate.climate_columns`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.paths import paths

SOIL_FEATURES: tuple[str, ...] = (
    "soil_code",
    "soil_awc",
    "soil_w_avail",
    "soil_sand",
    "soil_clay",
)


@dataclass(frozen=True)
class SoilPar:
    """The four fields of one `soilpar` row this module uses, as the parameter file states them."""

    w_pwp: float
    w_fc: float
    sand: float
    clay: float

    @property
    def w_avail(self) -> float:
        # `w_fc - w_pwp` in that order and in Python floats, which is exactly what the sealed
        # experiment computes -- so the two agree bitwise, not merely to rounding.
        return self.w_fc - self.w_pwp


# `par/soil_20m.js` (the file `param_lpjmlfit.js` includes) and `par/soil.js`, which agree on every
# field used here; `tests/test_soil.py` re-reads both through `cpp -P` and pins every value.
SOILPAR: dict[str, SoilPar] = {
    "clay": SoilPar(0.284, 0.398, 0.22, 0.58),
    "silty clay": SoilPar(0.259, 0.378, 0.06, 0.47),
    "sandy clay": SoilPar(0.205, 0.295, 0.52, 0.42),
    "clay loam": SoilPar(0.214, 0.345, 0.32, 0.34),
    "silty clay loam": SoilPar(0.247, 0.387, 0.10, 0.34),
    "sandy clay loam": SoilPar(0.143, 0.256, 0.58, 0.27),
    "loam": SoilPar(0.139, 0.292, 0.43, 0.18),
    "silt loam": SoilPar(0.177, 0.368, 0.17, 0.13),
    "sandy loam": SoilPar(0.100, 0.228, 0.58, 0.10),
    "silt": SoilPar(0.177, 0.368, 0.10, 0.30),
    "loamy sand": SoilPar(0.060, 0.149, 0.82, 0.06),
    "sand": SoilPar(0.022, 0.088, 0.92, 0.03),
    "clay (light)": SoilPar(0.284, 0.398, 0.24, 0.48),
    "rock and ice": SoilPar(0.0001, 0.005, 0.99, 0.01),
}

# The `soilmap` of the ground truth's saved input list (`input_2000_2019.js`), which every corpus
# config includes unchanged: index = the code in the soil file, `None` = a cell the model skips.
SOILMAP: tuple[str | None, ...] = (
    None,
    "clay",
    "silty clay",
    "sandy clay",
    "clay loam",
    "silty clay loam",
    "sandy clay loam",
    "loam",
    "silt loam",
    "sandy loam",
    "silt",
    "loamy sand",
    "sand",
    "rock and ice",
)

# Soil types that are not a texture: they keep their code but carry NaN in the physical columns.
NOT_A_TEXTURE: frozenset[str] = frozenset({"rock and ice"})


def code_table() -> npt.NDArray[np.float64]:
    """(256, 4) per-code (w_avail, sand, clay, is_valid_code); NaN rows for every unusable code.

    256 rows because the file is one unsigned byte per cell, so every value it can hold has a row
    and a lookup can never index out of range -- an unknown code simply lands on a NaN row.
    """
    out = np.full((256, 4), np.nan)
    out[:, 3] = 0.0
    for code, name in enumerate(SOILMAP):
        if name is None:
            continue
        out[code, 3] = 1.0
        if name in NOT_A_TEXTURE:
            continue
        par = SOILPAR[name]
        out[code, :3] = (par.w_avail, par.sand, par.clay)
    return out


@lru_cache(maxsize=4)
def soil_codes(soil_bin: str | None = None) -> npt.NDArray[np.uint8]:
    """Every global cell's soil code: one unsigned byte per cell, no header, in grid order.

    Cached for the reason `climate._static_inputs` is: a corpus decode asks once per RUN, and the
    file does not depend on the run. Callers only read the array.
    """
    src = soil_bin or str(paths()["inputs"]["soil"])
    return np.fromfile(src, dtype=np.uint8)


def soil_columns(
    cells: Sequence[int] | npt.NDArray[np.integer[Any]],
    soildepth: npt.NDArray[np.float64],
    soil_bin: str | None = None,
) -> dict[str, npt.NDArray[np.float64]]:
    """The five `SOIL_FEATURES` for GLOBAL cell indices `cells`, given each cell's soil depth.

    `soildepth` is the `soildepth` climate feature of the same rows, in the input's own units
    (metres); it is taken rather than re-read so the two can never describe different cells.
    """
    gsel = np.asarray(cells, dtype=np.int64)
    depth = np.asarray(soildepth, dtype=np.float64)
    if depth.shape != gsel.shape:
        raise ValueError(f"{gsel.size} cells but {depth.size} soil depths")
    codes = soil_codes(soil_bin)
    if gsel.size and (gsel.min() < 0 or gsel.max() >= codes.size):
        raise ValueError(
            f"cells {int(gsel.min())}..{int(gsel.max())} but the soil file holds {codes.size}"
        )
    code = codes[gsel].astype(np.int64)
    table = code_table()[code]
    w_avail = table[:, 0]
    return {
        "soil_code": np.where(table[:, 3] > 0, code.astype(np.float64), np.nan),
        "soil_awc": depth * w_avail,
        "soil_w_avail": w_avail,
        "soil_sand": table[:, 1],
        "soil_clay": table[:, 2],
    }
