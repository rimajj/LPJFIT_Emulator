#!/usr/bin/env bash
# PreCompact — the context is about to be summarised. Write the handoff NOW.
#
# Context exhaustion is precisely where the predecessor lost handoffs: the session kept working,
# then ended abruptly with its state only in a context that no longer exists. Compaction is a KNOWN
# EVENT, so it gets a hook rather than a hope.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
LINE=""; [[ "$BRANCH" == line/* ]] && LINE="${BRANCH#line/}"
cat <<TXT

[precompact] Context is about to be compacted. Before anything else:
  1. write lines/${LINE:-<line>}/STATE.md '## NEXT — start here' and COMMIT it
  2. make sure every campaign you launched has a ledger row (tools/campaigns.py status)
  3. make sure every harvested result has a verdict (tools/render_verdict.py <id>)
Anything not written to a file is about to stop existing.
TXT
exit 0
