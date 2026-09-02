#!/usr/bin/env python3
"""B4 -- ssp126 as a genuinely held-out THIRD forcing leg.

Line X exploration probe (read-only except its own outputs under /p/tmp/jamirp/X_explore).

The question: LPJmL-FIT has been run on a THIRD forcing leg (ssp126, both seeds, complete
2026-08-18) that appears in no record. Historic + ssp370 BRACKET it (ssp126 warms ~0.23x of
ssp370 on a common pre-2020 baseline). So it is the only out-of-distribution / bracketed-
interpolation test this project can run. Does a direct climatology -> 20-year-window state map,
fitted on historic + ssp370 only, carry a transferable climate response to ssp126?

Stages (positional arg 1):
  prov   provenance gate: build strings, completion lines, ntasks, restart lineage, env switches
  clim   per-cell 20-yr window climatology for ALL THREE legs from the .clm forcing (identical code)
  vegc   per-cell 20-yr window vegetation carbon for 3 legs x 2 members from the gridded vegc_*.nc
  fit    the pre-registered held-out-leg experiment + every null
  ind    ssp126 per-stem roster: header gate, parallel raw-CSV scan, per-cell-year counts + sample
  indresp  ssp126 stem-count response vs historic, both seeds, with the two-seed spread

Everything is written to /p/tmp/jamirp/X_explore/b4_*.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

OUT = "/p/tmp/jamirp/X_explore"
TBL = "/p/tmp/jamirp/emulator_global/tables"
G = "/p/projects/waldspektrum/priesner/clustering/global"
NCELL = 67420

HIST1 = (
    f"{G}/Historical/ground_truth/model_output/"
    "transient_2000_2019_npatch25_nspinup1000_nspinyear30_random_seed1"
)
HIST2 = (
    f"{G}/Historical/ground_truth/model_output/"
    "transient_2000_2019_npatch25_nspinup1000_nspinyear30_random_seed2"
)
S370_1 = f"{G}/ssp370/ground_truth/model_output/transient_2020_2100_npatch25_random_seed1"
S370_2 = (
    f"{G}/ssp370/ground_truth/model_output/"
    "transient_2020_2100_npatch25_random_seed2_from_hist_seed2"
)
S370_FAKE = f"{G}/ssp370/ground_truth/model_output/transient_2020_2100_npatch25_random_seed2"
S126_1 = f"{G}/ssp126/ground_truth/model_output/transient_2020_2100_npatch25_random_seed1"
S126_2 = f"{G}/ssp126/ground_truth/model_output/transient_2020_2100_npatch25_random_seed2"

RUNS = {
    ("historic", 1): HIST1,
    ("historic", 2): HIST2,
    ("ssp370", 1): S370_1,
    ("ssp370", 2): S370_2,
    ("ssp126", 1): S126_1,
    ("ssp126", 2): S126_2,
}
VEGC = {
    ("historic", 1): f"{HIST1}/output/vegc_2000_2019.nc",
    ("historic", 2): f"{HIST2}/output/vegc_2000_2019.nc",
    ("ssp370", 1): f"{S370_1}/output/vegc_2020_2100.nc",
    ("ssp370", 2): f"{S370_2}/output/vegc_2020_2100.nc",
    ("ssp126", 1): f"{S126_1}/output/vegc_2020_2100.nc",
    ("ssp126", 2): f"{S126_2}/output/vegc_2020_2100.nc",
}
IND126 = {
    1: f"{S126_1}/output/ind_2020_2100.csv",
    2: f"{S126_2}/output/ind_2020_2100.csv",
}
IND_HIST = {
    1: f"{HIST1}/output/ind_2000_2019.csv",
    2: f"{HIST2}/output/ind_2000_2019.csv",
}

# The three legs' forcing .clm (all orderA, 67420 cells, 365 noleap bands, MIXED v2-int16-scalar-0.1
# / v3-float32 -- read header-driven, never with a hardcoded dtype).
CLM3 = {
    "historic": {
        "tas": f"{G}/temperature_test.clm",
        "pr": f"{G}/precipitation_test.clm",
        "rsds": f"{G}/short_wave_radiation_test.clm",
        "huss": f"{G}/humid_test.clm",
    },
    "ssp370": {
        "tas": f"{G}/ssp370/tas_mpi-esm1-2-hr_ssp370_2015-2100_orderA.clm",
        "pr": f"{G}/ssp370/pr_mpi-esm1-2-hr_ssp370_2015-2100_orderA.clm",
        "rsds": f"{G}/ssp370/rsds_mpi-esm1-2-hr_ssp370_2015-2100_orderA.clm",
        "huss": f"{G}/ssp370/huss_mpi-esm1-2-hr_ssp370_2015-2100_orderA.clm",
    },
    "ssp126": {
        "tas": f"{G}/ssp126/tas_mpi-esm1-2-hr_ssp126_2015-2100_orderA.clm",
        "pr": f"{G}/ssp126/pr_mpi-esm1-2-hr_ssp126_2015-2100_orderA.clm",
        "rsds": f"{G}/ssp126/rsds_mpi-esm1-2-hr_ssp126_2015-2100_orderA.clm",
        "huss": f"{G}/ssp126/huss_mpi-esm1-2-hr_ssp126_2015-2100_orderA.clm",
    },
}

# (leg, window label, y0, y1).  hist is the BASELINE window every response is measured against.
WINDOWS = [
    ("historic", "hist_2000_2019", 2000, 2019),
    ("ssp370", "s370_2020_2039", 2020, 2039),
    ("ssp370", "s370_2080_2099", 2080, 2099),
    ("ssp126", "s126_2020_2039", 2020, 2039),
    ("ssp126", "s126_2080_2099", 2080, 2099),
]
BASE_W = "hist_2000_2019"

CLIM_FEATS = [
    "tas_wmean_degC", "pr_wmean_mm_yr", "rsds_wmean", "huss_wmean",
    "tas_cold_month", "tas_warm_month", "tas_seasonality", "gdd5", "frostdays",
]
ADDR_FEATS = ["geo_x", "geo_y", "geo_z", "lat"]
SOIL_FEATS = ["soil_code"]

_MONTH_EDGES = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def _say(m: str = "") -> None:
    print(m, flush=True)


def _dt(t0: float) -> str:
    return f"{time.time() - t0:.1f}s"


# =================================================================================================
# PRE-REGISTRATION -- printed before ANY result is computed, in every stage.
# =================================================================================================
PREREG = r"""
=================================================================================================
B4 PRE-REGISTRATION  (printed before any result is computed; verbatim in the final report)
=================================================================================================

QUESTION
  A third LPJmL-FIT forcing leg exists (ssp126, both members, complete 2026-08-18) and is recorded
  nowhere.  Historic + ssp370 BRACKET it.  Fitting a DIRECT (non-autoregressive) map
  climate-window-climatology -> 20-year-window forest state on historic + ssp370 only, does that
  map carry a transferable climate response to the unseen ssp126 leg?

BLESSED STATISTIC
  Per-cell RESPONSE R^2 on vegetation carbon:
      truth  dV126(cell) = VegC(ssp126, 2080-2099) - VegC(historic, 2000-2019)      [gC/m2]
      pred   dV126_hat   = f(clim(ssp126,2080-2099), cell) - f(clim(historic,2000-2019), cell)
  with the SAME fitted f producing both terms, so anything static in the cell (its address, its
  soil) cancels exactly in the difference.  Universe: ALL cells with finite VegC in every leg --
  NO inner join across windows or legs (B3 lost 4635 treeline cells to one).  Truth uses the
  two-member mean.  Secondary statistics: Pearson r, through-origin slope, and the fraction of
  cells inside the acceptance tolerance max(10% of |truth|, the leg's own two-member spread).
  Cross-validation: 5 spatially BLOCKED folds (15 deg lon x 5 deg lat blocks, TWO independent
  colourings), so a cell's ssp126 prediction comes from a model that never saw that cell in ANY
  window (ADR 0040's lesson: a hashed fold makes a pure geographic address score 0.84 instead of
  0.14-0.21).

NULLS, AND THE VALUE EACH MUST RETURN -- DERIVED BEFORE THE RUN
  N1  ADDRESS-ONLY.  Features = geo_x, geo_y, geo_z, lat and NOTHING else, fitted on the same rows
      as the treatment.  Its features do not depend on the window, so its two predictions are the
      SAME NUMBER and its predicted response is IDENTICALLY 0.000000 for every cell.
      MUST RETURN: max |dV126_hat| = 0 exactly, and a response R^2 EQUAL TO N2's to machine
      precision.  This is a free harness check: if N1 != N2 the difference-of-two-predictions
      construction is broken.
  N2  ZERO-RESPONSE (do nothing).  dV126_hat = 0 for every cell.
      MUST RETURN: R^2 = 1 - SUM(dV^2)/SUM((dV-mean(dV))^2) = -n*mean(dV)^2/SS_tot, i.e.
      NECESSARILY <= 0, and exactly 0 only if the global mean response is exactly 0.  Its
      correlation with truth is undefined (a constant), reported as nan.
  N3  GLOBAL MEMORISATION.  dV126_hat = k_glob * dV370_truth, k_glob = the global-mean warming
      ratio dTbar(ssp126)/dTbar(ssp370) on the COMMON historic baseline (ADR 0310 reports 0.227;
      recomputed here from the .clm and reported).  A model that memorised the ssp370 response
      pattern and rescaled it EQUALS this null.  A model that learned a climate response must
      BEAT it.  MUST RETURN: slope ~1 against truth if and only if the two legs' VegC responses
      are proportional; its R^2 is not derivable a priori and is reported.
  N3b LOCAL MEMORISATION.  dV126_hat = (dT_cell(ssp126)/dT_cell(ssp370)) * dV370_truth, the ratio
      clipped to [-2, 2] and set to 0 where |dT_cell(ssp370)| < 0.25 K.  Strictly stronger than N3.
  N4  LEVEL-PERSISTENCE (for the LEVEL score only, which is NOT the blessed statistic).
      VegC_hat(window) = VegC(historic).  MUST RETURN: level R^2 far above 0 (vegetation carbon is
      dominated by where the cell is), which is exactly why the LEVEL score must not be quoted.
  P   PROVENANCE BOUND (a null on the confound, not on skill).  ssp126 ran on an Aug-12-2026
      executable; historic and ssp370 seed1 on Feb-5-2026; the valid ssp370 seed2 on Jul-21-2026.
      The two-member spread within a BUILD-MATCHED pair (historic Feb5/Feb5, ssp126 Aug12/Aug12)
      versus within the CROSS-BUILD pair (ssp370 Feb5/Jul21) bounds the rebuild effect.
      MUST RETURN: if the rebuilds are physics-inert, ssp370's two-member spread must NOT be
      systematically larger than the two build-matched legs' spreads.  If it IS materially larger,
      the leg comparison is confounded and I say so.

FALSIFIER  (the margin below which I conclude the map learned NO transferable climate response)
  The map has learned a transferable climate response ONLY IF its held-out ssp126 response R^2
  exceeds BOTH
      (a) the zero-response null N2 by >= 0.05 absolute, AND
      (b) the better of the memorisation nulls N3 / N3b by >= 0.05 absolute,
  on the blocked-fold, all-cell, per-cell basis, on BOTH fold colourings.  If either margin is
  below 0.05 I report NO transferable response.  Additionally, the target is only SCOREABLE if the
  two-member noise floor is small against the signal: median(two-member spread of dV126) /
  median(|dV126|) must be < 0.5.  If it is not, no verdict is possible and I say that instead.

TRAPS I AM EXPLICITLY GUARDING
  * The acceptance basis is PER CELL over all cells, both scenarios and the response between them
    (ADR 0106).  No area-weighted global aggregate appears in any acceptance criterion and none is
    quoted as one here.
  * The incumbent is LPJmL-FIT itself; no speed or fidelity comparison against it is made here.
  * NEVER cmp a NetCDF -- LPJmL writes a wall-clock timestamp into `history`; only DECODED
    variables are compared.
  * NEVER judge a C run from SLURM state -- the stock job files always exit 0; the required
    evidence is the line "lpjml successfully terminated, 67420 grid cells processed." in a
    NON-EMPTY log resolved as the newest non-empty lpjml_*.out in the run dir.
=================================================================================================
"""


# =================================================================================================
# helpers
# =================================================================================================
def _latlon() -> pl.DataFrame:
    cells, lats, lons = [], [], []
    with open(f"{TBL}/cell_latlon.txt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.split()
            if len(p) < 5:
                continue
            cells.append(int(p[0]))
            lats.append(float(p[3]))
            lons.append(float(p[4]))
    rlat = np.radians(np.asarray(lats))
    rlon = np.radians(np.asarray(lons))
    return pl.DataFrame({
        "Cell": np.asarray(cells, dtype=np.int64),
        "lat": np.asarray(lats), "lon": np.asarray(lons),
        "geo_x": np.cos(rlat) * np.cos(rlon),
        "geo_y": np.cos(rlat) * np.sin(rlon),
        "geo_z": np.sin(rlat),
    })


def _blocked_fold(lat: np.ndarray, lon: np.ndarray, salt: str, k: int = 5) -> np.ndarray:
    """15 deg lon x 5 deg lat blocks -> one of k folds, by a salted hash of the block id."""
    bl = np.floor((lat + 90.0) / 5.0).astype(np.int64)
    bo = np.floor((lon + 180.0) / 15.0).astype(np.int64)
    out = np.empty(len(lat), dtype=np.int64)
    cache: dict[tuple[int, int], int] = {}
    for i in range(len(lat)):
        key = (int(bl[i]), int(bo[i]))
        f = cache.get(key)
        if f is None:
            h = hashlib.sha256(f"{salt}|{key[0]}|{key[1]}".encode()).hexdigest()
            f = int(h[:8], 16) % k
            cache[key] = f
        out[i] = f
    return out


def _r2(y: np.ndarray, p: np.ndarray) -> float:
    ss_res = float(np.sum((y - p) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def _corr(y: np.ndarray, p: np.ndarray) -> float:
    if np.std(p) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def _slope0(y: np.ndarray, p: np.ndarray) -> float:
    d = float(np.sum(p * p))
    return float(np.sum(y * p) / d) if d > 0 else float("nan")


# =================================================================================================
# STAGE prov
# =================================================================================================
def _newest_nonempty_log(run: str) -> str | None:
    best, bestm = None, -1.0
    for fn in os.listdir(run):
        if not (fn.startswith("lpjml") and fn.endswith(".out")):
            continue
        p = os.path.join(run, fn)
        if os.path.getsize(p) == 0:
            continue
        m = os.path.getmtime(p)
        if m > bestm:
            best, bestm = p, m
    return best


def stage_prov() -> None:
    _say("\n### STAGE prov -- provenance gate on all six members (+ the invalid one)")
    rows = []
    allruns = dict(RUNS)
    allruns[("ssp370_FAKE", 2)] = S370_FAKE
    for (leg, seed), run in sorted(allruns.items()):
        log = _newest_nonempty_log(run)
        rec = {"leg": leg, "seed": seed, "run": run, "log": os.path.basename(log or "NONE"),
               "log_bytes": os.path.getsize(log) if log else 0}
        if log is None:
            rec.update(build="NO NON-EMPTY LOG", ntasks="?", done="FATAL: 0-byte log only",
                       seedline="?")
        else:
            txt = open(log, errors="replace").read()
            mb = re.search(r"lpjml C Version ([0-9.]+) \(([^)]+)\)", txt)
            mt = re.search(r"running on (\d+) tasks", txt)
            md = re.search(r"lpjml successfully terminated, (\d+) grid cells processed", txt)
            ms = re.search(r"(Random seed: \d+|Reading random seeds from restart file\.)", txt)
            rec.update(
                build=(mb.group(2) if mb else "?"),
                version=(mb.group(1) if mb else "?"),
                ntasks=(mt.group(1) if mt else "?"),
                done=(f"OK {md.group(1)} cells" if md else "MISSING completion line"),
                seedline=(ms.group(1) if ms else "?"),
            )
        cfgs = []
        sd = os.path.join(run, "scripts_for_running_the_model")
        if os.path.isdir(sd):
            cfgs = sorted(os.listdir(sd))
        rec["cfg_files"] = ";".join(cfgs)
        # restart lineage + the two opt-in env switches
        restart, rseed, newseed = "?", "?", "?"
        envsw = []
        for fn in cfgs:
            p = os.path.join(sd, fn)
            try:
                t = open(p, errors="replace").read()
            except OSError:
                continue
            if fn.endswith(".js"):
                m = re.search(r'"restart_filename"\s*:\s*"([^"]+)"', t)
                if m:
                    restart = m.group(1)
                m = re.search(r'"random_seed"\s*:\s*(\d+)', t)
                if m:
                    rseed = m.group(1)
                m = re.search(r'"new_seed"\s*:\s*(true|false)', t)
                if m:
                    newseed = m.group(1)
            for sw in ("LPJ_RUNG2_DIR", "LPJ_RUNG2_APPLY_DIR", "LPJ_IND_TRUE_GPP",
                       "LPJ_IND_ALL_HEIGHTS"):
                if sw in t:
                    envsw.append(f"{fn}:{sw}")
        rec["restart_from"] = restart.replace(G + "/", "")
        rec["random_seed"] = rseed
        rec["new_seed"] = newseed
        rec["optin_env_switches"] = ";".join(envsw) if envsw else "NONE"
        # the forcing the run actually read
        forc = []
        ip = os.path.join(sd, "input_2020_2100.js")
        if not os.path.exists(ip):
            for fn in cfgs:
                if fn.startswith("input"):
                    ip = os.path.join(sd, fn)
        if os.path.exists(ip):
            t = open(ip, errors="replace").read()
            for k in ("temp", "prec", "rsds", "swdown", "humid", "lwnet", "co2"):
                m = re.search(r'"' + k + r'"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', t)
                if m:
                    forc.append(f"{k}={os.path.basename(m.group(1))}")
        rec["forcing"] = ";".join(forc)
        ind = os.path.join(run, "output", "ind_2000_2019.csv")
        if not os.path.exists(ind):
            ind = os.path.join(run, "output", "ind_2020_2100.csv")
        rec["ind_bytes"] = os.path.getsize(ind) if os.path.exists(ind) else 0
        vp = VEGC.get((leg, seed))
        rec["vegc_bytes"] = os.path.getsize(vp) if vp and os.path.exists(vp) else 0
        rows.append(rec)
        _say(f"  {leg:12s} seed{seed}  build={rec['build']:12s} ntasks={rec['ntasks']:>5s}  "
             f"{rec['done']}")
        _say(f"      log={rec['log']} ({rec['log_bytes']} B)  seedline='{rec['seedline']}'")
        _say(f"      random_seed={rec['random_seed']} new_seed={rec['new_seed']} "
             f"restart_from={rec['restart_from']}")
        _say(f"      opt-in env switches in config/jcf: {rec['optin_env_switches']}")
        _say(f"      forcing: {rec['forcing']}")
        _say(f"      ind={rec['ind_bytes']} B  vegc={rec['vegc_bytes']} B")
    t = pl.DataFrame(rows)
    t.write_csv(f"{OUT}/b4_provenance.csv")
    _say(f"\n  WROTE {OUT}/b4_provenance.csv")

    _say("\n  -- byte-size clone check (the ADR-0041 fake-seed signature is EQUAL file size) --")
    for leg in ("historic", "ssp370", "ssp126"):
        a = t.filter((pl.col("leg") == leg) & (pl.col("seed") == 1))["ind_bytes"][0]
        b = t.filter((pl.col("leg") == leg) & (pl.col("seed") == 2))["ind_bytes"][0]
        _say(f"    {leg:9s} ind bytes s1={a} s2={b} diff={a - b} -> "
             f"{'CLONE SUSPECT' if a == b else 'distinct'}")
    a = t.filter(pl.col("leg") == "ssp370_FAKE")["ind_bytes"][0]
    b = t.filter((pl.col("leg") == "ssp370") & (pl.col("seed") == 1))["ind_bytes"][0]
    _say(f"    the KNOWN-INVALID ssp370 'seed2' vs ssp370 seed1: {a} vs {b} diff={a - b} "
         f"-> {'CLONE (as documented)' if a == b else 'unexpected'}")


# =================================================================================================
# STAGE clim
# =================================================================================================
def _clm_window_stats(paths: dict[str, str], y0: int, y1: int) -> dict[str, np.ndarray]:
    from build_transient_boundary import open_clm  # noqa: PLC0415

    out: dict[str, np.ndarray] = {}
    mm, fy, ncell, nb, sc = open_clm(paths["tas"])
    if nb != 365 or ncell != NCELL:
        raise SystemExit(f"FATAL: {paths['tas']} nbands={nb} ncell={ncell}")
    i0, i1 = y0 - fy, y1 - fy
    if i0 < 0 or i1 >= mm.shape[0]:
        raise SystemExit(f"FATAL: {paths['tas']} covers {fy}..{fy + mm.shape[0] - 1}")
    n = i1 - i0 + 1
    acc = {k: np.zeros(ncell) for k in
           ("tas_wmean_degC", "tas_cold_month", "tas_warm_month", "tas_seasonality",
            "gdd5", "frostdays")}
    for i in range(i0, i1 + 1):
        yr = np.asarray(mm[i], dtype=np.float64) * sc
        mon = np.stack([yr[:, _MONTH_EDGES[m]:_MONTH_EDGES[m + 1]].mean(axis=1)
                        for m in range(12)], axis=1)
        acc["tas_wmean_degC"] += yr.mean(axis=1)
        acc["tas_cold_month"] += mon.min(axis=1)
        acc["tas_warm_month"] += mon.max(axis=1)
        acc["tas_seasonality"] += mon.max(axis=1) - mon.min(axis=1)
        acc["gdd5"] += np.maximum(yr - 5.0, 0.0).sum(axis=1)
        acc["frostdays"] += (yr < 0.0).sum(axis=1)
    out.update({k: v / n for k, v in acc.items()})
    for var, mode, name in (("pr", "sum", "pr_wmean_mm_yr"), ("rsds", "mean", "rsds_wmean"),
                            ("huss", "mean", "huss_wmean")):
        mm, fy, ncell, nb, sc = open_clm(paths[var])
        i0, i1 = y0 - fy, y1 - fy
        a = np.zeros(ncell)
        for i in range(i0, i1 + 1):
            yr = np.asarray(mm[i], dtype=np.float64) * sc
            a += yr.sum(axis=1) if mode == "sum" else yr.mean(axis=1)
        out[name] = a / (i1 - i0 + 1)
    return out


def stage_clim() -> str:
    out = f"{OUT}/b4_cell_window_clim3.parquet"
    _say("\n### STAGE clim -- per-cell window climatology, ALL THREE legs, identical code")
    geo = _latlon()
    soil = (
        pl.scan_parquet(f"{TBL}/cell_year_feats.parquet")
        .filter(pl.col("Year") == 2000).select(["Cell", "soil_code"]).collect()
    )
    rows = []
    for leg, wlab, y0, y1 in WINDOWS:
        t0 = time.time()
        st = _clm_window_stats(CLM3[leg], y0, y1)
        d = (
            pl.DataFrame({"Cell": np.arange(NCELL, dtype=np.int64), **st})
            .join(geo, on="Cell", how="left", validate="1:1")
            .join(soil, on="Cell", how="left", validate="1:1")
            .with_columns(pl.lit(leg).alias("leg"), pl.lit(wlab).alias("window"),
                          pl.lit(y0, dtype=pl.Int32).alias("y0"),
                          pl.lit(y1, dtype=pl.Int32).alias("y1"))
        )
        rows.append(d)
        _say(f"  {wlab:16s} ({_dt(t0)})  tas={st['tas_wmean_degC'].mean():.4f} degC  "
             f"pr={st['pr_wmean_mm_yr'].mean():.1f} mm/yr  gdd5={st['gdd5'].mean():.1f}  "
             f"cold={st['tas_cold_month'].mean():.3f}  frost={st['frostdays'].mean():.1f}")
    tbl = pl.concat(rows, how="vertical").sort(["Cell", "window"])
    if tbl.select(["Cell", "window"]).n_unique() != tbl.height:
        raise SystemExit("FATAL: duplicate (Cell, window)")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    _say(f"  WROTE {out} rows={tbl.height} cols={tbl.width} "
         f"({os.path.getsize(out) / 1e6:.1f} MB)")

    base = tbl.filter(pl.col("window") == BASE_W).select(["Cell", "tas_wmean_degC"]).rename(
        {"tas_wmean_degC": "tas_base"})
    _say("\n  -- the leg AMPLITUDES on the COMMON historic 2000-2019 baseline (unweighted "
         "mean over all 67420 cells; NOT an acceptance basis) --")
    amp = {}
    for wlab in ("s370_2020_2039", "s370_2080_2099", "s126_2020_2039", "s126_2080_2099"):
        j = tbl.filter(pl.col("window") == wlab).select(["Cell", "tas_wmean_degC"]).join(
            base, on="Cell", validate="1:1")
        d = (j["tas_wmean_degC"] - j["tas_base"]).to_numpy()
        amp[wlab] = d
        _say(f"    {wlab:16s} dT = {d.mean():+.4f} K   median {np.median(d):+.4f}   "
             f"cooling cells {100.0 * (d < 0).mean():.2f} %")
    k = amp["s126_2080_2099"].mean() / amp["s370_2080_2099"].mean()
    a126, a370 = amp["s126_2080_2099"], amp["s370_2080_2099"]
    pc = float(np.corrcoef(a126, a370)[0, 1])
    pcd = float(np.corrcoef(a126 - a126.mean(), a370 - a370.mean())[0, 1])
    _say(f"    => k_glob (ssp126/ssp370 late dT, common baseline) = {k:.4f}")
    _say(f"       per-cell dT correlation between the legs, RAW  r = {pc:.4f}  "
         f"(includes each leg's global mean warming)")
    _say(f"       per-cell dT correlation, each leg DEMEANED     r = {pcd:.4f}  "
         "(the pattern proper -- this is the number a memorisation null lives on)")
    _say("       NOTE: on a 2020s->2090s baseline instead of the common historic one the same "
         "two legs give a much smaller ssp126 amplitude; the criterion-relevant convention is "
         "the COMMON baseline, which is what is used above and everywhere below.")
    d2 = amp["s126_2080_2099"] - amp["s126_2020_2039"]
    d3 = amp["s370_2080_2099"] - amp["s370_2020_2039"]
    _say(f"       for the record, the 2020s->2090s convention: ssp126 dT = {d2.mean():+.4f} K, "
         f"ssp370 dT = {d3.mean():+.4f} K, ratio {d2.mean() / d3.mean():.4f}, "
         f"ssp126 cooling cells {100.0 * (d2 < 0).mean():.2f} %")
    return out


# =================================================================================================
# STAGE vegc
# =================================================================================================
def stage_vegc() -> str:
    import netCDF4 as nc  # noqa: PLC0415

    out = f"{OUT}/b4_cell_window_vegc.parquet"
    _say("\n### STAGE vegc -- per-cell window vegetation carbon, 3 legs x 2 members")
    geo = _latlon()
    lat0 = geo["lat"].to_numpy()
    lon0 = geo["lon"].to_numpy()
    cells = geo["Cell"].to_numpy()

    rows = []
    ilat = ilon = None
    for (leg, seed), path in sorted(VEGC.items()):
        d = nc.Dataset(path)
        v = d.variables["VegC"]
        la = d.variables["lat"][:].astype(float)
        lo = d.variables["lon"][:].astype(float)
        t = d.variables["time"]
        yr0 = int(re.search(r"since (\d+)", t.units).group(1))
        nyr = v.shape[0]
        if ilat is None:
            ilat = np.rint((lat0 - la[0]) / (la[1] - la[0])).astype(int)
            ilon = np.rint((lon0 - lo[0]) / (lo[1] - lo[0])).astype(int)
            if ilat.min() < 0 or ilat.max() >= len(la) or ilon.min() < 0 \
                    or ilon.max() >= len(lo):
                raise SystemExit("FATAL: orderA cell falls outside the vegc grid")
            back_lat = la[ilat]
            back_lon = lo[ilon]
            e = max(np.abs(back_lat - lat0).max(), np.abs(back_lon - lon0).max())
            _say(f"  grid map gate: orderA cell -> (ilat,ilon) round-trip max |dlat|,|dlon| = "
                 f"{e:.6f} deg (must be 0 at 0.5 deg cell centres)")
            if e > 1e-9:
                raise SystemExit("FATAL: grid map round-trip nonzero")
        arr = np.asarray(v[:], dtype=np.float64)
        fill = float(getattr(v, "_FillValue", -1e32))
        arr = np.where(arr <= fill / 2, np.nan, arr)
        ser = arr[:, ilat, ilon]  # (nyear, ncell)
        for wleg, wlab, y0, y1 in WINDOWS:
            if wleg != leg:
                continue
            j0, j1 = y0 - yr0, y1 - yr0
            if j0 < 0 or j1 >= nyr:
                raise SystemExit(f"FATAL: {path} covers {yr0}..{yr0 + nyr - 1}, need {y0}..{y1}")
            w = np.nanmean(ser[j0:j1 + 1], axis=0)
            rows.append(pl.DataFrame({
                "Cell": cells, "leg": leg, "seed": seed, "window": wlab,
                "vegc": w, "n_finite": np.isfinite(ser[j0:j1 + 1]).sum(axis=0),
            }))
            _say(f"  {leg:9s} s{seed} {wlab:16s} mean={np.nanmean(w):9.2f} gC/m2  "
                 f"finite cells={int(np.isfinite(w).sum())}/{NCELL}")
        d.close()
    tbl = pl.concat(rows, how="vertical").sort(["Cell", "window", "seed"])
    if tbl.select(["Cell", "window", "seed"]).n_unique() != tbl.height:
        raise SystemExit("FATAL: duplicate (Cell, window, seed)")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    _say(f"  WROTE {out} rows={tbl.height} ({os.path.getsize(out) / 1e6:.1f} MB)")

    _say("\n  -- NULL P: the two-member spread per leg (BUILD-MATCHED vs CROSS-BUILD) --")
    pv = tbl.pivot(on="seed", index=["Cell", "window"], values="vegc")
    pv = pv.rename({"1": "s1", "2": "s2"})
    for wlab in [w[1] for w in WINDOWS]:
        s = pv.filter(pl.col("window") == wlab)
        a, b = s["s1"].to_numpy(), s["s2"].to_numpy()
        ok = np.isfinite(a) & np.isfinite(b)
        sp = np.abs(a[ok] - b[ok])
        lv = 0.5 * (a[ok] + b[ok])
        rel = sp / np.maximum(np.abs(lv), 1.0)
        tag = {"hist_2000_2019": "Feb5/Feb5 MATCHED",
               "s370_2020_2039": "Feb5/Jul21 CROSS", "s370_2080_2099": "Feb5/Jul21 CROSS",
               "s126_2020_2039": "Aug12/Aug12 MATCHED",
               "s126_2080_2099": "Aug12/Aug12 MATCHED"}[wlab]
        _say(f"    {wlab:16s} [{tag:18s}] n={int(ok.sum())}  median |s1-s2| = {np.median(sp):8.3f} "
             f"gC/m2  median rel = {np.median(rel):.5f}  p90 rel = "
             f"{np.quantile(rel, 0.9):.5f}")
    return out


# =================================================================================================
# STAGE fit
# =================================================================================================
def _fit_predict(train_x, train_y, pred_sets, seed=0):
    import lightgbm as lgb  # noqa: PLC0415

    m = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=40,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=seed,
        n_jobs=int(os.environ.get("OMP_NUM_THREADS", "16")), verbose=-1,
    )
    m.fit(train_x, train_y)
    return [m.predict(x) for x in pred_sets]


def stage_fit() -> None:
    _say("\n### STAGE fit -- the pre-registered held-out-leg experiment")
    clim = pl.read_parquet(f"{OUT}/b4_cell_window_clim3.parquet")
    vg = pl.read_parquet(f"{OUT}/b4_cell_window_vegc.parquet")
    tgt = (
        vg.group_by(["Cell", "window", "leg"])
        .agg(pl.col("vegc").mean().alias("vegc"), pl.len().alias("nseed"))
    )
    if tgt["nseed"].min() != 2:
        raise SystemExit("FATAL: a (Cell, window) has fewer than 2 members")
    df = clim.join(tgt.select(["Cell", "window", "vegc"]), on=["Cell", "window"],
                   how="left", validate="1:1")
    # NO inner join across windows: a cell missing in one window keeps its rows in the others.
    wide = df.pivot(on="window", index="Cell", values="vegc")
    have = np.ones(wide.height, dtype=bool)
    for w in [x[1] for x in WINDOWS]:
        have &= np.isfinite(wide[w].to_numpy())
    keep_cells = wide["Cell"].to_numpy()[have]
    _say(f"  cells with finite VegC in ALL FIVE windows: {len(keep_cells)}/{NCELL} "
         f"(structural-zero universe; nothing dropped by an inner join across seeds/legs)")

    per_seed = vg.pivot(on="seed", index=["Cell", "window"], values="vegc").rename(
        {"1": "s1", "2": "s2"})
    ps = per_seed.pivot(on="window", index="Cell", values=["s1", "s2"])
    ps_cols = ps.columns

    d = df.filter(pl.col("Cell").is_in(pl.Series(keep_cells)))
    lat = d.filter(pl.col("window") == BASE_W)["lat"].to_numpy()
    lon = d.filter(pl.col("window") == BASE_W)["lon"].to_numpy()
    cell_order = d.filter(pl.col("window") == BASE_W)["Cell"].to_numpy()

    def mat(wlab, feats):
        s = d.filter(pl.col("window") == wlab).sort("Cell")
        if not np.array_equal(s["Cell"].to_numpy(), cell_order):
            raise SystemExit("FATAL: cell order mismatch")
        return s.select(feats).to_numpy().astype(np.float64), s["vegc"].to_numpy()

    ARMS = {
        "A_clim":        CLIM_FEATS + SOIL_FEATS,
        "A_clim_addr":   CLIM_FEATS + SOIL_FEATS + ADDR_FEATS,
        "N1_addr_only":  ADDR_FEATS + SOIL_FEATS,
    }
    W_ALL = [x[1] for x in WINDOWS]
    X = {}
    Y = {}
    for wlab in W_ALL:
        for arm, feats in ARMS.items():
            X[(wlab, arm)], Y[wlab] = mat(wlab, feats)

    # truth responses
    dv126 = Y["s126_2080_2099"] - Y[BASE_W]
    dv370 = Y["s370_2080_2099"] - Y[BASE_W]
    dv126e = Y["s126_2020_2039"] - Y[BASE_W]

    # per-seed spread of the RESPONSE dv126 (the acceptance tolerance denominator)
    def col(w, s):
        nm = f'{{"{s}","{w}"}}' if f'{{"{s}","{w}"}}' in ps_cols else None
        for c in ps_cols:
            if c == "Cell":
                continue
            if w in c and s in c:
                nm = c
        return nm
    idx = {int(c): i for i, c in enumerate(ps["Cell"].to_numpy())}
    order_idx = np.array([idx[int(c)] for c in cell_order])
    sp = {}
    for s in ("s1", "s2"):
        c126 = col("s126_2080_2099", s)
        chist = col(BASE_W, s)
        sp[s] = (ps[c126].to_numpy()[order_idx] - ps[chist].to_numpy()[order_idx])
    seed_spread = np.abs(sp["s1"] - sp["s2"])
    ratio = np.median(seed_spread) / max(np.median(np.abs(dv126)), 1e-12)
    _say(f"\n  -- SCOREABILITY: dv126 median |truth| = {np.median(np.abs(dv126)):.3f} gC/m2, "
         f"median two-member spread = {np.median(seed_spread):.3f} -> ratio = {ratio:.4f} "
         f"({'SCOREABLE (<0.5)' if ratio < 0.5 else 'NOT SCOREABLE (>=0.5)'})")
    _say(f"     dv370 median |truth| = {np.median(np.abs(dv370)):.3f} gC/m2")
    _say(f"     mean dv126 = {dv126.mean():+.3f}   mean dv370 = {dv370.mean():+.3f} gC/m2")
    r_leg = float(np.corrcoef(dv126, dv370)[0, 1])
    r_legd = float(np.corrcoef(dv126 - dv126.mean(), dv370 - dv370.mean())[0, 1])
    _say(f"     per-cell VegC response correlation between the two legs: RAW r = {r_leg:.4f}, "
         f"DEMEANED r = {r_legd:.4f}")
    _say(f"     sign disagreement: {100.0 * np.mean(np.sign(dv126) != np.sign(dv370)):.2f} % of "
         "cells have OPPOSITE-SIGN VegC responses in the two legs")

    # k_glob from the climatology (recomputed, not taken from the record)
    tb = d.filter(pl.col("window") == BASE_W).sort("Cell")["tas_wmean_degC"].to_numpy()
    t126 = d.filter(pl.col("window") == "s126_2080_2099").sort("Cell")[
        "tas_wmean_degC"].to_numpy()
    t370 = d.filter(pl.col("window") == "s370_2080_2099").sort("Cell")[
        "tas_wmean_degC"].to_numpy()
    dt126, dt370 = t126 - tb, t370 - tb
    k_glob = float(dt126.mean() / dt370.mean())
    _say(f"     k_glob = {k_glob:.4f} (recomputed on the kept cells)")

    # nulls that need no fit
    n2 = np.zeros_like(dv126)
    n3 = k_glob * dv370
    rr = np.clip(np.where(np.abs(dt370) < 0.25, 0.0, dt126 / np.where(dt370 == 0, 1, dt370)),
                 -2, 2)
    n3b = rr * dv370

    res = []

    def score(name, arm, colour, y, p, extra=""):
        r = {"target": name, "arm": arm, "colouring": colour, "n_cells": len(y),
             "R2": _r2(y, p), "r": _corr(y, p), "slope0": _slope0(y, p),
             "mae": float(np.mean(np.abs(y - p))),
             "median_abs_err": float(np.median(np.abs(y - p))),
             "note": extra}
        tol = np.maximum(0.10 * np.abs(y), seed_spread) if name == "dv126_late" else \
            np.maximum(0.10 * np.abs(y), 0.0)
        r["frac_within_tol"] = float(np.mean(np.abs(y - p) <= tol))
        res.append(r)
        _say(f"    {name:12s} {arm:22s} {colour:6s}  R2={r['R2']:+8.4f}  r={r['r']:+7.4f}  "
             f"slope0={r['slope0']:+8.4f}  medAE={r['median_abs_err']:8.2f}  "
             f"within-tol={r['frac_within_tol']:.4f}  {extra}")

    _say("\n  -- NULLS THAT NEED NO FIT (target dv126_late) --")
    score("dv126_late", "N2_zero_response", "n/a", dv126, n2,
          "must be <=0 by construction")
    score("dv126_late", "N3_global_memorise", "n/a", dv126, n3, f"k_glob={k_glob:.4f}")
    score("dv126_late", "N3b_local_memorise", "n/a", dv126, n3b, "")

    _say("\n  -- TREATMENT + N1, blocked folds, two colourings --")
    for colour in ("saltA", "saltB"):
        fold = _blocked_fold(lat, lon, colour, 5)
        nb = len(set(zip(np.floor((lat + 90) / 5).astype(int),
                         np.floor((lon + 180) / 15).astype(int), strict=True)))
        _say(f"   {colour}: {nb} populated 15x5 deg blocks -> 5 folds, sizes "
             f"{[int((fold == f).sum()) for f in range(5)]}")
        for arm in ARMS:
            # PRIMARY: fit on historic + ssp370 rows only
            pred = {w: np.full(len(dv126), np.nan) for w in W_ALL}
            for f in range(5):
                tr = fold != f
                te = fold == f
                xs = [X[(w, arm)][tr] for w in (BASE_W, "s370_2020_2039", "s370_2080_2099")]
                ys = [Y[w][tr] for w in (BASE_W, "s370_2020_2039", "s370_2080_2099")]
                tx = np.concatenate(xs, axis=0)
                ty = np.concatenate(ys, axis=0)
                outs = _fit_predict(tx, ty, [X[(w, arm)][te] for w in W_ALL])
                for w, o in zip(W_ALL, outs, strict=True):
                    pred[w][te] = o
            p126 = pred["s126_2080_2099"] - pred[BASE_W]
            p370 = pred["s370_2080_2099"] - pred[BASE_W]
            p126e = pred["s126_2020_2039"] - pred[BASE_W]
            if arm == "N1_addr_only":
                mx = float(np.max(np.abs(p126)))
                _say(f"    N1 harness check: max |predicted response| = {mx:.3e} "
                     f"(pre-registered: exactly 0)")
            score("dv126_late", f"{arm}|fit_hist+370", colour, dv126, p126)
            score("dv126_early", f"{arm}|fit_hist+370", colour, dv126e, p126e)
            score("dv370_late(in-dist)", f"{arm}|fit_hist+370", colour, dv370, p370,
                  "IN-distribution leg, for contrast")
            score("level_s126_late", f"{arm}|fit_hist+370", colour,
                  Y["s126_2080_2099"], pred["s126_2080_2099"],
                  "LEVEL score -- not the blessed statistic")
        # N4: level persistence
        score("level_s126_late", "N4_level_persistence", colour, Y["s126_2080_2099"], Y[BASE_W],
              "why the LEVEL score must not be quoted")

        # SECONDARY: fit on historic ONLY (genuine extrapolation)
        for arm in ("A_clim", "A_clim_addr"):
            pred = {w: np.full(len(dv126), np.nan) for w in W_ALL}
            for f in range(5):
                tr = fold != f
                te = fold == f
                outs = _fit_predict(X[(BASE_W, arm)][tr], Y[BASE_W][tr],
                                    [X[(w, arm)][te] for w in W_ALL])
                for w, o in zip(W_ALL, outs, strict=True):
                    pred[w][te] = o
            score("dv126_late", f"{arm}|fit_hist_ONLY", colour, dv126,
                  pred["s126_2080_2099"] - pred[BASE_W])
            score("dv370_late(extrap)", f"{arm}|fit_hist_ONLY", colour, dv370,
                  pred["s370_2080_2099"] - pred[BASE_W])

    rt = pl.DataFrame(res)
    rt.write_csv(f"{OUT}/b4_fit_results.csv")
    _say(f"\n  WROTE {OUT}/b4_fit_results.csv  ({rt.height} rows)")

    _say("\n  -- VERDICT AGAINST THE PRE-REGISTERED FALSIFIER --")
    n2r = rt.filter(pl.col("arm") == "N2_zero_response")["R2"][0]
    n3r = max(rt.filter(pl.col("arm") == "N3_global_memorise")["R2"][0],
              rt.filter(pl.col("arm") == "N3b_local_memorise")["R2"][0])
    for arm in ("A_clim|fit_hist+370", "A_clim_addr|fit_hist+370"):
        for colour in ("saltA", "saltB"):
            r = rt.filter((pl.col("target") == "dv126_late") & (pl.col("arm") == arm)
                          & (pl.col("colouring") == colour))["R2"][0]
            _say(f"    {arm} {colour}: R2={r:+.4f}  margin over N2={r - n2r:+.4f}  "
                 f"margin over best memorisation null={r - n3r:+.4f}  -> "
                 f"{'LEARNED' if (r - n2r >= 0.05 and r - n3r >= 0.05) else 'NOT LEARNED'}")

    # per-cell dump for the record
    pl.DataFrame({
        "Cell": cell_order, "lat": lat, "lon": lon,
        "vegc_hist": Y[BASE_W], "vegc_s370_late": Y["s370_2080_2099"],
        "vegc_s126_late": Y["s126_2080_2099"],
        "dv126": dv126, "dv370": dv370, "dv126_seedspread": seed_spread,
        "dt126": dt126, "dt370": dt370,
    }).write_parquet(f"{OUT}/b4_percell_response.parquet", compression="zstd")
    _say(f"  WROTE {OUT}/b4_percell_response.parquet")


# =================================================================================================
# STAGE ind -- the raw ssp126 roster
# =================================================================================================
IND_COLS = ["Year", "ID", "Type", "Height", "Age", "agb", "vegc", "transp", "npp", "gpp",
            "wscal_mean", "SLA", "Longevity", "Wooddens", "LAI", "fpc_ind", "minwscal", "D95",
            "D95max", "beta_root", "k_root", "mort_npp", "mort_age", "mort_water", "mort_temp",
            "mort", "isdead", "Patch", "Cell"]
KEEP = ["Year", "Type", "Height", "agb", "vegc", "npp", "SLA", "Wooddens", "LAI", "fpc_ind",
        "minwscal", "D95max", "mort", "isdead", "Patch", "Cell", "Age", "ID"]
Y0_126, NY_126 = 2020, 81


class _Slice(io.RawIOBase):
    """Bounded reader over [start, end) of a file -- lets pyarrow parse one byte range."""

    def __init__(self, path, start, end):
        self._f = open(path, "rb")
        self._f.seek(start)
        self._left = end - start

    def readable(self):
        return True

    def readinto(self, b):
        if self._left <= 0:
            return 0
        n = min(len(b), self._left)
        mv = memoryview(b)[:n]
        got = self._f.readinto(mv)
        self._left -= got
        return got

    def close(self):
        self._f.close()


def _range_bounds(path, nw):
    sz = os.path.getsize(path)
    with open(path, "rb") as f:
        hdr = len(f.readline())
    edges = [hdr]
    with open(path, "rb") as f:
        for i in range(1, nw):
            p = hdr + (sz - hdr) * i // nw
            f.seek(p)
            f.readline()
            edges.append(f.tell())
    edges.append(sz)
    return [(edges[i], edges[i + 1]) for i in range(nw) if edges[i + 1] > edges[i]]


def _scan_range(args):
    path, start, end, sample_mod = args
    import pyarrow as pa  # noqa: PLC0415
    from pyarrow import csv  # noqa: PLC0415

    ro = csv.ReadOptions(block_size=1 << 26, use_threads=False, column_names=IND_COLS)
    # PIN EVERY dtype. The `ind` TXT writer prints with %g, so a column that is integral in the
    # first 64 MiB block (Wooddens is 0 for grass and 270217 for trees) is INFERRED int64 and then
    # dies on the first real float -- exactly the CLAUDE.md "pin the dtypes" trap, which is what
    # killed the first attempt at CSV column #13 (Wooddens = 71394.7).
    co = csv.ConvertOptions(
        include_columns=KEEP,
        column_types={"Year": pa.int16(), "Type": pa.int8(), "isdead": pa.int8(),
                      "Patch": pa.int16(), "Cell": pa.int32(), "Age": pa.int32(),
                      "ID": pa.int64(), "Height": pa.float32(), "agb": pa.float64(),
                      "vegc": pa.float64(), "npp": pa.float64(), "SLA": pa.float32(),
                      "Wooddens": pa.float32(), "LAI": pa.float32(),
                      "fpc_ind": pa.float32(), "minwscal": pa.float32(),
                      "D95max": pa.float32(), "mort": pa.float32()},
    )
    nb = NY_126 * NCELL
    cnt_live = np.zeros(nb, dtype=np.int32)
    cnt_all = np.zeros(nb, dtype=np.int32)
    agb_live = np.zeros(nb, dtype=np.float64)
    max_patch = -1
    nrows = 0
    samples = []
    r = csv.open_csv(_Slice(path, start, end), read_options=ro, convert_options=co)
    while True:
        try:
            b = r.read_next_batch()
        except StopIteration:
            break
        nrows += b.num_rows
        yr = b.column("Year").to_numpy(zero_copy_only=False).astype(np.int64)
        ce = b.column("Cell").to_numpy(zero_copy_only=False).astype(np.int64)
        ty = b.column("Type").to_numpy(zero_copy_only=False).astype(np.int64)
        de = b.column("isdead").to_numpy(zero_copy_only=False).astype(np.int64)
        pa_ = b.column("Patch").to_numpy(zero_copy_only=False).astype(np.int64)
        ag = b.column("agb").to_numpy(zero_copy_only=False).astype(np.float64)
        key = (yr - Y0_126) * NCELL + ce
        tree = ty <= 6
        live = tree & (de == 0)
        cnt_all += np.bincount(key[tree], minlength=nb).astype(np.int32)
        cnt_live += np.bincount(key[live], minlength=nb).astype(np.int32)
        agb_live += np.bincount(key[live], weights=ag[live], minlength=nb)
        if pa_.size:
            max_patch = max(max_patch, int(pa_.max()))
        if sample_mod > 0:
            m = tree & (ce % sample_mod == 0)
            if m.any():
                samples.append(b.filter(pa.array(m)))
    tb = None
    if samples:
        import pyarrow as pa2  # noqa: PLC0415
        tb = pa2.Table.from_batches(samples)
    return nrows, cnt_live, cnt_all, agb_live, max_patch, tb


def stage_ind(seed: int, nw: int, sample_mod: int) -> None:
    import multiprocessing as mp  # noqa: PLC0415

    path = IND126[seed]
    _say(f"\n### STAGE ind -- ssp126 seed{seed} raw roster scan")
    _say(f"  file={path}  {os.path.getsize(path)} B")
    with open(path) as f:
        hdr = f.readline().strip().split(",")
    _say(f"  header gate: {len(hdr)} columns")
    if hdr != IND_COLS:
        raise SystemExit(f"FATAL: header != frozen 29-col ind schema\n  got {hdr}")
    _say("  header IDENTICAL to the frozen 29-column ind schema, in order -> PASS")
    rngs = _range_bounds(path, nw)
    _say(f"  {len(rngs)} byte ranges over {nw} workers; sample_mod={sample_mod}")
    t0 = time.time()
    nb = NY_126 * NCELL
    cl = np.zeros(nb, dtype=np.int64)
    ca = np.zeros(nb, dtype=np.int64)
    ab = np.zeros(nb, dtype=np.float64)
    gmax_patch = -1
    nrows = 0
    tbs = []
    with mp.get_context("fork").Pool(nw) as pool:
        for i, (n, a, b, c, d, tb) in enumerate(
            pool.imap_unordered(_scan_range,
                                [(path, s, e, sample_mod) for s, e in rngs])
        ):
            nrows += n
            cl += a
            ca += b
            ab += c
            gmax_patch = max(gmax_patch, d)
            if tb is not None:
                tbs.append(tb)
            _say(f"    range {i + 1}/{len(rngs)} done ({_dt(t0)}) rows so far {nrows}")
    _say(f"  max Patch id seen anywhere in the file = {gmax_patch} "
         f"(the run name says npatch25, so 24 is the expected value)")
    dt = time.time() - t0
    gb = os.path.getsize(path) / 1e9
    _say(f"  SCAN DONE {nrows} rows, {gb:.1f} GB in {dt:.1f} s -> {gb / dt * 1000:.0f} MB/s "
         f"aggregate over {nw} workers")
    _say(f"  MEASURED COST of a FULL columnar conversion of this leg: {gb / (gb / dt) / 3600:.3f} "
         f"node-h per seed at {nw} cpus == {nw * dt / 3600:.3f} core-h per seed; "
         f"both seeds = {2 * nw * dt / 3600:.3f} core-h")

    yr = np.repeat(np.arange(Y0_126, Y0_126 + NY_126), NCELL)
    ce = np.tile(np.arange(NCELL), NY_126)
    keep = ca > 0
    cy = pl.DataFrame({
        "seed": np.full(int(keep.sum()), seed, dtype=np.int8),
        "Year": yr[keep].astype(np.int16), "Cell": ce[keep].astype(np.int32),
        "n_trees_live": cl[keep].astype(np.int32), "n_trees_all": ca[keep].astype(np.int32),
        "agb_live_sum": ab[keep],
        "n_patch_obs": np.full(int(keep.sum()), gmax_patch + 1, dtype=np.int16),
    })
    p = f"{OUT}/b4_ssp126_cellyear_s{seed}.parquet"
    cy.write_parquet(p, compression="zstd", statistics=True)
    _say(f"  WROTE {p} rows={cy.height} ({os.path.getsize(p) / 1e6:.1f} MB)")
    if cy.select(["Year", "Cell"]).n_unique() != cy.height:
        raise SystemExit("FATAL: duplicate (Year, Cell)")
    if tbs:
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415
        big = pa.concat_tables(tbs)
        sp = f"{OUT}/b4_ssp126_stems_sample_s{seed}.parquet"
        pq.write_table(big, sp, compression="zstd")
        _say(f"  WROTE {sp} rows={big.num_rows} ({os.path.getsize(sp) / 1e6:.1f} MB)  "
             f"[cells with Cell %% {sample_mod} == 0, trees only]")


def stage_indresp() -> None:
    _say("\n### STAGE indresp -- ssp126 tree-count response vs historic, both seeds")
    npc = pl.read_parquet(f"{TBL}/cell_npatch.parquet")
    parts = []
    for s in (1, 2):
        p = f"{OUT}/b4_ssp126_cellyear_s{s}.parquet"
        if os.path.exists(p):
            parts.append(pl.read_parquet(p))
    if not parts:
        raise SystemExit("FATAL: no b4_ssp126_cellyear_s*.parquet -- run stage ind first")
    cy = pl.concat(parts)
    _say(f"  loaded {cy.height} (seed, Year, Cell) rows for seeds "
         f"{sorted(cy['seed'].unique().to_list())}")
    st = pl.read_parquet(f"{OUT}/prep_cell_window_state.parquet")

    rows = []
    for s in sorted(cy["seed"].unique().to_list()):
        c = cy.filter(pl.col("seed") == s)
        for wlab, y0, y1 in (("s126_2020_2039", 2020, 2039), ("s126_2080_2099", 2080, 2099)):
            w = c.filter((pl.col("Year") >= y0) & (pl.col("Year") <= y1))
            agg = (
                w.group_by("Cell").agg(
                    pl.col("n_trees_live").sum().alias("_n"),
                    pl.col("agb_live_sum").sum().alias("_a"),
                    pl.col("n_patch_obs").max().alias("n_patches_obs"),
                    pl.len().alias("n_years_present"),
                )
                .join(npc, on="Cell", how="left")
                .with_columns(pl.max_horizontal(
                    pl.col("n_patches").fill_null(0), pl.col("n_patches_obs")
                ).alias("n_patches_eff"))
                .with_columns(
                    (pl.col("_n") / (pl.col("n_patches_eff") * (y1 - y0 + 1)))
                    .alias("stems_per_patch"),
                    (pl.col("_a") / (pl.col("n_patches_eff") * (y1 - y0 + 1)))
                    .alias("agb_per_patch"),
                    pl.lit(wlab).alias("window"), pl.lit(s, dtype=pl.Int8).alias("seed"),
                )
            )
            rows.append(agg.select(["Cell", "seed", "window", "n_years_present",
                                    "n_patches_eff", "stems_per_patch", "agb_per_patch"]))
            tb = agg.filter(pl.col("_n") > 0).height
            _say(f"  seed{s} {wlab}: tree-bearing cells = {tb} of {NCELL}; "
                 f"mean stems/patch over present cells = "
                 f"{agg['stems_per_patch'].mean():.4f}")
    tb126 = pl.concat(rows)
    tb126.write_parquet(f"{OUT}/b4_ssp126_cell_window_state.parquet", compression="zstd")
    _say(f"  WROTE {OUT}/b4_ssp126_cell_window_state.parquet rows={tb126.height}")

    hist = st.filter(pl.col("window") == "hist_2000_2019").select(
        ["Cell", "seed", "stems_per_patch", "agb_per_patch"]).rename(
        {"stems_per_patch": "sp_hist", "agb_per_patch": "agb_hist"})
    s370 = st.filter(pl.col("window") == "ssp370_2080_2099").select(
        ["Cell", "seed", "stems_per_patch"]).rename({"stems_per_patch": "sp_370"})
    _say("\n  -- per-cell stems/patch response, STRUCTURAL ZEROS (a cell with no >5 m tree in a "
         "window is a 0 on the per-patch basis, NOT a dropped row) --")
    for s in sorted(tb126["seed"].unique().to_list()):
        a = (
            tb126.filter((pl.col("seed") == s) & (pl.col("window") == "s126_2080_2099"))
            .select(["Cell", "stems_per_patch"]).rename({"stems_per_patch": "sp_126"})
            .join(hist.filter(pl.col("seed") == s).select(["Cell", "sp_hist"]),
                  on="Cell", how="full", coalesce=True)
            .join(s370.filter(pl.col("seed") == s).select(["Cell", "sp_370"]),
                  on="Cell", how="full", coalesce=True)
            .with_columns(pl.col("sp_126").fill_null(0.0), pl.col("sp_hist").fill_null(0.0),
                          pl.col("sp_370").fill_null(0.0))
        )
        d126 = (a["sp_126"] - a["sp_hist"]).to_numpy()
        d370 = (a["sp_370"] - a["sp_hist"]).to_numpy()
        _say(f"   seed{s}: n_cells={a.height}  mean d(stems/patch) ssp126={d126.mean():+.4f}  "
             f"ssp370={d370.mean():+.4f}  ratio={d126.mean() / d370.mean():.4f}  "
             f"pattern r={np.corrcoef(d126, d370)[0, 1]:.4f}")
        _say(f"           cells gaining trees under ssp126: "
             f"{100 * (d126 > 0).mean():.2f} %, losing: {100 * (d126 < 0).mean():.2f} %")
        a.write_parquet(f"{OUT}/b4_ssp126_stemresp_s{s}.parquet", compression="zstd")


# =================================================================================================
# STAGE indgate -- validate the raw-CSV scanner against an INDEPENDENT existing table
# =================================================================================================
def stage_indgate(seed: int, nw: int) -> None:
    """Run the SAME scanner on the HISTORIC roster and compare its per-cell-window living tree
    stem-year total, integer for integer, against agent P0's prep_cell_window_state.parquet
    (built from the committed parquet roster by a completely different code path).  This is the
    only available proof that the 186 GB raw-CSV path is not silently wrong."""
    import multiprocessing as mp  # noqa: PLC0415

    global Y0_126, NY_126
    path = IND_HIST[seed]
    _say(f"\n### STAGE indgate -- historic seed{seed} raw scan vs the independent parquet table")
    Y0_126, NY_126 = 2000, 20
    with open(path) as f:
        hdr = f.readline().strip().split(",")
    if hdr != IND_COLS:
        raise SystemExit("FATAL: historic header != frozen 29-col schema")
    rngs = _range_bounds(path, nw)
    nb = NY_126 * NCELL
    cl = np.zeros(nb, dtype=np.int64)
    t0 = time.time()
    nrows = 0
    with mp.get_context("fork").Pool(nw) as pool:
        for n, a, _b, _c, _d, _tb in pool.imap_unordered(
            _scan_range, [(path, a0, b0, 0) for a0, b0 in rngs]
        ):
            nrows += n
            cl += a
    gb = os.path.getsize(path) / 1e9
    _say(f"  scanned {nrows} rows / {gb:.1f} GB in {_dt(t0)}")
    yr = np.repeat(np.arange(Y0_126, Y0_126 + NY_126), NCELL)
    ce = np.tile(np.arange(NCELL), NY_126)
    mine = (
        pl.DataFrame({"Year": yr, "Cell": ce, "n": cl})
        .filter((pl.col("Year") >= 2000) & (pl.col("Year") <= 2019))
        .group_by("Cell").agg(pl.col("n").sum().alias("n_stem_years_mine"))
    )
    ref = (
        pl.read_parquet(f"{OUT}/prep_cell_window_state.parquet")
        .filter((pl.col("window") == "hist_2000_2019") & (pl.col("seed") == seed))
        .select(["Cell", "n_stem_years"])
    )
    j = ref.join(mine, on="Cell", how="left").with_columns(
        pl.col("n_stem_years_mine").fill_null(0))
    d = (j["n_stem_years"] - j["n_stem_years_mine"]).to_numpy()
    _say(f"  GATE: {j.height} cells in the independent table; exact integer matches = "
         f"{int((d == 0).sum())}  mismatches = {int((d != 0).sum())}  max |diff| = "
         f"{int(np.abs(d).max()) if len(d) else 0}")
    extra_cells = mine.join(ref, on="Cell", how="anti").height
    _say(f"  cells the raw scan sees with >=1 living tree stem-year that the independent table "
         f"does NOT list: {extra_cells}")
    if (d != 0).sum() > 0:
        _say("  -> MISMATCH: the raw-CSV path and the parquet path DISAGREE; report it, do not "
             "hide it")
    else:
        _say("  -> PASS: the raw-CSV scanner reproduces the independent table integer for integer")


# =================================================================================================
# STAGE fitstem -- the SAME pre-registered experiment on the TREE-SPECIFIC target
# =================================================================================================
def stage_fitstem() -> None:
    _say("\n### STAGE fitstem -- the same held-out-leg experiment on stems per patch (TREES ONLY)")
    clim = pl.read_parquet(f"{OUT}/b4_cell_window_clim3.parquet")
    st = pl.read_parquet(f"{OUT}/prep_cell_window_state.parquet")
    # ONE denominator for every leg: the run is npatch25 everywhere, so 25 x n_years, and a cell
    # with no >5 m tree in a window is a STRUCTURAL ZERO, not a dropped row.
    ref = (
        st.select(["Cell", "window", "seed", "n_stem_years", "n_years"])
        .with_columns((pl.col("n_stem_years") / (25.0 * pl.col("n_years"))).alias("spp"))
        .with_columns(pl.col("window").replace({"ssp370_2020_2039": "s370_2020_2039",
                                                "ssp370_2080_2099": "s370_2080_2099"}))
    )
    mine = []
    for sd in (1, 2):
        pth = f"{OUT}/b4_ssp126_cellyear_s{sd}.parquet"
        if not os.path.exists(pth):
            _say(f"  MISSING {pth} -- skipping seed {sd}")
            continue
        c = pl.read_parquet(pth)
        for wlab, y0, y1 in (("s126_2020_2039", 2020, 2039), ("s126_2080_2099", 2080, 2099)):
            a = (
                c.filter((pl.col("Year") >= y0) & (pl.col("Year") <= y1))
                .group_by("Cell").agg(pl.col("n_trees_live").sum().alias("n_stem_years"))
                .with_columns(
                    (pl.col("n_stem_years") / (25.0 * (y1 - y0 + 1))).alias("spp"),
                    pl.lit(wlab).alias("window"), pl.lit(sd, dtype=pl.Int64).alias("seed"),
                    pl.lit(y1 - y0 + 1, dtype=pl.Int64).alias("n_years"),
                )
            )
            mine.append(a.select(ref.columns))
    allst = pl.concat([x.with_columns(
        pl.col("Cell").cast(pl.Int64), pl.col("n_stem_years").cast(pl.Int64),
        pl.col("n_years").cast(pl.Int64), pl.col("seed").cast(pl.Int64),
        pl.col("spp").cast(pl.Float64),
    ).select(["Cell", "window", "seed", "n_stem_years", "n_years", "spp"])
        for x in [ref] + mine], how="vertical")
    seeds = sorted(allst["seed"].unique().to_list())
    _say(f"  seeds available: {seeds}; windows: {sorted(allst['window'].unique().to_list())}")
    # structural zeros: dense (Cell x window) grid, seed-mean
    tg = (
        allst.group_by(["Cell", "window"]).agg(pl.col("spp").mean().alias("spp"),
                                               pl.len().alias("nseed"))
    )
    W_ALL = [x[1] for x in WINDOWS]
    grid = pl.DataFrame({"Cell": np.repeat(np.arange(NCELL, dtype=np.int64), len(W_ALL)),
                         "window": W_ALL * NCELL})
    tg = grid.join(tg, on=["Cell", "window"], how="left").with_columns(
        pl.col("spp").fill_null(0.0))
    _say(f"  dense target grid {tg.height} rows = {NCELL} cells x {len(W_ALL)} windows "
         "(structural zeros filled; NOTHING inner-joined away)")
    d = clim.join(tg, on=["Cell", "window"], how="inner", validate="1:1")
    base = d.filter(pl.col("window") == BASE_W).sort("Cell")
    cell_order = base["Cell"].to_numpy()
    lat, lon = base["lat"].to_numpy(), base["lon"].to_numpy()

    def mat(wlab, feats):
        sdf = d.filter(pl.col("window") == wlab).sort("Cell")
        return sdf.select(feats).to_numpy().astype(np.float64), sdf["spp"].to_numpy()

    ARMS = {"A_clim": CLIM_FEATS + SOIL_FEATS,
            "A_clim_addr": CLIM_FEATS + SOIL_FEATS + ADDR_FEATS,
            "N1_addr_only": ADDR_FEATS + SOIL_FEATS}
    X, Y = {}, {}
    for wlab in W_ALL:
        for arm, feats in ARMS.items():
            X[(wlab, arm)], Y[wlab] = mat(wlab, feats)
    ds126 = Y["s126_2080_2099"] - Y[BASE_W]
    ds370 = Y["s370_2080_2099"] - Y[BASE_W]
    # two-member spread of the RESPONSE (needs per-seed rows on both ends)
    per = (
        allst.filter(pl.col("window").is_in([BASE_W, "s126_2080_2099"]))
        .pivot(on="window", index=["Cell", "seed"], values="spp")
    )
    per = per.with_columns(pl.col(BASE_W).fill_null(0.0),
                           pl.col("s126_2080_2099").fill_null(0.0))
    per = per.with_columns((pl.col("s126_2080_2099") - pl.col(BASE_W)).alias("dr"))
    pv = per.pivot(on="seed", index="Cell", values="dr")
    pv = pv.rename({c: f"seed{c}" for c in pv.columns if c != "Cell"})
    scol = [c for c in pv.columns if c != "Cell"]
    full = pl.DataFrame({"Cell": cell_order}).join(pv, on="Cell", how="left")
    if len(scol) == 2:
        spread = np.abs(full[scol[0]].fill_null(0).to_numpy()
                        - full[scol[1]].fill_null(0).to_numpy())
    else:
        spread = np.zeros(len(cell_order))
        _say("  WARNING: only one ssp126 member available -> the two-member spread is 0 and the "
             "tolerance falls back to 10 % of |truth|")
    ratio = np.median(spread) / max(np.median(np.abs(ds126)), 1e-12)
    _say(f"  SCOREABILITY: median |d stems/patch| ssp126 = {np.median(np.abs(ds126)):.4f}, "
         f"median two-member spread = {np.median(spread):.4f} -> ratio {ratio:.4f}")
    _say(f"  mean d stems/patch: ssp126 = {ds126.mean():+.4f}, ssp370 = {ds370.mean():+.4f}, "
         f"between-leg r = {np.corrcoef(ds126, ds370)[0, 1]:.4f}, opposite sign at "
         f"{100.0 * np.mean(np.sign(ds126) != np.sign(ds370)):.2f} % of cells")
    tb = {w: int((Y[w] > 0).sum()) for w in W_ALL}
    _say(f"  tree-bearing cells (>0 living >5 m stems in the window, seed-mean): {tb}")

    tbase = d.filter(pl.col("window") == BASE_W).sort("Cell")["tas_wmean_degC"].to_numpy()
    dt126 = d.filter(pl.col("window") == "s126_2080_2099").sort(
        "Cell")["tas_wmean_degC"].to_numpy() - tbase
    dt370 = d.filter(pl.col("window") == "s370_2080_2099").sort(
        "Cell")["tas_wmean_degC"].to_numpy() - tbase
    k_glob = float(dt126.mean() / dt370.mean())
    res = []

    def score(name, arm, colour, y, p, extra=""):
        tol = np.maximum(0.10 * np.abs(y), spread) if name == "ds126_late" else 0.10 * np.abs(y)
        r = {"target": name, "arm": arm, "colouring": colour, "n_cells": len(y),
             "R2": _r2(y, p), "r": _corr(y, p), "slope0": _slope0(y, p),
             "median_abs_err": float(np.median(np.abs(y - p))),
             "frac_within_tol": float(np.mean(np.abs(y - p) <= tol)), "note": extra}
        res.append(r)
        _say(f"    {name:12s} {arm:24s} {colour:6s} R2={r['R2']:+8.4f} r={r['r']:+7.4f} "
             f"slope0={r['slope0']:+8.4f} medAE={r['median_abs_err']:8.4f} "
             f"within-tol={r['frac_within_tol']:.4f} {extra}")

    _say("\n  -- NULLS THAT NEED NO FIT --")
    score("ds126_late", "N2_zero_response", "n/a", ds126, np.zeros_like(ds126), "<=0 by constr.")
    score("ds126_late", "N3_global_memorise", "n/a", ds126, k_glob * ds370,
          f"k_glob={k_glob:.4f}")
    rr = np.clip(np.where(np.abs(dt370) < 0.25, 0.0, dt126 / np.where(dt370 == 0, 1, dt370)),
                 -2, 2)
    score("ds126_late", "N3b_local_memorise", "n/a", ds126, rr * ds370)

    _say("\n  -- TREATMENT + N1, blocked folds, two colourings --")
    for colour in ("saltA", "saltB"):
        fold = _blocked_fold(lat, lon, colour, 5)
        for arm in ARMS:
            pred = {w: np.full(len(ds126), np.nan) for w in W_ALL}
            for f in range(5):
                tr, te = fold != f, fold == f
                tx = np.concatenate([X[(w, arm)][tr] for w in
                                     (BASE_W, "s370_2020_2039", "s370_2080_2099")], axis=0)
                ty = np.concatenate([Y[w][tr] for w in
                                     (BASE_W, "s370_2020_2039", "s370_2080_2099")], axis=0)
                outs = _fit_predict(tx, ty, [X[(w, arm)][te] for w in W_ALL])
                for w, o in zip(W_ALL, outs, strict=True):
                    pred[w][te] = o
            score("ds126_late", f"{arm}|fit_hist+370", colour, ds126,
                  pred["s126_2080_2099"] - pred[BASE_W])
            score("ds370_late", f"{arm}|fit_hist+370", colour, ds370,
                  pred["s370_2080_2099"] - pred[BASE_W], "IN-distribution, for contrast")
            score("level_s126", f"{arm}|fit_hist+370", colour, Y["s126_2080_2099"],
                  pred["s126_2080_2099"], "LEVEL -- not the blessed statistic")
        score("level_s126", "N4_level_persistence", colour, Y["s126_2080_2099"], Y[BASE_W],
              "why the LEVEL score must not be quoted")
    rt = pl.DataFrame(res)
    rt.write_csv(f"{OUT}/b4_fitstem_results.csv")
    _say(f"\n  WROTE {OUT}/b4_fitstem_results.csv ({rt.height} rows)")
    n2r = rt.filter(pl.col("arm") == "N2_zero_response")["R2"][0]
    n3r = max(rt.filter(pl.col("arm") == "N3_global_memorise")["R2"][0],
              rt.filter(pl.col("arm") == "N3b_local_memorise")["R2"][0])
    _say("\n  -- VERDICT AGAINST THE PRE-REGISTERED FALSIFIER (stems/patch) --")
    for arm in ("A_clim|fit_hist+370", "A_clim_addr|fit_hist+370"):
        for colour in ("saltA", "saltB"):
            r = rt.filter((pl.col("target") == "ds126_late") & (pl.col("arm") == arm)
                          & (pl.col("colouring") == colour))["R2"][0]
            _say(f"    {arm} {colour}: R2={r:+.4f} margin over N2={r - n2r:+.4f} "
                 f"margin over best memorisation={r - n3r:+.4f} -> "
                 f"{'LEARNED' if (r - n2r >= 0.05 and r - n3r >= 0.05) else 'NOT LEARNED'}")
    pl.DataFrame({"Cell": cell_order, "lat": lat, "lon": lon,
                  "spp_hist": Y[BASE_W], "spp_s370_late": Y["s370_2080_2099"],
                  "spp_s126_late": Y["s126_2080_2099"], "ds126": ds126, "ds370": ds370,
                  "ds126_seedspread": spread}).write_parquet(
        f"{OUT}/b4_percell_stem_response.parquet", compression="zstd")
    _say(f"  WROTE {OUT}/b4_percell_stem_response.parquet")


# =================================================================================================
def main() -> int:
    print(PREREG, flush=True)
    stage = sys.argv[1] if len(sys.argv) > 1 else "prov"
    os.makedirs(OUT, exist_ok=True)
    _say(f"### stage={stage} argv={sys.argv[1:]}")
    if stage == "prov":
        stage_prov()
    elif stage == "clim":
        stage_clim()
    elif stage == "vegc":
        stage_vegc()
    elif stage == "fit":
        stage_fit()
    elif stage == "ind":
        seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        nw = int(sys.argv[3]) if len(sys.argv) > 3 else 32
        sm = int(sys.argv[4]) if len(sys.argv) > 4 else 100
        stage_ind(seed, nw, sm)
    elif stage == "indresp":
        stage_indresp()
    elif stage == "indgate":
        stage_indgate(int(sys.argv[2]) if len(sys.argv) > 2 else 1,
                      int(sys.argv[3]) if len(sys.argv) > 3 else 32)
    elif stage == "fitstem":
        stage_fitstem()
    else:
        raise SystemExit(f"unknown stage {stage}")
    _say("\n=== STAGE OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
