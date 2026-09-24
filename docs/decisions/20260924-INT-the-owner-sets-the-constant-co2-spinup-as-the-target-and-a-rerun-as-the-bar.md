# The owner sets the stored constant-CO₂ spin-up as the target and "as good as a rerun" as the bar

- **Status:** accepted
- **Date:** 2026-09-24
- **Line:** INT (integrator, recording owner decisions)
- **Supersedes:** nothing; it answers the open owner questions of `20260915-D-the-spinup-did-converge-*`
  ("which CO₂ level is the target") and of `20260918-INT-*` (a new corpus version or not), and it
  parks the mid-tier corpus and the all-cell truth campaign that `PLAN.md` carried as owed.

## The four questions and the owner's answers, verbatim where it matters

Asked on 2026-09-24, after a read of the whole repository showed four decisions blocking the large
runs that "finished" seemed to need.

1. **The CO₂ level of the equilibrium target.** Answer: **276.59 ppm** — the model's own
   pre-industrial spin-up constant, which every pilot result already uses. Nothing is re-based.
2. **What counts as passing, given that a second run of the model itself meets the conjunctive
   per-cell band in only 0.47–0.56 of cells.** Answer: **"as good as a rerun"** — per cell, the
   emulator must land inside the band `max(10 %, the model's own two-run spread)` statistically no
   less often than an independent second run of the original model does.
3. **Approval of large compute** (a 1,000-cell × 100-climate × 2-seed corpus, and all-cell
   reference spin-ups under present-day and 2090s climates). Answer, verbatim: *"you dont need new
   runs. there is spinup, ssp370 and ssp126 available already. in teh spinup only the years until
   the onset of rising co2 levels should be used. the ssp scenarios only go 100 years, so no
   eqiuilibrium reached yet. for now make the emulator work for the spinup wiht constant co2. when
   that works i will give oyu more data"*.
4. **The acceptance cell set and patch count.** Answer: **the 56,986 cells with any stem** in
   the restart file, **25 patches**; the 54,020 cells with a tree over 5 m are a subset.

## What follows from them

- **The target is the stored global spin-up's constant-CO₂ stretch**: model years 1000–1699 of
  the Historical ground-truth runs (seeds 1 and 2), which recycle the first 30 forcing years,
  **1901–1930**, at the 276.59 ppm clamp (`getco2.c:47`). Years 1700–1999 carry the CO₂ ramp and
  are not used. The SSP runs are transients that never settle, so they are not an equilibrium
  target.
- ⚠ **That run kept, per cell, only vegetation carbon for those years** (`vegc_spinup_1999.nc`,
  trees + grass, both seeds, every year). There is no restart and no per-tree table before 1999.
  So the all-cell acceptance test exists for **one quantity**; tree counts and traits can only be
  tested where two constant-CO₂ seeds of a spin-up exist — the pilot, whose full second seed ran
  on 2026-09-23 (6,000/6,000, `pilot-v2-constco2-s2`).
- **"As good as a rerun" is operationalised** (in every pre-registration that uses it) as
  non-inferiority: `D = frac(emulator) − frac(rerun) ≥ −0.02`, both scored against each seed with a
  band whose width comes from a pair the scored pair does not set (an earlier half-window of the
  same runs for the spin-up; the cell's other 29 climates for the pilot). The 2-point margin was
  stated before any model arm ran.
- **Parked, not abandoned:** the mid-tier corpus tooling and the all-cell truth builder
  (`scripts/corpus_truth.py`, marked PARKED) stay in the repository and working; nothing launches
  them without a new owner decision. The corpus schema-3 re-decode (soil columns, blank tree-type
  shares on treeless rows) was done without new spin-ups as `pilot-v3-constco2`.
- The owner's "when that works" makes a **rerun-grade vegetation-carbon map on the stored spin-up**
  the next milestone to report against; the full-state criterion is a further step.

## The first measurements against it (2026-09-24)

| sealed test | emulator | rerun | best lookup | outcome |
|---|---|---|---|---|
| `X-20260924-spinup-vegc-from-pilot` | 24.7 % in band (variance expl. 0.926) | 85.9 % | 18.4 % | fail (b) |
| `X-20260924-spinup-vegc-from-spinup` | 42.7 % (0.961) | 85.9 % | 33.1 % | fail (b) |
| `X-20260924-pilot-state-asgood` (19 at once) | 0.36 % of rows | 10.35 % | 3.25 % | fail (c) |

All nulls returned their pre-registered values exactly. 56,986 cells for the first two; 200 cells ×
30 climates for the third.

## Consequences for how work is done

- Do not propose new spin-up campaigns to the owner as the next step; the owner has said more
  data follows success on this target.
- Report every result against the rerun, never against 1.0.
- The CO₂ question is closed at 276.59 ppm (and the emulator still never sees CO₂: invariant 8).
