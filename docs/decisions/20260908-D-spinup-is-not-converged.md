# The 1000-year spin-up has not converged, so "equilibrium" is the wrong word for the target

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** D
- **Supersedes:** nothing. Corrects an assumption in `PLAN.md` (rung 0's "highest-leverage number").

## What was measured

`vegc_spinup_1999.nc` is a 1000-step global vegetation-carbon trajectory of the spin-up itself, for
both random seeds. It is cited in no predecessor document. `scripts/corpus_convergence.py` reads it,
maps it onto orderA cell order through `grid_1999.nc: cellid`, and asks when the trajectory stops
moving. Convergence is judged on a **30-year running mean** — 30 is `nspinyear`, so exactly one
climate cycle averages out — against a band of `max(10 %, that cell's own two-seed spread)`.

| | value |
|---|---|
| global vegetation carbon at year 200 / 500 / 1000 | 719 / 735 / **890** Pg C |
| mean of the final 100 years | 794 Pg C |
| trend over the last 200 years (30-yr running mean) | **+51.9 Pg C per century, +6.53 %/century** |
| global curve stays within 10 % of its final level from year | 197 |
| … within 5 %, 2 %, 1 % | **never** |
| vegetated cells not settled at year 1000 | **57.9 %** |
| cells still rising faster than 1 % / 5 % per century | **73.3 % / 58.0 %** |
| median per-cell trend at year 1000 | **+6.81 %/century** |
| cells settled by year 300 / 500 / 700 | 1.3 % / 1.9 % / 4.1 % |

The curve is not a monotone approach to a plateau. It rises steeply to ~719 Pg C by year 200, sits
between 728 and 736 Pg C from year 200 to about year 800, and then **rises again** to 890 Pg C by
year 1000. The two seeds agree on this to 0.073 % of the global level, so it is not noise.

The likely mechanism is in the configuration rather than the physics: `lpjmlfit.js` sets
`inherit_startyear: 200`, so for the first 200 years every trait combination is seeded everywhere
and trait *inheritance* only begins after that. What follows is slow trait sorting, whose timescale
is far longer than biomass turnover. This attribution is **not established here** — only the
trajectory is measured — but it is the first thing to check.

## Two things this changes

**1. "Equilibrium" is the wrong word, and `PLAN.md`'s product A must be requalified.** The stored
`restart_1999.lpj` is not the stationary forest a climate supports. It is *the state LPJmL-FIT
produces after its own standard 1000-year spin-up followed by the 1901–1999 historical transient*.
That is a well-defined, reproducible and useful target — it is exactly what a user of the model
gets, and skipping it is exactly the saving on offer — but it is a **protocol-defined** state, not
a physical equilibrium. Every claim must say which it is. Where `PLAN.md` says "the stationary
forest that climate supports", read "the state the model's standard spin-up protocol reaches".

**2. The corpus budgets do NOT drop; the hoped-for 3.3× is refuted.** Rung 0 asked whether the
forest is stationary by ~300 years, which would cut every tier proportionally. It is not: global
vegetation carbon at year 300 is 728 Pg C against 890 Pg C at year 1000, a 22 % difference — far
outside the 10 % floor and outside the two-seed spread in almost every cell. A shortened spin-up
would produce a systematically *different* state, not a cheaper version of the same one. So the
pilot tier stays at ~670 core-hours and the full tier at ~133,000, and any future ensemble must
run the full 1000 years to be comparable with the existing ground truth.

A cheaper corpus therefore has to come from fewer spin-ups or fewer patches, not from shorter ones.

## The noise floor, measured here for the first time on this data

The acceptance tolerance is `max(10 %, the model's own two-seed spread)`, and that spread is now
measured on the end-of-spin-up vegetation carbon of all 61,700 vegetated cells:

| quantile of the two-seed relative spread | value |
|---|---|
| median | **3.41 %** |
| p90 | **13.61 %** |
| p99 | **42.39 %** |

So the 10 % floor binds for most cells and the two-seed term binds in the tail — which is the
regime `MEMORY.md:noise-floor` describes ("up to 29 % in low-density cells"; the p99 here is
larger still). Separately, the **interannual** variability of annual vegetation carbon in the final
century has a median of **16.5 %** of the level. That is an order of magnitude larger than the
two-seed spread of the 100-year mean, and it is why convergence must be judged on a smoothed
series.

⚠ The first version of this measurement compared *annual* values against a band derived from the
difference of two *100-year means* and reported "68 % of cells never converge". That was an
artifact of the definition. Both diagnostics are now computed and reported separately, and the
conclusion above survives on the smoothed one.

## What was NOT established

* The mechanism. `inherit_startyear: 200` is a hypothesis, not a finding.
* Whether the trajectory would ever settle. It is still climbing at year 1000; nothing here bounds
  where it stops.
* Whether the same non-convergence holds for the trait distributions and the stem counts. Only
  vegetation carbon has a stored trajectory; the other quantities exist only at year 1999.

## Consequences recorded elsewhere

* `MEMORY.md` — two new rows: the non-convergence, and the measured noise floor. (Integrator.)
* `PLAN.md` — rung 0's convergence question is answered NO; the budget note must go. (Integrator.)
* `lines/D/STATE.md` — the corpus-tier numbers stand as written.
