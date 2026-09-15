### Added

- The species-mix kill test has a verdict, and it is a **pass**: which tree species a forest is made
  of does shift when the climate shifts, and that shift can be predicted. Score 0.425610 against a
  pre-registered pass mark of 0.337858 and a best information-free competitor of 0.177858, at both
  spatial fold radii, with all seven pre-registered competitors returning the values they were
  required to return. Read it as 49 % of what is attainable — perfect here is 0.863852, not 1.0,
  because the model being emulated is stochastic — and that ceiling is still a lower bound until a
  second seed exists. Basis: 200 cells, 30 climates, one seed, one binary; 5,258 of 5,800
  comparisons score, because composition is only scored where a forest existed at both ends.
  `experiments/X-20260914-pilot-composition-response/verdict.md`.

### Changed

- **The state synthesiser's copying of species composition is now a measured defect rather than a
  disclosed simplification.** It takes each tree's species from the cell's present-day forest, so an
  emulated warmed forest cannot change its species mix at all — and the signal that discards is most
  of what the 0.43 above is made of.
