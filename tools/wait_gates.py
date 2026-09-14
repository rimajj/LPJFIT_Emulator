#!/usr/bin/env python3
"""Poll CI for exactly the gates a diff triggers -- and refuse to poll for anything else.

    tools/wait_gates.py [--timeout 900] [--ref origin/main]

Asks `tools/expected_gates.py` which check-runs will appear, then polls only those. If the answer is
"none", it exits 0 immediately.

⚠ `--ref` IS LOAD-BEARING ON `main`. The default base answers "what does this branch add over
main?", which is the right question for a line and a VACUOUS one for main itself: on main the diff
against origin/main is empty by construction, so the default would report "no gate will run" for
every commit main ever carries. That is not a hypothetical -- main sat red on three gates while
nothing in the repository could say so. Pass the pre-push sha (`--ref <old main>`) to get main's own
gate list, which is what GitHub filters the push on.

WHY THE REFUSAL MATTERS. A workflow skipped by its path filter reports **no status at all**, not a
"skipped" status. So a loop written as "wait until `test` completes" hangs forever on a commit that
changed only prose -- which is most commits here. The predecessor hit this. Naming a gate this diff
cannot trigger is therefore an error, not a harmless request.

`gh` is not reliably on PATH, so this uses the REST API with the token from the user's gh config --
which lives outside every worktree on purpose (see docs/reference/cluster.md).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import expected_gates
from _common import BASE_OK, diff_base, repo_root

TOKEN_PATH = Path.home() / ".config" / "gh" / "hosts.yml"


def token() -> str | None:
    try:
        data = yaml.safe_load(TOKEN_PATH.read_text(encoding="utf-8")) or {}
        return data.get("github.com", {}).get("oauth_token")
    except Exception:
        return None


def remote_slug(root: Path) -> str | None:
    """`owner/repo` for `origin`, for every URL form git accepts.

    ⚠ THIS RETURNED `repo` WITHOUT THE OWNER for an scp-like SSH remote (`git@host:owner/repo.git`),
    which is the form in use here -- so every API request went to `/repos/LPJFIT_Emulator/...` and
    404'd, and the 404 was retried as a transient hiccup until the timeout. wait_gates had therefore
    never once polled successfully in this repository; it only ever timed out. The remote is also
    SSH-aliased (`git@github-lpjfit:...`), so the host is not literally `github.com` and cannot be
    matched on. Taking the LAST TWO path components is what makes all of the forms agree:

        git@host:owner/repo.git          ssh://git@host:22/owner/repo
        https://github.com/owner/repo    /local/path/owner/repo
    """
    url = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not url:
        return None
    url = url.removesuffix(".git")
    if "://" in url:
        url = url.split("://", 1)[1]
    if ":" in url:  # scp-like `host:path`, or a `host:port/path` left by the scheme strip
        url = url.split(":", 1)[1]
    parts = [p for p in url.strip("/").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def check_runs(slug: str, sha: str, tok: str) -> dict[str, str]:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{slug}/commits/{sha}/check-runs",
        headers={"Authorization": f"token {tok}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as fh:
        data = json.load(fh)
    out: dict[str, str] = {}
    for run in data.get("check_runs", []):
        name = str(run.get("name", ""))
        status = str(run.get("status", ""))
        concl = str(run.get("conclusion") or "")
        out[name] = concl if status == "completed" else status
    return out


REFUSAL_HELP = {
    404: "the slug is wrong, or the token cannot see this repository",
    401: f"the token in {TOKEN_PATH} is stale -- run `gh auth login`",
    403: "rate-limited, or the token lacks the checks scope",
}

# How far back to look for a still-valid verdict, and how long to wait before concluding that an
# absent gate is absent for good rather than merely slow.
INHERIT_MAX_BACK = 25
ABSENT_GRACE_S = 90
ABSENT_VERDICT_S = 180
GREEN = ("success", "neutral", "skipped")


def effective(job: str, runs: dict[str, str], inherited: dict[str, tuple[str, str]]) -> str | None:
    """This sha's own status for `job`, or an ancestor's when one may be carried forward."""
    own = runs.get(job)
    if own is not None:
        return own
    carried = inherited.get(job)
    return carried[1] if carried else None


def trigger_patterns(job: str, branch: str) -> list[str] | None:
    """The paths whose touching makes `job` run on `branch`; None if it never runs there."""
    gates, meta = expected_gates.load_gates()
    for g in gates:
        if str(g["job"]) != job:
            continue
        if not expected_gates.branch_matches(branch, list(g.get("branches", ["main"]))):
            return None
        return list(g.get("paths", [])) + list(meta.get("always", []))
    return None


def files_between(root: Path, a: str, b: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", f"{a}..{b}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def ancestors(root: Path, sha: str, limit: int) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "rev-list", f"--max-count={limit}", sha],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [ln.strip() for ln in out.splitlines() if ln.strip()][1:]


def inherited_verdict(
    job: str, branch: str, *, root: Path, slug: str, sha: str, tok: str
) -> tuple[str, str] | None:
    """The newest ancestor's verdict for `job`, when nothing since then could have changed it.

    ⚠ WHY THIS IS SOUND AND NOT A GUESS. GitHub decides whether a path-filtered workflow runs from
    the PUSH diff -- only the commits in that one push -- while `expected_gates` computes what a
    merge must verify from the whole BRANCH diff. Those differ whenever a branch is pushed more than
    once, which is every branch here, because protocol commits the handoff last and that final push
    is documentation-only. The gate then never runs on the head sha, reports NO STATUS AT ALL rather
    than "skipped", and a poll for it hangs to the timeout -- three merge attempts were lost to this
    on 2026-09-09 (docs/decisions/20260909-X-gate-selector-reads-a-different-diff-than-github.md).

    So: find the newest ancestor that actually carries a verdict for this gate, then require that
    NOTHING between that sha and this one touches the paths the gate filters on. If nothing does,
    GitHub's own filter says the gate would be skipped on every commit since -- so the old verdict
    still describes this tree, exactly as it describes the sha it ran on. The test uses the same
    `gates.toml` patterns and the same matcher that decide what to poll for in the first place, so
    it is no more trusted than the selection already is.

    Returns `(ancestor_sha, conclusion)`, or None when no verdict may be carried forward -- either
    because something since then DID touch the gate's paths (so it must really run) or because no
    ancestor in range ever ran it.
    """
    patterns = trigger_patterns(job, branch)
    if patterns is None:
        return None
    for anc in ancestors(root, sha, INHERIT_MAX_BACK):
        try:
            runs = check_runs(slug, anc, tok)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None
        verdict = runs.get(job)
        if verdict in (None, "queued", "in_progress"):
            continue
        changed = files_between(root, anc, sha)
        if any(expected_gates.glob_match(p, f) for f in changed for p in patterns):
            return None
        return anc, verdict
    return None


def poll(
    want: list[str],
    slug: str,
    sha: str,
    tok: str,
    *,
    timeout: int,
    interval: int,
    branch: str = "main",
    root: Path | None = None,
) -> int:
    """Poll `want` on `sha` until every one is green (0), one fails (1), or we cannot ask (2).

    Split out of `main` so each of those three exits stays a single, readable statement about the
    verdict rather than a branch buried in a retry loop -- `tools/merge.sh` now refuses a merge on
    anything but 0, so which exit is produced when is the contract.

    ⚠ AN ABSENT GATE IS NOT A SLOW GATE, and conflating them cost 15 minutes per merge. A gate with
    NO check-run at all may simply not have been triggered by this push, in which case waiting can
    never end. After `ABSENT_GRACE_S` each still-absent gate is resolved once against its ancestors
    (see `inherited_verdict`); whatever cannot be resolved that way gets a named diagnosis and a
    bounded second deadline rather than the full timeout.
    """
    deadline = time.time() + timeout
    started = time.time()
    root = root or repo_root()
    inherited: dict[str, tuple[str, str]] = {}
    unresolved: dict[str, float] = {}
    diagnosed: set[str] = set()
    while time.time() < deadline:
        try:
            runs = check_runs(slug, sha, tok)
        # HTTPError before URLError: it is a subclass, and the two mean opposite things. A 404 for a
        # wrong slug or a 401 for a stale token is PERMANENT -- retrying it to the timeout reports
        # "still pending", which reads as "CI is slow" when the truth is "nothing was ever asked".
        except urllib.error.HTTPError as exc:
            if exc.code in REFUSAL_HELP:
                print(
                    f"\nwait_gates: the API REFUSED this request: HTTP {exc.code}", file=sys.stderr
                )
                print(f"  repos/{slug}/commits/{sha}/check-runs", file=sys.stderr)
                print(f"  {exc.code} -> {REFUSAL_HELP[exc.code]}", file=sys.stderr)
                print("  Nothing was polled. Do NOT read this as green.", file=sys.stderr)
                return 2
            print(f"  (api hiccup: {exc}; retrying)")
            time.sleep(interval)
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  (api hiccup: {exc}; retrying)")
            time.sleep(interval)
            continue

        # Resolved OUTSIDE the loop body as a plain dict rather than a closure: a function defined
        # in a loop that reads the loop's own variables is exactly the B023 shape this repo gates
        # on, and it breaks silently the day it is called from another iteration.
        seen = {g: effective(g, runs, inherited) for g in want}

        failed = [g for g in want if seen[g] not in (None, "queued", "in_progress", *GREEN)]
        if failed:
            print("\nwait_gates: FAILED: " + ", ".join(f"{g}={seen[g]}" for g in failed))
            return 1

        pending = [g for g in want if seen[g] in (None, "queued", "in_progress")]
        if not pending:
            print(
                "\nwait_gates: all expected gates green: "
                + ", ".join(f"{g}={seen[g]}" for g in want)
            )
            for g, (anc, concl) in sorted(inherited.items()):
                print(
                    f"  note: {g} did not run on this sha; carried {concl} forward from {anc[:9]},"
                    " because nothing since then touches the paths it filters on."
                )
            return 0

        # An absent gate (no check-run at all) is the ambiguous one. Give CI a grace period to
        # create it, then resolve it ONCE rather than waiting out the clock on a gate that this
        # push could never have triggered.
        absent = [g for g in pending if runs.get(g) is None]
        # ⚠ A gate can stop being absent. CI sometimes creates the check-run minutes after the push,
        # and without this prune a gate recorded as unresolved on one iteration would still be
        # counted against the refusal below after it had appeared and gone green -- turning a slow
        # gate into a refused merge, which is this bug in the opposite direction.
        for g in [g for g in unresolved if g not in absent]:
            del unresolved[g]
            diagnosed.discard(g)
        if absent and time.time() - started >= ABSENT_GRACE_S:
            for g in absent:
                if g in inherited or g in unresolved:
                    continue
                got = inherited_verdict(g, branch, root=root, slug=slug, sha=sha, tok=tok)
                if got is None:
                    unresolved[g] = time.time()
                else:
                    inherited[g] = got
                    print(f"  resolved: {g}={got[1]} inherited from {got[0][:9]}")

        for g in sorted(unresolved):
            if g in diagnosed:
                continue
            diagnosed.add(g)
            print(
                f"\n  ⚠ {g}: NO check-run on this sha, and no ancestor verdict can be carried\n"
                f"    forward. Either CI has not created it yet, or this push did not touch the\n"
                f"    paths {g} filters on -- in which case it will NEVER appear and this is not\n"
                f"    a slow gate. Force a verdict with:\n"
                f"      gh workflow run {g}.yml --ref {branch}\n"
            )
        if unresolved and time.time() - min(unresolved.values()) >= ABSENT_VERDICT_S:
            print(
                "\nwait_gates: REFUSING -- these gates never appeared and cannot be inherited: "
                + ", ".join(sorted(unresolved)),
                file=sys.stderr,
            )
            print(
                "  This is NOT a green result and NOT a timeout: the workflow was never run on\n"
                "  this commit. Dispatch it with the command above, then poll again.",
                file=sys.stderr,
            )
            return 1

        print(f"  pending: {', '.join(pending)}")
        time.sleep(interval)

    print(f"\nwait_gates: timed out after {timeout}s; still pending.", file=sys.stderr)
    print("  Do NOT merge on a timeout -- check by hand.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument(
        "--ref",
        default="origin/main",
        help="compare against this ref (default origin/main; on main pass the pre-push sha)",
    )
    args = ap.parse_args(argv)

    root = repo_root()
    branch = expected_gates.current_branch()

    # Ask FIRST whether the diff can be computed at all. "No gate will run" and "I cannot tell which
    # gates would run" both produce an empty list, and only the first of them licenses a merge.
    _, base_status = diff_base(args.ref)
    if base_status != BASE_OK:
        for line in expected_gates.unusable_base_message(args.ref, base_status, branch):
            print(line, file=sys.stderr)
        print("  Do NOT read this as green. Nothing was polled.", file=sys.stderr)
        return 2

    files = expected_gates.changed_vs(args.ref)
    want, skip = expected_gates.expected(files, branch)

    if not want:
        print("wait_gates: this diff triggers NO gate -- no check-run will ever appear.")
        print("  Nothing to wait for. Merge when ready.")
        return 0

    print(f"wait_gates: waiting for {', '.join(want)}")
    print(f"  (will NOT poll, because this diff cannot trigger them: {', '.join(skip) or 'none'})")

    tok = token()
    slug = remote_slug(root)
    if not tok or not slug:
        print("\nwait_gates: no API token or no remote -- cannot poll.", file=sys.stderr)
        print(f"  token: {'found' if tok else f'not found at {TOKEN_PATH}'}", file=sys.stderr)
        print(f"  remote: {slug or 'none'}", file=sys.stderr)
        print("  Check the gates by hand; do not assume they passed.", file=sys.stderr)
        return 2

    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()

    return poll(
        want,
        slug,
        sha,
        tok,
        timeout=args.timeout,
        interval=args.interval,
        branch=branch,
        root=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
