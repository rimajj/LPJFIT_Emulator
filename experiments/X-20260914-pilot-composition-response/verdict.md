# Verdict — X-20260914-pilot-composition-response

outcome: pass

**Question.** Shown a cell's real present-day forest and a perturbed climate, can the emulator predict the CHANGE in the share of stems held by each of the seven tree types better than the best information-free competitor -- which is "every type's share moves by the same fraction of what it already holds"? If it cannot, then the shipped synthesiser's inability to shift species at all costs nothing measurable, and that limitation may continue to ship disclosed. If it can, that limitation is a real capability gap and the synthesiser must stop copying composition.

**Estimand.** `skill_composition_mean` — For each of the seven tree types, compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) pooled over all scored (cell, climate) pairs, where dtrue = pft_frac_i(perturbed point) - pft_frac_i(control) is a WITHIN-CELL PAIRED CONTRAST. The statistic is the unweighted mean of the seven. Denominator SUM(dtrue^2), not the variance of dtrue: that pins the no-response null analytically at exactly 0.0. ⚠ A SEPARATE ESTIMAND FROM THE SEALED RESPONSE TEST, DELIBERATELY AND NOT AN EXTENSION OF IT. X-20260909-pilot-warming-response is sealed around "the unweighted mean of the seven RESPONSE_QUANTITIES" and its recorded 0.545304 reproduces only while that tuple has exactly those seven members. Appending composition to it would silently redefine what a sealed experiment measures. The two numbers are quoted SEPARATELY and NEVER summed or averaged. `tests/test_composition_arm.py` asserts RESPONSE_QUANTITIES is unchanged. ⚠ pft_frac_i IS THE SHARE OF THE CELL'S STEMS OF TYPE i, COUNTED PER INDIVIDUAL AND NOT WEIGHTED BY BIOMASS (corpus/state.py builds it as bincount(ids) / ids.size). A type that is numerically rare but holds the canopy therefore scores small. That is a property of the definition, not of the emulator, and it belongs in any sentence quoting one of these numbers. THE SEVEN SHARES SUM TO 1 to within 2e-16 on every treed row, so only six are free. Every arm is scored under the identical redundancy, so the comparison is fair, but no single term may be read as independent evidence and the mean of seven is not a mean of seven independent skills. TREELESS HANDLING, FIXED HERE AND NOT LATER -- METHOD DECISION 1 OF 2. corpus/state.py writes 0.0 into every pft_frac_* of a treeless cell. As a LEVEL that is defensible; as a CHANGE it is not, because it reads as "type 3's share fell from 0.81 to 0.00" when there is no mix at all, and it is the same collapse that stems_per_patch already scores in full in the sealed response arm. Measured, leaving it in inflates the total squared change by 15-18 % on most types and would let a model buy apparent species-shift skill by predicting die-off. score.blank_treeless_composition sets those to NaN and a pair drops per quantity when the arm OR the control has no stems: 542 of 5,800 pairs, being 493 from the 17 cells already treeless under their own control plus 49 arms that went treeless. 5,258 pairs score. ⚠ THE DISCLOSURE THAT TRAVELS WITH EVERY NUMBER FROM THIS EXPERIMENT: composition is scored where a forest existed at BOTH ends, which selects toward the milder perturbations. ONE DENOMINATOR FOR EVERY ARM -- METHOD DECISION 2 OF 2. score.skill_vs_no_change builds its denominator over rows where the PREDICTION is finite, so an arm that declines to answer on the hard rows would be scored on an easier subset than its competitors. Here that is a live effect, not a precaution: 9.3 % of pairs are undefined and they cluster at the 17 cells treeless under their own control. Of 36,806 scorable cell-quantity entries at 15 deg the fills needed are nearest_cell_response 2,296, nearest_analogue_response 1,253, shuffled_cells 3,360, and zero for the other four. Every arm is therefore scored on the IDENTICAL truth-finite set and a missing prediction is IMPUTED AS NO CHANGE. That direction is the conservative one -- it pulls a negative null UP toward zero, making the competitor stronger and the bar harder -- and it keeps no_response pinned analytically at exactly 0.0.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12 -- ONE binary for all 6,000 runs, so no build-mismatch arm is needed. Pilot corpus v1: 200 cells x 30 climates x 1 seed, each a single-cell 1000-year spin-up, npatch=25, tree PFTs only, base climate window 1970-1999, constant CO2 and CO2 never written. State is read from the end-of-spin-up restart file, which is UNCENSORED, so it includes stems under 5 m that the per-tree text output drops. 5,800 pairs of which 5,258 score per type. ⚠ THE TARGET IS PROTOCOL-DEFINED, NOT AN EQUILIBRIUM. The 1000-year spin-up is not converged (57.9 % of vegetated cells still moving, median +6.8 %/century). What is estimated is "the mix the model's standard spin-up reaches", and the paired contrast is legitimate because both arms of a pair carry the same drift under the same protocol.

## What this means

**Which tree species a forest is made of shifts when the climate shifts, and that shift can be
predicted.** Shown a cell's present-day forest and a changed climate, the model predicts how each of
the seven tree types' share of the stems moves, scoring **0.425610** where the best competitor that
is told nothing about the climate change scores **0.177858** and the pre-registered pass mark was
**0.337858**. It passes at both spatial fold radii, and every one of the seven pre-registered
competitors returned the value it was required to return, so the comparison stands rather than
being void for lack of power.

**Read it as 49 % of what is attainable, never as 49 % wrong.** Perfect is **0.863852** here, not
1.0, because the model being emulated is stochastic: two identical runs of it disagree, and no
predictor can do better than that disagreement. That ceiling is still a **lower bound** — pinning it
needs a second seed on a subset of the pilot, which is outstanding with line D.

**The consequence is concrete and it is a defect, not a curiosity.** The shipped state synthesiser
copies each tree's species from the cell's present-day forest, so an emulated warmed forest cannot
change its species mix at all. Before today it was arguable that this cost nothing measurable. It
costs something measurable: the signal it discards is most of what a 0.43 score is made of.

**What this does NOT say.** It is 200 cells of 54,020, one seed, and one binary. Composition is
scored only where a forest existed both before and after, which drops 542 of 5,800 comparisons and
tilts what remains toward the milder climate changes. The shares count stems, not biomass, so a type
that is numerically rare but holds the canopy scores small. And this is a *response* test: it says
the change is learnable, not that any emulated forest's absolute species mix is within tolerance.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_composition_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.42561 | 0.247752 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| level_mean_response | 0.0343315 | — | 0.034332 +/- 0.01 [OK] |
| proportional_median_response | 0.177858 | — | 0.177858 +/- 0.01 [OK] |
| proportional_mean_response | -27.6194 | — | -27.6194 +/- 1 [OK] |
| nearest_cell_response | -0.357056 | — | -0.357056 +/- 0.01 [OK] |
| nearest_analogue_response | -0.366684 | — | -0.366684 +/- 0.01 [OK] |
| shuffled_cells | -0.835107 | — | -0.835107 +/- 0.05 [OK] |
| **DECISION** | pass_if > 0.16 | **PASS** | 0.247752 |

- margin 0.247752 satisfies > 0.16
<!-- END GENERATED -->
