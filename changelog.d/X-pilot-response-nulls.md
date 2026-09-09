### Added

- **The kill test finally has data that can answer it, and a sealed pre-registration to answer it
  with.** Line D's pilot corpus spins the SAME cell up under 30 climates, so climate and geography
  are no longer collinear and the warming response is separately identified — which was X1's own
  diagnosis of why its `fail` was not decisive. `X-20260909-pilot-warming-response` is sealed with
  seven nulls, every value derived from the truth before the model exists.
- **The bar is 0.145690, and it is not "no change".** The strongest information-free competitor is
  *every cell changes by the same fraction of what it already has*, applied to the held-out cell's
  own present-day forest. "Every cell changes by the same amount" scores 0.095610 and predicting no
  change at all scores exactly 0.0. A pass requires the emulator to reach **0.225690**.
- `scripts/exp_derive_nulls_pilot.py` — decodes all 6,000 pilot restart files and derives every null
  in **9 seconds on 32 cores**. Re-running it against a new corpus version or a new blocking radius
  is one job, so no future response claim has an excuse for arriving without its nulls.

### Changed

- **Copying another cell's response is worse than saying nothing changes.** The geographically
  nearest cell scores **−0.281166** and the climatically most similar cell **−0.239753**, both below
  the zero of "no change". The response is cell-specific and does not transfer between cells, so
  space-for-time substitution actively hurts here. It is not uniform, though: the climate-analogue
  null reaches **+0.329** on soil carbon and **+0.168** on above-ground biomass while collapsing to
  **−0.639** on stem count and **−0.585** on wood density. The *size* of the response scales with
  standing stock; its *composition* does not.
- **The blocking radius, which has flipped a null's sign before, barely matters here** — the two
  strong nulls move by less than 0.003 between 15° and 5° blocks. The pilot's 200 cells sit in 164
  populated 15° tiles, so there is no near neighbour to interpolate from at either radius. This is
  the property the 20-adjacent-cell block of X4 lacked.
- **The response is not smooth in temperature, and this is the majority behaviour rather than one
  odd cell.** Only **40.5 %** of the 200 cells have a monotone above-ground-carbon response across
  0 / +2 / +4 / +6 K. Predicting a cell's +4 K response from its **own** +2 K and +6 K responses —
  far more information than any emulator gets — reaches only **0.6176**, and **0.3342** for median
  stem height. Line D saw this at the Amazon cell; it holds across the corpus. Consequence: a
  held-out-climate-level experiment would charge the emulator for the roughness of the response
  surface, so this pre-registration deliberately holds out **space**, not levels, and requires the
  29-row per-level table to be reported beside the pooled number.

### Fixed

- **X1's pass threshold, transplanted here, would have pre-registered a guaranteed `invalid` — by
  eight hundred-thousandths.** The best null beats the runner-up by **0.050080**, and X1's rule was
  "> 0.050", so the best null would itself have satisfied the pass rule and the no-power check would
  have voided the verdict. The threshold is 0.080, derived from the nulls rather than inherited.
  This is the second time deriving nulls before designing the statistic has caught a dead experiment
  before it was sealed.
- **The obvious way to build the proportional null is unusable, and the number is on the record.**
  Aggregating the donor fractions by mean instead of median scores **−27.4** pooled and **−173.8** on
  above-ground biomass: the fraction has a near-zero control in its denominator at the 39 cells that
  go treeless under some perturbation. Both forms are pre-registered so "unusable" stays a
  measurement.
- `scripts/exp_derive_nulls_pilot.py` uses **spawn, not fork**, for its worker pool. polars' Rust
  thread pool is not fork-safe: forking after the parent has touched polars leaves every worker
  blocked on an inherited lock at **zero CPU, with no error and no progress**, which is exactly how
  the first version of this script behaved for four minutes before it was killed.
