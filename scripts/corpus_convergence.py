#!/usr/bin/env python
"""How long does the 1000-year spin-up actually take to converge?

    NCPUS=4 PARTITION=priority TIME=00:40:00 scripts/sbatch_py.sh D-conv-v0 \\
        scripts/corpus_convergence.py --out-version v0

THE HIGHEST-LEVERAGE NUMBER AVAILABLE RIGHT NOW, and it is recorded in no predecessor document.
`vegc_spinup_1999.nc` is a full 1000-step global vegetation-carbon trajectory of the spin-up, for
BOTH seeds. If the forest is stationary well before 1000 years, every corpus budget in `PLAN.md`
drops proportionally -- the pilot tier's 670 core-hours, the full tier's 133,000.

HOW CONVERGENCE IS DEFINED HERE, and why not more simply. A cell is called converged at year `y`
if from `y` onwards its vegetation carbon never again leaves a band around its own final level.
The band is `max(10 %, this cell's own two-seed spread at the end of the spin-up)` -- the project's
acceptance tolerance, applied to itself. Using a fixed 10 % instead would call a low-density cell
"not converged" for noise the model itself produces on identical input, which is the same mistake
as scoring an emulator against a tolerance tighter than the model's own reproducibility.

⚠ The trajectory is on a (lat, lon) grid, NOT in orderA cell order. `grid_1999.nc: cellid(lat,lon)`
is the map. Pairing them by position instead would silently relabel every cell.
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

TAIL_YEARS = 100  # the window whose mean defines "the final level"
FLOOR_TOLERANCE = 0.10  # invariant 5: the band is max(10 %, the two-seed spread)
CHUNK = 100  # time steps read at once


def cell_index_map(grid_nc: Path, ncell: int) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """(lat_idx, lon_idx) for orderA cell 0..ncell-1, from `cellid(lat,lon)`."""
    with netCDF4.Dataset(grid_nc) as ds:
        cellid = np.asarray(ds.variables["cellid"][:])
    if hasattr(cellid, "filled"):
        cellid = cellid.filled(-1)
    flat = cellid.reshape(-1)
    lat_i, lon_i = np.divmod(np.arange(flat.size), cellid.shape[1])
    valid = flat >= 0
    order = np.argsort(flat[valid])
    lat_sorted = lat_i[valid][order]
    lon_sorted = lon_i[valid][order]
    ids = flat[valid][order]
    if ids.size != ncell or ids[0] != 0 or ids[-1] != ncell - 1:
        raise ValueError(
            f"cellid covers {ids.size} cells spanning {ids[0]}..{ids[-1]}, expected 0..{ncell - 1}"
        )
    return lat_sorted, lon_sorted


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
            print(f"  read years {start}-{stop - 1}", flush=True)
    return out


def convergence_year(
    traj: npt.NDArray[np.float32], tol: npt.NDArray[np.float64]
) -> npt.NDArray[np.int32]:
    """First year from which the trajectory never again leaves its own final band.

    Computed backwards: walk from the end and record the last year the band was violated. That is
    one pass instead of a per-cell search, and it gives the LAST exit rather than the first entry --
    the distinction matters for a cell that wanders back out after briefly settling.
    """
    nyear, ncell = traj.shape
    level = np.nanmean(traj[-TAIL_YEARS:], axis=0).astype(np.float64)
    band = np.maximum(np.abs(level) * tol, 1e-9)
    outside = np.abs(traj.astype(np.float64) - level) > band
    # last index where outside is True, or -1 if never
    idx = np.where(outside.any(axis=0), nyear - 1 - outside[::-1].argmax(axis=0), -1)
    return (idx + 1).astype(np.int32)


def main() -> int:
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

    print("seed 1:", flush=True)
    t1 = read_trajectory(path(key1), lat_i, lon_i)
    print("seed 2:", flush=True)
    t2 = read_trajectory(path(key2), lat_i, lon_i)
    nyear = t1.shape[0]

    final1 = np.nanmean(t1[-TAIL_YEARS:], axis=0).astype(np.float64)
    final2 = np.nanmean(t2[-TAIL_YEARS:], axis=0).astype(np.float64)
    mean_final = (final1 + final2) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        two_seed = np.where(mean_final > 0, np.abs(final1 - final2) / mean_final, np.nan)

    tol = np.maximum(FLOOR_TOLERANCE, np.nan_to_num(two_seed, nan=FLOOR_TOLERANCE))
    conv1 = convergence_year(t1, tol)
    conv2 = convergence_year(t2, tol)

    vegetated = mean_final > 1.0  # gC/m2; below this a cell carries no forest at all
    frame = pl.DataFrame(
        {
            "cell": np.arange(lat_i.size, dtype=np.int32),
            "vegc_final_seed1": final1,
            "vegc_final_seed2": final2,
            "two_seed_spread": two_seed,
            "tolerance": tol,
            "conv_year_seed1": conv1,
            "conv_year_seed2": conv2,
            "vegetated": vegetated,
        }
    )
    frame.write_parquet(out / "spin_convergence.parquet")

    # Area-weighted global trajectory, for the headline curve. 0.5 deg cells, so the area of a cell
    # depends on its latitude and an unweighted global mean would over-count the poles ~2x.
    with netCDF4.Dataset(grid_nc) as ds:
        lats = np.asarray(ds.variables["lat"][:])
    res = 0.5
    earth_r = 6_371_000.0
    lat_edges = np.deg2rad(np.stack([lats - res / 2, lats + res / 2], axis=1))
    cell_area = (
        earth_r**2 * np.deg2rad(res) * (np.sin(lat_edges[:, 1]) - np.sin(lat_edges[:, 0]))
    )
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

    veg = frame.filter(pl.col("vegetated"))
    cy = np.asarray(veg["conv_year_seed1"].to_numpy())
    plateau1 = float(glob1[-TAIL_YEARS:].mean())

    def frac_by(year: int) -> float:
        return float((cy <= year).mean())

    def global_within(pct: float) -> int:
        """First year from which the global curve stays within `pct` of its final plateau."""
        off = np.abs(glob1 - plateau1) > pct * plateau1
        return int(nyear - 1 - off[::-1].argmax()) + 2 if off.any() else 1

    summary = {
        "source_seed1": str(path(key1)),
        "source_seed2": str(path(key2)),
        "nyear": nyear,
        "ncell": int(lat_i.size),
        "vegetated_cells": int(veg.height),
        "tolerance_rule": "max(10 %, this cell's own two-seed spread of final VegC)",
        "median_two_seed_spread_vegetated": float(np.nanmedian(veg["two_seed_spread"].to_numpy())),
        "p90_two_seed_spread_vegetated": float(
            np.nanpercentile(veg["two_seed_spread"].to_numpy(), 90)
        ),
        "global_vegc_pgc_final": plateau1,
        "global_converged_year_1pct": global_within(0.01),
        "global_converged_year_2pct": global_within(0.02),
        "global_converged_year_5pct": global_within(0.05),
        "cell_conv_year_median": float(np.median(cy)),
        "cell_conv_year_p90": float(np.percentile(cy, 90)),
        "cell_conv_year_p99": float(np.percentile(cy, 99)),
        "cell_conv_year_max": int(cy.max()),
        "frac_converged_by_200": frac_by(200),
        "frac_converged_by_300": frac_by(300),
        "frac_converged_by_500": frac_by(500),
        "frac_converged_by_700": frac_by(700),
        "frac_never_converged": float((cy >= nyear).mean()),
        "seed_agreement_on_conv_year_median_abs_diff": float(
            np.median(np.abs(veg["conv_year_seed1"].to_numpy() - veg["conv_year_seed2"].to_numpy()))
        ),
    }
    (out / "spin_convergence.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
