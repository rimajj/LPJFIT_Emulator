"""The login-node guard must still deny what it denied, and its escape hatches must actually open.

WHY THIS TEST EXISTS. `.claude/hooks/slurm-guard.sh` refuses heavy work on the shared login node and
refuses any submission path that skips the campaign ledger. Its refusal messages offer an override —
`ALLOW_LOGIN_HEAVY=1 <your command>`, `ALLOW_RAW_SBATCH=1 <your command>` — and **neither worked**.
A PreToolUse hook runs in the harness's environment, not in the shell the command is about to run
in, so the guard checked a variable that a command prefix can never set. The advice was unusable.

That matters because every rule is a KEYWORD match over the command string: a command is heavy if
it mentions Python and any of train/bench/corpus/sweep/eval/probe/… anywhere. In a project whose
subject matter is corpora and training, ordinary commands say those words — handing
`tools/inbound.py` a message body that quoted `corpus/state.py` was refused as a heavy job, and a
commit message naming the `sbatch` wrapper was refused as a ledger bypass. Neither runs anything.

FIXED 2026-09-14 by matching the rules against the command with the ARGUMENTS OF PROSE-CARRYING
FLAGS removed, so the guard stops reading other people's prose as commands. Living with it meant
prefixing `ALLOW_LOGIN_HEAVY=1` to ordinary `git` and `inbound` commands — which is worse than the
annoyance it solved, because it trains the reflex of switching the guard off on commands it was
never for, and that reflex does not stop at the harmless ones.

⚠ THE TWO HALVES BELOW PULL AGAINST EACH OTHER, which is the point of pinning both. Every case in
MUST_ALLOW is a command that would have been wrongly denied; every case in MUST_DENY is a way prose
stripping could open a real hole, and the two marked ones are the exact reason the rule is written
by FLAG rather than by quoting. Widening the prose list will turn one of them red.

A hook is invisible when it works, so nothing but a test distinguishes "correctly allowing this"
from "not denying anything at all" — the sibling guard was first written with no execute bit and
every case passed vacuously.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "slurm-guard.sh"
# Every variable that makes the hook allow unconditionally. Stripped from the child; see `verdict`.
_OVERRIDES = frozenset({"ALLOW_LOGIN_HEAVY", "ALLOW_RAW_SBATCH", "SLURM_JOB_ID"})
sys.path.insert(0, str(ROOT / "tools"))

import check_no_abs_paths as checker  # noqa: E402

MUST_DENY = [
    # heavy Python on the shared login node: it dies with the session, taking the result with it
    "python3 scripts/corpus_build.py --tier pilot",
    "python scripts/train_emulator.py --folds 15deg",
    # ⚠ A QUOTED STRING THAT IS THE PROGRAM. This is why prose is stripped by FLAG and not by
    # quoting: commit-guard.sh strips every quoted string, and doing that here would allow the one
    # command this hook most exists to deny.
    'python3 -c "import torch; torch.zeros(1)"',
    # ⚠ `-m` TAKES A MODULE, NOT A MESSAGE, once the program is Python. Settled by whitespace: a
    # commit message has spaces, a module path never does. Read `-m` as prose unconditionally and
    # this launches a distributed training job on the login node.
    "python3 -m torch.distributed.run --nproc 4 scripts/fit_model.py",
    # prose stripping must not launder a real job: the keyword is in the PROGRAM, not the message
    'python3 scripts/corpus_build.py --body "harmless"',
    # a submission that bypasses the ledger, so no later session can find the job
    "sbatch job.sh",
    "srun --ntasks 1 hostname",
    # an experiment submission with no pre-registration
    "scripts/sbatch_py.sh train scripts/train_emulator.py",
    # the C model needs its module environment and a scheduler
    "bin/lpjml lpjml.js",
    # ⚠ THE FIVE WAYS THE 2026-09-15 VERB ALLOWLIST COULD HAVE OPENED A HOLE. Each must stay red:
    # a safe verb cannot launder an unsafe one later in the same command...
    "cat notes.md && python3 scripts/corpus_build.py --tier pilot",
    # ...including when no whitespace surrounds the operator, so shlex keeps it in one token
    "cat a.py&&python3 scripts/corpus_build.py",
    # executing a script is not reading it, however the path is spelled
    "./scripts/corpus_build.py --tier pilot",
    # an unrecognised verb keeps the OLD behaviour rather than being assumed harmless
    "bash -c 'python3 scripts/corpus_build.py'",
    # a substitution can hide any program at all behind a safe-looking verb
    "cat $(python3 scripts/corpus_build.py --print-path)",
]

MUST_ALLOW = [
    # the wrappers themselves: they are what writes the ledger row
    "scripts/sbatch_py.sh mytag scripts/summarise.py",
    "scripts/sbatch_py.sh --exp X-20260908-warming-response score scripts/score.py",
    "scripts/sbatch_cmodel.sh subset20 --years 1",
    # scheduler queries are how a session judges a silent job
    "sacct -j 123456 --format=Elapsed,TotalCPU",
    "squeue -u jamirp",
    "scancel 123456",
    # ordinary work must not trip it
    "git status --short",
    "python3 tools/check_budgets.py",
    "python3 -m pytest -q tests/test_folds.py",
    # COMMANDS THAT RUN NOTHING AND ONLY TALK ABOUT ONE. Each was denied before 2026-09-14, and the
    # only way past was to switch the guard off. The words are cargo: no job can be launched
    # through `-m`, `--body` or `--reason`.
    'python3 tools/inbound.py --to D --body "see corpus/state.py:159"',
    'git commit -m "fix(launcher): the sbatch wrapper lost three jobs"',
    'git commit -m "docs(corpus): rebuild corpus_build.py under the genuine second seed"',
    'python3 tools/campaigns.py abandon --tag t --reason "the corpus build died"',
    # READING A FILE IS NOT RUNNING IT. Stripping prose on 2026-09-14 fixed the FLAGS and left the
    # FILE PATHS, so all fifteen of these were denied until 2026-09-15 -- a keyword in the PATH of
    # a file being read still counted as a job. Measured, not supposed.
    "cat scripts/train_emulator.py",
    "wc -l scripts/corpus_build.py",
    "head -50 src/vegemu/corpus/state.py",
    "tail -20 scripts/corpus_pilot.py",
    "grep -n pft_frac src/vegemu/corpus/state.py",
    "ls -la src/vegemu/corpus/state.py",
    "sed -n '1,20p' scripts/corpus_build.py",
    "diff scripts/corpus_build.py scripts/corpus_pilot.py",
    "cp scripts/corpus_build.py /tmp/backup.py",
    "ruff check src/vegemu/corpus/state.py",
    "ruff format --check scripts/corpus_build.py",
    "git diff scripts/corpus_build.py",
    "git log --oneline -5 -- scripts/train_emulator.py",
    # ⚠ THE ONE THAT MADE IT URGENT. commit-guard.sh denies staging and committing in one command,
    # so staging MUST be its own command -- and this hook refused that command for any file under
    # corpus/ or named train_*. Lines D and T could not stage their own principal sources without
    # switching the guard off, on every commit: the exact reflex the 2026-09-14 fix existed to stop.
    "git add scripts/corpus_build.py",
    # a pipeline is exempt only if EVERY segment's verb is one that cannot run a file
    "head -50 src/vegemu/corpus/state.py | wc -l",
]

# The overrides the guard's own messages advertise, in the only form a Bash tool call can use.
MUST_ALLOW_WITH_HATCH = [
    "ALLOW_LOGIN_HEAVY=1 python3 scripts/corpus_build.py --tier pilot",
    'ALLOW_LOGIN_HEAVY=1 python3 tools/inbound.py --body "corpus/state.py"',
    "ALLOW_RAW_SBATCH=1 sbatch chained.jcf",
]


def verdict(command: str) -> str:
    """Either "deny" or "allow", as the hook decides for `command`.

    ⚠ THE THREE OVERRIDE VARIABLES ARE STRIPPED FROM THE CHILD'S ENVIRONMENT. The hook exits 0 --
    allow -- as its very first act if any of them is set, and it inherits whatever the session
    exported. So running this suite from a shell that had used the documented
    `ALLOW_LOGIN_HEAVY=1` escape hatch turned every MUST_DENY case red at once, which reads as "the
    guard is broken" rather than "the guard is switched off for this shell". A test of a deny rule
    must control the thing that disables the rule.
    """
    env = {k: v for k, v in os.environ.items() if k not in _OVERRIDES}
    proc = subprocess.run(
        [str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(f"hook exited {proc.returncode}: {proc.stderr}")
    out = proc.stdout.strip()
    if not out:
        return "allow"
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        pytest.fail(f"hook emitted non-JSON: {out[:200]}")
    return str(payload.get("hookSpecificOutput", {}).get("permissionDecision", "allow"))


def test_hook_is_executable() -> None:
    """Without the execute bit it denies nothing, and every case below passes vacuously."""
    assert HOOK.is_file(), f"missing: {HOOK}"
    assert HOOK.stat().st_mode & 0o111, f"{HOOK} is not executable, so it denies nothing"


@pytest.mark.parametrize("command", MUST_DENY)
def test_heavy_and_ledger_bypassing_commands_are_denied(command: str) -> None:
    assert verdict(command) == "deny", f"the guard let this through: {command}"


@pytest.mark.parametrize("command", MUST_ALLOW)
def test_wrappers_queries_and_ordinary_work_are_allowed(command: str) -> None:
    assert verdict(command) == "allow", f"the guard blocked legitimate work: {command}"


@pytest.mark.parametrize("command", MUST_ALLOW_WITH_HATCH)
def test_the_advertised_escape_hatch_actually_opens(command: str) -> None:
    """The prefix form, which is what the refusal message tells you to type.

    If this fails, the guard is refusing the very command it told you to run -- and the only way
    past it is to edit the guard, which is how a guard stops being trusted.
    """
    assert verdict(command) == "allow", f"the hatch the guard advertises does not open: {command}"


def test_the_pathsafety_gate_does_not_mistake_this_guard_for_a_job_script() -> None:
    """A file that must NAME `sbatch` in order to refuse it is not a thing that submits jobs.

    The `pathsafety` gate treats any shell file mentioning `sbatch` as a job script and demands an
    `--account` flag and a completion sentinel, which is nonsense for a hook whose purpose is to
    deny submission. It is exempted by a declared marker rather than by inspection: telling
    "submits" from "talks about submitting" means lexing shell, and the attempt mis-scanned the real
    wrapper -- a comment with an apostrophe opened a quoted span that swallowed its `$(sbatch ...)`
    line. Hence the second half of this test, which is the half that matters: the exemption must not
    have leaked to the two scripts that DO submit.
    """

    def is_job_script(rel: str) -> bool:
        text = (ROOT / rel).read_text(encoding="utf-8")
        return bool(checker.SBATCH_RE.search(text)) and not checker.NOT_A_JOB_MARK.search(text)

    assert not is_job_script(".claude/hooks/slurm-guard.sh"), (
        "the guard is being checked as if it submitted jobs"
    )
    for wrapper in ("scripts/sbatch_py.sh", "scripts/sbatch_cmodel.sh"):
        assert is_job_script(wrapper), f"{wrapper} SUBMITS and must stay under the SLURM checks"


def test_the_escape_hatch_is_named_the_same_way_in_the_message_and_the_check() -> None:
    """Read both out of the hook: a drifted name would make the printed advice wrong again.

    Restating the variable names here would keep passing after the hook renamed them, which is the
    failure this test is for.
    """
    text = HOOK.read_text(encoding="utf-8")
    for var in ("ALLOW_LOGIN_HEAVY", "ALLOW_RAW_SBATCH"):
        # once in the prefix check, once in the message that offers it
        assert text.count(var) >= 2, f"{var} is checked or advertised, but not both"
