"""A cross-line message must not spend the recipient's line budget -- FOR TWO WEEKS.

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

WHY THE EXEMPTION EXPIRES, added 2026-09-18. The original exemption was unbounded, resting on the
premise -- written in its own docstring -- that "an inbound is transient by construction: it is
read, actioned, and rotated away". Nothing made that true. Rotation needs a human to add an
`## ARCHIVE` heading, and a permanently exempt block creates no pressure to do it, so the inbox only
grew. On 2026-09-18 line D's STATE.md was 436 lines, 338 of them 17 message blocks, and the gate
called it clean against a budget of 120. Two of those blocks held undischarged one-line asks that
both said "land it in the corpus version bump, it gets more expensive after"; the bump shipped
without either. So the grace period is the trigger the rotation chore never had.

The exemption is still deliberately narrow: only message blocks, only in a `STATE.md`, only with the
heading `tools/inbound.py` writes, only while dated within the grace window. Everything the owner
wrote is counted exactly as before — a line cannot buy headroom by being messaged, and now it cannot
buy it by being messaged a long time ago either.

EVERY TEST HERE PINS AN EXPLICIT `today`. A test that read the wall clock would be the same bug one
level up: it would pass on the day it was written and start failing on its own later.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from check_budgets import INBOUND_GRACE_DAYS, _without_inbound

SENT = dt.date(2026, 9, 10)
FRESH = SENT + dt.timedelta(days=INBOUND_GRACE_DAYS)  # the last day it is still free
STALE = SENT + dt.timedelta(days=INBOUND_GRACE_DAYS + 1)  # the first day it is charged

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


def test_a_fresh_inbound_block_is_not_counted() -> None:
    assert _without_inbound(OWN + INBOUND + TAIL, FRESH) == OWN + TAIL


def test_the_senders_fresh_mirror_is_not_counted_either() -> None:
    """The mirror is the sender's evidence that the message was sent; it is equally transient."""
    assert _without_inbound(OWN + MIRROR + TAIL, FRESH) == OWN + TAIL


def test_several_blocks_and_a_block_at_end_of_file() -> None:
    assert _without_inbound(OWN + INBOUND + MIRROR + TAIL, FRESH) == OWN + TAIL
    assert _without_inbound(OWN + INBOUND, FRESH) == OWN


def test_the_owners_own_lines_are_still_counted() -> None:
    """The property that keeps the budget meaningful: being messaged buys no headroom."""
    long_own = OWN + [f"durable state line {i}" for i in range(200)]
    assert len(_without_inbound(long_own + INBOUND, FRESH)) == len(long_own)
    assert len(_without_inbound(long_own, FRESH)) == len(long_own)


def test_a_heading_that_merely_mentions_inbound_is_still_counted() -> None:
    """Narrow by design — only the headings the tool actually writes are exempt."""
    sneaky = [*OWN, "## Notes on the INBOUND process", "", "prose", "", *TAIL]
    assert _without_inbound(sneaky, FRESH) == sneaky


# --- the expiry: what stops an exempt inbox growing forever ---------------------------------


def test_a_stale_inbound_block_IS_counted() -> None:
    """The whole point. Past the window the message is the recipient's own content."""
    assert _without_inbound(OWN + INBOUND + TAIL, STALE) == OWN + INBOUND + TAIL
    assert _without_inbound(OWN + MIRROR + TAIL, STALE) == OWN + MIRROR + TAIL


def test_the_boundary_is_inclusive_and_one_day_apart() -> None:
    """Pin both sides, so a drift from <= to < is a failing test and not a silent week."""
    assert _without_inbound(INBOUND, FRESH) == []
    assert _without_inbound(INBOUND, STALE) == INBOUND
    assert (STALE - FRESH).days == 1


def _mirror_on(d: dt.date) -> list[str]:
    return [
        f"## Outbound to line D ({d.isoformat()}) — please add soil type",
        "",
        "the same message, kept by the sender as evidence it was sent",
        "",
    ]


def test_a_stale_block_does_not_swallow_the_fresh_one_after_it() -> None:
    """A counted heading must end any skip in progress, or real state would vanish between blocks.

    The mixed case is the one worth pinning: the skip is a running flag, so a block that is NOT
    exempt has to clear it. If it did not, an old message would silently eat every line up to the
    next `## ` heading -- which is how an exemption turns into data loss instead of a budget.
    """
    # On FRESH, the August mirror is long stale and INBOUND (2026-09-10) is exactly at the edge.
    old_mirror = _mirror_on(dt.date(2026, 8, 1))
    assert _without_inbound([*OWN, *old_mirror, *INBOUND, *TAIL], FRESH) == [
        *OWN,
        *old_mirror,
        *TAIL,
    ]
    # And on a day where both are stale, nothing is removed at all.
    assert _without_inbound(OWN + MIRROR + INBOUND + TAIL, STALE) == OWN + MIRROR + INBOUND + TAIL


def test_an_undated_message_heading_is_counted() -> None:
    """No date means it cannot be aged, so it does not get the exemption."""
    undated = [*OWN, "## INBOUND from line T — no date here", "", "body", "", *TAIL]
    assert _without_inbound(undated, FRESH) == undated


def test_an_unparseable_date_is_counted() -> None:
    bad = [*OWN, "## INBOUND from line T (2026-13-45) — impossible date", "", "body", "", *TAIL]
    assert _without_inbound(bad, FRESH) == bad
