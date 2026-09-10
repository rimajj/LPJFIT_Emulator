### Added

- **`scripts/synth_drift.py` — the drift scorer, with the null and the ceiling in the same table as the result.** Four twenty-year runs of the real model over cells 42480–42499 (20 of 54,020, temperate Europe, present-day, one task each): the emulated state, two control seeds that supply the tolerance, and a **third control seed that supplies the ceiling**. Without that third arm the result has no scale, because a band leg is inside its own band by construction. Record: `docs/decisions/20260909-T-t3-drift-fails-below-the-null.md`.

### Changed

- **The synthesised restart survives twenty years of the real model and fails the drift test below the null.** The emulated state fails **0 of 20 cells** inside `max(10 %, the two-seed spread)` on all 22 quantities at once, median 16 of 22.
- **The ceiling — a third run of the real model — is 25 % of cells, median 21 of 22.** So the test has power and this is a fail, not an uninformative metric. It also means the conjunctive test at year 20 is only about a quarter attainable on this block: any "N % of cells pass" needs the ceiling beside it.
- **The no-change null — handing the model back the true 1999 state — scores 0 %, median 18 of 22, and is closer to the control on 14 of the 22 quantities.** The emulated state is a worse description of year 2019 than the state it was built to replace.
- **No collapse and no runaway**, which is what this test existed to ask: block vegetation carbon grows ×1.34 against the control's ×1.21 and the block total closes from −10.6 % to −1.3 %. That closing is error cancellation across cells, not improvement — the per-cell median gap **grew**, 0.087 → 0.140, against the two controls' own 0.010 → 0.097.
- **The shortfall is exactly where the mechanism predicts:** leaf area (a real run 90 % of cells, the emulated state 15 %), the trait medians, and the low tail of rooting depth — all quantities the two-trait donor transplant does not control. Where the emulator beats the null is stems per patch and the height upper tail, the two things it actually predicts.
