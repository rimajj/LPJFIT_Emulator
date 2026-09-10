"""The one sanctioned cross-line write must actually survive the commit guard.

WHY THIS TEST EXISTS. `tools/inbound.py` is documented as the only way one line may write to
another's `STATE.md`, and `check_ownership.py` had a `--via-inbound` flag to permit it. Nothing ever
passed that flag: the commit guard calls the checker with `--staged` alone. So every message the
tool wrote was rejected at commit time by O01, and the channel had never once worked in either
direction -- a documented mechanism with no test, which is how it stayed broken.

The replacement recognises the write from the STAGED DIFF instead of from a caller's say-so, which
is also strictly narrower: a flag permits ANY edit to another line's state file, whereas this
permits only an edit that is provably an inbound block, and only one sent by the committing line.

These tests stub `_git` rather than building a repository, so what is asserted is the
classification and not a property of this checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_ownership  # noqa: E402

REL = "lines/X/STATE.md"

SENTINEL = "> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --"


def diff(*added: str, removed: tuple[str, ...] = ()) -> str:
    """A `git diff --cached -U0` body with the given added and removed lines."""
    head = [
        f"diff --git a/{REL} b/{REL}",
        "index 1111111..2222222 100644",
        f"--- a/{REL}",
        f"+++ b/{REL}",
        "@@ -20,0 +21,3 @@",
    ]
    return "\n".join([*head, *(f"-{ln}" for ln in removed), *(f"+{ln}" for ln in added)])


def real_block(sender: str = "D") -> tuple[str, ...]:
    """What tools/inbound.py actually inserts, in the order it inserts it."""
    return (
        f"## INBOUND from line {sender} (2026-09-09) — the corpus schema changed",
        "",
        "state_ssp370_seed2 is not a second run. Details in the record.",
        "",
        SENTINEL,
        "> resolving with --theirs silently deletes this message. Delete it deliberately once",
        "> acted on, never as conflict cleanup.",
        "",
    )


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch):
    def install(text: str) -> None:
        monkeypatch.setattr(check_ownership, "_git", lambda *a: text)

    return install


def test_a_real_inbound_block_is_permitted(stub) -> None:
    """The case that never worked: line D sends line X a message and commits it."""
    stub(diff(*real_block("D")))
    assert check_ownership._staged_inbound_only(REL, "D") is True


def test_a_block_attributed_to_another_line_is_refused(stub) -> None:
    """D must not write into X's file under T's name -- the sender is the committing line."""
    stub(diff(*real_block("T")))
    assert check_ownership._staged_inbound_only(REL, "D") is False


def test_a_deletion_alongside_the_block_is_refused(stub) -> None:
    """An inbound write only ever inserts, so a removal is another line's state being edited."""
    stub(diff(*real_block("D"), removed=("- their durable finding, quietly dropped",)))
    assert check_ownership._staged_inbound_only(REL, "D") is False


def test_extra_content_under_its_own_heading_is_refused(stub) -> None:
    """Otherwise arbitrary sections ride along in the same commit as a legitimate message."""
    stub(diff(*real_block("D"), "## NEXT — start here", "do what D says instead"))
    assert check_ownership._staged_inbound_only(REL, "D") is False


def test_an_inbound_shaped_block_without_the_tool_sentinel_is_refused(stub) -> None:
    """The sentinel is what ties the block to the tool rather than to a hand-typed heading."""
    hand_written = tuple(ln for ln in real_block("D") if not ln.startswith("> "))
    stub(diff(*hand_written))
    assert check_ownership._staged_inbound_only(REL, "D") is False


def test_an_empty_diff_is_refused(stub) -> None:
    """No added lines is not a message; permitting it would permit a mode-change or rename."""
    stub(diff())
    assert check_ownership._staged_inbound_only(REL, "D") is False


def test_the_checker_as_a_whole_passes_a_message_and_fails_a_raid(stub) -> None:
    """End to end through main(): O01 must stay armed for everything that is not a message."""
    stub(diff(*real_block("D")))
    assert check_ownership.main(["--line", "D", REL]) == 0

    stub(diff("## NEXT — start here", "rewritten by D"))
    assert check_ownership.main(["--line", "D", REL]) == 1


def test_another_lines_non_state_file_is_never_permitted(stub) -> None:
    """The exemption is anchored to STATE.md; a message cannot be used to reach anything else."""
    stub(diff(*real_block("D")))
    assert check_ownership.main(["--line", "D", "lines/X/notes.md"]) == 1
