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

✅ **The three-session carbon blocker is CLOSED, and it closed in the opposite direction from its
name.** Re-emitted the restart from `main`'s committed synthesiser at `5cc59c0` and ran year 2000
over the 20-cell block: block vegetation carbon is **112,763 vs 100,691 gC, i.e. 12.0 % HIGH** —
not halved, not low. The model sheds the excess over ~4 years and reaches **−1.6 % by 2019**,
inside the two-seed band (0.102). The re-emitted file is **byte-identical** to the one line T's
20-year `t5` arm was scored on (`1e856119…`), which independently confirms T's "verified inert"
claim and makes `t5`'s numbers citable against a versioned synthesiser — they were not yesterday.
Record: `20260910-D-the-halved-carbon-is-gone-verified-from-the-committed-synthesiser.md`.
⚠ Say the sign right: T measured the FILE 6.7 % high, the model takes it to 12.0 % high at year
end. "Halved carbon" describes only rosters the model REJECTED, and that roster is gone.

✅ **Item 2 of the last handoff was answered by line T, not by me — do not re-run it.** The model
never recomputes `D95max`: every write is at tree birth, and `allocation_tree.c` writes `D95`, a
different field. Imposition works, makes fidelity WORSE than the donor accident, and **ships
switched off** (`IMPOSED_TRAITS = ()`). Record: `20260909-T-imposing-rooting-depth-works-…`.

✅ **The C-model submission wrapper — all three defects fixed, each verified by running it.**
It now **pins and loads its own module set** for the job AND for the `--check` pre-flight, so a
run no longer depends on who submitted it; it `ldd`-checks the binary before spending the
allocation. ⚠ **The skill's claim that the pre-flight "needs no modules" was WRONG** — `lpjcheck`
links the same libraries, so `--check` died with the same `libnetcdf.so.19` message, in the one
command meant to tell you the config is fine. Measured and corrected. And the wrapper **no longer
echoes the completion phrase** into the log, so the unanchored `grep -c 'successfully terminated'`
that returned 1 on a dead job cannot match a decoy; every harvest command it writes is anchored
`^lpjml successfully terminated`. Proven by submitting from a shell with NO modules: pre-flight
passed, the job ran 20/20 cells in 9 s, and the phrase now appears exactly once — on the model's
own line.

**Next, in order:**

1. **Corpus v2 is still blocked on TWO decisions, neither of them D's. Ask, do not assume.**
   - **Integrator:** `config/paths.yaml` needs a `ssp370_seed2_from_hist_seed2` key. The genuine
     second run is on disk and verified — different size (133,580,962,759 vs 133,559,375,490),
     written 2026-08-03 — but it came from the Jul-21 build, not Feb-05, so the corrected pair
     straddles a build boundary and that must be disclosed.
   - **Line X:** does v2 also put `pft_frac_*` in `SCORED_CONJUNCTIVE`? Those columns are computed
     but not scored, so the synthesiser must COPY species composition from a template — which is
     exactly what stops an emulated warmed restart shifting composition at all.
   - ⚠ **ONE rebuild or the other, never two** — each is a new corpus version and a changed corpus
     is a changed question. v0/v1 hashes are untouched either way.
   - **Inbound budgets, re-measured today:** D **100**/120, T **115**/120, X **117**/120. D is
     reachable again (it was at 120 and blocked, which is why T's wrapper defects arrived via the
     changelog rather than the inbound channel). Always `wc -l lines/<to>/STATE.md` first.
2. **`tools/rotate_state.py D` is due** — this file was at 100 of 120 before this block landed.
3. **The 17 empty controls are NOT a reason to re-select cells** — 14 are the model being right,
   and dropping them narrows the envelope the design spans. Detail, plus the both-bases warning
   line X needs before sealing rung 1: `20260909-D-corpus-v1-decoded.md`.
4. **Nothing of D's is in flight.** Both of today's campaigns are harvested and
   `campaigns.py --check` is green.

⚠ **Still true from yesterday, and it cost a near-miss:** re-`fetch` immediately before diagnosing
any gate failure in another line's files, and compare worktrees on disk (`diff -rq`), not just
`git diff`, which answers against whatever ref you last fetched. Only a cache-free
`mypy --strict --cache-dir=/dev/null` proves a red gate real.

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
