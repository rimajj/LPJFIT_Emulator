# Verdict — X-20260924-restart-worst-quantity

outcome: fail

**Question.** The deliverable is a restart file the real model loads. For each pilot cell and each of the 29 climates it was spun up under besides its control, the synthesiser (`scripts/synth_pilot.py --stage synth --arm map`) writes a restart from the climate-only equilibrium map's out-of-fold prediction, starting from the cell's CONTROL restart; the forest in that file is read back with the corpus's own decoder. The retired emitted-restart test asked "inside the acceptance band on all 22 quantities at once?" and could rank nothing: at the 10 % floor its six nulls sat within 0.004 of zero and a shuffled cell tied first (`docs/decisions/20260915-X-x4-is-not-sealable-*`, `20260915-X-the-perturbed-spread-does-not-widen-*`).
THE FALSIFIABLE CLAIM: scored by its WORST quantity in band units -- the same band, the same 10 % floor, no quantity dropped, no climate excluded -- the read-back forest is closer to the settled forest than the best information-free restart, which is the cell's own control restart copied unchanged, by more than 0.34 in -log(median worst-quantity error): its typical target's worst quantity must sit at most exp(-0.34) = 0.71 times as many bands off as the unedited control's.

**Estimand.** `worst_quantity_skill` — ROWS: the 5,800 (cell, perturbed climate) targets of pilot-v2-constco2 -- 200 cells x the 29 climates other than each cell's control. The control is the synthesiser's template and the `same_cell_template` null, so it is the input, not a target. TRUTH per target: the mean of the two runs of that spin-up (seed 1, and seed 2 from pilot-v2-constco2-s2), per quantity, for the 22 of SCORED_CONJUNCTIVE. A trait quantile is undefined in a treeless run; where either run is treeless it is undefined in the mean. BAND per target per quantity: max(10 %, s) x |truth| with no additive floor (`vegemu.score.band_from_spread`, `abs_floor=0.0`), where s is the MEDIAN over the same cell's OTHER 29 climates of that quantity's two-run relative spread |s1 - s2| / |mean| (`vegemu.score.spread_across_climates`). The scored climate's own pair never sets its own band, which is what stops a real run passing by arithmetic; the transfer across climates rests on the measured flatness of the run-to-run spread under perturbation (20 cells x 30 climates, median 0.0301 perturbed vs 0.0310 control). Measured on this corpus: median floored s 0.100, 14.5 % of cell-quantity-climates above the floor. PER TARGET: e = max over the 19 quantities of SCORED_CONJUNCTIVE that vary (all but the three fine-root-conductivity quantiles, constant 0.02 in every tree-bearing run; `score.assert_constant_quantities` refuses the run if they vary) of |pred - truth| / band, with the rules of `vegemu.score`'s C1 section: a quantity is scored only where the truth exists; a missing prediction where it exists is e = inf; a zero band passes only an exact prediction; a row with nothing scored is e = inf. STATISTIC: -log of the LOWER median of e over the 5,800 targets (`score.worst_quantity_skill`). Higher is better; exp(-statistic) is the median target's worst-quantity error in bands. Chosen before any arm was scored under it, for having no free parameter; not tuned on any arm. REPORTED BESIDE IT, NEVER DECIDED ON: the ACCEPTANCE NUMBER -- the share of targets with every scored quantity inside its band (`share_within_band`) -- with its ceiling; the retired test's 22-quantity conjunctive fraction for continuity; e quantiles; which quantity sets e how often; the statistic per climate; per-quantity band rates; the same after one year of the real C model on whatever targets were run; and the synthesiser's oracle arm (true state in), which measures what the synthesis alone loses.

**Reference basis.** LPJmL-FIT 5.6.004, binary built 2026-08-12, one binary for all 12,000 runs. Pilot corpus v2-constco2: 200 cells x 30 climates x TWO seeds, single-cell 1000-year spin-ups, npatch=25, tree PFTs only, base climate window 1970-1999, CO2 constant at 276.59 ppm. Seed 1 is corpus/pilot-v2-constco2 (corpus.parquet); seed 2 is runs/pilot-v2-constco2-s2 (manifest corpus/pilot-v2-constco2-s2/runs.csv, same forcing files as seed 1, differing only in the random seed; the seed-2 logs print "Random seed: 2", both seeds stamped "5.6.004 (Aug 12 2026)"), 6,000 of 6,000 runs carrying the "lpjml successfully terminated" line, its states read with the corpus decoder by `scripts/exp_read_replicate_states.py` (job 2281341). State from the end-of-spin-up restart. 200 of the 56,986 eligible cells, not the acceptance criterion's 54,020. Level quantities scored in units of their own band; the statistic is dimensionless.

## What this means

**Outcome (b): the emitted restart file is closer to the truth than the cell's unedited forest,
but not by the pre-registered margin.** Read back from the file the synthesiser writes (climate-only
map, predicted species mix, climate-derived type rule), each of the 5,800 perturbed pilot targets'
worst quantity sits a median **6.74** tolerances from the two-run truth; leaving the cell's own
control forest unchanged sits at **8.85**. That is a margin of **0.272** on the log scale against the
**0.34** the rule required (a bar of -1.840; the model is at -1.908). All six nulls returned their
values exactly and fell in the physically expected order.

**Where the remaining gap sits.** Fed each target's own true state, the synthesiser alone reaches
-1.312 (median 3.7 tolerances; reported, never decided on); one real run against the two-run mean
reaches -0.190 (1.2 tolerances). So the map's prediction costs about 0.6 and the synthesis about 1.1
on this scale. Fully inside the band on all 19 at once: 5.3 % of targets (control forest 5.5 %, one
real run 37.5 %).

⚠ 200 pilot cells, year 0 read from the file, no scenario leg; not the all-cell criterion.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | worst_quantity_skill | vs best null | pre-registered null return |
|---|---|---|---|
| model | -1.9076 | 0.2724 | — |
| same_cell_template | -2.18 | — | -2.18 +/- 0.001 [OK] |
| nearest_analogue_any_climate | -2.34807 | — | -2.34807 +/- 0.001 [OK] |
| nearest_analogue_same_point | -2.48255 | — | -2.48255 +/- 0.001 [OK] |
| geographic_address | -2.5202 | — | -2.5202 +/- 0.001 [OK] |
| climatological_mean | -3.07948 | — | -3.07948 +/- 0.001 [OK] |
| shuffled_target | -3.51308 | — | -3.51308 +/- 0.001 [OK] |
| **DECISION** | pass_if > 0.34 | **FAIL** | 0.2724 |

- margin 0.2724 does not satisfy > 0.34
<!-- END GENERATED -->
