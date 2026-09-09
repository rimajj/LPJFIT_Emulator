# `git add … && git commit` in one command disables every commit-time checker

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** X
- **Kind:** a bug in shared `.claude/hooks/` and `tools/`, found by tripping it. Same class as
  `20260909-X-gate-selector-reads-a-different-diff-than-github.md`: a guard reading a different file
  set than the thing it protects.

## What happened

A decision record went in at 131 lines against its 120-line budget. Nothing stopped it locally; CI
caught it and turned `budgets` red, costing a merge cycle. Both of the two local defences that exist
precisely for this failed, for two independent reasons.

## Bug 1 — the commit guard inspects the index BEFORE the command runs

`.claude/hooks/commit-guard.sh` is `PreToolUse[Bash]`. It reads the staged set and bails early:

```bash
STAGED="$(git diff --cached --name-only --diff-filter=ACMR)"
[[ -z "$STAGED" ]] && exit 0
```

A `PreToolUse` hook fires **once, before the whole command**. So for the extremely natural

```bash
git add <paths> && git commit -m "…"
```

the index is still **empty** when the hook looks, `STAGED` is empty, and the guard exits 0 without
running `check_budgets`, `check_ownership`, `check_experiments`, `check_secrets` or the
silent-corruption lint subset. Verified directly:

```
$ git diff --cached --name-only --diff-filter=ACMR | wc -l
0
$ printf '%s' '{"tool_input":{"command":"git add docs/ && git commit -q -m x"}}' \
    | .claude/hooks/commit-guard.sh ; echo $?
0
```

**Every commit in this session used that form, so none of them was checked.** The guard only works
when `git add` has already happened in an earlier, separate command — which is a property of how the
caller happens to split their shell lines, not of anything the guard can see. It is worth being
precise about what this is not: the documented `ALLOW_COMMIT_GUARD_SKIP=1` escape hatch was never
used, and `ALLOW_LOGIN_HEAVY=1` (the login-node hook's escape) has no effect here — the guard's
command regex matches a leading `VAR=1` prefix perfectly well. The bypass is silent and needs no
opt-in, which is exactly what makes it worse than the escape hatch: a `Guard-skip:` trailer is
counted and reported by CI, and this leaves no trace at all.

## Bug 2 — `check_budgets` with no arguments cannot see a NEW file

`select_files` falls through to `tracked_files()`, i.e. `git ls-files`, which excludes untracked
paths. So a freshly written over-budget document passes the full local run and only starts failing
once it is committed — the moment it becomes too late. Measured on the same file, at 122 lines:

```
$ tools/check_budgets.py                      # exit 0  -- untracked, therefore invisible
$ tools/check_budgets.py docs/decisions/<it>   # exit 1  -- B01 122 lines, budget 120
```

`staged_files()` is fine (`--diff-filter=ACMR` includes adds); the hole is only in the default path,
which is the one a human runs by hand to check their work.

## Fixes, in order

1. **Make the guard fail closed on an empty index.** If the command contains a `git add`/`git stage`
   and the index is empty, the guard cannot know what will be committed, so it must not pass. Either
   deny with "stage in a separate step, then commit", or move the checks to a real `pre-commit` hook
   in `.githooks/`, which runs after staging by construction and cannot be defeated by shell
   grouping. **The `.githooks/` route is the correct one** — it removes the class rather than this
   instance, and `git commit` cannot outrun it.
2. **Make bare `check_budgets` include untracked files**, so "I checked before committing" means
   something. `tracked_files()` plus `git ls-files --others --exclude-standard` is the whole change,
   and the same fall-through is in every checker sharing `select_files`, so fix it in `_common.py`.
3. **A CI assertion that the guard is reachable**: commit something deliberately over budget in a
   fixture repo via `add && commit` and assert the guard denies. Without it this regresses invisibly,
   because a guard that silently passes looks exactly like a guard that found nothing.

⚠ **The trap in fixing only #1's cheap half.** Denying on "empty index plus a `git add` in the
command" still passes the equally common `git commit -am "…"`, which stages nothing beforehand and
never appears as a `git add`. Only the `.githooks/` route covers that.

## What this cost, and what it did not

One merge cycle, and a 131-line record in history at `934bc2e` that had to be rewritten in place.
It did **not** corrupt anything: CI caught the budget, which is the third of the three defences the
runbook names, and it held. The lesson is about the order of the defences, not their existence —
the two cheap local ones were both silently absent, so every over-budget or ownership-violating
commit this session reached CI unchecked, and only the gates that happened to be triggered ran.
