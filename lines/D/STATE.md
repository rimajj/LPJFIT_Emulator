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

**Nothing of D's is in flight** — the 2026-09-10 campaigns are harvested and `tools/campaigns.py
--check` is green. The three-session carbon blocker is **closed**, in the opposite direction from
its name: the emulated restart starts **high**, not halved, and converges into the two-seed band.
Say the sign right — T measured the FILE 6.7 % high, the model takes it to **12.0 % high** at the
end of year one (112,763 vs 100,691 gC), then sheds it to −1.6 % by 2019, inside the two-seed band
(0.102). "Halved carbon" describes only rosters the model REJECTED. Narrative is in the journal;
record: `20260910-D-the-halved-carbon-is-gone-verified-from-the-committed-synthesiser.md`.
⚠ **`MEMORY.md` is integrator-only (O04), so a line CANNOT promote a fact into it** — four rows are
requested in `changelog.d/D-ssp370-second-seed-provenance.md`, including a correction to
`restart-loads`, whose "0.53 off" is a roster the model later rejected. Keep the sign here until
they land.

**Next, in order:**

1. **Corpus v2 is blocked on TWO decisions, neither of them D's. BOTH ASKED 2026-09-10 via a
   changelog fragment (`changelog.d/D-ssp370-second-seed-provenance.md`) — awaiting answers.**
   D's half is now verified and recorded; do not re-measure it.
   - **Integrator:** the configured `ground_truth.ssp370_seed2` is a **byte-clone of seed 1**
     (both `restart_2100.lpj` exactly 133,559,375,490 B; the directory carries its own
     `INVALID_NOT_A_SECOND_SEED.md`). The genuine run is on disk at `…_from_hist_seed2`
     (133,580,962,759 B) and **completed** — anchored terminate line, all 67,420 cells. It needs a
     **NEW** `ssp370_seed2_from_hist_seed2` key: repointing the existing key in place would
     silently change what three sealed pre-registrations cite. It ran on the **Jul-21** build, not
     Feb-05, so the corrected pair straddles a build boundary that must be disclosed — and
     `paths.yaml`'s own comment does not mention that build at all.
   - **Line X:** does v2 also put `pft_frac_*` in `SCORED_CONJUNCTIVE`? Those columns are computed
     but not scored, so the synthesiser must COPY species composition from a template — which is
     exactly what stops an emulated warmed restart shifting composition at all.
   - ⚠ **ONE rebuild or the other, never two** — each is a new corpus version and a changed corpus
     is a changed question. v0/v1 hashes are untouched either way.
   - ⚠ **Nothing is silently wrong meanwhile:** `check_seeds_differ` fails the build on an
     identical RNG triple, and its six tests pass. Record:
     `20260910-D-the-ssp370-second-seed-exists-and-the-configured-path-is-its-clone.md`.
   - **Always `wc -l lines/<to>/STATE.md` before writing** — X was at 117/120, which is why both
     asks went via the changelog; an inbound block would have blocked X's own commits.
2. **The 17 empty controls are NOT a reason to re-select cells** — 14 are the model being right,
   and dropping them narrows the envelope the design spans. Detail, plus the both-bases warning
   line X needs before sealing rung 1: `20260909-D-corpus-v1-decoded.md`.

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
