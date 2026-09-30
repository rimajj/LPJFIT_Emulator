# The Germany equilibrium runs become their own corpus, truth window ending in 3070

- **Status:** accepted
- **Date:** 2026-09-30
- **Line:** INT (integrator, recording an owner decision)
- **Relates to:** `20260924-INT-the-owner-sets-the-constant-co2-spinup-as-the-target-and-a-rerun-as-the-bar.md`
  ("when that works I will give you more data"). Nothing here changes the global target or its bar.

## What was given

The owner pointed at `germany.runs` (`config/paths.yaml`): LPJmL-FIT 5.6.004 production runs for
Germany, 9,067 cells at ~0.07 deg, npatch 250, natural vegetation, two ESMs (ACCESS-CM2,
MPI-ESM1-2-HR) x ssp126 / ssp245 / ssp370 x seeds 1 and 2. Each run follows its scenario to 2100,
then recycles random years of 2071-2100 until 3100. CO2 is constant at 415.78 ppm from 2020.
So every cell has six settled climates, each with two seeds: the same-cell-many-climates design the
global stored spin-up (one climate per place) cannot provide.

## What was found before using it (read-only inventory, 2026-09-30)

1. **The humidity input is misread in two segments.** The forcing holds relative humidity. The
   segments 2015-2070 and 2101-3070 declare it (the model logs `rhumid`); 2071-2100 and 3071-3100
   do not (logged `humid`), in every one of the 12 future runs. There `getvpd.c` reads the file as
   specific humidity, clips relative humidity to 1, and the vapour-pressure deficit is zero every
   day, so the dryness term of tree water stress (`waterstress_tree.c`) is off. The 3100 restarts
   and the per-tree tables of 3071-3100 come from those 30 years.
2. **Two builds:** ssp245 ran on the 2026-02-05 build (after an inheritance fix in `new_tree.c`),
   ssp126 and ssp370 on the 2025-12-17 build.
3. **Two damaged or unjoined files:** MPI-ESM1-2-HR ssp370 seed 2's 3100 outputs were overwritten
   by a cancelled rerun (the `*_3100_backup.nc` survive; its per-tree table stops at 3073);
   ACCESS-CM2 ssp370 seed 2 was never concatenated to one 2101-3100 series.
4. Its CO2 (415.78 ppm) and patch count (250) differ from the global target's (276.59, 25).

## The decision (owner, 2026-09-30: "yes, go ahead")

- **A separate corpus, `germany-eq-v1`, never pooled with the global stored spin-up.** The emulator
  does not see CO2 (`MEMORY.md:co2-closed`), so pooling two CO2 levels would blur them.
- **Truth = each seed's mean vegetation carbon over 2821-3070; band = max(10 %, the two seeds'
  spread over 2571-2820)**, the global test's construction moved inside the clean segment. The
  3071-3100 shift is measured and reported per cell, never used as truth.
- **Inputs from the 2071-2100 daily forcing**, relative humidity read as relative (as the clean
  segments did), by the same feature functions as every global table (`scripts/germany_corpus.py`).
- **ssp245 is kept and flagged**; every result is reported with and without it.
- The first test is the climate response: predict a scenario the model never trained on, for the
  same cells, pre-registered with the strongest same-cell null before anything is scored.

## Not decided here

Whether the humidity defect should be fixed by re-running 3071-3100 is the owner's call (it is
their production data). Tree counts and traits at a clean date need the 3070 restart decoded; the
per-tree tables are all from a defective segment.
