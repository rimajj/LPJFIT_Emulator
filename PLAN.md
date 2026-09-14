# PLAN.md — the roadmap (budget: 150 lines, enforced)

The single roadmap. Design rationale goes in a decision record, not here. Agents append rung status
only; the ladder itself changes on an owner steer.

## The two products

| | **A — equilibrium** (primary) | **B — year-2100 transient** |
|---|---|---|
| Input | a 30-year climate summary | the 2019 state + the 2020–2100 climate trajectory |
| Output | the stationary forest that climate supports | the actual 2100 forest, still lagging climate |
| Truth | **new spin-ups we run**, incl. under 2090s climate | existing warming-run truth on disk |

Build A first. B reuses A's entire state-writing stack and adds a starting state as input.

**Output stage 1** = what the emulator predicts natively (restart file + per-cell state summary).
**Output stage 2, on demand** = the model's own output files, in particular the complete per-tree CSV.
Stage 2 is obtained by running the real C model **one year** from the emitted restart file — it *is*
the original model writing them, so it is byte-genuine, including the four annual flux-accumulator
columns that are not functions of state. ~7 core-hours for all 54,020 cells.

## Why this can work when the predecessor could not

The existing data has exactly **one climate per location**, so climate and geography are collinear and
the warming response is not identified (see `MEMORY.md:ident-limit`). Our target is an *equilibrium*,
and the spin-up is per-cell and embarrassingly parallel, so we **generate a designed climate-
perturbation ensemble: the same cell spun up under many climates**. That decollinearises climate from
place by construction, and it is the experiment the predecessor could never run.

## The gate ladder

Each rung is a pre-registered experiment. Status is updated here when a verdict lands.

| rung | question | kills if it fails | status |
|---|---|---|---|
| **0** | Does our reader/writer round-trip a real restart file byte-identically? | the restart deliverable entirely | **PASSED 2026-09-08** |
| **1** | **THE KILL TEST.** Given a cell's climate shifted by +4 K, can a model beat "predict this cell as it is today"? | the whole project, in ~week 3 for ~670 core-hours | **FAILED on existing data (−0.727 vs 0.000); now MANDATORY on a designed corpus** |
| **2** | Does the map meet `max(10 %, two-seed spread)` conjunctively per cell? | the science, not the engineering | **FAILED: 0.036 against a best null of 0.021, gate 0.071** |
| **3** | Is a synthesised restart file valid and stable in the real model? | the restart deliverable | **valid; carbon starts 6.7 % HIGH (never halved) and sheds to −1.6 % inside the band by yr 20; still fails conjunctively, 5 % against a 25 % ceiling** |
| **4** | **End-to-end.** Emulated restart → real transient vs real restart → real transient. | the deliverable as a whole | blocked on rung 3's state fidelity |
| **5** | Does the response survive a **held-out forcing leg**? | the warming claim | draftable now; the low-emissions leg is untouched |
| **6** | Product B, and stage-2 output reconstruction. | product B only | not started |
| **7** | All 54,020 tree-bearing cells, both scenarios, at acceptance-grade patch count. | acceptance | not started |

### Rung 0 — format round-trip (line D). PASSED.
100 real cells spanning 360,183 B → 3,546,287 B round-trip byte-identically, plus both whole `.clm`
input files. Spec: `docs/reference/binfmt.md`.

⚠ **The convergence question came back NO, and in the opposite direction to the hope.** The
1000-year spin-up has not converged: global vegetation carbon is 719 Pg C at year 200, 735 at 500
and 890 at 1000, still rising at +6.5 %/century with both seeds agreeing to 0.07 %. So **no budget
below drops** — a 300-year run would differ by 22 % — and "equilibrium" is the wrong word for the
target: it is the state the model's standard protocol reaches, which is exactly what a model user
gets and what skipping it saves. Record: `docs/decisions/20260908-D-spinup-is-not-converged.md`.

### Rung 1 — the kill test (line X, corpus from line D)
Pilot corpus: **200 cells × 30 climates × 1 seed = 6,000 spin-ups ≈ 670 core-hours, ~20 min on 2048
cores, 11 GB**. Fit any reasonable model of equilibrium tree count and trait medians from the climate
summary. Score on held-out cells **and held-out perturbation levels**, under spatially blocked folds.

Nulls, each with its required return written down before the run:

| null | what it is |
|---|---|
| **same-cell baseline** | predict this cell's own *unperturbed* equilibrium — the decisive one |
| geographic address | unit-sphere x/y/z, no climate at all |
| nearest-analogue cell | the observed equilibrium of the most climatically similar training cell |
| climatological mean | the global mean equilibrium |

**Pass** = beats the same-cell baseline by a pre-registered margin on the perturbed legs *and* survives
spatial blocking. **Fail** = there is no learnable warming response; the project stops.

### Corpus tiers (line D)

| tier | design | spin-ups | core-hours | wall @2048 | disk |
|---|---|---|---|---|---|
| pilot | 200 cells × 30 climates × 1 seed | 6,000 | 670 | ~20 min | 11 GB |
| mid | 1,000 × 100 × 2 | 200,000 | 22,200 | ~11 h | 380 GB |
| full | 3,000 × 200 × 2 | 1,200,000 | 133,000 | ~65 h | 2.3 TB |

Perturbation design rules (the physical-coherence ones are not optional):
1. Calibrate perturbation directions on the **real climate-model deltas** (delta-change method), so
   every perturbed climate lies on the manifold a climate model actually produces.
2. **Hold relative humidity fixed** when scaling temperature (Clausius–Clapeyron), and disclose it —
   adding 6 K while leaving specific humidity alone produces impossible relative humidity.
3. Axes: temperature scale, precipitation scale, precipitation seasonality, radiation, interannual
   variability. Latin hypercube plus a small full-factorial core.
4. **Deliberately span beyond today's envelope**, where space-for-time is known to be sign-wrong.
5. **Constant CO₂ always** (`MEMORY.md:co2-closed`).
6. Cells stratified by the ~161 independent 15° tiles, so spatial folds mean something.
7. Run with `LPJ_IND_ALL_HEIGHTS` so the per-tree output is uncensored; the restart target is
   uncensored regardless.

### Restart synthesis (line D/T) — the approach

Do **not** predict 1.9 MB of consistent state from scratch. We always hold a real, valid restart for
the same cell under a nearby climate, so: **template-conditioned synthesis.** Every field is LEARNED
(the roster, the per-tree bad-years counter, soil carbon, litter), DERIVED (per-tree carbon pools from
the pipe model; the entire 20-year climate buffer computed straight from the climate input, not learned
at all; the sapling gene pool from the roster), COPIED (inert crop/nitrogen fields), RELAXED (the fast
soil water/ice/enthalpy/temperature block, taken from the template — it must be *mutually* consistent
and nothing validates it), or FREE (random seed, tree IDs).

Validation ladder, cheapest first: **t0** byte round-trip → **t1** config pre-flight accepts →
**t2** the C loads it and runs 1 year without aborting → **t3** 20 years with no drift beyond the
two-seed spread, **scored on a WINDOW MEAN — a real restart itself passes in only 90.9 % of cells,
and that is the ceiling** → **t4** the state distribution matches → **t5** = rung 4.

The **short polish run** fallback (write an approximate restart, let the C relax the fast state for
N years) is **dead, and not for the reason expected: measured at N = 1 it is a no-op** (+0.016 and
−0.005 for the two working synthesis versions). The model neither repairs the state nor rejects
it — it carries it. The lever has to be applied at year 0, in the synthesis.

### Model class (line T)
Target is a joint distribution over a variable-length roster in trait × size × age × growth-failure
space. Start with a **size-structured distribution head** (integral-projection style) as the
interpretable baseline that can pass rung 1 cheaply; target architecture is a **permutation-equivariant
set network with a stochastic per-tree head** (binomial-survival / Poisson-birth, conservative by
construction). No published vegetation-model emulator reproduces trait or size distributions at all.

## Now — the critical path, and what is actually datable

**Four of the five steps to the next verdict are done. The fifth has been owed for four sessions,
and nothing else in the repository is on the critical path.** The pilot corpus is built (200 cells
× 30 climates, 337 core-hours), and both experiments that consume it are SEALED with their nulls
derived and their bars written down before any model existed. What is missing is the model arm.

| the two sealed experiments | bar to beat | a pass needs | ceiling | owed by |
|---|---|---|---|---|
| **rung 1, the kill test** (`X-20260909-pilot-warming-response`) | **0.145690** — every cell changes by the same fraction of what it already has, NOT 0.0 | 0.225690 | 0.8697 | **T** |
| **rung 5, the held-out forcing leg** (`X-20260908-heldout-forcing-leg`) | 0.033749 | 0.0837 | 0.538490 | **T** |

Why the corpus had to exist first: a response obtained by SUBTRACTING two level predictions only
works where the true change is large against the level error (−0.727), and the existing data holds
one climate per location, so climate and place are inseparable. The designed ensemble is the only
identified path to a response, and it changes the target from a level to a change. ⚠ **The compute
was never the bottleneck**: the pilot is 20 minutes on 2048 cores. The sessions are.

Corpus v2 is unblocked as of 2026-09-14, both its open decisions answered by the owner: the genuine
high-emissions second run, and **species composition as a predicted, conjunctively scored quantity
— one rebuild, not two.** Composition is not one more quantity. The synthesiser COPIES it from the
template because nothing scores it, so an emulated warmed forest is structurally forbidden from
shifting its species mix at all — a candidate mechanism for the response failure, not a gap.

**Only the kill test's verdict is datable**, and it is the rung that can stop the project, which is
why it was placed early. Full acceptance (rung 7) has **no defensible date**: the conjunctive pass
rate is 0.0351 against an attainable ceiling of **0.5585, not 1.0** — 6 % of what is reachable
rather than 3.5 % of perfect — what closes that gap is unknown, and it needs the mid or full
corpus. A kill-test pass turns an unidentified problem into an ordinary fitting problem; only then
does a completion date mean anything. Detail: `lines/<L>/STATE.md`.
