# The session hooks call bare `python3`, so an interpreter crash is reported as a real finding

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** X
- **Fix owner:** integrator — `.claude/hooks/**` is integrator-exclusive
  (`config/ownership.toml`), so line X can diagnose this but must not patch it.

## What was found

Every session start has been reporting two open loops that do not exist:

    exp X-20260908-climate-state-map:  verdict metrics block is STALE
    exp X-20260908-warming-response:   verdict metrics block is STALE

**Both are false.** Under the project interpreter recorded at `config/paths.yaml:166`
(`/home/jamirp/.conda/envs/py311_new/bin/python`, 3.11.9), `render_verdict.py --check` reports
*up to date* for both, and re-rendering them changes **no byte** (`git diff` empty afterwards).

The cause is in `.claude/hooks/session-open-loops.sh:27`:

    elif ! python3 tools/render_verdict.py "$id" --check >/dev/null 2>&1; then

Bare `python3` on the login node is **3.9.21**, which has no `tomllib` (3.11+). `tools/_common.py`
imports it at module scope, so the script dies with `ModuleNotFoundError` and exit 1 before it
reads a single verdict. `2>/dev/null` discards the traceback, and the hook maps "non-zero" to one
specific meaning — "the block is stale" — so a crash is rendered as a substantive finding.

## Why this is the shape already recorded three times

This is a **fourth instance of one shape: a guard whose input is not what it guards.** It sits
beside the commit guard that sees an empty index, the gate selector that reads a different diff
than GitHub, and `slurm-guard` matching a command's *text* (which fired on a plain `sed` of a
`.py` file during this session). Here the hook conflates *"the checker said no"* with *"the
checker could not run"* — and the two demand opposite actions.

The cost is not just noise. The reported remedy is `tools/render_verdict.py <id>`, which under the
same bare `python3` also crashes, and under a working one rewrites the file identically. So the
instruction cannot clear the loop it reports, and the loop returns every session. It also
**masks a real stale block**: a genuinely stale verdict is indistinguishable from this.

## The same latent bug elsewhere

Verified: under 3.9 all four staged checkers exit 1 on the import, not on a finding —
`check_budgets`, `check_ownership`, `check_experiments`, `check_secrets`.

- `.claude/hooks/commit-guard.sh:35-38` — its `run()` treats a non-zero exit as a *finding* and
  denies. So it fails **closed**, not open: no check is silently skipped, but a commit made from a
  shell whose `python3` is 3.9 is refused with four tracebacks as its stated reason.
- `.claude/hooks/session-open-loops.sh:42` (`check_flags`) and `session-campaigns.sh:15` share the
  pattern (`2>/dev/null || true`), so both degrade to silence rather than to an error.
- **CI is unaffected** — every workflow pins `python-version: "3.11"`.

## Suggested fix, for the integrator to make

1. Resolve the interpreter once from the recorded path rather than `PATH`:
   `PY="$(sed -n 's/^ *python: *//p' config/paths.yaml | head -1)"`, falling back to `python3`.
   `tools/_paths.py` cannot be used for this — it imports `yaml` and so has the same problem.
2. **Distinguish the two outcomes.** Capture the status; on a non-zero exit *with* stderr that
   names an import failure, report the hook as broken — never as a finding about the repo.
3. Consider guarding at the source: have `tools/_common.py` fail with a one-line message naming
   the required interpreter instead of a bare `ModuleNotFoundError`.

Until it is fixed, treat those two open loops as noise, and run checkers with the project python.
