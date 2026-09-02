"""B5 — is a FIXED-SIZE stand summary information-sufficient for the fluxes an atmosphere needs?

Line X exploration probe (read-only). Answers ADR 0310 section 11's first unverified item:
whether a compact, fixed-dimensional summary of a patch's tree roster determines the patch's
carbon and water flux, or whether the flux head needs the roster itself.

Stages (positional arg 1):
  build   -- build the patch-year feature table (summary tiers + roster shape + climate + targets)
  model   -- the arm ladder: level R^2, within-cell-year R^2, and the historic->ssp370 response
  nonlin  -- direct tests of the three named per-stem nonlinearities

Everything is written to /p/tmp/jamirp/X_explore/suff_*.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "/p/tmp/jamirp/X_explore"
GLOB = "/p/tmp/jamirp/emulator_global"

A_TAB = f"{OUT}/prep_paired_stems.parquet"
CLIM = f"{OUT}/b2_cellyear_clim.parquet"
SUSPECT = f"{OUT}/prep_suspect_cell_blocks.csv"
FEAT = f"{OUT}/suff_patch_features.parquet"

# per-PFT Lambert-Beer extinction, imported convention (K_LAMBERT_BEER_BL 0.59 / _NL 0.45)
K_BEER = {0: 0.59, 1: 0.45, 2: 0.59, 3: 0.59, 4: 0.45, 5: 0.59, 6: 0.45}

CLIM_COLS = [
    "tas_ann", "tas_cold", "tas_warm", "tas_seas", "gdd5",
    "frostdays", "pr_ann", "rsds_ann", "huss_ann",
]

TIER = {
    "k3": ["n_stems", "lai_stand", "agb_sum"],
    "k6": ["n_stems", "lai_stand", "agb_sum", "h_mean", "h_max", "age_mean"],
    "k10": ["n_stems", "lai_stand", "agb_sum", "h_mean", "h_max", "age_mean",
            "fpc_sum", "h_sd", "SLA_mean", "Wooddens_mean"],
    "k14": ["n_stems", "lai_stand", "agb_sum", "h_mean", "h_max", "age_mean",
            "fpc_sum", "h_sd", "SLA_mean", "Wooddens_mean",
            "vegc_sum", "D95max_mean", "minwscal_mean", "Longevity_mean"],
}
TIER["k21"] = TIER["k14"] + [f"frac_pft{i}" for i in range(7)]

SHAPE = [
    "h_p10", "h_p25", "h_p50", "h_p75", "h_p90", "h_min",
    "agb_p50", "agb_p90", "agb_max_frac", "agb_cv",
    "lai_mean", "lai_sd", "fpc_sd", "fpc_max",
    "SLA_sd", "Wooddens_sd", "D95max_sd", "minwscal_sd", "Longevity_sd",
    "cov_h_sla", "cov_h_wd", "cov_h_lai", "age_sd",
    "nbin_5_10", "nbin_10_20", "nbin_20_30", "nbin_30p",
    "sla_jensen",
]

PREREG = r"""
================================================================================
PRE-REGISTRATION -- B5, written before any result was computed
================================================================================
QUESTION
  Is a FIXED-SIZE summary of a patch's tree roster (plus that year's climate)
  information-sufficient to determine that patch's total tree carbon flux and
  tree transpiration -- at the LEVEL, and at the historic->ssp370 RESPONSE?
  Equivalently: can the daily/annual flux head of a data-driven emulator be a
  network on a compact per-cell state, or does it need the individual roster?

  Framing note: a flux head is TEACHER-FORCED by construction -- it is handed the
  current state and must return the flux.  So this is an information-sufficiency
  question about a fixed-dimensional statistic of the roster, not a forecasting
  question.  It is NOT a test of forcing extrapolation.

BASIS (stated with every number, per trap 3)
  PRIMARY basis = per PATCH-YEAR, seed 1, 674-cell deterministic sample
  (Cell % 100 == 0; 549 tree-bearing in historic, 598 in ssp370), historic
  2000-2019 + ssp370 2020-2100, ALL EMITTED stems (isdead 0 and 1, because a stem
  that dies at the end of year y still produced year y's flux), above the model's
  own 5 m writer cut only.  This is NOT the acceptance basis (ADR 0106: per cell,
  all 54 020 tree-bearing cells, both scenarios, tolerance max(10 %, the C's own
  two-run spread)); the per-cell 20-yr-mean numbers below are the closest thing to
  it and are labelled as such.

TARGET
  T1 = patch-total annual tree NPP  = sum over emitted stems of the `npp` column
  T2 = patch-total annual tree transpiration = sum of the `transp` column
  Both are EXACT sums of emitted per-stem quantities, so the roster-complete
  predictor is the identity and the only question is what a summary discards.

BLESSED STATISTICS
  S1  out-of-sample R^2 of T1, 5 folds, PRIMARY fold scheme = spatially BLOCKED
      (15 deg lon x 5 deg lat tiles assigned to folds); secondary = hashed by cell
  S2  out-of-sample R^2 of T1 on the WITHIN-cell-year deviation (climate exactly
      controlled -- the purest sufficiency test)
  S3  through-origin response score on the per-cell 20-yr means,
      R2_0 = 1 - sum((dT - dP)^2) / sum(dT^2), where
      dT = true  mean(T1) over ssp370 2080-2099 minus over historic 2000-2019
      dP = predicted same, on IDENTICAL row sets (so occupancy cancels)
      plus the OLS slope of dT on dP and Pearson r
  S4  out-of-sample R^2 of T2

NULLS AND THE VALUE EACH MUST RETURN  (derived BEFORE the run)
  n0  CLIMATE ONLY, no stand state at all.
      Climate is constant across the 25 patches of a cell-year, so n0's R^2 is
      bounded ABOVE by the between-cell-year variance share
          R2_max(n0) = 1 - E[Var(T1 | Cell,Year)] / Var(T1).
      I compute that bound and print it as the FIRST result.  If n0 exceeds it the
      code is wrong.  On S2 (within-cell-year deviation) n0 must return EXACTLY
      <= 0.0000, because a climate-only predictor is constant within a cell-year.
  n1  lai_stand ALONE (the classic big-leaf state).  IF a big-leaf state were
      sufficient, n1 must return R^2 within 0.02 of the best roster-informed arm
      (n3).  Derived expectation if it is NOT sufficient: patch NPP scales with
      stem number and stem size while stand LAI saturates through Beer-Lambert, so
      n1 should fall well short.
  n1b lai_stand + climate.
  nP  PERSISTENCE, ZERO PARAMETERS: predict T1(patch, y) = T1(patch, y-1).
      Its value is computed in closed form as
          R2 = 1 - sum((T1_y - T1_{y-1})^2) / sum((T1_y - mean)^2)
      on exactly the rows where the lag exists.  MANDATORY (campaign standing rule
      after ADR 0311 section 8).  Any summary arm that does not beat nP has
      demonstrated nothing.  On the RESPONSE, nP is expected to be NEARLY PERFECT
      (a one-year lag reproduces a 60-year window difference almost exactly), so
      it is reported as a ceiling-style reference, not as a competitor.
  nZ  DO-NOTHING on the response: dP = 0 for every cell.  By construction of
      S3 this returns EXACTLY 0.0000.
  nU  UNIFORM response: dP = mean(dT) for every cell.  Value computed in closed
      form, no model.
  n2  THE ARM UNDER TEST: the fixed-size summary (k21) + climate.
  n3  THE ROSTER-INFORMED REFERENCE: n2 + 28 roster-shape statistics the summary
      discards (height quantiles, trait dispersions, size-trait covariances,
      size-class counts, dominance, and a mechanism-derived Jensen gap for the
      SLA cap on Vcmax).

FALSIFIER  (what result makes me say a fixed-size summary is NOT sufficient)
  LEVEL:     R^2(n3) - R^2(n2) > 0.02  on S1, or > 0.02 on S2.
  RESPONSE:  |slope(n3) - slope(n2)| > 0.10, or slope(n2) outside [0.90, 1.10],
             or R2_0(n2) < 0.80.
  A named per-stem nonlinearity MATTERS if adding its own dispersion statistic
  alone to n2 raises R^2 by >= 0.005 AND the |partial correlation| of n2's
  out-of-sample residual with that statistic exceeds 0.05.
  If instead R^2(n3) - R^2(n2) <= 0.02 AND the response slopes agree to 0.10,
  I conclude a fixed-size summary IS sufficient at the ANNUAL flux level on this
  basis, and say so plainly even though it is the less interesting answer.

WHAT THIS CANNOT DECIDE (stated before the run)
  (a) The DAILY fluxes.  The 199 GB daily dataset carries only ALL-PFT fluxes and
      no per-PFT split, so grass (up to 42 % of GPP) cannot be removed and the
      mandatory basis check of the fdiff-validate skill cannot be satisfied.  Its
      directory listing is reported as a coverage finding.
  (b) The roster-complete ceiling.  Under -DPERMUTE each stem's realised water
      supply is clipped against a RUNNING cross-stem accumulator in a randomly
      permuted order, so even the full roster does not determine the flux.  Every
      R^2 below therefore has an unmeasured ceiling < 1, and n3's residual is an
      UPPER bound on that permutation noise, not a measurement of it.
================================================================================
"""


def log(*a):
    print(*a, flush=True)


def suspect_filter(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Exclude the 5 damaged (leg, seed, Cell) blocks flagged by the prep agent."""
    sus = pl.read_csv(SUSPECT)
    log("suspect blocks file columns:", sus.columns)
    key = sus.select(["leg", "seed", "Cell"]).unique().with_columns(
        pl.col("seed").cast(pl.Int8), pl.col("Cell").cast(pl.Int64)
    )
    log(f"excluding {key.height} damaged (leg,seed,Cell) blocks")
    return lf.join(key.lazy(), on=["leg", "seed", "Cell"], how="anti")


# ----------------------------------------------------------------- stage build
def stage_build(seeds: list[int]) -> None:
    t0 = time.time()
    keep = [
        "leg", "seed", "Cell", "Patch", "Year", "Type", "Height", "Age", "agb",
        "vegc", "transp", "npp", "SLA", "Longevity", "Wooddens", "LAI",
        "fpc_ind", "minwscal", "D95max", "isdead",
    ]
    lf = pl.scan_parquet(A_TAB).select(keep).filter(pl.col("seed").is_in(seeds))
    lf = suspect_filter(lf)
    # per-PFT Beer coefficient for the stand-LAI reconstruction (ADR 0035)
    kmap = pl.when(pl.col("Type") == 0).then(0.59)
    for t, k in K_BEER.items():
        if t == 0:
            continue
        kmap = kmap.when(pl.col("Type") == t).then(k)
    lf = lf.with_columns(kmap.otherwise(None).alias("k_beer"))
    lf = lf.with_columns(
        pl.when(pl.col("LAI") > 1e-12)
        .then(pl.col("LAI") * pl.col("fpc_ind")
              / (1.0 - (-pl.col("k_beer") * pl.col("LAI")).exp()))
        .otherwise(0.0).alias("lai_contrib"),
        (pl.col("SLA") ** (-0.383)).alias("sla_pow"),
    )

    g = ["leg", "seed", "Cell", "Patch", "Year"]
    aggs = [
        pl.len().alias("n_stems"),
        pl.col("lai_contrib").sum().alias("lai_stand"),
        pl.col("agb").sum().alias("agb_sum"),
        pl.col("vegc").sum().alias("vegc_sum"),
        pl.col("npp").sum().alias("npp_sum"),
        pl.col("transp").sum().alias("transp_sum"),
        pl.col("fpc_ind").sum().alias("fpc_sum"),
        pl.col("Height").mean().alias("h_mean"),
        pl.col("Height").max().alias("h_max"),
        pl.col("Height").min().alias("h_min"),
        pl.col("Height").std().alias("h_sd"),
        pl.col("Age").mean().alias("age_mean"),
        pl.col("Age").cast(pl.Float64).std().alias("age_sd"),
        pl.col("SLA").mean().alias("SLA_mean"),
        pl.col("Wooddens").mean().alias("Wooddens_mean"),
        pl.col("D95max").mean().alias("D95max_mean"),
        pl.col("minwscal").mean().alias("minwscal_mean"),
        pl.col("Longevity").mean().alias("Longevity_mean"),
        pl.col("SLA").std().alias("SLA_sd"),
        pl.col("Wooddens").std().alias("Wooddens_sd"),
        pl.col("D95max").std().alias("D95max_sd"),
        pl.col("minwscal").std().alias("minwscal_sd"),
        pl.col("Longevity").std().alias("Longevity_sd"),
        pl.col("LAI").mean().alias("lai_mean"),
        pl.col("LAI").std().alias("lai_sd"),
        pl.col("fpc_ind").std().alias("fpc_sd"),
        pl.col("fpc_ind").max().alias("fpc_max"),
        pl.col("agb").max().alias("agb_max"),
        pl.col("agb").std().alias("agb_sd"),
        pl.col("agb").quantile(0.5).alias("agb_p50"),
        pl.col("agb").quantile(0.9).alias("agb_p90"),
        pl.col("Height").quantile(0.10).alias("h_p10"),
        pl.col("Height").quantile(0.25).alias("h_p25"),
        pl.col("Height").quantile(0.50).alias("h_p50"),
        pl.col("Height").quantile(0.75).alias("h_p75"),
        pl.col("Height").quantile(0.90).alias("h_p90"),
        pl.cov("Height", "SLA").alias("cov_h_sla"),
        pl.cov("Height", "Wooddens").alias("cov_h_wd"),
        pl.cov("Height", "LAI").alias("cov_h_lai"),
        (pl.col("sla_pow").mean() - pl.col("SLA").mean() ** (-0.383)).alias("sla_jensen"),
        ((pl.col("Height") >= 5) & (pl.col("Height") < 10)).sum().alias("nbin_5_10"),
        ((pl.col("Height") >= 10) & (pl.col("Height") < 20)).sum().alias("nbin_10_20"),
        ((pl.col("Height") >= 20) & (pl.col("Height") < 30)).sum().alias("nbin_20_30"),
        (pl.col("Height") >= 30).sum().alias("nbin_30p"),
        (pl.col("npp") < 0).mean().alias("f_npp_neg"),
        pl.col("npp").filter(pl.col("npp") < 0).sum().alias("npp_neg_sum"),
        pl.col("isdead").mean().alias("f_dead"),
    ]
    for i in range(7):
        aggs.append((pl.col("Type") == i).mean().alias(f"frac_pft{i}"))

    df = lf.group_by(g).agg(aggs).collect()          # NON-streaming (key-set safety)
    assert df.select(g).n_unique() == df.height, "duplicate patch-year key"
    log(f"[build] patch-year rows={df.height} unique-key OK  ({time.time()-t0:.0f}s)")

    df = df.with_columns(
        (pl.col("agb_max") / pl.col("agb_sum")).alias("agb_max_frac"),
        (pl.col("agb_sd") / pl.col("agb_sum") * pl.col("n_stems")).alias("agb_cv"),
        pl.col("n_stems").cast(pl.Float64),
    )
    # persistence: previous year's own patch total (same leg+seed+cell+patch)
    df = df.sort(["leg", "seed", "Cell", "Patch", "Year"]).with_columns(
        pl.col("npp_sum").shift(1).over(["leg", "seed", "Cell", "Patch"]).alias("npp_lag1"),
        pl.col("transp_sum").shift(1).over(["leg", "seed", "Cell", "Patch"]).alias("transp_lag1"),
        pl.col("Year").shift(1).over(["leg", "seed", "Cell", "Patch"]).alias("year_lag1"),
    ).with_columns(
        pl.when(pl.col("year_lag1") == pl.col("Year") - 1)
        .then(pl.col("npp_lag1")).otherwise(None).alias("npp_lag1"),
        pl.when(pl.col("year_lag1") == pl.col("Year") - 1)
        .then(pl.col("transp_lag1")).otherwise(None).alias("transp_lag1"),
    )

    clim = pl.read_parquet(CLIM).select(["Cell", "Year"] + CLIM_COLS)
    n0 = df.height
    df = df.join(clim, on=["Cell", "Year"], how="left")
    miss = df.select(pl.col("tas_ann").is_null().mean()).item()
    log(f"[build] climate join: rows {n0} -> {df.height}, missing climate frac={miss:.6f}")
    df = df.filter(pl.col("tas_ann").is_not_null())

    # 15 deg lon x 5 deg lat blocked folds, from the shared per-cell climatology table
    geo = (pl.read_parquet(f"{OUT}/prep_cell_window_clim.parquet")
           .select(["Cell", "lat", "lon"]).unique(subset=["Cell"]))
    df = df.join(geo, on="Cell", how="left")
    assert df.select(pl.col("lat").is_null().sum()).item() == 0, "cells without lat/lon"
    df = df.with_columns(
        (((pl.col("lon") + 180) / 15).floor().cast(pl.Int64) * 1000
         + ((pl.col("lat") + 90) / 5).floor().cast(pl.Int64)).alias("tile")
    )
    tiles = sorted(df.select("tile").unique().to_series().to_list())
    rng = np.random.default_rng(20260902)
    tf = {t: int(f) for t, f in zip(tiles, rng.integers(0, 5, len(tiles)), strict=True)}
    df = df.with_columns(
        pl.col("tile").replace_strict(tf, return_dtype=pl.Int64).alias("fold_blocked"),
        ((pl.col("Cell") // 100) % 5).alias("fold_hashed"),
    )
    log(f"[build] {len(tiles)} populated 15x5 tiles -> 5 blocked folds")
    log(df.group_by("fold_blocked").agg(
        pl.len(), pl.col("Cell").n_unique().alias("nc")).sort("fold_blocked"))

    df.write_parquet(FEAT)
    log(f"[build] wrote {FEAT}  rows={df.height} cols={len(df.columns)} ({time.time()-t0:.0f}s)")


# ----------------------------------------------------------------- stage model
def r2(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ss = ((y - p) ** 2).sum()
    sm = ((y - y.mean()) ** 2).sum()
    return 1.0 - ss / sm


def fit_arm(df: pl.DataFrame, feats: list[str], target: str, foldcol: str, ncpu: int):
    import lightgbm as lgb
    y = df[target].to_numpy()
    X = df.select(feats).to_numpy()
    folds = df[foldcol].to_numpy()
    pred = np.full(len(y), np.nan)
    for f in sorted(set(folds.tolist())):
        tr, te = folds != f, folds == f
        m = lgb.LGBMRegressor(
            n_estimators=400, learning_rate=0.06, num_leaves=63,
            min_child_samples=40, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.9, n_jobs=ncpu, verbose=-1, random_state=7,
        )
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


def within_r2(df: pl.DataFrame, y: np.ndarray, p: np.ndarray) -> float:
    """R^2 on the within-cell-year deviation: climate exactly controlled."""
    d = df.select(["Cell", "Year"]).with_columns(
        pl.Series("y", y), pl.Series("p", p)
    ).with_columns(
        (pl.col("y") - pl.col("y").mean().over(["Cell", "Year"])).alias("yd"),
        (pl.col("p") - pl.col("p").mean().over(["Cell", "Year"])).alias("pd"),
    )
    return r2(d["yd"].to_numpy(), d["pd"].to_numpy())


def response_score(df: pl.DataFrame, y: np.ndarray, p: np.ndarray):
    """Per-cell 20-yr-mean historic(2000-2019) -> ssp370(2080-2099) change."""
    d = df.select(["leg", "Cell", "Year"]).with_columns(pl.Series("y", y), pl.Series("p", p))
    h = d.filter((pl.col("leg") == "historic") & (pl.col("Year").is_between(2000, 2019)))
    f = d.filter((pl.col("leg") == "ssp370") & (pl.col("Year").is_between(2080, 2099)))
    hm = h.group_by("Cell").agg(pl.col("y").mean().alias("yh"), pl.col("p").mean().alias("ph"))
    fm = f.group_by("Cell").agg(pl.col("y").mean().alias("yf"), pl.col("p").mean().alias("pf"))
    j = hm.join(fm, on="Cell", how="inner")   # a cell must exist in BOTH windows to have a delta
    dt = (j["yf"] - j["yh"]).to_numpy()
    dp = (j["pf"] - j["ph"]).to_numpy()
    r2_0 = 1.0 - ((dt - dp) ** 2).sum() / (dt**2).sum()
    dpc = dp - dp.mean()
    slope = float(np.dot(dpc, dt - dt.mean()) / max((dpc**2).sum(), 1e-30))
    slope0 = float(np.dot(dp, dt) / max((dp**2).sum(), 1e-30))
    rr = float(np.corrcoef(dt, dp)[0, 1]) if dp.std() > 0 else float("nan")
    return dict(n_cells=len(dt), resp_R2_0=r2_0, resp_slope=slope,
                resp_slope_origin=slope0, resp_r=rr,
                mean_dt=float(dt.mean()), mean_dp=float(dp.mean()),
                sd_dt=float(dt.std()), sd_dp=float(dp.std()))


def stage_model(ncpu: int) -> None:
    df = pl.read_parquet(FEAT).filter(pl.col("seed") == 1)
    log(f"[model] rows={df.height} cells={df['Cell'].n_unique()} (seed 1)")

    # ---- the derived n0 ceiling and the persistence null: closed form, no model
    tgt = "npp_sum"
    y = df[tgt].to_numpy()
    within = df.select(["Cell", "Year", tgt]).with_columns(
        (pl.col(tgt) - pl.col(tgt).mean().over(["Cell", "Year"])).alias("d")
    )
    var_within = float((within["d"].to_numpy() ** 2).mean())
    var_tot = float(((y - y.mean()) ** 2).mean())
    n0_cap = 1.0 - var_within / var_tot
    log(f"\n[RESULT 1 -- the derived n0 ceiling] between-cell-year variance share "
        f"= {n0_cap:.4f}  (n0 cannot exceed this)")
    log(f"    Var(T1)={var_tot:.1f}  E[Var(T1|Cell,Year)]={var_within:.1f}  "
        f"mean(T1)={y.mean():.2f} gC/m2/yr per patch")

    rows = []
    lagged = df.filter(pl.col("npp_lag1").is_not_null())
    yl = lagged["npp_sum"].to_numpy()
    pl_ = lagged["npp_lag1"].to_numpy()
    nP_r2 = r2(yl, pl_)
    nP_within = within_r2(lagged, yl, pl_)
    nP_resp = response_score(lagged, yl, pl_)
    log(f"[RESULT 2 -- persistence null nP, ZERO parameters] R2={nP_r2:.4f}  "
        f"within-cell-year R2={nP_within:.4f}  on {lagged.height} rows with a lag")
    log(f"    nP response: {nP_resp}")
    rows.append(dict(arm="nP_persistence", target=tgt, fold="none", nfeat=0,
                     R2=nP_r2, R2_within=nP_within, **nP_resp))

    # uniform-response null nU and do-nothing nZ, closed form
    d0 = df.select(["leg", "Cell", "Year", tgt]).with_columns(pl.Series("p", y))
    zz = response_score(d0, y, np.zeros_like(y))
    dt_only = response_score(d0, y, y)
    log(f"[RESULT 3 -- response nulls] nZ do-nothing R2_0 must be 0.0000, is "
        f"{zz['resp_R2_0']:.4f}; identity arm must be 1.0000, is {dt_only['resp_R2_0']:.4f}")

    arms: dict[str, list[str]] = {
        "n0_climate_only": CLIM_COLS,
        "n1_laistand_only": ["lai_stand"],
        "n1b_laistand_clim": ["lai_stand"] + CLIM_COLS,
        "k3": TIER["k3"],
        "k6": TIER["k6"],
        "k10": TIER["k10"],
        "k14": TIER["k14"],
        "k21": TIER["k21"],
        "k3_clim": TIER["k3"] + CLIM_COLS,
        "k6_clim": TIER["k6"] + CLIM_COLS,
        "k10_clim": TIER["k10"] + CLIM_COLS,
        "k14_clim": TIER["k14"] + CLIM_COLS,
        "n2_k21_clim": TIER["k21"] + CLIM_COLS,
        "n3_k21_clim_shape": TIER["k21"] + CLIM_COLS + SHAPE,
    }
    # single-mechanism additions, for the nonlinearity falsifier
    arms["n2+sla_disp"] = TIER["k21"] + CLIM_COLS + ["SLA_sd", "sla_jensen"]
    arms["n2+trait_disp"] = TIER["k21"] + CLIM_COLS + [
        "SLA_sd", "sla_jensen", "Wooddens_sd", "D95max_sd", "minwscal_sd", "Longevity_sd"]
    arms["n2+height_shape"] = TIER["k21"] + CLIM_COLS + [
        "h_p10", "h_p25", "h_p50", "h_p75", "h_p90", "h_min"]
    arms["n2+sizeclass"] = TIER["k21"] + CLIM_COLS + [
        "nbin_5_10", "nbin_10_20", "nbin_20_30", "nbin_30p"]
    arms["n2+dominance"] = TIER["k21"] + CLIM_COLS + [
        "agb_max_frac", "agb_cv", "agb_p50", "agb_p90"]
    arms["n2+lag1"] = TIER["k21"] + CLIM_COLS + ["npp_lag1"]

    preds: dict[str, np.ndarray] = {}
    for fold in ("fold_blocked", "fold_hashed"):
        for name, feats in arms.items():
            if fold == "fold_hashed" and name not in (
                    "n0_climate_only", "n1b_laistand_clim", "n2_k21_clim", "n3_k21_clim_shape"):
                continue
            sub = df
            if "npp_lag1" in feats:
                sub = df.filter(pl.col("npp_lag1").is_not_null())
            t = time.time()
            p = fit_arm(sub, feats, tgt, fold, ncpu)
            rec = dict(arm=name, target=tgt, fold=fold, nfeat=len(feats),
                       R2=r2(sub[tgt].to_numpy(), p),
                       R2_within=within_r2(sub, sub[tgt].to_numpy(), p),
                       **response_score(sub, sub[tgt].to_numpy(), p))
            rows.append(rec)
            if fold == "fold_blocked":
                preds[name] = p if sub.height == df.height else np.full(df.height, np.nan)
            log(f"[{fold}] {name:24s} nfeat={len(feats):3d} R2={rec['R2']:.4f} "
                f"within={rec['R2_within']:.4f} respR2_0={rec['resp_R2_0']:.4f} "
                f"slope={rec['resp_slope']:.3f} ({time.time()-t:.0f}s)")

    # ---- transpiration
    for name in ("n0_climate_only", "n1b_laistand_clim", "n2_k21_clim", "n3_k21_clim_shape"):
        feats = arms[name]
        t = time.time()
        p = fit_arm(df, feats, "transp_sum", "fold_blocked", ncpu)
        rec = dict(arm=name, target="transp_sum", fold="fold_blocked", nfeat=len(feats),
                   R2=r2(df["transp_sum"].to_numpy(), p),
                   R2_within=within_r2(df, df["transp_sum"].to_numpy(), p),
                   **response_score(df, df["transp_sum"].to_numpy(), p))
        rows.append(rec)
        log(f"[transp] {name:24s} R2={rec['R2']:.4f} within={rec['R2_within']:.4f} "
            f"respR2_0={rec['resp_R2_0']:.4f} slope={rec['resp_slope']:.3f} ({time.time()-t:.0f}s)")
    lagT = df.filter(pl.col("transp_lag1").is_not_null())
    rows.append(dict(arm="nP_persistence", target="transp_sum", fold="none", nfeat=0,
                     R2=r2(lagT["transp_sum"].to_numpy(), lagT["transp_lag1"].to_numpy()),
                     R2_within=within_r2(lagT, lagT["transp_sum"].to_numpy(),
                                         lagT["transp_lag1"].to_numpy()),
                     **response_score(lagT, lagT["transp_sum"].to_numpy(),
                                      lagT["transp_lag1"].to_numpy())))
    log(f"[transp] nP_persistence R2={rows[-1]['R2']:.4f}")

    res = pl.DataFrame(rows)
    res.write_csv(f"{OUT}/suff_arms.csv")
    log(f"\n[model] wrote {OUT}/suff_arms.csv")

    # ---- residual diagnostics: does n2's OOS residual correlate with what it discards?
    if "n2_k21_clim" in preds and not np.isnan(preds["n2_k21_clim"]).all():
        resid = df[tgt].to_numpy() - preds["n2_k21_clim"]
        drows = []
        for c in SHAPE:
            v = df[c].to_numpy().astype(float)
            ok = np.isfinite(v) & np.isfinite(resid)
            if ok.sum() < 1000 or np.nanstd(v[ok]) == 0:
                continue
            drows.append(dict(stat=c, n=int(ok.sum()),
                              pearson_r=float(np.corrcoef(v[ok], resid[ok])[0, 1])))
        dd = pl.DataFrame(drows).sort(pl.col("pearson_r").abs(), descending=True)
        dd.write_csv(f"{OUT}/suff_resid_corr.csv")
        log("[model] n2 OOS-residual correlation with discarded roster shape (top 10):")
        log(dd.head(10))

    # ---- per-cell 20-yr-mean relative error: the closest thing to the owner's basis
    crows = []
    for name in ("n1b_laistand_clim", "n2_k21_clim", "n3_k21_clim_shape"):
        if name not in preds or np.isnan(preds[name]).all():
            continue
        d = df.select(["leg", "Cell", "Year", tgt]).with_columns(pl.Series("p", preds[name]))
        for lab, lg, y0, y1 in (("historic", "historic", 2000, 2019),
                                ("ssp370_2080_2099", "ssp370", 2080, 2099)):
            w = d.filter((pl.col("leg") == lg) & (pl.col("Year").is_between(y0, y1)))
            m = w.group_by("Cell").agg(pl.col(tgt).mean().alias("t"), pl.col("p").mean().alias("q"))
            m = m.filter(pl.col("t").abs() > 1e-9)
            rel = ((m["q"] - m["t"]) / m["t"]).abs().to_numpy()
            crows.append(dict(arm=name, window=lab, n_cells=len(rel),
                              frac_within_10pct=float((rel <= 0.10).mean()),
                              median_abs_rel=float(np.median(rel)),
                              p90_abs_rel=float(np.quantile(rel, 0.9))))
    cc = pl.DataFrame(crows)
    cc.write_csv(f"{OUT}/suff_percell.csv")
    log("[model] per-cell 20-yr-mean accuracy (NOT the acceptance basis -- 549/598 of "
        "54 020 cells, patch basis):")
    log(cc)


# ---------------------------------------------------------------- stage nonlin
def stage_nonlin() -> None:
    """Direct tests of the three per-stem nonlinearities named in ADR 0310 section 11."""
    keep = ["leg", "seed", "Cell", "Patch", "Year", "Type", "Height", "Age",
            "SLA", "Wooddens", "LAI", "fpc_ind", "npp", "transp", "agb", "wscal_mean"]
    lf = suspect_filter(pl.scan_parquet(A_TAB).select(keep).filter(pl.col("seed") == 1))
    df = lf.collect()
    log(f"[nonlin] stem-years={df.height}")

    # --- T2: the net-assimilation / growth-respiration kink (npp_tree.c:52)
    #        npp = (assim<mresp) ? assim-mresp : (assim-mresp)*(1-r_growth)
    #        sign(npp) is exactly the branch indicator.
    tot = df["npp"].sum()
    neg = df.filter(pl.col("npp") < 0)
    log(f"\n[T2 rectifier] emitted stem-years with npp<0 (the no-growth-respiration branch): "
        f"{neg.height}/{df.height} = {neg.height/df.height:.5f}")
    log(f"    their npp mass = {neg['npp'].sum():.4g} of a total {tot:.4g}  "
        f"(= {neg['npp'].sum()/tot:.6f})")
    by = df.group_by("Type").agg(
        pl.len().alias("n"), (pl.col("npp") < 0).mean().alias("f_neg"),
        pl.col("npp").mean().alias("npp_mean")).sort("Type")
    log(by)
    pyr = df.group_by(["leg", "Cell", "Patch", "Year"]).agg(
        (pl.col("npp") < 0).mean().alias("f_neg"), pl.len().alias("n"))
    log(f"    patch-years with >=1 negative-npp stem: "
        f"{pyr.filter(pl.col('f_neg') > 0).height}/{pyr.height} = "
        f"{pyr.filter(pl.col('f_neg') > 0).height/pyr.height:.4f}")
    log(f"    patch-years with >=25% of stems negative: "
        f"{pyr.filter(pl.col('f_neg') >= 0.25).height/pyr.height:.5f}")

    # --- T1: the SLA cap on Vcmax (photosynthesis.c:90-95).  If the cap binds, a stem's
    #     assimilation per unit absorbed light is capped by a decreasing function of SLA,
    #     so patch total depends on the SLA DISTRIBUTION, not its mean.  Measure whether
    #     per-stem npp per unit leaf area is a NONLINEAR function of SLA at fixed size.
    d = df.filter((pl.col("LAI") > 0) & (pl.col("fpc_ind") > 0) & (pl.col("npp") > 0))
    d = d.with_columns(
        (pl.col("npp") / pl.col("fpc_ind")).alias("npp_per_cover"),
        (pl.col("SLA")).alias("sla"),
    )
    # within (Cell, Year, Type) so climate, PFT parameters and stand are all held fixed;
    # bin by height decile so size is controlled too
    d = d.with_columns(
        (pl.col("Height").rank("ordinal").over(["Cell", "Year", "Type"])
         / pl.len().over(["Cell", "Year", "Type"]) * 10).ceil().alias("hdec"),
        (pl.col("sla").rank("ordinal").over(["Cell", "Year", "Type"])
         / pl.len().over(["Cell", "Year", "Type"]) * 5).ceil().alias("slaq"),
    )
    prof = d.group_by(["slaq"]).agg(
        pl.len().alias("n"), pl.col("sla").mean().alias("sla_mean"),
        pl.col("npp_per_cover").mean().alias("npp_per_cover_mean"),
        pl.col("Height").mean().alias("h_mean")).sort("slaq")
    log("\n[T1 SLA cap] per-stem NPP per unit crown cover by within-(cell,year,PFT) SLA quintile:")
    log(prof)
    prof.write_csv(f"{OUT}/suff_nonlin_sla_profile.csv")

    # --- T3: the cross-stem running water accumulator under -DPERMUTE
    #     (water_stressed.c:155-176, daily_natural.c:92 permute).  Two stems in the SAME
    #     patch-year with the same PFT, age, height, SLA, wood density, crown LAI and crown
    #     cover are physically IDENTICAL -- they see the same layered light and the same
    #     weather.  Any npp difference between them can only come from their position in the
    #     random soil-water depletion order.  This is the ONE test that isolates T3.
    # water-limitation incidence: the clip can only bind on days when supply < demand,
    # for which the emitted potential leaf-on index wscal_mean < 1 is a necessary proxy.
    log(f"\n[T3 incidence] stem-years with wscal_mean < 0.999: "
        f"{df.filter(pl.col('wscal_mean') < 0.999).height / df.height:.4f}; "
        f"< 0.90: {df.filter(pl.col('wscal_mean') < 0.90).height / df.height:.4f}; "
        f"< 0.50: {df.filter(pl.col('wscal_mean') < 0.50).height / df.height:.4f}")

    # relaxed matched twins + a CROSS-PATCH control with identical bucketing.
    # A within-patch bucket's npp spread is an UPPER BOUND on (residual trait/size
    # mismatch + layered-light position + depletion order); the cross-patch bucket adds
    # patch composition on top, so within < cross is the expected ordering.
    b = df.with_columns(
        pl.col("Height").round(0).alias("bh"),
        (pl.col("SLA") * 1e3).round(0).alias("bs"),
        (pl.col("Wooddens") / 1e4).round(0).alias("bw"),
        pl.col("LAI").round(1).alias("bl"),
    )
    attrs = ["bh", "bs", "bw", "bl"]
    aggs = [
        pl.len().alias("k"),
        pl.col("npp").mean().alias("npp_m"), pl.col("npp").min().alias("npp_lo"),
        pl.col("npp").max().alias("npp_hi"),
        pl.col("transp").mean().alias("tr_m"), pl.col("transp").min().alias("tr_lo"),
        pl.col("transp").max().alias("tr_hi"),
        pl.col("Height").max().alias("hhi"), pl.col("Height").min().alias("hlo"),
        pl.col("SLA").max().alias("shi"), pl.col("SLA").min().alias("slo"),
    ]
    for label, gk in (
        ("within-patch", ["leg", "Cell", "Patch", "Year", "Type", "Age", *attrs]),
        ("cross-patch ", ["leg", "Cell", "Year", "Type", "Age", *attrs]),
    ):
        tw = b.group_by(gk).agg(aggs).filter((pl.col("k") >= 2) & (pl.col("npp_m") > 1e-9))
        log(f"\n[T3 twins {label}] buckets>=2: {tw.height}  stems in them: {tw['k'].sum()}")
        if tw.height == 0:
            continue
        tw = tw.with_columns(
            ((pl.col("npp_hi") - pl.col("npp_lo")) / pl.col("npp_m")).alias("rel_spread_npp"),
            ((pl.col("tr_hi") - pl.col("tr_lo"))
             / pl.col("tr_m").abs().clip(1e-12)).alias("rel_spread_tr"),
            ((pl.col("hhi") - pl.col("hlo")) / pl.col("hhi")).alias("match_h"),
            ((pl.col("shi") - pl.col("slo")) / pl.col("shi")).alias("match_sla"),
        )
        log(tw.select(
            pl.col("rel_spread_npp").median().alias("npp_relspread_med"),
            pl.col("rel_spread_npp").quantile(0.9).alias("npp_relspread_p90"),
            pl.col("rel_spread_tr").median().alias("transp_relspread_med"),
            pl.col("rel_spread_tr").quantile(0.9).alias("transp_relspread_p90"),
            pl.col("match_h").median().alias("h_mismatch_med"),
            pl.col("match_h").quantile(0.95).alias("h_mismatch_p95"),
            pl.col("match_sla").median().alias("sla_mismatch_med"),
        ))
        if label.startswith("within"):
            tw.select(["leg", "Cell", "Patch", "Year", "Type", "k", "rel_spread_npp",
                       "rel_spread_tr", "match_h", "match_sla"]).write_parquet(
                f"{OUT}/suff_nonlin_twins.parquet")


# ----------------------------------------------------------------- stage daily
DAILY_DIR = "/p/tmp/jamirp/esm_land_daily/daily_2000_2019_global_c0_67419_seed1/output"
FORCE_DIR = "/p/projects/waldspektrum/priesner/clustering/global"
CLM_VARS = {
    "tas": "temperature_test.clm",
    "pr": "precipitation_test.clm",
    "rsds": "short_wave_radiation_test.clm",
    "huss": "humid_test.clm",
    "lwnet": "long_wave_radiation_test.clm",
}
DAILY_FEAT = f"{OUT}/suff_daily_features.parquet"


def _open_clm(path: str):
    """Header-driven .clm open (v3 float32 HDR=51 / v2 int16 HDR=43). Same algebra as
    scripts/build_transient_boundary.py::open_clm, reimplemented here so this probe stays
    self-contained and read-only. Returns (memmap, firstyear, ncell, nbands, scalar)."""
    import struct
    dt_map = {0: "<i1", 1: "<i2", 2: "<i4", 3: "<f4", 4: "<f8"}
    with open(path, "rb") as f:
        raw = f.read(64)
    if raw[:7] != b"LPJCLIM":
        raise SystemExit(f"FATAL {path}: not LPJCLIM")
    version, order, firstyear, nyear, _fc, ncell, nbands = struct.unpack("<7i", raw[7:35])
    if order != 1:
        raise SystemExit(f"FATAL {path}: order={order}")
    scalar = struct.unpack("<f", raw[39:43])[0]
    if version >= 3:
        hdr, dt = 51, dt_map[struct.unpack("<i", raw[47:51])[0]]
    else:
        hdr, dt = 43, "<i2"
    per = ncell * nbands * np.dtype(dt).itemsize
    sz = os.path.getsize(path)
    if (sz - hdr) != nyear * per:
        raise SystemExit(f"FATAL {path}: size mismatch ({(sz - hdr) / per:.4f} yr)")
    mm = np.memmap(path, dtype=dt, mode="r", offset=hdr, shape=(nyear, ncell, nbands))
    log(f"    clm {os.path.basename(path)} v{version} {dt} scalar={scalar} "
        f"firstyear={firstyear} nyear={nyear} ncell={ncell} nbands={nbands} hdr={hdr}")
    return mm, firstyear, ncell, nbands, float(scalar)


def stage_daily_build(ncells_want: int) -> None:
    import netCDF4 as nc

    # (1) grass screen -- the daily fluxes are ALL-PFT and there is no per-PFT daily output,
    #     so the only defensible basis is cells where grass carries almost no carbon.
    log("[daily] grass screen on the raw historic roster (Cell % 100 == 0) ...")
    raw = (pl.scan_parquet(f"{GLOB}/ind_hist_seed1_all.parquet")
           .select(["Cell", "Type", "npp"])
           .filter(pl.col("Cell") % 100 == 0)
           .group_by("Cell")
           .agg(pl.col("npp").filter(pl.col("Type") <= 6).sum().alias("npp_tree"),
                pl.col("npp").filter(pl.col("Type") >= 7).sum().alias("npp_grass"))
           .collect())
    raw = raw.with_columns(
        (pl.col("npp_grass") / (pl.col("npp_grass") + pl.col("npp_tree"))).alias("grass_share")
    ).filter(pl.col("npp_tree") > 0)
    log(f"    {raw.height} tree-bearing sampled cells; grass share quantiles "
        f"{raw['grass_share'].quantile(0.1):.4f} / {raw['grass_share'].quantile(0.5):.4f} / "
        f"{raw['grass_share'].quantile(0.9):.4f}")
    low = raw.filter(pl.col("grass_share") < 0.05).sort("Cell")
    log(f"    cells with grass < 5 % of stand NPP: {low.height}")
    step = max(1, low.height // ncells_want)
    sel = low.gather_every(step).head(ncells_want)
    cells = sel["Cell"].to_list()
    log(f"    selected {len(cells)} cells; their grass share: max="
        f"{sel['grass_share'].max():.4f} median={sel['grass_share'].median():.4f}")
    sel.write_csv(f"{OUT}/suff_daily_cells.csv")

    # (2) cell -> (ilat, ilon) from the run's own grid.nc
    g = nc.Dataset(f"{DAILY_DIR}/grid.nc")
    cid = g.variables["cellid"][:]
    g.close()
    idx = {}
    m = np.ma.getmaskarray(cid)
    flat = np.asarray(cid)
    for c in cells:
        hit = np.argwhere((flat == c) & (~m))
        if hit.shape[0] != 1:
            raise SystemExit(f"FATAL cell {c}: {hit.shape[0]} grid.nc matches")
        idx[c] = (int(hit[0, 0]), int(hit[0, 1]))
    ilat = np.array([idx[c][0] for c in cells])
    ilon = np.array([idx[c][1] for c in cells])

    # (3) daily fluxes + the model's own root-zone water, chunked over time
    daily = {}
    for var, fname in (("gpp", "d_gpp.nc"), ("transp", "d_transp.nc"),
                       ("rootmoist", "d_rootmoist.nc")):
        d = nc.Dataset(f"{DAILY_DIR}/{fname}")
        vn = [v for v in d.variables if v not in
              ("time", "time_bnds", "lat", "lat_bnds", "lon", "lon_bnds")][0]
        v = d.variables[vn]
        nt = v.shape[0]
        buf = np.empty((nt, len(cells)), dtype=np.float32)
        t0 = time.time()
        for a in range(0, nt, 365):
            b = min(a + 365, nt)
            blk = np.asarray(v[a:b, :, :])
            buf[a:b, :] = blk[:, ilat, ilon]
        log(f"    read {fname} var={vn} units={getattr(v, 'units', '?')} "
            f"nt={nt} ({time.time() - t0:.0f}s)  -- NOTE the `units` attribute is known to "
            f"say /month while the values are per DAY")
        daily[var] = buf
        d.close()
    nt = daily["gpp"].shape[0]
    assert nt == 20 * 365, f"expected 7300 daily steps, got {nt}"

    # (4) daily forcing
    force = {}
    for k, fn in CLM_VARS.items():
        mm, fy, ncell, nbands, sc = _open_clm(f"{FORCE_DIR}/{fn}")
        assert nbands == 365, f"{fn} nbands={nbands}"
        y0 = 2000 - fy
        arr = np.empty((nt, len(cells)), dtype=np.float32)
        for j, c in enumerate(cells):
            if c >= ncell:
                raise SystemExit(f"FATAL {fn}: cell {c} >= ncell {ncell}")
            arr[:, j] = (np.asarray(mm[y0:y0 + 20, c, :], dtype=np.float32) * sc).reshape(-1)
        force[k] = arr

    # (5) assemble the cell-day frame
    yr = np.repeat(np.arange(2000, 2020), 365)
    doy = np.tile(np.arange(1, 366), 20)
    rows = {
        "Cell": np.tile(np.asarray(cells), nt),
        "Year": np.repeat(yr, len(cells)),
        "doy": np.repeat(doy, len(cells)),
    }
    for k, v in daily.items():
        rows[f"d_{k}"] = v.reshape(-1)
    for k, v in force.items():
        rows[k] = v.reshape(-1)
    df = pl.DataFrame(rows)
    df = df.with_columns(
        (2 * np.pi * pl.col("doy") / 365).sin().alias("doy_sin"),
        (2 * np.pi * pl.col("doy") / 365).cos().alias("doy_cos"),
    ).sort(["Cell", "Year", "doy"])
    for c in ("tas", "pr", "rsds", "huss"):
        for w in (7, 30, 90):
            df = df.with_columns(
                pl.col(c).rolling_mean(w, min_samples=1).over("Cell").alias(f"{c}_r{w}"))
    df = df.with_columns(
        pl.col("d_gpp").shift(1).over("Cell").alias("gpp_lag1d"),
        pl.col("d_transp").shift(1).over("Cell").alias("transp_lag1d"),
    )

    # (6) the cell-year stand state: patch-ENSEMBLE MEAN summary, plus the roster shape and
    #     the BETWEEN-PATCH dispersion the ensemble mean discards
    pf = pl.read_parquet(FEAT).filter(
        (pl.col("seed") == 1) & (pl.col("leg") == "historic") & pl.col("Cell").is_in(cells))
    summ_cols = TIER["k21"]
    aggs = [pl.col(c).mean().alias(f"c_{c}") for c in summ_cols]
    aggs += [pl.col(c).mean().alias(f"c_{c}") for c in SHAPE]
    aggs += [pl.col(c).std().alias(f"bp_{c}") for c in
             ("n_stems", "lai_stand", "agb_sum", "h_max", "h_mean", "fpc_sum")]
    aggs += [pl.len().alias("n_patches_obs")]
    cy = pf.group_by(["Cell", "Year"]).agg(aggs)
    assert cy.select(["Cell", "Year"]).n_unique() == cy.height
    df = df.join(cy, on=["Cell", "Year"], how="inner")

    geo = (pl.read_parquet(f"{OUT}/prep_cell_window_clim.parquet")
           .select(["Cell", "lat", "lon"]).unique(subset=["Cell"]))
    df = df.join(geo, on="Cell", how="left")
    tiles = df.with_columns(
        (((pl.col("lon") + 180) / 15).floor().cast(pl.Int64) * 1000
         + ((pl.col("lat") + 90) / 5).floor().cast(pl.Int64)).alias("tile"))
    tl = sorted(tiles.select("tile").unique().to_series().to_list())
    rng = np.random.default_rng(20260902)
    tf = {t: int(f) for t, f in zip(tl, rng.integers(0, 5, len(tl)), strict=True)}
    df = tiles.with_columns(
        pl.col("tile").replace_strict(tf, return_dtype=pl.Int64).alias("fold_blocked"))
    df.write_parquet(DAILY_FEAT)
    log(f"[daily] wrote {DAILY_FEAT} rows={df.height} cols={len(df.columns)} "
        f"cells={df['Cell'].n_unique()} tiles={len(tl)}")


def stage_daily_model(ncpu: int) -> None:
    df = pl.read_parquet(DAILY_FEAT).drop_nulls(subset=["d_gpp", "d_transp", "c_lai_stand"])
    log(f"[dmodel] rows={df.height} cells={df['Cell'].n_unique()}")
    env = (["tas", "pr", "rsds", "huss", "lwnet", "doy_sin", "doy_cos", "lat", "d_rootmoist"]
           + [f"{c}_r{w}" for c in ("tas", "pr", "rsds", "huss") for w in (7, 30, 90)])
    k21c = [f"c_{c}" for c in TIER["k21"]]
    shp = ([f"c_{c}" for c in SHAPE]
           + [f"bp_{c}" for c in
              ("n_stems", "lai_stand", "agb_sum", "h_max", "h_mean", "fpc_sum")]
           + ["n_patches_obs"])
    arms = {
        "nW_env_only": env,
        "nL_env_lai": env + ["c_lai_stand"],
        "nS_env_k21": env + k21c,
        "nR_env_k21_shape": env + k21c + shp,
    }
    rows = []
    for tgt in ("d_gpp", "d_transp"):
        lagc = "gpp_lag1d" if tgt == "d_gpp" else "transp_lag1d"
        sub = df.drop_nulls(subset=[lagc])
        y = sub[tgt].to_numpy()
        p = sub[lagc].to_numpy()
        rows.append(dict(arm="nPd_persistence_prevday", target=tgt, nfeat=0, R2=r2(y, p)))
        log(f"[dmodel] {tgt} nPd_persistence_prevday R2={rows[-1]['R2']:.4f} (0 parameters)")
        # per-cell leave-one-year-out day-of-year climatology (DIFFERENT basis: in-cell)
        cl = sub.select(["Cell", "Year", "doy", tgt]).with_columns(
            pl.col(tgt).sum().over(["Cell", "doy"]).alias("s"),
            pl.col(tgt).count().over(["Cell", "doy"]).alias("n"))
        cl = cl.with_columns(((pl.col("s") - pl.col(tgt)) / (pl.col("n") - 1)).alias("q"))
        rows.append(dict(arm="nDOY_incell_climatology", target=tgt, nfeat=0,
                         R2=r2(cl[tgt].to_numpy(), cl["q"].to_numpy())))
        log(f"[dmodel] {tgt} nDOY_incell_climatology R2={rows[-1]['R2']:.4f} "
            f"(0 parameters, IN-CELL basis -- not comparable to the cell-held-out arms)")
        for name, feats in arms.items():
            t = time.time()
            pr = fit_arm(df, feats, tgt, "fold_blocked", ncpu)
            yy = df[tgt].to_numpy()
            rows.append(dict(arm=name, target=tgt, nfeat=len(feats), R2=r2(yy, pr)))
            log(f"[dmodel] {tgt} {name:20s} nfeat={len(feats):3d} R2={rows[-1]['R2']:.4f} "
                f"({time.time() - t:.0f}s)")
    pl.DataFrame(rows).write_csv(f"{OUT}/suff_daily_arms.csv")
    log(f"[dmodel] wrote {OUT}/suff_daily_arms.csv")


def main() -> None:
    log(PREREG)
    log(f"repo root (derived from script): {REPO}")
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    ncpu = int(os.environ.get("SLURM_CPUS_PER_TASK", "8"))
    log(f"stage={stage} ncpu={ncpu} polars={pl.__version__}")
    if stage == "build":
        seeds = [int(s) for s in (sys.argv[2] if len(sys.argv) > 2 else "1,2").split(",")]
        stage_build(seeds)
    elif stage == "model":
        stage_model(ncpu)
    elif stage == "nonlin":
        stage_nonlin()
    elif stage == "daily_build":
        stage_daily_build(int(sys.argv[2]) if len(sys.argv) > 2 else 48)
    elif stage == "daily_model":
        stage_daily_model(ncpu)
    else:
        raise SystemExit(f"unknown stage {stage}")
    log("stage complete")


if __name__ == "__main__":
    main()
