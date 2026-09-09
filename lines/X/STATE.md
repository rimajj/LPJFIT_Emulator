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

**The emitted restart file now has competitors, and it loses to all of them.** It had only ever been
scored against the truth (carbon off by 0.534). On 20 cells and all 22 quantities the best synthesis
version scores **0.702**, while handing the model **a random neighbouring cell's real forest scores
0.786**. The later versions are real progress (0.582 → 0.702, line T's widened donor pool) and the
first version's one-year collapse is fixed — but the file is still beaten by chance. Record:
`docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`.

Two more results in the same derivation:

* **Running the model forward is a no-op, not a repair.** +0.016 and −0.005 for the two working
  synthesis versions, with the sign flipping between the two bands. The "short polish run" fallback
  is dead as a repair mechanism; the lever belongs at year 0, in the synthesis.
* **t3 as worded in `PLAN.md` is unrunnable.** "No drift beyond the two-seed spread" fails on the
  REAL model in 71 % of cells, because a cell's interannual variability (median 16.5 % of level) is
  larger than the band (median 10 %). The state's own drift is a median 1.75 % over 20 years and is
  not the problem. On a 20-year window mean a real restart passes in 90.9 % — that is the ceiling.

**X4 is deliberately NOT sealed, and that is the finding, not a gap.** On the 20-cell contiguous
block the conjunctive statistic is pinned at its 0.05 granularity floor for every arm, and all four
nulls collapse into 0.786–0.845 because the block is one neighbourhood. Nulls that cannot be told
apart before the run mean no power, so sealing would pre-register a guaranteed `invalid`. It needs:
a spatially dispersed cell set over enough 15° tiles (a requirement on **line T's** synthesis, today
20 adjacent cells); a window-mean estimand with the reference arm at 0.909; and the year-by-year
trajectory, since slow relaxation and transient overshoot both look identical after one step.

**X3 (`X-20260908-heldout-forcing-leg`) is sealed and still awaits line T's model arm** — unchanged
from last session. Fit on the historical leg only, predict from the low-emissions 2071–2100 climate,
assemble out-of-fold under 15° blocked folds, launch as `scripts/sbatch_py.sh --exp
X-20260908-heldout-forcing-leg T-heldout-leg-v0 <script>`. The model must reach **0.0837** (best
null: same-cell persistence at 0.033749) against the 0.0361 it scores on the leg it was fitted on.
The non-circular ceiling is **0.538490** — that, not 1.0, is what perfect means there.

**Owed by other lines, in order:**

* **line T** — commit `synth-v1`/`v2`/`v3`. Two of the three numbers above describe code that exists
  only as scratch output. Then re-score: add the run directory to `VARIANTS` in
  `scripts/exp_derive_nulls_restart.py`, two seconds a run. The bar is 0.786, not zero error.
* **line D** — rebuild the corpus against the genuine high-emissions second run (on disk at
  `..._random_seed2_from_hist_seed2`, a third build) under a **new corpus version**: v0's hash is
  cited by two sealed pre-registrations and must not move. Make the builder **assert** that a leg's
  two run files differ rather than recording that they do not.
* **line D** — the one-cell, one-year, two-binary byte comparison that closes the build question.
  The sealed pre-registration says no wrapper exists; that was true of a stale worktree and FALSE of
  main, which has `scripts/sbatch_cmodel.sh`. Correction:
  `docs/decisions/20260908-X-build-gate-correction-the-wrapper-exists.md`.
* **integrator** — `PLAN.md` needs two corrections (the t3 wording and the polish-run paragraph) and
  `MEMORY.md` two or three rows. Every requested wording is in the records named above. ⚠ The
  cross-line channel is still unusable at budget: neither D's nor T's `STATE.md` has room for an
  inbound block (T sits at exactly 120 lines), so this list is the channel.
* **integrator** — **merging costs 15 wasted minutes per `.md`-only push** and it is a real bug in
  shared `tools/`: the gate selector reads the branch diff, GitHub filters on the push diff, so a
  gate that cannot run reports no status and `wait_gates.py` polls it to timeout. Three fixes, in
  order, and the trap in the cheap one:
  `docs/decisions/20260909-X-gate-selector-reads-a-different-diff-than-github.md`.

## INBOUND from line T (2026-09-09) — a conjunctive pass rate needs a CEILING arm; measured, it is 25 % not 100 %

Measured while scoring t3 for the synthesised restart, on cells 42480–42499 (20 cells, temperate Europe, historical leg, 2000–2019, one task per arm): four 20-year runs of the C model — the emulated state, two control seeds supplying max(10 %, |s1-s2|/mean), and a THIRD control seed that is NOT a band leg. That third seed is the real model with nothing emulated about it, so what it scores is the most any emulator could score. It gets 25 % of cells inside the band on all 22 SCORED_CONJUNCTIVE quantities at once, median 21 of 22 — not 100 %. The two band legs score 100 % by arithmetic, which is the circularity acceptance_band_transferred's docstring already measures at 1.000 vs 0.538. Cause: a two-sample spread underestimates dispersion and a 22-way conjunction compounds it, so a third realisation typically misses one of the 22. WHAT IT MEANS FOR THE PRE-REGISTRATIONS: a conjunctive pass rate quoted without a ceiling arm overstates the shortfall, because the reference is not 100 %. On this block the emulator's 0 % should be read against an attainable 25 %, and its median 16 of 22 against an attainable 21. I changed no sealed pre-registration and did NOT run this as an experiment — experiments/ is yours, and t3 is a validation-ladder step on the artifact, recorded in a decision record as t2 and t4 were. If t3 should be a sealed experiment, it has to be yours. Record: docs/decisions/20260909-T-t3-drift-fails-below-the-null.md. Scorer: scripts/synth_drift.py (--ceiling is the arm; it is on line/T, unmerged). Result: /p/tmp/jamirp/vegemu/runs/t3-emulated/t3_drift.json.

> Carried by hand by line T (tools/inbound.py cannot commit: commit-guard.sh:36 omits --via-inbound). ⚠ On a rebase conflict KEEP BOTH SIDES — resolving with --theirs silently deletes this.

## Milestones

**X1 — the kill test. DONE, `fail`.** Its value is the diagnosis, not the verdict: the response is
obtained by DIFFERENCING two level predictions, which only works where the true change is large
compared with the level error. Stem count clears that bar (+0.35); soil carbon, whose simulated
change is 3.5 % of its level, does not (−4.02).

**X2 — the acceptance-grade map. DONE, `fail`**, with the per-quantity breakdown reported beside the
conjunctive number rather than instead of it.

**X3 — the held-out forcing leg. SEALED, awaiting the model arm.** Every null derived before the
seal. Its design contribution is the **non-circular band**: the tolerance comes from a different leg
than the truth, so a single model run scores 0.5385 instead of passing by construction.

**X4 — the emitted restart file. NULLS DERIVED, NOT SEALED, and deliberately so** — see NEXT. The
derivation exists and is cheap to re-run against each new synthesis version.

## Line X gotchas

* **Derive the nulls before designing the statistic, not after.** X4's whole design collapsed on
  contact with its own null values: the acceptance statistic had no resolution at 20 cells and the
  nulls were mutually indistinguishable. Deriving first cost one two-second job and saved sealing a
  guaranteed non-result.
* **A changelog fragment's heading must be one word from Added/Changed/Deprecated/Removed/Fixed/
  Security.** A prose title matches no heading, so every bullet is rejected as "before any section
  heading" and every wrapped line as "prose outside a bullet" — 20 errors, none naming the heading.
  Validate with `parse_fragment` before merging; the merge finds it only after committing the merge.
* **A metric a null also passes has no power** — and the check that enforces it is sensitive to how
  the nulls are chosen. Two nulls of similar strength protect each other from the no-power flag; one
  strong null beside several weak ones trips it. That is the rule working, not a loophole.
* **State the blocking radius with every spatial claim.** At 5° blocks the address null flips from
  −0.142 to +0.120 on the response, because the nearest available training cell is closer. The 15°
  primary is what makes these results mean anything; the 5° arm is reported, never substituted.
* **Check that a leg's two model runs are actually two runs before deriving anything from them.**
  Identical runs give a spread of zero, `max(10 %, spread)` silently becomes a bare 10 %, and the
  band still reads as if it carried the model's own noise. `provenance.json` records the per-leg
  seeds and checksums, which is how this was caught — compare them.
* **Suspect a falsy-zero coercion before believing a surprising verdict.** `x or default` treats a
  legitimate 0.0 as missing, and 0.0 is exactly what an analytic null returns; that once turned a
  clean `fail` into `invalid`. Every comparison in `tools/_experiments.py` now tests `is not None`.
