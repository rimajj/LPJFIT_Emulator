# The gate selector reads the branch diff; GitHub reads the push diff, so merging polls for gates that never run

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** X
- **Governs:** `tools/expected_gates.py`, `tools/wait_gates.py`, `tools/merge.sh`, `.github/gates.toml`
- **Found while** merging the X4 derivation — four merge attempts, three of them lost to this.

## The defect

`tools/expected_gates.py` computes which gates a merge must wait for from the **cumulative branch
diff**, `origin/main...HEAD`. GitHub Actions decides whether a path-filtered workflow runs from the
**push diff** — only the commits in that push. Those two are the same only when a branch is one
commit, or when every push touches the same file types.

They diverged three times in one session, in both directions:

| pushed sha | what that push touched | expected (branch diff) | what actually reported |
|---|---|---|---|
| `045a2b5` | `.py` + `.md` | budgets, lint, pathsafety | all three |
| `ccbd320` | `.md` only | budgets, lint, pathsafety | **budgets only** |
| `baf2587` | `.py` only | budgets, lint, pathsafety | **lint, pathsafety only** |
| `67de506` | `.md` only | budgets, lint, pathsafety | **budgets only** |

A gate that does not run **reports no status at all** — not "skipped" — so `wait_gates.py` polls it
until its 900-second timeout. Every merge attempt after a single-file-type push therefore costs 15
minutes and then fails, and the only way through is `--allow-red`, whose reason then has to explain
a red that is not red but absent. That is the repo's own documented trap
(`CLAUDE.md`: "a skipped workflow reports no status at all"), reached through the tool that exists
to prevent it.

The workflow files already carry the warning in a comment — *"a drifted filter makes an agent wait
forever for a gate that will never appear"* — but they frame it as filters drifting from
`gates.toml`. The filters have not drifted. The mismatch is between two different diffs, and no
amount of keeping the two declarations in sync fixes it.

## Why `--allow-red` is the wrong shape for this

`--allow-red` records a *reason a red gate is acceptable*. Here the gate is not red, it is unknown,
and the honest reason has to say "this gate did not run because the last push did not touch its file
types, and it was green on the earlier sha that did". That sentence is now in a merge-commit trailer
on main, which is a bad place for it: it reads as a suppressed failure rather than a tooling gap.

## The fix, in preference order

**The mechanism already exists.** `wait_gates.py --ref` takes the base to diff against, and its own
docstring calls it load-bearing for precisely this reason: *"Pass the pre-push sha to get main's own
gate list, which is what GitHub filters the push on."* The insight is already in the tool; it is
simply not applied to line branches, where `merge.sh` lets the base default to `origin/main`.

1. **Resolve each gate against the most recent pushed sha whose push diff could have triggered it**,
   while still requiring the full set the branch diff implies. This is the correct semantics: it
   neither waits for a gate that cannot appear nor silently drops one because the last push happened
   not to touch its file types. Needs no workflow change.
2. Cheaper, and strictly better than today: **have `merge.sh` pass `--ref <pre-push sha of
   origin/line/L>`**, so the expected list matches what GitHub actually filtered. ⚠ Not sufficient on
   its own — it makes the poll terminate quickly, but a gate whose files were pushed earlier is then
   never checked at all, which trades a hang for a blind spot. Pair it with 1.
3. Cheapest stopgap, worth doing regardless: **`wait_gates.py` should distinguish "no status yet"
   from "this sha's push could not have triggered this workflow"** and say so in seconds rather than
   timing out in fifteen minutes. It already parses the path filters; it does not consult them when
   deciding whether to keep waiting.

## Consequences

1. **Integrator — this is `tools/`-owned shared machinery.** Any line that pushes a documentation
   commit last (which is most of them, since the handoff is committed last by protocol) hits it.
2. **Every line, until it is fixed:** if `wait_gates.py` hangs, check whether your final push
   touched the file types the pending gate filters on before assuming the gate is slow.
3. This is the **third** instance in this repo of one calm message covering two opposite states —
   after the empty-vs-uncomputable diff, the 0.0-vs-missing score, and the 404-vs-pending remote —
   and the second in gate tooling specifically. `MEMORY.md:two-states-one-message` should gain
   "pending vs never-going-to-run" as a named case.
