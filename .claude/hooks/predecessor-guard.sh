#!/usr/bin/env bash
# PreToolUse[Bash] — DENY any command that could modify the OLD project.
#
# THE OWNER'S CONSTRAINT, verbatim (2026-09-08): "the old project should not be changed in any way."
#
# The old project is the HYBRID physics/ML emulator. It is a different thing from this one, it is
# finished as far as this repo is concerned, and this repo exists to reuse what transfers from it
# (docs/reference/inherited.md) as an INDEPENDENT project. It lives in two places:
#
#   on disk    /p/projects/open/Jamir/esm_land_emulator + worktrees wt-{S,M,E,O,X}  # pathsafety: allow
#   on GitHub  rimajj/LPJmLFIT_Emulator, reached through the SSH alias `github-esm`
#
# ⚠ THE TWO REPOSITORY NAMES DIFFER BY TWO LETTERS, and that is the whole reason this hook exists:
#
#     rimajj/LPJmLFIT_Emulator   the OLD hybrid project   -> never write
#     rimajj/LPJFIT_Emulator     THIS project             -> normal target of every push
#
# A typo, or a copied command, lands on the wrong one. The names are far too close to leave to care.
#
# WHY A HOOK AND NOT A NOTE IN MEMORY.md. This repo's own finding, from the project it inherits
# from: every rule that was prose was violated, and every rule that was a hook or a gate held. A
# standing owner constraint with nothing enforcing it is prose.
#
# WHAT IS DELIBERATELY STILL ALLOWED: reading. The old project is the read-only archive of record --
# citing it is the point, so log, show, diff, status, grep, cat and find all pass untouched. Only
# MUTATION is denied.
#
# Escape hatch: ALLOW_PREDECESSOR_WRITE=1. It exists so the hook cannot become a dead end, but the
# owner instruction above is STANDING: do not use it without a new instruction from the owner that
# says, in their words, that the old project may be changed.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ -z "$CMD" ]] && exit 0
[[ -n "${ALLOW_PREDECESSOR_WRITE-}" ]] && exit 0

deny() {
  python3 - "$1" <<'PY'
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}))
PY
  exit 0
}

# --- What counts as "the old project" -------------------------------------------------------------
# The repository name is matched on LPJmLFIT, which is NOT a substring of this project's
# LPJFIT_Emulator, so the two can never be confused by this pattern.
# Defined ONCE and referenced everywhere below, including inside the denial messages. Repeating the
# literal was the first version, and it meant five copies of the one string that must never drift.
# Each definition carries the per-line marker tools/check_no_abs_paths.py prescribes for a file that
# has to NAME a forbidden pattern in order to enforce it.
OLD_REMOTE='github-esm|LPJmLFIT'
OLD_PATHS='/p/projects/open/Jamir/(esm_land_emulator|wt-[SMEOX])'  # pathsafety: allow (IS the refusal)
OLD_HUMAN='/p/projects/open/Jamir/esm_land_emulator + worktrees wt-{S,M,E,O,X}'  # pathsafety: allow

# --- What counts as mutation ----------------------------------------------------------------------
GIT_WRITE='push|commit|merge|rebase|reset|revert|cherry-pick|am|apply|checkout|switch|restore|stash|tag|gc|prune|clean|worktree|remote[[:space:]]+(add|set-url|remove|rename)|branch[[:space:]]+-[dDmM]|update-ref|filter-branch|fast-import'

# Verbs that touch the old tree WHEREVER its path appears in the command. `mv` belongs here, not
# with the copies below: moving a file OUT of the old tree still removes it from the old tree.
SH_DESTRUCTIVE='\brm\b|\bmv\b|\btee\b|\btruncate\b|\bdd\b|\bchmod\b|\bchown\b|\bmkdir\b|\btouch\b|\bln\b|sed[[:space:]]+-i|\bshred\b'

# Copy-like verbs leave the source untouched, so they are only a write when the old tree is the
# DESTINATION -- the last argument. This distinction is required, not a nicety: taking something
# FROM the old project INTO this one is the whole reusability plan, and it is what the denial
# message below tells you to do. A guard that forbade its own advice would just be worked around.
SH_COPY='\bcp\b|\brsync\b|\binstall\b'
LAST_ARG="${CMD##* }"

# 1. Anything that PUSHES to the old project's remote. This is the case that would rewrite published
#    history, so it is checked first and on its own.
if [[ "$CMD" =~ $OLD_REMOTE ]]; then
  if [[ "$CMD" =~ (^|[[:space:]])git([[:space:]]|.*[[:space:]])(push|remote[[:space:]]+(set-url|add|remove|rename)|update-ref) ]]; then
    deny "DENIED: this command writes to the OLD project's GitHub repository.

  rimajj/LPJmLFIT_Emulator  (SSH alias github-esm)  =  the OLD HYBRID emulator
  rimajj/LPJFIT_Emulator    (SSH alias github-lpjfit) =  THIS project

The owner's standing instruction is that the old project must not be changed in any way. The two
repository names differ by two letters, which is exactly how a command ends up on the wrong one.

If you meant to push THIS project, the remote is already correct -- just use:
  git push --force-with-lease origin <branch>
and never name the other repository or its alias in a push at all."
  fi
fi

# 2. Any mutation of the old project's working trees on disk.
if [[ "$CMD" =~ $OLD_PATHS ]]; then
  WRITES=0
  [[ "$CMD" =~ (^|[[:space:]])git([[:space:]]|.*[[:space:]])($GIT_WRITE) ]] && WRITES=1
  [[ "$CMD" =~ ($SH_DESTRUCTIVE) ]] && WRITES=1
  [[ "$CMD" =~ ($SH_COPY) && "$LAST_ARG" =~ ^($OLD_PATHS) ]] && WRITES=1
  [[ "$CMD" =~ \>\>?[[:space:]]*($OLD_PATHS) ]] && WRITES=1
  if [[ "$WRITES" == 1 ]]; then
    deny "DENIED: this command modifies the OLD project's files on disk.

  $OLD_HUMAN
      = the OLD HYBRID emulator, a DIFFERENT project from this one

The owner's standing instruction is that it must not be changed in any way. It is the read-only
archive of record: cite it, never write to it.

READING it is fine and is the point -- git log, git show, git diff, git status, grep, cat and find
all pass. What transfers into this project is distilled in docs/reference/inherited.md; add to that
file here rather than reaching back into the old tree.

If you need something FROM there, copy it INTO this repo (destination inside this worktree), which
this hook allows, rather than editing anything over there."
  fi
fi
exit 0
