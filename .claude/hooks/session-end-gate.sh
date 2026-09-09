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
#
# ⚠ CAPTURED FIRST, NOT PIPED, AND THAT IS THE WHOLE POINT. This was
#     git log ... | grep -qE "..."
# under `set -o pipefail`, and it made the gate UNSATISFIABLE: `grep -q` exits at its FIRST match,
# `git log` is still writing (21 KB over eleven commits in the case that caught it), so `git log`
# takes SIGPIPE, `pipefail` promotes 141 to the pipeline's status, and the `if` is false however
# good the handoff is. Worse, it failed hardest for the sessions doing the right thing: `git log`
# emits newest-first, so refreshing the handoff in your LAST commit puts the match at the very top
# of the stream and guarantees the early exit.
#
# ⚠ AND IT ONLY REPRODUCES WHEN RUN AS A SCRIPT, which is how a hook runs. The identical pipeline
# typed into an interactive subshell returns 0 six times out of six; run as a script it returns 141
# six times out of six. So an inline check reports the bug fixed when it is not -- verify by
# executing this FILE, which `tests/test_session_end_gate.py` does.
LOG="$(git log origin/main..HEAD --name-only --format=%B 2>/dev/null || true)"
if grep -qE "lines/$LINE/STATE.md|NEXT: unchanged" <<<"$LOG"; then
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
