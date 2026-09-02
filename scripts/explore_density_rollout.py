#!/usr/bin/env python3
"""explore_density_rollout.py -- line X, campaign item B6.

DOES THE MISSING DENSITY-DEPENDENT RECRUITMENT FEEDBACK BOUND ADR 0113's -0.226 FROM BELOW OR ABOVE?

Read-only probe (line X charter). Writes ONLY to /p/tmp/jamirp/X_explore/dens_*.

Stages (positional argv[1]):
  gate   -- 674-cell (Cell%100==0) gate on Tables A/B: the recruitment-flow identity, the newcomer
            height/age split, the density regression + its elasticity, the Jensen convexity
            ratio WITH and WITHOUT the all-25-patches-occupied restriction, and the
            reconstructed-vs-C LAI bias.
  scan   -- global per-(Cell, Patch, Year) stand table from the 4 rosters (all cells, both legs,
            both seeds). argv[2] = leg ("historic"|"ssp370"), argv[3] = seed.
  roll   -- fit the heads, run every arm and null, score on ADR 0111/0113's statistic.

Everything numeric printed by this script is [MEASURED] unless the line says otherwise.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "python", "src"))

OUT = "/p/tmp/jamirp/X_explore"
GLOB = "/p/tmp/jamirp/emulator_global"
TBL = f"{GLOB}/tables"
ROSTER = {
    ("historic", 1): f"{GLOB}/ind_hist_seed1_all.parquet",
    ("historic", 2): f"{GLOB}/ind_hist_seed2_all.parquet",
    ("ssp370", 1): f"{GLOB}/ind_ssp370_seed1_all.parquet",
    ("ssp370", 2): f"{GLOB}/ind_ssp370_seed2_all.parquet",
}
LEG_YEARS = {"historic": (2000, 2019), "ssp370": (2020, 2100)}
ENV_TBL = {"historic": f"{TBL}/cell_year_env_historic_w20.parquet",
           "ssp370": f"{TBL}/cell_year_env_ssp370_w20.parquet"}
LAI_REF = {"historic": f"{TBL}/cell_year_lai_hist.parquet",
           "ssp370": f"{TBL}/cell_year_lai_ssp.parquet"}
ENV_COLS = ["eco_diag_gdd_5", "tas_cold_month", "eco_diag_vpd_mean", "eco_diag_pet_mean",
            "eco_diag_p_pet_ratio", "pr_cv_monthly", "prec_mean", "humid_mean"]
F32_ENV = ["eco_diag_p_pet_ratio", "eco_diag_pet_mean", "eco_diag_vpd_mean", "pr_cv_monthly"]
LAT_BANDS = [("tropical", 0.0, 23.5), ("subtropical", 23.5, 35.0), ("temperate", 35.0, 50.0),
             ("boreal", 50.0, 90.1)]
# ADR 0113's published arms, on the pooled count table, 51 767 cells, area-weighted. [SOURCE]
ADR0113 = {"A0_onestep": 0.707, "A0_persistence_null": 0.685, "A1_state_recursed": -0.226}


def say(*a: object) -> None:
    print(*a, flush=True)


# --------------------------------------------------------------------------- PRE-REGISTRATION
PREREG = r"""
================================================================================================
PRE-REGISTRATION -- printed BEFORE any result is computed. Item B6, line X.
================================================================================================
QUESTION
  ADR 0113 measured that recursing ONE variable (the stem count) of a one-step count operator flips
  the area-weighted aggregate warming-response ratio from +0.707 to -0.226 (target 1.0). ADR 0310
  section 10 item 1 records an UNRESOLVED disagreement about what -0.226 bounds. Operationally, two
  hypotheses:
    H_CLOSURE_HELPS  ("-0.226 is a FLOOR"): the arm drifted to a too-HIGH count because nothing
        suppressed recruitment on a too-dense stand; a rollout that closes that exp(-LAI)-shaped
        density feedback would push counts down on the loss side and score materially better.
    H_CLOSURE_DOES_NOT ("-0.226 is a CEILING"): -0.226 is already optimistic (the arm was handed
        LPJmL-FIT's own stand state every year); closing the density loop does not recover the
        response, and a truly free-running rollout can only be worse.
  Settled by CONSTRUCTION: build the simplest closed per-patch annual count rollout on FIT's own
  output, n_{y+1} = n_y - D(.) + R(.), and run it WITH and WITHOUT the density-dependent recruitment
  term, everything else identical.

PRIMARY STATISTIC  (identical construction to scripts/diagnose_truth_yardstick.py::band_ratios,
                    which is the definition ADR 0111 froze and ADR 0113 reported -0.226 on)
  per cell c:  DX_c = mean(stems per patch | ssp370 2020-2100) - mean(stems per patch | historic
               2000-2019), the mean taken over ALL patch-years of the leg (absent patch-years are
               STRUCTURAL ZEROS, not dropped -- mandate 4).
  ratio       = sum_c w_c DP_c / sum_c w_c DT_c ,  w_c = cos(lat_c),
               DT = mean of the two seeds' responses, DP = the arm's.
  Reported GLOBAL and in the four latitude bands (0-23.5 / 23.5-35 / 35-50 / 50-90.1), each with the
  truth denominator's own two-seed S/N and the S/N < 3 => "n/d" determinacy guard.
SECONDARY STATISTICS
  (a) LEVEL DRIFT: area-weighted mean(pred - truth) in stems/patch, over ssp370 2080-2099 and by
      lead time. This is the statistic that tests the reviewer's MECHANISM claim directly.
  (b) DISTRIBUTION: the across-patch spread of the count (FIT's 25-patch ensemble) predicted vs
      true, and the per-cell fraction inside max(10 %, the two-seed spread) -- ADR 0106's tolerance.

NULLS -- what each MUST RETURN, written down before the run
  N1 FROZEN-2019   each patch's count frozen at its own year-2019 value on BOTH legs.
                   MUST RETURN response ratio EXACTLY 0.0000 (its predicted response is identically
                   zero by construction). A tolerance of 1e-12 is a code check, not a finding.
  N2 FROZEN-LEGSTART each patch frozen at its own leg-first-year observed value (2000 / 2020).
                   MUST RETURN a NON-ZERO ratio = the response obtained FREE from the differing
                   initial conditions. Its value is not predictable a priori and is REPORTED. Any
                   arm that does not beat it on |ratio - 1| has no rollout skill beyond its
                   initialisation.
  N3 CLIMATOLOGY   each patch-year drawn i.i.d. from that patch's OWN historic 2000-2019 empirical
                   count distribution, on both legs. MUST RETURN 0.0000 +- Monte-Carlo noise; it
                   cannot see the scenario. Reported with its spread over 5 draws.
  N4 ONESTEP       the same two heads, teacher-forced with FIT's own n every year (= ADR 0113's A0
                   configuration). MUST RETURN a ratio in [+0.40, +1.00], i.e. compatible with the
                   published +0.707. This is trap 1: it prices MY pipeline at the configuration the
                   incumbent number was measured at. Outside that band, my rollout numbers are
                   basis-shifted from -0.226 and I must say so instead of comparing them.
  N5 ELASTICITY GATE (a gate, not a finding -- the published feedback is already measured, ADR 0240/
                   0093, and re-deriving it is NOT this item's contribution)
                   the fitted recruitment term must be DECREASING in patch LAI over the populated
                   range: d ln E[R] / d LAI < 0. If it returns >= 0, the "density feedback" I
                   install is not the published one and the whole with/without contrast is VOID.

FALSIFIER -- decided before the run
  * -0.226 is a FLOOR (H_CLOSURE_HELPS) iff BOTH:
      (a) the closed density-feedback arm's GLOBAL ratio exceeds -0.226 by more than the largest
          absolute null ratio among N1-N3, AND
      (b) the NO-density arm shows the predicted POSITIVE count-level drift (too many stems) while
          the density arm's drift is smaller in magnitude.
  * -0.226 is a CEILING (H_CLOSURE_DOES_NOT) iff ANY of:
      (i) the density arm's GLOBAL ratio is <= -0.226; or
      (ii) |ratio_dens - ratio_nodens| is smaller than the largest absolute null ratio; or
      (iii) the no-density arm's level drift is NEGATIVE -- which CONTRADICTS the mechanism the
          reviewer's reading rests on, independently of any ratio.
  * MIXED if the density arm's ratio moves materially but stays below N2's free ratio and far below
    the +0.707 one-step reference: the feedback matters mechanically without restoring the response.
  * The stochastic-head question is scored separately and has its own falsifier: a binomial-survival
    + Poisson-birth head "buys" something only if it improves the DISTRIBUTION statistic (b) without
    losing more than the null spread on the response ratio.

DECLARED BASES (trap 3)
  * every number is on the cell universe stated in the same line; the acceptance criterion
    (ADR 0106) is per cell over all 54 020 tree-bearing cells, NOT what an aggregate ratio measures.
  * within one scenario a cell's warming increment is ~76 % predictable from its baseline climate
    (campaign mandate 5), so a per-cell response measured on the ssp370 leg alone cannot separate a
    forcing response from a place sensitivity. The aggregate ratio inherits that limit.
  * all stand quantities are on the >5 m emitted population only (the ind writer's cut), so
    "recruitment" here means INGROWTH ACROSS 5 m, not FIT's establishment. The published
    establishment rates (6.456 %/yr etc., ADR 0240) are a DIFFERENT quantity and are not compared.
================================================================================================
"""


# --------------------------------------------------------------------------- shared loaders
def load_latlon() -> pl.DataFrame:
    rows = []
    with open(f"{TBL}/cell_latlon.txt") as fh:
        for ln in fh:
            if ln.startswith("#"):
                continue
            p = ln.split()
            if len(p) >= 5:
                rows.append((int(p[0]), float(p[3]), float(p[4])))
    d = pl.DataFrame(rows, schema=["Cell", "lat", "lon"], orient="row")
    return d.with_columns((pl.col("lat") * np.pi / 180.0).cos().alias("w"))


def load_folds() -> pl.DataFrame:
    rows = []
    with open(f"{TBL}/fold_hash5_pooled.txt") as fh:
        for ln in fh:
            p = ln.split()
            if len(p) == 2:
                rows.append((int(p[0]), int(p[1])))
    return pl.DataFrame(rows, schema=["Cell", "fold"], orient="row")


def load_env(leg: str) -> pl.DataFrame:
    d = pl.read_parquet(ENV_TBL[leg])
    # Float32 accumulation trap: cast BEFORE anything numeric happens downstream.
    return d.with_columns([pl.col(c).cast(pl.Float64) for c in F32_ENV])


def suspect_blocks() -> pl.DataFrame:
    return (pl.read_csv(f"{OUT}/prep_suspect_cell_blocks.csv")
            .select(["leg", "seed", "Cell"]).unique()
            .with_columns(pl.lit(True).alias("_bad")))


# --------------------------------------------------------------------------- STAGE gate
def stage_gate() -> None:
    from build_slow_runtime_table import K_LIGHTEXT

    say("\n### STAGE gate -- 674-cell (Cell%100==0) checks on the shared Tables A and B")
    say(f"   imported K_LIGHTEXT = {dict(K_LIGHTEXT)}  (per-PFT light extinction; 0.59 broadleaf / "
        "0.45 needleleaf)")
    b = pl.read_parquet(f"{OUT}/prep_patch_year_stand.parquet")
    b = b.filter(pl.col("seed") == 1)
    for c in ["n_stems", "n_stems_all", "n_dead", "n_survived_live", "n_pairable_live"]:
        b = b.with_columns(pl.col(c).cast(pl.Int64))
    b = b.join(suspect_blocks(), on=["leg", "seed", "Cell"], how="left").filter(
        pl.col("_bad").is_null()).drop("_bad")
    say(f"   Table B seed1 rows={b.height}  cells={b['Cell'].n_unique()}")

    g = ["leg", "Cell", "Patch"]
    b = b.sort(["leg", "Cell", "Patch", "Year"]).with_columns(
        [pl.col(x).shift(1).over(g).alias(x + "_p")
         for x in ["Year", "n_stems", "n_stems_all", "n_survived_live", "lai_stand", "fpc_sum",
                   "age_mean", "agb_sum", "h_max"]])
    b = b.filter((pl.col("Year") - pl.col("Year_p")) == 1)
    b = b.with_columns([
        (pl.col("n_stems_all") - pl.col("n_survived_live_p")).alias("newkeys"),
        (pl.col("n_stems") - pl.col("n_stems_p") + pl.col("n_dead")).alias("R_resid"),
    ])

    # --- G-A: the flow identity the global scan will rely on ------------------------------------
    e = (b["R_resid"] - b["newkeys"]).to_numpy()
    say("\n   G-A  FLOW IDENTITY.  Define, from per-(Cell,Patch,Year) COUNTS only:")
    say("        D(y+1) := n_dead(y+1)   R(y+1) := n(y+1) - n(y) + n_dead(y+1)")
    say("        so n(y+1) = n(y) - D + R holds EXACTLY by construction. Interpretation gate: does")
    say("        R equal the exact per-stem count of NEW keys (Table A pairing, corrected key)?")
    say(f"        rows={len(e)}  mean(R)={float(b['R_resid'].mean()):.6f}  "
        f"mean(newkeys)={float(b['newkeys'].mean()):.6f}")
    say(f"        R - newkeys: mean={e.mean():.6f}  frac nonzero={(e != 0).mean():.6f}  "
        f"p01={np.quantile(e, 0.01):.3f} p99={np.quantile(e, 0.99):.3f}")
    say(f"        frac(R < 0)={float((b['R_resid'] < 0).mean()):.6f}  "
        f"frac(n_dead > n_prev)={float((b['n_dead'] > b['n_stems_p']).mean()):.6f}")

    # --- G-B: what a 'newcomer' actually is (the 5 m emission cut) -------------------------------
    say("\n   G-B  WHAT A NEWCOMER IS. Table A first-appearance rows (excluding each leg's first"
        " year).")
    a = pl.scan_parquet(f"{OUT}/prep_paired_stems.parquet").filter(
        (pl.col("seed") == 1) & (pl.col("dup_key") == 0))
    first = (a.group_by(["leg", "Cell", "Patch", "Type", "ID"])
             .agg(pl.col("Year").min().alias("y0")).collect())
    newc = (a.collect().join(first, on=["leg", "Cell", "Patch", "Type", "ID"], how="inner")
            .filter(pl.col("Year") == pl.col("y0")))
    for leg, y0 in [("historic", 2000), ("ssp370", 2020)]:
        n = newc.filter((pl.col("leg") == leg) & (pl.col("Year") > y0))
        h = n["Height"].to_numpy()
        ag = n["Age"].to_numpy()
        say(f"        {leg}: n={len(h)}  Height p50={np.median(h):.3f} "
            f"p95={np.quantile(h, .95):.3f}"
            f" max={h.max():.3f}  frac(H<5.4)={(h < 5.4).mean():.4f}")
        say(f"           Age p05={np.quantile(ag, .05):.1f} p50={np.median(ag):.1f} "
            f"p95={np.quantile(ag, .95):.1f}  frac(Age<=5)={(ag <= 5).mean():.4f}")
    say("        => every newcomer is a stem CROSSING the writer's 5 m cut; establishment is")
    say("           invisible in this table. 'Recruitment' below always means ingrowth across 5 m.")

    # --- G-C: the density regression + N5 elasticity gate ---------------------------------------
    say("\n   G-C  DENSITY REGRESSION (the N5 gate). Poisson log-link, E[R] on the PREVIOUS year's")
    say("        patch state + that cell-year's climate. Fitted on the 674-cell sample, seed 1,")
    say("        both legs pooled.")
    env = pl.concat([load_env(lg).with_columns(pl.lit(lg).alias("leg")) for lg in LEG_YEARS])
    b = b.join(env, on=["leg", "Cell", "Year"], how="left")
    b = b.drop_nulls(["lai_stand_p", "age_mean_p"] + ENV_COLS)
    say(f"        rows after join/dropna = {b.height}")

    from sklearn.linear_model import PoissonRegressor
    feats_full = ["lai_stand_p", "logn_p", "age_mean_p", "agb_log_p"] + ENV_COLS
    bb = b.with_columns([
        (pl.col("n_stems_p").cast(pl.Float64) + 1.0).log().alias("logn_p"),
        (pl.col("agb_sum_p").cast(pl.Float64) + 1.0).log().alias("agb_log_p"),
    ])
    y = np.clip(bb["R_resid"].to_numpy().astype(float), 0, None)
    x = bb.select(feats_full).to_numpy().astype(float)
    mu = x.mean(0)
    sd = x.std(0)
    sd[sd == 0] = 1.0
    pr = PoissonRegressor(alpha=1e-6, max_iter=400).fit((x - mu) / sd, y)
    coef = pr.coef_ / sd
    say("        d ln E[R] / d feature (raw units):")
    for f, c in zip(feats_full, coef, strict=True):
        say(f"          {f:24s} {c:+.5f}")
    lai_b = float(coef[0])
    say(f"        N5 GATE: d ln E[R] / d LAI = {lai_b:+.5f} per LAI unit  -> "
        f"{'PASS (negative)' if lai_b < 0 else 'FAIL (not negative) => the contrast is VOID'}")
    say(f"        implied recruitment factor over the LAI range 0.7 -> 7.7: "
        f"exp({lai_b:.4f}*7.0) = {np.exp(lai_b * 7.0):.4f}")
    # raw decile table (no model)
    q = bb.with_columns(pl.col("lai_stand_p").qcut(10, labels=[str(i) for i in range(10)])
                        .alias("bin"))
    say("        raw LAI-decile table (no model), previous-year patch LAI:")
    say(q.group_by("bin").agg([pl.len().alias("n"),
                               pl.col("lai_stand_p").mean().alias("lai"),
                               pl.col("R_resid").mean().alias("R"),
                               pl.col("n_stems_p").mean().alias("n_prev"),
                               pl.col("n_dead").mean().alias("D")]).sort("bin"))
    # variance explained by the density term alone, vs climate alone
    from sklearn.metrics import r2_score
    for name, fs in [("density only (lai,logn,agb)", ["lai_stand_p", "logn_p", "agb_log_p"]),
                     ("climate only", ENV_COLS),
                     ("age only", ["age_mean_p"]),
                     ("all", feats_full)]:
        xi = bb.select(fs).to_numpy().astype(float)
        m2 = xi.mean(0)
        s2 = xi.std(0)
        s2[s2 == 0] = 1.0
        p2 = PoissonRegressor(alpha=1e-6, max_iter=400).fit((xi - m2) / s2, y)
        say(f"          pseudo-R2 (deviance-free, plain R2 of E[R]) {name:28s} "
            f"{r2_score(y, p2.predict((xi - m2) / s2)):.4f}")

    # --- G-D: the Jensen convexity ratio, WITH and WITHOUT the 25-patch restriction -------------
    say("\n   G-D  JENSEN CONVEXITY of the fitted kernel, per (leg,Cell,Year):")
    say("        ratio = mean_p Rhat(lai_p) / Rhat(mean_p lai_p), holding all non-LAI features at")
    say("        the patch mean. ADR 0310 sec 10 item 4's two prior estimates were median 1.221")
    say("        vs 1.082 (q95 tail ~8.4-8.5 replicating), BOTH conditioned on all 25 patches")
    say("        occupied -- excluding the bright patches carrying 64.8 % of recruitment. Both")
    say("        conditionings are reported here.")
    xs = bb.select(feats_full).to_numpy().astype(float)
    rhat = pr.predict((xs - mu) / sd)
    key = bb.select(["leg", "Cell", "Year"]).with_columns([
        pl.Series("rhat", rhat), pl.Series("lai", xs[:, 0]),
        pl.Series("occ", (bb["n_stems_p"].to_numpy() > 0).astype(np.int8)),
    ])
    # mean-LAI counterfactual: replace column 0 by the cell-year mean, keep the rest
    lai_cm = key.group_by(["leg", "Cell", "Year"]).agg([
        pl.col("lai").mean().alias("lai_bar"), pl.len().alias("npy"),
        pl.col("occ").sum().alias("nocc")])
    j = key.join(lai_cm, on=["leg", "Cell", "Year"], how="left")
    xs_cf = xs.copy()
    xs_cf[:, 0] = j["lai_bar"].to_numpy()
    j = j.with_columns(pl.Series("rhat_cf", pr.predict((xs_cf - mu) / sd)))
    agg = j.group_by(["leg", "Cell", "Year"]).agg([
        pl.col("rhat").mean().alias("r_mean"), pl.col("rhat_cf").mean().alias("r_at_mean"),
        pl.col("npy").first(), pl.col("nocc").first()])
    agg = agg.filter(pl.col("r_at_mean") > 1e-9).with_columns(
        (pl.col("r_mean") / pl.col("r_at_mean")).alias("jensen"))
    for lbl, sel in [("ALL cell-years (no restriction)", agg),
                     ("all 25 patches occupied", agg.filter(
                         (pl.col("npy") == 25) & (pl.col("nocc") == 25)))]:
        v = sel["jensen"].to_numpy()
        if len(v) == 0:
            say(f"        {lbl:34s} n=0")
            continue
        say(f"        {lbl:34s} n={len(v):8d} median={np.median(v):.4f} "
            f"mean={v.mean():.4f} q95={np.quantile(v, .95):.4f} q99={np.quantile(v, .99):.4f}")
    # who carries the recruitment
    kk = key.sort("rhat", descending=True)
    tot = float(kk["rhat"].sum())
    n5 = max(1, int(0.05 * kk.height))
    say(f"        share of fitted recruitment in the brightest 5 % of patch-years (lowest LAI): "
        f"{float(kk.head(n5)['rhat'].sum()) / tot:.4f}   [ADR 0093 published 0.648 for the C]")

    # --- G-E: the reconstructed-LAI bias against the C's own LAI_STAND, GLOBAL ------------------
    say("\n   G-E  RECONSTRUCTED PATCH LAI vs the C's OWN LAI_STAND output, per cell-year.")
    say("        (cell_year_lai_{hist,ssp}.parquet IS the C's gridded LAI_STAND, all trees, cell")
    say("        mean -- scripts/build_laistand_lai_feature.py. The reconstruction is >5 m only.)")
    for leg in LEG_YEARS:
        ref = pl.read_parquet(LAI_REF[leg])
        mine = (pl.read_parquet(f"{OUT}/prep_patch_year_stand.parquet",
                                columns=["leg", "seed", "Cell", "Year", "lai_stand"])
                .filter((pl.col("seed") == 1) & (pl.col("leg") == leg))
                .group_by(["Cell", "Year"]).agg(pl.col("lai_stand").mean().alias("mine")))
        jj = mine.join(ref, on=["Cell", "Year"], how="inner").filter(pl.col("lai") > 0.05)
        r = (jj["mine"] / jj["lai"]).to_numpy()
        say(f"        {leg}: n={len(r)} cell-years (674-cell sample)  ratio mine/C: "
            f"median={np.median(r):.4f} mean={r.mean():.4f} p05={np.quantile(r, .05):.4f} "
            f"p95={np.quantile(r, .95):.4f}")
    say("        [carry this bias with every LAI-conditioned number below]")
    say("\n### STAGE gate done")


# --------------------------------------------------------------------------- STAGE scan
def stage_scan(leg: str, seed: int) -> None:
    from build_slow_runtime_table import patch_stand_lai_expr
    from lpjmlfit_emulator.data import TREE_TYPES

    y0, y1 = LEG_YEARS[leg]
    dst = f"{OUT}/dens_patch_year_{leg}_s{seed}.parquet"
    say(f"\n### STAGE scan -- {leg} seed{seed} -> {dst}")
    say(f"   TREE_TYPES = {tuple(TREE_TYPES)}   years {y0}-{y1}")
    live = pl.col("isdead") == 0
    parts = []
    step = 5
    for ya in range(y0, y1 + 1, step):
        yb = min(ya + step - 1, y1)
        t = time.time()
        lf = (pl.scan_parquet(ROSTER[(leg, seed)],
                              parallel="row_groups")
              .select(["Year", "Cell", "Patch", "Type", "isdead", "Height", "Age", "agb",
                       "LAI", "fpc_ind"])
              .filter((pl.col("Year") >= ya) & (pl.col("Year") <= yb)
                      & (pl.col("Type") <= 6))
              .with_columns(patch_stand_lai_expr().alias("_sl"))
              .group_by(["Cell", "Patch", "Year"])
              .agg(
                  pl.len().alias("n_all"),
                  live.sum().alias("n"),
                  (pl.col("isdead") == 1).sum().alias("n_dead"),
                  pl.col("_sl").filter(live).sum().alias("lai_stand"),
                  pl.col("fpc_ind").filter(live).sum().alias("fpc_sum"),
                  pl.col("agb").filter(live).sum().alias("agb_sum"),
                  (pl.col("Age") - 1).filter(live).mean().alias("age_mean"),
                  pl.col("Height").filter(live).max().alias("h_max"),
                  (pl.col("Height") * pl.col("fpc_ind")).filter(live).sum().alias("_hfpc"),
              ))
        d = lf.collect()
        # KEY-SET assertion (mandate: streaming group_by is not deterministic; this is NOT
        # streaming, and we prove the key set anyway).
        assert d.select(["Cell", "Patch", "Year"]).n_unique() == d.height, "duplicate keys!"
        parts.append(d)
        say(f"   {ya}-{yb}: {d.height} patch-years  ({time.time() - t:.0f}s)")
    d = pl.concat(parts)
    d = d.with_columns([
        pl.when(pl.col("fpc_sum") > 0).then(pl.col("_hfpc") / pl.col("fpc_sum"))
        .otherwise(0.0).alias("h_mean"),
        pl.col("n").cast(pl.Int32), pl.col("n_dead").cast(pl.Int32),
        pl.col("n_all").cast(pl.Int32),
    ]).drop("_hfpc")
    d = d.fill_null(0.0)
    assert d.select(["Cell", "Patch", "Year"]).n_unique() == d.height
    d.write_parquet(dst)
    say(f"   WROTE {dst}: {d.height} rows, cells={d['Cell'].n_unique()}, "
        f"patches max={d['Patch'].max()}, mean n={float(d['n'].mean()):.4f}")


# --------------------------------------------------------------------------- rollout machinery
def read_pxy(leg: str, seed: int, cols: list[str] | None = None) -> pl.DataFrame:
    """Read a dens_patch_year_* table, restoring the integer key dtypes.

    NOTE: stage_scan's `fill_null(0.0)` promoted EVERY column to Float64 (a float fill literal
    promotes an integer column silently). The keys are cast back here rather than by rebuilding the
    4 tables -- the same class of silent dtype drift the repo's Float32 accumulation trap is about.
    """
    d = pl.read_parquet(f"{OUT}/dens_patch_year_{leg}_s{seed}.parquet", columns=cols)
    for c in ("Cell", "Patch", "Year"):
        if c in d.columns:
            d = d.with_columns(pl.col(c).cast(pl.Int64))
    return d


def build_dense(leg: str, seed: int, cells: np.ndarray) -> dict:
    """Dense [chain, year] arrays for one (leg, seed). chain = (cell, patch) over 0..NP-1."""
    y0, y1 = LEG_YEARS[leg]
    ny = y1 - y0 + 1
    np_ = 25
    lut = np.full(int(cells.max()) + 1, -1, dtype=np.int64)
    lut[cells] = np.arange(len(cells))
    nch = len(cells) * np_
    d = read_pxy(leg, seed)
    d = d.filter(pl.col("Cell").is_in(pl.Series(cells)) & (pl.col("Patch") < np_))
    row = lut[d["Cell"].to_numpy()] * np_ + d["Patch"].to_numpy()
    assert row.min() >= 0
    col = d["Year"].to_numpy() - y0
    out = {}
    for name, dt, src in [("n", np.float32, "n"), ("n_dead", np.float32, "n_dead"),
                          ("lai", np.float32, "lai_stand"), ("agb", np.float32, "agb_sum"),
                          ("age", np.float32, "age_mean"), ("hmax", np.float32, "h_max"),
                          ("fpc", np.float32, "fpc_sum")]:
        a = np.zeros((nch, ny), dtype=dt)
        a[row, col] = d[src].to_numpy().astype(dt)
        out[name] = a
    out["present"] = np.zeros((nch, ny), dtype=bool)
    out["present"][row, col] = True
    out["cells"] = cells
    out["np"] = np_
    out["ny"] = ny
    out["y0"] = y0
    return out


def env_matrix(leg: str, cells: np.ndarray) -> np.ndarray:
    """[cell, year, feature] climate."""
    y0, y1 = LEG_YEARS[leg]
    e = load_env(leg).filter(pl.col("Cell").is_in(pl.Series(cells)))
    lut = np.full(int(cells.max()) + 1, -1, dtype=np.int64)
    lut[cells] = np.arange(len(cells))
    m = np.zeros((len(cells), y1 - y0 + 1, len(ENV_COLS)), dtype=np.float32)
    r = lut[e["Cell"].to_numpy()]
    c = e["Year"].to_numpy() - y0
    m[r, c, :] = e.select(ENV_COLS).to_numpy().astype(np.float32)
    return m




# --------------------------------------------------------------------------- feature sets
#: full state seen by the DEATH head and by the DENSITY recruitment head
FEAT_STATE = ["n_p", "lai_p", "agb_p", "age_p", "hmax_p", "fpc_p"]
#: the DENSITY features -- these are what the "without the feedback" arm's recruitment head loses
FEAT_DENS = ["n_p", "lai_p", "agb_p", "fpc_p"]
#: state features that are NOT a density measure (kept in both arms)
FEAT_NONDENS = ["age_p", "hmax_p"]
NENV = len(ENV_COLS)


def make_features(cols, s, y, env, nroll, lairoll, cell_rep, idx):
    """Feature matrix for the step y -> y+1: state at y, climate at y+1.

    `nroll` / `lairoll` are already restricted to `idx`; None means "use FIT's own value".
    """
    src = {
        "n_p": s["n"][idx, y] if nroll is None else nroll,
        "lai_p": s["lai"][idx, y] if lairoll is None else lairoll,
        "agb_p": s["agb"][idx, y],
        "age_p": s["age"][idx, y],
        "hmax_p": s["hmax"][idx, y],
        "fpc_p": s["fpc"][idx, y],
    }
    x = [src[c] for c in cols if c in src]
    x += [env[cell_rep[idx], y + 1, k] for k in range(NENV)]
    return np.column_stack(x).astype(np.float32)


def cell_means(p: np.ndarray, ncell: int, npatch: int) -> np.ndarray:
    """[chain, year] -> per-cell mean over all patch-years (structural zeros already in p)."""
    return p.reshape(ncell, npatch, p.shape[1]).mean(axis=(1, 2))


def score_arm(name: str, xh: np.ndarray, xs: np.ndarray, truth: dict, ll: pl.DataFrame,
              rows: list, univ: np.ndarray | None = None, ulab: str = "ALL") -> dict:
    """xh/xs = per-CELL leg-mean stems/patch for the arm. Appends every band row to `rows`."""
    dp = xs - xh
    d1 = truth["s1_ssp"] - truth["s1_hist"]
    d2 = truth["s2_ssp"] - truth["s2_hist"]
    dbar = 0.5 * (d1 + d2)
    la = np.abs(ll["lat"].to_numpy())
    w = ll["w"].to_numpy()
    if univ is None:
        univ = np.ones(len(w), dtype=bool)
    out = {}
    for band, lo, hi in [("GLOBAL", 0.0, 90.1)] + LAT_BANDS:
        m = (la >= lo) & (la < hi) & (w > 0) & univ
        if m.sum() < 20:
            continue
        ww = w[m] / w[m].sum()
        num = float((dp[m] * ww).sum())
        den = float((dbar[m] * ww).sum())
        noise = abs(float((d1[m] * ww).sum()) - float((d2[m] * ww).sum())) / np.sqrt(2.0)
        snr = abs(den) / noise if noise > 0 else float("inf")
        ratio = num / den if den != 0 else float("nan")
        det = snr >= 3.0
        rows.append(dict(arm=name, universe=ulab, band=band, n_cells=int(m.sum()),
                         num=num, den=den,
                         two_seed_noise=noise, snr=snr,
                         ratio=ratio if det else float("nan"), ratio_raw=ratio, determined=det))
        out[band] = (ratio, det, snr)
    g = out["GLOBAL"]
    bands = "  ".join(f"{b}={out[b][0]:+.3f}{'' if out[b][1] else '(n/d)'}"
                      for b, _, _ in LAT_BANDS if b in out)
    gnum = float((dp[univ] * w[univ]).sum() / w[univ].sum())
    say(f"   {name:26s} [{ulab:7s}] GLOBAL ratio={g[0]:+.4f}  (pred resp={gnum:+.5f} "
        f"snr={g[2]:.1f}{'' if g[1] else ' UNDETERMINED'})   {bands}")
    return out


def stage_roll() -> None:
    import lightgbm as lgb

    t00 = time.time()
    say("\n### STAGE roll -- fit the heads, run every arm and null, score on ADR 0111/0113's"
        " statistic")
    ll_all = load_latlon()
    folds = load_folds()

    # ---- universe: cells with >=1 tree stem-year in ANY leg, ANY seed. Structural zeros for the
    # rest of a cell's patch-years; NO inner join across legs/seeds (mandate 4).
    tb = []
    for leg in LEG_YEARS:
        for sd in (1, 2):
            d = read_pxy(leg, sd, ["Cell", "n"])
            tb.append(d.filter(pl.col("n") > 0).select("Cell").unique())
    cells = np.sort(pl.concat(tb).unique()["Cell"].to_numpy())
    badc = set(int(c) for c in suspect_blocks()["Cell"].to_numpy())
    nb = len(cells)
    cells = np.array([c for c in cells if int(c) not in badc])
    say(f"   dropped {nb - len(cells)} cells named in prep_suspect_cell_blocks.csv "
        "(the 5 damaged ssp370-seed2 roster blocks) from the universe entirely")
    say(f"   UNIVERSE: {len(cells)} cells tree-bearing in at least one leg/seed (of 67 420). "
        "ADR 0111's capped basis was 51 767 cells; ADR 0106's criterion names 54 020 historic "
        "tree-bearing cells. THIS IS AN AGGREGATE, NOT THE ACCEPTANCE BASIS.")
    fmap = dict(zip(folds["Cell"].to_numpy(), folds["fold"].to_numpy(), strict=True))
    fold_of = np.array([fmap.get(int(c), int(c) % 5) for c in cells], dtype=np.int8)
    order = np.argsort(fold_of, kind="stable")
    cells, fold_of = cells[order], fold_of[order]
    ll = pl.DataFrame({"Cell": cells}).join(ll_all, on="Cell", how="left")
    assert ll["lat"].null_count() == 0, "a universe cell is missing from cell_latlon.txt"
    NP = 25
    ncell = len(cells)
    cell_rep = np.repeat(np.arange(ncell), NP)
    chain_fold = np.repeat(fold_of, NP)
    say(f"   chains = {ncell * NP}; fold sizes (cells) = "
        f"{[int((fold_of == f).sum()) for f in range(5)]}  "
        f"(fold map read from tables/fold_hash5_pooled.txt, the map the forests themselves use)")

    st, envm = {}, {}
    for leg in LEG_YEARS:
        st[(leg, 1)] = build_dense(leg, 1, cells)
        envm[leg] = env_matrix(leg, cells)
        say(f"   dense {leg} seed1: mean n={float(st[(leg, 1)]['n'].mean()):.4f}  "
            f"ny={st[(leg, 1)]['ny']}  max Patch used={NP - 1}")

    # ---- truth per-cell leg means (both seeds)
    truth = {}
    for leg, tag in [("historic", "hist"), ("ssp370", "ssp")]:
        for sd in (1, 2):
            d = read_pxy(leg, sd, ["Cell", "Patch", "Year", "n"]).filter(pl.col("Patch") < NP)
            bad = suspect_blocks().filter((pl.col("leg") == leg) & (pl.col("seed") == sd))
            if bad.height:
                d = d.join(bad.select("Cell").with_columns(pl.lit(True).alias("_b")), on="Cell",
                           how="left").filter(pl.col("_b").is_null()).drop("_b")
                say(f"   excluded {bad.height} damaged (leg,seed,Cell) blocks from {leg} s{sd}")
            y0, y1 = LEG_YEARS[leg]
            agg = d.group_by("Cell").agg(pl.col("n").sum().alias("s"))
            m = dict(zip(agg["Cell"].to_numpy(), agg["s"].to_numpy(), strict=True))
            den = NP * (y1 - y0 + 1)
            truth[f"s{sd}_{tag}"] = np.array([m.get(int(c), 0) / den for c in cells], dtype=float)
    w = ll["w"].to_numpy()
    for k, v in truth.items():
        say(f"   truth {k}: area-weighted mean stems/patch = {float((v * w).sum() / w.sum()):.5f}")
    d1 = truth["s1_ssp"] - truth["s1_hist"]
    d2 = truth["s2_ssp"] - truth["s2_hist"]
    dbar = 0.5 * (d1 + d2)
    univ_hist = truth["s1_hist"] > 0          # tree-bearing in the HISTORIC leg, seed 1
    say(f"   SECOND UNIVERSE 'HISTTB' = cells tree-bearing in historic seed1: "
        f"{int(univ_hist.sum())} cells (ADR 0106's 54 020 basis). The wide 'ALL' universe adds the "
        "cells that hold no tree today and GAIN trees under warming -- mandate 4's structural "
        "zeros -- and that changes the SIGN of the truth's own aggregate response:")
    for lab, mm in [("ALL", np.ones(len(w), dtype=bool)), ("HISTTB", univ_hist)]:
        say(f"     TRUTH aggregate response [{lab:6s}, {int(mm.sum())} cells] = "
            f"{float((dbar[mm] * w[mm]).sum() / w[mm].sum()):+.5f} stems/patch; two-seed noise "
            f"{abs(float(((d1[mm] - d2[mm]) * w[mm]).sum() / w[mm].sum())) / np.sqrt(2):.5f}  "
            "[ADR 0111 published -0.122 +- 0.0042 on its own capped 51 767 cells]")

    # ------------------------------------------------------------------ fit the heads
    say("\n   --- fitting the heads: LightGBM, poisson for the two count flows, l2 for LAI. "
        "5-fold BY CELL. ---")
    XF = FEAT_STATE + [f"env{k}" for k in range(NENV)]
    XN = FEAT_NONDENS + [f"env{k}" for k in range(NENV)]
    STRIDE = 17
    tr = {"XF": [], "XN": [], "D": [], "R": [], "LAI": [], "NEXT": [], "fold": []}
    for leg in LEG_YEARS:
        s = st[(leg, 1)]
        for y in range(s["ny"] - 1):
            idx = np.arange(y % STRIDE, s["n"].shape[0], STRIDE)
            tr["XF"].append(make_features(XF, s, y, envm[leg], None, None, cell_rep, idx))
            tr["XN"].append(make_features(XN, s, y, envm[leg], None, None, cell_rep, idx))
            nn = s["n"][idx, y]
            nd = s["n_dead"][idx, y + 1].astype(float)
            nx = s["n"][idx, y + 1].astype(float)
            tr["R"].append(np.clip(nx - nn + nd, 0, None))
            tr["D"].append(nd + np.clip(nn - nx - nd, 0, None))
            tr["LAI"].append(s["lai"][idx, y + 1].astype(float))
            tr["NEXT"].append(nx)
            tr["fold"].append(chain_fold[idx])
    XFa = np.vstack(tr["XF"])
    XNa = np.vstack(tr["XN"])
    yD = np.concatenate(tr["D"])
    yR = np.concatenate(tr["R"])
    yL = np.concatenate(tr["LAI"])
    yN = np.concatenate(tr["NEXT"])
    fo = np.concatenate(tr["fold"])
    del tr
    say(f"   training rows = {len(yD)} (systematic stride {STRIDE} over chains, offset rotating "
        f"by year); mean D={yD.mean():.5f} mean R={yR.mean():.5f}")
    say(f"   identity check on the training rows: mean(n_next - n_prev - R + D) = "
        f"{0.0:.1e} by construction (D and R are defined as the residual pair)")

    P = dict(objective="poisson", num_leaves=48, learning_rate=0.10, n_estimators=140,
             min_child_samples=200, verbose=-1, n_jobs=int(os.environ.get("NCPUS", "16")),
             force_row_wise=True)
    PL = dict(P, objective="l2")
    models = {}
    for head, X, yv, par in [("D", XFa, yD, P), ("Rdens", XFa, yR, P), ("Rnodens", XNa, yR, P),
                             ("LAI", XFa, yL, PL), ("NEXT", XFa, yN, P)]:
        for f in range(5):
            m = fo != f
            t = time.time()
            models[(head, f)] = lgb.LGBMRegressor(**par).fit(X[m], yv[m])
            if f == 0:
                say(f"   head {head:8s} fold0 fitted in {time.time() - t:.0f}s on {int(m.sum())}"
                    f" rows; predicting held-out fold mean pred="
                    f"{models[(head, 0)].predict(X[~m]).mean():.5f} vs truth {yv[~m].mean():.5f}")
    # N5 gate: is the fitted DENSITY recruitment head decreasing in LAI?
    say("\n   N5 ELASTICITY GATE on the FITTED head (partial dependence at the global medians):")
    base = np.median(XFa, axis=0)[None, :].repeat(9, axis=0)
    lg_ = np.array([0.05, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0])
    base[:, XF.index("lai_p")] = lg_
    pdp = np.mean([models[("Rdens", f)].predict(base) for f in range(5)], axis=0)
    for a_, b_ in zip(lg_, pdp, strict=True):
        say(f"      LAI={a_:5.2f} -> E[R]={b_:.5f}")
    dln = (np.log(max(pdp[-1], 1e-9)) - np.log(max(pdp[2], 1e-9))) / (lg_[-1] - lg_[2])
    say(f"   d ln E[R] / d LAI over 0.5->8 = {dln:+.4f} per LAI unit -> "
        f"{'PASS (negative)' if dln < 0 else 'FAIL => the with/without contrast is VOID'}")

    # ------------------------------------------------------------------ arms
    rows: list[dict] = []
    results: dict[str, dict] = {}
    lead_rows: list[dict] = []

    def predict(head: str, X: np.ndarray) -> np.ndarray:
        o = np.empty(X.shape[0], dtype=np.float64)
        for f in range(5):
            m = chain_fold == f
            if m.any():
                o[m] = models[(head, f)].predict(X[m])
        return o

    def rollout(leg: str, rhead: str, closed_lai: bool, mode: str, rng_seed: int = 0
                ) -> np.ndarray:
        """Free-running per-patch count rollout. Returns [chain, year] predictions."""
        s = st[(leg, 1)]
        ny = s["ny"]
        nch = s["n"].shape[0]
        allidx = np.arange(nch)
        p = np.zeros((nch, ny), dtype=np.float32)
        n = s["n"][:, 0].astype(np.float64)          # seeded with FIT's own leg-first-year count
        p[:, 0] = n
        lai = s["lai"][:, 0].astype(np.float64) if closed_lai else None
        rng = np.random.default_rng(1000 + rng_seed)
        for y in range(ny - 1):
            Xf = make_features(XF, s, y, envm[leg], n, lai, cell_rep, allidx)
            D = np.clip(predict("D", Xf), 0, None)
            if rhead == "Rdens":
                R = np.clip(predict("Rdens", Xf), 0, None)
            else:
                Xn = make_features(XN, s, y, envm[leg], n, lai, cell_rep, allidx)
                R = np.clip(predict("Rnodens", Xn), 0, None)
            if mode == "mean":
                n = np.clip(n - np.minimum(D, n) + R, 0, None)
            else:
                ni = np.rint(n).astype(np.int64)
                surv_p = np.where(ni > 0, 1.0 - np.clip(D / np.maximum(ni, 1), 0, 1), 0.0)
                n = (rng.binomial(ni, surv_p) + rng.poisson(np.clip(R, 0, 50))).astype(float)
            if closed_lai:
                lai = np.clip(predict("LAI", Xf), 0, None)
            p[:, y + 1] = n
        return p

    def onestep(leg: str, rhead: str) -> np.ndarray:
        """Teacher-forced: FIT's own n every year (= ADR 0113's A0 configuration)."""
        s = st[(leg, 1)]
        ny = s["ny"]
        nch = s["n"].shape[0]
        allidx = np.arange(nch)
        p = np.zeros((nch, ny), dtype=np.float32)
        p[:, 0] = s["n"][:, 0]
        for y in range(ny - 1):
            Xf = make_features(XF, s, y, envm[leg], None, None, cell_rep, allidx)
            D = np.clip(predict("D", Xf), 0, None)
            if rhead == "Rdens":
                R = np.clip(predict("Rdens", Xf), 0, None)
            else:
                Xn = make_features(XN, s, y, envm[leg], None, None, cell_rep, allidx)
                R = np.clip(predict("Rnodens", Xn), 0, None)
            nn = s["n"][:, y].astype(np.float64)
            p[:, y + 1] = np.clip(nn - np.minimum(D, nn) + R, 0, None)
        return p

    def single_target(leg: str, recurse: bool) -> np.ndarray:
        """ADR 0113's own formulation: ONE forest predicting n(y+1) directly.
        recurse=False == arm A0 (one-step, C-forced); recurse=True == arm A1."""
        s = st[(leg, 1)]
        ny = s["ny"]
        nch = s["n"].shape[0]
        allidx = np.arange(nch)
        p = np.zeros((nch, ny), dtype=np.float32)
        p[:, 0] = s["n"][:, 0]
        n = s["n"][:, 0].astype(np.float64)
        for y in range(ny - 1):
            Xf = make_features(XF, s, y, envm[leg], n if recurse else None, None, cell_rep, allidx)
            n = np.clip(predict("NEXT", Xf), 0, None)
            p[:, y + 1] = n
            if not recurse:
                n = s["n"][:, y + 1].astype(np.float64)
        return p

    def register(name: str, ph: np.ndarray, ps: np.ndarray) -> None:
        xh = cell_means(ph, ncell, NP)
        xs = cell_means(ps, ncell, NP)
        results[name] = dict(xh=xh, xs=xs, ph=ph, ps=ps)
        score_arm(name, xh, xs, truth, ll, rows, None, "ALL")
        score_arm(name, xh, xs, truth, ll, rows, univ_hist, "HISTTB")
        # level drift, area-weighted, on the ssp370 leg
        s = st[("ssp370", 1)]
        for lo, hi, lbl in [(0, 4, "2020-2024"), (10, 19, "2030-2039"), (40, 49, "2060-2069"),
                            (60, 79, "2080-2099")]:
            pm = cell_means(ps[:, lo:hi + 1], ncell, NP)
            tm = cell_means(s["n"][:, lo:hi + 1].astype(np.float32), ncell, NP)
            dr = float(((pm - tm) * w).sum() / w.sum())
            lead_rows.append(dict(arm=name, window=lbl, drift=dr,
                                  pred=float((pm * w).sum() / w.sum()),
                                  truth=float((tm * w).sum() / w.sum())))
        say("      level drift (area-weighted, stems/patch): " + "  ".join(
            f"{r['window']}={r['drift']:+.4f}" for r in lead_rows if r["arm"] == name))

    say("\n   --- N1/N2/N3: the nulls ---")
    # N1 frozen at 2019 on BOTH legs
    n2019 = st[("historic", 1)]["n"][:, -1].astype(np.float32)
    ph = np.repeat(n2019[:, None], st[("historic", 1)]["ny"], axis=1)
    ps = np.repeat(n2019[:, None], st[("ssp370", 1)]["ny"], axis=1)
    register("N1_FROZEN2019", ph, ps)
    # N2 frozen at each leg's own first year
    ph = np.repeat(st[("historic", 1)]["n"][:, 0][:, None], st[("historic", 1)]["ny"], axis=1)
    ps = np.repeat(st[("ssp370", 1)]["n"][:, 0][:, None], st[("ssp370", 1)]["ny"], axis=1)
    register("N2_FROZEN_LEGSTART", ph, ps)
    # N3 climatology: i.i.d. draws from each patch's OWN historic empirical distribution
    hn = st[("historic", 1)]["n"]
    n3 = []
    for k in range(5):
        rng = np.random.default_rng(7000 + k)
        jh = rng.integers(0, hn.shape[1], size=hn.shape)
        js = rng.integers(0, hn.shape[1], size=(hn.shape[0], st[("ssp370", 1)]["ny"]))
        ph = np.take_along_axis(hn, jh, axis=1)
        ps = np.take_along_axis(hn, js, axis=1)
        score_arm(f"N3_CLIMATOLOGY_s{k}", cell_means(ph, ncell, NP),
                  cell_means(ps, ncell, NP), truth, ll, rows, univ_hist, "HISTTB")
        r = score_arm(f"N3_CLIMATOLOGY_s{k}", cell_means(ph, ncell, NP),
                      cell_means(ps, ncell, NP), truth, ll, rows, None, "ALL")
        n3.append(r["GLOBAL"][0])
    say(f"   N3 climatology over 5 draws: mean ratio={np.mean(n3):+.5f}  sd={np.std(n3):.5f}  "
        f"(MUST be ~0)")

    say("\n   --- ADR 0113 REPLICATION with its OWN single-target formulation (one forest for "
        "n(y+1)). A0 published +0.707, A1 published -0.226. This is the comparability anchor for "
        "everything below. ---")
    register("A0_REPLICA_onestep", single_target("historic", False), single_target("ssp370", False))
    register("A1_REPLICA_recursed", single_target("historic", True), single_target("ssp370", True))

    say("\n   --- N4: the one-step teacher-forced reference for the D/R DECOMPOSITION ---")
    register("N4_ONESTEP_dens", onestep("historic", "Rdens"), onestep("ssp370", "Rdens"))
    register("N4_ONESTEP_nodens", onestep("historic", "Rnodens"), onestep("ssp370", "Rnodens"))

    say("\n   --- the closed rollouts: conditional mean ---")
    for name, rh, cl in [("ROLL_NODENS_mean", "Rnodens", False),
                         ("ROLL_DENS_mean", "Rdens", False),
                         ("ROLL_CLOSEDLAI_mean", "Rdens", True)]:
        t = time.time()
        register(name, rollout("historic", rh, cl, "mean"), rollout("ssp370", rh, cl, "mean"))
        say(f"      ({time.time() - t:.0f}s)")

    say("\n   --- the closed rollouts: STOCHASTIC head (binomial survival + Poisson births) ---")
    for name, rh, cl in [("ROLL_NODENS_stoch", "Rnodens", False),
                         ("ROLL_DENS_stoch", "Rdens", False),
                         ("ROLL_CLOSEDLAI_stoch", "Rdens", True)]:
        rr = []
        for k in range(2):
            t = time.time()
            ph = rollout("historic", rh, cl, "stoch", k)
            ps = rollout("ssp370", rh, cl, "stoch", k)
            register(f"{name}_s{k}", ph, ps)
            rr.append(results[f"{name}_s{k}"])
            say(f"      ({time.time() - t:.0f}s)")
        # ensemble mean over stochastic draws
        register(name + "_ens",
                 np.mean([r["ph"] for r in rr], axis=0), np.mean([r["ps"] for r in rr], axis=0))

    # ------------------------------------------------------------------ distribution scoring
    say("\n   --- DISTRIBUTION vs FIT's 25-patch ensemble (ssp370 2080-2099), the tolerance the "
        "acceptance criterion actually asks for ---")
    s1 = st[("ssp370", 1)]["n"][:, 60:80].astype(np.float64)
    tp = s1.reshape(ncell, NP, -1).mean(axis=2)          # 25 patch means per cell, truth seed 1
    dist_rows = []
    for name, r in results.items():
        pp = r["ps"][:, 60:80].astype(np.float64).reshape(ncell, NP, -1).mean(axis=2)
        sd_p = pp.std(axis=1)
        sd_t = tp.std(axis=1)
        # Wasserstein-1 between the two 25-point patch distributions, per cell
        w1 = np.abs(np.sort(pp, axis=1) - np.sort(tp, axis=1)).mean(axis=1)
        ok = sd_t > 0
        dist_rows.append(dict(
            arm=name,
            sd_pred=float((sd_p * w).sum() / w.sum()),
            sd_truth=float((sd_t * w).sum() / w.sum()),
            sd_ratio=float((sd_p[ok] * w[ok]).sum() / (sd_t[ok] * w[ok]).sum()),
            w1=float((w1 * w).sum() / w.sum()),
            mean_abs_bias=float((np.abs(pp.mean(1) - tp.mean(1)) * w).sum() / w.sum())))
        say(f"   {name:24s} across-patch sd pred/truth = {dist_rows[-1]['sd_ratio']:.4f}  "
            f"(pred {dist_rows[-1]['sd_pred']:.4f} vs truth {dist_rows[-1]['sd_truth']:.4f})  "
            f"W1={dist_rows[-1]['w1']:.4f}  |cell bias|={dist_rows[-1]['mean_abs_bias']:.4f}")

    # per-cell tolerance (ADR 0106): |pred - truth| <= max(10 %, the two-seed spread)
    say("\n   --- per-cell acceptance check on the ssp370 2080-2099 count level "
        "(ADR 0106's basis) ---")
    t1 = tp.mean(1)
    d2c = read_pxy("ssp370", 2, ["Cell", "Patch", "Year", "n"]).filter(
        (pl.col("Patch") < NP) & (pl.col("Year") >= 2080) & (pl.col("Year") <= 2099))
    agg = d2c.group_by("Cell").agg(pl.col("n").sum().alias("s"))
    mm = dict(zip(agg["Cell"].to_numpy(), agg["s"].to_numpy(), strict=True))
    t2 = np.array([mm.get(int(c), 0) / (NP * 20) for c in cells], dtype=float)
    spread = np.abs(t1 - t2) / np.maximum(0.5 * (t1 + t2), 1e-9)
    tol = np.maximum(0.10, spread)
    acc_rows = []
    for name, r in results.items():
        pm = r["ps"][:, 60:80].astype(np.float64).reshape(ncell, NP, -1).mean(axis=(1, 2))
        rel = np.abs(pm - t1) / np.maximum(t1, 1e-9)
        ok = t1 > 0
        frac = float((rel[ok] <= tol[ok]).mean())
        acc_rows.append(dict(arm=name, frac_within=frac, n_cells=int(ok.sum())))
        say(f"   {name:24s} cells within max(10 %, two-seed spread) = {frac:.4f} "
            f"of {int(ok.sum())} cells with trees")
    say(f"   [reference: the truth's OWN second seed scores "
        f"{float((spread[t1 > 0] <= tol[t1 > 0]).mean()):.4f} by construction]")


    # ---------------------------------------------------------------- ADR 0116's one-sidedness
    # Bin cells by FIT's OWN leg-mean count response and read each arm's drift in that bin.
    # ADR 0116 section 4 measured the recursion reproducing 86.7 % of a large DECLINE against
    # 96.2 % of a large INCREASE (shortfall 3.5x) at lead 18. If the missing density feedback is
    # the cause, the arm that closes it must shrink the LOSS-side shortfall specifically.
    say("\n   --- ONE-SIDEDNESS: drift by decile of FIT's own leg-mean response (ADR 0116 sec 4's "
        "construction, on the leg-mean basis rather than at a fixed lead) ---")
    dec = np.argsort(np.argsort(dbar)) * 10 // len(dbar)
    onesided = []
    say(f"   {'arm':26s} " + " ".join(f"d{k + 1:<7d}" for k in range(10)))
    say(f"   {'FIT own response dbar':26s} " + " ".join(
        f"{float((dbar[dec == k] * w[dec == k]).sum() / w[dec == k].sum()):+7.3f} "
        for k in range(10)))
    for name, r in results.items():
        dp = (r['xs'] - r['xh']) - dbar
        cells_row = []
        for k in range(10):
            m = dec == k
            cells_row.append(float((dp[m] * w[m]).sum() / w[m].sum()))
            onesided.append(dict(arm=name, decile=k + 1, drift=cells_row[-1],
                                 fit_response=float((dbar[m] * w[m]).sum() / w[m].sum())))
        say(f"   {name:26s} " + " ".join(f"{v:+7.3f} " for v in cells_row))
    pl.DataFrame(onesided).write_csv(f"{OUT}/dens_onesided.csv")
    # per-cell arm responses, so any follow-up needs no rerun
    pc = {"Cell": cells, "lat": ll["lat"].to_numpy(), "w": w, "dbar": dbar, "d1": d1, "d2": d2}
    for name, r in results.items():
        pc[f"{name}__hist"] = r["xh"]
        pc[f"{name}__ssp"] = r["xs"]
    pl.DataFrame(pc).write_parquet(f"{OUT}/dens_percell_arms.parquet")
    say(f"   wrote {OUT}/dens_onesided.csv and dens_percell_arms.parquet")

    # ---------------------------------------------------------------- persist + verdict
    pl.DataFrame(rows).write_csv(f"{OUT}/dens_response_ratios.csv")
    pl.DataFrame(lead_rows).write_csv(f"{OUT}/dens_level_drift.csv")
    pl.DataFrame(dist_rows).write_csv(f"{OUT}/dens_distribution.csv")
    pl.DataFrame(acc_rows).write_csv(f"{OUT}/dens_acceptance.csv")
    say(f"\n   wrote {OUT}/dens_response_ratios.csv, dens_level_drift.csv, "
        "dens_distribution.csv, dens_acceptance.csv")

    say("\n" + "=" * 96)
    say("VERDICT AGAINST THE PRE-REGISTERED FALSIFIER")
    say("=" * 96)
    gr = {r["arm"]: r for r in rows if r["band"] == "GLOBAL" and r["universe"] == "HISTTB"}
    grall = {r["arm"]: r for r in rows if r["band"] == "GLOBAL" and r["universe"] == "ALL"}
    null_max = max(abs(gr[k]["ratio_raw"]) for k in gr
                   if k.startswith(("N1_", "N2_", "N3_")))
    say(f"   largest absolute NULL ratio (N1/N2/N3) = {null_max:.4f}  <- the discrimination "
        "threshold fixed by the pre-registration")
    for k in ["N1_FROZEN2019", "N2_FROZEN_LEGSTART", "A0_REPLICA_onestep",
              "A1_REPLICA_recursed", "N4_ONESTEP_dens", "ROLL_NODENS_mean",
              "ROLL_DENS_mean", "ROLL_CLOSEDLAI_mean", "ROLL_DENS_stoch_ens",
              "ROLL_NODENS_stoch_ens", "ROLL_CLOSEDLAI_stoch_ens"]:
        if k in gr:
            say(f"   {k:26s} ratio[HISTTB]={gr[k]['ratio_raw']:+.4f}  "
                f"ratio[ALL]={grall[k]['ratio_raw']:+.4f}")
    say(f"   ADR 0113 published: A0 one-step {ADR0113['A0_onestep']:+.3f}, persistence null "
        f"{ADR0113['A0_persistence_null']:+.3f}, A1 state-recursed "
        f"{ADR0113['A1_state_recursed']:+.3f}")
    dl = {(r["arm"], r["window"]): r["drift"] for r in lead_rows}
    for k in ["ROLL_NODENS_mean", "ROLL_DENS_mean", "ROLL_CLOSEDLAI_mean"]:
        say(f"   {k:26s} level drift 2080-2099 = {dl.get((k, '2080-2099'), float('nan')):+.4f} "
            "stems/patch")
    say(f"   elapsed {time.time() - t00:.0f}s")


def main() -> None:
    say(PREREG)
    stage = sys.argv[1] if len(sys.argv) > 1 else "gate"
    say(f"[stage={stage}] argv={sys.argv[1:]}")
    if stage == "gate":
        stage_gate()
    elif stage == "scan":
        stage_scan(sys.argv[2], int(sys.argv[3]))
    elif stage == "roll":
        stage_roll()
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()
