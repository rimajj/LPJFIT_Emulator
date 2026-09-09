### Line X — the emitted restart file now has competitors, and it loses to all of them

- **The synthesised restart file is beaten by chance.** It had only ever been scored against the
  truth (vegetation carbon off by 0.534). Given nulls, on 20 cells and all 22 scored quantities, the
  best synthesis version scores **0.702** where handing the model **a random neighbouring cell's real
  forest scores 0.786**. The nulls are all self-consistent forests; a file assembled from donors to
  match predicted height and wood-density quantiles matches those marginals and inherits everything
  else from whichever donor was picked. Matching marginals does not make a forest.
- **The later synthesis versions are a real gain, and the first version's one-year collapse is
  fixed.** 0.582 → 0.702 from line T's widened donor pool. `synth-v0` had been dynamically rejected —
  it shed 2.5 MB of stems in a single year and its biomass, leaf area index and stem count all fell
  to a 0.00 pass rate; the later versions track the control.
- **Running the real model forward is a no-op, not a repair.** +0.016 and −0.005 for the two working
  versions, with the sign flipping between the two acceptance bands. That kills the "short polish
  run" fallback as a repair mechanism — the lever belongs at year 0, in the synthesis.
- **`X4` is deliberately NOT sealed.** On this 20-cell contiguous block the conjunctive statistic is
  pinned at its 0.05 granularity floor for every arm, and all four nulls collapse into 0.786–0.845
  because the block is one neighbourhood. A test whose nulls cannot be told apart before it runs has
  no power, so sealing would pre-register a guaranteed `invalid`. What it needs first is written down.
- **t3 as worded in `PLAN.md` is unrunnable.** "20 years with no drift beyond the two-seed spread"
  fails on the REAL model in 71 % of cells, because a cell's interannual variability (median 16.5 %
  of its level) is larger than the band (median 10 %). The state's own drift is a median 1.75 % over
  20 years and is not the problem — the noise is. On a 20-year window mean a real restart passes in
  90.9 % of cells, and that, not 1.0, is the ceiling.
- Record: `docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`. Two
  corrections to `PLAN.md` and one new `MEMORY.md` row are requested there, both integrator-owned.
