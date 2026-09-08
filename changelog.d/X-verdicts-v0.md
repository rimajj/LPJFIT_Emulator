### Added

- **Both verdicts, both FAIL, and every null returned its pre-registered value** — so neither is `invalid`: the apparatus did exactly what was declared and these are clean failures of the model, not of the measurement.
- **The map test**: the emulator reaches 0.0361 of cells inside the acceptance band on all 22 quantities at once, against 0.0212 for the climatically nearest analogue and 0.0187 for the nearest cell. It beats every null by 1.7×, but the gate asked for a margin of 0.050 and it delivered 0.0149.
- **The kill test**: −0.727 against 0.000 for predicting no change. Diagnosed rather than merely reported — stem count carries real response skill (+0.35) and leaf area some (+0.10), while soil carbon is four times worse than nothing, because the response is obtained by DIFFERENCING two level predictions and that only works where the true change is large compared with the level error. Record: `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
- **The pre-declared 5° sensitivity check turned out to be load-bearing**, not a footnote: at 5° blocks the address null flips from −0.142 to +0.120 on the response and would trip the no-power rule. The 15° primary is what makes the result mean anything.

### Fixed

- **A falsy-zero coercion in the verdict engine reported a clean `fail` as `invalid`.** `x or default` treats a legitimate 0.0 as missing — and 0.0 is exactly what an analytic null is built to return, so the no-change null dropped out of the comparison and the next null's margin was measured against a negative arm: 0.0162 was computed as 0.1586. Every comparison in `tools/_experiments.py` now tests `is not None`.
