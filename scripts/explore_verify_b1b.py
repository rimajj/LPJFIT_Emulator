#!/usr/bin/env python
"""B1 adversarial verification, ROUND 2 (independent of the V1-V4 pass).

Four attacks the first verification pass did not run.  Read-only except this
file and /p/tmp/jamirp/X_explore/verify_b1b_*.

Run:  scripts/sbatch_python.sh X-vb1b scripts/explore_verify_b1b.py [limit_cells]
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explore_hidden_counter as H  # noqa: E402
import explore_verify_b1 as V  # noqa: E402

OUT = "/p/tmp/jamirp/X_explore"
KEY = V.KEY

PREREG = r"""
================================================================================
PRE-REGISTRATION — B1 ADVERSARIAL VERIFICATION, ROUND 2
   printed BEFORE any result.  Four attacks the V1-V4 pass did not run.
================================================================================

 W1  THE FINDING'S CEILING FOR A BIOMASS-PREDICTING LEARNED MODEL IS NOT A
     CEILING — IT IS A HARDCODED SIGN RULE.
     The finding's null N-C is `predict a growth failure iff agb(y+1)<agb(y)`,
     scores recall 0.3455, and is then promoted in the headline and in
     `what_would_have_to_be_true` to "a purely learned model that predicts
     biomass and reads off the sign is CAPPED AT 35 % detection".  That is a
     claim about the INFORMATION in the biomass columns; N-C measures only one
     fixed FUNCTION of them.  From the C source the sign rule cannot be the
     ceiling: `mortality_tree_ind.c:66` sets bm_delta = bm_inc.carbon/nind -
     turnover_ind, while the emitted `agb`/`vegc` are nind-scaled pool sums with
     different membership (ADR 0127), so Delta-agb differs from bm_delta by a
     LEARNABLE function of the level variables, not by noise.
     STATISTIC: positive-class recall / fpr / balanced accuracy of a LEARNED
     classifier on nested feature sets, same 5-folds-by-cell OOF protocol, same
     pair population, same label as the finding.
       L0 = the single feature `_d_agb`            (gate: must reproduce N-C)
       L1 = biomass ONLY: agb, vegc at y and y+1 and their two deltas
            ("an operator that predicts biomass perfectly and nothing else")
       L2 = L1 + the printed per-stem geometry (Height, LAI, fpc_ind) at both
            years + deltas.  Still NO npp, NO transp/wscal, NO stand, NO climate.
       L3 = the finding's full M3                  (gate: must reproduce 0.9023)
     NULLS / DERIVED VALUES, written down now:
       * L0 MUST return recall within 0.01 of N-C's 0.3455 and fpr within 0.005
         of 0.0204 — a learned threshold on one monotone feature can only
         reproduce or trade along that feature's own ROC.  If it does not, my
         pipeline is not the finding's and nothing else here is admissible.
       * L3 MUST return recall 0.90 +- 0.01 and fpr <= 0.008 (the finding's
         0.902341 / 0.006595).  Same admissibility gate.
       * The do-nothing null N-A returns recall EXACTLY 0.000, balanced accuracy
         EXACTLY 0.500, accuracy = P[c(y+1)==0] = 0.865210.
     FALSIFIER FOR W1: if L1 recall < 0.50 then biomass alone really is weak and
     the finding's "capped at 35 %" survives as a statement about the columns
     (I withdraw W1 and say so).  If L1 recall >= 0.80 at fpr <= 0.05 — the
     finding's OWN "IS propagable" bar — then the headline's central asymmetry
     ("hybrid gets it free, purely learned is capped at 35 %") is REFUTED,
     because a model that predicts only biomass clears the bar.

 W2  THE DECISIVE ROLLOUT NUMBER IS A POOLED COUNT RATIO, NOT AN IDENTIFICATION
     STATISTIC, AND NOT PER CELL.
     "the population of trees marked for certain death is within 5 % of the
     truth" is n5_prop/n5_true pooled over 674 cells x 2 legs x 2 seeds.  A
     count ratio of 1.00 is achievable with ZERO overlap between the two sets,
     and the acceptance criterion (ADR 0106) is PER CELL.
     STATISTIC: (a) precision / recall / Jaccard of the propagated certain-death
     set {cp>=5} against the truth set {c(y+1)>=5}, at lead 10 and pooled;
     (b) the PER-CELL distribution of n5_prop/n5_true over cells with
     n5_true >= 20, and the share of those cells inside +-10 %.
     NULLS: (i) N-A gives precision/recall/Jaccard all EXACTLY 0 and a per-cell
     ratio EXACTLY 0 in every cell; (ii) a WITHIN-CELL-YEAR SHUFFLE of the
     propagated flag preserves the pooled count ratio exactly by construction
     and MUST return Jaccard ~= the base rate of the truth set inside the cell-
     year, i.e. ~0.006 — this is the null that shows a count ratio has no
     identification content.
     FALSIFIER FOR W2: if Jaccard > 0.70 at lead 10 AND >= 60 % of cells with
     n5_true >= 20 are inside +-10 %, the pooled ratio is standing in for a real
     per-cell result and W2 is withdrawn.

 W3  THE PROPAGATED COUNTER IS SCORED ON THE TRUTH'S SURVIVORS, SO IT IS
     ALLOWED TO REACH AND EXCEED THE HARD-KILL VALUE WITHOUT CONSEQUENCE.
     `mortality_tree_ind.c:134-136`: `if (bm_inc_counter >= BM_INC_COUNTER_MAX)
     mort = 1;` with BM_INC_COUNTER_MAX = 5 (`:22`).  So in the C a stem that
     reaches 5 DIES that year; a truth row with c>=5 must be the LAST row of its
     chain.  The rollout instead walks each arm's counter along the truth's own
     roster, so a propagated cp can hit 5 and keep going to 6, 7, ... on a stem
     the C kept alive — a state the C cannot produce, and in a free-running
     rollout that stem would have been removed, changing the stand.
     STATISTIC: (a) share of TRUTH rows with c(y+1)>=5 that are NON-terminal in
     their chain; (b) count/share of propagated rows with cp>=5 while the stem
     is non-terminal in truth (an invented removal with no consequence) and with
     cp>=6 (a value the C cannot hold); (c) max cp.
     NULL / DERIVED VALUE: (a) MUST be ~0.000 if my reading of the hard kill is
     right.  Non-zero (a) refutes MY reasoning, not the finding, and I withdraw
     W3 and report that instead.
     FALSIFIER FOR W3: if (a) is ~0 and (b) is < 1 % of the propagated
     certain-death set, the leakage is cosmetic and W3 is withdrawn.

 W4  IS THE M1-vs-M3 GAP INSIDE THE FOLD-TO-FOLD SPREAD?
     The finding reports "adding the exactly recovered hidden state buys almost
     nothing: recall 0.907188 vs 0.902341" — a 0.0048 difference quoted to six
     decimals with no error bar, from 5 folds over 674 cells.
     STATISTIC: per-fold recall for each ladder arm; the across-fold standard
     deviation and the standard error of the 5-fold mean.
     FALSIFIER FOR W4: if the 0.0048 gap exceeds 2 standard errors of the
     fold mean, it is resolvable and W4 is withdrawn.

BASIS (trap 3, restated)
  674-cell shared sample (Cell % 100 == 0), both forcing legs, both seeds, 25
  patches, the above-5 m emitted stem population, the five P0 suspect blocks
  excluded.  NOT the acceptance criterion's 54 020 tree-bearing cells / both
  scenarios / the response between them.  Two seeds POOLED, so no number here is
  scored against the C's own two-run spread.  Nothing here is area-weighted and
  nothing here is an acceptance verdict.
================================================================================
"""

T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:7.1f}s]", *a, flush=True)


def binstats(y, p, thr=0.5):
    return H.binstats(y, p, thr)


def fmt(name, b):
    return (f"   {name:44s} acc={b['acc']:.4f} bal={b['bal']:.4f} "
            f"recall={b['recall']:.4f} fpr={b['fpr']:.4f} prec={b['prec']:.4f}")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    print(PREREG, flush=True)
    if limit:
        log(f"*** SMOKE: first {limit} cells ***")
    log(f"polars={pl.__version__} numpy={np.__version__}")

    Q, climcols = V.build_pairs(limit)
    Q = Q.with_columns(
        _d_agb=pl.col("agb_1") - pl.col("agb"),
        _d_vegc=pl.col("vegc_1") - pl.col("vegc"),
        _d_H=pl.col("Height_1") - pl.col("Height"),
        _d_LAI=pl.col("LAI_1") - pl.col("LAI"),
        _d_fpc=pl.col("fpc_ind_1") - pl.col("fpc_ind"),
        _d_npp=pl.col("npp_1") - pl.col("npp"),
    )
    truth1 = Q["c2b_1"].to_numpy()
    prev = Q["c2b"].to_numpy()
    lab = (truth1 >= 1).astype(np.int8)
    cellv = Q["Cell"].to_numpy()
    log(f"pairs={Q.height}  prevalence P[c(y+1)>=1]={lab.mean():.6f} "
        f"(finding: 0.134790)")

    # -------------------------------------------------------------- nulls
    log("\n" + "=" * 78)
    log("NULL LADDER (each against the value it MUST return)")
    log("=" * 78)
    log(f"   derived: N-A accuracy MUST equal P[c(y+1)==0] = {1 - lab.mean():.6f}")
    log(fmt("N-A  c==0 forever", binstats(lab, np.zeros(lab.size))))
    log(fmt("N-B  sign persistence (c(y)>=1)", binstats(lab, (prev >= 1).astype(float))))
    dagb = Q["_d_agb"].to_numpy()
    dvegc = Q["_d_vegc"].to_numpy()
    log(fmt("N-C  perfect agb sign rule (ORACLE)", binstats(lab, (dagb < 0).astype(float))))
    log(fmt("N-C' perfect vegc sign rule (ORACLE)", binstats(lab, (dvegc < 0).astype(float))))

    # ---------------------------------------------------- W1 feature ladder
    log("\n" + "=" * 78)
    log("W1 — is the biomass 'ceiling' a ceiling, or just one fixed rule?")
    log("=" * 78)
    import lightgbm as lgb

    f_y = [*[c for c in V.STEMCOLS if c not in ("mort_npp", "mort_water")],
           "n_stems", "agb_sum", "npp_sum", "lai_stand", "h_max", "h_mean",
           "age_mean", "fpc", "Wooddens_median", "Type", *climcols]
    f_clim1 = [f"{c}_1" for c in climcols]
    f_st1 = [f"{c}_1" for c in V.NXT_STEM]
    LADDER = {
        "L0 single feature _d_agb": ["_d_agb"],
        "L1 biomass only (agb,vegc @y,y+1,d)": ["agb", "vegc", "agb_1", "vegc_1",
                                                "_d_agb", "_d_vegc"],
        "L2 L1 + printed geometry": ["agb", "vegc", "agb_1", "vegc_1", "_d_agb",
                                     "_d_vegc", "Height", "LAI", "fpc_ind",
                                     "Height_1", "LAI_1", "fpc_ind_1",
                                     "_d_H", "_d_LAI", "_d_fpc"],
        "L3 = the finding's full M3": (f_y + f_clim1 + f_st1
                                       + ["_d_agb", "_d_vegc", "_d_H", "_d_LAI",
                                          "_d_npp"]),
    }
    fold = ((cellv // 100) % 5).astype(np.int64)
    ncpu = int(os.environ.get("SLURM_CPUS_PER_TASK", "16"))
    log(f"folds by cell (the finding's own scheme), n_jobs={ncpu}")
    for c in ("mort_npp_1", "mort_water_1", "mort_npp", "mort_water"):
        for nm, fs in LADDER.items():
            assert c not in fs, f"LEAK: {c} in {nm}"
    log("   leak assertion passed: no counter-carrying hazard column in any arm")

    oof, foldrec = {}, {}
    for nm, feats in LADDER.items():
        X = Q.select(feats).to_numpy().astype(np.float32)
        nnan = int(np.isnan(X).sum())
        ninf = int(np.isinf(X).sum())
        pr = np.zeros(lab.size)
        fr = []
        for k in range(5):
            tr, te = fold != k, fold == k
            sub = np.where(tr)[0]
            if sub.size > 4_000_000:
                sub = sub[:: max(1, sub.size // 4_000_000)]
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.08,
                                   num_leaves=127, min_child_samples=200,
                                   n_jobs=ncpu, verbose=-1)
            m.fit(X[sub], lab[sub])
            pr[te] = m.predict_proba(X[te])[:, 1]
            fr.append(binstats(lab[te], pr[te])["recall"])
        oof[nm] = pr
        foldrec[nm] = fr
        b = binstats(lab, pr)
        log(fmt(nm, b) + f"   [nan={nnan} inf={ninf} in X]")
        del X

    # ------------------------------------------------------------ W4 spread
    log("\n" + "=" * 78)
    log("W4 — per-fold recall spread")
    log("=" * 78)
    for nm, fr in foldrec.items():
        a = np.array(fr)
        log(f"   {nm:44s} folds={np.round(a, 4).tolist()} "
            f"sd={a.std(ddof=1):.4f} sem={a.std(ddof=1) / np.sqrt(5):.4f}")

    # ------------------------------------------- rollout for W2 / W3 on L3
    log("\n" + "=" * 78)
    log("W2 + W3 — the certain-death set: identification, per cell, and the")
    log("           counterfactually impossible propagation past the hard kill")
    log("=" * 78)
    S, perm, ch, first, lead = V.chains(Q)
    truth1S = S["c2b_1"].to_numpy()
    prevS = prev[perm]
    cellS = S["Cell"].to_numpy()
    yrS = S["Year"].to_numpy()
    legS = S["leg"].to_numpy()
    seedS = S["seed"].to_numpy()
    cinit = np.zeros(ch.size, dtype=np.int64)
    cinit[first] = prevS[first]

    # (W3a) is a truth row with c>=5 terminal in its chain?
    last_in_chain = np.ones(ch.size, dtype=bool)
    last_in_chain[:-1] = ch[:-1] != ch[1:]
    t5 = truth1S >= 5
    log(f"   truth rows with c(y+1)>=5: {int(t5.sum())}  of which NON-terminal "
        f"in their chain: {int((t5 & ~last_in_chain).sum())} "
        f"({(t5 & ~last_in_chain).sum() / max(t5.sum(), 1) * 100:.3f} %)")
    log("      (derived: MUST be ~0 -- the C sets mort=1 at counter>=5, so the")
    log("       stem dies that year and cannot appear again)")

    arms = {"N-A c==0 forever": np.zeros(ch.size),
            "N-C perfect-agb sign rule": (dagb[perm] < 0).astype(float)}
    for nm in LADDER:
        arms[nm] = (oof[nm][perm] >= 0.5).astype(float)

    rows, percell = [], []
    for nm, pr in arms.items():
        cp = H.runlength_init(ch, pr.astype(np.int8), cinit)
        for lo, hi in ((1, 1), (5, 5), (10, 10), (20, 20), (1, 200)):
            m = (lead >= lo) & (lead <= hi)
            if m.sum() < 200:
                continue
            a, b = t5[m], cp[m] >= 5
            inter = int(np.sum(a & b))
            rows.append(dict(
                arm=nm, lead=f"{lo}-{hi}" if lo != hi else str(lo), n=int(m.sum()),
                n5_true=int(a.sum()), n5_prop=int(b.sum()),
                ratio_c5=(int(b.sum()) / int(a.sum())) if a.sum() else float("nan"),
                prec5=inter / max(int(b.sum()), 1),
                rec5=inter / max(int(a.sum()), 1),
                jaccard=inter / max(int(a.sum()) + int(b.sum()) - inter, 1),
                cp_max=int(cp[m].max()),
                imposs_ge6=int(np.sum(cp[m] >= 6)),
                invented_nonterminal=int(np.sum((cp[m] >= 5) & ~a & ~last_in_chain[m])),
            ))
        # W2b: per-cell ratio, pooled over all leads
        df = pl.DataFrame(dict(Cell=cellS, t5=t5.astype(np.int64),
                               p5=(cp >= 5).astype(np.int64)))
        g = df.group_by("Cell").agg(pl.col("t5").sum(), pl.col("p5").sum())
        g = g.filter(pl.col("t5") >= 20)
        rr = (g["p5"] / g["t5"]).to_numpy()
        percell.append(dict(
            arm=nm, n_cells=g.height,
            med=float(np.median(rr)) if rr.size else float("nan"),
            q10=float(np.quantile(rr, 0.10)) if rr.size else float("nan"),
            q90=float(np.quantile(rr, 0.90)) if rr.size else float("nan"),
            frac_within_10pct=float(np.mean(np.abs(rr - 1) <= 0.10)) if rr.size else 0.0,
            frac_within_25pct=float(np.mean(np.abs(rr - 1) <= 0.25)) if rr.size else 0.0,
        ))

    # W2 null (ii): within-cell-year shuffle of the BEST arm's propagated flag
    rng = np.random.default_rng(20260902)
    best = "L3 = the finding's full M3"
    cp_best = H.runlength_init(ch, arms[best].astype(np.int8), cinit)
    grp = pl.DataFrame(dict(leg=legS, seed=seedS, Cell=cellS, Year=yrS,
                            f=(cp_best >= 5).astype(np.int64),
                            u=rng.random(ch.size))).with_row_index("i")
    # shuffle f within (leg,seed,Cell,Year): sort by u inside group, keep counts
    sh = grp.with_columns(
        f_sh=pl.col("f").sort_by("u").over(["leg", "seed", "Cell", "Year"])
    ).sort("i")["f_sh"].to_numpy().astype(bool)
    inter = int(np.sum(t5 & sh))
    log(f"\n   W2 NULL (within cell-year shuffle of the best arm's flag): "
        f"n_prop={int(sh.sum())} (count ratio preserved by construction: "
        f"{sh.sum() / max(t5.sum(), 1):.4f}), "
        f"precision={inter / max(int(sh.sum()), 1):.4f}, "
        f"recall={inter / max(int(t5.sum()), 1):.4f}, "
        f"jaccard={inter / max(int(t5.sum()) + int(sh.sum()) - inter, 1):.4f}")
    log(f"      base rate of the truth set = {t5.mean():.6f} "
        "(the value the shuffle null must return for precision)")

    R = pl.DataFrame(rows)
    with pl.Config(tbl_rows=100, tbl_width_chars=260, tbl_cols=20):
        log("\n" + str(R))
    R.write_csv(os.path.join(OUT, "verify_b1b_certain_death.csv"))
    PC = pl.DataFrame(percell)
    with pl.Config(tbl_rows=40, tbl_width_chars=200):
        log("\nPER-CELL certain-death count ratio (cells with n5_true>=20):")
        log(str(PC))
    PC.write_csv(os.path.join(OUT, "verify_b1b_percell.csv"))

    st = pl.DataFrame([dict(arm=nm, **binstats(lab, oof[nm])) for nm in LADDER]
                      + [dict(arm="N-A", **binstats(lab, np.zeros(lab.size))),
                         dict(arm="N-B", **binstats(lab, (prev >= 1).astype(float))),
                         dict(arm="N-C agb", **binstats(lab, (dagb < 0).astype(float))),
                         dict(arm="N-C' vegc", **binstats(lab, (dvegc < 0).astype(float)))])
    st.write_csv(os.path.join(OUT, "verify_b1b_ladder.csv"))
    log(f"\nwrote {OUT}/verify_b1b_{{ladder,certain_death,percell}}.csv")
    log(f"DONE in {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
