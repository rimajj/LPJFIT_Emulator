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
The previous handoff's item 1 (`add agb to MATCH_TRAITS`) rested on a wrong diagnosis and is
RETRACTED — do not do it. Read `docs/decisions/20260909-T-the-roster-was-valid-but-not-viable.md`
first; it has the whole attribution and every caveat.

In one line: donors were matched on height and wood density and never on tree TYPE, so 31 % of the
stems written into twenty temperate cells were tropical, and the model killed them all in year one.
The synthesis was never at fault — the file held 6.7 % MORE biomass than the truth, not half.

**The artifact.** `/p/tmp/jamirp/vegemu/runs/synth-v2/restart/restart_1999_emulated.lpj`, 47.9 MB,
sha256 `64fdbf2d…`, cells 42480–42499, campaign `T-synth-v3`. ⚠ `synth-v3` is the REJECTED
five-trait variant — do not pick it up by mistake. Rebuild:
`scripts/sbatch_py.sh <tag> scripts/synth_restart.py --first-cell 42480 --ncell 20 --out-dir <dir>`.

**Numbers** (20 cells of 54,020, temperate Europe, present-day, seed 1 — NOT the acceptance test):

* **After one year of the real model**, median |emulated − control| / control: vegetation carbon
  **0.091**, biomass 0.092, stems per patch 0.088, median height 0.063 — all inside the band, from
  0.543 / 0.610 / 0.490 / 0.099. Carbon goes ×1.04 over the year vs the control's ×1.02, was ×0.35.
* **The conjunctive test still FAILS: 0 of 20 cells** inside the band on all 22 quantities at once,
  median 15 of 22 — a rate consistent with the emulator's own held-out 3.6 %, so inherited from the
  prediction rather than added by the synthesis.
* Sealed and unchanged: level map 0.0361 conjunctively (nearest analogue 0.0212; gate wanted a 0.050
  margin, got 0.0149); warming response −0.727 against 0.000 for predicting no change.

**Next, cheapest first:**

1. **Run t3 — 20 years, drift against the two-seed spread.** Worth doing now and it was not before:
   a state that collapsed in year one said nothing about year twenty. Same two-arm subset recipe as
   t2, `scripts/corpus_cmodel_config.py --years 2000 2019` then `scripts/sbatch_cmodel.sh`.
2. **Leaf area is 30 % low and does not move.** Leaf carbon is a per-stem MASS and the transplant
   matches traits, not masses. A cell-total mass constraint is a different mechanism, not built.
3. **Do NOT widen `MATCH_TRAITS`** — measured: 11 of 22 quantities degrade, median cell 15 → 12 hits.
   One donor is one real stem. `--match-traits` exists so the next attempt is a measurement.
4. **Do NOT tune the model to chase the map gate** — the pre-registration is sealed; a changed model
   is a new `exp_id`.
5. **The response model must predict the CHANGE directly**, blocked on D's pilot corpus; differencing
   two level predictions is the whole −0.727. `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
6. **T1, the GPU path: still not built, still not needed** — boosted trees on 16 CPU cores, 4 min.

**The merge is blocked, and not by this work.** CI on 2e2d57a: green on test, pathsafety, flags,
experiments; RED on lint (`ruff format`, four D files) and types (15 in `binfmt/clm.py`, 1 at
`corpus/state.py:159`, **none** in `src/vegemu/models`). Every failure is D-exclusive, so T cannot
clear them. **Do not merge with `--allow-red` without asking the owner.**

⚠ **LINE D HAS NOT BEEN TOLD — relay the Outbound block below by hand.** It could not be committed:
`commit-guard.sh` never passes `check_ownership.py --via-inbound`, the flag that exists to permit
the one sanctioned cross-line write; and its advertised escape hatch cannot open, because
`commit-guard.sh:22` reads `ALLOW_COMMIT_GUARD_SKIP` from the harness environment rather than the
command prefix — the same bug `slurm-guard.sh` already fixed and regression-tested. Both files are
integrator-owned, so **no line can currently send another line a message that survives a commit.**

Housekeeping: all five campaigns this session (`T-synth-v2/v3/v4`, `T-cmodel-t2b/t2c`) are harvested
with exit codes, artifact hashes and results; `tools/campaigns.py --check` green.

## Outbound to line D (2026-09-09) — line/T is blocked from merging by lint+types failures that are 100% in D-exclusive paths

Line T pushed 2e2d57a; both red gates are entirely in your paths, so T cannot clear them and tools/merge.sh refuses. TYPES: 16 errors in 2 files, both yours. src/vegemu/binfmt/clm.py, 15 of them, 'ClmHeader gets multiple values for keyword argument' at lines 150/153/164/174 -- the dataclass is being constructed with both a positional and a keyword form of the same field. And src/vegemu/corpus/state.py:159, 'Name out already defined on line 139' -- the empty-summary branch and the main branch both bind 'out', which is a no-redef under strict; annotate one or rename it. src/vegemu/models is clean, so this is the entire remaining types debt in the package. LINT: 'ruff format --check .' reports 4 files, all yours: scripts/corpus_cmodel_config.py, scripts/corpus_convergence.py, src/vegemu/binfmt/restart.py, src/vegemu/corpus/state.py. Same cause the integrator diagnosed for T's three -- hand-aligned continuation lines ruff format has never produced, i.e. it was simply never run on them. Fix is 'ruff format' on those four and nothing else; T has done its own three plus the no-any-return in models/synth.py. SEPARATELY, AND IT MAY MATTER TO YOU SINCE corpus/state.py IS YOURS: today's restart-synthesis work found that a stem's PFT id is climatically constrained -- LPJmL-FIT kills a tropical broadleaved evergreen with certainty in a temperate cell (mort_temp reaches 1.0 at 73 days below 12.5 C, tree/mortality_tree_ind.c), and a donor pool spanning biomes had put 31 % such stems into a temperate block, half the roster dying in one simulated year. corpus/state.py already computes pft_frac_* per cell but those columns are not in SCORED_CONJUNCTIVE, so the synthesiser must copy species composition from a template rather than predict it -- which is exactly what stops an emulated warmed-climate restart from shifting composition at all. Record: docs/decisions/20260909-T-the-roster-was-valid-but-not-viable.md.

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
