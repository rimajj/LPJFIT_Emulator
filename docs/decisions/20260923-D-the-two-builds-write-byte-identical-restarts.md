# The Feb-05 and Aug-12 builds write byte-identical restarts: one cell, one year

- **Status:** accepted
- **Date:** 2026-09-23
- **Line:** D
- **Closes:** the test owed in `lines/D/STATE.md` NEXT item 3 and in `MEMORY.md:build-provenance`
  ("Feb-05 -> Aug-12 is inert ... Not byte-proven"), and the caveat carried in
  X-20260908-heldout-forcing-leg's reference basis.
- **Jobs:** 2281237 (`D-tru-bytetest-aug12a`), 2281238 (`-aug12b`), 2281323 (`-feb05d`); three
  failed Feb-05 attempts before it are in the ledger with their causes (below).

## The result

| arm | binary (config/paths.yaml key) | restart_2000 sha256 | vs arm A |
|---|---|---|---|
| A | `lpjml.binary` (built 2026-08-12, 11,907,840 B) | `7d25600f…ee664` | — |
| B | `lpjml.binary` again (determinism control) | `7d25600f…ee664` | `cmp`: identical |
| C | `lpjml.binary_pristine` (built 2026-02-05, 11,819,784 B) | `7d25600f…ee664` | `cmp`: 0 bytes differ |

The per-tree text output (`ind__bytetest.csv`) and the annual flux table (`globalflux__bytetest.csv`)
are also byte-identical across all three arms. The NetCDF outputs were not compared as bytes (a
wall-clock timestamp goes into their `history` attribute, `MEMORY.md:netcdf-cmp`).

**The test was not vacuous:** the year changed the state (input restart 2,464,163 B, output
2,456,407 B), and the printed year-2000 fluxes (NEP 61.835, fire 17.203 ktC; transpiration
463079.5 dam3) are the same in all three logs. So there was a year of real dynamics for the two
builds to disagree on, and they did not disagree in a single byte.

## What was held identical

- **The start state:** cell 42490 cut verbatim from the stored historical seed-1 `restart_1999.lpj`
  with `scripts/corpus_restart_subset.py --first-cell 42490 --ncell 1` (2.5 MB, byte-exact cut,
  round-trip asserted). Copied into each run directory; md5 identical in all three.
- **The config:** `scripts/corpus_cmodel_config.py --years 2000 2000 --tag bytetest`, one per run
  directory; the three config files are byte-identical (md5 `9652f751…`). `-DFROM_RESTART`, so the
  RNG state is read from the restart (`new_seed` false) and the seed cannot differ.
- **Year, cell, task count:** model year 2000 only, one cell, one MPI task, same inputs.

## What could NOT be held identical, and why it does not weaken the result

1. **One shared library.** The Feb-05 build links `libjson-c.so.4` (module `json-c/0.13.1`); the
   pinned set loads `json-c/0.17` (`.so.5`), which the Aug-12 build needs. json-c is the config
   parser. First attempt died in 1 s at the wrapper's `ldd` check (job 2281239).
2. **The output-description list.** The Feb-05 build is compiled with `NOUT 419`; the live
   `par/outputvars.js` lists 421 because the Aug-12 work added `d_grass_gpp`/`d_grass_npp`, and the
   model refuses a mismatch (`ERROR232`, job 2281271). The Feb-05 arm therefore read the
   **Jan-28 git-HEAD** `par/outputvars.js` and `include/conf.h` of `$LPJROOT` (419 entries; the
   only difference is those two lines), staged in its run directory beside a byte-identical copy
   of `param_lpjmlfit.js` so the preprocessor finds them first. A first try without `conf.h` died
   in `cpp` (job 2281310). Nothing in `$LPJROOT` was modified. Both differences are output
   bookkeeping and the config parser, not physics -- and the restart bytes confirm it.

## What this licenses, and what it does not

- ✅ **"The Feb-05 -> Aug-12 difference is inert for a stock run" is now a measurement**, not an
  argument from reading the diff: identical restart, identical per-tree output, identical fluxes,
  for one year from a real forested state with every rung-2 environment switch unset.
- ✅ So the stored historical + ssp370-seed-1 legs (Feb-05) and anything run with the Aug-12 build
  can be compared without a build caveat **for stock runs**, and the corpus's one-binary rule is
  about reproducibility, not about a known physics difference.
- ❌ **One cell, one year, the transient branch.** Not a spin-up, not a scenario leg, not a cell
  where fire, establishment or mortality took a branch this one did not. A code path the year did
  not exercise is not tested. The diff argument (`MEMORY.md:build-provenance`) still covers those.
- ❌ **Not the Jul-21 build** (the genuine ssp370 second seed). No `lpjml` binary dated 2026-07-21
  remains in `$LPJROOT/bin` (listed 2026-09-23), so the three-build statement is two-thirds measured.
- ❌ **Not with `LPJ_IND_ALL_HEIGHTS` / `LPJ_IND_TRUE_GPP` set.** Those switches exist only in the
  Aug-12 build and change what it writes; this test is for the default, which is how every stored
  leg was produced.

## Found on the way: the completion line carries the binary's FILE NAME

The Feb-05 build prints `lpjml.pre_dgrass.bak successfully terminated`, not `lpjml successfully
terminated`. `scripts/sbatch_cmodel.sh` recorded the fixed `^lpjml successfully terminated` as the
harvest command for every run, so any run of a non-default build would have been judged FAILED by
its own ledger row. Fixed in the same change: the pattern is built from the basename of the binary
`LPJ_BINARY_KEY` resolved to, dots escaped, in the task-farm runner and in both recorded harvest
commands; `tests/test_corpus_truth.py` pins it with a fake `srun`.

## Reproduce

```bash
B=<scratch>/runs/truth-bytetest
scripts/corpus_restart_subset.py --first-cell 42490 --ncell 1 --out $B/restart_1999_c42490.lpj
for arm in aug12a aug12b feb05; do scripts/corpus_cmodel_config.py --restart \
  $B/restart_1999_c42490.lpj --first-cell 42490 --ncell 1 --years 2000 2000 --run-dir $B/$arm \
  --tag bytetest; done
# feb05 only: git -C $LPJROOT show HEAD:par/outputvars.js > $B/feb05/par/outputvars.js, the same
# for include/conf.h, and cp $LPJROOT/param_lpjmlfit.js $B/feb05/
TIME=00:15:00 scripts/sbatch_cmodel.sh D-...-aug12a $B/aug12a/lpjml_bytetest.js $B/aug12a
LPJ_MODULES="<pinned set with json-c/0.13.1>" LPJ_BINARY_KEY=lpjml.binary_pristine \
  TIME=00:15:00 scripts/sbatch_cmodel.sh D-...-feb05 $B/feb05/lpjml_bytetest.js $B/feb05
cmp $B/aug12a/restart/restart_2000_bytetest.lpj $B/feb05/restart/restart_2000_bytetest.lpj
```
