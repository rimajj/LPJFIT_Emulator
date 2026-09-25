# Verdict — X-20260924-equilibrium-learning-curve
outcome: pass
**Question.** `X-20260923-equilibrium-from-climate` passed at 0.607582 with about 160 training cells per fold, against an attainable 0.950. Whether the next corpus should be bigger -- the "mid corpus" -- turns on whether that number is still rising with the number of training places, or has flattened.
A DESCRIPTIVE CURVE with one pre-registered question. The curve: the held-out skill when each training fold keeps 25, 50, 75 or 100 % of its cells (about 40, 80, 120, 160), five fixed subsamples per fraction, the held-out cells unchanged. THE FALSIFIABLE CLAIM: the last step of the curve -- from 75 % to 100 % -- still adds more than 0.020 of variance explained.

**Estimand.** `skill_gain_last_quarter` — gain = S(100 %) - mean over subsample seeds 1-5 of S(75 %), where S is `skill_equilibrium_mean` exactly as sealed (per quantity 1 - SSE / SS about the pooled truth mean over every row where the truth exists, the four forest-scale quantities on log1p, mean over the 19 that vary), all arms fitted by the sealed recipe in one job and scored on the IDENTICAL held-out rows. S(100 %) IS the sealed recipe. SUBSAMPLING. Within each training fold, a fraction f of its CELLS is kept, whole (all 30 of a cell's climates together), by one permutation per (seed, fold) truncated to round(f x n); so for one seed the 25 % cells sit inside the 50 %, which sit inside the 75 %. The held-out fold is never subsampled, so every arm is scored on the same 6,000 rows and every difference is paired. REPORTED BESIDE IT, NEVER DECIDED ON: the whole curve (per fraction the five seeds, their mean and spread, per quantity), and the gain per doubling of training cells (25 -> 50 % and 50 -> 100 %). ⚠ No extrapolation of the curve beyond 160 cells is licensed by this experiment.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 6,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x 1 seed, single-cell 1000-year spin-ups, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. State from the end-of-spin-up restart (uncensored). Inputs as the sealed map: the 86 climate features (including soil depth) and five soil-texture columns. Training cells per fold at 100 %: 159, 159, 156, 160, 166 at 15 deg. 200 of the 56,986 eligible cells, not the acceptance criterion's 54,020. Dimensionless; a DIFFERENCE of two ratios of sums of squares -- a ratio, not a level.

## What this means

**Outcome: pass — the equilibrium map is still learning when it runs out of training places.**
Held-out skill with 25, 50, 75 and 100 % of each fold's training cells (about 40, 80, 120, 160):
0.421, 0.522, 0.573, 0.608. The last quarter adds 0.034, against a pre-registered bar of 0.020 and
0.0044 of pure subsampling noise; each doubling of training cells adds roughly 0.09-0.10 with no
sign of flattening. 5-degree blocking, reported beside it, draws the same curve (0.428 to 0.610).
The apparatus reproduced the sealed 0.607582 exactly first.

⚠ **What it does not license:** no extrapolation beyond 160 cells, so no promise of what a larger
corpus would reach. It says only that more places were still paying at the pilot's size. The
owner parked new model runs on 2026-09-24; this is evidence for when that is revisited, not a
reason to launch. 200 of the 56,986 cells; not an acceptance claim.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_gain_last_quarter | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.0342194 | 0.0342194 | — |
| no_further_gain | 0 | — | 0 +/- 1e-06 [OK] |
| subsample_noise | 0.0044129 | — | 0.004413 +/- 0.001 [OK] |
| **DECISION** | pass_if > 0.02 | **PASS** | 0.0342194 |

- margin 0.0342194 satisfies > 0.02
<!-- END GENERATED -->
