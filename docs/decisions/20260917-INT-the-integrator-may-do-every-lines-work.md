# The integrator may do every line's work, and the rule that said otherwise was never enforced

- **Status:** accepted
- **Date:** 2026-09-17
- **Line:** INT
- **Governs:** `config/ownership.toml`, `CLAUDE.md` §Work lines, `.claude/hooks/session-line-context.sh`
- **Owner instruction, 2026-09-17**, verbatim: *"you are the master, the integrator, you are allowed
  to do everything also in every line's work!!! change the rules accordingly"*

## The decision

The integrator, working on `main`, may write any path in the repository, including another line's
`lines/<L>/**`, `journal/<L>/**`, `campaigns/<L>/**`, and any line's exclusive source tree. No
request-and-wait, no `tools/inbound.py` round trip.

## ⚠ Nothing was enforced that needed changing. The defect was the PROSE

Checked before editing anything, by staging a change to `lines/D/STATE.md` on `main` and running the
checker: **it passes**. The code has always agreed with the owner's instruction.

- `check_ownership.py` resolves the line from the branch name, so on `main` there is no line; its
  own docstring already said "On `main` the caller is the integrator and only O02/O03 can fire".
- `path-guard.sh` guards the another-line rule and the `config/` rule behind `[[ -n "$LINE" ]]`.

What was false was the text. The **session greeting printed at the start of every integrator
session** said this worktree was "for INTEGRATION and shared edits only", that "feature work does
not belong here", and that "`config/ownership.toml` enforces that, and the commit guard will refuse
it". The last clause is the damaging one: it is a specific, checkable claim about the enforcement,
and it was wrong. `CLAUDE.md` said `main` was "integration only" and that the only sanctioned
cross-line write was `tools/inbound.py`.

**So the cost was not blocked commits — it was sessions that never tried.** A session start that
asserts a refusal is as effective as the refusal, and cheaper to get wrong, because nothing tests a
greeting. This is the same shape as `MEMORY.md:doc-asserts-unverified` (CLAUDE.md named five skills;
one existed) and is why `B08` now fails an unresolvable pointer — an assertion in always-loaded prose
is load-bearing and was, until now, unchecked.

It also explains an item already on the record: `MEMORY.md:integrator-items-rot-silently` describes
lines filing requests to integrator-owned paths that nothing polls. The mirror image was true too —
the integrator believed it could not reach into a line, so items rotted in both directions.

## What still binds the integrator, and why it is not the same thing

Kept deliberately, and put to the owner as a separate choice, which they took:

1. an **accepted decision record** is immutable (`O03`) — supersede with a new record;
2. a **sealed pre-registration** is immutable, by hash — supersede with a new experiment id;
3. `campaigns/*/ledger.jsonl` and `experiments/*/result.jsonl` are **append-only**, written by tool.

These protect **evidence**, not territory. None has ever blocked work, because superseding is always
available, and each exists so that a result cannot be quietly improved after the fact. The owner's
instruction was about line boundaries; it was not an instruction to make the audit trail editable.

## Scheduling advice that survives, demoted from a rule

Prefer a line's own worktree while that line is being actively worked: one branch, one session, no
rebase races. That is now stated as scheduling, and nowhere as permission.

## Consequences

1. **The greeting, the runbook and the ownership map now say the same thing**, and the ownership map
   says *why* the exclusive rules exist — line against line, to keep merges conflict-free.
2. **Done in the same session on the same instruction:** all 40 open campaigns closed, each verified
   from the runs rather than from a document (6,602/6,602 spin-ups successful). They would have
   blocked every merge from 2026-09-22, and no line had closed one because the session that launched
   each had ended.
3. **An assertion about enforcement, printed by a hook, deserves a test.** None of the three claims
   in that greeting was checked by anything. Not fixed here; recorded as the next thing to fix in
   this area.
