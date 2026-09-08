# The synthesised restart's carbon was not halved by the synthesis; the model killed the roster

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** T
- **Supersedes the attribution** in `20260908-T-restart-loads-but-carbon-is-halved.md` §"Why the
  carbon is half right". That record's measurements stand; its cause does not.
- **Basis for every number below:** cells 42480–42499, 20 of 54,020, one region (temperate Europe),
  present-day climate, historical seed 1. **This is not the acceptance test.**

## What the earlier record concluded, and why it was wrong

It concluded that the transplant delivered about half the mass the emulator asked for, because a
stem with the right height and wood density can still carry the wrong mass, and recommended adding
above-ground biomass to the matching objective. Both are wrong, and one measurement settles it:
**read the state summary of the file that was written**, instead of inferring it from the run.
Above-ground biomass, gC/m²: the real state **3,777**; the emulator predicted **4,308** (+12 %);
**the file that was written 4,030 (+6.7 %)**; the model's output after one year ≈**1,400** (−63 %).

The file was 6.7 % **high**, not 50 % low. Nothing was lost in synthesis; the carbon was destroyed
during the simulated year. The earlier record compared year-2000 output against year-2000 output,
so it measured the collapse and attributed it to the writer.

## What actually happened, from the model's own diagnosis

Both arms are subset runs over the same block, same config, same single task, so only the starting
state differs. The control is stationary, as an equilibrium state should be; the emulated arm lost
half its stems and two thirds of its carbon in twelve months.

| | stems per patch, in → out | vegetation carbon, in → out |
|---|---|---|
| control | 19.58 → 18.88 (**×0.96**) | 4,822 → 4,957 (**×1.03**) |
| emulated | 18.94 → 9.62 (**×0.51**) | 6,188 → 2,153 (**×0.35**) |

`ind__*.csv` carries a per-individual mortality diagnosis, and it is unambiguous: **tropical
broadleaved evergreen, 2,372 stems, 100 % dead, `mort_temp` = 1.000** — certain death. Boreal
needleleaved summergreen, 240 stems, also 100 %, by one of the two hard kills rather than the graded
terms. All five other types: 0.9–2.0 %. `tree/mortality_tree_ind.c` computes `mort_temp =
5.0 × stress_days / 365`, capped at 1, counting any day outside the type's temperature band, and a
tropical broadleaved evergreen's band starts at **+12.5 °C** (`par/pft_lpjmlfit.js`) — so in a
temperate European cell it reaches the 73 stress days that make death certain in about ten weeks.

**31 % of the stems written into the file were of a type those cells' own real state never
contains.** The pool was ten cells "chosen to span the trait and size space" — which means it spans
*biomes* — and the donor choice minimised distance in (height, wood density) while never looking at
type, so the nearest match for a temperate stem was often an Amazonian one. 48.6 % of the stems
above the output threshold could not live there; 49.2 % of the roster died.

## The general lesson, which is not about trees

Every stem was a byte-exact copy of a real stem the model produced, so every stem was individually
valid. **The roster was not viable.** Three gates passed it — a byte-identical round-trip, the
config pre-flight, and a one-year run that did not abort under `-DSAFE` — and none can see this: a
round-trip validates a **layout**, whereas this is a **cross-reference between a record and its
cell's climate** (the litter-index fault in the earlier record, one level up); and "does not abort"
is not "accepts the state" — the model *repaired* the state by killing what did not belong, then
reported success.

**A validity check on the parts is not a viability check on the whole.** Anything assembled from
individually-valid pieces drawn from different contexts needs an assertion about the assembly;
`tests/test_synth_admissibility.py` is that assertion here.

## The fix, and what it bought

Tree type moves from FREE to **COPIED** — taken from the target cell's own template roster at the
matching size rank, with the trait match made only among donors of that type. The template is a real
state of that cell, so its type set is admissible by construction, and taking the type at the
matching size *rank* preserves the template's type–size association, without which a type that is
never tall would be asked to be the tallest stem. `inadmissible_placed` must be zero, per cell.

That immediately exposed the next constraint, which is the honest sign the first one was real: with
types constrained the pool became binding. The block needs 983 temperate broadleaved summergreen
stems above 12 m — where the mass is — and the ten biome cells held **50**, so every tall one was
reused about twenty times. The pool is now nine biome cells plus a **proximity band** of 20 cells
either side: 25,424 donor stems against 6,745. Proximity, not "the cells richest in what this block
lacks", which would make the result a selected maximum. Cell 42490 left the biome list because it
sits inside the default block, and `_donor_cells` now refuses any donor inside the block being
written — a donor from the target block scores the synthesis against itself.

**After one year of the real model, median |emulated − control| / control over the 20 cells:**

| | veg. carbon | above-ground biomass | stems/patch | median height |
|---|---|---|---|---|
| as it was (v0) | 0.543 | 0.610 | 0.490 | 0.099 |
| type-constrained (v1) | 0.296 | 0.279 | 0.068 | 0.053 |
| **+ widened pool (v2)** | **0.091** | **0.092** | **0.088** | **0.063** |

The state is now **stationary**: vegetation carbon ×1.04 over the first year against the control's
×1.02, where before it was ×0.35.

## Tried, and it does not work: matching more traits

Six of the 22 scored quantities are trait quantiles the transplant does not target, so the obvious
move is to target them. Measured, same cells: five traits instead of two **hits the three medians it
adds and wrecks the tails** — rooting-depth median 0.295 → 0.157, longevity median 0.096 → 0.075,
but wood density's 90th percentile 0.063 → 0.167, longevity's 0.192 → 0.371, above-ground biomass
0.091 → 0.154. Net 11 of 22 worse, 6 better, median cell hitting 12 of 22 instead of 15. Not a
hyperparameter: a donor is **one real stem** carrying one value of every trait at once, and all
targets are drawn at the same rank, so a five-trait match asks for a stem at the same quantile of
five distributions simultaneously. No such stem need exist. Default stays at two; the set is a
parameter (`--match-traits`) so the next attempt is a measurement rather than an edit.

## What is still wrong, stated plainly

- **The conjunctive test still fails: 0 of these 20 cells** are inside the band on all 22 quantities
  at once, median 15 of 22. Carbon passing t4 is not the acceptance criterion. That rate is
  consistent with the emulator's own held-out 3.6 %, so it is inherited from the prediction rather
  than added by the synthesis — but it is still a fail.
- **20 cells of 54,020, one region, one climate.** Says nothing about the rest or the warmed leg.
- **Two errors partly cancel.** The emulator over-predicts biomass by 12 % and the pool still
  delivers 8 % less mass per stem than these cells hold, so the file lands closer to the truth than
  the prediction does. Arithmetic, not skill, and it will not cancel elsewhere.
- **Leaf area is 30 % low and barely moves**, because leaf carbon is a per-stem mass and the
  transplant matches traits, not masses. A cell-total mass constraint is a different mechanism and
  is not built.
- **Composition cannot change.** Copying the type mix from the template means a warmed restart
  carries present-day composition, and a composition shift is a large part of the warming response.
  `corpus/state.py` already computes `pft_frac_*`; the limit lifts when those enter the scored set.
- t3 (20-year drift inside the two-seed spread) is now worth running, which it was not before.
