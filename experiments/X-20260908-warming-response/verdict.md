# Verdict — X-20260908-warming-response
outcome: fail
**Question.** A model trained only on the historical leg is shown the same cell's climate twice -- 1970-1999, and 2071-2100 under the high-emissions scenario -- and asked for a state each time. Does the DIFFERENCE between its two answers explain more of the model's own simulated change than predicting no change at all, than giving every cell the average change, and than copying the change of the geographically nearest cell?
If it cannot, there is no learnable warming response and the project stops. That is the whole point of putting this rung this early.

**Estimand.** `skill_response_mean` — For each of seven quantities -- stems per patch, above-ground biomass, leaf area index, soil carbon, and the medians of stem height, wood density and specific leaf area -- compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) over the scored held-out cells, where dtrue = truth(ssp370, 2100) - truth(historical, 1999) and both truths are the MEAN of that leg's two seeds. The statistic is the unweighted mean of the seven. Denominator SUM(dtrue^2), not the variance of dtrue: that pins the decisive null analytically at exactly 0.0 -- predicting no change scores zero by construction, a perfect prediction scores 1, and a prediction uncorrelated with the truth scores about -1. Unweighted so no single quantity's variance dominates. A conjunctive band test is deliberately NOT used here: a relative band around a change that is near zero is itself near zero, so the acceptance band is the right test for a LEVEL and the wrong test for a CHANGE.

**Reference basis.** LPJmL-FIT 5.6.004. Base = restart_1999.lpj of the historical leg (spin-up plus the 1901-1999 transient); future = restart_2100.lpj of the ssp370 leg. Both seed 1 and seed 2, both legs produced by the SAME 2026-02-05 binary build, so this pair is build-matched -- which is why ssp370 and not ssp126 is the primary leg here. npatch=25, tree PFTs only, climate windows 1970-1999 and 2071-2100, 56,950 cells tree-bearing in BOTH legs and BOTH seeds. Constant CO2 throughout, by design. Dimensionless; a ratio of sums of squares, i.e. a ratio not a level.

## What this means

**The emulator's answer to "how does this forest change when the climate warms" is worse than
answering "it does not change".** It scored −0.727 where predicting no change scores exactly 0.000
and giving every cell the world-average change scores +0.016. This is a clean failure, not a broken
measurement: all four comparison arms returned precisely the values written down before the run.

**The failure is arithmetic, and it is diagnosed.** The emulator predicts a forest, not a change;
the change is obtained by asking it twice and subtracting. Subtracting two predictions does not
cancel their error — it roughly doubles it — so this only works where the real change is large
compared with how far off the emulator is in the first place. Stem count clears that bar and
carries real skill (+0.35); leaf area partly does (+0.10). Soil carbon does not: the model's own
simulated change in it is 3.5 % of its level, far smaller than the emulator's error, and there
subtraction returns −4.02. The unweighted average of the seven is what was pre-registered, so that
is the number reported.

**What is still unknown, and it is the important part.** This does NOT show that a data-driven
emulator cannot capture a warming response. It shows that one trained on **a single climate per
location** cannot — which is the identification limit, measured here for the first time on the
actual target rather than argued from feature importances. In the training data, climate and place
are inseparable, so the emulator learned where forests are, not how they move. Whether the response
is learnable at all is answered by data that does not exist yet: the same cells spun up under many
different climates, so the training target can be the change itself.

**One caveat that is not a footnote.** The pre-declared 5°-block sensitivity arm shows that the
"copy the nearest cell" comparison flips from −0.142 to +0.120 when the held-out blocks are made
smaller, because the nearest available neighbour is then closer. At that radius this experiment
would have measured spatial interpolation. The 15° result is the one that means anything.

Full reasoning: `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.

## Correction appended 2026-09-14 — the declared truth was one realisation, not a two-seed mean

The configured high-emissions second seed was a **bit-identical clone of the first** (fixed on `main`
2026-09-14; `ground_truth.ssp370_seed2` now resolves to the genuine run). Of line X's sealed set,
**this experiment is the only one the correction reaches** — X3 declares the leg unused in any arm,
and the pilot uses its own runs.

**What is wrong as stated.** The reference basis says the truth is "the MEAN of that leg's two
seeds". It was the mean of one seed with itself, i.e. a single realisation, so the scored change
carries a single draw's noise rather than the lower noise of an average. The cell-eligibility
condition "tree-bearing in BOTH legs and BOTH seeds" was likewise weaker than written.

**What is not wrong.** All arms share that same truth, so the comparison is internally consistent,
and every null returned its pre-registered value. The outcome does not turn on this: −0.727 against
a null pinned analytically at 0.000 is not a margin that a noise-level change in the target could
close, and the diagnosis — the change is a difference of two predictions, so their errors add
instead of cancelling — is independent of how the target was averaged. **The `fail` stands.**

⚠ **But the reason this leg was chosen does not survive the fix.** The basis names build-matching as
why the high-emissions leg and not the low-emissions one is primary here: both seeds from the same
2026-02-05 build. That held only because seed 2 was a copy of seed 1. The genuine seed 2 was written
by the 2026-07-21 build, so a re-run on the corrected pair **straddles a build boundary** and loses
the single property that motivated the choice. Anyone re-running this must either re-derive the
justification or pick the other leg — it is not a drop-in repoint. This is not re-sealed and not
re-scored; the result stands as measured, with its basis corrected.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | skill_response_mean | vs best null | pre-registered null return |
|---|---|---|---|
| model | -0.727071 | -0.743286 | — |
| no_response | 0 | — | 0 +/- 1e-06 [OK] |
| mean_response | 0.016215 | — | 0.016215 +/- 0.002 [OK] |
| geographic_address_response | -0.142351 | — | -0.142351 +/- 0.02 [OK] |
| shuffled_response | -0.91287 | — | -0.91287 +/- 0.2 [OK] |
| **DECISION** | pass_if > 0.05 | **FAIL** | -0.743286 |

- margin -0.743286 does not satisfy > 0.05
<!-- END GENERATED -->
