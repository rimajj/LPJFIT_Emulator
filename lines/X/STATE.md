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

**A third experiment is sealed and ready to run: `X-20260908-heldout-forcing-leg`.** It asks whether
the map survives a forcing leg it has never seen — the low-emissions leg — scored with the same
statistic, the same 22 quantities and the same code as the map test, so the two numbers are directly
comparable. **All five nulls were derived before sealing**, and the bar they set is demanding:

| null | required return | note |
|---|---|---|
| **same-cell persistence** | **0.033749** | the decisive one: hand back today's forest |
| geographically nearest cell | 0.005426 | 0.007006 at 5° |
| climatically nearest analogue | 0.004688 | space-for-time, in its natural habitat |
| shuffled | 0.000632 | the chance rate of the metric |
| the average forest | 0.000000 | |

So the model must reach **0.0837** to pass, against the 0.0361 it scores on the leg it was fitted on.
The **non-circular ceiling is 0.538490** — that, not 1.0, is what "perfect" now means, because the
band no longer comes from the same two model runs whose average is the truth.

**Line T owes the model arm**: fit on the historical leg only, predict from the low-emissions
2071–2100 climate, assemble out-of-fold under 15° blocked folds, and launch as
`scripts/sbatch_py.sh --exp X-20260908-heldout-forcing-leg T-heldout-leg-v0 <script>`. The launcher
refuses anything else. Report both bands and both blocking radii; the failure MODE is pre-named in
the decision rule and is the informative part.

**Two findings landed this session, both from gating the build provenance before using the leg:**

1. **The build gate CLEARS the low-emissions leg.** Three builds, not two; the difference between
   the two that matter is 19 uncommitted source files whose every behavioural change is switched
   off unless an environment variable is set, and those job scripts do not set it. Byte-equality is
   NOT proven. `docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md`
2. ⚠ **The high-emissions leg has no second model run.** Its two "seed" tables are byte-identical
   across all 22 quantities and all 67,420 cells — the second run started from the FIRST run's own
   initial state. So a two-run average from it is a single draw, and a tolerance derived from it is
   the bare 10 % floor wearing the costume of "10 % or the model's own spread". The kill test's
   verdict stands and is NOT re-run. `docs/decisions/20260908-X-ssp370-has-no-second-seed.md`

**Owed by other lines, in order:**

* **line D** — rebuild the corpus against the genuine high-emissions second run (on disk, at
  `..._random_seed2_from_hist_seed2`, from a third build), under a **new corpus version**: v0's hash
  is cited by two sealed pre-registrations and must not move. Make the builder **assert** that a
  leg's two run files differ, rather than recording that they do not.
* **line D** — run the one-cell, one-year, two-binary byte comparison that would close the build
  question outright. ⚠ The sealed pre-registration says no wrapper exists for it; that was true of
  this 29-commit-stale worktree and FALSE of main, which already has `scripts/sbatch_cmodel.sh`.
  Nothing blocks the test. A sealed file cannot be edited, so the correction is
  `docs/decisions/20260908-X-build-gate-correction-the-wrapper-exists.md`.
* **integrator** — two `MEMORY.md` rows are now wrong or incomplete; both requested wordings are in
  the two records above.

**Merged to main and pushed**, with `--allow-red` recorded as a trailer: `lint` and `types` are red
**on main itself** in D- and T-owned files this diff never touches; it is green on all five gates it
can affect. The failure list went to `CHANGELOG.md` because **neither D's nor T's `STATE.md` has
room for an inbound block** (T sits at exactly 120 lines) — I tried, it broke all three budgets, I
backed it out. Tell the integrator: the cross-line channel is unusable at budget.

Housekeeping: none owed. The stale `origin` warning is deleted deliberately, as line INT asked:
the remote is settled and pushing works (`MEMORY.md:the-repo`, `repo-is-clean`).

## INBOUND from line INT (2026-09-08) — merging now refuses a red gate, and the gate poller had never once worked here

Nothing in this is a defect of yours — it is two changes to how merging works, and one measurement you should have. THE MEASUREMENT: main's code gates had never run on main (path filters, plus a history replacement that triggers no workflow at all), so I dispatched them by hand. main is GREEN on budgets, changelog, experiments, flags, campaigns, pathsafety and RED on lint and types, all of it merged in from lines D and T, both of whom now have their share with the evidence. THE CHANGE THAT AFFECTS YOU: `tools/merge.sh` no longer prints the gate list and advise, it REFUSES — it polls the pushed sha and stops unless every triggered gate is green, with a sha whose status cannot be determined counting as not green. A prose-only commit triggers nothing and passes instantly, so a pre-registration or a verdict still merges immediately; the override is `tools/merge.sh X --allow-red 'reason'`, recorded as a trailer in the merge commit. THE ONE MOST RELEVANT TO YOUR OWN GOTCHA LIST: `tools/wait_gates.py` had never once worked in this repository. It built the API address from the remote URL and dropped the OWNER for the `git@host:owner/repo` form, so every request 404'd — and because `HTTPError` is a subclass of `URLError`, that 404 was retried as a transient hiccup until the timeout, whose message is "still pending". A permanently wrong address and a genuinely slow gate printed the same words. That is the third instance in this repo of one calm message covering two opposite states (empty vs uncomputable diff; 0.0 score vs missing score; 404 vs pending), and it is now a MEMORY row (two-states-one-message) precisely because your line keeps finding this class. Please also DELETE the warning in your NEXT block saying origin points at the predecessor and needs an owner decision: that is settled (MEMORY.md:the-repo, repo-is-clean), pushing works, and re-asking it is the one thing the owner said never to re-ask. Record: docs/decisions/20260908-INT-main-was-red-and-no-one-could-tell.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

**Acted on (2026-09-08, line X):** the `origin` warning is deleted from NEXT above. The
`two-states-one-message` row is this line's own gotcha and is kept as one.

## Milestones

**X1 — the kill test. DONE, sealed before the run, verdict `fail`.** Its value is not the verdict
but the diagnosis: the response is obtained by DIFFERENCING two level predictions, which only works
where the true change is large compared with the level error. Stem count clears that bar (+0.35);
soil carbon, whose simulated change is 3.5 % of its level, does not (−4.02).

**X2 — the acceptance-grade map. DONE, verdict `fail`**, with the per-quantity breakdown reported
beside the conjunctive number rather than instead of it.

**X3 — the held-out forcing leg. SEALED, awaiting the model arm.** Every null derived before the
seal, the decisive one being persistence at 0.033749. Its design contribution is the **non-circular
band**: the tolerance comes from a different leg than the truth, so a single model run scores 0.5385
instead of passing by construction.

**X4 — a pre-registration for the emitted restart file (OPEN).** The artifact now exists and passes
t0–t2 of the validation ladder; t3 (20-year drift inside the two-seed spread) and t5 (end to end)
are pre-registrable claims and nobody has written them down yet.

## Line X gotchas

* **A metric a null also passes has no power** — and the check that enforces it is sensitive to how
  the nulls are chosen. Two nulls of similar strength protect each other from the no-power flag;
  one strong null beside several weak ones trips it. That is not a loophole, it is the rule working:
  it says the metric cannot separate the model from a thing that knows nothing.
* **State the blocking radius with every spatial claim.** At 5° blocks the address null flips from
  −0.142 to +0.120 on the response, because the nearest available training cell is closer. The 15°
  primary is what makes these results mean anything, and the 5° arm is reported, never substituted.
* **Check that a leg's two model runs are actually two runs, before deriving anything from them.**
  Identical runs give a spread of zero, `max(10 %, spread)` silently becomes a bare 10 %, and the
  band still reads as if it carried the model's own noise. `provenance.json` records the per-leg
  random seeds and checksums, which is how this was caught — compare them.
* **Suspect a falsy-zero coercion before believing a surprising verdict.** `x or default` treats a
  legitimate 0.0 as missing, and 0.0 is exactly what an analytic null is built to return; that once
  turned a clean `fail` into `invalid`. Every comparison in `tools/_experiments.py` now tests
  `is not None`.
