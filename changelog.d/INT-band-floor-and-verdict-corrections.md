### Added

- **The acceptance test can now judge quantities that live near zero.** Tolerance here is a
  percentage of the true value, which works for quantities like biomass but collapses for a share:
  a tree type that makes up 0.2 % of a forest's stems gets a tolerance of 0.02 %, and nothing can
  land inside it — not the emulator, and not a second run of the simulator being emulated. The test
  now also carries a minimum tolerance in the units of the quantity itself. **The value is measured,
  not chosen:** it is how much the simulator disagrees with itself, from one run to the next, in
  90 % of cases — 0.0384 in share units, against a typical disagreement of 0.0027. Raising such a
  threshold after seeing the results is not a threshold, and the code says so beside the number.
- ⚠ **It deliberately has no default value, and every place that computes a tolerance now has to
  say which one it wants.** A minimum expressed in *shares of stems* is meaningless for soil carbon
  and merely wrong for leaf area, so a default would quietly apply a figure measured for one
  quantity to every other. The five existing places all ask for none, which reproduces every
  previously published number exactly — checked to the last bit, not approximately, and locked down
  by a test so that adding a convenient default turns the suite red.

### Fixed

- **Three published results stated their setup wrongly, and now say so in the same paragraph.**
  Each described the simulations behind it as run at constant carbon dioxide. They were not: the
  1,000-year warm-up runs against a changing carbon dioxide record, so its last 300 years carry the
  real historical rise of about a third. Two of them additionally said the warm-up "had not
  settled", which was withdrawn in September — that apparent drift was the response to rising
  carbon dioxide, and with it held fixed the curve is flat.
- **No result changes, and the reason is worth stating.** Every run in the set shares the identical
  carbon dioxide path, so it is the same for every comparison and cannot favour one over another.
  What the error genuinely breaks is the word *equilibrium*: what these results describe is the
  forest the standard warm-up reaches *through* the historical carbon dioxide rise, not the forest a
  climate would eventually support. Re-running them against the newer set built with carbon dioxide
  held fixed remains outstanding.
- **The correction is attached to the wrong sentence rather than filed elsewhere**, so the mistaken
  claim cannot be read without it. The original sealed plans keep their original wording and were
  deliberately not edited — they are the record of what was promised in advance, and editing them
  after the fact would destroy the thing that makes them worth having.
