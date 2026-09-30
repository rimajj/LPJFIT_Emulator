# Verdict — X-20260930-germany-state-new-climate
outcome: fail
**Question.** The second test on the owner's Germany equilibrium runs (decision 20260930-INT-the-germany-equilibrium-runs-become-their-own-corpus), and the first on the owner's full acceptance clause there: tree counts AND trait medians AND trait distributions, per cell, at once. The carbon test (X-20260930-germany-vegc-new-climate) scored vegetation carbon only. The state is each run's 3070 restart -- the last full state inside the clean 2101-3070 segment -- proven readable on all twelve files (germany_corpus.py restart: 49 records per file byte-identical, decoded VegC equal to the model's own 3070 output within 5.6e-8, job 2360270) and decoded for every cell (germany_state_3070.parquet, job 2360277). Hold out one climate at a time and predict every cell's 19-quantity state under it from maps trained on the other five.
THE FALSIFIABLE CLAIM: D = frac(map) - frac(rerun) >= -0.02 over the 54,402 rows.
⚠ WHAT A PASS WOULD NOT SAY: Germany only, 9,067 cells at ~9 km, CO2 415.78 ppm, npatch 250 -- nothing about the global target; one snapshot year (3070) per seed, so the rerun reference includes year-to-year noise and is itself only 0.494; the species mix is not among the 19; climates inside the span of six ESM x SSP windows only.

**Estimand.** `asgood_state_germany_newclimate` — Computed by scripts/exp_germany_state.py. A row is (cell, climate), all 54,402 (9,067 cells x six climates). The 19 quantities of score.SCORED_VARYING: stems per patch; above-ground biomass, LAI, soil carbon; p10, p50 and p90 of wood density, SLA, D95max, leaf longevity and height (fine-root conductivity is one constant value in every row, asserted by assert_constant_quantities, and is not scored, as in the global test). Truth T_k = seed k's state decoded from its restart_3070_nv.lpj (vegemu.corpus.state.summarise_cell, schema 3). Band w, per cell and quantity = score.spread_across_climates: max(0.10, the median two-seed relative spread over the cell's OTHER five climates); 99.25 % of cell-quantities sit at the bare 10 % floor. Per-row pass vs T_k = every quantity T_k defines satisfies |x - T_k| <= w |T_k| (a trait of a treeless truth is not scored; an undefined prediction of a defined quantity fails). Per-row score = mean over k = 1, 2; frac = mean over rows; frac(rerun) = seed 2 scored against seed 1 and seed 1 against seed 2, averaged (0.494127); D = frac(arm) - frac(rerun). FOLDS: leave-one-climate-out, six folds, a row's fold is its (ESM, SSP); no row of the held-out climate trains its prediction. THE MODEL ARM: per quantity and fold one LightGBM regressor with the carbon test's frozen settings (exp_germany_vegc.LEARNER, chosen on the GLOBAL spin-up dev folds by screen_spinup_vegc.py round 2; 3000 trees, L1 loss), fitted on both seeds' rows of the other five climates where that seed defines the quantity; log1p target for stems per patch, biomass, LAI and soil carbon, natural scale for the traits; emitted = clipped at 0 and each trait's three quantiles sorted ascending (exp_germany_state.emit). Inputs: the 258 columns of germany_climate.parquet, all from the 2071-2100 daily forcing and the soil inputs. REPORTED BESIDE, NEVER DECIDED ON: frac and D per held-out climate; per-quantity band rates beside the rerun's; a BLIND arm, the same learners on the six soil columns only; the two-seed mean as a predictor; frac without ssp245 (ssp245 rows neither train nor are scored; four folds); the flat-10 % conjunctive rate.

**Reference basis.** The owner's Germany production runs (germany.runs in config/paths.yaml): LPJmL 5.6.004 with the individual-tree extension, npatch 250, natural vegetation, fire on, nitrogen off, 9,067 cells, seeds 1 and 2; ssp126 and ssp370 on the 2025-12-17 build, ssp245 on the 2026-02-05 build. CO2 constant 415.78 ppm over every year used. Truth = the 3070 restarts, inside the clean segment (2071-2100 and 3071-3100 read relative humidity as specific; see the decision record). germany_state_3070.parquet sha256 8786617314ec4670...; germany_climate.parquet sha256 b3ff8a9489d2d3c6.... 54,402 rows; 24 of the 108,804 seed states hold no trees; a level share of a conjunction over 19 quantities; the statistic a difference of two shares.

## What this means

**Outcome: fail, at outcome (b), by 3.7 percentage points.** Predicting every cell's whole
settled forest (tree count, three stocks, and the 10th/50th/90th percentiles of five traits, all
19 at once) under a climate held out of training, the map gets every quantity inside the band in
**43.7 %** of the 54,402 rows. A second run of the model does **49.4 %**, so the rule needed
47.4 % (D -0.0573 against -0.02). It is far above every null: the best, copying the same cell's
state from its most similar training climate, scores 12.9 %. All five nulls returned their
pre-registered values exactly.

| held-out climate | map | rerun | the map's worst quantities, vs the rerun's rate |
|---|---|---|---|
| ACCESS-CM2 ssp126 | 0.468 | 0.549 | |
| ACCESS-CM2 ssp245 | **0.671** | 0.520 | above the rerun (it predicts the seed average) |
| ACCESS-CM2 ssp370 (hottest) | 0.476 | 0.619 | leaf longevity p10 0.82 vs 0.99; soil carbon 0.90 vs 1.00 |
| MPI-ESM1-2-HR ssp126 (coldest) | 0.269 | 0.288 | D95max p10 0.77 vs 0.92; stems 0.66 vs 0.78 |
| MPI-ESM1-2-HR ssp245 | **0.289** | 0.510 | **stems per patch 0.63 vs 0.93; leaf longevity p90 0.67 vs 0.96** |
| MPI-ESM1-2-HR ssp370 | 0.448 | 0.480 | |

Over all rows the map trails the rerun most on leaf longevity (p10 0.913 vs 0.984, p50 0.949 vs
0.994, p90 0.856 vs 0.913), the small-tree end of D95max (0.821 vs 0.892) and tree count (0.829
vs 0.874); it is above the rerun on biomass (0.819 vs 0.779), as any predictor of the seed average
is. The same learners on soil alone score 6.4 %, so the map reads the climate; without the ssp245
runs it drops to 31.3 % against a rerun's 48.4 %, so it needs climate coverage.

⚠ **Not tested, but the obvious suspect for the worst fold:** the ssp245 runs are on the newer
build (a change to how new trees inherit traits, `new_tree.c`). With MPI ssp245 held out, ACCESS
ssp245 is the only training climate from that build, and its worst misses are tree count and the
longevity tail, both plausibly build-dependent. Separating build from climate needs its own test.
⚠ One snapshot year per seed: a rerun lands only 49.4 % because single years differ (biomass
beyond 10 % in 22 % of rows), so this rule is "as good as a rerun", never "within 10 % of the
truth". Germany only (9,067 cells, CO2 415.78 ppm, 250 patches); species mix not scored.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_state_germany_newclimate | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.0573416 | -0.0573416 | — |
| same_cell_nearest_climate | -0.365602 | — | -0.365602 +/- 0.001 [OK] |
| same_cell_mean | -0.413882 | — | -0.413882 +/- 0.001 [OK] |
| nearest_analogue | -0.412163 | — | -0.412163 +/- 0.001 [OK] |
| training_mean | -0.472087 | — | -0.472087 +/- 0.001 [OK] |
| shuffled | -0.432925 | — | -0.432925 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.0573416 |

- margin -0.0573416 does not satisfy >= -0.02
<!-- END GENERATED -->
