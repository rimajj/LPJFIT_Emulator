"""explore_verify_b2.py — line X, ADVERSARIAL VERIFICATION of campaign item B2.

Read-only against every artifact of scripts/explore_perstem_ladder.py.  Writes only to
/p/tmp/jamirp/X_explore/vb2_*.

WHAT I AM TRYING TO BREAK
  B2 reports (a) a per-stem death-ranking AUC of 0.742 and a per-stem growth R^2 of 0.887 as
  evidence the corpus is rich in learnable signal; (b) that the climate block adds +0.0030 AUC /
  +0.0033 R^2 once the stem and its patch are known, below a pre-registered 0.005 threshold; and
  (c) that a historic-fitted operator carries 57 % of the amplitude and 75-81 % of the achievable
  spatial pattern of the warming response in death rate, while ADDING climate RAISES the amplitude
  and LOWERS the correlation.

PRE-REGISTRATION OF THIS VERIFICATION (written before any result was computed)
  V1  INTEGRITY.  No inf / no NaN in any feature column used by any arm; the reported row count,
      patch-year count and cell count reproduce.  FALSIFIER: any inf, or a count that misses.
  V2  LABEL / HAZARD ARITHMETIC.  Reproduce deaths, sum(mort), the 23.5 % excess, and test the two
      claims the report makes about it that NO log line contains:
        (i) `mort >= 1` implies `isdead == 1` at rate exactly 1.000000, on 463 301 rows;
        (ii) E[isdead] = 0.042154 against E[mort] = 0.031739.
      MUST RETURN for (i): if the claim is right, rate == 1.0 and the row count is the number of
      mort>=1 rows -- which from the ladder log's frac(mort>=1)=0.007516 must be ~82 000, NOT
      463 301.  A count that does not match is a mis-citation.
      ALSO the documented CLAUDE.md trap: `mort_*` is uninitialised garbage in the first year of a
      restarted run.  Both legs here ARE restarted runs (historic from restart_1999, ssp370 from
      restart_2019), so I recompute the excess with years 2000 and 2020 dropped.  MUST RETURN: if
      the trap does not bite, the excess fraction is unchanged to ~1e-3.
  V3  THE PERSISTENCE NULL FOR T2 -- THE NULL THE LADDER DOES NOT CONTAIN.  The campaign brief
      requires a persistence null for any one-step number, and ADR 0310 killed a headline exactly
      here (96 % of a one-step count skill was persistence).  T2 = agb(y+1) - agb(y); the
      persistence null is "next year's increment equals THIS year's increment", i.e. the single
      column m_dagb_prev, which the ladder only ever introduces at rung n6 bundled with three other
      columns.  I score, on the SAME 2 500 000-row subsample, the SAME hash5 folds and the SAME
      learner settings:
        p0_raw   prediction = m_dagb_prev verbatim, NO FIT AT ALL
        p1       GBM on [m_dagb_prev]
        p2       GBM on [m_dagb_prev, m_npp_prev]
        p3       GBM on [m_dagb_prev, m_npp_prev, Age, Height]
      MUST RETURN: if T2's R^2 of 0.887 is a real learning result rather than persistence, then
      p1 must fall well BELOW n1's 0.73732, and p3 well below n6's 0.88709.
      FALSIFIER (mine): I will conclude B2's T2 SIGNAL HEADLINE IS A PERSISTENCE NULL RESTATED if
      p1 >= 0.70 (i.e. one lagged column alone reaches ~95 % of n1's R^2) or p3 >= 0.85 (i.e. four
      trivial columns reach ~96 % of the full ladder).  I will conclude the headline SURVIVES if
      p3 <= 0.80.
  V4  T1 memory-only arm (B6 alone), the same question on the death target.
  V5  FORCING-LEG DISCONTINUITY.  The two legs come from DIFFERENT data sources -- historic
      GSWP3-W5E5 (`temperature_test.clm`, v3 float32) and ssp370 MPI-ESM1-2-HR (v2 int16 scalar
      0.1).  If any climate column steps at 2019->2020, the "climate" block carries a LEG
      INDICATOR, and a leg indicator would raise a response AMPLITUDE while degrading its spatial
      PATTERN -- which is EXACTLY the signature B2 reports as its sharpest negative.  Test: a GBM
      given ONLY the climate block, cells held out by hash5 fold, asked to classify leg on the
      overlapping-decade window (historic 2010-2019 vs ssp370 2020-2029).
      MUST RETURN: if there is no leg artefact, AUC ~ 0.5-0.7 (the two decades genuinely differ in
      climate, so it cannot be 0.5).  FALSIFIER: AUC >= 0.95 means the block is a leg flag and the
      n5 response arm's amplitude gain is an artefact, not climate information.
      Also reported: the raw per-variable step, historic 2010-2019 mean vs ssp370 2020-2029 mean,
      against the within-historic decade-to-decade step 2000-2009 -> 2010-2019 as the scale.
  V6  IS THE "CLIMATE DEGRADES THE SPATIAL PATTERN" RESULT SIGNIFICANT?  B2 reports r 0.7456 (n4)
      vs 0.6573 (n5) on 497 cells with NO uncertainty on either.  Cells are spatially correlated,
      so I bootstrap the paired difference r(n4) - r(n5) two ways: over CELLS, and over the 15 deg
      SPATIAL BLOCKS of the committed fold map (the honest unit).  MUST RETURN: the difference is
      significant only if the block bootstrap's 95 % interval excludes 0.
  V7  ORDER-DEPENDENCE OF THE "1.2 % OF SKILL IS CLIMATE" DECOMPOSITION.  A nested ladder prices
      the LAST block added; climate is added second-to-last by construction.  I report the same
      block's fully-marginal price (climonly - n0) and its price without the patch block
      (own_clim - n3) beside the fully-conditional one (n5 - n4), as the range.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

OUT = "/p/tmp/jamirp/X_explore"
FEAT = f"{OUT}/b2_stem_features.parquet"
CLIM = f"{OUT}/b2_cellyear_clim.parquet"
LADDER = f"{OUT}/b2_ladder.csv"
RESPCELLS = f"{OUT}/b2_response_cells.parquet"
TBL = "/p/tmp/jamirp/emulator_global/tables"
BLOCKMAP = f"{TBL}/foldmaps/foldmap_block15.0_buf5.0_s0.txt"

RNG = 20260819          # the same seed the probe used, so the subsample is IDENTICAL
LADDER_N = 2_500_000    # the same subsample size
NTHREAD = int(os.environ.get("SLURM_CPUS_PER_TASK", os.environ.get("NCPUS", "16")))

_T0 = time.time()


def _say(m: str) -> None:
    print(f"[{time.time() - _T0:7.1f}s] {m}", flush=True)


LGB = dict(objective=None, n_estimators=250, learning_rate=0.06, num_leaves=63,
           min_child_samples=100, max_bin=63, subsample=0.8, subsample_freq=1,
           colsample_bytree=0.8, reg_lambda=1.0, n_jobs=NTHREAD, verbose=-1,
           random_state=RNG, force_col_wise=True)

CLIM_ANN = ["tas_ann", "tas_cold", "tas_warm", "tas_seas", "gdd5", "frostdays",
            "pr_ann", "rsds_ann", "huss_ann"]
CLIM_ROLL = ["tas_ann_m5", "tas_ann_m10", "pr_ann_m5", "pr_ann_m10", "gdd5_m5", "gdd5_m10",
             "tas_cold_m20", "tas_warm_m20", "trange_m20"]
CLIM_ANOM = ["d_tas_ann", "d_pr_ann", "d_gdd5", "d_tas_cold"]
ENV_W20 = ["eco_diag_gdd_5", "tas_cold_month", "eco_diag_vpd_mean", "eco_diag_pet_mean",
           "eco_diag_p_pet_ratio", "pr_cv_monthly", "prec_mean", "humid_mean"]
B5 = CLIM_ANN + CLIM_ROLL + CLIM_ANOM + [f"w20_{c}" for c in ENV_W20]
B6 = ["m_dagb_prev", "m_npp_prev", "m_neg_run", "m_nneg3"]


def _fit_predict(xtr, ytr, xte, task):
    import lightgbm as lgb
    par = dict(LGB)
    par["objective"] = "binary" if task == "t1" else "regression"
    m = (lgb.LGBMClassifier(**par) if task == "t1" else lgb.LGBMRegressor(**par))
    m.fit(xtr, ytr)
    return (m.predict_proba(xte)[:, 1] if task == "t1" else m.predict(xte))


def _r2(y, p):
    return 1.0 - float(np.sum((y - p) ** 2)) / float(np.sum((y - y.mean()) ** 2))


def _auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p))


# =================================================================================================
def v1_v2_integrity() -> None:
    _say("=== V1/V2 integrity + label/hazard arithmetic ===")
    lf = pl.scan_parquet(FEAT)
    cols = ["leg", "Year", "Cell", "Patch", "Type", "ID", "mort", "isdead", "agb",
            "d_agb", "pairable", "survived", "m_dagb_prev", "npp", "Height", "Age"]
    d = lf.select(cols).collect()
    _say(f"   rows={d.height} (report: 10 919 647)  cells={d['Cell'].n_unique()} (report: 601)")
    py = d.select(["leg", "Cell", "Patch", "Year"]).n_unique()
    _say(f"   distinct patch-years={py} (report: 1 276 977)")

    # inf / nan audit over EVERY numeric feature column actually used by an arm
    sch = lf.collect_schema()
    numcols = [c for c, t in zip(sch.names(), sch.dtypes(), strict=True)
               if t in (pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Int8, pl.UInt32)]
    bad = []
    for c in numcols:
        s = lf.select(pl.col(c)).collect().to_series()
        if s.dtype in (pl.Float64, pl.Float32):
            ninf = int(s.is_infinite().sum())
            nnan = int(s.is_nan().sum())
        else:
            ninf = nnan = 0
        nnul = int(s.null_count())
        if ninf or nnan or nnul:
            bad.append((c, ninf, nnan, nnul))
    _say(f"   columns with inf/nan/null ({len(bad)} of {len(numcols)}):")
    for c, i, n, u in bad:
        _say(f"      {c:26s} inf={i:9d} nan={n:9d} null={u:9d}")

    tot_d = int(d["isdead"].sum())
    tot_m = float(d["mort"].sum())
    _say(f"   deaths={tot_d} sum(mort)={tot_m:.1f} excess={tot_d - tot_m:.1f} "
         f"({(tot_d - tot_m) / tot_d:.4f})")
    _say(f"   E[isdead]={tot_d / d.height:.6f}  E[mort]={tot_m / d.height:.6f}   "
         f"(report's N3 row: 0.042154 vs 0.031739)")
    for lg in ("historic", "ssp370"):
        s = d.filter(pl.col("leg") == lg)
        _say(f"   leg={lg:9s} n={s.height:9d} deaths={int(s['isdead'].sum()):8d} "
             f"E[isdead]={float(s['isdead'].mean()):.6f} E[mort]={float(s['mort'].mean()):.6f}")

    # claim (i): mort >= 1 => isdead == 1
    c1 = d.filter(pl.col("mort") >= 1.0)
    _say(f"   CLAIM(i) rows with mort>=1: {c1.height}  death rate among them "
         f"{float(c1['isdead'].mean()):.6f}   (report cites '463 301 checked')")
    _say(f"   certain deaths = {int(c1['isdead'].sum())} = "
         f"{int(c1['isdead'].sum()) / tot_d:.6f} of all deaths (report: 17.6 %)")

    # the restarted-run first-year mort trap
    yr = d.group_by(["leg", "Year"]).agg([
        pl.len().alias("n"), pl.col("isdead").mean().alias("ed"),
        pl.col("mort").mean().alias("em"), (pl.col("mort") >= 1).mean().alias("f1")]).sort(
        ["leg", "Year"])
    _say("   per-year E[isdead] / E[mort] (first 4 + last of each leg):")
    for lg in ("historic", "ssp370"):
        s = yr.filter(pl.col("leg") == lg)
        for r in list(s.iter_rows(named=True))[:4] + list(s.iter_rows(named=True))[-1:]:
            _say(f"      {lg:9s} {r['Year']} n={r['n']:8d} E[isdead]={r['ed']:.6f} "
                 f"E[mort]={r['em']:.6f} frac(mort>=1)={r['f1']:.6f}")
    dd = d.filter(~(((pl.col("leg") == "historic") & (pl.col("Year") == 2000))
                    | ((pl.col("leg") == "ssp370") & (pl.col("Year") == 2020))))
    td, tm = int(dd["isdead"].sum()), float(dd["mort"].sum())
    _say(f"   excess with the two restart-first-years DROPPED: {(td - tm) / td:.4f} "
         f"(with them: {(tot_d - tot_m) / tot_d:.4f})")

    # the T2 target
    t2 = d.filter(pl.col("pairable") & (pl.col("survived") == 1) & pl.col("d_agb").is_not_null())
    y = t2["d_agb"].to_numpy()
    _say(f"   T2 labels={t2.height} (report: 10 234 575) mean={y.mean():.4f} sd={y.std():.4f} "
         f"min={y.min():.4f} max={y.max():.4f} frac<=0={float((y <= 0).mean()):.4f}")
    mp = t2["m_dagb_prev"].to_numpy()
    ok = ~np.isnan(mp)
    _say(f"   m_dagb_prev available on {ok.mean():.4f} of T2 rows; "
         f"corr(d_agb, m_dagb_prev) on those = {np.corrcoef(y[ok], mp[ok])[0, 1]:+.4f}")


# =================================================================================================
def v3_v4_persistence() -> None:
    """The persistence null the ladder does not contain, on the IDENTICAL subsample/folds."""
    _say("=== V3/V4 persistence nulls ===")
    lf = pl.scan_parquet(FEAT)

    # ---- T2 ----------------------------------------------------------------------------------
    need = ["d_agb", "m_dagb_prev", "m_npp_prev", "Age", "Height", "fold_hash5", "buf_hash5",
            "m_neg_run", "m_nneg3"]
    df = (lf.filter(pl.col("pairable") & (pl.col("survived") == 1)
                    & pl.col("d_agb").is_not_null())
          .select(need).collect())
    if df.height > LADDER_N:                     # identical sample: same seed, shuffle=False
        df = df.sample(n=LADDER_N, seed=RNG, shuffle=False)
    df = df.filter(pl.col("fold_hash5").is_not_null())
    _say(f"   T2 subsample {df.height} rows (probe used 2 500 000)")
    y = df["d_agb"].to_numpy().astype(np.float64)
    fold = df["fold_hash5"].to_numpy()
    buf = df["buf_hash5"].to_numpy()
    arms = {
        "P0raw_mdagb_prev_NOFIT": ["m_dagb_prev"],
        "P1_gbm_mdagb_prev": ["m_dagb_prev"],
        "P2_gbm_mdagb_npp_prev": ["m_dagb_prev", "m_npp_prev"],
        "P3_gbm_mem4": B6,
        "P4_gbm_mem4_age_height": B6 + ["Age", "Height"],
    }
    rows = []
    for name, cols in arms.items():
        x = df.select(cols).to_numpy().astype(np.float32)
        per = []
        for k in range(5):
            te = fold == k
            tr = (fold != k) & (((buf >> k) & 1) == 0)
            if name.startswith("P0raw"):
                p = np.nan_to_num(x[te, 0].astype(np.float64))   # NaN -> 0 = "no growth known"
            else:
                p = _fit_predict(x[tr], y[tr], x[te], "t2")
            per.append(_r2(y[te], p))
        v = np.array(per)
        rows.append(dict(task="t2", arm=name, mean=float(v.mean()),
                         se=float(v.std(ddof=1) / np.sqrt(v.size))))
        _say(f"   t2 {name:26s} R2={v.mean():.5f} +/- {v.std(ddof=1) / np.sqrt(5):.5f}  "
             + " ".join(f"{q:.4f}" for q in v))

    # ---- T1 ----------------------------------------------------------------------------------
    need1 = ["isdead", "fold_hash5", "buf_hash5", "Age", "Height"] + B6
    d1 = lf.select(need1).collect()
    if d1.height > LADDER_N:
        d1 = d1.sample(n=LADDER_N, seed=RNG, shuffle=False)
    d1 = d1.filter(pl.col("fold_hash5").is_not_null())
    _say(f"   T1 subsample {d1.height} rows")
    y1 = d1["isdead"].to_numpy().astype(np.float64)
    f1, b1 = d1["fold_hash5"].to_numpy(), d1["buf_hash5"].to_numpy()
    for name, cols in {"M1_gbm_mem4_only": B6,
                       "M2_gbm_mem4_age_height": B6 + ["Age", "Height"]}.items():
        x = d1.select(cols).to_numpy().astype(np.float32)
        per = []
        for k in range(5):
            te = f1 == k
            tr = (f1 != k) & (((b1 >> k) & 1) == 0)
            per.append(_auc(y1[te], _fit_predict(x[tr], y1[tr], x[te], "t1")))
        v = np.array(per)
        rows.append(dict(task="t1", arm=name, mean=float(v.mean()),
                         se=float(v.std(ddof=1) / np.sqrt(v.size))))
        _say(f"   t1 {name:26s} AUC={v.mean():.5f} +/- {v.std(ddof=1) / np.sqrt(5):.5f}  "
             + " ".join(f"{q:.4f}" for q in v))
    pl.DataFrame(rows).write_csv(f"{OUT}/vb2_persistence.csv")
    _say(f"   wrote {OUT}/vb2_persistence.csv")


# =================================================================================================
def v5_legstep() -> None:
    _say("=== V5 forcing-leg discontinuity / leg-indicator test ===")
    cl = pl.read_parquet(CLIM)
    # the raw step, and the within-historic decade step as the scale
    win = {"h0009": (2000, 2009), "h1019": (2010, 2019), "s2029": (2020, 2029)}
    mm = {}
    for lab, (a, b) in win.items():
        mm[lab] = (cl.filter((pl.col("Year") >= a) & (pl.col("Year") <= b))
                   .select([pl.col(c).cast(pl.Float64).mean().alias(c) for c in CLIM_ANN]))
    _say("   variable            hist2000s   hist2010s   ssp2020s | within-hist step | leg step")
    for c in CLIM_ANN:
        a, b, s = (float(mm["h0009"][c][0]), float(mm["h1019"][c][0]), float(mm["s2029"][c][0]))
        _say(f"   {c:18s} {a:11.4f} {b:11.4f} {s:11.4f} | {b - a:+15.4f} | {s - b:+9.4f}")

    # the leg classifier: climate block ONLY, cells held out
    lf = pl.scan_parquet(FEAT)
    sel = ((pl.col("leg") == "historic") & (pl.col("Year") >= 2010) & (pl.col("Year") <= 2019)) | \
          ((pl.col("leg") == "ssp370") & (pl.col("Year") >= 2020) & (pl.col("Year") <= 2029))
    d = (lf.filter(sel).select(["leg", "Cell", "fold_hash5", "buf_hash5"] + B5).collect())
    d = d.filter(pl.col("fold_hash5").is_not_null())
    if d.height > 1_500_000:
        d = d.sample(n=1_500_000, seed=RNG, shuffle=False)
    y = (d["leg"] == "ssp370").to_numpy().astype(np.float64)
    x = d.select(B5).to_numpy().astype(np.float32)
    f, b = d["fold_hash5"].to_numpy(), d["buf_hash5"].to_numpy()
    per = []
    for k in range(5):
        te = f == k
        tr = (f != k) & (((b >> k) & 1) == 0)
        per.append(_auc(y[te], _fit_predict(x[tr], y[tr], x[te], "t1")))
    v = np.array(per)
    _say(f"   LEG CLASSIFIER from the climate block alone (2010s hist vs 2020s ssp370, cells "
         f"held out): AUC={v.mean():.5f} +/- {v.std(ddof=1) / np.sqrt(5):.5f}  "
         + " ".join(f"{q:.4f}" for q in v))
    _say(f"   n={d.height} rows, base rate ssp370={y.mean():.4f}")
    # and the same with the ANOMALY + w20 columns removed, to see which part carries it
    sub = [c for c in B5 if not c.startswith("d_") and not c.startswith("w20_")]
    x2 = d.select(sub).to_numpy().astype(np.float32)
    per2 = []
    for k in range(5):
        te = f == k
        tr = (f != k) & (((b >> k) & 1) == 0)
        per2.append(_auc(y[te], _fit_predict(x2[tr], y[tr], x2[te], "t1")))
    _say(f"   same, RAW annual+rolling climate only ({len(sub)} cols): "
         f"AUC={np.mean(per2):.5f}")

    # ---- THE CONTROL FOR MY OWN STATISTIC (trap 2 applied to me) ---------------------------
    # An AUC of ~0.84 on adjacent decades is only evidence of a SPLICE artefact if the SAME
    # classifier, on two decades from the SAME source with a similar temperature step, scores
    # materially LOWER.  MUST RETURN: if the within-historic control also scores ~0.84, then 0.84
    # is just "decades are distinguishable" and there is NO splice signature -- my V5 claim dies.
    sel2 = ((pl.col("leg") == "historic") & (pl.col("Year") >= 2000) & (pl.col("Year") <= 2009)) | \
           ((pl.col("leg") == "historic") & (pl.col("Year") >= 2010) & (pl.col("Year") <= 2019))
    d2 = (pl.scan_parquet(FEAT).filter(sel2)
          .select(["Year", "Cell", "fold_hash5", "buf_hash5"] + B5).collect())
    d2 = d2.filter(pl.col("fold_hash5").is_not_null())
    y2 = (d2["Year"] >= 2010).to_numpy().astype(np.float64)
    f2, b2 = d2["fold_hash5"].to_numpy(), d2["buf_hash5"].to_numpy()
    for lab, cc in (("ALL climate cols", B5), ("RAW annual+rolling only", sub)):
        xx = d2.select(cc).to_numpy().astype(np.float32)
        pp = []
        for k in range(5):
            te = f2 == k
            tr = (f2 != k) & (((b2 >> k) & 1) == 0)
            pp.append(_auc(y2[te], _fit_predict(xx[tr], y2[tr], xx[te], "t1")))
        _say(f"   CONTROL within-historic 2000s vs 2010s, {lab:24s}: AUC={np.mean(pp):.5f} "
             f"(n={d2.height}, base={y2.mean():.4f})")


# =================================================================================================
def v6_respsig() -> None:
    _say("=== V6 is 'climate degrades the spatial pattern' significant? ===")
    w = pl.read_parquet(RESPCELLS)
    bm = pl.read_csv(BLOCKMAP, separator=" ", comment_prefix="#", has_header=False,
                     new_columns=["Cell", "blkfold", "blkbuf"])
    # a spatial block id: recover it from lat/lon of the cell via the grid used in the feature table
    geo = (pl.scan_parquet(FEAT).select(["Cell", "lat", "lon"]).unique().collect())
    rng = np.random.default_rng(RNG + 11)
    for task in ("t1", "t2"):
        sub = w.filter((pl.col("task") == task) & (pl.col("window") == "ssp_late"))
        a = sub.filter(pl.col("arm") == "n4").join(geo, on="Cell", how="left")
        b = sub.filter(pl.col("arm") == "n5").select(
            ["Cell", "truth_ssp_late", "truth_hist", "pred_ssp_late", "pred_hist"]).rename(
            {"pred_ssp_late": "p5_late", "pred_hist": "p5_hist",
             "truth_ssp_late": "t5_late", "truth_hist": "t5_hist"})
        j = a.join(b, on="Cell", how="inner").join(bm, on="Cell", how="left")
        tx = (j["truth_ssp_late"] - j["truth_hist"]).to_numpy()
        p4 = (j["pred_ssp_late"] - j["pred_hist"]).to_numpy()
        p5 = (j["p5_late"] - j["p5_hist"]).to_numpy()
        # sanity: the truth columns must agree between the two arms
        dt = float(np.max(np.abs(tx - (j["t5_late"] - j["t5_hist"]).to_numpy())))
        r4 = float(np.corrcoef(tx, p4)[0, 1])
        r5 = float(np.corrcoef(tx, p5)[0, 1])
        _say(f"   {task} ncell={tx.size} truth-column agreement max|diff|={dt:.3g} "
             f"r(n4)={r4:+.4f} r(n5)={r5:+.4f} diff={r4 - r5:+.4f}")
        # 15 deg block id from lat/lon (the honest resampling unit; the committed map's fold is a
        # colouring of these blocks, so I rebuild the block itself)
        blk = (np.floor(j["lat"].to_numpy() / 15.0).astype(int) * 100
               + np.floor(j["lon"].to_numpy() / 15.0).astype(int))
        ub = np.unique(blk)
        _say(f"      distinct 15 deg blocks holding these cells: {ub.size}")
        for unit, ids in (("cell", None), ("block15", blk)):
            ds = np.empty(2000)
            for i in range(2000):
                if ids is None:
                    s = rng.integers(0, tx.size, tx.size)
                else:
                    pick = rng.integers(0, ub.size, ub.size)
                    s = np.concatenate([np.where(ids == ub[q])[0] for q in pick])
                if s.size < 5:
                    ds[i] = np.nan
                    continue
                with np.errstate(invalid="ignore"):
                    ds[i] = (np.corrcoef(tx[s], p4[s])[0, 1] - np.corrcoef(tx[s], p5[s])[0, 1])
            lo, hi = np.nanpercentile(ds, [2.5, 97.5])
            _say(f"      bootstrap over {unit:8s}: r(n4)-r(n5) = {np.nanmean(ds):+.4f} "
                 f"95% CI [{lo:+.4f}, {hi:+.4f}]  "
                 f"{'EXCLUDES 0' if lo > 0 or hi < 0 else 'INCLUDES 0'}")


# =================================================================================================
def v7_order() -> None:
    _say("=== V7 order-dependence of the climate share ===")
    L = pl.read_csv(LADDER)
    for task in ("t1", "t2"):
        g = {r["arm"]: r["mean"] for r in
             L.filter((pl.col("task") == task) & (pl.col("scheme") == "hash5")).iter_rows(
                 named=True)}
        span = g["n6"] - g["n0"]
        _say(f"   {task}: span(n6-n0)={span:.5f}")
        _say(f"      climate priced LAST  (n5-n4)          = {g['n5'] - g['n4']:+.5f} "
             f"= {(g['n5'] - g['n4']) / span:6.2%} of span")
        _say(f"      climate priced without patch (own_clim-n3) = {g['own_clim'] - g['n3']:+.5f} "
             f"= {(g['own_clim'] - g['n3']) / span:6.2%}")
        _say(f"      climate priced FIRST (climonly-n0)   = {g['climonly'] - g['n0']:+.5f} "
             f"= {(g['climonly'] - g['n0']) / span:6.2%}")
        _say(f"      patch priced LAST-ish (n4-n3)={g['n4'] - g['n3']:+.5f}  "
             f"addr-n4={g['addr'] - g['n4']:+.5f}")


def main() -> None:
    st = sys.argv[1] if len(sys.argv) > 1 else "all"
    if st in ("all", "cheap"):
        v1_v2_integrity()
        v5_legstep() if st == "all" else None
        v6_respsig()
        v7_order()
    if st == "v5":
        v5_legstep()
    if st in ("all", "ml"):
        v3_v4_persistence()
        if st == "ml":
            v5_legstep()
    _say("### VERIFY DONE")


if __name__ == "__main__":
    main()
