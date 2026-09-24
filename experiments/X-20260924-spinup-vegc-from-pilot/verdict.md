# Verdict — X-20260924-spinup-vegc-from-pilot

outcome: fail

**Question.** The owner, 2026-09-24: "you dont need new runs. there is spinup ... available already. in the spinup only the years until the onset of rising co2 levels should be used ... for now make the emulator work for the spinup with constant co2." And the pass rule the owner chose the same day: the emulator must be AS GOOD AS A RERUN of the original model, cell by cell, on the 56,986 cells that carry any stem, at 25 patches.
The stored global spin-up (seeds 1 and 2, model years 1000-1999) recycles the 1901-1930 climate and holds CO2 at 276.59 ppm until model year 1699. Of those constant-CO2 years it kept, per cell, only vegetation carbon. So this is the all-cell test that exists: shown only a cell's 1901-1930 climate and its soil, the emulator trained ONLY on the 200-cell constant-CO2 pilot (single-cell spin-ups under 30 perturbed 1970-1999 climates) predicts that cell's equilibrium vegetation carbon, and it is scored exactly the way a second run of the model would be scored.
THE FALSIFIABLE CLAIM: D = frac(emulator) - frac(rerun) >= -0.02, i.e. across the 56,986 cells the emulator lands inside the acceptance band at most 2 cells in 100 less often than a second run of LPJmL-FIT does.
⚠ WHAT A PASS WOULD NOT SAY: nothing about tree counts, traits or soil carbon (not stored for these years; they stay a pilot test), nothing about a warmed climate (1901-1930 is the only climate here), and nothing about the restart file (this scores the map's vegetation-carbon head, not a synthesised restart).

**Estimand.** `asgood_vegc_spinup` — Rows: the 56,986 cells with any stem in the stored restart_1999, seed 1 (the owner's acceptance set), each in a 15-degree tile the pilot covers (asserted). Truth per seed k in {1, 2}: T_k = that seed's mean total vegetation carbon (netCDF VegC, trees + grass, gC/m2) over model years 1450-1699. Band per cell: w = max(0.10, s), s = |H_1 - H_2| / mean(H_1, H_2), where H_k is seed k's mean over the EARLIER, DISJOINT years 1200-1449, so the pair being scored never sets its own tolerance; s = 0 where mean(H) <= 1 gC/m2. An arm x passes against T_k if |x - T_k| <= w * |T_k|; its per-cell score is the mean over k = 1, 2. frac(x) = the mean per-cell score over the 56,986 cells. frac(rerun) scores T_2 against T_1 and T_1 against T_2 with the same w. THE STATISTIC: D(x) = frac(x) - frac(rerun). Higher is better; 0 means exactly as good as a rerun; the emulator predicts one value per cell and is scored against both seeds. THE EMULATOR (model arm): one LightGBM regressor per fold with the sealed recipe's hyperparameters (scripts/exp_model_pilot_response.PARAMS, as in X-20260923-equilibrium-from-climate), fitted on log1p of each pilot row's two-seed mean of its 1200-1699 VegC window mean, from the same 91 features (86 CLIMATE_FEATURES + 5 soil columns), on the pilot cells of the other four folds (all 30 climates each); predictions are expm1, clipped at 0. Each global cell is predicted by the model of its own tile's fold. REPORTED BESIDE THE STATISTIC, NEVER DECIDED ON, with every null beside it: frac(x); variance explained on log1p against the two-seed mean (T_1 + T_2) / 2; the share inside a FLAT 10 % of that mean; D per latitude band; a 90 % interval on D from 1,000 bootstrap resamples of whole 15-degree tiles (seed 7).

**Reference basis.** The stored global LPJmL-FIT 5.6.004 spin-up, Historical ground truth, Feb-05 2026 binary, npatch 25, seeds 1 and 2, model years 1000-1999, 67,420 cells; CO2 276.59 ppm (the getco2.c clamp) for model years < 1700, which is the only part used. Recycled climate: the first 30 years (1901-1930) of GSWP3-W5E5 v3 forcing. Per-cell target from vegc_spinup_1999.nc via scripts/spinup_target.py --stage truth (spinup_truth.parquet sha256 37391b3f70c12995...). Inputs: that 1901-1930 window's 86 CLIMATE_FEATURES + 5 soil columns joined as in exp_equilibrium_map.load (climate_spinup.parquet sha256 cc1f795157f19e59...). Training: pilot corpus v2-constco2 (200 cells x 30 climates, single-cell spin-ups, Aug-12 binary, constant CO2 276.59 ppm) with its full second seed pilot-v2-constco2-s2; targets from each run's own vegc_spinup_*.nc (pilot_trajectory_stats.parquet sha256 745197c70804b209...). 56,986 cells scored, level (a share of cells inside a band), the statistic a difference of two shares.

## What this means

**Outcome (b): the emulator beats every lookup, and it is not yet as good as a rerun.** Trained only
on the 200-cell pilot and shown only each cell's 1901-1930 climate and soil, it lands inside the
acceptance band in **24.7 %** of the 56,986 cells, where a second run of the model lands inside it
in **85.9 %**. So D = **-0.612** (tile-bootstrap 90 %: -0.633 to -0.591) against the -0.02 the
owner's rule needs; the best lookup, copying the most similar pilot climate, is at -0.675. All four
nulls returned their pre-registered values exactly.

**Where it is strong: the shape of the global forest.** It explains **0.926** of the variation in
log vegetation carbon across all cells (the most similar pilot climate: 0.576; a rerun: 0.995),
from a model that never saw the stored run, its protocol or its climate window. **Where it fails:
the last factor of two.** A typical cell is off by more than the 10 % a rerun stays within; the
shortfall is spread over every latitude band (D -0.53 to -0.68), worst north of 50 deg N.

⚠ Vegetation carbon only -- the stored spin-up kept nothing else for these years. The first run of
this model arm lost its reported-beside detail to a key clash (decision values unaffected); it was
re-run with identical decision values (jobs 2286377, 2286394) and the detail is from the re-run.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_spinup | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.612168 | -0.612168 | — |
| training_mean | -0.812129 | — | -0.812129 +/- 0.001 [OK] |
| nearest_analogue | -0.675043 | — | -0.675043 +/- 0.001 [OK] |
| nearest_geographic | -0.734821 | — | -0.734821 +/- 0.001 [OK] |
| shuffled | -0.814753 | — | -0.814753 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.612168 |

- margin -0.612168 does not satisfy >= -0.02
<!-- END GENERATED -->
