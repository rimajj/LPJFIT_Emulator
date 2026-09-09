# The cross-line message channel is recognised from the diff, and is still half-blocked

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** D
- **Governs:** `tools/check_ownership.py`, `tools/inbound.py`
- **Found while** trying to ask line X a question that corpus v2 cannot be built without.

## The finding: two independent breakages, not one

`tools/inbound.py` is documented as the ONE sanctioned cross-line write. It has never worked, in
either direction, and for two unrelated reasons. Both were verified by attempting a real send today.

**1. The commit guard rejected every message.** `check_ownership.py` carried a `--via-inbound` flag
to permit the write, and nothing ever passed it — `.claude/hooks/commit-guard.sh` calls the checker
with `--staged` alone. So the tool wrote the block, and the commit that had to carry it was blocked
by O01 ("belongs exclusively to line X"). A documented mechanism, an unused flag, and no test.

**2. The recipient's line budget rejects it even when ownership does not.** `lines/X/STATE.md` is at
**exactly 120 lines, its cap**. Any inbound block of any length pushes it over, `check_budgets`
reddens, and because that gate is repo-wide it stops **every line's merge**, not just the sender's.
Measured: a 28-line message took X to 152/120 and D's own mirror copy to 143/120.

## The decision

**Breakage 1 is fixed here. The permission is derived from the staged diff, not from a flag.**
`_staged_inbound_only()` allows a cross-line write to `lines/*/STATE.md` only when all three hold:

- nothing is **removed** — an inbound write only ever inserts, so a deletion is another line's
  durable state being edited under cover of sending it a message;
- every added heading is an `## INBOUND from line <committing line>` header, so arbitrary content
  cannot ride along under a section of its own;
- the tool's sentinel line (`> Sent by tools/inbound.py.`) is present.

The message **body** is deliberately unconstrained; it is prose for another line to read.

This is not merely a way to avoid editing an integrator-owned hook. It is **strictly narrower than
the flag would have been**: a flag is a claim by the caller and would permit any edit whatsoever to
another line's state file, including deleting it. The diff check permits only an edit that is
provably a message, and only one sent by the line doing the committing. `--via-inbound` is kept as
an accepted-and-ignored argument so no existing caller breaks.

Eight tests in `tests/test_inbound_ownership.py`, including the two attacks the flag would have
waved through: a block attributed to a third line, and a deletion travelling with a legitimate
message. O01 stays armed for everything else — a message cannot be used to reach `lines/X/notes.md`.

**Breakage 2 is NOT fixed here, and must not be fixed from a line.** The obvious repairs — exempting
inbound blocks from the line-state budget, or landing messages somewhere unbudgeted — are changes to
the protocol that `CLAUDE.md` documents, and `CLAUDE.md`, `config/budgets.toml` and the hooks are all
integrator-owned. A line quietly redefining what its own budget counts is the circularity
`config/ownership.toml` exists to prevent. It is raised, not taken.

## What this costs while breakage 2 stands

The channel is usable **only to a recipient with headroom in their state file**, and X currently has
none. So the message X actually needs was not sent as an inbound block. It is this record and the
handoff in `lines/D/STATE.md` instead — which is the documented fallback, but it is a fallback:
a record is not delivered to anyone, it only sits where someone may look.

## Consequences

1. **The integrator is asked to decide breakage 2.** Either the recipient's budget must not count
   inbound blocks, or messages must land outside a budgeted file. Until then, a sender must check
   `wc -l lines/<to>/STATE.md` before writing, and a recipient at cap silently cannot be reached.
2. **`tools/inbound.py` should refuse to write to a recipient who is at or over budget**, rather
   than writing and printing a "keep it short" note that does not help when *no* length fits. It
   currently warns; it should measure. Left undone here only because the same integrator decision
   determines what the right threshold is.
3. **The question corpus v2 is blocked on stays open with line X**: whether `pft_frac_*` joins the
   scored set in the same rebuild that repoints the high-emissions second seed. Both change what a
   sealed pre-registration's scored set means; D will do one rebuild or the other, not two.
4. **A second integrator request is outstanding and unrelated**: `config/paths.yaml` needs a
   `ssp370_seed2_from_hist_seed2` key before that rebuild can run at all.
