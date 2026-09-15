# A named skill must exist

- **Date:** 2026-09-15
- **Line:** INT (integrator)
- **Status:** accepted
- **Touches:** `CLAUDE.md`, `.claude/hooks/session-line-context.sh`, `.claude/skills/experiment-registry/`,
  `tools/check_budgets.py`, `tests/test_skill_refs.py`, `.github/gates.toml`, `.github/workflows/budgets.yml`

## Context

`CLAUDE.md` named five skills — `experiment-registry`, `method-discipline`, `commit-and-merge`,
`slurm-campaign`, `skill-creator`. One of them existed (`cmodel-run`, which the runbook does not
name). Nothing checked the other four.

Two of the dangling names were printed **at runtime**, not merely written in a document:

- `.claude/hooks/session-line-context.sh` printed `Skill: commit-and-merge.` at **every session
  start**, on every line.
- `.claude/hooks/slurm-guard.sh` printed `Skill: experiment-registry.` inside the body of a
  **deny** — so an agent was blocked from submitting a job and, in the same breath, sent to a page
  that did not exist.

This was seen twice from opposite directions and fixed neither time. Line T recorded it on
2026-09-09: *"the skills are referenced everywhere and enforced nowhere … `.claude/skills/**` is
shared-owned so a line MAY create them, but inventing five procedures under a 14-slot cap is an
owner call, not a line's. Raised, not fixed."* Line X hit the same edge on 2026-09-15 from the other
side: E12 changed behaviour, and its documented home turned out not to exist.

This is invariant 9 violated in the plainest way — a chore with a triggering event and no failing
gate — and it is this repository's recurring bug in a new place: **documentation asserting a fact
that nothing verifies.** It is the same shape as `guard-reads-wrong-input`, one level up: there a
guard judged the wrong input, here a document asserted an unchecked one.

## Decision

**A `Skill:` or `Method:` pointer must name a skill that exists. `B08` fails the build otherwise.**

`tools/check_budgets.py` scans `CLAUDE.md`, `.claude/hooks/*.sh` and `.claude/skills/*/SKILL.md`
for the pointer form those files actually use, and requires `.claude/skills/<name>/SKILL.md` to be
present. The check is **repo-wide, not per-file**: the pointer and the page it names are almost
never in the same diff, so a `--staged` run restricted to changed files would miss every real case.

Three consequences follow, and all three are part of this decision.

### 1. `experiment-registry` is written, because its content was derivable

It is now `.claude/skills/experiment-registry/SKILL.md` (112 lines): the five-command lifecycle, all
fourteen codes with the fix for each, and E12's three distinct messages told apart — bytes never
committed, a seal that genuinely postdates its run, and a shallow clone, which is *not a finding*.

Nothing in it was invented. Every code and every hint is transcribed from the branches of
`tools/check_experiments.py` that emit them, and the page says that file is the authority if the two
ever disagree. A deny hook already pointed here, which made it the highest-value of the four.

### 2. The other three pointers are removed rather than written

`method-discipline`, `commit-and-merge` and `slurm-campaign` were never written, and T was right
that inventing three procedures speculatively is not a line's call — nor an integrator's. Each
pointer also sat at the end of a `CLAUDE.md` section that **already carries the procedure inline**
(`## Commit and merge`, `## Long jobs`, and invariants 1–5 respectively), so removing it loses no
content that a session ever had.

A pointer to a page that does not exist is worse than no pointer: it sends a blocked session hunting
for something unfindable. If any of the three is later wanted, `B08` does not obstruct writing it —
it only forbids naming it first. The `skill-creator` reference is reworded to name the actual act
(write `.claude/skills/<name>/SKILL.md`) rather than a tool that is not installed here.

### 3. The budgets gate now triggers on hook changes

`.claude/hooks/**` is a source `B08` scans, but the `budgets` gate did not run on it — so a commit
touching only a hook could introduce a dangling pointer and skip CI entirely. Added to
`.github/gates.toml` and `.github/workflows/budgets.yml` together, which `tools/check_gates.py`
requires.

## Consequences

- The runbook resolves. `python3 tools/check_budgets.py` is green, where it reported four dangling
  pointers before the change.
- `tests/test_skill_refs.py` (10 tests) pins both directions: a missing skill is a finding, a
  resolving one is silent, hooks and skill-to-skill cross-references are scanned, two pointers on
  one line are both caught, and ordinary prose does not match. The last test runs against the
  **real** tree, so re-introducing a dangling name fails locally as well as in CI.
- The kebab requirement (a name must contain a hyphen) is deliberate: a gate that cries wolf gets
  routed around, which is exactly the lesson E12 had to learn the same week.
- **Not decided here:** whether `method-discipline`, `commit-and-merge` and `slurm-campaign` should
  eventually exist. They are removed as pointers, not ruled out as pages. Two skills of fourteen are
  now used, so the cap is not the constraint.
