### Added

- `docs/reference/band-test-ceiling.md` — what the conjunctive band test can actually attain, and
  what each scored quantity is worth against that rather than against perfection. The headline: a
  tolerance derived from the same two model runs that define the truth is passed by any predictor
  of the run-to-run average, by arithmetic, so the apparent ceiling of "every cell passes" is not a
  measurement. Taking the tolerance from a different climate scenario instead puts the attainable
  score at 0.5585, against the emulator's 0.0351 — so the emulator is at 6 % of what is reachable,
  not 3.6 % of perfect. No single quantity is worth more than +0.0084, and seven of the twenty-two
  made perfect still leaves 89 % of cells failing.
- The emulator can fit one predicted quantity differently from the rest — on a bounded scale, or
  against absolute rather than squared error — where the quantity's own structure calls for it.
  Measured for rooting depth and **shipped switched off**, so the model is byte-identical and no
  published number changes meaning.

### Fixed

- The job submission wrapper recorded nothing in the campaign ledger when the caller's shell had
  the system Python on its path: the record was written by an interpreter too old for the tool that
  writes it, and it failed *after* the job was already queued. The submission printed success and
  the run went unrecorded. It now uses the configured interpreter and refuses quietly-succeeding
  failure.
- The same wrapper could not submit a script that takes no arguments at all — the job died in five
  seconds on an empty argument the wrapper itself inserted.
- A message from one work line to another no longer spends the recipient's file-length budget.
  Charged to the recipient, it meant any line could turn the whole repository's build red by
  telling another line something, and the recipient could neither pre-empt nor quickly fix it. It
  had already cost one real message, which is resent with this change.
