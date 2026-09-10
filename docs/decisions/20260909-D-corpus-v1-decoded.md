# The pilot corpus is decoded, it validates against the global truth, and 17 of its 200 control points are deserts

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** D
- **Supersedes:** nothing. Completes `docs/decisions/20260909-D-pilot-corpus-v1.md` (the runs) by
  turning it into the table rung 1 is scored on.

⚠ **THIS RECORD IS ALSO A MESSAGE TO LINE X**, for the same reason the previous one was: the one
sanctioned cross-line channel, `tools/inbound.py`, cannot commit and pushes a recipient at its
120-line budget over it, which reddens `budgets` and stops **every** line's merge. Read §"For
line X" — one item there changes what rung 1's decisive null measures.

## What now exists

`/p/tmp/jamirp/vegemu/corpus/pilot-v1/corpus.parquet` — **6,000 rows × 181 columns**, one row per
spin-up, all 6,000 decoded, **0 failures**, 8.9 s on 16 processes.

| | |
|---|---|
| identity | `corpus_sha256 fbe74ed2416b265f4c874959ab8b186679a641cedf3e18df32b125f7362e1e4d` |
| plan it realises | `plan_sha256 bad787ade3fc609b25cf8ebc87dfd0978e4a8690` |
| keys | `name, cell, point, kind, tile, stage, seed, leg, state_year` |
| the climate, as coefficients | `dtemp_k, fprec, sprec, frad, fiav` — the design point, so a row's climate is recoverable from the row alone |
| features | **86**, `vegemu.corpus.climate.CLIMATE_FEATURES`, computed from that run's **own** perturbed forcing |
| targets | **76**, `vegemu.corpus.state.STATE_COLUMNS` less `cell` |
| never features | `cell`, `lon`, `lat` (the address is a pre-registered null) and `truth_stems_total` (a lagged truth, carried only for the check below) |
| report | `decode.json` beside it; driver `scripts/corpus_pilot.py --stage decode` |

Each row's features summarise the **actual** forcing that run read, not the baseline plus a recipe —
that is what makes a row a (climate → state) pair on its own terms, which is the estimand.

## The corpus reproduces the global ground truth — measured, not assumed

`MEMORY.md:subset-diverges` records that a subset re-run of LPJmL-FIT is *not* a per-cell replica of
the global run (one cell diverges at the first step) and says never to score a subset re-run against
global truth. Every one of these 6,000 runs is a single-cell subset run. So how far the corpus
drifts from the model it is supposed to emulate was an **open, unmeasured risk**, and the control
design point — whose forcing is byte-identical to the historical baseline — is what measures it.

Two results, over the 200 control runs against the stored global `restart_1999`:

- **The perturbation writer is exactly neutral at the summary level too.** Annual temperature,
  precipitation and radiation of every control run agree with the selection table built from the
  source forcing to **max absolute difference 0.0**, all 200 cells. Byte identity was already
  checked at write time; this is the same claim surviving a completely independent read path.
- **Where the control grew a forest, it is the same forest.** Over the 183 controls with stems:
  Spearman **0.961**, Pearson **0.975** on stem count, and the control/truth ratio has median
  **1.023** with p10/p90 **0.839 / 1.231**. So a single-cell 1000-year subset spin-up lands within
  about ±20 % of the global run's stem count with no detectable bias.

That is a stronger agreement than `subset-diverges` guarantees, and it is the first evidence that
this corpus and the ground truth describe the same model. It does **not** license scoring a subset
run against global truth — divergence is real and the tolerance is unquantified beyond the above.

## The finding: 17 of the 200 control points grew nothing, and it is two different problems

The control is the one design point that *should* reproduce the truth, and at 17 cells it is empty
while the truth has 101–1,746 stems. They split cleanly:

**Group A — 14 cells that are deserts, and the model is right.** `dry_months = 12` (all twelve
months under 30 mm), aridity **0.0001–0.014**, restart at exactly the 360,275 B vegetation-free
floor, and **soil carbon exactly 0.0** — nothing grew in 1000 years, not even litter. The driest
controls that *did* grow trees sit at aridity **0.010–0.021**, so LPJmL-FIT's spin-up flips between
desert and sparse forest across a threshold near aridity ≈ 0.015, and these 14 sit at or under it.
**15 of the 200 selected cells have under 50 mm/yr of rain**, minimum 0.42 mm/yr; 13 of the 14 are
`maximin` picks. This is design rule 4 ("deliberately span beyond today's envelope") working as
specified, with a consequence nobody costed: at the dry extreme the protocol's own spin-up
equilibrium is bare ground while the stored truth carries sparse forest.

**Group B — 3 cold, wet, bistable cells** (98, 54601, 64590; aridity 0.22–4.08, `dry_months` 0).
These have **real soil carbon, 13.7–17.9 kgC/m²**, so vegetation lived and died. They are not
deserts, they are cells where the outcome is not determined by the climate: cell 98's control is
empty, yet **22 of its other 29 climates are forests**, up to 1,332 stems against a truth of 1,457.

## For line X — what this changes about rung 1

1. **The same-cell baseline null is evaluated at the control point, and at 17 of 200 cells that
   point is bare ground.** So at 8.5 % of cells the decisive null predicts a desert while the
   perturbed legs are forests, and *any* model that predicts "some forest" beats it there by the
   full range of the target. The null does not become invalid, but its margin is inflated by a
   subpopulation that has nothing to do with a warming response, and the pre-registration should
   say which basis it reports on: all 200 cells, or the 183 whose control is a forest. **Report
   both.** Pre-registering only the all-cells basis would let a 17-cell artefact carry the verdict.
2. **The conjunctive-band basis has a floor problem in the same 17 cells.** Every trait quantile is
   NaN where there are no stems (`_empty_summary`, deliberately — a zero median is a lie a model
   will happily fit), so a per-cell conjunctive test over 76 quantities is undefined there. Decide
   whether a treeless cell passes, fails, or is excluded, and state it in the pre-registration.
3. **6.3 % of all 6,000 rows are treeless** (380), against 6.2 % from the restart-byte proxy — so
   the proxy in the harvest stage was very nearly right. The treeless rate peaks at 34/200 on design
   point `lhs03` (−0.73 K, 0.67× precipitation) and is 17/200 at the control, i.e. drying is what
   empties cells, not warming.
4. **`truth_stems_total` is in the table and is a lagged truth.** It exists for the check above. A
   model that saw it would score beautifully on a held-out cell. Exclude it explicitly.

## Two bugs this work found and fixed

- **A subset `.clm` file's cell number was read as a row number.** `climate_table` indexed the
  global soil-depth and grid-coordinate files by row, which is correct only when `firstcell = 0`.
  Every global input has `firstcell = 0`; the perturbation writer's single-cell files carry
  `firstcell = <that cell>`. So the whole corpus would have been given **cell 0's soil depth and
  cell 0's latitude**, with no error raised anywhere. Corpus v0's tables are byte-unchanged by the
  fix, because for a global file the two indices are the same array.
- **polars does not survive `fork`.** A forked worker that touched a DataFrame hung forever with no
  error and no traceback: the first attempt at this decode burned its wall-clock limit having
  produced nothing. `vegemu.corpus.state` already avoided this by returning dicts from workers and
  building the frame in the parent; `climate.py` now exposes `climate_columns` (numpy only,
  fork-safe) with `climate_table` as the parent-only wrapper, and the rule is written at both call
  sites. Decoding went from >8 s per run to 0.0015 s per run.

## What line D does next

Rebuild under a **new corpus version** for the two known corpus changes — the high-emissions leg's
missing second seed (`docs/decisions/20260908-X-ssp370-has-no-second-seed.md`) and putting
`pft_frac_*` in the scored set (line T's ask). A changed corpus is a changed question, so neither
touches v1's hash or anything citing it. The 17 control points are **not** a reason to re-select
cells: 14 of them are the model being right about a desert, and dropping them would quietly narrow
the very envelope the design set out to span. One row is worth adding to `MEMORY.md`, which only the
integrator may write: the subset-vs-global agreement above bounds `subset-diverges` for the first
time.
