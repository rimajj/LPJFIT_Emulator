# Verdict — X-20260924-pilot-state-asgood

outcome: fail

**Question.** The owner's acceptance criterion is tree counts AND trait distributions AND trait medians inside max(10 %, the model's own two-run spread), per cell; on 2026-09-24 the owner chose the pass rule "as good as a rerun": the emulator passes if it lands inside that band as often as a second run of the original model does. The stored global spin-up kept only vegetation carbon for its constant-CO2 years, so the FULL state can be tested only where both seeds of a constant-CO2 spin-up exist: the pilot, 200 cells x 30 climates, now with its full second seed.
THE FALSIFIABLE CLAIM: D = frac(emulator) - frac(rerun) >= -0.02 on the 6,000 pilot rows, where a row passes only if EVERY one of the 19 varying scored quantities is inside the band at once.
WHAT IT ADDS TO THE SEALED X-20260923-equilibrium-from-climate: that experiment asked whether the map explains variance (it does, 0.608); this asks the owner's acceptance question of the same predictions, against the rerun, on the conjunctive per-row band.

**Estimand.** `asgood_state_pilot` — Rows: the 6,000 (cell, climate) spin-ups of pilot-v2-constco2 (200 cells x 30 climates). Quantities: the 19 of SCORED_CONJUNCTIVE that vary (score.SCORED_VARYING: stems per patch, above-ground biomass, leaf area index, soil carbon, and the 10th/50th/90th percentiles of wood density, specific leaf area, 95 % rooting depth, leaf longevity and height); the three fine-root-conductivity quantiles are one constant and pass every arm, so they are left out. Truth per seed k in {1, 2}: T_k = seed k's end-of-spin-up restart state (pilot-v2-constco2 and pilot-v2-constco2-s2). Band per (cell, climate, quantity): w = score.spread_across_climates on the two seeds, i.e. max(0.10, the median two-seed relative spread of that quantity over the cell's OTHER 29 climates) -- the pair being scored never sets its own tolerance. An arm x passes a row against T_k if every quantity T_k defines satisfies |x - T_k| <= w |T_k| (a trait of a treeless truth is not scored; a trait x leaves undefined where T_k has one fails). Per row the score is the mean over k = 1, 2; frac(x) is the mean over the 6,000 rows; frac(rerun) scores T_2 against T_1 and T_1 against T_2 with the same w. THE STATISTIC: D(x) = frac(x) - frac(rerun); higher is better. THE MODEL ARM is the emulator's EMITTED out-of-fold prediction: the post-processed `pred_` heads of the saved climate-only map models/equimap-v1/oof_pilot.parquet (sealed recipe, 5 folds of whole 15-degree tiles, seed 42; stocks clipped at zero, trait quantiles sorted, traits blank where it predicts no trees). Its raw heads are reported beside, never decided on. REPORTED BESIDE, NEVER DECIDED ON: frac(x); frac(x) on rows tree-bearing in both seeds; the per-quantity band rate.

**Reference basis.** LPJmL-FIT 5.6.004, Aug-12 2026 binary. Pilot corpus v2-constco2 (seed 1, corpus.parquet sha256 9c117cb6c045fe90...) and its full second seed pilot-v2-constco2-s2 (replicate_s2.parquet sha256 b88c67875705f3dd...): 200 cells x 30 climates, single-cell 1000-year spin-ups, npatch 25, CO2 constant 276.59 ppm, base window 1970-1999; state from the end-of-spin-up restart. Emulator: models/equimap-v1/oof_pilot.parquet (sha256 97a485df6161ea8c...), inputs the 86 CLIMATE_FEATURES + 5 soil columns. 200 of the 56,986 cells; a share of rows inside a conjunctive band, and the statistic a difference of two shares.

## What this means

**Outcome (c): on the full state, under the owner's rule, the emulator is no better than copying
a neighbour.** A row passes only if all 19 varying quantities are inside the band at once. A second
run of the model does that in **10.35 %** of the 6,000 pilot rows; the emulator's emitted prediction
in **0.36 %** (D = -0.0999), below the best lookup -- the nearest training cell's forest under the
same climate, 3.25 % (D -0.071), most of it treeless rows copied from a treeless neighbour. On rows
tree-bearing in both seeds the emulator passes 0.03 %. All four nulls returned their values exactly.

**What that does and does not mean.** Quantity by quantity the emulator is inside the band in 18 %
(biomass) to 71 % (wood density p10) of rows, but almost never on all 19 in the same row; the sealed
map explains 0.608 of the variance of the same predictions. The conjunctive per-row band is
dominated by realisation noise -- the model itself fails it in 90 % of rows -- so getting there needs
a prediction that is right on every quantity of the same forest at once, which independent
per-quantity regressors are not built to be. It is the sharpest statement so far of the gap.

⚠ 200 cells, pilot only; the raw heads score 0.03 % (the post-processing helps). Not the all-cell
criterion, which exists only for vegetation carbon (X-20260924-spinup-vegc-*).

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_state_pilot | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.0999167 | -0.0999167 | — |
| training_mean | -0.1035 | — | -0.1035 +/- 0.001 [OK] |
| nearest_analogue | -0.0881667 | — | -0.088167 +/- 0.001 [OK] |
| nearest_geographic | -0.071 | — | -0.071 +/- 0.001 [OK] |
| shuffled | -0.1035 | — | -0.1035 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.0999167 |

- margin -0.0999167 does not satisfy >= -0.02
<!-- END GENERATED -->
