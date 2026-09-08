### Added

- **The emulator** (`src/vegemu/models/emulator.py`): one gradient-boosted head per scored quantity, fitted per spatial fold. Predicting the 10th/50th/90th percentile of each trait directly IS a non-parametric distribution head, which is why this and not a parametric kernel is the first model; its limits — marginal quantiles predicted independently, no stochastic per-stem head — are stated in the module.
- **A restart file the real LPJmL-FIT loads and runs.** `scripts/synth_restart.py` emits one by template-conditioned synthesis with rank-matched stem transplant: 20 cells, 47.9 MB, 9,506 stems placed against 9,506 requested, achieved height and wood-density distributions within 0.3 % of the prediction. The model's own words: *"lpjml successfully terminated, 20 grid cells processed."*
- **Twelve validation figures** (`scripts/plot_validation.py`), covering both what works and what does not.

### Fixed

- **The per-stem `litter` byte is an INDEX into its patch's litter list, not a value.** A transplanted stem carried its donor patch's index and the C refused the file with `ERROR195`. No round-trip test can catch this: within one record the index is always consistent, and it breaks only when a stem moves between patches. Indices are now remapped to the target patch's slot for the same PFT.

### Changed

- **The emitted state loads but its carbon is half right** — vegetation carbon 2,561 against the control's 5,035 gC/m², a median relative difference of 0.534 — and the cause is attributed, not guessed: for the same cells the emulator predicts above-ground biomass to 12 %, so the fault is that carbon is not one of the donor-matching targets. Record: `docs/decisions/20260908-T-restart-loads-but-carbon-is-halved.md`.
