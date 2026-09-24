#!/usr/bin/env python3
"""Move a line's stale state into its journal, mechanically.

    tools/rotate_state.py <LINE> [--dry-run]

Everything below an `## ARCHIVE` heading in `lines/<L>/STATE.md` is appended to the line's current
journal file for the month and removed from the state file.

WHY A TOOL AND NOT AN INSTRUCTION. The predecessor had a documented cap and a documented procedure
for staying under it, and the procedure never ran once -- because it asked for judgement ("decide
what is still durable state") with no trigger. Judgement plus no trigger equals never. This asks for
one decision instead: move a heading under `## ARCHIVE`. The tool does the rest.

If there is no `## ARCHIVE` section, the tool says what to do rather than guessing which of your
sections has stopped being state -- deleting the wrong one is worse than being over budget.

THE JOURNAL ROLLS OVER AT ITS CAP. A month's journal is a SERIES of files,
`journal/<L>/<YYYY-MM>.md` then `<YYYY-MM>b.md`, `<YYYY-MM>c.md`, ... -- names that sort in the
order they were written, and all of which the `journal/*/*.md` budget glob covers. The archive
goes to the newest file of the series if it fits under that file's line budget
(`config/budgets.toml`), and otherwise starts the next one. This used to append to `<YYYY-MM>.md`
unconditionally while the budget's own note said "auto-rotated by the writer at the cap", and
nothing did: line T's September journal stood at 597 of 800 lines with ~300 lines of message
blocks waiting to be archived, so the one sanctioned way to get a STATE file under ITS budget
would have pushed the journal over its own, and the commit guard would have refused the pair. An
archive too big for even an empty file is refused, not split -- move half of it under
`## ARCHIVE`, rotate, then move the rest.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import config, glob_match, repo_root

ARCHIVE = "## ARCHIVE"

# `<YYYY-MM>.md` is part one; later parts carry a letter. 25 roll-overs in one month is far past any
# plausible use, and running out is an error rather than a silent overwrite.
_PART_SUFFIXES = ("", *"bcdefghijklmnopqrstuvwxyz")


def journal_cap(line: str, month: str) -> int | None:
    """The line budget `config/budgets.toml` sets for this line's journal, or None if it sets none.

    Resolved the way `check_budgets.py` resolves it -- the longest matching glob wins -- so the
    writer and the gate cannot disagree about where the wall is.
    """
    rel = f"journal/{line}/{month}.md"
    best: int | None = None
    best_len = -1
    for b in config("budgets").get("budget", []):
        pattern = str(b.get("glob", ""))
        if pattern and glob_match(pattern, rel) and len(pattern) > best_len:
            best, best_len = int(b["max_lines"]), len(pattern)
    return best


def journal_series(jdir: Path, month: str) -> list[Path]:
    """The month's journal files that exist, in the order they were written."""
    return [p for s in _PART_SUFFIXES if (p := jdir / f"{month}{s}.md").exists()]


def _part_header(line: str, month: str, previous: Path) -> str:
    return (
        f"# Line {line} journal — {month} (continued)\n\n"
        f"Continues `{previous.name}`, which reached its line budget. Append-only narrative, never "
        f"read at\nsession start; the handoff is the `## NEXT` block of `lines/{line}/STATE.md`.\n"
    )


def choose_journal(
    jdir: Path, line: str, month: str, addition: str, cap: int | None
) -> tuple[Path, str]:
    """Where `addition` goes, and that file's full new text. Raises ValueError if it cannot fit.

    The newest file of the series is kept while `existing + addition` stays within `cap`; otherwise
    the next part is started, with a header pointing back at its predecessor. `cap=None` (no budget
    configured) never rolls over.
    """

    def fits(text: str) -> bool:
        return cap is None or len(text.splitlines()) <= cap

    too_big = ValueError(
        f"the archive is {len(addition.splitlines())} lines, more than even an empty journal file "
        f"holds under its budget of {cap}; move half of it under `{ARCHIVE}`, rotate, then move "
        "the rest"
    )
    series = journal_series(jdir, month)
    if not series:
        # A month's first rotation creates part one bare, exactly as before this learned to roll.
        first = addition.lstrip("\n")
        if not fits(first):
            raise too_big
        return jdir / f"{month}.md", first
    current = series[-1]
    text = current.read_text(encoding="utf-8") + addition
    if fits(text):
        return current, text
    index = _PART_SUFFIXES.index(current.name[len(month) : -len(".md")])
    if index + 1 >= len(_PART_SUFFIXES):
        raise ValueError(f"journal/{line}/{month}: every part name up to 'z' is used")
    fresh = _part_header(line, month, current) + addition
    if not fits(fresh):
        raise too_big
    return jdir / f"{month}{_PART_SUFFIXES[index + 1]}.md", fresh


def rotate(root: Path, line: str, today: _dt.date, cap: int | None, dry_run: bool = False) -> int:
    """Move everything under `## ARCHIVE` in lines/<line>/STATE.md into the journal. Exit code."""
    state = root / "lines" / line / "STATE.md"
    if not state.exists():
        print(f"rotate_state: no such file: {state}", file=sys.stderr)
        return 2

    lines = state.read_text(encoding="utf-8").splitlines()
    n = len(lines)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == ARCHIVE), None)
    if start is None:
        print(f"lines/{line}/STATE.md is {n} lines.")
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

    month = today.strftime("%Y-%m")
    jdir = root / "journal" / line
    stamp = f"\n## {today.isoformat()} — rotated out of STATE.md\n\n{body}\n"
    try:
        journal, text = choose_journal(jdir, line, month, stamp, cap)
    except ValueError as exc:
        print(f"rotate_state: {exc}", file=sys.stderr)
        return 1
    rel = journal.relative_to(root).as_posix()
    rolled = not journal.exists() and journal.name != f"{month}.md"

    if dry_run:
        print(f"would move {len(moved)} line(s) from lines/{line}/STATE.md")
        print(f"           into {rel}{' (a NEW part: the last one is full)' if rolled else ''}")
        print(f"           leaving {len(kept)} line(s)")
        return 0

    jdir.mkdir(parents=True, exist_ok=True)
    journal.write_text(text, encoding="utf-8")
    state.write_text("\n".join(kept) + "\n", encoding="utf-8")

    print(f"moved {len(moved)} line(s) -> {rel}")
    if rolled:
        print(f"           a NEW journal part: the previous one would have passed {cap} lines")
    print(f"lines/{line}/STATE.md is now {len(kept)} lines")
    print("\nCommit both files together, so the state and its archive never disagree.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("line")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    today = _dt.date.today()
    cap = journal_cap(args.line, today.strftime("%Y-%m"))
    return rotate(repo_root(), args.line, today, cap, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
