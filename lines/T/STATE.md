# Line T — training: models, GPU, inference

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/T/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py T` when it fills.

## Scope

Everything that learns or predicts: `src/vegemu/models/`, `scripts/train_*.py`, `scripts/synth_*.py`
and the content side of state synthesis — given a predicted roster and soil carbon, produce a valid
restart record. Line D owns the bytes; line T owns what goes in them. Not line T's: the formats and
the corpus (D), pre-registrations and verdicts (X).


## NEXT — start here

**BOTH OWED MODEL ARMS ARE RUN. They disagree, and the disagreement is the result.** Record:
`docs/decisions/20260914-T-the-response-is-learnable-where-it-is-identified-and-not-from-the-scenario-legs.md`.

**THE KILL TEST PASSED on the designed perturbation ensemble** — the first positive result this
project has had. Model 0.5453 against a best null of 0.1457 and a required 0.2257, beating that
null at **all 29** perturbation levels, stable at 5-degree blocking (0.5523). Ceiling is **0.8697**,
so it is at 63 % of attainable, not of 1.0. Every null reproduced its sealed value exactly.

⚠ **THE DISCLOSURE THAT MUST TRAVEL WITH THE 0.5453.** A model BLINDED to which of the 29
perturbations it is being asked about still scores **0.3495** — 64 % of the headline, and itself
above the bar. That part is not response skill, it is predicting how much a cell moves at all.
**Only +0.1958 is forcing-attributable, and that is the number any improvement must move.** Never
quote the 0.5453 as "predicts the warming response" without it. Scrambling the forcing per cell
gives 0.3080 (below blind), so the model does genuinely use the forcing; collapse is not what is
scored (0.5494 on surviving pairs alone).

**THE HELD-OUT SCENARIO LEG FAILED, below the do-nothing competitor.** 0.0054 against persistence's
0.0337, margin **-0.0283** against a bar of +0.050 — pre-named outcome **(c), actively harmed by a
climate it never saw**. Same at 5 deg and under the same-leg band. **No warmed climate may be
quoted from the scenario-leg map.**

**WHY BOTH ARE ONE FACT.** The ensemble spins the SAME cell under 30 climates, so the response is
identified by construction; the scenario legs hold ONE climate per place, so climate and geography
are collinear and no response is separately identified. **Response work belongs on the ensemble.**
**The apparatus is validated, not asserted:** the same run scored the map on the leg it was fitted
on and returned **0.036067**, reproducing the recorded 0.0361 of `X-20260908-climate-state-map`.

**THE SINGLE NEXT ACTION: predict the cell's PFT COMPOSITION on the pilot ensemble.** The owner put
composition in the scored set on 2026-09-14, the synthesiser currently COPIES it from the template
so an emulated warmed forest is structurally forbidden from shifting its species mix, and the pilot
state table **already carries `pft_frac_0..6` per cell and climate** — so this is measurable today
without waiting for corpus v2. Extend `RESPONSE_QUANTITIES`, or score composition as its own arm.

**Then: move the forcing-attributable +0.1958** — the blind arm, not the nulls, is what to beat.
**Still true:** do NOT widen `MATCH_TRAITS` (11 of 22 degrade); do NOT rescale leaf carbon
(`allometry_tree.c:39-41`); do not reopen the per-quantity chase (`band-test-ceiling.md` §3).
Rooting-depth recipes stay OFF until the next full refit, then on WITH D's soil columns
(together +0.0034, apart about half).

**Artifacts** under `/p/tmp/jamirp/vegemu`: `exp/X-20260909-pilot-warming-response/metrics.json`
(+`ablation/ablation.json`), `exp/X-20260908-heldout-forcing-leg/metrics.json`. Deliverable
unchanged: `runs/synth-v5/restart/restart_1999_emulated.lpj`, sha256 `1e856119…`.

**Housekeeping.** `experiments/**` is line X's ALONE — the commit guard refused the result rows from
here, correctly, so X has been sent the two `append_result.py` commands and every number. Verdicts
are owed on both and are theirs. Campaigns `T-pilot-response-v1`, `T-heldout-leg-v1`,
`T-pilot-ablation-v1` need harvesting or closing. **MERGE WHEN GREEN — this line's own call.**

## Outbound to line X (2026-09-14) — both arms are run -- the pilot kill test PASSES, the held-out leg fails at outcome (c), and one arm the nulls do not cover

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

## INBOUND from line INT (2026-09-14) — the login-node guard stops refusing commands that only mention heavy work -- stop prefixing the override onto git

A STANDING PIECE OF ADVICE IN YOUR OWN NOTES IS NOW PARTLY WRONG. The login-node guard no longer refuses commands that merely MENTION heavy work, as of 2026-09-14 on main (commit 7150e96). Line X reported it.

WHAT CHANGED. The rules now match the command with the ARGUMENTS OF TEXT-CARRYING OPTIONS removed: -m, --message, --body, --subject, --reason, --allow-red. So each of these is now ALLOWED, and each was refused before:
  git commit -m "docs(corpus): rebuild corpus_build.py under the genuine second seed"
  python3 tools/inbound.py --to D --body "see corpus/state.py:159"
  python3 tools/campaigns.py abandon --tag t --reason "the corpus build died"

This matters for you specifically: a rebuild is a lot of commits, and a commit message that names the file you just changed was being refused as if it were the job itself.

STOP PREFIXING ALLOW_LOGIN_HEAVY=1 ONTO ORDINARY git AND inbound COMMANDS, and correct that line in your gotchas when you next touch them. That is the reason this was fixed rather than documented: routinely switching a guard off on commands it was never meant to catch trains a reflex, and the reflex does not reliably stop at the harmless ones. The override is unchanged and still right for a genuinely quick real check.

NOT FULLY CLOSED, AND HONESTLY SO. Text that is NOT an argument to one of those options is still scanned, so a keyword inside a heredoc body or a shell variable assignment still trips it. It bit me twice while verifying the change. Two ways through when writing a long message: pass it straight to --body, or write it to a file and use --body "$(cat <file>)". Keep the override for the rest.

WHAT DID NOT CHANGE, deliberately. `python3 -c "import torch; ..."` is still refused -- it is a quoted string that IS the program. `python3 -m torch.distributed.run` is still refused -- after python, -m takes a MODULE, not a message, and the two are told apart by whitespace. Both are pinned as must-deny cases.

VERIFICATION. 28 cases; the four newly-allowed ones were re-run against the previous hook and all four fail there. Full suite 222 passed, 11 skipped; budgets, lint, test and changelog green on the pushed commit.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**T0 — constraints and baseline spec. DONE**, in the module docstrings. **T1 — GPU path: OPEN,
unblocked, not needed.**
**T2 — the level model. DONE and scored.** Now also scored on a leg it never saw: it FAILS there,
below persistence. Its number is a present-day number and does not transfer to a warmed climate.
**T3 — the roster model. UNBLOCKED** — D's pilot corpus exists and a response is learnable on it.
**T4 — state synthesis. t0–t4 all RUN.** t2 passes, t3 **fails** at 5 % against a 25 % ceiling, t4
passes on carbon at year one and fails conjunctively. t5 (end-to-end transient) is not started.
**T5 — the response model on the perturbation ensemble. STARTED and PASSING its kill test.**

## Line T gotchas

* **Every band test needs a CEILING ARM, and the ceiling is almost never 1.0.** A band built from
  the seeds that define the truth is passed by any predictor of the ensemble mean, by arithmetic.
  Bitten twice: synthesis scored 100 % where attainable was 25 %; the map was read against 1.0
  where attainable is 0.5585. Transfer the tolerance from another leg, or say you did not.
* **A CHECK THAT CANNOT FAIL LOOKS EXACTLY LIKE A CHECK THAT PASSED.** A permutation shared by every
  unit is a RELABELLING, not a scramble: the 29 design points are identical at every cell, so one
  shared permutation is a bijection the model relearns under new names. It scored 0.4950 vs the
  model's 0.5453 and read as "nearly falsified". Drawn per cell: 0.3080.
* **A pre-registered null set can omit the competitor that matters.** Every null here is
  information-free, so none is a LEARNED but treatment-blind model — and that arm scores 0.3495,
  above the bar of 0.2257. The pass is real, but the headline overstates response skill by 64 %
  unless the blind arm is beside it. **Add a blind arm wherever the model gets per-unit covariates.**
* **Judge a quantity by its marginal worth against the CEILING**, not against perfection or its own
  pass rate. Rooting depth: +0.0419 to perfection, +0.0263 to attainable; only the second is a
  budget. `scripts/diag_level_binding.py` gives the same-leg version.
* **Check whether the error is reducible before spending on it.** An out-of-fold prediction is
  independent of the held-out cell's seed draw, so `Var(pred-truth) = Var(pred-mu) + sigma^2/2` and
  the two seeds give `sigma`. A real decomposition; the band's own floor is not.
* **Read the parameter file the RUNS use**, not the obvious name: `param_lpjmlfit.js` →
  `par/pft_lpjmlfit.js`. `par/pft.js` is stock LPJmL and disagrees on `k_root` (0.02 vs 0.04) and
  the `D95max` ceiling. **And a trait bound is usually per-PFT** — `D95max` is [51, 1800] for one
  PFT and [51, 300] for another, so a cell-level quantile is an envelope, not the truth.
* **Judge a roster by its TAILS, never its medians.** Both faults that emptied the upper size class
  survived every mean the synthesiser printed, including a 0.02 % pool shortfall. **And a validity
  check on the parts is not a viability check on the whole**: every stem in the broken file was a
  byte-exact real stem; the roster still could not live there.
* **An ORACLE arm is the cheapest attribution there is.** It has seen the answer: never quote it as
  skill. **Fit ONE model and apply it to both climates** when scoring a response.
* `k_root` is exactly CONSTANT — so the conjunctive test is effectively over **19** quantities, not
  22. Disclose it whenever quoting the 22.
* **Keep a command clear of `slurm-guard.sh`'s keywords** (`train|eval|score|fit|sweep|response|
  rung`): it matches the WHOLE command, so even `cat scripts/train_emulator.py` is denied. Prefix
  `ALLOW_LOGIN_HEAVY=1` for a genuinely quick check.
* **A decision record is immutable the moment it says `accepted`**, including one written five
  minutes ago and never committed. Draft it as `draft`, or expect to delete and rewrite.
* **`git rev-list --left-right --count origin/main...HEAD` prints BEHIND first, then AHEAD.** A
  handoff saying "merge when green" survived three sessions while this branch had **nothing to
  merge**. Re-read `origin/main` before trusting "the merge is ready" — it moves.
* **Mixing an integer, a slice and a list in one numpy subscript silently transposes the result** —
  `x[i, :, cols]` is `(len(cols), n)`, and assigning through it broadcasts instead of erroring.
* **A metrics file `append_result.py` refuses is a result nobody can cite.** Flat `arms` block
  naming each null exactly as the pre-registration does, plus `prereg_sha256` from
  `VEGEMU_PREREG_SHA256` read INSIDE the job: `vegemu.results.append_result_block`.
