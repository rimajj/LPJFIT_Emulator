#!/usr/bin/env bash
# PreToolUse[Bash] — DENY a `git commit` that violates an invariant.
#
# Runs the checkers against the STAGED set only, so the cost scales with the diff rather than the
# repo. Everything here was a prose rule in the predecessor, and every one of them was violated:
#   budgets (a doc over its cap, a prose row in MEMORY.md, a new root .md, the skill caps)
#   ownership (another line's exclusive path, an unowned path, an accepted decision record edited)
#   experiments (a sealed pre-registration modified, a result with no nulls)
#   the two silent-corruption lint rules
#   a hardcoded absolute cluster path
#   a credential literal
#
# Only the SILENT-CORRUPTION lint subset runs here (B905 zip-without-strict, B023 loop-variable
# closure, plus undefined/unused names). Full ruff is CI's job -- a guard that nags about formatting
# on every commit gets bypassed, and a bypassed guard is worse than none.
#
# Escape hatch: ALLOW_COMMIT_GUARD_SKIP=1, which requires a `Guard-skip: <reason>` trailer that CI
# counts and reports -- so a bypass is visible rather than free.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ "$CMD" =~ (^|[[:space:];&|])git[[:space:]]+(-[^[:space:]]+[[:space:]]+)*commit ]] || exit 0
[[ -n "${ALLOW_COMMIT_GUARD_SKIP-}" ]] && exit 0

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# The command with the ARGUMENTS OF PROSE-CARRYING FLAGS removed -- `-m`, `--message`, `--body`,
# `--subject`, `--reason`, `--allow-red`. Every rule below matches against THIS and never against
# $CMD, so no rule can be tripped by what a commit message happens to say. FAILS CLOSED: a command
# that will not lex, a missing or crashed lexer, and an empty result all fall back to the raw
# command, i.e. to the old broad matching, which can never widen into a bypass.
CMD_SCAN="$(printf '%s' "$CMD" | python3 "$(dirname "${BASH_SOURCE[0]}")/_lex_command.py" 2>/dev/null | tail -n +2)"
[[ -z "$CMD_SCAN" ]] && CMD_SCAN="$CMD"

cd "$REPO" 2>/dev/null || exit 0

# ⚠ FAIL CLOSED WHEN THE COMMAND STAGES ITS OWN FILES. A PreToolUse hook fires ONCE, before the
# whole command, so for the extremely natural `git add <paths> && git commit -m …` the index is
# still empty (or stale) when we look here. The guard used to read that empty index, conclude there
# was nothing to check and exit 0 -- silently, needing no opt-in, leaving none of the `Guard-skip:`
# trace CI counts. Every commit of the session that found it had used that form, so not one of them
# was ever checked (docs/decisions/20260909-X-the-commit-guard-sees-an-empty-index.md).
#
# Note this is NOT only an empty-index bug: even with a non-empty index, an inline `git add` adds
# files the guard never saw, so its verdict is about the wrong set either way. Hence the test is on
# the COMMAND, not on the index. Denying is right rather than merely safe -- staging in a separate
# step costs one extra tool call and makes the guard's view of the commit exactly correct.
#
# ⚠ ON THE SCAN, NOT ON $CMD, AND THAT DISTINCTION WAS A BUG FOR SIX DAYS. Until 2026-09-15 this
# line tested the RAW command, so a commit whose MESSAGE merely mentioned staging was refused as if
# it staged -- measured in both quote styles. The stripped copy already existed thirty lines below
# and was used only by the ` -a ` rule under it: the comment there states the principle correctly
# and the fix had been applied to the line beneath it rather than the line above. Found by being
# denied while committing the write-up of the sibling guard's defect, which is the fifth measured
# instance in this repo of ONE shape -- A GUARD MATCHING TEXT THAT IS NOT WHAT IT GUARDS.
#
# WHY NOT THE OLD `sed` THAT STRIPPED EVERY QUOTED STRING. Because a quoted string can BE the
# command: `bash -c "git add x && git commit -m y"` would then stop matching here, while the filter
# at the top still matched on the raw text -- dropping it straight through to the stale-index
# bypass this whole guard exists to prevent. Stripping only the ARGUMENT OF A PROSE FLAG keeps that
# case red and lets an ordinary commit message through. Shared lexer, one copy, see _lex_command.py.
if [[ "$CMD_SCAN" =~ (^|[[:space:];&|])git[[:space:]]+(add|stage)([[:space:]]|$) ]]; then
  python3 - <<'PY'
import json
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
  "permissionDecisionReason":"""Stage and commit in two separate commands.

This one command both stages files and commits them. A PreToolUse hook runs ONCE, before the whole
command, so the checkers would inspect the index as it is NOW -- before `git add` has run -- and
would pass judgement on the wrong set of files (usually an empty one, which reads as "nothing to
check" and lets everything through). That silent bypass is exactly what this guard exists to stop.

Do this instead:
  git add <paths>
  git commit -m "..."

The second command is then checked against the real staged set."""}}))
PY
  exit 0
fi

STAGED="$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)"
# `git commit -a` stages every tracked modification at commit time, so the index alone again
# understates what is about to land. That set IS knowable up front, so fold it in rather than deny.
# Prose is stripped first: otherwise a commit MESSAGE containing " -a " would widen the checked set
# and report findings about files the commit never touches -- the same shape of bug as the one
# above, which this repo has now hit five times. `--amend` cannot match: its `a` is not preceded by
# whitespace-then-single-dash.
#
# THIS USED TO HAVE ITS OWN `sed` that stripped every quoted string, and that private copy is what
# let the rule above drift: one rule stripped, the rule over it did not, and nothing tied them
# together. Both now read CMD_SCAN. Strictly this is the more conservative of the two -- a ` -a `
# inside a non-prose quoted string still widens the checked set, which over-checks rather than
# under-checks, and over-checking is the safe direction here.
if [[ "$CMD_SCAN" =~ (^|[[:space:]])(-[a-zA-Z]*a[a-zA-Z]*|--all)([[:space:]]|$) ]]; then
  STAGED="$(printf '%s\n%s' "$STAGED" "$(git diff --name-only --diff-filter=ACMR 2>/dev/null || true)" | sort -u | sed '/^$/d')"
fi
[[ -z "$STAGED" ]] && exit 0

FINDINGS=""
run() { local out; out="$($@ 2>&1)" || FINDINGS="$FINDINGS

$out"; }

run python3 tools/check_budgets.py --staged
run python3 tools/check_ownership.py --staged
run python3 tools/check_experiments.py --staged
run python3 tools/check_secrets.py --staged

PYFILES="$(echo "$STAGED" | grep '\.py$' || true)"
if [[ -n "$PYFILES" ]]; then
  # shellcheck disable=SC2086
  run python3 tools/check_no_abs_paths.py $PYFILES
  if command -v ruff >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    run ruff check --select B905,B023,F821,F811,E722 --force-exclude $PYFILES
  fi
fi
SHFILES="$(echo "$STAGED" | grep '\.sh$' || true)"
# shellcheck disable=SC2086
[[ -n "$SHFILES" ]] && run python3 tools/check_no_abs_paths.py $SHFILES

if [[ -n "$FINDINGS" ]]; then
  python3 - "$FINDINGS" <<'PY'
import json, sys
reason = f"""The commit guard refused this commit.
{sys.argv[1]}

Fix the findings above, or -- if a checker is genuinely wrong -- bypass it VISIBLY:
  ALLOW_COMMIT_GUARD_SKIP=1 git commit ...   and add a trailer:  Guard-skip: <why>

Every rule above was prose in the predecessor repo, and every one of them was violated. Two of the
lint rules are not style: a zip() without strict= silently truncates paired rows, and a closure over
a loop variable breaks silently the day it is called outside its iteration."""
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":reason}}))
PY
fi
exit 0
