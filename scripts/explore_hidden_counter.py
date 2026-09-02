#!/usr/bin/env python
"""B1 — is LPJmL-FIT's hidden per-tree growth-failure counter OBSERVABLE?

Line X exploration probe (read-only; writes only under /p/tmp/jamirp/X_explore).

Three questions, in order:
  (1) can `bm_inc_counter` be read correctly out of the rung-2 roster dumps?
      -> self-gated by recomputing mort_water / mort_npp / mort_age / mort_prob
         from the dumped columns + the COMMITTED per-PFT table.
  (2) is it RECOVERABLE from the globally emitted 29-column `ind` table?
      (2a) run-length of consecutive non-positive biomass increments
      (2b) algebra on the emitted `mort_npp` and `Wooddens`
  (3) how much does it matter (hazard mass, deaths, trait association)?

Stages (positional arg 1): dump | global | both
"""

from __future__ import annotations

import math
import os
import sys
import time

import numpy as np
import polars as pl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "/p/tmp/jamirp/X_explore"
DUMPROOT = "/p/tmp/jamirp/S_rung2"
TABLE_A = os.path.join(OUT, "prep_paired_stems.parquet")
SUSPECT = os.path.join(OUT, "prep_suspect_cell_blocks.csv")
PARAMS = os.path.join(REPO, "test/testitems/references/S_pft_mortality_params.csv")

# ADR 0035: per-PFT Lambert-Beer extinction, needleleaved 0.45 / broadleaved 0.59
K_BEER = {0: 0.59, 1: 0.45, 2: 0.59, 3: 0.59, 4: 0.45, 5: 0.59, 6: 0.45}

# the 12 rung-2 cells with a full modern arm set (P0/agent-S1 coverage census)
CELLS = [12045, 12235, 18371, 22732, 22990, 32628, 42490, 42757, 42973, 44048, 52059, 57087]
LEGS = ["historic", "ssp370"]

# derived a priori from mortality_tree_ind.c (see PREREG): the r = mort_npp/mort_max
# intervals for successive counter values are DISJOINT WITH GAPS.  Forbidden closed
# bands, in r units:
FORBIDDEN = [(1.0, 5.0 / 3.0), (2.0, 2.5), (3.0, 10.0 / 3.0), (4.0, 25.0 / 6.0)]

PREREG = r"""
================================================================================
PRE-REGISTRATION  —  B1: is the hidden per-tree growth-failure counter observable?
   printed BEFORE any result is computed.  Do not read past this block until you
   have read this block.
================================================================================

THE QUESTION
  LPJmL-FIT carries a private per-tree integer `bm_inc_counter` c (the run of
  consecutive years with non-positive individual biomass increment).  It
  MULTIPLIES two of the four mortality hazards and hard-kills at c >= 5.  It is
  NOT a column of the globally emitted 29-column `ind` table (its print line is
  commented out at fwriteoutput_ind.c:96).  Q: is it (1) readable from the
  rung-2 dumps, (2) RECOVERABLE from the global table, (3) how much does it
  matter?

THE C CODE THIS PROBE PORTS  (/home/jamirp/lpjml56fit/src/tree/mortality_tree_ind.c)
  bm_delta = pft->bm_inc.carbon/pft->nind - turnover_ind          (:66, :69)
  if (tree->age==1) tree->bm_inc_counter = 0;                     (:70-71)
  if (bm_delta<0) counter += 1; else counter = 0;                 (:73-80)
  mort_max = pow(10, wdmort_1 + wdmort_2/(wooddens/1e6))          (:98)
  mort_npp = min(1, mort_max/(1+KMORT_2*exp(k_mort*bm_delta/leafarea_real))
                       * (1+counter))     [ =1 if leafarea_real<=1e-6 ]  (:101-107)
  mort_age = min(1, KMORTBG_LNF*(q+1)/longevity * (age/longevity)^q)     (:113)
  mort_water = min(1, mort_water_factor*water_stress/365 * (1+counter))  (:118)
  mort_temp  = min(1, mort_temp_factor *temp_stress /365)                (:122)
  mort  = min(1, mort_npp+mort_age+mort_water+mort_temp);  =1 if counter>=5;
          =1 if leaf_c < leaf_carbon_sapl                          (:126-138)
  NOTE annual_tree.c:65 does `tree->age++` AFTER mortality_tree_ind, so the
  DUMPED/EMITTED age is post-increment and the hazard used age-1 (ADR 0031).

STATISTIC 1 (Q1, the column-reading self-gate)
  max |recomputed - dumped| for mort_water, mort_npp, mort_age, mort_prob, using
  ONLY dumped columns + test/testitems/references/S_pft_mortality_params.csv.
  MUST RETURN: <= 1e-12 absolute on rows where the quantity is not at its cap.
  The dumps print full double precision (17 sig figs), so there is no print
  floor here; a residual above 1e-12 means I am reading the wrong column
  (trap 1, the silent #H-header-to-field offset) or the wrong parameter.
  SECOND, INDEPENDENT offset guard (trap 5p2): `temp_stress` must be CONSTANT
  within every (year, patch, pft_id) group.  MUST RETURN: 0 groups with spread.

STATISTIC 2a (Q2a, the run-length route)
  exact-integer agreement rate of chat_2a vs the dumped counter on `grow`-phase
  tree stem-years, where chat_2a is the run length of consecutive years with a
  non-positive year-over-year change in a GLOBALLY EMITTED biomass column
  (agb; vegc), paired on (patch, pft_id, treeidx) = the global table's
  (Patch, Type, ID).  Reported (i) overall, (ii) on the c >= 1 subset, (iii) on
  the top decile of hazard mass, (iv) under the global table's own >5 m
  emission cut, (v) split by whether the stem has a "sync point" (an observed
  non-negative increment earlier in the same unbroken observation run), because
  without one the run length is only a LOWER bound.

STATISTIC 2b (Q2b, the algebraic route)
  Write r = mort_npp/mort_max, both emitted (mort_npp is column 22 of the ind
  table; mort_max is a closed form in the emitted Wooddens and Type).  Then
      r = (1+c)/D,   D = 1 + 0.2*exp(0.01*bm_delta/leafarea_real) > 1.
  DERIVED A PRIORI, and this is the whole content of route 2b:
      c = 0  <=>  bm_delta >= 0  <=>  D >= 1.2  <=>  r <= 1/1.2 = 0.833333
      c >= 1 <=>  bm_delta <  0  <=>  1 < D < 1.2  <=>  (1+c)/1.2 < r < 1+c
  so the admissible r-intervals for c = 0,1,2,3,4 are
      (0, 0.8333] , (1.6667, 2) , (2.5, 3) , (3.3333, 4) , (4.1667, 5)
  which are DISJOINT AND SEPARATED BY GAPS.  Therefore
      c = ceil(r) - 1        EXACTLY, on any row where mort_npp is not capped.
  Statistic: exact-integer agreement of ceil(r)-1 vs the dumped counter, on the
  informative rows (mort_npp < 1), plus the share of rows that are informative.
  TRUTH-FREE VALIDATION available at global scale with no dump at all: the
  fraction of rows whose r falls in a FORBIDDEN band [1, 1.6667] u [2, 2.5] u
  [3, 3.3333] u [4, 4.1667].  MUST RETURN: 0.000 %.  A non-zero rate refutes
  either the algebra or the column reading.
  Also tested: is `leafarea_real` itself recoverable from the emitted LAI,
  fpc_ind and the per-PFT extinction coefficient?  ADR 0035 gives
  crownarea*nind = fpc_ind/(1-exp(-k*LAI)) and lai_tree.c:18 gives
  LAI = leaf_c*sla/crownarea, so leafarea_real*nind = LAI*fpc_ind/(1-exp(-k*LAI)).
  MUST RETURN: relative residual <= 1e-12 in dump space (full precision).

THE NULLS  (derived before the run; a skill number without these is worthless)
  NULL-0  "chat = 0 everywhere".  Its exact-integer agreement rate MUST equal
          the prevalence of c = 0 in the scored population.  ADR 0093 puts the
          global prevalence of c >= 1 at 11.69 %, so NULL-0 must return
          approximately 0.883.  Both are printed side by side.  A reconstruction
          that does not beat NULL-0 by a wide margin is worthless.
  NULL-0b "chat = 0 everywhere" on the c >= 1 subset MUST return exactly 0.000.
  NULL-1  the counter-blind hazard: recomputing mort_npp and mort_water with
          c forced to 0 must NOT reproduce the dumped values.  Reported as the
          nominated-hazard-mass ratio sum(nind*h_c=0)/sum(nind*mort_prob); a
          value of 1.000 would mean the counter is inert here and would kill
          Q3.  ADR 0243 measured 0.7834 -> 0.6847 for the counter's share, so
          this must land materially below 1.
  NULL-2  route 2b's lower bound c >= ceil(r)-1 is a DERIVED INEQUALITY, not a
          fit; its violation rate MUST be 0.000 %.  It is a gate, not a result.
  NULL-3  route 2a's `pairable`/sync bookkeeping: a stem-year whose previous
          year is absent has NO increment, so chat_2a there MUST be reported
          separately and never counted as a match.

THE FALSIFIER  (stated before the run; if this fires I say the counter is LATENT)
  I will conclude the counter is NOT recoverable from global observables, and
  must be carried as a latent state axis (the published remedy being the
  latent-frailty / individual-heterogeneity extension of an integral projection
  model), if EITHER
    (F1) route 2b's exact-integer agreement on informative rows is < 0.99 (it is
         a derived identity, so anything below that means the derivation is
         wrong), AND route 2a's exact-integer agreement on the c >= 1 subset is
         < 0.50 -- i.e. worse than a coin flip on the stems that carry the
         mortality; OR
    (F2) the informative share of route 2b is < 0.50 AND route 2a on the c >= 1
         subset is < 0.50 -- i.e. the exact route exists but covers less than
         half the corpus and the fallback fails.
  If route 2b is exact and covers essentially the whole corpus, the answer is
  RECOVERABLE and the ADR-0093 objection to a learned per-stem operator weakens
  to a state-content requirement rather than an impossibility.

BASIS DISCLOSURE (trap 3)
  Q1/Q2 scoring is on 12 rung-2 cells x 2 forcing legs x the REC arm x seed 1 --
  NOT on the acceptance criterion's 54 020 tree-bearing cells.  The global-scale
  arm is the 674-cell shared sample (Cell % 100 == 0), both legs, both seeds.
  Neither is the acceptance basis; no number here is an acceptance verdict.
  The rung-2 REC arm is pure OBSERVATION (no emulator decision), so its roster is
  LPJmL-FIT's own; but it is a single-cell re-run, so per ADR 0041 it is NOT a
  per-cell replica of the global run and the dump roster cannot be joined to the
  global table stem by stem.  That is why the truth-scoring lives entirely in
  dump space and the global table is used for scale, incidence and the
  truth-free gates.
================================================================================
"""


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- parameters
def load_params() -> dict[int, dict[str, float]]:
    rows = pl.read_csv(PARAMS, comment_prefix="#")
    out = {}
    for r in rows.iter_rows(named=True):
        if int(r["pft_id"]) <= 6:
            out[int(r["pft_id"])] = {k: v for k, v in r.items() if k != "name"}
    return out


def leaf_carbon_sapl(p: dict[str, float], sla: np.ndarray) -> np.ndarray:
    kpr = p["kpr"]
    return (
        p["lai_sapl"]
        * p["allom1"]
        * p["wood_sapl"] ** (kpr * 0.5)
        * (4.0 * sla / math.pi / p["k_latosa"]) ** (kpr * 0.5)
        / sla
    ) ** (2.0 / (2.0 - kpr))


# ---------------------------------------------------------------- dump reader
DUMP_COLS = [
    "year", "patch", "treeidx", "pft_id", "age", "sla", "wooddens", "height",
    "crownarea", "nind", "fpc", "leaf_c", "sapwood_c", "heartwood_c", "root_c",
    "sapwood_bg_c", "heartwood_bg_c", "debt_c", "bm_inc_c", "water_stress",
    "temp_stress", "bm_inc_counter", "isdead", "mort_prob", "mort_npp",
    "mort_age", "mort_water", "mort_temp", "bm_delta", "leafarea_real",
]


def parse_dump(path: str) -> dict[str, dict[str, np.ndarray]]:
    """Return {phase: {col: array}} for phases grow and mort."""
    names = None
    with open(path) as f:
        for line in f:
            if line.startswith("#H T"):
                names = line.split()[2:]
                break
    if names is None:
        raise RuntimeError(f"no '#H T' header in {path}")
    # trap 1: header name k lives at record FIELD k+1 (field 0 is the 'T' tag)
    pos = {n: i + 1 for i, n in enumerate(names)}
    missing = [c for c in DUMP_COLS if c not in pos]
    if missing:
        raise RuntimeError(f"dump {path} lacks columns {missing}")
    take = [pos[c] for c in DUMP_COLS]
    buf: dict[str, list] = {"grow": [], "mort": []}
    with open(path) as f:
        for line in f:
            if line[0] != "T":
                continue
            fs = line.split()
            ph = fs[1]
            if ph == "grow" or ph == "mort":
                buf[ph].append([fs[i] for i in take])
    out = {}
    for ph, rows in buf.items():
        if not rows:
            out[ph] = {c: np.zeros(0) for c in DUMP_COLS}
            continue
        arr = np.array(rows, dtype=np.float64)
        out[ph] = {c: arr[:, i] for i, c in enumerate(DUMP_COLS)}
    return out


def dkey(d: dict[str, np.ndarray]) -> np.ndarray:
    y = d["year"].astype(np.int64)
    p = d["patch"].astype(np.int64)
    t = d["pft_id"].astype(np.int64)
    i = d["treeidx"].astype(np.int64)
    return (((y * 100 + p) * 10 + t) * 10_000_000) + i


# ---------------------------------------------------------------- hazard port
def port_hazards(d: dict[str, np.ndarray], P: dict, counter: np.ndarray):
    """Recompute the four hazards + mort_prob from dumped columns."""
    n = d["year"].size
    mmax = np.zeros(n)
    mwf = np.zeros(n)
    mtf = np.zeros(n)
    longv = np.zeros(n)
    lcs = np.zeros(n)
    pid = d["pft_id"].astype(int)
    for k, p in P.items():
        m = pid == k
        if not m.any():
            continue
        mmax[m] = 10.0 ** (p["wdmort_1"] + p["wdmort_2"] / (d["wooddens"][m] / 1e6))
        mwf[m] = p["mort_water_factor"]
        mtf[m] = p["mort_temp_factor"]
        longv[m] = p["longevity"]
        lcs[m] = leaf_carbon_sapl(p, d["sla"][m])
    p0 = P[next(iter(P))]
    kmort, kmort2 = p0["k_mort"], p0["kmort_2"]
    lnf, q, nday = p0["kmortbg_lnf"], p0["kmortbg_q"], p0["ndayyear"]
    lar = np.maximum(d["leafarea_real"], 1e-300)
    g = np.where(d["leafarea_real"] > 0, d["bm_delta"] / lar, 0.0)
    raw_npp = mmax / (1.0 + kmort2 * np.exp(kmort * g)) * (1.0 + counter)
    mnpp = np.where(d["leafarea_real"] > 1e-6, np.minimum(raw_npp, 1.0), 1.0)
    age_pre = d["age"] - 1.0  # annual_tree.c:65 increments AFTER the hazard
    mage = np.minimum(1.0, lnf * (q + 1.0) / longv * (age_pre / longv) ** q)
    mwat = np.minimum(1.0, mwf * d["water_stress"] / nday * (1.0 + counter))
    mtmp = np.minimum(1.0, mtf * d["temp_stress"] / nday)
    mort = np.minimum(1.0, mnpp + mage + mwat + mtmp)
    mort = np.where(counter >= p0["bm_inc_counter_max"], 1.0, mort)
    mort = np.where(d["leaf_c"] < lcs, 1.0, mort)
    return dict(mort_max=mmax, mort_npp=mnpp, raw_npp=raw_npp, mort_age=mage,
                mort_water=mwat, mort_temp=mtmp, mort_prob=mort)


# ---------------------------------------------------------------- route 2b
def route_2b(mort_npp: np.ndarray, mort_max: np.ndarray):
    r = mort_npp / mort_max
    c = np.maximum(0, np.ceil(r - 1e-9).astype(np.int64) - 1)
    informative = mort_npp < 1.0 - 1e-12
    forbidden = np.zeros(r.size, dtype=bool)
    for lo, hi in FORBIDDEN:
        forbidden |= (r >= lo) & (r <= hi)
    return r, c, informative, forbidden


def g6(x: np.ndarray) -> np.ndarray:
    """emulate the ind TXT writer's %g = 6 significant digits"""
    return np.array([float(f"{v:.6g}") for v in x])


# ---------------------------------------------------------------- route 2a
def runlength_vec(key_stem: np.ndarray, delta: np.ndarray, have: np.ndarray):
    """Vectorised twin of runlength(); gated against it on the dump stage."""
    n = delta.size
    idx = np.arange(n)
    new_stem = np.ones(n, dtype=bool)
    new_stem[1:] = key_stem[1:] != key_stem[:-1]
    sync_event = have & (delta >= 0.0)
    reset = new_stem | (~have) | sync_event
    last_reset = np.maximum.accumulate(np.where(reset, idx, -1))
    chat = idx - last_reset
    break_event = new_stem | (~have)
    last_sync = np.maximum.accumulate(np.where(sync_event, idx, -1))
    last_break = np.maximum.accumulate(np.where(break_event, idx, -1))
    synced = (last_sync >= 0) & (last_sync >= last_break)
    return chat.astype(np.int64), synced


def runlength(key_stem: np.ndarray, year: np.ndarray, delta: np.ndarray,
              have: np.ndarray):
    """chat = run length of consecutive non-positive increments.

    key_stem : per-stem identity (already sorted by (key_stem, year))
    delta    : increment INTO this year (nan where unavailable)
    have     : True where an increment into this year exists (prev year present
               AND observable)
    Returns (chat, synced) where synced marks rows for which a non-negative
    increment has already been observed in the current unbroken run -- only
    those rows are exactly determined; the rest are lower bounds.
    """
    n = year.size
    chat = np.zeros(n, dtype=np.int64)
    synced = np.zeros(n, dtype=bool)
    cur = 0
    syn = False
    for i in range(n):
        new_stem = i == 0 or key_stem[i] != key_stem[i - 1]
        if new_stem:
            cur = 0
            syn = False
        if not have[i]:
            # observation chain broken -> reset to the agnostic 0 and de-sync
            cur = 0
            syn = False
        else:
            if delta[i] < 0.0:
                cur = cur + 1
            else:
                cur = 0
                syn = True
        chat[i] = cur
        synced[i] = syn
    return chat, synced


def conf_matrix(truth: np.ndarray, pred: np.ndarray, kmax: int = 6) -> str:
    lines = ["      pred->  " + "".join(f"{j:>9d}" for j in range(kmax)) + f"     >={kmax}"]
    for i in range(kmax):
        row = [int(((truth == i) & (pred == j)).sum()) for j in range(kmax)]
        hi = int(((truth == i) & (pred >= kmax)).sum())
        lines.append(f"  true c={i:<3d}   " + "".join(f"{v:>9d}" for v in row) + f"{hi:>9d}")
    hi_t = truth >= kmax
    if hi_t.any():
        row = [int((hi_t & (pred == j)).sum()) for j in range(kmax)]
        lines.append(f"  true c>={kmax:<2d}  " + "".join(f"{v:>9d}" for v in row)
                     + f"{int((hi_t & (pred >= kmax)).sum()):>9d}")
    return "\n".join(lines)


# ================================================================ STAGE dump
def stage_dump():
    P = load_params()
    log("\n" + "=" * 78)
    log("STAGE dump — Q1 (read the counter) + Q2 (recover it) + Q3 (does it matter)")
    log("  arm=REC (pure observation = LPJmL-FIT's own roster), mode=predict, seed=1")
    log("=" * 78)

    parts = []
    gates = []
    for leg in LEGS:
        for cell in CELLS:
            p = os.path.join(
                DUMPROOT, f"S_r2s_{leg}_c{cell}_REC_predict_s1_dump", "roster_rank0000.txt"
            )
            if not os.path.exists(p):
                log(f"  MISSING {p}")
                continue
            t0 = time.time()
            d = parse_dump(p)
            gr, mo = d["grow"], d["mort"]
            if gr["year"].size == 0:
                log(f"  EMPTY {leg} c{cell}")
                continue
            c_true = gr["bm_inc_counter"]
            assert np.all(c_true == np.round(c_true)), "counter is not integral"
            c_true = c_true.astype(np.int64)

            # ---- G1: hazard self-gate (the column-reading proof)
            h = port_hazards(gr, P, c_true.astype(np.float64))
            unc = h["raw_npp"] <= 1.0
            res_npp = np.abs(h["mort_npp"] - gr["mort_npp"])
            res_wat = np.abs(h["mort_water"] - gr["mort_water"])
            res_age = np.abs(h["mort_age"] - gr["mort_age"])
            res_tmp = np.abs(h["mort_temp"] - gr["mort_temp"])
            res_prb = np.abs(h["mort_prob"] - gr["mort_prob"])
            # age semantics control: the WRONG (post-increment) age
            longv = np.array([P[int(k)]["longevity"] for k in gr["pft_id"]])
            p0 = P[next(iter(P))]
            mage_post = np.minimum(
                1.0, p0["kmortbg_lnf"] * (p0["kmortbg_q"] + 1) / longv
                * (gr["age"] / longv) ** p0["kmortbg_q"]
            )
            res_age_post = np.abs(mage_post - gr["mort_age"])

            # ---- G2: trap 5p2 offset guard — temp_stress constant in (y,patch,pft)
            gid = (gr["year"].astype(np.int64) * 1000 + gr["patch"].astype(np.int64) * 10
                   + gr["pft_id"].astype(np.int64))
            tg = pl.DataFrame({"g": gid, "ts": gr["temp_stress"]}).group_by("g").agg(
                (pl.col("ts").max() - pl.col("ts").min()).alias("spread")
            )
            ts_bad = int((tg["spread"] > 0).sum())

            # ---- G3: leafarea_real from the EMITTED LAI + fpc_ind + k_pft
            ca = np.maximum(gr["crownarea"], 1e-300)
            lai = np.where(gr["crownarea"] > 0, gr["leaf_c"] * gr["sla"] / ca, 0.0)
            kb = np.array([K_BEER[int(x)] for x in gr["pft_id"]])
            denom = 1.0 - np.exp(-kb * lai)
            ok = (lai > 0) & (denom > 0) & (gr["fpc"] > 0)
            la_hat = np.zeros_like(lai)
            la_hat[ok] = lai[ok] * gr["fpc"][ok] / denom[ok] / gr["nind"][ok]
            rel_la = np.zeros_like(lai)
            lr = np.maximum(gr["leafarea_real"][ok], 1e-300)
            rel_la[ok] = np.abs(la_hat[ok] - gr["leafarea_real"][ok]) / lr

            # ---- realized deaths (from the `mort` phase, matched key-for-key)
            kg, km = dkey(gr), dkey(mo)
            order = np.argsort(km)
            ins = np.searchsorted(km[order], kg)
            ins = np.clip(ins, 0, km.size - 1)
            hit = km[order][ins] == kg
            dead = np.zeros(kg.size)
            dead[hit] = mo["isdead"][order][ins[hit]]

            gates.append(dict(
                leg=leg, cell=cell, n=int(kg.size), years=int(np.ptp(gr["year"])) + 1,
                res_npp=float(res_npp[unc].max() if unc.any() else np.nan),
                res_wat=float(res_wat.max()), res_age=float(res_age.max()),
                res_tmp=float(res_tmp.max()), res_prb=float(res_prb.max()),
                res_age_postinc=float(res_age_post.max()),
                ts_groups_with_spread=ts_bad,
                rel_leafarea_from_LAI=float(rel_la[ok].max() if ok.any() else np.nan),
                death_match=float(hit.mean()),
                secs=round(time.time() - t0, 1),
            ))

            df = pl.DataFrame({
                "leg": [leg] * kg.size, "cell": np.full(kg.size, cell, dtype=np.int64),
                "year": gr["year"].astype(np.int64), "patch": gr["patch"].astype(np.int64),
                "pft": gr["pft_id"].astype(np.int64), "idx": gr["treeidx"].astype(np.int64),
                "age": gr["age"].astype(np.int64), "height": gr["height"],
                "nind": gr["nind"], "wooddens": gr["wooddens"], "sla": gr["sla"],
                "c_true": c_true, "bm_delta": gr["bm_delta"],
                "leafarea_real": gr["leafarea_real"],
                "mort_npp": gr["mort_npp"], "mort_water": gr["mort_water"],
                "mort_prob": gr["mort_prob"], "mort_max": h["mort_max"],
                "raw_npp": h["raw_npp"],
                "agbA": (gr["leaf_c"] + gr["sapwood_c"] + gr["heartwood_c"]
                         - gr["debt_c"]) * gr["nind"],
                "vegcA": (gr["leaf_c"] + gr["sapwood_c"] + gr["heartwood_c"] + gr["root_c"]
                          + gr["sapwood_bg_c"] + gr["heartwood_bg_c"] - gr["debt_c"]) * gr["nind"],
                "dead": dead,
            })
            parts.append(df)
            log(f"  {leg:9s} c{cell}  {kg.size:8d} grow stem-years  {time.time()-t0:5.1f}s")

    G = pl.DataFrame(gates)
    D = pl.concat(parts)
    G.write_csv(os.path.join(OUT, "hidden_counter_dump_gates.csv"))
    log("\n--- Q1 GATES (per dump) ---  [must be <= 1e-12 ; ts_groups_with_spread must be 0]")
    with pl.Config(tbl_cols=-1, tbl_rows=40, tbl_width_chars=250, float_precision=3):
        log(str(G))
    log("\nWORST OVER ALL DUMPS:")
    for c in ["res_npp", "res_wat", "res_age", "res_tmp", "res_prb",
              "res_age_postinc", "rel_leafarea_from_LAI"]:
        log(f"   max {c:24s} = {G[c].max():.3e}")
    log(f"   sum ts_groups_with_spread = {G['ts_groups_with_spread'].sum()}  (must be 0)")
    log(f"   min death_match           = {G['death_match'].min():.6f}")
    log(f"   total grow stem-years     = {G['n'].sum()}")

    # ================= NULL-1: the counter-blind hazard
    log("\n--- NULL-1: the counter-blind hazard (is the counter inert here?) ---")
    for leg in LEGS:
        S = D.filter(pl.col("leg") == leg)
        c = S["c_true"].to_numpy().astype(float)
        mmax = S["mort_max"].to_numpy()
        g = S["bm_delta"].to_numpy() / np.maximum(S["leafarea_real"].to_numpy(), 1e-300)
        lar = S["leafarea_real"].to_numpy()
        raw0 = mmax / (1.0 + 0.2 * np.exp(0.01 * g))
        npp0 = np.where(lar > 1e-6, np.minimum(raw0, 1.0), 1.0)
        # mort_water with c=0
        wat0 = S["mort_water"].to_numpy() / (1.0 + c)
        nind = S["nind"].to_numpy()
        # nominated hazard, counter-blind: npp0 + age + wat0 + temp, capped, NO hard kill
        base = S["mort_prob"].to_numpy() - S["mort_npp"].to_numpy() - S["mort_water"].to_numpy()
        h0 = np.minimum(1.0, npp0 + wat0 + np.maximum(base, 0.0))
        ratio = float((nind * h0).sum() / (nind * S["mort_prob"].to_numpy()).sum())
        log(f"   {leg:9s}  sum(nind*h[c=0]) / sum(nind*mort_prob) = {ratio:.4f}"
            f"   (1.000 would mean the counter is inert)")

    # ================= Q2b: the algebraic route
    log("\n--- Q2b: the ALGEBRAIC route  c = ceil(mort_npp/mort_max) - 1 ---")
    rows = []
    for leg in ["ALL"] + LEGS:
        S = D if leg == "ALL" else D.filter(pl.col("leg") == leg)
        mn = S["mort_npp"].to_numpy()
        mx = S["mort_max"].to_numpy()
        ct = S["c_true"].to_numpy()
        nind = S["nind"].to_numpy()
        mp = S["mort_prob"].to_numpy()
        # the ind TXT writer prints %g = 6 significant digits, so a global-table
        # consumer sees mort_npp and Wooddens rounded.  Arm "%g6" is that regime.
        pids = S["pft"].to_numpy().astype(int)
        w1 = np.array([P[int(p)]["wdmort_1"] for p in pids])
        w2 = np.array([P[int(p)]["wdmort_2"] for p in pids])
        mx6 = 10.0 ** (w1 + w2 / (g6(S["wooddens"].to_numpy()) / 1e6))
        for prec, mn_, mx_ in (("full", mn, mx), ("%g6", g6(mn), mx6)):
            r, c2b, info, forb = route_2b(mn_, mx_)
            lb_ok = float((c2b <= ct).mean())
            hm = nind * mp
            dec = hm >= np.quantile(hm, 0.9)
            rows.append(dict(
                leg=leg, prec=prec, n=int(ct.size),
                informative_share=float(info.mean()),
                forbidden_share=float(forb.mean()),
                lower_bound_valid=lb_ok,
                exact_all=float((c2b == ct).mean()),
                exact_informative=float((c2b[info] == ct[info]).mean()) if info.any() else np.nan,
                exact_c_ge_1=(float((c2b[ct >= 1] == ct[ct >= 1]).mean())
                              if (ct >= 1).any() else np.nan),
                exact_top_decile_hazmass=float((c2b[dec] == ct[dec]).mean()),
                null0_all=float((ct == 0).mean()),
                null0_c_ge_1=0.0,
                detect_c_ge_1=float((c2b[ct >= 1] >= 1).mean()) if (ct >= 1).any() else np.nan,
                false_pos_c_ge_1=float((c2b[ct == 0] >= 1).mean()),
            ))
    R2B = pl.DataFrame(rows)
    R2B.write_csv(os.path.join(OUT, "hidden_counter_route2b.csv"))
    with pl.Config(tbl_cols=-1, tbl_rows=20, tbl_width_chars=260, float_precision=6):
        log(str(R2B))
    S = D
    mn, mx, ct = S["mort_npp"].to_numpy(), S["mort_max"].to_numpy(), S["c_true"].to_numpy()
    _, c2b, info, _ = route_2b(mn, mx)
    log("\n  confusion matrix, route 2b (full precision, informative rows only):")
    log(conf_matrix(ct[info], c2b[info]))
    log("\n  the rows that are NOT informative (mort_npp capped at 1):")
    ni = ~info
    if ni.any():
        log(f"    n={int(ni.sum())}  ({ni.mean()*100:.4f} %)   true-c distribution: "
            + str({int(k): int(v) for k, v
                   in zip(*np.unique(ct[ni], return_counts=True), strict=True)}))
        log(f"    of those, share with leafarea_real<=1e-6: "
            f"{float((S['leafarea_real'].to_numpy()[ni] <= 1e-6).mean()):.4f}")

    # ================= Q2a: the run-length route
    log("\n--- Q2a: the RUN-LENGTH route (paired on (patch,pft,treeidx) = (Patch,Type,ID)) ---")
    rows = []
    for leg in LEGS:
        S = D.filter(pl.col("leg") == leg).sort(["cell", "patch", "pft", "idx", "year"])
        stem = (S["cell"].to_numpy().astype(np.int64) * 10_000_000_000
                + S["patch"].to_numpy() * 100_000_000
                + S["pft"].to_numpy() * 10_000_000 + S["idx"].to_numpy())
        yr = S["year"].to_numpy()
        ct = S["c_true"].to_numpy()
        ht = S["height"].to_numpy()
        nind = S["nind"].to_numpy()
        mp = S["mort_prob"].to_numpy()
        bmd = S["bm_delta"].to_numpy()
        same = np.concatenate([[False], stem[1:] == stem[:-1]])
        contig = same & (np.concatenate([[0], yr[1:] - yr[:-1]]) == 1)
        for pname, col in (("agb", "agbA"), ("vegc", "vegcA")):
            v = S[col].to_numpy()
            dv = np.full(v.size, np.nan)
            dv[1:] = v[1:] - v[:-1]
            for cut, cname in ((0.0, "FULL"), (5.0, ">5m cut")):
                vis = ht > cut
                prev_vis = np.concatenate([[False], vis[:-1]])
                have = contig & vis & prev_vis
                dvz = np.nan_to_num(dv, nan=1.0)
                chat, syn = runlength(stem, yr, dvz, have)
                chat_v, syn_v = runlength_vec(stem, dvz, have)
                assert np.array_equal(chat, chat_v), "runlength vec/loop disagree"
                assert np.array_equal(syn, syn_v), "synced vec/loop disagree"
                sel = vis  # only rows the global table would emit
                hm = nind * mp
                dec = sel & (hm >= np.quantile(hm[sel], 0.9))
                s1 = sel & (ct >= 1)
                rows.append(dict(
                    leg=leg, proxy=pname, censor=cname, n_scored=int(sel.sum()),
                    have_increment=float(have[sel].mean()),
                    synced=float(syn[sel].mean()),
                    exact_all=float((chat[sel] == ct[sel]).mean()),
                    null0_all=float((ct[sel] == 0).mean()),
                    exact_c_ge_1=float((chat[s1] == ct[s1]).mean()) if s1.any() else np.nan,
                    detect_c_ge_1=float((chat[s1] >= 1).mean()) if s1.any() else np.nan,
                    false_pos_c_ge_1=float((chat[sel & (ct == 0)] >= 1).mean()),
                    exact_top_decile_hazmass=float((chat[dec] == ct[dec]).mean()),
                    exact_synced=(float((chat[sel & syn] == ct[sel & syn]).mean())
                                  if (sel & syn).any() else np.nan),
                    exact_unsynced=(float((chat[sel & ~syn] == ct[sel & ~syn]).mean())
                                    if (sel & ~syn).any() else np.nan),
                    sign_agree_delta_vs_bmdelta=(
                        float(((dv[have] < 0) == (bmd[have] < 0)).mean())
                        if have.any() else np.nan),
                ))
    R2A = pl.DataFrame(rows)
    R2A.write_csv(os.path.join(OUT, "hidden_counter_route2a.csv"))
    with pl.Config(tbl_cols=-1, tbl_rows=40, tbl_width_chars=280, float_precision=6):
        log(str(R2A))

    # ================= Q3: does it matter?
    log("\n--- Q3: how much does the counter matter (ADR 0093 §4.4 replication) ---")
    for leg in ["ALL"] + LEGS:
        S = D if leg == "ALL" else D.filter(pl.col("leg") == leg)
        ct = S["c_true"].to_numpy()
        nind = S["nind"].to_numpy()
        mp = S["mort_prob"].to_numpy()
        dead = S["dead"].to_numpy()
        m1 = ct >= 1
        log(f"  {leg:9s} n={ct.size:8d}"
            f"  share stems c>=1 = {m1.mean()*100:6.2f} %"
            f"  share of hazard mass = {(nind[m1]*mp[m1]).sum()/(nind*mp).sum()*100:6.2f} %"
            f"  share of DEATHS = {dead[m1].sum()/max(dead.sum(),1)*100:6.2f} %"
            f"  (ADR 0093: 11.69 / 44.8 / 37.8)")
    log("\n  E[Wooddens | c] by PFT (stem mean; ADR 0093: +19 % over c=0..5)")
    tab = (D.group_by(["pft", "c_true"])
            .agg(pl.len().alias("n"), pl.col("wooddens").mean().alias("wd"))
            .sort(["pft", "c_true"]))
    with pl.Config(tbl_rows=80, tbl_width_chars=140, float_precision=1):
        log(str(tab))
    log("\n  one-year selection differential mean(Wooddens|survived)-mean(Wooddens|all),")
    log("  raw vs COUNTER-STRATIFIED (the sign-reversal test):")
    for pft in sorted(D["pft"].unique().to_list()):
        S = D.filter(pl.col("pft") == pft)
        wd = S["wooddens"].to_numpy()
        alive = S["dead"].to_numpy() < 0.5
        ct = S["c_true"].to_numpy()
        if alive.sum() == 0 or wd.size < 50:
            continue
        raw = wd[alive].mean() - wd.mean()
        num = 0.0
        den = 0.0
        for k in np.unique(ct):
            m = ct == k
            if m.sum() < 5 or (alive & m).sum() == 0:
                continue
            num += m.sum() * (wd[alive & m].mean() - wd[m].mean())
            den += m.sum()
        strat = num / den if den > 0 else np.nan
        log(f"    pft {pft}: n={wd.size:7d}  raw S = {raw:+10.1f}"
            f"   within-counter S = {strat:+10.1f}"
            f"   {'SIGN FLIP' if np.isfinite(strat) and raw*strat < 0 else ''}")

    D.select(["leg", "cell", "year", "patch", "pft", "idx", "age", "height", "nind",
              "wooddens", "c_true", "bm_delta", "mort_npp", "mort_max", "mort_prob",
              "dead"]).write_parquet(os.path.join(OUT, "hidden_counter_dump_stems.parquet"))
    log(f"\nwrote {OUT}/hidden_counter_dump_stems.parquet ({D.height} rows)")


# ============================================================== STAGE global
def stage_global():
    P = load_params()
    log("\n" + "=" * 78)
    log("STAGE global — route 2b + route 2a on the GLOBALLY EMITTED table")
    log("  basis: Table A (prep_paired_stems.parquet) = 674 cells (Cell%100==0),")
    log("         both legs, both seeds. NOT the acceptance basis (54 020 cells).")
    log("  NO dump truth exists here (ADR 0041: a single-cell re-run is not a")
    log("  replica of the global run), so this stage carries the TRUTH-FREE gates")
    log("  (forbidden-band rate, the counter recursion) and the scale/incidence.")
    log("=" * 78)

    sus = pl.read_csv(SUSPECT)
    log(f"  excluding {sus.height} suspect (leg,seed,Cell) blocks per P0: "
        + str(sus.select(sus.columns[:3]).rows()))
    scols = set(sus.columns)
    keys = [c for c in ["leg", "seed", "Cell"] if c in scols]

    lf = pl.scan_parquet(TABLE_A).select(
        ["leg", "seed", "Cell", "Patch", "Type", "ID", "Year", "Age", "Height",
         "agb", "vegc", "Wooddens", "LAI", "fpc_ind", "mort_npp", "mort_age",
         "mort_water", "mort_temp", "mort", "isdead", "dup_key"]
    ).filter(pl.col("dup_key") == 0)
    D = lf.collect()
    log(f"  Table A rows (dup_key==0): {D.height}")
    D = D.join(sus.select(keys).with_columns(pl.lit(True).alias("_bad")),
               on=keys, how="left").filter(pl.col("_bad").is_null()).drop("_bad")
    log(f"  after suspect-block exclusion: {D.height}")

    # first year of each leg: the emitted mort_* can be uninitialised garbage
    y0 = {"historic": 2000, "ssp370": 2020}
    firsty = pl.Series([y0[x] for x in D["leg"].to_list()])
    D = D.with_columns(is_first_year=(D["Year"] == firsty))
    log(f"  first-leg-year rows (dropped from scoring): {int(D['is_first_year'].sum())}")

    # ---------- route 2b
    pid = D["Type"].to_numpy()
    wd = D["Wooddens"].to_numpy()
    w1 = np.array([P[int(p)]["wdmort_1"] for p in pid])
    w2 = np.array([P[int(p)]["wdmort_2"] for p in pid])
    mmax = 10.0 ** (w1 + w2 / (wd / 1e6))
    mn = D["mort_npp"].to_numpy()
    r, c2b, info, forb = route_2b(mn, mmax)
    D = D.with_columns(r=pl.Series(r), c2b=pl.Series(c2b),
                       info=pl.Series(info), forb=pl.Series(forb),
                       mort_max=pl.Series(mmax))

    log("\n--- TRUTH-FREE GATE 1: the forbidden r-bands (must be 0.000 %) ---")
    for leg in LEGS:
        for fy in (True, False):
            S = D.filter((pl.col("leg") == leg) & (pl.col("is_first_year") == fy))
            if S.height == 0:
                continue
            log(f"   {leg:9s} first_year={str(fy):5s} n={S.height:9d}"
                f"  forbidden={S['forb'].mean()*100:8.4f} %"
                f"  informative={S['info'].mean()*100:7.3f} %"
                f"  r>=6 (impossible: c<=5)="
                f"{float((S['r'].to_numpy() >= 6.0).mean()) * 100:7.4f} %"
                f"  max r={float(S['r'].max()):.3f}")
    # what the counter distribution looks like globally, recovered
    Dg = D.filter(~pl.col("is_first_year"))
    log("\n--- recovered counter distribution on the global table (route 2b) ---")
    for leg in LEGS:
        S = Dg.filter((pl.col("leg") == leg) & pl.col("info"))
        c = S["c2b"].to_numpy()
        u, ct_ = np.unique(c, return_counts=True)
        log(f"   {leg:9s} n={c.size:9d}  " + "  ".join(
            f"c={int(a)}:{b/c.size*100:6.3f}%" for a, b in zip(u, ct_, strict=True)))
        log(f"              share c>=1 = {float((c>=1).mean())*100:.3f} %"
            f"   (ADR 0093 global: 11.69 %)")

    log("\n--- TRUTH-FREE GATE 2: the counter RECURSION  c(y) in {0, c(y-1)+1} ---")
    Ds = Dg.filter(pl.col("info")).sort(["leg", "seed", "Cell", "Patch", "Type", "ID", "Year"])
    stem = (Ds["leg"].cast(pl.Categorical).to_physical().to_numpy().astype(np.int64) * 10**15
            + Ds["seed"].to_numpy().astype(np.int64) * 10**14
            + Ds["Cell"].to_numpy().astype(np.int64) * 10**9
            + Ds["Patch"].to_numpy().astype(np.int64) * 10**8
            + Ds["Type"].to_numpy().astype(np.int64) * 10**7
            + Ds["ID"].to_numpy().astype(np.int64))
    yr = Ds["Year"].to_numpy()
    c = Ds["c2b"].to_numpy()
    contig = np.concatenate([[False], (stem[1:] == stem[:-1]) & (yr[1:] - yr[:-1] == 1)])
    prev = np.concatenate([[0], c[:-1]])
    okrec = (c == 0) | (c == prev + 1)
    log(f"   consecutive-year pairs: {int(contig.sum())}")
    log(f"   recursion violations  : {int((~okrec & contig).sum())}"
        f"   ({float((~okrec & contig).mean() / max(contig.mean(),1e-12))*100:.4f} % of pairs)")
    log("   NOTE: a violation can also be a legitimate broken chain -- a stem below the")
    log("   5 m emission cut in an intervening year is absent from the table.  This gate")
    log("   is scored only on strictly consecutive EMITTED years.")

    # ---------- route 2a on global observables, cross-checked against 2b
    log("\n--- Q2a x Q2b CROSS-CHECK on global observables (no truth needed) ---")
    rows = []
    for proxy in ("agb", "vegc"):
        v = Ds[proxy].to_numpy()
        dv = np.full(v.size, np.nan)
        dv[1:] = v[1:] - v[:-1]
        have = contig
        chat, syn = runlength_vec(stem, np.nan_to_num(dv, nan=1.0), have)
        m = have  # only rows where an increment exists
        rows.append(dict(
            proxy=proxy, n_pairs=int(m.sum()),
            sign_agree=float(((dv[m] < 0) == (c[m] >= 1)).mean()),
            exact_agree_2a_vs_2b=float((chat[m] == c[m]).mean()),
            agree_on_2b_c_ge_1=float((chat[m & (c >= 1)] == c[m & (c >= 1)]).mean()),
            detect_2b_c_ge_1=float((chat[m & (c >= 1)] >= 1).mean()),
            synced_share=float(syn[m].mean()),
            exact_agree_synced=float((chat[m & syn] == c[m & syn]).mean()),
        ))
    X = pl.DataFrame(rows)
    with pl.Config(tbl_cols=-1, tbl_width_chars=240, float_precision=6):
        log(str(X))
    X.write_csv(os.path.join(OUT, "hidden_counter_global_crosscheck.csv"))

    # ---------- Q3 at global scale, with the RECOVERED counter
    log("\n--- Q3 at global scale using the RECOVERED counter (674 cells) ---")
    for leg in LEGS:
        S = Dg.filter((pl.col("leg") == leg) & pl.col("info"))
        cc = S["c2b"].to_numpy()
        mp = S["mort"].to_numpy()
        dd = S["isdead"].to_numpy()
        m1 = cc >= 1
        log(f"   {leg:9s} n={cc.size:9d}"
            f"  stems c>=1 {m1.mean()*100:6.2f} %"
            f"  hazard mass {mp[m1].sum()/mp.sum()*100:6.2f} %"
            f"  deaths {dd[m1].sum()/max(dd.sum(),1)*100:6.2f} %"
            f"   (ADR 0093: 11.69 / 44.8 / 37.8; nind is constant per cell so"
            f" mass=sum(mort))")
    log("\n   E[Wooddens | recovered c] by PFT, global sample:")
    T = (Dg.filter(pl.col("info")).group_by(["Type", "c2b"])
         .agg(pl.len().alias("n"), pl.col("Wooddens").mean().alias("wd"))
         .sort(["Type", "c2b"]))
    with pl.Config(tbl_rows=90, tbl_width_chars=140, float_precision=1):
        log(str(T))
    T.write_csv(os.path.join(OUT, "hidden_counter_global_wooddens_by_c.csv"))

    Dg.select(["leg", "seed", "Cell", "Patch", "Type", "ID", "Year", "Age", "Height",
               "Wooddens", "mort_npp", "mort_max", "r", "c2b", "info", "forb",
               "mort", "isdead"]).write_parquet(
        os.path.join(OUT, "hidden_counter_global_recovered.parquet"))
    log(f"\nwrote {OUT}/hidden_counter_global_recovered.parquet ({Dg.height} rows)")


PREREG_PROP = r"""
================================================================================
PRE-REGISTRATION — B1 EXTENSION: is the counter PROPAGABLE, not just READABLE?
   printed BEFORE any result is computed.
================================================================================

WHY THIS EXTENSION EXISTS  (what stages `dump` and `global` did NOT answer)
  Route 2b recovers the counter EXACTLY -- but out of `mort_npp`, which is an
  OUTPUT of LPJmL-FIT's own mortality routine.  That makes the counter an
  observed TRAINING INPUT over the whole global corpus.  It does NOT make it
  available at ROLLOUT time: a free-running learned operator emits no
  `mort_npp`, so it must ADVANCE the counter from its own predicted state,
      c(y+1) = 0          if bm_delta(y+1) >= 0
             = c(y) + 1    otherwise
  and the only thing that rule needs is the SIGN of next year's individual
  biomass increment.  So the operational question is: CAN THAT SIGN BE
  PREDICTED?  Recovery and propagation are different claims; stage `global`
  measured only the first, and route 2a is one FIXED proxy for the second, not
  a ceiling on it.

STATISTIC (the blessed one)
  positive-class RECALL and balanced accuracy for the binary event
      E(y+1) := [ bm_delta(y+1) < 0 ]  ==  [ recovered c(y+1) >= 1 ]
  on strictly consecutive-year emitted stem pairs of the global table, scored
  on OUT-OF-FOLD predictions, 5 folds BY CELL.  Recall is blessed because the
  c >= 1 stems carry the mortality (stage `global`: 10.5-13.6 % of stem-years,
  42-46 % of the hazard mass).  Decisive for a rollout, and reported second:
  after propagating the counter for L years from a truth-initialised start,
  (i) exact-integer agreement vs the recovered truth at lead L, (ii) the ratio
  of the propagated to the true size of the CERTAIN-DEATH set c >= 5, and
  (iii) the nominated-hazard-mass ratio, all as functions of L.

THE ARMS
  N-A  "the summary-state assumption": always predict E=0, i.e. c == 0 forever.
  N-B  "sign persistence": predict E(y+1)=1 iff c(y) >= 1.
  N-C  "PERFECT ABOVE-GROUND BIOMASS": predict E(y+1)=1 iff agb(y+1) < agb(y)
       using the TRUE emitted agb.  This is an ORACLE -- handed next year's
       truth -- and it is THE CEILING FOR ANY OPERATOR THAT PREDICTS BIOMASS
       AND INFERS THE COUNTER FROM IT.
  N-C' the same on vegc.
  M2   LightGBM on year-y observables + year-y and year-(y+1) forcing only.
       A genuine one-step-ahead forecast: no next-year state, no hidden state.
       `mort_npp` and `mort_water` at year y are EXCLUDED from M2 because both
       carry the factor (1+c(y)) and would smuggle the hidden state in.
  M3   M2 + the year-(y+1) emitted per-stem and stand state (npp, Height, LAI,
       agb, vegc, fpc_ind and their year-over-year changes) -- i.e. an operator
       that has ALREADY produced next year's state and only has to decide the
       sign of bm_delta.  M3 strictly CONTAINS N-C's rule, so M3 < N-C would
       itself be a bug.  This is the practical ceiling for a purely learned
       per-stem operator.
  M1   M3 + the exactly recovered hidden state at year y (the counter c(y) and
       the growth efficiency G(y) = bm_delta(y)/leafarea_real(y)).  Teacher-
       forced on the hidden state, therefore an UPPER BOUND, not a rollout
       number.

THE NULLS AND WHAT EACH MUST RETURN  (derived before the run)
  N-A accuracy MUST equal the prevalence of c(y+1) == 0 on the scored pairs.
      Stage `global`'s recovered distribution puts that at 0.895 (historic) /
      0.864 (ssp370), so about 0.87 pooled.  N-A positive-class recall MUST be
      EXACTLY 0.000 and its balanced accuracy EXACTLY 0.500.  Any arm that does
      not beat balanced accuracy 0.500 has learned nothing.
  N-B accuracy is DERIVABLE from the recovered counter distribution alone:
      with onset rate a = P(c=1)/P(c=0) and continuation rate
      b = P(c>=2)/P(c>=1),  accuracy = P(c=0)(1-a) + P(c>=1) b.  Stage `global`
      gives a = 6.360/89.493 = 0.0711 and b = (10.507-6.360)/10.507 = 0.3947
      on the historic leg, so N-B accuracy MUST come out NEAR 0.873 -- i.e.
      WORSE than N-A.  Both the derived and the measured value are printed.
  N-C accuracy MUST come out near the same-year sign agreement stage `global`
      already measured between the emitted Delta-agb and the true bm_delta:
      0.894 (agb) / 0.898 (vegc).  If it does, a PERFECT biomass predictor
      still mis-updates the counter on about 10.6 % of stem-years.
  ROLLOUT NULL: propagating with N-A must give exact agreement equal to the
      prevalence of c == 0 at each lead and a certain-death-set ratio of
      EXACTLY 0.000 at every lead.

THE FALSIFIER
  I conclude the counter is NOT PROPAGABLE from observables -- so a learned
  per-stem operator must carry it as an explicitly modelled latent with its own
  dynamics and cannot infer it from its own biomass track -- if the best
  rollout-legitimate arm (M3) has positive-class recall < 0.50 at a false-
  positive rate at or below the event prevalence, OR if the propagated
  certain-death-set ratio leaves [0.5, 2.0] by lead 10.
  I conclude it IS propagable if M3 reaches recall >= 0.80 at a false-positive
  rate <= 0.05 AND the certain-death ratio stays in [0.8, 1.25] out to lead 10.

GATE ADDED HERE (a new exact identity, gated in dump space BEFORE it is used)
  Inverting route 2b yields the GROWTH EFFICIENCY as well: with D = (1+c)/r,
      G = bm_delta/leafarea_real = ln((D-1)/KMORT_2)/k_mort
  so the global table exactly encodes a SECOND hidden per-stem quantity.
  MUST RETURN: max relative residual vs the dumped bm_delta/leafarea_real
  <= 1e-9 at full precision on informative, non-forbidden rows.  The same
  residual is reported at the ind writer's %g 6-significant-digit precision,
  because that is the precision the global table actually has -- there the
  requirement is only that the MEDIAN relative residual be <= 1e-3, and the
  quantiles are printed rather than a pass/fail, because a 6-digit print of a
  quantity that enters through a logarithm has a derivable precision floor.

BASIS DISCLOSURE (trap 3)
  The G-inversion gate is on 12 rung-2 cells x 2 legs x the REC arm x seed 1.
  Everything else is the 674-cell shared sample (Cell % 100 == 0), both legs,
  both seeds -- NOT the acceptance criterion's 54 020 tree-bearing cells, and
  no number here is an acceptance verdict.  Every stem quantity is on the
  above-5 m emitted population only (the `ind` writer's cut), and the five
  P0 suspect (leg,seed,Cell) blocks are excluded.
================================================================================
"""

KMORT = 0.01
KMORT_2 = 0.2


def invert_G(r: np.ndarray, c: np.ndarray) -> np.ndarray:
    """bm_delta/leafarea_real from the emitted mort_npp/mort_max ratio + counter."""
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = (1.0 + c) / r
        x = (dd - 1.0) / KMORT_2
        gg = np.log(x) / KMORT
    return np.where(x > 0, gg, np.nan)


def runlength_init(chain_id: np.ndarray, pred: np.ndarray, c_init: np.ndarray):
    """Counter propagated forward: rl=0 where pred==0 else rl(prev)+1, with the
    chain's first row seeded by c_init (the truth-initialised start)."""
    n = pred.size
    idx = np.arange(n)
    new = np.ones(n, dtype=bool)
    new[1:] = chain_id[1:] != chain_id[:-1]
    reset = (pred == 0)
    last_reset = np.maximum.accumulate(np.where(reset, idx, -1))
    last_new = np.maximum.accumulate(np.where(new, idx, -1))
    rl = idx - np.maximum(last_reset, last_new - 1)
    # if no reset since the chain start, the seed still applies
    seed_live = last_reset < last_new
    seed = np.where(seed_live, c_init[last_new], 0)
    return np.where(reset, 0, rl + seed).astype(np.int64)


def binstats(y: np.ndarray, p: np.ndarray, thr: float = 0.5) -> dict:
    yh = p >= thr
    tp = int(np.sum(yh & (y == 1)))
    fp = int(np.sum(yh & (y == 0)))
    fn = int(np.sum((~yh) & (y == 1)))
    tn = int(np.sum((~yh) & (y == 0)))
    rec = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    prec = tp / max(tp + fp, 1)
    return dict(acc=(tp + tn) / y.size, recall=rec, fpr=fpr, prec=prec,
                bal=0.5 * (rec + 1.0 - fpr), tp=tp, fp=fp, fn=fn, tn=tn)


def fmt_bs(name: str, b: dict) -> str:
    return (f"   {name:34s} acc={b['acc']:.4f}  bal_acc={b['bal']:.4f}  "
            f"recall={b['recall']:.4f}  fpr={b['fpr']:.4f}  prec={b['prec']:.4f}")


# ================================================================ STAGE prop
def stage_prop(limit_cells: int = 0):
    P = load_params()
    log(PREREG_PROP)
    if limit_cells:
        log(f"  *** SMOKE: restricted to the first {limit_cells} cells ***")
    log("\n" + "=" * 78)
    log("STAGE prop — is the counter PROPAGABLE?  (recovery != propagation)")
    log("=" * 78)

    # ---------------------------------------------------------------- G gate
    log("\n--- NEW GATE: the growth efficiency G = bm_delta/leafarea_real is")
    log("    ALSO exactly recoverable by inverting route 2b (dump space) ---")
    rows = []
    for leg in LEGS:
        for cell in CELLS:
            p = os.path.join(DUMPROOT, f"S_r2s_{leg}_c{cell}_REC_predict_s1_dump",
                             "roster_rank0000.txt")
            if not os.path.exists(p):
                continue
            gr = parse_dump(p)["grow"]
            if gr["year"].size == 0:
                continue
            pid = gr["pft_id"].astype(int)
            keep = pid <= 6
            pidk = pid[keep]
            w1 = np.array([P[int(q)]["wdmort_1"] for q in pidk])
            w2 = np.array([P[int(q)]["wdmort_2"] for q in pidk])
            mmax = 10.0 ** (w1 + w2 / (gr["wooddens"][keep] / 1e6))
            mn = gr["mort_npp"][keep]
            lar = gr["leafarea_real"][keep]
            g_true = np.where(lar > 0, gr["bm_delta"][keep] / np.maximum(lar, 1e-300), np.nan)
            for prec, mnx in (("full", mn), ("%g6", g6(mn))):
                r_, c_, info_, forb_ = route_2b(mnx, mmax)
                gh = invert_G(r_, c_.astype(np.float64))
                ok = info_ & (~forb_) & np.isfinite(gh) & np.isfinite(g_true) & (lar > 1e-6)
                if not ok.any():
                    continue
                rel = np.abs(gh[ok] - g_true[ok]) / np.maximum(np.abs(g_true[ok]), 1e-300)
                rows.append(dict(leg=leg, cell=cell, prec=prec, n=int(ok.sum()),
                                 rel_med=float(np.median(rel)),
                                 rel_p90=float(np.quantile(rel, 0.90)),
                                 rel_p99=float(np.quantile(rel, 0.99)),
                                 rel_max=float(rel.max())))
    G = pl.DataFrame(rows)
    for prec in ("full", "%g6"):
        S = G.filter(pl.col("prec") == prec)
        log(f"   prec={prec:5s} n={int(S['n'].sum()):8d}  "
            f"median rel={float(S['rel_med'].median()):.3e}  "
            f"p90={float(S['rel_p90'].max()):.3e}  "
            f"p99={float(S['rel_p99'].max()):.3e}  "
            f"WORST rel={float(S['rel_max'].max()):.3e}")
    G.write_csv(os.path.join(OUT, "hidden_counter_G_inversion_gate.csv"))

    # ---------------------------------------------------------- pair table
    sus = pl.read_csv(SUSPECT)
    keys = [c for c in ["leg", "seed", "Cell"] if c in set(sus.columns)]
    stemcols = ["Age", "Height", "agb", "vegc", "npp", "transp", "wscal_mean", "SLA",
                "Longevity", "Wooddens", "LAI", "fpc_ind", "minwscal", "D95", "D95max",
                "beta_root", "mort_npp", "mort_age", "mort_water", "mort_temp"]
    lf = pl.scan_parquet(TABLE_A).select(
        ["leg", "seed", "Cell", "Patch", "Type", "ID", "Year", "isdead", "dup_key",
         *stemcols]
    ).filter(pl.col("dup_key") == 0)
    if limit_cells:
        lf = lf.filter(pl.col("Cell") <= 100 * limit_cells)
    D = lf.collect().drop("dup_key")
    D = D.join(sus.select(keys).with_columns(pl.lit(True).alias("_b")), on=keys,
               how="left").filter(pl.col("_b").is_null()).drop("_b")
    y0 = {"historic": 2000, "ssp370": 2020}
    D = D.filter(pl.col("Year") != pl.col("leg").replace_strict(y0, return_dtype=pl.Int64))
    log(f"\n  stem-years after exclusions + first-leg-year drop: {D.height}")

    pid = D["Type"].to_numpy()
    w1 = np.array([P[int(q)]["wdmort_1"] for q in pid])
    w2 = np.array([P[int(q)]["wdmort_2"] for q in pid])
    mmax = 10.0 ** (w1 + w2 / (D["Wooddens"].to_numpy() / 1e6))
    r_, c_, info_, forb_ = route_2b(D["mort_npp"].to_numpy(), mmax)
    D = D.with_columns(c2b=pl.Series(c_), info=pl.Series(info_), forb=pl.Series(forb_),
                       G_rec=pl.Series(invert_G(r_, c_.astype(np.float64))))

    # stand state
    B = pl.scan_parquet(os.path.join(OUT, "prep_patch_year_stand.parquet")).select(
        ["leg", "seed", "Cell", "Patch", "Year", "n_stems", "agb_sum", "npp_sum",
         "lai_stand", "h_max", "h_mean", "age_mean", "fpc", "Wooddens_median"]
    ).collect()
    D = D.join(B, on=["leg", "seed", "Cell", "Patch", "Year"], how="left")

    # per-cell-year climate (both legs); cast the Float32 columns before use
    CL = []
    for leg, f in (("historic", "cell_year_env_historic_w20.parquet"),
                   ("ssp370", "cell_year_env_ssp370_w20.parquet")):
        c_ = pl.scan_parquet(f"/p/tmp/jamirp/emulator_global/tables/{f}").collect()
        CL.append(c_.with_columns(pl.lit(leg).alias("leg")))
    CL = pl.concat(CL, how="vertical")
    climcols = [c for c in CL.columns if c not in ("Cell", "Year", "leg")]
    CL = CL.with_columns([pl.col(c).cast(pl.Float64) for c in climcols])
    D = D.join(CL, on=["leg", "Cell", "Year"], how="left")

    # ---- build strictly-consecutive-year pairs (y -> y+1) by self-join
    key = ["leg", "seed", "Cell", "Patch", "Type", "ID"]
    nxt_stem = ["Height", "agb", "vegc", "npp", "transp", "wscal_mean", "LAI", "fpc_ind",
                "n_stems", "agb_sum", "npp_sum", "lai_stand", "h_max", "Age"]
    NX = D.select([*key, "Year", "c2b", "info", "forb", "isdead", *nxt_stem, *climcols])
    NX = NX.rename({c: f"{c}_1" for c in ["c2b", "info", "forb", "isdead",
                                          *nxt_stem, *climcols]})
    NX = NX.with_columns(Year=pl.col("Year") - 1)
    Q = D.join(NX, on=[*key, "Year"], how="inner")
    log(f"  consecutive-year pairs: {Q.height}")
    Q = Q.filter(pl.col("info") & ~pl.col("forb") & pl.col("info_1") & ~pl.col("forb_1"))
    log(f"  pairs with an EXACT counter at BOTH years: {Q.height}")

    lab = (Q["c2b_1"].to_numpy() >= 1).astype(np.int8)
    prev = Q["c2b"].to_numpy()
    log(f"  event prevalence P[bm_delta(y+1)<0] = {lab.mean():.6f}")

    # ---------------------------------------------------------------- nulls
    log("\n--- THE NULLS (each printed against the value it MUST return) ---")
    pc0 = 1.0 - lab.mean()
    log(f"   derived: N-A accuracy MUST equal P[c(y+1)==0] = {pc0:.6f}")
    bA = binstats(lab, np.zeros(lab.size))
    log(fmt_bs("N-A  c == 0 forever", bA))
    a_on = float(np.mean(lab[prev == 0])) if (prev == 0).any() else float("nan")
    b_con = float(np.mean(lab[prev >= 1])) if (prev >= 1).any() else float("nan")
    log(f"   derived: onset a=P[E|c(y)=0]={a_on:.4f}  continuation "
        f"b=P[E|c(y)>=1]={b_con:.4f}"
        f"  => N-B accuracy MUST be {pc0 * (1 - a_on) + (1 - pc0) * b_con:.6f}")
    bB = binstats(lab, (prev >= 1).astype(float))
    log(fmt_bs("N-B  sign persistence", bB))
    for nm, col0, col1 in (("N-C  perfect agb (ORACLE)", "agb", "agb_1"),
                           ("N-C' perfect vegc (ORACLE)", "vegc", "vegc_1")):
        d_ = Q[col1].to_numpy() - Q[col0].to_numpy()
        log(fmt_bs(nm, binstats(lab, (d_ < 0).astype(float))))

    # ------------------------------------------------------------- learners
    import lightgbm as lgb

    f_y = [*[c for c in stemcols if c not in ("mort_npp", "mort_water")],
           "n_stems", "agb_sum", "npp_sum", "lai_stand", "h_max", "h_mean",
           "age_mean", "fpc", "Wooddens_median", "Type", *climcols]
    f_clim1 = [f"{c}_1" for c in climcols]
    f_st1 = [f"{c}_1" for c in nxt_stem]
    A = {
        "M2 (y-state + y/y+1 forcing)": f_y + f_clim1,
        "M3 (+ y+1 per-stem & stand state)": f_y + f_clim1 + f_st1 + ["_d_agb", "_d_vegc",
                                                                     "_d_H", "_d_LAI",
                                                                     "_d_npp"],
        "M1 (+ recovered hidden state)": (f_y + f_clim1 + f_st1
                                          + ["_d_agb", "_d_vegc", "_d_H", "_d_LAI",
                                             "_d_npp", "c2b", "G_rec", "mort_npp",
                                             "mort_water"]),
    }
    Q = Q.with_columns(
        _d_agb=pl.col("agb_1") - pl.col("agb"), _d_vegc=pl.col("vegc_1") - pl.col("vegc"),
        _d_H=pl.col("Height_1") - pl.col("Height"), _d_LAI=pl.col("LAI_1") - pl.col("LAI"),
        _d_npp=pl.col("npp_1") - pl.col("npp"),
    )
    fold = ((Q["Cell"].to_numpy() // 100) % 5).astype(np.int64)
    ncpu = int(os.environ.get("SLURM_CPUS_PER_TASK", "16"))
    log(f"\n--- LEARNERS (LightGBM, 5 folds BY CELL, n_jobs={ncpu}) ---")
    oof = {}
    for name, feats in A.items():
        X = Q.select(feats).to_numpy().astype(np.float32)
        pr = np.zeros(lab.size)
        for k in range(5):
            tr, te = fold != k, fold == k
            sub = np.where(tr)[0]
            if sub.size > 4_000_000:
                sub = sub[:: max(1, sub.size // 4_000_000)]
            m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.08, num_leaves=127,
                                   min_child_samples=200, n_jobs=ncpu, verbose=-1)
            m.fit(X[sub], lab[sub])
            pr[te] = m.predict_proba(X[te])[:, 1]
        oof[name] = pr
        log(fmt_bs(name, binstats(lab, pr)))
        thr = float(np.quantile(pr, 1.0 - lab.mean()))
        log(fmt_bs(f"   ^ at prevalence-matched thr={thr:.3f}", binstats(lab, pr, thr)))
        del X

    # ------------------------------------------------------------- rollout
    log("\n--- ROLLOUT: propagate the counter L years from a truth-initialised")
    log("    start, using each arm's own predicted sign (chains cut at any year")
    log("    gap; c seeded from the recovered truth at the chain start) ---")
    # ONE permutation carried by an explicit row id, so nothing can mis-pair
    Q = Q.with_row_index("_rid")
    S = Q.sort([*key, "Year"])
    perm = S["_rid"].to_numpy().astype(np.int64)
    yr_u = S["Year"].to_numpy()
    same = np.ones(yr_u.size, dtype=bool)
    kc = [S[c].to_numpy() for c in key]
    labS, prevS, truth1 = lab[perm], prev[perm], S["c2b_1"].to_numpy()
    oofS = {k: v[perm] for k, v in oof.items()}
    d_agb = (S["agb_1"] - S["agb"]).to_numpy()
    mn = S["mort_npp"].to_numpy()
    mw = S["mort_water"].to_numpy()
    mage = S["mort_age"].to_numpy()
    mtmp = S["mort_temp"].to_numpy()
    mw_capped = mw >= 1.0 - 1e-12
    log(f"    mort_water already at its cap on {int(mw_capped.sum())} rows "
        f"({mw_capped.mean() * 100:.4f} %) -- held at 1 in the hazard rebuild")

    newchain = np.ones(yr_u.size, dtype=bool)
    same[1:] = np.logical_and.reduce([a[1:] == a[:-1] for a in kc])
    newchain[1:] = (~same[1:]) | (yr_u[1:] != yr_u[:-1] + 1)
    chain = np.cumsum(newchain) - 1
    first_idx = np.where(newchain)[0]
    c_init = np.zeros(chain.size, dtype=np.int64)
    c_init[first_idx] = prevS[first_idx]
    lead = np.arange(yr_u.size) - first_idx[chain] + 1
    log(f"    chains={first_idx.size}  max lead={int(lead.max())}  rows={yr_u.size}")

    def haz(cc):
        """nominated hazard with counter cc, rebuilt from the emitted columns:
        mort_npp and mort_water both carry the factor (1+c_true) exactly, so
        dividing them by (1+c_true) and re-multiplying is an identity on any
        row where neither was clipped at 1."""
        f = (1.0 + cc) / (1.0 + truth1)
        mwx = np.where(mw_capped, 1.0, np.minimum(1.0, mw * f))
        h = np.minimum(1.0, mn * f) + mage + mwx + mtmp
        return np.where(cc >= 5, 1.0, np.minimum(1.0, h))

    hz_true = haz(truth1.astype(np.float64))
    nz = float(np.sum(hz_true))
    n5_true_all = int(np.sum(truth1 >= 5))
    log(f"    truth: certain-death set (c>=5) = {n5_true_all} rows "
        f"({n5_true_all / truth1.size * 100:.3f} %),  total hazard mass = {nz:.1f}")

    arms = {"N-A  c==0 forever": np.zeros(labS.size),
            "N-C  perfect agb (ORACLE)": (d_agb < 0).astype(float)}
    for k, v in oofS.items():
        arms[k] = (v >= 0.5).astype(float)
    thrM3 = None
    for k, v in oofS.items():
        if k.startswith("M3"):
            thrM3 = float(np.quantile(v, 1.0 - labS.mean()))
            arms[k + " @prev-thr"] = (v >= thrM3).astype(float)

    rows = []
    for nm, pr in arms.items():
        cp = runlength_init(chain, (pr >= 0.5).astype(np.int8), c_init)
        hz = haz(cp.astype(np.float64))
        for lo, hi in ((1, 1), (2, 2), (3, 3), (5, 5), (10, 10), (15, 15),
                       (20, 20), (1, 5), (6, 20), (21, 200)):
            m = (lead >= lo) & (lead <= hi)
            if m.sum() < 200:
                continue
            n5t = int(np.sum(truth1[m] >= 5))
            n5p = int(np.sum(cp[m] >= 5))
            rows.append(dict(
                arm=nm, lead=f"{lo}" if lo == hi else f"{lo}-{hi}", n=int(m.sum()),
                exact=float(np.mean(cp[m] == truth1[m])),
                null0_exact=float(np.mean(truth1[m] == 0)),
                mean_c_prop=float(cp[m].mean()), mean_c_true=float(truth1[m].mean()),
                n5_true=n5t, n5_prop=n5p,
                ratio_c5=(n5p / n5t) if n5t else float("nan"),
                haz_ratio=float(np.sum(hz[m]) / np.sum(hz_true[m])),
            ))
    R = pl.DataFrame(rows)
    with pl.Config(tbl_rows=200, tbl_width_chars=250, tbl_cols=20):
        log(str(R))
    R.write_csv(os.path.join(OUT, "hidden_counter_prop_rollout.csv"))

    st = pl.DataFrame([
        dict(arm=nm, **{k: v for k, v in binstats(labS, arms[nm]).items()})
        for nm in arms
    ])
    st.write_csv(os.path.join(OUT, "hidden_counter_prop_onestep.csv"))
    log(f"\nwrote {OUT}/hidden_counter_prop_rollout.csv  and  _prop_onestep.csv")

    # what a propagated counter does to the trait association (ADR 0093 §4.4)
    log("\n--- consequence for the selection argument: E[Wooddens | c] with the")
    log("    PROPAGATED counter vs the TRUE one (M3 arm) ---")
    m3 = [k for k in oofS if k.startswith("M3")][0]
    cp = runlength_init(chain, (oofS[m3] >= 0.5).astype(np.int8), c_init)
    wd = S["Wooddens"].to_numpy()
    ty = S["Type"].to_numpy()
    out = []
    for t in range(7):
        mt = ty == t
        if mt.sum() < 500:
            continue
        for lo, hi in ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 9)):
            a = mt & (truth1 >= lo) & (truth1 <= hi)
            b = mt & (cp >= lo) & (cp <= hi)
            out.append(dict(Type=t, c=lo, n_true=int(a.sum()), n_prop=int(b.sum()),
                            wd_true=float(wd[a].mean()) if a.any() else float("nan"),
                            wd_prop=float(wd[b].mean()) if b.any() else float("nan")))
    W = pl.DataFrame(out)
    with pl.Config(tbl_rows=60, tbl_width_chars=200):
        log(str(W))
    W.write_csv(os.path.join(OUT, "hidden_counter_prop_wooddens.csv"))


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "both"
    log(PREREG)
    log(f"stage={stage}  repo={REPO}  polars={pl.__version__}  numpy={np.__version__}")
    os.makedirs(OUT, exist_ok=True)
    if stage in ("dump", "both"):
        stage_dump()
    if stage in ("global", "both"):
        stage_global()
    if stage in ("prop", "both"):
        stage_prop(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    log("\nDONE")


if __name__ == "__main__":
    main()
