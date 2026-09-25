# Verdict — X-20260925-continuation-same-window

outcome: fail

**Question.** The successor of X-20260925-spinup-restart-continuation (sealed, fail, unedited), with two changes and nothing else. (1) THE REFERENCE. That test read a 10-year mean of one continuation against a rerun that compares two 250-year means (0.858711), which no 10-year mean of a real run reaches: measured on the stored run itself (scripts/diag_window_ceiling.py, job 2319481), a real seed's 10-year window lands in band on 0.598 of the 56,986 scored cells and 0.622 of those in folds 3-4. The owner decided on 2026-09-25 that "as good as a rerun" for a continuation means as good as a real run scored on the same window (docs/decisions/20260925-INT-a-continuation-is- judged-against-a-real-run-on-the-same-window.md). (2) THE FILE. The emulated restart now takes its trees from the pilot's constant-CO2 spin-ups (vegemu.models.pilot_donors:PilotBank; the 1999 donors carried the 1999 CO2 into a 276.59 ppm run and died in year 5) and its stem count is rescaled per cell until its vegetation carbon matches the screened carbon map's held-out prediction (SpinupRule match_vegc; the map writing stem counts and sizes put the old file 20 % low).
THE FALSIFIABLE CLAIM: on the 20,123 tree-bearing scored cells of folds 3 and 4, D = frac(the continued emulated restart, years 1-10) - frac(a real run, 10-year window) >= -0.02.
⚠ EXPECTED OUTCOME, STATED BEFORE SEALING: FAIL, outcome (b). A dev diagnostic on 51 of the 1,015 members (journal/X/2026-09b.md, 2026-09-25 evening) put the same construction at frac 0.561 on its 846 folds-3-4 cells, about D -0.06, with the loss concentrated in a year-5 die-off (-9.4 % of vegetation carbon). This test gives the all-cell number with every null beside it.
⚠ WHAT A PASS WOULD NOT SAY: vegetation carbon only; one climate (1901-1930); nothing about a warmed climate; and the template of each cell is still its own restart_1999 record (grasses, soil water, profiles, header), whose information the restart_1999 continuation null measures.

**Estimand.** `asgood_vegc_continuation_same_window` — Truth, band and per-cell pass EXACTLY as X-20260924-spinup-vegc-from-pilot, by the same code (scripts/exp_spinup_vegc.py scored_set and score): T_k = seed k's mean VegC over model years 1450-1699; w = max(0.10, s) from the 1200-1449 halves; an arm x passes against T_k if |x - T_k| <= w |T_k|, its per-cell score the mean over k = 1, 2. SCORED CELLS: the scored cells whose 15-degree tile is in fold 3 or 4 of the sealed tile -> fold map (15 deg, k=5, seed 42): 20,123 of 56,986 -- the carbon target was CHOSEN on folds 0-2, so only 3-4 are clean. THE REFERENCE, per cell: diag_window_ceiling.window_cell_scores(10): each non-overlapping 10-year window (25 of them) of model years 1450-1699 of seed k, scored against T_(3-k) with w, averaged over both seeds and all windows; frac(real, 10) = 0.622260 on these cells. It replaces rerun_cell / frac_rerun in exp_spinup_vegc.score, so D = frac(x) - frac(real, 10) and the tile bootstrap reads against it. THE STATISTIC: D on continuation years 1-10. x FOR A CONTINUATION ARM: the real model's own annual VegC (netCDF, trees + grass) averaged over continuation years 1-10, per cell, from the continuation run of the predecessor, unchanged: scripts/spinup_continuation.py build (the stored run's saved config; restart from the arm's file, 30 shuffled draws of 1901-1930 at model years 1871-1900, constant 276.59 ppm, -DFROM_RESTART, Aug-12 2026 binary, npatch 25, no restart written; outputs VegC, globalflux, grid, climatyear), the same 1,015 members (members.json sha256 bbfb9768...), which must all print the model's completion line; every arm draws the same 30 years (checked). THE MODEL ARM: restart_1699_emulated.lpj of runs/spinup-product-v3vegc-global (job 2322007): scripts/synth_global.py run --cell-rule vegemu.models.spinup_rule:SpinupRule --synth-kwargs {"stop_year": 1699, "litter_rule": "soilc", "match_vegc": true} --donor-rule vegemu.models.pilot_donors:PilotBank --donor-opts {"predictions": <equimap-v1 pred_1901_1930_heldout.parquet>}, template restart_1999 seed 1, predictions = equimap-v1's held-out table (sha256 03f7f765...) plus pred_vegc_target = the screen's pred_best (held out per fold, T-screen-spinup-vegc-r2/predictions.parquet sha256 99e84e9a...; merged table sha256 3f678917...). match_vegc: up to 3 re-syntheses scaling stems_per_patch toward vegc_target - template grass, tolerance 2 %, cap 4x the map's count; no trees where the target is at or below the grass; map-treeless cells stay treeless. As written 2026-09-25 (job 2322007, verify PASS, 128,190,246,163 B, sha256 6cef14e080a9bb8c...): 56,986 cells synthesised, 10,434 passed through, 33,971,450 stems placed, 0 inadmissible; 48,737 cells matched within 2 %, 4,262 below the grass (no trees written), 2,369 passes exhausted, 1,253 capped, 236 with no tree carbon, 129 map-treeless; total written / target 0.996 (first pass 0.806). REPORTED BESIDE, NEVER DECIDED ON: years 21-30 (against the same 10-year reference); year 1 alone (against the 1-year reference, 0.540600 on these cells); all 56,986 cells (10-year reference 0.598312); frac; variance explained on log1p; the flat-10 % rate; D by latitude; the tile bootstrap interval; and D against the 250-year rerun (0.869478 on these cells), so the predecessor's reading stays visible.

**Reference basis.** Stored global LPJmL-FIT 5.6.004 spin-up, Historical ground truth, Feb-05 2026 binary, npatch 25, seeds 1 and 2, model years 1000-1699 at the 276.59 ppm clamp, recycled 1901-1930 GSWP3-W5E5; spinup_truth.parquet sha256 37391b3f70c12995... and vegc_spinup_1999.nc of each seed (the reference's windows; the script asserts they reproduce the truth's means). Continuations: LPJmL-FIT 5.6.004 Aug-12 2026 binary at constant 276.59 ppm. 20,123 cells scored (folds 3-4 of the 56,986 with any stem), a level (share of cells in band), the statistic a difference of two shares.

## What this means

**Outcome (b), fail: better than every null, not yet as good as a real run.** Started from the
carbon-matched emulated restart and continued 30 years at constant CO2, the real model lands in
band over years 1-10 on **49.4 %** of the 20,123 held-out cells, where a real run's 10-year window
does on **62.2 %**: D = **-0.129** (tile bootstrap 90 % -0.163 to -0.092) against the -0.02 the
rule needs. The best null, the climate-analogue lookup, is at -0.303; restart_1999 continued the
same way at -0.341; the file this replaces at -0.349. All six nulls returned their sealed values.
1015/1015 members completed; every arm drew the same 30 years.

**Where it is already real-run grade: year 1.** Year 1 alone, against a real single year: D -0.018
on these cells (-0.053 to +0.017), +0.001 on all 56,986. The first-decade loss is the year-5
die-off (global vegetation carbon 678 -> 607 PgC between years 4 and 5, then regrowth to 685 by
year 30); years 21-30 are at D -0.125. All cells, years 1-10: frac 0.470 vs 0.598 (D -0.129).
Worst north of 50 N (-0.156, 9,530 cells) and in the tropics (-0.15 to -0.16); best south of
23.5 S (-0.048). The 51-member dev sample had suggested about -0.06 on its 846 folds-3-4 cells:
the sample was not representative of this subset, and the sealed number is this one.

Vegetation carbon only, one climate. The year-5 cause is not found: zeroing inherited bad-growth
counters made it worse and fewer taller stems did not change it (journal, dev).

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_continuation_same_window | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.128522 | -0.128522 | — |
| restart_1999_continuation | -0.340592 | — | -0.340592 +/- 0.001 [OK] |
| previous_emulated_continuation | -0.349413 | — | -0.349413 +/- 0.001 [OK] |
| training_mean | -0.561409 | — | -0.561409 +/- 0.001 [OK] |
| nearest_analogue | -0.302899 | — | -0.302899 +/- 0.001 [OK] |
| nearest_geographic | -0.381516 | — | -0.381516 +/- 0.001 [OK] |
| shuffled | -0.573212 | — | -0.573212 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.128522 |

- margin -0.128522 does not satisfy >= -0.02
<!-- END GENERATED -->
