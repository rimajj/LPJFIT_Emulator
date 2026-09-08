### Added — line D

* **The corpus builder** (`src/vegemu/corpus/`, `scripts/corpus_build.py`). Per-cell state
  summaries read straight out of the restart files — counts, stocks, the growth-failure counter,
  the height distribution, PFT composition and five quantiles of each of eight per-stem traits —
  and per-cell 30-year climate summaries read out of the `.clm` forcing. Both seeds of all three
  legs, so the acceptance tolerance (the model's own two-seed spread) is measured rather than
  assumed. Provenance, including each source file's decoded header, ships with every table.
