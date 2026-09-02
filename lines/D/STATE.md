# Line D — data: binary formats, corpus generation, provenance

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/D/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py D` when it fills.

## Scope

Everything that reads or writes LPJmL-FIT's own file formats, and the corpus that comes out of them:

* the **restart-file** reader and writer (`src/vegemu/binfmt/`) — the project's central deliverable
* the `.clm` forcing reader and **writer** (the writer is what makes a perturbed climate possible)
* the NetCDF and per-tree-table output writers
* corpus generation: the perturbation design, the spin-up campaigns, provenance
* `scripts/corpus_*.py`, `scripts/sbatch_cmodel.sh`

Not line D's: models and training (T), pre-registrations and verdicts (X).

## NEXT — start here

**Rung 0. Nothing else in the project can proceed until this passes, and it needs no model, no
science and no cluster job. Read `PLAN.md` and `docs/reference/inherited.md` §4 first.**

**The task: round-trip a real LPJmL-FIT restart file byte-identically.** Read one cell out of the
real 119 GiB file, write it back, `cmp`. Then 100 cells spanning the size range.

```
target  config/paths.yaml -> ground_truth.restart_spinup_end        (restart_1999.lpj, 119 GiB)
build   src/vegemu/binfmt/restart.py   +  docs/reference/binfmt.md  +  tests/test_restart_roundtrip.py
```

The format is already fully reverse-engineered and verified against that file — **the spec is in the
approved plan, transcribed into `docs/reference/binfmt.md` as your first act.** Key points:

* magic `"LPJRESTART"`, version **33**, `Real` = float64, `Bool` = int32, little-endian native
* a 40-byte generic header, then a 30-byte restart header **whose disk order differs from the C
  struct declaration order**, then `int64[ncell]` of **absolute byte offsets**, then the cell records
* per cell: 25 patches, each a 23-layer soil block + a litter list + a PFT list in which — because
  this configuration runs `individual: true` — **every single tree is its own 554-byte PFT entry**;
  then a 20-year climate buffer (containing *variable-length* ring buffers), then the sapling pool
* measured sizes: min 360,183 B (a vegetation-free cell), median 2,216,864, max 3,546,287

**Do it in this order, and stop at the first thing that fails:**

1. Header only. Decode the 84-byte prefix and the index array; assert `index[0] == 84 + 8*ncell` and
   `ncell == 67420`, `nbands == 22`, `individual == 1`, `datatype == 4`. Cheap, and it validates the
   whole framing before you touch a record.
2. One cell, read → write → `cmp`. Use the index to seek; never scan.
3. 100 cells across the size range. A vegetation-free cell and the densest cell exercise different
   branches (empty PFT list; a long one).
4. A property-based round-trip over *synthetic* records (`hypothesis`) for the variable-length parts —
   the ring buffers and the tree list are where an off-by-one hides. Mark the real-file tests
   `needs_real_data` so the suite still runs where `/p` is not mounted.

**Two measurements to take while you are in there**, both cheap and both change the corpus budget:

* the **real per-spin-up cost**, so `PLAN.md`'s 0.4 core-s/cell-year assumption stops being an
  assumption;
* the **actual convergence time of the spin-up**, from `ground_truth.spinup_trajectory_seed1`
  (`vegc_spinup_1999.nc`, a 1000-step global vegetation-carbon trajectory that is recorded in no
  predecessor document). If the forest is stationary well before 1000 years, every corpus tier in
  `PLAN.md` drops proportionally. This is the single highest-leverage number available right now.

**Do not** start the `.clm` writer, the perturbation design or any corpus run until the round-trip
passes. A corpus generated before the format is proven is a corpus that has to be regenerated.

Housekeeping: none owed — the line was bootstrapped complete. Refresh this block before you end;
a `Stop` hook blocks once if you commit without it.

## Milestones

**D0 — restart-file round-trip (OPEN, not started).** The gate above. Blocks everything.

**D1 — the `.clm` writer (blocked on D0).** Mirror of the header-driven reader. Round-trip every real
input file byte-identically before generating a single perturbed one; the format is version-dependent
and the scenario set is mixed (see `docs/reference/inherited.md` §4).

**D2 — the perturbation design and the pilot corpus (blocked on D1).** 200 cells × 30 climates,
~670 core-hours. Delta-change directions calibrated on the real scenario legs; relative humidity held
fixed under warming; constant CO₂ always. Cells stratified by the ~161 independent 15° tiles.

**D3 — provenance.** Per-shard `provenance.json` incl. the C binary's build date, and the corpus
manifest hash that a pre-registration cites. A corpus is immutable once cited.

## Line D gotchas

*(none yet — add them here, or promote a procedure to a skill)*
