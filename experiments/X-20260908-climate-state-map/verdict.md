# Verdict — X-20260908-climate-state-map
outcome: fail
**Question.** Given only a cell's 30-year climate summary -- and no knowledge of where the cell is -- can a learned map put the model's own forest state inside the acceptance band on stem count AND every scored trait median AND both tails of every scored trait distribution, simultaneously, in more held-out cells than the geographically nearest forest or the climatically nearest analogue does?

**Estimand.** `band_frac_conjunctive` — The fraction of scored cells in which EVERY one of 22 quantities lands inside its own acceptance band. The 22 are: stems per patch; above-ground biomass, leaf area index and soil carbon; the median of each of wood density, specific leaf area, fine-root conductivity, the 95th-percentile rooting depth, leaf longevity and stem height; and the 10th and 90th percentile of each of those six traits. A cell's band for a quantity is max(10 %, |seed1-seed2| / |mean|) * |mean| -- the project's acceptance tolerance, i.e. ten per cent or the model's own two-seed spread, whichever is larger. The truth is the MEAN of the two seeds, because ~28 % of residual variance is the model's own realisation noise and the correct target is therefore the ensemble expectation, not a single draw. Aggregation is per cell, unweighted, computed once over the assembled out-of-fold prediction -- every cell is held out exactly once -- rather than averaged over folds, which would give a fold containing the Amazon the same weight as one containing Patagonia. A NaN on either side counts as a MISS.

**Reference basis.** LPJmL-FIT 5.6.004, historical leg, state read from restart_1999.lpj (the end of the 1000-year spin-up plus the 1901-1999 historical transient -- NOT a converged equilibrium, see docs/decisions/20260908-D-spinup-is-not-converged.md), npatch=25, tree PFTs only, climate window 1970-1999, truth = mean of random_seed1 and random_seed2, both produced by the 2026-02-05 LPJmL-FIT binary build, 56,950 cells that are tree-bearing (>= 0.5 stems per patch) in BOTH seeds out of 67,420. Dimensionless fraction.

## What this means

**Climate alone does predict the forest, and it beats every honest competitor — but not by the
margin that was demanded in advance.** Given only a 30-year climate summary, and told nothing about
where the cell is, the emulator got the whole forest right at once — stem count, three carbon and
leaf stocks, six trait medians and both tails of six trait distributions, all 22 inside the
model's own reproducibility band — in 3.6 % of held-out cells. Copying the forest from the
climatically most similar training cell manages 2.1 %; copying from the geographically nearest
training cell, 1.9 %. So the emulator is 1.7× the best alternative, and the gate asked for it to be
roughly 3.4× that. It is a fail on the pre-registered terms, and those terms were sealed before the
model was fitted.

**3.6 % sounds much worse than the emulator actually is, and both numbers matter.** The test is
conjunctive on purpose: a cell counts only if all 22 quantities land inside their band
simultaneously. Taken one at a time the emulator puts 41–100 % of cells inside the band, and the
distribution of "how many of the 22 hit" peaks at 17–18 out of 22. Most cells get most of the way
there and are stopped by one or two quantities — above-ground biomass (41 %) and leaf area (48 %)
most often. Neither number should be quoted without the other.

**What the band is.** Not a flat 10 %. LPJmL-FIT is stochastic, so the tolerance is ten per cent or
the disagreement between two runs of the model that differ only in their random seed, whichever is
larger — 3.4 % at the median but 42 % in the noisiest cells. A tighter band would charge the
emulator for noise no emulator can predict.

**What is still unknown.** This measures the forest under one climate. It says nothing about how
the forest RESPONDS to a different climate — that is the companion experiment
`X-20260908-warming-response`, and it failed. Two honest disclosures travel with the number above:
one of the 22 quantities (fine-root conductivity) is nearly constant across the globe and so passes
everywhere for free; and the band is derived from the same two model runs whose average is the
target, which makes the "one run of the model against the average of two" reference trivially
perfect and therefore a ceiling rather than a comparison.

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
