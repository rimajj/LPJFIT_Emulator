# The command-lexer fix is applied on an owner decision, and review of it found a third hole

- **Status:** accepted; **the fix IS applied**, with both cases pinned in both directions
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/_lex_command.py`, and through it `slurm-guard.sh` and `commit-guard.sh`
- **Supersedes the status line only** of `20260916-INT-the-command-lexer-resplits-prose-on-shell-operators.md`,
  which stays accepted and unedited: its diagnosis is what this record acts on. That record says
  "the fix is NOT applied — it needs an owner decision". This is that decision, and the result.

## The decision

The owner was asked, in plain language, whether to apply the fix or keep the workaround, and chose
**apply the fix and pin both cases**. Nothing else about the diagnosis changed; the patch applied is
the one that record describes.

⚠ **The earlier refusal was correct and is not overturned by this.** An agent must not relax a
safety guard on its own initiative, however good its argument — that is the case the rule exists
for. What changed is that the owner decided, not that the argument got better.

## What is now in the file

1. **Segment on separator TOKENS, not characters.** `shlex(..., punctuation_chars=True,
   whitespace_split=True)` emits real operators as their own tokens and leaves quoted text whole, so
   prose stops manufacturing segments.
2. **Only command separators split a segment** — `;`, `&`, `&&`, `|`, `||`, `|&`. Deliberately NOT
   `<`, `>`, `<<`, `(`, `)`, which shlex's punctuation set tokenises alongside them. A redirection
   continues its command; splitting on one would have newly denied `grep -n x src/… > /tmp/hits.py`.
   That is a hole this change could have opened in the OTHER direction, and it is pinned.
3. **A heredoc body is data only when the command receiving it cannot execute it.** `git commit -F -
   <<'MSG'` hands its body to `git`; `python3 - <<'PY'` and `bash <<EOF` hand theirs to an
   interpreter, keep them, and stay denied. Same by-capability discipline as the prose list.

## The third hole, found by reviewing the fix rather than by being bitten

The first version of the heredoc code rescanned from the start of the string after lifting a body
out. The `<<DELIM` stays in the command text — it is part of the command — so the rescan matched it
again, found no second terminator, and swallowed everything after the first terminator as though it
were more message. That hides a real second command from the verb check:

```
git commit -F - <<'MSG'
a message
MSG
&& python3 scripts/corpus_build.py        <- was becoming "body", i.e. invisible
```

Fixed by resuming the scan after the body just taken. **It is in MUST_DENY**, so it cannot come
back. Worth noting for its own sake: this is the fourth defect in this one file, and the first found
by reading the change rather than by having ordinary work refused.

## Measured, old lexer against new, on the cases the suite pins

Verdicts taken from both versions of the file by running each against the same input.

| command | before | after |
|---|---|---|
| `grep -n 'def test\|MUST_DENY\|python3 -c\|torch' tests/test_slurm_guard.py` | UNSAFE | **SAFE** |
| `grep -rn 'train\|corpus' src/vegemu/corpus/state.py` | UNSAFE | **SAFE** |
| `git commit -F - <<'MSG' … ran 20 h ago; the result is on main … MSG` | UNSAFE | **SAFE** |
| `python3 -c "import torch; torch.zeros(1)"` | UNSAFE | UNSAFE |
| `cat a.py&&python3 scripts/corpus_build.py` | UNSAFE | UNSAFE |
| `cat notes.md && python3 scripts/corpus_build.py --tier pilot` | UNSAFE | UNSAFE |
| `bash -c 'python3 scripts/corpus_build.py'` | UNSAFE | UNSAFE |
| `cat $(python3 scripts/corpus_build.py --print-path)` | UNSAFE | UNSAFE |
| `./scripts/corpus_build.py --tier pilot` | UNSAFE | UNSAFE |
| `python3 -m torch.distributed.run --nproc 4 scripts/fit_model.py` | UNSAFE | UNSAFE |
| `python3 - <<'PY' import torch … PY` | UNSAFE | UNSAFE |
| `bash <<'EOF' python3 scripts/corpus_build.py … EOF` | UNSAFE | UNSAFE |

**Every command that must stay denied stays denied**, including all five the suite calls out as the
ways the 2026-09-15 verb allowlist could have opened a hole. Full suite: 294 passed, 1 skipped.

## Two cases are pinned that this fix did NOT repair, and they are filed apart

`git commit -m "… ; … | …"` and the redirection case above both passed BEFORE the change. They are
in MUST_ALLOW because this change could have broken them — the first is protected by prose
stripping, the second by keeping `>` out of the separator set. Filing them under "instances 7 and 8"
would have made the suite look like it demonstrated more than it does, which is the same overstating
invariant 4 guards against for numbers.

## What is still true

The workaround (`git commit -F <file>`) still works and is still better than the override, which
switches the guard off entirely. `MEMORY.md:guard-reads-wrong-input` stays at eight instances — this
record closes 7 and 8 rather than reducing the count, because the count is of the SHAPE, and the
shape's lesson is unchanged: before adding a rule to either hook, ask what input it judges.
