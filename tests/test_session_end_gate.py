"""The Stop gate must be SATISFIABLE, and it was not.

WHY THIS TEST EXISTS. `session-end-gate.sh` blocks a session that committed work without refreshing
its line's handoff. For an unknown number of sessions it blocked EVERY session instead, including
ones whose handoff was refreshed and committed, because the check was

    git log origin/main..HEAD --name-only --format=%B | grep -qE "lines/$LINE/STATE.md|..."

under `set -o pipefail`. `grep -q` exits at its FIRST match; `git log` still had ~21 KB to write, so
it took SIGPIPE; `pipefail` promoted 141 to the pipeline's status; the `if` went false. The gate
then told a session that had just refreshed its handoff that it had not.

Two properties of that bug make it worth a permanent test rather than a comment:

  * IT PUNISHED THE CORRECT BEHAVIOUR HARDEST. `git log` emits newest-first, so refreshing the
    handoff in your LAST commit puts the match at the very top of the stream and makes the early
    exit certain.
  * IT DOES NOT REPRODUCE INTERACTIVELY. The identical pipeline typed into an interactive subshell
    returns 0 six times out of six; run as a script -- which is how a hook runs -- it returns 141
    six times out of six. So a by-hand check reports the bug fixed when it is not. These tests
    execute the hook FILE, which is the only form that reproduces it.

The bulk in `test_allows_when_the_newest_commit_touches_state` is not padding, but the threshold is
NOT the 64 KB pipe buffer: measured on line/X, the broken gate took SIGPIPE 6/6 at 15,841 bytes, a
quarter of the buffer. It is a race against a `grep -q` that exits on its FIRST match, and
newest-first output puts that match in the first few lines, so `git log` loses it at modest sizes.
The sibling `head -15` pipeline in `path-guard.sh` is safe for a stronger reason than "small": it is
ONE write of ~667 bytes, which lands before `grep` can quit -- verified 12/12.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "session-end-gate.sh"

pytestmark = pytest.mark.skipif(not HOOK.exists(), reason="hook not present")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo() -> Iterator[Path]:
    """A throwaway repo with an `origin/main` ref and `line/Z` checked out."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "wt"
        path.mkdir()
        _git(path, "init", "-q", "-b", "main")
        _git(path, "config", "user.email", "t@example.invalid")
        _git(path, "config", "user.name", "test")
        (path / "seed.txt").write_text("seed\n")
        _git(path, "add", "-A")
        _git(path, "commit", "-qm", "base")
        # The hook compares against origin/main, so that ref must exist. No remote is needed.
        _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
        _git(path, "checkout", "-qb", "line/Z")
        yield path


def _commit(repo: Path, rel: str, body: str, message: str) -> None:
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def _decision(repo: Path) -> str:
    """Run the hook as a script, as the harness does, and return its decision."""
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"stop_hook_active": False}),
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "CLAUDE_PROJECT_DIR": str(repo),
            "HOME": str(repo),
        },
    )
    assert proc.returncode == 0, (
        f"the hook must exit 0 and speak through its JSON; got {proc.returncode}"
    )
    out = proc.stdout.strip()
    return str(json.loads(out)["decision"]) if out else "allow"


def test_blocks_when_the_handoff_was_not_refreshed(repo: Path) -> None:
    """The gate must still do its job -- a fix that merely always returns 0 is not a fix."""
    _commit(repo, "src/thing.py", "x = 1\n", "feat: work with no handoff refresh")
    assert _decision(repo) == "block"


def test_allows_when_the_handoff_was_refreshed(repo: Path) -> None:
    _commit(repo, "src/thing.py", "x = 1\n", "feat: work")
    _commit(
        repo, "lines/Z/STATE.md", "## NEXT — start here\n\ndo the thing\n", "docs(state): handoff"
    )
    assert _decision(repo) == "allow"


def test_allows_the_next_unchanged_escape_hatch(repo: Path) -> None:
    """The documented hatch sat inside the same grep and failed with it."""
    _commit(
        repo,
        "src/thing.py",
        "x = 1\n",
        "chore: nothing to hand off\n\nNEXT: unchanged (docs-only typo fix)",
    )
    assert _decision(repo) == "allow", "the hatch the block message advertises must work"


def test_allows_nothing_committed(repo: Path) -> None:
    """No commits ahead of main is not a missing handoff."""
    assert _decision(repo) == "allow"


def test_allows_when_the_newest_commit_touches_state(repo: Path) -> None:
    """THE REGRESSION, in the exact shape that was broken.

    The handoff is refreshed in the NEWEST commit, so `git log`'s newest-first output puts the match
    on the first lines and `grep -q` quits immediately, while a large body of older commits is still
    queued behind it. That is what the old pipeline failed on, and it is what a conscientious
    session produces.
    """
    # The live failure reproduced 6/6 at 15,841 bytes over eleven commits, so this is comfortably
    # past the point where `git log` still has output queued when `grep -q` quits. Bigger than
    # needed on purpose: the fixture must not sit near the edge of the race it is probing.
    filler = ("lorem ipsum dolor sit amet consectetur adipiscing elit " * 12).strip()
    for i in range(90):
        _commit(repo, f"src/f{i}.py", f"x = {i}\n", f"feat: change {i}\n\n{filler}")
    _commit(
        repo, "lines/Z/STATE.md", "## NEXT — start here\n\ndo the thing\n", "docs(state): handoff"
    )

    log = _git(repo, "log", "origin/main..HEAD", "--name-only", "--format=%B")
    assert len(log) > 50_000, f"fixture too small to expose the bug ({len(log)} bytes)"
    assert log.splitlines()[0].startswith("docs(state)"), "the match must sit at the TOP"

    assert _decision(repo) == "allow", (
        "the gate blocked a session that DID refresh its handoff -- the SIGPIPE regression"
    )
