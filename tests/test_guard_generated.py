"""The deny hooks, tested against commands NOBODY WROTE BY HAND.

WHY THIS FILE EXISTS, and it is the lesson of instances 7 to 10 rather than of any one of them.
`tests/test_slurm_guard.py` is a hand-written list of commands, and four times now the command that
broke the login-node guard was one that was not on it:

    7  a quoted `grep` pattern containing a vertical bar
    8  a commit message on stdin whose text contained an English semicolon
    9  an `--body` argument that TALKED ABOUT a heredoc, inside the fix for 7 and 8
   10  a heredoc body that is not valid shell, so the step deciding whether a body EXISTS
       crashed and the body was keyword-matched after all

Each was found by being blocked during ordinary work, after a green suite. A list of cases somebody
thought of cannot contain the case nobody thought of, so this file does not hold a list: it builds
its commands out of THIS REPOSITORY -- its own prose, its own files, its own commit messages -- and
asserts the only property that matters for all of them.

THE PROPERTY. Every command built here RUNS NOTHING. It writes a file with `cat`, or carries text
in `-m`, `--body`, `--reason`, or hands a message to `git` on stdin, or searches a file with `grep`.
The receiving verb cannot execute what it is handed, which is the by-capability rule the owner
approved on 2026-09-16. So a deny is a false deny by construction -- no judgement call, and no need
for this file to be updated when the guard's keyword list changes.

⚠ A CORPUS TEST CAN GO VACUOUS WITHOUT FAILING. If the corpus ever comes back empty -- a moved path,
a shallow clone, a filter that stops matching -- every assertion below passes and nothing is being
tested. `test_the_corpus_is_large_enough_to_mean_anything` is what stops that, and it is the
sibling of the execute-bit test in `test_slurm_guard.py`, written after a guard passed every case
vacuously because it had no execute bit.
"""

from __future__ import annotations

import functools
import json
import os
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "slurm-guard.sh"
_OVERRIDES = frozenset({"ALLOW_LOGIN_HEAVY", "ALLOW_RAW_SBATCH", "SLURM_JOB_ID"})

# WHAT IS DELIBERATELY NOT COVERED, stated because a cap nobody can see reads as "everything is
# covered". Each hook invocation costs ~60 ms (two interpreter starts), so the corpus is filtered to
# the ADVERSARIAL subset -- text carrying shell punctuation or one of the guard's trigger words --
# and then strided. Unstrided, these families are ~1,900 commands and two minutes of suite time.
# The strides are prime-ish and fixed, so the sample is deterministic and spread across sources
# rather than clustered in whichever directory sorts first.
PROSE_STRIDE = 11
FILE_STRIDE = 2
BODY_LINES = 40  # a body long enough to carry real quoting, short enough to stay fast

# Punctuation that makes a paragraph interesting to a lexer. A paragraph with none of it, and no
# trigger word either, cannot exercise any rule in the hook.
SHELLISH = (*(";|&<>$`" + chr(39) + chr(34) + "\\"), ".py")


def verdict(command: str) -> str:
    """ "deny" or "allow", as the hook decides -- with the override variables stripped.

    The hook allows unconditionally if any of them is set, so a session that had used the
    documented escape hatch would otherwise turn this whole file green for the wrong reason.
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


def _tracked(*patterns: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *patterns],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return sorted(out)


@functools.lru_cache(maxsize=1)
def prose() -> tuple[tuple[str, str], ...]:
    """Paragraphs this repository has actually written, deduplicated and strided.

    Decision records and line-state files are where the punctuation lives: semicolons, vertical
    bars, heredoc markers being discussed, `.py` paths mid-sentence. Commit messages are included
    best-effort -- a shallow CI checkout has only one, and that must not fail anything.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def keep(t: str) -> bool:
        return 20 <= len(t) <= 600 and t not in seen and any(s in t for s in SHELLISH)

    for rel in _tracked("docs/decisions/*.md", "lines/*/STATE.md", "*.md"):
        for para in (ROOT / rel).read_text(encoding="utf-8").split("\n\n"):
            t = para.strip()
            if keep(t):
                seen.add(t)
                out.append((rel, t))
    log = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-200", "--format=%B%x00"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    for msg in log.split("\x00"):
        t = msg.strip()
        if keep(t):
            seen.add(t)
            out.append(("git-log", t))
    return tuple(out[::PROSE_STRIDE])


@functools.lru_cache(maxsize=1)
def file_bodies() -> tuple[tuple[str, str], ...]:
    """The head of every tracked text file, as a heredoc body.

    This is what an agent does all day -- write a script or a note with `cat > f <<'PY'` -- and it
    is the family that was refused for 12 of this repository's own 177 files on 2026-09-16.
    """
    out: list[tuple[str, str]] = []
    for rel in _tracked("*.py", "*.sh", "*.md", "*.toml", "*.yaml", "*.yml")[::FILE_STRIDE]:
        body = "\n".join((ROOT / rel).read_text(encoding="utf-8").splitlines()[:BODY_LINES])
        if body.strip() and not any(ln.strip() == "PY" for ln in body.splitlines()):
            out.append((rel, body))
    return tuple(out)


def _failures(cases: Sequence[tuple[str, str]]) -> list[str]:
    """Every case the hook refuses, reported together rather than one at a time.

    Parametrising ~400 subprocess cases would bury the suite in test ids and stop at the first
    red; the interesting output is HOW MANY and WHICH, which is what a false-denial bug looks like.
    """
    return [f"[{src}] {cmd.splitlines()[0][:110]}" for src, cmd in cases if verdict(cmd) == "deny"]


def _report(kind: str, cases: Sequence[tuple[str, str]]) -> None:
    bad = _failures(cases)
    assert not bad, (
        f"the guard refused {len(bad)} of {len(cases)} {kind} that run nothing:\n"
        + "\n".join(bad[:20])
    )


PROSE_FLAG_TEMPLATES = (
    "git commit -m {q}",
    "python3 tools/inbound.py --to D --subject 's' --body {q}",
    "python3 tools/campaigns.py abandon --tag t --reason {q}",
)


def test_a_message_carried_in_a_prose_flag_is_never_a_job() -> None:
    """`-m`, `--body`, `--reason`: instances 3, 7 and 9 all lived here.

    ONE TEMPLATE PER PARAGRAPH, ROTATING, rather than all three on each: three times the commands
    for no new coverage of the lexer, which sees the same paragraph either way. Every paragraph is
    still used and every template still runs on a third of them.
    """
    cases = [
        (src, PROSE_FLAG_TEMPLATES[i % len(PROSE_FLAG_TEMPLATES)].format(q=shlex.quote(t)))
        for i, (src, t) in enumerate(prose())
    ]
    _report("messages", cases)


def test_a_message_handed_to_git_on_stdin_is_never_a_job() -> None:
    """Instance 8: the body is data because `git` cannot execute what it is handed."""
    cases = [
        (src, f"git commit -F - <<'MSG'\n{t}\nMSG")
        for src, t in prose()
        if not any(ln.strip() == "MSG" for ln in t.splitlines())
    ]
    _report("commit messages on stdin", cases)


def test_writing_one_of_this_repos_own_files_with_a_heredoc_is_never_a_job() -> None:
    """INSTANCE 10, and the reason this file exists at all.

    `cat` cannot execute what it is handed, so the body is data -- but the step that decides
    whether a body exists lexed the RAW text, body included. A body is data, and data need not be
    balanced shell: one escaped quote and `shlex` raises, the command falls down the fail-closed
    path, and the body is keyword-matched after all. 12 of this repository's own 177 tracked files
    could not be written this way, including the lexer itself and two lines' state files.

    Diagnosed in the 2026-09-16 record whose slug begins `an-unlexable-heredoc-body`.

    ⚠ THE COMMAND IS BUILT HERE, not in `file_bodies()`. Handing the bare body to the hook, as the
    first draft of this file did, tests nothing about heredocs: a body that happens to start
    `#!/usr/bin/env python3` then IS an unsafe command, so it is correctly denied, and the family
    goes red for a reason that has nothing to do with the bug it is pinning. Caught by checking the
    same family against a patched guard and finding it still red -- the verification that a red
    test is red for its stated reason.
    """
    cases = [(rel, f"cat > /tmp/copy_of_file <<'PY'\n{body}\nPY") for rel, body in file_bodies()]
    _report("file writes", cases)


def test_a_read_with_a_shell_builtin_appended_is_never_a_job() -> None:
    """`wc -l x.py ; echo done` is a read and a print, and the guard used to refuse it.

    None of these verbs can execute a file, so by the allowlist's own stated discipline they
    belong on it. Eight of ten such commands were refused until 2026-09-16; the two survivors
    survived only on the accident that `.py;` is not `.py `, so the keyword regex missed them --
    punctuation luck, not a safety property.
    """
    paths = _tracked("scripts/*.py", "src/vegemu/**/*.py")[:5]
    suffixes = ("; echo done", "&& echo ok", "; pwd", "; true", "; test -f /tmp/x")
    cases = [(p, f"wc -l {p} {sfx}") for p in paths for sfx in suffixes]
    cases += [(p, f"cd {Path(p).parent} && ls -l {Path(p).name}") for p in paths]
    _report("reads with a builtin appended", cases)


def test_searching_one_of_this_repos_own_files_is_never_a_job() -> None:
    """Instance 7: a quoted search pattern is not a pipeline, however many bars it contains."""
    paths = _tracked("src/vegemu/**/*.py", "scripts/*.py", "tools/*.py")[:6]
    patterns = [
        "train|corpus|eval",
        "def test|python3 -c|torch",
        "corpus.*\\.py",
        "pft_frac|vegc",
    ]
    cases = [(p, f"grep -rn {shlex.quote(pat)} {p}") for p in paths for pat in patterns]
    _report("searches", cases)


def test_the_corpus_is_large_enough_to_mean_anything() -> None:
    """Without this, an empty corpus is a green suite.

    The floors are deliberately far below today's counts (they were 242 paragraphs and 177 files
    on 2026-09-16): this is a vacuity check, not a snapshot that has to be edited whenever the
    repository grows.
    """
    n_prose, n_files = len(prose()), len(file_bodies())
    assert n_prose >= 30, f"only {n_prose} prose paragraphs found -- the corpus has gone vacuous"
    assert n_files >= 20, f"only {n_files} tracked file bodies found -- the corpus has gone vacuous"


def test_the_trigger_words_are_read_out_of_the_hook_and_not_restated_here() -> None:
    """The corpus is only adversarial if it contains the words the guard actually reacts to.

    Restating the list here would keep this file passing after the hook's list changed -- the same
    drift `test_slurm_guard.py` pins for the escape-hatch names. So: assert the hook still keyword-
    matches, and that the corpus contains those keywords, without hard-coding what they are.
    """
    text = HOOK.read_text(encoding="utf-8")
    line = next((ln for ln in text.splitlines() if "train|bench|corpus" in ln), None)
    assert line is not None, "the heavy-Python keyword rule has moved -- re-point this test at it"
    words = [w for w in line.split("(")[-1].split(")")[0].split("|") if w.isidentifier()]
    assert len(words) >= 5, f"only parsed {words} out of the hook's keyword rule"
    haystack = " ".join(t for _, t in prose()) + " ".join(b for _, b in file_bodies())
    hit = [w for w in words if w in haystack]
    assert len(hit) >= 3, f"the corpus mentions only {hit} of the guard's trigger words {words}"
