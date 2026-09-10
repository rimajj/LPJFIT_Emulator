### Fixed

- `scripts/sbatch_py.sh` recorded no campaign ledger row when the caller's shell had the system
  `python3` on its path. The row was written with bare `python3`, and the tool that writes it needs
  Python 3.11; on 3.9 it died with a traceback *after* the job was already queued, so the
  submission printed success and the run went unrecorded. It now uses the configured cluster
  interpreter and exits non-zero, with the recovery command, if the row cannot be written.
- `scripts/sbatch_py.sh` could not submit a script that takes no arguments: the argument list was
  built with `printf '%q ' "$@"`, which emits one empty quoted argument when there are none, so
  the job died in five seconds on `unrecognized arguments:`.
- An `EXPECT` containing spaces was word-split into several positional arguments to the ledger
  writer instead of being passed as one value.

### Added

- `scripts/screen_d95max.py`, which screens candidate fixes for the level model's rooting-depth
  heads against the conjunctive band test. The heads' error is shown to be mostly reducible rather
  than the model's own realisation noise, and its signature is shrinkage toward the middle of the
  range plus an unbounded target for a trait the model bounds to [51, 1800] mm. Arms are compared
  on three of the five blocked folds and the winner quoted on the other two.
