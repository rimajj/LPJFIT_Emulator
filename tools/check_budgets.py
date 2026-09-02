#!/usr/bin/env python3
"""Enforce the document size budgets in config/budgets.toml.

WHY THIS EXISTS. In the predecessor repo, documentation was capped by prose and the prose lost. Its
memory file carried its own documented limit of 400 lines in its own header and reached 647 (+62 %);
its always-loaded runbook reached 1,255 lines; one line-state file reached 3,924 lines and had stopped
being state at all. A dedicated consolidation procedure existed the whole time and never ran, because
nothing ever made it run. The cap was never the missing piece -- the mechanism was.

So the same limits now fail a commit and fail CI, and raising one is an owner act:

    B01  a file is over its line budget
    B02  a MEMORY.md row is not a well-formed fixed-column row (prose creeping in)
    B03  a section is over its section budget
    B04  a root-level .md file is not in the allowlist
    B05  the skill set is over its aggregate line or file cap
    B06  config/budgets.toml was modified without the owner-approval trailer
    B07  a skill has been unused past the failure threshold and is not listed in RETENTION.md
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# tools/ is a flat directory of executables, not an installed package, so make the sibling module
# importable whether this file is run as a script or imported by a test.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Report,
    base_parser,
    config,
    glob_match,
    read_lines,
    repo_root,
    select_files,
    tracked_files,
)

OWNER_TRAILER = "Budget-change-approved-by: owner"


def _budget_for(rel: str, budgets: list[dict]) -> dict | None:
    """The most specific matching budget: the longest glob wins, so a narrower rule overrides."""
    best: dict | None = None
    best_len = -1
    for b in budgets:
        pattern = str(b.get("glob", ""))
        if pattern and glob_match(pattern, rel) and len(pattern) > best_len:
            best, best_len = b, len(pattern)
    return best


def check_line_budgets(rel: str, lines: list[str], budgets: list[dict], rep: Report) -> None:
    b = _budget_for(rel, budgets)
    if b is None:
        return
    limit = int(b["max_lines"])
    n = len(lines)
    if n > limit:
        over = n - limit
        rep.add(
            rel,
            "B01",
            f"{n} lines, budget {limit} (over by {over})",
            hint=b.get("note", "") or f"rotate with tools/rotate_state.py, or move depth to a reference file",
        )

    # Structural row format. This is what makes MEMORY.md unable to become a narrative: a row that is
    # not a fixed-column table row is a finding, so the file's SHAPE is enforced, not just its size.
    row_format = b.get("row_format")
    if row_format:
        import re as _re

        rx = _re.compile(str(row_format))
        for i, ln in enumerate(lines, start=1):
            s = ln.strip()
            if not s.startswith("|"):
                continue
            # Skip the header row and the |---|---| separator.
            if _re.fullmatch(r"\|[\s|:-]+\|", s):
                continue
            if s.startswith("| id ") or s.startswith("| Kind "):
                continue
            if not rx.match(s):
                rep.add(
                    rel,
                    "B02",
                    "table row does not match the required fixed-column format",
                    line=i,
                    hint="rows are `| id | fact (<=200 chars) | source | YYYY-MM-DD |` — prose belongs in a skill or docs/reference/",
                )


def check_sections(rel: str, lines: list[str], sections: list[dict], rep: Report) -> None:
    for s in sections:
        if not glob_match(str(s.get("glob", "")), rel):
            continue
        heading = str(s["heading"])
        limit = int(s["max_lines"])
        start = None
        for i, ln in enumerate(lines):
            if ln.strip() == heading:
                start = i
                break
        if start is None:
            continue
        # The section runs to the next heading at the SAME OR SHALLOWER depth, ignoring headings
        # inside fenced code blocks (a `## ` in an example would otherwise truncate it).
        depth = len(heading) - len(heading.lstrip("#"))
        end = len(lines)
        in_fence = False
        for i in range(start + 1, len(lines)):
            stripped = lines[i].lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not stripped.startswith("#"):
                continue
            d = len(stripped) - len(stripped.lstrip("#"))
            if d <= depth:
                end = i
                break
        n = end - start
        if n > limit:
            rep.add(
                rel,
                "B03",
                f"section {heading!r} is {n} lines, budget {limit}",
                line=start + 1,
                hint=s.get("note", ""),
            )


def check_root_allowlist(files: list[str], allow: list[str], rep: Report) -> None:
    for rel in files:
        if "/" in rel or not rel.endswith(".md"):
            continue
        if rel not in allow:
            rep.add(
                rel,
                "B04",
                "new root-level markdown file is not in the allowlist",
                hint=(
                    "the predecessor accumulated seven partially-superseding root planning documents "
                    "(~1,584 lines) that every session was told to read. Put this in docs/reference/, "
                    "a skill, or PLAN.md — or add it to [root_md].allow with owner approval"
                ),
            )


def check_aggregates(aggregates: list[dict], rep: Report) -> None:
    tracked = tracked_files()
    for agg in aggregates:
        pattern = str(agg.get("glob", ""))
        matched = [f for f in tracked if glob_match(pattern, f)]
        max_files = agg.get("max_files")
        if max_files is not None and len(matched) > int(max_files):
            rep.add(
                pattern,
                "B05",
                f"{len(matched)} files, cap {max_files}",
                hint="merge or delete one first — a cap is what convenes the dedup pass that otherwise never happens",
            )
        max_total = agg.get("max_total_lines")
        if max_total is not None:
            total = 0
            for f in matched:
                ls = read_lines(f)
                if ls is not None:
                    total += len(ls)
            if total > int(max_total):
                rep.add(
                    pattern,
                    "B05",
                    f"{total} total lines, cap {max_total}",
                    hint="push depth into references/, which is loaded on demand instead of inventoried every session",
                )


def check_owner_trailer(files: list[str], rep: Report) -> None:
    """A budget may only be RAISED by the owner.

    Without this the whole scheme is circular: the agent bound by a cap can edit the cap. Only fires
    when budgets.toml is MODIFIED -- adding the file (the bootstrap commit) is not a budget change,
    and neither is deleting it.
    """
    if "config/budgets.toml" not in files:
        return
    name_status = subprocess.run(
        ["git", "-C", str(repo_root()), "diff", "--cached", "--name-status", "--", "config/budgets.toml"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    # "A<TAB>config/budgets.toml" on first add; "M<TAB>..." on a real change. No staged entry at all
    # means we are running over the tracked set (CI), where a modification is judged from the commit.
    if name_status.startswith("A"):
        return
    msg = subprocess.run(
        ["git", "-C", str(repo_root()), "log", "-1", "--format=%B"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # At commit time the new message is not in the log yet, so consult the prepared message too.
    prepared = repo_root() / ".git" / "COMMIT_EDITMSG"
    if prepared.exists():
        msg += "\n" + prepared.read_text(encoding="utf-8", errors="replace")
    if OWNER_TRAILER not in msg:
        rep.add(
            "config/budgets.toml",
            "B06",
            "budgets changed without owner approval",
            hint=f"a budget is raised by the owner, not by the agent it binds. Add the trailer `{OWNER_TRAILER}`",
        )


def check_skill_hygiene(hygiene: dict, rep: Report) -> None:
    """Unused skills become visible, then warn, then fail.

    Reads .claude/skill-usage.log (one `<iso8601>\t<skill>` line per invocation, appended by a hook).
    Absent log => nothing to say; a brand-new repo must not fail this.
    """
    fail_days = int(hygiene.get("fail_days", 90))
    log = repo_root() / ".claude" / "skill-usage.log"
    if not log.exists():
        return
    retention = repo_root() / ".claude" / "skills" / "RETENTION.md"
    exempt = retention.read_text(encoding="utf-8") if retention.exists() else ""

    last: dict[str, float] = {}
    for ln in log.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        try:
            ts = time.mktime(time.strptime(parts[0][:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
        name = parts[1].strip()
        last[name] = max(last.get(name, 0.0), ts)

    now = time.time()
    for skill_md in sorted((repo_root() / ".claude" / "skills").glob("*/SKILL.md")):
        name = skill_md.parent.name
        if name in exempt:
            continue
        seen = last.get(name)
        age_days = (now - seen) / 86400.0 if seen else None
        if age_days is not None and age_days > fail_days:
            rep.add(
                f".claude/skills/{name}/SKILL.md",
                "B07",
                f"unused for {age_days:.0f} days (threshold {fail_days})",
                hint="delete it, merge it into a neighbour, or list it in .claude/skills/RETENTION.md with a reason",
            )


def main(argv: list[str] | None = None) -> int:
    ap = base_parser(__doc__ or "")
    args = ap.parse_args(argv)
    cfg = config("budgets")
    rep = Report("check_budgets")

    files = select_files(args)
    budgets = list(cfg.get("budget", []))
    sections = list(cfg.get("section_budget", []))

    for rel in files:
        if not rel.endswith(".md"):
            continue
        lines = read_lines(rel)
        if lines is None:
            continue
        check_line_budgets(rel, lines, budgets, rep)
        check_sections(rel, lines, sections, rep)

    check_root_allowlist(files, list(cfg.get("root_md", {}).get("allow", [])), rep)
    check_aggregates(list(cfg.get("aggregate_budget", [])), rep)
    check_owner_trailer(files, rep)
    check_skill_hygiene(dict(cfg.get("skill_hygiene", {})), rep)

    return rep.emit()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
