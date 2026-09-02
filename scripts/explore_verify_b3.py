#!/usr/bin/env python
"""Line X -- ADVERSARIAL VERIFICATION of item B3 (the direct climatology -> window-state map).

Read-only. Writes only under /p/tmp/jamirp/X_explore/ with the prefix ``vb3_``.

The item under test claims (a) climate genuinely beats a map-coordinates-only null under spatially
blocked folds, (b) the warming increment is 62-76 % predictable from the baseline climate, (c) the
fitted map still predicts "76-100 % of the same per-cell change" with the warming scaled to zero,
(d) the reference model's own replicate is outside a pure 10 % band on 2.7-34.0 % of cells, and
(e) a set of response numbers on a 53 085-cell universe.  This script attacks all five.

Usage (positional only):   scripts/explore_verify_b3.py <stage>
    stage = all | v1 | v2 | v3 | v4 | v5
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
STATE_PQ = os.path.join(SCRATCH, "prep_cell_window_state.parquet")
CLIM_PQ = os.path.join(SCRATCH, "prep_cell_window_clim.parquet")
SUSPECT_CSV = os.path.join(SCRATCH, "prep_suspect_cell_blocks.csv")

W_HIST = "hist_2000_2019"
W_FUT = "ssp370_2080_2099"

PREREG = r"""
===============================================================================================
PRE-REGISTRATION -- adversarial verification of item B3.  Frozen before any result of THIS
script was read.  Every threshold is stated with the value that would make me say the finding
under test survives, and the value that would make me say it is refuted.
===============================================================================================

V1  THE STRONGER ADDRESS NULL -- a SMOOTH GLOBAL SPATIAL BASIS, still no climate at all.
    WHY: the item's headline rests on R^2(clim) - R^2(geo) under blocked folds, where `geo` is
    RAW unit-sphere x,y,z fed to an axis-aligned tree ensemble.  Under blocked folds a tree on raw
    x,y,z CANNOT generalise to a held-out 15deg tile: every leaf is an axis-aligned box in (x,y,z)
    and the held-out tile's box is populated only by cells the buffer removed.  So the geo arm's
    collapse is partly an ENCODING artifact, not proof that climate carries physics.  The fair
    address null is a smooth basis of position that a tree CAN interpolate: sin/cos of lat and lon
    at wavenumbers 1,2,3,4,6,8 plus x,y,z (21 columns vs climate's 18) -- strictly more capacity
    than the climate arm, and STILL only "where you are".
    STATISTIC: R^2(sph) minus R^2(clim), blocked 15deg + 5deg buffer, both colourings, 6 level
    targets and 6 response targets.
    NULLS AND WHAT THEY MUST RETURN, derived before the run:
      * The mean null must return R^2 = 0.000000 exactly (same convention as the item).
      * `geo` must reproduce the item's own values to <1e-3 (0.2902/0.1505/0.2807/... for the
        level at salt 0), which certifies I rebuilt its folds identically.  If it does not, my
        fold construction differs and V1 is void.
    REFUTES the headline IF R^2(sph) >= R^2(clim) - 0.05 on 4 or more of the 6 LEVEL targets at
      both colourings: a coordinates-only model, merely better encoded, then matches climate and
      "climate is not an address proxy" is unsupported.
    HEADLINE SURVIVES IF R^2(sph) <= R^2(clim) - 0.15 on 4 or more of the 6 level targets at both
      colourings.  Anything between is PARTIAL -- reported as a narrowing, not a refutation.
    I EXPECT, honestly: partial.  Forest state is smooth at 15deg scale, so I expect the basis to
    recover much of the level; the response is where I expect climate to keep a real margin.

V2  THE IDENTIFICATION CLAIM, which appears in NO log and NO artifact of the item -- only inside
    the prose of its own pre-registration block.  Reported as [MEASURED]: warming increment 76.4 %
    linearly predictable from baseline climate, median 62.0 % across 16 change features,
    corr(increment, baseline temp) = -0.7827, increment mean 3.312 K, sd 0.973 K.
    STATISTIC: exactly that -- OLS of each of the 16 climate-CHANGE features on all 16 BASELINE
    climate features, in-sample R^2, on the same 53 085-cell universe; plus the correlation and the
    increment moments.
    CONFIRMED IF every quoted number reproduces to +-0.02 (R^2 / correlation) and +-0.02 K
    (moments).  REFUTED IF any is outside that.  There is no null here: it is an arithmetic claim.

V3  THE INCUMBENT'S PRICE (trap 1).  The item reports "the reference model's own second run is
    OUTSIDE a pure 10 % band on 13.7 % of cells for stem count" -- but that compares one replicate
    against the MEAN OF ITSELF AND THE OTHER, whose error is (s1-s2)/2, i.e. HALF a replicate's
    real disagreement.  The honest replicate-vs-replicate number is |s1-s2| > 0.10*|ref|.
    STATISTIC: both, side by side, per target, 25 patches.
    PREDICTED, before the run: the honest number is roughly 2x the reported one wherever the
    reported one is small, so ~25-30 % for stems and ~45-50 % for biomass.
    THE ITEM IS CORRECTED (not refuted) IF the honest number is materially larger; the direction
    matters because the item uses the reported number to argue the max() clause is necessary --
    the honest number makes that argument STRONGER, not weaker.

V4  THE COUNTERFACTUAL STATISTIC.  The item's headline sentence says the fitted map "still
    predicted 76-100 % of the SAME per-cell change" with the warming scaled to zero.  Its actual
    statistic is mean|pred(alpha=0)| / mean|pred(alpha=1)| -- a ratio of MAGNITUDES, which is
    blind to whether the per-cell pattern changed at all.  A map could return a completely
    different per-cell field of the same average size and score 1.0.
    STATISTIC: the displacement fraction  mean|pred(1) - pred(0)| / mean|pred(1)|  and
    corr(pred(0), pred(1)), per cell, clim arm, stems + biomass, blocked 15deg+5deg both
    colourings.
    CONFIRMED IF corr(pred0, pred1) >= 0.9 and displacement <= 0.3 -- then the predictions really
    are nearly the same field and the item's word "same" is justified.
    REFUTED IF corr <= 0.7 or displacement >= 0.5 -- then the magnitude ratio near 1 was
    coincidental and the sentence overstates what was measured.

V5  THE UNIVERSE (the defect I expect to matter most).  The item's design is a 4-WAY INNER JOIN
    over (2 windows x 2 replicates), so a cell must bear a >5 m tree in ALL FOUR blocks to be
    scored.  Measured from the prep table before writing this: the historic leg has 54 020
    tree-bearing cells, the 2080-2099 leg has 57 599, and the intersection is 53 089.  So the
    scored universe DROPS 4 136 cells that hold no tree today and a MEAN OF 7.31 STEMS PER PATCH
    in the 2080s -- a per-cell warming response as large as the entire mean standing state of a
    kept cell (7.44) -- plus 495 cells that lose their trees.  Nothing in the item discloses this;
    it reports the universe as "98.3 % of the criterion's own 54 020 tree-bearing cells", which is
    true of the historic leg and hides that the response universe is conditioned on SURVIVING AND
    NOT ARRIVING.
    STATISTIC: rebuild the response on the UNION universe -- a cell is in if it bears trees in
    both replicates of at least one window -- filling an absent (window, replicate) with a
    STRUCTURAL ZERO (0 stems per patch, 0 biomass per patch; the trait medians are undefined at
    zero trees so V5 covers only the count and biomass targets, which is stated, not worked
    around).  Then: mean true response, the zero-change null, R^2 / amplitude / pattern of the
    clim arm, and the per-cell pass fraction, on both universes side by side, blocked folds.
    NULLS: the zero-change null is recomputed on the repaired universe (it MUST fall, because the
    arriving cells have a response far larger than their own two-replicate spread); the mean null
    must still return R^2 = 0.000000.
    THE ITEM'S RESPONSE NUMBERS ARE REFUTED AS UNREPRESENTATIVE IF, on the repaired universe, the
    mean true stem response changes SIGN or changes by more than 100 % of its intersection-universe
    value, or the clim arm's per-cell margin over the zero-change null moves by more than 5
    percentage points in either direction.
    THEY SURVIVE, NARROWED, IF the margins move by less than 2 percentage points and the sign of
    the mean response is unchanged -- then the exclusion is a disclosure defect, not a numerical
    one.
    NOTE ON DIRECTION, stated before the run so I cannot claim it afterwards: I do not know which
    way this goes.  The arriving cells could be EASY for a climate map (arrival is a suitability
    threshold, and suitability is a climate function), which would make the item's response
    verdict too PESSIMISTIC; or they could be unlearnable, making it too optimistic.  Either way
    the item's numbers are on a universe that excludes the model's largest warming response.
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
COUNT_TARGETS = ["stems_per_patch", "agb_per_patch"]
KFOLDS = 5
BLK = [("blk15_buf5_s0", 15.0, 5.0, 0), ("blk15_buf5_s1", 15.0, 5.0, 1)]
WAVE = [1, 2, 3, 4, 6, 8]

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
    d = np.sum(y * y)
    return float(np.sum(y * p) / d) if d > 0 else float("nan")


def corr(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    if y.std() == 0 or p.std() == 0:
        return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def build_folds(lat, lon, schemes, extra_hash=True):
    """Rebuild the item's fold construction verbatim (block tiles + geodesic buffer)."""
    from sklearn.neighbors import BallTree

    n = len(lat)
    rad = np.deg2rad(np.column_stack([lat, lon]))
    tree = BallTree(rad, metric="haversine")
    out = {}
    items = list(schemes)
    for name, bdeg, bufdeg, salt in items:
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
        out[name] = dict(fold=fold, trainmask=trainmask, nblocks=len(uniq))
        log(f"[folds] {name:16s} blocks={len(uniq)} "
            f"test={[int((fold == f).sum()) for f in range(KFOLDS)]} "
            f"train={[int(trainmask[f].sum()) for f in range(KFOLDS)]}")
    if extra_hash:
        cells = np.arange(n)
        out["hash"] = dict(fold=np.array([_h(f"vhash:{int(c)}") % KFOLDS for c in cells]),
                           trainmask=None, nblocks=n)
        f = out["hash"]["fold"]
        out["hash"]["trainmask"] = np.array([f != k for k in range(KFOLDS)])
    return out


def fit_oos(X, y, fd):
    from lightgbm import LGBMRegressor

    pred = np.full(len(y), np.nan)
    for f in range(KFOLDS):
        te = fd["fold"] == f
        tr = fd["trainmask"][f]
        if te.sum() == 0 or tr.sum() < 200:
            continue
        pred[te] = LGBMRegressor(**LGB_PARAMS).fit(X[tr], y[tr]).predict(X[te])
    return pred


def sph_basis(lat, lon):
    """A SMOOTH GLOBAL basis of position -- no climate.  21 columns."""
    la = np.deg2rad(lat)
    lo = np.deg2rad(lon)
    cols = [np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]
    names = ["x", "y", "z"]
    for k in WAVE:
        cols += [np.sin(k * la), np.cos(k * la), np.sin(k * lo), np.cos(k * lo)]
        names += [f"sinlat{k}", f"coslat{k}", f"sinlon{k}", f"coslon{k}"]
    # drop the degenerate k=1 duplicates of z / x-y phase? keep -- extra capacity favours the null
    return np.column_stack(cols).astype(np.float64), names


# ---------------------------------------------------------------------------------------------
def stage_v1(df):
    lat = df["lat"].to_numpy().astype(float)
    lon = df["lon"].to_numpy().astype(float)
    folds = build_folds(lat, lon, BLK, extra_hash=False)
    Xsph, sphnames = sph_basis(lat, lon)
    Xgeo = df.select(GEO_COLS).to_numpy().astype(np.float64)
    log(f"[v1] smooth spatial basis: {Xsph.shape[1]} columns {sphnames}")
    rows = []
    for family in ("level_hist", "response"):
        for t in TARGETS:
            key = "hist" if family == "level_hist" else "resp"
            y = df[f"{t}__{key}_ref"].to_numpy().astype(np.float64)
            if family == "level_hist":
                Xcl = df.select([f"{c}__hist" for c in CLIM_COLS]
                                + [f"{c}__hist" for c in SOIL_COLS]).to_numpy().astype(np.float64)
            else:
                Xcl = df.select([f"{c}__hist" for c in CLIM_COLS]
                                + [f"{c}__fut" for c in CLIM_COLS]
                                + [f"{c}__hist" for c in SOIL_COLS]).to_numpy().astype(np.float64)
            for scheme, fd in folds.items():
                res = {}
                for arm, X in (("clim", Xcl), ("geo", Xgeo), ("sph", Xsph)):
                    t0 = time.time()
                    p = fit_oos(X, y, fd)
                    p = np.where(np.isfinite(p), p, y.mean())
                    res[arm] = dict(r2=r2(y, p), amp=slope0(y, p), pr=corr(y, p),
                                    secs=time.time() - t0)
                rows.append(dict(family=family, target=t, fold_scheme=scheme,
                                 n_cells=len(y), n_blocks=folds[scheme]["nblocks"],
                                 r2_clim=res["clim"]["r2"], r2_geo=res["geo"]["r2"],
                                 r2_sph=res["sph"]["r2"],
                                 sph_minus_clim=res["sph"]["r2"] - res["clim"]["r2"],
                                 sph_minus_geo=res["sph"]["r2"] - res["geo"]["r2"],
                                 pattern_r_clim=res["clim"]["pr"], pattern_r_sph=res["sph"]["pr"],
                                 npatch=25))
                log(f"[v1] {family:11s} {t:16s} {scheme:14s} clim {res['clim']['r2']:+.4f} "
                    f"geo {res['geo']['r2']:+.4f} SPH {res['sph']['r2']:+.4f}   "
                    f"sph-clim {rows[-1]['sph_minus_clim']:+.4f}")
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, "vb3_v1_spatial_basis.csv")
    out.write_csv(p)
    log(f"[v1] wrote {p}")
    log("\n[v1] VERDICT against the pre-registered thresholds")
    for scheme in [b[0] for b in BLK]:
        for family in ("level_hist", "response"):
            s = out.filter((pl.col("fold_scheme") == scheme) & (pl.col("family") == family))
            nref = int((s["sph_minus_clim"] >= -0.05).sum())
            nsur = int((s["sph_minus_clim"] <= -0.15).sum())
            log(f"  {family:11s} {scheme:14s} targets with sph >= clim-0.05: {nref}/6 "
                f"(>=4 REFUTES) ; with sph <= clim-0.15: {nsur}/6 (>=4 SURVIVES)")
    return out


def stage_v2(df):
    log("\n[v2] identification: baseline climate -> climate change, in-sample linear R^2")
    Xb = df.select([f"{c}__hist" for c in CLIM_COLS]).to_numpy().astype(np.float64)
    Xb1 = np.column_stack([np.ones(len(Xb)), Xb])
    rows = []
    for c in CLIM_COLS:
        d = df[f"{c}__dlt"].to_numpy().astype(np.float64)
        beta, *_ = np.linalg.lstsq(Xb1, d, rcond=None)
        pred = Xb1 @ beta
        rows.append(dict(change_feature=c, r2_from_baseline=r2(d, pred),
                         mean_change=float(d.mean()), sd_change=float(d.std()),
                         corr_with_baseline_tas=corr(df["tas_wmean_degC__hist"].to_numpy(), d)))
        log(f"  {c:30s} R2={rows[-1]['r2_from_baseline']:+.4f} "
            f"mean={rows[-1]['mean_change']:+.4f} sd={rows[-1]['sd_change']:.4f} "
            f"corr(baseline tas)={rows[-1]['corr_with_baseline_tas']:+.4f}")
    out = pl.DataFrame(rows)
    med = float(out["r2_from_baseline"].median())
    tas = out.filter(pl.col("change_feature") == "tas_wmean_degC")
    log(f"\n  QUOTED 0.764 for the temperature increment  -> MEASURED "
        f"{float(tas['r2_from_baseline'][0]):+.4f}")
    log(f"  QUOTED median 0.620 across 16 change features -> MEASURED {med:+.4f}")
    log(f"  QUOTED corr(increment, baseline temp) -0.7827 -> MEASURED "
        f"{float(tas['corr_with_baseline_tas'][0]):+.4f}")
    log(f"  QUOTED increment mean 3.312 K sd 0.973 K     -> MEASURED "
        f"{float(tas['mean_change'][0]):.4f} / {float(tas['sd_change'][0]):.4f}")
    p = os.path.join(SCRATCH, "vb3_v2_identification.csv")
    out.write_csv(p)
    log(f"[v2] wrote {p}")
    return out


def stage_v3(df):
    log("\n[v3] the incumbent's price: replicate-vs-replicate, not replicate-vs-its-own-mean")
    rows = []
    for t in TARGETS:
        s1 = df[f"{t}__hist_s1"].to_numpy().astype(np.float64)
        s2 = df[f"{t}__hist_s2"].to_numpy().astype(np.float64)
        ref = (s1 + s2) / 2.0
        band = 0.10 * np.abs(ref)
        as_reported = float(np.mean(np.abs(s2 - ref) > band))
        honest = float(np.mean(np.abs(s1 - s2) > band))
        rows.append(dict(target=t, n_cells=len(ref), npatch=25,
                         outside_10pct_replicate_vs_mean=as_reported,
                         outside_10pct_replicate_vs_replicate=honest,
                         ratio=honest / as_reported if as_reported > 0 else float("nan"),
                         median_rel_spread=float(np.median(np.abs(s1 - s2) / np.abs(ref)))))
        log(f"  {t:16s} as the item reports it {100 * as_reported:6.2f} %   "
            f"HONEST replicate-vs-replicate {100 * honest:6.2f} %   "
            f"x{rows[-1]['ratio']:.2f}   median relative disagreement "
            f"{100 * rows[-1]['median_rel_spread']:.2f} %")
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, "vb3_v3_incumbent_price.csv")
    out.write_csv(p)
    log(f"[v3] wrote {p}")
    return out


def stage_v4(df):
    from lightgbm import LGBMRegressor

    log("\n[v4] counterfactual: is the alpha=0 prediction the SAME FIELD, or just the same size?")
    lat = df["lat"].to_numpy().astype(float)
    lon = df["lon"].to_numpy().astype(float)
    folds = build_folds(lat, lon, BLK, extra_hash=False)
    cols = ([f"{c}__hist" for c in CLIM_COLS] + [f"{c}__fut" for c in CLIM_COLS]
            + [f"{c}__hist" for c in SOIL_COLS])
    X = df.select(cols).to_numpy().astype(np.float64)
    fut_i = [i for i, c in enumerate(cols) if c.endswith("__fut")]
    his_i = [cols.index(c.replace("__fut", "__hist")) for c in cols if c.endswith("__fut")]
    assert len(fut_i) == len(his_i) == len(CLIM_COLS)
    rows = []
    for t in COUNT_TARGETS:
        y = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        for scheme, fd in folds.items():
            p0 = np.full(len(y), np.nan)
            p1 = np.full(len(y), np.nan)
            for f in range(KFOLDS):
                te = fd["fold"] == f
                tr = fd["trainmask"][f]
                if te.sum() == 0 or tr.sum() < 200:
                    continue
                m = LGBMRegressor(**LGB_PARAMS).fit(X[tr], y[tr])
                p1[te] = m.predict(X[te])
                Xa = X[te].copy()
                Xa[:, fut_i] = Xa[:, his_i]          # alpha = 0 : future climate := historic
                p0[te] = m.predict(Xa)
            ok = np.isfinite(p1)
            mag_ratio = float(np.abs(p0[ok]).mean() / np.abs(p1[ok]).mean())
            disp = float(np.abs(p1[ok] - p0[ok]).mean() / np.abs(p1[ok]).mean())
            rows.append(dict(target=t, fold_scheme=scheme, n_cells=int(ok.sum()),
                             item_magnitude_ratio=mag_ratio,
                             displacement_fraction=disp,
                             corr_pred0_pred1=corr(p0[ok], p1[ok]),
                             signed_aggregate_ratio=float(abs(p0[ok].mean())
                                                          / abs(p1[ok].mean())),
                             mean_true_response=float(y[ok].mean()), npatch=25))
            log(f"  {t:16s} {scheme:14s} item's magnitude ratio {mag_ratio:.4f} | "
                f"DISPLACEMENT {disp:.4f} | corr(pred0,pred1) "
                f"{rows[-1]['corr_pred0_pred1']:+.4f} | signed-aggregate ratio "
                f"{rows[-1]['signed_aggregate_ratio']:.4f}")
    out = pl.DataFrame(rows)
    log("\n[v4] pre-registered: CONFIRMED if corr>=0.9 and displacement<=0.3 ; "
        "REFUTED if corr<=0.7 or displacement>=0.5")
    for r in rows:
        v = ("CONFIRMED" if (r["corr_pred0_pred1"] >= 0.9 and r["displacement_fraction"] <= 0.3)
             else "REFUTED" if (r["corr_pred0_pred1"] <= 0.7
                               or r["displacement_fraction"] >= 0.5) else "BETWEEN")
        log(f"   {r['target']:16s} {r['fold_scheme']:14s} -> {v}")
    p = os.path.join(SCRATCH, "vb3_v4_counterfactual_pattern.csv")
    out.write_csv(p)
    log(f"[v4] wrote {p}")
    return out


def build_union(df_int: pl.DataFrame) -> pl.DataFrame:
    """The UNION universe: tree-bearing in both replicates of at least ONE window.

    An absent (window, replicate) is a STRUCTURAL ZERO for the count and biomass targets.
    """
    st = pl.read_parquet(STATE_PQ)
    sus = pl.read_csv(SUSPECT_CSV)
    bad = {(r["leg"], int(r["seed"]), int(r["Cell"])) for r in sus.iter_rows(named=True)}
    keep = ["Cell", *COUNT_TARGETS]
    frames = {}
    for wname, wlab, leg in (("hist", W_HIST, "historic"), ("fut", W_FUT, "ssp370")):
        for sd in (1, 2):
            d = st.filter((pl.col("window") == wlab) & (pl.col("seed") == sd)).select(keep)
            excl = [c for (lg, s2, c) in bad if lg == leg and s2 == sd]
            if excl:
                d = d.filter(~pl.col("Cell").is_in(excl))
            frames[(wname, sd)] = d.rename(
                {c: f"{c}__{wname}_s{sd}" for c in COUNT_TARGETS}
            )
    h = frames[("hist", 1)].join(frames[("hist", 2)], on="Cell", how="inner")
    f = frames[("fut", 1)].join(frames[("fut", 2)], on="Cell", how="inner")
    uni = pl.concat([h.select("Cell"), f.select("Cell")]).unique()
    log(f"[v5] both-replicate historic cells {h.height}, both-replicate future cells {f.height}, "
        f"UNION {uni.height} (the item scored {df_int.height})")
    d = uni.join(h, on="Cell", how="left").join(f, on="Cell", how="left")
    fill = [pl.col(c).fill_null(0.0) for c in d.columns if c != "Cell"]
    d = d.with_columns(fill)
    cl = pl.read_parquet(CLIM_PQ)
    for wname, wlab, leg in (("hist", W_HIST, "historic"), ("fut", W_FUT, "ssp370")):
        c = cl.filter((pl.col("window") == wlab) & (pl.col("leg") == leg)).select(
            ["Cell", *(["lat", "lon", *GEO_COLS] if wname == "hist" else []),
             *SOIL_COLS, *CLIM_COLS])
        c = c.rename({x: f"{x}__{wname}" for x in [*SOIL_COLS, *CLIM_COLS]})
        d = d.join(c, on="Cell", how="inner")
    ex = []
    for t in COUNT_TARGETS:
        h1, h2 = pl.col(f"{t}__hist_s1"), pl.col(f"{t}__hist_s2")
        f1, f2 = pl.col(f"{t}__fut_s1"), pl.col(f"{t}__fut_s2")
        ex += [((h1 + h2) / 2).alias(f"{t}__hist_ref"),
               ((f1 + f2) / 2).alias(f"{t}__fut_ref"),
               (((f1 + f2) / 2) - ((h1 + h2) / 2)).alias(f"{t}__resp_ref"),
               (((f1 - h1) - (f2 - h2)).abs()).alias(f"{t}__resp_spread")]
    return d.with_columns(ex)


def stage_v5(df_int):
    log("\n[v5] SURVIVORSHIP: the item's 4-way inner join drops arriving and dying cells")
    uni = build_union(df_int)
    inter_cells = set(df_int["Cell"].to_list())
    added = uni.filter(~pl.col("Cell").is_in(list(inter_cells)))
    log(f"[v5] cells the item never scored: {added.height}")
    rows = []
    for name, d in (("intersection_item", df_int), ("union_repaired", uni)):
        lat = d["lat"].to_numpy().astype(float)
        lon = d["lon"].to_numpy().astype(float)
        folds = build_folds(lat, lon, BLK, extra_hash=False)
        Xcl = d.select([f"{c}__hist" for c in CLIM_COLS] + [f"{c}__fut" for c in CLIM_COLS]
                       + [f"{c}__hist" for c in SOIL_COLS]).to_numpy().astype(np.float64)
        Xgeo = (d.select(GEO_COLS).to_numpy().astype(np.float64) if name == "intersection_item"
                else sph_basis(lat, lon)[0][:, :3])
        for t in COUNT_TARGETS:
            y = d[f"{t}__resp_ref"].to_numpy().astype(np.float64)
            sp = d[f"{t}__resp_spread"].to_numpy().astype(np.float64)
            tol = np.maximum(0.10 * np.abs(y), sp)
            zero_null = float(np.mean(np.abs(y) <= tol))
            for scheme, fd in folds.items():
                for arm, X in (("clim", Xcl), ("geo", Xgeo)):
                    p = fit_oos(X, y, fd)
                    p = np.where(np.isfinite(p), p, y.mean())
                    pf = float(np.mean(np.abs(p - y) <= tol))
                    rows.append(dict(universe=name, target=t, arm=arm, fold_scheme=scheme,
                                     n_cells=len(y), mean_true_response=float(y.mean()),
                                     mean_abs_true_response=float(np.abs(y).mean()),
                                     sd_true_response=float(y.std()),
                                     r2=r2(y, p), amp=slope0(y, p), pattern_r=corr(y, p),
                                     frac_inside_tol=pf, zero_null_frac=zero_null,
                                     margin_pp=100 * (pf - zero_null), npatch=25))
                    log(f"  {name:18s} {t:16s} {arm:5s} {scheme:14s} n={len(y):6d} "
                        f"meantrue {rows[-1]['mean_true_response']:+.4f} "
                        f"r2 {rows[-1]['r2']:+.4f} amp {rows[-1]['amp']:+.4f} "
                        f"pass {pf:.4f} vs zero {zero_null:.4f} "
                        f"({rows[-1]['margin_pp']:+.2f} pp)")
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, "vb3_v5_universe.csv")
    out.write_csv(p)
    log(f"[v5] wrote {p}")
    log("\n[v5] the arriving/dying cells, described")
    for t in COUNT_TARGETS:
        a = added[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        i = df_int[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        log(f"  {t:16s} added n={len(a)} mean resp {a.mean():+.4f} median {np.median(a):+.4f} "
            f"max {a.max():+.4f} | item-scored n={len(i)} mean resp {i.mean():+.4f}")
    la = added["lat"].to_numpy()
    log(f"  added-cell latitude: min {la.min():.2f} median {np.median(la):.2f} max {la.max():.2f}"
        f" ; fraction above 50N {float(np.mean(la > 50)):.3f}")
    return out


def stage_v6(df_int):
    """Arithmetic only: what the SURVIVORSHIP exclusion does to the two do-nothing NULLS.

    The item's two headline null numbers are (a) the persistence null on the future level, which it
    reports as BEATING the climate map (12.96 % vs 7.35 % on the conjunctive form), and (b) the
    zero-change null on the response.  Both are computed on the 4-way intersection, which excludes
    4 635 cells that hold no tree today.  Persistence predicts ZERO trees there against a truth of
    ~7.3 stems per patch, so it must fail every one of them -- i.e. the exclusion INFLATES the null
    that the item reports as the winner.  No fitting: this is pure arithmetic on the two universes.
    """
    log("\n[v6] the do-nothing nulls on both universes -- arithmetic only, no model")
    uni = build_union(df_int)
    rows = []
    for name, d in (("intersection_item", df_int), ("union_repaired", uni)):
        for t in COUNT_TARGETS:
            h = d[f"{t}__hist_ref"].to_numpy().astype(np.float64)
            fu = d[f"{t}__fut_ref"].to_numpy().astype(np.float64)
            resp = d[f"{t}__resp_ref"].to_numpy().astype(np.float64)
            spr = d[f"{t}__resp_spread"].to_numpy().astype(np.float64)
            # future-level tolerance needs the future two-replicate spread
            f1 = d[f"{t}__fut_s1"].to_numpy().astype(np.float64)
            f2 = d[f"{t}__fut_s2"].to_numpy().astype(np.float64)
            spf = np.abs(f1 - f2)
            tol_f = np.maximum(0.10 * np.abs(fu), spf)
            tol_r = np.maximum(0.10 * np.abs(resp), spr)
            rows.append(dict(
                universe=name, target=t, n_cells=len(fu),
                persistence_null_future_level=float(np.mean(np.abs(h - fu) <= tol_f)),
                zero_change_null_response=float(np.mean(np.abs(resp) <= tol_r)),
                npatch=25))
            log(f"  {name:18s} {t:16s} n={len(fu):6d} persistence-null on the FUTURE level "
                f"{rows[-1]['persistence_null_future_level']:.4f}"
                f"   zero-change null on the RESPONSE "
                f"{rows[-1]['zero_change_null_response']:.4f}")
    # the conjunctive form restricted to the two targets that are defined at zero trees
    for name, d in (("intersection_item", df_int), ("union_repaired", uni)):
        okp = np.ones(d.height, dtype=bool)
        okz = np.ones(d.height, dtype=bool)
        for t in COUNT_TARGETS:
            h = d[f"{t}__hist_ref"].to_numpy().astype(np.float64)
            fu = d[f"{t}__fut_ref"].to_numpy().astype(np.float64)
            resp = d[f"{t}__resp_ref"].to_numpy().astype(np.float64)
            spr = d[f"{t}__resp_spread"].to_numpy().astype(np.float64)
            spf = np.abs(d[f"{t}__fut_s1"].to_numpy().astype(np.float64)
                         - d[f"{t}__fut_s2"].to_numpy().astype(np.float64))
            okp &= np.abs(h - fu) <= np.maximum(0.10 * np.abs(fu), spf)
            okz &= np.abs(resp) <= np.maximum(0.10 * np.abs(resp), spr)
        log(f"  {name:18s} CONJUNCTIVE over stems+biomass only: persistence {okp.mean():.4f}  "
            f"zero-change {okz.mean():.4f}")
        rows.append(dict(universe=name, target="stems+agb_conjunctive", n_cells=d.height,
                         persistence_null_future_level=float(okp.mean()),
                         zero_change_null_response=float(okz.mean()), npatch=25))
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, "vb3_v6_nulls_both_universes.csv")
    out.write_csv(p)
    log(f"[v6] wrote {p}")
    return out


def stage_v7(df):
    """The RECORD'S OWN address null: a 1-NN geographic surrogate, not a tree on x,y,z.

    ADR 0040 sect.3 -- the record the item derives its N1/N2 thresholds from -- measures the address
    null as a **1-NN transferred from each fold's training set**.  The item instead fed raw
    unit-sphere x,y,z to the same 400-tree LightGBM ensemble.  Those are different estimators, and
    under blocked folds the difference is not cosmetic: an axis-aligned tree cannot leave the boxes
    its training tiles occupy, while a 1-NN always returns the nearest surviving training cell.
    ADR 0310 sect.2(iv) reports a blocked-fold address score of **0.353** on its response target
    against the item's -0.25/-0.39, which is the size of gap this stage tests for.
    PRE-REGISTERED, before running: if the 1-NN address beats the item's tree-on-xyz `geo` arm by
    more than 0.15 in R^2 on most targets, the item's headline discriminator margin is overstated
    by that amount and must be requoted against this null instead.  The item's CONCLUSION survives
    anyway iff R^2(clim) - R^2(1nn) still exceeds its own pre-registered 0.05 threshold.
    """
    from sklearn.neighbors import BallTree

    log("\n[v7] the record's own address null: 1-NN geographic surrogate under the SAME folds")
    lat = df["lat"].to_numpy().astype(float)
    lon = df["lon"].to_numpy().astype(float)
    rad = np.deg2rad(np.column_stack([lat, lon]))
    folds = build_folds(lat, lon, BLK, extra_hash=False)
    rows = []
    for family, key in (("level_hist", "hist"), ("response", "resp")):
        for t in TARGETS:
            y = df[f"{t}__{key}_ref"].to_numpy().astype(np.float64)
            if family == "level_hist":
                Xcl = df.select([f"{c}__hist" for c in CLIM_COLS]
                                + [f"{c}__hist" for c in SOIL_COLS]).to_numpy().astype(np.float64)
            else:
                Xcl = df.select([f"{c}__hist" for c in CLIM_COLS]
                                + [f"{c}__fut" for c in CLIM_COLS]
                                + [f"{c}__hist" for c in SOIL_COLS]).to_numpy().astype(np.float64)
            for scheme, fd in folds.items():
                p1nn = np.full(len(y), np.nan)
                for f in range(KFOLDS):
                    te = fd["fold"] == f
                    tr = fd["trainmask"][f]
                    if te.sum() == 0 or tr.sum() < 200:
                        continue
                    bt = BallTree(rad[tr], metric="haversine")
                    _, idx = bt.query(rad[te], k=1)
                    p1nn[te] = y[tr][idx[:, 0]]
                pc = fit_oos(Xcl, y, fd)
                pc = np.where(np.isfinite(pc), pc, y.mean())
                r2n = r2(y, np.where(np.isfinite(p1nn), p1nn, y.mean()))
                rows.append(dict(family=family, target=t, fold_scheme=scheme, n_cells=len(y),
                                 r2_clim=r2(y, pc), r2_1nn_address=r2n,
                                 clim_minus_1nn=r2(y, pc) - r2n,
                                 corr_1nn=corr(y, np.where(np.isfinite(p1nn), p1nn, y.mean())),
                                 npatch=25))
                log(f"  {family:11s} {t:16s} {scheme:14s} clim {rows[-1]['r2_clim']:+.4f}  "
                    f"1-NN address {r2n:+.4f}  (r={rows[-1]['corr_1nn']:+.4f})  "
                    f"clim-1nn {rows[-1]['clim_minus_1nn']:+.4f}  "
                    f"{'>=0.05' if rows[-1]['clim_minus_1nn'] >= 0.05 else '<0.05 INTERPOLATOR'}")
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, "vb3_v7_1nn_address.csv")
    out.write_csv(p)
    log(f"[v7] wrote {p}")
    return out


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    log(PREREG)
    log(f"[env] repo={REPO} stage={stage} polars={pl.__version__} numpy={np.__version__}")
    import lightgbm
    import sklearn
    log(f"[env] lightgbm={lightgbm.__version__} sklearn={sklearn.__version__}")
    df = pl.read_parquet(DESIGN)
    log(f"[env] design {df.height} rows x {df.width} cols")
    if stage in ("all", "v2"):
        stage_v2(df)
    if stage in ("all", "v3"):
        stage_v3(df)
    if stage in ("all", "v4"):
        stage_v4(df)
    if stage in ("all", "v5"):
        stage_v5(df)
    if stage in ("all", "v6"):
        stage_v6(df)
    if stage in ("all", "v7"):
        stage_v7(df)
    if stage in ("all", "v1"):
        stage_v1(df)
    log("[done]")


if __name__ == "__main__":
    main()
