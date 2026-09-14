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

**THE COMPOSITION ARM IS BUILT AND ITS APPARATUS IS DERIVED. It is blocked on line X sealing, and
on nothing else.** Everything is in `docs/reference/composition-response.md`; X has been sent a
short pointer to it. **Do not run the model arm before the seal** — that ordering is the whole point
of invariant 2, and `sbatch_py.sh --exp` enforces it.

**The question.** `models/synth.py` copies each tree's TYPE from the cell's own template roster, so
an emulated warmed forest cannot change which species it holds. Whether that limit costs anything
depends on whether the composition response is learnable — measurable now, without corpus v2.

**What was derived** (campaign `T-nulls-composition`, job 2194883): best null
`proportional_median_response` **0.177858** (0.188750 at 5 deg), next competitor `level_mean`
0.034332 — a decision-relevant gap of **0.1435**, more than triple the response test's 0.0414.
Ceiling, rho=0 conservative lower bound, **0.863852**, so a +0.080 bar of 0.2579 is readable.
**The target is not degenerate: the most abundant tree type differs from the control's in 24.9 % of
the 5,258 scoring pairs**, and a type's share moves with RMS 0.15–0.21.

**A SEPARATE estimand, not an extension of `RESPONSE_QUANTITIES`.** That tuple IS a sealed
pre-registration's estimand and its 0.5453 only reproduces while it has exactly seven members.
Appending to it would silently redefine a sealed experiment. A test now asserts it is untouched.

⚠ **Two method decisions that must survive into the verdict, both measured not assumed.** (1) A
treeless cell's `pft_frac_*` is 0.0 from the state summariser; as a CHANGE that is a collapse
wearing a composition's clothes, inflating the scored movement by 15–18 %. Blanked now, so 542 of
5,800 pairs drop and **composition is scored where a forest existed at both ends**. (2) Every arm is
now on one denominator with missing predictions imputed as no-change; the neighbour nulls needed
2,296 and 1,253 fills, so that asymmetry was live here, not theoretical. Both detailed in the ref.

**WHEN X SEALS:** `scripts/sbatch_py.sh --exp <id> T-comp-model-v1 scripts/exp_model_pilot_composition.py
--out <dir> --cache /p/tmp/jamirp/vegemu/exp/X-pilot-nulls-v1/state_pilot-v1.parquet --exp-id <id>`
(add `--threshold` if the sealed bar is not 0.080). It reuses the sealed response arm's features,
folds, leakage assertions, out-of-fold fit and decision arithmetic unchanged.

**If X has not sealed, the other track is: move the forcing-attributable +0.1958** on the response
arm — the BLIND arm at 0.3495, not the nulls, is what to beat. The headline 0.5453 is 64 % blind
skill and must never be quoted as "predicts the warming response" without that.

**Still true:** do NOT widen `MATCH_TRAITS` (11 of 22 degrade); do NOT rescale leaf carbon
(`allometry_tree.c:39-41`); do not reopen the per-quantity chase (`band-test-ceiling.md` §3).
Rooting-depth recipes stay OFF until the next full refit, then on WITH D's soil columns. **No warmed
climate may be quoted from the scenario-leg map** — it failed below persistence.

**Owed by X, still open:** verdicts on `X-20260909-pilot-warming-response` and
`X-20260908-heldout-forcing-leg`, and now a composition pre-registration. Deliverable unchanged:
`runs/synth-v5/restart/restart_1999_emulated.lpj`, sha256 `1e856119…`.

## Milestones

**T0 spec DONE** (module docstrings). **T1 GPU path OPEN**, unblocked, not needed.
**T2 the level model DONE and scored** — but it FAILS on a leg it never saw, below persistence, so
its number is a present-day number and does not transfer to a warmed climate.
**T3 the roster model UNBLOCKED** — D's pilot corpus exists and a response is learnable on it.
**T4 state synthesis, t0–t4 RUN**: t2 passes, t3 **fails** at 5 % against a 25 % ceiling, t4 passes
on carbon at year one and fails conjunctively. t5 (end-to-end transient) not started.
**T5 the response model on the ensemble — PASSING its kill test.**
**T6 composition — apparatus derived, model arm written, blocked on X's seal.**

## Line T gotchas

* **Every band test needs a CEILING ARM, and the ceiling is almost never 1.0.** A band built from
  the seeds that define the truth is passed by any predictor of the ensemble mean, by arithmetic.
  Bitten three times: synthesis scored 100 % where attainable was 25 %; the map read against 1.0
  where attainable is 0.5585; the pilot test sealed at 0.2257 before perfect was known to be 0.8697.
* **A CHECK THAT CANNOT FAIL LOOKS EXACTLY LIKE A CHECK THAT PASSED.** A permutation shared by every
  unit is a RELABELLING, not a scramble: the 29 design points are identical at every cell, so one
  shared permutation is a bijection the model relearns under new names. It scored 0.4950 vs the
  model's 0.5453 and read as "nearly falsified". Drawn per cell: 0.3080.
* **A pre-registered null set can omit the competitor that matters.** Every null here is
  information-free, so none is a LEARNED but treatment-blind model — and that arm scores 0.3495,
  above the bar of 0.2257. **Add a blind arm wherever the model gets per-unit covariates.**
* **A skill score's denominator can differ between arms and nobody will notice.**
  `skill_vs_no_change` masks on `isfinite(pred) & isfinite(true)`, so an arm that predicts NaN on
  the hard rows is scored on an easier subset than its rivals. Put every arm on the truth-finite set
  and impute the gaps as no-change — that filling is conservative, it strengthens a null.
* **Zero and "missing" are different, and the state summariser conflates them for shares.** A
  treeless cell gets `pft_frac_* = 0.0` but `*_p50 = NaN`. As a CHANGE the zero is a fake shift.
* **Judge a quantity by its marginal worth against the CEILING**, not against perfection or its own
  pass rate. Rooting depth: +0.0419 to perfection, +0.0263 to attainable; only the second is a
  budget. `scripts/diag_level_binding.py` gives the same-leg version.
* **Check whether the error is reducible before spending on it.** An out-of-fold prediction is
  independent of the held-out cell's seed draw, so `Var(pred-truth) = Var(pred-mu) + sigma^2/2` and
  the two seeds give `sigma`. A real decomposition; the band's own floor is not.
* **Read the parameter file the RUNS use**: `param_lpjmlfit.js` → `par/pft_lpjmlfit.js`, NOT stock
  `par/pft.js`, which disagrees on `k_root` (0.02 vs 0.04) and the `D95max` ceiling. **A trait bound
  is usually per-PFT**, so a cell-level quantile is an envelope, not the truth.
* **Judge a roster by its TAILS, never its medians.** Both faults that emptied the upper size class
  survived every mean the synthesiser printed. **A validity check on the parts is not a viability
  check on the whole**: every stem in the broken file was byte-exact; it still could not live there.
* **An ORACLE arm is the cheapest attribution there is** — it has seen the answer, so never quote it
  as skill. **Fit ONE model and apply it to both climates** when scoring a response.
* `k_root` is exactly CONSTANT — the conjunctive test is over **19** quantities, not 22. Say so.
* **The login-node guard no longer scans arguments to `-m/--message/--body/--subject/--reason`**
  (fixed on main 2026-09-14), so ordinary `git commit -m` and `inbound.py --body` need no override.
  It DOES still scan heredoc bodies, shell assignments and bare paths — write a long message to a
  file and pass it with `-F` or `--body "$(cat …)"`. Keep `ALLOW_LOGIN_HEAVY=1` for quick real checks.
* **A decision record is immutable the moment it says `accepted`**, including one written five
  minutes ago and never committed. Write `draft`, or expect to delete and rewrite.
* **`git rev-list --left-right --count origin/main...HEAD` prints BEHIND first, then AHEAD.** Re-read
  `origin/main` before trusting "the merge is ready" — it moves.
* **Mixing an integer, a slice and a list in one numpy subscript silently transposes the result** —
  `x[i, :, cols]` is `(len(cols), n)`, and assigning through it broadcasts instead of erroring.
* **A metrics file `append_result.py` refuses is a result nobody can cite.** Flat `arms` block
  naming each null exactly as the pre-registration does, plus `prereg_sha256` from
  `VEGEMU_PREREG_SHA256` read INSIDE the job: `vegemu.results.append_result_block`.

## Outbound to line X (2026-09-14) — composition kill test: apparatus derived, ready to seal

Sent via `tools/inbound.py`; kept as the sender's evidence, per that tool's own warning that a
rebase resolved with `--theirs` deletes the receiver's copy silently. **Full text of what was sent
is `docs/reference/composition-response.md`** — the message was a pointer to it plus the four
numbers now in NEXT above, the seven-value regression, and one note that the X-20260909 verdict
should state the denominator asymmetry rather than leave it unstated. Asked X for the exp id and the
threshold if it is not 0.080.
