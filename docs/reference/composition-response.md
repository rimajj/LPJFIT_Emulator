# Predicting a shift in the species mix — the apparatus

What every information-free competitor scores when asked how a cell's mix of tree types changes
under a perturbed climate, how far apart those competitors are, and how well a perfect predictor
could possibly do. Derived 2026-09-14 by `scripts/exp_derive_nulls_composition.py` on pilot corpus
v1; campaign `T-nulls-composition`, job 2194883. Artifact:
`/p/tmp/jamirp/vegemu/exp/T-nulls-composition/nulls_composition.json`.

**Nothing here is fitted and nothing here is claimed.** This is the apparatus a pre-registration
needs before the question can be asked. The model arm exists
(`scripts/exp_model_pilot_composition.py`) and has deliberately **not** been run.

---

## Why the question exists

`models/synth.py` copies each tree's TYPE from the target cell's own template roster. That is
deliberate and well-founded — letting type float put 31 % tropical broadleaved evergreens into a
block of temperate European cells, and LPJmL-FIT killed every one of them inside the first year,
taking half the roster and two thirds of the carbon with them. The consequence, disclosed in that
module's own docstring since the transplant was written, is that **an emulated warmed forest cannot
change which species it holds**. Whether that limit costs anything depends on whether the
composition response is learnable at all, which is what this apparatus makes it possible to ask.

## The estimand

`skill_composition_mean` — the unweighted mean over the seven tree types of
`1 - SUM((dpred - dtrue)^2) / SUM(dtrue^2)`, pooled over (cell, climate) pairs, where
`dtrue = pft_frac_i(perturbed) - pft_frac_i(control)` is a **within-cell paired contrast**.

⚠ **A separate estimand from the sealed response test, deliberately.**
`X-20260909-pilot-warming-response` is sealed around "the unweighted mean of the seven"
`RESPONSE_QUANTITIES`, and its recorded 0.5453 reproduces only while that tuple has exactly seven
members. Appending the composition columns to it would silently redefine a sealed experiment. The
two numbers are quoted separately and **never summed**.

**Basis.** Pilot corpus v1: 200 cells × 29 perturbed climates + control, 1 seed, npatch=25, base
window 1970–1999, constant CO₂ and CO₂ never written. State from the end-of-spin-up restart, which
is uncensored. Dimensionless ratio of sums of squares, not a level. 5,800 pairs, of which **5,258
score** per quantity.

⚠ **`pft_frac_i` is the share of the cell's STEMS of type i, counted per INDIVIDUAL and not
weighted by biomass** (`corpus/state.py` builds it as `bincount(ids) / ids.size`). A type that is
numerically rare but holds the canopy therefore scores small. That is a property of the definition,
not of the emulator, and it belongs in any sentence quoting one of these numbers.

**The seven shares sum to 1**, to within 2e-16 on every treed row, so only six are free. Every arm
is scored under the identical redundancy, but no single term is independent evidence.

## How big is the target

Measured *before* any null value, per line X's rule that a design must be checked against its own
numbers before it is sealed.

| type | scorable pairs | RMS change | p90 abs change | share of pairs moving > 5 pp |
|---|---|---|---|---|
| `pft_frac_0` | 5,258 | 0.2112 | 0.2748 | 28.9 % |
| `pft_frac_1` | 5,258 | 0.1689 | 0.2158 | 36.1 % |
| `pft_frac_2` | 5,258 | 0.1538 | 0.2182 | 32.5 % |
| `pft_frac_3` | 5,258 | 0.1869 | 0.2441 | 33.0 % |
| `pft_frac_4` | 5,258 | 0.2070 | 0.2582 | 23.5 % |
| `pft_frac_5` | 5,258 | 0.1509 | 0.1508 | 20.1 % |
| `pft_frac_6` | 5,258 | 0.0877 | 0.0329 | 7.3 % |

**The plain-language form: the most abundant tree type is different from the control's in 1,309 of
5,258 pairs — 24.9 %.** A quarter of the cell-and-climate combinations are a different forest by
the simplest test there is. The target is not degenerate.

## What each competitor scores

15-degree blocking is primary; 5-degree is a pre-declared sensitivity check reported alongside,
never substituted. `k = 5`, fold seed 42, whole tiles held out together, one fold label per cell.

| competitor | 15° | 5° |
|---|---|---|
| `no_response` — predict no change anywhere | **0.000000** | 0.000000 |
| `level_mean_response` — the training cells' mean change at that design point | 0.034332 | 0.040552 |
| `proportional_median_response` — **the best null** | **0.177858** | 0.188750 |
| `proportional_mean_response` — the same with a mean, unusable, kept as a measurement | −27.619377 | −26.879787 |
| `nearest_cell_response` — copy the geographically nearest training cell | −0.357056 | −0.320205 |
| `nearest_analogue_response` — copy the climatically nearest training cell | −0.366684 | −0.291273 |
| `shuffled_cells` — the truth, permuted across cells | −0.835107 | −0.835107 |

`no_response` is analytic and exact: with `dpred = 0` the numerator equals the denominator.
`shuffled_cells` is identical at both radii because the permutation does not use the folds.

**Separation.** The decision-relevant gap — best null minus `level_mean_response` — is **0.143527**,
more than three times the corresponding gap in the sealed response test (0.041413). The minimum
adjacent gap is 0.009628, but it sits between `nearest_cell` and `nearest_analogue`, both deeply
negative and neither a decision arm, so it does not threaten the test's power.

**Best null per type**, at 15°: 0/−0.0244, 1/+0.3374, 2/+0.0886, 3/−0.0284, 4/+0.4738, 5/−0.0065,
6/+0.4045. The proportional rule carries three types and does nothing on the other four — the
pooled 0.178 is not a uniform competence.

## The ceiling

Same argument and same code as `exp_derive_ceiling_pilot.py`. LPJmL-FIT is stochastic, the target
is a paired contrast of single runs, so a perfect emulator predicts the noise-free change and its
residual is the model's own realisation noise. σ is estimated from the historical seed-1 and seed-2
end-of-spin-up restarts at the same 200 cells.

* **ρ = 0 (independent noise), the conservative lower bound: 0.863852**
* ρ = 0.5 (partial cancellation): 0.931926

Per type at ρ = 0: 0.9786 / 0.7499 / 0.8988 / 0.9817 / 0.9723 / 0.7481 / 0.7176.

The control and perturbed arms share a random seed, so the truth lies between the two and pinning
it needs a second seed for a subset of the pilot — a cheap, concrete ask of line D.

At a +0.080 pass margin the bar would be **0.257858 against an attainable 0.863852**. Readable —
unlike the sealed response test, which was sealed at 0.2257 before anyone had computed that perfect
was 0.8697.

---

## Two method decisions that belong in the pre-registration, not in a footnote

### 1. A forest that disappears is not a forest that changed species

`corpus/state.py:_empty_summary` writes **0.0** into every `pft_frac_*` of a treeless cell, because
it zeroes all of `STATE_COLUMNS` and then re-blanks only the trait quantiles. As a *level* that is
defensible. As a *change* it is not: it reads as "type 3's share fell from 0.81 to 0.00", which is
not a shift in the mix — there is no mix — and it is the same collapse `stems_per_patch` already
scores in full in the sealed response arm. **Measured: leaving it in inflates the total squared
change by 15–18 % on most types**, and it would let a model buy apparent species-shift skill by
predicting die-off.

`score.blank_treeless_composition` restores the rule the trait medians already use, for the
identical reason: a wood density of zero is not light wood, it is no wood. A pair drops per quantity
when the arm **or** the control has no stems — **542 of 5,800**, being 493 from the 17 cells already
treeless under their own control, plus 49 arms that went treeless.

⚠ **The disclosure that travels with the number:** composition is therefore scored where a forest
existed at both ends, which selects toward the milder perturbations.

Not fixed at source because `src/vegemu/corpus/**` is line D's exclusively, and every cached state
table already on disk carries the zeros. The masking is idempotent and needs no re-decode.

### 2. Every arm must share one denominator

`score.skill_vs_no_change` builds its denominator over the rows where the **prediction** is finite,
so an arm that declines to answer on the hard rows is scored on an easier subset than its
competitors. Here that is a live effect and not a precaution — 9.3 % of pairs are undefined and they
cluster at the 17 cells treeless under their own control. Fills needed at 15°, out of 36,806
scorable cell-quantity entries:

| arm | predictions filled |
|---|---|
| `nearest_cell_response` | 2,296 |
| `nearest_analogue_response` | 1,253 |
| `shuffled_cells` | 3,360 |
| the other four | 0 |

So every arm is scored on the identical truth-finite set, and a missing prediction is **imputed as
no change**. That filling is the conservative direction: it pulls a negative null *up* toward zero,
making the competitor stronger and the bar harder, and it keeps `no_response` pinned analytically at
exactly 0.0.

**This asymmetry also existed in `X-20260909-pilot-warming-response`.** There it could only touch
`nearest_cell` and `nearest_analogue`, both of which scored negative and neither of which was the
best null, so the pass at 0.5453 is unaffected — but that verdict should say so rather than leave it
unstated.

---

## Regression: the shared refactor changed nothing

`derive_nulls` was split into `build_null_predictions` + the scorer so this arm could reuse the null
arithmetic rather than re-implement it. Re-running the sealed derivation on the same cache
reproduces all seven sealed values to six decimals — 0.145690 / 0.095610 / 0.000000 / −0.239753 /
−0.281166 / −0.797389 / −27.402105. Campaign `T-nulls-pilot-regression`, job 2194882. The
equivalence is also asserted directly in `tests/test_composition_arm.py`, because nothing in the
sealed experiment's own directory would go red if it drifted.
