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

✅ **MERGED. The three-session blocker is gone.** `line/D` is on `main` at `6bcb2ca`, and `main` is
green on all eight gates that push triggered. **No `--allow-red` was needed** — do not carry the
2026-09-09 override forward, the condition it was approved for no longer exists. The integration
worktree's four staged files were committed by the integrator, and the Stop-gate SIGPIPE fix landed
(`0e6fc9f`), so both of last session's blockers are retired. Nothing of line D's is in flight:
`campaigns.py --check` is green, and the `W-lpjml-*` jobs in `squeue` are another project's
(`WorkDir=…/clustering/wt-paper2`), not this one's.

⚠ **`main` MOVED UNDER ME MID-SESSION, and it fabricated a convincing false problem.** After a clean
rebase, `mypy --strict` was red at `models/synth.py:143` and `models/emulator.py:192` — both
T-owned, both byte-identical to my `origin/main` — so it read exactly like the recorded "repo-wide
gate red on another line's files" case, whose remedy is to fix it centrally as integrator. **That
remedy would have been wrong and would have hand-edited another line's source.** Line T merged
(`f133867`) *while I worked*: their own fixes were already on the real `main` and my base had gone
stale between my `pull` and my `diff`. **The tell:** the integration worktree reported clean at
`origin/main` yet its `synth.py` differed from mine on disk. **So: re-`fetch` immediately before
diagnosing any gate failure in another line's files, and compare worktrees on disk (`diff -rq`), not
just `git diff`, which answers against whatever ref you last fetched.** Only a cache-free
`mypy --strict --cache-dir=/dev/null` proves a red gate real — the warm cache reinforced the error.

**Next, in order:**

1. **The halved carbon is line T's FIX, now on `main` — but D's verification run is still owed and
   must NOT be run against `synth-v6`.** T's diagnosis: tree type was a free field, so 31 % of stems
   in a temperate block were tropical evergreen, which the model killed inside year one
   (`mort_temp` in `tree/mortality_tree_ind.c`). Type is now COPIED from the target cell's own
   template roster and `inadmissible_placed` must be zero. At FILE level T measures above-ground
   biomass **4,030 vs 3,777 gC/m², 6.7 % HIGH, not halved** — the loss happened *during the run*, to
   a roster the model rejected. ⚠ `/p/tmp/jamirp/vegemu/runs/synth-v6` (written 08:57 today,
   `inadmissible_stems_total: 0`) came from line T's **uncommitted** `synth.py` and carries an
   in-flight rooting-depth imposition (`imposed: {D95max: template}`, `imposed_clamped: 9`). A number
   measured against it would cite an unversioned synthesiser and be superseded within the hour.
   **Re-emit from `main`'s committed synthesiser, then run the year** (20 cells, 1 yr ≈ 8 s, via
   `scripts/sbatch_cmodel.sh`).
2. **The rooting-depth question T flagged is a MODEL-RUN question, so it is D's.** T imposes `D95max`
   as a stored per-tree field (`binfmt/restart.py:358`, offset 337) but the model derives it from
   height. **Does the model recompute it at the first allocation and overwrite the imposed value?**
   T calls that "the whole risk" and it cannot be answered from the file — only by loading it.
3. **Corpus v2 is still blocked on TWO decisions, neither of them D's. Ask, do not assume.**
   - **Integrator:** `config/paths.yaml` needs a `ssp370_seed2_from_hist_seed2` key. The genuine
     second run is on disk and verified — different size (133,580,962,759 vs 133,559,375,490),
     written 2026-08-03 — but it came from the Jul-21 build, not Feb-05, so the corrected pair
     straddles a build boundary and that must be disclosed.
   - **Line X:** does v2 also put `pft_frac_*` in `SCORED_CONJUNCTIVE`? Those columns are computed
     but not scored, so the synthesiser must COPY species composition from a template — which is
     exactly what stops an emulated warmed restart shifting composition at all.
   - ⚠ **ONE rebuild or the other, never two** — each is a new corpus version and a changed corpus
     is a changed question. v0/v1 hashes are untouched either way.
   - **Inbound budget, re-checked today:** `lines/X/STATE.md` is **117/120** (3 lines of headroom —
     tight, verify the block fits before sending), `lines/T/STATE.md` is **120/120, still blocked**.
     Always `wc -l lines/<to>/STATE.md` first; over budget reddens `budgets` and stops EVERY merge.
4. **The 17 empty controls are NOT a reason to re-select cells** — 14 are the model being right, and
   dropping them narrows the envelope the design spans. Detail, plus the both-bases warning line X
   needs before sealing rung 1: `20260909-D-corpus-v1-decoded.md`.

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
