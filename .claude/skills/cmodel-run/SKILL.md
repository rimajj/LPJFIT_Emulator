---
name: cmodel-run
description: Run the LPJmL-FIT C model on SLURM — the module set it needs, the config pre-flight, and the one line that counts as success. Use whenever launching `scripts/sbatch_cmodel.sh`, when a run dies instantly with `error while loading shared libraries`, when a job exits 0 with no output, or when deciding whether a finished run may be scored.
---

# Running the C model

`scripts/slurm-guard.sh` denies calling `bin/lpjml` from a session and points here. This skill
existed only as that pointer until 2026-09-09, when its absence cost three failed jobs in a row.

## The module set — the wrapper now supplies it, and you no longer need to

✅ **Fixed 2026-09-10: `scripts/sbatch_cmodel.sh` pins and loads its own module set**, for both the
job and the `--check` pre-flight, so nothing below depends on what your shell has loaded. Just:

```bash
TIME=00:30:00 scripts/sbatch_cmodel.sh <tag> <config.js> <run-dir>
```

Override with `LPJ_MODULES="…"` if the binary is rebuilt against a different set. The job also
runs `ldd` on the binary before spending its allocation, so a wrong set now fails with the missing
library named, instead of a cryptic one-second death.

⚠ **The history, because it explains three lost jobs.** The wrapper used to submit with
`--export=ALL` and no `module load`, so the job inherited whatever the SUBMITTING SHELL happened to
have. From a shell with no modules the model died in under a second with

```
error while loading shared libraries: libnetcdf.so.19: ...
```

then `libudunits2.so.0` — with no modules the binary is short **exactly those two**, and the loader
names one per attempt, so chasing them singly costs a job each. The pinned set is:

```
netcdf-c/4.9.2 hdf5/1.14.5 udunits/2.2.28 szip/2.1.1 zlib/1.3.1 zstd/1.5.6 curl/8.4.0
openssl/3.6.0 libxml2/2.11.0 m4/4-1.4.19 expat/2.5.0 json-c/0.17 eccodes/2.32.1 proj/9.5.1
intel/oneAPI/2024.0.0 gcc/15.2.0
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

Validates the config and every input path without running. A `WARNING035` about a missing soil
code is normal on this grid and is not a failure.

⚠ **This skill said "and needs no modules" until 2026-09-10, and that was wrong.** `lpjcheck`
links the same libraries as `lpjml`, so from a module-free shell the pre-flight died with the
identical `libnetcdf.so.19` message — in the one command whose whole purpose is to tell you the
config is good, where a missing environment reads as a broken config. The wrapper now loads the
set for `--check` too; verified passing from a shell with no modules loaded.

## ⚠ Judging the result: only one line counts

**Never judge a C run by its exit code** — the stock job files exit 0 even when the model died
mid-century. Require the model's own line:

```bash
grep '^lpjml successfully terminated' logs/<tag>.<jobid>.out
```

⚠ **Anchor the pattern**, always — `^lpjml successfully terminated`. Measured 2026-09-09: a job
that failed with exit 127 in zero seconds still matched an unanchored `grep -c`, because the
wrapper echoed the phrase into every log as advice. ✅ **Fixed 2026-09-10**: the wrapper's trailing
NOTE no longer contains the phrase, and every harvest command it writes into the ledger is
anchored — so on a run submitted after that date the only match is the model's own line. Anchor
anyway: logs from before the fix still carry the decoy.

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
