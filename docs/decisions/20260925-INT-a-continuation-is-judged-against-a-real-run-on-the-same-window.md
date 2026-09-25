# A continuation is judged against a real run averaged over the same window

- **Status:** accepted
- **Date:** 2026-09-25
- **Line:** INT (integrator, recording an owner decision)
- **Refines:** `20260924-INT-the-owner-sets-the-constant-co2-spinup-as-the-target-and-a-rerun-as-the-bar.md`
  ("as good as a rerun"); it does not change the band, the cell set, the margin or the target.

## What was found

`X-20260925-spinup-restart-continuation` scores a restart by continuing the real model from it for
30 years and averaging ONE run's vegetation carbon over years 1-10. It read that 10-year mean
against `frac(rerun) = 0.858711`, which compares one seed's 250-year mean (1450-1699) with the
other's. A 10-year mean carries far more of the model's own year-to-year noise. Measured on the
stored run itself (`scripts/diag_window_ceiling.py`, job 2319481: an L-year window of one seed,
scored against the other seed's truth with the sealed band, every non-overlapping window in
1450-1699), all 56,986 scored cells:

| window (years) | 1 | 5 | 10 | 20 | 30 | 50 | 125 | 250 |
|---|---|---|---|---|---|---|---|---|
| in band | 0.498 | 0.560 | 0.598 | 0.647 | 0.679 | 0.729 | 0.816 | 0.859 |

L = 250 reproduces the rerun exactly. So under the sealed rule a PERFECT restart continued for 10
years scores D of about -0.26: that test's bar was unreachable by construction, a missing ceiling
arm (line T's standing gotcha: every band test needs one).

## The decision (owner, 2026-09-25: "on my call: agree with your suggestion")

**"As good as a rerun" for a continuation means as good as a real run scored on the SAME window.**
For a continuation arm scored on an L-year mean, the reference is `frac(real, L)`: an L-year window
mean of a real seed of the stored run, scored against the other seed's truth with the same band,
averaged over both seeds and every non-overlapping window of the truth stretch, on the same cells.
`D = frac(arm) - frac(real, L) >= -0.02`. Band, cell set, margin and truth are unchanged.

## What follows

- `X-20260925-spinup-restart-continuation` stays sealed and `fail`; it is not edited. Its successor
  is a new experiment id with this reference.
- A static map (a prediction that is not a run) is still read against the 250-year rerun: its
  number has no year-to-year noise to carry. The two references must never be mixed in one table
  without saying which is which.
- Rejected alternative: keep the 250-year reference and continue for 250 years (on the order of
  1,000+ core-hours for the globe, extrapolated from ~140 per 30 years).
