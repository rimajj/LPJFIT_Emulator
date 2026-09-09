# The kill test's bar is not "no change" — it is a proportional response, at 0.1457

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** X
- **Realises:** `PLAN.md` rung 1 on line D's pilot corpus (`20260909-D-pilot-corpus-v1.md`).
  Does not supersede X1 (`X-20260908-warming-response`), whose `fail` stands on its own data.

## What was decided

`X-20260909-pilot-warming-response` is **sealed**, with seven nulls whose values were derived from
the truth before any model exists. The emulator must reach **0.225690** to pass.

This is X1's question — can the emulator predict how a forest *changes*? — asked on data that can
answer it. X1 returned `fail`, but its own diagnosis was that the question was not cleanly askable
on the two ground-truth legs: each cell holds exactly one climate there, so climate and geography
are collinear and a warming response is not separately identified. The pilot corpus spins the same
cell up under 30 climates with the same config, window and random seed, so the only difference
between an arm and its control is the climate.

## The nulls, and the one that sets the bar

200 cells × 29 perturbed climates = 5,800 within-cell paired contrasts, out of fold under
15° blocked 5-fold, seven quantities, `skill_response_mean`:

| null | pooled | what it knows |
|---|---|---|
| **proportional_median_response** | **+0.145690** | the level, and the cell's own standing state |
| level_mean_response | +0.095610 | the level only |
| no_response | 0.000000 | nothing (analytic) |
| nearest_analogue_response | −0.239753 | the climatically closest other cell |
| nearest_cell_response | −0.281166 | the geographically nearest other cell |
| shuffled_cells | −0.797389 | the right answers on the wrong cells |
| proportional_mean_response | −27.402105 | the same as the best null, built wrong |

**The bar is "every cell changes by the same fraction of what it already has"**, applied to the
held-out cell's own present-day forest — not "nothing changes". That competitor is not a
technicality: it is the first thing a scientist would propose, the estimand is a difference of
levels, and the cells run from Amazon to Sahel. It beats the additive form by 0.050.

Per quantity it is carried by soil carbon (0.5539) and above-ground biomass (0.2309) and is near
zero or negative on the trait medians (median height −0.0203, SLA 0.0058). **The size of the
response scales with standing stock; its composition does not.**

## Three findings the design rests on

**1. Copying another cell's response is worse than saying nothing changes.** Both borrowing nulls are
below zero — nearest cell −0.281166, closest climate analogue −0.239753. The response is
cell-specific, so space-for-time substitution actively hurts here. It is not uniform, and the
non-uniformity is the shape of the problem: the analogue null reaches **+0.3292 on soil carbon** and
**+0.1677 on above-ground biomass** while collapsing to **−0.6387 on stem count** and **−0.5849 on
wood density**.

**2. The blocking radius barely matters, for the first time in this project.** The two strong nulls
move by less than 0.003 between 15° and 5° blocks (0.145690 → 0.144655; 0.095610 → 0.097965). At 5°
the 200 cells occupy 194 distinct blocks, so the folds are all but random by cell — and it still does
not matter, because the cells sit in 164 populated 15° tiles and there is no near neighbour to
interpolate from at either radius. Contrast X2, where the address null flipped from −0.142 to +0.120
at 5°, and X4, whose 20 adjacent cells were one neighbourhood. **This is a property of line D's cell
design, and it is what makes the result a spatial claim rather than an interpolation score.**

**3. The response is not smooth in temperature, and that is the majority behaviour.** Only **40.5 %**
of the 200 cells have a monotone above-ground-carbon response across 0 / +2 / +4 / +6 K. Predicting a
cell's +4 K response from its **own** +2 K and +6 K responses — far more information than any
emulator is given — reaches only **0.6176**, and **0.3342** for median stem height. Line D saw this
at the Amazon cell (−36 % at +2 K, −97 % at +4 K, back to ~35 % of control at +6 K) and asked whether
it was an Amazon quirk. It is not. Two consequences, both binding on the sealed record: the split
holds out **space, not climate levels**, because a held-out-level design would charge the emulator
for the roughness of the response surface; and the **29-row per-level table is part of the result**,
not an appendix, so a pass on the pooled statistic with a fail at more than half the levels must be
reported as such.

## Two traps caught before sealing

**X1's pass threshold, transplanted here, would have pre-registered a guaranteed `invalid` — by
eight hundred-thousandths.** The no-power rule scores each null on the same comparator as the model:
under `model_minus_best_null` that is the null minus the best *other* null. The best null beats the
runner-up by **0.050080**, and X1's rule was `> 0.050`. The best null would have satisfied the pass
rule, and E08 would have voided the verdict before the model was even fitted. The threshold is
**0.080**, derived from these nulls, leaving the binding margin 0.030 clear. This is the second time
line X's rule — *derive the nulls before designing the statistic* — has caught a dead experiment
before it was sealed; the first was X4, still deliberately unsealed.

**The obvious way to build the best null is unusable, and the number is on the record.** Aggregating
the donor fractions with a mean instead of a median scores **−27.402105** pooled and **−173.8** on
above-ground biomass: the fraction carries a near-zero control in its denominator at the 39 cells
that go treeless, so a few enormous donor ratios get multiplied onto the standing state of large
cells. Both forms are pre-registered so that "unusable" stays a measurement rather than a remark.

## Disclosures that travel with every number from this corpus

* **380 of 6,000 runs (6.33 %, touching 39 of 200 cells) end with no stems.** Counts and stocks keep
  those rows — zero is legitimate and a collapse to zero is the largest response in the corpus. The
  three trait medians cannot: a wood density of zero is not light wood, it is no wood, so 5,620 of
  6,000 rows survive there. **The trait medians are therefore scored where vegetation survived**,
  which selects toward the milder perturbations. Line D's independent estimate from restart byte size
  alone was 374 of 6,000 (6.2 %); the decoded stem count says 380. Two unrelated methods, one answer.
* **The target is protocol-defined, not an equilibrium.** The 1000-year spin-up is not converged
  (57.9 % of vegetated cells still moving). The paired contrast is legitimate because both arms carry
  the same drift; a claim about the stationary forest a climate supports is not licensed.
* **Eligibility here is 56,986 cells, not the acceptance criterion's 54,020.** Line D's number is the
  restart's own uncensored stem count; the 54,020 counts cells with a *visible* tree. Quote one or
  the other, never both as one number.
* This is **200 cells, not 54,020**. A pass licenses nothing about fidelity; it says a learnable
  cell-specific response exists. Failing stops the project.

## What was NOT established

**Nothing about the emulator** — no model was fitted, and what was pinned down is the apparatus. Not
**why 40.5 % are monotone**, and not **whether the same bar holds at the mid tier**: the proportional
null is strong partly because 30 climates share one design.

## Reproduce

`scripts/exp_derive_nulls_pilot.py --version pilot-v1 --nproc 32 --degrees 15 --out <dir>`, under
`sbatch_py.sh`: all 6,000 restarts decode and every null derives in **9 seconds on 32 cores**, and
with the state cached a change of blocking radius is a one-second re-run. Result:
`/p/tmp/jamirp/vegemu/exp/X-pilot-nulls-15deg/nulls_pilot.json`.
