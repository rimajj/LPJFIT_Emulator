"""Placeholder so the `test` gate has something to run before line D lands the format tests.

Deliberately asserts something real rather than `assert True`: that config/paths.yaml parses and
that the entry every other component depends on is present. A gate that cannot fail is not a gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _paths(key: str) -> str:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "_paths.py"), key],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, f"_paths.py {key} failed: {out.stderr}"
    return out.stdout.strip()


def test_paths_config_resolves_the_restart_target() -> None:
    """The file rung 0 must round-trip is named, and the name interpolates."""
    p = _paths("ground_truth.restart_spinup_end")
    assert p.endswith("restart_1999.lpj"), p
    assert "${" not in p, "an unresolved ${...} reference leaked through"


def test_paths_config_rejects_a_missing_key() -> None:
    """A missing key must fail loudly: a silent empty string in an sbatch line is how a job 'runs
    successfully' over no data."""
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "_paths.py"), "cells.does_not_exist"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 3
    assert "cells" in out.stderr


def test_prototype_cell_is_the_right_index() -> None:
    """42490, not 28008 -- the latter is Hainich in a different grid and the Sonoran desert here."""
    assert _paths("cells.hainich") == "42490"
