# Composition is a separate scored arm, and a forest that disappears must not count as one that changed species

- **Date:** 2026-09-14
- **Line:** T
- **Status:** accepted
- **Experiments:** apparatus for a composition kill test; pre-registration owed by line X

## What was decided

Three things, in the order they bind.

1. **Composition is scored as its own arm, with its own nulls and its own bar — not by appending to
   `RESPONSE_QUANTITIES`.** The handoff offered both. Only one is available: that tuple *is* the
   estimand of the sealed `X-20260909-pilot-warming-response` ("the unweighted mean of the seven"),
   and its recorded 0.5453 reproduces only while it has exactly seven members. Appending to it would
   silently redefine a sealed experiment and destroy the reproducibility of its own headline. The
   two numbers are quoted separately and never summed. A test asserts the tuple is untouched.

2. **A treeless cell's tree-type shares are blanked before any contrast is taken.**
   `corpus/state.py:_empty_summary` writes `0.0` into every `pft_frac_*` of a cell with no stems,
   because it zeroes all of `STATE_COLUMNS` and then re-blanks only the trait quantiles. As a
   *level* that is defensible. As a *change* it is a collapse wearing a composition's clothes: it
   reads as "type 3's share fell from 0.81 to 0.00", which is not a shift in the mix — there is no
   mix — and it is the same event `stems_per_patch` already scores in full in the sealed response
   arm. This is the rule the trait medians already use, for the identical reason.

3. **Every arm is scored on one denominator, with a missing prediction imputed as no change.**
   `score.skill_vs_no_change` builds its denominator over rows where the *prediction* is finite, so
   an arm that declines to answer on the hard rows is scored on an easier subset than its rivals.

## Why, with the numbers

**The target is not degenerate, and that was checked before any null value was quoted** — line X's
X4 lesson. A tree type's share of the stems moves with an RMS of 0.15–0.21 across the 5,258 scoring
pairs, and by more than five percentage points in 20–36 % of them. In plain terms: **the most
abundant tree type is different from the control's in 1,309 of 5,258 pairs, 24.9 %.**

**Decision 2 is worth 15–18 % of the scored movement.** Leaving the zeros in inflates the total
squared change by that much on most types, and it would let a model buy apparent species-shift skill
by predicting die-off — a skill it is already credited for elsewhere. The price of blanking is a
disclosure, not a footnote: **542 of 5,800 pairs drop** (493 from the 17 cells already treeless
under their own control, 49 from arms that went treeless), so composition is scored where a forest
existed at both ends, which selects toward the milder perturbations.

**Decision 3 is a live effect here, not a precaution.** At 15-degree blocking, out of 36,806 scorable
cell-quantity entries, `nearest_cell_response` needed 2,296 fills, `nearest_analogue_response` 1,253
and `shuffled_cells` 3,360. Without the fix those three would have been scored on materially easier
subsets than the model. Imputing no-change is the conservative direction — it pulls a negative null
*up* toward zero, making the competitor stronger and the bar harder — and it keeps `no_response`
pinned analytically at exactly 0.0.

**The same asymmetry exists in `X-20260909-pilot-warming-response`.** There it could only touch
`nearest_cell` and `nearest_analogue`, both of which scored negative and neither of which was the
best null, so the 0.5453 pass is unaffected. X has been told, because a verdict should state that
rather than leave it unstated.

## What the apparatus came out at

Campaign `T-nulls-composition`, job 2194883. Full table in `docs/reference/composition-response.md`.

| arm | 15° (primary) | 5° |
|---|---|---|
| `proportional_median_response` — **best null** | **0.177858** | 0.188750 |
| `level_mean_response` | 0.034332 | 0.040552 |
| `no_response` (analytic, exact) | 0.000000 | 0.000000 |
| `nearest_cell_response` | −0.357056 | −0.320205 |
| `nearest_analogue_response` | −0.366684 | −0.291273 |
| `shuffled_cells` | −0.835107 | −0.835107 |
| `proportional_mean_response` (unusable, kept as a measurement) | −27.619377 | −26.879787 |

**Separation is better than the response test's**: the decision-relevant gap, best null minus
`level_mean`, is 0.143527 against 0.041413 there. **Ceiling, ρ = 0 conservative lower bound:
0.863852** (ρ = 0.5: 0.931926), so at a +0.080 margin the bar of 0.2579 is readable — unlike
`X-20260909`, which was sealed at 0.2257 before anyone had computed that perfect was 0.8697.

## What this does not decide

**Nothing about whether the emulator can predict composition.** No model was fitted. The model arm
is written (`scripts/exp_model_pilot_composition.py`) and deliberately **not run**: `experiments/**`
is line X's, the pre-registration is X's to write and seal, and running the scored arm first is the
ordering invariant 2 exists to prevent.

It also does not fix the zeros at source. `src/vegemu/corpus/**` is line D's exclusively, and every
cached state table on disk already carries them, so the masking lives in the shared scorer where it
is idempotent and needs no re-decode. If D ever re-decodes, `_empty_summary` is the right place.

## Consequences

- `derive_nulls` is split into `build_null_predictions` + the scorer so both arms share one
  implementation. Verified: re-running the sealed derivation reproduces all seven of its values to
  six decimals (campaign `T-nulls-pilot-regression`, job 2194882), and the equivalence is asserted
  in `tests/test_composition_arm.py`, because nothing in the sealed experiment's own directory would
  go red if it drifted.
- Any number from this arm must carry two clauses: the shares are of **stems, counted per
  individual and not weighted by biomass**, so a rare type holding the canopy scores small; and the
  seven shares sum to 1, so only six are free.
- Line T is blocked on X's seal for the scored answer, and on nothing else.
