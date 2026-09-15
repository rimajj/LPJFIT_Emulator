"""The commit guard must deny a commit that stages its own files, and nothing else.

WHY THIS TEST EXISTS, AND WHY ITS ABSENCE WAS PART OF THE BUG. `.claude/hooks/commit-guard.sh` runs
the repo's checkers against the STAGED set before a commit lands. Its sibling `slurm-guard.sh` has
had a suite pinning both directions since it was written; this one had none. So when the rule at
`:38` was left testing the RAW command while the stripped copy thirty lines below was used only by
the rule beneath it, nothing noticed for six days. A hook is invisible when it works: without a
test, "correctly allowing this" and "not denying anything at all" look identical.

THE DEFECT, measured 2026-09-15: a commit whose MESSAGE merely mentioned staging was refused as if
the command staged files, in both quote styles. It was found by being denied while committing the
write-up of the sibling guard's defect -- which is to say, exactly when you most need to write
about staging is exactly when you could not.

⚠ THE TWO HALVES BELOW PULL AGAINST EACH OTHER, which is the point of pinning both. MUST_DENY holds
the real inline-staging forms plus the case that says WHY the repair is not "strip every quoted
string": `bash -c "git add x && git commit -m y"` is a quoted string that IS the command, and
stripping it would drop that command through to the stale-index bypass the guard exists to prevent.
MUST_ALLOW holds every way of merely TALKING about staging. Widening the prose list turns the
former red; narrowing it turns the latter red.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "commit-guard.sh"
LEXER = ROOT / ".claude" / "hooks" / "_lex_command.py"
# The variable that makes the hook allow unconditionally. Stripped from the child; see `verdict`.
_OVERRIDES = frozenset({"ALLOW_COMMIT_GUARD_SKIP"})

MUST_DENY = [
    # the real thing: one command that both stages and commits, so the hook would judge an index
    # that does not yet contain the files the commit is about to include
    'git add src/vegemu/score.py && git commit -m "feat: a thing"',
    "git add . && git commit -m 'feat: a thing'",
    "git stage src/vegemu/score.py && git commit -m 'feat: a thing'",
    'git add -A; git commit -m "feat: a thing"',
    # ⚠ A QUOTED STRING THAT IS THE COMMAND. This is why the repair strips the argument of a PROSE
    # FLAG and not every quoted string: strip all quotes and this stops matching here, while the
    # filter at the top of the hook still matches on the raw text -- so it would fall through to
    # reading a stale index, which is the silent bypass the guard exists to stop.
    'bash -c "git add x && git commit -m y"',
]

MUST_ALLOW = [
    # ordinary commits, the overwhelming majority of calls
    'git commit -m "docs: an ordinary message"',
    "git commit -F /tmp/message.txt",
    "git commit --amend --no-edit",
    # COMMITS THAT ONLY TALK ABOUT STAGING. Every one was denied before 2026-09-15, and the only way
    # past was to write the message to a file -- which is a fine workaround and a bad requirement.
    'git commit -m "fix(guard): git add was refused when the message mentioned it"',
    "git commit -m 'docs(runbook): git stage and commit must be two commands'",
    'git commit -m "docs: explain why git add inline is denied"',
    # the sibling rule, fixed earlier by the same principle: a ` -a ` in a message must not widen
    # the checked set to every modified file in the tree
    'git commit -m "note: the -a flag stages every tracked modification"',
    # not a commit at all
    "git add src/vegemu/score.py",
    "git status --short",
]


def verdict(command: str) -> str:
    """Either "deny" or "allow", as the hook decides for `command`.

    ⚠ THE OVERRIDE IS STRIPPED FROM THE CHILD'S ENVIRONMENT. The hook exits 0 -- allow -- as an
    early act if it is set, and it inherits whatever the session exported, so running this suite
    from a shell that had used the documented escape hatch would turn every MUST_DENY case red at
    once and read as "the guard is broken" rather than "the guard is switched off for this shell".
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
    # The hook prints checker findings as plain text when it denies for a budget/ownership reason;
    # only a JSON payload is a permission decision.
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return "allow"
    return str(payload.get("hookSpecificOutput", {}).get("permissionDecision", "allow"))


def test_hook_and_lexer_are_executable() -> None:
    """Without the execute bit the hook denies nothing and every case below passes vacuously."""
    assert HOOK.is_file(), f"missing: {HOOK}"
    assert HOOK.stat().st_mode & 0o111, f"{HOOK} is not executable, so it denies nothing"
    assert LEXER.is_file(), f"missing: {LEXER} -- both guards fall back to raw matching without it"


@pytest.mark.parametrize("command", MUST_DENY)
def test_a_command_that_stages_its_own_files_is_denied(command: str) -> None:
    assert verdict(command) == "deny", f"the guard let this through: {command}"


@pytest.mark.parametrize("command", MUST_ALLOW)
def test_merely_talking_about_staging_is_allowed(command: str) -> None:
    assert verdict(command) == "allow", f"the guard blocked legitimate work: {command}"


def test_no_deny_rule_reads_the_raw_command() -> None:
    """Pinned structurally, because `:38` reading `$CMD` is the exact line that regressed.

    Restating the rule in prose would keep passing after someone reverted it, which is the failure
    this test is for.

    ⚠ ONE RAW READ IS CORRECT AND IS EXCLUDED ON PURPOSE: the `am I a commit at all` filter at the
    top runs BEFORE the lexer, because lexing costs ~30 ms and this hook is consulted on every Bash
    call in the session. That filter cannot deny anything -- its only outcomes are `exit 0` and
    `carry on` -- so the worst a false positive there can do is run the checkers over a real staged
    set and find nothing. A rule that can DENY is a different matter, and that is what is pinned.
    Those are written `if [[ ... ]]`; the filter is a bare `[[ ... ]] || exit 0`.
    """
    text = HOOK.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if line.lstrip().startswith(("if [[", "elif [[")) and '"$CMD"' in line
    ]
    assert not offenders, (
        "a deny rule matches the RAW command; it must read CMD_SCAN so a commit MESSAGE cannot "
        "trip it: " + " | ".join(offenders)
    )
    # ...and pin the exemption itself, so a NEW raw read cannot hide behind it.
    raw_reads = [ln.strip() for ln in text.splitlines() if '"$CMD"' in ln]
    assert len(raw_reads) == 3, (
        "expected exactly three raw reads -- the entry filter, and the two lines that build "
        f"CMD_SCAN from it. Found {len(raw_reads)}: " + " | ".join(raw_reads)
    )


def test_both_guards_share_one_lexer_rather_than_a_second_copy() -> None:
    """Two copies of the prose stripper is how the two hooks drifted apart in the first place."""
    for hook in ("commit-guard.sh", "slurm-guard.sh"):
        text = (ROOT / ".claude" / "hooks" / hook).read_text(encoding="utf-8")
        assert "_lex_command.py" in text, f"{hook} does not use the shared lexer"
        assert "import shlex" not in text, f"{hook} has grown its own lexer again"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
