#!/usr/bin/env python3
"""Enforce path ownership from config/ownership.toml.

WHY `unowned = deny`. The predecessor's ownership map grew to fifteen prose rows precisely BECAUSE
nothing enforced it: an audit found roughly 60 % of its source tree unowned, and the map was patched
by hand every time that bit somebody. Denying the commit on an unowned path forces a rule to be
added
at the moment of the first write, which keeps the map short and -- the part that actually matters --
keeps it TRUE.

    O01  a staged path belongs exclusively to another line
    O02  a staged path matches no rule at all (and unowned = "deny")
    O03  an accepted decision record was modified rather than added
    O04  a path is integrator-only and this is a line branch

The current line is resolved from the branch name (`line/D` -> D), so it is the directory you
launched
in that decides, and nobody has to declare it. On `main` the caller is the integrator and only
O02/O03
can fire.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    Report,
    _git,
    base_parser,
    config,
    glob_match,
    read_lines,
    repo_root,
    staged_files,
)


def current_line() -> str | None:
    """The work line of this worktree, or None if we are on main / detached."""
    branch = subprocess.run(
        ["git", "-C", str(repo_root()), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if branch.startswith("line/"):
        return branch.split("/", 1)[1] or None
    return None


def _rules(cfg: dict) -> list[tuple[str, str, str]]:
    """Flatten to (glob, owner, kind)."""
    out: list[tuple[str, str, str]] = []
    for rule in cfg.get("rule", []):
        owner = str(rule.get("owner", "*"))
        kind = str(rule.get("kind", "shared"))
        for g in rule.get("globs", []):
            out.append((str(g), owner, kind))
    return out


def _match(rel: str, rules: list[tuple[str, str, str]]) -> tuple[str, str, str] | None:
    """Most specific match wins: the longest glob, so a narrow carve-out beats a broad rule."""
    best: tuple[str, str, str] | None = None
    best_len = -1
    for glob, owner, kind in rules:
        if glob_match(glob, rel) and len(glob) > best_len:
            best, best_len = (glob, owner, kind), len(glob)
    return best


def accepted_adr_modified(files: list[str]) -> list[str]:
    """Decision records that are ACCEPTED and were modified (not added) in this change.

    An immutable audit trail is only immutable if editing one fails. Supersede with a new record.
    """
    out: list[str] = []
    status = subprocess.run(
        ["git", "-C", str(repo_root()), "diff", "--cached", "--name-status", "--diff-filter=MR"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    modified = {ln.split("\t")[-1].strip() for ln in status.splitlines() if ln.strip()}
    for rel in files:
        if rel not in modified or not glob_match("docs/decisions/*.md", rel):
            continue
        lines = read_lines(rel) or []
        head = "\n".join(lines[:15]).lower()
        if "status" in head and "accepted" in head:
            out.append(rel)
    return out


INBOUND_SENTINEL = "> Sent by tools/inbound.py."


def _staged_inbound_only(rel: str, sender: str) -> bool:
    """Is the staged change to `rel` nothing but an inbound block written by line `sender`?

    WHY THIS IS DERIVED FROM THE DIFF AND NOT FROM A FLAG. `--via-inbound` was the original design
    and it never once worked: nothing passed it. The commit guard calls this checker with `--staged`
    alone, so every message `tools/inbound.py` wrote was blocked at commit time by O01 -- the one
    sanctioned cross-line write was unusable, in both directions, for as long as it has existed.

    Reading the diff is also strictly SAFER than the flag would have been. A flag is a claim by the
    caller and permits any edit whatsoever to another line's STATE.md; this permits only an edit
    that is provably an inbound block, and only from the line doing the committing. Three
    conditions, all necessary:

      * nothing is REMOVED -- an inbound write only ever inserts, so a deletion is somebody editing
        another line's state under cover of sending it a message;
      * every added heading is an `## INBOUND from line <sender>` header, so arbitrary content
        cannot ride along under a section of its own;
      * the tool's sentinel line is present, which is what ties the block to the tool.

    The message BODY is deliberately unconstrained. It is prose for another line to read.
    """
    diff = _git("diff", "--cached", "-U0", "--", rel).splitlines()
    added: list[str] = []
    for ln in diff:
        if ln.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if ln.startswith("-"):
            return False  # a removal is never part of sending a message
        if ln.startswith("+"):
            added.append(ln[1:])
    if not added:
        return False

    header = f"## INBOUND from line {sender} ("
    headings = [ln for ln in added if ln.startswith("## ")]
    if not headings or any(not ln.startswith(header) for ln in headings):
        return False
    return any(ln.startswith(INBOUND_SENTINEL) for ln in added)


def main(argv: list[str] | None = None) -> int:
    ap = base_parser(__doc__ or "")
    ap.add_argument("--line", default=None, help="override the detected work line")
    ap.add_argument(
        "--via-inbound",
        action="store_true",
        help=(
            "deprecated and ignored: the sanctioned cross-line write is now recognised from the "
            "staged diff, because nothing ever passed this flag"
        ),
    )
    args = ap.parse_args(argv)

    cfg = config("ownership")
    meta = dict(cfg.get("meta", {}))
    unowned_policy = str(meta.get("unowned", "deny"))
    rules = _rules(cfg)
    rep = Report("check_ownership")

    files = args.paths or staged_files()
    line = args.line or current_line()

    for rel in files:
        m = _match(rel, rules)
        if m is None:
            if unowned_policy == "deny":
                rep.add(
                    rel,
                    "O02",
                    "matches no ownership rule",
                    hint=(
                        "add a rule to config/ownership.toml. This is deliberate: the "
                        "predecessor's map "
                        "drifted out of truth because unowned paths were silently allowed"
                    ),
                )
            else:
                print(f"{rel}: unowned (allowed by policy)", file=sys.stderr)
            continue

        glob, owner, kind = m
        if owner == "integrator" and line is not None:
            rep.add(
                rel,
                "O04",
                f"integrator-only (rule {glob!r}), and this is line {line}",
                hint=(
                    "request the change; it lands on main. Line branches do not edit the protocol "
                    "or the config"
                ),
            )
        elif (
            kind == "exclusive"
            and owner not in ("*", "integrator")
            and line is not None
            and owner != line
        ):
            if (
                line is not None
                and glob_match("lines/*/STATE.md", rel)
                and _staged_inbound_only(rel, line)
            ):
                continue
            rep.add(
                rel,
                "O01",
                f"belongs exclusively to line {owner} (rule {glob!r}), and this is line {line}",
                hint=(
                    "raise it as an integration point, or use tools/inbound.py to append a message "
                    "to their STATE.md"
                ),
            )

    for rel in accepted_adr_modified(files):
        rep.add(
            rel,
            "O03",
            "accepted decision record was modified",
            hint=(
                "records are immutable once accepted — supersede it with a new one that says what "
                "changed and why"
            ),
        )

    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
