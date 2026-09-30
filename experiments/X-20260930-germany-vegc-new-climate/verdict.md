# Verdict — X-20260930-germany-vegc-new-climate
outcome: fail
**Question.** The first test on the owner's Germany equilibrium runs (decision 20260930-INT-the-germany-equilibrium-runs-become-their-own-corpus): every one of 9,067 cells settled under six climates (ACCESS-CM2 and MPI-ESM1-2-HR x ssp126 / ssp245 / ssp370, each the 2071-2100 window recycled for a millennium), two seeds each. Hold out one climate at a time and predict every cell's settled vegetation carbon under it from a map trained on the other five climates. The same cell under the other climates trains the map: this is the same-place, new-climate question the global stored spin-up (one climate per place) cannot ask.
THE FALSIFIABLE CLAIM: D = frac(map) - frac(rerun) >= -0.02 over the 54,390 scored rows.
⚠ WHAT A PASS WOULD NOT SAY: Germany only, 9,067 cells at ~9 km, CO2 415.78 ppm, npatch 250 -- nothing about the global target; vegetation carbon only, nothing about tree counts or traits; climates inside the span of six ESM x SSP windows, so nothing about a climate outside it.

**Estimand.** `asgood_vegc_germany_newclimate` — Computed by scripts/exp_germany_vegc.py. A row is (cell, climate); it is SCORED where both seeds' truth is > 0 (54,390 of 54,402). Truth T_k = seed k's mean VegC over model years 2821-3070; band w = max(0.10, s), s = |E_1 - E_2| / mean(E_1, E_2) with E_k seed k's mean over the disjoint earlier window 2571-2820 (0 where that mean is <= 1 gC/m2). Per-row pass = (1[|x - T_1| <= w T_1] + 1[|x - T_2| <= w T_2]) / 2; frac = mean over scored rows; frac(rerun) = the same with seed 2 predicting seed 1 and seed 1 predicting seed 2, averaged (0.999853); D = frac(arm) - frac(rerun). FOLDS: leave-one-climate-out, six folds, a row's fold is its (ESM, SSP); no row of the held-out climate trains its prediction. THE MODEL ARM: one LightGBM regressor per fold with the settings the global spin-up screen selected on the GLOBAL dev folds (screen_spinup_vegc.py round 2; frozen in the script's LEARNER, 3000 trees, L1 loss), fitted on log1p of each training row's truth, one row per seed, all training rows of the other five climates; prediction expm1, clipped at 0. Inputs: the 258 columns of germany_climate.parquet (85 forcing columns of CLIMATE_FEATURES, soil depth, the five SOIL_FEATURES, the 167 columns of features_v3.V3_ALLP), all from the 2071-2100 daily forcing and the soil inputs. REPORTED BESIDE, NEVER DECIDED ON: frac and D per held-out climate; frac without ssp245 (ssp245 rows neither train nor are scored; four folds); a BLIND arm, the same learner on the six soil columns only; the two-seed mean as a predictor (the ceiling); variance explained on log1p; the flat 10 % rate.

**Reference basis.** The owner's Germany production runs (germany.runs in config/paths.yaml): LPJmL 5.6.004 with the individual-tree extension, npatch 250, natural vegetation, fire on, nitrogen off, 9,067 cells, seeds 1 and 2; ssp126 and ssp370 on the 2025-12-17 build, ssp245 on the 2026-02-05 build. CO2 constant 415.78 ppm over every year used. Truth and band inside the clean 2101-3070 segment (the 2071-2100 and 3071-3100 segments read relative humidity as specific humidity; see the decision record). germany_truth.parquet sha256 a2780d3c33bb7a1b...; germany_climate.parquet sha256 b3ff8a9489d2d3c6.... Scored: 54,390 rows = cells x six climates; a level share; the statistic a difference of two shares.

## What this means

**Outcome: fail, by 0.22 percentage points, at outcome (b).** Predicting every cell's settled
vegetation carbon under a climate held out of training, the map lands inside the band in
**97.77 %** of the 54,390 scored rows; a second run of the model does 99.99 %, so the rule needed
97.99 % (D -0.0222 against -0.02). It beats every null by far, including the decisive one, copying
the same cell's carbon from its most similar training climate (91.77 %). All five nulls returned
their pre-registered values exactly.

| held-out climate (mean temperature) | map | same cell, nearest climate |
|---|---|---|
| ACCESS-CM2 ssp126 (11.8 C) | 0.9902 | 0.9156 |
| ACCESS-CM2 ssp245 (12.5 C) | 0.9938 | 0.8513 |
| ACCESS-CM2 ssp370 (13.8 C) | **0.9248** | 0.9007 |
| MPI-ESM1-2-HR ssp126 (10.0 C) | 0.9808 | 0.9746 |
| MPI-ESM1-2-HR ssp245 (10.9 C) | 0.9845 | 0.9550 |
| MPI-ESM1-2-HR ssp370 (12.1 C) | 0.9918 | 0.9091 |

The one fold that fails is the hottest and driest climate, 1.3 C above anything left in training:
extrapolation. The five climates inside the training span are at or near rerun grade. Beside it:
the same learner on soil alone scores 0.7916, so the map reads the climate; without the ssp245
runs (three training climates, four folds) it drops to 0.8985, so it needs climate coverage.

⚠ Germany only (9,067 cells, CO2 415.78 ppm, 250 patches), vegetation carbon only, climates within
six ESM x SSP windows. The first model job (2360094) wrote no seal stamp; the stamped re-run
(2360128) reproduced every number exactly and is the recorded one.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_germany_newclimate | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.0221916 | -0.0221916 | — |
| same_cell_nearest_climate | -0.0821475 | — | -0.082147 +/- 0.001 [OK] |
| same_cell_mean | -0.14749 | — | -0.14749 +/- 0.001 [OK] |
| nearest_analogue | -0.359147 | — | -0.359147 +/- 0.001 [OK] |
| training_mean | -0.401278 | — | -0.401278 +/- 0.001 [OK] |
| shuffled | -0.470914 | — | -0.470914 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.0221916 |

- margin -0.0221916 does not satisfy >= -0.02
<!-- END GENERATED -->
