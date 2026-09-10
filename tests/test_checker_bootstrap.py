"""Every repository checker must run when started by whatever `python3` the caller happens to have.

WHY THIS EXISTS. `tools/_common.py`'s own contract says the checkers are called from three places --
a commit-deny hook, a git pre-commit hook, and CI -- and that "the caller must not have to care".
One of those callers does not get to choose its interpreter: the hook runs `python3` from whatever
PATH it inherits, and on this cluster's login nodes that is 3.9, which has no `tomllib`.

On 2026-09-10 that stopped being theoretical. Every checker died on the import, so the commit guard
refused every commit in the session with five tracebacks where five findings should have been -- and
its documented escape hatch could not lift it either, because the hook reads
ALLOW_COMMIT_GUARD_SKIP from its own environment rather than the caller's. A guard that fails closed
on its own environment is not a guard; it is an outage that looks like a verdict.

So a checker started by too old an interpreter now re-execs itself once under the one named in
`config/paths.yaml`. This test runs each checker under the bare `python3` a hook would find and
asserts it produces a verdict rather than a traceback. It is skipped when `python3` is already 3.11
or newer, because then there is nothing to prove.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
# The tools a hook or a shell wrapper invokes without choosing the interpreter. `--help` is enough:
# the failure being guarded against happened at IMPORT time, long before any argument was read.
TOOLS = (
    "check_budgets.py",
    "check_ownership.py",
    "check_experiments.py",
    "check_secrets.py",
    "check_no_abs_paths.py",
    "check_flags.py",
    "check_gates.py",
    "expected_gates.py",
    "wait_gates.py",
    "campaigns.py",
)


def _bootstrap_python() -> str:
    exe = shutil.which("python3")
    if exe is None:
        pytest.skip("no `python3` on PATH, so no bootstrap interpreter to test against")
    # As an integer, deliberately: the first version of this compared the repr of a version tuple
    # as a STRING, and "(3, 9)" > "(3, 11)" because "9" > "1" -- so every case skipped and the test
    # passed while proving nothing.
    out = subprocess.run(
        [exe, "-c", "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if int(out) >= 311:
        pytest.skip(
            f"`python3` is already 3.{int(out) - 300}; no older interpreter here to re-exec"
        )
    return exe


@pytest.mark.parametrize("tool", TOOLS)
def test_a_checker_started_by_an_old_python_still_produces_a_verdict(tool: str) -> None:
    exe = _bootstrap_python()
    proc = subprocess.run(
        [exe, str(REPO / "tools" / tool), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,  # the exit code IS the assertion below
    )
    combined = proc.stdout + proc.stderr
    assert "ModuleNotFoundError" not in combined, (
        f"{tool} died on an import under {exe} instead of re-execing:\n{combined}"
    )
    assert proc.returncode == 0, f"{tool} exited {proc.returncode} under {exe}:\n{combined}"


def test_this_interpreter_is_new_enough_to_be_the_target() -> None:
    """The re-exec target is only useful if the configured interpreter is itself 3.11 or newer."""
    assert sys.version_info >= (3, 11)
