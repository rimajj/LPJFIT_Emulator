"""Per-cell climate summaries out of the `.clm` forcing — the emulator's inputs.

THE ESTIMAND THIS SERVES. The emulator is a direct map from a climate summary to a state. So the
input is a 30-year window of climate ending at the year the state was written, reduced to
per-cell statistics: annual level, monthly climatology, seasonality, and interannual variability.
No lagged state, no year index, no cell identity.

⚠ WHAT IS DELIBERATELY ABSENT
* **CO2.** The emulator does not see it and must not respond to it. LPJmL-FIT runs constant CO2 on
  purpose -- with nitrogen limitation off its CO2 fertilization is unbounded -- so having no CO2
  response is faithfulness, not a gap (`MEMORY.md:co2-closed`). Standing owner decision.
* **latitude and longitude.** They are computed here and stored, but they are NOT features: the
  geographic address is one of the pre-registered NULLS. A feature set that quietly contains the
  address turns any per-cell score into a spatial-interpolation score.
* **any lagged or initial state.** Cross-validation by cell holds out SPACE, not TIME, so a lagged
  truth feature would make the score one-step teacher-forced and it would still look excellent.

WINDOW LENGTH. 30 years, matching `nspinyear` -- the spin-up cycles exactly 30 forcing years, so a
30-year window is the natural climate a state is in equilibrium with, and it is long enough for the
interannual-variability features to mean something.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.clm import ClmReader, read_grid
from vegemu.paths import paths

NDAYYEAR = 365  # noleap
NMONTH = 12
# Day-of-year boundaries of each month in a 365-day noleap year.
MONTH_LEN: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
MONTH_START: tuple[int, ...] = tuple(int(x) for x in np.cumsum((0, *MONTH_LEN[:-1])))

VARS: tuple[str, ...] = ("tas", "pr", "rsds", "lwnet", "huss")
# Variables whose annual aggregate is a SUM rather than a mean. Getting this wrong turns
# precipitation into a meaningless per-day average that still correlates with the truth.
SUM_VARS: frozenset[str] = frozenset({"pr"})


@dataclass(frozen=True)
class Window:
    """A forcing leg and the 30 years of it that a state is being explained by."""

    leg: str
    first: int
    last: int
    state_year: int

    @property
    def nyear(self) -> int:
        return self.last - self.first + 1

    def describe(self) -> str:
        return f"{self.leg} {self.first}-{self.last} -> state at {self.state_year}"


# The three legs available. `historical` explains `restart_1999`; the two scenario legs explain
# their own `restart_2100`, and the CONTRAST between them is the response test -- same cell, same
# history to 2019, two different climates. That contrast is the one thing the predecessor could not
# construct from its data (`docs/reference/inherited.md` §2).
WINDOWS: dict[str, Window] = {
    "historical": Window("historical", 1970, 1999, 1999),
    "ssp370": Window("ssp370", 2071, 2100, 2100),
    "ssp126": Window("ssp126", 2071, 2100, 2100),
}


def _feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for var in VARS:
        names += [f"{var}_ann", f"{var}_iav"]
        names += [f"{var}_m{m + 1:02d}" for m in range(NMONTH)]
    names += [
        "tas_coldest_month",
        "tas_warmest_month",
        "tas_seasonal_range",
        "gdd5",
        "gdd0",
        "frost_days",
        "pr_wettest_month",
        "pr_driest_month",
        "pr_seasonality",
        "dry_months",
        "vpd_ann",
        "vpd_warm_quarter",
        "aridity",
        "tas_warm_quarter",
        "pr_warm_quarter",
        "soildepth",
    ]
    return tuple(names)


CLIMATE_FEATURES: tuple[str, ...] = _feature_names()

# Stored beside the features but NEVER given to a model: these are the nulls and the fold keys.
NON_FEATURE_COLUMNS: tuple[str, ...] = ("cell", "lon", "lat", "leg", "state_year")


def _saturation_vapour_pressure(temp_c: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Tetens, in Pa. Used only to turn specific humidity into a vapour-pressure deficit."""
    return 610.78 * np.exp(17.269 * temp_c / (temp_c + 237.3))


def _vpd(temp_c: npt.NDArray[np.float64], huss: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Vapour-pressure deficit in Pa from temperature and specific humidity, at sea-level pressure.

    Approximate by construction -- no surface-pressure input exists in this forcing set -- but it is
    a monotone function of the actual deficit, which is all a learned map needs. Recorded as
    approximate rather than quietly labelled "VPD".
    """
    pressure = 101_325.0
    vapour = huss * pressure / (0.622 + 0.378 * huss)
    return np.maximum(_saturation_vapour_pressure(temp_c) - vapour, 0.0)


def _monthly(daily: npt.NDArray[np.float64], reduce_sum: bool) -> npt.NDArray[np.float64]:
    """(ncell, 365) -> (ncell, 12), summing or averaging within each month."""
    out = np.empty((daily.shape[0], NMONTH), dtype=np.float64)
    for m in range(NMONTH):
        block = daily[:, MONTH_START[m] : MONTH_START[m] + MONTH_LEN[m]]
        out[:, m] = block.sum(axis=1) if reduce_sum else block.mean(axis=1)
    return out


@lru_cache(maxsize=4)
def _static_inputs(
    soildepth: str, coord: str
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Soil depth and the grid coordinate for every global cell, read once per process.

    Cached because the pilot corpus calls `climate_table` once per RUN -- 6,000 single-cell forcing
    sets -- and both of these are whole-globe files that do not depend on the run at all. Without
    the cache that is 6,000 re-reads of the same 67,420-cell arrays to answer the same question.
    Callers only read the arrays; nothing here writes to them.
    """
    depth = ClmReader(soildepth)
    with depth:
        soil = np.asarray(depth.year(depth.header.firstyear)[:, 0], dtype=np.float64)
    return soil, read_grid(coord)


def climate_columns(  # noqa: PLR0915 -- a flat sequence of independent feature definitions
    window: Window,
    cells: Sequence[int] | None = None,
    files: dict[str, str] | None = None,
    soildepth: str | None = None,
    coord: str | None = None,
) -> dict[str, npt.NDArray[Any]]:
    """Reduce one leg's 30-year window to one row per cell, as plain arrays.

    Reads a whole year block per variable per year -- 150 sequential reads for the window -- and
    accumulates. That is the cheap direction: the file is laid out `value[year][cell][band]`, so a
    year is contiguous and a cell is not.

    ⚠ THIS IS THE ENTRY POINT A FORKED WORKER MUST CALL, and `climate_table` is not. polars runs a
    Rust thread pool that does not survive `fork`, so a forked child that touches a DataFrame hangs
    forever with no error and no traceback -- the symptom is a job that burns its whole wall-clock
    limit having produced nothing. `vegemu.corpus.state` already keeps to this rule by having its
    workers return dicts and building the frame in the parent; the pilot corpus decodes 6,000 runs
    the same way. Everything here is numpy and file I/O, so it is fork-safe.

    ⚠ `cells` IS ALWAYS A GLOBAL CELL INDEX, NEVER A ROW NUMBER, and the difference only shows up on
    a subset file. A `.clm` header declares `firstcell`, so the perturbation writer's single-cell
    files carry `firstcell = <that cell>` and hold exactly one row. Row `i` of such a file is global
    cell `firstcell + i`, and the soil depth and the grid coordinate are read from GLOBAL files that
    must be indexed by the global number. Reading them at the row number instead returns cell 0's
    soil depth and cell 0's coordinate, with no error anywhere -- a wrong feature that looks
    entirely normal. Every global input has `firstcell = 0`, so this is a no-op for them and corpus
    v0's tables are byte-unchanged.
    """
    cfg = paths()
    files = files or {v: str(cfg["inputs"][window.leg][v]) for v in VARS}
    soildepth = soildepth or str(cfg["inputs"]["soildepth"])
    coord = coord or str(cfg["inputs"]["coord"])

    readers = {v: ClmReader(files[v]) for v in VARS}
    ncell = readers["tas"].header.ncell
    firstcell = readers["tas"].header.firstcell
    for var, reader in readers.items():
        if reader.header.ncell != ncell:
            raise ValueError(f"{var} has ncell={reader.header.ncell}, tas has {ncell}")
        if reader.header.firstcell != firstcell:
            raise ValueError(
                f"{var} starts at cell {reader.header.firstcell}, tas at {firstcell}. The five "
                "variables do not describe the same cells, so every row would mix two places."
            )
        if reader.header.nbands != NDAYYEAR:
            raise ValueError(
                f"{var} has nbands={reader.header.nbands}, expected {NDAYYEAR} (daily)"
            )

    # `gsel` numbers cells globally, `sel` numbers rows within these files. They differ by
    # `firstcell` and are the same array for every global input.
    gsel = (
        np.arange(firstcell, firstcell + ncell)
        if cells is None
        else np.asarray(cells, dtype=np.int64)
    )
    sel = gsel - firstcell
    if sel.size and (sel.min() < 0 or sel.max() >= ncell):
        raise ValueError(
            f"requested cells {int(gsel.min())}..{int(gsel.max())} but these files hold "
            f"{firstcell}..{firstcell + ncell - 1}"
        )
    n = sel.size
    ny = window.nyear

    monthly = {v: np.zeros((n, NMONTH), dtype=np.float64) for v in VARS}
    annual_by_year = {v: np.empty((n, ny), dtype=np.float64) for v in VARS}
    gdd5 = np.zeros(n)
    gdd0 = np.zeros(n)
    frost = np.zeros(n)
    vpd_monthly = np.zeros((n, NMONTH), dtype=np.float64)

    opened = {v: r.__enter__() for v, r in readers.items()}
    try:
        for iy, year in enumerate(range(window.first, window.last + 1)):
            daily: dict[str, npt.NDArray[np.float64]] = {}
            for var in VARS:
                block = opened[var].year(year)
                daily[var] = block[sel] if cells is not None else block
                is_sum = var in SUM_VARS
                monthly[var] += _monthly(daily[var], is_sum)
                annual_by_year[var][:, iy] = (
                    daily[var].sum(axis=1) if is_sum else daily[var].mean(axis=1)
                )
            temp = daily["tas"]
            gdd5 += np.maximum(temp - 5.0, 0.0).sum(axis=1)
            gdd0 += np.maximum(temp, 0.0).sum(axis=1)
            frost += (temp < 0.0).sum(axis=1)
            vpd_monthly += _monthly(_vpd(temp, daily["huss"]), reduce_sum=False)
    finally:
        for v, r in readers.items():
            r.__exit__(None, None, None)
            del v

    for var in VARS:
        monthly[var] /= ny
    vpd_monthly /= ny
    gdd5 /= ny
    gdd0 /= ny
    frost /= ny

    cols: dict[str, npt.NDArray[Any]] = {}
    for var in VARS:
        cols[f"{var}_ann"] = annual_by_year[var].mean(axis=1)
        cols[f"{var}_iav"] = annual_by_year[var].std(axis=1, ddof=1)
        for m in range(NMONTH):
            cols[f"{var}_m{m + 1:02d}"] = monthly[var][:, m]

    tmon = monthly["tas"]
    pmon = monthly["pr"]
    cols["tas_coldest_month"] = tmon.min(axis=1)
    cols["tas_warmest_month"] = tmon.max(axis=1)
    cols["tas_seasonal_range"] = tmon.max(axis=1) - tmon.min(axis=1)
    cols["gdd5"] = gdd5
    cols["gdd0"] = gdd0
    cols["frost_days"] = frost
    cols["pr_wettest_month"] = pmon.max(axis=1)
    cols["pr_driest_month"] = pmon.min(axis=1)
    annual_pr = pmon.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cols["pr_seasonality"] = np.where(
            annual_pr > 0, pmon.std(axis=1, ddof=1) / (annual_pr / NMONTH), 0.0
        )
    cols["dry_months"] = (pmon < 30.0).sum(axis=1).astype(np.float64)
    cols["vpd_ann"] = vpd_monthly.mean(axis=1)

    # The warmest consecutive three months (cyclic), which is the growing season for most of the
    # tree-bearing domain and a far better predictor than an annual mean at high latitudes.
    tri_t = np.stack([tmon[:, np.arange(m, m + 3) % NMONTH].mean(axis=1) for m in range(NMONTH)], 1)
    warm = tri_t.argmax(axis=1)
    idx = (warm[:, None] + np.arange(3)[None, :]) % NMONTH
    rows = np.arange(n)[:, None]
    cols["tas_warm_quarter"] = tmon[rows, idx].mean(axis=1)
    cols["pr_warm_quarter"] = pmon[rows, idx].sum(axis=1)
    cols["vpd_warm_quarter"] = vpd_monthly[rows, idx].mean(axis=1)

    # A dimensionless water-supply index. Priestley-Taylor-flavoured: net radiation converted to an
    # evaporative equivalent, so it is a ratio and not a level.
    latent = 2.45e6  # J/kg
    pet = np.maximum(cols["rsds_ann"], 0.0) * 86400.0 / latent * 365.0
    with np.errstate(divide="ignore", invalid="ignore"):
        cols["aridity"] = np.where(pet > 0, annual_pr / pet, 0.0)

    soil, grid = _static_inputs(soildepth, coord)
    cols["soildepth"] = soil[gsel]

    return {
        "cell": gsel.astype(np.int32),
        "lon": grid[gsel, 0],
        "lat": grid[gsel, 1],
        "leg": np.full(n, window.leg),
        "state_year": np.full(n, window.state_year, dtype=np.int32),
        **{k: v.astype(np.float64) for k, v in cols.items()},
    }


def climate_table(
    window: Window,
    cells: Sequence[int] | None = None,
    files: dict[str, str] | None = None,
    soildepth: str | None = None,
    coord: str | None = None,
) -> pl.DataFrame:
    """`climate_columns` as a table, in the fixed column order. Call this in the PARENT only."""
    cols = climate_columns(window, cells=cells, files=files, soildepth=soildepth, coord=coord)
    return pl.DataFrame(cols).select([*NON_FEATURE_COLUMNS, *CLIMATE_FEATURES])


def basis(window: Window, files: dict[str, str] | None = None) -> dict[str, Any]:
    """The reference basis of a climate table: which files, which version, which scalar.

    The version and scalar are in here because the input set is MIXED -- v3 float32 for historic,
    v2 int16 with scalar 0.1 for the scenario legs' tas/pr/rsds/lwnet -- and a table built with one
    hardcoded dtype would look entirely normal.
    """
    cfg = paths()
    files = files or {v: str(cfg["inputs"][window.leg][v]) for v in VARS}
    return {
        "leg": window.leg,
        "window": [window.first, window.last],
        "state_year": window.state_year,
        "nyear": window.nyear,
        "co2": "constant by design; NOT a feature (MEMORY.md:co2-closed)",
        "files": {
            var: {
                "path": files[var],
                "header": ClmReader(files[var]).header.describe(),
                "bytes": Path(files[var]).stat().st_size,
            }
            for var in VARS
        },
    }
