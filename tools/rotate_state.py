#!/usr/bin/env python3
"""Move a line's stale state into its journal, mechanically.

    tools/rotate_state.py <LINE> [--dry-run]

Everything below an `## ARCHIVE` heading in `lines/<L>/STATE.md` is appended to
`journal/<L>/<YYYY-MM>.md` and removed from the state file.

WHY A TOOL AND NOT AN INSTRUCTION. The predecessor had a documented cap and a documented procedure
for staying under it, and the procedure never ran once -- because it asked for judgement ("decide
what is still durable state") with no trigger. Judgement plus no trigger equals never. This asks for
one decision instead: move a heading under `## ARCHIVE`. The tool does the rest.

If there is no `## ARCHIVE` section, the tool says what to do rather than guessing which of your
sections has stopped being state -- deleting the wrong one is worse than being over budget.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root

ARCHIVE = "## ARCHIVE"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("line")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = repo_root()
    state = root / "lines" / args.line / "STATE.md"
    if not state.exists():
        print(f"rotate_state: no such file: {state}", file=sys.stderr)
        return 2

    lines = state.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == ARCHIVE), None)
    if start is None:
        print(f"lines/{args.line}/STATE.md is {n} lines.")
        print(f"\nThere is no `{ARCHIVE}` section, so there is nothing to rotate yet.")
        print("Add one, and move under it whatever has stopped being CURRENT state -- closed")
        print(
            "milestones, superseded findings, anything more than about two weeks old. Then re-run."
        )
        print(
            "\nThe test: would the next session act differently if it never read this? If not, it"
        )
        print("belongs in the journal.")
        return 1

    moved = lines[start + 1 :]
    kept = lines[:start]
    while kept and not kept[-1].strip():
        kept.pop()

    body = "\n".join(moved).strip()
    if not body:
        print(f"rotate_state: `{ARCHIVE}` is empty; nothing to move.")
        return 0

    month = time.strftime("%Y-%m")
    journal = root / "journal" / args.line / f"{month}.md"
    stamp = f"\n## {time.strftime('%Y-%m-%d')} — rotated out of STATE.md\n\n{body}\n"

    if args.dry_run:
        print(f"would move {len(moved)} line(s) from lines/{args.line}/STATE.md")
        print(f"           into journal/{args.line}/{month}.md")
        print(f"           leaving {len(kept)} line(s)")
        return 0

    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(stamp)
    state.write_text("\n".join(kept) + "\n", encoding="utf-8")

    print(f"moved {len(moved)} line(s) -> journal/{args.line}/{month}.md")
    print(f"lines/{args.line}/STATE.md is now {len(kept)} lines")
    print("\nCommit both files together, so the state and its archive never disagree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
