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

**Two experiments are sealed, run, harvested and rendered. Both FAIL. Every null returned its
pre-registered value**, so neither is `invalid`: the apparatus did what was declared and these are
failures of the model, not of the measurement.

| experiment | model | best null | margin | gate | outcome |
|---|---|---|---|---|---|
| `X-20260908-climate-state-map` | 0.0361 | 0.0212 | +0.0149 | > 0.050 | **fail** |
| `X-20260908-warming-response` | −0.7271 | +0.0162 | −0.7433 | > 0.050 | **fail** |

**The design choice worth reusing: every null is a deterministic function of the corpus and the
fold assignment, with no learner and no free parameters.** That is what made it possible to DERIVE
each null's required value before the run instead of guessing it — `scripts/exp_derive_nulls.py`,
and all eight values came back exact. The address null is a spatial nearest neighbour rather than a
latitude/longitude regression for the same reason, and it is the stronger null besides.

**Next, in order:**

1. **Write the third pre-registration: the HELD-OUT FORCING LEG.** The low-emissions leg is on disk
   and untouched. It warms 0.227× of the high leg on a common baseline, its spatial pattern
   correlates only 0.19–0.22 with it, and 15–26 % of scored cells cool — so a model that memorised
   the high-emissions pattern must fail it. ⚠ Gate the build provenance FIRST: that leg came from
   an Aug-12 binary build while historical and ssp370-seed1 came from the Feb-05 build, so a delta
   involving it carries an unquantified confound and the pre-registration must say so.
2. **Do not re-run either sealed experiment with a changed model.** A changed question or a changed
   model is a NEW `exp_id` that names the old one in `supersedes:`. The registry hashes the sealed
   file precisely so this cannot happen unnoticed.
3. **The next response experiment is blocked on line D's pilot corpus**, and that is now the
   finding rather than a scheduling note: the response failed because the training corpus holds one
   climate per location, so the target must become the CHANGE itself, which needs the same cell
   under many climates. `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
4. **Consider a non-circular acceptance band.** The band is currently derived from the same two
   seeds whose mean is the truth, so the single-realisation arm sits at exactly half a band and
   always passes — it is reported as a CEILING, not a null, and the circularity is disclosed in the
   estimand. A band built from a DIFFERENT leg's two-seed spread would break the circle and is
   available today.

⚠ A falsy-zero bug in the verdict engine reported the response experiment as `invalid` before it
was fixed: `x or default` treats a legitimate 0.0 as missing, and 0.0 is exactly what an analytic
null returns. Every comparison in `tools/_experiments.py` now tests `is not None`. If a verdict
ever looks surprising, check for that class of coercion before believing it.

⚠ `origin` points at the predecessor's GitHub repository and shares no ancestor with this history,
so nothing has been pushed; everything is merged into LOCAL `main`. Owner decision needed.

Housekeeping: none owed.

## INBOUND from line INT (2026-09-08) — merging now refuses a red gate, and the gate poller had never once worked here

Nothing in this is a defect of yours — it is two changes to how merging works, and one measurement you should have. THE MEASUREMENT: main's code gates had never run on main (path filters, plus a history replacement that triggers no workflow at all), so I dispatched them by hand. main is GREEN on budgets, changelog, experiments, flags, campaigns, pathsafety and RED on lint and types, all of it merged in from lines D and T, both of whom now have their share with the evidence. THE CHANGE THAT AFFECTS YOU: `tools/merge.sh` no longer prints the gate list and advise, it REFUSES — it polls the pushed sha and stops unless every triggered gate is green, with a sha whose status cannot be determined counting as not green. A prose-only commit triggers nothing and passes instantly, so a pre-registration or a verdict still merges immediately; the override is `tools/merge.sh X --allow-red 'reason'`, recorded as a trailer in the merge commit. THE ONE MOST RELEVANT TO YOUR OWN GOTCHA LIST: `tools/wait_gates.py` had never once worked in this repository. It built the API address from the remote URL and dropped the OWNER for the `git@host:owner/repo` form, so every request 404'd — and because `HTTPError` is a subclass of `URLError`, that 404 was retried as a transient hiccup until the timeout, whose message is "still pending". A permanently wrong address and a genuinely slow gate printed the same words. That is the third instance in this repo of one calm message covering two opposite states (empty vs uncomputable diff; 0.0 score vs missing score; 404 vs pending), and it is now a MEMORY row (two-states-one-message) precisely because your line keeps finding this class. Please also DELETE the warning in your NEXT block saying origin points at the predecessor and needs an owner decision: that is settled (MEMORY.md:the-repo, repo-is-clean), pushing works, and re-asking it is the one thing the owner said never to re-ask. Record: docs/decisions/20260908-INT-main-was-red-and-no-one-could-tell.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**X1 — the kill test. DONE, sealed before the run, verdict `fail`.** Its value is not the verdict
but the diagnosis: the response is obtained by DIFFERENCING two level predictions, which only works
where the true change is large compared with the level error. Stem count clears that bar (+0.35);
soil carbon, whose simulated change is 3.5 % of its level, does not (−4.02).

**X2 — the acceptance-grade map. DONE, verdict `fail`**, with the per-quantity breakdown reported
beside the conjunctive number rather than instead of it.

**X3 — the held-out forcing leg (OPEN, draftable today).** See NEXT item 1.

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
