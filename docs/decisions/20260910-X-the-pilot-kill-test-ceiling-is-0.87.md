# The pilot kill test's ceiling is 0.87, so the bar is reachable — and the pilot's soil carbon is 2.7 % light

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** X
- **Completes:** `X-20260909-pilot-warming-response`, which was sealed with a bar and no ceiling.
  Does not modify it — the sealed record is unchanged and this adds the number needed to read it.

## What was decided

**A perfect emulator could score at most 0.8697** on this test, against a bar of **0.225690**. The
bar is therefore reachable with wide headroom, and the pre-registration is sound as sealed.

This closes an omission in my own work. The experiment was sealed with a pass mark and no statement
of what perfect means — the same gap line T caught in the drift test (a conjunctive pass rate read
against an implied 100 % when a third real model seed reaches only 25 %) and the same one X3 had
already fixed for itself, where perfect is 0.538490 rather than 1.0. A bar without a ceiling cannot
be read: 0.225690 is a modest ask or an impossible one depending on a number nobody had computed.

## Why the ceiling is below 1.0 at all, and why it is nonetheless high

LPJmL-FIT is stochastic. Writing a state as `X = mu + eps`, the target is a contrast of two single
runs, `dtrue = dmu + (eps_p - eps_0)`, so the target itself carries noise. A perfect emulator
predicts the noise-free `dmu` — it cannot know which realisation the truth drew — so its residual is
exactly `-(eps_p - eps_0)` and `ceiling = 1 - SUM Var(eps_p - eps_0) / SUM dtrue^2`.

`sigma` is estimated from the only two-seed pair that exists at these cells: the ground truth's
historical seed 1 and seed 2 end-of-spin-up restarts, where `(s1 - s2)` has variance `2 sigma^2`.

| quantity | ceiling |
|---|---|
| soilc | 0.9765 |
| lai | 0.9580 |
| sla_p50 | 0.8930 |
| wooddens_p50 | 0.8875 |
| agb | 0.8834 |
| stems_per_patch | 0.7563 |
| height_p50 | 0.7333 |
| **mean (the estimand)** | **0.8697** |

It is high because the perturbations are **large** — up to +6 K and ×0.7 precipitation — so the
response dwarfs run-to-run noise. That is the opposite of X3 and of the drift test, where the signal
was comparable to the noise and the ceiling collapsed toward the nulls. The two tightest quantities
are the two noisiest relative to their response: median stem height and stem count.

⚠ **This is a LOWER bound, deliberately.** Line D gives a cell's control and perturbed arms the
**same random seed**, so `eps_p` and `eps_0` are correlated to an unknown degree and
`Var(eps_p - eps_0) = 2 sigma^2 (1 - rho)`. The table is `rho = 0`. At `rho = 0.5` it is 0.9349; at
`rho = 1` the noise cancels entirely and the ceiling is 1.0. Measuring `rho` needs a **second seed
for a subset of the pilot** — 20 cells × 30 climates at line D's measured 3.37 core-minutes per
spin-up is **~34 core-hours**, which is 10 % of what the pilot already cost. Worth asking for, not
worth blocking on: every value of `rho` puts the ceiling above the bar.

## The apparatus check the same two reads paid for

Nobody had checked that the pilot's **single-cell** control spin-up reproduces the **global** run's
state at the same cell. Line D proved the neutral design point is a structural no-op in the forcing
*bytes*; that is not the same as proving the resulting *state* matches, because the model's random
stream need not be identical when it walks 1 cell instead of 67,420. Measured at all 200 cells,
as a fraction of the seed-1 level, median:

| quantity | signed pilot − s1 | signed s1 − s2 (control) | \|s1−s2\| | \|pilot−s1\| |
|---|---|---|---|---|
| stems_per_patch | +0.70 % | −0.33 % | 7.25 % | 9.64 % |
| agb | −0.17 % | +0.39 % | 11.07 % | 16.40 % |
| lai | −0.36 % | +0.78 % | 6.06 % | 8.24 % |
| **soilc** | **−2.68 %** | −0.36 % | **1.69 %** | **6.04 %** |
| height_p50 | 0.00 % | 0.00 % | 2.68 % | 3.85 % |
| wooddens_p50 | −0.55 % | −0.03 % | 3.33 % | 4.99 % |
| sla_p50 | −0.07 % | +0.42 % | 2.52 % | 3.60 % |

**Six of the seven are unbiased.** Their signed offsets (0.00–0.70 %) are the size of the
seed-to-seed control column, so the pilot is a different *draw*, not a different *model*. Their
scatter is ~1.4× the two-seed scatter, which is expected of an independent draw compared against a
single reference that is itself a draw.

**Soil carbon is not.** A systematic −2.68 %, against a −0.36 % control — the pilot's single-cell
spin-up ends consistently *lighter* in soil carbon, and only 20 % of cells fall within the global
run's own two-seed spread. This is the behaviour the slowest pool should show if the spin-up
protocol differs even slightly, and line D has already recorded that the 1000-year spin-up is not
converged (57.9 % of vegetated cells still moving, median +6.8 %/century). No attribution is offered
here; what is established is that the offset is real, systematic, and confined to soil carbon.

### What that does and does not threaten

* **It does not threaten this experiment.** The estimand is a **within-pilot paired contrast** —
  both arms come from the same protocol, so a per-cell offset cancels in `dtrue` exactly. That is
  the property the paired design was chosen for.
* **It does threaten any comparison of pilot LEVELS to ground-truth LEVELS.** A model trained on
  pilot-v1 and scored against ground-truth soil carbon inherits a 2.7 % systematic offset before it
  makes a single error of its own. Line T should not mix the two bases without a stated bridge, and
  X2/X3 score against ground truth, not against the pilot.
* **It makes the ceiling slightly optimistic**, because `sigma` came from the global run. If the
  pilot's own realisation variance is the ~2× implied by its 1.4× scatter, the conservative ceiling
  falls to **≈0.74** — still more than three times the bar, so the conclusion is unchanged. A second
  pilot seed would replace this estimate with a measurement.

## What was NOT established

* **Why soil carbon is light.** Protocol, spin-up length, and the single-cell random stream are all
  live candidates; distinguishing them is line D's, and needs one cell run both ways.
* **`rho`, the seed correlation between a cell's arms**, which is the whole width of the
  0.8697–1.0 band. Needs a second pilot seed.
* **Nothing about the emulator.** No model was fitted here either.

## Reproduce

`scripts/exp_derive_ceiling_pilot.py --state <pilot state parquet> --out <dir>` under
`sbatch_py.sh`. It seeks 200 cells out of each of two 119 GiB restarts — minutes, not hours, because
the reader uses the file's own offset table and never scans. Result:
`/p/tmp/jamirp/vegemu/exp/X-pilot-ceiling2/ceiling_pilot.json`.
