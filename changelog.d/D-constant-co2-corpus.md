### Fixed

- **The spin-up was never run at constant CO₂, and fixing it removes about a quarter of the forest's
  carbon.** The model's CO₂ input is a file of real year-by-year values from 1700 onward, and the
  1000-year spin-up runs model years 1000–1999 — so its last 300 years were driven by the actual
  industrial-era CO₂ rise, +32.8 %. Rebuilt with CO₂ genuinely held fixed (corpus `v2-constco2`,
  6,000 runs, all completed), the same 200 locations under the same 30 climates hold **24 % less
  vegetation carbon**, 25 % less above-ground biomass and 21 % less leaf area, with 4 % more stems —
  a younger, lighter forest. The number of locations with no trees at all is unchanged, 380 of 6,000.

- **So "the 1000-year spin-up never settles down" was wrong, and it was our error.** Under fixed CO₂
  the forest is flat to **0.15 % per century** from year 200 on; the 6.5 % per century previously
  reported is the CO₂ response, and the trend was measured over a 200-year window lying entirely
  inside the CO₂ rise. Found by the owner asking why one location showed no late increase — it does
  not, because the dense forests that hold most of the carbon are flat or shrinking and the increase
  is concentrated in sparse ones.

- **The wording that hid it was "untouched".** Every corpus build recorded that CO₂ was "untouched
  and never written", which was true and is not the same claim as "constant". Both the code comment
  and the provenance file now state which of the two they mean.

- **No previously reported score is affected.** Every run of a given corpus shares the identical CO₂
  path, so it cannot bias a comparison between climates — the warming-response and species-mix
  results stand. What it breaks is calling the result an equilibrium.

### Added

- `scripts/corpus_pilot.py --const-co2` and `corpus_spinup_config.write_constant_co2`, which pin CO₂
  by writing a single-value forcing file. Done that way, rather than with the model's own
  climate-fixing switch, because that switch also replaces the weather sequence — and rather than by
  shifting the run's calendar, because that would silently convert 30 real weather years into 30
  more randomly drawn ones. Details and the source lines: `docs/reference/corpus-design.md`.
