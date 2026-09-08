#!/usr/bin/env bash
# Run the LPJmL-FIT C model, and record it in the campaign ledger.
#
#   scripts/sbatch_cmodel.sh --check <tag> <config.js>      # config pre-flight only, no job
#   scripts/sbatch_cmodel.sh <tag> <config.js> <run-dir>    # submit the run
#
# Env knobs: NTASKS=1 TIME=00:30:00 PARTITION=priority QOS= ACCOUNT=waldspektrum
#            LPJ_DEFINES="-DFROM_RESTART"   preprocessor flags; set to "" for a SPIN-UP run
#
# ─── WHY A WRAPPER ─────────────────────────────────────────────────────────────────────────────
# A PreToolUse hook denies calling `bin/lpjml` from a session: it needs its module environment, it
# is far too slow for the login node, and a run started there dies with the session. And raw sbatch
# is denied because this wrapper is what writes the campaign ledger row -- the only reason a later
# session can find, judge and harvest a job whose results arrive after the launching session ended.
#
# ─── THE FOUR TRAPS, ALL MEASURED, ALL SPECIFIC TO THE C MODEL ─────────────────────────────────
# 1. NEVER JUDGE A C RUN BY ITS EXIT CODE. The stock job files always exit 0, so a run that died
#    mid-century leaves a plausible truncated output behind a green row. The only evidence of
#    success is the model's OWN line, `lpjml successfully terminated, <n> grid cells processed.`,
#    in a NON-EMPTY log. This wrapper writes that requirement into the ledger row as the harvest
#    command, so the next session checks the right thing.
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
LPJBIN="$(python3 "$REPO/tools/_paths.py" lpjml.binary)"
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
DEFINES="${LPJ_DEFINES--DFROM_RESTART}"
read -r -a DEFS <<< "$DEFINES"
echo "sbatch_cmodel: defines = ${DEFINES:-(none, i.e. the spin-up branch)}"

# ─── t1: the config pre-flight. Validates without running, so it is free. ──────────────────────
if (( CHECK )); then
  echo "sbatch_cmodel: pre-flight with lpjcheck (validates the config and every input, no run)"
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
# Inputs, all exported by the job script: LPJBIN LPJ_DEFS MANIFEST
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
n=0
while IFS=$'\t' read -r name cfg rdir; do
  [ -z "${name// }" ] && continue
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
echo "=== launched $n of $want members; waiting ==="
if [ "$n" -ne "$want" ]; then
  echo "LAUNCH SHORTFALL: the manifest has $want lines but only $n started." >&2
fi
wait

# The verdict is the model's own line in each member's own log, never the exit codes above.
ok=0
while IFS=$'\t' read -r name cfg rdir; do
  [ -z "${name// }" ] && continue
  if grep -q 'successfully terminated' "$rdir/lpjml.$name.log" 2>/dev/null; then
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
module list 2>&1 || true
$BODY
echo "=== JOB DONE tag=$TAG exit=\$rc ==="
echo "=== NOTE: the exit code is NOT the verdict. Require the model's own line:"
echo "===   'lpjml successfully terminated, <n> grid cells processed.'"
exit \$rc
SLURM
)

echo "submitted $TAG as job $JOBID  (log: logs/$TAG.$JOBID.out)"
echo "run dir: $RUN_DIR   runs: $NRUNS"
echo
echo "JUDGE IT BY THE MODEL'S OWN LINE, not by the exit code:"
if [[ -n "$MANIFEST" ]]; then
  # Each member logs to its own run directory, so the job log alone cannot prove all of them
  # finished. The harvest command counts the members that printed the model's own line, and the
  # answer must be $NRUNS -- anything less is a partial campaign wearing a green exit code.
  HARVEST="grep -l 'successfully terminated' \$(awk -F'\t' 'NF{print \$3\"/lpjml.\"\$1\".log\"}' $MANIFEST) | wc -l   # must be $NRUNS"
  CMDLINE="LPJ_DEFINES='$DEFINES' scripts/sbatch_cmodel.sh --manifest $MANIFEST $TAG"
else
  HARVEST="grep 'successfully terminated' logs/$TAG.$JOBID.out"
  CMDLINE="LPJ_DEFINES='$DEFINES' scripts/sbatch_cmodel.sh $TAG $CONFIG $RUN_DIR"
fi
echo "  $HARVEST"

python3 "$REPO/tools/campaigns.py" launch \
  --line "$LINE" --tag "$TAG" --job "$JOBID" \
  --partition "$PARTITION" --cpus "$NTASKS" \
  --log-glob "logs/$TAG.$JOBID.out" \
  --cmd "$CMDLINE" \
  --harvest-cmd "$HARVEST" \
  ${EXPECT:+--expect $EXPECT}
