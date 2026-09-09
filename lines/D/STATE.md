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

**D2 IS DONE. The pilot corpus is a TABLE and rung 1 is unblocked.**
`/p/tmp/jamirp/vegemu/corpus/pilot-v1/corpus.parquet` — **6,000 rows × 181 cols**, 0 failures, 8.9 s
on 16 procs: 86 climate features from each run's OWN perturbed forcing + the 5 design coefficients +
fold keys + 76 state targets. `truth_stems_total` is a LAGGED TRUTH, diagnostic only, never a
feature. `corpus_sha256 fbe74ed2416b265f4c874959ab8b186679a641cedf3e18df32b125f7362e1e4d`; driver
`corpus_pilot.py --stage decode`, `decode.json` beside it; no open campaigns in the ledger.

**The corpus was validated against the global truth, which nothing guaranteed** — all 6,000 are
single-cell subset runs and `MEMORY.md:subset-diverges` forbids scoring one against global truth.
Over the 183 controls that grew a forest: Spearman **0.961**, ratio median **1.023**, p10/p90
**0.839/1.231**; and all 200 controls' annual tas/pr/rsds reproduce the source to **max abs diff 0**.

⚠ **17 of the 200 control points grew NOTHING, and line X needs this before sealing rung 1.** 14 are
real deserts (12 dry months, aridity 0.0001–0.014, soil carbon exactly 0; the driest cells that DID
grow trees sit at 0.010–0.021, so the flip is sharp) — the model is right, and they are `maximin`
picks doing what design rule 4 asked. 3 are cold/wet bistable cells with real soil carbon; cell 98
is a forest under 22 of its other 29 climates. **The same-cell baseline null is evaluated at the
control point**, so at 8.5 % of cells the decisive null predicts bare ground and anything predicting
"some forest" beats it by the full target range — report BOTH bases, all 200 and the 183. Treeless
overall is 380/6,000 (6.3 %), peaking at 34/200 on `lhs03` (−0.73 K, 0.67× precip): DRYING empties
cells, not warming. All of it: **`docs/decisions/20260909-D-corpus-v1-decoded.md`**.

⚠ **`tools/inbound.py` is still unusable both ways, so that record IS the message to X.** It cannot
commit (`commit-guard.sh:36` omits `--via-inbound`), and a recipient at its 120-line budget reddens
`budgets`, which stops EVERY line's merge.

🚫 **PUSHED (1368569) BUT NOT MERGED — the blocker is not line D's.** `budgets`/`test`/`pathsafety`/
`flags` green; `lint` and `types` RED, every failure in a line-T exclusive file: `mypy --strict` finds
**1 error in 16 files** (`models/synth.py:143`, `Returning Any`) and `ruff format` would rewrite
`models/synth.py`, `models/__init__.py`, `scripts/train_emulator.py`. **Both were already red on
`main` before this branch existed**, so merging adds no failure — but `merge.sh` refuses a red gate
and says hand it to the owner, not merge around it, and `inbound.py` cannot. Override:
`tools/merge.sh D --allow-red '<why>'`, written into the merge commit; an owner call. Until it lands
the table is invisible to X and T on `main`, which is the rung-1 critical path.

**Next, in order:**

1. **Corpus v2 — do BOTH corpus changes in one rebuild, after a word with line X.** (a) The
   high-emissions leg's second seed is not a second run: `state_ssp370_seed1`/`_seed2` in **v0** are
   byte-identical across all 22 quantities and all 67,420 cells, because the second run started
   from the first's initial state, so any tolerance from that leg collapses to the bare 10 % floor
   while still looking like "10 % or the model's own spread". The genuine second run **is** on disk.
   (b) Put `pft_frac_*` in `SCORED_CONJUNCTIVE`: a stem's PFT id is climatically constrained
   (`mort_temp` hits 1.0 after 73 days below 12.5 °C, `tree/mortality_tree_ind.c`), and because
   those columns are computed but not scored, the synthesiser must COPY species composition from a
   template — which is exactly what stops an emulated warmed restart shifting composition at all.
   ⚠ Both change what a SEALED pre-registration's "all 22 quantities" means, so both need a new
   corpus version, and neither touches v0/v1 hashes — a changed corpus is a changed question.
   Records: `20260908-X-ssp370-has-no-second-seed.md`,
   `20260909-T-the-roster-was-valid-but-not-viable.md`, `20260909-T-t3-drift-fails-below-the-null.md`.
2. **The emitted restart carries about half the right carbon** — donors matched on height and wood
   density, not mass. Line T's fix; line D owns the verification run, and 20 cells for a year is 8 s.
3. **The 17 empty controls are NOT a reason to re-select cells.** 14 are the model being right, and
   dropping them would quietly narrow the envelope the design set out to span.

## Milestones

**D2 — the pilot corpus. DONE, runs and table both.** `vegemu.corpus.select` and
`scripts/corpus_pilot.py --stage plan|build|verify|harvest|decode`; `tests/test_select.py` is 16
tests including "every populated tile gets a cell". Records: `20260909-D-pilot-corpus-v1.md` (the
6,000 spin-ups, 337 core-hours), `20260909-D-corpus-v1-decoded.md` (the table and its validation).

**D3 — provenance. PARTLY DONE.** Every corpus table ships a `provenance.json` with each source
file's size, mtime and decoded header, plus the hash a pre-registration cites.

## Line D gotchas

* **A byte-identical round-trip validates a LAYOUT, not a CROSS-REFERENCE.** The last byte of a PFT
  entry indexes that patch's litter list; it is self-consistent inside any one record, so a
  round-trip cannot see it, and it breaks only when a stem moves between patches. Only running the
  real model found it. Any field indexing into another part of the same record needs its own check.
* **Never judge a C run by its exit code**; require the model's own line `lpjml successfully
  terminated, <n> grid cells processed.` in a non-empty log. The wrapper writes that grep into the
  ledger row as the harvest command.
* The `.clm` size check the C only warns about (`WARNING032`) is a hard refusal here: a size
  mismatch means the dtype or the year count is wrong and every value read is silently shifted.
* **`srun` forwards its stdin to the task**, and inside `while read … done < manifest` that stdin IS
  the manifest. It swallowed 18 of 25 lines, the job exited 0, and the log said "7 of 7" because the
  counter came from the same starved loop. Redirect the member from `/dev/null`; count off the file.
* **A script loaded by path must be registered in `sys.modules` before `exec_module`**, or
  `@dataclass` raises an `AttributeError` inside `dataclasses.py` that reads as a broken standard
  library. Three loaders had the bug; the why is in `corpus_pilot.py:_load`.
* **A complete campaign is not a usable corpus.** Judge the spin-ups by the model's own completion
  line, then judge the CORPUS separately: restart byte size is a free proxy (≈360 KB with no
  vegetation, ≈1.9 MB with a forest) and a run's cost tracks it — 1 min treeless, 3–8 min forested.
  It was a good one: 374/6,000 treeless by bytes against 380/6,000 by decoded stem count.
* **polars does not survive `fork`: a forked worker that touches a DataFrame hangs forever** with no
  error and no traceback, so the job burns its wall-clock limit with an empty log — which reads as a
  slow filesystem. Workers return plain dicts, the parent builds the frame. `corpus.climate` splits
  `climate_columns` (numpy, fork-safe) from `climate_table` (parent only); `corpus.state` always did.
* **A subset `.clm` declares its cell in `firstcell`; indexing a GLOBAL file by row is silent.**
  Global inputs have `firstcell = 0`, so row and cell coincide until a single-cell file arrives —
  then every row gets cell 0's soil depth and cell 0's coordinate, with nothing raised.
* **Do not export `ALLOW_LOGIN_HEAVY` before running the test suite.** The guard allows
  unconditionally when it, `ALLOW_RAW_SBATCH` or `SLURM_JOB_ID` is set, and it inherits the
  session's environment, so every must-deny case in `tests/test_slurm_guard.py` went red at once —
  which reads as "the guard is broken". The test now strips all three; the trap is the general one.
