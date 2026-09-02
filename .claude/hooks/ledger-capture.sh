#!/usr/bin/env bash
# PostToolUse[Bash] — belt and braces for the one hole in the ledger.
#
# The wrapper writes its own launch row, but if it crashed AFTER sbatch returned a job id the job
# exists with no row. This notices that and prints the exact command to fix it.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ "$CMD" =~ (scripts/sbatch_[a-z_]+\.sh|ALLOW_RAW_SBATCH) ]] || exit 0
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
if [[ "$CMD" =~ ALLOW_RAW_SBATCH ]]; then
  cat <<'TXT'

[ledger] That was a RAW submission, so no wrapper wrote a ledger row. Record it now, or the job is
invisible to every later session:
  tools/campaigns.py launch --line <L> --tag <tag> --job <jobid> \
      --harvest-cmd '<how to collect it>' --harvest-by '<YYYY-MM-DDTHH:MM:SSZ>'
TXT
fi
exit 0
