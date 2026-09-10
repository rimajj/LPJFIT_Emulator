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

**READ `docs/reference/band-test-ceiling.md` BEFORE PLANNING ANYTHING.** It replaces the premise the
last three handoffs were written under. The short version: the conjunctive score's ceiling is
**0.5585**, not 1.0 — the apparent 1.0 is an artefact of taking the tolerance from the same two
seeds that define the truth, which makes any predictor of the ensemble mean pass by construction.
The shipped model scores 0.0351 on a non-circular band, so it is at **6 % of attainable**, not
3.6 % of perfect.

**ROOTING DEPTH IS FINISHED AS A TOPIC. Both routes are measured and both are small.** Route 1
(impose it) worked and hurt fidelity; route 2 (predict it better) works and buys +0.0034. Record:
`docs/decisions/20260910-T-rooting-depth-route-2-is-small-and-the-ceiling-is-0.56.md`. Against the
real ceiling, perfect rooting depth is worth +0.0263 and perfect `soilc` — the best single quantity
— is worth +0.0084. **Seven of the 22 quantities made perfect still leaves 89 % of cells failing.**
Do not open a per-quantity chase again; the arithmetic is in the reference, §3.

**THE SINGLE NEXT ACTION: make a broadly-wrong CELL broadly right.** Failure clusters 151× more
than independent per-quantity rates would give, 23.4 % of cells fail only 1–3 quantities, and
failure lives in low-biomass forest (0.2–0.8 % pass in the lowest four biomass deciles against
14.6 % overall). Two cell-level explanations are already **excluded by measurement**: a single
shared per-cell error factor (leading residual component carries 24.7 %; removing it with an oracle
moves 0.0361 → 0.0428) and deriving one trait from another through the model's own trait corridor
(makes it far worse — record §4, do not retry). What has NOT been tried: fitting the low-biomass
regime as its own problem, and predicting the cell's PFT composition, which currently appears
nowhere and which every per-PFT parameter in the C model depends on.

**What ships today, switched off.** `Emulator` takes per-head `Recipe`s (bounded target,
absolute-error objective); `ROOTING_DEPTH_RECIPES` is the measured one. Default empty, so the model
is **byte-identical** and no reported number changes meaning. Turn it on at the next full refit,
together with the soil features requested from D — measured together, and the pair is what earned
+0.0034 rather than +0.0017. Not worth a standalone rebuild of the deliverable.

**Still true, still blocking.** The response model must predict the CHANGE directly (blocked on D's
pilot corpus). Do NOT widen `MATCH_TRAITS` (11 of 22 quantities degrade). Do NOT rescale leaf
carbon (`allometry_tree.c:39-41` derives height from it). Turn rooting-depth imposition ON before
quoting any warmed climate, regardless of its present-day cost.

**The artifacts**, under `/p/tmp/jamirp/vegemu`. Deliverable
`runs/synth-v5/restart/restart_1999_emulated.lpj`, sha256 `1e856119…`, cells 42480–42499
(`synth-v2` superseded, `-v3` the rejected five-trait variant, `-v4` the un-anchored tail). Level
model out-of-fold `exp/map-response-v0/oof_map.parquet`; today's screen
`exp/screen-d95max/screen.json`, sha256 `e1dad6b9…`. Response −0.727.

**Housekeeping, clear.** Six campaigns harvested, `--check` green. No verdict owed (no `exp_id`).
**NOTHING WAITS ON THE OWNER. MERGE WHEN THE GATES ARE GREEN — this line's own call**, per the
owner, 2026-09-09. A previous session invented "do not merge unasked" and wrote it here; because
this block is replayed verbatim at session start, three sessions obeyed a rule nothing enforced.
Never park a green branch — if you write such a hold here, the hold is wrong.

⚠ Read the CI note in `docs/reference/cluster.md` before polling: `expected_gates.py` names gates a
docs-only push never runs, and `wait_gates.py` then hangs.

## Outbound to line X (2026-09-10) — quote the attainable ceiling beside the map score — 0.5585, not 1.0

The map score 0.0361 read against an implied ceiling of 1.0 looks like near-total failure; the attainable ceiling is 0.5585, so it is 6 % of attainable. Derivation, per-quantity table, caveats: docs/reference/band-test-ceiling.md. Also worth one sentence in the verdict: k_root is constant, so 3 of the 22 quantities pass for any prediction.

## Outbound to line D (2026-09-10) — add soil TYPE to the corpus features — soil depth alone is not enough

The corpus carries soil DEPTH but not soil TYPE, and type is what sets how much water the column holds. Rooting depth is selected by exactly that, so the level model lacks the physically right input for 3 of the 22 scored quantities. Measured first: soil code explains 2.5-3.0 % of the D95max residual variance as a main effect, and adding these columns was the single best lever on the confirm folds among six candidates.

ASKED: four columns in climate_<leg>.parquet from /p/projects/waldspektrum/priesner/clustering/global/soil_code_test.soil.bin (one unsigned byte per cell, no header, grid order, so a cell id indexes it directly; codes 1-9, 11, 12 occur) crossed with par/soil.js -- soil_awc_mm (soildepth * (w_fc - w_pwp)), soil_w_avail, soil_sand, soil_clay. Per-code values are transcribed in scripts/screen_d95max.py (SOILPAR). An unknown code must become NaN, not zero: zero reads as 'holds no water at all'.

WATCH: this changes CLIMATE_FEATURES, so every sealed leakage assertion and every stored oof_map.parquet is against the old feature set -- it needs a corpus version bump, not an in-place edit. Line T is not blocked on it. Record: docs/decisions/20260910-T-rooting-depth-route-2-is-small-and-the-ceiling-is-0.56.md

## Outbound to line D (2026-09-10) — RESENT — sbatch_cmodel.sh pins no modules, so a C run inherits the submitting shell

This message was written on 2026-09-09 and DROPPED, because lines/D/STATE.md sat at exactly its 120-line budget and an inbound block would have reddened the repo-wide budgets gate. That trap is fixed as of 2026-09-10 (an inbound block no longer counts against the recipient's budget), so here it is.

DEFECT: scripts/sbatch_cmodel.sh submits with --export=ALL and has no module load line, so a C run silently inherits the submitting shell's modules. A session whose shell has none submits a job that dies in under a second on libnetcdf.so.19, then libudunits2.so.0 -- one library per attempt if chased singly. Three jobs were lost to it. 20260908-X-build-provenance-of-the-low-emissions-leg.md already recorded that no job script pins its library set; this is that gap biting a caller. The durable fix belongs in the wrapper, which D owns.

The working module set was recovered from a green run's own 'module list' and is written up in .claude/skills/cmodel-run/SKILL.md.

ALSO: grep -c 'successfully terminated' returns 1 on a FAILED job, because the wrapper's own advice text contains the phrase. Anchor it: grep '^lpjml successfully terminated'.

## Milestones

**T0 — constraints and baseline spec. DONE**, in the module docstrings.
**T1 — the GPU launch path. OPEN, unblocked, not needed.**
**T2 — the level model. DONE and scored**, now attributed per quantity against a real ceiling
rather than against perfection; see NEXT.
**T3 — the roster model (set network, stochastic per-tree head).** Pointless before D's pilot corpus.
**T4 — state synthesis. t0–t4 all RUN.** t2 passes, t3 **fails** at 5 % against a 25 % ceiling, t4
passes on carbon at year one and fails conjunctively. t5 (end-to-end transient) is not started.

## Line T gotchas

* **Every band test needs a CEILING ARM, and the ceiling is almost never 1.0.** A band built from
  the same two seeds that define the truth is passed by any predictor of the ensemble mean, by
  arithmetic. This line has now been bitten twice: the synthesis legs scored 100 % where the
  attainable number was 25 %, and the map score was read against an implied 1.0 where the
  attainable number is 0.5585. Transfer the tolerance from another leg, or state that you did not.
* **Judge a quantity by its marginal worth against the CEILING, not against perfection and not by
  its own pass rate.** Rooting depth is worth +0.0419 to perfection and +0.0263 to attainable; only
  the second is a budget for effort. `scripts/diag_level_binding.py` gives the same-leg version.
* **Check whether the error is reducible before spending on it.** An out-of-fold prediction is
  independent of the held-out cell's seed draw, so `Var(pred-truth) = Var(pred-mu) + sigma^2/2` and
  the two seeds give `sigma`. That is a real decomposition; the band's own floor is not.
* **Read the parameter file the RUNS use, not the one with the obvious name.** The ground truth goes
  through `param_lpjmlfit.js` → `par/pft_lpjmlfit.js`; `par/pft.js` is the stock LPJmL file and
  disagrees on `k_root` (0.02 vs 0.04) and on the `D95max` ceiling.
* **A trait bound is usually per-PFT.** `D95max` runs [51, 1800] for one PFT and [51, 300] for
  another; a cell-level quantile mixes them, so a single interval is an envelope, not the truth.
* **Judge a roster by its TAILS, never by its medians.** Both faults that emptied the upper size
  class survived every mean the synthesiser printed, including a 0.02 % pool shortfall.
* **A validity check on the parts is not a viability check on the whole.** Every stem in the broken
  file was a byte-exact real stem; the roster was still not a forest that could live there.
* **An ORACLE arm is the cheapest attribution there is.** It has seen the answer: never quote it as
  skill. **Fit ONE model and apply it to both climates** when scoring a response.
* `k_root` is exactly CONSTANT — zero error, zero spread, zero oracle gain — so the conjunctive test
  is effectively over **19** quantities. Disclose it whenever quoting the 22.
* **Keep a command clear of `slurm-guard.sh`'s keywords** (`train|eval|score|fit|sweep|response|
  rung`): it matches the WHOLE command, so even `cat scripts/train_emulator.py` is denied. Any
  command naming a `.py` file also trips the login-node guard — prefix `ALLOW_LOGIN_HEAVY=1` for a
  genuinely quick check.
* **A decision record is immutable the moment it says `accepted`**, including one written five
  minutes ago and never committed. Draft it as `draft`, or expect to delete and rewrite.
* **Re-read `origin/main` before trusting "the merge is ready"** — it moved twice in two days.
