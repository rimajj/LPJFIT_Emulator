#!/usr/bin/env python3
"""Enforce the document size budgets in config/budgets.toml.

WHY THIS EXISTS. In the predecessor repo, documentation was capped by prose and the prose lost. Its
memory file carried its own documented limit of 400 lines in its own header and reached 647
(+62 %); its always-loaded runbook reached 1,255 lines; one line-state file reached 3,924 lines and
had stopped being state at all. A dedicated consolidation procedure existed the whole time and never
ran, because nothing ever made it run. The cap was never the missing piece -- the mechanism was.

So the same limits now fail a commit and fail CI, and raising one is an owner act:

    B01  a file is over its line budget
    B02  a MEMORY.md row is not a well-formed fixed-column row (prose creeping in)
    B03  a section is over its section budget
    B04  a root-level .md file is not in the allowlist
    B05  the skill set is over its aggregate line or file cap
    B06  config/budgets.toml was modified without the owner-approval trailer
    B07  a skill has been unused past the failure threshold and is not listed in RETENTION.md
    B08  a `Skill:`/`Method:` pointer names a skill that does not exist -- a DANGLING POINTER
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
import time
from pathlib import Path

# tools/ is a flat directory of executables, not an installed package, so make the sibling module
# importable whether this file is run as a script or imported by a test.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
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


# A cross-line message, as `tools/inbound.py` writes it into the recipient's file and mirrors it
# into the sender's. The DATE IS REQUIRED for the exemption: it is what makes the block ageable, and
# an undated heading is not what the tool writes, so it is counted as ordinary content.
_INBOUND_HEADING = re.compile(
    r"^##\s+(?:INBOUND from line|Outbound to line)\b[^(]*\((?P<date>\d{4}-\d{2}-\d{2})\)",
    re.IGNORECASE,
)

# How long a cross-line message stays free. Two weeks, which is deliberately the same horizon
# `tools/rotate_state.py` already prints as its own advice ("anything more than about two weeks
# old" belongs in the journal) -- so the gate and the documented procedure now say one thing.
#
# NOT IN budgets.toml ON PURPOSE. Editing that file requires the owner-approval trailer (B06), and
# this constant TIGHTENS the gate rather than lifting a cap, so it must not be something an agent
# can quietly retune. Making it owner-tunable is an owner act.
INBOUND_GRACE_DAYS = 14


def _is_fresh(datestr: str, today: _dt.date) -> bool:
    """Is this message still transient -- i.e. too new for the recipient to have triaged it?"""
    try:
        sent = _dt.date.fromisoformat(datestr)
    except ValueError:
        return False  # unparseable => not exempt; the budget is the safe default
    return (today - sent).days <= INBOUND_GRACE_DAYS


def _without_inbound(lines: list[str], today: _dt.date | None = None) -> list[str]:
    """The file minus any cross-line message block that is still FRESH.

    WHY FRESH AND NOT FOREVER. The exemption is real and stays: the budget is a repo-wide gate over
    every tracked file, so charged naively it becomes a trap that fires on the recipient. Line X
    sitting at 117 of its 120 lines has three lines of headroom, an inbound block costs eight
    whatever its body says, and so ANY message from another line turns the build red for everyone --
    through no action of the recipient, who cannot pre-empt it and may not open a session for days.
    That happened on 2026-09-10 and is what prompted the exemption.

    WHY IT MUST EXPIRE. The exemption was written on the premise, stated in its own docstring, that
    "an inbound is transient by construction -- it is read, actioned, and rotated away". Nothing
    made that true. Rotation needs a human to add an `## ARCHIVE` heading, and an exempt block
    creates no pressure to do it, so the inbox only ever grows: by 2026-09-18 line D's STATE.md was
    436 lines of which 338 were 17 message blocks, all uncounted, and the gate reported it clean at
    a budget of 120. Two of those blocks carried undischarged one-line asks against corpus v2 --
    line T's soil-type columns and the treeless `pft_frac_*` NaN fix -- both of which said "land it
    in the version bump, it gets more expensive after". v2 was built and declared closed without
    either. That is invariant 9 exactly: a chore with a triggering event and no failing gate.

    So a message is free while the recipient plausibly has not seen it, and after that it is theirs:
    it has been read and actioned (rotate it) or it has not (that is the thing worth failing over).
    The clock is the trigger the chore never had. `check_skill_hygiene` below already fails a build
    on elapsed time alone, so this is the repo's existing shape, not a new one.

    A block runs from its heading to the next `## ` heading, or to the end of the file.
    """
    today = today or _dt.date.today()
    out: list[str] = []
    skipping = False
    for ln in lines:
        m = _INBOUND_HEADING.match(ln)
        if m:
            # A stale block stops any skip in progress and is counted from its own heading down.
            skipping = _is_fresh(m.group("date"), today)
            if skipping:
                continue
        elif skipping and ln.startswith("## "):
            skipping = False
        if not skipping:
            out.append(ln)
    return out


def check_line_budgets(rel: str, lines: list[str], budgets: list[dict], rep: Report) -> None:
    b = _budget_for(rel, budgets)
    if b is None:
        return
    limit = int(b["max_lines"])
    n = len(_without_inbound(lines)) if rel.endswith("STATE.md") else len(lines)
    if n > limit:
        over = n - limit
        # Say both numbers when they differ, so "123 lines" in the editor and "115 lines" in the
        # finding do not read as a bug in the gate.
        counted = (
            f"{n} lines"
            if n == len(lines)
            else (
                f"{n} of {len(lines)} lines "
                f"({len(lines) - n} in messages under {INBOUND_GRACE_DAYS} days old)"
            )
        )
        rep.add(
            rel,
            "B01",
            f"{counted}, budget {limit} (over by {over})",
            hint=b.get("note", "")
            or "rotate with tools/rotate_state.py, or move depth to a reference file",
        )

    # Structural row format. This is what makes MEMORY.md unable to become a narrative: a row that
    # is not a fixed-column table row is a finding, so the file's SHAPE is enforced, not just its
    # size.
    row_format = b.get("row_format")
    if row_format:
        rx = re.compile(str(row_format))
        for i, ln in enumerate(lines, start=1):
            s = ln.strip()
            if not s.startswith("|"):
                continue
            # Skip the header row and the |---|---| separator.
            if re.fullmatch(r"\|[\s|:-]+\|", s):
                continue
            if s.startswith("| id ") or s.startswith("| Kind "):
                continue
            if not rx.match(s):
                rep.add(
                    rel,
                    "B02",
                    "table row does not match the required fixed-column format",
                    line=i,
                    hint=(
                        "rows are `| id | fact (<=200 chars) | source | YYYY-MM-DD |` — prose "
                        "belongs in a skill or docs/reference/"
                    ),
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
                    "the predecessor accumulated seven partially-superseding root planning "
                    "documents (~1,584 lines) that every session was told to read. Put this in "
                    "docs/reference/, "
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
                hint=(
                    "merge or delete one first — a cap is what convenes the dedup pass that "
                    "otherwise never happens"
                ),
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
                    hint=(
                        "push depth into references/, which is loaded on demand instead of "
                        "inventoried every session"
                    ),
                )


def check_owner_trailer(files: list[str], rep: Report) -> None:
    """A budget may only be RAISED by the owner.

    Without this the whole scheme is circular: the agent bound by a cap can edit the cap. Only fires
    when budgets.toml is MODIFIED -- adding the file (the bootstrap commit) is not a budget change,
    and neither is deleting it.
    """
    if "config/budgets.toml" not in files:
        return

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo_root()), *args], capture_output=True, text=True, check=False
        ).stdout

    # Was budgets.toml ACTUALLY changed by the change under review?
    #
    # This guard is load-bearing and its first version was wrong in a way worth recording. It fired
    # whenever "config/budgets.toml" merely appeared in the file list -- and in the default mode
    # that
    # list is every TRACKED file, so the check fired on every clean run of the whole repo and
    # reported a budget change that had not happened. A gate that cries wolf gets bypassed, and a
    # bypassed gate is worse than none.
    staged = _git("diff", "--cached", "--name-status", "--", "config/budgets.toml").strip()
    if staged:
        # A fresh ADD is the bootstrap commit, not a budget change.
        if staged.startswith("A"):
            return
    else:
        # Nothing staged => judge from history. Only complain if the file differs from its state at
        # the merge base (CI) or in the last commit (local).
        base = (
            _git("merge-base", "origin/main", "HEAD").strip() or _git("rev-parse", "HEAD~1").strip()
        )
        if not base:
            return
        if not _git("diff", "--name-only", base, "HEAD", "--", "config/budgets.toml").strip():
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
            hint=(
                "a budget is raised by the owner, not by the agent it binds. "
                f"Add the trailer `{OWNER_TRAILER}`"
            ),
        )


def check_skill_hygiene(hygiene: dict, rep: Report) -> None:
    """Unused skills become visible, then warn, then fail.

    Reads .claude/skill-usage.log (one `<iso8601>\t<skill>` line per invocation, appended by a
    hook).
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
                hint=(
                    "delete it, merge it into a neighbour, or list it in "
                    ".claude/skills/RETENTION.md with a reason"
                ),
            )


# A pointer to a skill, as the runbook and the hooks actually write it: `Skill: commit-and-merge`,
# ``Skill: `experiment-registry` ``, `Method: `method-discipline``. The kebab requirement (at least
# one hyphen) is what keeps ordinary prose after a "Method:" heading from matching.
SKILL_REF = re.compile(r"\b(?:Skill|Method)s?:\s*`?([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`?")

# Where a dangling pointer actually costs a session: the always-loaded runbook, the hooks (which
# print skill names while DENYING a command), and the skills' own cross-references.
SKILL_REF_SOURCES = ("CLAUDE.md", ".claude/hooks/*.sh", ".claude/skills/*/SKILL.md")


def check_skill_refs(rep: Report) -> None:
    """B08: a named skill must exist.

    WHY THIS EXISTS. `CLAUDE.md` named five skills and one of them existed. Two of the names were
    printed at runtime by hooks -- `session-line-context.sh` at every session start, and
    `slurm-guard.sh` in the body of a DENY, so an agent was blocked and sent to a page that was not
    there. Line T recorded the hole on 2026-09-09 ("referenced everywhere and enforced nowhere") and
    line X hit it again on 2026-09-15; nothing failed in between, because nothing was watching. That
    is the exact shape invariant 9 rules out: a chore with no triggering event and no failing gate.
    """
    root = repo_root()
    have = {p.parent.name for p in root.glob(".claude/skills/*/SKILL.md")}
    for pattern in SKILL_REF_SOURCES:
        for path in sorted(root.glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(path.relative_to(root))
            for lineno, ln in enumerate(text.splitlines(), start=1):
                for m in SKILL_REF.finditer(ln):
                    name = m.group(1)
                    if name in have:
                        continue
                    rep.add(
                        rel,
                        "B08",
                        f"names skill {name!r}, which does not exist",
                        line=lineno,
                        hint=(
                            f"write .claude/skills/{name}/SKILL.md, or remove the pointer. A "
                            "pointer to a page that is not there is worse than no pointer: it "
                            "sends a blocked session hunting for it"
                        ),
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
    # Repo-wide, not per-file: the pointer and the skill it names are almost never in the same diff,
    # so a --staged run that only looked at changed files would miss every real case.
    check_skill_refs(rep)

    return rep.emit()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
