#!/usr/bin/env python3
"""Fold changelog.d/*.md fragments into CHANGELOG.md.

    tools/collate_changelog.py            # collate and rewrite CHANGELOG.md
    tools/collate_changelog.py --check    # exit 1 if any fragment is still uncollated (the CI gate)

WHY FRAGMENTS AT ALL. A work line never edits CHANGELOG.md: several lines editing one file makes a
merge conflict on every merge. A line writes `changelog.d/<line>-<slug>.md` instead -- separate
files never conflict -- and whoever holds the merge lock folds them in.

WHY THIS RUNS INSIDE THE MERGE LOCK, AND WHY A CI GATE WATCHES IT. This is the predecessor's single
most instructive process failure. The chore was specified as "the integrator collates at an
integration point" -- but there is no orchestrator: each line merges its own branch, so nothing
ever convened an integration point for anyone to attend. Measured cost: 56 fragments piled up over
13 days while CHANGELOG.md was edited three times in the same window. No gate, and no complaint.

The generalised rule, which this repo applies to every chore: an integrator-owned task needs a
triggering EVENT and a VISIBILITY mechanism, or it silently rots. Here the event is every merge (the
merge script calls this while holding the lock) and the visibility is the `changelog` gate on main.

Fragment format -- one or more Keep-a-Changelog sections:

    ### Added
    - the thing that was added

An unknown section heading is an ERROR, not a warning: a typo that silently drops a line from the
changelog is worse than a failed build.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root

SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
HEADING_RE = re.compile(r"^#{2,4}\s*(?P<name>[A-Za-z]+)\s*$")
UNRELEASED_RE = re.compile(r"^##\s*\[?Unreleased\]?\s*$", re.IGNORECASE)


def parse_fragment(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Return ({section: [bullets]}, [errors])."""
    out: dict[str, list[str]] = {}
    errors: list[str] = []
    current: str | None = None
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        m = HEADING_RE.match(line.strip())
        if m:
            name = m.group("name").capitalize()
            if name not in SECTIONS:
                errors.append(
                    f"{path.name}:{i}: unknown section {m.group('name')!r}; "
                    f"expected one of {', '.join(SECTIONS)}"
                )
                current = None
            else:
                current = name
                out.setdefault(current, [])
            continue
        if not line.strip():
            continue
        # A bullet marker is `-` or `*` FOLLOWED BY WHITESPACE. Testing only the first character
        # mis-read a continuation line that opened with `**bold**` as a new bullet, which silently
        # split one entry in two and dropped the `**` -- a corrupted changelog with a green build,
        # which is exactly the failure mode this file exists to prevent.
        stripped = line.lstrip()
        if len(stripped) > 1 and stripped[0] in "-*" and stripped[1].isspace():
            if current is None:
                errors.append(f"{path.name}:{i}: bullet before any section heading")
            else:
                out[current].append("- " + stripped[1:].strip())
        # Continuation of the previous bullet.
        elif current and out.get(current):
            out[current][-1] += " " + line.strip()
        else:
            errors.append(f"{path.name}:{i}: prose outside a bullet")
    return out, errors


def fragments() -> list[Path]:
    d = repo_root() / "changelog.d"
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.md") if p.name != "README.md")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--version", default="Unreleased")
    args = ap.parse_args(argv)

    frags = fragments()
    if args.check:
        if frags:
            print(
                f"changelog: {len(frags)} uncollated fragment(s) on this branch:", file=sys.stderr
            )
            for f in frags:
                print(f"  changelog.d/{f.name}", file=sys.stderr)
            print("\nfix with one command:  tools/collate_changelog.py", file=sys.stderr)
            print(
                "(a fragment on a LINE branch is correct and this gate does not run there; on main "
                "it is debt)",
                file=sys.stderr,
            )
            return 1
        return 0

    if not frags:
        print("changelog: nothing to collate")
        return 0

    merged: dict[str, list[str]] = {}
    errors: list[str] = []
    for f in frags:
        sections, errs = parse_fragment(f)
        errors.extend(errs)
        for name, bullets in sections.items():
            merged.setdefault(name, []).extend(bullets)
    if errors:
        print(f"changelog: {len(errors)} malformed fragment line(s)", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1

    body: list[str] = []
    for name in SECTIONS:
        if merged.get(name):
            body.append(f"### {name}")
            body.extend(merged[name])
            body.append("")

    path = repo_root() / "CHANGELOG.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = (
            "# Changelog\n\n"
            "All notable changes to this project. Format: Keep a Changelog; newest first.\n"
            "Entries are `changelog.d/<line>-<slug>.md` fragments, folded in at merge.\n\n"
            "## [Unreleased]\n\n"
        )

    lines = text.splitlines()
    # Insert directly beneath the Unreleased heading, so the newest content is first.
    idx = next((i for i, ln in enumerate(lines) if UNRELEASED_RE.match(ln.strip())), None)
    if idx is None:
        lines = ["# Changelog", "", "## [Unreleased]", "", *lines]
        idx = 2
    at = idx + 1
    while at < len(lines) and not lines[at].strip():
        at += 1
    stamp = [f"<!-- collated {time.strftime('%Y-%m-%d')} from {len(frags)} fragment(s) -->", ""]
    lines[at:at] = stamp + body
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for f in frags:
        f.unlink()

    print(f"collated {len(frags)} fragment(s) into CHANGELOG.md")
    for name in SECTIONS:
        if merged.get(name):
            print(f"  {name}: {len(merged[name])} entry(ies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
