"""explore_perstem_ladder.py — line X, campaign item B2.

THE QUESTION
  A permutation-equivariant set/graph network over the per-stem roster is the one purely-learned
  architecture nobody has priced: learn the per-stem annual update from the stem's own state plus
  permutation-invariant pooled summaries of its patch. Two things have never been measured.
    (1) How much learnable signal is in the ~2.5e9 paired per-stem label corpus at all?
    (2) Does CLIMATE add anything PER STEM once the STAND is conditioned on?  ADR 0181 found the
        cell-level count model's apparent warming response was inherited from the stand
          (through-origin
        response slope: stand 0.994, climate 0.016); ADR 0179 found the climate channel structurally
        wide open (10.2 % of splits) and FLAT.  If the same holds per stem, a learned operator's
        warming response can only come from stand feedback.

WHAT THIS SCRIPT DOES
  Builds a nested NULL LADDER on two targets and reports every rung, on TWO fold schemes
    (hash-by-cell
  and spatially blocked 15 deg blocks / 5 deg buffer, read from the committed ADR-0040 fold
    maps, two
  colourings), then a SEPARATE response experiment: fit on the historic leg only, predict both legs,
  and score the per-cell leg DIFFERENCE against the truth's, with the climate block deleted as
    the null.

  Stages (positional argv[1]):  prep | ladder | resp
    prep    -> /p/tmp/jamirp/X_explore/b2_stem_features.parquet  (+ b2_cellyear_clim.parquet)
    ladder  -> b2_ladder_<scheme>.csv, b2_calibration.csv, b2_subsets.csv
    resp    -> b2_response.csv, b2_response_cells.parquet

READ-ONLY except this script and /p/tmp/jamirp/X_explore/b2_*.  No git, no src/, no other line's
  state.

------------------------------------------------------------------------------------------------
BASIS FACTS THIS SCRIPT DEPENDS ON (all traceable, none re-derived here)

* Table A = /p/tmp/jamirp/X_explore/prep_paired_stems.parquet (agent P0): 21 785 911 stem-years,
  the 674-cell deterministic sample `Cell % 100 == 0`, historic 2000-2019 + ssp370 2020-2100,
    seeds 1+2.
  601 of those cells are tree-bearing in at least one leg.  [SOURCE: P0 report]
* The cross-year individual identity is (Cell, Patch, Type, ID) — NOT ADR 0125's (Cell, Patch, ID).
  `ID` is `tree->index`, taken from a counter held PER PFT PARAMETER ENTRY
  ([SOURCE] /home/jamirp/lpjml56fit/src/tree/new_tree.c:85-86), so two stems of different `Type` in
  one patch can share an `ID`.  P0 measured 0/0/0 identity violations on 20 417 713 pairs with
    `Type`
  in the key and 61/183/17 without it.  This script uses the corrected key and excludes `dup_key
    == 1`.
* 5 damaged (leg, seed, Cell) blocks (all ssp370 seed2, year 2071) are excluded via
  prep_suspect_cell_blocks.csv.  This script uses seed 1 for all fitting, so they cannot bite,
    but the
  exclusion is applied anyway.
* Mortality is applied AFTER allocation ([SOURCE] annual_natural.c: the hazard loop at :73
  precedes the
  FPC accumulation at :256), so a stem emitted with `isdead == 1` DID grow through that year. 
    Therefore
  the correct "patch state during year y" pools ALL emitted stems, dead-flagged included. 
    Pooling only
  the LIVING stems (as prep_patch_year_stand.parquet does, by design) would make every patch
    aggregate a
  function of the focal stem's own label -> label leakage.  THIS SCRIPT RECOMPUTES ALL PATCH
    AGGREGATES
  over all emitted stems and never joins Table B.
* `isdead` is a per-individual Bernoulli draw on `mort`
  ([SOURCE] /home/jamirp/lpjml56fit/src/tree/mortality_tree_ind.c:128-143:
  `mort = mort_npp + mort_age + mort_water + mort_temp`, capped at 1, then `mort = 1` if
  `bm_inc_counter >= BM_INC_COUNTER_MAX` or `leaf_c < leaf_carbon_sapl`, saved as
    `tree->mort_prob`).
  So `mort` is the CEILING for T1 and the residual is the C's own coin flip.  `mort*` columns are
  NEVER features; `mort` alone is reported as a separate ceiling row.
* `gpp` in the 29-col schema is a byte copy of `npp` (ADR 0130) — excluded from the feature set.
* `k_root` is a constant 0.02 in this configuration (ADR 0117) — excluded.
* n6 (the C's own `bm_inc_counter`) is NOT USABLE as a feature for T1.  The counter increments when
  `bm_delta < 0` and multiplies TWO of the four hazards
  ([SOURCE] mortality_tree_ind.c:70-82, :103, :121), and the only route to it from the emitted table
  runs through `mort_npp` / `mort_water`, which ARE the answer.  Instead n6 is the per-stem
    MEMORY the
  counter encodes, rebuilt from the paired identity out of PAST state only: last year's biomass
  increment, last year's npp, the run length of consecutive non-positive increments, and the
    count of
  non-positive increments in the last 3 years.  That is the architecturally interesting question
  anyway (does a Markov-in-current-state operator suffice?).  Said plainly in the report.

------------------------------------------------------------------------------------------------
Usage
  /home/jamirp/.conda/envs/py311_new/bin/python scripts/explore_perstem_ladder.py prep
  TIME=03:00:00 NCPUS=32 scripts/sbatch_python.sh X-perstem scripts/explore_perstem_ladder.py ladder
  (parameters are POSITIONAL — the wrapper forwards only a fixed list of env names.)
"""

from __future__ import annotations

import os
import struct
import sys
import time
import warnings

import numpy as np
import polars as pl

warnings.filterwarnings("ignore", message="X does not have valid feature names")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python", "src"))
sys.path.insert(0, _HERE)

from build_slow_runtime_table import K_LIGHTEXT, patch_stand_lai_expr  # noqa: E402
from build_transient_boundary import CLM, CLM_EXTRA  # noqa: E402

OUT = "/p/tmp/jamirp/X_explore"
TBL = "/p/tmp/jamirp/emulator_global/tables"
TABLE_A = f"{OUT}/prep_paired_stems.parquet"
SUSPECT = f"{OUT}/prep_suspect_cell_blocks.csv"
CLIMWIN = f"{OUT}/prep_cell_window_clim.parquet"
FOLDMAPS = {
    "hash5": f"{TBL}/foldmaps/foldmap_hash.txt",
    "block_s0": f"{TBL}/foldmaps/foldmap_block15.0_buf5.0_s0.txt",
    "block_s1": f"{TBL}/foldmaps/foldmap_block15.0_buf5.0_s1.txt",
}
FEAT = f"{OUT}/b2_stem_features.parquet"
CLIM = f"{OUT}/b2_cellyear_clim.parquet"

SEED_FIT = 1  # all fitting on seed 1; seed 2 is reserved for the two-seed noise floor
LADDER_N = 2_500_000  # rows subsampled for the ladder (of ~10.9e6 seed-1 stem-years)
RNG = 20260819
NTHREAD = int(os.environ.get("SLURM_CPUS_PER_TASK", os.environ.get("NCPUS", "16")))

WINDOWS = [("hist", "historic", 2000, 2019),
           ("ssp_early", "ssp370", 2020, 2039),
           ("ssp_late", "ssp370", 2080, 2099)]
MIN_STEMYEARS = 200  # per cell per window, for a cell to enter the response regression

_T0 = time.time()


def _say(msg: str) -> None:
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ================================================================================================
# PRE-REGISTRATION — printed before any result is computed, in every stage.
# ================================================================================================
PREREG = r"""
================================================================================================
PRE-REGISTRATION (item B2) — written before any result was computed
================================================================================================
QUESTION
  Q1  How much learnable signal does the paired per-stem corpus contain, for (T1) whether a stem is
      killed this year and (T2) how much biomass it adds next year?
  Q2  Does CLIMATE add anything PER STEM once the STAND is conditioned on?
  Q3  Does a model fitted on the historic leg alone carry the WARMING RESPONSE, and is that response
      distinguishable from the one a climate-blind model inherits from the stand?

TARGETS
  T1  isdead (the C's own kill flag for that stem-year; a Bernoulli draw on `mort`).
      BLESSED STATISTIC: holdout AUC.  Also reported: Brier, log-loss, calibration by decile.
  T2  d_agb = agb(y+1) - agb(y) for the SAME individual (paired on (Cell,Patch,Type,ID)), i.e.
      conditional on survival.  BLESSED STATISTIC: holdout R^2 against the HOLDOUT mean.

NESTED FEATURE RUNGS (strictly nested; each adds exactly one block)
  n0  intercept only (train-set mean; no fit)
  n1  + Age, Height
  n2  + own sampled traits: SLA, Wooddens, D95max, minwscal, Longevity, Type
  n3  + own current-year carbon/water state: npp, agb, vegc, LAI, fpc_ind, transp, wscal_mean
  n4  + permutation-invariant pooled summaries of the stem's OWN PATCH (recomputed over ALL emitted
        stems, so no label leakage) + the stem's rank/share within it + the pooled crown area and
        stand-LAI of the stems TALLER than it.  This is the set-network's information set.
  n5  + the cell's climate for that year (8 annual variables from the .clm forcing, read by
    identical
        code on both legs), its 5- and 10-year trailing means, its anomaly against the cell's own
        2000-2019 mean, and the 8 ready-made 20-year-window features.
  n6  + per-stem MEMORY from PAST state only (last year's biomass increment, last year's npp,
    the run
        length of consecutive non-positive increments, the count of such in the last 3 years).
        This stands in for the C's own bm_inc_counter, which CANNOT be a T1 feature (see the
          header).
  EXTRA ARMS
  addr    n4 + the geographic ADDRESS (lat, lon, unit-sphere x/y/z) INSTEAD of climate — the
    null for
          the n5 increment.  ADR 0040 measured a pure address scoring 0.837 under hash folds and
          0.140/0.210 under blocked folds on a trait target, so an address must be nulled
            explicitly.
  permclim  n4 + the climate block with the cell -> climate-series correspondence PERMUTED (each
    cell
          gets another cell's series, consistently across folds).  Preserves every marginal and the
          temporal structure, destroys the cell-climate link.  This is the strict null for n5.
  CEILING  `mort` ALONE, for T1 only.  `mort*` columns are never in any rung.
  climonly  the climate block ALONE (no stem, no stand).  Does climate carry ANY per-stem
            information before the stand is conditioned on?
  addronly  the geographic address ALONE (lat/lon/x/y/z).  The null for climonly: a cell's ADDRESS
            already encodes its mean death rate and mean growth, so climonly must beat addronly to
            be climate rather than geography.
  own_clim  n3 + climate (own size/traits/state + climate, but NO patch block).  Comparing
            (own_clim - n3) against (n5 - n4) isolates whether the STAND block is what absorbs
            climate's per-stem information -- the per-stem form of ADR 0181's cell-level finding.

FOLD SCHEMES  (both reported; the fold ASSIGNMENT is read from the committed ADR-0040 maps, never
               reimplemented -- a reimplemented hash silently scores a different experiment)
  hash5     5-fold by cell, foldmap_hash.txt
  block_s0  5-fold by 15 deg spatial block with a 5 deg buffer dilated out of training, salt 0
  block_s1  the same at salt 1 (ADR 0040 measured a large colouring-to-colouring spread, so two
            colourings are mandatory; run for the top rungs only, to fit the compute budget)

WHAT EACH NULL MUST RETURN
  N1  n0 on T1 must return AUC = 0.5000 exactly (a constant score) and Brier ~ p(1-p) with p the
      base death rate ~0.0422, i.e. ~0.0404.  n0 on T2 must return R^2 <= 0 (the train mean scored
      against the holdout mean), and |R^2| < 0.01 if the folds are exchangeable.
  N2  A rung whose added block carries NO information must return the previous rung's score:
      n_k - n_(k-1) = 0 within noise.  "Within noise" is defined BEFORE the run as
      2 x SE_paired, where SE_paired = sd over the 5 folds of the per-fold difference / sqrt(5).
  N3  CEILING (T1): AUC(`mort`) must be < 1 strictly, because isdead is a coin flip on mort; and
      Brier(`mort`) must equal mean(mort*(1-mort)) to within Monte-Carlo error -- that identity is a
      self-check on the label.  Every AUC in the ladder is to be read against this ceiling, not 1.0.
  N4  permclim must return n4 within 2 x SE_paired.  If it returns MORE than n4, the climate
    block is
      acting as a capacity/regularisation artefact and the n5 increment cannot be read as climate.
  N5  Response stage, do-nothing null: predicted leg difference identically 0 -> through-origin
    slope
      exactly 0.0000.  Two-seed noise floor: truth(seed1) vs truth(seed2) per-cell leg difference --
      its slope and correlation are the CEILING for any model scored against a single-seed truth.
  N6  addronly is a CONSTANT within a cell, so in the RESPONSE stage its predicted leg difference
      can move only through nothing at all -> its slope must be EXACTLY 0.0000.  If it is not,
      the response pipeline has a leak and every response number in this report is void.
  N7  climonly and own_clim must both exceed addronly for climate to be climate; and if the climate
      block carries per-stem information that the stand does NOT already carry, then
      (own_clim - n3) and (n5 - n4) must be EQUAL within 2 x SE_paired.  If instead
      (own_clim - n3) >> (n5 - n4), climate's per-stem information is REDUNDANT with the stand --
      which is the per-stem analogue of ADR 0181's cell-level result and is the outcome I expect.

FALSIFIERS, stated as numbers, before the run
  F1 (Q2, the climate question).  I will conclude CLIMATE ADDS NOTHING PER STEM BEYOND THE STAND if
     BOTH  n5 - n4 <= 0.005 in AUC (T1)  AND  n5 - n4 <= 0.005 in R^2 (T2), on the hash5 scheme.
     I will conclude CLIMATE ADDS SOMETHING BUT NO MORE THAN A GEOGRAPHIC ADDRESS if the increment
     exceeds 0.005 but does not exceed (addr - n4) by more than 2 x SE_paired.
     I will conclude CLIMATE ADDS GENUINE PER-STEM SIGNAL only if n5 - n4 > 0.005, exceeds
     (addr - n4) + 2 x SE_paired, and survives the blocked scheme (block_s0 and block_s1).
  F2 (Q1, the signal question).  I will conclude THE CORPUS CONTAINS LITTLE LEARNABLE SIGNAL BEYOND
     THE STEM'S OWN SIZE if n6 - n1 <= 0.02 in AUC and <= 0.05 in R^2.
  F3 (Q3, the response question).  I will conclude THE RESPONSE IS STAND-INHERITED, NOT LEARNED FROM
     CLIMATE, if |slope(n5) - slope(n4)| <= 0.10 and the two are within 2 bootstrap SE of each
       other.
     I will conclude NO MODEL CARRIES THE RESPONSE AT ALL if slope(n5) < 0.10.
     Any slope is void as evidence unless the two-seed truth-vs-truth slope (N5) is materially above
     it -- if the per-cell true leg difference is mostly seed noise, the regression has no target.
  F5 (redundancy).  I will conclude CLIMATE'S PER-STEM INFORMATION IS REDUNDANT WITH THE STAND if
     (own_clim - n3) > 0.005 while (n5 - n4) <= 0.005, i.e. the same climate block that helps a
     stand-blind model is worthless once the patch is conditioned on.  I will conclude CLIMATE
     CARRIES NO PER-STEM INFORMATION AT ALL, redundant or otherwise, if climonly <= addronly + 2 SE.
  AMENDMENT 1, logged before the full run and AFTER null N3 failed on a login-node read of the
  prep output (disclosed, not retrofitted).  N3 pre-registered that Brier(`mort`) must equal
  mean(mort*(1-mort)) because isdead is a coin flip on mort.  MEASURED: 0.032481 vs 0.022983, and
  E[isdead] = 0.042154 while E[mort] = 0.031739 -- so `mort` UNDER-states the realised death rate.
  Reading the C settled it: isdead is TRUE if ANY of three things happens, and only ONE of them is
  the erand48 draw on `mort` ([SOURCE] src/tree/annual_tree.c:31-48) -- the others are a
  POOL-NEGATIVITY test (isneg_tree) and `!survive(...)`, a DETERMINISTIC BIOCLIMATIC kill that is a
  pure function of the cell's 20-year climate buffer.  Consequences, all pre-registered here:
    (a) AUC(`mort`) is the ceiling for the DOCUMENTED STOCHASTIC HAZARD ONLY, not for a learner.  A
        learner CAN legitimately exceed it, because the other two channels are deterministic.  Every
        AUC in this report is reported against it with that wording and never as "the ceiling".
    (b) The bioclimatic channel's own two variables are now IN the climate block (tas_cold_m20,
        tas_warm_m20, trange_m20).  This makes F1 a much stronger test: if the n5 increment is still
        nil, climate adds nothing per stem EVEN WHEN HANDED THE EXACT VARIABLES OF THE MODEL'S OWN
        DETERMINISTIC CLIMATE-DRIVEN KILL.
    (c) A new measurement, attributing the excess: what fraction of deaths sit in (cell,PFT,year)
        groups where survive()'s own predicate, evaluated from the forcing, is FALSE.
  F4 (basis).  Every number here is on the 601-tree-bearing-cell sample `Cell % 100 == 0`, seed
    1, and
     is NOT on the acceptance criterion's basis (per cell, all 54 020 tree-bearing cells, both
     scenarios, and the response between them, tolerance max(10 %, the C's own two-run spread)).
     Stated in the same sentence as every number in the report.
================================================================================================
"""


# ================================================================================================
# helpers
# ================================================================================================
def _uniq_assert(df: pl.DataFrame, keys: list[str], what: str) -> None:
    n = df.select(keys).n_unique()
    if n != df.height:
        raise SystemExit(f"FATAL {what}: {df.height - n} duplicated keys on {keys}")
    _say(f"   key-uniqueness {what} on {keys}: {df.height} rows, 0 duplicates -> PASS")


def _open_clm(path):
    """Header-driven .clm open (a local copy of build_transient_boundary.open_clm's logic, kept
      local so
    this probe does not depend on that module's print side effects). Returns (memmap, firstyear,
      scalar)."""
    dt_map = {0: "<i1", 1: "<i2", 2: "<i4", 3: "<f4", 4: "<f8"}
    with open(path, "rb") as f:
        raw = f.read(64)
    if raw[:7] != b"LPJCLIM":
        raise SystemExit(f"FATAL: {path} not LPJCLIM")
    version, order, firstyear, nyear, _fc, ncell, nbands = struct.unpack("<7i", raw[7:35])
    if order != 1:
        raise SystemExit(f"FATAL: {path} order={order} != 1 (YEARCELL)")
    scalar = struct.unpack("<f", raw[39:43])[0]
    if version >= 3:
        hdr, dt = 51, dt_map[struct.unpack("<i", raw[47:51])[0]]
    else:
        hdr, dt = 43, "<i2"
    sz = os.path.getsize(path)
    per = ncell * nbands * np.dtype(dt).itemsize
    if (sz - hdr) != nyear * per:
        raise SystemExit(f"FATAL: {path} size mismatch ({(sz - hdr) / per:.4f} years)")
    mm = np.memmap(path, dtype=dt, mode="r", offset=hdr, shape=(nyear, ncell, nbands))
    _say(f"   clm {os.path.basename(path)}: v{version} {dt} scalar={scalar} "
         f"years {firstyear}..{firstyear + nyear - 1} nbands={nbands}")
    return mm, firstyear, float(scalar)


_MONTH_EDGES = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def _annual_stats(path: str, cells: np.ndarray, y0: int, y1: int, kind: str) -> dict:
    """Per-cell per-year annual statistics for the given cells, from the daily .clm.

    kind='tas' -> mean, cold/warm month, seasonality, gdd5 (daily sum of max(T-5,0)), frostdays.
    kind='sum' -> annual total (precipitation).  kind='mean' -> annual mean (rsds, huss).
    """
    mm, fy, scalar = _open_clm(path)
    ny = y1 - y0 + 1
    keys = (["tas_ann", "tas_cold", "tas_warm", "tas_seas", "gdd5", "frostdays"]
            if kind == "tas" else ["v"])
    out = {k: np.empty((ny, cells.size), dtype=np.float64) for k in keys}
    for j, y in enumerate(range(y0, y1 + 1)):
        i = y - fy
        if i < 0 or i >= mm.shape[0]:
            raise SystemExit(f"FATAL: {path} lacks year {y}")
        yr = np.asarray(mm[i][cells], dtype=np.float64) * scalar  # (ncells, 365)
        if kind == "tas":
            mon = np.stack([yr[:, _MONTH_EDGES[m]:_MONTH_EDGES[m + 1]].mean(axis=1)
                            for m in range(12)], axis=1)
            out["tas_ann"][j] = yr.mean(axis=1)
            out["tas_cold"][j] = mon.min(axis=1)
            out["tas_warm"][j] = mon.max(axis=1)
            out["tas_seas"][j] = mon.max(axis=1) - mon.min(axis=1)
            out["gdd5"][j] = np.maximum(yr - 5.0, 0.0).sum(axis=1)
            out["frostdays"][j] = (yr < 0.0).sum(axis=1)
        else:
            out["v"][j] = yr.sum(axis=1) if kind == "sum" else yr.mean(axis=1)
    return out


# ================================================================================================
# STAGE prep
# ================================================================================================
CLIM_ANN = ["tas_ann", "tas_cold", "tas_warm", "tas_seas", "gdd5", "frostdays",
            "pr_ann", "rsds_ann", "huss_ann"]
CLIM_ROLL = ["tas_ann_m5", "tas_ann_m10", "pr_ann_m5", "pr_ann_m10", "gdd5_m5", "gdd5_m10",
             # the TWO INPUTS OF THE C's OWN DETERMINISTIC BIOCLIMATIC KILL, handed to the learner
             # explicitly.  survive() ([SOURCE] src/lpj/survive.c:23-29) returns FALSE -- killing
             # EVERY stem of that PFT in that cell that year, outside `mort` entirely -- unless
             #     getbufferavg(climbuf->min) >= pftpar->temp.low   AND
             #     getbufferavg(climbuf->max) - getbufferavg(climbuf->min) >= min_temprange
             # and climbuf->min/max are the COLDEST/WARMEST MONTH mean of each year
             # ([SOURCE] src/lpj/climbuf.c:134-137 accumulates over `mtemp`, :153-154 buffers them),
             # so these three columns ARE that test's own variables at 20-year buffer length.
             "tas_cold_m20", "tas_warm_m20", "trange_m20"]
CLIM_ANOM = ["d_tas_ann", "d_pr_ann", "d_gdd5", "d_tas_cold"]
ENV_W20 = ["eco_diag_gdd_5", "tas_cold_month", "eco_diag_vpd_mean", "eco_diag_pet_mean",
           "eco_diag_p_pet_ratio", "pr_cv_monthly", "prec_mean", "humid_mean"]


def stage_prep(limit: int = 0) -> None:
    """limit > 0 restricts to the first `limit` cells and writes to *_smoke paths -- a cheap
    end-to-end logic check before the full SLURM run, never a result."""
    global FEAT, CLIM
    print(PREREG, flush=True)
    _say(f"### STAGE prep  (cell limit={limit or 'none'})")

    # ---- cells --------------------------------------------------------------------------------
    cells = (pl.scan_parquet(TABLE_A).select("Cell").unique().collect()["Cell"]
             .sort().to_numpy())
    if limit:
        cells = cells[:limit]
        FEAT = FEAT.replace(".parquet", "_smoke.parquet")
        CLIM = CLIM.replace(".parquet", "_smoke.parquet")
    _say(f"   tree-bearing sampled cells: {cells.size}")

    # ---- (1) the cell-year climate table (both legs, identical code) ---------------------------
    # The model's own forcing timeline is historic .clm through 2019 then ssp370 .clm from 2020, so
    # the trailing means are built on that CONCATENATED series (which is what the C actually saw).
    _say("   building cell-year climate 1980..2100 (historic <=2019, ssp370 >=2020); the read "
         "starts 20 yr before 2000 so the 20-year bioclimatic buffer is COMPLETE at year 2000")
    parts = []
    for leg, ya, yb in [("historic", 1980, 2019), ("ssp370", 2020, 2100)]:
        t = _annual_stats(CLM[leg], cells, ya, yb, "tas")
        pr = _annual_stats(CLM_EXTRA[leg]["pr"], cells, ya, yb, "sum")["v"]
        rs = _annual_stats(CLM_EXTRA[leg]["rsds"], cells, ya, yb, "mean")["v"]
        hu = _annual_stats(CLM_EXTRA[leg]["huss"], cells, ya, yb, "mean")["v"]
        ny = yb - ya + 1
        d = {"Cell": np.tile(cells, ny),
             "Year": np.repeat(np.arange(ya, yb + 1), cells.size)}
        for k, v in t.items():
            d[k] = v.reshape(-1)
        d["pr_ann"] = pr.reshape(-1)
        d["rsds_ann"] = rs.reshape(-1)
        d["huss_ann"] = hu.reshape(-1)
        parts.append(pl.DataFrame(d))
    clim = pl.concat(parts).sort(["Cell", "Year"])
    _uniq_assert(clim, ["Cell", "Year"], "clim")

    roll = []
    for c, w in [("tas_ann", 5), ("tas_ann", 10), ("pr_ann", 5), ("pr_ann", 10),
                 ("gdd5", 5), ("gdd5", 10), ("tas_cold", 20), ("tas_warm", 20)]:
        roll.append(pl.col(c).rolling_mean(window_size=w, min_samples=w)
                    .over("Cell").alias(f"{c}_m{w}"))
    clim = clim.with_columns(roll).with_columns(
        (pl.col("tas_warm_m20") - pl.col("tas_cold_m20")).alias("trange_m20"))
    ref = (clim.filter((pl.col("Year") >= 2000) & (pl.col("Year") <= 2019))
           .group_by("Cell")
           .agg([pl.col(c).mean().alias(f"ref_{c}") for c in
                 ("tas_ann", "pr_ann", "gdd5", "tas_cold")]))
    clim = clim.join(ref, on="Cell", how="left").with_columns([
        (pl.col("tas_ann") - pl.col("ref_tas_ann")).alias("d_tas_ann"),
        (pl.col("pr_ann") - pl.col("ref_pr_ann")).alias("d_pr_ann"),
        (pl.col("gdd5") - pl.col("ref_gdd5")).alias("d_gdd5"),
        (pl.col("tas_cold") - pl.col("ref_tas_cold")).alias("d_tas_cold"),
    ])
    # the 8 ready-made 20-year-window features, both legs
    env = pl.concat([
        pl.read_parquet(f"{TBL}/cell_year_env_historic_w20.parquet")
        .with_columns([pl.col(c).cast(pl.Float64) for c in ENV_W20]),
        pl.read_parquet(f"{TBL}/cell_year_env_ssp370_w20.parquet")
        .with_columns([pl.col(c).cast(pl.Float64) for c in ENV_W20]),
    ]).filter(pl.col("Cell").is_in(cells)).rename({c: f"w20_{c}" for c in ENV_W20})
    _uniq_assert(env, ["Cell", "Year"], "env_w20")
    clim = clim.join(env, on=["Cell", "Year"], how="left")
    keep = ["Cell", "Year"] + CLIM_ANN + CLIM_ROLL + CLIM_ANOM + [f"w20_{c}" for c in ENV_W20]
    clim = clim.filter(pl.col("Year") >= 2000).select(keep)
    nn = {c: int(clim[c].null_count()) for c in keep if clim[c].null_count() > 0}
    _say(f"   clim table {clim.shape}; null counts (nonzero only): {nn}")
    clim.write_parquet(CLIM)
    _say(f"   wrote {CLIM}")

    # ---- (2) the stem table -------------------------------------------------------------------
    sus = pl.read_csv(SUSPECT).select(["leg", "seed", "Cell"]).unique()
    a = (pl.scan_parquet(TABLE_A)
         .filter(pl.col("seed") == SEED_FIT)
         .filter(pl.col("dup_key") == 0)
         .filter(pl.col("Type") <= 6)
         .filter(pl.col("Cell").is_in(cells))
         .collect())
    _say(f"   Table A seed{SEED_FIT}, dup_key==0, Type<=6: {a.shape}")
    a = a.join(sus, on=["leg", "seed", "Cell"], how="anti")
    _say(f"   after excluding suspect blocks: {a.shape}")

    pw = ["leg", "Cell", "Patch", "Year"]
    a = a.with_columns(patch_stand_lai_expr().alias("_laic"))

    # patch aggregates over ALL emitted stems (dead-flagged included -- they grew this year)
    aggs = [
        pl.len().alias("p_n"),
        pl.col("agb").sum().alias("p_agb"), pl.col("vegc").sum().alias("p_vegc"),
        pl.col("npp").sum().alias("p_npp"), pl.col("transp").sum().alias("p_transp"),
        pl.col("fpc_ind").sum().alias("p_fpc"), pl.col("_laic").sum().alias("p_lai"),
        pl.col("Height").max().alias("p_hmax"), pl.col("Height").mean().alias("p_hmean"),
        pl.col("Height").std().alias("p_hsd"),
        pl.col("Height").quantile(0.5).alias("p_hmed"),
        pl.col("Age").mean().alias("p_agemean"), pl.col("Age").max().alias("p_agemax"),
        pl.col("SLA").mean().alias("p_sla"), pl.col("Wooddens").mean().alias("p_wd"),
        pl.col("D95max").mean().alias("p_d95max"), pl.col("minwscal").mean().alias("p_minwscal"),
        pl.col("Longevity").mean().alias("p_longev"),
        pl.col("wscal_mean").mean().alias("p_wscal"),
        pl.col("Type").n_unique().alias("p_ntype"),
    ] + [(pl.col("Type") == t).sum().alias(f"p_npft{t}") for t in range(7)]
    patch = a.group_by(pw).agg(aggs)
    _uniq_assert(patch, pw, "patch")
    a = a.join(patch, on=pw, how="left")

    # focal-stem position within the patch: pooled crown/LAI of the TALLER stems (light competition)
    a = a.sort(pw + ["Height"], descending=[False, False, False, False, True])
    a = a.with_columns([
        (pl.col("fpc_ind").cum_sum().over(pw) - pl.col("fpc_ind")).alias("p_fpc_above"),
        (pl.col("_laic").cum_sum().over(pw) - pl.col("_laic")).alias("p_lai_above"),
        pl.int_range(0, pl.len()).over(pw).cast(pl.Float64).alias("p_n_above"),
    ])
    a = a.with_columns([
        (pl.col("p_n_above") / pl.col("p_n")).alias("p_rank_h"),
        (pl.col("Height") / pl.col("p_hmax")).alias("p_h_rel"),
        (pl.col("agb") / pl.col("p_agb")).alias("p_agb_share"),
        (pl.col("npp").rank("average", descending=True).over(pw) / pl.col("p_n"))
        .alias("p_rank_npp"),
    ])

    # per-stem MEMORY from PAST state only (n6)
    g = ["leg", "Cell", "Patch", "Type", "ID"]
    a = a.sort(g + ["Year"])
    a = a.with_columns([
        pl.col("Year").shift(1).over(g).alias("_ylag"),
        pl.col("agb").shift(1).over(g).alias("_agblag"),
        pl.col("npp").shift(1).over(g).alias("_npplag"),
    ])
    a = a.with_columns([
        pl.when(pl.col("Year") - pl.col("_ylag") == 1)
        .then(pl.col("agb") - pl.col("_agblag")).alias("m_dagb_prev"),
        pl.when(pl.col("Year") - pl.col("_ylag") == 1)
        .then(pl.col("_npplag")).alias("m_npp_prev"),
    ])
    flag = (pl.col("m_dagb_prev") <= 0).fill_null(False)
    a = a.with_columns((~flag).cum_sum().over(g).alias("_blk"))
    a = a.with_columns([
        flag.cast(pl.Int32).cum_sum().over(g + ["_blk"]).alias("m_neg_run"),
        flag.cast(pl.Int32).rolling_sum(window_size=3, min_samples=1).over(g).alias("m_nneg3"),
    ])

    # climate + address
    a = a.join(clim, on=["Cell", "Year"], how="left")
    geo = (pl.read_parquet(CLIMWIN)
           .filter((pl.col("leg") == "historic") & (pl.col("window") == "hist_2000_2019"))
           .select(["Cell", "lat", "lon", "geo_x", "geo_y", "geo_z"]))
    if geo.height == 0:
        geo = (pl.read_parquet(CLIMWIN).select(["Cell", "lat", "lon", "geo_x", "geo_y", "geo_z"])
               .unique(subset=["Cell"]))
    a = a.join(geo, on="Cell", how="left")

    # folds, read from the committed maps (never reimplemented)
    for tag, path in FOLDMAPS.items():
        fm = (pl.read_csv(path, separator=" ", comment_prefix="#", has_header=False,
                          new_columns=["Cell", "fold", "bufmask"])
              .rename({"fold": f"fold_{tag}", "bufmask": f"buf_{tag}"}))
        a = a.join(fm, on="Cell", how="left")
        miss = int(a[f"fold_{tag}"].null_count())
        _say(f"   foldmap {tag}: {miss} stem-years in cells absent from the map "
             f"({a.filter(pl.col(f'fold_{tag}').is_null())['Cell'].n_unique()} cells)")

    a = a.drop(["_ylag", "_agblag", "_npplag", "_blk", "_laic", "gpp", "k_root"])
    a.write_parquet(FEAT)
    _say(f"   wrote {FEAT}  {a.shape}")

    # ---- coverage numbers the response stage needs --------------------------------------------
    hist = a.filter(pl.col("leg") == "historic")
    for c in ("tas_ann", "gdd5", "d_tas_ann"):
        lo, hi = hist[c].min(), hist[c].max()
        late = a.filter((pl.col("leg") == "ssp370") & (pl.col("Year") >= 2080)
                        & (pl.col("Year") <= 2099))
        inr = float(((late[c] >= lo) & (late[c] <= hi)).mean())
        _say(f"   POOLED training-range coverage of ssp370 2080-2099 on {c}: {inr:.4f} "
             f"(historic range {lo:.3f}..{hi:.3f})")
    # per-cell (space-for-time is what carries the pooled coverage)
    pc = (hist.group_by("Cell").agg([pl.col("tas_ann").min().alias("lo"),
                                     pl.col("tas_ann").max().alias("hi")]))
    late = (a.filter((pl.col("leg") == "ssp370") & (pl.col("Year") >= 2080))
            .join(pc, on="Cell", how="inner"))
    inr = float(((late["tas_ann"] >= late["lo"]) & (late["tas_ann"] <= late["hi"])).mean())
    _say(f"   PER-CELL historic-range coverage of ssp370 2080-2100 on tas_ann: {inr:.4f}")
    _stage_prep_biokill(a)
    _say("### STAGE prep DONE")


# survive()'s per-PFT thresholds, read from the live par file with `cpp -P` (never by eye) --
# [SOURCE] /home/jamirp/lpjml56fit/par/pft_lpjmlfit.js keys "temp".low and "min_temprange".
TEMP_LOW = {0: 2.5, 1: -30.0, 2: -15.0, 3: -30.0, 4: -80.0, 5: -80.0, 6: -80.0}
MIN_TRANGE = {0: -1000.0, 1: -1000.0, 2: -1000.0, 3: -1000.0, 4: -1000.0, 5: -1000.0, 6: 30.0}


def _stage_prep_biokill(a: pl.DataFrame) -> None:
    """ATTRIBUTE the deaths the emitted `mort` does NOT describe.

    `isdead` is TRUE if ANY of three things happens ([SOURCE] src/tree/annual_tree.c:31-48):
      (1) allocation_tree returns TRUE  = isneg_tree, a POOL-NEGATIVITY test;
      (2) mortality_tree_ind returns TRUE = `erand48(seed) < mort` OR isneg_tree
          ([SOURCE] src/tree/mortality_tree_ind.c:152-155);
      (3) `!survive(...)` -- the DETERMINISTIC BIOCLIMATIC kill, which is a pure function of the
          cell's 20-year climate buffer and kills EVERY stem of that PFT in that cell at once.
    Only the erand48 draw in (2) is described by the emitted `mort` column, so E[isdead] > E[mort]
    and AUC(mort) is NOT the ceiling for a learner.  This measures how big (3) is, by evaluating
    survive()'s own predicate from the forcing and cross-tabulating it against whole-(cell,PFT,year)
    wipeouts that the hazard does not explain."""
    _say("   --- attribution of the deaths `mort` does not describe ---")
    g = (a.group_by(["leg", "Cell", "Year", "Type"])
         .agg([pl.len().alias("n"), pl.col("isdead").sum().alias("ndead"),
               pl.col("mort").sum().alias("mortsum"), pl.col("mort").mean().alias("mortmean"),
               pl.col("tas_cold_m20").first().alias("tc20"),
               pl.col("trange_m20").first().alias("tr20")]))
    lo = pl.col("Type").replace_strict(TEMP_LOW, return_dtype=pl.Float64)
    mr = pl.col("Type").replace_strict(MIN_TRANGE, return_dtype=pl.Float64)
    g = g.with_columns((((pl.col("tc20") >= lo) & (pl.col("tr20") >= mr))).alias("surv_ok"))
    tot_d = int(g["ndead"].sum())
    tot_m = float(g["mortsum"].sum())
    _say(f"   groups={g.height}  deaths={tot_d}  sum(mort)={tot_m:.1f}  "
         f"excess={tot_d - tot_m:.1f} ({(tot_d - tot_m) / tot_d:.4f} of all deaths)")
    for ok in (True, False):
        s = g.filter(pl.col("surv_ok") == ok)
        if s.height == 0:
            _say(f"   surv_ok={ok}: 0 groups")
            continue
        d, m = int(s["ndead"].sum()), float(s["mortsum"].sum())
        _say(f"   surv_ok={ok!s:5s}: groups={s.height:8d} stemyears={int(s['n'].sum()):9d} "
             f"deaths={d:8d} sum(mort)={m:10.1f} excess={d - m:9.1f} "
             f"deathrate={d / max(int(s['n'].sum()), 1):.5f}")
    # whole-group wipeouts the hazard cannot explain
    wipe = g.filter((pl.col("ndead") == pl.col("n")) & (pl.col("n") >= 5)
                    & (pl.col("mortmean") < 0.5))
    _say(f"   unexplained WIPEOUTS (all n>=5 stems of a (cell,PFT,year) dead, mean mort<0.5): "
         f"{wipe.height} groups, {int(wipe['ndead'].sum())} deaths "
         f"({int(wipe['ndead'].sum()) / tot_d:.4f} of all deaths); "
         f"of those, surv_ok==False in {int((~wipe['surv_ok']).sum())} groups "
         f"({float((~wipe['surv_ok']).mean()):.4f})")
    g.write_csv(f"{OUT}/b2_biokill_groups.csv")
    _say(f"   wrote {OUT}/b2_biokill_groups.csv")


# ================================================================================================
# feature blocks / arms
# ================================================================================================
B1 = ["Age", "Height"]
B2 = ["SLA", "Wooddens", "D95max", "minwscal", "Longevity", "Type"]
B3 = ["npp", "agb", "vegc", "LAI", "fpc_ind", "transp", "wscal_mean"]
B4 = (["p_n", "p_agb", "p_vegc", "p_npp", "p_transp", "p_fpc", "p_lai", "p_hmax", "p_hmean",
       "p_hsd", "p_hmed", "p_agemean", "p_agemax", "p_sla", "p_wd", "p_d95max", "p_minwscal",
       "p_longev", "p_wscal", "p_ntype", "p_fpc_above", "p_lai_above", "p_n_above", "p_rank_h",
       "p_h_rel", "p_agb_share", "p_rank_npp"] + [f"p_npft{t}" for t in range(7)])
B5 = CLIM_ANN + CLIM_ROLL + CLIM_ANOM + [f"w20_{c}" for c in ENV_W20]
B6 = ["m_dagb_prev", "m_npp_prev", "m_neg_run", "m_nneg3"]
BADDR = ["lat", "lon", "geo_x", "geo_y", "geo_z"]

ARMS = {
    "n0": [], "n1": B1, "n2": B1 + B2, "n3": B1 + B2 + B3, "n4": B1 + B2 + B3 + B4,
    "n5": B1 + B2 + B3 + B4 + B5, "n6": B1 + B2 + B3 + B4 + B5 + B6,
    "addr": B1 + B2 + B3 + B4 + BADDR,
    "permclim": B1 + B2 + B3 + B4 + B5,      # climate block permuted across cells
    "ceiling_mort": ["mort"],                # T1 only -- the C's own kill probability
    # --- WHERE does climate's per-stem information go?  Three arms added before the full run
    #     (only an 8-cell smoke run of rungs n0..n3 existed at that point; no climate arm had ever
    #     been scored at any scale).  climonly vs addronly is the ADR-0040 address null applied to
    #     climate ALONE; own_clim vs n3 is the same climate block added WITHOUT the patch block, so
    #     comparing (own_clim - n3) against (n5 - n4) says whether the patch/stand block is what
    #     absorbs climate's information.
    "climonly": B5,
    "addronly": BADDR,
    "own_clim": B1 + B2 + B3 + B5,
}
TOP_ARMS = ["n4", "n5", "addr"]              # the arms run on the second blocked colouring
LGB = dict(objective=None, n_estimators=250, learning_rate=0.06, num_leaves=63,
           min_child_samples=100, max_bin=63, subsample=0.8, subsample_freq=1,
           colsample_bytree=0.8, reg_lambda=1.0, n_jobs=NTHREAD, verbose=-1,
           random_state=RNG, force_col_wise=True)


def _metrics_t1(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import log_loss, roc_auc_score
    pc = np.clip(p, 1e-7, 1 - 1e-7)
    return {"auc": float(roc_auc_score(y, p)) if y.min() != y.max() else float("nan"),
            "brier": float(np.mean((p - y) ** 2)),
            "logloss": float(log_loss(y, pc, labels=[0, 1]))}


def _metrics_t2(y: np.ndarray, p: np.ndarray) -> dict:
    sse = float(np.sum((y - p) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    return {"r2": 1.0 - sse / sst, "rmse": float(np.sqrt(sse / y.size)),
            "sd_y": float(y.std())}


def _permute_climate(df: pl.DataFrame) -> pl.DataFrame:
    """Give each cell ANOTHER cell's climate series (a derangement), consistently for every row.
    Preserves every climate marginal and the temporal structure; destroys the cell-climate link."""
    cells = df["Cell"].unique().sort().to_numpy()
    rng = np.random.default_rng(RNG + 7)
    perm = cells.copy()
    for _ in range(50):
        rng.shuffle(perm)
        if not np.any(perm == cells):
            break
    m = pl.DataFrame({"Cell": cells, "_pcell": perm})
    cl = pl.read_parquet(CLIM).rename({"Cell": "_pcell"})
    return (df.drop(B5).join(m, on="Cell", how="left")
            .join(cl, on=["_pcell", "Year"], how="left").drop("_pcell"))


def _fit_predict(xtr, ytr, xte, task):
    import lightgbm as lgb
    par = dict(LGB)
    par["objective"] = "binary" if task == "t1" else "regression"
    if xtr.shape[1] == 0:
        base = float(ytr.mean())
        return np.full(xte.shape[0], base)
    m = (lgb.LGBMClassifier(**par) if task == "t1" else lgb.LGBMRegressor(**par))
    m.fit(xtr, ytr)
    return (m.predict_proba(xte)[:, 1] if task == "t1" else m.predict(xte))


def _fit_predict_lin(xtr, ytr, xte, task):
    """Second hypothesis class: a LINEAR model, which unlike a tree CAN extrapolate outside the
    training range. Load-bearing for the response stage -- a tree that cannot extrapolate would
    report 'no response' for a purely mechanical reason."""
    from sklearn.linear_model import LogisticRegression, Ridge
    mu, sd = np.nanmean(xtr, axis=0), np.nanstd(xtr, axis=0)
    sd[sd == 0] = 1.0
    ztr = np.nan_to_num((xtr - mu) / sd)
    zte = np.nan_to_num((xte - mu) / sd)
    if task == "t1":
        m = LogisticRegression(max_iter=300, C=1.0)
        m.fit(ztr, ytr)
        return m.predict_proba(zte)[:, 1]
    m = Ridge(alpha=10.0)
    m.fit(ztr, ytr)
    return m.predict(zte)


def _load(task: str, n: int | None) -> pl.DataFrame:
    lf = pl.scan_parquet(FEAT)
    if task == "t2":
        lf = lf.filter(pl.col("pairable") & (pl.col("survived") == 1)
                       & pl.col("d_agb").is_not_null())
    df = lf.collect()
    if n is not None and df.height > n:
        df = df.sample(n=n, seed=RNG, shuffle=False)
    return df


# ================================================================================================
# STAGE ladder
# ================================================================================================
def stage_ladder() -> None:
    print(PREREG, flush=True)
    _say(f"### STAGE ladder   NTHREAD={NTHREAD} LADDER_N={LADDER_N}")
    rows, calib, subs = [], [], []
    for task, ycol in [("t1", "isdead"), ("t2", "d_agb")]:
        df = _load(task, LADDER_N)
        _say(f"   {task}: {df.height} rows, {df['Cell'].n_unique()} cells, "
             f"target mean {df[ycol].mean():.6g}")
        dfp = _permute_climate(df)
        arms = [a for a in ARMS if not (a == "ceiling_mort" and task == "t2")]
        for scheme in ("hash5", "block_s0", "block_s1"):
            use = arms if scheme != "block_s1" else TOP_ARMS
            fc, bc = f"fold_{scheme}", f"buf_{scheme}"
            d = df.filter(pl.col(fc).is_not_null())
            dq = dfp.filter(pl.col(fc).is_not_null())
            for arm in use:
                cols = ARMS[arm]
                src = dq if arm == "permclim" else d
                y = src[ycol].to_numpy().astype(np.float64)
                x = (src.select(cols).to_numpy().astype(np.float32)
                     if cols else np.zeros((src.height, 0), dtype=np.float32))
                fold = src[fc].to_numpy()
                buf = src[bc].to_numpy()
                per = []
                for k in range(5):
                    te = fold == k
                    tr = (fold != k) & (((buf >> k) & 1) == 0)
                    if te.sum() == 0 or tr.sum() == 0:
                        continue
                    if arm == "ceiling_mort":
                        p = x[te, 0]
                    else:
                        p = _fit_predict(x[tr], y[tr], x[te], task)
                    yte = y[te]
                    m = _metrics_t1(yte, p) if task == "t1" else _metrics_t2(yte, p)
                    m.update(fold=k, n_te=int(te.sum()), n_tr=int(tr.sum()))
                    per.append(m)
                    if arm in ("n4", "n5", "n6", "ceiling_mort") and scheme == "hash5":
                        if task == "t1":
                            q = np.quantile(p, np.linspace(0, 1, 11))
                            q[0], q[-1] = -np.inf, np.inf
                            b = np.digitize(p, q[1:-1])
                            for j in range(10):
                                s = b == j
                                if s.sum() > 0:
                                    calib.append(dict(task=task, arm=arm, fold=k, decile=j,
                                                      n=int(s.sum()),
                                                      pred=float(p[s].mean()),
                                                      obs=float(yte[s].mean())))
                        cm = src["mort"].to_numpy()[te]
                        for lab, sel in (("certain", cm >= 1.0), ("discretionary", cm < 1.0)):
                            if sel.sum() > 100:
                                mm = (_metrics_t1(yte[sel], p[sel]) if task == "t1"
                                      else _metrics_t2(yte[sel], p[sel]))
                                mm.update(task=task, arm=arm, fold=k, subset=lab,
                                          n=int(sel.sum()),
                                          target_mean=float(yte[sel].mean()))
                                subs.append(mm)
                key = "auc" if task == "t1" else "r2"
                v = np.array([q[key] for q in per])
                rows.append(dict(task=task, scheme=scheme, arm=arm, nfeat=len(cols),
                                 nfold=len(per), mean=float(v.mean()),
                                 sd=float(v.std(ddof=1)) if v.size > 1 else float("nan"),
                                 se=float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else
                                 float("nan"),
                                 **{f"f{q['fold']}": q[key] for q in per},
                                 **{f"aux_{k2}": float(np.mean([q[k2] for q in per]))
                                    for k2 in per[0] if k2 not in (key, "fold")}))
                _say(f"   {task} {scheme:9s} {arm:13s} nfeat={len(cols):3d} "
                     f"{key}={v.mean():.5f} +/- {rows[-1]['se']:.5f}  folds="
                     + " ".join(f"{q:.4f}" for q in v))
        # paired increments with their own SE (the pre-registered noise definition)
        _say(f"   --- {task}: paired rung increments (hash5) ---")
        for scheme in ("hash5", "block_s0"):
            got = {r["arm"]: r for r in rows if r["task"] == task and r["scheme"] == scheme}
            for a, b in [("n1", "n0"), ("n2", "n1"), ("n3", "n2"), ("n4", "n3"), ("n5", "n4"),
                         ("n6", "n5"), ("addr", "n4"), ("permclim", "n4"), ("n6", "n1"),
                         ("climonly", "n0"), ("climonly", "addronly"), ("own_clim", "n3"),
                         ("n4", "own_clim")]:
                if a in got and b in got:
                    fa = np.array([got[a][f"f{k}"] for k in range(5) if f"f{k}" in got[a]])
                    fb = np.array([got[b][f"f{k}"] for k in range(5) if f"f{k}" in got[b]])
                    if fa.size == fb.size and fa.size > 1:
                        d0 = fa - fb
                        se = d0.std(ddof=1) / np.sqrt(d0.size)
                        rows.append(dict(task=task, scheme=scheme, arm=f"DELTA_{a}_minus_{b}",
                                         nfeat=-1, nfold=d0.size, mean=float(d0.mean()),
                                         sd=float(d0.std(ddof=1)), se=float(se)))
                        _say(f"   {task} {scheme:9s} DELTA {a:8s}-{b:8s} = "
                             f"{d0.mean():+.5f} +/- {se:.5f} (2SE={2 * se:.5f}) "
                             f"{'SIGNIFICANT' if abs(d0.mean()) > 2 * se else 'within noise'}")
    pl.DataFrame(rows).write_csv(f"{OUT}/b2_ladder.csv")
    pl.DataFrame(calib).write_csv(f"{OUT}/b2_calibration.csv")
    pl.DataFrame(subs).write_csv(f"{OUT}/b2_subsets.csv")
    _say(f"   wrote {OUT}/b2_ladder.csv, b2_calibration.csv, b2_subsets.csv")

    # N3 self-check on the label: Brier(mort) must equal mean(mort*(1-mort))
    d = _load("t1", LADDER_N)
    mo = d["mort"].to_numpy()
    yy = d["isdead"].to_numpy()
    _say(f"   N3 label self-check: Brier(mort)={np.mean((mo - yy) ** 2):.6f} vs "
         f"mean(mort*(1-mort))={np.mean(mo * (1 - mo)):.6f}; "
         f"frac(mort>=1)={np.mean(mo >= 1):.6f}; "
         f"frac of deaths that are certain={np.mean(mo[yy == 1] >= 1):.6f}")
    _say("### STAGE ladder DONE")


# ================================================================================================
# STAGE resp
# ================================================================================================
def _slope_origin(x: np.ndarray, y: np.ndarray) -> float:
    d = float(np.sum(x * x))
    return float(np.sum(x * y) / d) if d > 0 else float("nan")


def _boot_slope(x, y, nb=500):
    rng = np.random.default_rng(RNG + 3)
    s = np.empty(nb)
    for i in range(nb):
        j = rng.integers(0, x.size, x.size)
        s[i] = _slope_origin(x[j], y[j])
    return float(np.nanstd(s))


def stage_resp() -> None:
    print(PREREG, flush=True)
    _say(f"### STAGE resp   NTHREAD={NTHREAD}")
    res, cellrows = [], []
    for task, ycol in [("t1", "isdead"), ("t2", "d_agb")]:
        df = _load(task, None)
        _say(f"   {task}: {df.height} rows total")
        dfp = _permute_climate(df)
        fc, bc = "fold_hash5", "buf_hash5"
        df = df.filter(pl.col(fc).is_not_null())
        dfp = dfp.filter(pl.col(fc).is_not_null())
        wl = np.full(df.height, "", dtype=object)
        yr = df["Year"].to_numpy()
        leg = df["leg"].to_numpy()
        for lab, lg, y0, y1 in WINDOWS:
            wl[(leg == lg) & (yr >= y0) & (yr <= y1)] = lab
        cellv = df["Cell"].to_numpy()
        yv = df[ycol].to_numpy().astype(np.float64)
        fold = df[fc].to_numpy()
        buf = df[bc].to_numpy()
        is_hist = leg == "historic"

        for arm in ("n3", "n4", "n5", "n6", "addr", "permclim", "climonly", "own_clim",
                    "addronly"):
            src = dfp if arm == "permclim" else df
            cols = ARMS[arm]
            x = src.select(cols).to_numpy().astype(np.float32)
            for mdl in ("gbm", "lin"):
                pred = np.full(df.height, np.nan)
                for k in range(5):
                    tr = is_hist & (fold != k) & (((buf >> k) & 1) == 0)
                    te = fold == k
                    if tr.sum() == 0 or te.sum() == 0:
                        continue
                    fn = _fit_predict if mdl == "gbm" else _fit_predict_lin
                    pred[te] = fn(x[tr], yv[tr], x[te], task)
                agg = pl.DataFrame({"Cell": cellv, "win": wl, "y": yv, "p": pred})
                agg = (agg.filter(pl.col("win") != "")
                       .group_by(["Cell", "win"])
                       .agg([pl.len().alias("n"), pl.col("y").mean().alias("truth"),
                             pl.col("p").mean().alias("pred")]))
                w = (agg.filter(pl.col("n") >= MIN_STEMYEARS)
                     .pivot(on="win", index="Cell", values=["truth", "pred"]))
                for late in ("ssp_late", "ssp_early"):
                    need = [f"truth_{late}", "truth_hist", f"pred_{late}", "pred_hist"]
                    if not all(c in w.columns for c in need):
                        continue
                    ww = w.drop_nulls(need)
                    tx = (ww[f"truth_{late}"] - ww["truth_hist"]).to_numpy()
                    py = (ww[f"pred_{late}"] - ww["pred_hist"]).to_numpy()
                    sl = _slope_origin(tx, py)
                    se = _boot_slope(tx, py)
                    r = float(np.corrcoef(tx, py)[0, 1]) if tx.size > 2 else float("nan")
                    res.append(dict(task=task, arm=arm, model=mdl, window=late, ncell=tx.size,
                                    slope=sl, slope_se=se, corr=r,
                                    rms_true=float(np.sqrt(np.mean(tx ** 2))),
                                    rms_pred=float(np.sqrt(np.mean(py ** 2))),
                                    mean_true=float(tx.mean()), mean_pred=float(py.mean())))
                    _say(f"   {task} {arm:9s} {mdl} {late:9s} ncell={tx.size:4d} "
                         f"slope={sl:+.4f}+/-{se:.4f} r={r:+.4f} "
                         f"rms_true={np.sqrt(np.mean(tx ** 2)):.5g} "
                         f"rms_pred={np.sqrt(np.mean(py ** 2)):.5g}")
                    if arm in ("n4", "n5") and mdl == "gbm":
                        cellrows.append(ww.with_columns([
                            pl.lit(task).alias("task"), pl.lit(arm).alias("arm"),
                            pl.lit(late).alias("window")]))
        # ---- the two-seed noise floor on the TRUTH (no model at all) --------------------------
        lf = pl.scan_parquet(TABLE_A).filter(pl.col("Type") <= 6).filter(pl.col("dup_key") == 0)
        if task == "t2":
            lf = lf.filter(pl.col("pairable") & (pl.col("survived") == 1)
                           & pl.col("d_agb").is_not_null())
        t = lf.select(["leg", "seed", "Cell", "Year", ycol]).collect()
        t = t.join(pl.read_csv(SUSPECT).select(["leg", "seed", "Cell"]).unique(),
                   on=["leg", "seed", "Cell"], how="anti")
        wexp = pl.concat([
            t.filter((pl.col("leg") == lg) & (pl.col("Year") >= y0) & (pl.col("Year") <= y1))
            .with_columns(pl.lit(lab).alias("win"))
            for lab, lg, y0, y1 in WINDOWS])
        g = (wexp.group_by(["seed", "Cell", "win"])
             .agg([pl.len().alias("n"), pl.col(ycol).mean().alias("truth")])
             .filter(pl.col("n") >= MIN_STEMYEARS)
             .pivot(on="win", index=["seed", "Cell"], values="truth"))
        for late in ("ssp_late", "ssp_early"):
            if late not in g.columns or "hist" not in g.columns:
                continue
            gg = (g.drop_nulls([late, "hist"])
                  .with_columns((pl.col(late) - pl.col("hist")).alias("diff"))
                  .select(["seed", "Cell", "diff"])
                  .pivot(on="seed", index="Cell", values="diff").drop_nulls())
            a1 = gg["1"].to_numpy()
            a2 = gg["2"].to_numpy()
            sl = _slope_origin(a1, a2)
            r = float(np.corrcoef(a1, a2)[0, 1])
            res.append(dict(task=task, arm="TRUTH_seed2_on_seed1", model="none", window=late,
                            ncell=a1.size, slope=sl, slope_se=_boot_slope(a1, a2), corr=r,
                            rms_true=float(np.sqrt(np.mean(a1 ** 2))),
                            rms_pred=float(np.sqrt(np.mean(a2 ** 2))),
                            mean_true=float(a1.mean()), mean_pred=float(a2.mean())))
            _say(f"   {task} NOISE FLOOR   {late:9s} ncell={a1.size:4d} truth(s2) on truth(s1): "
                 f"slope={sl:+.4f} r={r:+.4f} rms_s1={np.sqrt(np.mean(a1 ** 2)):.5g} "
                 f"rms(s1-s2)/sqrt2={np.sqrt(np.mean((a1 - a2) ** 2) / 2):.5g}")
            res.append(dict(task=task, arm="NULL_do_nothing", model="none", window=late,
                            ncell=a1.size, slope=0.0, slope_se=0.0, corr=float("nan"),
                            rms_true=float(np.sqrt(np.mean(a1 ** 2))), rms_pred=0.0,
                            mean_true=float(a1.mean()), mean_pred=0.0))
    pl.DataFrame(res).write_csv(f"{OUT}/b2_response.csv")
    if cellrows:
        pl.concat(cellrows, how="diagonal").write_parquet(f"{OUT}/b2_response_cells.parquet")
    _say(f"   wrote {OUT}/b2_response.csv (+ b2_response_cells.parquet)")
    _say("### STAGE resp DONE")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: explore_perstem_ladder.py {prep|ladder|resp} [arg]")
    st = sys.argv[1]
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    _say(f"K_LIGHTEXT imported = {dict(K_LIGHTEXT)}")
    if st == "prep":
        stage_prep(arg)
    elif st == "smoke":
        global FEAT, CLIM, LADDER_N
        stage_prep(arg or 8)
        LADDER_N = 200_000
        stage_ladder()
        stage_resp()
    else:
        {"ladder": stage_ladder, "resp": stage_resp}[st]()


if __name__ == "__main__":
    main()
