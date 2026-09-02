#!/usr/bin/env bash
# PreToolUse[Bash] — DENY heavy work on the login node, and deny any submission path that would
# bypass the campaign ledger.
#
# WHY A DENY HOOK AND NOT DOCUMENTATION. The predecessor documented "anything over a few seconds
# goes to SLURM" in prose, and it was violated until a deny hook existed. Every rule in that repo
# that was prose was violated; every rule that was a hook or a gate held.
#
# What it blocks, and why each one:
#   * raw `sbatch` / `srun` submission  -> the wrapper is what writes the campaign ledger row, and
#     results arrive after the launching session has ended. A job with no row is a job nobody
#     returns for. Override: ALLOW_RAW_SBATCH=1 (and then write the row by hand).
#   * a wrapper invocation for a training/eval tag with no --exp -> an experiment with no
#     pre-registration cannot be launched at all.
#   * heavy Python on the login node (train/bench/corpus/sweep/eval/probe/export, torch, nohup,
#     backgrounding) -> overloads the shared login node and, worse, dies with the session.
#   * a direct call to the LPJmL-FIT binary -> same, plus it needs its module environment.
# Auto-allowed inside a job ($SLURM_JOB_ID set). Escape hatch: ALLOW_LOGIN_HEAVY=1.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ -z "$CMD" ]] && exit 0
[[ -n "${SLURM_JOB_ID-}" ]] && exit 0
[[ -n "${ALLOW_LOGIN_HEAVY-}" ]] && exit 0

deny() {
  python3 - "$1" <<'PY'
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}))
PY
  exit 0
}

# Scheduler queries and the wrappers themselves always pass.
if [[ "$CMD" =~ (^|[[:space:];&|])(squeue|sacct|sinfo|scontrol|scancel|sstat)([[:space:]]|$) ]]; then exit 0; fi
if [[ "$CMD" =~ scripts/sbatch_[a-z_]+\.sh ]]; then
  # ... but a training/eval submission must carry a pre-registration.
  if [[ "$CMD" =~ (train|eval|score|fit|sweep|response|rung) ]] && [[ ! "$CMD" =~ --exp[[:space:]] ]]; then
    deny "This looks like an experiment submission with no --exp <exp_id>.

An experiment must be PRE-REGISTERED before it runs: estimand, reference basis, folds, and every
null WITH THE VALUE IT MUST RETURN. Otherwise the result is unfalsifiable after the fact.

  cp -r experiments/_template experiments/<LINE>-\$(date +%Y%m%d)-<slug>
  \$EDITOR experiments/<id>/preregistration.yaml
  tools/seal_experiment.py <id>
  scripts/sbatch_py.sh --exp <id> <tag> <script.py>

Skill: experiment-registry. If this genuinely is not an experiment, rename the tag."
  fi
  exit 0
fi

if [[ "$CMD" =~ (^|[[:space:];&|])(sbatch|srun)([[:space:]]|$) ]] && [[ -z "${ALLOW_RAW_SBATCH-}" ]]; then
  deny "Raw sbatch/srun is denied. Submit through a wrapper instead:

  scripts/sbatch_py.sh [--exp <id>] <tag> <script.py> [args...]
  scripts/sbatch_cmodel.sh <tag> ...        # the LPJmL-FIT model

The wrapper writes the row in campaigns/<line>/ledger.jsonl. That row is the ONLY reason a later
session can find, judge and harvest this job -- results here arrive hours to days after the session
that launched them has ended, so a job with no ledger row is a job nobody comes back for.

Genuinely need a raw submission (a chained .jcf, say)? ALLOW_RAW_SBATCH=1, then record it:
  tools/campaigns.py launch --line <L> --tag <tag> --job <jobid> ..."
fi

if [[ "$CMD" =~ bin/lpjml([[:space:]]|$) ]]; then
  deny "Do not run the LPJmL-FIT binary directly from a session.

It needs its exact module environment, it is far too slow for the login node, and a run started
here dies with the session. Use:  scripts/sbatch_cmodel.sh <tag> ...
Skill: cmodel-run (the module set, the config pre-flight, the completion line to require)."
fi

if [[ "$CMD" =~ nohup[[:space:]] ]] || [[ "$CMD" =~ [^\&]\&[[:space:]]*$ ]]; then
  if [[ "$CMD" =~ (python|torch|\.py([[:space:]]|$)) ]]; then
    deny "A backgrounded or nohup'd Python job on the login node dies with the session, and its
result is then unrecoverable. Submit it: scripts/sbatch_py.sh <tag> <script.py>"
  fi
fi

if [[ "$CMD" =~ python[0-9.]*[[:space:]] ]] || [[ "$CMD" =~ \.py([[:space:]]|$) ]]; then
  if [[ "$CMD" =~ (train|bench|corpus|sweep|eval|probe|export|spinup|rollout|fit_|score_) ]]; then
    deny "This looks like heavy Python on the login node. It shares one node with every other
session, and it dies when this session ends.

  scripts/sbatch_py.sh <tag> <script.py> [args...]

A genuinely quick check (a few seconds) is fine: ALLOW_LOGIN_HEAVY=1 <your command>"
  fi
fi
exit 0
