#!/usr/bin/env bash
# SessionStart — resolve the work line from the DIRECTORY this session launched in, and replay that
# line's handoff block verbatim.
#
# Line identity comes from the branch of the launch directory, so the human never has to state it
# and cannot get it wrong. The handoff is `## NEXT — start here` in lines/<L>/STATE.md: it is the
# entire mechanism by which one session continues another.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
# Recovery for the states where --abbrev-ref is useless. Both were earned the hard way in the
# predecessor: mid-rebase and detached HEAD both report "HEAD", which silently loses line identity.
if [[ "$BRANCH" == "HEAD" ]]; then
  if [[ -f .git/rebase-merge/head-name ]]; then
    BRANCH="$(sed 's|refs/heads/||' .git/rebase-merge/head-name)"
  else
    BRANCH="detached:$(basename "$PWD")"
  fi
fi
LINE=""
[[ "$BRANCH" == line/* ]] && LINE="${BRANCH#line/}"

# The worktree paths come from config/paths.yaml, never from a literal here. This message is the
# one that tells a human where to `cd`, so a hardcoded path that has gone stale sends the next
# session to the wrong checkout -- and a SessionStart hook must still never fail, hence the `||`
# fallback to the key name rather than an empty string.
worktree() { python3 "$REPO/tools/_paths.py" "project.worktrees.$1" 2>/dev/null || echo "<project.worktrees.$1 unresolved>"; }

echo "=== vegemu — a purely data-driven LPJmL-FIT state emulator ==="
if [[ -z "$LINE" ]]; then
  cat <<TXT
LINE: none (branch $BRANCH, integrator worktree).

You are the INTEGRATOR, and on the owner's instruction of 2026-09-17 you may do ANY line's work
from here. Nothing in config/ownership.toml stops you: line exclusivity is line-vs-line and has
never fired on main. The text that used to sit here said the opposite, and it was simply wrong.

Three rules still bind you, and none is about ownership -- they protect evidence, not territory:
  * an ACCEPTED decision record is immutable; supersede it with a new one
  * a SEALED pre-registration is immutable; supersede it with a new experiment id
  * campaigns/*/ledger.jsonl and experiments/*/result.jsonl are append-only, written by tool

Still PREFER a line's own worktree when that line is being actively worked -- one branch, one
session, no rebase races. Scheduling advice now, not a permission boundary:
  cd $(worktree D)   # line D — data: binary formats, corpus generation, provenance
  cd $(worktree T)   # line T — training: models, GPU, inference
  cd $(worktree X)   # line X — experiments: pre-registrations, nulls, verdicts
TXT
  exit 0
fi

STATE="lines/$LINE/STATE.md"
AHEAD="$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo '?')"
BEHIND="$(git rev-list --count "HEAD..origin/main" 2>/dev/null || echo '?')"
DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "LINE: $LINE   branch: $BRANCH   ahead/behind origin/main: $AHEAD/$BEHIND   uncommitted: $DIRTY"
[[ "$BEHIND" != "0" && "$BEHIND" != "?" ]] && echo "  -> rebase first: git pull --rebase origin main"
echo
echo "Protocol: CLAUDE.md (short by design). Ownership: config/ownership.toml. Before merging, run"
echo "tools/expected_gates.py -- it computes which CI gates this diff triggers, so you never poll"
echo "for a check that will not appear."
echo

if [[ ! -f "$STATE" ]]; then
  echo "!! $STATE does not exist. Create it from another line's file and write a NEXT block."
  exit 0
fi

# Extract the handoff verbatim. Fence-aware: a '## ' inside a fenced code block must not be mistaken
# for the end of the section (that bug truncated a predecessor handoff mid-command).
awk '
  /^## NEXT — start here$/ { inblk=1 }
  inblk {
    if ($0 ~ /^```/) { fence = !fence }
    if (!fence && /^## / && !/^## NEXT — start here$/) { exit }
    print
  }
' "$STATE" || true

if ! grep -q '^## NEXT — start here$' "$STATE"; then
  cat <<TXT

!! No '## NEXT — start here' block in $STATE.
   The previous session ended without writing a handoff, so there is no continuity to replay.
   Read PLAN.md for the rung ladder and this line's scope, decide what is next, and write the
   block before you end. Do NOT invent continuity that was never recorded.
TXT
fi
