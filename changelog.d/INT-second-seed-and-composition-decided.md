### Changed

- **`ground_truth.ssp370_seed2` now points at the genuine second run**
  (`…_random_seed2_from_hist_seed2`, verified complete on disk 2026-09-14, restart 133,580,962,759 B
  vs seed 1's 133,559,375,490 B). The bit-identical clone it used to point at is retained as
  `ssp370_seed2_INVALID_CLONE_OF_SEED1` — three sealed pre-registrations cite corpus hashes computed
  against it, so it stays resolvable as provenance and is an input to nothing. Repointed rather than
  added beside, because the original bug was silent and leaving the obvious key poisoned keeps it
  armed. ⚠ The corrected pair straddles a binary build boundary (Feb-05 / Jul-21) and that must be
  disclosed with every number derived from it.

### Decided

- **Species composition (`pft_frac_*`) becomes a predicted quantity and enters the conjunctive
  scored set at corpus v2.** Not a scoping question: the synthesiser copies composition from the
  template because nothing scores it, and a copied composition cannot shift — so an emulated warmed
  forest is currently forbidden from changing its species mix at all, which is the one thing the
  warming test most needs it to do. ⚠ Widening a conjunction can only lower the pass rate; v2 numbers
  must be reported beside the v1-scope number on the same model, with a re-measured ceiling arm.
- Both changes land in **ONE** corpus rebuild. Record:
  `docs/decisions/20260914-INT-both-open-corpus-decisions-are-answered-by-the-owner.md`.
