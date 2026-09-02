#!/usr/bin/env bash
# Stop — block ONCE if this session committed work without refreshing its handoff.
#
# WHY A BLOCKING HOOK. The predecessor put "refresh NEXT before your session ends" in a skill AND in
# the session-start injection, i.e. it asked twice, politely. A session that runs out of context or
# is simply stopped does not read either. The Stop event is the only place that fires at the actual
# moment, so it is the only place the duty can be enforced.
#
# Guarded by stop_hook_active so it can never loop.
set -uo pipefail
IN="$(cat)"
ACTIVE="$(echo "$IN" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("stop_hook_active",False))' 2>/dev/null || echo True)"
[[ "$ACTIVE" == "True" ]] && exit 0

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
[[ "$BRANCH" == line/* ]] || exit 0
LINE="${BRANCH#line/}"

# Commits made on this branch that are not yet on main.
N="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
[[ "$N" == "0" ]] && exit 0

# Did any of them touch the handoff? An explicit "NEXT: unchanged (<reason>)" also satisfies it.
if git log origin/main..HEAD --name-only --format=%B 2>/dev/null | grep -qE "lines/$LINE/STATE.md|NEXT: unchanged"; then
  exit 0
fi

python3 - "$LINE" "$N" <<'PY'
import json, sys
line, n = sys.argv[1], sys.argv[2]
print(json.dumps({"decision": "block", "reason": f"""This session made {n} commit(s) on line {line} but did not refresh its handoff.

Update the `## NEXT — start here` block in lines/{line}/STATE.md and commit it. That block IS the
handoff: the next session's start is generated from it verbatim, so anything not written there stops
existing. Say what you did, what you measured, what is still broken, and the single next action.

Also check: did you launch a SLURM campaign? It must have a ledger row (the wrapper writes one). Did
you harvest a result? It needs a verdict (tools/render_verdict.py <id>).

If there is genuinely nothing to hand off, say so in your last commit message with a line reading
  NEXT: unchanged (<reason>)"""}))
PY
exit 0
