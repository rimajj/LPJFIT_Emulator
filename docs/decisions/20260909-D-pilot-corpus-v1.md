# The pilot corpus, version v1: which cells, which climates, and what it can and cannot support

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** D
- **Supersedes:** nothing. Realises `PLAN.md` §Corpus tiers, pilot row, and its design rules 1–7.

⚠ **THIS RECORD IS ALSO A MESSAGE TO LINE X, because the one sanctioned cross-line channel would
break a gate.** `lines/X/STATE.md` sits at exactly its 120-line budget, so any `tools/inbound.py`
block pushes it over, turns the `budgets` gate red, and `tools/merge.sh` then refuses every line's
merge. Line X hit the same wall from the other side and used the changelog. Read §"For line X".

## What was built

6,000 single-cell 1000-year LPJmL-FIT spin-ups: **200 cells × 30 climates × 1 seed**. All 6,000
printed the model's own completion line and all 6,000 wrote a restart file.

| | measured |
|---|---|
| cost | **337 core-hours**; 3.37 core-minutes per spin-up. `PLAN.md` estimated 670 |
| wall | 24 shards of 250 members; the 23 later ones ran concurrently on 5,750 CPU, ~8 min each |
| forcing | 1.5 GB, every one of the 30,000 files exactly 43,851 B |
| restarts | 12 GB; bytes p5 / p50 / p95 = 360,275 / 2,179,450 / 2,809,564 |
| treeless | **374 of 6,000 (6.2 %)** at or below the vegetation-free floor |
| identity | `plan_sha256 bad787ade3fc609b25cf8ebc87dfd0978e4a869068d9408c73945ec3dc667f99` |

Location: `/p/tmp/jamirp/vegemu/corpus/pilot-v1` (cells.csv, design.csv, runs.csv, provenance.json);
runs at `/p/tmp/jamirp/vegemu/runs/pilot-v1/c<cell>/<point>/`. Driver: `scripts/corpus_pilot.py`.

## The cell design, and why it is a design

A uniform random draw would have failed twice: it concentrates cells where cells are dense (up to
900 tree-bearing cells in one 15° tile against 1 in another), and it puts most held-out cells within
a few hundred kilometres of a training cell, which turns every per-cell score into a
spatial-interpolation score. `vegemu.corpus.select` instead does, deterministically:

1. **5 forced** biome reference cells — the cells the direction test characterised.
2. **159 tile medoids** — every populated 15° tile gets the cell closest to its own climate median.
3. **36 maximin** — the remaining budget goes to the climates stages 1–2 left thinnest.

All **164** populated tiles are covered. Tiles come from `vegemu.score.spatial_blocks` at 15°, the
same function `blocked_spatial_folds` uses, so a blocked fold holds out whole tiles by construction.
The design coordinates are **the five perturbation axes' own baselines** — annual temperature,
annual precipitation (logged), precipitation seasonality, shortwave, interannual variability — one
per axis, so cells × climates covers the joint space instead of a slice. Nothing draws a random
number, so a pre-registration can cite `plan_sha256` and regenerate the design.

## For line X — the three things to read before pre-registering rung 1

**1. The 30 climates are the SAME 30 at every cell.** One exactly-neutral control, an 11-point
temperature × precipitation factorial core (dtemp 0/+2/+4/+6 K × fprec 0.7/1.0/1.3, less the point
that *is* the control), and 18 Latin-hypercube points over all five axes. So a **held-out
perturbation level** is well defined, and the **same-cell baseline null is free at every cell**:
control and perturbed share the cell, the config, the forcing window and the random seed, so the
only difference is the climate. Disclosed cost: the five-dimensional axis space is sampled at 18
free points globally, not 200 × 18. That coverage is what the mid tier's 100 climates buys.

**2. There is no within-tile replication.** With about one cell per tile, holding out a tile holds
out one cell; 5-fold blocking gives ~33 tiles / ~40 cells per fold. The folds are honest, but they
cannot separate spatial interpolation from climate response. If that separation is needed, say so
and the mid tier can place 4 cells in fewer tiles instead — it is a design choice, not a limit.

**3. Eligibility is 56,986 cells, not the acceptance criterion's 54,020.** Ours is the restart
file's own uncensored stem count. The 54,020 came from the predecessor's per-tree text table, which
drops every stem at or below 5 m (`MEMORY.md:ind-censored`), so it counts cells with a *visible*
tree. Quote whichever you use; never both as one number.

### And the two responses nobody has explained

Both are LPJmL-FIT's own behaviour, not our forcing design: an attribution arm warmed the same +4 K
while leaving specific humidity alone — so relative humidity fell instead of holding fixed — and the
answer moved only 1–2 points at four of five cells.

**The response is not monotone in temperature.** At the Amazon cell (12045), vegetation carbon is
−36 % at +2 K, **−97 % at +4 K** (flat and dead from year one, 667 gC/m²), and back to ~35 % of
control at +6 K. The three forcing files differ ONLY in the temperature increment (29.2 / 31.2 /
33.2 °C annual mean) and the +6 K run provably opened the +6 K file. A monotone prior, a
linear-in-dtemp model, or a fold design that assumes interpolation between levels is safe will all
be wrong here — and a skill score averaged over levels will hide it.

**One cell gains carbon, and its arms are on different transients.** The Sahel cell (18371) is
+48…+53 % at +4 K. Its control is still climbing at year 1000 (303 → 953 gC/m² across the ten
100-year blocks) while its +4 K arm peaked early and is falling (1706 → 1636). At year 1000 the two
arms are two states each still moving — the non-converged spin-up
(`docs/decisions/20260908-D-spinup-is-not-converged.md`: 57.9 % of vegetated cells not settled,
median drift +6.8 %/century). **The target is protocol-defined**: "the state the model's standard
1000-year spin-up reaches", not an equilibrium. A per-cell paired contrast between two arms of the
same protocol is legitimate, because both arms carry the same drift; a claim about the stationary
forest a climate supports is not.

Directions at the other three cells, for calibration: boreal Siberia (52059) −14…−33 %, Hainich
(42490) −4…−19 %, Iberia (33335) −53…−64 % and monotone. Three of five matched the expectation
written down before the runs; Sahel and Hainich did not.

## What was NOT established

* **The corpus is 6,000 restart FILES, not a table.** Decoding them into per-(cell, climate) state
  rows is D2b, and nothing in this record is evidence about the state distribution beyond restart
  byte size — which is only a proxy for "did a forest establish".
* **Why 6.2 % are treeless.** The fraction is small enough not to threaten the tier, and it is a
  real property of the axis ranges (which deliberately span beyond today's envelope), but no
  attribution to particular axes or cells is offered here.
* **Whether the +6 K Amazon recovery is physical.** Only that it is reproducible and is the model's.
