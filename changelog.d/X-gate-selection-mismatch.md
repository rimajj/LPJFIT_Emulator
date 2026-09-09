### Fixed

- **Diagnosed why merging polls for gates that never run.** `tools/expected_gates.py` computes the
  gate list from the cumulative branch diff (`origin/main...HEAD`); GitHub decides whether a
  path-filtered workflow runs from the **push** diff. They agree only when every push touches the
  same file types. In one session they diverged three times in both directions — a `.md`-only push
  reported budgets alone, a `.py`-only push reported lint and pathsafety alone — and because a
  workflow that does not run reports **no status at all**, each mismatch cost a 900-second
  `wait_gates.py` timeout and forced `--allow-red` for a gate that was not red but absent. The
  mechanism for the fix already exists (`wait_gates.py --ref`, whose docstring calls it load-bearing
  for exactly this reason); it is simply never applied to line branches. Three fixes in preference
  order, and the warning that the cheap one trades a hang for a blind spot, are in
  `docs/decisions/20260909-X-gate-selector-reads-a-different-diff-than-github.md`. Not fixed here:
  it is shared `tools/` machinery and deserves its own change, not a tail-end edit.
