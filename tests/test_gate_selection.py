"""The gate-selection tooling must never answer "nothing to verify" when it means "cannot tell".

WHY THIS TEST EXISTS. `tools/expected_gates.py` is what a session consults before merging, and its
"EXPECTED GATES: (none) -> merge when ready" is trusted. It computed that from
`git merge-base origin/main HEAD`, and an EMPTY merge base was treated as one case when it is two:

    the ref does not resolve      a fresh clone -- fall back to the staged set, keep the bootstrap
                                  working, and no CI exists to poll anyway;
    the ref shares no history     a WRONG remote -- the diff cannot be computed, so an empty answer
                                  is a fabrication.

This repo hit the second one: `origin` pointed at the predecessor's GitHub repository, which shares
no ancestor with this history. Every commit on every branch was told no gate would run, and a real
`pathsafety` violation sat on `main` behind that reassurance.

The three tests below pin the distinction itself, not the incident: a real empty diff still licenses
a merge, an unrelated base is refused loudly, and the fallback for an unrelated base is EVERY file
rather than no files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _common  # noqa: E402
from _common import BASE_OK, BASE_UNKNOWN, BASE_UNRELATED, diff_base  # noqa: E402


def _git_raw(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """git, with a non-zero exit allowed -- `merge-base` on unrelated histories exits 1 BY DESIGN,
    and that exit is the fact under test."""
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )


def _git(cwd: Path, *args: str) -> str:
    out = _git_raw(cwd, *args)
    assert out.returncode == 0, f"git {' '.join(args)} failed: {out.stderr}"
    return out.stdout


def _expected_gates(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / "expected_gates.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )


@pytest.fixture
def unrelated_repo(tmp_path: Path) -> Path:
    """A repo with a ref that resolves but shares no commit with HEAD.

    Built rather than mocked: the behaviour under test is git's, and `merge-base` returning empty
    for unrelated histories is exactly the fact the production code now depends on.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("ours\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "--quiet", "-m", "ours")

    # An orphan branch: a real ref, zero shared commits -- the predecessor-remote situation in
    # miniature, without needing a network or a second repository.
    _git(repo, "checkout", "--quiet", "--orphan", "theirs")
    # `-rqf .` clears the index AND the working tree. Clearing only the index would leave a.txt
    # untracked, and checking `main` back out would then refuse to overwrite it.
    _git(repo, "rm", "-rqf", ".")
    (repo / "b.txt").write_text("theirs\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "--quiet", "-m", "theirs")
    _git(repo, "checkout", "--quiet", "main")
    return repo


def test_unrelated_history_is_classified_unrelated_not_unknown(
    unrelated_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug, stated as a test: a ref that resolves but shares no commit is its OWN case.

    `diff_base` runs git inside `repo_root()`, so point that at the throwaway repo. What is under
    test is the classification, and it must come out `unrelated` -- if it came out `unknown` the
    caller would fall back to the staged set, which on a clean tree is empty, which is the
    fabricated "nothing changed" this whole module exists to prevent.
    """
    probe = _git_raw(unrelated_repo, "merge-base", "theirs", "HEAD")
    assert probe.returncode != 0 and probe.stdout.strip() == "", (
        "precondition: git must report no merge base for unrelated histories"
    )
    monkeypatch.setattr(_common, "repo_root", lambda: unrelated_repo)

    base, status = _common.diff_base("theirs")
    assert status == BASE_UNRELATED, f"got {status!r}; an unrelated ref must not read as unknown"
    assert base is None

    # And the fallback must be every tracked file, not none of them.
    assert _common.changed_vs("theirs") == _common.tracked_files() == ["a.txt"]


def test_diff_base_classifies_this_repo_and_a_bogus_ref() -> None:
    """The three statuses are distinguishable in practice, on real refs.

    `HEAD~1` shares history, so it is BASE_OK; a name that resolves to nothing is BASE_UNKNOWN.
    Both must be reachable, or the classification is decorative.
    """
    base, status = diff_base("HEAD~1")
    assert status == BASE_OK and base, (base, status)

    _, status = diff_base("refs/heads/definitely-not-a-branch-here")
    assert status == BASE_UNKNOWN, status


def test_expected_gates_refuses_an_unusable_base_and_says_what_is_unknown() -> None:
    """Against an unresolvable ref: exit 2, and the word 'merge' must not appear as advice.

    Exit 2 is this repo's convention for "the checker itself could not run", and it is what keeps
    `tools/wait_gates.py` from reporting green off a diff nobody could compute.
    """
    proc = _expected_gates("--ref", "refs/heads/definitely-not-a-branch-here")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    text = (proc.stdout + proc.stderr).lower()
    assert "cannot compute" in text
    assert "merge when ready" not in text, "an uncomputable diff must never license a merge"
    # It must still be USEFUL: name the conservative gate list rather than just refusing.
    assert "conservative" in text or "whole tracked tree" in text


def test_expected_gates_still_answers_a_computable_diff() -> None:
    """The normal path is intact: a real base gives a real, exit-0 answer."""
    proc = _expected_gates("--ref", "HEAD~1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "diff vs HEAD~1" in proc.stdout
    assert "EXPECTED GATES" in proc.stdout


def test_unrelated_base_falls_back_to_every_file_not_no_files() -> None:
    """The direction of the fallback is the safety property, so pin it explicitly.

    `changed_vs` on an unrelated base returns every tracked file. Under-checking is what let a
    violation reach `main`; over-checking costs seconds.
    """
    _, status = diff_base("origin/main")
    if status != BASE_UNRELATED:
        pytest.skip(f"origin/main is {status!r} here, not unrelated -- nothing to assert")
    assert _common.changed_vs("origin/main") == _common.tracked_files()
