### Added

- **A usable test for the restart file the emulator writes, replacing the one that could not tell
  anything apart.** The old test asked, for each cell and climate, a yes/no question — is the forest
  in the file within tolerance on all 22 measured properties at once? — and almost nothing ever
  was, so every comparison predictor scored within 0.004 of zero and pure chance tied for first.
  The new score keeps the same tolerance (10 % or the model's own run-to-run difference, whichever
  is larger), keeps all 19 properties that vary (the three fine-root-conductivity percentiles are
  the same 0.02 in every run on this corpus, so they are left out, and the test refuses to run if
  they ever vary) and all the climates, and still judges each forest by its single worst property;
  it only records *how far* outside the tolerance that worst property is, instead of just
  "outside". The headline number is minus the logarithm of the typical (median) forest's worst
  error, measured in tolerances. The share of forests fully inside the tolerance is still reported
  beside it, next to what a perfect emulator of the model's average would score.

- **Measured: the new score does rank the comparison predictors, in the order physics expects.**
  On the 200-cell, 30-climate constant-CO₂ pilot, with a second run of every spin-up now available:
  the cell's own unchanged forest is best (its typical worst property is 8.8 tolerances off), then
  copying the most similar climate anywhere (10.5), the same climate elsewhere (12.0), the nearest
  cell (12.4), the average forest (21.7) and a random cell (33.6). The same order holds on the
  retired test's own inputs, whose old numbers were reproduced exactly first. One of the model's
  own two runs, scored against the average of the two, is 1.2 tolerances off on its worst property
  and fully inside the tolerance for only 37.5 % of forests. That is roughly what a perfect emulator
  of the model's average would score. It is not what an independent rerun of the model would
  score: that is the owner's pass reference from 2026-09-24, it would score lower, and measuring it
  needs a third run.

- **The test is pre-registered and sealed** (`X-20260924-restart-worst-quantity`) before the
  emulator's restart files were scored: to pass, the forest read back from the emulator's file must
  be typically within 6.3 tolerances on its worst property, against 8.8 for leaving the cell's
  forest unchanged. The emulator's side has not been run yet.

- Shared scoring pieces for every test: one function for the "what does one real run of the model
  score" ceiling, a tolerance taken from the same cell's other climates (so a run can never pass simply
  because the tolerance was built from itself), and a combined set that adds the seven tree-type
  shares, each with its own measured floor, always reported beside the plain 22-property number.

### Changed

- Loading a scenario leg now refuses one whose two "independent runs" are the same run twice
  (byte-identical or identical in content) — the known case is the high-emissions leg of the first
  corpus — unless the caller explicitly allows it. The two older, closed analyses that read that
  leg use only its average and build no tolerance from it, so they now pass that permission and
  compute exactly what they did before.
- The sentence that states the basis of a number no longer always says "level"; the caller states
  whether it is a level or a ratio. Existing sentences are unchanged.
