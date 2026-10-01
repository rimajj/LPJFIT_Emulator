# Verdict — X-20261001-germany-state-415ppm

outcome: fail

**Question.** X-20260930-germany-state-new-climate failed at outcome (b), D -0.0573, and its worst held-out climate was MPI-ESM1-2-HR ssp245 (0.289 vs a rerun's 0.510). That run -- both seeds -- held CO2 at 401.63 ppm over 2101-3070 where the other ten held 415.78 (decision 20261001-INT-mpi-ssp245-ran-at-401-ppm-so-it-is-not-the-germany-target). The emulator does not see CO2 and must not respond to it, so that run is a different target and the sealed test mixed it into training, scoring and the bands. Re-run the same test, every rule unchanged, on the five climates at 415.78 ppm: leave one out, predict every cell's 19-quantity state under it from maps trained on the other four.
THE FALSIFIABLE CLAIM: D = frac(map) - frac(rerun) >= -0.02 over the 45,335 rows.
⚠ WHAT IS ALREADY KNOWN, disclosed before sealing: the sealed six-climate fit, restricted to these five held-out climates, scored 0.4664 vs a rerun's 0.4912 (D -0.025) -- but with maps that trained on the 401.63-ppm run and bands built from five other climates, so it is not this number. This test was chosen because the run's CO2 file differs (found in its config, not in a score), and the reason holds whatever it returns. ⚠ WHAT A PASS WOULD NOT SAY: Germany only, 9,067 cells at ~9 km, CO2 415.78 ppm, npatch 250 -- nothing about the global target; one snapshot year (3070) per seed, so a rerun lands only ~0.49; the species mix is not among the 19; every held-out climate but ACCESS ssp245 is an extreme (ssp126 or ssp370) of its ESM, so four of five folds extrapolate along the scenario axis.

**Estimand.** `asgood_state_germany_newclimate` — Computed by scripts/exp_germany_state.py --exclude MPI-ESM1-2-HR/ssp245 (commit 278ff6c; the default path reproduces all five sealed null values of X-20260930-germany-state-new-climate exactly, job 2369763). Every rule is that experiment's, with the excluded run removed BEFORE anything is built: a row is (cell, climate), 45,335 rows (9,067 cells x five climates). The 19 quantities of score.SCORED_VARYING. Truth T_k = seed k's 3070 restart state. Band w per cell and quantity = score.spread_across_climates over the five climates: max(0.10, the median two-seed relative spread over the cell's OTHER FOUR climates); 99.13 % of cell-quantities sit at the bare 10 % floor. Per-row pass vs T_k = every quantity T_k defines is inside |x - T_k| <= w |T_k|; per-row score = mean over k = 1, 2; frac = mean over rows; frac(rerun) = seed 2 against seed 1 and seed 1 against seed 2, averaged (0.491552); D = frac(arm) - frac(rerun). FOLDS: leave-one-climate-out, five folds. THE MODEL ARM: per quantity and fold one LightGBM with exp_germany_vegc.LEARNER unchanged (chosen on the GLOBAL spin-up dev folds), fitted on both seeds' rows of the four training climates; log1p target for stems per patch, biomass, LAI and soil carbon; emitted = clipped at 0, each trait's three quantiles sorted. Inputs: the 258 columns of germany_climate.parquet. REPORTED BESIDE, NEVER DECIDED ON: frac and D per held-out climate; per-quantity band rates beside the rerun's; the BLIND arm (soil columns only); the two-seed mean as a predictor; frac with ACCESS ssp245 also removed (the old build only, four climates, three-climate training); the flat-10 % rate.

**Reference basis.** The owner's Germany production runs (germany.runs in config/paths.yaml): LPJmL 5.6.004 with the individual-tree extension, npatch 250, natural vegetation, fire on, nitrogen off, 9,067 cells, seeds 1 and 2; ACCESS-CM2 ssp126/ssp245/ssp370 and MPI-ESM1-2-HR ssp126/ssp370. CO2 415.78 ppm in every year 2101-3070 of all five (input_*.js co2 = RCP85_co2_1765-2500_const_from_2020.dat, read at fix_climate_year 2100). Builds: ssp126 and ssp370 on 2025-12-17; ACCESS ssp245 on 2026-02-05, whose only change (new_tree.c) moves the extreme tails of wood density and D95max (diag_germany_build_fingerprint.py, job 2369693). EXCLUDED: MPI-ESM1-2-HR ssp245, CO2 401.63. Truth = the 3070 restarts (germany_state_3070.parquet sha256 8786617314ec4670...; germany_climate.parquet sha256 b3ff8a9489d2d3c6...). A level share of a conjunction over 19 quantities; the statistic a difference of two shares.

## What this means

**Outcome: fail, at outcome (b), by 4.2 percentage points -- worse than the six-climate test.**
With the one run at another CO2 (MPI ssp245, 401.63 ppm) removed from training, scoring and the
bands, the map gets all 19 quantities of a cell's settled forest inside the band in **43.0 %** of
the 45,335 rows; a second run of the model does **49.2 %**, so the rule needed 47.2 % (D -0.0615
against -0.02). All five nulls returned their pre-registered values exactly; the best, copying the
cell's state from its most similar training climate, scores 10.3 %.

| held-out climate | this test | six-climate test | rerun |
|---|---|---|---|
| ACCESS-CM2 ssp126 | 0.478 | 0.468 | 0.549 |
| ACCESS-CM2 ssp245 | 0.663 | 0.671 | 0.521 |
| ACCESS-CM2 ssp370 (hottest) | 0.504 | 0.476 | 0.620 |
| MPI-ESM1-2-HR ssp126 (coldest) | 0.281 | 0.269 | 0.288 |
| MPI-ESM1-2-HR ssp370 | **0.224** | 0.448 | 0.481 |

Reading: the prediction behind this test -- that the mixed-CO2 run caused the failure -- is
**wrong**. Training without it helps three of the four folds that kept their nearest climate
slightly (+0.01 to +0.03), which fits a small contamination, but MPI ssp370 collapses (0.448 ->
0.224) because MPI ssp245 was its nearest training climate: with it gone that fold extrapolates.
So the binding limit is climate COVERAGE (four training climates are too few), as the global
learning curve already said. With ACCESS ssp245 removed as well (the old build only, three
training climates): 0.313 vs 0.484 -- the same four climates, and the same number, as the
six-climate test's no-ssp245 arm. Blind arm (soil only) 0.064.
Biggest per-quantity gaps vs the rerun: leaf longevity p10 0.884 vs 0.986 and p50 0.936 vs 0.994,
D95max p10 0.807 vs 0.888, soil carbon 0.958 vs 1.000.
⚠ The MPI ssp245 dip in tree count and the longevity tail is still only SUSPECTED to be CO2; this
test cannot score that run. Germany only, 9,067 cells, 250 patches, one snapshot year per seed.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_state_germany_newclimate | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.0615198 | -0.0615198 | — |
| same_cell_nearest_climate | -0.388706 | — | -0.388706 +/- 0.001 [OK] |
| same_cell_mean | -0.418529 | — | -0.418529 +/- 0.001 [OK] |
| nearest_analogue | -0.409772 | — | -0.409772 +/- 0.001 [OK] |
| training_mean | -0.470277 | — | -0.470277 +/- 0.001 [OK] |
| shuffled | -0.430374 | — | -0.430374 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.0615198 |

- margin -0.0615198 does not satisfy >= -0.02
<!-- END GENERATED -->
