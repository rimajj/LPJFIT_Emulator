### Added

- **The pilot corpus exists, and with it the experiment the predecessor could never run.** Every
  existing ground-truth leg holds exactly one climate per location, so climate and geography are
  collinear and a warming response is not separately identified — which is what the predecessor's
  kill test failed on. This spins the *same* cell up under **thirty** climates: 200 cells × 30
  climates × 1 seed = **6,000 single-cell 1000-year spin-ups**, all 6,000 of which printed the
  model's own completion line and wrote a restart file. Cost **337 core-hours** against the
  roadmap's estimate of 670, or 3.37 core-minutes per 1000-year spin-up; 24 shards of 250, the last
  23 running at once on 5,750 cores at about 8 minutes each. 1.5 GB of forcing, 12 GB of restarts.
  Corpus version v1, `plan_sha256 bad787ade3fc609b25cf8ebc87dfd0978e4a869068d9408c73945ec3dc667f99`.
- ⚠ **A complete campaign is not yet a usable corpus, and this is 6,000 restart *files*, not a
  table.** Decoding them into per-(cell, climate) state rows is the next step and the only thing
  standing between the corpus and the kill test. What can be said already, from restart byte size
  alone: the median record is 2.18 MB, which is a real forest, and **374 of 6,000 (6.2 %) came back
  at or below the vegetation-free floor** of ~360 KB. So the deliberately-wide axis ranges are not
  wiping out vegetation, but that 6.2 % belongs beside every number the corpus later supports.
- **`vegemu.corpus.select` chooses which cells the corpus spins up, and it is a design rather than a
  sample.** A uniform draw would concentrate cells where cells are dense — up to 900 tree-bearing
  cells in one 15° tile against 1 in another — and would put most held-out cells within a few
  hundred kilometres of a training cell, which turns a per-cell score into a spatial-interpolation
  score. Instead: the five biome reference cells are forced in, then **every populated 15° tile gets
  one cell** (the tile's climate medoid), then the remaining budget is spent by a **maximin fill**
  on the climates the first two stages left thinnest. All **164** populated tiles are covered.
  Nothing draws a random number, so a pre-registration can cite the design and regenerate it.
- **The design coordinates are the five perturbation axes' own baselines**, one each — annual
  temperature, annual precipitation (logged), precipitation seasonality, shortwave, interannual
  variability. That is what makes cells × climates cover the joint space instead of a slice of it.
- `scripts/corpus_pilot.py` runs the tier in four stages — plan, build, verify, harvest — so every
  file the 6,000 spin-ups will read is proven to exist *before* 337 core-hours burn, and the whole
  campaign has one harvest command however many SLURM shards it took. The harvest counts the runs
  that printed the model's own completion line and the restart files they wrote, never exit codes,
  and reports the restart-size distribution because "complete" and "usable" are different claims.
- Full record, including the disclosures line X needs before pre-registering the kill test — the
  shared-versus-per-cell design trade-off, the absence of within-tile replication, and the two
  responses nobody has explained: `docs/decisions/20260909-D-pilot-corpus-v1.md`.

### Changed

- `scripts/corpus_perturb_clm.py` splits into `load_base` and `write_point`. A cell's 30-year
  baseline block and its calibrated seasonal shapes depend on the cell and never on the
  perturbation, so they are now read once and reused across all 30 climates; calling `build` thirty
  times per cell repeated the calibration read thirty times, about a million small random reads to
  produce the same thirty answers. Every check the old path made still runs, because it *is* the
  path `build` takes.
- **Tree-bearing cells are 56,986 on the restart file's own stem count, not the 54,020 of the
  acceptance criterion.** That figure came from the predecessor's per-tree text table, which drops
  every stem at or below 5 m, so it counts cells with at least one *visible* tree; ours counts cells
  with at least one tree. The larger set is the right basis for a corpus whose target is the restart
  file, but the two are not interchangeable and neither may be quoted without saying which it is.
- ⚠ **The one sanctioned cross-line channel does not work against a line that is at budget, and
  that is an integrator matter.** The disclosures above were written as a `tools/inbound.py` message
  to line X, which is exactly the tool's purpose. `lines/X/STATE.md` sits at **exactly** its
  120-line budget, so the block pushed it to 128, turned the `budgets` gate red — and
  `tools/merge.sh` now *refuses* on a red gate, so it would have blocked **every** line's merge, not
  just this one. The message was withdrawn and routed through a decision record instead. No
  minimum-length message avoids this: the smallest possible block is about eight lines, and a line
  at budget has none. Line X hit the same wall from the other side and used the changelog for the
  same reason. So today there is no working way to put a message in front of a line whose state file
  is full, and both workarounds in use rely on the recipient reading main. Worth either exempting
  inbound blocks from the recipient's budget, or having `inbound.py` refuse up front and say where
  to put the content instead — it currently warns *after* writing.

### Fixed

- **Line D's share of the two red gates is clear, and here is exactly what is left.** `types` went
  from **17 errors to 1**, and the one that remains is not line D's; `lint`'s format check went from
  14 files to **3**, none of them line D's. What is left, for whoever owns it:
  `src/vegemu/models/synth.py:143` (an `Any` returned from a function declared to return an array —
  the same one-line annotation used twice in `corpus/perturb.py` here), plus `ruff format` on
  `scripts/train_emulator.py`, `src/vegemu/models/__init__.py` and `src/vegemu/models/synth.py`.
  All four are **line T's exclusive paths**, so `check_ownership` refuses the fix from line D — the
  guard working as designed, and the reason this note exists instead.
- ⚠ **Two of the type errors cleared here were in `corpus/perturb.py` and had never been seen**,
  because that file landed on a branch whose gates had never run. The commit that introduced it
  claimed to have made its array types explicit for strict checking; it missed two functions. A gate
  that has never executed is not a gate, and "I fixed it for the type checker" is not evidence until
  the checker has actually said so.
- Three places loaded a sibling script by path without registering it in `sys.modules`. Every module
  here opens with `from __future__ import annotations`, so annotations are strings and `@dataclass`
  resolves them through `sys.modules[cls.__module__]` — which is `None` for a module loaded that
  way. The symptom is an `AttributeError` raised inside `dataclasses.py` the moment the loaded
  script merely *defines* a dataclass, so it reads as a broken standard library rather than a broken
  loader. It cost two real-data tests when the first dataclass was added to a script.
- The maximin fill tested exhaustion with `isfinite`, but an unvisited candidate's nearest-neighbour
  distance is `+inf`, which is also not finite — so starting from an empty set reported "exhausted"
  immediately and selected nothing at all. The test that caught it asks for a fill of a whole frame.
- **The guard's own deny tests could switch themselves off.** `.claude/hooks/slurm-guard.sh` allows
  unconditionally when `ALLOW_LOGIN_HEAVY`, `ALLOW_RAW_SBATCH` or `SLURM_JOB_ID` is set, and it
  inherits them from the session — so running the suite from a shell that had used the documented
  escape hatch turned every must-deny case in `tests/test_slurm_guard.py` red at once, which reads
  as "the guard is broken" rather than "the guard is off for this shell". All three are now stripped
  from the child. It cost this session a false diagnosis before the commit that fixes it.
- `ruff format` had never been applied to eleven of line D's and the shared test files; the diffs are
  hand-aligned continuation lines no ruff version produces. No logic changed.
- The `.clm` header reader no longer builds `ClmHeader` by star-unpacking `struct.unpack`. That read
  as "gets multiple values for keyword argument" at four call sites, because `struct.unpack` is
  typed as a tuple of unknown length so nothing proves the unpack stops before `cellsize_lon`. The
  runtime binding was correct. The six integers every version shares are now read once and bound
  **by name**, with each version's tail following on the same handle — which a format reader wants
  anyway, since this is where the order of six integers in a file becomes the meaning of six fields.
