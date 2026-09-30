# Figures

Built by `scripts/plot_current.py` from files already on disk; it fits nothing. Each figure's
subtitle states its basis. Last rebuilt 2026-09-30.

| figure | what it shows |
|---|---|
| `01_acceptance_vegc.png` | The acceptance test: share of cells whose vegetation carbon lands inside the tolerance band, emulator vs a second run of the model vs simple lookups. Stored global spin-up, constant CO₂. |
| `02_vegc_error_map.png` | Where the best carbon map is wrong, and where it falls short of a rerun. |
| `03_vegc_scatter.png` | Predicted vs true carbon cell by cell, and the distribution of relative error. |
| `04_learning_curve.png` | More places help, more cells in the same places barely do (development diagnostic). |
| `05_near_twins.png` | Neighbouring cells with near-identical inputs agree less well than two runs of one cell (development diagnostic). |
| `06_climate_response_tests.png` | The three sealed tests on the 200-cell pilot: change under a new climate, species mix, settled forest from climate alone; with each test's pass bar, the best reachable score, and a model that never sees the climate change. |
| `07_restart_continuation.png` | The emulated restart file continued 30 years in the real model, against a real run. |
| `08_year5_die_off.png` | Why carbon drops in year 5: trees mixed between forest patches; the fixes tried. |
| `09_tolerance_band.png` | Why the tolerance is max(10 %, the model's own run-to-run spread). |
| `10_spinup_convergence.png` | The stored spin-up settles; its late rise is the historical CO₂ increase. |

`archive/2026-09-08-first-map/` holds the first experiment's figures (existing scenario runs, one
climate per place, rising CO₂), superseded; rebuilt by `scripts/plot_validation.py`.
