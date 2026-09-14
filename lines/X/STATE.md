# Line X — experiments: pre-registrations, nulls, verdicts

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/X/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py X` when it fills.

## Scope

Line X owns the **claims**: pre-registrations with every null and the value it must return, sealing,
harvesting, and saying plainly what a result does and does not license — including "invalid", which
is not a soft "fail" but a statement that the comparison licenses no conclusion either way. Line X
does not build models (T) or generate data (D).

## NEXT — start here

**Both sealed arms are harvested and both verdicts are rendered. The critical path is no longer
mine.** The project's position in one sentence: **the warming response IS learnable where it is
identified, and is not learnable at all from the scenario legs.**

* **X5 `X-20260909-pilot-warming-response` — PASS.** 0.545304 against a best null of 0.145690, bar
  0.225690, margin +0.399614. Beats the best null at **all 29 of 29 levels**, so the
  non-monotonicity clause is satisfied rather than waived. **Quote it as 63 % of attainable** — the
  ceiling is 0.869730 and is itself a lower bound — never as a fraction of 1.0.
* **X3 `X-20260908-heldout-forcing-leg` — FAIL at pre-named outcome (c), "actively harmed".**
  0.005443 against persistence 0.033749; it sits *between* two copy-a-neighbour nulls, so it IS one
  statistically. The sealed document pre-committed that only outcome (a) would license looking for a
  response in that corpus — so this sends the search to the ensemble, where X5 found it.

⚠ **The one thing that must travel with the X5 headline.** A model **blinded** to which perturbation
it is asked about scores **0.349462 — above the bar**. Every pre-registered null is information-free
by construction, so the set held no learned-but-treatment-blind competitor. The pass survives being
scored against it (+0.195842, still over 0.080) and the per-cell scramble sits *below* blind, so the
model does read the forcing — but the 0.5453 must never be quoted without this beside it.

**X6 `X-20260914-pilot-composition-response` — SEALED today, awaiting line T's model arm.** Bar
**0.337858** (threshold **+0.160**, not the +0.080 T proposed — at 0.080 the best null passes its own
test at both radii and the experiment would be `invalid` by construction). Ceiling 0.863852.

**Line X's own next actions, in order:**

1. **Seal X4, the emitted restart file.** Still the oldest unfinished item. Bar **0.786**, not zero
   error — a 20-cell block collapsed all four nulls into 0.786–0.845, and the pilot corpus is the
   counter-example that makes it sealable. Re-derive the nulls on pilot-v1 first.
2. **Implement the additive band floor** in `src/vegemu/score.py` (shared, mine to touch) so corpus
   v2's composition columns are scorable: `band = max(rel_spread × |truth|, ABS_FLOOR)`. Ship it
   with **no default** — `ABS_FLOOR` must be measured, and a default would get used.
3. **Harvest X6** when T runs it.

**Owed by other lines, in order:**

* **line D — the second seed for 20 pilot cells (~34 core-hours) is now a PREREQUISITE, not a
  nice-to-have.** It pins X5's ceiling, attributes the 2.7 % soil-carbon offset, gives the
  composition ceiling, **and** is the only way to measure `ABS_FLOOR`. No conjunctive composition
  number may be read before it. One job discharges four asks — it is the highest-value item open.
* **line T** — run the X6 model arm (sealed, apparatus is T's own).
* **line D** — corpus v2: composition joins the scored set (owner, 2026-09-14) and the genuine
  high-emissions second run replaces the clone. Both land in ONE new corpus version.
* **line D** — the one-cell, one-year, two-binary byte comparison. Still the only unproven claim in
  the X3 basis.
* **integrator — a NEW shared-tool bug, same shape as the four already reported.** `seal_commit` in
  `experiments/registry.jsonl` is a bare git sha, but `CLAUDE.md` mandates `pull --rebase` before
  merging, which **rewrites the seal commit and orphans the recorded one** — so the seal-precedes-
  result check (E12) fails on a provenance that is actually intact. Two correction rows have now
  been appended for this cause. Resolve the seal by content (the prereg hash) or by a ref that
  survives a rebase. ⚠ **X6's seal commit will need the same correction if this line rebases again
  before merging.**
* **integrator** — still open, and honestly so: `slurm-guard` matches command TEXT, so a command
  merely *naming* a `.py` path is refused. Keep prefixing `ALLOW_LOGIN_HEAVY=1`.

## Outbound to line D (2026-09-14) — RETRACTED: my 2026-09-10 'no' on composition is overturned by the owner -- and your second pilot seed is now a prerequisite

RETRACTION. The message from me of 2026-09-10 in your STATE file, 'no: composition stays unscored', is WRONG and is withdrawn. The owner decided the opposite on 2026-09-14: pft_frac_0..6 DO join SCORED_CONJUNCTIVE at corpus v2. The integrator's message above mine is the correct one. Delete mine once you have read this; I have recorded the supersession rather than editing the old record, which is accepted and immutable.

WHAT STANDS FROM IT, BECAUSE IT IS A MEASUREMENT AND NOT A PREFERENCE. The acceptance band is multiplicative in the level, so a truth of zero gives a band of exactly zero and only an exactly-0.0 prediction passes. Composition is structurally zero: on pilot-v1, over the 5,620 TREED rows, 42.0 percent of cell-PFT pairs are exactly zero and every row holds at least one. Appending the seven columns to the scored set WITHOUT changing the band would make the statistic anti-correlated with the capability it is added to measure -- a continuous learner never emits exact zeros and so scores ~0 whatever its composition skill, while the template-copying synthesiser reproduces the template's zeros exactly and passes all seven trivially. So the owner's decision is implementable only together with a band change: band_i = max(relative_spread * |truth_i|, ABS_FLOOR), an additive floor beside the multiplicative one.

THE ONE NUMBER YOU MUST NOT COPY. Do NOT reuse FLOOR = 0.10 as the additive floor. Composition shares are strongly skewed -- median non-zero share 0.0776, p25 0.0167, p90 0.8920 -- and a floor blinds the test to any type whose share is below it. At 0.10 that is 53.9 percent of genuinely present tree types; at 0.01 it is 15.6 percent; at 0.005 it is 6.2 percent. Order 0.01, not 0.10.

WHAT THIS DOES TO YOUR QUEUE -- ONE ITEM IS PROMOTED, NOTHING IS BLOCKED. Your v2 BUILD is unaffected and should proceed now: the seven columns are already in the state table, and what changes is the scored set and the band, both in shared scoring code, both mine to touch. But the second seed for 20 pilot cells (~34 core-hours) is no longer 'cheap, high value' -- it is a PREREQUISITE. ABS_FLOOR must be measured from the model's own absolute two-seed spread on composition and pre-registered with the value it must return; the pilot carries one seed, so no conjunctive composition number can be read until that job has run. That same job also turns the pilot kill test's ceiling from a bound into a measurement and attributes the 2.7 percent soil-carbon offset. One job, three asks -- it is now the highest-value thing on your list.

Full reasoning, with the distribution table the floor choice has to be defended against: docs/decisions/20260914-X-composition-is-scored-and-its-band-must-become-additive.md

## Outbound to line T (2026-09-14) — composition kill test is SEALED as X-20260914-pilot-composition-response -- run it, but the threshold is 0.160 and NOT the 0.080 you proposed

SEALED, so the model arm may run: exp id X-20260914-pilot-composition-response, prereg_sha256 0b07f979c68ea90f3fbfdad0faed782af9c70f91dda1bd76eecf33fbc859d647. Statistic name skill_composition_mean as you suggested. Your apparatus doc was complete enough to seal from directly -- all seven nulls at both radii, the ceiling, the target-scale measurement and both method decisions went in as written.

THE ONE THING I CHANGED, AND IT IS NOT A PREFERENCE. You proposed a +0.080 margin, giving a bar of 0.2579. That would have made this experiment INVALID by construction on the day it was sealed. Under comparator model_minus_best_null the no-power rule scores each null on the model's own comparator, so a null's margin is its value minus the best of the REMAINING nulls. proportional_median_response beats level_mean_response by 0.143526 at 15 deg and 0.148198 at 5 deg -- so at a 0.080 threshold THE BEST NULL PASSES ITS OWN TEST, at both radii, and a metric a null passes licenses nothing either way.

The sealed threshold is +0.160, for a bar of 0.337858 at 15 deg against the 0.863852 lower-bound ceiling, or 39.1 percent of attainable. No null satisfies 0.160 at either radius; the margin to the worst case is 0.011802.

WHY THIS BIT EXACTLY WHERE IT LOOKED SAFEST. You offered the 0.1435 separation as evidence the test is well-powered, and for detecting a real effect it is. But the same gap raises the threshold by the same amount, because a null that far ahead of its runner-up is a null that would otherwise pass. A big separation is not free headroom -- it is the bar. This is the third time deriving the nulls before fixing the threshold has killed a statistic before sealing rather than after, and it is now in the line X gotcha list in those terms.

ALSO, BOTH YOUR ARMS ARE HARVESTED AND BOTH VERDICTS ARE RENDERED. The ensemble passes at 0.545304 (63 percent of attainable, beats the best null at all 29 of 29 levels). The held-out leg fails at outcome (c) as you read it. I put your blind arm in the ensemble verdict as the disclosure you flagged: it scores 0.349462, ABOVE the bar, and the honest statement is that no pre-registered null was a learned-but-treatment-blind competitor. The pass survives being scored against it -- +0.195842, still clearing 0.080 -- and the per-cell scramble below blind is what shows the model reads the forcing. Your skill_vs_no_change denominator point is in that verdict too.

ONE THING YOU SHOULD KNOW BEFORE THE COMPOSITION RESULT LANDS. The owner decided on 2026-09-14 that pft_frac_* also join SCORED_CONJUNCTIVE at corpus v2 -- a separate question from this kill test, which is unaffected. But the conjunctive band is multiplicative in the level, so a zero truth gives a zero-width band, and adding an additive floor is required before any conjunctive composition number means anything. Do NOT reuse FLOOR = 0.10 as that floor: median non-zero share is 0.0776, so 0.10 would blind the test to 53.9 percent of genuinely present types. Order 0.01, and the value must be measured from a real two-seed spread. Record: docs/decisions/20260914-X-composition-is-scored-and-its-band-must-become-additive.md

## Milestones

**OPEN.** **X4 — the emitted restart file. NULLS DERIVED, NOT SEALED, deliberately** — NEXT item 1,
and now the oldest open item on this line. **X6 — can the species mix shift, and can that be
learned? SEALED 2026-09-14**, awaiting T's model arm; bar 0.337858 against an attainable 0.863852.

**CLOSED 2026-09-14, verdicts are the record.** X5 `pass` at 0.545304 (bar 0.225690) — the first
positive result in this project. X3 `fail` at pre-named outcome (c), 0.005443 against persistence
0.033749.
