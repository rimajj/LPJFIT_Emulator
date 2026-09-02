# Exploration note — what the published literature actually says about a learned vegetation emulator

* **Line:** X (project direction & exploration). **Status:** exploration note, not a decision.
* **Date:** 2026-08-19. **Belongs to:** the open owner conversation recorded in ADR 0310 (a purely / more
  data-driven emulator). **Nothing here has been raised with line S, M, E or O, or written to `MEMORY.md`.**
* **Basis:** one literature agent of the round-2 campaign (`wf_5ba7e1aa-b45`, item S2), which read the two
  most load-bearing papers as full PDFs and the rest via full-text extraction. **Read §6 before quoting any
  single digit.**

ADR 0310 §6 named three literature families it had been missing and said the closest precedent **should be
read before designing anything**. This note is that reading. It changes the picture in four places, corrects
ADR 0310 in three, and supplies — for the first time in this project — a *published, quantified mechanism* for
the response inversion we measured ourselves.

---

## 1. The two counts that frame everything

Both were pre-registered with an expected value of 0, and both came back 0.

| statistic | value |
|---|---|
| published works reporting a skill number for a **distributional** target (a size or trait distribution, not an aggregate and not a coarse categorical class) under a **held-out forcing**, with a stated null | **0** |
| published works whose held-out forcing lies **outside** the trained range and whose response was still correct | **0** |

The second is the important one. **Every published success is a bracketed interpolation** — the test forcing
sat *between* two forcings already in the training set:

* the LPJ-GUESS emulator held out the two middle emissions pathways while training on the lowest and highest
  [SOURCE, the paper says so in as many words];
* the atmosphere emulator ACE2-SOM held out tripled CO2 while training on 1×, 2× and 4× [SOURCE];
* the forest-landscape emulator held out one of four climate scenarios spanning a common range [SOURCE].

**And every attempt at genuine extrapolation in those same papers failed** — twice with the authors naming it
as a fundamental limitation of purely learned models.

⇒ **A design consequence, immediately.** The moderate-emissions run that finished on 2026-08-18 (ADR 0310 §7.1)
warms about **0.227×** the high-emissions run on a common baseline, so the historical period and the
high-emissions run **bracket** it. That is the exact analogue of the tripled-CO2 test, and it is **the only
held-out-forcing design in this literature with any precedent for succeeding.** Its build provenance has to be
gated first (a different binary date).

---

## 2. The closest precedent does much less than we credited it with

**Natel et al. 2025, *Geoscientific Model Development* 18, 4317** — a machine-learning emulator of LPJ-GUESS.
ADR 0310 recorded it as *"97 % runtime saving, and a neural net extrapolating BETTER than a random forest to
2100"*, on grid-cell carbon. **Three corrections, in ascending order of importance:**

1. The headline saving is **95 %**, not 97 % [SOURCE, abstract]. (The paper is internally inconsistent here —
   its own equation applied to its own wall-clock numbers, 5765 s versus 1.3 s and 2.8 s on the same
   344-cell, 165-year benchmark, gives 99.93 %. Report the paper's 95 % and the raw times separately.)
2. The neural net beats the random forest **only for vegetation carbon and only in the warmer pathways**
   [SOURCE, Table 3 + §4.1.2]. The random forest is better in the historical period, better for soil carbon,
   and better for heterotrophic respiration. The unqualified "extrapolates better" is wrong.
3. ⚠ **It is not a state operator at all.** It is a **static regression** from (climate, soil, pre-disturbance
   carbon pools, years since the last stand-replacing disturbance) to six carbon numbers, with **no state fed
   forward** [SOURCE, §2.2 + Table 1]. It cannot drift, cannot go unstable, and cannot be tested for error
   compounding — so **it carries no information about the rollout question, in either direction.** It also
   never sees LPJ-GUESS's own cohorts or patches. This is a bigger correction than the 95-vs-97 one.

**Its actual skill, on the quantity closest to ours.** Living-vegetation carbon, out-of-sample cells:
**0.79 / 0.81** (neural net / random forest) in the historical period, falling to **0.52 / 0.54 / 0.57 / 0.62**
and **0.59 / 0.58 / 0.60 / 0.61** for the four future pathways [SOURCE, Table 3]. Two things about that:

* the drop from ~0.80 to ~0.55 **is the paper's real result and is invisible in its headline error metric**,
  which is normalised by the range of the data;
* the cells were split **randomly, not spatially blocked** [SOURCE, §3.1], so even 0.80 is a
  spatial-interpolation score and an upper bound;
* **no null of any kind is reported** — no persistence, no climatology, no geographic address.

**Two things in that paper nobody would find from the abstract, and both matter more than its positive result:**

* ⛳ **Its own unadvertised negative result.** Their *first* approach trained on stylised factorial
  perturbations of temperature, precipitation and CO2, and *"the trained models failed to extrapolate
  effectively to the real CMIP6 climate change scenarios"*. Pre-training on the factorial set and fine-tuning
  on the realistic one **also failed, in two distinct ways** — either the model stayed biased toward the
  factorial data, or *"flexible weight adaptation during fine tuning effectively erased the pre-trained
  knowledge"*. Their own conclusion, verbatim: *"This highlights a fundamental limitation of purely ML-based
  emulators: they lack the structural constraints of process-based models and may fail to generalize across
  divergent data distributions."* [SOURCE]
* ⛳ **They decline to let their own emulator carry the state.** In the coupled framework it was built for, the
  emulator is a fast five-year lookahead inside an optimisation loop, and then: *"to maintain realism in
  projections, the emulator will not be used to simulate actual carbon outcomes for the next 5 years… Instead,
  LPJ-GUESS will be employed to simulate carbon dynamics during that period, and the emulator will resume
  operation in the next coupling cycle."* [SOURCE]
* ⚠ **It contains the exact leak this project found in its own count model.** Soil carbon scores **0.98–0.99**,
  and the discussion says why: the initial soil-carbon pool is one of the input features, and *"the inclusion
  of the highly correlated initial SoilC pool likely simplified the learning task, potentially inflating
  emulator accuracy metrics for SoilC"* [SOURCE]. Published, self-diagnosed, and left in the headline table.

---

## 3. The most damaging result is from forestry, not machine learning — and it names our own failure

**Perret, Evans & Sax 2024, *PNAS* 121(1):e2304404120.** 339 individual ponderosa pines, 23 populations across
western North America, fitted 1900–2015 and validated against observed growth 1982–2015.

**The climate–growth relationship read off geography has the OPPOSITE SIGN to the one read off time.** Trees
grow faster in *warmer places*; the same trees grow slower in *warmer years* [SOURCE]. Consequently a model
fitted to the spatial gradient was *"wrong in both magnitude and direction"*: its correlation with observed
growth turns **negative above about 0.5 °C of warming** (r = −0.42, P = 0.04), and by 2100 under the high
pathway it predicts growth **increases of up to +300 %** where the temporal model correctly predicts declines
[SOURCE]. The temporal model is the control here, and it wins.

**Why this is the most important paper in the set for us.** ADR 0310 §7.6 measured that 95.1 % of cells' 2090s
temperature falls inside today's spatial range and concluded space-for-time is *"viable in interpolation"*.
**Being inside the spatial envelope is not sufficient** — the spatial and temporal responses can have opposite
signs at every point inside it. So:

* the **geographic-address null is not merely a competing explanation to report beside a number — it is a
  diagnosis.** A model that scores well on hash folds and collapses on spatially blocked folds is not
  "somewhat spatial"; it is potentially *sign-wrong* on the response.
* this is, as far as this reading found, **the first named mechanism anyone in this project has for the
  measured −0.226 response inversion.**
* ⚠ **Flag it `[REASONED]` wherever it is used to explain our own numbers.** The paper is about annual ring
  width in one species; the transfer is an inference. It is a strong one — the quantity is growth, which drives
  the growth-efficiency mortality hazard, and the mechanism has a direct analogue (their spatial pattern
  reflects multi-generational local adaptation, ours reflects which trait values have survived where; their
  temporal response is plasticity away from a local optimum, ours is the same trees pushed off their sampled
  optima) — but our oracle has no adaptation and no migration, so the mechanism is **not identical**.

**The only form the literature says can work:** a model whose skill survives spatially blocked folds and whose
response is fitted **on the time axis within cells**.

---

## 4. Where the literature is POSITIVE — and it is positive about exactly the architecture our own critic proposed

**Cozzi et al. 2025, arXiv:2505.21426** — a permutation-invariant graph network over **individuals** with a
**stochastic (diffusion) output head**, versus the identical network with an averaging head:

| statistic | full model | deterministic-head ablation |
|---|---|---|
| individual-level distribution error (Earth Mover's Distance), three settings | 0.06 / 0.15 / 0.18 | 0.06 / **0.35 / 0.40** (2.2–2.3× worse) |
| aggregate error 25 steps **beyond** the 10-step training horizon | < 0.1 / < 0.2 / < 0.2 | > 0.4 / > 0.6 / > 0.5 |

Its own ablations are the nulls — a graph-free head and a deterministic head — and an AR(1) aggregate baseline
is also reported and fails on cyclic dynamics [SOURCE]. **This is direct published support for ADR 0310 §5.4's
architecture (keep the individuals) and §5's stochastic-head recommendation, together.**
⚠ **Do not cite it as precedent for the warming response:** it is a non-peer-reviewed preprint, its systems are
a 1950-agent segregation model and a 2048-agent predator-prey model, and it reports **no held-out-parameter
test at all.** Evidence for the *architecture* and the *head*, not for forcing transfer.

**And one result that cuts FOR the owner and should not be buried.** Rucker et al. 2025 (arXiv:2511.00274), on
reproducing forced regional temperature trends 1981–2014: *"a fully data-driven AI emulator can perform
comparably to, or better than, hybrid and physics-based models in capturing regional thermodynamic trends"*,
with the purely learned model best of all on the vertical structure of midlatitude warming [SOURCE]. So
**"the hybrid must win" is not a safe prior.** Its qualifier is the authors' own: the test is in-distribution,
and neither model captures heat-extreme or drying trends over the US Southwest or South America.

---

## 5. Where the literature is NEGATIVE about purely learned surrogates

**Dyer et al., NeurIPS 2024, "Interventionally Consistent Surrogates"** — an agent-based epidemic model, held-out
test set of 1000 trajectories, the intervention a lockdown:

* a surrogate trained on observational trajectories is **2.7× to 14.2× worse** on the interventional test set
  than one trained on interventional data [SOURCE, Table 1];
* ⚠ **and it is BETTER on the observational test set** (2.952 vs 4.134 for one family) — so **the failure is
  undetectable from observational skill**;
* it gets the **sign** wrong: *"the observationally trained surrogate predicts that the lockdown will
  temporarily INCREASE infections"* where the simulator shows a decrease; in policy ranking it called
  no-intervention the *best* option in 1 of 5 repeats [SOURCE, Fig. 5 + §5];
* ⛳ **the hybrid family won on both criteria:** *"the LODE-RNN — which combines the 'mechanistic' SIRS ODE with
  a flexible RNN — achieves the best interventional and observational consistencies of all surrogates"*
  [SOURCE]. The pure learned recurrent network is the comparator, and it loses.

**ACE2-SOM (Clark et al. 2025, JGR-MLC, DOI 10.1029/2024JH000575)** is the best held-out-forcing result in any
earth-system domain, and it comes with the matching negative: on held-out tripled CO2 it beats a real physics
baseline by 70–74 % RMSE at ~1/25 the cost, but **forced outside the equilibria it was trained on (abrupt
quadrupling) it reaches the new equilibrium in about three years while violating global energy conservation**,
with spurious radiative sensitivities. The paper's own conclusion restricts such models *"to emulating the
climate of roughly the last…"* the range they were trained on [SOURCE]. ACE2's own abstract is equally blunt:
it reproduces El Niño and the 80-year temperature trend, *"however, its sensitivities to separately changing
sea surface temperature and carbon dioxide are not entirely realistic"* [SOURCE].

---

## 6. Two corrected precedents, and the hybrid nobody here has considered

**Rammer & Seidl 2019 (*Methods in Ecology and Evolution*, DOI 10.1111/2041-210X.13171)** — the one real
precedent for a century-scale autoregressive *vegetation state* operator, emulating the individual-based forest
model iLand. Corrected numbers: the state space is **514 000 potential** states (6597 height × 26 composition ×
3 leaf-area classes) of which **1 418 were realised in training**; trained on 16.8 million transitions;
one-step accuracy **85.7 %** (target state) and **86.3 %** (time to transition), 97.1 % top-3; over 500 years,
cell-wise accuracy **0.565** composition, **0.602** structure, **0.946** functioning. The 500-year test used a
scenario **not used for training** — a genuine (bracketed) held-out forcing. **No baseline reported.**
It **samples** transitions from the predicted probability distribution rather than taking the most likely one
[SOURCE] — a second precedent for a stochastic head.

⛳ **And the architecture in it that nobody in this project has considered.** It preserves the *within-state*
attribute distributions **by table lookup** — a database of the full attribute distribution per (discrete state
× residence time), compiled from 7.7 × 10⁷ process-model data points — rather than by learning them. That is a
hybrid of a different kind from ours: **learn a coarse transition operator, and recover the distribution by
looking it up in the oracle's own output.** Worth pricing.

**Astola et al. 2026 (*Silva Fennica* 60(1):25012)** — the only autoregressive, rolled-out *cohort-level* forest
emulator found. Trained on 29 619 Finnish inventory plots × 10 climate realisations, tested on 11 850 held-out
plots. Relative RMSE over a **25-year** rollout: tree height **5.5–6.9 %**, stem diameter **6.5–7.0 %**, basal
area **12.0–21.0 %**, net primary production **11.6–22.0 %**; bias within ±2 % [SOURCE]. **Against our own 10 %
tolerance, height and diameter pass and basal area and productivity fail** — at 25 years, on stand means, on a
managed-forest inventory problem far easier than ours. No null reported, and explicitly **not** size
distributions.

**And the process models themselves are not clean on this target** (Eckes-Shephard et al. 2025, *New
Phytologist* 248(6):2722): across nine vegetation demographic models the shape of the stem-count-by-diameter
distribution is *"generally captured"* but with systematic biases — small size classes over-estimated at
boreal/temperate sites and under-estimated at the tropical site, large trees predicted where none were
observed; 6–7 of 9 over-estimate growth and 6–8 of 9 under-estimate carbon turnover time [SOURCE].

**ADR 0310 §6's claim that no published DGVM emulator reproduces trait or size distributions SURVIVED a
deliberate attempt to refute it** — the three nearest candidates each fail explicitly (cohort means, not
distributions; table lookup, not learned; grid-cell carbon).

---

## 7. The null problem is a field-level gap, not a local failing

Three of the four vegetation/forest emulator papers report **no baseline of any kind** (Natel et al. 2025;
Rammer & Seidl 2019; Astola et al. 2026). Every machine-learning weather/climate and surrogate-methodology
paper reports a real one — a coarser physics model at 25× the cost, an operational ensemble, or explicit
ablations. ⇒ ADR 0310's decision 4 proposed a reporting rule as a local method observation; **the literature
says it is a gap in the vegetation-emulator field specifically, and that the neighbouring field has already
solved it.** Any number we produce without its null beside it will be indistinguishable from those.

---

## 8. Reliability of this note — read before quoting a digit

* **Full PDFs read page by page:** Natel et al. 2025, Dyer et al. 2024. Their numbers are direct quotations
  and are the most reliable here.
* **Extracted from HTML/PMC full text by a summarising model (SOURCE-with-one-hop):** Rammer & Seidl 2019,
  ACE2 / ACE2-SOM, Rucker et al. 2025, Perret et al. 2024, Astola et al. 2026, Eckes-Shephard et al. 2025,
  Cozzi et al. 2025. **High confidence in direction and qualitative claims, medium in the last digit — if one
  becomes load-bearing in an ADR, re-verify it against the paper.**
* **Not read:** GenCast's and NeuralGCM's full texts (over the fetch size limit). GenCast's headline (greater
  skill than the operational ensemble on 97.4 % of 1320 targets, Nature 637:84) is a verbatim abstract quote.
  ⚠ **The number we would actually want — how much variance or extreme-quantile amplitude a deterministic head
  loses versus a generative one, in a FORCED-RESPONSE setting rather than a weather setting — was not obtained
  and may not exist.** The mechanism is universally stated in that literature and its direction is not in
  doubt; the only quantification on a *close* problem is Cozzi et al.'s ablation above.
* **Not fully discharged:** the integral-projection-model sub-item. Kernels over size *and* traits are standard
  (Ellner, Childs & Rees 2016; Merow et al. 2014), eco-evolutionary variants projecting a heritable trait
  distribution under selection exist (Rees & Ellner 2016), and hidden per-individual state has two published
  forms — shared-frailty hazard models fitted to individual tree mortality (DOI 10.1007/s13253-015-0217-2) and
  the integral-projection/Lefkovitch extension for unmeasurable within-stage development (Castaño 2017).
  **What was NOT found is any published case of a fitted demographic kernel being transferred to a climate
  outside its fitting range and validated there.** ⇒ treat *"the IPM literature already answers the
  hidden-state objection"* as **true for fitting and unaddressed for transfer.**
* **Staleness check (trap 4):** the newest records were checked (line S is at ADR 0245). The 0170–0189 block was
  not re-read in full, so if one of those contains a literature review of these families, this note duplicates
  it; nothing in the titles suggests one.

---

## 9. What this note changes

**Four things become design constraints rather than preferences:**

1. **The held-out-forcing test must be a bracketed interpolation** — the only design with published precedent
   for succeeding. The moderate-emissions leg is bracketed by the historical period and the high-emissions leg.
2. **The target must be the distribution and the head must be stochastic** — the one leg the literature now
   supports positively, at 2.2–2.3× on distributional error, and the only precedent that survived 500 years
   also samples rather than taking the most likely outcome.
3. **Spatially blocked folds and a geographic-address null are not hygiene, they are the diagnosis** — because
   the spatial and temporal climate responses can have **opposite signs** inside the same envelope.
4. **A skill number without a null is worth nothing here** — the field it comes from does not report them, and
   the one paper that scores 0.98–0.99 explains in its own discussion that the reason is a leaked input.

**And two results point in opposite directions, which is worth stating plainly rather than resolving:** a purely
learned atmospheric emulator matched or beat a hybrid on forced regional trends *inside* its training
distribution, while a hybrid surrogate beat every purely learned family on getting the *sign of a response to a
changed condition* right. **The owner's stated hope is the second of those.**
