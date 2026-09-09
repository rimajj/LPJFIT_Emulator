### Fixed

- **The corpus builder now refuses a leg whose "two runs" are one run twice, instead of quietly
  writing it down.** The stored ground truth is supposed to hold two independent runs of the
  vegetation model per scenario, and the gap between them is what tells us how much of a difference
  is just the model's own randomness — the accuracy target is "within 10 %, *or* within the model's
  own run-to-run spread, whichever is wider". One of the three scenarios never had two runs: the
  second job restarted from the first job's saved state, and the model takes its random numbers from
  the state file it starts from, so it reproduced the first run exactly — same file size, same
  checksum, same recorded random-number seeds, identical numbers in all 76 quantities and all 67,420
  grid cells. With no gap between the two runs, "10 % or the model's own spread" silently becomes a
  flat 10 % while still being described as the wider of the two.

  That defect was recorded accurately in the build's provenance file and read by nobody, while three
  sealed analyses went on to cite the corpus. So the check is no longer advisory: the build now
  compares each scenario's two runs on **two independent signals** — the recorded random-number
  seeds (the cause) and the decoded numbers themselves (the effect) — and if either says the runs
  are not two runs, it **withholds the corpus fingerprint**. That fingerprint is the only handle an
  analysis can cite, so a corpus that fails cannot be registered against at all. The provenance file
  is still written, with the fingerprint it *would* have had and the reason it was withheld, so the
  failure is diagnosable rather than merely fatal. A run that grows no overlapping grid cells is
  also a failure, not a pass — comparing nothing is no evidence.

  Replayed against the existing corpus, the check reproduces the known result exactly: the
  historical and low-emissions scenarios differ between their two runs in 63,372 and 63,586 of
  67,420 cells and pass; the high-emissions scenario differs in **0** cells and is refused on both
  signals. The genuine second high-emissions run does exist on disk, in a third directory, and is
  a different file size written three weeks later — but wiring it in needs a path entry in the
  integrator-owned config, and it came from a later build of the model than its partner, which has
  to be disclosed. Until then the map entry carries a warning at the point of use and the build
  fails on that scenario. Records: `docs/decisions/20260908-X-ssp370-has-no-second-seed.md`;
  tests in `tests/test_corpus_seed_gate.py`.
