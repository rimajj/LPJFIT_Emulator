### Line X — the emitted restart file now has competitors, and it loses to all of them

The synthesised restart file had been reported against the truth alone (vegetation carbon off by
0.534). It now has nulls. On 20 cells and all 22 scored quantities, the best synthesis version scores
**0.702** where handing the model **a random neighbouring cell's real forest scores 0.786** — the
file is still beaten by chance. The later synthesis versions are a genuine improvement (0.582 →
0.702) and the first version's one-year collapse is fixed, but running the real model forward for a
year neither repairs nor rejects the state: +0.016 and −0.005 for the two working versions, a sign
that flips between the two acceptance bands. That kills the "short polish run" fallback as a repair
mechanism — the lever belongs at year 0, in the synthesis.

**`X4` is deliberately NOT sealed.** On this 20-cell contiguous block the conjunctive statistic is
pinned at its 0.05 granularity floor for every arm, and all four nulls collapse into 0.786–0.845
because the block is one neighbourhood. A test whose nulls cannot be told apart before it runs has no
power, so sealing it would pre-register a guaranteed `invalid`. What X4 needs first is written down.

Also measured: **t3 as worded in `PLAN.md` is unrunnable.** "20 years with no drift beyond the
two-seed spread" fails on the real model in 71 % of cells, because a cell's interannual variability
(median 16.5 % of its level) is larger than the band (median 10 %). The state's own drift is a median
1.75 % over 20 years and is not the problem — the noise is. On a 20-year window mean a real restart
passes in 90.9 % of cells, and that, not 1.0, is the ceiling.

Record: `docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`.
Two corrections to `PLAN.md` and one new `MEMORY.md` row are requested there, both integrator-owned.
