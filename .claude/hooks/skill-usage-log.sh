#!/usr/bin/env bash
# PostToolUse[Skill] — record that a skill was invoked, for the hygiene pass.
# Unused skills become visible at 30 days, warn at 60, and FAIL the budgets gate at 90.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
NAME="$(cat | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_input",{}).get("skill",""))' 2>/dev/null || true)"
[[ -z "$NAME" ]] && exit 0
printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NAME" >> "$REPO/.claude/skill-usage.log"
exit 0
