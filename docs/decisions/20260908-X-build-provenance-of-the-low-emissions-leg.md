# The low-emissions leg is admissible: the build boundary it crosses contains nothing that ran

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** X
- **Governs:** `X-20260908-heldout-forcing-leg`; qualifies `MEMORY.md:build-provenance`
- **Gate discharged.** `lines/X/STATE.md` required build provenance to be settled *before* a
  pre-registration used this leg, on the grounds that a delta involving it "carries an unquantified
  confound". It is no longer unquantified. This record is what the gate produced.

## What the ground truth actually is

The restart files carry no build stamp (`MEMORY.md:restart-no-checksum`), so the authority is the
model's own log banner, `lpjml C Version 5.6.004 (<date>)`, in each run's stdout:

| leg / run | build | started from | in corpus v0? |
|---|---|---|---|
| historical, seeds 1 and 2 | **Feb 5 2026** | own 1000-year spin-up | yes |
| high emissions, seed 1 | **Feb 5 2026** | historical seed 1 | yes |
| high emissions, "seed 2" | **Feb 5 2026** | historical seed **1** — a duplicate | yes, wrongly |
| high emissions, seed 2 from hist seed 2 | **Jul 21 2026** | historical seed 2 | no |
| **low emissions, seeds 1 and 2** | **Aug 12 2026** | historical seeds 1 and 2 | yes |

So there are **three** builds in play, not two — the Jul-21 one produced the only genuine second
realisation of the high-emissions leg, which is a separate finding
(`docs/decisions/20260908-X-ssp370-has-no-second-seed.md`). Every run above reports the model's own
completion line for all 67,420 cells, with only the three benign configuration warnings that all
legs emit.

## What is inside the Feb-05 → Aug-12 boundary

The model source is a git checkout whose newest commit is **2026-01-28**, before both builds. Both
binaries were therefore compiled from the *same commit* plus uncommitted working-tree edits, and the
whole difference is **19 modified files, +657 / −17 lines**. Reading all of them:

**Every behavioural change is gated behind a rung-2 environment variable**, the retired
predecessor's hybrid-demography interface:

- `annual_natural.c` — four `rung2_dump_patch()` calls, no-ops unless `LPJ_RUNG2_DIR` is set;
  `rung2_apply_begin_patch()`/`reset`/`end`, no-ops unless `LPJ_RUNG2_APPLY_DIR` is set; the
  deferred kill pass behind `config->individual && rung2_defer_mortality()`.
- `annual_tree.c` — the mortality deferral behind the same `rung2_defer_mortality()`.
- `establishmentpft_ind.c` — the recruit substitution behind
  `rung2_apply_enabled() && rung2_apply_nrecruit() >= 0`.

**The ungated changes cannot reach the state:**

- Two new per-tree fields (`bm_delta`, `leafarea_real`), written in `mortality_tree_ind()`, zeroed in
  `new_tree()` and `fread_tree()`, read by nothing in the physics, and **deliberately absent from the
  restart serialisation** — so the restart layout is unchanged.
- One new per-PFT annual accumulator (`agpp_gross`), zeroed by all three `init_*` functions, read by
  nothing in the physics, and reaching an output column only behind `LPJ_IND_TRUE_GPP`.
- Two new output slots (`NOUT` 419 → 421) for grass daily gross and net primary production,
  accumulated only for grass PFTs into output arrays.
- `gasdev.c` — a function-scope `static` hoisted to file scope plus a read-only getter. Same
  initialisers, same lifetime, **so the random-deviate stream is unchanged.** This is the change that
  would have mattered most and it is the one that provably does not.
- Compiler flags unchanged: `Makefile.inc` predates both builds; `src/lpj/Makefile` changed only to
  add the two rung-2 objects.

**And the gates were shut.** The low-emissions job scripts export exactly `LPJROOT`, `LPJOUTPATH`
and `LPJRESTARTPATH` — no rung-2 variable, no `LPJ_IND_*` variable — and none appears in the shell
profile either.

## Two independent corroborations

1. **The restart layout claim is confirmed from the other end.** The corpus reader parses both legs
   identically — 22 bands, 77 columns, 67,420 cells — which it could not do if the serialisation had
   changed.
2. **The stochasticity behaves the same.** Over the 56,950 cells tree-bearing in both seeds of both
   legs, the relative two-seed spread agrees to within 6 % on every summary: median 0.03027
   (historical, Feb-05) vs 0.03207 (low emissions, Aug-12), p90 0.16350 vs 0.16529, and 19.30 % vs
   20.01 % of cell-quantities above the 10 % floor. Had mortality, establishment or the random stream
   actually changed, there is no reason these would land that close.

## What is NOT proven, and the test that would prove it

**Byte-equality has not been demonstrated.** The decisive test is cheap and specific: run one cell
for one year from the *same* restart under both binaries and byte-compare the restart written. The
Feb-05 binary is preserved as `bin/lpjml.pre_dgrass.bak`, so it is possible today; it has not been
run because no `scripts/sbatch_cmodel.sh` wrapper exists yet, and building one is line D's work.
Until then the honest statement is *"no behavioural difference exists on the code path these runs
took"*, not *"the binaries are identical"*.

Two smaller residuals, recorded so nobody has to rediscover them:

- **No job script contains a `module load` line**, so the runtime library set is not recorded. Library
  churn in this window is documented fact — an earlier high-emissions attempt died on a missing
  `libjson-c.so.4`. A different maths library could change last-bit results. That is a risk of the
  same order as the model's own realisation noise, not a structural one.
- **Output slot numbering changed** (419 → 421 with two inserted definitions). Never compare output
  *files* across this boundary by slot index. It does not touch restart-derived state, which is what
  this project scores.

## Consequences

1. **The low-emissions leg is admissible** as the scored truth of `X-20260908-heldout-forcing-leg`,
   with the build boundary stated in the reference basis and the byte test named as outstanding.
2. **`MEMORY.md:build-provenance` needs an integrator edit.** It currently says the leg "is
   confounded by two intervening rebuilds", which overstates what the rebuilds contain, and it names
   two builds where there are three. Requested wording: *"Ground truth spans three builds (Feb-5,
   Jul-21, Aug-12 2026); the Feb-05→Aug-12 difference is inert for a stock run (all changes gated
   behind unset rung-2 env vars, restart layout unchanged) but is not proven byte-identical."*
3. **The gate itself generalises**: build provenance is established from the log banner, not the
   restart, and a claimed rebuild must be diffed against the source tree before it is called a
   confound. Any future leg gets the same treatment.
