# 0311 — Round 2: the warming response IS partly learnable from climatology, the hidden per-tree state is exactly recoverable and propagable, and climate adds nothing per tree beyond the stand

* **Status:** **exploratory — a recorded exploration, NOT a decision.** The two owner instructions that bind
  ADR 0310 bind this record identically: *"no! stop! dont write anythign of this to other lines!!!"* and
  *"you are also nto the correct person to discuss this with. relocate our whole discussion to a new line…"*
  ⇒ **nothing here has been raised with line S, M, E or the integrator; nothing was written to `MEMORY.md`,
  `EXECUTION_PLAN.md` or any other line's `STATE.md`; nothing binds anyone or schedules any work.**
* **Date:** 2026-08-19 (measured), recorded 2026-09-02.
* **Line:** X — project direction & exploration. Tier-1 block 0310–0329. **Next free number: 0312.**
* **Continues:** ADR 0310 (the same owner conversation). Owner's words this round: *"continue the exploration
  of the feasibility of a more data driven emulator"* — note **more**, not necessarily **purely**.
* **Corrects:** ADR 0310 §7.4 (the geographic-address null was *not* "never run"), ADR 0310 §4/§7.4's kill of
  the response-from-climate claim (a hash-fold artifact on a drift-contaminated target), ADR 0310 §5's
  "single-draw R² cannot discriminate arms", and — **outside line X's territory, therefore RAISED HERE ONLY,
  NOT PROPAGATED** — ADR 0125's per-stem identity key and one sentence of line S's newest record. See §6.
* **Basis:** workflow `wf_5ba7e1aa-b45`, 11 agents that completed (2 scouts + 1 table prep + 3 measurements +
  2 adversarial verifiers + 1 replayed literature scout), ~3.7 M subagent tokens, 921 tool uses, 3 SLURM
  campaigns. Journal:
  `~/.claude/projects/-p-projects-open-Jamir-esm-land-emulator-lines-X/71d6fd2b-.../subagents/workflows/wf_5ba7e1aa-b45/journal.jsonl`.
  ⚠ **Three planned measurements (B4 the third forcing leg, B5 flux-state sufficiency, B6 the density-feedback
  rollout), the synthesis and the completeness critic DID NOT RUN** — see §8.

---

## 1. Why this round exists, and what it was allowed to conclude

ADR 0310 answered the owner's question as six problems and left the decisive parts **unmeasured**: it recorded
**zero positive evidence** that the warming response is learnable, and it named the per-stem roster operator as
the one architecture nobody had priced. This round measured three of those, each with **the nulls derived and
written down before the run** — the discipline ADR 0310's own history says is load-bearing (five numbers died to
it last round).

Every headline below is stated with its null in the same sentence, its comparison basis, and its patch count.

---

## 2. The three measurements

### B1 — the hidden per-tree growth-failure state is NOT hidden, and a rollout CAN carry it ⚠ UNVERIFIED

**The objection under test** is ADR 0093 §4.4/§4.5, owner-approved: every tree carries a private
consecutive-bad-growth-years counter that multiplies two of the four mortality hazards and hard-kills at 5; it
is trait-correlated; ~11.7 % of stems carry ~44.8 % of mortality mass; and factorising trait ⊥ counter
**reverses the selection sign in 4 of 7 tree types**. ADR 0093 concludes the summary-state family is dead.

**(a) The counter is exactly recoverable from the globally printed 29-column table, by algebra.**
Exact-integer agreement **1.000000** on 694 662 grow-phase tree stem-years (12 cells × 2 legs), confusion table
perfectly diagonal over counts 0…5, covering 99.95 % of rows — against a **`counter = 0 everywhere` null of
0.877821 overall and exactly 0.000 on the stems that matter**. At the table's actual 6-significant-digit print
precision it is **0.997808** overall and **0.982056** on the `counter ≥ 1` stems. A **second** hidden quantity —
the growth efficiency — falls out of the same inversion at machine precision (median residual 2.8e-15).
⚠ The pre-registered *maximum*-residual clause **FAILED** (worst 9.5e-01): the inversion passes through a
logarithm and is ill-conditioned on a sub-1 % tail. Reported as a pre-registration miss, not restated.
⚠ The obvious alternative — rebuilding the counter as a run of non-positive printed biomass changes — **does
not work**: 0.890 agreement against a do-nothing null of 0.881, i.e. **one percentage point**, and recall on
the `counter ≥ 1` stems only 0.259. The printed biomass change agrees in sign with the true increment only
**91.47 %** of the time.

**(b) The split that is the real result.** Can a free-running operator *update* the counter from its own state?

| arm | recall on growth-failure years | false-alarm rate | certain-death population after 10 yr of self-updating |
|---|---|---|---|
| **`counter = 0` null** | **0.0000** (balanced accuracy exactly 0.5000) | — | **0.000** at every lead |
| perfect-biomass oracle (handed next year's truth) | 0.3455 | 0.0204 | 0.187 |
| **one-year-ahead forecast** from this year's stand + climate | **0.2771** | 0.0187 | **2.063** — and its exact agreement falls **below the do-nothing null** from lead 3 onward |
| **model that first produces next year's per-tree state** | **0.9023** | **0.0066** | **1.054** (1.032 at lead 5, 1.119 at lead 20) |

*(19 980 621 consecutive-year tree pairs with an exact counter at both years, 674 cells at `Cell % 100 == 0`,
both legs, both seeds, out-of-fold with 5 folds by cell.)*
The last arm **passes** the pre-registered propagation clause (recall ≥ 0.80 at false-alarm ≤ 0.05, certain-death
ratio in [0.8, 1.25] to lead 10); the forecast arm **fails** it (leaves [0.5, 2.0] by lead 5). Discarding the
counter costs **15–35 % of total nominated death risk** (ratio 0.852 at lead 1 falling to 0.661 at lead 20)
where the good arm holds 0.997–1.030.

**(c) ADR 0093's global replication, with the recovered counter** (21.3 M stem-years, 674 cells, both legs,
both seeds): incidence/hazard-mass/deaths **10.51 % / 41.91 % / 34.64 %** historic and **13.65 % / 45.89 % /
39.15 %** warming — **bracketing** ADR 0093's published 11.69 % / 44.8 % / 37.8 %. The trait gradient replicates
per tree type at **+10.0 % to +22.4 %** (ADR 0093's single +19 % sits inside). The **sign reversal replicates in
3 of 7 types pooled** (ADR 0093: 4 of 7; at the 12 dump cells only 1 of 7) ⇒ **the count of flips is
basis-dependent; the mechanism replicates.** And the propagated counter **retains the trait gradient**
(+12.87…+21.37 % vs a true +12.62…+22.32 %).

⇒ **ADR 0093's refutation transfers as a STATE-CONTENT REQUIREMENT, and the requirement is measurably
satisfiable** — but only by an operator that produces next year's per-tree carbon state and reads the counter
off it. It is fatal to a summary-state operator and **inert for the hybrid**, because the quantity it keys off
is computed exactly by the existing fast physics core.

⚠⚠ **B1's adversarial verifier never ran** (session usage limit). **B1 is the one unverified item in this
record.** Its self-gates are strong (every hazard recomputed against the dumps to ≤ 8.9e-16; a deliberate
wrong-age control returns 2.3e-03; an independent header-offset guard passes) but the campaign's own history is
that verifiers refute. **Treat B1 as PLAUSIBLE, not CONFIRMED.**

### B2 — per-tree learning works; climate adds nothing beyond the stand ✅ NARROWED by its verifier

**On 10.9 M tree-years**, out-of-fold: death **AUC 0.742** and growth **R² 0.887**, against an intercept null of
0.5000 / −0.00129. The death AUC **beats the reference model's own nominated probability (0.70058)** — which is
itself the ceiling *for one of three kill channels*.

**⚠ The verifier refuted the magnitude, and the correction runs 10–11× against the report's own decomposition
while leaving its thesis intact.** The growth target is a one-step increment, and ADR 0310 §2(ii) sets a
**STANDING RULE** — report the persistence null beside every one-step number — which B2 violated. Measured by
the verifier on an identical subsample, identical folds, identical settings: **copying last year's own biomass
increment, zero parameters, no fit, returns R² 0.80536 = 90.7 % of B2's 0.887.** Six trivial columns return
96.7 %. So the honest span is **+0.0817 R²** over a free copy, and the block decomposition becomes
**own-state-beyond-persistence 74.3 % / patch 18.9 % / climate 4.1 %**, not the reported 97.6 / 1.7 / 0.4.

**What survives every attack — and it is the answer to the campaign's actual question.** The **absolute**
climate increment does not move:

| question | measured | pre-registered threshold |
|---|---|---|
| climate beyond tree + patch, death | **+0.00300 AUC** (hash) → **+0.00081** (blocked, within noise) | 0.005 ⇒ **falsifier FIRED for "climate adds nothing"** |
| climate beyond tree + patch, growth | **+0.00333 R²** → +0.00226 blocked | 0.005 ⇒ same |
| is there learnable per-tree signal at all? | **+0.17511 AUC / +0.14978 R²** over size alone | 0.02 / 0.05 ⇒ **decisively yes** |
| is climate genuinely climate, not geography? | climate-only **beats coordinates-only by +0.0299 to +0.1030** in all four pairings, all significant | > 2× paired SE ⇒ **yes** |
| is climate redundant with the stand? | helps a **stand-blind** model by **+0.01051** while helping the full model by +0.00300 | ⇒ **redundancy verdict fired, as pre-registered** |

**And the same shape on the response:** the model reproduces 57 % of the per-cell amplitude and 75–81 % of the
achievable spatial pattern of the change in death rate — but **a version with climate deleted does essentially
as well, and adding climate makes the pattern worse in all four pairings.** Two-seed ceiling on that target:
slope +0.9716, r +0.9158, run-to-run scatter 30 % of the signal ⇒ **the per-cell response signal is real, so
the regression has a target.** A coordinates-only arm's implied response is exactly 0 (±5e-15) ⇒ no leak.

**A pre-registration failure that turned into the round's most useful incidental finding.** The label self-check
(if the kill flag is a draw on the nominated probability then Brier = mean p(1−p)) **FAILED**: 0.032430 vs
0.022972, E[isdead] 0.042154 vs E[mort] 0.031739 ⇒ **the nominated probability describes only 76.5 % of the
deaths the model carries out.** ⚠ **The verifier then showed this is already recorded** — ADR 0047 §1, ADR 0120
§2 and ADR 0187 §5(a) each name the other two kill channels explicitly, and ADR 0187 quantifies the
contamination per arm. So it is a **third independent estimate narrowing ADR 0310 §10 item 2's open
disagreement (32.4 % vs 11.0 %)**, not a discovery. Two more of B2's five "surprises" were likewise stale
against records it had been told to read.

**Verifier's own two new facts, worth keeping.** (i) **The 2019/2020 forcing splice, precipitation — ADR 0310
§11 lists it as unchecked.** Now checked over 601 cells: precipitation steps **+21.09 mm/yr** across the splice
against a within-historic decade step of +5.78 (3.6×); shortwave steps −0.776 W/m² against +0.017 (**opposite
sign**). A classifier tells the legs apart at AUC 0.84161 against a within-historic control of 0.78174 ⇒ the
signature is **real but small (+0.060)**, and it was measured to have **no consequence for any B2 number** (a
pure leg indicator is worth R² 0.000225 on growth). (ii) The documented "`mort_*` is garbage in a restarted
run's first year" trap **does not bite the global tables** for either leg.

### B3 — the direct climatology → 20-year-window map: the response IS partly learnable, and the map is still two orders of magnitude from the bar ✅ NARROWED by its verifier

This is the architecture ADR 0310 §4 listed as *"never considered"*, and the one whose **estimand equals the
acceptance criterion** (ADR 0106/0111 are stated on 20-year windows) and which **cannot drift** (no rollout).

**(a) The missing null was run, and it is huge.** Coordinates-only (unit-sphere x,y,z, **no climate**), level
target, hash folds: **R² 0.7512–0.9370 on 6 of 6 targets**, recovering 88–96 % of the climate arm.
⇒ **every hash-fold level number in this project is a spatial-interpolation score and must be labelled one.**
Pre-registered clause N1 (≥ 0.45 on ≥ 4 of 6) **confirmed, and four of six exceeded the predicted upper bound.**

**(b) Under honest folds, climate beats the address decisively — and SUBSUMES it.** Blocked 15° tiles + 5°
buffer, 161 populated tiles, two colourings. Climate-only minus coordinates-only:

| | stems | biomass | SLA | wood density | rooting depth | drought threshold |
|---|---|---|---|---|---|---|
| **level** | +0.403/+0.396 | +0.453/+0.410 | +0.405/+0.418 | +0.424/+0.412 | +0.229/+0.286 | +0.198/+0.219 |
| **response** (clean 20-vs-20 yr) | **+0.548/+0.715** | +0.346/+0.336 | +0.175/+0.210 | +0.193/+0.227 | +0.162/+0.187 | +0.493/+0.407 |

All twelve level values clear the pre-registered 0.05 by **3–9×**; climate *alone* matches climate+coordinates
to < 0.02 ⇒ **climate subsumes the address rather than proxying it.** The coordinates arm's **response** R² is
**negative on five of six targets.** Under a severe buffer the coordinates arm goes negative on four of six
level targets too ⇒ blocking genuinely severs adjacency.

⇒ ⛳ **THIS IS THE FIRST POSITIVE EVIDENCE IN THIS PROJECT THAT THE WARMING RESPONSE CARRIES LEARNABLE SIGNAL,
and it refutes ADR 0310 §7.4's kill of the claim** — that kill was measured on **hash folds** against a
**drift-contaminated 20-vs-81-year** target. On a clean 20-vs-20-year target under blocked folds it does not
hold. The verifier attacked this with **three independent address nulls** (raw x/y/z, a 21-column smooth
spatial basis with *more capacity* than the climate arm, and the record's own 1-NN surrogate) and the
discriminator margin came out **2–6× LARGER** than quoted.

**(c) ⚠ The verifier found a survivorship defect that makes B3's response verdict TOO PESSIMISTIC by ~2×.**
B3's design is a 4-way inner join over (2 windows × 2 replicates), so a cell scores only if it bears a > 5 m
tree in **all four** blocks. That **silently drops 4 635 cells** (8.0 % of the union) that hold **no tree today**
and a mean of **+6.455 stems/patch in the 2080s** — a per-cell response **231× the mean of the cells it did
score** — i.e. **the poleward treeline advance, the model's single largest warming response** (median latitude
57.75 °N, 52.6 % above 50 °N). Repairing the universe with structural zeros (which is B3's *own* primary
denominator convention) and refitting with identical folds and hyperparameters:

| | as reported | repaired |
|---|---|---|
| mean true stem response | +0.0279 | **+0.5440** (19.5×) |
| climate response R² | 0.2740/0.3414 | **0.5289/0.5673** |
| amplitude | 0.416/0.424 | **0.641/0.648** |
| pattern correlation | 0.557/0.596 | **0.737/0.758** |
| discriminator vs address | +0.528/+0.733 | **+0.769/+0.798** |

**(d) And on the owner's basis it is nowhere near the bar.** Fraction of cells with **all six** quantities
simultaneously inside `max(10 %, the reference's own two-run spread)`, **per cell, 53 085 cells, 25 patches,
blocked folds**:

* **today's state: 7.18 % / 7.21 %** (18.78 % under hash folds — an interpolation score);
* **the change to the 2080s: 2.93 % / 2.85 %**, against a **zero-change null of 2.67 %** ⇒ the map buys
  **+0.26 percentage points**;
* **the future state: 7.35 %**, against a **persistence null (predict today) of 12.96 %** ⇒ the climate map is
  **5.6 pp WORSE than assuming nothing changes.** (The verifier's repair narrows that gap by 1–3 pp; it does
  not close it.) Per-target the map beats the zero-change null by +2.71 pp (stems) and +7.72 pp (biomass) but
  **loses by 1.9–2.9 pp on two trait axes**.
* ⛳ **The reproducibility ceiling nobody had computed:** one reference replicate predicting the other's
  per-cell 20-year change scores R² **0.8315 stems · 0.3699 biomass · 0.4209 SLA · 0.1233 wood density ·
  −0.5243 rooting depth**. **Rooting depth's response is not reproducible by the reference model itself.**
  And the reference's own second run sits **outside a pure 10 % band on 13.7 % of cells for stem count, 25.0 %
  for biomass, 34.0 % for rooting depth**, at 25 patches.

**(e) The space-for-time transfer test fails, and the literature named the mechanism in advance.** Fitted on
today's leg only, then asked for the 2080s: it beats the zero-change null on **1 of 6** quantities (+0.85 pp
biomass) and loses by 15–18 pp on the four trait axes. In the **3.70 %** of cells whose 2080s climate is hotter
than the hottest tree-bearing cell today, **4 of 6 quantities get the direction of the change WRONG** — stem
count truth **−0.7175** per patch, predicted **+1.030**; wood density truth −4 106, predicted +12 815 — and the
zero-change null beats the map on **6 of 6** there. **Why:** the truth **reverses sign** between the bulk and the
extrapolating regime (stems +0.0565 in the bulk vs −0.7175 there), so a map fitted on the bulk carries the bulk
sign into a regime where it inverts. ⇒ **exactly the failure `exploration_data_driven_literature.md` §3
documents from 339 ponderosa pines** (the spatially-inferred climate response is the wrong sign, going
directionally wrong above ~0.5 °C of warming).

---

## 3. The deepest finding: within one scenario, the forcing is not an independent variable

**A cell's warming increment is 76.4 % linearly predictable from its own baseline climate** (median 62.0 % over
16 change features; corr(increment, baseline temperature) = **−0.7827**; increment mean 3.312 K, sd 0.973 K).
⇒ **"response to warming" and "sensitivity of this place" are not separately identified from one scenario.**
Three consequences, all measured, all consistent:

1. **Knowing the future climate adds nothing over knowing only today's** on 5 of 6 targets (differences < 0.05).
   Biomass is the lone exception (+0.123/+0.127).
2. **The climate-*change*-only arm carries almost nothing**: response R² +0.037/+0.011 for stems, and
   **negative** for wood density and rooting depth.
3. **Counterfactual:** re-run the fitted map with the warming scaled to **zero** and **76–110 % of the predicted
   per-cell change survives** (stems 1.095 — *more* change with no warming than with full warming). The
   structurally scenario-blind control returned exactly 1.0000 in 18 of 18 groups, so the probe is correctly
   wired. ⚠ On the **global aggregate signed** basis biomass instead reads 0.045–0.052 (95 % forcing-driven) —
   **a 15× disagreement between the per-cell and aggregate bases on the same fitted model.** State the basis.

⇒ **A third forcing leg is not a nice-to-have; it is the only way to break this degeneracy.** And the
literature says the *bracketed* design (historic and the high leg bracket the low-emissions leg at 0.227×) is
the only one with published precedent for succeeding.

---

## 4. What is now POSITIVE, NEGATIVE, and UNMEASURED

**Positive (new this round):**
* the warming response carries **real learnable signal from climatology** under spatially blocked folds, on a
  clean 20-vs-20-year target, against three independent address nulls (§2 B3b, strengthened by the repair in
  B3c). ADR 0310's "zero positive evidence" no longer holds.
* the hidden per-tree state is **exactly recoverable** and, given an operator that produces next year's carbon
  state, **propagable through a self-fed rollout** (§2 B1). ⚠ unverified.
* the per-tree corpus contains **large learnable signal** (+0.175 AUC / +0.150 R² over size alone), and it is
  **19.98 M paired labels** on a 1 %-of-cells sample alone.
* **published support for the exact architecture** ADR 0310's critic named: a permutation-invariant network over
  individuals with a **stochastic** head beat its own deterministic ablation by 2.2–2.3× on individual-level
  distributions and held up 25 steps beyond its training horizon.

**Measured negative:**
* **climate adds nothing per tree once the tree and its patch are known** (+0.003, below the pre-registered
  0.005, and within noise under blocking) — the per-tree analogue of ADR 0181's per-cell finding. A free-running
  rollout's response can therefore only come from state it generates itself.
* **space-for-time transfer fails**, and fails *sign-wrong*, exactly where it matters (§2 B3e).
* the direct map is **two orders of magnitude from the per-cell acceptance bar** and **loses to persistence** on
  the future state.
* a one-year-ahead forecast **cannot** carry the per-tree memory (worse than doing nothing from lead 3).
* **rooting depth's response is not reproducible by the reference model itself** (replicate-vs-replicate R²
  −0.5243) ⇒ that axis has no learnable response target at 25 patches.

**Unmeasured (and the three that were planned and did not run):** the third forcing leg as a bracketed
held-out test; whether a fixed-size stand summary suffices for the daily fluxes; the closed density-feedback
rollout; the whole rollout-training family (multi-step loss, pushforward, noise injection); a stochastic
binomial-survival/Poisson-birth head; the compounding of a daily head's error with an annual head's.

---

## 5. What this does to ADR 0310's open items

**Settled or materially narrowed:**
* §10 item 1 (does −0.226 bound from below or above?) — **narrowed toward "from above", but not by this round's
  own measurement.** The prior-art scout found the density feedback **has** been measured twice inside the
  reference model's own physics: over-killing arms saw their own recruitment run at **27.6–70.6 %/yr against the
  model's own 6.456 %/yr**, and a counterfactual estimate of the same quantity came out **18× low**. The feedback
  is **negative and large**, and the drift it would correct runs in the direction where counts are **too high**
  (drift channel: lagged count r = −0.336, mean age +0.330, every climate/flux feature |r| ≤ 0.084). ⇒ the
  disagreement's "unmeasured" status is gone; the disagreement itself (about a *learned closed* rollout) is not.
* §10 item 2 (unexplained mortality 32.4 % vs 11.0 %) — a **third independent estimate, 23.5 %**, lands inside
  the bracket (§2 B2).
* §11 (the 2019/2020 splice checked for temperature only) — **precipitation now checked**: +21.09 mm/yr step,
  3.6× a within-historic decade step, with **no measurable consequence** for the per-tree numbers.
* §5's *"single-draw R² cannot discriminate arms; the ceiling is a variance ceiling"* — **overstated.** The exact
  Bernoulli floor is 4.14–4.58 % of the per-patch level against a measured holdout error of 0.828 stems ⇒ the
  irreducible part is **~28 % of the residual variance, not all of it**. There is explainable structure left.
  (⚠ cross-basis reconciliation of two published numbers — weak.)

**Still open:** §10 items 3, 4 and 5; the compounding question; everything in §4's unmeasured list.

**One new discrepancy nobody should quote across:** ADR 0310 records a blocked-fold coordinates-only score of
**0.353** on its response target; B3's nominally equivalent arm returns **−0.254/−0.391**. Different targets and
probably different estimators; **not reconciled.** Do not print the two side by side as the same measurement.

---

## 6. Three corrections that belong to somebody else — RAISED HERE, NOT PROPAGATED

⚠ **Line X does not write into another line's territory. These are recorded so they are not lost, and
propagating them is the owner's decision, not this line's.**

1. ⛳ **ADR 0125's per-stem cross-year identity key is WRONG, and the corrected key is `(Cell, Patch, PFT, ID)`,
   not `(Cell, Patch, ID)`.** The tree number is issued by a counter kept **per plant type**, so two trees of
   different types in the same patch can carry the same number. **On the documented key the identity gates
   failed on every leg; on the corrected key there are 0 violations of 20.4 M consecutive-year tree pairs on
   three independent checks** (age increments by exactly 1; SLA and wood density bit-identical across each
   pair; the vanished-stem population gated on height). Evidence, including the cancelled first attempt kept as
   the record of the failure: `logs/X-prep-a.1845487.out` (failing) and `logs/X-prep-a2.1846436.out` (passing).
   **Anyone building a per-stem model on the documented key is pairing trees that are not the same tree.**
2. **"`bm_inc_counter` … not recoverable from the annual `ind` output" is wrong** (line S's newest record). It is
   exactly recoverable (§2 B1a). Separately: it **is** populated into the output struct at
   `fwriteoutput_ind.c:167` and only its **print line is commented out at :96**, so the binary's RAW mode
   already carries it and a one-line opt-in switch of the kind already shipped twice would emit it globally.
3. **The heat/cold-stress day count is EXACTLY invertible from the global table** — `round(mort_temp × 365/5)`,
   verified to 2.4e-05 (the writer's own print precision), because the scaling factor is a single global macro
   and the underlying quantity is an integer day count. ADR 0243's input inventory treats "recompute it from
   forcing" as the only route; **reading it back out of the training table is strictly cheaper** for anyone
   building a learned per-tree operator.

**Two data defects found while building the shared tables, both flagged not deleted:**
* **five damaged `(leg, seed, Cell)` blocks in the ssp370 seed-2 roster around year 2071** — a stand of 31 m
  trees appears or vanishes in a single year, which cannot happen. Listed in
  `/p/tmp/jamirp/X_explore/prep_suspect_cell_blocks.csv`; **root cause not established** (most plausibly the
  raw-CSV-to-parquet path), and it was **not checked** whether the other three rosters carry an analogous defect
  the height discriminator cannot see.
* ⚠ **the two roster seeds were NOT re-verified as a valid independent pair** (same binary, same task count —
  ADR 0041's gate). That is an open gate on **every number in this record.**

---

## 7. The bar, stated once, because it disciplines everything above

At the German test site the reference model's **two identical runs differ by 10.614 vs 9.072 stems per patch in
the same window**, while its **entire warming signal at that cell is 10.614 → 7.828**. The model's own
run-to-run noise is **over half** the signal being emulated. Globally, the reference's own second run is outside
a pure 10 % band on 13.7 % of cells for stem count and 34.0 % for rooting depth, **at 25 patches** — and the
acceptance-grade reference needs ~125–192 patches, which resolves its own response to 8.5–12 %.
**Quote no tolerance number without its patch count.**

---

## 8. What did NOT run, and the process lesson

**Did not run:** the third-forcing-leg test (B4), flux-state sufficiency (B5), the density-feedback rollout
(B6), the synthesis that was to price the whole spectrum from the shipping hybrid to the pure learned model,
the completeness critic, and **B1's adversarial verifier**. Cause: a session usage limit, then transient server
overload, then the limit again. The workflow is resumable —
`Workflow({scriptPath: '…/data-driven-emulator-feasibility-round2-wf_5ba7e1aa-b45.js', resumeFromRunId:
'wf_5ba7e1aa-b45'})` — with everything above replaying from cache; restore `ITEMS` (currently `.slice(0, 3)`)
and set `RUN_SYNTH = true`.

⚠ **The process lesson, and it is the highest-value thing to carry forward.** ADR 0310 §2(ii) wrote the
persistence rule down as a **STANDING RULE** after a reviewer killed a headline on exactly it — and **B2
violated it anyway**, in the same campaign, having been instructed to read that record. A rule in an ADR body
does not fire. **It has to be in the pre-registration template the measuring agent fills in.** Same for two
other traps that recurred: three of B2's five "surprises" were stale against records it had been told to read,
and one numbers row existed in **no log and no artifact** (the verifier reproduced most of it and found a label
error plus one unreproducible figure) ⇒ **anything tagged `[MEASURED]` needs a log line.**

---

## 9. Artifacts

Probes (all line-X-owned, lint-clean under `ruff --select E,F,I,UP,B --line-length 100`, pre-registration in
each script's own header and reprinted in every job log):
`scripts/explore_prep_tables.py` · `scripts/explore_hidden_counter.py` · `scripts/explore_perstem_ladder.py` ·
`scripts/explore_direct_window_map.py` · `scripts/explore_verify_b2.py` · `scripts/explore_verify_b3.py`.
Shared tables under `/p/tmp/jamirp/X_explore/`: `prep_paired_stems.parquet` (21 785 911 × 40) ·
`prep_patch_year_stand.parquet` (2 553 172 × 43) · `prep_cell_window_state.parquet` (334 212 × 26, **both
seeds** ⇒ a per-cell two-seed noise floor for the 20-year state with no model run) ·
`prep_cell_window_clim.parquet` (202 260 × 37) · `prep_cell_year_census.parquet` (11 029 804 × 9) ·
`prep_suspect_cell_blocks.csv` (the exclusion list) plus the `b3_*` and `vb2_*`/`vb3_*` result sets.
Literature: `docs/notes/exploration_data_driven_literature.md`.

⚠ **Basis warnings that travel with every per-tree number here:** the 674-cell `Cell % 100 == 0` sample (of
which only 547–598 are tree-bearing), **not** the criterion's 54 020 cells; seed 1 only for the B2 ladder;
**above-5 m stems only**, because the reference model's per-tree writer emits nothing shorter, so no stand
quantity here is a whole-stand quantity; and **25 patches** throughout.

---

## 10. Nothing here is implemented, and nothing has been raised

No `src/**` change, no flag, no artifact in any component's path, no edit to any other line's `STATE.md`, to
`MEMORY.md`, to `EXECUTION_PLAN.md` or to `CHANGELOG.md`. §6's three corrections and two data defects are real
and will matter to other lines eventually; **propagating them is the owner's call.** The purely data-driven
direction is **still not refuted and still not demonstrated** — but for the first time it has a positive
measurement on the part the owner actually cares about, and a measured negative on the part that would have to
carry it.
