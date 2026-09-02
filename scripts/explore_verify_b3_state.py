#!/usr/bin/env python
"""Line X -- SECOND adversarial verification of item B3 (the direct climatology -> window map).

Read-only.  Writes only under /p/tmp/jamirp/X_explore/ with the prefix ``vb3s_``.

Item B3's headline rests on ONE discriminator: under spatially blocked folds a climate arm beats a
map-COORDINATES-only arm on the per-cell 20-year RESPONSE by +0.162 .. +0.715 R^2.  ADR 0311 records
that its first verifier attacked the *coordinates* null three ways and the margin grew.  This script
attacks a different thing: whether a coordinates null is the RIGHT null for a RESPONSE at all.

It also executes the two attacks item B3's own first verifier PRE-REGISTERED and never ran (its V3
and V4 -- no ``vb3_v3*``/``vb3_v4*`` artifact exists and neither appears in ADR 0311).

Usage (positional only):   scripts/explore_verify_b3_state.py <stage>
    stage = all | gate | state | boot | cf | price
"""

from __future__ import annotations

import hashlib
import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = "/p/tmp/jamirp/X_explore"
DESIGN = os.path.join(SCRATCH, "b3_design_v3.parquet")

PREREG = r"""
===============================================================================================
PRE-REGISTRATION -- second adversarial verification of item B3.  Frozen before any result of THIS
script was read.  Every threshold below carries the value that would make me say the finding under
test survives and the value that would make me say it is refuted.
===============================================================================================

A  THE PRESENT-STATE NULL -- the null item B3 never ran, and the one that decides what its
   headline may be called.
   WHY.  B3's positive claim is "the warming RESPONSE carries learnable signal", and its whole
   evidence is R^2(climate) - R^2(coordinates) on the per-cell change.  A coordinates arm is a
   null for "is this an address proxy?"  It is NOT a null for "is this a warming response?",
   because a change field has a second, forcing-free source of predictability that no coordinate
   arm can express and that every emulator gets for FREE: the cell's own present-day state.  A
   stand with 20 stems can lose 5; a stand with 1 stem cannot.  If the change is a deterministic
   function of today's state, a model reproduces it while knowing nothing whatever about warming
   -- and cannot distinguish one emissions scenario from another, which is exactly B3's own
   deepest finding.
   ALREADY MEASURED BEFORE WRITING THIS (in-sample, 1 slope + 1 intercept, no climate, no folds,
   on B3's own design table): change ~ level_hist gives R^2 0.2219 stems / 0.2714 biomass /
   0.2546 SLA / 0.1007 wood density / 0.0173 rooting depth / 0.0048 drought threshold, against
   B3's blocked climate response R^2 of 0.2740 / 0.3652 / 0.1450 / 0.0967 / 0.0587 / 0.4263.
   So a TWO-PARAMETER forcing-free model already recovers 81 % / 74 % of the two headline targets.
   STATISTIC.  OOS R^2 on the response target, blocked 15deg + 5deg buffer, BOTH colourings, all
   six targets, arms:
     clim        = B3's own arm (both windows' climate + soil)          [reproduction]
     geo         = B3's own null (unit-sphere x,y,z)                    [reproduction]
     state6      = the six present-day reference state values ONLY -- no climate, no coordinates
     state1      = the single present-day value of the SAME target only
     state_clim  = state6 + climate  (does climate add over the state?)
   ⚠ SHARED-NOISE HAZARD, stated before the run because it would make MY attack the artifact:
   the scored target is  resp_ref = mean(fut) - mean(hist),  so it CONTAINS the state feature with
   a minus sign, and the two-seed-mean level carries its own sampling noise.  A state arm can
   therefore "predict" part of the target by cancelling shared noise.  I bound it two ways:
     (i) analytically, from the measured two-seed spread (half-normal: sigma^2 = pi/8 * E|h1-h2|^2
         per replicate, so the level-mean's noise variance is sigma^2/2), reported as
         ``shared_noise_r2_bound``;
     (ii) empirically, with a SEED-SPLIT design in which the feature comes from replicate 2 and
         the target from replicate 1 (y = f1 - h1, features = h2), so the shared noise is exactly
         zero.  Climate is noise-free, so it is scored on the same split target for a like-for-
         like ratio.  The seed-split numbers are the ones I will believe.
   NULLS AND WHAT THEY MUST RETURN, derived before the run:
     * ``clim`` and ``geo`` must reproduce B3's published blocked response R^2 to < 0.005 absolute
       (clim 0.2740/0.3652/0.1450/0.0967/0.0587/0.4263 and geo -0.2541/0.0140/-0.0248/-0.1076/
       -0.0873/-0.0793 at salt 0).  If they do not, my fold rebuild differs from B3's and stage A
       is VOID -- not a refutation.
     * a mean null must return R^2 = 0.000000 (convention check).
     * ``state1`` must return at least (its in-sample linear value - 0.03) on stems and biomass; a
       1-feature tree cannot fall far below the 1-feature line unless the pipeline is broken.
   VERDICT RULE.
     REFUTED AS STATED -- B3's headline may not be called evidence about a warming response -- IF
       state6 >= clim - 0.05 on 4 or more of the 6 targets at BOTH colourings, in the seed-split
       design.
     NARROWED IF state6 recovers >= 50 % of clim's R^2 on stems AND biomass at both colourings
       while staying below clim - 0.05: climate then adds real signal, but the majority of the
       "response skill" is forcing-free state equilibration and the coordinates discriminator
       overstates the climate contribution by that factor.
     SURVIVES UNSCATHED IF state6 recovers < 25 % of clim on stems and biomass.
   I EXPECT, honestly: NARROWED.  The two-parameter in-sample number already recovers 74-81 % on
   the two headline targets, but part of that is the shared noise I am about to bound away, and I
   do not know how much survives the seed split.

B  TILE-LEVEL UNCERTAINTY.  B3 quotes twelve discriminator values and ADR 0311 tabulates them with
   NO uncertainty of any kind; the honest denominator is 161 populated 15deg tiles, not 53 085
   rows, and two colourings are a 2-sample check, not an interval.
   STATISTIC: a block bootstrap over the populated 15deg tiles (1000 resamples, tiles drawn with
   replacement, R^2 recomputed on the resampled cells) for R^2(clim)-R^2(geo) and
   R^2(clim)-R^2(state6), response family, salt 0, all six targets.
   B3's DISCRIMINATOR IS CONFIRMED for a target if the clim-geo margin's 2.5th percentile > 0, and
   REFUTED for that target if the interval contains 0.  Pre-registered expectation: the two
   headline targets clear it easily; rooting depth (+0.162) and wood density (+0.193) are the ones
   I expect may not.

C  THE WORD "SAME" IN THE COUNTERFACTUAL.  B3's headline says the fitted map "still predicted
   76-100 % of the SAME per-cell change" with the warming scaled to zero.  Its statistic is
   mean|pred(0)| / mean|pred(1)| -- a ratio of MAGNITUDES, blind to whether the per-cell field
   moved at all.  A map could return a completely different field of the same average size and
   score 1.0.  This is item B3's own first verifier's pre-registered V4, which was never run: no
   ``vb3_v4`` artifact exists and it appears nowhere in ADR 0311.
   STATISTIC: corr(pred(alpha=0), pred(alpha=1)) and displacement = mean|pred(1)-pred(0)| /
   mean|pred(1)|, clim arm, blocked 15deg+5deg both colourings, all six targets.
   THE WORD "SAME" IS JUSTIFIED IF corr >= 0.9 and displacement <= 0.3.
   IT IS AN OVERSTATEMENT IF corr <= 0.7 or displacement >= 0.5.  Anything between: partial.

D  THE INCUMBENT'S HONEST PRICE (trap 1).  B3 prices the reference model as "its own second run is
   outside a pure 10 % band on 13.7 % of cells for stem count" -- but that is one replicate against
   the MEAN OF ITSELF AND THE OTHER, whose deviation is |s1-s2|/2, i.e. HALF the replicates' real
   disagreement.  This is item B3's own first verifier's pre-registered V3, also never run.
   STATISTIC: fraction of cells with |s1-s2| > 0.10|ref| (replicate vs replicate) beside B3's
   |s1-ref| > 0.10|ref|, per target, 25 patches.  Pure arithmetic, no fitting, no null needed.
   PREDICTED before the run: about 2x B3's number wherever B3's is small.  This CORRECTS rather
   than refutes -- it makes B3's own argument for the max() clause stronger -- but it also means
   every pass fraction in B3 is scored against a band TWICE the reference's own scatter about the
   quantity being scored, which B3 does not disclose.
===============================================================================================
"""

CLIM_COLS = [
    "tas_wmean_degC", "pr_wmean_mm_yr", "rsds_wmean", "huss_wmean",
    "tas_cold_month_clm", "tas_warm_month_clm", "tas_seasonality_clm", "gdd5_clm",
    "frostdays_clm", "eco_diag_gdd_5_wmean", "eco_diag_vpd_mean_wmean",
    "eco_diag_pet_mean_wmean", "eco_diag_p_pet_ratio_wmean", "pr_cv_monthly_wmean",
    "prec_mean_wmean", "humid_mean_wmean",
]
SOIL_COLS = ["soil_code", "soil_depth"]
GEO_COLS = ["geo_x", "geo_y", "geo_z"]
TARGETS = [
    "stems_per_patch", "agb_per_patch", "SLA_median",
    "Wooddens_median", "D95max_median", "minwscal_median",
]
KFOLDS = 5
BLK = [("blk15_buf5_s0", 15.0, 5.0, 0), ("blk15_buf5_s1", 15.0, 5.0, 1)]
CF_ALPHAS = [0.0, 1.0]

# B3's published blocked-fold response R^2 at salt 0 -- the reproduction gate for stage A.
B3_CLIM_RESP_S0 = [0.2740, 0.3652, 0.1450, 0.0967, 0.0587, 0.4263]
B3_GEO_RESP_S0 = [-0.2541, 0.0140, -0.0248, -0.1076, -0.0873, -0.0793]
INSAMPLE_LIN = [0.2219, 0.2714, 0.2546, 0.1007, 0.0173, 0.0048]

LGB_PARAMS = dict(
    n_estimators=400, num_leaves=63, learning_rate=0.05, min_child_samples=20,
    subsample=1.0, colsample_bytree=1.0, reg_lambda=0.0, n_jobs=16, verbose=-1,
    random_state=0,
)


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def log(*a):
    print(*a, flush=True)


def r2(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    st = np.sum((y - y.mean()) ** 2)
    return float(1.0 - np.sum((y - p) ** 2) / st) if st > 0 else float("nan")


def slope0(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    d = float(np.sum(y * y))
    return float(np.sum(y * p) / d) if d > 0 else float("nan")


def corr(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    if y.std() == 0 or p.std() == 0:
        return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def pass_frac(y_ref, spread, pred, rel=0.10):
    tol = np.maximum(rel * np.abs(y_ref), spread)
    return float(np.mean(np.abs(pred - y_ref) <= tol))


def build_folds(lat, lon):
    """Rebuild item B3's fold construction verbatim (block tiles + geodesic buffer)."""
    from sklearn.neighbors import BallTree

    n = len(lat)
    rad = np.deg2rad(np.column_stack([lat, lon]))
    tree = BallTree(rad, metric="haversine")
    out = {}
    for name, bdeg, bufdeg, salt in BLK:
        tl = np.floor((lat + 90.0) / bdeg).astype(int)
        tn = np.floor((lon + 180.0) / bdeg).astype(int)
        ntl = int(np.ceil(360.0 / bdeg))
        tile = tl * ntl + tn
        uniq = np.unique(tile)
        tmap = {int(t): _h(f"tilefold:{salt}:{int(t)}") % KFOLDS for t in uniq}
        fold = np.array([tmap[int(t)] for t in tile])
        trainmask = np.ones((KFOLDS, n), dtype=bool)
        for f in range(KFOLDS):
            te = fold == f
            trainmask[f] = ~te
            if bufdeg > 0 and te.any():
                idx = tree.query_radius(rad[te], r=np.deg2rad(bufdeg))
                nb = np.unique(np.concatenate(idx))
                trainmask[f, nb] = False
        out[name] = dict(fold=fold, trainmask=trainmask, nblocks=len(uniq), tile=tile)
        log(f"[folds] {name:16s} populated_blocks={len(uniq)} "
            f"test={[int((fold == f).sum()) for f in range(KFOLDS)]} "
            f"train={[int(trainmask[f].sum()) for f in range(KFOLDS)]}")
    return out


def fit_oos(X, y, fd, xtest=None):
    """OOS predictions.  ``xtest`` (optional) is an alternative design matrix to PREDICT on."""
    from lightgbm import LGBMRegressor

    pred = np.full(len(y), np.nan)
    for f in range(KFOLDS):
        te = fd["fold"] == f
        tr = fd["trainmask"][f]
        if te.sum() == 0 or tr.sum() < 200:
            continue
        m = LGBMRegressor(**LGB_PARAMS).fit(X[tr], y[tr])
        pred[te] = m.predict((X if xtest is None else xtest)[te])
    return pred


def arm_matrix(df, arm):
    """Response-family feature matrices.  ``state*`` arms are the NEW nulls."""
    both = ([f"{c}__hist" for c in CLIM_COLS] + [f"{c}__fut" for c in CLIM_COLS]
            + [f"{c}__hist" for c in SOIL_COLS])
    if arm == "clim":
        cols = both
    elif arm == "geo":
        cols = GEO_COLS
    elif arm == "state6":
        cols = [f"{t}__hist_ref" for t in TARGETS]
    elif arm == "state6_s2":
        cols = [f"{t}__hist_s2" for t in TARGETS]
    elif arm == "state_clim":
        cols = [f"{t}__hist_ref" for t in TARGETS] + both
    else:
        raise ValueError(arm)
    return df.select(cols).to_numpy().astype(np.float64), cols


# ---------------------------------------------------------------------------------------------
def stage_state(df, folds):
    """Stage A: the present-state null, in both the shared-noise and the seed-split design."""
    rows = []
    for ti, t in enumerate(TARGETS):
        y_mean = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        sp = df[f"{t}__resp_spread"].to_numpy().astype(np.float64)
        h1 = df[f"{t}__hist_s1"].to_numpy().astype(np.float64)
        f1 = df[f"{t}__fut_s1"].to_numpy().astype(np.float64)
        y_split = f1 - h1
        # analytic shared-noise bound for the resp_ref design
        e_abs = float(df[f"{t}__hist_spread"].to_numpy().mean())
        sig2 = np.pi / 8.0 * e_abs ** 2          # per-replicate level variance (half-normal)
        bound = float((sig2 / 2.0) / np.var(y_mean))
        for scheme, fd in folds.items():
            for design, y in (("resp_ref", y_mean), ("seedsplit", y_split)):
                arms = (("clim", "geo", "state6", "state1", "state_clim")
                        if design == "resp_ref" else ("clim", "state6_s2", "state1_s2"))
                for arm in arms:
                    t0 = time.time()
                    if arm == "state1":
                        X = df.select([f"{t}__hist_ref"]).to_numpy().astype(np.float64)
                    elif arm == "state1_s2":
                        X = df.select([f"{t}__hist_s2"]).to_numpy().astype(np.float64)
                    else:
                        X, _ = arm_matrix(df, arm)
                    p = fit_oos(X, y, fd)
                    p = np.where(np.isfinite(p), p, y.mean())
                    rows.append(dict(
                        design=design, target=t, arm=arm, fold_scheme=scheme,
                        n_cells=len(y), n_blocks=fd["nblocks"], r2=r2(y, p),
                        amp_slope=slope0(y, p), pattern_r=corr(y, p),
                        frac_inside_tol=pass_frac(y_mean, sp, p) if design == "resp_ref"
                        else float("nan"),
                        shared_noise_r2_bound=bound if design == "resp_ref" else 0.0,
                        insample_lin_r2=INSAMPLE_LIN[ti], npatch=25, secs=time.time() - t0,
                    ))
                    log(f"[A] {design:9s} {t:16s} {arm:11s} {scheme:14s} "
                        f"r2={rows[-1]['r2']:+.4f} amp={rows[-1]['amp_slope']:+.3f} "
                        f"noisebound={bound:.4f} ({rows[-1]['secs']:.0f}s)")
                # convention check: the mean null, once per (design, scheme)
                pm = np.full(len(y), np.nan)
                for f in range(KFOLDS):
                    te = fd["fold"] == f
                    tr = fd["trainmask"][f]
                    pm[te] = y[tr].mean()
                rows.append(dict(
                    design=design, target=t, arm="null_mean", fold_scheme=scheme,
                    n_cells=len(y), n_blocks=fd["nblocks"], r2=r2(y, pm),
                    amp_slope=slope0(y, pm), pattern_r=corr(y, pm),
                    frac_inside_tol=pass_frac(y_mean, sp, pm) if design == "resp_ref"
                    else float("nan"),
                    shared_noise_r2_bound=bound if design == "resp_ref" else 0.0,
                    insample_lin_r2=INSAMPLE_LIN[ti], npatch=25, secs=0.0,
                ))
    out = pl.DataFrame({k: [r.get(k) for r in rows] for k in rows[0]}, infer_schema_length=None)
    p = os.path.join(SCRATCH, "vb3s_a_state_null.csv")
    out.write_csv(p)
    log(f"[A] wrote {p} ({out.height} rows)")

    log("\n[A] REPRODUCTION GATE (must be < 0.005 from B3's published salt-0 values)")
    ok = True
    for ti, t in enumerate(TARGETS):
        for arm, ref in (("clim", B3_CLIM_RESP_S0[ti]), ("geo", B3_GEO_RESP_S0[ti])):
            v = out.filter((pl.col("design") == "resp_ref") & (pl.col("target") == t)
                           & (pl.col("arm") == arm)
                           & (pl.col("fold_scheme") == "blk15_buf5_s0"))["r2"][0]
            d = abs(v - ref)
            ok &= d < 0.005
            log(f"    {t:16s} {arm:5s} mine {v:+.4f} B3 {ref:+.4f} |d|={d:.5f} "
                f"{'PASS' if d < 0.005 else 'FAIL'}")
    log(f"[A] GATE {'PASS -- my folds are B3s folds' if ok else 'FAIL -- stage A is VOID'}")

    log("\n[A] VERDICT vs the pre-registered rule (seed-split design is the believed one)")
    for design in ("resp_ref", "seedsplit"):
        sarm = "state6" if design == "resp_ref" else "state6_s2"
        for scheme, _, _, _ in BLK:
            n_match, n_half = 0, 0
            for t in TARGETS:
                s = out.filter((pl.col("design") == design) & (pl.col("fold_scheme") == scheme)
                               & (pl.col("target") == t))
                c = s.filter(pl.col("arm") == "clim")["r2"][0]
                v = s.filter(pl.col("arm") == sarm)["r2"][0]
                frac = v / c if c > 0 else float("nan")
                n_match += int(v >= c - 0.05)
                n_half += int(np.isfinite(frac) and frac >= 0.50)
                log(f"    {design:9s} {scheme:14s} {t:16s} clim {c:+.4f} state {v:+.4f} "
                    f"recovered {frac:6.1%}")
            log(f"    => {design} {scheme}: state within 0.05 of clim on {n_match}/6; "
                f">=50 % recovered on {n_half}/6")
    return out


# ---------------------------------------------------------------------------------------------
def stage_boot(df, folds):
    """Stage B: block bootstrap over 15deg tiles of the discriminator margins."""
    rng = np.random.default_rng(0)
    fd = folds["blk15_buf5_s0"]
    tile = fd["tile"]
    uniq = np.unique(tile)
    idx_by_tile = {int(u): np.flatnonzero(tile == u) for u in uniq}
    rows = []
    for t in TARGETS:
        y = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        preds = {}
        for arm in ("clim", "geo", "state6"):
            X, _ = arm_matrix(df, arm)
            p = fit_oos(X, y, fd)
            preds[arm] = np.where(np.isfinite(p), p, y.mean())
        for other in ("geo", "state6"):
            samp = np.empty(1000)
            for b in range(1000):
                pick = rng.choice(uniq, size=len(uniq), replace=True)
                ii = np.concatenate([idx_by_tile[int(u)] for u in pick])
                samp[b] = r2(y[ii], preds["clim"][ii]) - r2(y[ii], preds[other][ii])
            rows.append(dict(
                target=t, margin=f"clim_minus_{other}", fold_scheme="blk15_buf5_s0",
                n_tiles=int(len(uniq)),
                point=r2(y, preds["clim"]) - r2(y, preds[other]),
                boot_mean=float(samp.mean()), boot_sd=float(samp.std()),
                p2_5=float(np.percentile(samp, 2.5)), p97_5=float(np.percentile(samp, 97.5)),
                frac_le_zero=float(np.mean(samp <= 0)), npatch=25,
            ))
            log(f"[B] {t:16s} {rows[-1]['margin']:18s} point {rows[-1]['point']:+.4f} "
                f"boot {rows[-1]['boot_mean']:+.4f} sd {rows[-1]['boot_sd']:.4f} "
                f"CI [{rows[-1]['p2_5']:+.4f},{rows[-1]['p97_5']:+.4f}] "
                f"P(<=0)={rows[-1]['frac_le_zero']:.3f}")
    out = pl.DataFrame({k: [r.get(k) for r in rows] for k in rows[0]}, infer_schema_length=None)
    p = os.path.join(SCRATCH, "vb3s_b_bootstrap.csv")
    out.write_csv(p)
    log(f"[B] wrote {p} ({out.height} rows)")
    return out


# ---------------------------------------------------------------------------------------------
def stage_cf(df, folds):
    """Stage C: does the counterfactual at alpha=0 predict the SAME per-cell field?"""
    rows = []
    for t in TARGETS:
        y = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        X, cols = arm_matrix(df, "clim")
        fut_i = [i for i, c in enumerate(cols) if c.endswith("__fut")]
        his_i = [cols.index(c.replace("__fut", "__hist")) for c in cols if c.endswith("__fut")]
        X0 = X.copy()
        X0[:, fut_i] = X[:, his_i]                        # alpha = 0 counterfactual
        for scheme, fd in folds.items():
            p1 = fit_oos(X, y, fd)
            p0 = fit_oos(X, y, fd, xtest=X0)
            ok = np.isfinite(p1) & np.isfinite(p0)
            m1 = float(np.abs(p1[ok]).mean())
            rows.append(dict(
                target=t, fold_scheme=scheme, n_cells=int(ok.sum()),
                mean_abs_p1=m1, mean_abs_p0=float(np.abs(p0[ok]).mean()),
                magnitude_ratio=float(np.abs(p0[ok]).mean() / m1) if m1 > 0 else float("nan"),
                displacement=float(np.abs(p1[ok] - p0[ok]).mean() / m1) if m1 > 0
                else float("nan"),
                corr_p0_p1=corr(p0[ok], p1[ok]),
                signed_ratio=float(abs(p0[ok].mean()) / abs(p1[ok].mean()))
                if p1[ok].mean() != 0 else float("nan"),
                npatch=25,
            ))
            log(f"[C] {t:16s} {scheme:14s} magratio {rows[-1]['magnitude_ratio']:.4f} "
                f"displacement {rows[-1]['displacement']:.4f} "
                f"corr(p0,p1) {rows[-1]['corr_p0_p1']:+.4f}")
    out = pl.DataFrame({k: [r.get(k) for r in rows] for k in rows[0]}, infer_schema_length=None)
    p = os.path.join(SCRATCH, "vb3s_c_counterfactual.csv")
    out.write_csv(p)
    log(f"[C] wrote {p} ({out.height} rows)")
    log("\n[C] pre-registered rule: 'same' justified if corr>=0.9 AND displacement<=0.3; "
        "overstatement if corr<=0.7 OR displacement>=0.5")
    return out


# ---------------------------------------------------------------------------------------------
def stage_price(df):
    """Stage D: the incumbent's honest replicate-vs-replicate price (no fitting)."""
    rows = []
    for t in TARGETS:
        for fam, ref_c, a_c, b_c in (
            ("level_hist", f"{t}__hist_ref", f"{t}__hist_s1", f"{t}__hist_s2"),
            ("level_fut", f"{t}__fut_ref", f"{t}__fut_s1", f"{t}__fut_s2"),
        ):
            ref = df[ref_c].to_numpy().astype(np.float64)
            s1 = df[a_c].to_numpy().astype(np.float64)
            s2 = df[b_c].to_numpy().astype(np.float64)
            band = 0.10 * np.abs(ref)
            rows.append(dict(
                family=fam, target=t, n_cells=len(ref),
                b3_reported_out10=float(np.mean(np.abs(s1 - ref) > band)),
                honest_replicate_out10=float(np.mean(np.abs(s1 - s2) > band)),
                ratio=float(np.mean(np.abs(s1 - s2) > band)
                            / max(np.mean(np.abs(s1 - ref) > band), 1e-12)),
                median_rel_spread=float(np.median(np.abs(s1 - s2) / np.abs(ref))),
                npatch=25,
            ))
            log(f"[D] {fam:11s} {t:16s} B3-reported {rows[-1]['b3_reported_out10']:.4f}  "
                f"honest {rows[-1]['honest_replicate_out10']:.4f}  "
                f"x{rows[-1]['ratio']:.2f}  median rel spread "
                f"{rows[-1]['median_rel_spread']:.4f}")
    out = pl.DataFrame({k: [r.get(k) for r in rows] for k in rows[0]}, infer_schema_length=None)
    p = os.path.join(SCRATCH, "vb3s_d_incumbent_price.csv")
    out.write_csv(p)
    log(f"[D] wrote {p} ({out.height} rows)")
    return out


JOINT2_PREREG = r"""
-----------------------------------------------------------------------------------------------
E  THE OWNER'S CONJUNCTIVE BASIS, WITH THE FREE PRESENT STATE ADDED -- pre-registered before any
   result of this stage was read.
   WHY.  Stage A shows B3's response arms omit a feature every emulator has for free (today's
   state) and that including it roughly doubles the response R^2.  B3's three headline numbers on
   the owner's own conjunctive basis (all six quantities inside max(10 %, the reference's own
   two-run spread) in the SAME cell) were computed WITHOUT it: 7.18 % today, 2.93 % for the
   change, 7.35 % for the 2080s state against a persistence null of 12.96 %.  If those numbers
   move materially once the free feature is in, then B3's headline "two orders of magnitude from
   the bar" is measured on a handicapped model.
   STATISTIC: the conjunctive pass fraction, per cell, all 53 085 cells, 25 patches, blocked
   15deg+5deg both colourings, for the response family and the future-level family, arms
     clim        = B3's arm (climate only)                    [reproduction: 2.93 % / 7.35 %]
     state_clim  = climate + the six present-day state values
     state6      = the present-day state values only, no climate
   plus B3's own two do-nothing nulls recomputed here (zero-change 2.67 %, persistence 12.96 %).
   NULLS AND WHAT THEY MUST RETURN: the `clim` arm must reproduce B3's 0.02933 (response) and
   0.07352 (future level) at salt 0 to < 0.002; the zero-change null must return 0.02675 and the
   persistence null 0.12964 EXACTLY (they involve no fitting).  If not, this stage is VOID.
   B3'S CONJUNCTIVE VERDICT IS CORRECTED IF state_clim raises the response pass fraction by more
   than 2 percentage points, or raises the future-level pass fraction above the persistence null's
   12.96 %.  It is CONFIRMED IF both stay within 1 pp of B3's values.
   I EXPECT: the response number rises but stays far below the criterion; the future-level number
   rises a lot, because knowing today's state is most of the persistence null already, so this arm
   should at least MATCH persistence rather than lose to it by 5.6 pp.
-----------------------------------------------------------------------------------------------
"""


def stage_joint2(df, folds):
    """Stage E: the conjunctive criterion with the free present state as a feature."""
    log(JOINT2_PREREG)
    rows = []
    for family in ("response", "level_fut"):
        for scheme, fd in folds.items():
            ok = {}
            for arm in ("clim", "state_clim", "state6"):
                ok[arm] = np.ones(df.height, dtype=bool)
            ok["null_donothing"] = np.ones(df.height, dtype=bool)
            for t in TARGETS:
                if family == "response":
                    y = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
                    sp = df[f"{t}__resp_spread"].to_numpy().astype(np.float64)
                    dn = np.zeros(df.height)                       # zero-change null
                else:
                    y = df[f"{t}__fut_ref"].to_numpy().astype(np.float64)
                    sp = df[f"{t}__fut_spread"].to_numpy().astype(np.float64)
                    dn = df[f"{t}__hist_ref"].to_numpy().astype(np.float64)   # persistence null
                tol = np.maximum(0.10 * np.abs(y), sp)
                for arm in ("clim", "state_clim", "state6"):
                    if family == "response":
                        X, _ = arm_matrix(df, arm)
                    else:
                        base = ([f"{c}__fut" for c in CLIM_COLS]
                                + [f"{c}__hist" for c in SOIL_COLS])
                        st = [f"{t2}__hist_ref" for t2 in TARGETS]
                        cols = {"clim": base, "state_clim": st + base, "state6": st}[arm]
                        X = df.select(cols).to_numpy().astype(np.float64)
                    p = fit_oos(X, y, fd)
                    p = np.where(np.isfinite(p), p, y.mean())
                    ok[arm] &= np.abs(p - y) <= tol
                ok["null_donothing"] &= np.abs(dn - y) <= tol
            for arm, m in ok.items():
                rows.append(dict(family=family, fold_scheme=scheme, arm=arm,
                                 n_cells=df.height, n_blocks=fd["nblocks"],
                                 joint_pass=float(m.mean()), npatch=25))
                log(f"[E] {family:11s} {scheme:14s} {arm:16s} joint_pass "
                    f"{rows[-1]['joint_pass']:.5f}")
    out = pl.DataFrame({k: [r.get(k) for r in rows] for k in rows[0]}, infer_schema_length=None)
    p = os.path.join(SCRATCH, "vb3s_e_joint_state.csv")
    out.write_csv(p)
    log(f"[E] wrote {p} ({out.height} rows)")
    return out


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    log(PREREG)
    log(f"[env] repo={REPO} stage={stage}")
    df = pl.read_parquet(DESIGN)
    log(f"[env] design {df.height} rows x {df.width} cols from {DESIGN}")
    assert df.select("Cell").n_unique() == df.height, "design table has duplicate cells"
    lat = df["lat"].to_numpy().astype(float)
    lon = df["lon"].to_numpy().astype(float)
    folds = build_folds(lat, lon)
    if stage in ("all", "price"):
        stage_price(df)
    if stage in ("all", "state"):
        stage_state(df, folds)
    if stage in ("all", "boot"):
        stage_boot(df, folds)
    if stage in ("all", "cf"):
        stage_cf(df, folds)
    if stage in ("all", "joint2"):
        stage_joint2(df, folds)
    log("[done]")


if __name__ == "__main__":
    main()
