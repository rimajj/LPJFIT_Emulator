# Changelog

All notable changes to this project. Format: Keep a Changelog; newest first.
Entries are written as `changelog.d/<line>-<slug>.md` fragments and folded in at merge.

## [Unreleased]

<!-- collated 2026-09-08 from 3 fragment(s) -->

### Added
- **The LPJmL-FIT restart reader and writer** (`src/vegemu/binfmt/restart.py`). Rung 0 passes: 100 real cells spanning 360 KB to 3.5 MB read out of the 119 GiB ground-truth file and written back **byte-identically**, plus a property test over the four variable-length parts (the litter list, the per-stem PFT list, the two 20-year ring buffers, the sapling pool).
- **The `.clm` reader and writer** (`src/vegemu/binfmt/clm.py`). Two whole real input files round-trip byte-identically; the 11.7 GB forcing files are proven piecewise (header + one year's raw block). The mixed-version trap is now an executable assertion rather than a comment.
- **`docs/reference/binfmt.md`** — the field-by-field spec, each field naming its C source.
- `src/vegemu/paths.py` — resolved access to `config/paths.yaml` from inside the package.
- `src/vegemu/score.py` — the acceptance band, the conjunctive band-fraction statistic, the response skill, and the blocked spatial folds. Shared on purpose: line X derives what each null must return with the same code line T uses to measure the model.
- **The corpus builder** (`src/vegemu/corpus/`, `scripts/corpus_build.py`). Per-cell state summaries read straight out of the restart files — counts, stocks, the growth-failure counter, the height distribution, PFT composition and five quantiles of each of eight per-stem traits — and per-cell 30-year climate summaries read out of the `.clm` forcing. Both seeds of all three legs, so the acceptance tolerance (the model's own two-seed spread) is measured rather than assumed. Provenance, including each source file's decoded header, ships with every table.

### Changed
- **The 1000-year spin-up has not converged.** Global vegetation carbon is 719 Pg C at year 200, 735 at year 500 and **890 at year 1000**, still rising at **+6.5 %/century**; 58 % of vegetated cells are outside their own acceptance band at the end of the run and 73 % are still rising faster than 1 %/century. So the stored state is not an equilibrium but *the state the model's standard spin-up protocol reaches*, and `PLAN.md`'s hoped-for 3.3× cut to every corpus budget is refuted — a 300-year spin-up would differ by 22 %. Record: `docs/decisions/20260908-D-spinup-is-not-converged.md`.
- **The noise floor, measured on this data:** the two-seed relative spread of end-of-spin-up vegetation carbon has a median of 3.41 %, a p90 of 13.6 % and a p99 of 42.4 % across 61,700 vegetated cells. Interannual variability of the annual series is 16.5 % of the level.

<!-- collated 2026-09-02 from 1 fragment(s) -->

### Added
- the campaign ledger, so a job launched by a dead session cannot be lost

### Fixed
- the append-only checker no longer silently passes when origin/main is absent

