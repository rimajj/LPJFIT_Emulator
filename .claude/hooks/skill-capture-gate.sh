#!/usr/bin/env bash
# PostToolUse[Bash] — after a commit, ask whether it should have captured knowledge.
#
# Non-blocking on purpose: this is a judgement call, and a blocking prompt on every commit would be
# resented. The predecessor's version said "this project UNDER-creates skills"; with a hard cap in
# force the honest bias flips to "capture, but pay for it by merging or deleting one".
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ "$CMD" =~ git[[:space:]]+(-[^[:space:]]+[[:space:]]+)*commit ]] || exit 0
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
N=$(ls -d .claude/skills/*/ 2>/dev/null | wc -l | tr -d ' ')
L=$(cat .claude/skills/*/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
cat <<TXT

[capture] That commit is in. Did it contain any of:
  - a script you would run again              -> a skill (or a section of an existing one)
  - a non-obvious error and its fix           -> a skill's references/ file
  - a re-derivation of something already known-> the skill that should have told you: sharpen its
                                                 DESCRIPTION, do not write a second skill
  - a durable FACT rather than a procedure    -> one MEMORY.md row, or docs/reference/
  - a decision                                -> docs/decisions/<date>-<line>-<slug>.md
Capture it in a follow-up commit now, while you still remember why.
Skill budget: $N/14 skills, $L/2000 lines. At the cap, merge or delete one first.
TXT
exit 0
