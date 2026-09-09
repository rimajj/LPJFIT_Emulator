### Added — the perturbed `.clm` writer and the climate-perturbation design (line D, D1)

`vegemu.corpus.perturb` builds designed climate perturbations on five independent axes
(temperature, precipitation amount, precipitation seasonality, shortwave, interannual variability),
with the per-cell seasonal *shapes* calibrated on a within-leg climate-model contrast
(ssp370 2071–2100 minus 2015–2044). Relative humidity is held exactly fixed under the model's own
definition of it; net longwave is tied to the applied warming; CO₂ is untouched and never written.

`scripts/corpus_perturb_clm.py` writes a **one-cell** forcing set — 44 KB per variable instead of
11.7 GB — which is what makes the pilot corpus about 1.3 GB rather than ~450 GB. A neutral design
point is a structural no-op, so a zero-perturbation file is byte-identical to the slice of the real
source file it came from; that is checked against the real inputs in `tests/test_perturb.py`.

`scripts/corpus_spinup_config.py` builds a spin-up config by patching the ground truth's own saved
configuration with asserted replacements. `scripts/sbatch_cmodel.sh` gains `LPJ_DEFINES` (so a
spin-up can run with no preprocessor flag, as the ground truth's own job does) and a `--manifest`
task-farm mode: many single-cell runs inside one allocation behind one ledger row, which is what
the 6,000-run pilot corpus needs.

### Fixed

`docs/reference/binfmt.md` §3 said the spin-up cycles its 30 forcing years deterministically. The
configuration sets `shuffle_climate: true`, so the years are drawn at random; the formula quoted
was the branch that is not taken.
