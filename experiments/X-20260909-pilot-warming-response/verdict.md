# Verdict — X-20260909-pilot-warming-response
outcome: pass
**Question.** Shown a cell's real present-day forest and a perturbed climate, can the emulator predict HOW THAT FOREST CHANGES better than the best information-free competitor -- which is "every cell changes by the same fraction of what it already has"?
X1 asked this on the two ground-truth legs and answered `fail`, but its own diagnosis was that the question was not cleanly askable there: every cell holds exactly ONE climate, so climate and geography are collinear and a warming response is not separately identified. The pilot corpus removes that confound by construction -- the SAME cell is spun up under 30 climates with the same config, the same forcing window and the same random seed, so the only difference between an arm and its control is the climate. This is X1's question asked on data that can answer it.
If the emulator cannot beat the nulls here, it is not that the test was unfair.

**Estimand.** `skill_response_mean` — For each of seven quantities -- stems per patch, above-ground biomass, leaf area index, soil carbon, and the medians of stem height, wood density and specific leaf area -- compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) pooled over all scored (cell, climate) pairs, where dtrue = state(cell, perturbed point) - state(cell, control) is a WITHIN-CELL PAIRED CONTRAST. The statistic is the unweighted mean of the seven. Denominator SUM(dtrue^2), not the variance of dtrue: that pins the no-response null analytically at exactly 0.0. Unweighted so no single quantity's variance dominates. ⚠ THE POOLED NUMBER MAY NOT BE REPORTED ALONE. The per-level table (29 rows, one per perturbed design point) is part of the result, not an appendix, because the response is NOT monotone in temperature: only 40.5 % of the 200 cells have a monotone above-ground-carbon response across 0 / +2 / +4 / +6 K, and a level-averaged score is exactly the summary that hides it. A pass on the pooled statistic accompanied by a fail at more than half the 29 levels must be reported as such in the verdict. TREELESS HANDLING, FIXED HERE AND NOT LATER. 380 of the 6,000 runs (6.33 %, touching 39 of the 200 cells) end with no stems. For the count and stock quantities those rows are KEPT: zero is a legitimate value and a collapse to zero is the largest response in the corpus, so all 5,800 pairs score. For the three trait medians a treeless arm has no median at all -- a wood density of zero is not light wood, it is no wood -- so those rows are dropped per-quantity and 5,620 of 6,000 state rows remain. The consequence is a disclosure, not a footnote: the trait medians are therefore scored on cells where vegetation SURVIVED, which selects toward the milder perturbations, and the surviving row count is reported beside every trait number.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12 -- ONE binary for all 6,000 runs, so no build-mismatch arm is needed here (unlike the stored ground-truth legs). Pilot corpus v1: 200 cells x 30 climates x 1 seed, each a single-cell 1000-year spin-up, npatch=25, tree PFTs only, base climate window 1970-1999, constant CO2 and CO2 never written. State is read from the end-of-spin-up restart file, which is UNCENSORED, so it includes stems under 5 m that the per-tree text output drops. Cell eligibility was stems_total > 0 in the historical seed-1 end-of-spin-up restart = 56,986 cells, which is NOT the acceptance criterion's 54,020 (that counts cells with a VISIBLE tree); quote one or the other, never both as one number. Dimensionless; a ratio of sums of squares, i.e. a ratio and not a level. ⚠ THE TARGET IS PROTOCOL-DEFINED, NOT AN EQUILIBRIUM. The 1000-year spin-up is not converged (57.9 % of vegetated cells still moving, median +6.8 %/century). What is estimated is therefore "the state the model's standard spin-up reaches", and the paired contrast is legitimate because both arms of a pair carry the same drift under the same protocol. No claim about the stationary forest a climate supports is licensed by this experiment. ⚠ CORRECTION 2026-09-17, AND IT DOES NOT MOVE THE SCORE. Two statements in this basis are wrong. (1) "constant CO2 and CO2 never written" should read: CO2 is identical in every run and is never written by us, but it is NOT constant in time within a run -- the spin-up covers model years 1000-1999 against a TRANSIENT CO2 file, so its last 300 years carry the real historical rise, +32.8 % to 367.26 ppm. (2) "The 1000-year spin-up is not converged (57.9 % of vegetated cells still moving, median +6.8 %/century)" is WITHDRAWN: that trend was fitted INSIDE the CO2 ramp, so it measured CO2 fertilization and reported it as drift; with CO2 pinned the same curve is flat to +0.15 %/century. Nothing here is confounded, because all 6,000 runs share the identical CO2 path, so CO2 is a constant ACROSS the corpus and cannot affect a contrast between design points -- the estimand, the folds, the seven nulls and the 0.545304 all stand, and the paired-contrast argument survives verbatim (it turns out the shared thing is a CO2 forcing rather than a drift). What it does break is the word EQUILIBRIUM: what is estimated is the state the model's standard spin-up reaches THROUGH the historical CO2 rise to 1999 levels. The sealed pre-registration carries the original wording, is immutable, and has deliberately not been edited. Re-basing this experiment on corpus v2-constco2 is line X's open action. Record: docs/decisions/20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md.

## What this means

On an ensemble where the warming response is identified by construction — the same cell spun up
under 30 climates with one config, one forcing window and one seed — the emulator predicts how a
forest *changes* with skill **0.545304**, against **0.145690** for the best information-free
competitor. The bar was **0.225690**; the margin is **+0.399614**. This is the question X1 answered
`fail` on the scenario legs, asked on data that can separate climate from geography.
**Read it against the ceiling 0.869730, not against 1.0** — a real third model seed scored the same
way, itself a LOWER bound because a cell's two arms share a seed. So **63 % of attainable**.
**The non-monotonicity clause is satisfied, not waived.** The model beats the best null at **all 29
of 29 levels** (margins +0.114915 to +0.609290), so there is no majority-fail disclosure to make.
At 5° blocks it scores 0.552327: the conclusion does not turn on the blocking radius. **All seven
nulls reproduced their sealed values exactly** (`[OK]`), so the apparatus that produced 0.545304 is
the one sealed on 2026-09-09.

## The gap in the null set — disclosed, and it does not overturn the pass

⚠ **A model BLINDED to which of the 29 perturbations it is asked about scores 0.349462 — above the
bar of 0.225690.** Every null pre-registered here is information-free *by construction*, so the set
contained no learned-but-treatment-blind competitor. Without this arm beside it, 0.545304 reads as
far more response skill than was demonstrated.

**The pass survives the stricter test.** Against the blind arm as though it had been the best null
the margin is **+0.195842**, still clearing the pre-registered 0.080; and scrambling the forcing
*independently per cell* gives 0.308049 — **below** blind, so removing the forcing hurts less than
lying about it, i.e. the model does read the climate. These arms are **diagnostics, not nulls**:
unsealed, outside the decision rule. The outcome above is what the sealed rule returns.

⚠ **The scramble was broken first time and the broken version looked like a near-miss** (0.4950 vs
0.5453). It falsified nothing — the 29 design points are identical at every cell, so one shared
permutation is a relabelling the model relearns. **Draw a scramble arm per unit.**

## Basis, scope and three disclosures

* **Treeless rows.** Counts and stocks score all 5,800 pairs — a collapse to zero is the largest
  response in the corpus. The three trait medians drop 542 and score on **5,258**; quote that with
  every trait number. Collapse does not drive the headline: the 363 pairs that go treeless carry
  0.0001 of the squared change in above-ground biomass, and surviving pairs alone score 0.549371.
* **The denominator subset.** `skill_vs_no_change` builds its denominator from rows where the
  *prediction* is finite, so an arm that declines to answer is scored on an easier subset. Here that
  touches only `nearest_cell_response` and `nearest_analogue_response` — both negative, neither the
  best null — so the pass stands. Stated rather than left unstated.
* **The clone-seed correction does NOT reach this result:** no `max(10 %, spread)` band is used here,
  and the pilot's own runs never touch the high-emissions leg. Of the sealed set only
  `X-20260908-warming-response` is affected.

**What this does NOT license.** The response is identified *here by construction*; this says nothing
about learning it from the scenario legs, where climate and geography are collinear — that is X3,
and X3 fails. Not a contradiction — line T's record of 2026-09-14, "the response is learnable where
it is identified and not from the scenario legs", holds both. The target is the state the standard
1000-year spin-up reaches, which is not converged, so no claim about the stationary forest a climate
supports is licensed.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_response_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.545304 | 0.399614 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| level_mean_response | 0.0956096 | — | 0.09561 +/- 0.01 [OK] |
| proportional_median_response | 0.14569 | — | 0.14569 +/- 0.01 [OK] |
| proportional_mean_response | -27.4021 | — | -27.4021 +/- 1 [OK] |
| nearest_cell_response | -0.281166 | — | -0.281166 +/- 0.01 [OK] |
| nearest_analogue_response | -0.239753 | — | -0.239753 +/- 0.01 [OK] |
| shuffled_cells | -0.797389 | — | -0.797389 +/- 0.05 [OK] |
| **DECISION** | pass_if > 0.08 | **PASS** | 0.399614 |

- margin 0.399614 satisfies > 0.08
<!-- END GENERATED -->
