# Verdict — X-20260923-equilibrium-from-climate

outcome: pass

**Question.** Product A as the owner stated it on 2026-09-23: the spin-up takes a 30-year climate, recycles it for 1000 years, and the forest settles; the emulator should see ONLY that climate -- plus soil depth and soil texture, which the spin-up also reads and which the owner named as inputs -- and predict the settled forest. No present-day forest, no location, no statement of how the climate was perturbed.
THE FALSIFIABLE CLAIM: at cells it has never seen, held out in whole 15-degree tiles, such a model explains more of the variation in the settled forest than the best information-free competitor -- copying the forest of the climatically most similar training run -- by more than 0.125 in the mean variance-explained over the 19 scored quantities that vary.
WHY THIS IS NOT THE KILL TEST. Both kill tests give the model the cell's own present-day forest and score the CHANGE; on the species mix, a model blind to the climate change already clears that test's bar from the starting forest alone (`X-20260923-pilot-composition-blind-arm`). Here there is no starting forest to lean on. WHY IT IS NOT A REPEAT OF `X-20260908-climate-state-map`: that asked the question of the existing runs, one climate per place and a CO2-ramped non-equilibrium target. Here every cell was spun up under 30 climates with CO2 constant.

**Estimand.** `skill_equilibrium_mean` — Rows are the 6,000 (cell, climate) spin-ups of pilot-v2-constco2: 200 cells x 30 climates (the cell's control plus 29 perturbations). For each of the 22 quantities of SCORED_CONJUNCTIVE -- stems per patch, above-ground biomass, leaf area index, soil carbon, and the 10th/50th/90th percentile of wood density, specific leaf area, fine-root conductivity, 95 % rooting depth, leaf longevity and height -- the target is the LEVEL in the end-of-spin-up restart. The four forest-scale quantities are scored on log1p (they span four orders of magnitude); the eighteen trait quantiles as they are. A trait quantile is undefined in a treeless run (380 of 6,000) and those rows are not scored for traits; the forest-scale four are scored on all 6,000. Per quantity: 1 - SUM((pred - truth)^2) / SUM((truth - mean(truth))^2) over every row where the truth exists, computed once on the ASSEMBLED out-of-fold prediction, the mean taken over the pooled truth. The statistic is the unweighted mean over the 19 quantities that vary. ⚠ FINE-ROOT CONDUCTIVITY IS EXCLUDED FROM THE MEAN BECAUSE IT DOES NOT VARY: its three quantiles take one value in all 5,620 tree-bearing runs (spread ~1e-18), so variance explained is 0/0. It stays in the band rates, where every arm passes it for free. `assert_constant` refuses the run if it varies. An arm that leaves a scored row unpredicted is an error, not a skipped row. REPORTED BESIDE THE STATISTIC, NEVER DECIDED ON: per quantity and on all 22 at once, the share of TREE-BEARING rows inside +-10 % of the truth on the raw scale, for every arm and for the ceiling. ⚠ This is a FLAT 10 % band, STRICTER than the acceptance rule max(10 %, the model's own two-run spread), because the second run exists for only 20 of the 200 cells.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, each a single-cell 1000-year spin-up, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. State from the end-of-spin-up restart, which is uncensored. Inputs: the 86 CLIMATE_FEATURES of that run's own (perturbed) climate -- which include soil depth -- and five soil-texture columns read from the model's own soil input `soil_code_test.soil.bin` (code, available water capacity, available fraction, sand, clay; per-code values from par/soil.js as transcribed in scripts/screen_d95max.py). 200 of the 56,986 eligible cells, not the acceptance criterion's 54,020. Dimensionless; a ratio of sums of squares, i.e. a ratio and not a level.

## What this means

**Outcome (a), by a wide margin: the settled forest IS learnable from the 30-year climate and the
soil alone.** Shown only a run's climate summary, soil depth and soil texture, at places it never
saw (whole 15-degree tiles held out), the model explains **0.608** of the variation in the
equilibrium forest, mean over the 19 quantities that vary. The bar was 0.223; copying the forest of
the most similar training climate scores 0.098, and the nearest training location scores −0.131.
It beats that lookup at all 30 climate levels (worst 0.522) and holds at 5-degree blocking
(0.610). All four nulls returned their pre-registered values exactly. **Quote it as 64 % of the
attainable 0.950**, never against 1.0; that ceiling borrows its noise from two transient-CO2 runs.

**Where it is strong and where it is not.** Forest-scale quantities: stems 0.79, biomass 0.85,
leaf area 0.83, soil carbon 0.93 (ceilings 0.99–1.00). Trait quantiles are weaker, 0.29–0.80: the
lower tail and median of rooting depth (0.29, 0.36) and the wood-density, SLA and longevity
medians (0.42–0.60) are the gap. Fine-root conductivity is one constant value in this configuration and is not scored.

⚠ **It rarely lands within 10 %, and the flat band must travel with the headline.** Inside +-10 %
on all 22 at once: **0.0 %** of 5,620 tree-bearing runs (one real run predicting another: 4.9 %).
Per quantity 0.15 (biomass) to 0.71 over the 19 that vary, against the ceiling's 0.49–0.96; mean
over all 22 (fine-root conductivity passes free) 0.49, ceiling 0.80. On two
quantities (height_p10, longevity_p90) it lands inside the band LESS often than the analogue
lookup, although it explains more variance: a regression predicts the conditional mean, which
minimises squared error and is rarely within 10 % of a single noisy run. The flat band is stricter
than the acceptance rule, which widens it to the model's own two-run spread.

**Not measured here:** how much the soil texture adds (no ablation was pre-registered), any
scenario leg, and any cell outside these 200. 200 of 54,020; the acceptance criterion is untouched.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_equilibrium_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.607582 | 0.509916 | — |
| training_mean | -0.0062585 | — | -0.006259 +/- 0.001 [OK] |
| nearest_analogue | 0.097666 | — | 0.097666 +/- 0.001 [OK] |
| nearest_geographic | -0.130669 | — | -0.130669 +/- 0.001 [OK] |
| shuffled | -0.937174 | — | -0.937174 +/- 0.01 [OK] |
| **DECISION** | pass_if > 0.125 | **PASS** | 0.509916 |

- margin 0.509916 satisfies > 0.125
<!-- END GENERATED -->
