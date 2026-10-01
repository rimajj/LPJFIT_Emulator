# MPI-ESM1-2-HR ssp245 ran at 401.63 ppm CO₂, so it is not the Germany target

- **Status:** accepted
- **Date:** 2026-10-01
- **Line:** INT (integrator; invariant 8 applied to a data fact, no new owner steer)
- **Corrects:** `20260930-INT-the-germany-equilibrium-runs-become-their-own-corpus.md`, whose
  "CO2 is constant at 415.78 ppm from 2020" is false for 2 of the 12 runs. That record is
  immutable; this one supersedes that sentence only.

## What was found

1. **CO₂.** `MPI-ESM1-2-HR/ssp245/random_seed_{1,2}/input_MPI-ESM1-2-HR_ssp245.js` read
   `/home/jamirp/scripts/droughts/RCP85_co2_1765-3100_const_from_2015.dat` (401.63 ppm from 2015 on).
   The other ten future runs, and both historical runs, read
   `/p/projects/biodiversity/input_VERSION2/RCP85_co2_1765-2500_const_from_2020.dat` (415.78 from
   2020). With `fix_climate` on, `iterate.c:96-99` reads CO₂ at `fix_climate_year` (2100) for every
   later year, so over the whole clean segment 2101-3070 MPI ssp245 held **401.63** and the rest
   **415.78** — 3.4 % less. Its run configs are otherwise byte-identical to MPI ssp126's and ACCESS
   ssp245's (names substituted).
2. **The build.** The 2025-12-17 → 2026-02-05 change is one line (`lpjml56fit` `b2e5ca9`,
   `new_tree.c`): an inheriting newborn's wood density and D95max were clipped to the range of the
   *calling slot's* tree type rather than its own. Fingerprint over every cell of the twelve 3070
   restarts (`scripts/diag_germany_build_fingerprint.py`, job 2369693): on the old build every one of
   the 9,065 tree-bearing cells holds stems outside their own type's range (wood density 2.9-3.6 %,
   D95max 3.3-4.1 % of stems); on the new build 2-13 cells of 9,065. The effect sits in the extreme
   tail (temperate needleleaf D95max p99 1,144-1,234 vs 996; temperate summergreen 627-652 vs 497)
   and barely moves a type's p10/p50/p90.
3. **Which explains the worst fold.** The Germany state test's worst held-out climate was MPI ssp245
   (0.289 vs a rerun's 0.510). Per-cell medians: MPI ssp245 dips below BOTH neighbours in stems per
   patch (17.12 / 15.86 / 16.92 for ssp126/245/370) and leaf-longevity p90 (2.290 / 2.156 / 2.253);
   ACCESS ssp245, on the same new build at 415.78 ppm, is monotone in both (15.84 / 16.46 / 17.08;
   2.334 / 2.325 / 2.304). So the build does not produce the dip; the CO₂ difference is the only
   input unique to that run. Suspected, not proven: no run isolates CO₂ alone.

## The decision

- **MPI-ESM1-2-HR ssp245 leaves the Germany target** for any test that trains a map across
  climates. The emulator does not see CO₂ and must not respond to it (invariant 8), so a run at
  another CO₂ is a different target, and mixing it in teaches a CO₂ response as if it were climate.
  The corpus files are not changed; tests drop it with `exp_germany_state.py --exclude`.
- **ACCESS-CM2 ssp245 stays**, flagged as the new build: its CO₂ is right and its build effect is
  confined to traits' extreme tails. Results are still reported with and without it.
- The two sealed Germany verdicts stand as measured; they are read with this record. A five-climate
  re-test is a new experiment id, pre-registered before it is scored.

## For the owner

Both MPI ssp245 seeds point at a different CO₂ file from every other run. If that was not
intended, those two runs are the ones to redo (the owner's production data; not touched here).
