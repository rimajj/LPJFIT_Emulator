# Verdict — X-20260925-spinup-vegc-recipe-v2

outcome: fail

**Question.** X-20260924-spinup-vegc-from-spinup measured that a climate-only map with the sealed inputs (86 monthly climate features + 5 soil columns) and the sealed learner lands inside the acceptance band in 42.7 % of the 56,986 cells with any stem, where a second run of the model lands inside it in 85.9 % (D = -0.432). A dev screen (scripts/screen_spinup_vegc.py) then compared recipes using ONLY the scored cells of folds 0-2 and chose one by a rule fixed before it ran: features computed from the daily forcing (a soil-water bucket, drought spells, the model's own bioclimatic limits and fire curve, light weighted by the model's photosynthesis temperature response), the two-seed truth of the scored window as training rows, a two-stage split into tree-bearing and not, an absolute-error loss, tuned and early-stopped LightGBM settings, the pilot pooled into the training rows, and five-seed bagging.
THE FALSIFIABLE CLAIM: on the 20,123 scored cells of folds 3 and 4 -- each predicted by a model trained on the cells of the other four folds, the sealed construction restricted to those cells -- D = frac(recipe) - frac(rerun) >= -0.02, frac(rerun) restricted to the same cells.
⚠ EXPECTED OUTCOME, STATED BEFORE SEALING: FAIL. The screen already printed this recipe's value on these cells (see selection.held_out_already_quoted), about -0.26, far from -0.02. This is pre-registered so the best recipe found has a sealed, null-checked record on cells the choice never scored -- not because a pass is possible.
⚠ WHAT A PASS WOULD NOT SAY (as the sibling): the map has seen one climate per place, so it identifies no warming response and must never be quoted for a warmed climate; vegetation carbon only; nothing about a restart file.

**Estimand.** `asgood_vegc_spinup_heldout` — Identical to X-20260924-spinup-vegc-from-spinup (asgood_vegc_spinup: truth T_k = seed k's mean VegC over model years 1450-1699; band w = max(0.10, s) from the earlier disjoint half 1200-1449; per-cell pass averaged over both seeds; D = frac(x) - frac(rerun)), computed by the same code (exp_spinup_vegc.scored_set and score), RESTRICTED to the scored cells whose 15-degree tile is in fold 3 or 4 of the sealed tile -> fold map (global_folds: 15 deg, k=5, seed 42): 20,123 of the 56,986. frac(rerun) is recomputed on those 20,123 cells (0.869478). THE MODEL ARM: the recipe below, read field by field by scripts/exp_spinup_vegc_recipe_v2.py. For each held-out fold f in {3, 4}: training rows are every stored-spin-up cell outside fold f with finite truth, one row per seed with target log1p(T_k) (1450-1699 means), PLUS every pilot run of the pilot cells outside fold f, one row per seed (the pilot's own 1450-1699 means), weight 1; the source is never a feature. Stage 1: a LightGBM classifier (sealed settings) of "any stem in restart_1999" (stored spin-up rows) / "any stem at the end of the run" (pilot rows) -- a TRAINING label only. Stage 2: two regressors, on the tree-bearing and the other training rows, each with the tuned settings and the recipe's loss, early-stopped on a random 15 % of the TRAINING rows' 15-degree tiles and refitted on all training rows at the stopped tree count. A cell's prediction = p * tree-bearing head + (1 - p) * other head in log1p, averaged over five seeds, expm1, clipped at 0. Features: feature set v3p = the sealed 91 + the 167 columns of vegemu.corpus.features_v3.V3_ALLP (tables pinned below): 258 inputs. REPORTED BESIDE THE STATISTIC, NEVER DECIDED ON: frac; variance explained on log1p; the flat 10 % rate; D per latitude band; a 1,000-resample 15-degree-tile bootstrap interval; and the sealed recipe (91 features, sealed learner, spin-up pool) on the same cells.

**Reference basis.** As X-20260924-spinup-vegc-from-spinup: stored global LPJmL-FIT 5.6.004 spin-up, Feb-05 2026 binary, npatch 25, seeds 1 and 2, CO2 276.59 ppm for model years < 1700 (the only part used), recycled climate 1901-1930 (GSWP3-W5E5); spinup_truth.parquet sha256 37391b3f70c12995.... Pilot rows: pilot-v2-constco2 and its second seed (200 cells x 30 climates, single-cell spin-ups, Aug-12 binary, constant CO2), pilot_trajectory_stats.parquet sha256 745197c70804b209.... Scored: 20,123 of the 56,986 cells with any stem (folds 3-4). Level shares; the statistic a difference of two shares.

## What this means

**Outcome: fail, as stated before sealing, and the best vegetation-carbon map so far.** On the
20,123 tree-bearing cells of folds 3 and 4, each predicted by models that never saw its tile, the
screened recipe lands inside the acceptance band in **60.6 %** of cells, where a second run of the
model lands inside it in **86.9 %**: D = **-0.263** against the -0.02 the rule needs. On the same
cells the sealed recipe is at 42.6 % (D -0.443) and the best lookup, copying the most similar
training climate, at 31.9 % (D -0.550). It explains 0.980 of the variation in log vegetation
carbon. All four nulls returned their sealed values exactly (job 2319102).

⚠ Not a blind test: the screen had already printed this value (the pre-registration says so); what
the seal adds is that the recipe was chosen on folds 0-2 alone and its number here is now recorded
beside every null. Vegetation carbon only, one climate per place: nothing here may be quoted for a
warmed climate. The first model job (2318344) died after its fit on a missing input file, before
computing anything; the script now reads that file first (commit 7f86c80).

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_spinup_heldout | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.263057 | -0.263057 | — |
| training_mean | -0.808627 | — | -0.808627 +/- 0.001 [OK] |
| nearest_analogue | -0.550117 | — | -0.550117 +/- 0.001 [OK] |
| nearest_geographic | -0.628733 | — | -0.628733 +/- 0.001 [OK] |
| shuffled | -0.820429 | — | -0.820429 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.263057 |

- margin -0.263057 does not satisfy >= -0.02
<!-- END GENERATED -->
