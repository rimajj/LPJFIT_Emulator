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

**D2's SPIN-UPS ARE DONE. The pilot corpus exists as 6,000 real restart files.** 200 cells × 30
climates × 1 seed, corpus version **v1**, `plan_sha256 bad787ade3fc609b25cf8ebc87dfd0978e4a8690`.
All 6,000 printed the model's own completion line and all 6,000 wrote a restart — no reruns owed,
and `campaigns/D/ledger.jsonl` has **no open campaigns** for the first time on this line.

| | measured |
|---|---|
| cost | **337 core-hours**, 3.37 core-minutes per 1000-year spin-up (estimate was 670) |
| wall | 24 shards of 250, all 23 later ones concurrent on 5,750 CPU; ~8 min each |
| forcing | 1.5 GB, every file exactly 43,851 B |
| restarts | 12 GB; bytes p5/p50/p95 = 360,275 / 2,179,450 / 2,809,564 |
| treeless | **374 of 6,000 (6.2 %)** at or below the vegetation-free floor |
| tiles | all **164** populated 15° tiles covered; 5 forced biome + 159 medoids + 36 maximin |

Everything about it, including the message line X needs:
**`docs/decisions/20260909-D-pilot-corpus-v1.md`**. Driver: `scripts/corpus_pilot.py --stage
plan|build|verify|harvest`. Tables in `/p/tmp/jamirp/vegemu/corpus/pilot-v1`; runs under
`.../runs/pilot-v1/c<cell>/<point>`.

⚠ **`tools/inbound.py` is unusable both ways, so that message went via the record above.** It cannot
commit (`commit-guard.sh:36` omits `--via-inbound`; line T hand-carried theirs), and a recipient at
its 120-line budget — X was, D is now — reddens `budgets`, which stops EVERY line's merge.

**Next, in order:**

1. **D2b — DECODE the 6,000 restarts into the corpus table. The only thing between the corpus and
   rung 1, and nothing blocks it.** The decoder is the one corpus v0 used:
   `vegemu.corpus.state.summarise_cell` over `RestartReader`; v0 did 67,420 records with
   `--nproc 64`, so 6,000 of ~2.2 MB is smaller. Join on `runs.csv` (name, cell, point) and carry
   `design.csv`'s five coefficients into each row, or the climate a row belongs to is not
   recoverable from the row. ⚠ **A single-cell restart holds ONE record, not a slice of the global
   file** — v0's reader was aimed at a 119 GiB file of 67,420; check the count before trusting an
   index.
2. **The high-emissions leg's second seed is not a second run, and the corpus rebuild is line D's.**
   `state_ssp370_seed1` and `_seed2` in corpus **v0** are byte-identical across all 22 quantities
   and all 67,420 cells: the second run was started from the first's initial state. So any
   tolerance derived from that leg collapses to the bare 10 % floor while still looking like
   "10 % or the model's own spread". The genuine second run **is** on disk. Rebuild under a new
   corpus version — a changed corpus is a changed question, so it does not touch v0's hashes or the
   verdicts that cite them. Record: `docs/decisions/20260908-X-ssp370-has-no-second-seed.md`.
3. **The emitted restart carries about half the right carbon** — donors matched on height and wood
   density, not mass. Line T's fix; line D owns the verification run, and 20 cells for a year is 8 s.
4. **Line T's ask, and it is line D's because `corpus/state.py` is: put `pft_frac_*` in the scored
   set.** A stem's PFT id is climatically constrained — LPJmL-FIT kills a tropical broadleaved
   evergreen with certainty in a temperate cell (`mort_temp` reaches 1.0 after 73 days below
   12.5 °C, `tree/mortality_tree_ind.c`), which is what halved a synthesised roster's carbon in one
   simulated year. `state.py` already computes `pft_frac_*` per cell, but those columns are not in
   `SCORED_CONJUNCTIVE`, so the synthesiser must COPY species composition from a template instead of
   predicting it — and that is precisely what stops an emulated warmed-climate restart from
   shifting composition at all. ⚠ **Do not just add them.** The scored set fixes the quantity count
   that line X's SEALED pre-registrations cite ("all 22 quantities"), so widening it changes what
   those seals mean and needs a new corpus version and a word with line X — a changed corpus is a
   changed question. Records: `docs/decisions/20260909-T-the-roster-was-valid-but-not-viable.md`,
   `20260909-T-t3-drift-fails-below-the-null.md`.

## Milestones

**D0 — restart-file round-trip. DONE**, and the `.clm` reader/writer with it. The per-stem field map
is cross-checked against a number this repo did not produce: `height` puts 51.4 % of Hainich's stems
above the 5 m cut, against ~47 % measured independently in the predecessor.

**D0b — the C-model launch path. DONE.** `scripts/sbatch_cmodel.sh` (pre-flight, run, `--manifest`
task farm), `corpus_cmodel_config.py`, `corpus_restart_subset.py` (byte-exact control arm). A
20-cell one-year run from the real restart takes 8 s and prints the model's own completion line.

**D1 — the perturbed `.clm` writer. DONE.** `src/vegemu/corpus/perturb.py`,
`scripts/corpus_perturb_clm.py`, `corpus_spinup_config.py`, `corpus_d1_{forcing,direction}.py`;
`tests/test_perturb.py` is 40 tests including the byte identity.
Record: `docs/decisions/20260908-D-perturbation-design.md`.

**D2 — the pilot corpus. SPIN-UPS DONE, TABLE PENDING.** See NEXT. `vegemu.corpus.select` and
`scripts/corpus_pilot.py`; `tests/test_select.py` is 16 tests including "every populated tile gets a
cell". ⚠ It is 6,000 restart FILES, not a table — D2b is the decode.

**D3 — provenance. PARTLY DONE.** Every corpus table ships a `provenance.json` with each source
file's size, mtime and decoded header, plus the hash a pre-registration cites.

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
* **`srun` forwards its stdin to the task**, and inside `while read … done < manifest` that stdin
  IS the manifest. It swallowed 18 of 25 lines: seven members ran, eighteen never started, the job
  exited 0 and the log said "7 of 7" because the counter came from the same starved loop. Redirect
  the member from `/dev/null`, and take the expected count straight off the file.
* **A script loaded by path must be registered in `sys.modules` before `exec_module`.** Every module
  here opens with `from __future__ import annotations`, so annotations are strings and `@dataclass`
  resolves them through `sys.modules[cls.__module__]` — `None` for an unregistered module. It raises
  an `AttributeError` inside `dataclasses.py` the moment the loaded script merely *defines* a
  dataclass, so it reads as a broken standard library. Three loaders had the bug.
* **A complete campaign is not a usable corpus.** Judge the spin-ups by the model's own completion
  line, then judge the CORPUS separately: restart byte size is a free proxy (≈360 KB with no
  vegetation, ≈1.9 MB with a forest), and a run's cost tracks it — 1 min treeless, 3–8 min forested.
* **Do not export `ALLOW_LOGIN_HEAVY` before running the test suite.** The guard allows
  unconditionally when it, `ALLOW_RAW_SBATCH` or `SLURM_JOB_ID` is set, and it inherits the
  session's environment, so every must-deny case in `tests/test_slurm_guard.py` went red at once —
  which reads as "the guard is broken". The test now strips all three; the trap is the general one.
