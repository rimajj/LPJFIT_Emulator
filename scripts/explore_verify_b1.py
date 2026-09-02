#!/usr/bin/env python
"""ADVERSARIAL VERIFICATION of item B1 (the hidden per-tree growth-failure counter).

Read-only except this file and /p/tmp/jamirp/X_explore/verify_b1_*.
Re-runs the finding's own pair construction, then attacks four specific things.

Stages (positional arg 1): haz | sens | both
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explore_hidden_counter as H  # noqa: E402  (the probe under test)

OUT = "/p/tmp/jamirp/X_explore"
TABLE_A = os.path.join(OUT, "prep_paired_stems.parquet")
SUSPECT = os.path.join(OUT, "prep_suspect_cell_blocks.csv")

PREREG = r"""
================================================================================
PRE-REGISTRATION — ADVERSARIAL VERIFICATION of B1, printed before any result
================================================================================

WHAT I AM TESTING (four specific claims of the finding under test)

 V1  THE HAZARD REBUILD IS CLAIMED TO BE AN IDENTITY.  The probe's own comment
     says: "mort_npp and mort_water both carry the factor (1+c_true) exactly, so
     dividing them by (1+c_true) and re-multiplying is an identity on any row
     where neither was clipped at 1."  But the probe divides the YEAR-y columns
     mort_npp / mort_water / mort_age / mort_temp by (1 + c(y+1)), because
     `mort_*` was never renamed into the year-(y+1) half of its self-join
     (`nxt_stem` does not contain them).  mort_npp(y) carries (1 + c(y)), not
     (1 + c(y+1)).
     STATISTIC: the share of scored pairs on which c(y) != c(y+1) — that is the
     share of rows on which the divisor is the wrong year's counter.
     MUST RETURN: if it is 0.000 the defect is vacuous and V1 is withdrawn.
     DERIVED PREDICTION from the recovered distribution: c(y+1) = 0 whenever the
     increment is non-negative and c(y+1) = c(y)+1 otherwise, so c(y) == c(y+1)
     can happen ONLY when both are 0 — i.e. the share must be approximately
     1 - P[c(y)=0 and c(y+1)=0] which the finding's own numbers put near 0.19.
     CORRECTED NUMBER: rebuild the hazard from the year-(y+1) columns
     mort_{npp,age,water,temp}(y+1) with the counter factor (1+cp)/(1+c(y+1)),
     which IS an identity at cp = c(y+1), and recompute the two published
     hazard-mass ratios (the "cost of discarding the count", published as
     0.852 / 0.791 / 0.726 / 0.654 / 0.661 at leads 1/5/10/15/20, and the
     perfect-agb oracle's).
     FALSIFIER FOR V1: if the corrected ratios differ from the published ones by
     less than 0.01 in absolute value at every lead, the defect is immaterial and
     I will say so.

 V2  THE TRUTH LABEL IS CONTAMINATED BY OUT-OF-RANGE RECOVERIES.  The C caps the
     counter at 5 (hard kill), so the recovery ratio r = mort_npp/mort_max
     satisfies r < 6 identically.  The probe's `forb` mask checks only the four
     forbidden bands below r = 4.1667; it does NOT reject r >= 6.  The finding's
     own earlier log prints "r>=6 (impossible: c<=5) = 0.0228-0.0397 %,
     max r = 181.777" and those rows therefore survive into the pair table with
     a recovered counter of up to 180.
     STATISTIC: the count and share of scored pairs with r >= 6 at either year;
     their share of the truth certain-death set (c(y+1) >= 5), published as
     113 758 rows; and their share of the total truth hazard mass, published as
     579 672.3.
     MUST RETURN: > 0 rows (the earlier log already proves that) — the question
     is the magnitude.
     FALSIFIER FOR V2: if the contaminated rows are < 0.5 % of the certain-death
     set AND < 0.2 % of the hazard mass, the defect is cosmetic and I say so.

 V3  THE ARM THE PROPAGABILITY VERDICT RESTS ON IS AN ORACLE, NOT A ROLLOUT.
     M3 is handed the TRUE year-(y+1) per-stem state, including `npp` — which is
     the first of the two terms of the very quantity whose sign is the label
     (bm_delta = bm_inc/nind - turnover).  The finding's own pre-registration
     calls M3 "the practical ceiling", then the falsifier calls it "the best
     rollout-legitimate arm" and concludes the counter IS propagable.
     STATISTIC: M3's positive-class recall and false-positive rate, and the
     propagated certain-death-set ratio at leads 1/5/10/20, as a function of a
     multiplicative Gaussian error of relative size sigma in {0.05, 0.10, 0.20}
     applied to EVERY year-(y+1) per-stem and stand state feature (train and
     test at the same sigma, so the model is adapted to its own noise — the
     generous case; the year-y state is left exact, which is generous again).
     PLUS an ablation with `npp` removed at both years.
     MUST RETURN at sigma = 0: recall 0.9023 and fpr 0.0066, reproducing the
     finding (a different value means I have not reproduced its pipeline and
     nothing else I say about it is admissible).
     FALSIFIER FOR V3: if recall stays >= 0.80 at fpr <= 0.05 AND the lead-10
     certain-death ratio stays inside [0.8, 1.25] at sigma = 0.20, then the
     propagability conclusion is robust to state error and V3 is withdrawn.
     CONFIRMATION OF V3: if either clause of the finding's own pre-registered
     "IS propagable" test fails at a realistic sigma, then the verdict was
     obtained from an oracle and must be re-stated as an upper bound.

 V4  THE FOLDS ARE NOT SPATIALLY BLOCKED AND THERE IS NO GEOGRAPHIC-ADDRESS
     NULL.  The probe uses fold = (Cell // 100) % 5 over cells sampled every
     100th orderA index, i.e. a ROUND-ROBIN over the sampled cells, so each
     held-out cell is bracketed by trained neighbours.
     STATISTIC: (a) an ADDRESS-ONLY null — LightGBM on (Cell, Year) and nothing
     else — under the probe's own interleaved folds and under 5 contiguous
     orderA blocks; (b) M2 and M3 refitted under the blocked folds.
     MUST RETURN: under blocked folds the address-only null must lose most of
     whatever it has under interleaved folds; if it has nothing under either
     (balanced accuracy <= 0.52) then geography carries nothing here and V4 is
     withdrawn as immaterial.
     FALSIFIER FOR V4: address-only balanced accuracy <= 0.52 under BOTH fold
     schemes, and M2/M3 moving by < 0.01 in recall between fold schemes.

BASIS (trap 3, restated because it is the finding's own basis)
  674 cells (Cell % 100 == 0), both forcing legs, both seeds, 25 patches, the
  above-5 m emitted stem population only.  NOT the acceptance criterion's
  54 020 tree-bearing cells / both scenarios / the response between them, and
  nothing here is an acceptance verdict.  The two seeds are pooled, so no number
  here is scored against the C's own two-run spread.
================================================================================
"""


def log(*a):
    print(*a, flush=True)


STEMCOLS = ["Age", "Height", "agb", "vegc", "npp", "transp", "wscal_mean", "SLA",
            "Longevity", "Wooddens", "LAI", "fpc_ind", "minwscal", "D95", "D95max",
            "beta_root", "mort_npp", "mort_age", "mort_water", "mort_temp"]
NXT_STEM = ["Height", "agb", "vegc", "npp", "transp", "wscal_mean", "LAI", "fpc_ind",
            "n_stems", "agb_sum", "npp_sum", "lai_stand", "h_max", "Age"]
HAZ_NXT = ["mort_npp", "mort_age", "mort_water", "mort_temp"]
KEY = ["leg", "seed", "Cell", "Patch", "Type", "ID"]
LEADS = ((1, 1), (2, 2), (3, 3), (5, 5), (10, 10), (15, 15), (20, 20),
         (1, 5), (6, 20), (21, 200))


def build_pairs(limit_cells: int = 0):
    """Reproduce stage_prop's pair table, PLUS the year-(y+1) hazard columns."""
    P = H.load_params()
    sus = pl.read_csv(SUSPECT)
    keys = [c for c in ["leg", "seed", "Cell"] if c in set(sus.columns)]
    lf = pl.scan_parquet(TABLE_A).select(
        ["leg", "seed", "Cell", "Patch", "Type", "ID", "Year", "isdead", "dup_key",
         *STEMCOLS]
    ).filter(pl.col("dup_key") == 0)
    if limit_cells:
        lf = lf.filter(pl.col("Cell") <= 100 * limit_cells)
    D = lf.collect().drop("dup_key")
    D = D.join(sus.select(keys).with_columns(pl.lit(True).alias("_b")), on=keys,
               how="left").filter(pl.col("_b").is_null()).drop("_b")
    y0 = {"historic": 2000, "ssp370": 2020}
    D = D.filter(pl.col("Year") != pl.col("leg").replace_strict(y0, return_dtype=pl.Int64))
    log(f"  stem-years after exclusions + first-leg-year drop: {D.height}")
    nk = D.select([*KEY, "Year"]).n_unique()
    log(f"  key uniqueness gate: n_unique(key,Year) = {nk}  height = {D.height}"
        f"  -> {'OK' if nk == D.height else 'DUPLICATED KEYS'}")

    pid = D["Type"].to_numpy()
    w1 = np.array([P[int(q)]["wdmort_1"] for q in pid])
    w2 = np.array([P[int(q)]["wdmort_2"] for q in pid])
    mmax = 10.0 ** (w1 + w2 / (D["Wooddens"].to_numpy() / 1e6))
    r_, c_, info_, forb_ = H.route_2b(D["mort_npp"].to_numpy(), mmax)
    D = D.with_columns(c2b=pl.Series(c_), info=pl.Series(info_), forb=pl.Series(forb_),
                       rr=pl.Series(r_), imposs=pl.Series(r_ >= 6.0))

    B = pl.scan_parquet(os.path.join(OUT, "prep_patch_year_stand.parquet")).select(
        ["leg", "seed", "Cell", "Patch", "Year", "n_stems", "agb_sum", "npp_sum",
         "lai_stand", "h_max", "h_mean", "age_mean", "fpc", "Wooddens_median"]
    ).collect()
    D = D.join(B, on=["leg", "seed", "Cell", "Patch", "Year"], how="left")

    CL = []
    for leg, f in (("historic", "cell_year_env_historic_w20.parquet"),
                   ("ssp370", "cell_year_env_ssp370_w20.parquet")):
        c_ = pl.scan_parquet(f"/p/tmp/jamirp/emulator_global/tables/{f}").collect()
        CL.append(c_.with_columns(pl.lit(leg).alias("leg")))
    CL = pl.concat(CL, how="vertical")
    climcols = [c for c in CL.columns if c not in ("Cell", "Year", "leg")]
    CL = CL.with_columns([pl.col(c).cast(pl.Float64) for c in climcols])
    D = D.join(CL, on=["leg", "Cell", "Year"], how="left")

    ren = ["c2b", "info", "forb", "imposs", "isdead", *NXT_STEM, *HAZ_NXT, *climcols]
    NX = D.select([*KEY, "Year", *ren]).rename({c: f"{c}_1" for c in ren})
    NX = NX.with_columns(Year=pl.col("Year") - 1)
    Q = D.join(NX, on=[*KEY, "Year"], how="inner")
    log(f"  consecutive-year pairs: {Q.height}")
    Q = Q.filter(pl.col("info") & ~pl.col("forb") & pl.col("info_1") & ~pl.col("forb_1"))
    log(f"  pairs with an EXACT counter at BOTH years (the finding's population): {Q.height}")
    return Q, climcols


def stage_haz(Q: pl.DataFrame):
    log("\n" + "=" * 78)
    log("V1 + V2 — the hazard rebuild and the out-of-range recoveries (no models)")
    log("=" * 78)
    prev = Q["c2b"].to_numpy()
    truth1 = Q["c2b_1"].to_numpy()
    lab = (truth1 >= 1).astype(np.int8)
    log(f"\n  event prevalence P[c(y+1)>=1] = {lab.mean():.6f}   (finding: 0.134790)")

    # ---------------- V1: how far does the wrong-year divisor reach?
    share_diff = float(np.mean(prev != truth1))
    both0 = float(np.mean((prev == 0) & (truth1 == 0)))
    log("\n--- V1: the divisor the finding used is c(y+1); the factor actually")
    log("    carried by the year-y hazard columns it divides is c(y). ---")
    log(f"    share of pairs with c(y) != c(y+1)                   = {share_diff:.6f}")
    log(f"    derived cross-check 1 - P[c(y)=0 & c(y+1)=0]         = {1 - both0:.6f}")
    log(f"    mean (1+c(y))/(1+c(y+1))                             = "
        f"{float(np.mean((1.0 + prev) / (1.0 + truth1))):.6f}")

    # ---------------- V2: r >= 6 is impossible
    imp = Q["imposs"].to_numpy() | Q["imposs_1"].to_numpy()
    imp1 = Q["imposs_1"].to_numpy()
    log("\n--- V2: rows whose recovery ratio r >= 6, which the C cannot produce ---")
    log(f"    pairs with r>=6 at either year : {int(imp.sum())}  ({imp.mean()*100:.4f} %)")
    log(f"    pairs with r>=6 at year y+1    : {int(imp1.sum())}  ({imp1.mean()*100:.4f} %)")
    log(f"    max recovered c(y+1)           : {int(truth1.max())}   (the C caps at 5)")
    n5 = truth1 >= 5
    log(f"    truth certain-death set c(y+1)>=5 : {int(n5.sum())}  (finding: 113758)")
    log(f"       of which r>=6 garbage          : {int((n5 & imp1).sum())}"
        f"  ({float((n5 & imp1).sum()) / max(int(n5.sum()), 1) * 100:.3f} % of the set)")

    # ---------------- the two hazard rebuilds
    mn_y, mw_y = Q["mort_npp"].to_numpy(), Q["mort_water"].to_numpy()
    mage_y, mtmp_y = Q["mort_age"].to_numpy(), Q["mort_temp"].to_numpy()
    mn_1, mw_1 = Q["mort_npp_1"].to_numpy(), Q["mort_water_1"].to_numpy()
    mage_1, mtmp_1 = Q["mort_age_1"].to_numpy(), Q["mort_temp_1"].to_numpy()
    capw_y = mw_y >= 1.0 - 1e-12
    capw_1 = mw_1 >= 1.0 - 1e-12
    log(f"\n    mort_water at its cap: year y {int(capw_y.sum())} rows, "
        f"year y+1 {int(capw_1.sum())} rows")

    def haz_buggy(cc):
        f = (1.0 + cc) / (1.0 + truth1)
        mwx = np.where(capw_y, 1.0, np.minimum(1.0, mw_y * f))
        h = np.minimum(1.0, mn_y * f) + mage_y + mwx + mtmp_y
        return np.where(cc >= 5, 1.0, np.minimum(1.0, h))

    def haz_corr(cc):
        f = (1.0 + cc) / (1.0 + truth1)
        mwx = np.where(capw_1, 1.0, np.minimum(1.0, mw_1 * f))
        h = np.minimum(1.0, mn_1 * f) + mage_1 + mwx + mtmp_1
        return np.where(cc >= 5, 1.0, np.minimum(1.0, h))

    hb_t, hc_t = haz_buggy(truth1.astype(float)), haz_corr(truth1.astype(float))
    log(f"    truth hazard mass, finding's rebuild (year-y columns) = {hb_t.sum():.1f}"
        f"   (finding printed 579672.3)")
    log(f"    truth hazard mass, corrected  (year-(y+1) columns)    = {hc_t.sum():.1f}")
    log(f"    hazard mass carried by the r>=6 rows (corrected)      = "
        f"{hc_t[imp1].sum():.1f}  ({hc_t[imp1].sum()/hc_t.sum()*100:.3f} %)")
    return dict(prev=prev, truth1=truth1, lab=lab, imp1=imp1,
                haz_buggy=haz_buggy, haz_corr=haz_corr, hb_t=hb_t, hc_t=hc_t)


def chains(Q: pl.DataFrame):
    """Chain / lead bookkeeping, identical in construction to the finding's."""
    Q = Q.with_row_index("_rid")
    S = Q.sort([*KEY, "Year"])
    perm = S["_rid"].to_numpy().astype(np.int64)
    yr = S["Year"].to_numpy()
    kc = [S[c].to_numpy() for c in KEY]
    same = np.ones(yr.size, dtype=bool)
    same[1:] = np.logical_and.reduce([a[1:] == a[:-1] for a in kc])
    newchain = np.ones(yr.size, dtype=bool)
    newchain[1:] = (~same[1:]) | (yr[1:] != yr[:-1] + 1)
    ch = np.cumsum(newchain) - 1
    first = np.where(newchain)[0]
    lead = np.arange(yr.size) - first[ch] + 1
    return S, perm, ch, first, lead


def rollout_table(name, pred, ch, first, prevS, truth1S, lead, hz_b, hz_c,
                  hb_tS, hc_tS):
    cinit = np.zeros(ch.size, dtype=np.int64)
    cinit[first] = prevS[first]
    cp = H.runlength_init(ch, pred.astype(np.int8), cinit)
    hb, hc = hz_b(cp.astype(float)), hz_c(cp.astype(float))
    rows = []
    for lo, hi in LEADS:
        m = (lead >= lo) & (lead <= hi)
        if m.sum() < 200:
            continue
        n5t, n5p = int(np.sum(truth1S[m] >= 5)), int(np.sum(cp[m] >= 5))
        rows.append(dict(
            arm=name, lead=f"{lo}" if lo == hi else f"{lo}-{hi}", n=int(m.sum()),
            exact=float(np.mean(cp[m] == truth1S[m])),
            null0_exact=float(np.mean(truth1S[m] == 0)),
            n5_true=n5t, n5_prop=n5p,
            ratio_c5=(n5p / n5t) if n5t else float("nan"),
            haz_ratio_asfound=float(hb[m].sum() / hb_tS[m].sum()),
            haz_ratio_corrected=float(hc[m].sum() / hc_tS[m].sum()),
        ))
    return rows, cp


def stage_sens(Q: pl.DataFrame, climcols, ctx):
    import lightgbm as lgb

    log("\n" + "=" * 78)
    log("V3 + V4 — is M3 an oracle, and are the folds leaking geography?")
    log("=" * 78)
    lab = ctx["lab"]
    Q = Q.with_columns(
        _d_agb=pl.col("agb_1") - pl.col("agb"), _d_vegc=pl.col("vegc_1") - pl.col("vegc"),
        _d_H=pl.col("Height_1") - pl.col("Height"), _d_LAI=pl.col("LAI_1") - pl.col("LAI"),
        _d_npp=pl.col("npp_1") - pl.col("npp"),
    )
    f_y = [*[c for c in STEMCOLS if c not in ("mort_npp", "mort_water")],
           "n_stems", "agb_sum", "npp_sum", "lai_stand", "h_max", "h_mean",
           "age_mean", "fpc", "Wooddens_median", "Type", *climcols]
    f_c1 = [f"{c}_1" for c in climcols]
    f_s1 = [f"{c}_1" for c in NXT_STEM]
    f_d = ["_d_agb", "_d_vegc", "_d_H", "_d_LAI", "_d_npp"]
    feats_m3 = f_y + f_c1 + f_s1 + f_d
    feats_m2 = f_y + f_c1

    # ---- fold schemes
    cells = np.sort(Q["Cell"].unique().to_numpy())
    rank = {int(c): i for i, c in enumerate(cells)}
    cr = np.array([rank[int(c)] for c in Q["Cell"].to_numpy()])
    fold_int = ((Q["Cell"].to_numpy() // 100) % 5).astype(np.int64)   # the finding's
    blk = int(np.ceil(cells.size / 5))
    fold_blk = np.minimum(cr // blk, 4).astype(np.int64)
    log(f"\n  cells={cells.size}  interleaved folds: "
        f"{np.bincount(fold_int).tolist()}  blocked folds: {np.bincount(fold_blk).tolist()}")

    ncpu = int(os.environ.get("SLURM_CPUS_PER_TASK", "16"))

    def fit_oof(X, folds, tag):
        pr = np.zeros(lab.size)
        for k in range(5):
            sub = np.where(folds != k)[0]
            if sub.size > 4_000_000:
                sub = sub[:: max(1, sub.size // 4_000_000)]
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.08, num_leaves=127,
                                   min_child_samples=200, n_jobs=ncpu, verbose=-1)
            m.fit(X[sub], lab[sub])
            pr[folds == k] = m.predict_proba(X[folds == k])[:, 1]
        b = H.binstats(lab, pr)
        log(H.fmt_bs(tag, b))
        return pr, b

    S, perm, ch, first, lead = chains(Q)
    prevS, truth1S = ctx["prev"][perm], ctx["truth1"][perm]
    hb_tS, hc_tS = ctx["hb_t"][perm], ctx["hc_t"][perm]

    # rebuild the hazard closures directly in sorted order (cheaper, exact)
    def mk_haz(cols, cap):
        mn, mage, mw, mtmp = cols

        def f_(cc):
            f = (1.0 + cc) / (1.0 + truth1S)
            mwx = np.where(cap, 1.0, np.minimum(1.0, mw * f))
            h = np.minimum(1.0, mn * f) + mage + mwx + mtmp
            return np.where(cc >= 5, 1.0, np.minimum(1.0, h))
        return f_

    hzb = mk_haz([S["mort_npp"].to_numpy(), S["mort_age"].to_numpy(),
                  S["mort_water"].to_numpy(), S["mort_temp"].to_numpy()],
                 S["mort_water"].to_numpy() >= 1.0 - 1e-12)
    hzc = mk_haz([S["mort_npp_1"].to_numpy(), S["mort_age_1"].to_numpy(),
                  S["mort_water_1"].to_numpy(), S["mort_temp_1"].to_numpy()],
                 S["mort_water_1"].to_numpy() >= 1.0 - 1e-12)
    log(f"  chains={first.size}  max lead={int(lead.max())}  rows={lead.size}")

    allrows = []
    onestep = []

    # ---- baseline arms with NO model, so the rollout table is comparable
    d_agb = (S["agb_1"] - S["agb"]).to_numpy()
    for nm, pr in (("N-A  c==0 forever", np.zeros(lead.size)),
                   ("N-C  perfect agb (ORACLE)", (d_agb < 0).astype(float))):
        rws, _ = rollout_table(nm, pr >= 0.5, ch, first, prevS, truth1S, lead,
                               hzb, hzc, hb_tS, hc_tS)
        allrows += rws
        onestep.append(dict(arm=nm, sigma=np.nan, folds="n/a",
                            **H.binstats(lab[perm], pr)))

    # ---- V3: M3 under increasing error in the year-(y+1) state
    Xm3 = Q.select(feats_m3).to_numpy().astype(np.float32)
    idx = {c: i for i, c in enumerate(feats_m3)}
    pert = [f"{c}_1" for c in NXT_STEM if c != "Age"]
    rng = np.random.default_rng(20260819)
    for sigma in (0.0, 0.05, 0.10, 0.20):
        X = Xm3 if sigma == 0.0 else Xm3.copy()
        if sigma > 0.0:
            for c in pert:
                j = idx[c]
                X[:, j] *= (1.0 + sigma * rng.standard_normal(X.shape[0])).astype(np.float32)
            for a, b in (("_d_agb", "agb"), ("_d_vegc", "vegc"), ("_d_H", "Height"),
                         ("_d_LAI", "LAI"), ("_d_npp", "npp")):
                X[:, idx[a]] = X[:, idx[f"{b}_1"]] - X[:, idx[b]]
        tag = f"M3 sigma={sigma:.2f} (interleaved folds)"
        pr, b = fit_oof(X, fold_int, tag)
        onestep.append(dict(arm=tag, sigma=sigma, folds="interleaved", **b))
        rws, _ = rollout_table(tag, (pr[perm] >= 0.5), ch, first, prevS, truth1S,
                               lead, hzb, hzc, hb_tS, hc_tS)
        allrows += rws
        if sigma > 0.0:
            del X

    # ---- V3b: ablation, drop npp at both years
    ab = [c for c in feats_m3 if c not in ("npp", "npp_1", "_d_npp", "npp_sum",
                                           "npp_sum_1")]
    pr, b = fit_oof(Q.select(ab).to_numpy().astype(np.float32), fold_int,
                    "M3 minus npp (both years)")
    onestep.append(dict(arm="M3 minus npp (both years)", sigma=0.0,
                        folds="interleaved", **b))
    allrows += rollout_table("M3 minus npp (both years)", (pr[perm] >= 0.5), ch, first,
                             prevS, truth1S, lead, hzb, hzc, hb_tS, hc_tS)[0]

    # ---- V4: the address-only null and the blocked folds
    Xaddr = Q.select(["Cell", "Year"]).to_numpy().astype(np.float32)
    for fname, folds in (("interleaved", fold_int), ("blocked", fold_blk)):
        _, b = fit_oof(Xaddr, folds, f"ADDR (Cell,Year only) {fname} folds")
        onestep.append(dict(arm="ADDR (Cell,Year only)", sigma=np.nan, folds=fname, **b))
    Xm2 = Q.select(feats_m2).to_numpy().astype(np.float32)
    for fname, folds in (("interleaved", fold_int), ("blocked", fold_blk)):
        _, b = fit_oof(Xm2, folds, f"M2 {fname} folds")
        onestep.append(dict(arm="M2", sigma=np.nan, folds=fname, **b))
    del Xm2
    pr, b = fit_oof(Xm3, fold_blk, "M3 sigma=0.00 blocked folds")
    onestep.append(dict(arm="M3 sigma=0.00", sigma=0.0, folds="blocked", **b))
    allrows += rollout_table("M3 sigma=0.00 (blocked folds)", (pr[perm] >= 0.5), ch,
                            first, prevS, truth1S, lead, hzb, hzc, hb_tS, hc_tS)[0]

    R = pl.DataFrame(allrows)
    with pl.Config(tbl_rows=400, tbl_width_chars=260, tbl_cols=20):
        log("\n" + str(R))
    R.write_csv(os.path.join(OUT, "verify_b1_rollout.csv"))
    OS = pl.DataFrame(onestep)
    with pl.Config(tbl_rows=60, tbl_width_chars=240, tbl_cols=20):
        log("\n" + str(OS))
    OS.write_csv(os.path.join(OUT, "verify_b1_onestep.csv"))
    log(f"\nwrote {OUT}/verify_b1_rollout.csv and verify_b1_onestep.csv")


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "both"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    log(PREREG)
    log(f"stage={stage} limit_cells={limit} polars={pl.__version__} numpy={np.__version__}")
    t0 = time.time()
    Q, climcols = build_pairs(limit)
    ctx = stage_haz(Q)
    if stage in ("sens", "both"):
        stage_sens(Q, climcols, ctx)
    log(f"\nDONE in {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
