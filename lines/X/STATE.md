# Line X — experiments: pre-registrations, nulls, verdicts

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/X/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py X` when it fills.

## Scope

Line X owns the **claims**. Everything under `experiments/`:

* writing pre-registrations: the estimand, the reference basis, the folds, the leakage checks, and
  every null **with the value it must return, derived before the run**
* sealing them, harvesting results, and rendering verdicts
* saying plainly what a result does and does not license — including "invalid", which is not a soft
  "fail" but a statement that the comparison licenses no conclusion either way

Line X does not build models (T) or generate data (D). It decides what would count as evidence, and
then whether the evidence arrived. That separation is the point: the line that builds a thing should
not be the line that certifies it.

## NEXT — start here

**Write rung 1's pre-registration now, before the corpus exists.** That is not premature — it is the
whole method. A pre-registration written after the data is available is a pre-registration written
with one eye on the answer, and the registry hashes it precisely so that cannot happen unnoticed.

**Rung 1 is THE KILL TEST for the project.** Its question, in one sentence: *given a cell's climate
shifted by +4 K, can a model beat "predict this cell exactly as it is today"?* If not, there is no
learnable warming response and the project stops — in roughly week 3, for ~670 core-hours.

```
cp -r experiments/_template experiments/X-<YYYYMMDD>-rung1-kill-test
```

**The four nulls, and why the first one is decisive.** Read `docs/reference/inherited.md` §2 before
writing them — it explains why the predecessor could not construct the first null at all.

| null | what it is | why it is here |
|---|---|---|
| **same-cell baseline** | this cell's own *unperturbed* equilibrium, ignoring the perturbation | THE one that matters. If the model cannot beat it, there is no response, only geography. |
| geographic address | unit-sphere x/y/z, no climate at all | the null that killed the predecessor's response claim (0.654 against a reported 0.748) |
| nearest-analogue cell | the observed equilibrium of the most climatically similar training cell | this is the space-for-time null; it is the honest competitor |
| shuffled target | permuted within fold | the sanity check |

**Four things the pre-registration must get right, each of which the predecessor got wrong once:**

1. **`split.kind: blocked_spatial`, not `kfold_by_cell`.** Random folds turn any per-cell score into
   a spatial-interpolation score; the effective independent sample is ~161 tiles, not 54,020 cells.
2. **Hold out entire perturbation LEVELS as well as cells.** Interpolating between +2 K and +4 K is a
   different and much easier question than extrapolating to +6 K, and only the second one is the
   question. `holdout_perturbation` exists for this.
3. **Derive each null's `expected.value` and say where it came from.** Not "we will see what it
   returns" — the registry rejects that (E02), because a null that silently misbehaves is otherwise
   indistinguishable from a null that agreed with you.
4. **Do not guard it on an R² floor.** The Bernoulli realisation noise is ~28 % of residual variance,
   so a single-draw R² is near-saturated and cannot discriminate arms. Score the ensemble
   expectation, and state the patch count (25 in all existing data; acceptance grade is ~125–192).

Then `tools/seal_experiment.py <id>` and commit. It cannot be launched until it is sealed and
committed, and any later edit turns CI red. When line D's pilot corpus lands, fill in
`data.corpus_sha256` — **which means you seal AFTER the corpus manifest exists**, so the sequence is:
draft now, corpus lands, set the hash, seal, launch.

Housekeeping: none owed. Refresh this block before you end.

## Milestones

**X1 — rung 1's pre-registration (OPEN, draftable today).** The kill test. Draft it now; seal it when
the pilot corpus manifest exists.

**X2 — rung 2: does the equilibrium map meet the acceptance bar? (blocked on X1).** Per-cell counts
AND trait distributions AND trait medians, conjunctively, within `max(10 %, the two-seed spread)`.
Report the fraction of cells inside the band, never a mean.

**X3 — rung 5: the held-out forcing leg (blocked on X2).** The low-emissions scenario is the test a
memorised warming pattern must fail: it warms 0.227× of the high leg on a common baseline, its
spatial pattern correlates only 0.19–0.22 with it, and 15–26 % of scored cells *cool*. ⚠ Gate its
binary build provenance first — it was produced by a different build from the other legs.

## Line X gotchas

*(none yet)*
