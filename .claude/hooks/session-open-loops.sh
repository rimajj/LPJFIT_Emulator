#!/usr/bin/env bash
# SessionStart — the one place a rotting chore becomes visible. Prints only non-empty items.
#
# Each item here is a chore the predecessor lost track of: an experiment sealed and never run, a
# result never written up, a changelog fragment never folded in, an opt-in flag never flipped. The
# lesson it drew, generalised: every chore needs a triggering EVENT and a VISIBILITY mechanism.
# This is the visibility half.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
LINE=""; [[ "$BRANCH" == line/* ]] && LINE="${BRANCH#line/}"
OUT=""

# Experiments: sealed with no results / results with no verdict / stale generated block.
if [[ -d experiments ]]; then
  for d in experiments/*/; do
    id="$(basename "$d")"; [[ "$id" == _* ]] && continue
    [[ -f "$d/preregistration.yaml" ]] || continue
    grep -q '^status: sealed' "$d/preregistration.yaml" 2>/dev/null || continue
    if [[ ! -s "$d/result.jsonl" ]]; then
      OUT="$OUT
  exp $id: sealed, no results yet -> launch it, or add 'abandoned: <reason>'"
    elif [[ ! -f "$d/verdict.md" ]]; then
      OUT="$OUT
  exp $id: has results but NO VERDICT -> tools/render_verdict.py $id"
    elif ! python3 tools/render_verdict.py "$id" --check >/dev/null 2>&1; then
      OUT="$OUT
  exp $id: verdict metrics block is STALE -> tools/render_verdict.py $id"
    fi
  done
fi

# Changelog fragments: correct on a line, debt on main.
if [[ "$BRANCH" == "main" ]] && compgen -G "changelog.d/*.md" >/dev/null 2>&1; then
  n=$(ls changelog.d/*.md 2>/dev/null | grep -cv 'README.md$' || true)
  [[ "$n" -gt 0 ]] && OUT="$OUT
  $n uncollated changelog fragment(s) on main -> tools/collate_changelog.py"
fi

# Flags approaching or past their flip date.
FLAGS="$(python3 tools/check_flags.py 2>&1 | grep -E 'F0[123]' || true)"
[[ -n "$FLAGS" ]] && OUT="$OUT
  flags need a decision:
$(echo "$FLAGS" | sed 's/^/    /')"

# Document budget headroom, so compaction happens before the wall rather than at it.
if [[ -n "$LINE" && -f "lines/$LINE/STATE.md" ]]; then
  n=$(wc -l < "lines/$LINE/STATE.md")
  (( n * 100 / 120 >= 80 )) && OUT="$OUT
  lines/$LINE/STATE.md is $n/120 lines -> tools/rotate_state.py $LINE"
fi

[[ -n "$OUT" ]] && { echo; echo "OPEN LOOPS:$OUT"; }
exit 0
