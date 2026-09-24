"""The STATE rotation must never trade one budget breach for another.

WHY THIS EXISTS. `tools/rotate_state.py` is the one sanctioned way to get a `lines/<L>/STATE.md`
under its 120-line budget: move stale sections under `## ARCHIVE`, and the tool appends them to the
line's journal. It appended to `journal/<L>/<YYYY-MM>.md` UNCONDITIONALLY, while the journal budget
(800 lines) promised "auto-rotated by the writer at the cap" -- and nothing rotated. On 2026-09-23
line T's September journal stood at 597 lines with ~300 lines of cross-line messages due out of its
STATE file before their 14-day budget exemption lapsed, so rotating would have put the journal over
ITS budget and the commit guard would have refused the pair.

The tool now rolls over to `<YYYY-MM>b.md`, `c`, ... Every test pins an explicit `today` and cap, so
none depends on the wall clock or on `config/budgets.toml`, except the last, which pins the cap the
tool reads from the real config to the one the budget gate enforces.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from rotate_state import choose_journal, journal_cap, journal_series, rotate

TODAY = dt.date(2026, 9, 23)
MONTH = "2026-09"


def _state(root: Path, line: str, archived: list[str]) -> Path:
    path = root / "lines" / line / "STATE.md"
    path.parent.mkdir(parents=True)
    kept = ["# Line T", "", "## NEXT — start here", "", "do the thing", "", "## Milestones", ""]
    path.write_text("\n".join([*kept, "## ARCHIVE", "", *archived]) + "\n", encoding="utf-8")
    return path


def _journal(root: Path, line: str, name: str, n: int) -> Path:
    path = root / "journal" / line / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line {i}\n" for i in range(n)), encoding="utf-8")
    return path


def _n(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_an_archive_that_fits_is_appended_to_the_current_file(tmp_path: Path) -> None:
    j = _journal(tmp_path, "T", f"{MONTH}.md", 50)
    state = _state(tmp_path, "T", ["### old block", "", "body"])
    assert rotate(tmp_path, "T", TODAY, cap=100) == 0
    assert journal_series(j.parent, MONTH) == [j]
    text = j.read_text(encoding="utf-8")
    assert "## 2026-09-23 — rotated out of STATE.md" in text and text.endswith("body\n")
    assert "## ARCHIVE" not in state.read_text(encoding="utf-8")
    assert state.read_text(encoding="utf-8").endswith("## Milestones\n")


def test_an_archive_that_would_pass_the_cap_starts_the_next_part(tmp_path: Path) -> None:
    """The case that forced this: T at 597 of 800 with ~300 lines to archive."""
    j = _journal(tmp_path, "T", f"{MONTH}.md", 597)
    body = [f"message line {i}" for i in range(300)]
    _state(tmp_path, "T", body)
    assert rotate(tmp_path, "T", TODAY, cap=800) == 0
    b = j.parent / f"{MONTH}b.md"
    assert _n(j) == 597, "the full part must not be touched"
    assert journal_series(j.parent, MONTH) == [j, b]
    assert _n(b) <= 800
    text = b.read_text(encoding="utf-8")
    assert text.startswith(f"# Line T journal — {MONTH} (continued)")
    assert f"Continues `{MONTH}.md`" in text
    assert all(ln in text for ln in body), "nothing may be lost in the move"


def test_the_part_after_b_is_c_and_parts_sort_in_writing_order(tmp_path: Path) -> None:
    _journal(tmp_path, "X", f"{MONTH}.md", 800)
    _journal(tmp_path, "X", f"{MONTH}b.md", 795)
    _state(tmp_path, "X", ["a", "b", "c", "d", "e"])
    assert rotate(tmp_path, "X", TODAY, cap=800) == 0
    series = journal_series(tmp_path / "journal" / "X", MONTH)
    assert [p.name for p in series] == [f"{MONTH}.md", f"{MONTH}b.md", f"{MONTH}c.md"]
    # Lexical order is writing order, and a part never sorts after the next month's first file.
    assert sorted(p.name for p in series) == [p.name for p in series]
    assert sorted([f"{MONTH}c.md", "2026-10.md"])[0] == f"{MONTH}c.md"


def test_exactly_at_the_cap_still_fits(tmp_path: Path) -> None:
    jdir = tmp_path / "journal" / "D"
    _journal(tmp_path, "D", f"{MONTH}.md", 10)
    addition = "\n## 2026-09-23 — rotated out of STATE.md\n\nx\n"  # 4 lines onto 10
    path, text = choose_journal(jdir, "D", MONTH, addition, cap=14)
    assert path.name == f"{MONTH}.md" and len(text.splitlines()) == 14
    path, _ = choose_journal(jdir, "D", MONTH, addition, cap=13)
    assert path.name == f"{MONTH}b.md"


def test_an_archive_too_big_for_an_empty_file_is_refused_and_nothing_moves(
    tmp_path: Path,
) -> None:
    j = _journal(tmp_path, "T", f"{MONTH}.md", 10)
    state = _state(tmp_path, "T", [f"l{i}" for i in range(50)])
    before = state.read_text(encoding="utf-8")
    assert rotate(tmp_path, "T", TODAY, cap=20) == 1
    assert state.read_text(encoding="utf-8") == before
    assert journal_series(j.parent, MONTH) == [j] and _n(j) == 10


def test_a_months_first_rotation_creates_part_one(tmp_path: Path) -> None:
    _state(tmp_path, "D", ["only line"])
    assert rotate(tmp_path, "D", TODAY, cap=800) == 0
    j = tmp_path / "journal" / "D" / f"{MONTH}.md"
    assert j.read_text(encoding="utf-8").startswith("## 2026-09-23 — rotated out of STATE.md")


def test_no_cap_never_rolls_over(tmp_path: Path) -> None:
    j = _journal(tmp_path, "D", f"{MONTH}.md", 5000)
    _state(tmp_path, "D", ["x"])
    assert rotate(tmp_path, "D", TODAY, cap=None) == 0
    assert journal_series(j.parent, MONTH) == [j]


def test_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    j = _journal(tmp_path, "T", f"{MONTH}.md", 799)
    state = _state(tmp_path, "T", ["x", "y"])
    before = state.read_text(encoding="utf-8")
    assert rotate(tmp_path, "T", TODAY, cap=800, dry_run=True) == 0
    assert state.read_text(encoding="utf-8") == before and _n(j) == 799
    assert not (j.parent / f"{MONTH}b.md").exists()
    assert f"journal/T/{MONTH}b.md (a NEW part" in capsys.readouterr().out


def test_the_cap_is_the_one_the_budget_gate_enforces() -> None:
    """Read from the real config/budgets.toml, so the writer and the gate share one number."""
    assert journal_cap("T", MONTH) == 800
    assert journal_cap("X", f"{MONTH}b") == 800
