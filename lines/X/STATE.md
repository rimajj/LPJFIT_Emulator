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

⚠ **Line X is 9 commits ahead of `main`, pushed but NOT merged.** `tools/merge.sh` refused cleanly
inside its lock: the shared checkout `/p/projects/open/Jamir/vegemu` has **uncommitted staged work**
(a Stop-hook SIGPIPE fix), untouched and not half-merged, but no line can merge until its owner
commits or stashes it. `main` is also red on `lint` — `ruff format` on three of line T's files,
handled with `--allow-red`. Both in `changelog.d/X-main-is-red-on-ruff-format.md`.

**The kill test is sealed and the bar is 0.225690.** Line D's pilot corpus (200 cells × 30 climates,
same cell, same seed, only the climate differs) removes the collinearity that made X1's `fail`
non-decisive. `X-20260909-pilot-warming-response` has seven nulls, all derived before any model
exists, and **the bar is not "no change" (0.0) but "every cell changes by the same fraction of what
it already has", 0.145690**, on the cell's own present forest. Record:
`docs/decisions/20260909-X-the-kill-test-bar-is-a-proportional-response.md`.

**Owed by line T, now the critical path: the model arm.** `scripts/sbatch_py.sh --exp
X-20260909-pilot-warming-response T-pilot-response-v0 <script>`. The model gets the held-out cell's
**control state** (disclosed — production always holds a real restart), its baseline climate and the
design point's five axis coefficients, and predicts the change in the seven quantities. Folds: 15°
blocked 5-fold seed 42 via `blocked_spatial_folds`, as derived. Re-derive any null in one job:
`scripts/exp_derive_nulls_pilot.py --version pilot-v1 --nproc 32 --degrees 15 --out <dir>`.

Three things that constrain how the result may be reported:

* **Copying another cell's response is worse than saying nothing changes** (nearest cell −0.281166,
  analogue −0.239753) — but the analogue gets +0.3292 on soil carbon and −0.6387 on stem count.
* **The per-level table (29 rows) is part of the result, not an appendix.** Only 40.5 % of cells are
  monotone in carbon across 0/+2/+4/+6 K; a pooled pass with a fail at >half the levels must say so.
* **380 of 6,000 runs (6.33 %) are treeless.** Counts and stocks keep those rows; the three trait
  medians score on 5,620 — where vegetation survived. Say the row count with every trait number.

**X3 (`X-20260908-heldout-forcing-leg`) is sealed and still awaits line T's model arm** — unchanged
for two sessions. Fit on the historical leg only, predict from the low-emissions 2071–2100 climate,
assemble out-of-fold under 15° blocked folds. `scripts/sbatch_py.sh --exp
X-20260908-heldout-forcing-leg T-heldout-leg-v0 <script>`. It must reach **0.0837** (best null:
same-cell persistence, 0.033749) against the 0.0361 it scores on the leg it was fitted on. The
non-circular ceiling is **0.538490** — that, not 1.0, is what perfect means there.

**X4 (the emitted restart file) stays unsealed; the pilot corpus is what will fix it.** Its blocker
was a 20-cell contiguous block on which all four nulls collapsed into 0.786–0.845. The pilot design
is the counter-example: 200 cells over 164 tiles, blocking radius moving the nulls <0.003. Once T
can synthesise for a dispersed cell set, X4 is re-derivable against it. Bar 0.786, not zero error.

**Owed by other lines, in order:**

* **line T** — the two model arms above, plus the still-owed `synth-v1`/`v2`/`v3` commit (they exist
  only as scratch output); then re-score via `VARIANTS` in `scripts/exp_derive_nulls_restart.py`.
* **line D** — rebuild the corpus against the genuine high-emissions second run
  (`..._random_seed2_from_hist_seed2`) under a **new corpus version**: v0's hash is cited by two
  sealed pre-registrations and must not move. Make the builder **assert** the two run files differ.
* **line D** — the one-cell, one-year, two-binary byte comparison closing the build question; the
  sealed wording is corrected in `docs/decisions/20260908-X-build-gate-correction-the-wrapper-exists.md`.
* **integrator** — `PLAN.md` still needs last session's two corrections (the t3 wording, the
  polish-run paragraph); `MEMORY.md` wants rows for the proportional-response bar and the
  ceiling-arm rule. ⚠ The cross-line channel is unusable at budget, so this list is the channel.
* **integrator** — two shared-`tools/` bugs, each a guard reading a different file set than it
  guards: **`git add … && git commit` in ONE command silently disables every commit-time checker**
  (`docs/decisions/20260909-X-the-commit-guard-sees-an-empty-index.md`), and the gate selector reads
  a different diff than GitHub, 15 min per `.md`-only push (`…-gate-selector-reads-a-different-diff-than-github.md`).

## Milestones

**X1 — the kill test on the ground-truth legs. DONE, `fail`.** Its value is the diagnosis: the
response is obtained by DIFFERENCING two level predictions, which only works where the true change is
large compared with the level error. Superseded as a *test* by X5, not as a record.

**X2 — the acceptance-grade map. DONE, `fail`**, with the per-quantity breakdown reported beside the
conjunctive number rather than instead of it.

**X3 — the held-out forcing leg. SEALED, awaiting the model arm.** Its design contribution is the
**non-circular band**: the tolerance comes from a different leg than the truth, so a single model run
scores 0.5385 instead of passing by construction.

**X4 — the emitted restart file. NULLS DERIVED, NOT SEALED, deliberately** — see NEXT.

**X5 — the kill test where the response is identified. SEALED 2026-09-09, awaiting the model arm.**
Seven nulls; the bar is 0.145690 and a pass needs 0.225690.

## Line X gotchas

* **Derive the nulls before designing the statistic, not after.** Twice now this has caught a dead
  experiment before it was sealed: X4's statistic had no resolution and its nulls were mutually
  indistinguishable; X5 would have inherited X1's `> 0.050` threshold, which **the best null itself
  satisfies by 0.000080** — a guaranteed `invalid` under E08, before any model was fitted.
* **A threshold is derived from the nulls, never inherited from a sibling experiment.** The no-power
  rule scores each null on the same comparator as the model, so under `model_minus_best_null` what
  matters is the gap between the best null and the *runner-up*, not the best null's own value.
* **A conjunctive pass rate needs a CEILING arm** (line T, measured): a third real model seed scores
  25 % of cells inside the band on all 22 quantities at once, not 100 %, because a two-sample spread
  underestimates dispersion and a 22-way conjunction compounds it. Quoting a shortfall against an
  implied 100 % overstates it. t3 correctly stays a validation-ladder step in a decision record
  (`20260909-T-t3-drift-fails-below-the-null.md`); if it ever becomes an experiment it is line X's.
* **A metric a null also passes has no power** — and the check is sensitive to how the nulls are
  chosen. Two nulls of similar strength protect each other; one strong null beside several weak ones
  trips it. That is the rule working, not a loophole.
* **State the blocking radius with every spatial claim.** At 5° blocks the address null flipped from
  −0.142 to +0.120 on the X2 response. On pilot-v1 it moves the nulls by <0.003, because 200 cells
  sit in 164 tiles — a property of the cell design, so it must be re-checked per corpus, never assumed.
* **Check that a leg's two model runs are actually two runs before deriving anything from them.**
  Identical runs give a spread of zero and `max(10 %, spread)` silently becomes a bare 10 %.
* **Suspect a falsy-zero coercion before believing a surprising verdict.** `x or default` treats a
  legitimate 0.0 as missing, and 0.0 is exactly what an analytic null returns.
* **polars is not fork-safe.** A worker pool forked after the parent touched polars sits at zero CPU
  with no error and no progress. Use spawn. Judge a silent job by `sacct` CPU time, never by its log.
