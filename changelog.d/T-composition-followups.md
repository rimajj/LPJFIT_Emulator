### Changed

- **INTEGRATOR ASK — one `MEMORY.md` row is now misleading about timing.** The `composition-scored`
  row says the species mix "becomes predicted and conjunctively scored at corpus v2". Both halves
  are true of the eventual conjunctive band test, but read together they say nothing can happen
  until the next data rebuild — and that is wrong: the species response is measurable **today** on
  the existing perturbation runs, scored as a change rather than conjunctively, and it has been
  measured. A session reading that row would wait for a rebuild it does not need. Suggested
  replacement text for the same row, same columns: "pft_frac_\* is scored as a RESPONSE on the pilot
  ensemble now (apparatus derived 2026-09-14, best null 0.178, ceiling 0.864); conjunctive band
  scoring still waits for corpus v2. The synthesiser COPIES it from the template either way, so an
  emulated warmed forest cannot shift species until that changes."

### Added

- **A way to prove the species-mix model's plumbing without running it.** The scored model must not
  be run before its question is formally sealed, but its first run should not also be the first time
  the code has ever touched real data — a misalignment between the inputs and the targets looks
  exactly like a model with no skill, which is the one result this test must never produce by
  accident. A dry run now checks every shape, alignment and leakage assertion and stops before
  fitting anything, so it cannot compute the result or leak it. It passes: 96 inputs over 200 cells
  and 29 climates, 5,258 scorable pairs matching the apparatus exactly, and the 17 cells that have
  no forest even before warming correctly carrying "no value" rather than "zero".
