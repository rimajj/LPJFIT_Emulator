# PLAN.md — the roadmap (budget: 150 lines, enforced)

The single roadmap. Design rationale goes in a decision record, not here. Agents append rung status
only; the ladder changes on an owner steer.

## The two products

| | **A — equilibrium** (primary) | **B — year-2100 transient** |
|---|---|---|
| Input | a 30-year climate summary | the 2019 state + the 2020–2100 climate trajectory |
| Output | the stationary forest that climate supports | the actual 2100 forest, still lagging climate |
| Truth | **new spin-ups we run**, incl. under 2090s climate | existing warming-run truth on disk |

Build A first. B reuses A's entire state-writing stack and adds a starting state as input.
⚠ **A's output row is the GOAL, not what corpus v1 holds** — v1's spin-ups carry a CO₂ ramp, so
their end state is not stationary. That is what `v2-constco2` is for; see rung 0's ⚠ below.

**Output stage 1** = what the emulator predicts natively (restart file + per-cell state summary).
**Output stage 2, on demand** = the model's own output files, in particular the per-tree CSV, got by
running the real C model **one year** from the emitted restart — it *is* the original model writing
them, so it is byte-genuine, including the four annual flux-accumulator columns that are not
functions of state. ~7 core-hours for all 54,020 cells.

## Why this can work when the predecessor could not

The existing data has exactly **one climate per location**, so climate and geography are collinear and
the warming response is not identified (`MEMORY.md:ident-limit`). The spin-up is per-cell and
embarrassingly parallel, so we **generate a designed climate-perturbation ensemble: the same cell
spun up under many climates**. That decollinearises climate from place by construction, and it is
the experiment the predecessor could never run.

## The gate ladder

Each rung is a pre-registered experiment. Status is updated here when a verdict lands.

| rung | question | kills if it fails | status |
|---|---|---|---|
| **0** | Does our reader/writer round-trip a real restart file byte-identically? | the restart deliverable entirely | **PASSED 2026-09-08** |
| **1** | **THE KILL TEST.** Given a cell's climate shifted by +4 K, can a model beat "predict this cell as it is today"? | the whole project, in ~week 3 for ~670 core-hours | **PASSED 2026-09-14 on the designed corpus: 0.5453 vs a bar of 0.2257, = 63 % of attainable.** (Failed −0.727 on the existing data, as expected there.) Never quote it without the blind-arm caveat below |
| **2** | Does the map meet `max(10 %, two-seed spread)` conjunctively per cell? | the science, not the engineering | **FAILED: 0.036 against a best null of 0.021, gate 0.071** |
| **3** | Is a synthesised restart file valid and stable in the real model? | the restart deliverable | **valid; carbon starts 6.7 % HIGH (never halved) and sheds to −1.6 % inside the band by yr 20; still fails conjunctively, 5 % against a 25 % ceiling** |
| **4** | **End-to-end.** Emulated restart → real transient vs real restart → real transient. | the deliverable as a whole | blocked on rung 3's state fidelity |
| **5** | Does the response survive a **held-out forcing leg**? | the warming claim | **FAILED 2026-09-14 at pre-named outcome (c), 0.0054 vs persistence 0.0337** — the scenario legs cannot train a response. Not a contradiction of rung 1; see below |
| **6** | Product B, and stage-2 output reconstruction. | product B only | not started |
| **7** | All 54,020 tree-bearing cells, both scenarios, at acceptance-grade patch count. | acceptance | not started |
| **8** | **Can the species mix shift, and can that be learned?** | the synthesiser copying composition | **PASSED 2026-09-15: 0.425610 vs a sealed bar of 0.337858, best null 0.177858; 49 % of the attainable 0.863852.** Copying composition is a measured defect, not a free simplification |

### Rung 0 — format round-trip (line D). PASSED.
100 real cells, 360,183 B → 3,546,287 B, byte-identical, plus both `.clm` inputs. `binfmt.md`.

⚠ **CORRECTED 2026-09-15: the spin-up DOES converge — the late rise is CO₂, and this was our error.**
It runs model years 1000–1999 against a **transient** CO₂ file, so its last 300 years carry the real
historical rise, +32.8 %. While CO₂ is pinned the curve is flat to **+0.15 %/century**; over the ramp
it climbs +5.53 %/century at **r = +0.987** with CO₂. The old "not converged" fitted its trend over a
window lying entirely inside that ramp. Found by the owner asking why a single cell showed no rise.
**Every corpus run shares the identical CO₂ path, so no score is confounded and rungs 1 and 5
stand** — but v1's target is a forest still adjusting to a CO₂ step, not an equilibrium. **`v2-constco2`
is now BUILT, RUN AND DECODED** (6,000/6,000, 2026-09-15): pinning CO₂ costs **24 % of the vegetation
carbon**, with stems **+4.0 %** — a younger, lighter forest — while the treeless rows are unchanged at
380/6,000, so it changes *how much* forest there is, not *where*; that matches the global spin-up
curve's +21.2 % over the ramp. **No budget drops**: a shorter run ends at a different CO₂, so it is a
different state. `docs/reference/corpus-design.md`; record `20260915-D-the-spinup-did-converge-*`.

### Rung 1 — the kill test. PASSED 2026-09-14 (`X-20260909-pilot-warming-response`, line X)

**The project's first positive result: the warming response IS learnable where it is identified.**
Basis: pilot corpus v1, 200 cells × 30 climates × 1 seed, one binary, within-cell paired contrasts
under spatially blocked folds — the same cell under 30 climates separates climate from place, which
the existing data cannot do. The model predicts how a forest *changes* at **0.545304** against
**0.145690** for the best information-free competitor (every cell changes by the same fraction of
what it has — NOT zero), on a bar of **0.225690**, beating it at **all 29 of 29 levels**. **Quote it
as 63 % of attainable** — the ceiling is 0.869730 and is itself a lower bound — never against 1.0.

⚠ **What must travel with that headline.** A model **blinded** to which perturbation it is asked
about scores **0.349462, above the bar** — every pre-registered null was information-free, so none
was a learned-but-treatment-blind competitor. The pass survives it (**+0.195842**) and a per-cell
scramble falls below blind, so the model does read the forcing; but the headline is **64 % blind
skill**, and "predicts the warming response" without that number overstates it.

### Corpus tiers (line D)

| tier | design | spin-ups | core-hours | wall @2048 | disk |
|---|---|---|---|---|---|
| pilot | 200 cells × 30 climates × 1 seed | 6,000 | 670 | ~20 min | 11 GB |
| mid | 1,000 × 100 × 2 | 200,000 | 22,200 | ~11 h | 380 GB |
| full | 3,000 × 200 × 2 | 1,200,000 | 133,000 | ~65 h | 2.3 TB |

Seven design rules, each with the reason it is not optional: `docs/reference/corpus-design.md`.
⚠ **Rule 5 is the one that bit**: constant CO₂ is not the default and v0/v1 do not have it.

### Restart synthesis (line D/T) — the approach

Do **not** predict 1.9 MB of consistent state from scratch. We always hold a real, valid restart for
the same cell under a nearby climate, so: **template-conditioned synthesis.** Every field is LEARNED
(roster, per-tree bad-years counter, soil carbon, litter), DERIVED (carbon pools from the pipe model;
the 20-year climate buffer straight from the climate input; the sapling gene pool), COPIED (inert
crop/nitrogen), RELAXED (the fast soil water/ice/enthalpy/temperature block, from the template — it
must be *mutually* consistent and nothing validates it), or FREE (random seed, tree IDs).
⚠ **Species composition is COPIED today and that is now a measured defect** — see rung 8.

Validation ladder, cheapest first: **t0** byte round-trip → **t1** config pre-flight accepts →
**t2** the C loads it and runs 1 year without aborting → **t3** 20 years with no drift beyond the
two-seed spread, **scored on a WINDOW MEAN — a real restart itself passes in only 90.9 % of cells,
and that is the ceiling** → **t4** the state distribution matches → **t5** = rung 4.

The **short polish run** fallback (let the C relax the fast state for N years) is **dead, and not
for the reason expected: at N = 1 it is a no-op** (+0.016 and −0.005). The model neither repairs the
state nor rejects it — it carries it. The lever has to be applied at year 0, in the synthesis.

### Model class (line T)
Target is a joint distribution over a variable-length roster in trait × size × age × growth-failure
space. Start with a **size-structured distribution head** (integral-projection style) as the cheap
baseline; target architecture is a **permutation-equivariant set network with a stochastic per-tree
head** (binomial-survival / Poisson-birth, conservative by construction). No published
vegetation-model emulator reproduces trait or size distributions at all.

## Now — the critical path

**Rung 1 passed on 2026-09-14, and that is the hinge.** Whether a warming response could be learned
at all was the question that could stop this project; where climate and place are separable, it can.
Rung 5's failure the same day is not a contradiction — the *existing scenario legs* cannot train a
response, which is why the designed ensemble exists. Rungs 3–4 are blocked on state fidelity, not on
identification. ⚠ **Compute was never the bottleneck — the sessions are.**

**The second seed RAN on 2026-09-15 and discharged all five asks at once** (`pilot-v1-s2`, 20 cells
× 30 climates, 600 spin-ups). **The model's own run-to-run spread does NOT widen under climate
perturbation**: median 0.0301 against 0.0310 at present-day climate, 20.4 % of cell-quantities above
the 10 % floor either way. So **X4 is retired as the WRONG INSTRUMENT, not as a failure** — the floor
dominates 79.6 % of cell-quantities, the conjunctive level statistic has no power, and a replacement
needs a **new estimand**, never a widened floor (a threshold chosen after seeing the values). The
transferred band was legitimate all along, so nothing scored to date needs recomputing; `ABS_FLOOR`
= **0.0384**, measured; and the 2.7 % soil-carbon offset is a **real bias**, against a median
two-seed spread there of 1.43 %.

**And the species-mix kill test passed** (rung 8), turning the synthesiser's copying of species
composition from a disclosed simplification into a measured defect — now line T's principal build.

| open, in value order | owner | blocked on |
|---|---|---|
| **re-score rungs 1 and 8 on `v2-constco2`**, and restate both verdicts' wrong "constant CO₂" basis wording | **X** | nothing — v2 landed 2026-09-15 |
| **stop `models/synth.py` copying species composition**; it needs its own t0–t4 pass, not just a score | **T** | nothing |
| a NEW estimand for the emitted restart, replacing X4 | **X** | nothing |
| the additive band floor in the shared scorer, now with a measured 0.0384 | **X** | nothing |
| one cell, one year, two binaries, byte-compared — the only unproven rung-5 claim | **D** | nothing |
| 38 open ledger rows whose results have ALL landed; they block every merge from 2026-09-22 | **D T X** | nothing |

**Full acceptance (rung 7) has no defensible date**: the conjunctive pass rate is 0.0351 against an
attainable ceiling of **0.5585, not 1.0**, what closes that gap is unknown, and it needs the mid or
full corpus. ⚠ **That severity is not the emulator's alone** — one REAL realisation of the model
passes the same 22-quantity test in only **0.470** of its own 200 pilot cells. `lines/<L>/STATE.md`.
