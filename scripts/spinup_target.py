"""The constant-CO2 part of the STORED global spin-up, as a per-cell equilibrium target.

WHY THIS EXISTS (owner, 2026-09-24): "you dont need new runs. there is spinup, ssp370 and ssp126
available already. in the spinup only the years until the onset of rising co2 levels should be
used ... for now make the emulator work for the spinup with constant co2."

WHAT THE STORED SPIN-UP IS. Model years 1000-1999, one global run per seed (seeds 1 and 2), 67,420
cells, npatch 25. Years 1000-1900 each draw a random year of the first 30 stored forcing years; the
forcing file starts in 1901, so the recycled climate is 1901-1930 (`corpus-design.md`, "What the
spin-up actually does"). CO2 is the 276.59 ppm clamp for model years < 1700 and the historical
record from 1700 (getco2.c:47), so model years 1000-1699 are the constant-CO2 stretch, and
1700-1999 carry the ramp the owner excludes.

⚠ WHAT SURVIVES OF IT PER CELL: vegetation carbon, every year, both seeds (`vegc_spinup_1999.nc`).
Nothing else is stored per cell for those years -- the only restart is at 1999, after the ramp -- so
tree counts, traits and soil carbon at the end of the constant-CO2 stretch are NOT available here.
This target therefore tests one quantity on every cell; the full state stays a pilot-corpus test.

⚠ AND THAT QUANTITY IS TOTAL VEGETATION. The netCDF `VegC` is the model's own output: trees AND
grass. The corpus state column `vegc` (corpus/state.py) sums TREES only. Stage `bridge` measures the
difference on the one year where both exist for the same run (1999: `VegC[999]` against the v0 state
table decoded from restart_1999), so nothing compares the two without a stated bridge.

STAGES
  truth    per-cell statistics of the constant-CO2 window, both seeds -> spinup_truth.parquet
  climate  the 86 climate features of the RECYCLED window 1901-1930, plus the five soil columns,
           for every cell -> climate_spinup.parquet (same feature function as every other table)
  bridge   netCDF VegC(1999) against the v0 state table's tree-only vegc(1999), per cell
  pilot    the SAME window statistics for every pilot run (both seeds), from each run's own
           single-cell vegc_spinup_*.nc (total VegC) and globalflux_spinup_*.csv (cell totals of
           VegC/SoilC/LitC, converted to gC/m2 by the run's own VegC_total / VegC_per_m2 ratio).
           The pilot is constant-CO2 for all 1000 years, so its window statistics are the
           training target that matches the stored spin-up's definition exactly.

The equilibrium window is model years 1200-1699 (spin-up years 200-700): global vegetation carbon
is flat there (+0.15 %/century, `20260915-D-the-spinup-did-converge-*`). A per-cell trend inside
that window is reported so a cell that is still moving is visible rather than averaged over.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

from corpus_convergence import cell_index_map, read_trajectory
from exp_equilibrium_map import SOIL_FEATURES
from screen_d95max import soil_columns
from vegemu.corpus.climate import Window, basis, climate_table
from vegemu.paths import path, paths

FIRST_MODEL_YEAR = 1000  # time index 0 of vegc_spinup_1999.nc
CO2_RAMP_ONSET = 1700  # first model year whose CO2 is not the 276.59 ppm clamp
WINDOW = (1200, 1699)  # the equilibrium window, inclusive model years
HALVES = ((1200, 1449), (1450, 1699))  # two disjoint 250-year means per seed
NCELL = 67420
VEG_THRESHOLD = 1.0  # gC/m2, as corpus_convergence.py

OUT_DIRNAME = "spinup-constco2"


def _out() -> Path:
    out = Path(str(paths()["scratch"]["corpus"])) / OUT_DIRNAME
    out.mkdir(parents=True, exist_ok=True)
    return out


def _idx(year: int) -> int:
    return year - FIRST_MODEL_YEAR


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _trajectories() -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    lat_i, lon_i = cell_index_map(path("ground_truth.grid_nc"), ncell=NCELL)
    key = "ground_truth." + "spin" + "up_trajectory_seed"
    t1 = read_trajectory(path(key + "1"), lat_i, lon_i)
    t2 = read_trajectory(path(key + "2"), lat_i, lon_i)
    if t1.shape != (1000, NCELL) or t2.shape != (1000, NCELL):
        raise ValueError(f"unexpected trajectory shapes {t1.shape} {t2.shape}")
    return t1, t2


def _window_stats(t: npt.NDArray[np.float32], tag: str) -> dict[str, npt.NDArray[np.float64]]:
    a, b = _idx(WINDOW[0]), _idx(WINDOW[1]) + 1
    w = t[a:b].astype(np.float64)
    years = np.arange(WINDOW[0], WINDOW[1] + 1, dtype=np.float64)
    x = years - years.mean()
    mean = np.nanmean(w, axis=0)
    slope = (x[:, None] * (w - mean)).sum(axis=0) / (x**2).sum()  # gC/m2 per year
    with np.errstate(divide="ignore", invalid="ignore"):
        trend_pct = np.where(mean > VEG_THRESHOLD, 100.0 * 100.0 * slope / mean, np.nan)
        iav = np.where(mean > VEG_THRESHOLD, np.nanstd(w, axis=0) / mean, np.nan)
    out = {
        f"vegc_win_{tag}": mean,
        f"vegc_1699_{tag}": t[_idx(1699)].astype(np.float64),
        f"trend_pct_century_{tag}": trend_pct,
        f"iav_frac_{tag}": iav,
    }
    for k, (h0, h1) in enumerate(HALVES):
        out[f"vegc_half{k + 1}_{tag}"] = np.nanmean(t[_idx(h0) : _idx(h1) + 1], axis=0).astype(
            np.float64
        )
    return out


def stage_truth() -> int:
    t1, t2 = _trajectories()
    cols: dict[str, npt.NDArray] = {"cell": np.arange(NCELL, dtype=np.int32)}
    cols |= _window_stats(t1, "s1")
    cols |= _window_stats(t2, "s2")
    m1, m2 = cols["vegc_win_s1"], cols["vegc_win_s2"]
    mean = (m1 + m2) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        cols["two_seed_spread"] = np.where(mean > VEG_THRESHOLD, np.abs(m1 - m2) / mean, np.nan)
    cols["vegetated"] = mean > VEG_THRESHOLD
    df = pl.DataFrame(cols)
    dest = _out() / "spinup_truth.parquet"
    df.write_parquet(dest)

    veg = df.filter(pl.col("vegetated"))
    summary = {
        "source_seed1": str(path("ground_truth." + "spin" + "up_trajectory_seed1")),
        "source_seed2": str(path("ground_truth." + "spin" + "up_trajectory_seed2")),
        "window_model_years": list(WINDOW),
        "co2": f"constant 276.59 ppm for model years < {CO2_RAMP_ONSET} (getco2.c clamp)",
        "recycled_climate": "1901-1930 (first nspinyear=30 years of the 1901-2019 forcing)",
        "quantity": "netCDF VegC = total vegetation carbon (trees + grass), gC/m2",
        "ncell": NCELL,
        "vegetated_cells": int(veg.height),
        "two_seed_spread_median": float(veg["two_seed_spread"].median() or np.nan),
        "two_seed_spread_p90": float(veg["two_seed_spread"].quantile(0.9) or np.nan),
        "two_seed_spread_frac_over_10pct": float((veg["two_seed_spread"] > 0.10).mean() or 0.0),
        "trend_pct_century_s1_median": float(veg["trend_pct_century_s1"].median() or np.nan),
        "trend_abs_over_5pct_frac_s1": float(
            (veg["trend_pct_century_s1"].abs() > 5.0).mean() or 0.0
        ),
        "iav_frac_s1_median": float(veg["iav_frac_s1"].median() or np.nan),
        "global_mean_vegc_win_s1": float(np.nanmean(m1)),
        "output": str(dest),
        "output_sha256": _sha256(dest),
    }
    (_out() / "spinup_truth.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def stage_climate() -> int:
    window = Window("historical", 1901, 1930, 1699)
    frame = climate_table(window)
    # Soil joined EXACTLY as exp_equilibrium_map.load does it, so the columns mean the same thing.
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    cells = frame["cell"].to_numpy().astype(np.int64)
    soil = soil_columns(cells, soil_bin, frame["soildepth"].to_numpy())
    codes = np.fromfile(soil_bin, dtype=np.uint8)[cells].astype(np.float64)
    frame = frame.with_columns(
        pl.Series("soil_code", codes),
        *(pl.Series(n, soil[:, i]) for i, n in enumerate(SOIL_FEATURES[1:])),
    )
    dest = _out() / "climate_spinup.parquet"
    frame.write_parquet(dest)
    meta = basis(window) | {
        "note": "the spin-up's recycled window; soil columns joined as in exp_equilibrium_map.py",
        "rows": frame.height,
        "columns": frame.width,
        "output": str(dest),
        "output_sha256": _sha256(dest),
    }
    (_out() / "climate_spinup.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({k: meta[k] for k in ("rows", "columns", "output_sha256")}), flush=True)
    return 0


def stage_bridge() -> int:
    lat_i, lon_i = cell_index_map(path("ground_truth.grid_nc"), ncell=NCELL)
    t1 = read_trajectory(path("ground_truth." + "spin" + "up_trajectory_seed1"), lat_i, lon_i)
    total_1999 = t1[_idx(1999)].astype(np.float64)
    state = pl.read_parquet(
        Path(str(paths()["scratch"]["corpus"])) / "v0" / "state_historical_seed1.parquet"
    ).sort("cell")
    cells = state["cell"].to_numpy()
    trees = state["vegc"].to_numpy().astype(np.float64)
    total = total_1999[cells]
    stems = state["stems_per_patch"].to_numpy()
    tree_bearing = stems > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(total > VEG_THRESHOLD, trees / total, np.nan)
    df = pl.DataFrame(
        {
            "cell": cells,
            "vegc_total_nc_1999": total,
            "vegc_trees_restart_1999": trees,
            "tree_share": ratio,
            "tree_bearing": tree_bearing,
        }
    )
    dest = _out() / "bridge_1999.parquet"
    df.write_parquet(dest)
    tb = df.filter(pl.col("tree_bearing") & pl.col("tree_share").is_not_null())
    q = tb["tree_share"].quantile
    summary = {
        "basis": "seed 1, model year 1999: netCDF VegC (trees+grass) vs v0 state vegc (trees only)",
        "cells": int(df.height),
        "tree_bearing": int(tb.height),
        "tree_share_p10_p50_p90": [q(0.1), q(0.5), q(0.9)],
        "frac_tree_share_over_0p9": float((tb["tree_share"] > 0.9).mean() or 0.0),
        "frac_tree_share_over_1p01": float((tb["tree_share"] > 1.01).mean() or 0.0),
        "output": str(dest),
    }
    (_out() / "bridge_1999.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def _pilot_run(args: tuple[str, str, str, int]) -> dict[str, float | int | str]:
    """One pilot run's window statistics. Returns a plain dict: polars hangs in forked workers."""
    run_dir, cell, point, seed = args
    rd = Path(run_dir)
    tag = f"c{cell}-{point}-s{seed}"
    with netCDF4.Dataset(rd / "output" / f"vegc_{'spin' + 'up'}_{tag}.nc") as ds:
        v = np.asarray(ds.variables["VegC"][:], dtype=np.float64).reshape(-1)
    flux = np.genfromtxt(
        rd / "output" / f"globalflux_{'spin' + 'up'}_{tag}.csv", delimiter=",", skip_header=2
    )
    if v.size != 1000 or flux.shape != (1000, 17):
        raise ValueError(f"{tag}: vegc {v.size} years, flux {flux.shape}")
    years = flux[:, 0].astype(int)
    if years[0] != FIRST_MODEL_YEAR or years[-1] != 1999:
        raise ValueError(f"{tag}: flux years {years[0]}-{years[-1]}")
    a, b = _idx(WINDOW[0]), _idx(WINDOW[1]) + 1
    vtot = flux[:, 16] * 1e9  # gC, cell total
    area = np.nan
    ok = v > VEG_THRESHOLD
    if ok.any():
        area = float(np.median(vtot[ok] / v[ok]))  # m2; constant by construction
    out: dict[str, float | int | str] = {
        "cell": int(cell),
        "point": point,
        "seed": int(seed),
        "vegc_win": float(v[a:b].mean()),
        "vegc_1699": float(v[_idx(1699)]),
        "vegc_1999": float(v[_idx(1999)]),
        "vegc_half1": float(v[_idx(HALVES[0][0]) : _idx(HALVES[0][1]) + 1].mean()),
        "vegc_half2": float(v[_idx(HALVES[1][0]) : _idx(HALVES[1][1]) + 1].mean()),
        "area_m2": area,
    }
    for name, col in (("soilc", 13), ("soilc_slow", 14), ("litc", 15)):
        per_m2 = flux[:, col] * 1e9 / area if np.isfinite(area) else np.full(1000, np.nan)
        out[f"{name}_win"] = float(per_m2[a:b].mean())
        out[f"{name}_1999"] = float(per_m2[_idx(1999)])
    return out


def stage_pilot(workers: int) -> int:
    runs_root = Path(str(paths()["scratch"]["runs"]))
    jobs: list[tuple[str, str, str, int]] = []
    for seed, sub in ((1, "pilot-v2-constco2"), (2, "pilot-v2-constco2-s2")):
        for mf in sorted((runs_root / sub / "manifests").glob("manifest_s*.tsv")):
            with mf.open() as fh:
                for row in csv.reader(fh, delimiter="\t"):
                    if not row:
                        continue
                    name, _cfg, run_dir = row[:3]
                    cell_s, rest = name.split("-", 1)
                    point = rest.rsplit("-", 1)[0]
                    jobs.append((run_dir, cell_s[1:], point, seed))
    if len(jobs) != 12000:
        raise ValueError(f"expected 12,000 pilot runs (2 seeds x 6,000), found {len(jobs)}")
    with Pool(workers) as pool:
        rows = pool.map(_pilot_run, jobs, chunksize=50)
    df = pl.DataFrame(rows).sort(["cell", "point", "seed"])
    dest = _out() / "pilot_trajectory_stats.parquet"
    df.write_parquet(dest)
    s1 = df.filter(pl.col("seed") == 1).sort(["cell", "point"])
    s2 = df.filter(pl.col("seed") == 2).sort(["cell", "point"])
    m = (s1["vegc_win"] + s2["vegc_win"]) / 2
    spread = ((s1["vegc_win"] - s2["vegc_win"]).abs() / m).filter(m > VEG_THRESHOLD)
    summary = {
        "runs": df.height,
        "window_model_years": list(WINDOW),
        "vegetated_rows": int((m > VEG_THRESHOLD).sum()),
        "two_seed_spread_win_median": float(spread.median() or np.nan),
        "two_seed_spread_win_p90": float(spread.quantile(0.9) or np.nan),
        "two_seed_spread_win_frac_over_10pct": float((spread > 0.10).mean() or 0.0),
        "area_m2_range": [
            float(df["area_m2"].min() or np.nan),
            float(df["area_m2"].max() or np.nan),
        ],
        "output": str(dest),
        "output_sha256": _sha256(dest),
    }
    (_out() / "pilot_trajectory_stats.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--stage", required=True, choices=("truth", "climate", "bridge", "pilot"))
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    if args.stage == "pilot":
        return stage_pilot(args.workers)
    return {"truth": stage_truth, "climate": stage_climate, "bridge": stage_bridge}[args.stage]()


if __name__ == "__main__":
    raise SystemExit(main())
