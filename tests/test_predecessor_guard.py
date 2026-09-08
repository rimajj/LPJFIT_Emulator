"""The old project must not be changed in any way — as an executable test, not a note.

The owner's standing instruction (2026-09-08) is that the OLD hybrid emulator project is not to be
modified. This repo exists to reuse what transfers from it (`docs/reference/inherited.md`) as an
independent project. Two things make that easy to violate by accident:

  * the two GitHub repository names differ by two letters —
        rimajj/LPJmLFIT_Emulator   the OLD hybrid project
        rimajj/LPJFIT_Emulator     THIS project
    so a copied or mistyped push lands on the wrong repository;
  * the old project's checkout sits beside this one on the same filesystem.

`.claude/hooks/predecessor-guard.sh` denies both. This test is why that hook can be trusted: a hook
is invisible when it works, so nothing but a test distinguishes "correctly allowing everything" from
"not running at all". That distinction is not academic — the hook was written with no execute bit,
and every deny case silently passed while every allow case passed too, which looks identical to
success unless the denials are asserted.

READS ARE DELIBERATELY ALLOWED: the old project is the read-only archive of record, so citing it is
the point. Only mutation is denied — and copies are direction-sensitive, because taking something
FROM the old project INTO this one is the entire reuse plan.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "predecessor-guard.sh"

# These absolute paths are the SUBJECT of the test, not a configuration value: the guard is defined
# by which literal paths it refuses, so reading them from config/paths.yaml would mean the test no
# longer states what it checks. Marked per line, as tools/check_no_abs_paths.py prescribes for a
# file that must name a forbidden pattern in order to enforce it.
OLD = "/p/projects/open/Jamir/esm_land_emulator"  # pathsafety: allow (the guard's target)
OLD_WT_S = "/p/projects/open/Jamir/wt-S"  # pathsafety: allow (a worktree it guards)
OLD_WT_E = "/p/projects/open/Jamir/wt-E"  # pathsafety: allow (a worktree it guards)
SCRATCH = "/p/tmp/jamirp/vegemu"  # pathsafety: allow (a path it must NOT guard)
OLD_URL = "git@github-esm:rimajj/LPJmLFIT_Emulator.git"

MUST_DENY = [
    # --- writes to the old project's GitHub repository
    f"git push {OLD_URL} main",
    "git push --force github-esm main",
    f"git push -f {OLD_URL} --all",
    f"git remote set-url origin {OLD_URL}",
    f"cd /tmp && git push --force-with-lease {OLD_URL} line/X",
    # --- writes to the old project's files on disk
    f"git -C {OLD} commit -am wip",
    f"git -C {OLD} reset --hard HEAD~3",
    f"git -C {OLD_WT_S} rebase main",
    f"rm -rf {OLD}/docs",
    f"sed -i s/old/new/ {OLD}/MEMORY.md",
    f"echo hi >> {OLD}/JOURNAL.md",
    f"mv {OLD_WT_E}/x {OLD_WT_E}/y",
    f"chmod -R 777 {OLD}",
    # --- a copy INTO the old project is still a write to it
    f"cp docs/reference/inherited.md {OLD}/notes.md",
    f"rsync -a docs/ {OLD}/docs/",
    # --- moving OUT of the old tree removes it from the old tree
    f"mv {OLD}/x.md docs/reference/x.md",
]

MUST_ALLOW = [
    # --- reading the old project is the point
    f"git -C {OLD} log --oneline -20",
    f"git -C {OLD} show 4ffc58a --stat",
    f"git -C {OLD} status --short",
    f"git -C {OLD} diff HEAD~1",
    f"grep -rn noise {OLD}/docs",
    f"head -50 {OLD}/EXECUTION_PLAN.md",
    f"git ls-remote --heads {OLD_URL}",
    # --- taking FROM the old project INTO this one: the reuse plan
    f"cp -r {OLD}/docs/decisions/0311.md docs/reference/",
    f"rsync -a {OLD}/artifacts/ {SCRATCH}/ref/",
    # --- normal work on THIS project must not trip the guard
    "git push --force-with-lease origin main",
    "git push --force-with-lease origin line/X",
    "git push git@github-lpjfit:rimajj/LPJFIT_Emulator.git main",
    'git commit -am "fix: thing"',
    f"rm -rf {SCRATCH}/runs/tmp",
    "git push --delete origin line/E",
]


def verdict(command: str) -> str:
    """Either "deny" or "allow", as the hook decides for `command`."""
    proc = subprocess.run(
        [str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"hook exited {proc.returncode}: {proc.stderr}")
    out = proc.stdout.strip()
    if not out:
        return "allow"
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        pytest.fail(f"hook emitted non-JSON: {out[:200]}")
    return str(payload.get("hookSpecificOutput", {}).get("permissionDecision", "allow"))


def test_hook_is_executable() -> None:
    """Without the execute bit the hook cannot deny anything, and every case below passes
    vacuously. This exact mistake was made while writing it."""
    assert HOOK.is_file(), f"missing: {HOOK}"
    assert HOOK.stat().st_mode & 0o111, f"{HOOK} is not executable, so it denies nothing"


@pytest.mark.parametrize("command", MUST_DENY)
def test_mutating_the_old_project_is_denied(command: str) -> None:
    assert verdict(command) == "deny", f"the guard let this through: {command}"


@pytest.mark.parametrize("command", MUST_ALLOW)
def test_reading_it_and_normal_work_are_allowed(command: str) -> None:
    assert verdict(command) == "allow", f"the guard blocked legitimate work: {command}"


def test_the_remote_pattern_separates_the_two_repository_names() -> None:
    """The guard's own OLD_REMOTE pattern must match the old repository and NOT this one.

    Read out of the hook rather than restated here: a copy of the pattern in the test would keep
    passing after the hook's pattern changed, which is the failure mode a test is meant to catch.
    If this pattern ever matched this project's name, the guard would block our own pushes.
    """
    line = next(
        ln for ln in HOOK.read_text(encoding="utf-8").splitlines() if ln.startswith("OLD_REMOTE=")
    )
    pattern = line.split("=", 1)[1].strip().strip("'\"")
    assert re.search(pattern, "git@github-esm:rimajj/LPJmLFIT_Emulator.git"), pattern
    assert not re.search(pattern, "git@github-lpjfit:rimajj/LPJFIT_Emulator.git"), (
        f"the guard's remote pattern {pattern!r} also matches THIS project's remote, "
        "so it would block our own pushes"
    )
