#!/usr/bin/env bash
# Run the LPJmL-FIT C model, and record it in the campaign ledger.
#
#   scripts/sbatch_cmodel.sh --check <tag> <config.js>      # config pre-flight only, no job
#   scripts/sbatch_cmodel.sh <tag> <config.js> <run-dir>    # submit the run
#
# Env knobs: NTASKS=1 TIME=00:30:00 PARTITION=priority QOS= ACCOUNT=waldspektrum
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
#    selects the 1000-year spin-up branch and the run takes days instead of seconds.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CHECK=0
if [[ "${1-}" == "--check" ]]; then CHECK=1; shift; fi
TAG="${1:?usage: sbatch_cmodel.sh [--check] <tag> <config.js> [run-dir]}"
CONFIG="${2:?usage: sbatch_cmodel.sh [--check] <tag> <config.js> [run-dir]}"
RUN_DIR="${3:-$(dirname "$CONFIG")}"

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

[[ -f "$CONFIG" ]] || { echo "sbatch_cmodel: no such config: $CONFIG" >&2; exit 2; }
mkdir -p "$RUN_DIR/output" "$RUN_DIR/restart"

# ─── t1: the config pre-flight. Validates without running, so it is free. ──────────────────────
if (( CHECK )); then
  echo "sbatch_cmodel: pre-flight with lpjcheck (validates the config and every input, no run)"
  set +e
  "$LPJCHECK" -DFROM_RESTART "$CONFIG"
  rc=$?
  set -e
  if (( rc == 0 )); then
    echo "sbatch_cmodel: t1 PASSED -- the model's own pre-flight accepts this config and restart."
  else
    echo "sbatch_cmodel: t1 FAILED (lpjcheck exit $rc). Fix the config before submitting." >&2
  fi
  exit $rc
fi

NTASKS="${NTASKS:-1}"
TIME="${TIME:-00:30:00}"
PARTITION="${PARTITION:-priority}"
ACCOUNT="${ACCOUNT:-waldspektrum}"
if [[ "$PARTITION" == "priority" ]]; then QOS="${QOS:-priority}"; else QOS="${QOS:-short}"; fi
LOGDIR="$REPO/logs"; mkdir -p "$LOGDIR"

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
export LPJOUTPATH="$RUN_DIR"
export LPJRESTARTPATH="$RUN_DIR"
cd "$RUN_DIR"
echo "=== JOB START tag=$TAG host=\$(hostname) ntasks=$NTASKS ==="
module list 2>&1 || true
mpirun "$LPJBIN" -DFROM_RESTART "$CONFIG"
rc=\$?
echo "=== JOB DONE tag=$TAG mpirun_exit=\$rc ==="
echo "=== NOTE: the exit code is NOT the verdict. Require the model's own line:"
echo "===   'lpjml successfully terminated, <n> grid cells processed.'"
exit \$rc
SLURM
)

echo "submitted $TAG as job $JOBID  (log: logs/$TAG.$JOBID.out)"
echo "run dir: $RUN_DIR"
echo
echo "JUDGE IT BY THE MODEL'S OWN LINE, not by the exit code:"
echo "  grep -c 'successfully terminated' logs/$TAG.$JOBID.out"

python3 "$REPO/tools/campaigns.py" launch \
  --line "$LINE" --tag "$TAG" --job "$JOBID" \
  --partition "$PARTITION" --cpus "$NTASKS" \
  --log-glob "logs/$TAG.$JOBID.out" \
  --cmd "scripts/sbatch_cmodel.sh $TAG $CONFIG $RUN_DIR" \
  --harvest-cmd "grep 'successfully terminated' logs/$TAG.$JOBID.out" \
  ${EXPECT:+--expect $EXPECT}
