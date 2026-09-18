# The cross-line inbox was exempt from the size budget forever, so two corpus-v2 asks rotted unseen

- **Status:** accepted; the gate change is applied and tested. The two rotted asks are NOT actioned
  here — see "What is deliberately left open".
- **Date:** 2026-09-18
- **Line:** INT
- **Governs:** `tools/check_budgets.py`, `tools/inbound.py`,
  `tests/test_budget_inbound_exemption.py`

## What was found

`lines/D/STATE.md` was **436 lines against a budget of 120**, and `tools/check_budgets.py` reported
the repository clean. `lines/T/STATE.md` was 358 and `lines/X/STATE.md` 287, likewise clean.

The cause is `_without_inbound`, added 2026-09-10. It removes every cross-line message block before
counting, and it had no expiry. Of D's 436 lines, **338 were 17 message blocks**, none of them
counted. The recipient's own durable state was 98 lines, comfortably inside budget, and it was the
inbox — not the state — that had grown without limit.

The exemption's premise is stated in its own docstring: *"an inbound is transient by construction --
it is read, actioned, and rotated away."* **Nothing made that true.** Rotation is
`tools/rotate_state.py`, which requires a human to first add an `## ARCHIVE` heading and move
blocks under it. A permanently exempt block generates no pressure to do that, so the inbox only ever
grew. This is invariant 9 precisely: a chore with a triggering event and no failing gate.

## The cost, which is not the line count

Two of D's uncounted blocks carried undischarged asks, **both of which specifically asked to be
landed in the corpus version bump because they get more expensive afterwards**, and the bump
(`v2-constco2`, 6,000 spin-ups, landed 2026-09-15) shipped without either. Verified in the source on
2026-09-18, not inferred from a document:

| ask | sent | state today |
|---|---|---|
| T → D: four soil columns (`soil_awc_mm`, `soil_w_avail`, `soil_sand`, `soil_clay`), because soil *type* sets how much water the column holds and only *depth* is carried | 2026-09-10 | **not landed.** `CLIMATE_FEATURES` still carries `soildepth` and none of the four. The ask notes this needs a corpus version bump, not an in-place edit |
| T → D: `_empty_summary` must write NaN, not 0.0, into `pft_frac_*` for a treeless cell | 2026-09-14 | **not landed.** `corpus/state.py:106` still re-blanks only the quantile and trait-mean columns. The read-time workaround `score.blank_treeless_composition` is still load-bearing at four call sites |

Meanwhile D's `## NEXT` block records corpus v2 as landed and its decisions as "closed this session,
do not re-open". Both statements are true of what D was tracking, and neither ask was in it.

## The decision

**A message is free for 14 days and counted after that.** `_without_inbound` now requires a parseable
date in the heading and exempts a block only while it is within `INBOUND_GRACE_DAYS = 14`.

The original rationale is preserved intact, and it was a real problem: a line sitting at 117 of 120
lines has three lines of headroom, a message block costs eight whatever it says, so charging it
immediately turns the recipient's build red through no action of their own, possibly for days before
they next open a session. That happened on 2026-09-10 and is why the exemption exists. The grace
window keeps exactly that protection and nothing more.

After the window the block is the recipient's own content, because by then one of two things is
true: it was read and actioned, and rotating it is the two-second chore the tool exists for; or it
was not, which is the thing actually worth failing a build over.

**14 days is not an arbitrary number.** It is the horizon `tools/rotate_state.py` already prints as
its own advice — "anything more than about two weeks old" belongs in the journal — so the gate and
the documented procedure now say the same thing.

**The constant is deliberately NOT in `config/budgets.toml`.** Editing that file requires the
owner-approval trailer, and this constant tightens the gate rather than lifting a cap; making it
owner-tunable is an owner act, not a side effect of this change.

**Precedent for a clock-driven gate:** `check_skill_hygiene` in the same file already fails a build
on elapsed time alone. This is the repository's existing shape, not a new one.

## Measured, at three dates

| date | D counted | T counted | X counted | budget 120 |
|---|---|---|---|---|
| 2026-09-18 (today) | 98 of 436 | 115 of 358 | 79 of 287 | all pass |
| 2026-09-25 | 141 | 115 | 79 | **D fails** |
| 2026-10-02 | 436 | 358 | 287 | **all three fail** |

So the change is green on the day it lands and forces each line to triage its own inbox within two
weeks of being messaged. The full suite is green (320 passed, 1 skipped).

## Also fixed here

`tools/inbound.py` resolved the sender from the branch name and turned any non-`line/` branch into
the literal `"?"`. Every message the integrator sent without remembering `--from INT` was headed
**"INBOUND from line ?"** — six such blocks were written on 2026-09-16 and are in the repository. A
recipient cannot reply to "?" and cannot tell whether it came from the integrator or from a line
that did not exist yet. `main` now resolves to `INT`, and an unrecognised branch is a refusal that
asks for `--from` rather than a silent unanswerable heading.

The same tool printed "their STATE.md has a 120-line budget -- if this pushes them over ... they
will have to rotate", which the exemption had already made false and this change makes true again in
a different way. It now says what is actually the case.

## What is deliberately left open

**Neither rotted ask is actioned here, and neither should be actioned casually.** Both change what
the corpus decoder produces, and line T's own message says the treeless fix "changes v0/v1 state
tables if they are ever re-decoded". Landing either now puts the committed `corpus.parquet` — 6,000
rows, sha256 pinned, the basis for re-scoring two rungs — out of agreement with the code that would
regenerate it. The choice between a fresh corpus version and accepting that skew has a real compute
cost and is the owner's, so it is reported rather than taken.

**The inboxes are not rotated here either.** Each line's blocks are its own to triage, and the gate
now makes that happen on a schedule instead of on someone noticing.
