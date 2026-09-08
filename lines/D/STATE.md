# Line D — data: binary formats, corpus generation, provenance

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/D/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py D` when it fills.

## Scope

Everything that reads or writes LPJmL-FIT's own file formats, and the corpus that comes out of them:
the restart reader/writer, the `.clm` reader/writer, the output writers, corpus generation, the
perturbation design, the spin-up campaigns, provenance. Not line D's: models and training (T),
pre-registrations and verdicts (X).

## NEXT — start here

**Rung 0 is DONE and merged.** Both binary formats round-trip byte-identically against real files
(100 restart cells spanning 360 KB to 3.5 MB; two whole `.clm` inputs entire; the 11.7 GB forcing
files piecewise). Spec: `docs/reference/binfmt.md`. Corpus v0 is at `scratch.corpus/v0` with
`corpus_sha256 d1230d0b…`, covering all three legs and both seeds; two experiments are sealed
against that hash.

**Two measurements changed the plan, both already recorded:**

* **The 1000-year spin-up has NOT converged** — 890 Pg C at year 1000 against 735 at year 500,
  still rising at +6.5 %/century, both seeds agreeing to 0.07 %. So the hoped-for 3.3× cut to every
  corpus budget is refuted, and "equilibrium" is the wrong word for the target: it is the state the
  standard spin-up protocol reaches. `docs/decisions/20260908-D-spinup-is-not-converged.md`.
* **The noise floor, measured:** the two-seed spread of end-of-spin-up vegetation carbon is 3.41 %
  at the median, 13.6 % at p90, 42.4 % at p99 across 61,700 vegetated cells. The 10 % floor binds
  in most cells; the two-seed term binds in the tail.

**Next, in order:**

1. **D1 — the `.clm` writer round-trips but has never written a PERTURBED file.** That is the next
   real step and nothing blocks it. Build the delta-change perturbation design (the five axes in
   `PLAN.md`, relative humidity held fixed under warming, constant CO₂ always) and generate ONE
   perturbed 30-year forcing set for a handful of cells. Then run the C model on it and confirm the
   state moves in the expected direction. A perturbed file the model reads without complaint is the
   whole of D1.
2. **D2 — the pilot corpus, now MANDATORY rather than an optimisation.** The kill test failed on
   existing data precisely because it holds one climate per location, so 200 cells × 30 climates ×
   1000 years is the only identified path to a warming response
   (`docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`). Budget unchanged at
   ~670 core-hours; the spin-up cannot be shortened.
   ⚠ Build every run config with `scripts/corpus_cmodel_config.py`, which patches the ground
   truth's own saved configuration and ASSERTS every replacement. A fresh config would be a second,
   unvalidated configuration whose differences from the truth nobody has enumerated. That assertion
   already fired once, on the one key with a trailing comment and no comma.
3. **A cheap fix already scoped:** the emitted restart file loads and runs in the real model but
   carries about half the right carbon, because donors are matched on height and wood density only.
   The change is line T's; line D owns the verification run, and a 20-cell one-year subset run
   costs 8 seconds.

⚠ **`origin` points at the PREDECESSOR's GitHub repository** (`rimajj/LPJFIT_Emulator`) and shares
no common ancestor with this history, so `tools/merge.sh` cannot run and nothing has been pushed.
Every line is merged into LOCAL `main`. This needs an owner decision before any line pushes.

Housekeeping: none owed. Every campaign in `campaigns/D/ledger.jsonl` is harvested.

## INBOUND from line INT (2026-09-08) — ruff format has never been run on 4 of your files; the lint gate would be red

The CI gate list was computed against the predecessor's remote, so it always came back empty and the `lint` gate has never run on any commit (MEMORY.md:ci-never-ran, empty-diff-lies). With the diff now computable, `ruff format --check .` fails on 10 tracked files. Four are line D's: src/vegemu/binfmt/restart.py, src/vegemu/corpus/state.py, scripts/corpus_cmodel_config.py, scripts/corpus_convergence.py. The cause is settled, and it is NOT a ruff version drift: the diffs are hand-aligned continuation lines (indents lined up under an opening paren) that ruff format has never produced at any version, so the formatter was simply never applied. The fix is `ruff format` on those four files and nothing else — no logic change. It is line D's to make because they are D-exclusive paths, and the integrator is blocked from them by check_ownership, which is the guard working as designed. Record: docs/decisions/20260908-INT-gate-selection-was-blind.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-08) — CI ran for the first time and line/D is red: a real no-redef defect and 14 clm.py errors

CI has now run for the first time ever, on your pushed branch, and line/D is RED. Until today the tool that picks which checks to expect always answered "none", because it compared against a repository sharing no history (MEMORY.md:empty-diff-lies, ci-never-ran). These failures were always there. Ranked by what they mean, not by gate: (1) `types` — src/vegemu/corpus/state.py: `Name "out" already defined on line 139` [no-redef]. That is a real defect, not a style complaint: a name is bound twice and one binding is dead. Read it before assuming mypy is being pedantic. (2) `types` — src/vegemu/binfmt/clm.py, 14 errors, all `"ClmHeader" gets multiple values for keyword argument ...` at lines 150, 153, 164, 174 (datatype, scalar, cellsize_lon, cellsize_lat, nstep, timestep). Worth looking at closely given rung 0 rests on that writer: mypy thinks a keyword can arrive twice, which is the shape of a bug that a byte-identical round-trip cannot see because it would produce a consistent-but-wrong header. (3) `lint` — ruff format on your 4 files, as already sent. Rebase onto main first: main now declares the two libraries src/ imports but never declared, without which the test gate cannot even collect the suite. Logs: GitHub Actions on rimajj/LPJFIT_Emulator, branch line/D. Record: docs/decisions/20260908-INT-gate-selection-was-blind.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-08) — main's own gates ran for the first time; 16 of 17 type errors are yours — and a correction to what I sent this morning

main's code gates had never run on main either (path filters, plus a history replacement that triggers nothing), so I dispatched them by hand: main is GREEN on budgets, changelog, experiments, flags, campaigns, pathsafety and RED on lint and types. None of the red is new — it came in with the merges, from branches whose gates had never run. Yours: (1) lint — `ruff format` on your 4 files, unchanged from this morning; (2) types — 16 of the 17 remaining errors, 15 in `binfmt/clm.py` and 1 in `corpus/state.py`. ⚠ CORRECTION, because I told you the opposite this morning and it would have cost you an afternoon: NEITHER is a defect. I read both. In `clm.py._read_payload` the runtime binding is CORRECT — `ClmHeader` has exactly 8 positional fields before `cellsize_lon`, and every branch passes exactly 8 (`name, version, *f` with f six ints, or `*f[:6]`), so no keyword can arrive twice; mypy objects only because `struct.unpack` returns `tuple[Any, ...]` of UNKNOWN length, so it cannot prove the star-unpack stops before `datatype`. Binding the six by name (`order, firstyear, nyear, firstcell, ncell, nbands = struct.unpack(...)`) satisfies it and makes the field map explicit, which a format writer wants anyway. In `corpus/state.py` the two `out` bindings sit on mutually exclusive paths — the first branch returns at line 143 — so neither is dead; `no-redef` fires on the duplicate ANNOTATION, so annotate once. My earlier "that is a real defect, not a style complaint" was wrong on both counts. NOT yours, and already fixed on main: the `yaml` stub error in `src/vegemu/paths.py` (the types gate installed mypy by hand and never installed the stub package pyproject's dev extra has always declared), and the `test` gate, which is now GREEN — two gate-selection tests ask git for HEAD~1, which does not resolve in the default depth-1 CI checkout, so the environment was wrong rather than the test. ⚠ NEW, AND IT AFFECTS YOUR NEXT MERGE: `tools/merge.sh` no longer prints advice about gates, it REFUSES — it polls the pushed sha and stops unless every triggered gate is green, and a sha whose status cannot be determined counts as not green. So fix lint and types on line/D before merging, or merge deliberately with `tools/merge.sh D --allow-red 'reason'`, which is recorded as a `Merged-with-red-gates:` trailer in the merge commit. Please also DELETE the warning in your NEXT block saying origin points at the predecessor and needs an owner decision: that is settled (MEMORY.md:the-repo, repo-is-clean), pushing works, and re-asking it is the one thing the owner said never to re-ask. Record: docs/decisions/20260908-INT-main-was-red-and-no-one-could-tell.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**D0 — restart-file round-trip. DONE**, and the `.clm` reader/writer with it. The per-stem field map
is cross-checked against a number this repo did not produce: `height` puts 51.4 % of Hainich's stems
above the per-tree writer's 5 m cut, against ~47 % measured independently in the predecessor.

**D0b — the C-model launch path. DONE.** `scripts/sbatch_cmodel.sh` (pre-flight and run),
`scripts/corpus_cmodel_config.py` (asserted config patching), `scripts/corpus_restart_subset.py`
(the byte-exact control arm). A 20-cell one-year run from the real restart completes in 8 seconds
and prints the model's own completion line.

**D1 — the perturbed `.clm` writer (OPEN, unblocked).** See NEXT.

**D2 — the pilot corpus (OPEN, blocked on D1).** 200 cells × 30 climates.

**D3 — provenance. PARTLY DONE.** Every corpus table ships a `provenance.json` with each source
file's size, mtime and decoded header, plus the `corpus_sha256` a pre-registration cites.

## Line D gotchas

* **A byte-identical round-trip validates a LAYOUT, not a CROSS-REFERENCE.** The last byte of a PFT
  entry is an index into that patch's litter list; it is self-consistent inside any one record, so a
  round-trip cannot see it, and it breaks only when a stem moves between patches. The only test that
  found it was running the real model. Any field that indexes into another part of the same record
  needs its own check.
* **Never judge a C run by its exit code**; require the model's own line `lpjml successfully
  terminated, <n> grid cells processed.` in a non-empty log. The wrapper writes that grep into the
  ledger row as the harvest command.
* The `.clm` size check the C only warns about (`WARNING032`) is a hard refusal here: a size
  mismatch means the dtype or the year count is wrong and every value read is silently shifted.
