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

**The corpus builder now REFUSES a leg whose two seeds are one run twice** (2d5eaf4). It compares
the recorded RNG triple (the cause) and the decoded rows (the effect); a failure WITHHOLDS
`corpus_sha256`, so a defective corpus cannot be cited by a pre-registration at all. Replayed on
real v0: historical 63,372 and ssp126 63,586 of 67,420 cells differ (pass), **ssp370 differs in 0
and is refused on both signals**. Discharges consequence 2 of `20260908-X-ssp370-has-no-second-seed`.

**`tools/inbound.py` is HALF fixed** (5667030, record `20260909-D-inbound-recognised-from-the-diff`).
Ownership no longer needs the flag nothing ever passed — the write is recognised from the staged
diff (nothing removed, every added heading an `## INBOUND from line <you>`, tool sentinel present),
which is narrower than the flag and needs no hook change. ⚠ **The budget half still blocks it and is
integrator-owned**: `lines/X/STATE.md` is at **exactly 120/120**, so a message of ANY length reddens
`budgets` and stops EVERY line's merge. A real send was verified through ownership, then reverted
unsent. **Check `wc -l lines/<to>/STATE.md` before writing to anyone.**

🚫 **PUSHED (5667030) BUT NOT MERGED — same blocker as last session, unchanged.**
`/p/projects/open/Jamir/vegemu` still has the SAME 4 staged files (both `.claude/hooks/` guards,
`tests/test_session_end_gate.py`, `changelog.d/INT-stop-gate-sigpipe.md`), untouched since 11:59 on
2026-09-09. `git merge --no-ff` refuses on a dirty index, so `main` is not at risk. **Do not stash —
that is another session's work.** Poll `git -C /p/projects/open/Jamir/vegemu status --porcelain`;
when empty, `tools/merge.sh D --allow-red` (owner-approved 2026-09-09).
Gates on 5667030: `budgets`/`pathsafety`/`test` green, `lint` red **only** in the three line-T files
(`models/synth.py`, `models/__init__.py`, `scripts/train_emulator.py` need `ruff format`) — verified
none of them mine; `ruff check .` is clean. `types` last ran on 1368569 (red: `synth.py:143`).
⚠ **`tools/expected_gates.py` over-predicted here**: it named `types` and `flags`, which never ran,
because it diffs the whole branch against main while the workflows filter on the PUSH diff — and my
two commits touch no `src/vegemu`. `wait_gates` would have hung had `lint` not failed first.

**Next, in order:**

1. **Corpus v2 is blocked on TWO decisions, neither of them D's.** Ask, do not assume.
   - **Integrator:** `config/paths.yaml` needs a `ssp370_seed2_from_hist_seed2` key. The genuine
     second run is on disk and verified today — different file size (133,580,962,759 vs
     133,559,375,490), written 2026-08-03 — but it came from the Jul-21 build, not Feb-05, so the
     corrected pair straddles a build boundary and that must be disclosed.
   - **Line X:** does v2 also put `pft_frac_*` in `SCORED_CONJUNCTIVE`? Because those columns are
     computed but not scored, the synthesiser must COPY species composition from a template, which
     is exactly what stops an emulated warmed restart shifting composition at all. It changes what
     "all 22 quantities" means for every sealed pre-registration citing it.
   - ⚠ **ONE rebuild or the other, never two** — each is a new corpus version and a changed corpus
     is a changed question. v0/v1 hashes are untouched either way. The map entry in
     `corpus_build.py` carries the full warning at the point of use.
2. **The emitted restart carries about half the right carbon** — donors matched on height and wood
   density, not mass. Line T's fix; line D owns the verification run, and 20 cells for a year is 8 s.
3. **The 17 empty controls are NOT a reason to re-select cells.** 14 are the model being right, and
   dropping them would quietly narrow the envelope the design set out to span. Full detail, and the
   both-bases warning line X needs before sealing rung 1: `20260909-D-corpus-v1-decoded.md`.

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
