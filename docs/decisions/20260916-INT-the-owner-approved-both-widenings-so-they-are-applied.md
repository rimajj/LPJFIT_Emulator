# The owner approved both widenings, so they are applied — and the pinned defects are now pins

- **Status:** accepted; applied, verified, and the suite's xfail markers removed
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/_lex_command.py`, `tests/test_guard_generated.py`
- **Follows** `20260916-INT-an-unlexable-heredoc-body-defeats-the-rule-that-a-body-is-data.md`,
  which is accepted, unedited, and still says the fix is not applied. It was not, when it was
  written. This records the decision that changed that.

## The decision

Both changes widen what a permission hook treats as safe, so neither was an agent's to make. Put to
the owner with the measurement below, the answer was **apply both**.

**A.** When the raw command text will not lex, decide whether a heredoc exists by lexing the longest
**prefix** that does lex. A body begins on the line after its redirection, so any prefix that lexes
is command text. No lexable prefix carrying a real `<<` means the text is an unbalanced *command*,
and it fails closed exactly as before.
**B.** `echo printf true false pwd cd test [` join `SAFE_VERBS`. None can execute a file.

## What it changed, measured on three bases before and after

| basis | before | after |
|---|---|---|
| write each of 178 tracked files with `cat … <<'PY'` (runs nothing) | 12 refused | **0** |
| the 64 pinned + adversarial cases in `tests/test_slurm_guard.py` | — | **0 change, 0 wrong** |
| the 1,312 distinct commands this repo's sessions have ever issued | 41 refused | **32 refused** |
| `tests/test_guard_generated.py`, ~250 generated commands | 2 families red | **all green** |

Every one of the nine commands that changed verdict runs nothing. The 32 still refused all hand
their text to `python3 -`, `bash`, or a `.py` program — which is the rule working.

Full suite: **306 passed, 11 skipped, 0 xfailed**, exit 0. Both strict `xfail` markers are gone,
which is the mechanism doing its job: the fix landing turned them into failures and forced their
removal in the same commit.

## What this pair of records is really about

The defect was found by a corpus, not by a person being blocked — the first of ten instances of this
shape to be caught that way. But the *fix* still had to be measured against commands that were
actually issued, and that is what showed the first draft too narrow: it inspected the first line
only, and this repository's commonest committing idiom puts the redirection on line two.

⚠ **So the discipline is symmetric. Generate the cases to find the bug; check the fix against real
traffic before believing it.** Neither corpus alone would have got this right: the generated one
cannot know which commands people actually write, and the real one cannot contain the command
nobody has written yet.
