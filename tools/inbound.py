#!/usr/bin/env python3
"""Append a message to another line's STATE.md. The ONE sanctioned cross-line write.

    tools/inbound.py --to T --subject "the corpus schema changed" --body "..."

WHY A TOOL. Line ownership is otherwise absolute, and the edit-time path guard denies writing to
another line's files. But lines do occasionally need to tell each other something, and the
predecessor learned three things about how that goes wrong:

  1. an inbound block WILL rebase-conflict, because two branches now touch the same file;
  2. resolving that conflict with `--theirs` SILENTLY DELETES the message;
  3. so the block must be anchored somewhere stable, and the sender must keep a copy.

This tool therefore inserts the block immediately BEFORE a long-lived heading (`## Milestones`)
rather than at the end of the file, and mirrors it into the sender's own STATE.md under
`## Outbound`. If your message vanishes from their file after a rebase, yours is the evidence it was
sent -- check that it still exists on main before assuming it was received.

It sets VEGEMU_VIA_TOOL so the path guard allows this one write.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root

ANCHOR = "## Milestones"


def current_line(root: Path) -> str:
    branch = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return branch.split("/", 1)[1] if branch.startswith("line/") else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--to", required=True, help="destination line, e.g. T")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--from", dest="sender", default="", help="override the detected sender line")
    args = ap.parse_args(argv)

    root = repo_root()
    sender = args.sender or current_line(root) or "?"
    if args.to == sender:
        print("inbound: that is your own line.", file=sys.stderr)
        return 2

    dest = root / "lines" / args.to / "STATE.md"
    if not dest.exists():
        print(f"inbound: no such line: {dest}", file=sys.stderr)
        return 2

    today = time.strftime("%Y-%m-%d")
    block = (
        f"## INBOUND from line {sender} ({today}) — {args.subject}\n\n"
        f"{args.body.strip()}\n\n"
        f"> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --\n"
        f"> resolving with --theirs silently deletes this message. Delete it deliberately once\n"
        f"> acted on, never as conflict cleanup.\n\n"
    )

    text = dest.read_text(encoding="utf-8")
    if ANCHOR in text:
        # Before a long-lived heading, not at EOF: the end of the file is where two lines' appends
        # collide, and where a conflict resolution is most likely to drop one.
        text = text.replace(ANCHOR, block + ANCHOR, 1)
    else:
        text = text.rstrip() + "\n\n" + block
    os.environ["VEGEMU_VIA_TOOL"] = "1"
    dest.write_text(text, encoding="utf-8")

    # Mirror it, so the sender can prove what was sent. The mirror is the stated remedy for
    # failure mode 2 in this module's docstring -- a `--theirs` conflict resolution deletes the
    # recipient's copy silently -- so whether it was actually written must be REPORTED, not assumed.
    # It used to be skipped in silence for any sender without a lines/<sender>/STATE.md (the
    # integrator, or an undetected line) while the success line claimed it had been mirrored.
    mine = root / "lines" / sender / "STATE.md"
    mirrored = mine.exists()
    if mirrored:
        mtext = mine.read_text(encoding="utf-8")
        mirror = (
            f"## Outbound to line {args.to} ({today}) — {args.subject}\n\n{args.body.strip()}\n\n"
        )
        if ANCHOR in mtext:
            mtext = mtext.replace(ANCHOR, mirror + ANCHOR, 1)
        else:
            mtext = mtext.rstrip() + "\n\n" + mirror
        mine.write_text(mtext, encoding="utf-8")

    if mirrored:
        print(f"inbound: wrote to lines/{args.to}/STATE.md and mirrored in lines/{sender}/STATE.md")
        print("Commit both.")
    else:
        print(f"inbound: wrote to lines/{args.to}/STATE.md. Commit it.")
        print(
            f"inbound: NO SENDER COPY KEPT -- there is no lines/{sender}/STATE.md.",
            file=sys.stderr,
        )
        print(
            "  So the recipient's file is the ONLY copy, and a rebase resolved with --theirs "
            "would\n  erase it without trace. Your commit on main is then the only evidence: "
            "check the\n  block is still in their file after any rebase that touches it.",
            file=sys.stderr,
        )
    print("Note their STATE.md has a 120-line budget -- if this pushes them over, the")
    print("message still lands but they will have to rotate; keep it short.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
