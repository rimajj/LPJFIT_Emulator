### Added

- **The pilot corpus is now a table, and the kill test is unblocked.** All 6,000 single-cell restart
  files are decoded and joined to the forcing that produced them: **6,000 rows × 181 columns**, one
  row per (cell, climate), **0 failures**, 8.9 s on 16 processes. Each row carries 86 climate
  features computed from that run's *own* perturbed forcing — not the baseline plus a recipe — the
  five design coefficients that name the climate, spatial-fold keys, and 76 state targets: stem
  counts, carbon stocks, the height distribution, species composition, the growth-failure counter,
  and five quantiles of each of eight per-stem traits.
  `corpus_sha256 fbe74ed2416b265f4c874959ab8b186679a641cedf3e18df32b125f7362e1e4d`, at
  `/p/tmp/jamirp/vegemu/corpus/pilot-v1/corpus.parquet`, via
  `scripts/corpus_pilot.py --stage decode`. Record:
  `docs/decisions/20260909-D-corpus-v1-decoded.md`.
- **The corpus was checked against the model it is meant to emulate, and it agrees to about ±20 %.**
  Each cell's neutral "control" run reads forcing byte-identical to the historical baseline, so it
  should reproduce the forest the stored full-globe run holds at that cell — and nothing guaranteed
  it would, because re-running one cell on its own is known not to be a replica of the same cell
  inside a global run. Over the 183 control runs that grew a forest, the stem count matches the
  stored run at **rank correlation 0.961** and a median ratio of **1.023**, with the 10th and 90th
  percentiles at **0.839 and 1.231** — no detectable bias. Separately, every control run's annual
  temperature, precipitation and radiation reproduce the source forcing to **zero difference**,
  confirming the perturbation writer is exactly neutral through a completely independent read path.
- **17 of the 200 control runs grew nothing at all, and it is two different things.** Fourteen are
  cells with under 50 mm of rain a year (the driest is 0.42 mm) where all twelve months are dry and
  even the soil carbon comes back at exactly zero — nothing grew in a thousand years, and the model
  is simply right that they are desert. The dryness threshold is sharp: the driest cells that *did*
  grow trees sit just above them. Those cells were selected on purpose, to span beyond today's
  climate envelope, so they are the design working as specified rather than a defect. The other
  three are cold, wet cells that carry real soil carbon and are genuinely bistable — one of them
  grows a forest under 22 of its other 29 climates but not under its own present-day climate. This
  matters for the kill test because the decisive comparison ("predict this cell as it is today") is
  evaluated at exactly that control point, so at 8.5 % of cells it predicts bare ground; the
  pre-registration should report both bases, all 200 cells and the 183 whose control is a forest.

### Fixed

- **A one-cell forcing file's cell number was being read as a row number, which would have given
  the entire corpus the wrong soil depth and the wrong latitude.** The climate summariser indexed
  the whole-globe soil-depth and coordinate files by position, which is only correct for a
  whole-globe forcing file. The per-run files hold a single cell and declare which one it is in
  their header, so every row would have been handed cell 0's soil depth and cell 0's coordinate
  with no error raised anywhere. Corpus v0's tables are byte-unchanged by the fix.
- **A parallel worker that touched a dataframe hung forever, silently.** polars runs its own thread
  pool, which does not survive the process fork that the parallel decode uses, so the first attempt
  burned its entire wall-clock allowance having produced nothing — no error, no traceback, an empty
  log. The state summariser already avoided this by having workers return plain dictionaries and
  assembling the table in the parent; the climate summariser now offers the same fork-safe entry
  point, with the rule written at both call sites. Per-run decode time went from over 8 seconds to
  0.0015 seconds.
