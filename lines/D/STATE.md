# Line D — data: binary formats, corpus generation, provenance

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: newest `journal/D/<YYYY-MM>*.md` (never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py D` when it fills.

## Scope

Everything that reads or writes LPJmL-FIT's own file formats, and the corpus that comes out of them:
the restart reader/writer, the `.clm` reader/writer, the output writers, corpus generation, the
perturbation design, the spin-up campaigns, provenance. Not line D's: models and training (T),
pre-registrations and verdicts (X).

## NEXT — start here

**As of 2026-09-23** — rotated by the integrator: all 15 message blocks triaged into
`journal/D/2026-09.md` with a disposition each. The integrator refreshes this block at session end.

🔄 **A FULL constant-CO₂ SECOND SEED of the pilot is RUNNING from `main` — do NOT relaunch or
touch it.** All 200 cells × 30 climates at seed 2, CO₂ 276.59 ppm (plan job 2280660, build job
2280661, then 24 spin-up manifests `D-pilot-v2s2-s00`…`s23`, 250 runs each), writing
`runs/pilot-v2-constco2-s2/` and `corpus/pilot-v2-constco2-s2/`. It gives every pilot row a
two-run truth and a band measured on the constant-CO₂ basis. Nothing from it is harvested yet;
judge each run by `^lpjml successfully terminated`, never by exit code.

✅ **Corpus `v2-constco2` is LANDED — do NOT relaunch it**: 6,000/6,000 spin-ups, `corpus.parquet`
6,000 × 181 (sha256 `9c117cb6c045fe90…`). Model inputs come from the 78-column
`state_pilot-v2-constco2.parquet`, never `corpus.parquet` (`MEMORY.md:never-cache-corpus-parquet`).
Pinning CO₂ cost 24 % of the forest (`MEMORY.md:constco2-costs-24pct`). The 20-cell v1 replicate
`pilot-v1-s2` (600/600) is done and its measurements are in `MEMORY.md`.

🔄 **Parallel integrator branches (`int/*`) are building the corpus-v3 schema, the truth builder,
features, the equilibrium model, synthesis, the global restart writer and new scoring.** None had
landed on `main` at `cf11a5c`. Read `git log origin/main` before starting any of these.

⚠ **T's two corpus asks are STILL in no built corpus** (checked in source on main, 2026-09-23):
(1) the four soil-type columns — `CLIMATE_FEATURES` still has only `soildepth` (the climate-only
equilibrium map reads texture itself: `scripts/exp_equilibrium_map.py:SOIL_FEATURES`); (2) NaN, not
0.0, in `pft_frac_*` for a treeless cell — `corpus/state.py:_empty_summary` still re-blanks only
the quantile and trait-mean columns, so `score.blank_treeless_composition` stays load-bearing.
Both change what a decode produces, so they go into a NEW corpus version (v3 is the natural
place), never into v2 in place. Full asks: the 2026-09-23 rotation in `journal/D/2026-09.md`.

⚠ **Do NOT shorten any spin-up on the strength of "it converged"** — a shorter run is a different
state, and which state is the target is an owner question (`20260915-D-the-spinup-did-converge-*`).

**Still owed by this line:** one cell, one year, two binaries, byte-compared — the only unproven
rung-5 claim, and nothing blocks it: `scripts/sbatch_cmodel.sh` takes
`LPJ_BINARY_KEY=lpjml.binary_pristine`. Compare the RESTART bytes, never two NetCDF outputs
(`MEMORY.md:netcdf-cmp`); hold restart, config, year and seed identical so only the binary differs.

**Standing:** `--subset` is a STRIDE, not a prefix (the cell list runs south to north). The 17 empty
controls are not a reason to re-select cells (`20260909-D-corpus-v1-decoded.md`).

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
* **A script loaded by path must be registered in `sys.modules` before `exec_module`**, or
  `@dataclass` raises an `AttributeError` inside `dataclasses.py` that reads as a broken standard
  library. Three loaders had the bug; the why is in `corpus_pilot.py:_load`.
* **A subset `.clm` declares its cell in `firstcell`; indexing a GLOBAL file by row is silent.**
  Global inputs have `firstcell = 0`, so row and cell coincide until a single-cell file arrives —
  then every row gets cell 0's soil depth and cell 0's coordinate, with nothing raised.
* **The test suite needs the package importable**: CI does `pip install -e ".[dev]"`, so locally use
  `PYTHONPATH=src pytest -q -m "not needs_real_data"`. A bare `pytest` fails collection with
  `ModuleNotFoundError: vegemu`, which reads as a broken tree rather than a missing install.
* **The execution traps that were here are now `docs/reference/cluster.md` §"Five more of the same
  kind"** (exit codes, `srun` stdin, the polars `fork` hang, campaign-vs-corpus, and the
  `ALLOW_LOGIN_HEAVY` test trap) — they bite every line, so they stopped being line-D state. Two
  more live in the reference docs: CI polling in `cluster.md`, `WARNING032` in `binfmt.md`. Do not
  re-derive any of them here.
