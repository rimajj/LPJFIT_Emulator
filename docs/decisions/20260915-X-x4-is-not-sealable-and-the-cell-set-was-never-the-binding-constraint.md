# X4 still cannot be sealed, and the 20-cell neighbourhood was never the binding constraint

- **Status:** accepted
- **Date:** 2026-09-15
- **Line:** X
- **Governs:** the not-yet-sealed `X4` pre-registration (the emitted restart file); the restart
  deliverable's acceptance statistic; the priority of line D's second pilot seed
- **Derivation:** `scripts/exp_derive_nulls_restart_pilot.py`, campaigns `X-restart-pilot-nulls`
  (job 2201910) and `X-restart-pilot-nulls-sweep` (job 2201928),
  `/p/tmp/jamirp/vegemu/exp/X-restart-pilot-nulls-sweep/nulls_restart_pilot.json`
- **Qualifies, does not overturn:**
  `20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`. Every number in it stands.
  What changes is its diagnosis of *why* X4 could not be sealed.

## What that record predicted, and what actually happened

It named three things X4 needed first, the first being **a spatially dispersed cell set spanning
enough independent tiles that the nulls separate** — because on 20 contiguous cells the four nulls
collapsed into 0.786–0.845 and could not be told apart. The pilot corpus supplies exactly that:
**200 cells across 164 populated 15° tiles, 29 perturbed climates each, 5,800 scored targets**,
against 20 cells in one tile. So the derivation was re-run on it, with the same estimand (the
conjunctive band fraction over all 22 scored quantities), the same transferred band, and a null set
strengthened by two arms the 20-cell set could not hold.

**The nulls still cannot be told apart, and the reason is the opposite one.** There they were all
*high* and bunched. Here they are all *at the floor*:

| null, ssp126-transferred band, 15° blocking | conjunctive | mean per quantity |
|---|---|---|
| geographic address — nearest training cell | **0.004138** | 0.4209 |
| **shuffled — a random other cell's forest (chance)** | **0.004138** | 0.2738 |
| same-cell template — the cell's own present forest, unedited | 0.002586 | 0.4787 |
| nearest analogue, same design point | 0.001379 | 0.4392 |
| nearest analogue, any climate in the ensemble | 0.001207 | 0.4588 |
| climatological mean | 0.000000 | 0.3026 |
| *ceiling: one real realisation vs the two-seed mean* | *0.470* | *0.9552* |

Chance **ties for first**, the cell's own forest ranks *below* chance, and the smallest adjacent gap
is exactly 0.0. A statistic that ranks a random cell first has no power to rank a model, so sealing
this would pre-register a guaranteed `invalid` — the second time, on the cell set that was supposed
to be the fix.

## The cause is the band, and it is one unmade measurement

A floor sweep separates the two candidate explanations. The acceptance floor stays 10 %; the wider
floors are a diagnostic and are **not** acceptance numbers:

| band floor | best null | its value | ordering | ceiling |
|---|---|---|---|---|
| **0.10 (acceptance)** | geographic address | 0.0041 | **scrambled; chance tied first** | 0.470 |
| 0.15 | same-cell template | 0.0121 | correct | 0.705 |
| 0.20 | same-cell template | 0.0272 | correct | 0.845 |
| 0.29 | same-cell template | 0.0664 | correct | 0.895 |
| 0.50 | same-cell template | 0.1805 | correct | 0.965 |

From 0.15 upward the ranking snaps into the order physics predicts — *your own forest > the most
similar climate anywhere > the same climate elsewhere > the forest next door > the average forest >
a random forest* — and stays there at every wider floor. At 0.10 alone it is scrambled and pinned.
**So the collapse is a property of the tolerance, not of the cell set and not of the emitted file.**

The tolerance is `max(10 %, the model's own two-seed spread)`. On these 200 cells the transferred
spread **is** the bare floor: its median is exactly 0.100 and only **22.0 %** of cell-quantities
exceed it. And it is transferred from each cell's *present-day* climate, because **nobody has ever
run two seeds of a perturbed spin-up** — the spread of a forest driven to +6 K is unmeasured, and
the acceptance criterion itself puts it at up to 29 % in low-density cells, which is the middle of
the range where this test turns from powerless into usable.

## What this does and does not license

1. **X4 stays unsealed, and now has one named, datable blocker:** the model's own two-seed spread on
   a **perturbed** state. Line D's second seed for 20 pilot cells (~34 core-hours) is the only
   thing that measures it. That job already discharged four asks; **this is the fifth**, and X4 is
   the oldest open item on this line.
2. **If that spread lands near 0.29, X4 is sealable as designed** and the arithmetic is already
   done: best null 0.0664, largest null-against-the-rest margin 0.0062, so a threshold of 0.02 is
   valid and the bar would be **0.086 against an attainable 0.895**. If it lands near 0.10, the
   conjunctive level statistic is the wrong instrument and X4 needs a different estimand, not a
   different corpus.
3. **What was NOT done, deliberately.** Restricting the scored set to the mild perturbations, or
   dropping quantities, would each buy power — and both are choices made *after* seeing the values,
   which is the thing pre-registration exists to prevent. The estimand was not tuned to the result.
4. **`mean_per_quantity` separates cleanly and is still not an acceptance test.** Its ordering is
   correct, its spread is 0.205 and its smallest adjacent gap is 0.0182 against a ceiling of 0.955.
   It resolves what the conjunctive statistic cannot — but a mean over quantities lets a model buy a
   score by nailing soil carbon and missing every trait, so it stays an **engineering** diagnostic
   reported in a record, exactly where t3-drift was put. It must never be sealed as X4's statistic.
5. **A caution that reaches past X4.** The project's acceptance test is this statistic. Measured
   here, **one real realisation of the model reaches 0.470 of its own cells** at present-day climate
   on the transferred band — so the conjunctive-22 test at a 10 % band is severe even for the model
   being emulated, and every conjunctive number the project quotes should carry its ceiling.

## Basis, travelling with every number above

Pilot corpus v1: 200 cells × 30 climates × **one** seed, single-cell 1000-year spin-ups, npatch=25,
constant CO₂, state read from the uncensored end-of-spin-up restart. 5,800 (cell, climate) targets,
6.3 % of them treeless. Nulls out of fold on whole 15° tiles, 5 folds, 164 tiles. Band transferred
from the ssp126 leg's two genuine seeds (ssp370's are a bit-identical clone and are never used).
The ceiling is an **estimate**, measured at present-day climate on the historical pair, not on any
perturbed state — which is the same missing measurement as above.
