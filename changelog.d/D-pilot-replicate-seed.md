### Added

- **A second run of the same forests with a different random draw, so the model's own noise under a
  changed climate can be measured instead of guessed.** `scripts/corpus_pilot.py --seed N --subset M`
  reruns a subset of the pilot's cells and climates with only the model's random seed changed. It
  reuses the first run's climate files byte-for-byte rather than rebuilding them, so the difference
  between the pair is the model's own randomness and nothing else. 20 cells x 30 climates = 600
  spin-ups, about 67 core-hours, against the original pilot's 670.

  This is the measurement five open questions were waiting on. The project's acceptance rule is
  "within 10 %, or within the model's own run-to-run disagreement, whichever is wider" — and that
  disagreement has only ever been measured on today's climate, where it comes out at almost exactly
  10 %, i.e. no wider than the floor. Nobody has ever measured it on a forest driven to a warmer
  climate, which is the case the whole project is about.

### Fixed

- **The subset picks evenly spaced cells, not the first N.** The cell list is ordered south to
  north, so "the first 20 of 200" put every cell between 52 S and 27 S — one temperate band, no
  tropics and no boreal — and the quantity being measured is known to be largest in sparse forests.
  Caught by inspecting the first planned run; the replacement spans 52 S to 66 N across 20 separate
  regions. `tests/test_pilot_replicate.py` pins this, along with the two other ways a replicate can
  silently measure nothing: moving the original run's file paths, or rebuilding its climate inputs
  instead of sharing them.

- **A build that writes no climate files now says its no-op check did not run**, instead of
  reporting "all pass" over zero files checked. A check that cannot fail reads exactly like a check
  that passed.
