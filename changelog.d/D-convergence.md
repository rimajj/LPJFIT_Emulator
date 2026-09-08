### Measured — line D

* **The 1000-year spin-up has not converged.** Global vegetation carbon is 719 Pg C at year 200,
  735 at year 500 and **890 at year 1000**, still rising at **+6.5 %/century**; 58 % of vegetated
  cells are outside their own acceptance band at the end of the run and 73 % are still rising
  faster than 1 %/century. So the stored state is not an equilibrium but *the state the model's
  standard spin-up protocol reaches*, and `PLAN.md`'s hoped-for 3.3× cut to every corpus budget is
  refuted — a 300-year spin-up would differ by 22 %. Record:
  `docs/decisions/20260908-D-spinup-is-not-converged.md`.
* **The noise floor, measured on this data:** the two-seed relative spread of end-of-spin-up
  vegetation carbon has a median of 3.41 %, a p90 of 13.6 % and a p99 of 42.4 % across 61,700
  vegetated cells. Interannual variability of the annual series is 16.5 % of the level.

### Added — line D

* `src/vegemu/score.py` — the acceptance band, the conjunctive band-fraction statistic, the
  response skill, and the blocked spatial folds. Shared on purpose: line X derives what each null
  must return with the same code line T uses to measure the model.
