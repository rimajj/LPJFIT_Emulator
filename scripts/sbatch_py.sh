#!/usr/bin/env bash
# Submit a Python job to SLURM, and record it in the campaign ledger.
#
#   scripts/sbatch_py.sh <tag> <script.py> [args...]
#   scripts/sbatch_py.sh --exp <exp_id> <tag> <script.py> [args...]
#
# Env knobs (see the FORWARD list below -- an unlisted variable does NOT reach the job):
#   TIME=04:00:00  NCPUS=1  MEM_PER_CPU=  PARTITION=standard  QOS=  ACCOUNT=
#   HARVEST_CMD=   HARVEST_BY=            EXPECT=             DEPENDENCY=afterok:<jid>
#
# ─── WHY THIS WRAPPER IS THE ONLY WAY TO SUBMIT ────────────────────────────────────────────────
# A PreToolUse hook DENIES raw `sbatch`/`srun`. That is not bureaucracy: this wrapper is what
# writes the campaign ledger row, and results here arrive hours to days after the launching
# session has ended. A job with no ledger row is a job nobody will ever come back for.
#
# It also refuses to submit an experiment whose pre-registration is not sealed and committed, and
# it stamps that pre-registration's hash into the job environment so the result can prove which
# version governed the run.
#
# ─── THREE TRAPS THIS WRAPPER EXISTS TO PREVENT ────────────────────────────────────────────────
# 1. SELF-LOCATION. `REPO` is derived from this file, so a copy of the repo in a line's worktree
#    submits against ITS OWN tree. Predecessor scripts that hardcoded the repo root silently wrote
#    their output into the shared integration checkout and lost the result from the branch.
# 2. THE ENV-FORWARD LIST. SLURM's --export=ALL carries the environment, but a variable set only as
#    a command prefix (`FOO=1 scripts/sbatch_py.sh ...`) reaches the WRAPPER, not the job -- so the
#    job silently runs with FOO's default. Anything the job needs must be `export`ed, and the
#    wrapper echoes what it forwarded so an empty list is visible rather than assumed.
#    ⚠ AND THE MIRROR TRAP: a knob whose NAME COLLIDES with a variable this wrapper uses is
#    overwritten, and --export=ALL then ships the WRAPPER's value to the job. `export TAG=x` before
#    calling this makes the job run under the wrapper's tag, the job exits 0, and the scorer finds
#    nothing. The reserved names are listed in RESERVED below and the wrapper REFUSES to run if one
#    of them is already exported.
# 3. /tmp IS NOT SHARED. A compute node cannot read the login node's /tmp, so every path the job
#    reads or writes must be on /p. The wrapper refuses a --out or --input under /tmp.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_CFG="$REPO/tools/_paths.py"

# ─── reserved names (trap 2) ───────────────────────────────────────────────────────────────────
# Only names this wrapper OVERWRITES from its positional arguments are dangerous. The predecessor's
# exact failure: `export TAG=predict; sbatch_julia.sh S-mytag ...` -- the positional assignment
# clobbered the exported value, --export=ALL shipped the WRAPPER's tag to the job, the job exited 0,
# and the scorer reported "scoring 0 dumps". That reads as a missing campaign, not a clobbered knob.
#
# Deliberately NOT reserved: TIME/NCPUS/PARTITION/QOS/ACCOUNT are documented knobs and are meant to
# come from the environment; REPO/LOGDIR/PY are assigned unconditionally here before any use, and
# REPO in particular is so commonly exported in an interactive shell that refusing on it would make
# the wrapper unusable for no safety gain.
RESERVED="TAG SCRIPT EXP_ID JOBID PREREG_SHA LINE"
for name in $RESERVED; do
  if [[ -n "${!name-}" ]]; then
    echo "sbatch_py: refusing to run: \$$name is already exported (${!name})." >&2
    echo "  This wrapper assigns that name from its own arguments, so --export=ALL would ship the" >&2
    echo "  WRAPPER's value to your job -- the job would succeed while reading the wrong knob." >&2
    echo "  Rename your variable. (Reserved: $RESERVED)" >&2
    exit 2
  fi
done

# ─── args ──────────────────────────────────────────────────────────────────────────────────────
EXP_ID=""
if [[ "${1-}" == "--exp" ]]; then EXP_ID="${2:?--exp needs an experiment id}"; shift 2; fi
TAG="${1:?usage: sbatch_py.sh [--exp <id>] <tag> <script.py> [args...]}"
SCRIPT="${2:?usage: sbatch_py.sh [--exp <id>] <tag> <script.py> [args...]}"
shift 2

LINE="${TAG%%-*}"
if [[ ! "$LINE" =~ ^[DTX]$ ]]; then
  echo "sbatch_py: tag must start with the work line, e.g. D-corpus-v0 (got '$TAG')" >&2
  exit 2
fi

TIME="${TIME:-04:00:00}"
NCPUS="${NCPUS:-1}"
PARTITION="${PARTITION:-standard}"
ACCOUNT="${ACCOUNT:-waldspektrum}"
LOGDIR="$REPO/logs"; mkdir -p "$LOGDIR"

# ─── partition envelope and QOS ────────────────────────────────────────────────────────────────
# This cluster REQUIRES an explicit QOS, and the QOS must MATCH the partition. Getting either wrong
# fails at submit time with "Invalid qos specification", which reads like a permissions problem
# rather than a mismatched field -- so the default is derived from the partition here, AFTER the
# partition is known. (Defaulting QOS before this point is the bug that produced exactly that error:
# it set qos=short and then the priority branch could no longer override it.)
#
# Measured with `sacctmgr show qos`:
#   short    1 day  / 2048 cpu   the default for `standard`
#   medium   7 days / 1024 cpu   for a campaign needing more than a day per job
#   long    30 days /   32 cpu
#   priority 1 day               must be paired with PARTITION=priority
if [[ "$PARTITION" == "priority" ]]; then
  QOS="${QOS:-priority}"
  # `priority` is usually idle and starts almost immediately, but is capped at 64 CPU / 350 GB PER
  # JOB, and the memory cap is strictly proportional and not raisable.
  if (( NCPUS > 64 )); then
    echo "sbatch_py: partition=priority is capped at 64 CPU per job (asked $NCPUS)." >&2
    echo "  Use PARTITION=standard (up to 2048 CPU), or split the work into smaller chunks." >&2
    exit 2
  fi
else
  QOS="${QOS:-short}"
fi

# ─── /tmp refusal (trap 3) ─────────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    # `set -u` is on, and TMPDIR is frequently unset on a login shell, so it must be defaulted --
    # otherwise this guard aborts the wrapper with "TMPDIR: unbound variable" instead of checking
    # the argument, which turns a helpful refusal into a confusing crash.
    /tmp/*|*=/tmp/*|"${TMPDIR:-/nonexistent}"/*)   # pathsafety: allow (this line IS the /tmp refusal)
      echo "sbatch_py: '$arg' is under /tmp, which compute nodes cannot read." >&2
      echo "  Put job inputs and outputs on shared /p (see config/paths.yaml scratch.root)." >&2
      exit 2 ;;
  esac
done

# ─── experiment pre-registration gate ──────────────────────────────────────────────────────────
PREREG_SHA=""
if [[ -n "$EXP_ID" ]]; then
  PREREG="$REPO/experiments/$EXP_ID/preregistration.yaml"
  [[ -f "$PREREG" ]] || { echo "sbatch_py: no such experiment: $EXP_ID" >&2; exit 2; }
  grep -q '^status: sealed' "$PREREG" || {
    echo "sbatch_py: $EXP_ID is not sealed. Seal it first:" >&2
    echo "    tools/seal_experiment.py $EXP_ID" >&2
    echo "  An experiment that is not pre-registered before it runs is not pre-registered." >&2
    exit 2; }
  if ! git -C "$REPO" diff --quiet -- "experiments/$EXP_ID/preregistration.yaml" 2>/dev/null; then
    echo "sbatch_py: $EXP_ID has uncommitted changes. Commit the seal before launching," >&2
    echo "  so the seal provably exists in history before the run it governs." >&2
    exit 2
  fi
  PREREG_SHA="$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$PREREG")"
  SEALED="$(python3 - "$REPO" "$EXP_ID" <<'PYEOF'
import json, sys, pathlib
root, exp = pathlib.Path(sys.argv[1]), sys.argv[2]
p = root / "experiments" / "registry.jsonl"
out = ""
if p.exists():
    for ln in p.read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("exp_id") == exp and r.get("prereg_sha256"):
                out = r["prereg_sha256"]
print(out)
PYEOF
)"
  if [[ "$PREREG_SHA" != "$SEALED" ]]; then
    echo "sbatch_py: live pre-registration hash does not match the sealed one." >&2
    echo "  live=${PREREG_SHA:0:12} sealed=${SEALED:0:12}" >&2
    echo "  A sealed pre-registration is immutable; a changed question is a NEW exp_id." >&2
    exit 2
  fi
fi

# ─── the env-forward list (trap 2) ─────────────────────────────────────────────────────────────
# Only these reach the job, plus anything the caller `export`ed. Add a name here when a job needs
# a new knob -- and note the RESERVED check above, which is what makes a collision loud.
FORWARD="CELLS NCELLS SEED SCENARIO CORPUS OUT MODE SMOKE PERTURB LEVELS \
         LPJ_IND_ALL_HEIGHTS LPJ_IND_TRUE_GPP VEGEMU_LINE VEGEMU_PREREG_SHA256"
FWD_ECHO=""
for v in $FORWARD; do [[ -n "${!v-}" ]] && FWD_ECHO="$FWD_ECHO $v=${!v}"; done

DEPFLAG=()
[[ -n "${DEPENDENCY-}" ]] && DEPFLAG=(--dependency="$DEPENDENCY")

# ─── the two pythons, and why they are not the same one ────────────────────────────────────────
# BOOTSTRAP_PY is whatever `python3` means on the login node -- 3.9 here. It is only allowed to run
# tools/_paths.py, which is written to need nothing but the standard library of that version.
# PY_BIN is the configured cluster interpreter and is what the JOB and every repo tool runs under.
#
# ⚠ THEY WERE CONFLATED, AND IT COST A CAMPAIGN LEDGER ROW. The ledger write below used to call
# bare `python3`, and `tools/campaigns.py` reaches `tools/_common.py`, which imports `tomllib` --
# absent before 3.11. So campaigns.py died with a traceback AFTER the job was already submitted:
# the submission printed success, the job ran, and nothing recorded it. It only bites in a shell
# whose `python3` is the system one, which is why earlier launches from an activated environment
# worked and this was invisible until 2026-09-10. That makes it worse, not better -- the wrapper's
# correctness depended on the caller's shell.
#
# And the fallback that used to be here (`|| echo python3`) turned a missing config key into a job
# silently running under 3.9. Resolution now fails loudly instead.
BOOTSTRAP_PY="python3"
PY_BIN="$($BOOTSTRAP_PY "$REPO/tools/_paths.py" cluster.python)" || {
  echo "sbatch_py: cannot resolve cluster.python from config/paths.yaml." >&2
  echo "  Refusing to guess: a job that runs under the wrong interpreter fails in the middle," >&2
  echo "  hours after this session ends." >&2
  exit 2
}

# The job's argument list. `printf '%q ' "$@"` with NO arguments prints the format once against an
# empty argument, so the job line gained a bare '' and argparse rejected it -- every job submitted
# with no script arguments died in five seconds on "unrecognized arguments:". Guard on $#.
SCRIPT_ARGS=""
if (( $# > 0 )); then SCRIPT_ARGS="$(printf '%q ' "$@")"; fi

JOBID=$(sbatch --parsable \
  --job-name="$TAG" \
  --account="$ACCOUNT" \
  --partition="$PARTITION" \
  ${QOS:+--qos="$QOS"} \
  --time="$TIME" \
  --cpus-per-task="$NCPUS" \
  ${MEM_PER_CPU:+--mem-per-cpu="$MEM_PER_CPU"} \
  --output="$LOGDIR/$TAG.%j.out" \
  --export=ALL \
  "${DEPFLAG[@]}" \
  <<SLURM
#!/usr/bin/env bash
set -uo pipefail
export VEGEMU_LINE="$LINE"
export VEGEMU_PREREG_SHA256="$PREREG_SHA"
export PYTHONUNBUFFERED=1     # a silent log is indistinguishable from a hung job; unbuffer it
cd "$REPO"
echo "=== JOB START tag=$TAG exp=${EXP_ID:-none} host=\$(hostname) ==="
echo "=== env forwarded:${FWD_ECHO:- (none)} ==="
"$PY_BIN" "$SCRIPT" $SCRIPT_ARGS
rc=\$?
echo "=== JOB DONE tag=$TAG exit=\$rc ==="
exit \$rc
SLURM
)

echo "submitted $TAG as job $JOBID  (log: logs/$TAG.$JOBID.out)"
echo "env forwarded:${FWD_ECHO:- (none)}"

# ─── the ledger row. THIS is why raw sbatch is denied. ─────────────────────────────────────────
# Under PY_BIN, not the bootstrap python -- see the note above. And loud on failure: the job is
# already queued by the time we get here, so a silent ledger failure leaves a running job nobody
# will come back for, which is the one outcome this wrapper exists to make impossible.
LEDGER_ARGS=(
  launch
  --line "$LINE" --tag "$TAG" --job "$JOBID"
  --partition "$PARTITION" --cpus "$NCPUS"
  --log-glob "logs/$TAG.$JOBID.out"
  --cmd "scripts/sbatch_py.sh ${EXP_ID:+--exp $EXP_ID} $TAG $SCRIPT $*"
)
# Written as `if` blocks so the optional knobs are one readable list; the point of the rewrite is
# the QUOTING below, not the control flow.
if [[ -n "$EXP_ID" ]]; then LEDGER_ARGS+=(--exp "$EXP_ID"); fi
if [[ -n "${PREREG_SHA-}" ]]; then LEDGER_ARGS+=(--prereg-sha256 "$PREREG_SHA"); fi
if [[ -n "${HARVEST_CMD-}" ]]; then LEDGER_ARGS+=(--harvest-cmd "$HARVEST_CMD"); fi
if [[ -n "${HARVEST_BY-}" ]]; then LEDGER_ARGS+=(--harvest-by "$HARVEST_BY"); fi
# Quoted as ONE argument: an EXPECT with spaces used to word-split into several positionals.
if [[ -n "${EXPECT-}" ]]; then LEDGER_ARGS+=(--expect "$EXPECT"); fi

if ! "$PY_BIN" "$REPO/tools/campaigns.py" "${LEDGER_ARGS[@]}"; then
  echo "" >&2
  echo "sbatch_py: ⚠ JOB $JOBID IS QUEUED BUT NOT IN THE LEDGER." >&2
  echo "  The submission succeeded; only the record failed. Either write the row by hand" >&2
  echo "  or cancel the job -- an unrecorded job is one nobody replays at session start:" >&2
  echo "    scancel $JOBID" >&2
  exit 1
fi
