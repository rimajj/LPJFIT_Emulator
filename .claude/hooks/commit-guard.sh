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
cd "$REPO" 2>/dev/null || exit 0

STAGED="$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)"
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
