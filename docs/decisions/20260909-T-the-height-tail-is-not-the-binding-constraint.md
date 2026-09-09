# The height tail is not the binding constraint; rooting depth and biomass are

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** T
- **Revises** the first consequence of `20260909-T-the-roster-was-truncated-at-both-tails.md`,
  which named "improve the level model's height-tail prediction" as the single next action. That
  record's own measurements are **not retracted** — every one of them is reproduced below. What
  changes is the priority they were read to imply, and the reason.
- **Basis for every number below:** the level model's own out-of-fold predictions over **56,950
  cells**, LPJmL-FIT historical leg, state at 1999, climate window 1970–1999, npatch=25, truth =
  mean of seeds 1+2, blocked spatial folds k=5 at 15°. Statistic: `band_frac_conjunctive` with
  tolerance `max(10 %, the two-seed relative spread)`. Level, not ratio.
- **Method:** `scripts/diag_level_binding.py`, read-only over the `oof_map.parquet` the level-map
  job already wrote. **Nothing was fitted and no new skill number was produced** — this decomposes
  an already-reported error. ⚠ Every oracle number has SEEN THE ANSWER for the quantity it
  substitutes; it bounds where effort can pay and is never emulator skill.

## The two objects being scored are different, and both earlier records were right

The superseded action came from the **synthesised restart** on 20 cells, where biomass was 23 %
off. This record is about the **level model's own 22 predictions** over all 56,950. They agree:
the level model's median biomass error is 18.7 % globally. Neither number is wrong; the question
is which lever moves the score.

## Four cheap fixes to the height tail, all measured and all rejected

| candidate | measurement | verdict |
|---|---|---|
| de-bias the tail | median predicted/true `height_p90` = **0.9991** | nothing to remove |
| undo shrinkage | log–log slope of truth on prediction = **0.993** (1.0 = none) | nothing to undo |
| restore the spread | one-parameter log-variance inflation, fitted per fold on the others: band pass **68.5 → 67.8 %** | **worse** |
| fuse with the biomass head | the two log errors correlate **+0.776**; optimal fusion cuts the height error by **0.5 %** | worthless |

The height-tail error is unbiased scatter. No transformation of the existing model's outputs
removes it, so "improve the height tail" can only mean a change of features or learner.

## And on the level score, perfecting it outright buys almost nothing

Leave-one-out oracle: replace one quantity by the truth, recompute the conjunctive score
(baseline **0.0361**; the geographic-address null is 0.0187).

| quantity | pass % | oracle gain | cells failing only this |
|---|---|---|---|
| **D95max_p10** (rooting depth, low tail) | 61.1 | **+0.0128** | 729 |
| **D95max_p50** | 56.4 | **+0.0097** | 555 |
| **agb** (above-ground biomass) | 41.2 | **+0.0097** | 552 |
| **soilc** (soil carbon) | 56.4 | **+0.0090** | 510 |
| D95max_p90 | 71.3 | +0.0048 | 273 |
| … | | | |
| **height_p90** | 68.5 | **+0.0006** | **37** |

Jointly: rooting depth's three quantiles **+0.0419**, the four stocks **+0.0441**, all three
height knots +0.0051. Rooting depth alone is worth **as much as every stock together, from three
quantities instead of four**, and 70× the height tail.

## Biomass IS the height tail, amplified — which is how both records reconcile

Regressing the log biomass error on the log height errors over all 56,950 cells:

    d log(agb) / d log(height_p90)  = +2.885        (p50: +0.175, stems: +0.799)

So 2.885 × the 6.3 % median `height_p90` error = **18.1 %**, against the 18.7 % median biomass
error actually observed. The amplification claim in the superseded record is confirmed and
quantified: the level model's biomass error is essentially its height-tail error carried through
the allometry. Two consequences, and the second is the useful one:

1. The direct biomass prediction carries **no independent information** — same error, amplified.
   That is why fusing the two heads is worthless, and why imposing the predicted biomass on the
   roster would not help.
2. **The height tail has a target now, and it is set by biomass, not by height.** For biomass to
   sit inside a 10 % band, `height_p90` must be within 10 % / 2.885 = **3.5 %**. It is at 6.3 %.
   Roughly halving it is the requirement; "improve it" was never a stopping condition.

## Which errors are reducible: split by whether LPJmL-FIT reproduces itself

The band is `max(10 %, two-seed spread)`, so the stored band recovers that spread wherever it
exceeds the floor — and only there. `e/tol` = median relative error / median tolerance.

| quantity | reproducible half (spread ≤ 10 %) | | noisy half | |
|---|---|---|---|---|
| | n | pass % · e/tol | n | pass % · e/tol |
| **agb** | 28,516 | **32.2 % · 1.77** | 28,434 | 50.2 % · 1.07 |
| **D95max_p10** | 26,559 | 46.0 % · **1.11** | 30,391 | 74.2 % · 0.58 |
| **D95max_p50** | 29,737 | 48.4 % · 1.05 | 27,213 | 65.2 % · 0.76 |
| lai | 40,882 | 49.1 % · 1.03 | 16,068 | 45.3 % · 1.42 |
| soilc | 55,418 | 56.4 % · 0.84 | 1,532 | 56.7 % · 0.96 |
| height_p90 | 48,054 | 66.9 % · **0.60** | 8,896 | 76.6 % · 0.52 |

**Biomass is the one large reducible error.** In the half of the world where the original model
gives nearly the same answer twice — so the signal is there — the emulator is 1.77× outside
tolerance and passes 32 %. Rooting depth is only marginally outside (1.11×), and it is the
noisiest quantity the original model has: 53 % of cells exceed the 10 % floor, median spread 22 %.
Height's median cell is comfortably inside its band at 0.60; its 31.5 % failure rate is the tail
of its error distribution, not its centre.

## Failure is a property of the CELL, not of the quantity

Conjunctive pass is **0.0361** against **0.0002** expected if the 22 failures were independent —
**151× clustering**. 3.6 % of cells fail nothing, **23.4 % fail only 1–3** (the reachable margin),
31.6 % fail nine or more. Among the near-miss cells the offenders are `agb` (26.6 %),
`D95max_p10` (25.5 %), `D95max_p50` (23.8 %), `soilc` (20.1 %); `height_p90` is not in the top ten.
By biomass decile, conjunctive pass is 0.2–0.8 % in the four lowest and 14.6 % in the highest, so
the failure lives in **low-biomass forest**, not in the tall stands the previous record fixed.

## Consequences

1. **The next action is rooting depth, not the height tail** — the largest oracle gain (+0.0419
   for its three quantiles), only marginally outside tolerance, and the one quantity the
   synthesiser also caps (0.146 under a perfect prediction). Both scored objects point at it.
2. **The height tail keeps its place, with a number instead of an adjective:** get `height_p90`
   under 3.5 % median error, because that is what puts biomass inside its band. Re-measure the
   elasticity after any change; do not assume 2.885 survives.
3. **Post-hoc repair of the height heads is closed** — four candidates measured, all rejected.
   Any further gain needs different features or a different learner, not a recalibration.
4. **Chase cells, not quantities, for the conjunctive score.** 151× clustering and a 23.4 %
   near-miss margin mean the score moves by fixing broadly-wrong low-biomass cells.
5. `k_root`'s three quantiles are exactly constant — zero error, zero two-seed spread, zero oracle
   gain. The conjunctive test is effectively over **19** quantities, not 22. Disclose it.
