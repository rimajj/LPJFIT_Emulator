#!/usr/bin/env python3
"""Poll CI for exactly the gates a diff triggers -- and refuse to poll for anything else.

    tools/wait_gates.py [--timeout 900]

Asks `tools/expected_gates.py` which check-runs will appear, then polls only those. If the answer is
"none", it exits 0 immediately.

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
    url = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not url:
        return None
    tail = url.split(":")[-1] if ":" in url else url
    return tail.removesuffix(".git").strip("/").split("/", 1)[-1] if "/" in tail else None


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--interval", type=int, default=20)
    args = ap.parse_args(argv)

    root = repo_root()
    branch = expected_gates.current_branch()

    # Ask FIRST whether the diff can be computed at all. "No gate will run" and "I cannot tell which
    # gates would run" both produce an empty list, and only the first of them licenses a merge.
    _, base_status = diff_base("origin/main")
    if base_status != BASE_OK:
        for line in expected_gates.unusable_base_message("origin/main", base_status, branch):
            print(line, file=sys.stderr)
        print("  Do NOT read this as green. Nothing was polled.", file=sys.stderr)
        return 2

    files = expected_gates.changed_vs("origin/main")
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

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            runs = check_runs(slug, sha, tok)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  (api hiccup: {exc}; retrying)")
            time.sleep(args.interval)
            continue

        pending = [g for g in want if runs.get(g) in (None, "queued", "in_progress")]
        failed = [
            g
            for g in want
            if runs.get(g) not in (None, "queued", "in_progress", "success", "neutral", "skipped")
        ]
        if failed:
            print("\nwait_gates: FAILED: " + ", ".join(f"{g}={runs.get(g)}" for g in failed))
            return 1
        if not pending:
            print(
                "\nwait_gates: all expected gates green: "
                + ", ".join(f"{g}={runs.get(g)}" for g in want)
            )
            return 0
        print(f"  pending: {', '.join(pending)}")
        time.sleep(args.interval)

    print(f"\nwait_gates: timed out after {args.timeout}s; still pending.", file=sys.stderr)
    print("  Do NOT merge on a timeout -- check by hand.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
