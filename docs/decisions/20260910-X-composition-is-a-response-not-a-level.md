# Species composition is NOT added to the conjunctive band test — it is scored as a response

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** X
- **Answers:** line D's blocking question for corpus v2 — "does v2 also put `pft_frac_*` in
  `SCORED_CONJUNCTIVE`?" (`lines/D/STATE.md`, next-action 3). Corpus v2 was held on this.
- **Corrects:** the remedy asserted in `src/vegemu/models/synth.py:56-61`, which states that
  "the composition becomes predictable as soon as those columns are added to the scored set".
  Adding them to the *conjunctive band* set does the opposite. The limitation it describes is
  real; the fix named there is the wrong one.

## What was decided

**No.** `pft_frac_0…6` do **not** join `SCORED_CONJUNCTIVE`, in v2 or any later corpus version.
Composition is scored **as a change, on the response basis**, by a single bounded scalar with an
analytically pinned null — not as seven levels inside a relative-band conjunction.

The synthesiser may therefore keep copying composition from the template in v2. But that choice
stops being a free modelling convenience and becomes **the pre-registered null arm on
composition**, which must be named as such and beaten, not left undisclosed.

## Why adding them to the band test would be perverse, not merely weak

The band is multiplicative in the level (`src/vegemu/score.py:105-113`):

    truth = (s1 + s2) / 2 ;  band = max(0.10, |s1 - s2| / |truth|) * |truth|

So **a quantity whose truth is 0 gets a band of exactly 0**, and only an exactly-0.0 prediction
passes. Verified directly against the shipped functions: with `truth = 0`, predictions of `1e-9`,
`0.01` and `0.05` all MISS; only `0.0` hits.

`pft_frac_i` is structurally zero — a cell holds a few tree types out of seven. Measured on
`corpus/pilot-v1/corpus.parquet` (6,000 rows, the sealed pilot):

| fact | value |
|---|---|
| cell–PFT pairs exactly zero | 19,170 / 42,000 = **45.6 %** |
| rows with ≥1 exactly-zero `pft_frac` | **6,000 / 6,000 = 100 %** |
| cells holding all 7 PFTs | **0** |
| median PFTs present per row | 4 of 7 |
| treeless rows, all-zero composition | 380 |

Per-column zero rate: `pft_frac_0` 38.8 %, `_1` 18.4 %, `_2` 27.9 %, `_3` 22.8 %, `_4` 70.0 %,
`_5` 70.3 %, `_6` 71.4 %.

Every row carries at least one zero-width band. Two consequences, and they point the same way:

1. **Any continuous predictor scores ~0 conjunctively, whatever its composition skill.** The
   conjunction would go from 22 quantities to 29, and each row would gain a median of three
   pass-only-on-exact-0.0 columns. A learner essentially never emits exact zeros. The headline
   number stops varying with model quality, which is what makes it uninformative — the metric
   would report the same ~0 for a composition-blind model and a good one.
2. **The template-copying synthesiser passes all seven trivially.** It reproduces the template's
   composition exactly, zeros included. So the metric would award a perfect composition score to
   precisely the frozen-composition behaviour it was added to catch.

Taken together the statistic would be **anti-correlated with the capability it purports to
measure**: it punishes models that try and rewards the one that cannot shift composition at all.
Under invariant 3 that is a metric without power, so its verdict would be `invalid` — and this is
the second time deriving nulls first has killed a statistic before sealing rather than after
(the first being X4's, per `lines/X/STATE.md`).

A relative band on a bounded fraction is the same error already recorded one level up, at
`src/vegemu/score.py:59-61`: a relative band around a near-zero quantity is near-zero too. That
note was written about changes; it applies verbatim to composition fractions as levels.

## What is scored instead

A single derived quantity, on the response basis, where the target is a **difference** and so has
no near-zero denominator:

    comp_shift = 0.5 * SUM_i | pft_frac_i(warmed) - pft_frac_i(control) |

Total-variation distance between the two composition vectors. It is bounded in [0, 1], defined
when any or all components are zero, unit-free, and one number rather than seven — so it does not
dilute the conjunction. Scored with the existing `skill_vs_no_change`, which pins the null
analytically (invariant 2 — every null with the value it must return):

| arm | what it predicts | must return |
|---|---|---|
| **frozen composition** (copy the template — today's synthesiser) | `comp_shift = 0` | exactly **0.0** |
| a real model | its own shift | must exceed 0.0 to license any composition claim |
| uncorrelated shift | noise | about **-1.0** |

This makes the disclosed limitation **measurable and falsifiable** rather than invisible. The
frozen arm is not a hypothetical: it is what the shipped synthesiser does, so the null is the
current product and the gap over it is exactly the composition capability being claimed.

⚠ **A ceiling arm is required before this is read**, per the line X gotcha and the same omission
corrected in `20260910-X-the-pilot-kill-test-ceiling-is-0.87.md`: `comp_shift` is a contrast of
two single stochastic runs, so a perfect emulator cannot reach 1.0. It needs D's second seed on
the pilot cells (already requested) to be measured rather than bounded.

## Scope, and what this does not decide

- It does **not** widen the acceptance criterion. The owner's clause names tree counts, trait
  distributions and trait medians; composition is not in it. This adds a response diagnostic, so
  no sealed pre-registration changes and no sealed hash moves.
- It does **not** license quoting a warmed-climate composition. Until the response arm is run and
  beats 0.0, a warmed restart carries present-day composition and that must ship disclosed —
  unchanged from `synth.py:56-61`.
- It does **not** block corpus v2. `pft_frac_*` stay computed-and-unscored in the corpus, exactly
  as in v1, so v2's build is unaffected either way and D can proceed.
- The seven columns are **not** removed. They are the input to `comp_shift` and stay in the state
  table.
