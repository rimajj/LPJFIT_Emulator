# Verdict — X-20260924-equilibrium-soil-ablation
outcome: fail
**Question.** `X-20260923-equilibrium-from-climate` passed at 0.607582: from a run's 30-year climate summary (86 features, which include soil DEPTH) plus five soil-TEXTURE columns, a model explains 0.608 of the variation in the settled forest at held-out 15-degree tiles. Its verdict names, as not measured, how much the soil texture adds. The owner named texture as an input, so whether it earns its place is a question about Product A's input list, not a curiosity.
THE FALSIFIABLE CLAIM: removing the five soil-texture columns from the sealed recipe, and changing nothing else, lowers the held-out skill by more than 0.015 -- which is more than any of five uninformative soil assignments (every cell handed another cell's soil) changes it.

**Estimand.** `skill_gain_soil_texture` — A PAIRED DIFFERENCE OF THE SEALED STATISTIC, both halves fitted in one job: gain = S(the sealed recipe) - S(the sealed recipe without the five soil-texture columns) where S is `skill_equilibrium_mean` exactly as sealed -- per quantity 1 - SSE / SS about the pooled truth mean, over every (cell, climate) row where the truth exists, the four forest-scale quantities on log1p, the mean over the 19 quantities that vary -- on the same 6,000 rows, the same folds, the same learner, parameters and seed. Only the feature set differs: the ablated recipe drops soil_code, soil_awc, soil_w_avail, soil_sand and soil_clay (91 -> 86 features). ⚠ WHAT "TEXTURE" MEANS HERE. soil_awc is soil depth x the texture's available-water fraction, so it is a texture-by-depth column and goes with the texture; soil DEPTH itself is one of the 86 climate features and STAYS. The question is therefore "does texture add skill given depth and climate", not "does soil matter". WHY A DIFFERENCE, AND WHY `model_absolute`. The gate's comparators set a model against nulls whose values are fixed before the run. "The model without soil" cannot be fixed before the run without running it, and its level beside the already-known 0.607582 IS the answer, so it cannot be a null. The clean construction is to make the paired difference itself the estimand, whose nulls are then differences that CAN be fixed first: exactly 0 for "texture adds nothing", and the largest gain a placebo buys. Reported beside it, never decided on: the gain per quantity, per climate level, and in the flat 10 % band rates.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, single-cell 1000-year spin-ups, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. State from the end-of-spin-up restart (uncensored); 5,620 tree-bearing runs score the trait quantiles. Soil texture from the model's own input soil_code_test.soil.bin: 9 texture classes occur among the 200 cells, but three of them hold 167 (code 7: 85, code 9: 44, code 4: 38), which limits what any texture effect can show. 200 of the 56,986 eligible cells, not the acceptance criterion's 54,020. Dimensionless; a DIFFERENCE of two ratios of sums of squares -- a ratio, not a level.

## What this means

**Outcome: fail — on the pilot, soil texture adds almost nothing once climate and soil depth are
known.** Removing the five texture columns lowers the held-out skill by 0.0013 (0.607582 with them),
far below the pre-registered 0.015; handing every cell another cell's soil costs 0.004-0.005, so
the real texture is worth a little more than a wrong one, not much more than none. No single
quantity moves by more than 0.02 (median SLA +0.019, median wood density −0.015). At 5-degree
blocking, reported beside it: +0.0044. The apparatus reproduced the sealed 0.607582 exactly first.

⚠ **Weak power, stated plainly.** Three texture classes hold 167 of the 200 pilot cells, so this
says texture barely helps *across the textures the pilot contains*, not that texture does not
matter to LPJmL-FIT. It is no reason to drop texture from Product A's inputs, only no evidence for
keeping it on skill grounds. 200 of the 56,986 cells; not an acceptance claim.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_gain_soil_texture | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.00127477 | 0.00127477 | — |
| no_soil_texture | 0 | — | 0 +/- 1e-06 [OK] |
| soil_texture_permuted_max | -0.00388854 | — | -0.003889 +/- 0.001 [OK] |
| **DECISION** | pass_if > 0.015 | **FAIL** | 0.00127477 |

- margin 0.00127477 does not satisfy > 0.015
<!-- END GENERATED -->
