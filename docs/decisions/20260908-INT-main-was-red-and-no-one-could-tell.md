# main was red on three gates, and nothing in the repository was able to say so

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** INT (integration)
- **Supersedes:** nothing. Completes `20260908-INT-gate-selection-was-blind.md`: that record made
  the gate LIST computable, this one makes the gate VERDICT binding, on lines and on main.

## What was found

With the gate list finally computable, main's own gates had still never run. Every workflow here is
path-filtered, and the only pushes main has received since its history was replaced were prose, so
`budgets` and `changelog` are the only checks main had ever reported. The code gates were dispatched
by hand (`workflow_dispatch`, which every workflow here happens to declare) and main is:

| green | red |
|---|---|
| budgets, changelog, experiments, flags, campaigns, pathsafety | **lint, types, test** |

None of the three is new breakage. All of it was merged in, from `line/D` and `line/T`, on branches
whose gates had never run either. Attribution, so nobody re-derives it:

- **lint** — `ruff format` on 7 files (4 line D's, 3 line T's), already handed to both lines.
- **types** — 14 keyword-argument errors in D's `.clm` writer, one `no-redef` in D's corpus state,
  one `no-any-return` in T's synthesiser, all already handed over; **plus one that was nobody's**:
  `src/vegemu/paths.py` failed on a missing `yaml` stub package that `pyproject.toml`'s `dev` extra
  has declared since it was written. The `types` workflow installs `mypy numpy` by hand and simply
  never installed it. Fixed here.
- **test** — two tests in `tests/test_gate_selection.py` ask git for `HEAD~1`, which does not resolve
  in the default depth-1 CI checkout, so the tool under test correctly answered "cannot compute a
  diff" and the test correctly failed. The environment was wrong, not the test: `test.yml` now
  checks out full history. Fixed here.

## Why it stayed invisible, which is the part worth keeping

Three separate mechanisms each ended one step short of a verdict.

1. **`tools/merge.sh` printed the gate list and then advised.** Literally: `merge: (if any of those
   are not green, stop now)`. Three lines were merged past it.
2. **The same script closed with a paragraph** telling the session to go and check main's own CI
   afterwards. Nothing checked.
3. **`tools/wait_gates.py`, the tool that would have answered either question, had never once
   worked.** `remote_slug()` dropped the OWNER from an scp-like SSH remote — the only form this repo
   has ever used — so every request went to `/repos/LPJFIT_Emulator/...` and returned 404. `HTTPError`
   is a subclass of `URLError`, so that 404 was retried as a transient hiccup until the timeout,
   whose message is *"still pending"*. A wrong URL and a slow CI run printed the same words.

Point 3 is the same defect as the one the previous record is about, in a third place: **one
benign-looking message covering two situations that mean opposite things.** It is worth naming as a
class, because this repository has now produced it three times — an empty diff that meant an
uncomputable diff, a zero score that meant a missing score, and a 404 that read as a pending gate.

## What changed

- **`tools/merge.sh` refuses.** It runs `wait_gates.py` on the pushed sha and exits non-zero unless
  every triggered gate is green. Exit 2 ("cannot tell") is a refusal too — an unverifiable sha is
  not a green one. A prose-only commit triggers nothing and passes instantly, so this is not a
  blanket stop. The override is `--allow-red "<reason>"`, and the reason is written into the merge
  commit as a `Merged-with-red-gates:` trailer, because a guard with an unrecorded bypass is a
  guard that gets bypassed.
- **`tools/merge.sh` verifies main after the push**, from main's pre-push sha, and exits non-zero if
  main is not green. It cannot refuse retroactively; it can stop main's status from being a
  paragraph of advice.
- **`tools/wait_gates.py` gained `--ref`**, which is load-bearing on main: the default base asks
  "what does this branch add over main?", and on main that is empty by construction, so the default
  answers "no gate will run" for every commit main will ever carry.
- **`remote_slug()` keeps the owner** for all four URL forms, and a 401/403/404 now aborts with what
  to check instead of being retried into a timeout. `tests/test_wait_gates.py` pins both.
- **Two workflow fixes**, above: the `types` stub install and the full-history checkout for `test`.

## Consequences, stated plainly

- main stays red on `lint` and `types` until lines D and T merge their fixes; both know. The
  integrator cannot make those edits — the files are line-exclusive and `check_ownership` denies it,
  which is the guard working.
- Merging is now slower by however long CI takes, on any commit that touches code. That is the
  intended cost. The alternative was measured: three merges, three red gates, nobody informed.
- `workflow_dispatch` is the remedy for a commit whose push triggered nothing (a force-push over an
  unrelated history, or a filter that legitimately matched nothing but should be re-checked).
