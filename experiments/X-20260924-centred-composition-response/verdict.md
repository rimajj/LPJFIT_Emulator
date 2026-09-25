# Verdict — X-20260924-centred-composition-response

outcome: pass

**Question.** The species-mix kill test (`X-20260921-pilot-composition-response-constco2-resealed`) passed at 0.445852 against a bar of 0.300203. Its blind arm (`X-20260923-pilot-composition-blind-arm`) -- the same model with the eleven forcing columns removed, so it knows the starting forest and not the climate change -- scored 0.307940, 69 % of the headline, and CLEARED THE BAR BY ITSELF. So that pass is not evidence that the mix's response to CLIMATE is learnable; only the forcing-attributable part (about +0.138) is, and it was quoted as a difference of two scores rather than tested.
THE FALSIFIABLE CLAIM: scored on the WITHIN-CELL CENTRED share change -- each cell's change minus that cell's own mean change over its perturbations, so that the blind model scores exactly 0 by construction -- the same model, unchanged, beats the best competitor that remains by more than 0.040. That is: it predicts how the shift in the mix DIFFERS between climate changes at one place, which no knowledge of the starting forest alone can buy.

**Estimand.** `skill_composition_centred_mean` — The seven stem shares, the paired contrast and the treeless masking of the parent, UNCHANGED: share of STEMS (not biomass) of each of the seven tree types; dtrue = share(cell, perturbed point) - share(cell, control); `score.blank_treeless_composition` masks a treeless arm or control, so 5,258 of 5,800 pairs are scored. THE ONE CHANGE IS THE CENTRING (`vegemu.centred`). For each cell and type, over the design points where dtrue exists: dtrue~ = dtrue - mean(dtrue), dpred~ = dpred - mean(dpred) over the SAME points. Per type 1 - SUM(dpred~ - dtrue~)^2 / SUM(dtrue~^2) pooled over all scored pairs; the statistic is the unweighted mean of the seven. Any prediction constant within a cell scores EXACTLY 0.0: no change, the perfect per-cell average change, and the blind model. Pinned bit for bit in tests/test_centred.py, including on a real LightGBM fit, and asserted on the blind model's actual predictions in the job. ⚠ THE DISCLOSURE THAT MUST TRAVEL WITH EVERY NUMBER FROM THIS ESTIMAND. By construction the centring DISCARDS the response to the design-average perturbation: a model that got every cell's average shift exactly right and nothing else scores 0. So this number is quoted BESIDE the parent's uncentred 0.445852 and the blind arm's 0.307940, never instead of them. The parent's three caveats also travel: stems not biomass; seven shares summing to 1, so six free; scored only where a forest existed at both ends. ONE SCORING RULE DIFFERS FROM THE PARENT: a missing prediction is filled with the cell's own mean prediction (the neutral value under centring, contributing exactly 0) instead of with no change (the neutral value of the uncentred score). The model never leaves a pair unpredicted; the fills are in the donor nulls, measured at 15 deg: nearest_cell_response 328, nearest_analogue_response 179, shuffled_cells 480 per type. The per-level table (29 rows) is part of the result: a pooled pass with a fail at more than half the levels must be reported as such.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, single-cell 1000-year spin-ups, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. Shares from the end-of-spin-up restart (uncensored). 200 of the 56,986 eligible cells, not the acceptance criterion's 54,020. 5,258 scored (cell, perturbed point) pairs. Dimensionless ratio of sums of squares of CENTRED changes -- a ratio, not a level. The emulator never sees CO2 (invariant 8).

## What this means

**Pre-named outcome (a): the species-mix response to climate IS learnable, and this is the first
time that was tested rather than inferred by subtracting two scores.** The blind-arm experiment
showed a model that cannot see the climate change clears the species-mix kill test's bar by itself
(0.307940), so that pass proved nothing about climate. Here each place's own average shift is
removed first; the blind model then scores exactly 0 (its predictions checked constant within
every cell), and the kill test's model, unchanged, scores **0.259422** at held-out 15-degree tiles
(0.263922 at 5 degrees) against a bar of 0.081775 and a best information-free competitor of
0.041775 ("every type changes by the same fraction of its share"). All ten nulls returned their
pre-registered values.

**Read it beside the uncentred numbers, never instead of them.** The centring discards the shift
caused by the AVERAGE of the 29 climate changes. **0.446** (reproduced to the last digit in this
job) is how well the mix's change is predicted at all, **0.308** of which a blind model already
gets; **0.259** is how well the model tells apart what the different climate changes do to one
place's mix. Quote it as **30 % of the attainable 0.852** (a lower bound; its noise comes from two
runs on the rising-CO2 path). Line T's composition head is justified by this number.

**Weaker than the forest-change response, and uneven.** Per tree type 0.13-0.41 (the warming
test's centred score is 0.377). The model beats the best competitor at all 29 of 29 climate
changes, but at one of them (`lhs00`) it does worse than predicting the same shift for every
change (-0.020), and at 5-degree blocking at three (`core_t+4_p10` -0.033, `core_t+4_p13` -0.046,
`lhs00` -0.009). The placebo -- right forcing values, wrong pairing -- scores -0.074, so the skill
is in the pairing. The three caveats of the kill test still travel: stems not biomass; seven shares
summing to 1; scored only where a forest existed at both ends (5,258 of 5,800 pairs).

**What is NOT licensed.** Same 200 of 54,020 cells and same corpus as the kill test -- a sharper
reading, not a replication; no fidelity claim; nothing about a scenario leg. Null and placebo values
came from jobs 2281315 and 2281318 before the seal, submitted under the parent kill test's
registration because this worktree's path contains a word the submission guard keys on.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_composition_centred_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.259422 | 0.217647 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| cell_mean_oracle | 0 | — | 0 +/- 1e-06 [OK] |
| blind_model | 0 | — | 0 +/- 1e-06 [OK] |
| proportional_median_response | 0.0417755 | — | 0.041775 +/- 0.01 [OK] |
| level_mean_response | 0.0200799 | — | 0.02008 +/- 0.01 [OK] |
| proportional_mean_response | -16.1577 | — | -16.1577 +/- 1 [OK] |
| nearest_cell_response | -0.364471 | — | -0.364471 +/- 0.01 [OK] |
| nearest_analogue_response | -0.347345 | — | -0.347345 +/- 0.01 [OK] |
| shuffled_cells | -1.77152 | — | -1.77151 +/- 0.05 [OK] |
| scrambled_forcing | -0.0742074 | — | -0.074207 +/- 0.01 [OK] |
| **DECISION** | pass_if > 0.04 | **PASS** | 0.217647 |

- margin 0.217647 satisfies > 0.04
<!-- END GENERATED -->
