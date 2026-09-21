### Changed

- **The two big positive results were re-measured on a corrected set of simulations, and both
  held up — slightly better than before.** The earlier runs had been done on forests that were
  still growing in response to rising CO₂ in the air, rather than settled forests. That matters,
  because a settled forest under a given climate is exactly what this tool is meant to predict.
  Re-running everything with the CO₂ held fixed produces forests holding **24 % less carbon** —
  genuinely different forests, not the same ones rescaled — so there was no way to know the
  earlier answers would survive without redoing the measurement.

  **They did.** Predicting how a forest changes when its climate is shifted: **0.559**, where
  anything above **0.258** counts as a real result and a perfect predictor could reach about
  0.849. Predicting how the *mix of tree species* shifts: **0.446**, against **0.300** to count
  and about 0.863 for perfection. Every one of the fourteen deliberately-stupid comparison
  predictors returned precisely the value written down in advance, so neither result is an
  artefact of a broken measurement.

  **What this buys.** The claim that the tool can learn a warming response now applies to settled
  forests, which is the thing it is for — before, it applied only to forests caught mid-adjustment.
  And the decision to teach it to shift species composition, which the training work is currently
  built around, was not driven by a CO₂ side-effect. That was a real risk rather than a formality:
  more CO₂ in the air does not help all tree types equally, so a rising-CO₂ run reshuffles the
  species mix by itself, and some of the earlier result could have been that rather than climate.

- **The two bars the results are judged against were recalculated from the new simulations, so
  they moved in opposite directions** — the climate-response bar rose, the species-mix bar fell.
  Each result must be read against its own bar; the two headline numbers are not comparable to
  each other, and neither are the old and new numbers without their bars attached.

### Fixed

- **A tool was about to feed the model far more information than the earlier version of the same
  test had been given**, which would have made the two impossible to compare while looking like a
  like-for-like rerun. It was caught because the extra information included a column of text the
  arithmetic could not accept, so the job crashed instead of quietly producing a flattering
  number. The three affected runs are recorded as failures with that reason.

- **Two scripts had numbers from one particular experiment baked into them**, so running them on
  anything else printed the wrong reference value beside a correct result — in one case printing
  an old pass mark directly underneath a newly computed one. Both now take those values as
  arguments and print where they came from. Existing uses are unchanged to the last digit.

### Known issues

- **An experiment that has been formally registered cannot afterwards be marked as abandoned.**
  One rule says to record the reason in the registration document; another refuses any edit to a
  registered document. For a registered experiment these cannot both be obeyed, so an abandoned
  one has no way to say so and will be reported as neglected 30 days later. Two such experiments
  hit that date on **2026-10-21**. Neither was ever run. The recommended repair, and the reason
  the easier repair should be refused, are written up in the decision record.

- **Whether a bookkeeping command is permitted depends on what a past job was named.** Recording
  that a finished job has been collected is refused if that job's name happens to contain the word
  "corpus", and allowed otherwise — the safety check is reading the name as evidence of heavy
  computation. It blocked five such commands in a row. Pinned as a known defect with a test;
  repairing it loosens a safety check, which is the owner's call.
