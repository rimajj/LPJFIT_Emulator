# Line D — data: binary formats, corpus generation, provenance

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/D/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py D` when it fills.

## Scope

Everything that reads or writes LPJmL-FIT's own file formats, and the corpus that comes out of them:
the restart reader/writer, the `.clm` reader/writer, the output writers, corpus generation, the
perturbation design, the spin-up campaigns, provenance. Not line D's: models and training (T),
pre-registrations and verdicts (X).

## NEXT — start here

**Rung 0 is DONE and merged.** Both binary formats round-trip byte-identically against real files
(100 restart cells spanning 360 KB to 3.5 MB; two whole `.clm` inputs entire; the 11.7 GB forcing
files piecewise). Spec: `docs/reference/binfmt.md`. Corpus v0 is at `scratch.corpus/v0` with
`corpus_sha256 d1230d0b…`, covering all three legs and both seeds; two experiments are sealed
against that hash.

**Two measurements changed the plan, both already recorded:**

* **The 1000-year spin-up has NOT converged** — 890 Pg C at year 1000 against 735 at year 500,
  still rising at +6.5 %/century, both seeds agreeing to 0.07 %. So the hoped-for 3.3× cut to every
  corpus budget is refuted, and "equilibrium" is the wrong word for the target: it is the state the
  standard spin-up protocol reaches. `docs/decisions/20260908-D-spinup-is-not-converged.md`.
* **The noise floor, measured:** the two-seed spread of end-of-spin-up vegetation carbon is 3.41 %
  at the median, 13.6 % at p90, 42.4 % at p99 across 61,700 vegetated cells. The 10 % floor binds
  in most cells; the two-seed term binds in the tail.

**Next, in order:**

1. **D1 — the `.clm` writer round-trips but has never written a PERTURBED file.** That is the next
   real step and nothing blocks it. Build the delta-change perturbation design (the five axes in
   `PLAN.md`, relative humidity held fixed under warming, constant CO₂ always) and generate ONE
   perturbed 30-year forcing set for a handful of cells. Then run the C model on it and confirm the
   state moves in the expected direction. A perturbed file the model reads without complaint is the
   whole of D1.
2. **D2 — the pilot corpus, now MANDATORY rather than an optimisation.** The kill test failed on
   existing data precisely because it holds one climate per location, so 200 cells × 30 climates ×
   1000 years is the only identified path to a warming response
   (`docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`). Budget unchanged at
   ~670 core-hours; the spin-up cannot be shortened.
   ⚠ Build every run config with `scripts/corpus_cmodel_config.py`, which patches the ground
   truth's own saved configuration and ASSERTS every replacement. A fresh config would be a second,
   unvalidated configuration whose differences from the truth nobody has enumerated. That assertion
   already fired once, on the one key with a trailing comment and no comma.
3. **A cheap fix already scoped:** the emitted restart file loads and runs in the real model but
   carries about half the right carbon, because donors are matched on height and wood density only.
   The change is line T's; line D owns the verification run, and a 20-cell one-year subset run
   costs 8 seconds.

⚠ **`origin` points at the PREDECESSOR's GitHub repository** (`rimajj/LPJFIT_Emulator`) and shares
no common ancestor with this history, so `tools/merge.sh` cannot run and nothing has been pushed.
Every line is merged into LOCAL `main`. This needs an owner decision before any line pushes.

Housekeeping: none owed. Every campaign in `campaigns/D/ledger.jsonl` is harvested.

## Milestones

**D0 — restart-file round-trip. DONE**, and the `.clm` reader/writer with it. The per-stem field map
is cross-checked against a number this repo did not produce: `height` puts 51.4 % of Hainich's stems
above the per-tree writer's 5 m cut, against ~47 % measured independently in the predecessor.

**D0b — the C-model launch path. DONE.** `scripts/sbatch_cmodel.sh` (pre-flight and run),
`scripts/corpus_cmodel_config.py` (asserted config patching), `scripts/corpus_restart_subset.py`
(the byte-exact control arm). A 20-cell one-year run from the real restart completes in 8 seconds
and prints the model's own completion line.

**D1 — the perturbed `.clm` writer (OPEN, unblocked).** See NEXT.

**D2 — the pilot corpus (OPEN, blocked on D1).** 200 cells × 30 climates.

**D3 — provenance. PARTLY DONE.** Every corpus table ships a `provenance.json` with each source
file's size, mtime and decoded header, plus the `corpus_sha256` a pre-registration cites.

## Line D gotchas

* **A byte-identical round-trip validates a LAYOUT, not a CROSS-REFERENCE.** The last byte of a PFT
  entry is an index into that patch's litter list; it is self-consistent inside any one record, so a
  round-trip cannot see it, and it breaks only when a stem moves between patches. The only test that
  found it was running the real model. Any field that indexes into another part of the same record
  needs its own check.
* **Never judge a C run by its exit code**; require the model's own line `lpjml successfully
  terminated, <n> grid cells processed.` in a non-empty log. The wrapper writes that grep into the
  ledger row as the harvest command.
* The `.clm` size check the C only warns about (`WARNING032`) is a hard refusal here: a size
  mismatch means the dtype or the year count is wrong and every value read is silently shifted.
