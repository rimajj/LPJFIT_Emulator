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
# ─── FIVE THINGS HERE ARE LOAD-BEARING ─────────────────────────────────────────────────────────
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
set -euo pipefail

LINE="${1:?usage: tools/merge.sh <LINE>}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INT="$(python3 "$REPO/tools/_paths.py" project.root)"
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

if ! python3 "$REPO/tools/campaigns.py" --check; then
  echo "merge: refusing -- an open campaign is past its harvest deadline (above)." >&2
  echo "  Harvest it, or close it with a reason:" >&2
  echo "    tools/campaigns.py harvest|dead|abandon --tag <tag> --reason '<why>'" >&2
  exit 1
fi

echo "merge: expected CI gates for this diff:"
python3 "$REPO/tools/expected_gates.py" | sed 's/^/  /'
echo "merge: (if any of those are not green on $LOCAL, stop now)"

# --- the locked section -------------------------------------------------------------------------
exec 9>"$LOCK"
echo "merge: taking the integration lock..."
flock 9

git -C "$INT" fetch origin --quiet
git -C "$INT" pull --ff-only origin main
git -C "$INT" merge --no-ff --no-edit "origin/line/$LINE"

# Chore (4). You hold the lock => you are the integrator for this moment. Editing CHANGELOG.md here
# does not violate "never edit it from a line": this is main, in the integration worktree.
( cd "$INT" && python3 tools/collate_changelog.py )
if ! git -C "$INT" diff --quiet -- CHANGELOG.md changelog.d; then
  git -C "$INT" add CHANGELOG.md changelog.d
  git -C "$INT" -c commit.gpgsign=false commit -q \
    -m "docs(changelog): collate changelog.d fragments into CHANGELOG.md"
fi

git -C "$INT" push origin main
echo "merge: line/$LINE is on main."
echo
echo "Now check main's OWN latest CI run. Green branch gates do not guarantee a green main: some"
echo "gates are whole-repo, and only the NEWEST main sha carries a verdict (a rapid follow-up push"
echo "can cancel an intermediate run). If the merge touched no gate-watched path, main runs nothing"
echo "either and there is nothing to check -- ask tools/expected_gates.py, do not guess."
