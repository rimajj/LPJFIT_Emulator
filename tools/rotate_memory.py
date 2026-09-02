#!/usr/bin/env python3
"""Evict stale MEMORY.md rows into docs/reference/retired_facts.md.

    tools/rotate_memory.py [--days 90] [--dry-run]

A row is evicted when BOTH hold:
  * its `verified` date is older than --days, AND
  * its id is referenced by no decision record, experiment, skill or reference document.

The second condition is what makes this safe to run unattended: a fact that something still cites is
kept regardless of age, because the citation is evidence that it is still load-bearing.

WHY THIS IS A SET OPERATION AND NOT AN ESSAY. The predecessor's memory file was prose, so compacting
it meant rewriting it -- which is why the procedure for doing so never ran and the file ended 62 %
over its own documented cap. One fact per fixed-column row makes eviction mechanical.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root

ROW = re.compile(r"^\|\s*(?P<id>[a-z0-9-]+)\s*\|.*\|\s*(?P<ver>\d{4}-\d{2}-\d{2})\s*\|$")


def referenced(root: Path, ids: set[str]) -> set[str]:
    """Ids mentioned anywhere outside MEMORY.md itself."""
    if not ids:
        return set()
    hits: set[str] = set()
    out = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "grep",
            "-h",
            "-o",
            "-E",
            "|".join(re.escape(i) for i in ids),
            "--",
            "docs/",
            "experiments/",
            ".claude/skills/",
            "lines/",
            "PLAN.md",
            "CLAUDE.md",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for ln in out.splitlines():
        token = ln.strip()
        if token in ids:
            hits.add(token)
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = repo_root()
    mem = root / "MEMORY.md"
    lines = mem.read_text(encoding="utf-8").splitlines()

    cutoff = time.time() - args.days * 86400
    candidates: dict[int, str] = {}
    for i, ln in enumerate(lines):
        m = ROW.match(ln.strip())
        if not m:
            continue
        try:
            ts = time.mktime(time.strptime(m.group("ver"), "%Y-%m-%d"))
        except ValueError:
            continue
        if ts < cutoff:
            candidates[i] = m.group("id")

    if not candidates:
        print(f"MEMORY.md is {len(lines)} lines; no row is older than {args.days} days.")
        return 0

    keep = referenced(root, set(candidates.values()))
    evict = {i: fid for i, fid in candidates.items() if fid not in keep}

    if not evict:
        print(f"{len(candidates)} row(s) are older than {args.days} days, but all are still cited:")
        for fid in sorted(candidates.values()):
            print(f"  {fid}  (referenced -> kept)")
        return 0

    print(f"evicting {len(evict)} row(s) older than {args.days} days and cited by nothing:")
    for fid in sorted(evict.values()):
        print(f"  {fid}")
    if keep:
        print(f"keeping {len(keep)} aged but still-cited row(s): {', '.join(sorted(keep))}")
    if args.dry_run:
        return 0

    retired = root / "docs" / "reference" / "retired_facts.md"
    if not retired.exists():
        retired.write_text(
            "# Retired facts\n\nRows evicted from MEMORY.md by tools/rotate_memory.py: aged\n"
            "out, and cited by nothing at the time of eviction. Kept rather than deleted,\n"
            "because a fact that stopped being current is not one that was wrong.\n",
            encoding="utf-8",
        )
    with retired.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## Evicted {time.strftime('%Y-%m-%d')}\n\n")
        fh.write("| id | fact | source | verified |\n|---|---|---|---|\n")
        for i in sorted(evict):
            fh.write(lines[i].rstrip() + "\n")

    mem.write_text(
        "\n".join(ln for i, ln in enumerate(lines) if i not in evict) + "\n", encoding="utf-8"
    )
    print(f"\nMEMORY.md is now {len(lines) - len(evict)} lines. Commit both files together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
