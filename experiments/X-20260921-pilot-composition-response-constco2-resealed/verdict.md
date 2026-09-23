# Verdict — X-20260921-pilot-composition-response-constco2-resealed

outcome: pass

**Question.** Shown a cell's real present-day forest and a perturbed climate, can the emulator predict HOW THE SEVEN TREE TYPES' STEM SHARES CHANGE better than the best information-free competitor -- when the target state is a genuine equilibrium rather than a forest still climbing a CO2 ramp?
X6 (`X-20260914-pilot-composition-response`) answered YES on pilot corpus v1, at 0.425610 against a bar of 0.337858, and that is what turned the synthesiser's copying of species composition from a disclosed simplification into a MEASURED capability gap -- currently line T's principal build. A finding that redirects a line's work should not rest on a corpus whose end state is not the product's target. v1's spin-up ran against a transient CO2 file, so its last 300 years carry a +32.8 % CO2 rise; corpus v2-constco2 pins CO2 and re-runs the identical design, and the resulting forest holds 24 % less vegetation carbon.
⚠ AND COMPOSITION IS THE ARM WHERE A CO2 CHANGE IS MOST LIKELY TO BITE, WHICH IS WHY THIS IS NOT BOOKKEEPING. CO2 fertilisation is not type-neutral in LPJmL-FIT: it acts through photosynthesis and water-use efficiency, so a CO2 ramp is itself a competitive re-weighting between types. Some of the shift X6 measured could have been the corpus's CO2 transient rather than its climate perturbation. THE FALSIFIABLE CLAIM: the learnable composition response is a CLIMATE response and survives with CO2 held fixed, clearing a bar derived from v2's own nulls by the same construction X6 used.
If it does not, the case for building a composition head weakens, and line T's principal build was redirected by a CO2 artefact.

**Estimand.** `skill_composition_mean` — UNCHANGED FROM X-20260914-pilot-composition-response, deliberately and to the letter. Only the corpus varies. For each of the seven tree PFTs, the type's STEM SHARE is bincount(type ids) / total stems in the cell's end-of-spin-up roster. Compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) pooled over all scored (cell, climate) pairs, where dtrue = share(cell, perturbed point) - share(cell, control) is a WITHIN-CELL PAIRED CONTRAST. The statistic is the unweighted mean of the seven. ⚠ THE THREE THINGS THAT MUST TRAVEL WITH ANY NUMBER FROM THIS ESTIMAND, unchanged from X6 and restated because they are what makes it readable. (1) Shares count STEMS, NOT BIOMASS, so a type that is numerically rare but holds the canopy scores small. (2) The seven shares SUM TO 1, so only six are free and no single term is independent evidence. (3) It is scored ONLY where a forest existed at both ends -- 5,258 of 5,800 pairs on this corpus, the identical count to v1 -- which tilts what remains toward the milder perturbations. ⚠ THIS IS A SEPARATE ESTIMAND FROM THE RESPONSE TEST AND THE TWO ARE NEVER SUMMED OR AVERAGED. `RESPONSE_QUANTITIES` is a sealed experiment's estimand and its score only reproduces while that tuple has exactly seven members; appending the composition columns to it would silently redefine a sealed experiment. A test in the repository asserts that tuple is untouched. TREELESS HANDLING. `corpus/state.py` still writes 0.0 into `pft_frac_*` for a cell with no stems, so `score.blank_treeless_composition` masks those columns at read time, exactly as in X6. A share at zero stems is 0/0 -- undefined, not zero -- and left in it reads as "type 3's share fell from 0.81 to 0.00", which is the cell going treeless, an event `stems_per_patch` already scores in full in the response test. 493 pairs are dropped because the CONTROL has no mix and 49 because the ARM went treeless, 542 of 5,800 -- the identical bookkeeping to v1, because constant CO2 does not change which cells can hold a forest. Every arm is scored on the IDENTICAL set (the pairs where the truth is defined) and a missing prediction is imputed as NO CHANGE, so no arm is scored on an easier subset than its competitors.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12 -- ONE binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, each a single-cell 1000-year spin-up, npatch=25, tree PFTs only, base climate window 1970-1999. Shares are read from the end-of-spin-up restart file, which is UNCENSORED, so every stem counts including those under the 5 m cut the per-tree text output applies. Cell eligibility was stems_total > 0 in the historical seed-1 end-of-spin-up restart = 56,986 cells, NOT the acceptance criterion's 54,020. Dimensionless; a ratio of sums of squares, i.e. a ratio and not a level. ⚠ CO2 IS CONSTANT AT 276.59 ppm, AND THIS TIME THAT SENTENCE IS TRUE. Every run reads its own constant CO2 forcing file. The same sentence in X-20260914's reference basis was NOT true of v1 and has been corrected in that experiment's verdict. The emulator still never sees CO2 as a feature and must not respond to it (invariant 8): pinning CO2 removes a confound from the TARGET, it does not add an input. ⚠ THE TARGET IS NOW AN EQUILIBRIUM. X-20260914 inherited the disclosure that the 1000-year spin-up is not converged; that was a forced CO2 response read as drift and is WITHDRAWN. With CO2 pinned the trajectory is flat to +0.15 %/century. Record: `docs/decisions/20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md`.

## What this means

**The species-mix response is a CLIMATE response, not a CO2 artefact.** This was the real risk:
CO2 fertilisation in LPJmL-FIT acts through photosynthesis and water-use efficiency, so it is not
type-neutral, and some of what X6 measured on the CO2-ramped corpus could have been the ramp
re-weighting the types rather than the climate perturbation doing it. With CO2 pinned the model
scores **0.445852** against a pre-registered bar of **0.300203** — pre-named outcome (a), and
slightly stronger than X6's 0.425610 against 0.337858. All seven nulls returned their
pre-registered values exactly.

**So line T's principal build stands, and its justification no longer needs the CO2 caveat.** The
synthesiser copying each tree's type from the template roster remains a MEASURED capability gap
rather than a free simplification, and that statement now rests on a corpus whose end state is the
product's actual target.

**Quote it as 51.7 % of the attainable 0.863, never against 1.0**, and say that 0.863 is a lower
bound. ⚠ It carries the same basis mismatch as its sibling: the noise magnitude behind the ceiling
comes from two ground-truth spin-ups run under the TRANSIENT CO2 path, applied here to constant-CO2
contrasts, and the direction of that error is unknown.

**THE THREE THINGS THAT MUST TRAVEL WITH THE 0.445852**, unchanged from X6. (1) Shares count
**stems, not biomass**, so a type that is numerically rare but holds the canopy scores small.
(2) The seven shares **sum to 1**, so only six are free and no single term is independent evidence.
(3) It is scored **only where a forest existed at both ends** — 5,258 of 5,800 pairs — which tilts
what remains toward the milder perturbations.

⚠ **AND THE PER-LEVEL TABLE IS WEAKER THAN THE SIBLING'S, WHICH IS THE ONE CAUTION HERE.** The
model fails to beat no-change at **2 of the 29** perturbation levels — `core_t+0_p13` at −0.0882 and
`lhs10` at −0.0665 — against 0 of 29 for the response test. Both are low-temperature points, so
where the climate barely warms, predicting no shift in the mix is better than what the model
predicts. That does not overturn the pooled number (the pre-registered condition for that is a fail
at more than half the levels), but it is the shape of the remaining gap and it must be reported with
the headline rather than found later.

**Never sum or average this with the response test's 0.558968** — different estimands, different
nulls, different bars.

**What is still unknown.** 200 of 54,020 cells, so this is not a fidelity claim and the acceptance
criterion is untouched. It licenses nothing about composition under a SCENARIO leg: this ensemble
identifies the response by construction and the scenario legs do not identify it at all
(`X-20260908-heldout-forcing-leg`, outcome (c)).

⚠ **Corrected 2026-09-23 — the blind arm has now run** (`X-20260923-pilot-composition-blind-arm`;
this paragraph said none had). A model that knows the starting forest but NOT which climate change
it is asked about scores **0.307940**, clearing this experiment's bar of 0.300203 by itself (it
fails under the 5-degree blocking, 0.296620 against 0.305348). So this pass is not by itself
evidence that the mix's response to CLIMATE is learnable: only about **+0.138** of the 0.4459 is
attributable to the forcing (blind = 69 %, against 64.8 % on the response test).

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_composition_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.445852 | 0.285648 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| level_mean_response | 0.0327313 | — | 0.032731 +/- 0.01 [OK] |
| proportional_median_response | 0.160203 | — | 0.160203 +/- 0.01 [OK] |
| proportional_mean_response | -18.042 | — | -18.042 +/- 1 [OK] |
| nearest_cell_response | -0.32852 | — | -0.32852 +/- 0.01 [OK] |
| nearest_analogue_response | -0.3402 | — | -0.3402 +/- 0.01 [OK] |
| shuffled_cells | -0.839838 | — | -0.839838 +/- 0.05 [OK] |
| **DECISION** | pass_if > 0.14 | **PASS** | 0.285648 |

- margin 0.285648 satisfies > 0.14
<!-- END GENERATED -->
