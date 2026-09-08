# Verdict — X-20260908-warming-response
outcome: fail
**Question.** A model trained only on the historical leg is shown the same cell's climate twice -- 1970-1999, and 2071-2100 under the high-emissions scenario -- and asked for a state each time. Does the DIFFERENCE between its two answers explain more of the model's own simulated change than predicting no change at all, than giving every cell the average change, and than copying the change of the geographically nearest cell?
If it cannot, there is no learnable warming response and the project stops. That is the whole point of putting this rung this early.

**Estimand.** `skill_response_mean` — For each of seven quantities -- stems per patch, above-ground biomass, leaf area index, soil carbon, and the medians of stem height, wood density and specific leaf area -- compute 1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2) over the scored held-out cells, where dtrue = truth(ssp370, 2100) - truth(historical, 1999) and both truths are the MEAN of that leg's two seeds. The statistic is the unweighted mean of the seven. Denominator SUM(dtrue^2), not the variance of dtrue: that pins the decisive null analytically at exactly 0.0 -- predicting no change scores zero by construction, a perfect prediction scores 1, and a prediction uncorrelated with the truth scores about -1. Unweighted so no single quantity's variance dominates. A conjunctive band test is deliberately NOT used here: a relative band around a change that is near zero is itself near zero, so the acceptance band is the right test for a LEVEL and the wrong test for a CHANGE.

**Reference basis.** LPJmL-FIT 5.6.004. Base = restart_1999.lpj of the historical leg (spin-up plus the 1901-1999 transient); future = restart_2100.lpj of the ssp370 leg. Both seed 1 and seed 2, both legs produced by the SAME 2026-02-05 binary build, so this pair is build-matched -- which is why ssp370 and not ssp126 is the primary leg here. npatch=25, tree PFTs only, climate windows 1970-1999 and 2071-2100, 56,950 cells tree-bearing in BOTH legs and BOTH seeds. Constant CO2 throughout, by design. Dimensionless; a ratio of sums of squares, i.e. a ratio not a level.

## What this means

<!-- Two or three sentences in plain language. State what was measured, against what, and what is
     still unknown. If the outcome is `invalid`, say plainly which null misbehaved and why that
     voids the comparison rather than merely weakening it. -->

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
