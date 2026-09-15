# The perturbed two-seed spread does NOT widen, so X4 needs a new estimand

- **Status:** accepted
- **Date:** 2026-09-15
- **Line:** X
- **Measurement:** line D's replicate, `pilot-v1-s2`, jobs 2204531/2204532/2204533; analysis job
  2204592, `scripts/exp_measure_perturbed_spread.py`.
- **Decides:** the branch pre-stated in `20260915-X-x4-is-not-sealable-and-the-cell-set-was-never-the-binding-constraint.md`.

## The number

20 cells x 30 climates, seeds 1 and 2, identical forcing bytes, 22 conjunctive quantities, 600
paired rows. Relative spread `|s1-s2| / |mean|`, reported **unfloored** because a floored spread
cannot answer "is the spread above the floor?".

| basis | median | p90 | p99 | fraction above the 0.10 floor |
|---|---|---|---|---|
| control (present-day climate) | 0.0310 | 0.159 | 0.643 | 0.204 |
| **PERTURBED climates** | **0.0301** | 0.177 | 0.706 | **0.204** |

**The spread under perturbation is the same as the spread at present-day climate.** 0.0301 against
0.0310, and an identical 20.4 % of cell-quantities above the floor. It does not land near 0.29.

## What that decides, and it was pre-stated

**X4 IS NOT SEALABLE, AND NOT FOR WANT OF DATA.** The pre-stated branch was: near 0.29, X4 seals
with best null 0.066379 and a bar of 0.086; near 0.10, the conjunctive level statistic is the wrong
instrument and X4 needs a new estimand. The measurement is 0.03 — below even the low branch — so the
10 % floor dominates in 79.6 % of cell-quantities, the band is the floor wearing the spread's name,
and the nulls collapse for that reason and will keep collapsing.

⚠ **This closes the question the second seed was run to answer. It does not license widening the
floor.** A floor chosen because 0.15 makes the nulls behave is a threshold chosen after seeing the
values, which is the thing pre-registration exists to prevent. X4 is retired in its present form;
what replaces it is a new pre-registration with a new estimand, not a re-tuned old one.

**THE OLDEST OPEN ITEM ON THIS LINE IS THEREFORE CLOSED — as "wrong instrument", not as "pass" or
"fail".** It has been unsealable since 2026-09-09 and the reason is now measured rather than
suspected.

## Three more answers from the same job

**1. The transferred band was legitimate all along.** The acceptance tolerance is
`max(10 %, the model's own two-seed spread)`, and every band applied to a perturbed state so far has
transferred that spread from present-day climate. That transfer was an unverified assumption; it is
now measured, and the two spreads agree to 0.001. **Nothing scored to date needs recomputing on this
account.** The 2026-09-14 caution that the perturbed spread "is unmeasured, and the acceptance
criterion puts it at up to 29 %" is discharged: it is measured, and it is 3 %.

**2. `ABS_FLOOR` is 0.0384, measured, not chosen.** Absolute disagreement between seeds on tree-type
shares, over treed-at-both-ends pairs: median 0.0027, **p90 0.0384**, p99 0.1148. That is the same
order as the 0.01 the 2026-09-14 record argued for and four times smaller than the 0.10 it warned
against — at 0.0384 the test stays sensitive to any type whose share exceeds ~4 %, against the 53.9 %
of genuinely present types that 0.10 would have blinded it to. **Pre-register it with this value.**

**3. The 2.7 % soil-carbon offset is REAL, not noise.** The model's own median two-seed spread on
soil carbon is **1.43 %** (p90 6.99 %). A 2.7 % offset is nearly twice the typical disagreement, so
it is a bias to attribute, not a draw to shrug at.

## What this rests on, stated plainly

**20 cells of the pilot's 200**, chosen as an evenly spaced stride over a south-to-north ordering, so
they span 52 S to 66 N and stem densities 105 to 1539 — but they are 20 cells, and 2 of them are
treeless under their own control. 11,824 perturbed cell-quantity pairs is a large sample of a small
cell set, and the cell set is what limits it. A p99 of 0.71 says the tail is long: some
cell-quantities really do disagree by 70 % between identical runs, which is consistent with the
acceptance criterion's "up to 29 % in low-density cells" being about the tail and not the middle.

**The replicate shares seed 1's forcing bytes**, so the difference between the pair is the model's
RNG and nothing else. That is what makes these numbers the model's own noise rather than a
comparison of two builds or two climates.
