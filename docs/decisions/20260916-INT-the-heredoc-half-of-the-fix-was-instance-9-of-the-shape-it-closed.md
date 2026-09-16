# The heredoc half of the lexer fix was instance 9 of the shape it had just closed

- **Status:** accepted; fixed, pinned, and verified by re-running the command that was refused
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/_lex_command.py`
- **Follows** `20260916-INT-the-lexer-fix-is-applied-and-a-third-hole-was-found-in-review.md`, which
  is accepted and unedited. This records a defect found AFTER that record was written, in the change
  it describes. Neither earlier record is retracted; both diagnoses stand.

## What happened

Minutes after the fix landed on main with a green suite, an ordinary `tools/inbound.py` call was
**denied as heavy Python on the login node**. It runs nothing. Its `--body` carried the before/after
table from the previous record, which contains the literal string `git commit -F - <<'MSG'`.

## The cause, reproduced against the denied command rather than guessed

The new `HEREDOC` pattern was run over the **raw** command text. So it matched a heredoc marker that
was being *talked about* inside a quoted `--body` argument, treated the rest of that line as the end
of the command, and cut there. The cut left an unbalanced quote, `shlex` raised, and the file's
fail-closed path handed back the RAW string as the scan — which mentions `corpus/`, so the keyword
rule fired and the command was refused.

**This file's whole thesis is that a guard must judge the thing it guards, and the half of the fix
written to enforce that thesis violated it.** Instances 7 and 8 were the segmenter splitting raw
characters; the fix moved the segmenter to tokens and left the new heredoc pattern on raw text. Same
shape, one function further along, shipped in the same commit.

| | reads | can it tell prose from shell? |
|---|---|---|
| segmenter, before 2026-09-16 | raw characters | no — instances 7 and 8 |
| segmenter, after | lexer tokens | yes |
| heredoc pattern, as first written | raw characters | **no — instance 9** |
| heredoc pattern, now | gated on a lexer token | yes |

## The fix

Ask the lexer first. `<<` is a real redirection only when it comes back as its **own operator
token**, which it never does from inside a quoted argument. If no such token is present, the command
has no heredoc and no pattern is allowed near its text. The pattern itself is unchanged; what
changed is that it now only ever runs on a command already known to contain a real `<<`.

Pinned in `MUST_ALLOW` as the exact `inbound.py` call that was refused, body and all. Suite: 298
passed, 1 skipped. Every must-deny case is unchanged, re-verified by running the old and new lexer
against the same inputs.

## The lesson, which is about WHERE it was caught

The previous record's "third hole" was caught by **reading** the change — good, and cheap. This one
was caught by **being blocked by it during ordinary work**, after the change was committed, pushed,
and green on four gates. A test suite full of hand-written commands cannot contain the command you
have not written yet, and the one that broke it was a message *about* the fix.

⚠ **A guard change is not finished when its tests pass. It is finished when it has been used.** The
verification that mattered here was re-sending the refused message and watching it go through. Every
guard change in this repo should end with that step, on a command nobody wrote a test for.

## Count

`MEMORY.md:guard-reads-wrong-input` goes from eight instances to **nine**, and the row now names
where 9 was found, because that is the part that is new: not that a guard read the wrong input
again, but that it did so inside the fix for the previous two, and survived a green suite.
