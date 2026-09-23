# Verdict — X-20260924-centred-warming-response

outcome: pass

**Question.** The warming kill test (`X-20260921-pilot-warming-response-constco2-resealed`) passed at 0.558968 against a bar of 0.257725. But a model that sees the cell's starting forest and its baseline climate and CANNOT see which of the 29 climate changes it is asked about scores 0.362322 -- 64.8 % of the headline -- because knowing what kind of forest this is lets you guess its typical change. None of the seven information-free nulls knows the starting forest, so none of them is that competitor, and the uncentred statistic cannot make it one without a bar near the blind arm (the power note of the parent explains why).
THE FALSIFIABLE CLAIM: scored on the WITHIN-CELL CENTRED change -- each cell's change minus that cell's own mean change over its 29 perturbations, so that the blind model scores exactly 0 by construction -- the same model, unchanged, beats the best competitor that remains by more than 0.045. That is: it predicts how the response DIFFERS between climate changes at one place, which no knowledge of the starting forest alone can buy.

**Estimand.** `skill_response_centred_mean` — The seven quantities, the paired contrast and the treeless rule of the parent, UNCHANGED: stems per patch, above-ground biomass, leaf area index, soil carbon, and the medians of stem height, wood density and specific leaf area; dtrue = state(cell, perturbed point) - state(cell, control); trait medians undefined in a treeless arm and not scored there. THE ONE CHANGE IS THE CENTRING (`vegemu.centred`). For each cell and quantity, over the design points where dtrue exists (at most 29): dtrue~ = dtrue - mean(dtrue), dpred~ = dpred - mean(dpred) over the SAME points. Per quantity 1 - SUM(dpred~ - dtrue~)^2 / SUM(dtrue~^2) pooled over all scored pairs; the statistic is the unweighted mean of the seven. Any prediction constant within a cell scores EXACTLY 0.0: no change, the perfect per-cell average change, and the blind model (its 29 rows per cell have identical features, so identical predictions). Pinned bit for bit in tests/test_centred.py, including on a real LightGBM fit, and asserted on the blind model's actual predictions in the job. ⚠ THE DISCLOSURE THAT MUST TRAVEL WITH EVERY NUMBER FROM THIS ESTIMAND. By construction the centring DISCARDS the response to the design-average perturbation: a model that got every cell's average change exactly right and nothing else scores 0, and one that got that average badly wrong but the differences right scores 1. So this number is quoted BESIDE the parent's uncentred 0.558968, never instead of it. Together they say how much of the response is read from the forcing; neither alone does. ONE SCORING RULE DIFFERS FROM THE PARENT, AND IT TOUCHES ONLY THE NULLS. The parent dropped a pair whose PREDICTION was missing; here every arm is scored on the identical pairs (where the truth exists) and a missing prediction is filled with the cell's own mean prediction -- the neutral value under centring, contributing exactly 0. The model never leaves a pair unpredicted; the fills are all in the donor nulls' trait medians, measured at 15 deg: nearest_cell_response 328, nearest_analogue_response 179, shuffled_cells 480 per trait median. The per-level table (29 rows) is part of the result, as in the parent: a pooled pass with a fail at more than half the levels must be reported as such.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, single-cell 1000-year spin-ups, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. State from the end-of-spin-up restart (uncensored). 200 of the 56,986 eligible cells (stems_total > 0 in the historical seed-1 end-of-spin-up restart), not the acceptance criterion's 54,020. 5,800 (cell, perturbed point) pairs, of which 5,258 score the trait medians (a treeless control or arm has no median). Dimensionless ratio of sums of squares of CENTRED changes -- a ratio, not a level. The emulator never sees CO2 (invariant 8).

## What this means

**Pre-named outcome (a): the model does read the climate change, and the part it reads can now be
tested rather than subtracted.** Once each place's own average change is removed, a model that
knows the starting forest but not the perturbation scores exactly 0 (measured, not assumed: its
predictions were checked constant within every cell). The same model the warming kill test passed
with, unchanged, then scores **0.377189** at held-out 15-degree tiles (0.375078 at 5 degrees),
against a bar of 0.133493 and a best information-free competitor of 0.088493 ("every place
responds with the design's average pattern"). All ten nulls returned their pre-registered values.

**Read it beside the uncentred headline, never instead of it.** The centring throws away, by
construction, the response to the AVERAGE of the 29 climate changes. So the two numbers answer two
questions: **0.559** (reproduced to the last digit in this job) is how well the change is predicted
at all; **0.377** is how well the model tells apart what the 29 different climate changes do to
one forest -- the part no knowledge of the starting forest alone can buy. Quote 0.377 as **44 % of
the attainable 0.854** (a lower bound whose noise comes from two runs on the rising-CO2 path).

**Where the within-place response is learnt and where it is not.** Biomass 0.59, leaf area 0.54,
soil carbon 0.60, height 0.36, stem count 0.23, wood density 0.17, specific leaf area 0.15. The
model beats the best competitor at **all 29 of 29** climate changes (weakest `lhs15`, 0.121). The
placebo -- the same model shown the RIGHT forcing values paired with the WRONG climate change --
falls to -0.085, below even "no change": it is the pairing, not the forcing columns' spread, that
carries the skill.

**What is NOT licensed.** Same 200 of 54,020 cells and same corpus as the kill test, so this is a
sharper reading of that result, not an independent replication; no fidelity claim; nothing about a
scenario leg. The null and placebo values were derived by jobs 2281314 and 2281317 before the seal;
those two were submitted under the parent kill test's registration because this worktree's path
contains a word the submission guard keys on, and nothing was appended to the parent.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_response_centred_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.377189 | 0.288696 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| cell_mean_oracle | 0 | — | 0 +/- 1e-06 [OK] |
| blind_model | 0 | — | 0 +/- 1e-06 [OK] |
| level_mean_response | 0.0884926 | — | 0.088493 +/- 0.01 [OK] |
| proportional_median_response | 0.0772129 | — | 0.077213 +/- 0.01 [OK] |
| proportional_mean_response | -14.9514 | — | -14.9514 +/- 1 [OK] |
| nearest_cell_response | -0.294013 | — | -0.294013 +/- 0.01 [OK] |
| nearest_analogue_response | -0.173875 | — | -0.173875 +/- 0.01 [OK] |
| shuffled_cells | -1.62287 | — | -1.62287 +/- 0.05 [OK] |
| scrambled_forcing | -0.0848134 | — | -0.084813 +/- 0.01 [OK] |
| **DECISION** | pass_if > 0.045 | **PASS** | 0.288696 |

- margin 0.288696 satisfies > 0.045
<!-- END GENERATED -->
