# The synthesised state survives twenty years, and fails the drift test below the no-change null

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** T
- **Extends** `20260909-T-the-roster-was-valid-but-not-viable.md`, whose closing line said t3 was
  now worth running. It was. Nothing in that record is retracted.
- **Basis for every number below:** cells 42480–42499, 20 of 54,020, one region (temperate Europe),
  present-day climate, historical leg, years 2000–2019, one task per arm, 25 patches. Two control
  seeds supply the tolerance and a third supplies the ceiling. **This is not the acceptance test.**

## What was run

Four twenty-year runs of the real model over the same block, differing only in where they start and
in the random number stream:

| arm | starts from | seed | campaign |
|---|---|---|---|
| emulated | the emulator's restart file (`64fdbf2d…`) | the template's own | `T-cmodel-t3-emulated` |
| control | the true `restart_1999.lpj` | the file's own | `T-cmodel-t3-control` |
| control seed 2 | the same true file | `random_seed=2` | `T-cmodel-t3-control-s2` |
| **ceiling** | the same true file | `random_seed=3` | `T-cmodel-t3-ceiling` |

All four printed the model's own `lpjml successfully terminated, 20 grid cells processed.` The
tolerance is `max(10 %, |seed1−seed2|/mean)` per cell per quantity, measured on **this** block over
**these** years — the published noise figure is an end-of-spin-up global one and does not transfer.
The emulated arm shares control seed 1's random stream (the synthesiser copies the target cell's own
template record and never touches its seed bytes), so none of its gap can be excused as noise.

## The ceiling arm is why this record exists, and it was nearly not run

A band leg sits inside its own band by construction, so the 100 % the two control seeds score is
arithmetic, not attainment — the point line X had just merged as `acceptance_band_transferred`,
having measured a single realisation at 1.000 against its own band and 0.538 against a transferred
one. Without a third seed, "the emulated arm gets 0 of 20" is a number with no scale. **A third run
of the real model — same physics, new stream, nothing emulated — gets 25 % of cells and a median of
21 of 22.** That is the most any emulator could score here. It cost two minutes on one core.

## The result

| arm | inside the band on all 22 | median quantities hit | median over the 22 of the per-cell gap |
|---|---|---|---|
| emulated | **0 of 20 (0 %)** | **16 / 22** | 0.076 |
| **ceiling** — a third real run | **5 of 20 (25 %)** | **21 / 22** | 0.035 |
| null — "twenty years change nothing" | 0 of 20 (0 %) | 18 / 22 | — |
| the two band legs | 20 of 20 (100 %) | 22 / 22 | — (arithmetic) |

**The test has power**: the real model's own third run reaches 25 % and 21 of 22 where handing the
model back the true 1999 state reaches 0 % and 18 of 22. So this is a fail, not an `invalid`.

**And the emulated state fails below the null.** Its median 16 of 22 is worse than the 18 that the
*initial condition itself* scores. On 14 of the 22 quantities the true 1999 state is closer to the
year-2019 control than the emulated arm is, and per cell the emulated arm matches or beats the null
in only 10 of 20 cells and the ceiling in 1 of 20. Twenty years in, the emulated state is a worse
description of the control than the state the emulator was built to replace.

## What survived, stated as plainly as the failure

The state **does not collapse and does not run away**, which is the question t3 existed to ask and
which a state that died in year one could not have answered. Vegetation carbon over the block grows
×1.34 against the control's ×1.21, the two other seeds ×1.20 and ×1.22, and the block total closes
from **−10.6 % at 2000 to −1.3 % at 2019**.

⚠ **That −1.3 % is not the emulator improving.** Over the same twenty years the per-cell median
*absolute* gap in vegetation carbon **grew, from 0.087 to 0.140**, against the two controls' own
0.010 → 0.097. The block total converges because per-cell errors of opposite sign cancel in a sum.
Quote the per-cell number, never the total, and never the total alone.

The per-cell gap is the same order as the model's own noise from about year six (ratio 8.6× at 2000,
below 1 between 2009 and 2013, 1.4× at 2019) but exceeds it on **17 of the 22** quantities. Three
`k_root` quantiles are identical in every arm and contribute nothing, as already disclosed.

## Where the shortfall is, and it is exactly where the mechanism predicts

Ceiling minus emulated pass rate, worst first — a large gap here is a quantity a real run gets right
and the emulated state does not:

| quantity | a real run | emulated | the no-change null |
|---|---|---|---|
| leaf area | 90 % | **15 %** | 20 % |
| rooting depth, low tail | 90 % | 35 % | 100 % |
| stems per patch | 70 % | 25 % | 10 % |
| height median | 95 % | 50 % | 80 % |
| height upper tail | 90 % | 50 % | **5 %** |
| rooting depth median | 85 % | 50 % | 85 % |
| wood density median | 100 % | 70 % | 100 % |
| longevity median | 100 % | 75 % | 100 % |

Every row is a quantity the donor transplant does not control: it matches two traits (height and
wood density) at matching size rank and copies tree type from the template, so trait medians and
leaf area are precisely what it cannot set. Leaf area is the worst and was already known to be a
per-stem **mass** the transplant never targets. The two rows where the emulator beats the null —
stems per patch and the height upper tail — are the two the emulator actually predicts, and the
height upper tail is where the null is worst of all (5 %), because a forest's tallest trees are what
twenty years genuinely changes.

## What this says about the acceptance test itself, which line T does not own

**The conjunctive-on-22 test at year 20 is about 25 % attainable by the real model on this block.**
A two-sample spread underestimates dispersion, and a 22-way conjunction compounds it: the third run
typically misses one of the 22. Any future statement of the form "N % of cells pass" needs the
ceiling beside it or it overstates the shortfall — 0 % against an attainable 25 %, and 16 of 22
against an attainable 21, is a different claim from 0 % against 100 %. Relayed to line X, which owns
the pre-registrations and the band.

## What follows

1. The transplant needs a **cell-total mass constraint** (leaf area, then above-ground mass), not
   more matched traits — five traits was measured and rejected on 2026-09-08.
2. Trait medians need the **predicted** distribution imposed on the roster, not inherited from
   whichever donors were near in two dimensions.
3. **Do not quote t3 as a pass on carbon.** Carbon passes at year one (0.091) and is 0.140 at year
   twenty, above the model's own 0.097.
4. Every number here is 20 cells of 54,020 in one region under one climate. The acceptance criterion
   is all cells, both scenarios, and the response between them.
