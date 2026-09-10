---
name: cmodel-run
description: Run the LPJmL-FIT C model on SLURM — the module set it needs, the config pre-flight, and the one line that counts as success. Use whenever launching `scripts/sbatch_cmodel.sh`, when a run dies instantly with `error while loading shared libraries`, when a job exits 0 with no output, or when deciding whether a finished run may be scored.
---

# Running the C model

`scripts/slurm-guard.sh` denies calling `bin/lpjml` from a session and points here. This skill
existed only as that pointer until 2026-09-09, when its absence cost three failed jobs in a row.

## The module set, and why the wrapper does not supply it

⚠ **`scripts/sbatch_cmodel.sh` submits with `--export=ALL` and no `module load` line, so the job
inherits whatever the SUBMITTING SHELL happens to have loaded.** A session whose shell has no
modules submits a job with no modules, and the model dies in under a second with

```
/home/jamirp/lpjml56fit/bin/lpjml: error while loading shared libraries: libnetcdf.so.19: ...
```

then `libudunits2.so.0`, then the next one — one library per attempt if you chase them singly.
Load the whole set in the SAME command as the submission, because a fresh shell forgets:

```bash
source /usr/share/lmod/lmod/init/bash
module load netcdf-c/4.9.2 hdf5/1.14.5 udunits/2.2.28 szip/2.1.1 zlib/1.3.1 zstd/1.5.6 \
            curl/8.4.0 openssl/3.6.0 libxml2/2.11.0 m4/4-1.4.19 expat/2.5.0 json-c/0.17 \
            eccodes/2.32.1 proj/9.5.1 intel/oneAPI/2024.0.0 gcc/15.2.0
TIME=00:30:00 scripts/sbatch_cmodel.sh <tag> <config.js> <run-dir>
```

**Recovering the set from a run that worked** — better than trusting this list, which will age:

```bash
sed -n '/Currently Loaded Modules/,/^ *$/p' logs/<a-successful-tag>.<jobid>.out \
  | grep -oE '[A-Za-z0-9_+-]+/[A-Za-z0-9._/-]+' | sort -u
```

The wrapper prints `module list` into every job log for exactly this reason, so any green run is a
usable record of a working environment. `docs/decisions/20260908-X-build-provenance-of-the-low-
emissions-leg.md` already flagged that no job script records its library set; this is that gap
biting. The durable fix belongs in the wrapper (line D owns it), not in every caller.

## The pre-flight is free — use it

```bash
scripts/sbatch_cmodel.sh --check <tag> <config.js> <run-dir>
```

Validates the config and every input path without running, and needs no modules. A `WARNING035`
about a missing soil code is normal on this grid and is not a failure.

## ⚠ Judging the result: only one line counts

**Never judge a C run by its exit code** — the stock job files exit 0 even when the model died
mid-century. Require the model's own line:

```bash
grep '^lpjml successfully terminated' logs/<tag>.<jobid>.out
```

⚠ **Anchor the pattern.** `grep -c 'successfully terminated'` returns 1 on a *failed* job, because
the wrapper's own advice text contains that phrase:

```
=== NOTE: the exit code is NOT the verdict. Require the model's own line:
===   'lpjml successfully terminated, <n> grid cells processed.'
```

Measured 2026-09-09: a job that failed with exit 127 in zero seconds still matched an unanchored
`grep -c`. Anchor with `^`, or check the cell count.

## Reading a silent job

* **Python** block-buffers stdout, so a healthy Python job's log is empty until it exits — judge it
  by `sacct` CPU time, never by log length.
* **The C model is the opposite**: it writes output files within ~15 seconds. A zero-byte log and
  an empty `output/` a minute in is a dead job, not an early one. Do not wait it out.

## Setting up a run directory

The config resolves `restart/...` and `output/...` against `LPJRESTARTPATH`/`LPJOUTPATH`, which the
wrapper sets to the run dir, so both subdirectories must exist and the input restart goes in
`<run-dir>/restart/`. Copying an existing arm's config and editing it is the normal path;
`-DFROM_RESTART` (which the wrapper passes) is what selects the transient block rather than the
1000-year spin-up branch.
