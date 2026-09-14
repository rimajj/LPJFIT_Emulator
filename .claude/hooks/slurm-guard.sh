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
#
# pathsafety: not-a-job (this file REFUSES submission; it must name sbatch in order to match it,
# and was duly asked by the pathsafety gate for an --account flag and a job-completion sentinel)
# Auto-allowed inside a job ($SLURM_JOB_ID set). Escape hatch: ALLOW_LOGIN_HEAVY=1.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
[[ -z "$CMD" ]] && exit 0
[[ -n "${SLURM_JOB_ID-}" ]] && exit 0
[[ -n "${ALLOW_LOGIN_HEAVY-}" ]] && exit 0

# WHAT THE RULES BELOW ARE MATCHED AGAINST: the command with the ARGUMENTS OF PROSE-CARRYING FLAGS
# removed. Every rule here is a keyword match over the command string, so it used to fire on any
# command that merely MENTIONED one of those words. Two commands that run nothing were refused:
#   python3 tools/inbound.py --to D --body "see corpus/state.py:159"   -> "heavy Python"
#   git commit -m "fix(launcher): the sbatch wrapper lost three jobs"  -> "ledger bypass"
#
# This is the third instance in this repo of ONE bug shape -- A GUARD MATCHING TEXT THAT IS NOT WHAT
# IT GUARDS. The other two are fixed in commit-guard.sh (an inline `git add`, and a commit message
# containing " -a " widening the checked set). The workaround here was to prefix ALLOW_LOGIN_HEAVY=1
# to ordinary `git` and `inbound` commands, which is worse than the annoyance it solved: it trains
# the reflex of disabling the guard on commands the guard was never for, and that reflex does not
# stop at the ones that are harmless.
#
# WHY BY FLAG AND NOT BY QUOTING. commit-guard.sh strips every quoted string. That is right there
# and wrong here: `python3 -c "import torch; torch.zeros(1)"` is a quoted string that IS the
# program, and is exactly what this hook exists to deny. So the list is closed and explicit, and
# every entry takes free text by construction -- no job can be launched through `--body`. It is
# every prose-carrying flag in the repo, checked 2026-09-14: -m (git), --message, --body and
# --subject (tools/inbound.py), --reason (tools/campaigns.py), --allow-red (tools/merge.sh).
#
# DELIBERATELY A SECOND python3 RATHER THAN FOLDED INTO THE JSON READ ABOVE, at ~30 ms per Bash
# call. That read fails OPEN -- a crash there empties CMD and the hook allows everything, silently.
# Keeping the lexing separate means its own failure modes (below) fall back to the RAW command, i.e.
# to the old broad matching, and can never widen into a total bypass.
#
# FAILS CLOSED, twice over: a command that will not lex keeps the raw string, and so does an empty
# or crashed result.
CMD_SCAN="$(printf '%s' "$CMD" | python3 -c '
import shlex, sys
raw = sys.stdin.read()
PROSE = {"--message", "--body", "--subject", "--reason", "--allow-red"}


def is_prose_arg(flag, arg):
    if flag in PROSE:
        return True
    # -m is a git message here, but a MODULE in `python3 -m torch.distributed.run`. A commit
    # message has whitespace; a module name never does. That is the whole difference.
    return flag == "-m" and any(c.isspace() for c in arg)


try:
    toks = shlex.split(raw)
except ValueError:
    print(raw)
    raise SystemExit
out, i = [], 0
while i < len(toks):
    t = toks[i]
    head, sep, _ = t.partition("=")
    if sep and head in PROSE:
        out.append(head)
        i += 1
        continue
    if i + 1 < len(toks) and is_prose_arg(t, toks[i + 1]):
        out.append(t)
        i += 2
        continue
    out.append(t)
    i += 1
print(" ".join(out))
' 2>/dev/null || printf '%s' "$CMD")"
[[ -z "$CMD_SCAN" ]] && CMD_SCAN="$CMD"

# ...AND the same variable written as a PREFIX ON THE COMMAND, which is the form this hook's own
# refusal message tells you to use. It never worked: a PreToolUse hook runs in the harness's
# environment, not in the shell the command is about to run in, so `ALLOW_LOGIN_HEAVY=1 <cmd>` was
# still denied and the advice was unusable. An escape hatch that the guard advertises must actually
# open. Read off CMD_SCAN too, so that QUOTING the prefix inside a message cannot open it.
if [[ "$CMD_SCAN" =~ (^|[[:space:]\;\&\|])ALLOW_LOGIN_HEAVY=[^[:space:]]+[[:space:]] ]]; then exit 0; fi
if [[ "$CMD_SCAN" =~ (^|[[:space:]\;\&\|])ALLOW_RAW_SBATCH=[^[:space:]]+[[:space:]] ]]; then
  # Deliberate, and it leaves a trace in the transcript -- but the ledger row is still owed:
  #   tools/campaigns.py launch --line <L> --tag <tag> --job <jobid> ...
  exit 0
fi

deny() {
  python3 - "$1" <<'PY'
import json,sys
print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}))
PY
  exit 0
}

# Scheduler queries and the wrappers themselves always pass.
if [[ "$CMD_SCAN" =~ (^|[[:space:];&|])(squeue|sacct|sinfo|scontrol|scancel|sstat)([[:space:]]|$) ]]; then exit 0; fi
if [[ "$CMD_SCAN" =~ scripts/sbatch_[a-z_]+\.sh ]]; then
  # ... but a training/eval submission must carry a pre-registration.
  if [[ "$CMD_SCAN" =~ (train|eval|score|fit|sweep|response|rung) ]] && [[ ! "$CMD_SCAN" =~ --exp[[:space:]] ]]; then
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

if [[ "$CMD_SCAN" =~ (^|[[:space:];&|])(sbatch|srun)([[:space:]]|$) ]] && [[ -z "${ALLOW_RAW_SBATCH-}" ]]; then
  deny "Raw sbatch/srun is denied. Submit through a wrapper instead:

  scripts/sbatch_py.sh [--exp <id>] <tag> <script.py> [args...]
  scripts/sbatch_cmodel.sh <tag> ...        # the LPJmL-FIT model

The wrapper writes the row in campaigns/<line>/ledger.jsonl. That row is the ONLY reason a later
session can find, judge and harvest this job -- results here arrive hours to days after the session
that launched them has ended, so a job with no ledger row is a job nobody comes back for.

Genuinely need a raw submission (a chained .jcf, say)? ALLOW_RAW_SBATCH=1, then record it:
  tools/campaigns.py launch --line <L> --tag <tag> --job <jobid> ..."
fi

if [[ "$CMD_SCAN" =~ bin/lpjml([[:space:]]|$) ]]; then
  deny "Do not run the LPJmL-FIT binary directly from a session.

It needs its exact module environment, it is far too slow for the login node, and a run started
here dies with the session. Use:  scripts/sbatch_cmodel.sh <tag> ...
Skill: cmodel-run (the module set, the config pre-flight, the completion line to require)."
fi

if [[ "$CMD_SCAN" =~ nohup[[:space:]] ]] || [[ "$CMD_SCAN" =~ [^\&]\&[[:space:]]*$ ]]; then
  if [[ "$CMD_SCAN" =~ (python|torch|\.py([[:space:]]|$)) ]]; then
    deny "A backgrounded or nohup'd Python job on the login node dies with the session, and its
result is then unrecoverable. Submit it: scripts/sbatch_py.sh <tag> <script.py>"
  fi
fi

if [[ "$CMD_SCAN" =~ python[0-9.]*[[:space:]] ]] || [[ "$CMD_SCAN" =~ \.py([[:space:]]|$) ]]; then
  # `torch` is in this list because the header above has always claimed it was, and it was not:
  # importing torch on the login node allocates a multi-gigabyte process and a thread pool per
  # session. The keyword set is broad and still matches anywhere in the command -- but the command
  # it now matches is CMD_SCAN, which no longer carries anyone's prose. Breadth costs only false
  # denials of things that MENTION a keyword, and those are exactly what the stripping removes.
  if [[ "$CMD_SCAN" =~ (train|bench|corpus|sweep|eval|probe|export|spinup|rollout|fit_|score_|torch) ]]; then
    deny "This looks like heavy Python on the login node. It shares one node with every other
session, and it dies when this session ends.

  scripts/sbatch_py.sh <tag> <script.py> [args...]

A genuinely quick check (a few seconds) is fine: ALLOW_LOGIN_HEAVY=1 <your command>"
  fi
fi
exit 0
