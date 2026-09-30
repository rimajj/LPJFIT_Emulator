#!/usr/bin/env python
"""The Germany equilibrium corpus: settled vegetation carbon under six climates, and its inputs.

    NCPUS=16 scripts/sbatch_py.sh D-germany-truth   scripts/germany_corpus.py truth
    NCPUS=16 scripts/sbatch_py.sh D-germany-climate scripts/germany_corpus.py climate --workers 16
    NCPUS=4  scripts/sbatch_py.sh D-germany-check   scripts/germany_corpus.py check
    NCPUS=12 scripts/sbatch_py.sh D-germany-restart scripts/germany_corpus.py restart --workers 12
    NCPUS=64 scripts/sbatch_py.sh D-germany-state   scripts/germany_corpus.py state --workers 64

WHAT THE RUNS ARE (owner, 2026-09-30; inventory in `journal/D/2026-09b.md`). 9,067 cells of Germany
at ~0.07 deg, npatch 250, natural vegetation, LPJmL 5.6.004 with the individual-tree extension.
Two ESMs (ACCESS-CM2, MPI-ESM1-2-HR) x ssp126/ssp245/ssp370 x seeds 1 and 2. Each run follows the
real scenario to 2100, then recycles random years of 2071-2100 until 3100. CO2 is constant at
415.78 ppm from 2020, so it is constant over everything used here and never a feature
(`MEMORY.md:co2-closed`).

⚠ THE HUMIDITY DEFECT, AND WHY THE TRUTH WINDOW ENDS IN 3070. The forcing's humidity file holds
RELATIVE humidity. The segments 2015-2070 and 2101-3070 declare it so (the model logs "rhumid");
the segments 2071-2100 and 3071-3100 do not (logged "humid"), so there the model reads it as
SPECIFIC humidity, `getvpd.c` clips relative humidity to 1, and the vapour-pressure deficit is zero
every day. So the last 30 years, the 3100 restart and the per-tree output of 3071-3100 come from a
forest with no dryness stress. The truth here is taken inside the clean 2101-3070 segment, and the
3071-3100 shift is REPORTED per cell (`shift3100_s*`) so the defect's size is on record.

TRUTH (stage `truth`), per cell x ESM x scenario x seed, from the annual `VegC` NetCDF output:
  * `vegc_win`: mean of model years 2821-3070 (250 years, clean);
  * `vegc_early`: mean of 2571-2820, the disjoint earlier window the band is built from, as the
    global test builds its band from 1200-1449 (`exp_spinup_vegc`);
  * `trend_pct_century`: least-squares slope over 2571-3070 in % of the mean per century;
  * `iav_frac`: interannual SD / mean over the truth window;
  * `shift3100`: mean(3071-3100) / mean(3041-3070) - 1, the humidity defect's footprint.
Sources: `vegc_3070.nc` (2101-3070) and the 3071-3100 segment -- `vegc_3100_backup.nc` where it
exists, else a 30-step `vegc_3100.nc` (ACCESS-CM2 ssp370 seed 2 was never concatenated;
MPI-ESM1-2-HR ssp370 seed 2's `vegc_3100.nc` was overwritten by a cancelled rerun and is all-masked,
its backup is intact). Where a 1000-step `vegc_3100.nc` also exists, its last 30 steps must equal
the backup.

INPUTS (stage `climate`), per cell x ESM x scenario, from the daily forcing of 2071-2100 -- the
window the equilibrium recycles:
  * the 85 forcing columns of `vegemu.corpus.climate.CLIMATE_FEATURES` and the 167 derived columns
    of `features_v3.V3_ALLP`, computed by the SAME functions as every global table;
  * two conversions into the units those functions take, both the model's own:
      lwnet = lwdown - 5.6704e-8 (T + 273.15)^4       (`numeric/petpar2.c`, `radiation_lwdown`);
      huss  = rh exp(17.67 T / (T + 273.16 - 29.65)) / (0.263 x 1013.25),
    the exact inverse of `features_v3.vpd_pa`, so that function recovers the model's relative
    humidity (`spitfire/getvpd.c`, `relative_humidity = true` as in the clean segments);
  * soil: the code from the Germany soil file, the depth from the Pelletier NetCDF the runs read
    (nearest 5-arcmin cell), and the five `SOIL_FEATURES` from them.
No location, no scenario name, no ESM name and no CO2 is ever a feature; `cell`, `lon`, `lat`,
`esm` and `ssp` are stored as keys only.

CHECK (stage `check`): the daily-array path must reproduce the stored global tables EXACTLY on real
cells -- `climate_columns_from_daily` against `climate_spinup.parquet` and `v3_columns` against the
v3p spin-up table, 200 global cells, 1901-1930. That proves the Germany columns mean what the
global ones mean; the two unit conversions are proven by their provenance above, not by this.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import ClmReader, read_grid
from vegemu.corpus import features_v3 as fv3
from vegemu.corpus.climate import CLIMATE_FEATURES, VARS, climate_columns_from_daily
from vegemu.corpus.soil import SOIL_FEATURES, soil_columns_for_codes
from vegemu.paths import path, paths

Array = npt.NDArray[np.float64]

ESMS: tuple[str, ...] = ("ACCESS-CM2", "MPI-ESM1-2-HR")
SSPS: tuple[str, ...] = ("ssp126", "ssp245", "ssp370")
SEEDS: tuple[int, ...] = (1, 2)
FIRST_EQ = 2101  # first year of the recycled-climate segment
WIN = (2821, 3070)  # truth window, clean
EARLY = (2571, 2820)  # band window, clean, disjoint
TREND = (2571, 3070)
BEFORE = (3041, 3070)
AFTER = (3071, 3100)  # the humidity-defect segment
CLIM = (2071, 2100)  # the forcing window the equilibrium recycles
# Germany forcing file stems for each of our five variables, and their raw meaning.
FORCING: dict[str, str] = {
    "tas": "TMean",
    "pr": "tpr",
    "rsds": "SWR",
    "lwnet": "LWR",
    "huss": "HRMean",
}
SIGMA = 5.6704e-8  # petpar2.c
CHUNK = 1200  # cells per climate task: ~2.5 GB of float64 days plus the feature work


def _out() -> Path:
    p = Path(str(paths()["scratch"]["corpus"])) / "germany-eq-v1"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _commit() -> str:
    r = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parent.parent), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout.strip()


def grid() -> Array:
    g = read_grid(path("germany.coord"))
    assert g.shape == (9067, 2), g.shape
    return g


# -- truth ---------------------------------------------------------------------------------------


def _read_vegc(fn: Path) -> tuple[Array, Array, Array, Array]:
    import netCDF4  # noqa: PLC0415 -- only the truth stage needs it

    with netCDF4.Dataset(str(fn)) as f:
        v = f.variables["VegC"]
        v.set_auto_mask(True)
        data = np.ma.filled(v[:].astype(np.float64), np.nan)
        lat = np.asarray(f.variables["lat"][:], dtype=np.float64)
        lon = np.asarray(f.variables["lon"][:], dtype=np.float64)
        t = f.variables["time"]
        # The files use a 365-day calendar; decoding them as "standard" drifts a year by 3070.
        cal = getattr(t, "calendar", "standard")
        years = np.array([d.year for d in netCDF4.num2date(t[:], t.units, cal)])
    return data, lat, lon, years


def _nsteps(fn: Path) -> int:
    import netCDF4  # noqa: PLC0415

    with netCDF4.Dataset(str(fn)) as f:
        return len(f.dimensions["time"])


def _to_cells(data: Array, lat: Array, lon: Array, g: Array) -> Array:
    """(time, lat, lon) -> (time, 9067) by the nearest grid centre, which must be within 1 % of a
    grid spacing (the NetCDF is written on the run's own grid)."""
    iy = np.abs(lat[None, :] - g[:, 1:2]).argmin(axis=1)
    ix = np.abs(lon[None, :] - g[:, 0:1]).argmin(axis=1)
    dy = np.abs(lat[iy] - g[:, 1]).max()
    dx = np.abs(lon[ix] - g[:, 0]).max()
    step = float(np.median(np.abs(np.diff(lat))))
    if max(dx, dy) > 0.01 * step:
        raise AssertionError(f"grid and NetCDF disagree by {max(dx, dy):.4g} deg")
    if np.unique(iy * lon.size + ix).size != g.shape[0]:
        raise AssertionError("two cells map to one NetCDF pixel")
    return data[:, iy, ix]


def run_series(esm: str, ssp: str, seed: int, g: Array) -> tuple[Array, dict[str, Any]]:
    """Annual VegC for 2101-3100, (1000, 9067), and a note of which files made it."""
    o = path("germany.runs") / esm / ssp / f"random_seed_{seed}" / "output"
    main, lat, lon, yrs = _read_vegc(o / "vegc_3070.nc")
    assert yrs[0] == FIRST_EQ and yrs[-1] == BEFORE[1] and yrs.size == 970, (esm, ssp, seed)
    backup = o / "vegc_3100_backup.nc"
    full = o / "vegc_3100.nc"
    note: dict[str, Any] = {"clean": "vegc_3070.nc"}
    if backup.exists():
        tail, lat2, lon2, y2 = _read_vegc(backup)
        note["tail"] = backup.name
        if (
            _nsteps(full) == 1000
        ):  # a concatenated full series exists: its tail must equal the backup
            fdata, *_ = _read_vegc(full)
            same = np.array_equal(fdata[-30:], tail, equal_nan=True)
            note["full_tail_equals_backup"] = bool(same)
            if not same:
                raise AssertionError(f"{o}: vegc_3100.nc's last 30 years differ from the backup")
        else:  # MPI-ESM1-2-HR ssp370 seed 2: a cancelled rerun overwrote it; even time is masked
            note["full"] = f"{_nsteps(full)}-step {full.name}, not a full series; not read"
    else:
        tail, lat2, lon2, y2 = _read_vegc(full)
        note["tail"] = full.name
    assert y2[0] == AFTER[0] and y2[-1] == AFTER[1] and y2.size == 30, (esm, ssp, seed, y2[:3])
    assert np.allclose(lat, lat2) and np.allclose(lon, lon2)
    series = np.concatenate([_to_cells(main, lat, lon, g), _to_cells(tail, lat, lon, g)], axis=0)
    note["nan_cells"] = int(np.isnan(series).any(axis=0).sum())
    return series, note


def _span(series: Array, span: tuple[int, int]) -> Array:
    return series[span[0] - FIRST_EQ : span[1] - FIRST_EQ + 1]


def stage_truth() -> int:
    import polars as pl  # noqa: PLC0415

    g = grid()
    rows: list[dict[str, Any]] = []
    notes: dict[str, Any] = {}
    domain: dict[str, list[float]] = {}
    t_years = np.arange(TREND[0], TREND[1] + 1, dtype=np.float64)
    for esm in ESMS:
        for ssp in SSPS:
            per_seed: dict[int, dict[str, Array]] = {}
            for seed in SEEDS:
                s, note = run_series(esm, ssp, seed, g)
                notes[f"{esm}/{ssp}/{seed}"] = note
                domain[f"{esm}/{ssp}/{seed}"] = np.nanmean(s, axis=1).tolist()
                win, early = _span(s, WIN), _span(s, EARLY)
                tr = _span(s, TREND)
                m = tr.mean(axis=0)
                slope = ((t_years - t_years.mean())[:, None] * (tr - m)).sum(axis=0) / (
                    (t_years - t_years.mean()) ** 2
                ).sum()
                with np.errstate(divide="ignore", invalid="ignore"):
                    per_seed[seed] = {
                        "vegc_win": win.mean(axis=0),
                        "vegc_early": early.mean(axis=0),
                        "trend_pct_century": np.where(m > 0, 100 * 100 * slope / m, 0.0),
                        "iav_frac": np.where(
                            win.mean(axis=0) > 0, win.std(axis=0) / win.mean(axis=0), 0.0
                        ),
                        "shift3100": np.where(
                            _span(s, BEFORE).mean(axis=0) > 0,
                            _span(s, AFTER).mean(axis=0) / _span(s, BEFORE).mean(axis=0) - 1,
                            np.nan,
                        ),
                    }
                print(f"  {esm} {ssp} seed {seed}: {note}", flush=True)
            for c in range(g.shape[0]):
                r: dict[str, Any] = {
                    "cell": c,
                    "lon": float(g[c, 0]),
                    "lat": float(g[c, 1]),
                    "esm": esm,
                    "ssp": ssp,
                }
                for seed, d in per_seed.items():
                    for k, v in d.items():
                        r[f"{k}_s{seed}"] = float(v[c])
                rows.append(r)
    frame = pl.DataFrame(rows)
    e1, e2 = frame["vegc_early_s1"].to_numpy(), frame["vegc_early_s2"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        spread = np.where((e1 + e2) / 2 > 1.0, np.abs(e1 - e2) / ((e1 + e2) / 2), 0.0)
    frame = frame.with_columns(pl.Series("two_seed_spread", spread))
    dest = _out() / "germany_truth.parquet"
    frame.write_parquet(dest)
    w1, w2 = frame["vegc_win_s1"].to_numpy(), frame["vegc_win_s2"].to_numpy()
    band = np.maximum(0.10, spread)
    rerun = (
        (np.abs(w1 - w2) <= band * np.abs(w2)).astype(float)
        + (np.abs(w2 - w1) <= band * np.abs(w1)).astype(float)
    ) / 2
    tr_abs = np.maximum(
        np.abs(frame["trend_pct_century_s1"].to_numpy()),
        np.abs(frame["trend_pct_century_s2"].to_numpy()),
    )
    sh = np.concatenate([frame["shift3100_s1"].to_numpy(), frame["shift3100_s2"].to_numpy()])
    summary = {
        "rows": frame.height,
        "cells": g.shape[0],
        "output": str(dest),
        "output_sha256": _sha256(dest),
        "code_commit": _commit(),
        "windows": {"truth": WIN, "band": EARLY, "trend": TREND, "shift": [BEFORE, AFTER]},
        "files": notes,
        "vegetated_both_seeds": int(((w1 > 0) & (w2 > 0)).sum()),
        "rerun_in_band": float(rerun[(w1 > 0) & (w2 > 0)].mean()),
        "band_is_floor_share": float((band == 0.10).mean()),
        "trend_abs_pct_century_quantiles": {
            str(q): float(np.nanquantile(tr_abs, q)) for q in (0.5, 0.9, 0.99)
        },
        "share_trend_over_2pct_century": float(np.mean(tr_abs > 2.0)),
        "shift3100_quantiles": {
            str(q): float(np.nanquantile(sh, q)) for q in (0.01, 0.1, 0.5, 0.9, 0.99)
        },
        "shift3100_share_beyond_10pct": float(np.nanmean(np.abs(sh) > 0.10)),
        "domain_mean_by_year": domain,
    }
    (_out() / "germany_truth.json").write_text(json.dumps(summary, indent=2, default=list))
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("domain_mean_by_year", "files")},
            indent=2,
            default=list,
        ),
        flush=True,
    )
    return 0


# -- climate -------------------------------------------------------------------------------------


def forcing_files(esm: str, ssp: str) -> dict[str, str]:
    d = path("germany.forcing") / esm
    return {v: str(d / f"{stem}_{esm}_{ssp}_germany.clm") for v, stem in FORCING.items()}


def convert(raw: dict[str, Array]) -> dict[str, Array]:
    """Germany's raw variables -> the units every feature function takes (module docstring)."""
    t = raw["tas"]
    out = dict(raw)
    out["lwnet"] = raw["lwnet"] - SIGMA * np.power(t + 273.15, 4)
    rh = np.clip(raw["huss"], 0.0, 1.0)
    out["huss"] = rh * np.exp(17.67 * t / (t + 273.16 - 29.65)) / (0.263 * 1013.25)
    return out


def static_soil() -> tuple[npt.NDArray[np.int64], Array]:
    """(soil code, soil depth in m) for the 9,067 cells."""
    import netCDF4  # noqa: PLC0415

    r = ClmReader(str(path("germany.soil")))
    with r:
        codes = np.asarray(r.year(r.header.firstyear)[:, 0]).astype(np.int64)
    g = grid()
    with netCDF4.Dataset(str(path("germany.soildepth_nc"))) as f:
        lat = np.asarray(f.variables["Latitude"][:], dtype=np.float64)
        lon = np.asarray(f.variables["Longitude"][:], dtype=np.float64)
        iy = np.abs(lat[None, :] - g[:, 1:2]).argmin(axis=1)
        ix = np.abs(lon[None, :] - g[:, 0:1]).argmin(axis=1)
        soild = f.variables["soild"]
        depth = np.array([float(soild[a, b]) for a, b in zip(iy, ix, strict=True)])
    assert codes.shape == depth.shape == (9067,)
    return codes, depth


def _climate_task(args: tuple[str, str, int, int, list[int], list[float]]) -> dict[str, Any]:
    esm, ssp, row0, row1, codes, depths = args
    t0 = time.time()
    raw, ids = fv3.read_rows(forcing_files(esm, ssp), CLIM[0], CLIM[1], row0, row1)
    daily = convert(raw)
    base = climate_columns_from_daily(
        [{v: daily[v][:, iy, :] for v in VARS} for iy in range(CLIM[1] - CLIM[0] + 1)]
    )
    v3 = fv3.v3_columns(
        daily, np.asarray(codes), np.asarray(depths), extras=True, productivity=True
    )
    return {"esm": esm, "ssp": ssp, "cells": ids, "base": base, "v3": v3, "s": time.time() - t0}


def stage_climate(workers: int) -> int:
    import polars as pl  # noqa: PLC0415

    g = grid()
    codes, depth = static_soil()
    soil = soil_columns_for_codes(codes, depth)
    tasks = [
        (
            esm,
            ssp,
            r0,
            min(r0 + CHUNK, 9067),
            codes[r0 : r0 + CHUNK].tolist(),
            depth[r0 : r0 + CHUNK].tolist(),
        )
        for esm in ESMS
        for ssp in SSPS
        for r0 in range(0, 9067, CHUNK)
    ]
    parts: list[pl.DataFrame] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(_climate_task, tasks):
            cells = np.asarray(res["cells"], dtype=np.int64)
            cols: dict[str, Any] = {
                "cell": cells.astype(np.int32),
                "lon": g[cells, 0],
                "lat": g[cells, 1],
                "esm": [res["esm"]] * cells.size,
                "ssp": [res["ssp"]] * cells.size,
            }
            cols.update(
                {k: np.asarray(res["base"][k]) for k in CLIMATE_FEATURES if k != "soildepth"}
            )
            cols["soildepth"] = depth[cells]
            cols.update({k: np.asarray(soil[k])[cells] for k in SOIL_FEATURES})
            cols.update({k: np.asarray(res["v3"][k]) for k in fv3.V3_ALLP})
            parts.append(pl.DataFrame(cols))
            print(
                f"  {res['esm']} {res['ssp']} cells {cells[0]}-{cells[-1]}: {res['s']:.0f} s",
                flush=True,
            )
    frame = pl.concat(parts).sort(["esm", "ssp", "cell"])
    assert frame.height == 9067 * len(ESMS) * len(SSPS)
    dest = _out() / "germany_climate.parquet"
    frame.write_parquet(dest)
    meta = {
        "rows": frame.height,
        "columns": frame.width,
        "window": CLIM,
        "features": {
            "climate": len(CLIMATE_FEATURES),
            "soil": len(SOIL_FEATURES),
            "v3_allp": len(fv3.V3_ALLP),
        },
        "files": {
            f"{e}/{s}": {
                v: {"path": p, "header": ClmReader(p).header.describe()}
                for v, p in forcing_files(e, s).items()
            }
            for e in ESMS
            for s in SSPS
        },
        "conversions": {
            "lwnet": "lwdown - 5.6704e-8 (T+273.15)^4",
            "huss": "rh exp(17.67T/(T+273.16-29.65)) / (0.263*1013.25)",
        },
        "soildepth": f"{path('germany.soildepth_nc')} var soild, nearest 5-arcmin cell",
        "co2": "constant 415.78 ppm over everything used; NOT a feature (MEMORY.md:co2-closed)",
        "output": str(dest),
        "output_sha256": _sha256(dest),
        "code_commit": _commit(),
    }
    (_out() / "germany_climate.json").write_text(json.dumps(meta, indent=2, default=list))
    print(json.dumps({k: meta[k] for k in ("rows", "columns", "output_sha256")}), flush=True)
    return 0


# -- check ---------------------------------------------------------------------------------------


def stage_check() -> int:
    import polars as pl  # noqa: PLC0415

    cfg = paths()
    corpus = Path(str(cfg["scratch"]["corpus"])) / "spinup-constco2"
    exp = Path(str(cfg["scratch"]["exp"]))
    clim = pl.read_parquet(corpus / "climate_spinup.parquet").sort("cell")
    v3p = pl.read_parquet(exp / "T-features-v3p" / "features_v3p_spinup.parquet").sort("cell")
    rng = np.random.default_rng(0)
    cells = np.sort(rng.choice(clim.height, 200, replace=False))
    files = {v: str(cfg["inputs"]["historical"][v]) for v in VARS}
    daily = fv3.read_cells(files, 1901, 1930, cells.tolist())
    base = climate_columns_from_daily([{v: daily[v][:, iy, :] for v in VARS} for iy in range(30)])
    codes = np.fromfile(str(cfg["inputs"]["soil"]), dtype=np.uint8).astype(np.int64)[cells]
    depth = clim["soildepth"].to_numpy()[cells]
    v3 = fv3.v3_columns(daily, codes, depth, extras=True, productivity=True)
    report: dict[str, Any] = {"cells": cells.size}
    for name, got, table, names in (
        ("base", base, clim, [c for c in CLIMATE_FEATURES if c != "soildepth"]),
        ("v3p", v3, v3p, list(fv3.V3_ALLP)),
    ):
        worst, bad = 0.0, []
        for k in names:
            ref = table[k].to_numpy().astype(np.float64)[cells]
            x = np.asarray(got[k], dtype=np.float64)
            same = (x == ref) | (np.isnan(x) & np.isnan(ref))
            if not same.all():
                bad.append(k)
                worst = max(worst, float(np.nanmax(np.abs(x - ref))))
        report[name] = {"columns": len(names), "unequal_columns": bad, "worst_abs": worst}
    report["verdict"] = (
        "PASS"
        if not report["base"]["unequal_columns"] and not report["v3p"]["unequal_columns"]
        else "FAIL"
    )
    (_out() / "germany_check.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["verdict"] == "PASS" else 1


# -- restart: the clean 3070 restarts, proven before they are decoded ---------------------------
#
# The 3070 restart is the last full state inside the clean segment (the 3100 one comes out of the
# 30 humidity-defect years), so it is where tree counts and traits come from. It is 195-211 GB per
# run, 250 patches, written by LPJmL 5.6.004 on two builds (ssp245 on 2026-02-05, the rest on
# 2025-12-17) -- neither of which our reader was proven on. Invariant 7: prove it on these files.

RESTART_YEAR = 3070
RT_SAMPLE = 48  # cells per file: an even stride, plus the file's largest record


def restart_file(esm: str, ssp: str, seed: int) -> Path:
    return (
        path("germany.runs")
        / esm
        / ssp
        / f"random_seed_{seed}"
        / "restart"
        / f"restart_{RESTART_YEAR}_nv.lpj"
    )


def _vegc_3070(esm: str, ssp: str, seed: int, g: Array) -> Array:
    """The model's own annual VegC for 3070 (last step of vegc_3070.nc), per cell."""
    o = path("germany.runs") / esm / ssp / f"random_seed_{seed}" / "output"
    data, lat, lon, yrs = _read_vegc(o / "vegc_3070.nc")
    assert yrs[-1] == RESTART_YEAR, (esm, ssp, seed, yrs[-1])
    return _to_cells(data[-1:], lat, lon, g)[0]


def _roundtrip_task(args: tuple[str, str, int]) -> dict[str, Any]:
    from vegemu.binfmt.restart import RestartReader, read_cell, write_cell  # noqa: PLC0415
    from vegemu.corpus.vegc import cell_vegc  # noqa: PLC0415

    esm, ssp, seed = args
    fn = restart_file(esm, ssp, seed)
    r = RestartReader(fn)
    sizes = r.cell_sizes()
    cells = sorted(
        set(np.linspace(0, r.ncell - 1, RT_SAMPLE).astype(int).tolist()) | {int(sizes.argmax())}
    )
    nc = _vegc_3070(esm, ssp, seed, grid())
    out: dict[str, Any] = {
        "file": str(fn),
        "bytes": r.filesize,
        "firstyear": r.generic.firstyear,
        "ncell": r.ncell,
        "layout": repr(r.layout),
        "cells": cells,
        "record_bytes_min_max": [int(sizes.min()), int(sizes.max())],
        "unequal": [],
        "npatch": set(),
        "rel_vegc_vs_output": [],
        "skip": 0,
    }
    t0 = time.time()
    with r:
        for c in cells:
            blob = r.cell_bytes(c)
            rec = read_cell(blob, r.layout)
            if write_cell(rec, r.layout) != blob:
                out["unequal"].append(c)
            if rec["skip"]:
                out["skip"] += 1
                continue
            out["npatch"].add(int(rec["stands"][0]["npatch"]))
            ours = cell_vegc(rec)["total"]
            out["rel_vegc_vs_output"].append(
                abs(ours - float(nc[c])) / max(abs(float(nc[c])), 1e-9)
            )
    out["s_per_cell"] = (time.time() - t0) / len(cells)
    out["npatch"] = sorted(out["npatch"])
    rel = np.asarray(out.pop("rel_vegc_vs_output"))
    out["vegc_vs_output_max_rel"] = float(rel.max()) if rel.size else None
    out["vegc_vs_output_share_1e-6"] = float((rel <= 1e-6).mean()) if rel.size else None
    return out


def stage_restart(workers: int) -> int:
    """Byte round-trip + a cross-check against the model's own 3070 VegC, on every 3070 file.

    PASS needs, per file: the header says year 3070 and 9,067 cells; every sampled record re-encodes
    to the same bytes; and the decoded total VegC equals the model's own VegC output for 3070 within
    1e-6 relative (float32 output) on every sampled vegetated cell -- which proves the record order
    is the grid order, not just that the bytes parse.
    """
    tasks = [(e, s, seed) for e in ESMS for s in SSPS for seed in SEEDS]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_roundtrip_task, tasks))
    fails: list[str] = []
    for r in res:
        bad = []
        if r["firstyear"] != RESTART_YEAR or r["ncell"] != 9067:
            bad.append("header")
        if r["unequal"]:
            bad.append(f"{len(r['unequal'])} records not byte-identical")
        if r["vegc_vs_output_share_1e-6"] != 1.0:
            bad.append(f"VegC off the output, max rel {r['vegc_vs_output_max_rel']:.3g}")
        r["verdict"] = "PASS" if not bad else "FAIL: " + "; ".join(bad)
        if bad:
            fails.append(r["file"])
        print(
            f"  {r['file']}: {r['verdict']}, {len(r['cells'])} cells, npatch {r['npatch']}, "
            f"{r['s_per_cell']:.2f} s/cell",
            flush=True,
        )
    report = {
        "files": res,
        "code_commit": _commit(),
        "verdict": "PASS" if not fails else "FAIL",
        "failed": fails,
    }
    (_out() / "germany_restart_check.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("verdict", "failed")}), flush=True)
    return 0 if not fails else 1


def _state_task(args: tuple[str, str, int, int, int]) -> list[dict[str, Any]]:
    from vegemu.binfmt.restart import RestartReader  # noqa: PLC0415
    from vegemu.corpus import schema as schema_mod  # noqa: PLC0415
    from vegemu.corpus.state import summarise_cell  # noqa: PLC0415
    from vegemu.corpus.vegc import cell_vegc  # noqa: PLC0415

    esm, ssp, seed, c0, c1 = args
    r = RestartReader(restart_file(esm, ssp, seed))
    rows: list[dict[str, Any]] = []
    with r:
        for c in range(c0, c1):
            rec = r.read(c)
            row: dict[str, Any] = summarise_cell(rec, c, r.layout, schema=schema_mod.CURRENT)
            v = cell_vegc(rec)
            row.update({"vegc_out_tree": v["tree"], "vegc_out_grass": v["grass"]})
            row.update({"esm": esm, "ssp": ssp, "seed": seed})
            rows.append(row)
    return rows


STATE_CHUNK = 64


def stage_state(workers: int) -> int:
    """Every cell of every 3070 restart -> the per-cell state vector (tree counts, size bins, the
    species mix, trait quantiles and means), schema 3, plus the model-definition VegC split. Refuses
    to run unless `restart` passed on these files at this commit's reader."""
    import polars as pl  # noqa: PLC0415

    from vegemu.corpus import schema as schema_mod  # noqa: PLC0415
    from vegemu.corpus.state import STATE_COLUMNS  # noqa: PLC0415

    chk = _out() / "germany_restart_check.json"
    if not chk.exists() or json.loads(chk.read_text())["verdict"] != "PASS":
        print(f"refusing: {chk} missing or not PASS -- run the `restart` stage first", flush=True)
        return 2
    tasks = [
        (e, s, seed, c0, min(c0 + STATE_CHUNK, 9067))
        for e in ESMS
        for s in SSPS
        for seed in SEEDS
        for c0 in range(0, 9067, STATE_CHUNK)
    ]
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, part in enumerate(ex.map(_state_task, tasks), 1):
            rows.extend(part)
            if i % 50 == 0:
                print(f"  {i}/{len(tasks)} chunks, {time.time() - t0:.0f} s", flush=True)
    keys = ["cell", "esm", "ssp", "seed"]
    frame = (
        pl.DataFrame(rows)
        .select(
            [*keys, *[c for c in STATE_COLUMNS if c != "cell"], "vegc_out_tree", "vegc_out_grass"]
        )
        .with_columns(pl.col("cell").cast(pl.Int32), pl.col("seed").cast(pl.Int8))
        .sort(["esm", "ssp", "seed", "cell"])
    )
    assert frame.height == 9067 * len(ESMS) * len(SSPS) * len(SEEDS), frame.height
    dest = _out() / "germany_state_3070.parquet"
    frame.write_parquet(dest)
    meta = {
        "rows": frame.height,
        "columns": frame.width,
        "schema": schema_mod.CURRENT,
        "restart_year": RESTART_YEAR,
        "files": {
            f"{e}/{s}/{sd}": str(restart_file(e, s, sd)) for e in ESMS for s in SSPS for sd in SEEDS
        },
        "restart_check_sha256": _sha256(chk),
        "treeless_rows": int((frame["stems_total"] == 0).sum()),
        "skip_rows": int((frame["skip"] == 1).sum()),
        "output": str(dest),
        "output_sha256": _sha256(dest),
        "code_commit": _commit(),
        "seconds": time.time() - t0,
    }
    (_out() / "germany_state_3070.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != "files"}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("stage", choices=("truth", "climate", "check", "restart", "state"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if a.stage == "truth":
        return stage_truth()
    if a.stage == "climate":
        return stage_climate(a.workers)
    if a.stage == "restart":
        return stage_restart(a.workers)
    if a.stage == "state":
        return stage_state(a.workers)
    return stage_check()


if __name__ == "__main__":
    raise SystemExit(main())
