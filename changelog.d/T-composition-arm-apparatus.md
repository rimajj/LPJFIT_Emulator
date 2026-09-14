### Added

- **The apparatus for scoring whether the emulator can predict a shift in the species mix.** The
  file-writing step copies each tree's type from the cell's present-day template, so an emulated
  warmed forest currently cannot change which species it holds — a limit the code has carried,
  disclosed, since the transplant was written. The pilot ensemble already records the share of each
  cell's stems held by each of the seven tree types under all 30 climates, so the question is
  measurable now rather than after a new model campaign. `exp_derive_nulls_composition.py` derives
  what every information-free competitor must score on it, how far apart those competitors are, and
  how well a perfect predictor could possibly do, which is what has to exist before the question can
  be sealed and asked.
- **The size of the target, measured before any skill number is quoted.** Across the 5,800
  cell-and-climate pairs a tree type's share of the stems moves with a root-mean-square of 0.15 to
  0.22, and by more than five percentage points in about 30 % of pairs. The plainest form of the
  same fact: **the most abundant tree type is different from the unwarmed one in a quarter of all
  cell-and-climate combinations.** There is real movement here to explain or fail to explain; a
  skill score on a quantity that never moved would be unreadable however good it looked.
- **The question is answerable, and the result will be readable when it arrives.** The strongest
  information-free competitor explains 0.178 of the movement, the next one 0.034 — a gap three times
  wider than the corresponding one in the already-sealed warming-response test, so the test can say
  *which kind* of skill a model demonstrated rather than merely that it beat something. A perfect
  predictor could reach 0.864, not 1.0, because the model being emulated is stochastic and the
  target is a difference of single runs. That ceiling is derived up front this time: the response
  test was sealed with a pass mark of 0.226 before anyone had computed that perfect was 0.870, and a
  pass mark with no ceiling beside it cannot be read as modest or impossible.
- **A test that the split of the competitor code changed none of its numbers.** The competitor
  values of an already-sealed experiment were measured by the pre-split code and nothing in that
  experiment's own files would go red if they drifted, so the equivalence is asserted directly.

### Fixed

- **A forest that disappears no longer counts as a forest that changed species.** The state
  summariser writes a share of zero for every tree type in a cell that has no stems left. Read as a
  change, that says "this type fell from 81 % of the stems to 0 %", which is not a shift in the mix
  — there is no mix — and it is the same collapse the stem count already scores in full. Left in, it
  inflated the total movement being scored by 15–18 % on most types and would have let a model buy
  apparent species-shift skill by predicting die-off. Those cells are now blanked, as the trait
  medians already were, and the 542 dropped pairs of 5,800 are reported rather than absorbed.
- **Every competitor is now scored on the same set of pairs.** The shared skill function builds its
  denominator from the rows where the *prediction* exists, so a competitor that declines to answer
  on the hard rows was scored on an easier subset than its rivals. That is harmless in the sealed
  response test but not here, where 9.3 % of pairs are undefined and cluster in the 17 cells that
  are already treeless before any warming. A missing prediction is now filled with "no change" — the
  neutral filling, and the one that keeps the do-nothing competitor pinned at exactly zero — and the
  number of fills is reported for each competitor.
