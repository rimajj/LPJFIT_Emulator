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

**The emitted restart file is now stationary under the real model and its carbon matches to 9 %.**
The previous handoff's item 1 was based on a wrong diagnosis and has been retracted — do not do it.
Read `docs/decisions/20260909-T-the-roster-was-valid-but-not-viable.md` first.

**What was actually wrong.** Donors were matched on height and wood density over a pool spanning
biomes, and the tree TYPE was never checked, so 31 % of the stems written into twenty temperate
European cells were tropical broadleaved evergreen — a type those cells never contain. The model
loaded the file, ran without aborting, and killed all of them in year one. The synthesis was fine:
the file held 6.7 % MORE above-ground biomass than the truth, not half. Type is now copied from the
target cell's own template at the matching size rank, and the pool is 25,424 stems from a proximity
band with the target block excluded.

**Where it stands, in numbers** (20 cells of 54,020, temperate Europe, present-day, seed 1 — this
is NOT the acceptance test):

* **The emitted file, after one year of the real model**, median |emulated − control| / control:
  vegetation carbon **0.091**, above-ground biomass 0.092, stems per patch 0.088, median height
  0.063 — all inside the band, from 0.543 / 0.610 / 0.490 / 0.099 before. Carbon over the first
  year now goes ×1.04 against the control's ×1.02, where it went ×0.35.
* **But the conjunctive test still fails: 0 of 20 cells** inside the band on all 22 quantities at
  once, median 15 of 22. That rate is consistent with the emulator's own held-out 3.6 %, so it is
  inherited from the prediction, not added by the synthesis.
* **Level map** (unchanged, sealed): 0.0361 of held-out cells conjunctively, against 0.0212 for the
  nearest climate analogue; beats every null by 1.7× but the gate wanted a 0.050 margin, got 0.0149.
* **Warming response** (unchanged, sealed): −0.727 against 0.000 for predicting no change.

**Next, in order, cheapest first:**

1. **Run t3 — 20 years, drift against the two-seed spread.** Worth doing now and it was not before;
   a state that collapsed in year one had nothing to say about year twenty. Same two-arm subset
   recipe as t2: `scripts/corpus_cmodel_config.py --years 2000 2019` then `scripts/sbatch_cmodel.sh`.
2. **Leaf area is 30 % low and does not move.** Leaf carbon is a per-stem MASS and the transplant
   matches traits, not masses. A cell-total constraint (pick among near-matching donors so the
   cell's total leaf carbon hits the prediction) is a different mechanism and is not built.
3. **Do NOT widen `MATCH_TRAITS`** — measured, it makes things worse: 11 of 22 quantities degrade,
   the median cell drops from 15 of 22 hits to 12. One donor is one real stem and cannot sit at the
   same quantile of five distributions. `--match-traits` exists so the next attempt is a measurement.
4. **Do NOT tune the current model to chase the map gate.** The pre-registration is sealed; a
   changed model is a new `exp_id`.
5. **The response model must predict the CHANGE directly**, blocked on line D's pilot corpus. The
   current architecture differences two level predictions, which is the whole −0.727 and is
   arithmetic, not a hyperparameter. `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
6. **T1, the GPU path, still not built and still not needed** — boosted trees on 16 CPU cores, 4 min.

**Gate debt from the INBOUND blocks: CLEARED.** `ruff format` applied to all three T files; the
`no-any-return` fixed at both plausible sites in `synth.py` (mypy is installed in no environment on
this cluster, so it could not be verified locally — if `types` is still red, that is where to look);
PLR0915 was already fixed by the rebase. `ruff check .` passes repo-wide. `ruff format --check .`
still fails on **four line-D files** (`scripts/corpus_cmodel_config.py`, `scripts/corpus_convergence.py`,
`src/vegemu/binfmt/restart.py`, `src/vegemu/corpus/state.py`) — D-exclusive paths, so line T cannot
fix them and `tools/merge.sh` will refuse until D does.

Housekeeping: campaigns T-synth-v2/v3/v4 and T-cmodel-t2b/t2c are launched and harvested in-session.

## Milestones

**T0 — the constraints and the baseline spec. DONE**, in the module docstrings.

**T1 — the GPU launch path (OPEN, unblocked, not needed).**

**T2 — the level model. DONE and scored.** See NEXT.

**T3 — the roster model (set network, stochastic per-tree head).** Pointless before the pilot corpus.

**T4 — state synthesis. DONE to t2, and t4 now PASSES on carbon** for the 20-cell block (0.091)
while FAILING the conjunctive test there (0 of 20). t3 is item 1 above.

## Line T gotchas

* **A validity check on the parts is not a viability check on the whole.** Every stem in the broken
  file was a byte-exact real stem; the roster was still not a forest that could live there. Round
  trips validate layouts, not cross-references to a cell's climate.
* **Read the state summary of the file you WROTE** before attributing anything to the writer. One
  such read overturned a whole decision record's diagnosis.
* **Fit ONE model and apply it to both climates** when scoring a response — `fit_out_of_fold` takes
  a LIST of feature matrices for exactly this reason.
* **Log-transform the strictly positive stock targets**; the acceptance band is relative.
* `k_root` is nearly constant across the domain and sits at 1.000 inside the band for all three of
  its quantiles, contributing nothing to the conjunctive test. Disclose it when quoting the 22.
