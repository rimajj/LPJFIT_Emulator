#!/usr/bin/env python
"""Adversarial verification of item B2, round 2 -- the RESPONSE stage's missing nulls.

Read-only. Consumes only artifacts item B2 already wrote:
    /p/tmp/jamirp/X_explore/b2_stem_features.parquet   (10 919 647 x 117)
    /p/tmp/jamirp/X_explore/b2_response_cells.parquet   (the learner's own per-cell windows)
    /p/tmp/jamirp/X_explore/b2_ladder.csv
Writes only /p/tmp/jamirp/X_explore/vb2r_*.

WHY THIS PROBE EXISTS
---------------------
B2's own report, its first adversarial verifier, and ADR 0311 all apply ADR 0310 section 2(ii)'s
STANDING RULE -- report the persistence null beside every one-step number -- to B2's SKILL stage
only.  B2's RESPONSE stage is also one-step teacher-forced (its own biggest caveat), it is scored
with a through-origin slope and a correlation, and it carries three nulls: do-nothing (slope 0 by
construction), coordinates-only (constant within a cell, so 0 by construction), and the two-seed
noise floor (a property of the truth, no model).  NOT ONE of those three is a free predictor built
from the true state the model is handed.  So no B2 or vb2 number says whether the response result
survives a zero-parameter copy.  That is what this probe measures.
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "/p/tmp/jamirp/X_explore"
FEAT = f"{OUT}/b2_stem_features.parquet"
CELLS = f"{OUT}/b2_response_cells.parquet"
LADDER = f"{OUT}/b2_ladder.csv"

WINDOWS = [("hist", "historic", 2000, 2019),
           ("ssp_early", "ssp370", 2020, 2039),
           ("ssp_late", "ssp370", 2080, 2099)]
MIN_STEMYEARS = 200
RNG = 20260902
_T0 = time.time()

PREREG = """
================================================================================================
PRE-REGISTRATION -- adversarial verification of B2, the RESPONSE stage    (written before any run)
================================================================================================
QUESTION
  B2 reports that a per-tree operator fitted on the historic leg alone reproduces 57 % of the
  amplitude and 75-81 % of the achievable spatial pattern of the per-cell warming change in death
  rate, and (growth) a spatial correlation of 0.955-0.966 that EXCEEDS the two-seed floor of 0.787.
  Every one of those numbers is computed by handing the model the TRUE future per-tree state.
  ASK: does a predictor with ZERO fitted parameters, built from the same handed-in true state,
  reproduce the same response?  If it does, the response numbers measure the information content
  of the state the model was handed, not anything the model learned.

STATISTIC (identical to B2's, deliberately -- same aggregation, same cells, same windows)
  per (Cell, window) mean of the predictor and of the truth; a cell enters only with
  n >= 200 stem-years in BOTH windows; the reported pair is the through-origin slope and the
  Pearson r of (pred_late - pred_hist) on (truth_late - truth_hist).

THE FREE PREDICTORS (no fit, no parameters, no training data used at all)
  R-N1  task t2 (growth):  p := m_dagb_prev, i.e. THIS tree's biomass increment LAST year.
        This is the response-stage form of the persistence null the standing rule mandates.
  R-N2  task t1 (death):   p := mort, the reference model's own nominated kill probability.
        Banned as a feature in B2's ladder, but it is a deterministic function of the true state
        the response stage hands the model, so it is available for free at prediction time.
  R-N3  task t1 (death):   p := mort_npp only (one of the four hazard terms) -- a weaker free
        predictor, included so R-N2 is not the only point on the curve.
  R-N4  task t2 (growth):  p := npp, this year's own productivity, unscaled and unfitted.

WHAT EACH NULL MUST RETURN (derived BEFORE the run -- this is the part ADR 0184 requires)
  R-N1: m_dagb_prev is the same physical quantity as the label, lagged one year.  A 20-year window
        mean of a 1-year-lagged series differs from the unlagged mean only in the two end years,
        i.e. by O(1/20) of the within-window variance.  DERIVED PREDICTION: slope in [0.9, 1.1]
        and r >= 0.97.  If it returns that, B2's t2 response slope 0.7587-0.8186 / r 0.955-0.966
        is WORSE than a free copy on both statistics.
  R-N2: the nominated hazard misses 23.5 % of realised deaths (B2's own finding) and scores
        AUC 0.70 against the learner's 0.742 per tree.  If per-tree ranking were what the response
        stage measured, R-N2's response r should sit BELOW the learner's 0.7456.  DERIVED
        PREDICTION under B2's own reading: r(R-N2) < 0.70.
  R-N3: mort_npp is one additive term of four; it must not beat R-N2.
  R-N4: npp is the wrong units and the wrong scale for d_agb, so its through-origin SLOPE must be
        far from 1; its r is the informative half.

FALSIFIERS (stated as numbers, before the run)
  F-A  I will conclude B2's t2 RESPONSE result is entirely a restatement of teacher forcing, and
       carries no evidence that the operator learned a warming response, if R-N1's r comes within
       0.03 of the best fitted t2 arm's r AND its |slope - 1| is smaller than the best fitted
       arm's |slope - 1|.
  F-B  I will conclude B2's t1 RESPONSE result is not evidence of learning if R-N2's r is at or
       above the best fitted t1 arm's r (0.7456 for n4) minus 2 x the paired bootstrap SE.
  F-C  I will conclude the response stage's nulls were ADEQUATE, and B2's response reading stands,
       if BOTH R-N1's r falls more than 0.03 below the fitted t2 arms AND R-N2's r falls more than
       2 paired SE below 0.7456.
  F-D  Independent of A-C: I will conclude B2's "share of all learnable skill by block" for the
       DEATH target is order-dependent to the point of being uninformative if recomputing it
       against a non-trivial baseline (the first verifier's memory+age+height arm, AUC 0.69258)
       moves the climate share by more than a factor of 2.

UNCERTAINTY
  Paired differences of correlations are bootstrapped 4000x BOTH over cells and over the populated
  15-degree blocks the cells sit in, because the 490-500 cells are not 490-500 independent units.
  A difference whose block-bootstrap 95 % interval spans 0 is NOT significant.

WHAT WOULD MAKE ME REPORT A SURPRISE
  If R-N1 does NOT return slope ~1 / r >= 0.97, my derivation of the lag algebra is wrong and I
  will say so rather than reinterpret the criterion.
================================================================================================
"""


def _say(msg: str) -> None:
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


def _slope_origin(x: np.ndarray, y: np.ndarray) -> float:
    d = float(np.sum(x * x))
    return float(np.sum(x * y) / d) if d > 0 else float("nan")


def _agg_windows(cell: np.ndarray, leg: np.ndarray, yr: np.ndarray,
                 truth: np.ndarray, pred: np.ndarray) -> pl.DataFrame:
    """Exactly B2's stage_resp aggregation: label windows, mean per (Cell, win), n>=200, pivot."""
    wl = np.full(cell.size, "", dtype=object)
    for lab, lg, y0, y1 in WINDOWS:
        wl[(leg == lg) & (yr >= y0) & (yr <= y1)] = lab
    agg = (pl.DataFrame({"Cell": cell, "win": wl, "y": truth, "p": pred})
           .filter(pl.col("win") != "")
           .group_by(["Cell", "win"])
           .agg([pl.len().alias("n"), pl.col("y").mean().alias("truth"),
                 pl.col("p").mean().alias("pred")]))
    assert agg.select(["Cell", "win"]).n_unique() == agg.height, "key set not unique"
    return agg.filter(pl.col("n") >= MIN_STEMYEARS).pivot(
        on="win", index="Cell", values=["truth", "pred"])


def _boot_pair(x: np.ndarray, ya: np.ndarray, yb: np.ndarray, blocks: np.ndarray,
               nb: int = 4000) -> dict:
    """Bootstrap r(x,ya) - r(x,yb) over cells and over blocks."""
    rng = np.random.default_rng(RNG)
    out = {}
    for mode in ("cell", "block"):
        d = np.empty(nb)
        if mode == "cell":
            for i in range(nb):
                j = rng.integers(0, x.size, x.size)
                d[i] = (np.corrcoef(x[j], ya[j])[0, 1] - np.corrcoef(x[j], yb[j])[0, 1])
        else:
            ub = np.unique(blocks)
            idx = {b: np.flatnonzero(blocks == b) for b in ub}
            for i in range(nb):
                pick = rng.integers(0, ub.size, ub.size)
                j = np.concatenate([idx[ub[p]] for p in pick])
                d[i] = (np.corrcoef(x[j], ya[j])[0, 1] - np.corrcoef(x[j], yb[j])[0, 1])
        out[mode] = (float(np.nanmean(d)),
                     float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5)))
    return out


def main() -> None:
    print(PREREG, flush=True)
    _say(f"repo root (derived) = {REPO}")
    for p in (FEAT, CELLS, LADDER):
        if not os.path.exists(p):
            raise SystemExit(f"missing input {p}")

    need = ["leg", "Year", "Cell", "isdead", "d_agb", "mort", "mort_npp", "m_dagb_prev",
            "npp", "pairable", "survived", "fold_hash5", "lat", "lon", "fpc_ind", "agb",
            "Age", "Height", "Type"]
    _say("loading b2_stem_features.parquet (columns needed only) ...")
    a = pl.read_parquet(FEAT, columns=need)
    _say(f"   {a.shape}")

    # ---------- integrity re-checks on the artifact itself -------------------------------------
    _say("--- integrity ---")
    nrow = a.height
    fin = {}
    for c in ("mort", "m_dagb_prev", "d_agb", "npp", "agb"):
        v = a[c].to_numpy().astype(np.float64)
        fin[c] = dict(n_nan=int(np.isnan(v).sum()), n_inf=int(np.isinf(v).sum()),
                      vmin=float(np.nanmin(v)), vmax=float(np.nanmax(v)))
        _say(f"   {c:12s} nan={fin[c]['n_nan']:9d} inf={fin[c]['n_inf']} "
             f"min={fin[c]['vmin']:.6g} max={fin[c]['vmax']:.6g}")
    dead = int(a["isdead"].sum())
    smort = float(a["mort"].sum())
    _say(f"   rows={nrow} deaths={dead} sum(mort)={smort:.1f} "
         f"excess={(dead - smort) / dead:.4f}")

    # the isneg / collapsed-crown observability claim B2 made
    disc = a.filter(pl.col("mort") < 1.0)
    nd = disc.height
    tiny_fpc = int(disc.filter(pl.col("fpc_ind") <= 1e-20).height)
    nonpos_agb = int(disc.filter(pl.col("agb") <= 0.0).height)
    dd = disc.filter(pl.col("isdead") == 1)
    _say(f"   discretionary rows={nd} of which deaths={dd.height}; "
         f"fpc_ind<=1e-20: {tiny_fpc}; agb<=0: {nonpos_agb}")
    _say(f"   among discretionary DEATHS: fpc_ind<=1e-20 "
         f"{int(dd.filter(pl.col('fpc_ind') <= 1e-20).height)}, "
         f"agb<=0 {int(dd.filter(pl.col('agb') <= 0.0).height)}")
    # mort==1 group
    cert = a.filter(pl.col("mort") >= 1.0)
    _say(f"   mort>=1 rows={cert.height} death rate={float(cert['isdead'].mean()):.6f}")

    rows = []
    # ---------- the free-predictor response nulls ----------------------------------------------
    learn = pl.read_parquet(CELLS)
    lat = a.group_by("Cell").agg([pl.col("lat").first(), pl.col("lon").first()])

    specs = [("t1", "isdead", "R-N2_mort", "mort"),
             ("t1", "isdead", "R-N3_mort_npp", "mort_npp"),
             ("t2", "d_agb", "R-N1_persistence_mdagb_prev", "m_dagb_prev"),
             ("t2", "d_agb", "R-N4_npp", "npp")]

    for task, ycol, name, pcol in specs:
        d = a
        if task == "t2":
            d = d.filter(pl.col("pairable") & (pl.col("survived") == 1)
                         & pl.col("d_agb").is_not_null())
        d = d.filter(pl.col("fold_hash5").is_not_null())
        d = d.filter(pl.col(pcol).is_not_null())
        w = _agg_windows(d["Cell"].to_numpy(), d["leg"].to_numpy(), d["Year"].to_numpy(),
                         d[ycol].to_numpy().astype(np.float64),
                         d[pcol].to_numpy().astype(np.float64))
        for late in ("ssp_late", "ssp_early"):
            nd2 = [f"truth_{late}", "truth_hist", f"pred_{late}", "pred_hist"]
            ww = w.drop_nulls(nd2)
            tx = (ww[f"truth_{late}"] - ww["truth_hist"]).to_numpy()
            py = (ww[f"pred_{late}"] - ww["pred_hist"]).to_numpy()
            sl = _slope_origin(tx, py)
            r = float(np.corrcoef(tx, py)[0, 1])
            rows.append(dict(task=task, arm=name, window=late, ncell=tx.size, slope=sl, corr=r,
                             rms_true=float(np.sqrt(np.mean(tx ** 2))),
                             rms_pred=float(np.sqrt(np.mean(py ** 2))),
                             mean_true=float(tx.mean()), mean_pred=float(py.mean())))
            _say(f"   {task} {name:28s} {late:9s} ncell={tx.size:4d} slope={sl:+.4f} "
                 f"r={r:+.4f} rms_true={np.sqrt(np.mean(tx**2)):.5g} "
                 f"rms_pred={np.sqrt(np.mean(py**2)):.5g}")
            # paired against the learner on the SAME cells
            for arm in ("n4", "n5"):
                lw = learn.filter((pl.col("task") == task) & (pl.col("arm") == arm)
                                  & (pl.col("window") == late))
                if lw.height == 0:
                    continue
                j = (ww.select(["Cell", f"truth_{late}", "truth_hist",
                                f"pred_{late}", "pred_hist"])
                     .rename({f"pred_{late}": "np_late", "pred_hist": "np_hist"})
                     .join(lw.select(["Cell", f"pred_{late}", "pred_hist"])
                           .rename({f"pred_{late}": "lp_late", "pred_hist": "lp_hist"}),
                           on="Cell", how="inner")
                     .join(lat, on="Cell", how="left"))
                txj = (j[f"truth_{late}"] - j["truth_hist"]).to_numpy()
                nullj = (j["np_late"] - j["np_hist"]).to_numpy()
                learnj = (j["lp_late"] - j["lp_hist"]).to_numpy()
                blk = (np.floor(j["lat"].to_numpy() / 15.0) * 100
                       + np.floor(j["lon"].to_numpy() / 15.0))
                b = _boot_pair(txj, nullj, learnj, blk)
                rn = float(np.corrcoef(txj, nullj)[0, 1])
                rl = float(np.corrcoef(txj, learnj)[0, 1])
                rows.append(dict(task=task, arm=f"PAIRED_{name}_minus_{arm}", window=late,
                                 ncell=txj.size, slope=float("nan"), corr=rn - rl,
                                 rms_true=float("nan"),
                                 rms_pred=float("nan"), mean_true=float("nan"),
                                 mean_pred=float("nan"),
                                 r_null=rn, r_learn=rl,
                                 boot_cell_lo=b["cell"][1], boot_cell_hi=b["cell"][2],
                                 boot_blk_lo=b["block"][1], boot_blk_hi=b["block"][2],
                                 nblock=int(np.unique(blk).size),
                                 slope_null=_slope_origin(txj, nullj),
                                 slope_learn=_slope_origin(txj, learnj)))
                _say(f"      vs {arm}: n={txj.size} nblk={np.unique(blk).size} "
                     f"r_null={rn:+.4f} r_learn={rl:+.4f} diff={rn - rl:+.4f} "
                     f"CI_cell[{b['cell'][1]:+.4f},{b['cell'][2]:+.4f}] "
                     f"CI_blk[{b['block'][1]:+.4f},{b['block'][2]:+.4f}] | "
                     f"slope_null={_slope_origin(txj, nullj):+.4f} "
                     f"slope_learn={_slope_origin(txj, learnj):+.4f}")

    out = pl.DataFrame(rows, infer_schema_length=None)
    out.write_csv(f"{OUT}/vb2r_response_nulls.csv")
    _say(f"wrote {OUT}/vb2r_response_nulls.csv")

    # ---------- F-D: the T1 share decomposition against a non-trivial baseline ----------------
    _say("--- F-D: T1 share decomposition, trivial vs non-trivial baseline ---")
    lad = pl.read_csv(LADDER)
    hz = lad.filter((pl.col("task") == "t1") & (pl.col("scheme") == "hash5")
                    & (~pl.col("arm").str.starts_with("DELTA")))
    got = {r["arm"]: r for r in hz.iter_rows(named=True)}
    metric = "auc_mean" if "auc_mean" in hz.columns else "mean"
    n0 = float(got["n0"][metric])
    n6 = float(got["n6"][metric])
    parts = {"own_size_age": float(got["n1"][metric]) - n0,
             "own_traits": float(got["n2"][metric]) - float(got["n1"][metric]),
             "own_cwstate": float(got["n3"][metric]) - float(got["n2"][metric]),
             "patch": float(got["n4"][metric]) - float(got["n3"][metric]),
             "climate": float(got["n5"][metric]) - float(got["n4"][metric]),
             "memory": n6 - float(got["n5"][metric])}
    span_triv = n6 - n0
    M2 = 0.6925847874901896  # first verifier's memory-4 + Age + Height arm, vb2_persistence.csv
    span_nont = n6 - M2
    _say(f"   n0={n0:.5f} n6={n6:.5f} span_trivial={span_triv:.5f} "
         f"non-trivial baseline (mem4+age+height)={M2:.5f} span={span_nont:.5f}")
    shrows = []
    for k, v in parts.items():
        s1 = 100 * v / span_triv
        s2 = 100 * v / span_nont
        shrows.append(dict(block=k, increment=v, share_vs_intercept_pct=s1,
                           share_vs_nontrivial_pct=s2, factor=s2 / s1 if s1 else float("nan")))
        _say(f"   {k:14s} inc={v:+.5f}  share vs intercept={s1:5.1f} %   "
             f"vs non-trivial={s2:6.1f} %   x{s2 / s1 if s1 else float('nan'):.2f}")
    pl.DataFrame(shrows).write_csv(f"{OUT}/vb2r_share_recomputed.csv")
    _say(f"wrote {OUT}/vb2r_share_recomputed.csv")
    _say("DONE")


if __name__ == "__main__":
    sys.exit(main())
