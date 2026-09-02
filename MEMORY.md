# MEMORY.md — cross-cutting durable facts (budget: 120 lines, enforced)

One fact per row. **Prose rows are rejected by the `budgets` gate** — the row format is structural, so
this file cannot become a narrative. Anything line-specific goes in `lines/<L>/STATE.md`; anything that
is a procedure goes in a skill; anything deep goes in `docs/reference/`.

Row format: `| id | fact (≤200 chars) | source | verified |`
Rows whose `verified` date is >90 days old and which no ADR or experiment references are evicted by
`tools/rotate_memory.py` into `docs/reference/retired_facts.md`.

| id | fact | source | verified |
|---|---|---|---|
| co2-closed | The emulator does not see CO2 and must not respond to it; LPJmL-FIT runs constant CO2 deliberately because its own CO2 fertilization is unbounded with nitrogen off. Never propose a CO2 feature. | owner, standing | 2026-09-02 |
| licensing-closed | Reuse of LPJmL-FIT and the TUM-PIK-ESM models is authorised (owner is a member of both groups). Cite transparently; never re-audit upstream licences or raise the question. | owner, standing | 2026-09-02 |
| goal-spinup | Primary deliverable is replacing the 1000-year spin-up and producing equilibrium state under any climate. Speed inside an atmosphere is OUT of scope, superseding the predecessor's ordering. | owner, 2026-09-02 | 2026-09-02 |
| acceptance | Tolerance is max(10%, the model's own two-seed spread), on tree counts AND trait distributions AND trait medians, conjunctively, per cell. A mean score is not an acceptance test. | owner, predecessor ADR 0106 | 2026-09-02 |
| noise-floor | LPJmL-FIT is stochastic: two identical runs differ by up to 29% in low-density cells. Published per-cell floor approx Height 0.020, agb 0.113, npp 0.062, LAI 0.025. | predecessor, measured | 2026-09-02 |
| ident-limit | Within one scenario a cell's warming increment is 76.4% predictable from its own baseline climate, so response-to-warming and sensitivity-of-place are not separately identified in existing data. | predecessor ADR 0311 | 2026-09-02 |
| eff-sample | The effective independent spatial sample is ~161 populated 15x15deg tiles (312 at 10deg, 957 at 5deg), not 54020 cells. Row counts overstate independent evidence by ~4 orders of magnitude. | predecessor, measured | 2026-09-02 |
| extrap-cells | 95.1% of cells' 2090s temperature is inside today's tree-cell range; 4.9% (~2600 cells) exceed the hottest tree cell today, and space-for-time is sign-wrong in the 3.7% genuinely extrapolating. | predecessor, measured | 2026-09-02 |
| ind-censored | The per-tree text output drops every stem at or below 5 m height, so it is a censored view of the roster and CANNOT be inverted into a restart file. Our own corpus targets restart files instead. | fwriteoutput_ind.c:122 | 2026-09-02 |
| ind-gpp-fake | The per-tree table's `gpp` column is a copy of `npp` (daily_natural.c:193 does agpp += npp). LPJmL-FIT has no per-individual GPP; a per-stem carbon-use efficiency comes out exactly 1.0000. | predecessor ADR 0130 | 2026-09-02 |
| subset-diverges | A subset re-run of LPJmL-FIT is not a per-cell replica of the global run: 1 cell diverges at the first step, a 21-cell block after 15 years. Never score a subset re-run against global truth. | predecessor ADR 0041 | 2026-09-02 |
| build-provenance | Existing ground-truth legs are split across a Feb-5-2026 and an Aug-12-2026 binary build; the low-emissions leg is confounded by two intervening rebuilds. Gate build provenance before using any leg. | predecessor ADR 0310 §7 | 2026-09-02 |
| bad-years-counter | Each tree has a consecutive-bad-growth-years counter that hard-kills at 5; ~10.5-13.7% of stems carry 42-46% of mortality mass; averaging it away reverses trait selection in 3-4 of 7 tree types. | predecessor ADR 0093/0311 | 2026-09-02 |
| counter-recoverable | That counter is exactly recoverable from the printed 29-column table by algebra: exact-integer agreement 1.000000 on 694662 stem-years against a counter=0 null of 0.878. | predecessor ADR 0311 B1 | 2026-09-02 |
| bernoulli-floor | ~2.4% of next-year count variance survives lag-1 and is the model's own per-patch Bernoulli noise; the exact floor is ~28% of residual variance. Single-draw R2 barely discriminates arms. | predecessor, measured | 2026-09-02 |
| target-is-expectation | Because of bernoulli-floor, the correct target is the ensemble expectation/distribution, not a single draw. No rung may be guarded on an R2 floor alone. | derived from bernoulli-floor | 2026-09-02 |
| restart-size | A restart record is ~1.9 MB/cell at 25 patches (min 360183 B vegetation-free, median 2216864, max 3546287); the global file is 119 GiB for 67420 cells. | measured on restart_1999.lpj | 2026-09-02 |
| restart-safe-abort | The C build has -DSAFE: it aborts a cell if the water balance exceeds 1.5 mm/yr. An inconsistent synthesised state therefore fails loudly rather than silently. | check_fluxes.c | 2026-09-02 |
| restart-no-checksum | The restart reader validates version, float size, cell size and the landuse/river/individual flags, but has NO checksum, NO build stamp and NO parameter-file hash. The year is a warning only. | openrestart.c | 2026-09-02 |
| netcdf-cmp | Never `cmp` two LPJmL NetCDF outputs: a wall-clock timestamp goes into the `history` attribute, so identical physics differ in bytes. Compare DECODED variables. | predecessor ADR 0043 | 2026-09-02 |
| c-log-truth | Never judge a C run from its scheduler exit code: the stock job files always exit 0. Require the model's own line `lpjml successfully terminated, <n> grid cells processed.` in a NON-EMPTY log. | predecessor, measured | 2026-09-02 |
| hainich-cell | The prototype cell Hainich is 0-based index 42490 in the orderA grid used by all ground truth. Index 28008 is Hainich in a DIFFERENT grid and is the Sonoran desert in orderA. | predecessor ADR 0083 | 2026-09-02 |
| positive-evidence | A direct 20-yr-climatology to 20-yr-state map beat a coordinates-only null under SPATIALLY BLOCKED folds by +0.162 to +0.715, and climate subsumed the address. Evidence for our estimand. | predecessor ADR 0311 | 2026-09-02 |
