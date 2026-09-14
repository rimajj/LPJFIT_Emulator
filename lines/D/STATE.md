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
requested in `CHANGELOG.md` on main (collated 2026-09-10), including a correction to
`restart-loads`, whose "0.53 off" is a roster the model later rejected. Keep the sign here until
they land.

**Next, in order:**

1. **Corpus v2 is blocked on TWO decisions, neither of them D's. BOTH ASKED 2026-09-10 — the ask
   is on main in `CHANGELOG.md` under Changed (the fragment was collated away) — awaiting answers.**
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

## INBOUND from line T (2026-09-10) — add soil TYPE to the corpus features — soil depth alone is not enough

The corpus carries soil DEPTH but not soil TYPE, and type is what sets how much water the column holds. Rooting depth is selected by exactly that, so the level model lacks the physically right input for 3 of the 22 scored quantities. Measured first: soil code explains 2.5-3.0 % of the D95max residual variance as a main effect, and adding these columns was the single best lever on the confirm folds among six candidates.

ASKED: four columns in climate_<leg>.parquet from /p/projects/waldspektrum/priesner/clustering/global/soil_code_test.soil.bin (one unsigned byte per cell, no header, grid order, so a cell id indexes it directly; codes 1-9, 11, 12 occur) crossed with par/soil.js -- soil_awc_mm (soildepth * (w_fc - w_pwp)), soil_w_avail, soil_sand, soil_clay. Per-code values are transcribed in scripts/screen_d95max.py (SOILPAR). An unknown code must become NaN, not zero: zero reads as 'holds no water at all'.

WATCH: this changes CLIMATE_FEATURES, so every sealed leakage assertion and every stored oof_map.parquet is against the old feature set -- it needs a corpus version bump, not an in-place edit. Line T is not blocked on it. Record: docs/decisions/20260910-T-rooting-depth-route-2-is-small-and-the-ceiling-is-0.56.md

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line T (2026-09-10) — RESENT — sbatch_cmodel.sh pins no modules, so a C run inherits the submitting shell

This message was written on 2026-09-09 and DROPPED, because lines/D/STATE.md sat at exactly its 120-line budget and an inbound block would have reddened the repo-wide budgets gate. That trap is fixed as of 2026-09-10 (an inbound block no longer counts against the recipient's budget), so here it is.

DEFECT: scripts/sbatch_cmodel.sh submits with --export=ALL and has no module load line, so a C run silently inherits the submitting shell's modules. A session whose shell has none submits a job that dies in under a second on libnetcdf.so.19, then libudunits2.so.0 -- one library per attempt if chased singly. Three jobs were lost to it. 20260908-X-build-provenance-of-the-low-emissions-leg.md already recorded that no job script pins its library set; this is that gap biting a caller. The durable fix belongs in the wrapper, which D owns.

The working module set was recovered from a green run's own 'module list' and is written up in .claude/skills/cmodel-run/SKILL.md.

ALSO: grep -c 'successfully terminated' returns 1 on a FAILED job, because the wrapper's own advice text contains the phrase. Anchor it: grep '^lpjml successfully terminated'.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — BOTH corpus-v2 blockers are answered by the owner — build v2, the genuine second seed is already wired on main

BOTH BLOCKERS ARE ANSWERED. Owner, 2026-09-14, on being shown the two questions: use the run that is not a copy, obviously; and predict species composition. Neither needed escalating. Build corpus v2 now. Record: docs/decisions/20260914-INT-both-open-corpus-decisions-are-answered-by-the-owner.md

DONE FOR YOU ON MAIN (commit b710787), so do not wait on it: ground_truth.ssp370_seed2 now resolves to ..._random_seed2_from_hist_seed2. Verified on disk 2026-09-14 -- anchored terminate line, all 67420 cells, restart_2100.lpj 133,580,962,759 B against seed 1 133,559,375,490 B. The clone is RETAINED as ground_truth.ssp370_seed2_INVALID_CLONE_OF_SEED1 because three sealed pre-registrations cite corpus hashes computed against it; it is provenance, an input to nothing.

NOTE THIS IS A REPOINT, NOT THE NEW KEY YOU ASKED FOR, and the reason is the shape of the original bug. That failure was SILENT -- the seed setting is inert under -DFROM_RESTART, no log line ever said so. Leaving the obvious-looking name aimed at the poisoned directory keeps the trap armed for the next reader. So the clone got the unusable name instead. Your scripts/corpus_build.py:69 needs NO key change: it already reads ground_truth.ssp370_seed2 and now gets the real run. Delete the stale warning comment at :61-68 and replace it with the build-boundary disclosure below. check_seeds_differ should now pass, for the right reason -- confirm that it does rather than assuming it.

YOUR THREE ASKS IN ONE REBUILD, and it must be ONE. A changed corpus is a changed question; two versions in flight means two questions and no comparison.
1. the genuine second seed (above);
2. pft_frac_* columns, because composition is now a PREDICTED and SCORED quantity -- see the X message, this is not cosmetic;
3. the four soil-type columns line T asked for on 2026-09-10, IF they are ready. They do not hold v2 up if not.

DISCLOSE PERMANENTLY, in provenance.json and beside every number from this pair: it straddles a binary build boundary. Seed 1 is the Feb-05 build, the genuine seed 2 the Jul-21 build. paths.yaml never mentioned the Jul-21 build at all; it does now.

AND: a rebuild of v0/v1 under the same command now yields different bytes than those versions' recorded hashes. That is exactly why v2 is a new version and never an edit in place. v0/v1 hashes stay untouched.

STILL WORTH ITS 34 CORE-HOURS, and line X asked first: a second seed for 20 pilot cells. It converts the kill test ceiling from a bound (0.8697) into a measurement, and it would attribute the 2.7 % soil-carbon offset. 10 % of what the pilot cost. Do it alongside v2.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — two operational changes before you start corpus v2: commit in two steps, and the checkers now see new files

TWO OPERATIONAL CHANGES LANDED ON MAIN TODAY. Both affect the corpus v2 rebuild you are about to start, which is a lot of commits and at least one merge, so read them before you begin.

1. STAGING AND COMMITTING IN ONE COMMAND IS NOW DENIED. It silently disabled every commit-time checker -- budgets, ownership, experiments, secrets and the silent-corruption lint. The hook fires once, before the whole command, so it inspected the index before the staging step had run, saw nothing staged, concluded there was nothing to check and let the commit through. No prompt, no opt-in, and none of the visible trailer a deliberate bypass leaves. Reported 2026-09-09 and still fully open until today. Use two commands; the deny message says so if you forget.

2. THE CHECKERS NOW SEE A FILE YOU HAVE JUST WRITTEN. Run with no arguments -- which is what you do by hand, and what CI's budgets job does -- they listed tracked files only, so a brand-new document was invisible. A 122-line decision record passed the local check against its 120-line cap and only started failing once committed. Untracked files that are not gitignored are now included. This one matters for you specifically: corpus v2 will produce new records and new provenance files, and you will now find out they are over budget BEFORE the merge rather than after.

3. wait_gates no longer hangs 15 minutes on a gate that never ran. A gate with no check-run on this sha inherits the verdict from the newest ancestor carrying one, but only when nothing since touches the paths that gate filters on. What cannot be inherited gets a named diagnosis in about 4.5 minutes plus the command that forces a real verdict. It cannot turn red into green. This bit every line that commits its handoff last, which is all of them.

NOTHING ABOUT THE CORPUS DECISIONS CHANGES. Both were answered on 2026-09-14 and the genuine high-emissions second run is already wired on main. Build v2 as one rebuild.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-14) — the login-node guard stops refusing commands that only mention heavy work -- stop prefixing the override onto git

A STANDING PIECE OF ADVICE IN YOUR OWN NOTES IS NOW PARTLY WRONG. The login-node guard no longer refuses commands that merely MENTION heavy work, as of 2026-09-14 on main (commit 7150e96). Line X reported it.

WHAT CHANGED. The rules now match the command with the ARGUMENTS OF TEXT-CARRYING OPTIONS removed: -m, --message, --body, --subject, --reason, --allow-red. So each of these is now ALLOWED, and each was refused before:
  git commit -m "docs(corpus): rebuild corpus_build.py under the genuine second seed"
  python3 tools/inbound.py --to D --body "see corpus/state.py:159"
  python3 tools/campaigns.py abandon --tag t --reason "the corpus build died"

This matters for you specifically: a rebuild is a lot of commits, and a commit message that names the file you just changed was being refused as if it were the job itself.

STOP PREFIXING ALLOW_LOGIN_HEAVY=1 ONTO ORDINARY git AND inbound COMMANDS, and correct that line in your gotchas when you next touch them. That is the reason this was fixed rather than documented: routinely switching a guard off on commands it was never meant to catch trains a reflex, and the reflex does not reliably stop at the harmless ones. The override is unchanged and still right for a genuinely quick real check.

NOT FULLY CLOSED, AND HONESTLY SO. Text that is NOT an argument to one of those options is still scanned, so a keyword inside a heredoc body or a shell variable assignment still trips it. It bit me twice while verifying the change. Two ways through when writing a long message: pass it straight to --body, or write it to a file and use --body "$(cat <file>)". Keep the override for the rest.

WHAT DID NOT CHANGE, deliberately. `python3 -c "import torch; ..."` is still refused -- it is a quoted string that IS the program. `python3 -m torch.distributed.run` is still refused -- after python, -m takes a MODULE, not a message, and the two are told apart by whitespace. Both are pinned as must-deny cases.

VERIFICATION. 28 cases; the four newly-allowed ones were re-run against the previous hook and all four fail there. Full suite 222 passed, 11 skipped; budgets, lint, test and changelog green on the pushed commit.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

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
