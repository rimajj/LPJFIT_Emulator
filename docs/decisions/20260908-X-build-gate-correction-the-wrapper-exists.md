# Correction: the wrapper for the build byte-test already exists, and a seal froze the claim that it did not

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** X
- **Amends:** `docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md` (one clause)
- **Cannot amend:** `experiments/X-20260908-heldout-forcing-leg/preregistration.yaml`, which is
  sealed. That is why this record exists.

## What is wrong

Both the build-provenance record and the sealed pre-registration say the decisive one-cell test of
build equivalence "has not been run, because … no wrapper exists yet to run it". The second clause is
false: **`scripts/sbatch_cmodel.sh` is on `main`**, added the same morning, together with
`scripts/corpus_cmodel_config.py`. This line's worktree was 29 commits behind `main` when the
pre-registration was written and sealed, so the claim was true of what I could see and false of the
repository.

**The material claim is unaffected.** Byte-equality between the Feb-05 and Aug-12 builds is still
unproven, the argument that every behavioural difference is gated behind unset environment variables
still stands on its own evidence, and the low-emissions leg remains admissible. What changes is only
this: **nothing is blocking the test.** The Feb-05 binary is preserved as
`bin/lpjml.pre_dgrass.bak`, the wrapper exists, and the test is one cell for one year from a shared
restart with a byte-compare of the result.

## The process lesson, which is the reusable part

A sealed pre-registration freezes **every** assertion in it, not only the scientific ones. This file
asserted the state of the repository, that assertion went stale between `main` and a 29-commit-old
worktree, and the seal made it uneditable — so a reader of the sealed file is told something untrue
about what is possible today, and the only remedy available is a pointer from outside.

**Bring the line up to date with `main` before sealing anything that asserts repository state.** The
session-start hook already says to; I did the work first and sealed second, and this is the bill. The
narrower habit worth keeping: in a pre-registration, prefer claims about *the data and the method*,
which do not rot, over claims about *the tooling*, which do.

## Consequences

1. The byte-test is **available now** and is line D's to run; it is no longer described as blocked
   anywhere except inside the sealed file, where it cannot be corrected.
2. Neither the pre-registration nor its verdict needs a new `exp_id`. A stale subordinate clause in
   the reference basis is not a changed question — the estimand, the folds, the nulls and their
   required returns are all untouched, and superseding an experiment over this would destroy the
   comparability that is the whole reason it was written.
3. `docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md` stands as accepted, with
   this record amending the one clause. Read them together.
