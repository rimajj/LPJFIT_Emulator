# Verdict — X-20260921-pilot-warming-response-constco2-resealed

outcome: pass

**Question.** Shown a cell's real present-day forest and a perturbed climate, can the emulator predict HOW THAT FOREST CHANGES better than the best information-free competitor -- when the target state is a genuine equilibrium rather than a forest still climbing a CO2 ramp?
X5 (`X-20260909-pilot-warming-response`) answered YES on pilot corpus v1, at 0.545304 against a bar of 0.225690. That answer is not withdrawn and nothing about it is suspect: every one of v1's 6,000 runs shares one identical CO2 path, so the contrast is clean and no score is confounded. What v1 cannot support is the word its product name depends on. Its spin-up ran model years 1000-1999 against a TRANSIENT CO2 file, so the last 300 years carry a +32.8 % CO2 rise and vegetation carbon follows it at +5.53 %/century (r = +0.987). A v1 end state is therefore a forest still adjusting to a CO2 step, not the stationary forest a climate supports -- and the stationary forest is Product A's entire target.
Corpus v2-constco2 pins CO2 and re-runs the identical design. It is a different forest, not a rescaled one: pinning CO2 costs 24 % of the vegetation carbon (median vegc -24.1 %, agb -25.5 %, lai -20.6 %, soilc -5.0 %, stems +4.0 %). So this is a real re-measurement and its answer is not implied by v1's. THE FALSIFIABLE CLAIM: the learnable warming response survives onto the equilibrium corpus at the same strength, i.e. the model clears a bar derived from v2's own nulls by the same construction v1 used.
If it does not, then what X5 measured was partly the emulator learning a CO2-fertilisation transient it will never be asked to reproduce, and Product A's kill test has not in fact passed.

**Estimand.** `skill_response_mean` — UNCHANGED FROM X-20260909-pilot-warming-response, deliberately and to the letter, because the only thing this experiment varies is the corpus. Changing the statistic and the data at the same time would make the comparison unreadable. For each of seven quantities -- stems per patch, above-ground biomass, leaf area index, soil carbon, and the medians of stem height, wood density and specific leaf area -- compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) pooled over all scored (cell, climate) pairs, where dtrue = state(cell, perturbed point) - state(cell, control) is a WITHIN-CELL PAIRED CONTRAST. The statistic is the unweighted mean of the seven. Denominator SUM(dtrue^2), not the variance of dtrue: that pins the no-response null analytically at exactly 0.0. Unweighted so no single quantity's variance dominates. ⚠ THE POOLED NUMBER MAY NOT BE REPORTED ALONE. The per-level table (29 rows, one per perturbed design point) is part of the result, not an appendix, because the response is NOT monotone in temperature: on THIS corpus only 43.5 % of the 200 cells have a monotone above-ground-carbon response across 0 / +2 / +4 / +6 K (v1: 40.5 %), and a level-averaged score is exactly the summary that hides it. A pass on the pooled statistic accompanied by a fail at more than half the 29 levels must be reported as such in the verdict. TREELESS HANDLING, FIXED HERE AND NOT LATER, AND IT IS UNCHANGED BY THE CO2 PINNING. 380 of the 6,000 runs (6.33 %, touching 39 of the 200 cells) end with no stems -- the identical count to v1, which is itself a finding: constant CO2 moves how much forest there is, not which cells can hold one. For the count and stock quantities those rows are KEPT: zero is a legitimate value and a collapse to zero is the largest response in the corpus, so all 5,800 pairs score. For the three trait medians a treeless arm has no median at all -- a wood density of zero is not light wood, it is no wood -- so those rows are dropped per-quantity and 5,620 of 6,000 state rows remain. The consequence is a disclosure, not a footnote: the trait medians are therefore scored on cells where vegetation SURVIVED, which selects toward the milder perturbations, and the surviving row count is reported beside every trait number.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12 -- ONE binary for all 6,000 runs, so no build-mismatch arm is needed here (unlike the stored ground-truth legs). Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, each a single-cell 1000-year spin-up, npatch=25, tree PFTs only, base climate window 1970-1999. State is read from the end-of-spin-up restart file, which is UNCENSORED, so it includes stems under 5 m that the per-tree text output drops. Cell eligibility was stems_total > 0 in the historical seed-1 end-of-spin-up restart = 56,986 cells, which is NOT the acceptance criterion's 54,020 (that counts cells with a VISIBLE tree); quote one or the other, never both as one number. Dimensionless; a ratio of sums of squares, i.e. a ratio and not a level. ⚠ CO2 IS CONSTANT AT 276.59 ppm, AND THIS TIME THAT SENTENCE IS TRUE. Every run reads its own constant CO2 forcing file. The identical sentence in X-20260909's reference basis was NOT true of v1 and has been corrected in that experiment's verdict; correcting it is half of why this experiment exists. The emulator still never sees CO2 as a feature and must not respond to it (invariant 8) -- pinning CO2 removes a confound from the TARGET, it does not add an input. ⚠ THE TARGET IS NOW AN EQUILIBRIUM, WHICH IS THE POINT, AND THE DISCLOSURE THAT USED TO SIT HERE IS WITHDRAWN. X-20260909 disclosed "the 1000-year spin-up is not converged (57.9 % of vegetated cells still moving, median +6.8 %/century)". That was a forced CO2 response read as drift: with CO2 pinned the same curve is flat to +0.15 %/century. So unlike v1, what this experiment estimates IS the stationary forest a climate supports, and a claim about Product A's target is licensed by it. Record: `docs/decisions/20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md`.

## What this means

**The warming response survives the removal of the CO2 transient, and is slightly stronger without
it.** Model **0.558968** against a pre-registered bar of **0.257725** — pre-named outcome (a); on
the CO2-ramped corpus v1 it was 0.545304 against 0.225690. None of X5's result was an artefact of
the corpus's CO2 rise: the learnable, cell-specific response is a response to CLIMATE, so Product
A's kill test may now be described as passed for a **stationary** target, not only a drifting one.
It is also the harder test — the best null ("every cell changes by the same fraction of what it
already has") is stronger here, 0.162725 against 0.145690, which is why the bar rose. All seven
nulls returned their pre-registered values exactly.

**Quote it as 65.9 % of the attainable 0.849, never against 1.0**, and say 0.849 is itself a lower
bound. ⚠ **THE CEILING CARRIES A BASIS MISMATCH THIS TIME**: the realisation noise behind it comes
from the two ground-truth spin-ups, which ran under the TRANSIENT CO2 path, applied here to
constant-CO2 contrasts. The direction of that error is unknown; pinning it needs a second seed of
the v2 corpus, which does not exist.

**The per-level table does not contradict the pooled number** — the check this estimand requires,
not an appendix: the model beats no-change at **all 29 of 29** levels, weakest +0.1243. The response
is still not monotone in temperature; only 43.5 % of cells have a monotone above-ground-carbon
response across 0 / +2 / +4 / +6 K.

**What is NOT licensed.** 200 of 54,020 cells: no fidelity claim, acceptance criterion untouched.
Nothing about a SCENARIO leg — the designed ensemble identifies the response by construction and
the scenario legs do not identify it at all (`X-20260908-heldout-forcing-leg`, outcome (c)).

### The blind arm — required beside the headline, and not in the table below

Pre-registered in the `power_note` as a REPORTED DIAGNOSTIC, deliberately not a decision null: a
null is judged on the model's own comparator, so a blind arm near 0.36 would force the threshold
above ~0.20 and the bar to ~0.56 — a different, harder experiment whose answer would not read as
"did v1's result survive the corpus change?". Same v2 table, same folds, job 2262406:

| arm | skill_response_mean |
|---|---|
| full model | 0.558968 |
| **BLIND** — the model cannot see WHICH perturbation it is asked about | **0.362322** |
| SCRAMBLED — the perturbation it is shown belongs to another cell | 0.331019 |

⚠ **SO THE HEADLINE IS 64.8 % BLIND SKILL, AND "PREDICTS THE WARMING RESPONSE" OVERSTATES IT WITHOUT
THIS NUMBER.** Most of 0.559 is knowing what kind of forest this is, not what is being done to it.
The forcing-attributable part is **+0.196646** — that is the quantity to move, not the headline —
and it is within 0.001 of v1's +0.195842, so pinning CO2 changed neither the headline's composition
nor the forcing-attributable part. Scrambled (0.331019) falls BELOW blind, so the model reads the
forcing it is shown rather than merely reacting to having been shown one.

**A collapse to treelessness is not carrying the score.** 363 of 5,800 pairs (6.26 %) end treeless;
the model scores 0.563341 on the survivors alone — higher, not lower. Those pairs are 3.9 % of the
squared change in stem count, under 1 % elsewhere.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_response_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.558968 | 0.396243 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| level_mean_response | 0.0981698 | — | 0.09817 +/- 0.01 [OK] |
| proportional_median_response | 0.162725 | — | 0.162725 +/- 0.01 [OK] |
| proportional_mean_response | -15.0273 | — | -15.0273 +/- 1 [OK] |
| nearest_cell_response | -0.277597 | — | -0.277597 +/- 0.01 [OK] |
| nearest_analogue_response | -0.201083 | — | -0.201083 +/- 0.01 [OK] |
| shuffled_cells | -0.800043 | — | -0.800043 +/- 0.05 [OK] |
| **DECISION** | pass_if > 0.095 | **PASS** | 0.396243 |

- margin 0.396243 satisfies > 0.095
<!-- END GENERATED -->
