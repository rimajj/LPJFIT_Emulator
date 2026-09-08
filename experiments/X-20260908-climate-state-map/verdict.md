# Verdict — X-20260908-climate-state-map
outcome: fail
**Question.** Given only a cell's 30-year climate summary -- and no knowledge of where the cell is -- can a learned map put the model's own forest state inside the acceptance band on stem count AND every scored trait median AND both tails of every scored trait distribution, simultaneously, in more held-out cells than the geographically nearest forest or the climatically nearest analogue does?

**Estimand.** `band_frac_conjunctive` — The fraction of scored cells in which EVERY one of 22 quantities lands inside its own acceptance band. The 22 are: stems per patch; above-ground biomass, leaf area index and soil carbon; the median of each of wood density, specific leaf area, fine-root conductivity, the 95th-percentile rooting depth, leaf longevity and stem height; and the 10th and 90th percentile of each of those six traits. A cell's band for a quantity is max(10 %, |seed1-seed2| / |mean|) * |mean| -- the project's acceptance tolerance, i.e. ten per cent or the model's own two-seed spread, whichever is larger. The truth is the MEAN of the two seeds, because ~28 % of residual variance is the model's own realisation noise and the correct target is therefore the ensemble expectation, not a single draw. Aggregation is per cell, unweighted, computed once over the assembled out-of-fold prediction -- every cell is held out exactly once -- rather than averaged over folds, which would give a fold containing the Amazon the same weight as one containing Patagonia. A NaN on either side counts as a MISS.

**Reference basis.** LPJmL-FIT 5.6.004, historical leg, state read from restart_1999.lpj (the end of the 1000-year spin-up plus the 1901-1999 historical transient -- NOT a converged equilibrium, see docs/decisions/20260908-D-spinup-is-not-converged.md), npatch=25, tree PFTs only, climate window 1970-1999, truth = mean of random_seed1 and random_seed2, both produced by the 2026-02-05 LPJmL-FIT binary build, 56,950 cells that are tree-bearing (>= 0.5 stems per patch) in BOTH seeds out of 67,420. Dimensionless fraction.

## What this means

<!-- Two or three sentences in plain language. State what was measured, against what, and what is
     still unknown. If the outcome is `invalid`, say plainly which null misbehaved and why that
     voids the comparison rather than merely weakening it. -->

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | band_frac_conjunctive | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.0360667 | 0.01482 | — |
| nearest_analogue | 0.0212467 | — | 0.021247 +/- 0.001 [OK] |
| geographic_address | 0.0186831 | — | 0.018683 +/- 0.001 [OK] |
| climatological_mean | 0 | — | 0 +/- 0.002 [OK] |
| shuffled_target | 0.00071993 | — | 0.00072 +/- 0.002 [OK] |
| **DECISION** | pass_if > 0.05 | **FAIL** | 0.01482 |

- margin 0.01482 does not satisfy > 0.05
<!-- END GENERATED -->
