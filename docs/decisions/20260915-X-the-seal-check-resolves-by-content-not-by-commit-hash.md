# The seal-precedes-the-run check resolves the seal by CONTENT, because the mandated rebase rewrites the commit it used to name

- **Status:** accepted
- **Date:** 2026-09-15
- **Line:** X
- **Fixes:** the shared-tool bug reported to the integrator on 2026-09-14 and listed in
  `lines/X/STATE.md`. `tools/**` is shared, so this line could fix it rather than only report it.
- **Extends the shape recorded five times now:** *a guard whose input is not what it guards.*

## What was wrong

E12 exists to enforce the one property that makes "pre-registered" a fact: **the pre-registration
existed before the run it governs.** It tested that by taking `seal_commit` from
`experiments/registry.jsonl` and asking git whether that hash is an ancestor of the commit that
introduced the first result row.

`CLAUDE.md` requires `git pull --rebase origin main` before merging. A rebase rewrites every commit
on the line that is not yet on main — the seal commit among them. The recorded hash then names an
object that is on no branch, ancestry of it is false for everything, and **E12 reports a violation
against provenance that is completely intact.**

It fired three times in one session, on three experiments, all of them genuinely sealed before their
runs. Each was "resolved" by appending a correction row to an append-only ledger. That is the part
worth naming: the ledger grew three rows of bookkeeping whose only purpose was to silence a checker,
and a real integrity gate that cries wolf is one people learn to route around. The correction rows
were honest and each was verified, but the third was written already knowing a fourth would be
needed — which is the point at which the workaround, not the symptom, is the bug.

## What was decided

**E12 resolves the seal by content. `seal_commit` is no longer read by any check.**

The registry already records `prereg_sha256`, the hash of the sealed bytes. A rebase cannot change
it, because it is a property of the file and not of the history that carries it. So the check now
asks the question it always meant to ask:

> Did the **exact sealed bytes** exist in committed history before the first result?

implemented as `seal_commit_by_content()`: walk the commits that touched
`preregistration.yaml`, oldest first; the first whose blob hashes to `prereg_sha256` is the seal;
require that commit to be an ancestor of the first result commit.

`seal_commit` stays in the ledger as a breadcrumb for a human reading it, and
`tools/seal_experiment.py` now says so in its own docstring, including the instruction **not** to
correct it when it goes stale. The three existing correction rows become inert provenance; the
ledger is append-only, so they stay where they are.

## ⚠ This is STRICTER than what it replaces, not a relaxation

That distinction is the whole reason this is a fix and not a workaround, so it is worth stating
precisely. **The old check never opened the commit it named.** It proved only that *some commit id*
preceded the result — so a `seal_commit` pointing at any early commit passed, including one that did
not contain the pre-registration at all, and including one whose copy of the file said something
different. The new check cannot pass unless the sealed bytes are genuinely present in history at a
point that precedes the results.

Concretely, it catches a case the old one was blind to: a pre-registration **edited after sealing**
now leaves no commit carrying the sealed bytes, and E12 says so in those words. Previously only E03
(live hash vs registry) would have noticed, and only while the registry row itself was trusted.

## What was measured, before and after

Content resolution was run against all five experiments in the registry. **It independently derives
exactly the commits the three hand-written correction rows had recorded** — the algorithm agrees with
the manual forensics, which is the check that it reproduces reality rather than merely being green.

The decisive pair, both run on the real repository:

| condition | old behaviour | new behaviour |
|---|---|---|
| orphaned `seal_commit` restored to the live registry | **FAIL** (the reported bug) | **pass** |
| `prereg_sha256` tampered so no commit carries it | pass (blind to it) | **E12 fires** |

Both directions matter. The first is the bug removed; the second is the proof that removing it did
not cost anything.

## How it is pinned

`tests/test_seal_provenance.py`, six tests, each building a throwaway git repository — the rebase
case performs a **real** rebase rather than simulating one:

1. after a rebase, the recorded hash is orphaned and the content resolution still finds the seal —
   and the test **asserts the old check fails on that same input**, so it cannot quietly stop
   reproducing the bug;
2. a seal that genuinely follows its results is still caught;
3. sealed bytes that were never committed are caught;
4. the **earliest** carrier wins, so a later touch of the file cannot move the seal past its own
   results;
5–6. both of those through the real `check_append_only` code path, because a correct helper proves
   nothing about the check that is supposed to call it.

## One deliberate behaviour change beyond the fix

A shallow clone cannot see the seal commit, and "not fetched" is not "not sealed". E12 now
distinguishes the two and says which it is. That follows the rule this repository has already had to
learn twice in hooks: **a checker that cannot run must say so, never report a finding it did not
measure.** CI is unaffected — `.github/workflows/experiments.yml` already checks out with
`fetch-depth: 0`.

## Scope

- No sealed pre-registration changes and no sealed hash moves. This is a checker change only.
- The three correction rows are not removed; the registry is append-only and they are now harmless.
- Not fixed here, and reported rather than touched: `CLAUDE.md` points at a skill
  `experiment-registry` as the place documenting every code E01–E14 and its fix. **That skill does
  not exist in the repository**, so E12's documented home is missing. `CLAUDE.md` is
  integrator-exclusive.
