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

**As of 2026-09-23** — rotated by the integrator (12 message blocks triaged, a disposition each,
into `journal/T/2026-09b.md`); the integrator refreshes this block at session end. Basis of every
number: pilot corpus v2-constco2 (200 cells × 30 climates × 1 seed, CO₂ 276.59 ppm), 200 of 54,020
tree-bearing cells — none of it is a fidelity claim.

✅ **Product A from climate + soil ALONE passes** (`X-20260923-equilibrium-from-climate`,
`scripts/exp_equilibrium_map.py`): 0.607582 mean variance explained over 19 varying quantities at
held-out 15° tiles, vs bar 0.222666 and analogue lookup 0.097666 — 64 % of the attainable 0.950.
**The gap is traits** (0.29–0.60: rooting depth, wood-density/SLA/longevity medians) **and the
band**: 0.0 % of runs inside a flat 10 % on all 22 (one real run vs another: 4.9 %).

✅ **Species-mix kill test re-passes at constant CO₂**: 0.445852 vs bar 0.300203 (51.7 % of the
attainable 0.862853). ⚠ **A model BLIND to the climate change scores 0.307940 and clears that bar
alone** (fails at 5° blocking, 0.296620 vs 0.305348): only ~+0.138 reads the forcing, so justify a
composition head by that, never by the 0.4459 (`X-20260923-pilot-composition-blind-arm`).
⚠ **Response kill test**: 0.558968 vs bar 0.257725, blind arm 0.362322 — 64.8 % is blind skill and
only +0.196646 reads the forcing; that, not the nulls, is what to move.

**THE PRINCIPAL BUILD: `models/synth.py` MUST STOP COPYING SPECIES COMPOSITION.** The model arm
(`scripts/exp_model_pilot_composition.py`) predicts each type's stem-share change; wiring it into
the roster builder is the work. ⚠ It needs its own t0–t4 pass, not just a score — right shares with
inadmissible stems has failed here twice — and a PER-LEVEL check: composition loses to no-change at
2 of 29 levels, both cold (`core_t+0_p13` −0.0882, `lhs10` −0.0665).

🔄 **Parallel integrator branches (`int/*`) are building the corpus-v3 schema, the truth builder,
features, the equilibrium model, synthesis, the global restart writer and new scoring**, which
overlap this line: read `git log origin/main` before starting. A full constant-CO₂ second seed of
the pilot is also running (integrator; jobs 2280660/2280661 + 24 spin-up manifests).

⚠ **With any composition number:** shares count stems, not biomass; the seven sum to 1 (six free);
scored only where a forest exists at both ends (5,258 of 5,800 pairs). It is a SEPARATE estimand —
`RESPONSE_QUANTITIES` is sealed (a test asserts it): never append to it, never sum the two scores.

**Still true:** do NOT widen `MATCH_TRAITS` (11 of 22 degrade); do NOT rescale leaf carbon
(`allometry_tree.c:39-41`); do not reopen the per-quantity chase (`band-test-ceiling.md` §3).
Rooting-depth recipes stay OFF until the next full refit, and the corpus still has NO soil-type
columns and still writes 0.0 into a treeless cell's `pft_frac_*` (D's NEXT). **No warmed climate may
be quoted from the scenario-leg map** (below persistence). Nothing here waits on X. Deliverable
unchanged: `runs/synth-v5/restart/restart_1999_emulated.lpj`, sha256 `1e856119…`.

## Milestones

**T0 spec DONE** (module docstrings). **T1 GPU path OPEN**, unblocked, not needed.
**T2 the level model DONE and scored** — but it FAILS on a leg it never saw, below persistence, so
its number is a present-day number and does not transfer to a warmed climate.
**T3 the roster model UNBLOCKED** — D's pilot corpus exists and a response is learnable on it.
**T4 state synthesis, t0–t4 RUN**: t2 passes, t3 **fails** at 5 % against a 25 % ceiling, t4 passes
on carbon at year one and fails conjunctively. t5 (end-to-end transient) not started.
**T5 the response model — PASSED** its kill test (v1 2026-09-14; re-passed at constant CO₂ 09-21).
**T6 composition — PASSED** (v1 2026-09-15; re-passed at constant CO₂ 09-21; blind arm 09-23).

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
* **No known prose-in-a-command case still trips the login-node guard** (flags, paths, heredoc
  bodies and quoted assignments all fixed by 2026-09-16); if one does, it is a bug to report, not a
  thing to work around. `ALLOW_LOGIN_HEAVY=1` is for a genuinely quick REAL check only.
* **A decision record is immutable the moment it says `accepted`**, including one written five
  minutes ago and never committed. Write `draft`, or expect to delete and rewrite.
* **`git rev-list --left-right --count origin/main...HEAD` prints BEHIND first, then AHEAD.** Re-read
  `origin/main` before trusting "the merge is ready" — it moves.
* **Mixing an integer, a slice and a list in one numpy subscript silently transposes the result** —
  `x[i, :, cols]` is `(len(cols), n)`, and assigning through it broadcasts instead of erroring.
* **A metrics file `append_result.py` refuses is a result nobody can cite.** Flat `arms` block
  naming each null exactly as the pre-registration does, plus `prereg_sha256` from
  `VEGEMU_PREREG_SHA256` read INSIDE the job: `vegemu.results.append_result_block`.
