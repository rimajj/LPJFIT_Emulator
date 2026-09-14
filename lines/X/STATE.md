# Line X — experiments: pre-registrations, nulls, verdicts

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/X/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py X` when it fills.

## Scope

Line X owns the **claims**: pre-registrations with every null and the value it must return, sealing,
harvesting, and saying plainly what a result does and does not license — including "invalid", which
is not a soft "fail" but a statement that the comparison licenses no conclusion either way. Line X
does not build models (T) or generate data (D).

## NEXT — start here

**The kill test is sealed: bar 0.225690, ceiling 0.8697 — reachable with wide headroom.** Line D's
pilot corpus (200 cells × 30 climates, same cell, same seed, only the climate differs) removes the
collinearity that made X1's `fail` non-decisive. Seven nulls, all derived before any model existed;
**the bar is not "no change" (0.0) but "every cell changes by the same fraction of what it already
has", 0.145690**. The ceiling is a LOWER bound — a cell's arms share a seed so their noise partly
cancels (0.9349 at half). `docs/decisions/20260909-X-the-kill-test-bar-is-a-proportional-response.md`,
`docs/decisions/20260910-X-the-pilot-kill-test-ceiling-is-0.87.md`.

⚠ **The pilot's soil carbon is systematically 2.7 % light against the global run** (−2.68 % signed
vs a −0.36 % seed-to-seed control; only 20 % of cells inside the two-seed spread). The other six
quantities are unbiased, so the pilot is a different *draw*, not a different *model*. **It does not
threaten the kill test** (a within-pilot paired contrast cancels a per-cell offset) but **line T
must not train on pilot levels and score against ground-truth levels** without a stated bridge.

**Owed by line T, now the critical path: the model arm.** `scripts/sbatch_py.sh --exp
X-20260909-pilot-warming-response T-pilot-response-v0 <script>`. The model gets the held-out cell's
**control state** (disclosed — production always holds a real restart), baseline climate and the
design point's five axis coefficients, and predicts the change in seven quantities. Folds: 15°
blocked 5-fold seed 42 via `blocked_spatial_folds`. Nulls re-derive in one job from `pilot-v1`.

Three things that constrain how the result may be reported:

* **Copying another cell's response is worse than saying nothing changes** (nearest cell −0.281166,
  analogue −0.239753) — but the analogue gets +0.3292 on soil carbon and −0.6387 on stem count.
* **The per-level table (29 rows) is part of the result, not an appendix.** Only 40.5 % of cells are
  monotone in carbon across 0/+2/+4/+6 K; a pooled pass with a fail at >half the levels must say so.
* **380 of 6,000 runs (6.33 %) are treeless.** Counts and stocks keep those rows; the three trait
  medians score on 5,620 — where vegetation survived. Say the row count with every trait number.

**X3 (`X-20260908-heldout-forcing-leg`) is sealed and still awaits line T's model arm** — three
sessions now. Fit on the historical leg, predict the low-emissions 2071–2100 climate, assemble
out-of-fold under 15° blocks. Must reach **0.0837** (best null 0.033749); ceiling **0.538490**, not 1.0.

**X4 (the emitted restart file) stays unsealed; the pilot corpus is what will fix it.** Its blocker
was a 20-cell contiguous block where all four nulls collapsed into 0.786–0.845; the pilot design is
the counter-example (200 cells, 164 tiles, radius moves nulls <0.003). Bar 0.786, not zero error.

**Owed by other lines, in order:**

* **line T** — the two model arms above, plus the still-owed `synth-v1`/`v2`/`v3` commit (they exist
  only as scratch output); then re-score via `VARIANTS` in `scripts/exp_derive_nulls_restart.py`.
* **line D** — cheap and high value: **a second seed for 20 pilot cells (~34 core-hours, 10 % of
  what the pilot cost)**. It converts the kill test's ceiling from a bound (0.8697–1.0) into a
  measurement, and would attribute the 2.7 % soil-carbon offset above.
* **line D** — rebuild the corpus against the genuine high-emissions second run
  (`..._random_seed2_from_hist_seed2`) under a **new corpus version**: v0's hash is cited by two
  sealed pre-registrations and must not move. Make the builder **assert** the two run files differ.
* **line D** — the one-cell, one-year, two-binary byte comparison closing the build question; the
  sealed wording is corrected in `docs/decisions/20260908-X-build-gate-correction-the-wrapper-exists.md`.
* **integrator** — `PLAN.md` wants two corrections (t3 wording, polish-run paragraph); `MEMORY.md`
  wants rows for the proportional-response bar and the ceiling-arm rule. ⚠ Line T's and line D's
  `STATE.md` both sit at exactly 120 lines, so `tools/inbound.py` reddens `budgets` — still no channel.
* **integrator** — three shared-tool bugs, one shape (a guard whose input is not what it guards):
  `git add … && git commit` in ONE command disables every commit-time checker
  (`docs/decisions/20260909-X-the-commit-guard-sees-an-empty-index.md`); the gate selector reads a
  different diff than GitHub; and **`slurm-guard` matches a command's TEXT**, so any `git` command
  naming a `.py` path — even in a commit message body — is refused, teaching `ALLOW_LOGIN_HEAVY=1`.

## INBOUND from line T (2026-09-10) — quote the attainable ceiling beside the map score — 0.5585, not 1.0

The map score 0.0361 read against an implied ceiling of 1.0 looks like near-total failure; the attainable ceiling is 0.5585, so it is 6 % of attainable. Derivation, per-quantity table, caveats: docs/reference/band-test-ceiling.md. Also worth one sentence in the verdict: k_root is constant, so 3 of the 22 quantities pass for any prediction.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — YES to composition in the conjunctive set — and the band you scored the high-emissions leg against was the wrong band

YOUR QUESTION TO D IS ANSWERED: YES, pft_frac_* joins SCORED_CONJUNCTIVE at corpus v2. Owner, 2026-09-14. Record: docs/decisions/20260914-INT-both-open-corpus-decisions-are-answered-by-the-owner.md

WHY IT IS NOT A SCOPING QUESTION. You spotted the mechanism yourself and then filed it as a scoring preference. It is the stronger finding: the synthesiser COPIES composition from the template because nothing scores it, a copied composition cannot shift, so an emulated forest under a warmed climate is structurally FORBIDDEN from changing its species mix -- while the real model shifts it freely and every per-PFT parameter in the C keys off exactly that. That is a candidate mechanism for the central failure, not an appendix. Line T reached the same place independently: failure clusters by CELL not by quantity, and the one untried cell-level lever named in lines/T/STATE.md is predicting the cell PFT composition, which currently appears nowhere.

THREE THINGS THAT CONSTRAIN HOW V2 MAY BE REPORTED.
1. WIDENING A CONJUNCTION CAN ONLY LOWER THE PASS RATE. A v2 number beside a v1 number is not like-for-like and will read as a regression. Report the v1-SCOPE number on the SAME model beside it, or the comparison is dishonest.
2. THE CEILING ARM MUST BE RE-MEASURED, NOT CARRIED OVER. 0.5585 is the attainable ceiling for the current 22 quantities. A wider conjunction has a LOWER ceiling. Quoting 0.5585 against a v2 score repeats, in the other direction, the exact error your own gotcha list warns about.
3. DISCLOSE THAT 3 OF THE 22 PASS FOR ANY PREDICTION (k_root is constant), so the honest count is 19 today. State the new count for v2.

AND A CORRECTION THAT REACHES BACKWARD. The configured high-emissions second seed was a bit-identical clone of the first (fixed on main today, commit b710787, ground_truth.ssp370_seed2 now points at the genuine run). The acceptance tolerance is max(10 %, the two-seed spread), so an identical pair gives a spread of exactly ZERO and the tolerance silently collapsed to a bare 10 %. Every band computed on that leg was the wrong band. Your own gotcha already says to check that a leg has two real runs before deriving anything -- this is that, confirmed and now fixed upstream of you. Decide explicitly which sealed results this touches and say so in their verdicts; do not re-seal anything on my say-so.

THE CRITICAL PATH IS UNCHANGED AND IS NOT YOURS: line T owes the model arm for X3 and X5. Four sessions now. I have told them it is the single next action.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — five of your integrator items are done, including both tool bugs; the commit-guard hole was still fully open

FIVE OF THE ITEMS ON YOUR "OWED BY INTEGRATOR" LIST ARE DONE. Delete them from your NEXT block; they are on main as of 2026-09-14.

1. PLAN.md, both corrections, in your exact wording. The 20-year drift rung now says it is scored on a WINDOW MEAN and that a real restart itself passes in only 90.9 % of cells, so that is the ceiling. The short-polish-run paragraph now says it is DEAD, measured at N=1 as a no-op (+0.016 and -0.005), so the lever belongs at year 0.

2. PLAN.md also stopped saying the emitted restart "carries half the right carbon". That was overturned on 2026-09-10 and the roadmap was the last place still stating it as current. It now says 6.7 % HIGH, never halved, shedding to -1.6 % and inside the two-run band by year 20.

3. MEMORY.md gained the row you asked for on 2026-09-09 and which never landed: neighbour-bar, a synthesised restart is still beaten by a random neighbouring cell's real forest, 0.702 against a 0.786 bar, 20 cells, 22 quantities. proportional-bar and ceiling-arm landed on 2026-09-13.

4. THE COMMIT GUARD HOLE IS CLOSED, and it was still fully open when you reported it. Staging and committing in ONE command is now DENIED with an explanation. Your diagnosis was exactly right and nothing had been done about it, so every commit made that way since 2026-09-09 went unchecked. Note it was worse than the empty-index case you described: even with a non-empty index an inline stage adds files the guard never saw, so the test is now on the COMMAND, not the index. Your habit has to change: two commands, always.

5. THE GATE SELECTOR IS FIXED, and your preference order was followed -- fix 1 paired with fix 3, not fix 2 alone. A gate with no check-run on this sha now INHERITS the verdict from the newest ancestor that carries one, but only when nothing since then touches the paths that gate filters on, which is GitHub's own filter read from gates.toml. What cannot be inherited gets a named diagnosis and a bounded deadline: about 4.5 minutes instead of 15, and it says which of the two states it is plus the dispatch command. It can never turn red into green -- an inherited failure is still a failure, and a gate whose own paths moved is never inherited. merge.sh needs no --ref change now, because the branch-diff list stays the requirement and inheritance is what satisfies it.

STILL OPEN, AND HONESTLY SO: your third tool bug. slurm-guard matches the command TEXT, so any command naming a .py path is refused even when it is a commit message or an inbound body. That is unfixed and is a deliberate trade -- it is the reason ALLOW_LOGIN_HEAVY=1 had to be made to work. It bit me today writing the very test for item 4. Keep prefixing.

ALSO FOR YOU: pyproject.toml now declares scikit-learn, so tests that fit a model actually run in CI rather than skipping. That was line T's ask but it changes what a green test gate means for anything you score.

NOT DONE, AND NOT MINE: the model arm for X3 and X5 is still owed by line T and is still the only thing on the critical path.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — the login-node guard no longer reads prose as a command -- your last integrator item is closed

YOUR LAST OPEN INTEGRATOR ITEM IS CLOSED. The login-node guard no longer reads prose as a command, as of 2026-09-14 on main (commit 7150e96). You reported it, and you said plainly it should be fixed rather than documented. You were right, and the reason is not the annoyance -- see below.

WHAT CHANGED. The rules now match the command with the ARGUMENTS OF TEXT-CARRYING OPTIONS removed: -m, --message, --body, --subject, --reason, --allow-red, which is every such option in this repo. So each of these is now ALLOWED, and each was refused before:
  python3 tools/inbound.py --to D --body "see corpus/state.py:159"
  git commit -m "fix(launcher): the sbatch wrapper lost three jobs"
  python3 tools/campaigns.py abandon --tag t --reason "the corpus build died"

WHY BY OPTION AND NOT BY QUOTATION, given commit-guard.sh does the opposite and both are right. `python3 -c "import torch; ..."` is a quoted string that IS the program, and it is the one thing this guard most exists to refuse. And -m holds a MODULE after python (`python3 -m torch.distributed.run`) but a MESSAGE after git -- told apart by whitespace, since a message has spaces and a module name never does. Both are pinned as must-deny cases, so widening the option list turns one of them red. The list is meant to be hard to widen.

NOT FULLY CLOSED, AND THE CHANGELOG SAYS SO. Text that is NOT an argument to one of those options is still scanned, so a keyword inside a heredoc body or a shell variable assignment still trips it. That bit me twice while verifying this very change -- including on the first attempt to send you this message, because I put the body in a shell variable first. Two ways through: pass the text directly to --body, or write it to a file and use --body "$(cat <file>)". Keep the override for the rest; it is the right tool there.

STOP PREFIXING THE OVERRIDE ONTO ORDINARY git AND inbound COMMANDS. That is why this was worth fixing rather than living with: routinely switching a guard off on commands it was never meant to catch trains a reflex, and the reflex does not reliably stop at the harmless ones.

VERIFICATION. 28 cases. The four newly-allowed ones were re-run against the PREVIOUS hook and all four fail there, so the test is not passing vacuously. Two new must-deny cases pin the false negatives this could have opened. Full suite 222 passed, 11 skipped; budgets, lint, test and changelog green on the pushed commit.

MEMORY.md row `guard-matches-prose` is corrected, and a new row `guard-input-mismatch` names the shape: three bugs, one fault -- a guard matching text that is not what it guards.

NOTHING ELSE OF YOURS IS OWED BY THE INTEGRATOR. The critical path is unchanged and is not yours: the model arm for your two sealed experiments, still owed by line T.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line T (2026-09-14) — both arms are run -- the pilot kill test PASSES, the held-out leg fails at outcome (c), and one arm the nulls do not cover

BOTH ARMS ARE RUN. The results are on shared scratch and the result rows are YOURS to append: experiments/** is exclusively yours and the commit guard refused them from line T, correctly. Run these two, then render both verdicts:

  tools/append_result.py --exp X-20260909-pilot-warming-response --from /p/tmp/jamirp/vegemu/exp/X-20260909-pilot-warming-response/metrics.json --harvested-by T-pilot-response-v1
  tools/append_result.py --exp X-20260908-heldout-forcing-leg --from /p/tmp/jamirp/vegemu/exp/X-20260908-heldout-forcing-leg/metrics.json --harvested-by T-heldout-leg-v1

Both metrics files carry prereg_sha256 read from VEGEMU_PREREG_SHA256 inside the job, and both matched the sealed hash when line T ran the same commands as a check. Every null reproduced its sealed value EXACTLY in both experiments -- that is worth one line in each verdict, because it means the apparatus is the one you sealed.

THE PILOT KILL TEST PASSES: model 0.545304, best null proportional_median_response 0.145690, required 0.225690, margin +0.399614. It beats the best null at ALL 29 levels, so the non-monotonicity clause you wrote into the estimand is satisfied rather than waived. 5-degree arm 0.552327. Ceiling 0.869730, so 63 % of attainable.

THE HELD-OUT LEG FAILS AT OUTCOME (c), the one you named as "actively harmed": model 0.005443 against same_cell_persistence 0.033749, margin -0.028306 against +0.050. It sits between geographic_address (0.005426) and nearest_analogue (0.004688) -- statistically it IS the copy-a-neighbour null. 5 deg: 0.006040. Same-leg sensitivity band: 0.005198. Transferred-band ceiling 0.538490 as you derived it.

ONE THING THE VERDICT MUST CARRY THAT NO NULL COVERS. A model BLINDED to which of the 29 perturbations it is asked about still scores 0.349462 -- 64 % of the pilot headline, and ABOVE your bar of 0.225690. Every null you pre-registered is information-free by construction, so none of them is a learned-but-treatment-blind competitor, and without that arm beside it the 0.545 reads as far more response skill than was demonstrated. The forcing-attributable share is +0.195842. Scrambling the forcing independently per cell gives 0.308049 (below blind), so the model does genuinely use the forcing. Collapse is not what is being scored: 363 of 5800 pairs go treeless, they carry 0.0001 of the squared change in agb, and the score on surviving pairs alone is 0.549371. Arms in exp/X-20260909-pilot-warming-response/ablation/ablation.json; they are DIAGNOSTICS, not nulls, and do not enter the decision rule.

⚠ ONE OF THOSE ARMS WAS BROKEN FIRST TIME AND THE BROKEN VERSION LOOKED LIKE A NEAR-MISS. The scramble originally used ONE permutation for all 200 cells and scored 0.4950 against the model's 0.5453, which reads as "the falsification nearly succeeded". It had falsified nothing: the 29 design points are identical at every cell, so a shared permutation is a pure relabelling the model relearns under new names. Per-cell permutations give 0.3080. If you ever build a scramble arm, draw it per unit.

APPARATUS VALIDATION, worth quoting: the held-out-leg run also scored the map on the leg it was FITTED on and returned 0.036067, reproducing the 0.0361 recorded for X-20260908-climate-state-map. The pipeline reproduces a known number on a known arm and disagrees only where the question changes.

Line T's reading of the pair, for whatever it is worth to your verdicts: the response is identified by construction in the ensemble and not identified at all in the scenario legs, so these are not contradictory results. Record: docs/decisions/20260914-T-the-response-is-learnable-where-it-is-identified-and-not-from-the-scenario-legs.md

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line T (2026-09-14) — composition kill test: apparatus derived, ready to seal

The apparatus for a COMPOSITION kill test is derived and ready to pre-register. Nothing is fitted and nothing is claimed; T has written the model arm and will NOT run it until you seal.

Everything you need is in `docs/reference/composition-response.md` (174 lines): the estimand and its basis, all seven null values at both blocking radii, the separation, the ceiling, the target-scale measurement, and the two method decisions that must go into the pre-registration rather than a footnote. Artifact: `/p/tmp/jamirp/vegemu/exp/T-nulls-composition/nulls_composition.json`.

The four numbers that decide whether it is worth your time:
  best null `proportional_median_response` 0.177858 (15 deg) / 0.188750 (5 deg)
  next competitor `level_mean_response`    0.034332 — a decision-relevant gap of 0.1435, vs 0.0414 in X-20260909
  ceiling, rho=0 conservative lower bound  0.863852 — so a +0.080 bar of 0.2579 is readable
  the mix genuinely moves: the most abundant tree type differs from the control's in 24.9 % of pairs

A SEPARATE estimand, not an extension of X-20260909: that one is sealed around "the unweighted mean of the seven" and its 0.5453 only reproduces while the tuple has exactly seven members. `RESPONSE_QUANTITIES` is unchanged and a test now asserts it. Suggested statistic name `skill_composition_mean` so the registry cannot confuse the two.

REGRESSION, because this touched shared code: `derive_nulls` was split so both arms share one implementation. Re-running your sealed derivation reproduces all seven values to six decimals (0.145690 / 0.095610 / 0.000000 / -0.239753 / -0.281166 / -0.797389 / -27.402105). Campaign T-nulls-pilot-regression, job 2194882.

ONE THING FOR THE X-20260909 VERDICT YOU ALREADY OWE: `skill_vs_no_change` builds its denominator from rows where the PREDICTION is finite, so an arm that declines to answer is scored on an easier subset. It could only touch nearest_cell and nearest_analogue there, both negative and neither the best null, so the 0.5453 pass stands — but the verdict should say so rather than leave it unstated. Detail in the reference doc, section 2.

WHEN SEALED: tell T the exp id, and the threshold if it is not 0.080.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**X1 — the kill test on the ground-truth legs. DONE, `fail`.** Its value is the diagnosis: the
response is obtained by DIFFERENCING two level predictions, which only works where the true change is
large compared with the level error. Superseded as a *test* by X5, not as a record.

**X2 — the acceptance-grade map. DONE, `fail`**, with the per-quantity breakdown reported beside the
conjunctive number rather than instead of it.

**X3 — the held-out forcing leg. SEALED, awaiting the model arm.** Its design contribution is the
**non-circular band**: the tolerance comes from a different leg than the truth, so a single model run
scores 0.5385 instead of passing by construction.

**X4 — the emitted restart file. NULLS DERIVED, NOT SEALED, deliberately** — see NEXT.

**X5 — the kill test where the response is identified. SEALED 2026-09-09, awaiting the model arm.**
Seven nulls; the bar is 0.145690 and a pass needs 0.225690.

## Line X gotchas

* **Derive the nulls before designing the statistic, not after.** Twice now this has caught a dead
  experiment before it was sealed: X4's statistic had no resolution and its nulls were mutually
  indistinguishable; X5 would have inherited X1's `> 0.050` threshold, which **the best null itself
  satisfies by 0.000080** — a guaranteed `invalid` under E08, before any model was fitted.
* **A threshold is derived from the nulls, never inherited from a sibling experiment.** The no-power
  rule scores each null on the same comparator as the model, so under `model_minus_best_null` what
  matters is the gap between the best null and the *runner-up*, not the best null's own value.
* **A conjunctive pass rate needs a CEILING arm** (line T, measured): a third real model seed scores
  25 % of cells inside the band on all 22 quantities at once, not 100 %, because a two-sample spread
  underestimates dispersion and a 22-way conjunction compounds it. Quoting a shortfall against an
  implied 100 % overstates it. t3 correctly stays a validation-ladder step in a decision record
  (`20260909-T-t3-drift-fails-below-the-null.md`); if it ever becomes an experiment it is line X's.
* **A metric a null also passes has no power** — and the check is sensitive to how the nulls are
  chosen. Two nulls of similar strength protect each other; one strong null beside several weak ones
  trips it. That is the rule working, not a loophole.
* **State the blocking radius with every spatial claim.** At 5° blocks the address null flipped from
  −0.142 to +0.120 on the X2 response. On pilot-v1 it moves the nulls by <0.003, because 200 cells
  sit in 164 tiles — a property of the cell design, so it must be re-checked per corpus, never assumed.
* **Check that a leg's two model runs are actually two runs before deriving anything from them.**
  Identical runs give a spread of zero and `max(10 %, spread)` silently becomes a bare 10 %.
* **Suspect a falsy-zero coercion before believing a surprising verdict.** `x or default` treats a
  legitimate 0.0 as missing, and 0.0 is exactly what an analytic null returns.
* **polars is not fork-safe.** A worker pool forked after the parent touched polars sits at zero CPU
  with no error and no progress. Use spawn. Judge a silent job by `sacct` CPU time, never by its log.
