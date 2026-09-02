#!/usr/bin/env python
"""Line X / item B3 -- the DIRECT, non-autoregressive climatology -> 20-year-mean-state map.

Read-only exploration probe. Fits a per-cell map from a cell's 20-year window climatology onto
that cell's 20-year mean forest state (and onto the historic -> ssp370 RESPONSE), and scores it
against the nulls that ADR 0310 found missing -- above all a PURE GEOGRAPHIC ADDRESS.

Usage (positional args only -- the SLURM wrapper forwards no unlisted env knob):

    scripts/explore_direct_window_map.py <stage> [outtag]

    stage = "all"   -- everything below
            "prep"  -- build + write the per-cell design table and the fold maps only
            "cv"    -- the level + response cross-validated arm matrix
            "leg"   -- the trained-on-one-leg (space-for-time) transfer test

Nothing outside /p/tmp/jamirp/X_explore/ is written.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = "/p/tmp/jamirp/X_explore"
STATE_PQ = os.path.join(SCRATCH, "prep_cell_window_state.parquet")
CLIM_PQ = os.path.join(SCRATCH, "prep_cell_window_clim.parquet")
SUSPECT_CSV = os.path.join(SCRATCH, "prep_suspect_cell_blocks.csv")

W_HIST = "hist_2000_2019"
W_FUT = "ssp370_2080_2099"

# ---------------------------------------------------------------------------------------------
# PRE-REGISTRATION -- printed before any result is computed. Derived from ADR 0040 sect.3/sect.4,
# ADR 0310 sect.7.4/sect.7.5/sect.7.6 and ADR 0106, with NO look at any number this script produces.
# ---------------------------------------------------------------------------------------------
PREREG = r"""
===============================================================================================
PRE-REGISTRATION -- item B3, the direct climatology -> 20-year-mean-state map
frozen before any result of this script was read; every threshold below is derived from records
that already existed (ADR 0040 sect.3/4, ADR 0310 sect.7.4-7.6, ADR 0106) -- see the derivations.
===============================================================================================

THE QUESTION
  Can a cell's 20-year-mean forest state -- and, decisively, the historic->ssp370 CHANGE in that
  state -- be predicted from that cell's own 20-year climatology, by a map with NO rollout and no
  lagged forest state at all?  This estimand EQUALS the acceptance criterion's own basis (ADR
  0106/0111 are stated on 20-year windows), so there is no aggregation step between the model
  output and the quantity that has to be inside tolerance.

THE BLESSED STATISTIC  (in this order)
  (1) PRIMARY, the owner's basis: the FRACTION OF CELLS whose prediction lands inside
      tol_i = max(0.10 * |y_ref_i| , |y_seed1_i - y_seed2_i|)
      with y_ref_i = mean of the two seeds.  Reported per target, per arm, per fold scheme, on the
      54020-scale per-cell universe (exact universe printed with every number).  A global aggregate
      is NOT the statistic and is reported only alongside the per-cell number.
  (2) SECONDARY: pooled out-of-sample R^2 (SST about the global mean of the scored cells).
  (3) For the RESPONSE only: the amplitude (through-origin slope of predicted on true response)
      and the pattern correlation, i.e. ADR 0040 sect.4's Ra / Rr pair.

THE ARMS
  clim      window-mean climate + soil, NO coordinates
  geo       unit-sphere x,y,z ONLY -- NO climate whatsoever.  THIS IS THE NULL THAT WAS MISSING.
  clim_geo  both
  (response only)  delta   the CHANGE in climate between the two windows only, + soil
  (response only)  climhist  the HISTORIC climatology only -- knows nothing about the future climate
  All arms share identical hyperparameters and feature_fraction = 1.0, so no mtry-like lever
  differs between them (ADR 0040 sect.6.4's hidden fourth lever).

THE NULLS, AND WHAT EACH MUST RETURN  (derived, written down before the run)

  N1  geo, LEVEL target, HASH folds.  MUST RETURN A LARGE NUMBER.
      Derivation: ADR 0040 sect.3 measured a 1-NN pure-address surrogate on per-cell median traits
      under the same hash-fold design at r = 0.914 (SLA) / 0.837 (Wooddens) / 0.747 (D95max) /
      0.950 (minwscal), i.e. R^2 ~ r^2 = 0.84 / 0.70 / 0.56 / 0.90.  A 400-tree axis-aligned
      ensemble on x,y,z is a COARSER interpolator than 1-NN (it can resolve ~25k leaf regions, not
      67420 cells), so I predict geo-hash R^2 in 0.45-0.85 for the trait levels and >= 0.5 for the
      count/biomass levels.  PREREGISTERED CLAUSE: if geo-hash R^2 >= 0.45 on at least four of the
      six level targets, then EVERY hash-fold level number in this campaign is a spatial-
      interpolation score and must be labelled as one.
      FALSIFIED IF geo-hash R^2 < 0.25 on most level targets (would mean my hash folds are not the
      ADR-0040 design and the whole comparison is on a different basis).

  N2  geo, LEVEL target, BLOCKED folds.  MUST COLLAPSE, unevenly across axes.
      Derivation: ADR 0040 sect.3, block 15deg + buffer 5deg, two salts: Wooddens 0.837 ->
      0.140/0.210 (R^2 ~ 0.02-0.04), SLA 0.914 -> 0.265/0.403 (R^2 ~ 0.07-0.16), D95max 0.747 ->
      0.339/0.389 (R^2 ~ 0.11-0.15), minwscal 0.950 -> 0.723/0.706 (R^2 ~ 0.50-0.52).
      PREREGISTERED: geo-blocked R^2 must be <= 0.20 for Wooddens and SLA, and MAY stay high
      (>= 0.35) for minwscal, whose spatial pattern is continental-scale.  A geo arm that does NOT
      collapse means my blocking is not severing adjacency and the blocked numbers are void.

  N3  geo vs clim_geo, ANY target, BLOCKED folds.  THE DISCRIMINATOR.
      If R^2(clim_geo) - R^2(geo) < 0.05 the model is a SPATIAL INTERPOLATOR, not a climate
      response model, and the arm must be reported as such.  ADR 0040 sect.3's conditioning DELTA
      was +0.058/+0.076 in r on Wooddens, so a delta of this order is the most that should be
      expected.

  N4  zero-change null on the RESPONSE target (predict no change at all).
      Its pass fraction is, exactly and by algebra, the fraction of cells whose true response is
      no larger than its own two-seed spread:  |0 - d| <= max(0.1|d|, s)  <=>  |d| <= s.
      Derivation of the expectation: ADR 0040 sect.4 measured sd(response)/sd(level) = 0.20-0.31 for
      the trait axes, and ADR 0310 sect.7.4 records that the per-cell response is small against the
      reference's own noise (the two-seed noise is only 3.42 % of the AGGREGATE response, which is
      a statement about the aggregate, not the cell).  PREREGISTERED PREDICTION: the zero-change
      null passes MORE THAN HALF of cells on at least one target.  If it does, then the per-cell
      response tolerance test has little power, and THAT IS ITSELF THE FINDING -- it is reported,
      not used to relax the criterion (ADR 0106 may only be amended by the owner).

  N5  persistence null on the FUTURE-LEVEL target (predict the historic level).
      Must return the fraction of cells whose response is inside its own tolerance -- the same
      algebra as N4 but with the level's tolerance, hence LARGER, so N5 >= N4 by construction.
      Any future-level arm that does not beat N5 has learned nothing about the future.

  N6  mean null (predict the training-fold mean).  MUST RETURN R^2 <= 0 (approximately 0, slightly
      negative out of sample).  A sanity check on the R^2 convention.

  N7  THE CEILING, not a null: one C replicate predicting the two-seed mean.  Its error is exactly
      (s1-s2)/2, so R^2_ceiling = 1 - var(s1-s2)/(4 var(y_ref)).  No learned arm can be asked to
      beat it.  Its pass fraction is 1.0 BY CONSTRUCTION (|s2-y_ref| = s/2 <= max(0.1|y_ref|, s)),
      which is disclosed rather than quoted as skill.

THE FALSIFIER  (what makes me conclude the response is NOT learnable from climatology)
  The response is NOT LEARNABLE FROM CLIMATOLOGY if, on the stems-per-patch and biomass-per-patch
  response targets, under BLOCKED 15deg folds AT BOTH SALTS, BOTH of the following hold:
      (F1)  R^2(clim_geo) - R^2(geo) < 0.05  AND  R^2(clim) < 0.10 ; and
      (F2)  the best climate arm's per-cell pass fraction exceeds the zero-change null's by
            less than 2 percentage points.
  The response IS (partly) learnable if F1 fails at both salts with a margin >= 0.05 AND the
  per-cell pass fraction beats the zero-change null by >= 5 percentage points.
  Anything between is MIXED and will be reported as such.

WHAT WOULD INVALIDATE THE WHOLE THING, disclosed up front
  * The two windows are NOT independent samples: ssp370 CONTINUES the historical chain from
    restart_2019, so a cell's future window inherits the same trajectory as its historic window.
    A map fitted on one window and scored on the other therefore shares per-cell state through the
    C's own memory, and the transfer test below is optimistic for that reason.
  * The reference is a 25-PATCH run.  ADR 0093's acceptance-grade reference needs ~125-192 patches
    and resolves its own response to 8.5-12 %, so every tolerance derived here from a 25-patch
    two-seed spread is LOOSER than the real one.  The patch count is printed with every tolerance.
  * The two-seed spread is estimated from exactly TWO draws, so it is a half-normal single-sample
    estimate of the C's own spread, not a converged one.
  * All state aggregates are on the above-5 m stem population only (the C's ind writer emits
    nothing shorter), and 5 (leg,seed,Cell) blocks are excluded as damaged (prep_suspect_*.csv).
===============================================================================================
"""

# ---------------------------------------------------------------------------------------------
# feature sets
# ---------------------------------------------------------------------------------------------
CLIM_COLS = [
    "tas_wmean_degC",
    "pr_wmean_mm_yr",
    "rsds_wmean",
    "huss_wmean",
    "tas_cold_month_clm",
    "tas_warm_month_clm",
    "tas_seasonality_clm",
    "gdd5_clm",
    "frostdays_clm",
    "eco_diag_gdd_5_wmean",
    "eco_diag_vpd_mean_wmean",
    "eco_diag_pet_mean_wmean",
    "eco_diag_p_pet_ratio_wmean",
    "pr_cv_monthly_wmean",
    "prec_mean_wmean",
    "humid_mean_wmean",
]
SOIL_COLS = ["soil_code", "soil_depth"]
GEO_COLS = ["geo_x", "geo_y", "geo_z"]

TARGETS = [
    "stems_per_patch",
    "agb_per_patch",
    "SLA_median",
    "Wooddens_median",
    "D95max_median",
    "minwscal_median",
]

KFOLDS = 5
FOLD_SCHEMES = [
    # (name, kind, block_deg, buffer_deg, salt)
    ("hash", "hash", 0.0, 0.0, 0),
    ("blk15_buf5_s0", "block", 15.0, 5.0, 0),
    ("blk15_buf5_s1", "block", 15.0, 5.0, 1),
    ("blk15_buf15_s0", "block", 15.0, 15.0, 0),
    ("blk5_buf2_s0", "block", 5.0, 2.0, 0),
]

LGB_PARAMS = dict(
    n_estimators=400,
    num_leaves=63,
    learning_rate=0.05,
    min_child_samples=20,
    subsample=1.0,
    colsample_bytree=1.0,
    reg_lambda=0.0,
    n_jobs=16,
    verbose=-1,
    random_state=0,
)


def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------------------------------------
# stage prep
# ---------------------------------------------------------------------------------------------
def build_design() -> pl.DataFrame:
    st = pl.read_parquet(STATE_PQ)
    cl = pl.read_parquet(CLIM_PQ)
    sus = pl.read_csv(SUSPECT_CSV)
    bad = {(r["leg"], int(r["seed"]), int(r["Cell"])) for r in sus.iter_rows(named=True)}
    log(f"[prep] suspect (leg,seed,Cell) blocks excluded: {len(bad)} -> {sorted(bad)}")

    keep = ["Cell", "n_patches_eff", "n_years", "n_patchyears_present", *TARGETS]
    frames = {}
    for wname, wlab in (("hist", W_HIST), ("fut", W_FUT)):
        for sd in (1, 2):
            leg = "historic" if wname == "hist" else "ssp370"
            d = st.filter((pl.col("window") == wlab) & (pl.col("seed") == sd)).select(keep)
            if bad:
                excl = [c for (lg, s2, c) in bad if lg == leg and s2 == sd]
                if excl:
                    d = d.filter(~pl.col("Cell").is_in(excl))
            d = d.rename({c: f"{c}__{wname}_s{sd}" for c in keep if c != "Cell"})
            frames[(wname, sd)] = d

    df = frames[("hist", 1)]
    for k in [("hist", 2), ("fut", 1), ("fut", 2)]:
        df = df.join(frames[k], on="Cell", how="inner")
    log(f"[prep] 4-way (window x seed) intersection cells: {df.height}")

    for wname, wlab in (("hist", W_HIST), ("fut", W_FUT)):
        leg = "historic" if wname == "hist" else "ssp370"
        c = cl.filter((pl.col("window") == wlab) & (pl.col("leg") == leg)).select(
            ["Cell", "lat", "lon", *GEO_COLS, *SOIL_COLS, *CLIM_COLS]
        )
        ren = {c2: f"{c2}__{wname}" for c2 in [*SOIL_COLS, *CLIM_COLS]}
        if wname == "fut":
            ren.update({"lat": "lat__fut", "lon": "lon__fut"})
            ren.update({g: f"{g}__fut" for g in GEO_COLS})
        c = c.rename(ren)
        df = df.join(c, on="Cell", how="inner")
    log(f"[prep] after joining both windows' climatology: {df.height}")

    # the geographic address must be identical in the two windows -- gate it
    for g in GEO_COLS:
        mx = float((df[g] - df[f"{g}__fut"]).abs().max())
        assert mx == 0.0, f"[prep] GATE FAILED: {g} differs between windows by {mx}"
    df = df.drop([f"{g}__fut" for g in GEO_COLS] + ["lat__fut", "lon__fut"])
    log("[prep] GATE: unit-sphere address identical in both windows for all cells -- PASS")

    # derived: reference value, two-seed spread, response, response spread
    exprs = []
    for t in TARGETS:
        h1, h2 = pl.col(f"{t}__hist_s1"), pl.col(f"{t}__hist_s2")
        f1, f2 = pl.col(f"{t}__fut_s1"), pl.col(f"{t}__fut_s2")
        exprs += [
            ((h1 + h2) / 2).alias(f"{t}__hist_ref"),
            (h1 - h2).abs().alias(f"{t}__hist_spread"),
            ((f1 + f2) / 2).alias(f"{t}__fut_ref"),
            (f1 - f2).abs().alias(f"{t}__fut_spread"),
            (((f1 + f2) / 2) - ((h1 + h2) / 2)).alias(f"{t}__resp_ref"),
            (((f1 - h1) - (f2 - h2)).abs()).alias(f"{t}__resp_spread"),
        ]
    for c in CLIM_COLS:
        exprs.append((pl.col(f"{c}__fut") - pl.col(f"{c}__hist")).alias(f"{c}__dlt"))
    df = df.with_columns(exprs)

    # coverage: a well-populated cell has >=80 % of its patch-years present in all four blocks
    cov = None
    for wname in ("hist", "fut"):
        for sd in (1, 2):
            frac = pl.col(f"n_patchyears_present__{wname}_s{sd}") / (
                pl.col(f"n_patches_eff__{wname}_s{sd}") * pl.col(f"n_years__{wname}_s{sd}")
            )
            cov = frac if cov is None else pl.min_horizontal(cov, frac)
    df = df.with_columns(cov.alias("cov_min"))
    df = df.with_columns((pl.col("cov_min") >= 0.8).alias("well_populated"))
    log(
        f"[prep] well-populated (>=80 % patch-years present in all 4 blocks): "
        f"{int(df['well_populated'].sum())} of {df.height}"
    )
    return df


def build_folds(df: pl.DataFrame) -> dict:
    from sklearn.neighbors import BallTree

    lat = df["lat"].to_numpy()
    lon = df["lon"].to_numpy()
    cells = df["Cell"].to_numpy()
    n = len(cells)
    rad = np.deg2rad(np.column_stack([lat, lon]))
    tree = BallTree(rad, metric="haversine")

    out = {}
    for name, kind, bdeg, bufdeg, salt in FOLD_SCHEMES:
        if kind == "hash":
            fold = np.array([_h(f"cellfold:{int(c)}") % KFOLDS for c in cells])
            nblocks = n
            tile = np.arange(n)
        else:
            tl = np.floor((lat + 90.0) / bdeg).astype(int)
            tn = np.floor((lon + 180.0) / bdeg).astype(int)
            ntl = int(np.ceil(360.0 / bdeg))
            tile = tl * ntl + tn
            uniq = np.unique(tile)
            nblocks = len(uniq)
            tmap = {int(t): _h(f"tilefold:{salt}:{int(t)}") % KFOLDS for t in uniq}
            fold = np.array([tmap[int(t)] for t in tile])
        trainmask = np.ones((KFOLDS, n), dtype=bool)
        for f in range(KFOLDS):
            te = fold == f
            trainmask[f] = ~te
            if kind == "block" and bufdeg > 0 and te.any():
                idx = tree.query_radius(rad[te], r=np.deg2rad(bufdeg))
                nb = np.unique(np.concatenate(idx)) if len(idx) else np.array([], dtype=int)
                trainmask[f, nb] = False
        sizes = [int((fold == f).sum()) for f in range(KFOLDS)]
        trsz = [int(trainmask[f].sum()) for f in range(KFOLDS)]
        blk_per_fold = [len(np.unique(tile[fold == f])) for f in range(KFOLDS)]
        log(
            f"[folds] {name:16s} kind={kind} block={bdeg} buffer={bufdeg} salt={salt} "
            f"populated_blocks={nblocks} test_sizes={sizes} train_sizes={trsz} "
            f"blocks_per_fold={blk_per_fold}"
        )
        out[name] = dict(
            fold=fold, trainmask=trainmask, nblocks=nblocks, test_sizes=sizes, train_sizes=trsz
        )
    return out


# ---------------------------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------------------------
def _frame(rows: list[dict]) -> pl.DataFrame:
    """Build a frame over the UNION of all row keys.

    ⚠ DEFECT THIS FIXES (found in run 1847261): ``pl.DataFrame(list_of_dicts)`` infers the schema
    from the first ``infer_schema_length`` (=100) rows only.  The first 100 rows here are all
    ``level_hist``, which carry none of the response-only keys, so ``amp_slope``, ``pattern_r`` and
    ``frac_inside_tol_levelbasis`` were SILENTLY DROPPED from the written CSV -- the same class of
    quiet truncation the brief warns about for ``zip()``.

    ⚠ AND THE SECOND ORDER OF THE SAME BUG (run 1847459 died on it, exit 1): normalising the KEYS
    is not enough, because row-oriented construction still infers each column's DTYPE from the
    first 100 rows -- where the response-only columns are all None, so polars typed them Null and
    then raised ``could not append value: 0.0 of type f64``.  Column-oriented construction with
    ``infer_schema_length=None`` types every column from ALL of its values, which is the only form
    that is safe here.  Recorded because the first fix LOOKED sufficient and was not.
    """
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    data = {k: [r.get(k) for r in rows] for k in keys}
    return pl.DataFrame(data, infer_schema_length=None)


def r2(y, p):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ss = np.sum((y - p) ** 2)
    st = np.sum((y - y.mean()) ** 2)
    return float(1.0 - ss / st) if st > 0 else float("nan")


def pass_frac(y_ref, spread, pred, rel=0.10):
    tol = np.maximum(rel * np.abs(y_ref), spread)
    ok = np.abs(pred - y_ref) <= tol
    return float(ok.mean()), float(np.mean(np.abs(pred - y_ref) <= rel * np.abs(y_ref)))


def slope_through_origin(y, p):
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


def fit_oos(X, y, folds):
    from lightgbm import LGBMRegressor

    pred = np.full(len(y), np.nan)
    for f in range(KFOLDS):
        te = folds["fold"] == f
        tr = folds["trainmask"][f]
        if te.sum() == 0 or tr.sum() < 200:
            continue
        m = LGBMRegressor(**LGB_PARAMS)
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


def feat_matrix(df: pl.DataFrame, arm: str, family: str) -> tuple[np.ndarray, list[str]]:
    if family == "level_hist":
        sfx = "hist"
    elif family == "level_fut":
        sfx = "fut"
    else:
        sfx = None
    if family in ("level_hist", "level_fut"):
        cols = {
            "clim": [f"{c}__{sfx}" for c in CLIM_COLS] + [f"{c}__{sfx}" for c in SOIL_COLS],
            "geo": GEO_COLS,
            "clim_geo": [f"{c}__{sfx}" for c in CLIM_COLS]
            + [f"{c}__{sfx}" for c in SOIL_COLS]
            + GEO_COLS,
        }[arm]
    else:  # response
        both = (
            [f"{c}__hist" for c in CLIM_COLS]
            + [f"{c}__fut" for c in CLIM_COLS]
            + [f"{c}__hist" for c in SOIL_COLS]
        )
        cols = {
            "clim": both,
            "geo": GEO_COLS,
            "clim_geo": both + GEO_COLS,
            "delta": [f"{c}__dlt" for c in CLIM_COLS] + [f"{c}__hist" for c in SOIL_COLS],
            "climhist": [f"{c}__hist" for c in CLIM_COLS] + [f"{c}__hist" for c in SOIL_COLS],
        }[arm]
    return df.select(cols).to_numpy().astype(np.float64), cols


# ---------------------------------------------------------------------------------------------
def stage_cv(df: pl.DataFrame, folds: dict, outtag: str, only_family: str | None = None):
    rows = []
    wp = df["well_populated"].to_numpy()
    npatch_note = 25
    families = [
        ("level_hist", "hist", ["clim", "geo", "clim_geo"]),
        ("level_fut", "fut", ["clim", "geo", "clim_geo"]),
        ("response", "resp", ["clim", "geo", "clim_geo", "delta", "climhist"]),
    ]
    if only_family is not None:
        families = [f for f in families if f[0] == only_family]
    for family, key, arms in families:
        for t in TARGETS:
            y = df[f"{t}__{key}_ref"].to_numpy().astype(np.float64)
            sp = df[f"{t}__{key}_spread"].to_numpy().astype(np.float64)
            s2 = (
                df[f"{t}__{'hist' if key == 'hist' else 'fut'}_s2"].to_numpy().astype(np.float64)
                if key != "resp"
                else (
                    df[f"{t}__fut_s2"].to_numpy() - df[f"{t}__hist_s2"].to_numpy()
                ).astype(np.float64)
            )
            lvl = df[f"{t}__hist_ref"].to_numpy().astype(np.float64)

            def emit(scheme, arm, pred, nb, y=y, sp=sp, lvl=lvl, t=t, family=family):
                pf, pf10 = pass_frac(y, sp, pred)
                pfw, _ = pass_frac(y[wp], sp[wp], pred[wp])
                rec = dict(
                    family=family,
                    target=t,
                    arm=arm,
                    fold_scheme=scheme,
                    n_blocks=nb,
                    n_cells=int(np.isfinite(pred).sum()),
                    r2=r2(y[np.isfinite(pred)], pred[np.isfinite(pred)]),
                    frac_inside_tol=pf,
                    frac_inside_10pct=pf10,
                    frac_inside_tol_wellpop=pfw,
                    n_cells_wellpop=int(wp.sum()),
                    npatch=npatch_note,
                )
                if family == "response":
                    rec["amp_slope"] = slope_through_origin(y, pred)
                    rec["pattern_r"] = corr(y, pred)
                    # response tolerance read against 10 % of the LEVEL instead of of the change
                    tol2 = np.maximum(0.10 * np.abs(lvl), sp)
                    rec["frac_inside_tol_levelbasis"] = float(
                        np.mean(np.abs(pred - y) <= tol2)
                    )
                rows.append(rec)

            # --- nulls that need no fit -------------------------------------------------------
            emit("none", "null_zero" if family == "response" else "null_mean",
                 np.zeros_like(y) if family == "response" else np.full_like(y, y.mean()), 0)
            emit("none", "ceiling_seed2", s2, 0)
            if family == "level_fut":
                emit("none", "null_persist_hist", df[f"{t}__hist_ref"].to_numpy(), 0)
            if family == "response":
                emit("none", "null_mean", np.full_like(y, y.mean()), 0)

            # --- fitted arms ------------------------------------------------------------------
            for scheme, fd in folds.items():
                for arm in arms:
                    X, cols = feat_matrix(df, arm, family)
                    t0 = time.time()
                    pred = fit_oos(X, y, fd)
                    n_pred = int(np.isfinite(pred).sum())
                    emit(scheme, arm, np.where(np.isfinite(pred), pred, y.mean()), fd["nblocks"])
                    rows[-1]["n_cells_actually_predicted"] = n_pred
                    log(
                        f"[cv] {family:11s} {t:16s} {arm:9s} {scheme:15s} p={len(cols):3d} "
                        f"r2={rows[-1]['r2']:+.4f} inside={rows[-1]['frac_inside_tol']:.4f} "
                        f"({time.time() - t0:.1f}s)"
                    )
    out = _frame(rows)
    p = os.path.join(SCRATCH, f"b3_cv_results{outtag}.csv")
    out.write_csv(p)
    log(f"[cv] wrote {p}  ({out.height} rows)")
    return out


def stage_leg(df: pl.DataFrame, folds: dict, outtag: str):
    """Fit on the HISTORIC window only, predict the ssp370 window -- space-for-time."""
    rows = []
    tas_h = df["tas_wmean_degC__hist"].to_numpy()
    tas_f = df["tas_wmean_degC__fut"].to_numpy()
    hot_today = float(np.max(tas_h))
    extrap = tas_f > hot_today
    log(
        f"[leg] hottest tree-bearing cell today {hot_today:.3f} degC; "
        f"cells whose 2080-2099 climatology exceeds it: {int(extrap.sum())} of {len(extrap)} "
        f"({100 * extrap.mean():.2f} %)"
    )
    # Is the extrapolating population independent spatial evidence, or one region?  A per-row count
    # is NOT evidence of spatial independence (campaign brief / ADR 0310 sect.7.5), so census the
    # 15deg tiles it occupies and how concentrated it is.
    lat_a = df["lat"].to_numpy()
    lon_a = df["lon"].to_numpy()
    tile15 = (np.floor((lat_a + 90.0) / 15.0).astype(int) * 24) + np.floor(
        (lon_a + 180.0) / 15.0
    ).astype(int)
    ut, ct = np.unique(tile15[extrap], return_counts=True)
    order = np.argsort(-ct)
    log(
        f"[leg] EXTRAP SPATIAL INDEPENDENCE: the {int(extrap.sum())} extrapolating cells occupy "
        f"{len(ut)} populated 15deg tiles of {len(np.unique(tile15))}; "
        f"largest tile holds {int(ct[order[0]])} ({100 * ct[order[0]] / extrap.sum():.1f} %), "
        f"top 3 tiles hold {int(ct[order[:3]].sum())} "
        f"({100 * ct[order[:3]].sum() / extrap.sum():.1f} %); "
        f"lat range {lat_a[extrap].min():.2f}..{lat_a[extrap].max():.2f}, "
        f"lon range {lon_a[extrap].min():.2f}..{lon_a[extrap].max():.2f}"
    )
    for t in TARGETS:
        yh = df[f"{t}__hist_ref"].to_numpy().astype(np.float64)
        yf = df[f"{t}__fut_ref"].to_numpy().astype(np.float64)
        spf = df[f"{t}__fut_spread"].to_numpy().astype(np.float64)
        spr = df[f"{t}__resp_spread"].to_numpy().astype(np.float64)
        for scheme, fd in folds.items():
            for arm in ("clim", "geo", "clim_geo"):
                Xh, _ = feat_matrix(df, arm, "level_hist")
                Xf, _ = feat_matrix(df, arm, "level_fut")
                pf = np.full(len(yf), np.nan)
                ph = np.full(len(yh), np.nan)
                from lightgbm import LGBMRegressor

                for f in range(KFOLDS):
                    te = fd["fold"] == f
                    tr = fd["trainmask"][f]
                    if te.sum() == 0 or tr.sum() < 200:
                        continue
                    m = LGBMRegressor(**LGB_PARAMS)
                    m.fit(Xh[tr], yh[tr])          # trained on the HISTORIC leg only
                    pf[te] = m.predict(Xf[te])     # asked for the FUTURE leg
                    ph[te] = m.predict(Xh[te])
                ok = np.isfinite(pf)
                r2all = float("nan")
                r2fut = r2(yf[ok], pf[ok]) if ok.sum() > 20 else float("nan")
                for pop, mask in (
                    ("all", ok),
                    ("interp", ok & ~extrap),
                    ("extrap", ok & extrap),
                ):
                    if mask.sum() < 20:
                        continue
                    predr = pf[mask] - ph[mask]
                    truer = yf[mask] - yh[mask]
                    tolr = np.maximum(0.10 * np.abs(truer), spr[mask])
                    rows.append(
                        dict(
                            target=t,
                            arm=arm,
                            fold_scheme=scheme,
                            population=pop,
                            n_cells=int(mask.sum()),
                            n_blocks=fd["nblocks"],
                            r2_future_level=r2(yf[mask], pf[mask]),
                            frac_inside_tol_future=pass_frac(yf[mask], spf[mask], pf[mask])[0],
                            r2_response=r2(truer, predr),
                            amp_slope_response=slope_through_origin(truer, predr),
                            pattern_r_response=corr(truer, predr),
                            frac_inside_tol_response=float(
                                np.mean(np.abs(predr - truer) <= tolr)
                            ),
                            frac_inside_tol_response_zero_null=float(
                                np.mean(np.abs(truer) <= tolr)
                            ),
                            mean_true_response=float(truer.mean()),
                            mean_pred_response=float(predr.mean()),
                            npatch=25,
                        )
                    )
                    if pop == "all":
                        r2all = rows[-1]["r2_response"]
                log(
                    f"[leg] {t:16s} {arm:9s} {scheme:15s} "
                    f"r2_fut_level={r2fut:+.4f} "
                    f"r2_resp(all)={r2all:+.4f}"
                )
    out = _frame(rows)
    p = os.path.join(SCRATCH, f"b3_leg_results{outtag}.csv")
    out.write_csv(p)
    log(f"[leg] wrote {p}  ({out.height} rows)")
    return out


def descriptive(df: pl.DataFrame, outtag: str):
    """Per-cell signal-to-noise of the response -- the property deciding the question's power."""
    rows = []
    for t in TARGETS:
        d = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        s = df[f"{t}__resp_spread"].to_numpy().astype(np.float64)
        lvl = df[f"{t}__hist_ref"].to_numpy().astype(np.float64)
        rows.append(
            dict(
                target=t,
                n_cells=len(d),
                mean_level_hist=float(lvl.mean()),
                mean_response=float(d.mean()),
                mean_abs_response=float(np.abs(d).mean()),
                median_abs_response=float(np.median(np.abs(d))),
                sd_response=float(d.std()),
                sd_level=float(lvl.std()),
                sd_resp_over_sd_level=float(d.std() / lvl.std()),
                mean_two_seed_spread_resp=float(s.mean()),
                median_two_seed_spread_resp=float(np.median(s)),
                frac_cells_resp_gt_spread=float(np.mean(np.abs(d) > s)),
                mean_two_seed_spread_level=float(
                    df[f"{t}__hist_spread"].to_numpy().mean()
                ),
                median_rel_spread_level=float(
                    np.median(df[f"{t}__hist_spread"].to_numpy() / np.abs(lvl))
                ),
                npatch=25,
            )
        )
    out = pl.DataFrame(rows)
    p = os.path.join(SCRATCH, f"b3_descriptive{outtag}.csv")
    out.write_csv(p)
    log(f"[desc] wrote {p}")
    with pl.Config(tbl_cols=-1, tbl_width_chars=250, fmt_float="full"):
        log(str(out))
    return out


CF_ALPHAS = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]

CF_PREREG = r"""
-----------------------------------------------------------------------------------------------
COUNTERFACTUAL FORCING-SCALING PROBE -- pre-registered before any result of it was read
-----------------------------------------------------------------------------------------------
WHY IT IS NEEDED (it was not in the original design): this script's own identification
measurement showed the warming increment is NOT an independent variable in a single-scenario
design -- a cell's climate CHANGE is 76 % linearly predictable from its BASELINE climate for
temperature (median 62 % across the 16 change features), and corr(increment, baseline temp) is
-0.78.  So a cross-sectional response model cannot be ASSUMED to have learned a FORCING response
rather than a baseline-climate SENSITIVITY MAP.  This probe separates the two without ssp126.

THE PROBE
  Take the fitted response model and re-evaluate it on the SAME held-out cell with a
  counterfactual future climatology  fut(alpha) = hist + alpha * (fut - hist),
  for alpha in {0, 0.25, 0.5, 1, 1.5, 2}.  Nothing else changes.

THE STATISTIC
  scenario_blind_fraction = |mean predicted response at alpha=0| / |mean predicted response at
  alpha=1|.  A genuine forcing-response map returns ~0 (no climate change => no response).  A map
  that reads only the baseline climate returns ~1 (its answer does not depend on the forcing).

THE NULLS, DERIVED BEFORE THE RUN
  C1 IDEAL, exact: at alpha=0 the counterfactual future climate IS the historic climate, so the
     true response to it is IDENTICALLY ZERO.  A faithful forcing-response model must return 0.
  C2 STRUCTURAL CONTROL, exact and known in advance: the `climhist` arm's features contain no
     future climate at all, so its prediction CANNOT depend on alpha and its
     scenario_blind_fraction must come out EXACTLY 1.0000.  If it does not, this probe is
     mis-wired and every number in it is void.  (Self-check, not a result.)
  C3 The `delta` arm is a pure forcing-response model by construction -- its only inputs are the
     climate CHANGES plus soil -- so at alpha=0 its entire climate feature vector is exactly zero.
     It is the arm with the best chance of returning ~0.

THE FALSIFIER
  If scenario_blind_fraction > 0.5 for the count and biomass targets on the blocked folds, the map
  cannot meaningfully distinguish a low-emissions from a high-emissions future, and it must NOT be
  described as capturing a warming response.

DISCLOSED LIMITATION, up front
  alpha != 1 puts the input off the training manifold (every training cell has fut > hist), and a
  gradient-boosted tree is piecewise constant, so off-manifold it holds the nearest bin: its
  alpha=0 answer is approximately "the response of the least-warming cell with this baseline", not
  a true zero-forcing answer.  So this probe measures SCENARIO DISCRIMINATION of the fitted map --
  the quantity an emulator asked about ssp126 would actually need -- and it is not a fidelity
  test.  Only the ssp126 leg (never converted to columnar form) can settle fidelity.
-----------------------------------------------------------------------------------------------
"""


def stage_counterfactual(df: pl.DataFrame, folds: dict, outtag: str):
    from lightgbm import LGBMRegressor

    log(CF_PREREG)
    schemes = ["hash", "blk15_buf5_s0", "blk15_buf5_s1"]
    rows = []
    for t in TARGETS:
        y = df[f"{t}__resp_ref"].to_numpy().astype(np.float64)
        for arm in ("clim", "delta", "climhist"):
            X, cols = feat_matrix(df, arm, "response")
            if arm == "clim":
                fut_i = [i for i, c in enumerate(cols) if c.endswith("__fut")]
                his_i = [
                    cols.index(c.replace("__fut", "__hist")) for c in cols if c.endswith("__fut")
                ]
            elif arm == "delta":
                fut_i = [i for i, c in enumerate(cols) if c.endswith("__dlt")]
                his_i = None
            else:
                fut_i, his_i = [], None
            for scheme in schemes:
                fd = folds[scheme]
                preds = {a: np.full(len(y), np.nan) for a in CF_ALPHAS}
                for f in range(KFOLDS):
                    te = fd["fold"] == f
                    tr = fd["trainmask"][f]
                    if te.sum() == 0 or tr.sum() < 200:
                        continue
                    m = LGBMRegressor(**LGB_PARAMS).fit(X[tr], y[tr])
                    for a in CF_ALPHAS:
                        Xa = X[te].copy()
                        if arm == "clim":
                            base = Xa[:, his_i]
                            Xa[:, fut_i] = base + a * (X[te][:, fut_i] - base)
                        elif arm == "delta":
                            Xa[:, fut_i] = a * X[te][:, fut_i]
                        preds[a][te] = m.predict(Xa)
                ok = np.isfinite(preds[1.0])
                blk = []
                for a in CF_ALPHAS:
                    rec = dict(
                        target=t,
                        arm=arm,
                        fold_scheme=scheme,
                        alpha=a,
                        n_cells=int(ok.sum()),
                        mean_pred_response=float(preds[a][ok].mean()),
                        mean_abs_pred_response=float(np.abs(preds[a][ok]).mean()),
                        sd_pred_response=float(preds[a][ok].std()),
                        mean_true_response=float(y[ok].mean()),
                        npatch=25,
                    )
                    rows.append(rec)
                    blk.append(rec)
                m0 = blk[0]["mean_pred_response"]
                m1 = next(r["mean_pred_response"] for r in blk if r["alpha"] == 1.0)
                sbf = abs(m0) / abs(m1) if m1 != 0 else float("nan")
                log(
                    f"[cf] {t:16s} {arm:9s} {scheme:14s} alpha0 {m0:+.5g}  alpha1 {m1:+.5g}"
                    f"  TRUE {y[ok].mean():+.5g}  scenario_blind_fraction {sbf:.4f}"
                )
    out = _frame(rows)
    p = os.path.join(SCRATCH, f"b3_counterfactual{outtag}.csv")
    out.write_csv(p)
    log(f"[cf] wrote {p}  ({out.height} rows)")
    return out


def stage_joint(df: pl.DataFrame, folds: dict, outtag: str):
    """The acceptance criterion's OWN conjunctive form: a cell passes only if EVERY target passes.

    ADR 0106 requires "everything -- tree counts AND trait distributions AND trait medians --
    within 10 %", per cell.  Every per-target pass fraction above is therefore an UPPER BOUND on
    the criterion; this stage computes the actual conjunction.  Reported for the level and for the
    response, for the best climate arm and for the two do-nothing nulls, on one fold scheme pair.
    """
    log("\n[joint] the criterion's conjunctive form -- a cell passes only if ALL targets pass")
    rows = []
    for scheme in ("hash", "blk15_buf5_s0", "blk15_buf5_s1"):
        fd = folds[scheme]
        for family, key in (("level_hist", "hist"), ("level_fut", "fut"), ("response", "resp")):
            ok_arm = np.ones(df.height, dtype=bool)
            ok_null = np.ones(df.height, dtype=bool)
            for t in TARGETS:
                y = df[f"{t}__{key}_ref"].to_numpy().astype(np.float64)
                sp = df[f"{t}__{key}_spread"].to_numpy().astype(np.float64)
                tol = np.maximum(0.10 * np.abs(y), sp)
                X, _ = feat_matrix(df, "clim", family)
                pred = fit_oos(X, y, fd)
                pred = np.where(np.isfinite(pred), pred, y.mean())
                ok_arm &= np.abs(pred - y) <= tol
                # the matching do-nothing null: zero change for the response, the historic level
                # for the future level, the global mean for the historic level
                if family == "response":
                    nl = np.zeros_like(y)
                elif family == "level_fut":
                    nl = df[f"{t}__hist_ref"].to_numpy().astype(np.float64)
                else:
                    nl = np.full_like(y, y.mean())
                ok_null &= np.abs(nl - y) <= tol
            rows.append(
                dict(
                    family=family,
                    fold_scheme=scheme,
                    n_blocks=fd["nblocks"],
                    n_cells=df.height,
                    joint_pass_clim=float(ok_arm.mean()),
                    joint_pass_donothing_null=float(ok_null.mean()),
                    npatch=25,
                )
            )
            log(
                f"[joint] {family:11s} {scheme:14s} n={df.height} "
                f"ALL SIX targets inside tolerance: clim {ok_arm.mean():.4f}  "
                f"do-nothing null {ok_null.mean():.4f}"
            )
    out = _frame(rows)
    p = os.path.join(SCRATCH, f"b3_joint{outtag}.csv")
    out.write_csv(p)
    log(f"[joint] wrote {p}")
    return out


def stage_verdict(outtag: str):
    """Evaluate EVERY pre-registered clause mechanically, from the written CSVs.

    Deliberately not by eye: each clause below restates its own threshold next to the measured
    value and prints PASS / FAIL / (the pre-registered prediction was wrong), so a retrofitted
    criterion is impossible.
    """
    cv = pl.read_csv(os.path.join(SCRATCH, f"b3_cv_results{outtag}.csv"))
    leg = pl.read_csv(os.path.join(SCRATCH, f"b3_leg_results{outtag}.csv"))
    BLK = ["blk15_buf5_s0", "blk15_buf5_s1"]

    def g(fam, tgt, arm, sch, col="r2"):
        r = cv.filter(
            (pl.col("family") == fam)
            & (pl.col("target") == tgt)
            & (pl.col("arm") == arm)
            & (pl.col("fold_scheme") == sch)
        )
        return float(r[col][0]) if r.height else float("nan")

    log("\n" + "=" * 95)
    log("VERDICT -- every pre-registered clause, evaluated mechanically")
    log("=" * 95)

    log("\nN1  geo / LEVEL / HASH must be LARGE (>=0.45 on >=4 of 6 => hash numbers are")
    log("    spatial-interpolation scores).  FALSIFIED if <0.25 on most targets.")
    n1 = [(t, g("level_hist", t, "geo", "hash")) for t in TARGETS]
    for t, v in n1:
        log(f"      {t:16s} R2(geo,hash) = {v:+.4f}   {'>=0.45' if v >= 0.45 else '<0.45'}")
    k = sum(v >= 0.45 for _, v in n1)
    log(f"    -> {k} of 6 at or above 0.45  =>  {'N1 CONFIRMED' if k >= 4 else 'N1 NOT CONFIRMED'}")

    log("\nN2  geo / LEVEL / BLOCKED must COLLAPSE; pre-registered <=0.20 for Wooddens and")
    log("    SLA, and MAY stay >=0.35 for minwscal.")
    for t in TARGETS:
        vs = [g("level_hist", t, "geo", s) for s in BLK]
        h = g("level_hist", t, "geo", "hash")
        log(f"      {t:16s} hash {h:+.4f} -> blocked {vs[0]:+.4f} / {vs[1]:+.4f}")
    for t, thr in (("Wooddens_median", 0.20), ("SLA_median", 0.20)):
        vs = [g("level_hist", t, "geo", s) for s in BLK]
        ok = all(v <= thr for v in vs)
        vd = "PASS" if ok else "FAIL (the pre-registered prediction was wrong)"
        log(f"    -> {t}: <= {thr} at both salts? {vd}")
    vs = [g("level_hist", t := "minwscal_median", "geo", s) for s in BLK]
    log(f"    -> {t}: stays >=0.35? {'yes' if all(v >= 0.35 for v in vs) else 'no'}")

    log("\nN3  THE DISCRIMINATOR: R2(clim_geo) - R2(geo) under BLOCKED folds; <0.05 => the arm")
    log("    is a spatial interpolator, not a climate model.  Also: clim alone vs clim_geo.")
    for fam in ("level_hist", "response"):
        log(f"    -- family {fam}")
        for t in TARGETS:
            for s in BLK:
                cg, ge, cl = (g(fam, t, a, s) for a in ("clim_geo", "geo", "clim"))
                d = cg - ge
                vd = ">=0.05" if d >= 0.05 else "<0.05 INTERPOLATOR"
                log(
                    f"      {t:16s} {s:14s} clim {cl:+.4f}  geo {ge:+.4f} "
                    f"clim_geo {cg:+.4f}   DELTA {d:+.4f}  {vd}"
                )

    log("\nN4  zero-change null on the RESPONSE, per-cell pass fraction.  Pre-registered")
    log("    prediction: it passes MORE THAN HALF the cells on at least one target.")
    over = 0
    for t in TARGETS:
        z = g("response", t, "null_zero", "none", "frac_inside_tol")
        arms = ("clim", "clim_geo", "climhist", "delta")
        best = max(
            g("response", t, a, s, "frac_inside_tol") for a in arms for s in BLK
        )
        over += z > 0.5
        log(
            f"      {t:16s} zero-null {z:.4f}   best blocked climate arm {best:.4f}"
            f"   margin {100 * (best - z):+.2f} pp"
        )
    log(f"    -> targets where doing nothing already passes >50 % of cells: {over} of 6")

    log("\nN5  persistence null on the FUTURE LEVEL (predict the historic level).")
    for t in TARGETS:
        p = g("level_fut", t, "null_persist_hist", "none", "frac_inside_tol")
        best = max(
            g("level_fut", t, a, s, "frac_inside_tol") for a in ("clim", "clim_geo") for s in BLK
        )
        log(
            f"      {t:16s} persistence {p:.4f}   best blocked climate arm {best:.4f}"
            f"   margin {100 * (best - p):+.2f} pp"
        )

    log("\nN6  mean null must return R2 ~ 0 (convention check).")
    for t in TARGETS:
        log(f"      {t:16s} R2(null_mean) = {g('level_hist', t, 'null_mean', 'none'):+.6f}")

    log("\nN7  CEILING -- one C replicate vs the two-seed mean.  Pass fraction is 1.0 BY")
    log("    CONSTRUCTION; the informative column is how often it is inside a PURE 10 % band.")
    for t in TARGETS:
        p10 = g("level_hist", t, "ceiling_seed2", "none", "frac_inside_10pct")
        log(
            f"      {t:16s} R2 {g('level_hist', t, 'ceiling_seed2', 'none'):+.4f}"
            f"   inside pure 10 % {p10:.4f}   (25 patches)"
        )

    log("\nTHE FALSIFIER, on the two headline response targets, at BOTH salts:")
    log("  F1: DELTA(clim_geo - geo) < 0.05 AND R2(clim) < 0.10 ;  F2: per-cell margin over the")
    log("  zero-change null < 2 pp.  Both true at both salts => NOT LEARNABLE.")
    for t in ("stems_per_patch", "agb_per_patch"):
        z = g("response", t, "null_zero", "none", "frac_inside_tol")
        for s in BLK:
            cg, ge, cl = (g("response", t, a, s) for a in ("clim_geo", "geo", "clim"))
            pf = g("response", t, "clim", s, "frac_inside_tol")
            f1 = (cg - ge) < 0.05 and cl < 0.10
            f2 = (pf - z) < 0.02
            log(
                f"      {t:16s} {s:14s} DELTA {cg - ge:+.4f}  R2(clim) {cl:+.4f}"
                f"  per-cell margin {100 * (pf - z):+.2f} pp   F1={f1}  F2={f2}"
            )

    log("\nTHE TRANSFER TEST (fitted on the HISTORIC leg only) -- the space-for-time question.")
    log("  Note the geo arm's features are IDENTICAL in both windows, so its implied response is")
    log("  EXACTLY ZERO: in this design the address arm IS the zero-change null (self-check).")
    for s in ["hash", *BLK]:
        log(f"    -- fold scheme {s}")
        for t in TARGETS:
            for pop in ("all", "interp", "extrap"):
                r = leg.filter(
                    (pl.col("target") == t)
                    & (pl.col("arm") == "clim")
                    & (pl.col("fold_scheme") == s)
                    & (pl.col("population") == pop)
                )
                if not r.height:
                    continue
                pc = float(r["frac_inside_tol_response"][0])
                zn = float(r["frac_inside_tol_response_zero_null"][0])
                mt = float(r["mean_true_response"][0])
                mp = float(r["mean_pred_response"][0])
                sign = "OK" if mt * mp > 0 else "WRONG"
                log(
                    f"      {t:16s} {pop:7s} n={int(r['n_cells'][0]):6d} "
                    f"R2resp {float(r['r2_response'][0]):+.4f} "
                    f"amp {float(r['amp_slope_response'][0]):+.4f} "
                    f"patt_r {float(r['pattern_r_response'][0]):+.4f} "
                    f"per-cell {pc:.4f} vs zero-null {zn:.4f} "
                    f"({100 * (pc - zn):+.2f} pp) "
                    f"| mean true {mt:+.4g} pred {mp:+.4g} SIGN {sign}"
                )
    log("=" * 95)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    outtag = ("_" + sys.argv[2]) if len(sys.argv) > 2 else ""
    log(PREREG)
    if stage == "verdict":
        stage_verdict(outtag)
        log("[done]")
        return
    log(f"[env] repo={REPO} scratch={SCRATCH} stage={stage} outtag={outtag!r}")
    log(f"[env] polars={pl.__version__} numpy={np.__version__}")
    import lightgbm
    import sklearn

    log(f"[env] lightgbm={lightgbm.__version__} sklearn={sklearn.__version__}")
    log(f"[env] LGB_PARAMS={json.dumps(LGB_PARAMS)}")
    log(f"[env] KFOLDS={KFOLDS} FOLD_SCHEMES={FOLD_SCHEMES}")

    t0 = time.time()
    df = build_design()
    dp = os.path.join(SCRATCH, f"b3_design{outtag}.parquet")
    df.write_parquet(dp)
    log(f"[prep] wrote {dp} ({df.height} rows x {df.width} cols) in {time.time() - t0:.1f}s")
    folds = build_folds(df)
    descriptive(df, outtag)
    if stage in ("all", "cv"):
        stage_cv(df, folds, outtag)
    if stage == "resp":
        stage_cv(df, folds, outtag, only_family="response")
    if stage == "cf":  # deliberately NOT part of "all" -- separate, later probes
        stage_counterfactual(df, folds, outtag)
    if stage == "joint":
        stage_joint(df, folds, outtag)
    if stage in ("all", "leg"):
        stage_leg(df, folds, outtag)
    log("[done]")


if __name__ == "__main__":
    main()
