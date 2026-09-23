#!/usr/bin/env bash
# Run the LPJmL-FIT C model, and record it in the campaign ledger.
#
#   scripts/sbatch_cmodel.sh --check <tag> <config.js>      # config pre-flight only, no job
#   scripts/sbatch_cmodel.sh <tag> <config.js> <run-dir>    # submit the run
#
# Env knobs: NTASKS=1 TIME=00:30:00 PARTITION=priority QOS= ACCOUNT=waldspektrum
#            LPJ_DEFINES="-DFROM_RESTART"   preprocessor flags; set to "" for a SPIN-UP run
#            LPJ_MODULES="..."              the module set the job loads; default is pinned below
#            HARVEST_BY=<ISO date>          when the ledger calls the campaign overdue
#            EST_CORE_HOURS=<h>             the member-based CPU estimate for the ledger row;
#                                           without it the row carries the bound NTASKS x TIME
#
# ─── PACKING: NTASKS SMALLER THAN THE MANIFEST (added 2026-09-23) ─────────────────────────────
# With a manifest, NTASKS defaults to its length: every member holds its own CPU for the whole
# job, so the allocation is charged at the LONGEST member's wall time. Measured on the 6,000-member
# pilot `v2-constco2`: 686.6 core-hours allocated for 361.2 of CPU, 1.90x, because a treeless
# member finishes in under a minute and a dense forest one takes up to nine. Set NTASKS below the
# manifest length and the farm keeps exactly NTASKS members in flight, starting the next one as
# each finishes, so the allocation tracks the CPU actually used. TIME must then cover
# (the manifest's CPU / NTASKS) + its longest member.
#
# ─── WHY A WRAPPER ─────────────────────────────────────────────────────────────────────────────
# A PreToolUse hook denies calling `bin/lpjml` from a session: it needs its module environment, it
# is far too slow for the login node, and a run started there dies with the session. And raw sbatch
# is denied because this wrapper is what writes the campaign ledger row -- the only reason a later
# session can find, judge and harvest a job whose results arrive after the launching session ended.
#
# ─── THE SIX TRAPS, ALL MEASURED, ALL SPECIFIC TO THE C MODEL ──────────────────────────────────
# 1. NEVER JUDGE A C RUN BY ITS EXIT CODE. The stock job files always exit 0, so a run that died
#    mid-century leaves a plausible truncated output behind a green row. The only evidence of
#    success is the model's OWN line, `lpjml successfully terminated, <n> grid cells processed.`,
#    at the START of a line (see trap 6) in a NON-EMPTY log. This wrapper writes that requirement
#    into the ledger row as the harvest command, so the next session checks the right thing.
# 2. A ZERO-BYTE LOG AFTER MINUTES IS A DEAD JOB, not early days -- the opposite of the Python
#    case. A healthy run creates its output files within ~15 seconds. Check the output directory a
#    minute after launch; do not wait out a silent job.
# 3. THE PATHS COME FROM THE ENVIRONMENT, not from the config. `LPJROOT`, `LPJOUTPATH` and
#    `LPJRESTARTPATH` are what turn the config's relative `output/...` and `restart/...` names into
#    real paths, so they are exported here and the run directory must contain both subdirectories.
# 4. `-DFROM_RESTART` is what selects the transient block of the config. Without it the config
#    selects the 1000-year spin-up branch and the run takes days instead of seconds. That is the
#    DEFAULT here, so a transient validation run needs no knob -- but corpus generation is the
#    opposite case and needs the spin-up branch, so set LPJ_DEFINES="" for it. Note the ground
#    truth's own spin-up job passes NO -D flag at all (not `-DSPINUP`), so "" is the faithful
#    setting and `-DSPINUP` would silently be a different spin-up.
# 5. THE JOB LOADS ITS OWN MODULES, and did not until 2026-09-10. `--export=ALL` used to hand the
#    job whatever the SUBMITTING SHELL happened to have loaded, so the same command was a green run
#    from one session and a one-second death from another. With no modules the binary is short
#    exactly two libraries -- `libnetcdf.so.19` and `libudunits2.so.0` -- and the loader names one
#    per attempt, so chasing them singly costs a job each. The job now purges and loads the pinned
#    LPJ_MODULES set, and CHECKS the binary resolves before spending an allocation on it.
# 6. ANCHOR THE COMPLETION-LINE GREP: `^lpjml successfully terminated`. This wrapper used to echo
#    the phrase into the job log as advice, so an unanchored `grep -c 'successfully terminated'`
#    returned 1 on a job that died in zero seconds with exit 127 -- a failed run wearing a pass.
#    Both halves are fixed: the recorded harvest commands are anchored, AND the advice text no
#    longer contains the phrase, so even a careless grep cannot match a decoy.
#    ⚠ AND THE LINE STARTS WITH THE BINARY'S OWN FILE NAME, not with "lpjml" (measured 2026-09-23):
#    the Feb-05 build is `lpjml.pre_dgrass.bak` and prints `lpjml.pre_dgrass.bak successfully
#    terminated`, so a fixed `^lpjml successfully` pattern fails every run of it. The pattern is
#    built from the basename of whichever binary LPJ_BINARY_KEY resolved to.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CHECK=0
MANIFEST=""
if [[ "${1-}" == "--check" ]]; then CHECK=1; shift; fi
if [[ "${1-}" == "--manifest" ]]; then MANIFEST="${2:?--manifest needs a file}"; shift 2; fi

if [[ -n "$MANIFEST" ]]; then
  TAG="${1:?usage: sbatch_cmodel.sh [--check] --manifest <file.tsv> <tag>}"
  CONFIG=""
  RUN_DIR="$(dirname "$MANIFEST")"
  [[ -f "$MANIFEST" ]] || { echo "sbatch_cmodel: no such manifest: $MANIFEST" >&2; exit 2; }
else
  TAG="${1:?usage: sbatch_cmodel.sh [--check] <tag> <config.js> [run-dir]}"
  CONFIG="${2:?usage: sbatch_cmodel.sh [--check] <tag> <config.js> [run-dir]}"
  RUN_DIR="${3:-$(dirname "$CONFIG")}"
fi

LINE="${TAG%%-*}"
if [[ ! "$LINE" =~ ^[DTX]$ ]]; then
  echo "sbatch_cmodel: tag must start with the work line, e.g. D-cmodel-t2 (got '$TAG')" >&2
  exit 2
fi

LPJROOT="$(python3 "$REPO/tools/_paths.py" lpjml.lpjroot)"
# WHICH BINARY. Default `lpjml.binary`, the Aug-12 build that produced the corpus. LPJ_BINARY_KEY
# names a DIFFERENT key in config/paths.yaml -- it is a key, never a path, so a run can only ever
# use a binary the provenance file already knows about, and the ledger row records which.
#
# ⚠ THIS EXISTS FOR ONE OUTSTANDING TEST, and until 2026-09-17 its absence WAS the blocker. Stored
# ground truth spans three builds. The Feb-05 -> Aug-12 difference is argued inert (every
# behavioural change sits behind unset rung-2 env vars, the restart layout is unchanged), and that
# argument travels in `MEMORY.md:build-provenance` and in X-20260908-heldout-forcing-leg's
# reference basis with the honest caveat "what is NOT proven is byte-equality: the decisive test --
# one cell, one year, one restart, both binaries, byte-compare -- has not been run, because the
# Feb-05 binary is preserved but no wrapper exists yet to run it". Now one does.
LPJ_BINARY_KEY="${LPJ_BINARY_KEY:-lpjml.binary}"
[[ "$LPJ_BINARY_KEY" == lpjml.* ]] || {
  echo "sbatch_cmodel: LPJ_BINARY_KEY must be a config/paths.yaml key under lpjml." >&2
  echo "  got '$LPJ_BINARY_KEY'; try lpjml.binary or lpjml.binary_pristine" >&2
  exit 2
}
LPJBIN="$(python3 "$REPO/tools/_paths.py" "$LPJ_BINARY_KEY")" || {
  echo "sbatch_cmodel: no such key in config/paths.yaml: $LPJ_BINARY_KEY" >&2; exit 2; }
LPJCHECK="$(python3 "$REPO/tools/_paths.py" lpjml.lpjcheck)"
export LPJROOT
export LPJOUTPATH="$RUN_DIR"
export LPJRESTARTPATH="$RUN_DIR"

if [[ -z "$MANIFEST" ]]; then
  [[ -f "$CONFIG" ]] || { echo "sbatch_cmodel: no such config: $CONFIG" >&2; exit 2; }
  mkdir -p "$RUN_DIR/output" "$RUN_DIR/restart"
fi

# The preprocessor flags select which BRANCH of the config is compiled, so they are part of the
# run's identity: the same config file under a different LPJ_DEFINES is a different simulation.
# Recorded in the ledger row for exactly that reason.
# ─── the module set, used by BOTH the pre-flight and the job (trap 5) ─────────────────────────
# Recovered from a run that worked (`D-cmodel-t2-control`, job 2080497) and reduced to the set the
# binaries actually need: with none of these loaded, `ldd` reports exactly libnetcdf.so.19 and
# libudunits2.so.0 unresolved, and lmod pulls the rest of the tree in as dependencies. Override
# with LPJ_MODULES when the binary is rebuilt against something else -- and when you do, recover
# the new set from a green log rather than guessing:
#   sed -n '/Currently Loaded Modules/,/^ *$/p' logs/<green-tag>.<jobid>.out
LPJ_MODULES="${LPJ_MODULES:-netcdf-c/4.9.2 hdf5/1.14.5 udunits/2.2.28 szip/2.1.1 zlib/1.3.1 \
zstd/1.5.6 curl/8.4.0 openssl/3.6.0 libxml2/2.11.0 m4/4-1.4.19 expat/2.5.0 json-c/0.17 \
eccodes/2.32.1 proj/9.5.1 intel/oneAPI/2024.0.0 gcc/15.2.0}"

# ⚠ THE PRE-FLIGHT IS NOT MODULE-FREE, though the skill said it was until 2026-09-10. `lpjcheck`
# links the same libraries as `lpjml`, so from a shell with no modules `--check` dies with the
# identical `libnetcdf.so.19` message -- which reads as a broken config rather than a missing
# environment, in the one command whose whole job is to tell you the config is fine. So load the
# set HERE too, in the wrapper's own shell, before lpjcheck runs.
load_lpj_modules() {
  [[ -f /usr/share/lmod/lmod/init/bash ]] || { echo "sbatch_cmodel: no lmod init; using the inherited environment" >&2; return 0; }
  # shellcheck disable=SC1091
  source /usr/share/lmod/lmod/init/bash
  module purge 2>/dev/null || true
  module load $LPJ_MODULES 2>/dev/null || { echo "sbatch_cmodel: 'module load' failed for: $LPJ_MODULES" >&2; return 1; }
  return 0
}

DEFINES="${LPJ_DEFINES--DFROM_RESTART}"
read -r -a DEFS <<< "$DEFINES"
echo "sbatch_cmodel: defines = ${DEFINES:-(none, i.e. the spin-up branch)}"

# ─── t1: the config pre-flight. Validates without running, so it is free. ──────────────────────
if (( CHECK )); then
  echo "sbatch_cmodel: pre-flight with lpjcheck (validates the config and every input, no run)"
  load_lpj_modules || exit 3
  rc=0
  if [[ -n "$MANIFEST" ]]; then
    # Every member, because a manifest whose members differ only in a filename is exactly the case
    # where one bad path hides behind twenty good ones.
    while IFS=$'\t' read -r name cfg rdir; do
      [[ -z "${name// }" ]] && continue
      mkdir -p "$rdir/output" "$rdir/restart"
      export LPJOUTPATH="$rdir" LPJRESTARTPATH="$rdir"
      set +e; "$LPJCHECK" -q ${DEFS[@]+"${DEFS[@]}"} "$cfg"; one=$?; set -e
      (( one == 0 )) || { echo "  FAILED: $name ($cfg)" >&2; rc=1; }
    done < "$MANIFEST"
    echo "sbatch_cmodel: pre-flighted $(grep -c . "$MANIFEST") manifest members"
  else
    set +e; "$LPJCHECK" ${DEFS[@]+"${DEFS[@]}"} "$CONFIG"; rc=$?; set -e
  fi
  if (( rc == 0 )); then
    echo "sbatch_cmodel: t1 PASSED -- the model's own pre-flight accepts this config and restart."
  else
    echo "sbatch_cmodel: t1 FAILED (lpjcheck exit $rc). Fix the config before submitting." >&2
  fi
  exit $rc
fi

NRUNS=1
if [[ -n "$MANIFEST" ]]; then NRUNS=$(grep -c . "$MANIFEST"); fi
NTASKS="${NTASKS:-$NRUNS}"
if (( NTASKS > NRUNS )); then
  echo "sbatch_cmodel: NTASKS=$NTASKS exceeds the $NRUNS runs; allocating $NRUNS (the rest would idle)." >&2
  NTASKS=$NRUNS
fi
if (( NTASKS < NRUNS )); then
  echo "sbatch_cmodel: PACKED farm -- $NRUNS members through $NTASKS CPUs, at most $NTASKS in flight."
  echo "  TIME must cover the manifest's CPU / $NTASKS plus its longest member, or members are lost."
fi
TIME="${TIME:-00:30:00}"
PARTITION="${PARTITION:-priority}"
ACCOUNT="${ACCOUNT:-waldspektrum}"
if [[ "$PARTITION" == "priority" ]]; then QOS="${QOS:-priority}"; else QOS="${QOS:-short}"; fi
if [[ "$PARTITION" == "priority" ]] && (( NTASKS > 64 )); then
  echo "sbatch_cmodel: partition=priority is capped at 64 CPU per job (asked $NTASKS)." >&2
  echo "  Use PARTITION=standard, or split the manifest." >&2
  exit 2
fi
LOGDIR="$REPO/logs"; mkdir -p "$LOGDIR"

# ─── what the ledger row must carry to reproduce and to cost this job ─────────────────────────
# LPJ_IND_* are the binary's opt-in output switches (config/paths.yaml, `lpjml`): inert unless set,
# but when set they change what every member WRITES, and --export=ALL hands the job whatever the
# submitting shell happened to have. So both values go into the job log and into the ledger row's
# command line, set or not -- an empty value recorded is a fact, an absent one is a guess.
IND_ENV="LPJ_IND_ALL_HEIGHTS='${LPJ_IND_ALL_HEIGHTS-}' LPJ_IND_TRUE_GPP='${LPJ_IND_TRUE_GPP-}'"
# SLURM's TIME forms: MM, MM:SS, HH:MM:SS, D-HH, D-HH:MM, D-HH:MM:SS.
time_to_hours() {
  local t="$1" d=0 a b c
  if [[ "$t" == *-* ]]; then
    d="${t%%-*}"; t="${t#*-}"
    IFS=: read -r a b c <<< "$t"
    awk -v d="$d" -v h="${a:-0}" -v m="${b:-0}" -v s="${c:-0}" 'BEGIN{printf "%.4f", d*24+h+m/60+s/3600}'
    return
  fi
  IFS=: read -r a b c <<< "$t"
  if [[ -z "${b-}" ]]; then awk -v m="$a" 'BEGIN{printf "%.4f", m/60}'
  elif [[ -z "${c-}" ]]; then awk -v m="$a" -v s="$b" 'BEGIN{printf "%.4f", m/60+s/3600}'
  else awk -v h="$a" -v m="$b" -v s="$c" 'BEGIN{printf "%.4f", h+m/60+s/3600}'
  fi
}
if [[ -n "${EST_CORE_HOURS-}" ]]; then
  EST="$EST_CORE_HOURS"; EST_BASIS="caller's member-based estimate"
else
  EST="$(awk -v n="$NTASKS" -v h="$(time_to_hours "$TIME")" 'BEGIN{printf "%.2f", n*h}')"
  EST_BASIS="allocation bound NTASKS x TIME, not an estimate of use"
fi
echo "sbatch_cmodel: est core-hours $EST ($EST_BASIS); $IND_ENV"

# ─── the batch body ────────────────────────────────────────────────────────────────────────────
# A MANIFEST run is a task farm: one single-cell spin-up per task, all inside ONE allocation and
# behind ONE ledger row. That is not tidiness -- the pilot corpus is 6,000 single-cell spin-ups, and
# 6,000 ledger rows would make the ledger useless as the thing a later session reads to find out
# what is outstanding. Each member gets its OWN LPJOUTPATH/LPJRESTARTPATH, because the config names
# its outputs relative to those and two members sharing them would overwrite each other.
#
# ⚠ THE RUNNER IS A FILE ON DISK, NOT AN EMBEDDED HEREDOC. Written as an embedded one it has to
# survive two rounds of expansion -- the `$(cat <<EOF)` that builds it and the `sbatch <<EOF` that
# ships it -- and a line continuation that does not survive both turns the member command into an
# empty string, which SLURM reports as `exit=127` with no other symptom. That happened; the fix is
# to write the runner with a QUOTED heredoc (no expansion at all) and pass its inputs as exported
# variables. It also means the exact runner is left on disk next to the manifest, so a failed
# member can be rerun by hand.
if [[ -n "$MANIFEST" ]]; then
  RUNNER="$(dirname "$MANIFEST")/.runner_$TAG.sh"
  cat > "$RUNNER" <<'RUNNEREOF'
#!/usr/bin/env bash
# Task farm for one manifest: <name>\t<config>\t<run-dir> per line, one SLURM task each.
# Inputs, all exported by the job script: LPJBIN LPJ_DEFS MANIFEST MAXPAR
#
# ⚠ AT MOST MAXPAR MEMBERS ARE IN FLIGHT (= the job's NTASKS); the next starts only when one ends
# (`wait -n`). That is what lets a manifest be LONGER than its allocation. Not left to `srun
# --exclusive` queueing alone: that works too, but it parks every not-yet-runnable member as a
# blocked srun process on the batch node, each of them polling the controller.
#
# ⚠ TWO BUGS THIS FILE IS SHAPED AROUND, BOTH MEASURED HERE, BOTH SILENT.
#
# 1. `srun` FORWARDS ITS STDIN TO THE TASK, and inside `while read ... done < manifest` its stdin
#    IS the manifest. It swallowed 18 of 25 lines: seven members ran, eighteen never launched, and
#    the job exited 0. Hence `< /dev/null` on the member -- `--input none` alone does not stop srun
#    from draining the descriptor.
# 2. THE COUNTER MUST NOT COME FROM THE SAME LOOP AS THE LAUNCH. The first version reported
#    "7 of 7" for a 25-line manifest, because both numbers came from the loop that had been
#    starved. `want` is read straight off the file, so an under-launch is loud.
set -uo pipefail
want=$(grep -c . "$MANIFEST")
maxpar="${MAXPAR:-$want}"
n=0
while IFS=$'\t' read -r name cfg rdir; do
  [ -z "${name// }" ] && continue
  while [ "$(jobs -rp | wc -l)" -ge "$maxpar" ]; do wait -n; done
  mkdir -p "$rdir/output" "$rdir/restart"
  (
    cd "$rdir" || exit 1
    export LPJOUTPATH="$rdir" LPJRESTARTPATH="$rdir"
    srun --exclusive --input none --ntasks=1 --cpus-per-task=1 "$LPJBIN" $LPJ_DEFS "$cfg" \
      > "$rdir/lpjml.$name.log" 2>&1 < /dev/null
    echo "member $name srun_exit=$?"
  ) &
  n=$((n+1))
done < "$MANIFEST"
echo "=== launched $n of $want members, at most $maxpar at a time; waiting ==="
if [ "$n" -ne "$want" ]; then
  echo "LAUNCH SHORTFALL: the manifest has $want lines but only $n started." >&2
fi
wait

# The verdict is the model's own line in each member's own log, never the exit codes above. It
# begins with the binary's own file name, dots escaped so the pattern stays literal.
donepat="^$(basename "$LPJBIN" | sed 's/\./\\./g') successfully terminated"
ok=0
while IFS=$'\t' read -r name cfg rdir; do
  [ -z "${name// }" ] && continue
  if grep -q "$donepat" "$rdir/lpjml.$name.log" 2>/dev/null; then
    ok=$((ok+1))
  else
    echo "MEMBER FAILED (no completion line): $name  -> $rdir/lpjml.$name.log"
    tail -n 5 "$rdir/lpjml.$name.log" 2>/dev/null | sed 's/^/    /'
  fi
done < "$MANIFEST"
echo "=== members reporting the model's own completion line: $ok of $want ==="
[ "$ok" -eq "$want" ]
RUNNEREOF
  chmod +x "$RUNNER"
  BODY=$(
    printf '%s\n' \
      "export LPJBIN=\"$LPJBIN\"" \
      "export LPJ_DEFS=\"$DEFINES\"" \
      "export MANIFEST=\"$MANIFEST\"" \
      "export MAXPAR=\"$NTASKS\"" \
      "bash \"$RUNNER\"" \
      'rc=$?'
  )
else
  BODY=$(
    printf '%s\n' \
      "export LPJOUTPATH=\"$RUN_DIR\"" \
      "export LPJRESTARTPATH=\"$RUN_DIR\"" \
      "cd \"$RUN_DIR\"" \
      "mpirun \"$LPJBIN\" $DEFINES \"$CONFIG\"" \
      'rc=$?'
  )
fi

JOBID=$(sbatch --parsable \
  --job-name="$TAG" \
  --account="$ACCOUNT" \
  --partition="$PARTITION" \
  --qos="$QOS" \
  --time="$TIME" \
  --ntasks="$NTASKS" \
  --output="$LOGDIR/$TAG.%j.out" \
  --export=ALL \
  <<SLURM
#!/usr/bin/env bash
set -uo pipefail
export LPJROOT="$LPJROOT"
echo "=== JOB START tag=$TAG host=\$(hostname) ntasks=$NTASKS runs=$NRUNS defines='$DEFINES' ==="
echo "=== binary key=$LPJ_BINARY_KEY  $IND_ENV ==="

# Trap 5: load the PINNED set, so this job's libraries do not depend on the submitting shell.
if [[ -f /usr/share/lmod/lmod/init/bash ]]; then
  source /usr/share/lmod/lmod/init/bash
  module purge 2>/dev/null || true
  module load $LPJ_MODULES || { echo "FATAL: 'module load' failed for: $LPJ_MODULES" >&2; exit 3; }
else
  echo "WARNING: no lmod init found; the job is running with the inherited environment." >&2
fi
module list 2>&1 || true

# Cheap, and it converts a cryptic one-second loader death into a named diagnosis.
if ldd "$LPJBIN" 2>/dev/null | grep -q 'not found'; then
  echo "FATAL: the module set does not resolve the binary's libraries:" >&2
  ldd "$LPJBIN" 2>&1 | grep 'not found' >&2
  echo "Recover a working set from a green log, then pass it as LPJ_MODULES. Skill: cmodel-run." >&2
  exit 3
fi

$BODY
echo "=== JOB DONE tag=$TAG exit=\$rc ==="
echo "=== NOTE: the exit code is NOT the verdict, and this log deliberately does NOT repeat the"
echo "===       model's completion phrase -- an unanchored grep for it used to match this very"
echo "===       advice and pass a dead job. Judge the run with the ledger's harvest command:"
echo "===   python3 tools/campaigns.py status --line $LINE     (or see skill cmodel-run)"
exit \$rc
SLURM
)

echo "submitted $TAG as job $JOBID  (log: logs/$TAG.$JOBID.out)"
echo "run dir: $RUN_DIR   runs: $NRUNS"
echo
echo "JUDGE IT BY THE MODEL'S OWN LINE, not by the exit code:"
DONEPAT="^$(basename "$LPJBIN" | sed 's/\./\\./g') successfully terminated"
if [[ -n "$MANIFEST" ]]; then
  # Each member logs to its own run directory, so the job log alone cannot prove all of them
  # finished. The harvest command counts the members that printed the model's own line, and the
  # answer must be $NRUNS -- anything less is a partial campaign wearing a green exit code.
  HARVEST="grep -l '$DONEPAT' \$(awk -F'\t' 'NF{print \$3\"/lpjml.\"\$1\".log\"}' $MANIFEST) | wc -l   # must be $NRUNS"
  CMDLINE="LPJ_BINARY_KEY='$LPJ_BINARY_KEY' LPJ_DEFINES='$DEFINES' $IND_ENV PARTITION=$PARTITION NTASKS=$NTASKS TIME=$TIME scripts/sbatch_cmodel.sh --manifest $MANIFEST $TAG"
else
  HARVEST="grep '$DONEPAT' logs/$TAG.$JOBID.out"
  CMDLINE="LPJ_BINARY_KEY='$LPJ_BINARY_KEY' LPJ_DEFINES='$DEFINES' $IND_ENV PARTITION=$PARTITION NTASKS=$NTASKS TIME=$TIME scripts/sbatch_cmodel.sh $TAG $CONFIG $RUN_DIR"
fi
# ⚠ THE BINARY IS PART OF THE RUN'S IDENTITY, exactly as LPJ_DEFINES is: the same config under a
# different build is a different simulation, and that is the whole point of the key existing. A
# ledger row that did not name it could not reproduce its own run.
echo "  $HARVEST"

# ⚠ UNDER THE CLUSTER INTERPRETER, NOT BARE `python3` -- the trap `sbatch_py.sh` documents: the
# login node's system python3 is 3.9, `tools/campaigns.py` needs 3.11 (`tomllib`), and a ledger
# write that dies AFTER the job is queued leaves a running job nobody will come back for.
PY_BIN="$(python3 "$REPO/tools/_paths.py" cluster.python)" || PY_BIN=""
[[ -x "$PY_BIN" ]] || PY_BIN="python3"
LEDGER_ARGS=(
  launch --line "$LINE" --tag "$TAG" --job "$JOBID"
  --partition "$PARTITION" --cpus "$NTASKS"
  --log-glob "logs/$TAG.$JOBID.out"
  --cmd "$CMDLINE"
  --harvest-cmd "$HARVEST"
  --est-core-hours "$EST"
)
if [[ -n "${HARVEST_BY-}" ]]; then LEDGER_ARGS+=(--harvest-by "$HARVEST_BY"); fi
if [[ -n "${EXPECT-}" ]]; then LEDGER_ARGS+=(--expect "$EXPECT"); fi
if ! "$PY_BIN" "$REPO/tools/campaigns.py" "${LEDGER_ARGS[@]}"; then
  echo "sbatch_cmodel: ⚠ JOB $JOBID IS QUEUED BUT NOT IN THE LEDGER. Write the row by hand or" >&2
  echo "  cancel it -- an unrecorded job is one nobody replays at session start: scancel $JOBID" >&2
  exit 1
fi
