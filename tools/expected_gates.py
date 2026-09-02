#!/usr/bin/env python3
"""Print exactly which CI gates a diff will trigger -- and which must NOT be polled.

Run this BEFORE polling CI. It is step 3 of the merge ritual, and it exists because of a specific
failure mode rather than as a convenience:

    A workflow skipped by its path filter reports NO STATUS AT ALL, not a "skipped" status.

So "wait until the test job completes" hangs forever on a commit that changed only prose. Most
commits in this repo are exactly that. The decision of what to wait for must therefore be COMPUTED
from the diff, never guessed -- and if the answer is "nothing", the merge can proceed at once.

    $ tools/expected_gates.py
    diff vs origin/main: 4 file(s)
    EXPECTED GATES: budgets, experiments
    NOT TRIGGERED (do not poll): lint, types, test, pathsafety, campaigns, changelog, flags

    $ tools/expected_gates.py --json      # for tools/wait_gates.py
    {"branch": "line/D", "files": 4, "expected": ["budgets"], "not_triggered": [...]}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import changed_vs, glob_match, repo_root  # noqa: E402


def load_gates() -> tuple[list[dict], dict]:
    """The declared gates and the meta block, from the single source of truth."""
    path = repo_root() / ".github" / "gates.toml"
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return list(data.get("gate", [])), dict(data.get("meta", {}))


def current_branch() -> str:
    """The branch name, or "main" when git cannot name one.

    `rev-parse --abbrev-ref HEAD` answers the literal string "HEAD" before the first commit and on a
    detached checkout. Treating that as a branch name matches no gate, which would report "(none)"
    and invite a merge with nothing verified -- so fall back to the most conservative answer, which
    is the branch that runs every gate.
    """
    out = subprocess.run(
        ["git", "-C", str(repo_root()), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return out if out and out != "HEAD" else "main"


def branch_matches(branch: str, patterns: list[str]) -> bool:
    for p in patterns:
        if p == branch:
            return True
        # GitHub's `line/**` semantics: match the whole subtree.
        if p.endswith("/**") and branch.startswith(p[:-2]):
            return True
        if glob_match(p, branch):
            return True
    return False


def expected(files: list[str], branch: str) -> tuple[list[str], list[str]]:
    gates, meta = load_gates()
    always = list(meta.get("always", []))
    run: list[str] = []
    skip: list[str] = []
    for g in gates:
        job = str(g["job"])
        if not branch_matches(branch, list(g.get("branches", ["main"]))):
            skip.append(job)
            continue
        patterns = list(g.get("paths", [])) + always
        if any(glob_match(p, f) for f in files for p in patterns):
            run.append(job)
        else:
            skip.append(job)
    return run, skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="origin/main", help="compare against this ref (default origin/main)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--branch", default=None, help="override the detected branch")
    args = ap.parse_args(argv)

    branch = args.branch or current_branch()
    files = changed_vs(args.ref)
    run, skip = expected(files, branch)

    if args.json:
        print(json.dumps({"branch": branch, "files": len(files), "expected": run, "not_triggered": skip}))
        return 0

    print(f"diff vs {args.ref}: {len(files)} file(s) on branch {branch}")
    if run:
        print("EXPECTED GATES: " + ", ".join(run))
    else:
        print("EXPECTED GATES: (none)")
        print("  -> no check-run will appear for this commit. Do not poll. Merge when ready.")
    if skip:
        print("NOT TRIGGERED (do not poll): " + ", ".join(skip))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
