# The roster was truncated at both tails, and the missing tall trees were the whole leaf-area loss

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** T
- **Extends** `20260909-T-t3-drift-fails-below-the-null.md`, which named leaf area as the largest
  single loss and proposed a cell-total leaf-mass constraint as the fix. **That mechanism is
  rejected here, on measurement.** Nothing else in that record is retracted.
- **Basis for every number below:** cells 42480–42499, 20 of 54,020, temperate Europe, present-day
  climate, historical leg, 2000–2019, one task per arm, 25 patches. Same band
  (`max(10 %, |seed1−seed2|/mean)`) and same ceiling seed as before; only the emulated arm was
  re-run. **This is not the acceptance test.**

## The proposed fix was aimed at the wrong field

Leaf carbon is not a free per-stem mass: `tree/allometry_tree.c:39-41` **derives height from it**,
`height = k_latosa * sapwood_carbon / (leaf_carbon * sla * wooddens)`. Multiplying leaf carbon by
the 1.41 the prediction asked for would have divided every tree's height by 1.41 at the first
allocation. Height, wood density and specific leaf area are all scored, so the only field free to
move with leaf carbon is sapwood, and half the stems held too little heartwood to pay for that.

## The leaf was missing because the tall trees were missing entirely

Leaf carbon by height class, against the true 1999 state:

| height class | stems, true | stems, synthesised | share of the leaf gap |
|---|---|---|---|
| **16–20 m** | **308** | **0** | **83 %** |
| **20–25 m** | **72** | **0** | **26 %** |

The tallest synthesised stem in the whole block was 13.31 m; the truth reaches 25.75 m. Those two
empty classes are 109 % of the shortfall — leaf area was the symptom, not the defect. And it was a
**targeting** failure: the donor pool held 794 admissible stems above 16 m reaching 30.34 m, and
the predicted `height_p90` was good to 7 %. Nothing ever asked for a tall tree.

## Two causes, and no summary number the synthesiser printed could see either

**The ranks were drawn per patch.** The predicted quantiles are CELL quantiles —
`corpus/state.py` pools all 25 patches before taking a percentile — but the roster was built inside
each patch from `u = (arange(n) + 0.5) / n` with n ≈ 19. Every patch got the same nineteen ranks,
spanning 0.026 to 0.974; the cell got twenty-five copies of one truncated ladder. A stand's tallest
tree lives near rank 0.998, so it was unaddressable in every cell, however good the prediction.

**The tail was a straight line.** Cell-level ranks alone are not enough: continuing the p50→p90
slope reaches 14.3 m at rank 0.999, still 9 m short. A forest's height distribution is strongly
right-skewed and three knots joined by straight lines cannot make one. The old file hit
`stems_per_patch` to 0.2 %, `height_p50` to 0.3 % and reported a median pool shortfall of
0.02 % while holding no tree above 13.31 m. **Everything it printed was a mean.**

## What was changed, in `src/vegemu/models/synth.py`

* Ranks are drawn once across the cell and dealt to patches at random, so each patch is a random
  SAMPLE of the stand rather than a copy of it.
* The distributional SHAPE comes from the template cell's own stems, recalibrated onto the three
  predicted knots (`recalibrate`); only location and spread are the emulator's. This extends the
  mechanism `type_ladder` already used for tree type to the matched traits — one real stem per
  rank, read whole, so the template's joint height–density structure survives.
* Outside the outer knots the map is **multiplicative, not extrapolated**. Measured: continuing the
  interior slope amplified the level model's 5 % error at the 90th percentile into 13 % at the
  99.9th and put biomass 21 % over the truth. Anchoring caps the distortion at the prediction's own
  error and is the identity when the prediction is right; it alone moved the year-0 biomass error
  0.320 → 0.233.

## The result at twenty years, and it is still a fail

| | before | after | ceiling | null |
|---|---|---|---|---|
| cells inside the band on all 22 | 0 % | **5 %** | 25 % | 0 % |
| median quantities hit | 16/22 | **18/22** | 21/22 | 18/22 |
| leaf area | 15 % | **85 %** | 90 % | 20 % |
| above-ground biomass | 55 % | **75 %** | 75 % | 30 % |
| vegetation carbon | 60 % | 85 % | 75 % | 30 % |
| height median / upper tail | 50 / 50 % | 75 / 70 % | 95 / 90 % | 80 / 5 % |
| wood density median | 70 % | 95 % | 100 % | 100 % |
| stems per patch | 25 % | 50 % | 70 % | 10 % |
| rooting depth, low tail | 35 % | 40 % | 90 % | 100 % |
| soil carbon | 80 % | 70 % | 100 % | 100 % |

5 % is **one cell of twenty** against an attainable 25 %, and the median of 18 of 22 exactly ties
the "twenty years change nothing" null — which still beats the emulator on rooting-depth low tail
and on soil carbon. What changed is that the emulator now decisively beats that null on the stocks,
where before it lost to it on 14 of the 22. A different and better failure.

**The drift also reverses direction.** The per-cell median vegetation-carbon gap used to GROW over
the twenty years, 0.087 → 0.140, against the two controls' own 0.010 → 0.097. It now SHRINKS,
0.189 → 0.078, ending **inside** the controls' own spread. The state starts further off in carbon
than before — the level model's height-tail error is now carried faithfully into mass — and the
model pulls it back instead of pushing it away. Block-total carbon is −1.6 % at 2019; as before,
**never quote that alone**, it hides opposite-sign per-cell errors.

## The residual is now the LEVEL MODEL's, not the synthesiser's

Feed the synthesiser the TRUE cell quantiles. Median relative error per cell against the truth:

| quantity | predicted quantiles | true quantiles |
|---|---|---|
| above-ground biomass | 0.233 | **0.004** |
| height, median / upper tail | 0.059 / 0.070 | 0.002 / 0.002 |
| stems per patch | 0.083 | 0.003 |
| leaf area / vegetation carbon | 0.088 / 0.219 | 0.021 / 0.029 |
| rooting depth, median / low tail | 0.119 / 0.177 | 0.127 / 0.146 |

Given a perfect summary of a cell, the synthesiser rebuilds that cell to within half a percent on
biomass. **The mechanism is no longer the binding constraint.** The exceptions are exactly the
traits the transplant does not match — rooting depth above all — which arrive attached to whichever
donor was chosen. ⚠ The oracle arm has seen the answer: it bounds the synthesiser and can never be
quoted as emulator skill.

## Consequences

1. **The next lever is the level model, not the synthesiser** — a 5 % error in predicted
   90th-percentile height becomes a 23 % error in biomass.
2. **Impose rooting depth, or accept 40 % on its low tail** — the one scored quantity the
   synthesiser itself caps, against 90 % attainable. Widening `MATCH_TRAITS` blindly stays refused
   (measured: 11 of 22 worse), but rooting depth is derived from height inside the model.
3. **Never judge a roster by medians.** `SynthReport` now carries the 90th-percentile shortfall
   per matched trait, the tallest stem placed, and the tallest the template holds.
4. Deliverable: `runs/synth-v5/restart/restart_1999_emulated.lpj`, sha256 `1e856119…`, superseding
   `synth-v2` (`64fdbf2d…`).
