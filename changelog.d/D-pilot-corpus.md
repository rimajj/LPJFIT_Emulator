### Added — the pilot corpus's cell design and its generator (line D, D2)

`vegemu.corpus.select` chooses which cells the corpus spins up, and it is a design rather than a
sample. A uniform draw would concentrate cells where cells are dense — boreal Eurasia and the Amazon
carry up to 900 tree-bearing cells per 15° tile, an oceanic island carries one — and would put most
held-out cells within a few hundred kilometres of a training cell, which turns a per-cell score into
a spatial-interpolation score. Instead: the five biome reference cells are forced in, then **every
populated 15° tile gets one cell** (the tile's climate medoid), then the remaining budget is spent
by a **maximin fill** on the climates the first two stages left thinnest. Nothing draws a random
number, so a pre-registration can cite the design and regenerate it.

The design coordinates are **the five perturbation axes' own baselines**, one each — annual
temperature, annual precipitation (logged), precipitation seasonality, shortwave, interannual
variability. That is what makes cells × climates cover the joint space instead of a slice of it.

`scripts/corpus_pilot.py` runs the tier in four stages — plan, build, verify, harvest — so that
every file the 6,000 spin-ups will read is proven to exist *before* 670 core-hours burn, and so the
whole campaign has one harvest command however many SLURM shards it took. The harvest counts the
runs that printed the model's own completion line and the restart files they wrote, never exit
codes.

### Changed

`scripts/corpus_perturb_clm.py` splits into `load_base` and `write_point`. A cell's 30-year baseline
block and its calibrated seasonal shapes depend on the cell and never on the perturbation, so they
are now read once and reused across all 30 climates; calling `build` thirty times per cell repeated
the calibration read thirty times, about a million small random reads to produce the same thirty
answers. Every check the old path made still runs, because it *is* the path `build` takes.

### Fixed

Three places loaded a sibling script by path without registering it in `sys.modules`. Every module
here opens with `from __future__ import annotations`, so annotations are strings and `@dataclass`
resolves them through `sys.modules[cls.__module__]` — which is `None` for a module loaded that way.
The symptom is an `AttributeError` raised inside `dataclasses.py` the moment the loaded script merely
*defines* a dataclass, so it reads as a broken standard library rather than a broken loader. It cost
two real-data tests when the first dataclass was added to a script.

The maximin fill tested exhaustion with `isfinite`, but an unvisited candidate's nearest-neighbour
distance is `+inf`, which is also not finite — so starting from an empty set reported "exhausted"
immediately and selected nothing at all. The test that caught it asks for a fill of a whole frame.

### Measured

**Tree-bearing cells are 56,986 on the restart file's own stem count, not the 54,020 of the
acceptance criterion.** That figure came from the predecessor's per-tree text table, which drops
every stem at or below 5 m, so it counts cells with at least one *visible* tree; ours counts cells
with at least one tree. The larger set is the right basis for a corpus whose target is the restart
file, but the two are not interchangeable. Among those cells, **164** 15° tiles are populated.
