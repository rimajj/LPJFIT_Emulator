"""The seal-precedes-the-run check must survive a rebase, because the runbook mandates one.

WHY THIS TEST EXISTS. `experiments/registry.jsonl` records a `seal_commit` hash, and E12 used to
test *that hash* for ancestry of the first result commit. But `CLAUDE.md` requires
`git pull --rebase origin main` before merging, and a rebase rewrites every commit on the line that
is not yet on main -- the seal commit among them. The recorded hash then names an object on no
branch, so ancestry is false for everything and E12 reported a violation against provenance that
was entirely intact.

That happened three times in a single session. Each was "fixed" by appending a correction row to an
append-only ledger -- bookkeeping performed to silence a checker, which is exactly how a real
integrity gate is taught to be ignored. It is the repository's recurring bug in a new place: a check
whose input is not the thing it is checking.

The fix resolves the seal by CONTENT (`prereg_sha256`, which a rebase cannot change) instead of by
recorded hash, and the tests below pin all three properties that matters:

  * the rebase case, built by actually rebasing, where the old test fails and the new one passes;
  * that this is STRICTER, not laxer -- a seal that genuinely follows its results is still caught,
    and so is one whose sealed bytes were never committed at all;
  * that the old test really does fail on the rebase case, so the regression test is not vacuous.

The repos here are built from scratch in a tmp dir: the failure that made this necessary was
environment-specific git state, so nothing is asserted about the repository the tests run in.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_experiments as ce  # noqa: E402
from _common import Report  # noqa: E402

EXP = "X-20260101-example"
PREREG = f"experiments/{EXP}/preregistration.yaml"
RESULT = f"experiments/{EXP}/result.jsonl"
SEALED_BYTES = b"schema_version: 1\nexp_id: X-20260101-example\nstatus: sealed\n"
SEALED_SHA = hashlib.sha256(SEALED_BYTES).hexdigest()


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip()


def commit(repo: Path, rel: str, data: bytes, msg: str) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    git(repo, "add", rel)
    git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    commit(repo, "README.md", b"base\n", "base")
    return repo


@pytest.fixture
def at_repo(monkeypatch):
    """Point the checker's git helpers at an arbitrary repo root."""

    def _use(repo: Path):
        monkeypatch.setattr(ce, "repo_root", lambda: repo)

    return _use


def is_ancestor(repo: Path, a: str, b: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def test_rebase_orphans_the_recorded_hash_but_not_the_content(tmp_path, at_repo):
    """The regression. A real rebase, not a simulated one."""
    repo = new_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "line/X")
    recorded_seal = commit(repo, PREREG, SEALED_BYTES, "seal")
    commit(repo, RESULT, b'{"arm": "model"}\n', "result")

    # main advances, then the line rebases onto it -- the mandated pre-merge workflow.
    git(repo, "checkout", "-q", "main")
    commit(repo, "other.md", b"main moved\n", "main moves")
    git(repo, "checkout", "-q", "line/X")
    git(repo, "-c", "commit.gpgsign=false", "rebase", "-q", "main")

    first_result = git(repo, "log", "--reverse", "--format=%H", "--", RESULT).split()[0]

    # The OLD check: the recorded hash is now an orphan, so ancestry is false. If this ever starts
    # passing, the regression test has stopped reproducing the bug and must be rewritten.
    assert not is_ancestor(repo, recorded_seal, first_result), (
        "the rebase did not rewrite the seal commit, so this test no longer covers the bug"
    )

    # The NEW check: resolved by content, found, and genuinely earlier than the result.
    at_repo(repo)
    resolved = ce.seal_commit_by_content(PREREG, SEALED_SHA)
    assert resolved is not None
    assert resolved != recorded_seal, "expected the rebase to have moved the commit"
    assert is_ancestor(repo, resolved, first_result)


def test_a_seal_that_really_follows_its_results_is_still_caught(tmp_path, at_repo):
    """The check must not have been traded away for convenience."""
    repo = new_repo(tmp_path)
    commit(repo, RESULT, b'{"arm": "model"}\n', "result FIRST")
    commit(repo, PREREG, SEALED_BYTES, "seal AFTER the run")

    first_result = git(repo, "log", "--reverse", "--format=%H", "--", RESULT).split()[0]
    at_repo(repo)
    resolved = ce.seal_commit_by_content(PREREG, SEALED_SHA)

    assert resolved is not None
    assert not is_ancestor(repo, resolved, first_result), "a post-hoc seal must not pass"


def test_sealed_bytes_that_were_never_committed_are_caught(tmp_path, at_repo):
    """Editing the pre-registration after sealing leaves no commit carrying the sealed bytes.

    The old test could not see this at all: it never opened the commit it named.
    """
    repo = new_repo(tmp_path)
    commit(repo, PREREG, b"schema_version: 1\nstatus: draft\n", "a DIFFERENT pre-registration")

    at_repo(repo)
    assert ce.seal_commit_by_content(PREREG, SEALED_SHA) is None


def test_the_earliest_carrier_wins_not_the_latest(tmp_path, at_repo):
    """A later no-op touch of the file must not move the seal forward past its own results."""
    repo = new_repo(tmp_path)
    sealed = commit(repo, PREREG, SEALED_BYTES, "seal")
    commit(repo, RESULT, b'{"arm": "model"}\n', "result")
    commit(repo, PREREG, b"# a comment\n" + SEALED_BYTES, "touch it")
    commit(repo, PREREG, SEALED_BYTES, "and put it back")

    at_repo(repo)
    resolved = ce.seal_commit_by_content(PREREG, SEALED_SHA)

    first_result = git(repo, "log", "--reverse", "--format=%H", "--", RESULT).split()[0]
    assert resolved == sealed, "must resolve to the FIRST commit carrying the sealed bytes"
    assert is_ancestor(repo, resolved, first_result)


# ------------------------------------------------------------------------------------------------
# End to end, through the real E12 code path -- because a correct helper proves nothing about the
# check that is supposed to call it.
# ------------------------------------------------------------------------------------------------

REGISTRY = "experiments/registry.jsonl"


def _registry_row(seal_commit: str) -> bytes:
    return (
        json.dumps(
            {
                "exp_id": EXP,
                "line": "X",
                "nulls": ["no_response"],
                "prereg_sha256": SEALED_SHA,
                "seal_commit": seal_commit,
                "sealed_at": "2026-01-01T00:00:00Z",
                "statistic": "s",
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def e12_findings(repo: Path) -> list[str]:
    """E12 findings only. Reads `rep.findings` directly: a `getattr(..., [])` default would make
    the "no findings" test pass even if the attribute were renamed away."""
    rep = Report("t")
    ce.check_append_only(rep, "origin/main")
    return [f.render() for f in rep.findings if f.code == "E12"]


def test_e12_is_silent_after_a_rebase_orphans_the_recorded_hash(tmp_path, at_repo, monkeypatch):
    repo = new_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "line/X")
    recorded_seal = commit(repo, PREREG, SEALED_BYTES, "seal")
    commit(repo, RESULT, b'{"arm": "model"}\n', "result")
    commit(repo, REGISTRY, _registry_row(recorded_seal), "register")

    git(repo, "checkout", "-q", "main")
    commit(repo, "other.md", b"main moved\n", "main moves")
    git(repo, "checkout", "-q", "line/X")
    git(repo, "-c", "commit.gpgsign=false", "rebase", "-q", "main")

    at_repo(repo)
    monkeypatch.chdir(repo)
    assert e12_findings(repo) == [], "intact provenance must not be reported as a violation"


def test_e12_still_fires_when_the_seal_really_follows_the_run(tmp_path, at_repo, monkeypatch):
    repo = new_repo(tmp_path)
    commit(repo, RESULT, b'{"arm": "model"}\n', "result FIRST")
    seal = commit(repo, PREREG, SEALED_BYTES, "seal AFTER the run")
    commit(repo, REGISTRY, _registry_row(seal), "register")

    at_repo(repo)
    monkeypatch.chdir(repo)
    assert e12_findings(repo), "a post-hoc seal must still be reported"
