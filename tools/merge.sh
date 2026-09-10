#!/usr/bin/env bash
# Merge a line into main, under a lock, with the integrator chores done inside it.
#
#   tools/merge.sh <LINE>
#
# ─── WHY IT IS A SCRIPT ────────────────────────────────────────────────────────────────────────
# The predecessor described this ritual in a 1,391-line skill. A 1,391-line skill describing a
# procedure is a script that was never written -- and the one chore inside it that had no code
# (collating changelog fragments) is the one that rotted for 13 days across 56 fragments.
#
# ─── SIX THINGS HERE ARE LOAD-BEARING ──────────────────────────────────────────────────────────
# 1. flock the integration worktree. It is the one shared checkout; without the lock, concurrent
#    lines interleave pull/merge/push in it and reintroduce exactly the contention that separate
#    worktrees were adopted to remove.
# 2. Merge `origin/line/<L>`, NOT the local branch. That is the sha CI actually verified; a
#    pre-rebase green verdict does not carry over to a post-rebase sha.
# 3. Never `git switch main` in a line worktree -- main is permanently checked out in the
#    integration worktree and git refuses (exit 128). Drive it with `git -C` instead, so nothing
#    ever leaves your own worktree and there is no "switch back" step to forget.
# 4. Collate the changelog INSIDE the lock. You hold the lock, so you are the integrator for this
#    moment; skipping it reds the `changelog` gate on main, and it is one command.
# 5. Refuse to merge past an overdue open campaign. A launched job nobody harvested is debt, and
#    main is where debt becomes everyone's.
# 6. Refuse to merge past a NON-GREEN gate, and verify main's own gates after the push. Both of
#    those used to be printed advice ("if any of those are not green, stop now" / "now check main's
#    own CI run"), and both were skipped -- three lines were merged while their gates had never run
#    at all, so main sat red on lint, types and test with nothing in the repository able to say so.
#    Advice that is followed only when convenient is not a guard.
set -euo pipefail

LINE="${1:?usage: tools/merge.sh <LINE> [--allow-red \"<reason>\"]}"
shift
ALLOW_RED=""
while (($#)); do
  case "$1" in
    --allow-red)
      ALLOW_RED="${2:?--allow-red needs a reason: it is written into the merge commit}"
      shift 2
      ;;
    *) echo "merge: unknown argument $1" >&2; exit 2 ;;
  esac
done
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- the two pythons ---------------------------------------------------------------------------
# `python3` on a login node here is 3.9, and every repo tool called below reaches tools/_common.py,
# which imports `tomllib` -- stdlib only from 3.11. So invoking them as bare `python3` makes this
# script die on a traceback in any shell with no environment activated, which is exactly the shell
# an agent starts in. tools/_paths.py is deliberately written against 3.9's stdlib alone, so it is
# the one thing the bootstrap interpreter may run, and it names the interpreter everything else
# wants.
#
# The same defect was found and fixed in scripts/sbatch_py.sh on 2026-09-10, where it had been
# losing the campaign ledger row on every launch from an unactivated shell -- silently, and after
# the job was already queued.
BOOTSTRAP_PY="python3"
PY="$($BOOTSTRAP_PY "$REPO/tools/_paths.py" cluster.python)" || {
  echo "merge: cannot resolve cluster.python from config/paths.yaml; refusing to guess." >&2
  exit 2
}
INT="$($BOOTSTRAP_PY "$REPO/tools/_paths.py" project.root)"
LOCK="$INT/.git/vegemu-integrate.lock"

command -v flock >/dev/null || { echo "merge: flock is required" >&2; exit 2; }

# --- pre-flight, in your own worktree, before taking the lock -----------------------------------
git -C "$REPO" fetch origin --quiet || { echo "merge: fetch failed; retry (SSH here is flaky)" >&2; exit 1; }

if [[ -n "$(git -C "$REPO" status --porcelain)" ]]; then
  echo "merge: worktree is dirty. Commit or stash first." >&2; exit 1
fi

BEHIND="$(git -C "$REPO" rev-list --count "HEAD..origin/main")"
if [[ "$BEHIND" != "0" ]]; then
  echo "merge: line/$LINE is $BEHIND commit(s) behind origin/main." >&2
  echo "  git pull --rebase origin main && git push --force-with-lease origin line/$LINE" >&2
  echo "  (the rebase rewrites already-pushed commits, so a plain push is rejected -- and git's own" >&2
  echo "   hint leads to a --no-rebase merge that DUPLICATES every rebased commit)" >&2
  exit 1
fi

LOCAL="$(git -C "$REPO" rev-parse HEAD)"
REMOTE="$(git -C "$REPO" rev-parse "origin/line/$LINE" 2>/dev/null || echo none)"
if [[ "$LOCAL" != "$REMOTE" ]]; then
  echo "merge: origin/line/$LINE ($REMOTE) is not your HEAD ($LOCAL)." >&2
  echo "  Push first: git push --force-with-lease origin line/$LINE" >&2
  echo "  We merge the pushed sha, because that is the one CI verified." >&2
  exit 1
fi

if ! "$PY" "$REPO/tools/campaigns.py" --check; then
  echo "merge: refusing -- an open campaign is past its harvest deadline (above)." >&2
  echo "  Harvest it, or close it with a reason:" >&2
  echo "    tools/campaigns.py harvest|dead|abandon --tag <tag> --reason '<why>'" >&2
  exit 1
fi

echo "merge: CI gates for this diff, on the pushed sha $LOCAL:"
"$PY" "$REPO/tools/expected_gates.py" | sed 's/^/  /'

# ENFORCED, not advised. wait_gates.py polls exactly the triggered gates and nothing else, so this
# does not hang on a prose-only commit: it exits 0 at once when the diff triggers nothing. Its exit
# 2 ("cannot tell which gates would run, or no API token") is a refusal too -- an unverifiable sha
# is not a green one.
if "$PY" "$REPO/tools/wait_gates.py" --timeout "${MERGE_GATE_TIMEOUT:-900}"; then
  :
else
  rc=$?
  echo >&2
  if [[ -z "$ALLOW_RED" ]]; then
    echo "merge: REFUSING -- the gates above are not green on $LOCAL (wait_gates exit $rc)." >&2
    echo "  Fix them on line/$LINE and push again. If the failure is not yours to fix, hand it to" >&2
    echo "  the owning line with tools/inbound.py rather than merging around it." >&2
    echo "  To merge anyway, say why -- it is recorded in the merge commit:" >&2
    echo "    tools/merge.sh $LINE --allow-red 'why this red gate is acceptable'" >&2
    exit 1
  fi
  echo "merge: PROCEEDING PAST A NON-GREEN GATE ON PURPOSE (wait_gates exit $rc)" >&2
  echo "  reason: $ALLOW_RED" >&2
fi

# --- the locked section -------------------------------------------------------------------------
exec 9>"$LOCK"
echo "merge: taking the integration lock..."
flock 9

git -C "$INT" fetch origin --quiet
git -C "$INT" pull --ff-only origin main

# main's pre-push sha, captured BEFORE the merge. It is the base GitHub filters the coming push on,
# and it is the only base from which main's own gate list can be computed: on main, a diff against
# origin/main is empty by construction, so asking the default question of main answers "no gate will
# run" forever. That is exactly how main came to sit red on three gates unnoticed.
PREV_MAIN="$(git -C "$INT" rev-parse HEAD)"

if [[ -n "$ALLOW_RED" ]]; then
  # Record the override where it cannot be lost: in the merge commit itself, as a trailer.
  git -C "$INT" merge --no-ff "origin/line/$LINE" \
    -m "Merge remote-tracking branch 'origin/line/$LINE'" \
    -m "Merged-with-red-gates: $ALLOW_RED"
else
  git -C "$INT" merge --no-ff --no-edit "origin/line/$LINE"
fi

# Chore (4). You hold the lock => you are the integrator for this moment. Editing CHANGELOG.md here
# does not violate "never edit it from a line": this is main, in the integration worktree.
( cd "$INT" && "$PY" tools/collate_changelog.py )
if ! git -C "$INT" diff --quiet -- CHANGELOG.md changelog.d; then
  git -C "$INT" add CHANGELOG.md changelog.d
  git -C "$INT" -c commit.gpgsign=false commit -q \
    -m "docs(changelog): collate changelog.d fragments into CHANGELOG.md"
fi

git -C "$INT" push origin main
echo "merge: line/$LINE is on main."
echo

# Green branch gates do not guarantee a green main: several gates are whole-repo, two lines can be
# individually green and jointly red, and only the NEWEST main sha carries a verdict. So verify
# main, from the base the push is filtered on. This cannot refuse anything -- main is already
# pushed -- but it makes main's status a REPORTED fact instead of a paragraph of advice, and the
# non-zero exit is what tells the session it owns a repair.
echo "merge: verifying main's own gates (base $PREV_MAIN)..."
if "$PY" "$INT/tools/wait_gates.py" --ref "$PREV_MAIN" --timeout "${MERGE_GATE_TIMEOUT:-900}"; then
  echo "merge: main is green on every gate this push triggered."
else
  rc=$?
  echo >&2
  echo "merge: ⚠ MAIN IS NOT GREEN (wait_gates exit $rc). line/$LINE is merged; the repair is now" >&2
  echo "  yours to make or to hand over. A gate that is red on main blocks nobody automatically," >&2
  echo "  which is precisely why it must not be left silent:" >&2
  echo "    - the failing file is yours      -> fix it on line/$LINE and merge again" >&2
  echo "    - it belongs to another line     -> tools/inbound.py, with the failing output quoted" >&2
  echo "    - it is the gate's own setup     -> it is integrator-owned; say so in MEMORY.md" >&2
  exit 1
fi
