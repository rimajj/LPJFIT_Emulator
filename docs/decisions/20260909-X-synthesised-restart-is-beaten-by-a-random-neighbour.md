# A synthesised restart is still beaten by a random neighbouring cell, and t3 as worded cannot be run

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** X
- **Governs:** rung 3 / t3 of the restart-synthesis validation ladder; the "short polish run"
  fallback in `PLAN.md`; the not-yet-sealed `X4` pre-registration
- **Derivation:** `scripts/exp_derive_nulls_restart.py`, campaign `X-derive-restart-v2`,
  `/p/tmp/jamirp/vegemu/exp/derive-restart-v2/derived_nulls_restart.json`
- **Qualifies, does not overturn:** `20260908-T-restart-loads-but-carbon-is-halved.md`. Its t0/t1/t2
  passes stand and so does its 0.534. This record adds the competitor that number was missing.

## What was measured, and from what

Nothing new was run in the model. Three one-year t2 runs already on scratch — one per synthesis
version — each wrote the state before and after a year of the real C model, and the corpus state
aggregator reads all of them with the code that built the corpus. So each synthesised state is
comparable to the real one at year 0 and year 1, on all 22 scored quantities, over the same 20 cells
(42480–42499), using the map experiment's own metric. Truth is the **control arm**: the byte-exact
real 1999 restart for those cells, run forward under the same config. The band is transferred from
the ssp126 leg's two genuine seeds rather than the historical leg's, because the control descends
from the historical seed-1 lineage and a tolerance from that leg would be circular in the way
`20260908-X-ssp370-has-no-second-seed.md` describes. Both bands are reported; where they disagree,
that is stated rather than resolved in our favour.

⚠ **`synth-v1` and `synth-v2or3` are UNCOMMITTED line-T work** — real measurements of real files,
but the code behind them is not in the history, so they are a moving target, not a baseline.

## Finding 1 — every null still beats the emitted file, including chance

Mean per-quantity pass rate, 20 cells × 22 quantities, transferred band:

| arm | score |
|---|---|
| ceiling: one real realisation against the two-seed mean | 0.970 |
| the average forest over the block | 0.845 |
| geographically nearest other cell's real forest | 0.823 |
| climatically nearest analogue's real forest | 0.814 |
| **shuffled — a random other cell's real forest** | **0.786** |
| **best synthesis (`synth-v2or3`), year 0** | **0.702** |
| first synthesis (`synth-v0`), year 0 | 0.582 |

The widened donor pool of the later versions is a real gain — 0.582 → 0.702 — and it is line T's fix
working. **It is still below chance:** a random neighbouring cell's real forest scores 0.786.

The mechanism generalises, and is why this matters beyond the carbon number: the nulls are all
**self-consistent forests**, whose stems have mass, crown, age and allometry that belong together, so
they land inside a 10 % band on most quantities. A file assembled from donors to match predicted
height and wood-density quantiles matches those marginals and inherits everything else from whichever
donor was picked. **Matching marginals does not make a forest.**

## Finding 2 — the one-year collapse was real, was specific to the first version, and is fixed

`mean_per_quantity`, transferred band. "frozen" is the emitted state scored against the year-1 truth
*without* running it — the arm that says whether running the model forward helped:

| version | year 0 | year 1 | frozen | effect of running one year |
|---|---|---|---|---|
| `synth-v0` | 0.582 | 0.455 | 0.589 | **−0.134 — moved sharply AWAY** |
| `synth-v1` | 0.589 | 0.591 | 0.575 | +0.016 |
| `synth-v2or3` | 0.702 | 0.693 | 0.698 | −0.005 |

`synth-v0` was being dynamically rejected: its year-1 restart is 45.3 MB against the control's
47.9 MB, so the model culled the transplanted trees, and above-ground biomass, leaf area index and
stems per patch all fell to a 0.00 pass rate in a single year. **That is fixed** — `synth-v1`'s
year-1 file is 47.8 MB and `synth-v2or3`'s grows to 48.1 MB, both in line with the control.

For the two fixed versions the effect of running a year is **indistinguishable from zero**: +0.016
and −0.005, and for `synth-v2or3` the sign flips between the two bands (−0.005 transferred, +0.007
same-leg), which is the definition of a null result. The corrected statement is not that the model
wrecks the state — it no longer does — but that **it neither repairs nor rejects it. It carries it.**
That still kills the **"short polish run" fallback** (`PLAN.md`: write an approximate restart, let
the C relax it for N years), for the opposite reason `synth-v0` alone would have suggested: at N = 1
it is a no-op, not a repair. The lever has to be applied at year 0, in the synthesis.

## Finding 3 — t3 as worded in `PLAN.md` is not a test, twice over

**The wording.** The ladder says "20 years with no drift beyond the two-seed spread". Applied to the
real model that criterion fails in 71 % of cells: over the 61,700 vegetated cells of corpus v0 the
interannual variability of a cell's own annual series is a median 16.5 % of its level while the band
is a median 10.0 %, so a single year sampled at the end differs from the start by more than the band
almost everywhere. The drift of the state — the residual spin-up trend, +6.8 %/century median —
contributes a median 1.75 % over 20 years and is not the problem. **The noise is.** Scored on a
20-year *window mean*, where the noise falls by √20, a real restart passes in 90.9 % of cells. So the
estimand must be a window mean and the reference arm is **0.909, not 1.0**.

**The cell set.** The conjunctive statistic — the acceptance-grade one — is pinned at the
1/20 = 0.05 granularity floor for *every* arm on this block: 0.10 for the best null, 0.05 for three
others, 0.00 for all three synthesis versions. Worse, the block is 20 contiguous half-degree cells,
i.e. one neighbourhood, so all four nulls collapse into 0.786–0.845 and cannot be told apart. **A
test whose nulls are indistinguishable before it runs has no power**, which by invariant 3 makes its
verdict `invalid` by construction. That is why **X4 is not sealed in this session**: sealing it would
pre-register a guaranteed non-result.

**X4 therefore needs three things first:** a spatially dispersed cell set spanning enough independent
15° tiles that the nulls separate (a requirement on line T's synthesis, today 20 adjacent cells); a
window-mean estimand with the reference arm declared at 0.909; and the year-by-year trajectory rather
than the endpoint, since whether finding 2's null result holds over decades — slow relaxation and
transient overshoot both being invisible after one step — is the only question a 20-year run answers.

## Consequences

1. **Line T — the donor-pool widening works; keep going, and measure against the nulls.** 0.582 →
   0.702 is real progress, but the bar is not zero error, it is **0.786**. Re-running this derivation
   costs two seconds (`scripts/exp_derive_nulls_restart.py`; add the run directory to `VARIANTS`), so
   every synthesis iteration can be scored against its nulls instead of against nothing.
2. **Line T — commit `synth-v1`/`v2`/`v3`.** Two of the three numbers here describe code that exists
   only as scratch output, which is the provenance gap the corpus build gate exists to prevent.
3. **Integrator — `PLAN.md` needs two corrections**, requested rather than made because it is
   integrator-owned. The t3 rung should read *"20 years with no drift beyond the two-seed spread,
   scored on a window mean; a real restart itself passes in only 90.9 % of cells, and that is the
   ceiling"*. The "short polish run" paragraph should carry *"measured at N = 1: a no-op (+0.016 and
   −0.005 for the two working synthesis versions), so the lever belongs at year 0"*.
4. **`MEMORY.md` — a new integrator row is requested.** Wording: *"a synthesised restart is still
   beaten by a random neighbouring cell's real forest (0.702 vs 0.786, 20 cells, 22 quantities);
   matching marginals does not make a self-consistent forest, and running the model forward neither
   repairs nor rejects it."*
5. **Basis, travelling with every number: 20 of 54,020 cells, one 15° tile, one year of model time,
   two of three synthesis versions uncommitted.** Not fidelity evidence, not an acceptance number —
   an engineering diagnosis, reported as one.
