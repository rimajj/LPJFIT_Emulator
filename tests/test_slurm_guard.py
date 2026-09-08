"""The login-node guard must still deny what it denied, and its escape hatches must actually open.

WHY THIS TEST EXISTS. `.claude/hooks/slurm-guard.sh` refuses heavy work on the shared login node and
refuses any submission path that skips the campaign ledger. Its refusal messages offer an override —
`ALLOW_LOGIN_HEAVY=1 <your command>`, `ALLOW_RAW_SBATCH=1 <your command>` — and **neither worked**.
A PreToolUse hook runs in the harness's environment, not in the shell the command is about to run
in, so the guard checked a variable that a command prefix can never set. The advice was unusable.

That matters because the heavy-Python rule is a KEYWORD match over the whole command string: a
command is heavy if it mentions Python and any of train/bench/corpus/sweep/eval/probe/… anywhere.
In a project whose subject matter is corpora and training, ordinary commands say those words —
handing `tools/inbound.py` a message body that quoted `corpus/state.py` was refused as a heavy job,
with an escape hatch that did not exist. A broad heuristic is the right trade only if the override
is real.

So the table below pins both halves at once: every deny the guard is FOR, and the two overrides.
A hook is invisible when it works, so nothing but a test distinguishes "correctly allowing this"
from "not denying anything at all" — the sibling guard was first written with no execute bit and
every case passed vacuously.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "slurm-guard.sh"

MUST_DENY = [
    # heavy Python on the shared login node: it dies with the session, taking the result with it
    "python3 scripts/corpus_build.py --tier pilot",
    "python scripts/train_emulator.py --folds 15deg",
    'python3 -c "import torch; torch.zeros(1)"',
    # ...including when the keyword only appears in a quoted argument. Broad on purpose; see the
    # module docstring. The override below is what makes that acceptable.
    'python3 tools/inbound.py --to D --body "see corpus/state.py:159"',
    # a submission that bypasses the ledger, so no later session can find the job
    "sbatch job.sh",
    "srun --ntasks 1 hostname",
    # an experiment submission with no pre-registration
    "scripts/sbatch_py.sh train scripts/train_emulator.py",
    # the C model needs its module environment and a scheduler
    "bin/lpjml lpjml.js",
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
]

# The overrides the guard's own messages advertise, in the only form a Bash tool call can use.
MUST_ALLOW_WITH_HATCH = [
    "ALLOW_LOGIN_HEAVY=1 python3 scripts/corpus_build.py --tier pilot",
    'ALLOW_LOGIN_HEAVY=1 python3 tools/inbound.py --body "corpus/state.py"',
    "ALLOW_RAW_SBATCH=1 sbatch chained.jcf",
]


def verdict(command: str) -> str:
    """Either "deny" or "allow", as the hook decides for `command`."""
    proc = subprocess.run(
        [str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
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


def test_the_escape_hatch_is_named_the_same_way_in_the_message_and_the_check() -> None:
    """Read both out of the hook: a drifted name would make the printed advice wrong again.

    Restating the variable names here would keep passing after the hook renamed them, which is the
    failure this test is for.
    """
    text = HOOK.read_text(encoding="utf-8")
    for var in ("ALLOW_LOGIN_HEAVY", "ALLOW_RAW_SBATCH"):
        # once in the prefix check, once in the message that offers it
        assert text.count(var) >= 2, f"{var} is checked or advertised, but not both"
