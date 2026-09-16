#!/usr/bin/env bash
# SessionStart — surface every open SLURM campaign for this line.
#
# THE GAP THIS CLOSES. Long jobs finish hours to days after the session that launched them has
# ended. No document a dead session could write makes a live session go and look. An injection at
# session start makes not-looking impossible.
#
# Degrades quietly: a slow or absent scheduler must never delay or break a session start.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
LINE=""; [[ "$BRANCH" == line/* ]] && LINE="${BRANCH#line/}"

# ⚠ SILENCE HERE USED TO MEAN EITHER "no open campaigns" OR "the replay could not run", and this
# hook is the ONLY thing that carries a launched job across the session boundary that launched it.
# Results land hours to days later, so a campaign nobody is told about is a campaign nobody harvests
# -- and an unharvested row blocks every merge once it goes overdue. `2>/dev/null || true` made the
# worse of those two states look exactly like the better one.
OUT="$(timeout 25 python3 tools/campaigns.py status ${LINE:+--line "$LINE"} --format hook 2>&1)"
RC=$?
if (( RC == 0 )); then
  [[ -n "$OUT" ]] && { echo; echo "$OUT"; }
else
  echo
  echo "⚠ THE CAMPAIGN REPLAY COULD NOT RUN (exit $RC). THIS IS NOT 'NO OPEN CAMPAIGNS'."
  [[ "$RC" == 124 ]] && echo "  It timed out after 25 s; the ledger may be large or the FS slow."
  printf '%s\n' "$OUT" | tail -3 | sed 's/^/  /'
  echo "  Any launched job is still out there. Check by hand: tools/campaigns.py status"
fi

# The sweeper's push inbox: results that arrived while nobody was looking.
INBOX="campaigns/.inbox"
if [[ -d "$INBOX" ]] && compgen -G "$INBOX/*.json" >/dev/null 2>&1; then
  echo
  echo "CAMPAIGN RESULTS THAT ARRIVED SINCE THE LAST SESSION ($INBOX):"
  for f in "$INBOX"/*.json; do
    python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(f\"  {d.get('tag','?'):24s} {d.get('event','?'):8s} {d.get('state','')} cpu={d.get('total_cpu','')}\")" "$f" 2>/dev/null
  done
  echo "  -> harvest or close each one, then: rm $INBOX/<tag>.json"
fi
exit 0
