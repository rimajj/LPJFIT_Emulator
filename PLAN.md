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
| **1** | **THE KILL TEST.** Given a cell's climate shifted by +4 K, can a model beat "predict this cell as it is today"? | the whole project, in ~week 3 for ~670 core-hours | **PASSED, AND RE-PASSED WITH CO₂ PINNED 2026-09-21: 0.5590 vs a bar of 0.2577, = 66 % of the attainable 0.8485** (on the CO₂-ramped v1 it was 0.5453 vs 0.2257). (Failed −0.727 on the existing data, as expected there.) Never quote it without the blind-arm caveat below |
| **2** | Does the map meet `max(10 %, two-seed spread)` conjunctively per cell? | the science, not the engineering | **FAILED: 0.036 against a best null of 0.021, gate 0.071** (existing runs, one climate per place). **On the settled-forest corpus, climate + soil only (owner's Product A, 2026-09-23): PASSED, 0.608 variance explained vs 0.098 analogue lookup, bar 0.223, = 64 % of the attainable 0.950 — but 0.0 % within a flat 10 % on all 22 (one real run: 4.9 %)** |
| **3** | Is a synthesised restart file valid and stable in the real model? | the restart deliverable | **valid; carbon starts 6.7 % HIGH (never halved) and sheds to −1.6 % inside the band by yr 20; still fails conjunctively, 5 % against a 25 % ceiling** |
| **4** | **End-to-end.** Emulated restart → real transient vs real restart → real transient. | the deliverable as a whole | blocked on rung 3's state fidelity |
| **5** | Does the response survive a **held-out forcing leg**? | the warming claim | **FAILED 2026-09-14 at pre-named outcome (c), 0.0054 vs persistence 0.0337** — the scenario legs cannot train a response. Not a contradiction of rung 1; see below |
| **6** | Product B, and stage-2 output reconstruction. | product B only | not started |
| **7** | **Owner, 2026-09-24:** as good as a rerun, on the 56,986 cells with a stem, 25 patches, CO₂ 276.59, against the STORED spin-up's constant-CO₂ years (no new runs). | acceptance | **FAILS, measured 2026-09-24.** Vegetation carbon (the only per-cell quantity stored): 24.7 % of cells in band vs a rerun's 85.9 % (pilot-trained, D −0.612; trained on the spin-up itself 42.7 %). Full state, pilot: 0.36 % vs 10.35 % (D −0.100, below a neighbour lookup). `X-20260924-spinup-vegc-*`, `-pilot-state-asgood` |
| **8** | **Can the species mix shift, and can that be learned?** | the synthesiser copying composition | **PASSED, AND RE-PASSED WITH CO₂ PINNED 2026-09-21: 0.4459 vs a bar of 0.3002, 52 % of the attainable 0.8629** (on v1: 0.4256 vs 0.3379). Copying composition is a measured defect, not a free simplification, and not a CO₂ artefact. ⚠ fails 2 of 29 levels, both cold. ⚠ **A model BLIND to the climate change scores 0.3079 and clears that bar by itself** (2026-09-23): only ~+0.138 of the 0.4459 reads the forcing |

### Rung 0 — format round-trip (line D). PASSED.
100 real cells, 360,183 B → 3,546,287 B, byte-identical, plus both `.clm` inputs. `binfmt.md`.

⚠ **CORRECTED 2026-09-15: the spin-up DOES converge — the late rise is CO₂, and this was our error.**
Its last 300 model years carry the historical CO₂ rise and the old "not converged" fitted a trend
inside that ramp; pinned, the curve is flat. No score was confounded — every run of a version shares
one CO₂ path — but a v1 end state is a forest still adjusting to a CO₂ step. **`v2-constco2` is
BUILT, RUN, DECODED AND NOW SCORED**: pinning CO₂ costs **24 % of the vegetation carbon**, changing
*how much* forest there is, not *where*, and **rungs 1 and 8 re-pass on it**. **No budget drops** —
a shorter run ends at a different CO₂. `docs/reference/corpus-design.md` §Rule 5.

### Rung 1 — the kill test. PASSED 2026-09-14, RE-PASSED AT CONSTANT CO₂ 2026-09-21 (line X)

**The project's first positive result: the warming response IS learnable where it is identified.**
Basis: 200 cells × 30 climates × 1 seed, one binary, within-cell paired contrasts under spatially
blocked folds — the same cell under 30 climates separates climate from place, which the existing
data cannot do. The model predicts how a forest *changes* at **0.5590** against **0.1627** for the
best information-free competitor (every cell changes by the same fraction of what it has — NOT
zero), on a bar of **0.2577**, beating it at **all 29 of 29 levels**. **Quote it as 66 % of
attainable** — the ceiling is 0.8485 and is itself a lower bound — never against 1.0. On the
CO₂-ramped v1 it was 0.5453 / 0.1457 / 0.2257, ceiling 0.8697 (`X-20260909-*`); the current basis
is `X-20260921-pilot-warming-response-constco2-resealed`.

⚠ **What must travel with that headline.** A model **blinded** to which perturbation it is asked
about scores **0.3623, above the bar** — every pre-registered null is information-free, so none is
a learned-but-treatment-blind competitor. The pass survives it (**+0.1966**, v1: +0.1958) and a
per-cell scramble falls below blind, so the model does read the forcing; but the headline is
**65 % blind skill**, and "predicts the warming response" without that number overstates it.

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
the same cell under a nearby climate, so: **template-conditioned synthesis** — each field is
LEARNED, DERIVED, COPIED, RELAXED or FREE. Validation ladder, cheapest first: **t0** byte round-trip
→ **t1** config pre-flight → **t2** the C runs 1 year → **t3** 20 years without drift → **t4** the
state distribution matches → **t5** = rung 4. The **short polish run** fallback is **dead, and not
for the reason expected: at N = 1 it is a no-op** — the model carries a bad state rather than
repairing or rejecting it, so the lever belongs at year 0, in the synthesis. ⚠ **Species
composition is COPIED and that is a measured defect** — rung 8. `docs/reference/restart-synthesis.md`.

### Model class (line T)
Target is a joint distribution over a variable-length roster in trait × size × age × growth-failure
space. Start with a **size-structured distribution head** (integral-projection style) as the cheap
baseline; target architecture is a **permutation-equivariant set network with a stochastic per-tree
head** (binomial-survival / Poisson-birth, conservative by construction). No published emulator
reproduces trait or size distributions at all.

## Now — the critical path

**Owner, 2026-09-24, and it reframes everything below rung 7.** CO₂ fixed at 276.59 ppm. Pass rule:
**as good as a rerun** of the model, per cell. Acceptance cells: the **56,986** with any stem, 25
patches. **No new runs**: "there is spinup, ssp370 and ssp126 available already; in the spinup only
the years until the onset of rising CO₂ should be used; the SSPs only go 100 years, so no
equilibrium. For now make the emulator work for the spinup with constant CO₂; when that works I
will give you more data." So the mid tier and the all-cell truth campaign are **PARKED**, not owed.
Record: `20260924-INT-*`.

⚠ **What the stored spin-up can test.** Model years 1000–1699 recycle the 1901–1930 climate at
constant CO₂; per cell it kept **only vegetation carbon** (both seeds, every year) — no restart and
no traits before 1999. So the all-cell test exists for vegetation carbon only; tree counts and
traits are tested on the pilot, whose full second seed ran 2026-09-23 (6,000/6,000).

**Where the emulator stands (2026-09-24), all against the owner's rule:**

| test | emulator | rerun | best lookup |
|---|---|---|---|
| vegetation carbon, 56,986 cells, trained on the pilot | 24.7 % (variance expl. 0.926) | 85.9 % | 18.4 % |
| same, trained on the stored spin-up's own cells | 42.7 % (0.961) | 85.9 % | 33.1 % |
| full state, 19 quantities at once, pilot 6,000 rows | 0.36 % | 10.35 % | 3.25 % |

It has the broad pattern and misses cell-level precision; even 57,000 training cells leave most cells
outside 10 % on vegetation carbon. ⚠ The full-state conjunction is failed by the model itself in 90 %
of rows: it rewards getting every quantity of one forest right at once.

| open, in value order | owner | blocked on |
|---|---|---|
| **the Product A chain for the spin-up**: held-out predictions for every cell's 1901–1930 climate → a synthesised restart for all 56,986 cells (`synth_global.py`) → the model loads it and stays near the stored equilibrium | T/D | the synthesis branch's review |
| **cell-level precision**: daily-forcing features and learner capacity, screened on dev folds only (`int/features`), then a sealed confirmation on untouched folds | T | nothing |
| **a coherent forest, not 19 separate regressions** — the conjunctive test needs every quantity of one row right together | T | the screen's result |
| synthesised established stems die at 2× the model's rate in year 1 even from a perfect prediction | T | nothing |
| the emitted-restart test is SEALED (`X-20260924-restart-worst-quantity`); its model arm waits on re-running the synthesiser against the final map | X | the synthesis merge |

**Still standing:** both kill tests (rungs 1, 8) with their blind-arm caveats; the equilibrium map
passes its skill test (0.608 vs a 0.223 bar). The two model builds write byte-identical restarts for
one cell-year (`20260923-D-the-two-builds-*`). ⚠ A rerun-grade vegetation-carbon map is the next
milestone the owner's "when that works" can be read against; full-state rerun grade is further.
