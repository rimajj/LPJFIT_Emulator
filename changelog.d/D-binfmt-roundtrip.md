### Added — line D

* **The LPJmL-FIT restart reader and writer** (`src/vegemu/binfmt/restart.py`). Rung 0 passes: 100
  real cells spanning 360 KB to 3.5 MB read out of the 119 GiB ground-truth file and written back
  **byte-identically**, plus a property test over the four variable-length parts (the litter list,
  the per-stem PFT list, the two 20-year ring buffers, the sapling pool).
* **The `.clm` reader and writer** (`src/vegemu/binfmt/clm.py`). Two whole real input files
  round-trip byte-identically; the 11.7 GB forcing files are proven piecewise (header + one year's
  raw block). The mixed-version trap is now an executable assertion rather than a comment.
* **`docs/reference/binfmt.md`** — the field-by-field spec, each field naming its C source.
* `src/vegemu/paths.py` — resolved access to `config/paths.yaml` from inside the package.
