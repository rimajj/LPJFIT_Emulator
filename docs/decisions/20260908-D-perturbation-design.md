# The delta-change perturbation design, and the one-cell `.clm` that makes the corpus affordable

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** D
- **Supersedes:** nothing. Implements `PLAN.md` §"Perturbation design rules" and unblocks D2.
- **Corrects:** the mechanism *hypothesised* in `20260908-D-spinup-is-not-converged.md` (see §5).

## 1. The decision

Five free axes, each an independent scalar drawn per design point, applied to a 30-year daily
forcing block for one cell:

| axis | unit | range | how it is applied |
|---|---|---|---|
| `dtemp` | K | −2 … +8 | added, with the climate model's own **seasonal warming shape** for that cell |
| `fprec` | × | 0.50 … 1.75 | multiplied, with the climate model's seasonal **shape of fractional change** |
| `sprec` | — | −0.5 … +1.0 | amplifies the cell's own precipitation seasonality at a preserved annual total |
| `frad` | × | 0.85 … 1.15 | multiplies shortwave, seasonally uniform |
| `fiav` | × | 0.5 … 2.0 | scales each year's departure from the 30-year block |

Two fields move but are **not** axes, because they are responses and not forcings:

- **`lwnet`** is tied to the temperature change that actually came out, at a per-cell per-month
  sensitivity in W/m²/K read off the climate model and clipped to ±3.
- **`huss`** is set so **relative humidity is exactly unchanged** — under *the model's own*
  definition of it, the Bolton form in `getvpd.c:38` at 1013.25 hPa, which is what LPJmL-FIT's tree
  water stress reads (`waterstress_tree.c:36`). Not a textbook formula: a textbook one would leave
  the model seeing a residual humidity drift while the test passed.

**CO₂ is untouched and no CO₂ file is written at all** (`MEMORY.md:co2-closed`).

The design is 1 neutral control + an 11-point temperature × precipitation factorial core + a
17-point Latin hypercube over all five axes, reproducible from a seed and this module alone.

## 2. Why the calibration contrast is *within one scenario leg*

The shapes come from **ssp370 (2071–2100) minus ssp370 (2015–2044)**, never from
scenario-minus-historical. The historical forcing is observational (GSWP3-W5E5) and the scenario
legs are MPI-ESM1-2-HR, so their difference is a **model bias**, not a climate change. Within one
leg both terms are the same model and the same file and the bias cancels exactly. At the five biome
test cells that contrast is +2.0 … +2.7 K, so the design's +8 K bound is about three times the
climate model's own late-century warming — deliberately outside today's envelope, which is rule 4.

## 3. Only the coefficients are free; the shapes are the climate model's

Scaling a cell's own warming *shape* does not re-introduce the collinearity the corpus exists to
break: the coefficient is drawn independently of the cell, so climate and place are decorrelated by
construction even though the applied field is place-specific. What the shape buys is physical
coherence — winter-amplified warming at high latitude is real and it moves phenology.

Guards, because a shape is a ratio and a ratio divides by noise: below 0.5 K of calibration warming
the temperature shape is replaced by flat and the longwave tie is switched off; below 2 % annual
precipitation change the precipitation shape is replaced by flat; every shape is clipped to [−1, 3]
and renormalised, so one desert month with a 900 % ratio cannot set a whole cell's structure. Every
guard that fires is written into the run's own `perturbation.json`, so a flat shape is visible
rather than silent.

## 4. Disclosures — the places this is knowingly approximate

- **Fixed relative humidity slightly over-moistens.** At the five test cells the climate model's own
  specific humidity rises ×1.08–1.16 over its late-century contrast, where holding relative humidity
  fixed at the same warming gives ×1.12–1.22. Land relative humidity falls a little in the climate
  model; we hold it flat. That is rule 2 applied as written, and it errs towards *less* drying
  stress, not more.
- **Shortwave is a free axis rather than tied to temperature.** The climate model's own change is
  −5.9 … +2.6 W/m² across the test cells, which the ±15 % range spans. Keeping it free keeps the
  axes independent, at the cost of not reproducing the joint temperature–cloud structure.
- **Longwave sensitivity is noisy per cell:** +0.70, −0.07, +0.21, +3.21, +0.24 W/m²/K at the five
  cells under ssp370; under ssp126, where the warming is ~0.3 K, the same ratio reaches +64 and is
  meaningless. Hence the ±3 clip and the 0.5 K floor.
- **A dry day always stays dry.** Precipitation is only ever multiplied, so the wet-day count is an
  invariant of the whole design — deliberate, because fire and phenology read the daily sequence,
  but it means the design cannot vary rainfall *frequency*, only amount and seasonality.

## 5. Two protocol facts that had to be established, and one correction

**The spin-up is run with no preprocessor flag at all.** The ground truth's own `slurm_spinup.jcf`
calls the binary with no `-D` argument (its `--comment` field says `-DFROM_RESTART` and is stale).
So `-DSPINUP` is *not* set, and every run built here must match that or it is a different spin-up.

**Therefore `inherit_startyear` was 0, not 200, in the run that produced every restart file we
compare against**, since the config sets 200 only under `#ifdef SPINUP`. Our runs print the model's
resolved value — `inheritance after 0 yrs` — so this is read off the model, not inferred.
`20260908-D-spinup-is-not-converged.md` proposed that 200-year "everything-is-everywhere" phase as
the likely mechanism for the late rise in the spin-up trajectory. That record flagged the
attribution as unestablished, and it is now **falsified**: the phase was never active. The
measurement stands; only its candidate explanation falls.

**1000 model years come out of a 30-year file as 970 shuffled + 30 sequential.** `iterate.c:88-119`
runs from `firstyear − nspinup` to `lastyear`, and any year before the *climate file's* first year
draws a random one of the first `nspinyear` stored years. With the stock `firstyear 2000,
lastyear 1999, nspinup 1000` and a file covering 1970–1999 that is 970 shuffled then 30 in order.
The ground truth was 901 + 99 because its file began in 1901. Same protocol, same 1000 years,
different split — so a run built here is comparable to another run built here and never to the
stored global output (`MEMORY.md:subset-diverges`).

## 6. The one-cell `.clm`, and why the corpus is 1.3 GB and not 450 GB

The model reads a climate year at `(startgrid − header.firstcell) · nbands · itemsize + headersize`
and strides by `header.ncell · nbands · itemsize` (`openclimate.c:207-219`). The only gate on the
range is `firstgrid ≥ header.firstcell && nall + firstgrid ≤ header.ncell + header.firstcell`
(`openinputfile.c:145`). So a file declaring `firstcell = <our cell>, ncell = 1` is both read and
validated correctly while the grid and soil inputs stay global. A whole perturbed forcing set for
one cell is therefore **44 KB per variable** rather than 11.7 GB, and the pilot corpus's 6,000
(cell, climate) pairs cost about **1.3 GB** instead of the ~450 GB a full-width file per design
point would have cost.

The writer **refuses a source that is not unscaled float**. The historical leg is v3 float32 with
scalar 1.0; the scenario legs are v2 int16 with scalar 0.1, and a perturbation written through one
of those would quantise to a tenth of a degree — a +0.05 K perturbation would round to zero and the
run would look like an unexplained null rather than an error.

## 7. What makes the writer trustworthy

A **neutral design point is a structural no-op**: every axis is guarded by an explicit `if`, so the
identity point returns the base arrays bit-for-bit. That turns "write a neutral perturbed file and
byte-compare it against the slice of the real source file it came from" into a genuine round-trip
proof of the *perturbed* writer (invariant 7) rather than a coincidence of two float paths. It
passes on all five variables against the real 11.7 GB inputs, as a test rather than a one-off.
