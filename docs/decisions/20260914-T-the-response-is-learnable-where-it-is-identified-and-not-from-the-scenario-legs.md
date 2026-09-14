# The warming response is learnable where it is identified, and not from the scenario legs

- **Date:** 2026-09-14
- **Line:** T
- **Status:** accepted
- **Experiments:** `X-20260909-pilot-warming-response`, `X-20260908-heldout-forcing-leg`

## What was decided

Both model arms this line had owed for five sessions were run. They disagree, and the disagreement
is the finding: **a cell-specific climate response is strongly learnable on the designed
perturbation ensemble, and is not learnable at all from the scenario legs, where the map is worse
than doing nothing.** Response work moves onto the perturbation ensemble. The scenario-leg map must
not be used to quote a warmed climate.

## The numbers, with their nulls and their ceilings

**The kill test on the pilot corpus — PASS, decisively.** 200 cells x 29 perturbed climates, paired
within cell, 15-degree blocking, out of fold.

| arm | `skill_response_mean` |
|---|---|
| **model** | **0.545304** |
| best null (`proportional_median_response`) | 0.145690 |
| `level_mean_response` | 0.095610 |
| `no_response` (analytic) | 0.000000 |
| `nearest_analogue_response` | -0.239753 |
| `nearest_cell_response` | -0.281166 |
| `shuffled_cells` | -0.797389 |
| *ceiling (independent-noise)* | *0.869730* |

Margin over the best null 0.399614 against a pre-registered bar of 0.080; the model needed 0.225690
and reached 0.545304. That is **62.7 % of the attainable ceiling, not of 1.0**. It beats the best
null at **all 29 levels** — the pre-registration required this to be checked, because the response
is not monotone in temperature and a pooled score is exactly the summary that would hide it. Stable
under the 5-degree sensitivity blocking (0.552327). Every null reproduced its sealed value exactly.

**The held-out forcing leg — FAIL, and the worst of the three pre-named kinds.** 56,950 cells, band
transferred from the historical leg, 15-degree blocking.

| arm | `band_frac_conjunctive` |
|---|---|
| best null (`same_cell_persistence`) | 0.033749 |
| **model** | **0.005443** |
| `geographic_address` | 0.005426 |
| `nearest_analogue` | 0.004688 |
| `shuffled_target` | 0.000632 |
| `climatological_mean` | 0.000000 |
| *ceiling (one real realisation)* | *0.538490* |

Margin **-0.028306** against a bar of +0.050. This is pre-named outcome **(c): the model scores
below persistence and is actively harmed by a climate it has not seen.** It is barely
distinguishable from copying the nearest cell's present-day forest. Same conclusion at 5 degrees
(0.006040) and under the same-leg sensitivity band (0.005198).

## Why the pass is believed: three arms that tried to break it

| arm | pooled | reading |
|---|---|---|
| full model | 0.545304 | — |
| **blind** (no forcing features at all) | **0.349462** | most of the score does not need the forcing |
| **scrambled** (forcing re-paired per cell) | **0.308049** | wrong forcing is worse than none |
| model on surviving pairs only | 0.549371 | collapse is not what is being scored |

**THE DISCLOSURE THAT MUST TRAVEL WITH THE 0.545.** A model that cannot tell which of the 29
perturbations it is being asked about still scores 0.349462 — **64 % of the headline, and itself
above the pre-registered bar of 0.225690.** That part is not response skill; it is predicting how
much a given cell's forest moves at all, from its control state and baseline climate. **The
forcing-attributable share is 0.545304 - 0.349462 = +0.195842.** Never quote the 0.545 as "the
emulator predicts the warming response" without it.

Forest collapse is not driving the number: 363 of 5,800 pairs (6.26 %) go treeless, they carry
0.0001 of the squared change in above-ground biomass and 0.0455 in stem count, and the score on
surviving pairs alone is 0.549371 — slightly *higher* than the full set.

## Why the two results do not contradict each other

They are the same fact measured twice. The pilot corpus spins the **same cell** up under 30
climates with one config, one forcing window and one seed, so the only difference between an arm
and its control is the climate and the response is identified **by construction**. The scenario legs
hold **exactly one climate per place**, so climate and geography are collinear and no warming
response is separately identified — which is what `X-20260908-warming-response` already diagnosed
and what this now confirms from the other direction: given an unseen forcing, the scenario-fitted
map does not merely fail to respond, it moves cells the wrong way and lands below persistence.

**The apparatus is validated rather than asserted.** The same run scored the map on the leg it was
fitted on and got **0.036067**, reproducing the recorded 0.0361 of `X-20260908-climate-state-map`.
The pipeline is therefore reproducing a known number on a known arm and disagreeing only where the
question changes.

## Consequences

1. **Response work moves to the perturbation ensemble.** It is the only data in this project where
   the question is answerable, and the answer there is positive.
2. **No warmed climate may be quoted from the scenario-leg map.** Below persistence is not a weak
   result, it is a wrong one.
3. **The next thing to measure is the forcing-attributable share, not the headline.** +0.195842 is
   the number that represents learned response, and it is what any improvement must move.
4. **Predicting species composition is now in scope** (owner, 2026-09-14) and the pilot corpus
   already carries `pft_frac_*` per cell and climate, so composition response can be measured on
   the ensemble without waiting for corpus v2.
5. Passing this kill test **licenses nothing about fidelity**. It is 200 cells, one seed, a
   protocol-defined 1000-year spin-up that is not converged, and a 7-quantity variance-explained
   statistic — not the 22-quantity conjunctive band over 54,020 cells that the acceptance criterion
   demands.

## What was NOT done

- The pilot corpus has **one seed per run**, so there is no two-seed spread on it and its ceiling is
  a modelled one (independent noise), not a measured realisation.
- The 0.869730 ceiling assumes independent realisation noise; the partially-correlated variant is
  0.934865 and both are in `X-pilot-ceiling-verify/ceiling_pilot.json`.
- Rooting-depth recipes stayed **off**, so both arms are the shipped model and their numbers mean
  what the other reported numbers mean.
