### Added

- **The kill test's ceiling is 0.8697, so its bar of 0.225690 is reachable with wide headroom.** The
  experiment had been sealed with a pass mark and no statement of what *perfect* means, which is the
  same omission line T caught in the drift test and the same one X3 had already fixed for itself
  (where perfect is 0.538490, not 1.0). A bar without a ceiling cannot be read at all. Record:
  `docs/decisions/20260910-X-the-pilot-kill-test-ceiling-is-0.87.md`.
- **Why the ceiling is below 1.0:** the model is stochastic and the target is a difference of two
  single runs, so the target itself carries realisation noise that no emulator can predict. It is
  nonetheless *high* here — 0.9765 for soil carbon down to 0.7333 for median stem height — because
  the perturbations are large (up to +6 K, ×0.7 precipitation) and the response dwarfs run-to-run
  noise. That is the opposite of X3 and of the drift test, where signal and noise were comparable.
- `scripts/exp_derive_ceiling_pilot.py` — seeks 200 cells out of each of two 119 GiB restart files
  in minutes, never scanning, using each file's own offset table.

### Changed

- **The ceiling is a deliberate LOWER bound, and the gap is worth one cheap run.** A cell's control
  and perturbed arms share a random seed, so their noise is correlated by an unknown amount: the
  0.8697 assumes no cancellation, 0.9349 assumes half, and perfect cancellation would give 1.0.
  Measuring it needs **a second seed for 20 pilot cells — about 34 core-hours, 10 % of what the
  pilot already cost**. Worth asking of line D; not worth blocking on, since every value puts the
  ceiling far above the bar.

### Fixed

- **The pilot corpus's soil carbon is systematically 2.7 % light against the global run, and that
  had never been checked.** Line D proved the neutral design point is a no-op in the forcing
  *bytes*; nobody had checked the resulting *state*. Measured at all 200 cells: six of the seven
  scored quantities are unbiased (signed offsets of 0.00–0.70 %, the size of the seed-to-seed
  control), so the single-cell pilot is a different *draw* and not a different *model*. **Soil
  carbon is the exception at −2.68 %** against a −0.36 % control, with only 20 % of cells inside the
  global run's own two-seed spread — the behaviour the slowest pool shows when a spin-up protocol
  differs slightly, and the spin-up is already known not to be converged.
- **What that does and does not threaten.** It does **not** threaten the kill test, whose estimand is
  a within-pilot paired contrast, so a per-cell offset cancels exactly — that is what the paired
  design was chosen for. It **does** threaten any comparison of pilot *levels* against ground-truth
  *levels*: a model trained on the pilot and scored on ground-truth soil carbon inherits a 2.7 %
  offset before making an error of its own, so line T must not mix the two bases without a bridge.
  It also makes the ceiling mildly optimistic — on the pilot's own wider scatter it would be ≈0.74,
  still more than three times the bar.
