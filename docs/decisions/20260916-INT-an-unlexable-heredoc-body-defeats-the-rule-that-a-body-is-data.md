# An unlexable heredoc body defeats the rule that a body is data — instance 10, fix NOT applied

- **Status:** diagnosed, fix written and verified, **not applied** — it needs an owner decision
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/_lex_command.py`, `tests/test_guard_generated.py`
- **Follows** the two accepted records of the same day, neither retracted:
  `20260916-INT-the-command-lexer-resplits-prose-on-shell-operators.md` (instances 7 and 8) and
  `20260916-INT-the-heredoc-half-of-the-fix-was-instance-9-of-the-shape-it-closed.md` (instance 9).

## What happened

Three of this session's first four commands were refused as heavy Python on the login node. All
three were the same thing: writing a probe script with `cat > /tmp/x.py <<'PY' … PY`. `cat` cannot
execute what it is handed, which is exactly the by-capability rule the owner approved that morning.

## The cause, reproduced against a minimal command rather than guessed

    cat > /tmp/t.py <<'PY'          <- DENIED
    print("the corpus's seed" + 'x\'y')
    PY

`main()` decided whether a heredoc exists by lexing the **raw text, body included**. A body is
DATA, and data need not be balanced shell: the escaped quote makes `shlex` raise, the command falls
down the fail-closed path, the raw string becomes the scan, it mentions `corpus`, and the keyword
rule fires. **The rule that a body is data was defeated by the step that decides whether there is a
body.** Same shape as 7, 8 and 9 — a guard judging input that is not what it guards — now the third
hole in the same morning's fix.

## A second, larger class, found while measuring the first

The safe-verb allowlist has no `echo`, `printf`, `true`, `false`, `pwd`, `cd` or `test`. None of
them can execute a file, so appending any of them to a read flips the whole command to unsafe:

    cat scripts/train_emulator.py ; echo done                 DENIED
    wc -l scripts/corpus_build.py && echo ok                  DENIED
    cd src/vegemu/corpus && ls -l state.py                    DENIED
    grep -n pft_frac src/vegemu/corpus/state.py | head -5 ; echo searched   DENIED

Eight of ten such commands are refused. The two that survive do so because `.py;` is not `.py `, so
the keyword regex misses — punctuation luck, not a safety property.

## What was measured, three ways

| basis | live guard | with the fix below |
|---|---|---|
| write each of 177 tracked files with `cat … <<'PY'` (runs nothing) | **12 refused** | 0 |
| the 64 pinned + adversarial cases in `tests/test_slurm_guard.py` | — | **2 change, 0 wrong** |
| the 1,312 distinct Bash commands this repo's sessions have ever issued | 41 refused | 32 refused |

The 12 include `.claude/hooks/_lex_command.py` itself, both `lines/D` and `lines/T` state files, and
four `scripts/*.py`. Of the 9 commands that change verdict, every one runs nothing; the 32 still
refused all hand their text to `python3 -`, `bash` or a `.py` program, which is correct.

⚠ **The transcript record already shows the workaround reflex this was meant to prevent.** Two past
sessions got past the guard by splitting a keyword inside quotes — `scripts/cor"pus_cmodel_config.py"`
and `git mv scripts/tr"ain_synth_restart.py" …`. That is worse than the annoyance it solves.

## The fix, written and verified out-of-tree

**A.** When the raw text will not lex, decide whether a heredoc exists by lexing the longest
**prefix** that does lex. A body begins on the line after its redirection, so any prefix that lexes
is command text. If no lexable prefix carries a real `<<`, the text is an unbalanced *command*, the
`ValueError` propagates, and the caller fails closed exactly as today.
**B.** Add `echo printf true false pwd cd test [` to `SAFE_VERBS`.

⚠ **The first version of A looked at the first line only, and the real-command corpus showed it too
narrow**: `cd <dir>` then `git commit -F - <<'EOF'` puts the redirection on line two, and that is
this repository's commonest committing idiom. Measuring against commands that were actually issued
is what caught it — the same lesson as instance 9, one layer earlier.

## Why it is not applied

Both parts **widen what a permission hook treats as safe**. The 2026-09-16 record established that
this is an owner decision, not an agent's, however good the argument; the harness classifier
independently refused the edit for the same reason. So the change is verified in `/tmp` and the
defects are pinned in the suite, awaiting a yes or no.

## The gate: `tests/test_guard_generated.py`

Every previous instance was found by being blocked during ordinary work, after a green suite — a
hand-written case list cannot contain the command nobody has written yet. So the new file builds its
commands out of this repository: its own paragraphs, its own tracked files, its own commit messages,
in templates that run nothing (`-m`, `--body`, `--reason`, `git commit -F -`, `cat > f <<'PY'`,
`grep`). A deny is a false deny by construction. Both defects above are pinned as **strict** xfails,
so the day the fix lands the suite goes red and the markers must go.

⚠ **Its first draft was red for the wrong reason**: it handed the file bodies to the hook as if they
were commands, so a body beginning `#!/usr/bin/env python3` was correctly denied and the family
looked like instance 10 when it was not. Caught by running the same family against the patched
guard and finding it still red. **A red test must be verified red for its stated cause**, exactly as
a green one must be verified non-vacuous.

## Count

`MEMORY.md:guard-reads-wrong-input` goes from nine to **ten**, and what is new is not the shape but
that the case was generated rather than imagined: the corpus found in one run what four sessions of
hand-written cases had missed.
