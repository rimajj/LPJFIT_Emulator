# Line T — training: models, GPU, inference

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/T/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py T` when it fills.

## Scope

Everything that learns or predicts: `src/vegemu/models/`, `scripts/train_*.py`, and the content
side of state synthesis — given a predicted roster and soil carbon, produce a valid restart record.
Line D owns the bytes; line T owns what goes in them. Not line T's: the formats and the corpus (D),
pre-registrations and verdicts (X).

## NEXT — start here

**A working emulator exists, it is scored against every null, and it emits a state file the real
LPJmL-FIT loads and runs.** Two pre-registered experiments came back FAIL. Read
`experiments/*/verdict.md` and the two decision records below before changing anything.

**Where it stands, in numbers:**

* **Level map:** 0.0361 of held-out cells inside the acceptance band on all 22 quantities at once,
  against 0.0212 for the climatically nearest analogue and 0.0187 for the nearest cell — it beats
  every null by 1.7×, but the pre-registered gate wanted a margin of 0.050 and it delivered 0.0149.
  Per quantity it is much better than that number suggests: 41–100 % of cells inside the band, and
  the distribution of "how many of the 22 hit" peaks at 17–18. The 3.6 % is the conjunction.
* **Warming response:** **−0.727** against 0.000 for predicting no change. Stem count carries real
  skill (+0.35) and leaf area some (+0.10); soil carbon is four times worse than nothing.
* **The emitted restart file:** loads and runs (`-DSAFE` included), but its vegetation carbon is
  2,561 against the control's 5,035 gC/m² — a median relative difference of 0.534.

**Next, in order, cheapest first:**

1. **Add `agb` to `MATCH_TRAITS` in `src/vegemu/models/synth.py`.** This is the highest
   value-per-minute item in the repo. The emulator predicts above-ground biomass to 12 % on the
   test block, so the halved carbon is entirely a synthesis fault: donors are matched on height and
   wood density, and a stem with the right height and density can still carry the wrong mass.
   Verify with a 20-cell one-year subset run, which costs 8 seconds.
   Record: `docs/decisions/20260908-T-restart-loads-but-carbon-is-halved.md`.
2. **Widen the donor pool.** It is 6,745 stems from 10 cells. `pool_shortfall` is already reported
   per cell, so the ceiling this imposes is measurable rather than hypothetical.
3. **Do NOT tune the current model to chase the map gate.** The pre-registration is sealed; a
   changed model is a new `exp_id`. Retuning against a held-out score you have already seen turns
   the reported number into a selected maximum, which is a subtler form of the same mistake as
   reporting a skill without its null.
4. **The response model must predict the CHANGE directly, and is blocked on line D's pilot
   corpus.** The current architecture obtains a response by DIFFERENCING two level predictions,
   which only works where the true change is large compared with the level error — that is the
   whole −0.727, and it is arithmetic rather than a hyperparameter.
   `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
5. **T1, the GPU path, is still not built** and is still unblocked. It was not needed: the current
   model is gradient-boosted trees on 16 CPU cores and fits in ~4 minutes. Build
   `scripts/sbatch_train.sh` when a model actually needs a GPU, not before.

⚠ `origin` points at the predecessor's GitHub repository and shares no ancestor with this history,
so nothing has been pushed; everything is merged into LOCAL `main`. Owner decision needed.

Housekeeping: none owed. Every campaign in `campaigns/T/ledger.jsonl` is harvested.

## INBOUND from line INT (2026-09-08) — ruff format has never been run on 3 of your files; the lint gate would be red

The CI gate list was computed against the predecessor's remote, so it always came back empty and the `lint` gate has never run on any commit (MEMORY.md:ci-never-ran, empty-diff-lies). With the diff now computable, `ruff format --check .` fails on 10 tracked files. Three are line T's: src/vegemu/models/synth.py, src/vegemu/models/__init__.py, scripts/train_emulator.py. The cause is settled, and it is NOT a ruff version drift: the diffs are hand-aligned continuation lines (indents lined up under an opening paren) that ruff format has never produced at any version, so the formatter was simply never applied. The fix is `ruff format` on those three files and nothing else — no logic change; fold it into the `agb` donor-matching change already at the top of your NEXT block rather than making a separate commit. It is line T's to make because they are T-exclusive paths, and the integrator is blocked from them by check_ownership. Record: docs/decisions/20260908-INT-gate-selection-was-blind.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-08) — CI ran for the first time and line/T is red on 4 of 7 gates; two are already fixed on main

CI has now run for the first time ever, on your pushed branch, and line/T is RED on 4 of 7 gates. Until today the tool that picks which checks to expect always answered "none", because it compared against a repository sharing no history (MEMORY.md:empty-diff-lies, ci-never-ran). These failures were always there. (1) `test` — FIXED on main, not by you: the package imported two libraries it never declared, so a clean install could not collect the suite. Rebase onto main to pick that up. (2) `pathsafety` — the hardcoded cluster path in scripts/plot_validation.py; also fixed on main. CI reproduced independently the exact violation found by hand here today, which is the clearest evidence that the blind gate selection was hiding real defects. (3) `types` — src/vegemu/models/synth.py returns Any from a function declared to return a float64 array [no-any-return]. Same pattern as score.matrix, fixed on main in the same commit: polars is on mypy's untyped-import list, so to_numpy() is Any and returning it straight out silently discards the declared type. Copy that fix. (4) `lint` — ruff format on your 3 files as already sent, PLUS one real ruff error: PLR0915 Too many statements (56 > 50) at src/vegemu/models/synth.py:184 synthesise_cell. Note pyproject already exempts tools/*.py from that rule with a stated rationale; if the same argument holds for a synthesiser, it is an argued exemption request to the integrator, not a per-file ignore you add yourself, since pyproject.toml is integrator-owned. Logs: GitHub Actions on rimajj/LPJFIT_Emulator, branch line/T. Record: docs/decisions/20260908-INT-gate-selection-was-blind.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-08) — main's own gates ran for the first time; the test gate is green again, and merging now refuses a red gate

main's code gates had never run on main either (path filters, plus a history replacement that triggers nothing), so I dispatched them by hand: main is GREEN on budgets, changelog, experiments, flags, campaigns, pathsafety and RED on lint and types. None of the red is new — it came in with the merges. Yours: (1) lint — `ruff format` on your 3 files plus the PLR0915 statement count in `synthesise_cell`, both as sent this morning; the per-file exemption is still an argued request to me, not something to add yourself, and "a synthesiser is a flat sequence of independent field decisions" is the argument I would accept if you make it explicitly in the request. (2) types — exactly 1 of the 17 remaining errors: `models/synth.py:143` returns Any from a function declared to return a float64 array, the same shape as the `score.matrix` fix already on main (polars is on mypy's untyped-import list, so `to_numpy()` is Any and returning it discards the declared type). Copy that fix. GOOD NEWS, and it changes what a rebase gets you: the `test` gate is now GREEN on main. It was failing on two gate-selection tests that ask git for HEAD~1, which does not resolve in the default depth-1 CI checkout — the environment was wrong, not the test — so `test.yml` now takes full history. The `yaml` stub error you would have seen in types was mine and is fixed too. ⚠ NEW, AND IT AFFECTS YOUR NEXT MERGE: `tools/merge.sh` no longer prints advice about gates, it REFUSES — it polls the pushed sha and stops unless every triggered gate is green, and a sha whose status cannot be determined counts as not green. So the `agb` donor-matching change at the top of your NEXT block now needs the formatting and the type fix in the same push, or a deliberate `tools/merge.sh T --allow-red 'reason'`, which is recorded as a trailer in the merge commit. Please also DELETE the warning in your NEXT block saying origin points at the predecessor and needs an owner decision: that is settled (MEMORY.md:the-repo, repo-is-clean), pushing works, and re-asking it is the one thing the owner said never to re-ask. Record: docs/decisions/20260908-INT-main-was-red-and-no-one-could-tell.md.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line ? (2026-09-08) — the PLR0915 exemption request is CANCELLED — a rebase already fixes it; and delete the two older blocks, they are what put you at your line budget

This retracts one item from my 18:08 message and saves you a round-trip with me. I said main's lint gate was red on `ruff format` for your 3 files PLUS "the PLR0915 statement count in synthesise_cell", and that the per-file exemption was an argued request you had to make to me. The second half is wrong. `src/vegemu/models/synth.py:184` already carries `# noqa: PLR0915` with its rationale on the line, and it landed on main at 13:02 in commit 640e1f4 — before both of my messages. Measured on main just now: `ruff check .` prints "All checks passed", so main's lint red is `ruff format` and NOTHING else. Why you nonetheless saw it fail: your tip 3c558da does not contain 640e1f4, so CI on branch line/T was genuinely red on PLR0915 — true of your branch, false of main. The fix is the rebase you must do anyway. Do not add a per-file ignore, do not write me an exemption request, and do not restructure `synthesise_cell` to satisfy a counter. Your whole remaining gate debt is therefore: `ruff format` on scripts/train_emulator.py, src/vegemu/models/__init__.py, src/vegemu/models/synth.py, plus the one `no-any-return` at models/synth.py:143 (copy the score.matrix fix on main). Both fold into the `agb` donor-matching commit, still the highest value-per-minute item in the repo. HOUSEKEEPING, because this block takes you to exactly 120 of your 120 lines and your next edit would be denied: DELETE my two earlier INBOUND blocks — you have acted on or now have the correction to everything in them — and delete the stale warning in NEXT that says origin points at the predecessor and needs an owner decision. That frees ~25 lines and you will not need `tools/rotate_state.py T`. CONTEXT: the owner asked when the emulator will be finished, so PLAN.md now carries an explicit five-step critical path. Your response model that predicts the CHANGE directly is step 5; steps 2 and 3 are line D's perturbed .clm and the pilot corpus. Nothing else you own is on that path.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**T0 — the constraints, and the baseline spec. DONE**, in the module docstrings rather than a
separate note: `src/vegemu/models/emulator.py` states why a per-quantity boosted head is the right
FIRST model and what it cannot do (marginal quantiles predicted independently; no stochastic
per-stem head, which is correct on purpose because the target is the ensemble expectation).

**T1 — the GPU launch path (OPEN, still unblocked, still not needed).**

**T2 — the level model. DONE and scored.** See NEXT.

**T3 — the roster model (set network with a stochastic per-tree head).** Blocked on nothing
technical, but pointless before the pilot corpus: the joint trait dependence it would add is not
what either failure is about.

**T4 — state synthesis. DONE to t2 on the ladder** (format round-trip, config pre-flight, the C
loads and runs a year), FAILING at t4 (the state distribution). t3 and t5 are not worth running
until item 1 above is done.

## Line T gotchas

* **Fit ONE model and apply it to both climates** when scoring a response. Fitting twice lets the
  fitting noise leak into the difference, which is the quantity under test — `fit_out_of_fold`
  takes a LIST of feature matrices for exactly this reason.
* **Log-transform the strictly positive stock targets.** The acceptance band is relative, so a
  squared error on the raw scale would spend nearly all its attention on the wet tropics.
* `k_root` comes out at 1.000 inside the band for all three of its quantiles — it is nearly
  constant across the domain, so it contributes nothing to the conjunctive test either way. Worth
  disclosing whenever the 22-quantity number is quoted.
