#!/usr/bin/env bash
# PreToolUse[Write|Edit|MultiEdit] — DENY an edit to something that must not be edited.
#
# Catches the violation at the EDIT, hours before it would surface as a rebase conflict or a red
# gate. Each target is immutable for a stated reason:
#   the OLD project's tree    -> owner's standing instruction: it must not be changed in any way.
#                                Checked FIRST, because it is the only target that lies OUTSIDE this
#                                repo, and every rule below reasons about a repo-relative path -- so
#                                an absolute path into the old tree matched nothing and was allowed.
#   another line's files      -> per-line files are why 5 lines x 887 commits merged without a
#                                prose merge war in the predecessor
#   a sealed pre-registration -> "pre-registered" means nothing if it can be edited after the run
#   an append-only ledger     -> results and seals are evidence; append a correction, never rewrite
#   an accepted decision      -> supersede it; an audit trail that can be edited is not one
#   config/budgets|ownership  -> the caps and the map bind the agent; they are owner-owned
set -uo pipefail
FILE="$(cat | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"
[[ -z "$FILE" ]] && exit 0
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO" 2>/dev/null || exit 0
REL="${FILE#$REPO/}"
[[ -n "${VEGEMU_VIA_TOOL-}" ]] && exit 0

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
LINE=""; [[ "$BRANCH" == line/* ]] && LINE="${BRANCH#line/}"

deny() {
  python3 - "$1" <<'PY'
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}))
PY
  exit 0
}

# The OLD project's tree. Matched on the ABSOLUTE path, before REL is trusted for anything: REL is
# only meaningful for a file inside this repo, and for a path outside it REL is still the absolute
# path, which matched none of the patterns below and so sailed through.
OLD_TREES='/p/projects/open/Jamir/(esm_land_emulator|wt-[SMEOX])'  # pathsafety: allow (IS the refusal)
if [[ "$FILE" =~ ^${OLD_TREES}(/|$) ]]; then
  deny "$FILE is in the OLD project, which must not be changed in any way (owner, standing).

That tree is the hybrid emulator -- a DIFFERENT project from this one -- and it is the read-only
archive of record: cite it, never write to it.

What transfers into this project is distilled in docs/reference/inherited.md. Add what you learned
to that file, HERE, rather than editing anything over there. Reading the old tree is fine and is
the point."
fi

# Another line's exclusive files.
if [[ -n "$LINE" && "$REL" =~ ^(lines|journal|campaigns)/([A-Z])/ ]]; then
  OTHER="${BASH_REMATCH[2]}"
  if [[ "$OTHER" != "$LINE" ]]; then
    deny "$REL belongs to line $OTHER; this is line $LINE.

Per-line FILES (never shared sections) are what keep merges conflict-free. The ONE sanctioned
cross-line write is an inbound message:

  tools/inbound.py --to $OTHER --subject '<one line>' --body '<what they need to know>'

which appends a dated block to their STATE.md and mirrors it in yours."
  fi
fi

# A sealed pre-registration.
#
# NOTE on quoting: `deny` takes a double-quoted string, so BACKTICKS AND $(...) INSIDE THESE MESSAGES
# ARE EXECUTED BY BASH. An earlier version wrote `supersedes:` in markdown backticks and bash duly
# tried to run it, printing "supersedes:: command not found" above the actual denial. Keep these
# messages free of backticks and command substitution; precompute anything dynamic into a variable.
if [[ "$REL" =~ ^experiments/[^/]+/preregistration\.yaml$ ]] && grep -q '^status: sealed' "$FILE" 2>/dev/null; then
  EXP_DIR="${REL#experiments/}"; EXP_DIR="${EXP_DIR%%/*}"
  deny "$REL is SEALED and immutable.

Its hash is recorded in experiments/registry.jsonl and was stamped into the job that ran under it.
Editing it now would make the result unprovable -- which is the exact failure this registry exists
to prevent (gate code E04).

A changed question is a NEW experiment:
  cp -r experiments/$EXP_DIR experiments/<LINE>-<YYYYMMDD>-<slug>
then set the new one's 'supersedes:' field to name this experiment."
fi

# Append-only ledgers.
if [[ "$REL" =~ ^(experiments|campaigns)/.*\.jsonl$ ]]; then
  deny "$REL is APPEND-ONLY and is written by tool, never by hand:

  results    tools/append_result.py --exp <id> --from <metrics.json>
  seals      tools/seal_experiment.py <id>
  campaigns  tools/campaigns.py launch|probe|harvest|dead|abandon

The tools copy provenance (the pre-registration hash the JOB ran under, the commit, the job id) out
of the run itself rather than out of your working tree. Hand-editing loses exactly that, and the
gate reports it as a non-append-only ledger (E11)."
fi

# An accepted decision record.
#
# ⚠ KEEP THE WRITER BOUNDED, AND BOUNDED MEANS ONE SMALL WRITE -- NOT "under 64 KB". `head -15`
# emits ~667 bytes in a single write that lands before `grep -q` can quit at the first match --
# verified 12/12. Replace it with an unbounded reader (`cat`, `git log`) and this pipeline starts
# taking SIGPIPE under `pipefail`, the `if` goes false, and the guard fails OPEN: accepted records
# become editable with no message. That is exactly how `session-end-gate.sh` was broken.
#
# Do NOT reason "my writer emits less than the 64 KB pipe buffer, so it finishes first." Measured on
# line/X, the broken gate took SIGPIPE 6/6 at 15,841 bytes -- a quarter of the buffer. It is a race
# against a `grep -q` that exits on its FIRST match, not a buffer-capacity question, and a
# newest-first stream puts that match in the first few lines. If you need more than a couple of
# hundred bytes, capture into a variable first and grep the variable.
if [[ "$REL" =~ ^docs/decisions/.*\.md$ ]] && [[ -f "$FILE" ]] && head -15 "$FILE" | grep -qi 'status.*accepted'; then
  deny "$REL is an ACCEPTED decision record and is immutable.

Supersede it: write a new record that states what changed and why, and reference this one. An audit
trail that can be edited is not an audit trail."
fi

# Owner-owned config.
if [[ -n "$LINE" && "$REL" =~ ^config/(budgets|ownership)\.toml$ ]]; then
  deny "$REL is owner-owned and cannot be edited from line $LINE.

These files bind the agent editing them, so allowing a line to change them makes the whole scheme
circular. Raising a budget additionally requires the trailer 'Budget-change-approved-by: owner'.
Request the change; it lands on main."
fi
exit 0
