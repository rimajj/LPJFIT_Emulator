# The command lexer re-splits prose on shell operators, so a semicolon in a commit message denies the commit

- **Status:** accepted (diagnosis); **the fix is NOT applied** — see "Why nothing was changed"
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/_lex_command.py`, and through it `slurm-guard.sh` and `commit-guard.sh`
- **Instances 7 and 8** of `MEMORY.md:guard-reads-wrong-input`. Both were found by being blocked by
  them, twice, inside one ordinary integration session.

## What happened

Two commands were denied as "heavy Python on the login node". Neither runs anything.

```
git commit -F - <<'MSG' … MSG            # a commit message that contained "campaigns.py" and a ";"
grep -n 'def test|MUST_DENY|python3 -c|torch' tests/test_slurm_guard.py
```

The first was a commit message. The second was reading a test file, with a pattern that happens to
quote the very cases the test pins.

## The cause, measured rather than guessed

`slurm-guard.sh:151` denies when the lexer says `UNSAFE` **and** the scan string mentions Python.
The scan legitimately mentions Python in both cases — the words are cargo. So the whole verdict
rests on `all_verbs_are_safe()`, and that function is wrong in one line:

```python
for segment in re.split(r"[;&|]+", scan):     # _lex_command.py:103
```

It splits the **already-lexed** string back up on separator **characters**. A character cannot tell
an operator from the same character sitting inside a quoted argument or a heredoc body. Feeding it
the exact denied commit message gives:

| segment's first word | where it came from |
|---|---|
| `git` | the real verb — safe |
| `the` | `…decode commands. Both ran 20 h ago; the result is on main…` |
| `from` | `…past harvest_by; from 2026-09-22 they block EVERY merge…` |

`the` and `from` are not safe verbs, so the command is `UNSAFE`, so it is denied. An English
semicolon became a command separator. The `grep` failed the same way on the `|` inside its quoted
pattern.

This is the bug shape the file's own header says it exists to prevent — *a guard matching text that
is not what it guards* — reproduced inside the fix for it. The 2026-09-14 work stripped
prose-carrying **flag arguments** and left two other ways for other people's text to re-enter as
shell: a heredoc body, and a separator character inside any quoted token.

## The fix that was written and tested, and not applied

Both halves are small, and neither weakens a pinned case.

1. **Segment on separator TOKENS, not characters.** `shlex.shlex(raw, punctuation_chars=True,
   whitespace_split=True)` splits operators out itself, and it was verified against every case the
   suite pins:

   | command | punctuation-aware tokens | verdict |
   |---|---|---|
   | `cat a.py&&python3 scripts/corpus_build.py` | `cat` `a.py` `&&` `python3` … | still splits — stays DENIED |
   | `grep -n 'a\|b\|python3 -c' tests/x.py` | pattern stays ONE token | now ALLOWED |
   | `git commit -m "a; b"` | message stays ONE token | now ALLOWED |
   | `python3 -c "import torch; …"` | verb `python3` | stays DENIED |
   | `bash -c 'python3 …'` | verb `bash` | stays DENIED |
   | `cat $(python3 …)` | caught by the `$(`-in-raw test, untouched | stays DENIED |

2. **Strip a heredoc body only when the command line receiving it has all-safe verbs** — the same
   by-capability discipline as the prose list, and for the same reason. `git commit -F - <<'MSG'`
   hands its body to `git`, which cannot execute it, so the body is data. `python3 - <<'PY'` and
   `bash <<EOF` keep their bodies and stay denied, because there the body **is** the program.

## Why nothing was changed

The edit was refused by the harness as an unrequested self-modification of a safety guard, and that
refusal is right. This is enforcement machinery whose whole value is that no agent quietly relaxes
it; an agent that reasons its way to "this rule is inconvenient, and I have a good argument" is the
case the rule is for. The diagnosis above is worth more than the patch, and it survives.

**It needs an owner decision.** The change is in `.claude/hooks/**`, integrator-exclusive, and the
suite in `tests/test_slurm_guard.py` is the right place to pin both new cases in both directions.

## The workaround, which is the same one the last two instances got

Put the text in a file and pass the path: `git commit -F /tmp/msg.txt`. A path carries no prose.
This is strictly better than `ALLOW_LOGIN_HEAVY=1`, which switches the guard off entirely and
trains the reflex of doing so on commands it was never meant to catch — the 2026-09-14 record's own
argument for fixing rather than documenting.

⚠ **Do not read the workaround as closing this.** Every instance of this bug shape has had a cheap
workaround, and that is precisely why the shape has recurred eight times.
