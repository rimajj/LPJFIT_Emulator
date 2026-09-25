# Verdict — X-20260925-spinup-restart-continuation

outcome: fail

**Question.** The owner, 2026-09-24: "make the emulator work for the spinup with constant co2"; pass rule the same day: AS GOOD AS A RERUN of the original model, cell by cell, on the 56,986 cells that carry any stem, at 25 patches, CO2 276.59 ppm (docs/decisions/20260924-INT-*).
The emulator's product is a restart file: every cell's forest, soil and climate memory at the end of the stored global spin-up's constant-CO2 stretch (model year 1699), written from the climate-only equilibrium map's held-out prediction for the cell's recycled 1901-1930 climate (`scripts/synth_global.py --cell-rule vegemu.models.spinup_rule:SpinupRule`). The sealed map test (X-20260924-spinup-vegc-from-pilot) scored the map's vegetation-carbon HEAD; this scores the FILE the way an equilibrium restart must be judged -- by handing it to the real model and letting the model run. LPJmL-FIT is started from the file (-DFROM_RESTART) and continues the stored run's own protocol for 30 model years (shuffled draws of 1901-1930, 276.59 ppm, every other setting the stored run's), and the mean vegetation carbon of continuation years 1-10 is scored exactly as a second run of the model would be.
THE FALSIFIABLE CLAIM: D = frac(emulated continuation) - frac(rerun) >= -0.02, i.e. across the 56,986 cells the model started from the emulated restart lands inside the acceptance band at most 2 cells in 100 less often than a second run of LPJmL-FIT does.
⚠ WHAT A PASS WOULD NOT SAY: nothing about tree counts, traits or soil carbon (the stored run kept only vegetation carbon for these years); nothing about a warmed climate (1901-1930 is the only climate here); and nothing about an emulator that never saw the cell -- the synthesiser's template is each cell's own restart_1999 record (see leakage_checks), whose information is exactly what the restart_1999 continuation null measures.

**Estimand.** `asgood_vegc_spinup` — Rows, truth, band, pass and frac EXACTLY as in X-20260924-spinup-vegc-from-pilot, computed by the same code (`scripts/exp_spinup_vegc.py` `scored_set` and `score`): the 56,986 cells with any stem in the stored restart_1999, seed 1, each in a 15-degree tile the pilot covers (asserted); T_k = seed k's mean total VegC (trees + grass, gC/m2) over model years 1450-1699; band w = max(0.10, s), s = |H_1 - H_2| / mean(H_1, H_2) with H_k seed k's 1200-1449 mean (s = 0 where mean(H) <= 1 gC/m2); an arm x passes against T_k if |x - T_k| <= w |T_k|, its per-cell score the mean over k = 1, 2; frac(x) the mean per-cell score; frac(rerun) = 0.858711 scores T_2 against T_1 and T_1 against T_2 with the same w. THE STATISTIC: D(x) = frac(x) - frac(rerun). x FOR AN ARM: the real model's own annual VegC output (netCDF, trees + grass) averaged over continuation years 1-10 (model years 1871-1880 of the continuation run), per cell. THE CONTINUATION RUN (`scripts/spinup_continuation.py`, identical for every arm): the stored run's saved config (`scripts_for_running_the_model/lpjml_2000_2019.js`) with exactly these changes, each asserted to hit: restart true from the arm's file, nspinup 30, nspinyear 30, firstyear 1901, lastyear 1900 (so all 30 years are shuffled spin-up draws of 1901-1930, iterate.c:102-119), a constant 276.59 ppm CO2 file, no restart written, outputs VegC (cdf), globalflux (txt), grid (cdf) and climatyear (txt); npatch 25, fire, shuffle, inheritance and every other setting unchanged; -DFROM_RESTART; Aug-12 2026 build (`lpjml.binary`, byte-identical to the Feb-05 build on the one cell-year tested, 20260923-D-the-two-builds-*). The 30 years drawn follow from the restart header's RNG state (openrestart.c:139); both arms carry restart_1999's header, so both draw the same 30 years (checked from the climatyear output; the model arm is refused if they differ). Run as 1,015 contiguous cell ranges of one task each in a task farm (members.json), the same ranges for every arm. THE MODEL ARM: the emulated restart `restart_1699_emulated.lpj` continued. Its cells: every cell with a stem in restart_1999 and a prediction is synthesised by `synthesise_cell` with predicted stem shares, the types the model's own bioclimatic limits admit under the cell's replayed 1699 climate buffer, that buffer itself (replayed from the cell's 1901-1930 forcing, the stored protocol stopped at 1699: 700 shuffled draws), and litter rescaled by predicted / template soil carbon; every other cell is restart_1999's record unchanged. As written 2026-09-24 (restart_1699_emulated.lpj, 127,214,462,509 B, sha256 7fe58fc220be43ac..., job 2287401): 56,986 cells synthesised, 10,434 passed through (no stem in the template), 32,210,123 stems placed of 32,369,762 requested; 620 synthesised cells hold no tree: 612 where the climate rule admits no tree type under the 1699 buffer (their requests are the whole 159,639-stem shortfall; 121 of them the map also predicts treeless) and 8 more the map predicts treeless. REPORTED BESIDE THE STATISTIC, NEVER DECIDED ON, with every null beside it: D on the mean of continuation years 21-30 (THE DRIFT WINDOW: the primary window scores whether the model holds the state in its first decade; 21-30 says where the state is going -- a model arm that passes on 1-10 and falls on 21-30 is relaxing away from the stored equilibrium, one that rises from 1-10 to 21-30 was placed off it and is being pulled back, and the restart_1999 continuation's own change between the windows is the rate at which the model sheds the CO2-ramp carbon); D of every single year; frac(x); variance explained on log1p against the two-seed mean; the flat-10 % rate; D per latitude band; the 90 % tile-bootstrap interval on D; the scored cells' total VegC over the truth's, per year; and the year-0 VegC read back from each arm's restart file (dev diagnostic, `scripts/spinup_product.py --stage year0`).

**Reference basis.** The stored global LPJmL-FIT 5.6.004 spin-up, Historical ground truth, Feb-05 2026 binary, npatch 25, seeds 1 and 2, model years 1000-1999, 67,420 cells; CO2 276.59 ppm (the getco2.c clamp) for model years < 1700, which is the only part scored. Recycled climate 1901-1930 of GSWP3-W5E5 v3. Per-cell truth from vegc_spinup_1999.nc via scripts/spinup_target.py --stage truth (spinup_truth.parquet sha256 37391b3f70c12995...). Continuation runs: LPJmL-FIT 5.6.004 Aug-12 2026 binary from restart_1999 (null arm) and from the emulated restart (model arm), model years 1871-1900 at constant 276.59 ppm (co2_const_276.59.txt sha256 ba414a720588249f...). Emulated restart: models/equimap-v1 pred_1901_1930_heldout.parquet (held-out per fold, sealed folds), template restart_1999 seed 1, census census_restart_1999.parquet. 56,986 cells scored, level (a share of cells inside a band), the statistic a difference of two shares.

## What this means

**Outcome: fail, and the run that produced it has a defect that hits both arms.** Started from the
emulated 1699 restart and continued at constant CO2 under the recycled 1901-1930 climate, the model
lands inside the band in **25.4 %** of the 56,986 cells over continuation years 1-10 (D -0.605;
tile-bootstrap 90 % -0.625 to -0.584), below the stored restart_1999 continued the same way (29.2 %,
D -0.567) and far from a rerun (85.9 %). By years 21-30 the two arms converge: 40.3 % and 41.0 %.
All nulls returned their values; both arms drew the same 30 climate years.

⚠ **The continuation protocol is not trustworthy yet.** Both arms lose a large part of their global
vegetation carbon in ONE year, the same one (emulated 566 -> 465 PgC, restart_1999 780 -> 523 PgC),
with NPP unchanged and litter jumping. The stored spin-up never drops more than 0.8 % in a year over
its 500 constant-CO2 years (1200-1699). So the die-off is an artefact of how the continuation was
set up (suspected, not verified: the per-tree five-bad-years kill rule firing after a mismatch at
the restart), and the scored window straddles it. The number is recorded as the rule gives it; it is
not evidence about the file's equilibrium. A corrected protocol needs a new experiment id.

**What still reads cleanly:** the emulated file starts with 573 PgC of vegetation carbon against the
stored equilibrium's 732 (22 % low globally), where restart_1999 starts 16 % high.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_spinup | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.604815 | -0.604815 | — |
| restart_1999_continuation | -0.567148 | — | -0.567148 +/- 0.001 [OK] |
| training_mean | -0.812129 | — | -0.812129 +/- 0.001 [OK] |
| nearest_analogue | -0.675043 | — | -0.675043 +/- 0.001 [OK] |
| nearest_geographic | -0.734821 | — | -0.734821 +/- 0.001 [OK] |
| shuffled | -0.814753 | — | -0.814753 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.604815 |

- margin -0.604815 does not satisfy >= -0.02
<!-- END GENERATED -->
