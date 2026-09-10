"""A cross-line message must not spend the recipient's line budget.

WHY THIS EXISTS. `tools/inbound.py` is the one sanctioned cross-line write, and `check_budgets` is
a repo-wide gate over every tracked file — it is run bare in CI, so it inspects the whole tree, not
just the diff. Charged naively those two combine into a trap that fires on the recipient:

    line X sits at 117 of its 120 lines — three lines of headroom
    an inbound block costs eight lines whatever its body says
    so ANY message from another line turns the build red, for everyone

The recipient did nothing, cannot pre-empt it, and may not open a session for days; meanwhile the
sender either drops the message or knowingly breaks the build. That happened on 2026-09-10, when a
line-T session sending two required messages found both recipients pushed over budget by the act of
being told something.

The exemption is deliberately narrow. Only the message blocks are uncounted, only in a `STATE.md`,
and only when they carry the heading `tools/inbound.py` writes. Everything the owner wrote is still
counted exactly as before — a line cannot buy headroom by being messaged, which is the property
that keeps the budget meaningful.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_budgets import _without_inbound

OWN = [
    "# Line X — experiments",
    "",
    "## NEXT — start here",
    "",
    "do the thing",
]
INBOUND = [
    "## INBOUND from line T (2026-09-10) — the corpus schema changed",
    "",
    "> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --",
    "",
    "body line one",
    "body line two",
    "",
]
MIRROR = [
    "## Outbound to line D (2026-09-10) — please add soil type",
    "",
    "the same message, kept by the sender as evidence it was sent",
    "",
]
TAIL = ["## Milestones", "", "X0 — done"]


def test_an_inbound_block_is_not_counted() -> None:
    assert _without_inbound(OWN + INBOUND + TAIL) == OWN + TAIL


def test_the_senders_mirror_is_not_counted_either() -> None:
    """The mirror is the sender's evidence that the message was sent; it is equally transient."""
    assert _without_inbound(OWN + MIRROR + TAIL) == OWN + TAIL


def test_several_blocks_and_a_block_at_end_of_file() -> None:
    assert _without_inbound(OWN + INBOUND + MIRROR + TAIL) == OWN + TAIL
    assert _without_inbound(OWN + INBOUND) == OWN


def test_the_owners_own_lines_are_still_counted() -> None:
    """The property that keeps the budget meaningful: being messaged buys no headroom."""
    long_own = OWN + [f"durable state line {i}" for i in range(200)]
    assert len(_without_inbound(long_own + INBOUND)) == len(long_own)
    assert len(_without_inbound(long_own)) == len(long_own)


def test_a_heading_that_merely_mentions_inbound_is_still_counted() -> None:
    """Narrow by design — only the headings the tool actually writes are exempt."""
    sneaky = [*OWN, "## Notes on the INBOUND process", "", "prose", "", *TAIL]
    assert _without_inbound(sneaky) == sneaky
