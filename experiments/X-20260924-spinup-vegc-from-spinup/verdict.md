# Verdict — X-20260924-spinup-vegc-from-spinup

outcome: fail

**Question.** The sibling of X-20260924-spinup-vegc-from-pilot, with the SAME estimand, cells, band, folds and pass rule, and ONE difference: the map is trained on the stored global spin-up's own cells in the other four folds (one climate per place, the reference's own global-run protocol), instead of on the pilot. It answers what the owner's all-cell target allows a climate-only map to reach on vegetation carbon, so a shortfall of the pilot-trained emulator can be read as a data problem (too few cells, single-cell protocol) or a problem of the target itself.
THE FALSIFIABLE CLAIM: D = frac(map) - frac(rerun) >= -0.02 on the 56,986 cells.
⚠ WHAT A PASS WOULD NOT SAY: this map has seen one climate per place, so it identifies no warming response (MEMORY.md:ident-limit) and must never be quoted for a warmed climate; nothing about tree counts or traits; nothing about a restart file.

**Estimand.** `asgood_vegc_spinup` — Identical to X-20260924-spinup-vegc-from-pilot (see its definition), except the model arm: one LightGBM regressor per fold with the same PARAMS, fitted on log1p of each stored-spin-up cell's two-seed mean of its 1200-1699 VegC window mean, from that cell's 91 features of the 1901-1930 window, on every cell OUTSIDE the predicted fold (cells in a tile no pilot cell covers are never scored and train every fold). Each scored cell is predicted by the model of its own tile's fold; its own tile never trains it. ⚠ The training target of the other cells uses years 1450-1699 of those cells; the scored cell's own truth never enters its own prediction.

**Reference basis.** As X-20260924-spinup-vegc-from-pilot: stored global spin-up, Feb-05 2026 binary, npatch 25, seeds 1 and 2, constant CO2 276.59 ppm for model years < 1700 (the only part used), recycled climate 1901-1930; spinup_truth.parquet sha256 37391b3f70c12995..., climate_spinup.parquet sha256 cc1f795157f19e59.... Training pool: the same stored spin-up, other folds, 67,420 cells minus the held-out fold. 56,986 cells scored; the statistic a difference of two shares.

## What this means

**Outcome (b): trained on the stored spin-up's own cells, a climate-only map reaches 42.7 % of cells
inside the band, against 85.9 % for a rerun.** D = **-0.432** (tile-bootstrap 90 %: -0.458 to
-0.407), beating the best lookup (-0.527) but far from the -0.02 the owner's rule needs. Variance
explained on log vegetation carbon: **0.961** (rerun 0.995). All four nulls returned their
pre-registered values exactly.

**What it tells the pilot-trained sibling.** Even with 52,000-57,000 training cells on the
reference's own protocol, the same inputs and learner leave most cells outside a 10 % band. So the
emulator's shortfall (24.7 %) is only partly the pilot's 200 cells: the 30-year climate plus soil,
fed to this learner, does not pin a cell's equilibrium carbon to within 10 % in most places. The
next levers are the inputs (daily-forcing features, soil water) and the target (a mean over two
seeds is what is learnable), not only more cells.

⚠ One climate per place: this map identifies no warming response and must never be quoted for a
warmed climate. Vegetation carbon only. The model arm was run twice with identical decision values
(jobs 2286378, 2286395); the reported-beside detail is from the second run.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | asgood_vegc_spinup | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.43165 | -0.43165 | — |
| training_mean | -0.806461 | — | -0.806461 +/- 0.001 [OK] |
| nearest_analogue | -0.527296 | — | -0.527296 +/- 0.001 [OK] |
| nearest_geographic | -0.596989 | — | -0.596989 +/- 0.001 [OK] |
| shuffled | -0.814753 | — | -0.814753 +/- 0.001 [OK] |
| **DECISION** | pass_if >= -0.02 | **FAIL** | -0.43165 |

- margin -0.43165 does not satisfy >= -0.02
<!-- END GENERATED -->
