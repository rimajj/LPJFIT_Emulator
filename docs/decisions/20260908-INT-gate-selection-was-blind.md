# The gate-selection tool reported "nothing to verify" for every commit ever made in this repo

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** INT (integration)
- **Supersedes:** nothing. Repairs the third leg of the CI scheme set up in
  `20260902-INT-agent-operating-system.md` §"which checks to expect", which is unchanged in intent.

## What was found

`tools/expected_gates.py` decides which CI checks a commit will trigger, and a session is told to
merge as soon as it prints none. On **main and on all three line branches, with a clean tree, it
printed none** — always, regardless of the diff:

```
diff vs origin/main: 0 file(s) on branch line/D
EXPECTED GATES: (none)
  -> no check-run will appear for this commit. Do not poll. Merge when ready.
```

The cause is one line of `_common.changed_vs`. It computed `git merge-base origin/main HEAD` and
treated an empty result as "the ref is unknown, fall back to the staged set". `origin` here points
at the **predecessor's** GitHub repository (`rimajj/LPJFIT_Emulator`), which resolves fine but shares
no commit with this history, so `merge-base` exits 1 with no output. On a clean tree the staged set
is empty, so the change list was empty, so no gate ever matched.

Two states were collapsed into one, and they mean opposite things:

| the base is | the honest reading |
|---|---|
| a real, shared merge base with no diff | nothing changed — nothing to verify, merge |
| a ref sharing no history | **the diff cannot be computed** — nothing *was* verified |

## That this was not merely theoretical

`tools/check_no_abs_paths.py` exits 1 on `main` as committed: `scripts/plot_validation.py:4`
hardcoded `/p/tmp/jamirp/vegemu/exp/...` in a usage example, which is exactly the P01 defect the
`pathsafety` gate exists to block. The violation reached `main` and sat there, because the tool
asked whether to expect `pathsafety` answered no every single time.

Two further consequences, both real and neither previously visible:

* `tools/wait_gates.py` took the same empty list and printed "this diff triggers NO gate — nothing
  to wait for. Merge when ready." It has a careful "cannot poll → return 2, do not assume they
  passed" path for a missing API token, and never reached it.
* CI has in fact **never run**, on any commit, because nothing has ever been pushed anywhere. So
  every gate in `.github/gates.toml` is at present unenforced except by the local checkers in
  `tools/`. `ruff format --check .`, which the `lint` gate runs, currently reports **10 tracked
  files** it would reformat — a second latent red build, left untouched here and flagged below.

## The decision

**An empty change list must not be reachable by accident.** `_common.diff_base()` now returns the
base *and why there isn't one* — `ok`, `unknown` (a fresh clone; keep the staged fallback so the
bootstrap works) or `unrelated` (a wrong remote).

1. On `unrelated`, `changed_vs` falls back to **every tracked file**. The honest answer to "what
   changed" is then "cannot tell", and the safe reading of that is all of them, never none. This
   matches the reasoning already written into `expected_gates.current_branch()`, which falls back to
   the branch that runs *every* gate for the same reason. Under-checking is what let a violation
   reach `main`; over-checking costs seconds.
2. `expected_gates.py` **exits 2** — the repo-wide code for "the checker itself could not run" —
   when the base is unusable, naming what is unknown, listing the gates the whole tree would
   trigger as the conservative answer, and pointing at `--ref` for a real one. It no longer prints
   the word "merge" in that case.
3. `wait_gates.py` refuses before polling, on its existing "do not assume they passed" path.
4. `tests/test_gate_selection.py` pins the distinction against a purpose-built orphan-branch repo,
   so the two causes of an empty base cannot be re-merged. Collapsing `unrelated` back into
   `unknown` fails it.

## What is deliberately NOT decided here

**Where this repository should be pushed.** `origin` pointing at the predecessor is the root cause
and it is an owner decision, not an integrator one — the predecessor remote also carries branches
named `line/X`, `line/S`, `line/M`, `line/E`, `line/O`, so a push from here could collide with a
different project's branch of the same name. Until it is set, `tools/merge.sh` cannot run at all (it
refuses because `rev-list HEAD..origin/main` counts every unrelated commit as "behind"), all lines
merge into local `main` only, and the nine workflows are decoration. The change above does not fix
that; it makes the tooling **say so** instead of reporting a clean bill of health.

**The 10 unformatted files.** Reformatting them is mechanical but would bury this repair in an
unrelated 10-file diff, and it is worth knowing whether the cause is a `ruff` version drift
(`pyproject.toml` pins only `>=0.6`; CI installs the latest, 0.16 here) rather than neglect. Left
as a named, separate piece of work.
