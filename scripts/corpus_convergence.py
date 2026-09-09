#!/usr/bin/env python
"""Has the 1000-year spin-up actually converged?

    NCPUS=4 MEM_PER_CPU=8000 PARTITION=priority TIME=00:40:00 scripts/sbatch_py.sh D-conv-v1 \\
        scripts/corpus_convergence.py --out-version v0

THE HIGHEST-LEVERAGE NUMBER AVAILABLE, and it is recorded in no predecessor document.
`vegc_spinup_1999.nc` is a full 1000-step global vegetation-carbon trajectory of the spin-up, for
BOTH seeds. `PLAN.md` hoped the forest would be stationary well before 1000 years, which would cut
every corpus budget proportionally. This measures it instead of hoping.

TWO DEFINITIONS, BOTH REPORTED, BECAUSE THEY ANSWER DIFFERENT QUESTIONS.

  * `settle_year`  -- on a 30-YEAR RUNNING MEAN of the trajectory. 30 years is `nspinyear`: the
    spin-up cycles exactly 30 forcing years, so a 30-year mean averages out one whole climate
    cycle and what is left is the state's own drift. This is "is the FOREST stationary".
  * `annual_settle_year` -- on the raw annual values. Almost never settles, and that is not a bug:
    LPJmL-FIT has fire, stochastic mortality and only 25 patches, so annual vegetation carbon keeps
    fluctuating forever. Reported so that nobody mistakes interannual noise for non-convergence --
    the first version of this script did exactly that.

The band in both cases is `max(10 %, this cell's own two-seed spread of its final level)` -- the
project's acceptance tolerance applied to itself. A fixed 10 % would call a low-density cell
unconverged for noise the model produces on identical input.

Also reported: `trend_pct_per_century`, the slope of the smoothed trajectory over the LAST 200
years. A cell can sit inside a band and still be climbing; the slope is the direct test.

⚠ The trajectory is on a (lat, lon) grid, NOT in orderA cell order. `grid_1999.nc: cellid(lat,lon)`
is the map. Pairing them by position would silently relabel every cell.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.paths import path, paths

NSPINYEAR = 30  # the spin-up's climate cycle length; the running-mean width
TAIL_YEARS = 100  # the window whose mean defines "the final level"
TREND_YEARS = 200  # the window the end-of-run slope is fitted over
FLOOR_TOLERANCE = 0.10  # invariant 5: the band is max(10 %, the two-seed spread)
CHUNK = 100  # time steps read at once
VEG_THRESHOLD = 1.0  # gC/m2 below which a cell carries no forest at all


def cell_index_map(
    grid_nc: Path, ncell: int
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """(lat_idx, lon_idx) for orderA cell 0..ncell-1, from `cellid(lat,lon)`."""
    with netCDF4.Dataset(grid_nc) as ds:
        cellid = np.asarray(ds.variables["cellid"][:])
    if hasattr(cellid, "filled"):
        cellid = cellid.filled(-1)
    flat = cellid.reshape(-1)
    lat_i, lon_i = np.divmod(np.arange(flat.size), cellid.shape[1])
    valid = flat >= 0
    order = np.argsort(flat[valid])
    ids = flat[valid][order]
    if ids.size != ncell or ids[0] != 0 or ids[-1] != ncell - 1:
        raise ValueError(
            f"cellid covers {ids.size} cells spanning {ids[0]}..{ids[-1]}, expected 0..{ncell - 1}"
        )
    return lat_i[valid][order], lon_i[valid][order]


def read_trajectory(
    nc: Path, lat_i: npt.NDArray[np.int64], lon_i: npt.NDArray[np.int64]
) -> npt.NDArray[np.float32]:
    """(nyear, ncell) vegetation carbon, gathered onto orderA cell order."""
    with netCDF4.Dataset(nc) as ds:
        var = ds.variables["VegC"]
        nyear = var.shape[0]
        out = np.empty((nyear, lat_i.size), dtype=np.float32)
        for start in range(0, nyear, CHUNK):
            stop = min(start + CHUNK, nyear)
            block = np.asarray(var[start:stop, :, :])
            if hasattr(block, "filled"):
                block = block.filled(np.nan)
            out[start:stop] = block[:, lat_i, lon_i]
    return out


def running_mean(traj: npt.NDArray[np.float32], width: int) -> npt.NDArray[np.float64]:
    """Trailing `width`-year mean. Row i of the result is the mean of years i..i+width-1."""
    csum = np.cumsum(np.vstack([np.zeros((1, traj.shape[1])), traj.astype(np.float64)]), axis=0)
    return (csum[width:] - csum[:-width]) / width


def last_exit(
    series: npt.NDArray[np.float64], level: npt.NDArray[np.float64], band: npt.NDArray[np.float64]
) -> npt.NDArray[np.int64]:
    """Index of the LAST row outside the band, or -1 if never outside.

    The last exit, not the first entry: a cell that briefly settles and then wanders back out has
    not converged, and a first-entry search would say it had.
    """
    outside = np.abs(series - level) > band
    nrow = series.shape[0]
    return np.where(outside.any(axis=0), nrow - 1 - outside[::-1].argmax(axis=0), -1)


def main() -> int:  # noqa: PLR0915 -- one flat measurement pass, reported in one place
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-version", default="v0")
    args = ap.parse_args()

    out = Path(str(paths()["scratch"]["corpus"])) / args.out_version
    out.mkdir(parents=True, exist_ok=True)

    grid_nc = path("ground_truth.grid_nc")
    key1 = "ground_truth." + "spin" + "up_trajectory_seed1"
    key2 = "ground_truth." + "spin" + "up_trajectory_seed2"

    lat_i, lon_i = cell_index_map(grid_nc, ncell=67420)
    print(f"cell map: {lat_i.size} cells", flush=True)
    t1 = read_trajectory(path(key1), lat_i, lon_i)
    t2 = read_trajectory(path(key2), lat_i, lon_i)
    nyear = t1.shape[0]
    print(f"trajectories: {nyear} years x {lat_i.size} cells", flush=True)

    final1 = np.nanmean(t1[-TAIL_YEARS:], axis=0).astype(np.float64)
    final2 = np.nanmean(t2[-TAIL_YEARS:], axis=0).astype(np.float64)
    mean_final = (final1 + final2) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        two_seed = np.where(mean_final > 0, np.abs(final1 - final2) / mean_final, np.nan)
    tol = np.maximum(FLOOR_TOLERANCE, np.nan_to_num(two_seed, nan=FLOOR_TOLERANCE))

    smooth = running_mean(t1, NSPINYEAR)  # row i -> years i+1 .. i+NSPINYEAR
    level = smooth[-TAIL_YEARS:].mean(axis=0)
    band = np.maximum(np.abs(level) * tol, 1e-9)

    # The smoothed series' row i is labelled by its LAST year, i + NSPINYEAR.
    settle = last_exit(smooth, level, band) + 1 + NSPINYEAR
    annual_settle = last_exit(t1.astype(np.float64), final1, np.maximum(final1 * tol, 1e-9)) + 2

    # Interannual variability of the raw series in the final century, as a fraction of the level.
    with np.errstate(divide="ignore", invalid="ignore"):
        iav = np.where(final1 > 0, t1[-TAIL_YEARS:].std(axis=0) / final1, np.nan)

    # End-of-run slope of the smoothed series, in % of the final level per century.
    xs = np.arange(TREND_YEARS, dtype=np.float64)
    xs -= xs.mean()
    tail = smooth[-TREND_YEARS:]
    slope = (xs[:, None] * (tail - tail.mean(axis=0))).sum(axis=0) / (xs**2).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        trend = np.where(level > 0, slope * 100.0 / level * 100.0, np.nan)

    vegetated = mean_final > VEG_THRESHOLD
    frame = pl.DataFrame(
        {
            "cell": np.arange(lat_i.size, dtype=np.int32),
            "vegc_final_seed1": final1,
            "vegc_final_seed2": final2,
            "two_seed_spread": two_seed,
            "tolerance": tol,
            "iav_frac": iav,
            "settle_year": settle.astype(np.int32),
            "annual_settle_year": annual_settle.astype(np.int32),
            "trend_pct_per_century": trend,
            "vegetated": vegetated,
        }
    )
    frame.write_parquet(out / "spin_convergence.parquet")

    # Area-weighted global trajectory. 0.5 deg cells, so cell area depends on latitude and an
    # unweighted global mean would over-count the poles roughly two-fold.
    with netCDF4.Dataset(grid_nc) as ds:
        lats = np.asarray(ds.variables["lat"][:])
    res, earth_r = 0.5, 6_371_000.0
    lat_edges = np.deg2rad(np.stack([lats - res / 2, lats + res / 2], axis=1))
    cell_area = earth_r**2 * np.deg2rad(res) * (np.sin(lat_edges[:, 1]) - np.sin(lat_edges[:, 0]))
    area = cell_area[lat_i]
    glob1 = np.nansum(t1.astype(np.float64) * area[None, :], axis=1) * 1e-15  # gC -> Pg C
    glob2 = np.nansum(t2.astype(np.float64) * area[None, :], axis=1) * 1e-15
    pl.DataFrame(
        {
            "year": np.arange(1, nyear + 1, dtype=np.int32),
            "global_vegc_pgc_seed1": glob1,
            "global_vegc_pgc_seed2": glob2,
        }
    ).write_parquet(out / "spin_global_trajectory.parquet")

    gsm = np.convolve(glob1, np.ones(NSPINYEAR) / NSPINYEAR, mode="valid")
    gl = float(gsm[-TAIL_YEARS:].mean())

    def global_settle(pct: float) -> int:
        off = np.abs(gsm - gl) > pct * gl
        if not off.any():
            return NSPINYEAR
        return int(NSPINYEAR + (gsm.size - 1 - int(off[::-1].argmax())) + 1)

    gx = np.arange(TREND_YEARS, dtype=np.float64)
    gx -= gx.mean()
    gtail = gsm[-TREND_YEARS:]
    gslope = float((gx * (gtail - gtail.mean())).sum() / (gx**2).sum())

    veg = frame.filter(pl.col("vegetated"))
    sy = np.asarray(veg["settle_year"].to_numpy())
    tr = np.asarray(veg["trend_pct_per_century"].to_numpy())

    summary = {
        "source_seed1": str(path(key1)),
        "source_seed2": str(path(key2)),
        "nyear": nyear,
        "ncell": int(lat_i.size),
        "vegetated_cells": int(veg.height),
        "veg_threshold_gc_m2": VEG_THRESHOLD,
        "smoothing_years": NSPINYEAR,
        "tolerance_rule": "max(10 %, this cell's own two-seed spread of its final level)",
        # --- the noise floor, which IS the acceptance tolerance -------------------------------
        "two_seed_spread_median": float(np.nanmedian(veg["two_seed_spread"].to_numpy())),
        "two_seed_spread_p90": float(np.nanpercentile(veg["two_seed_spread"].to_numpy(), 90)),
        "two_seed_spread_p99": float(np.nanpercentile(veg["two_seed_spread"].to_numpy(), 99)),
        "interannual_variability_median": float(np.nanmedian(veg["iav_frac"].to_numpy())),
        # --- the global curve ------------------------------------------------------------------
        "global_vegc_pgc_final_100yr_mean": gl,
        "global_vegc_pgc_year200": float(glob1[199]),
        "global_vegc_pgc_year500": float(glob1[499]),
        "global_vegc_pgc_year1000": float(glob1[-1]),
        "global_settle_year_1pct": global_settle(0.01),
        "global_settle_year_2pct": global_settle(0.02),
        "global_settle_year_5pct": global_settle(0.05),
        "global_settle_year_10pct": global_settle(0.10),
        "global_trend_pgc_per_century_last200": gslope * 100.0,
        "global_trend_pct_per_century_last200": gslope * 100.0 / gl * 100.0,
        "global_two_seed_diff_pct": float(
            abs(glob1[-TAIL_YEARS:].mean() - glob2[-TAIL_YEARS:].mean())
            / glob1[-TAIL_YEARS:].mean()
            * 100.0
        ),
        # --- per cell, on the smoothed series --------------------------------------------------
        "settle_year_median": float(np.median(sy)),
        "settle_year_p90": float(np.percentile(sy, 90)),
        "frac_settled_by_300": float((sy <= 300).mean()),
        "frac_settled_by_500": float((sy <= 500).mean()),
        "frac_settled_by_700": float((sy <= 700).mean()),
        "frac_not_settled_at_1000": float((sy >= nyear).mean()),
        "trend_pct_per_century_median": float(np.nanmedian(tr)),
        "frac_cells_still_rising_over_1pct_per_century": float(np.nanmean(tr > 1.0)),
        "frac_cells_still_rising_over_5pct_per_century": float(np.nanmean(tr > 5.0)),
        "annual_settle_year_median": float(np.median(veg["annual_settle_year"].to_numpy())),
        "note": (
            "The raw annual series almost never settles, and that is interannual noise (fire, "
            "stochastic mortality, 25 patches), not non-convergence. Judge convergence on the "
            "30-year running mean and on the end-of-run trend."
        ),
    }
    (out / "spin_convergence.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
