# Both open corpus-v2 decisions are answered: the genuine second run is the second run, and species composition becomes a predicted, scored quantity

- **Status:** accepted
- **Date:** 2026-09-14
- **Line:** INT (integration)
- **Decided by:** owner, 2026-09-14, on being shown the two questions
- **Supersedes:** nothing. Answers the two open asks recorded in
  `20260910-D-the-ssp370-second-seed-exists-and-the-configured-path-is-its-clone.md` and carried in
  `lines/D/STATE.md` since 2026-09-10, both of which had blocked the corpus rebuild for four days.

## The two questions, and the answers

Both had been escalated as decisions needing the owner. Neither was. The owner's answers, in
substance: **use the run that is not a copy — obviously**, and **predict species composition;
do everything that makes the emulator better.** Recorded here so neither is re-asked.

### 1. The high-emissions second run

**`ground_truth.ssp370_seed2` now resolves to `…_random_seed2_from_hist_seed2`.** Verified on disk
2026-09-14: complete (`lpjml successfully terminated, 67420 grid cells processed.`, anchored),
`restart/restart_2100.lpj` = 133,580,962,759 B against seed 1's 133,559,375,490 B, so it is
demonstrably a different realisation and not a byte-clone.

**The clone is retained, not deleted, under a name nobody will type by accident:**
`ssp370_seed2_INVALID_CLONE_OF_SEED1`. Three sealed pre-registrations cite corpus v0/v1 hashes that
were computed against it, so it is **provenance and must stay resolvable** — but it is no longer an
input to anything.

**This is a repoint of the existing key, not the new key line D proposed**, and the reason is the
shape of the original failure. That bug was *silent*: `random_seed` is inert under `-DFROM_RESTART`,
so bumping it produced an identical run with no warning in any log. Leaving the obvious-looking name
`ssp370_seed2` pointing at the poisoned directory keeps that landmine armed for every future reader
who reaches for the obvious key. Renaming the clone makes misuse impossible to do quietly, which is
the property that was missing in the first place. Exactly one consumer referenced the old spelling
(`scripts/corpus_build.py:69`) and that consumer *wants* the new target.

⚠ **Two disclosures ride with this pair, permanently:**

* **It straddles a binary build boundary.** Seed 1 was written by the Feb-05 build, the genuine
  seed 2 by the Jul-21 build. Any number derived from this pair must say so.
* **A rebuild of corpus v0/v1 under the same command now produces different bytes than those
  versions' recorded hashes.** That is why the rebuild is a **new corpus version**, never an
  in-place edit. `provenance.json` records each source file's size and mtime, so the change is
  visible rather than silent, and `check_seeds_differ` — which has been failing the build on the
  identical RNG triple — now passes for the right reason.

Why it matters beyond tidiness: the acceptance tolerance is `max(10 %, the model's own two-seed
spread)`. An identical pair gives a spread of exactly zero, so the tolerance silently collapsed to a
bare 10 % everywhere. Every band number computed against the clone was measured against the wrong
band.

### 2. Species composition

**`pft_frac_*` becomes a predicted quantity and enters `SCORED_CONJUNCTIVE` at corpus v2.**

This was framed as a scoring-scope question. It is not — it is plausibly on the critical path for
the project's central failure. The synthesiser currently **copies** species composition from the
template restart file, because nothing scores it. A copied composition cannot change. So an
emulated forest under a warmed climate is structurally incapable of shifting its species mix at
all — while the real model shifts it freely, and every per-species parameter in the C model keys off
exactly that composition. The one thing we most need the emulator to do, it is currently forbidden
from doing by an unscored field.

Line T's own measurements point the same way independently: failure clusters by **cell**, not by
quantity; making the seven best single quantities perfect still leaves 89 % of cells failing; and
the one cell-level explanation not yet tried is named in `lines/T/STATE.md` as "predicting the
cell's PFT composition, which currently appears nowhere".

⚠ **This raises the conjunctive bar and will lower the reported pass rate.** Adding quantities to a
conjunction can only make it harder. The comparison across corpus versions is therefore **not
like-for-like**, and any v2 number must be reported beside the v1-scope number computed on the same
model, or the change will read as a regression. It also needs its own **ceiling arm**: the attainable
ceiling is not 1.0 (it is 0.5585 on the current 22-quantity scope) and it must be re-measured for the
widened scope, not carried over.

## The one rebuild

⚠ **ONE corpus rebuild, not two.** Both changes land in the same new version. A changed corpus is a
changed question, and two versions in flight means two questions and no comparison. v0/v1 hashes are
untouched either way.

## What this record does not decide

The feature-set change line T asked D for on 2026-09-10 (four soil-type columns) also forces a
corpus version bump and is **not yet folded in here**. If it is ready when v2 is built it should
ride along in the same rebuild, for the same one-rebuild reason. If it is not, it does not hold v2
up — the composition and second-seed corrections are the ones with a decision behind them.
