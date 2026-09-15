# The designed climate-perturbation ensemble — design rules

Moved out of `PLAN.md` on 2026-09-15 under its 150-line budget. The roadmap keeps the tier table and
points here; this file is the authority on why each rule exists.

## Perturbation design rules

The physical-coherence ones are not optional.

1. Calibrate perturbation directions on the **real climate-model deltas** (delta-change method), so
   every perturbed climate lies on the manifold a climate model actually produces. A perturbation
   assembled from independent axis scalings visits combinations the atmosphere never produces, and a
   model scored there is being asked a question nobody will ever put to it.
2. **Hold relative humidity fixed** when scaling temperature (Clausius–Clapeyron), and disclose it.
   Adding 6 K while leaving specific humidity alone produces impossible relative humidity — the run
   will not fail, it will simply be physics nobody meant to simulate.
3. Axes: temperature scale, precipitation scale, precipitation seasonality, radiation, interannual
   variability. Latin hypercube plus a small full-factorial core.
4. **Deliberately span beyond today's envelope**, where space-for-time is known to be sign-wrong.
   4.9 % of cells' 2090s temperature already exceeds the hottest tree cell today
   (`MEMORY.md:extrap-cells`), so a design that stays inside today's range cannot be asked about
   them at all.
5. **CO₂ must be genuinely CONSTANT, and that takes a deliberate act** — see below. It is not the
   default, and it was not true of corpus v0 or v1.
6. Cells stratified by the ~161 independent 15° tiles, so spatial folds mean something
   (`MEMORY.md:eff-sample`).
7. Run with `LPJ_IND_ALL_HEIGHTS` so the per-tree output is uncensored; the restart target is
   uncensored regardless (`MEMORY.md:ind-censored`).

## Rule 5 in full: constant CO₂ is not the default

⚠ **Corpus v0 and v1 do NOT have constant CO₂, and the word that hid it was "untouched".** The
ground truth's CO₂ input is `global_co2_ann_1700_2022.txt`, a transient file, and the spin-up runs
**model years 1000–1999**. LPJmL clamps CO₂ to `param.co2_p` for any year before the file's first
year (`src/climate/getco2.c:47`, `*pco2 = (year<0) ? param.co2_p : data[year]`), so:

| spin-up years | model years | CO₂ |
|---|---|---|
| 1–700 | 1000–1699 | constant 276.59 ppm — the clamp, not a setting |
| 700–1000 | 1700–1999 | the real historical record, **276.59 → 367.26 ppm, +32.8 %** |

Global vegetation carbon follows that ramp at **+5.53 %/century, r = +0.987**, against
**+0.15 %/century** over the constant stretch. For a week this was recorded as the spin-up failing
to converge, because the convergence script fitted its trend over the last 200 years — a window
lying entirely inside the ramp.

**How to actually pin it.** There is no `fix_co2` option in this build. `fix_climate` does pin CO₂
(`iterate.c:96`) but the same flag also replaces the climate sequence after `fix_climate_year`
(`iterate.c:143-154`), so it cannot hold CO₂ still without changing what climate the run sees.
Moving `firstyear` before 1700 also works via the clamp, but the spin-up phase is
`year < climate->firstyear` (`iterate.c:102`) and our perturbed `.clm` files declare 1970 — so
shifting the window would convert the final 30 sequential climate years into 30 more shuffled
spin-up years, a second change wearing the first one's clothes.

**So: write a constant CO₂ text file** at `param.co2_p = 276.59` and point the input list at it.
That changes CO₂ and nothing else — same years, same climate handling, same restart year, same
assertions. `corpus_spinup_config.write_constant_co2`, reached by `corpus_pilot.py --const-co2`.

⚠ **An identical CO₂ path confounds nothing.** Every run of a given corpus version shares it, so it
cannot bias a contrast between design points, and the scores computed on v1 stand. What it breaks is
the word *equilibrium*: a v1 state is a forest still adjusting to a CO₂ step.

Record: `docs/decisions/20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md`.

## What the spin-up actually does with 30 years of forcing

`iterate.c:88-119`: the loop runs from `firstyear - nspinup` to `lastyear`, and any year before the
climate file's own first year draws a **random** one of the first `nspinyear` stored years, because
`shuffle_climate` is on — the model prints `shuffle climate` in its own run banner. With the stock
`firstyear 2000, lastyear 1999, nspinup 1000` and a forcing file covering 1970–1999, that is **970
shuffled years followed by the 30 file years in order**, and the restart is written at 1999.

⚠ That is 970+30 where the ground truth was 901+99, because its forcing file began in 1901. Same
protocol, same 1000 years, different split. A run built here is comparable to another run built
here, **never** to the stored global output (`MEMORY.md:subset-diverges`).

Because the shuffle draws from the model's own RNG, **the random seed changes a spin-up's climate
ORDER as well as its stochastic mortality**. That is what makes a second seed a genuine replicate of
the whole protocol rather than a re-roll of mortality alone — and it is why the two-seed spread is
the right denominator for an acceptance band.
