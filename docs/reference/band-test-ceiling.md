# What the conjunctive band test can attain, and what each quantity is worth

The blessed statistic of the map experiment is `band_frac_conjunctive`: the fraction of cells whose
prediction is inside the acceptance band on **all 22** scored quantities at once. This page records
what that statistic's ceiling actually is, and how much each quantity is worth against it. It
exists because both numbers are easy to get wrong in the same direction, and the wrong versions
make effort look better spent than it is.

**Basis for every number here:** corpus v0, historical leg, state at 1999, climate window
1970–1999, npatch 25, truth = mean of seeds 1+2, 56,950 cells tree-bearing in both seeds, 5 blocked
folds at 15°, out-of-fold predictions from `X-20260908-climate-state-map`
(`exp/map-response-v0/oof_map.parquet`). Dimensionless fractions (levels). Re-derivable read-only
in seconds; no SLURM.

## 1. On the same-leg band the ceiling is 1.0, analytically — so it is not a ceiling

`score.acceptance_band` sets `band = max(0.10, |s1-s2|/|truth|) * |truth|`, so `band >= |s1-s2|`
always. The truth is `(s1+s2)/2`, so a perfect predictor of the ensemble mean `mu` misses by
`truth - mu`, which is distributed exactly like `(s1-s2)/2` — at most half the band, **by
construction**. Every quantity's ceiling is therefore 1.0000, and so is the conjunctive one.

Two consequences, both load-bearing:

- **No statement of the form "we are near LPJmL-FIT's own noise floor" is available on this
  statistic.** A two-seed spread is a real thing and it is why the band is not a flat 10 %, but the
  band already contains it. Whatever the score is short of 1.0 on the same-leg band is emulator
  error, not realisation scatter.
- **A leave-one-out oracle on the same-leg band lifts a quantity to perfection for free**, so it
  overstates what improving that quantity can buy. Use §3.

## 2. The non-circular ceiling is 0.5585

`score.acceptance_band_transferred` takes the tolerance's *size* from a different leg in the same
cell, so nothing about the scored realisation pair sets its own tolerance. With the ssp126 leg
supplying the spread and the historical leg the truth:

| | shipped model | attainable ceiling |
|---|---|---|
| **conjunctive, all 22** | **0.0351** | **0.5585** |
| `stems_per_patch` | 0.5394 | 0.9547 |
| `agb` | 0.4282 | 0.8798 |
| `lai` | 0.4837 | 0.9464 |
| `soilc` | 0.5638 | 0.9987 |
| `wooddens_p10` / `_p50` / `_p90` | 0.853 / 0.787 / 0.821 | 0.994 / 0.996 / 0.988 |
| `sla_p10` / `_p50` / `_p90` | 0.717 / 0.669 / 0.771 | 0.971 / 0.982 / 0.982 |
| `k_root_p10` / `_p50` / `_p90` | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| `D95max_p10` / `_p50` / `_p90` | 0.612 / 0.559 / 0.711 | 0.927 / 0.940 / 0.957 |
| `longevity_p10` / `_p50` / `_p90` | 0.634 / 0.585 / 0.552 | 0.956 / 0.967 / 0.901 |
| `height_p10` / `_p50` / `_p90` | 0.748 / 0.725 / 0.690 | 0.964 / 0.970 / 0.977 |

⚠ **The ssp126 leg came from a different LPJmL-FIT build** (2026-08-12, against 2026-02-05 for the
historical and ssp370 legs), so the transfer carries an unquantified build confound. This bounds
the ceiling; it is never a skill number and must not be quoted as one.

Reassuringly, the model's own score barely moves under the swap — 0.0361 on the same-leg band,
0.0351 transferred. The circularity inflates the *ceiling*, not the score. **The shipped model is
at 6 % of what is attainable.**

`k_root` is constant across the whole corpus — 0.02, a scalar rather than an interval in
`par/pft_lpjmlfit.js`, which is the parameter file the ground-truth runs actually use (via
`param_lpjmlfit.js`; `par/pft.js` is the stock LPJmL file and says 0.04). So three of the 22
quantities are satisfied by any prediction and the effective test is on 19.

## 3. Leave-one-out worth, against the attainable ceiling rather than perfection

Each row lifts one quantity (or group) from the model's prediction to its attainable ceiling and
leaves everything else as predicted:

| lifted to its ceiling | conjunctive | gain |
|---|---|---|
| nothing (the model) | 0.0351 | — |
| `soilc` — the best single quantity | 0.0435 | +0.0084 |
| `D95max_p10` | 0.0432 | +0.0081 |
| `D95max_p50` | 0.0410 | +0.0059 |
| `agb` | 0.0387 | +0.0036 |
| rooting depth, all three quantiles | 0.0614 | +0.0263 |
| the four stocks (`stems`, `agb`, `lai`, `soilc`) | 0.0637 | +0.0286 |
| **both groups — seven quantities perfect** | **0.1114** | +0.0763 |

**No individual quantity is worth more than +0.0084**, and seven of the 22 made perfect still
leaves 89 % of cells failing. Failure is a property of the CELL: it clusters ~151× more than
independent per-quantity failure rates would produce, and it lives in low-biomass forest (0.2–0.8 %
of cells pass in the lowest four biomass deciles against 14.6 % overall).

So the lever is not a quantity. Anything that improves one quantity in isolation is capped in the
low thousandths, and the way to move this statistic is whatever makes a broadly-wrong cell broadly
right. Candidates already excluded by measurement: a single shared per-cell error factor (the
leading residual component carries 24.7 % of standardised residual variance, and removing it with
an oracle moves the score only 0.0361 → 0.0428), and deriving one trait from another through the
model's own trait corridor (see the 2026-09-10 decision record, §5).

## 4. How to re-derive any of it

`scripts/diag_level_binding.py` gives the same-leg decomposition and the failure-clustering
numbers. The transferred-band ceiling and the oracle table come from
`score.acceptance_band_transferred` applied to the historical and ssp126 legs with
`dataset.load_leg`, scored against the stored `oof_map.parquet`. Both are read-only, take seconds,
produce no new skill number, and therefore need no experiment id — they decompose an existing
result rather than creating one.
