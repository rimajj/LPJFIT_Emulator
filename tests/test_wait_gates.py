"""The gate poller must never report "still pending" when the truth is "nothing was ever asked".

WHY THIS TEST EXISTS. `tools/merge.sh` now REFUSES to merge unless `tools/wait_gates.py` says the
pushed sha is green, so the poller went from an advisory convenience to a guard. It was not fit for
that, and the way it failed is this repository's recurring bug in a new place: one benign-looking
message covering two opposite situations.

  * `remote_slug()` dropped the OWNER from an scp-like SSH remote (`git@host:owner/repo.git`) --
    which is the only form this repo has ever used. Every request therefore went to
    `/repos/LPJFIT_Emulator/...` and returned 404, so the poller had never once succeeded here.
  * That 404 was caught as a transient `URLError` (`HTTPError` is a subclass) and retried until the
    timeout, whose message is "still pending". A wrong slug and a slow CI run printed the same
    thing, and only one of them will ever come good.

Both tests below are environment-independent on purpose: the failure that made them necessary was a
test asserting something true only of the machine it was written on (`HEAD~1` does not resolve in a
depth-1 CI checkout). So the git history, the network and the token are all stubbed out, and what is
asserted is the classification.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import wait_gates  # noqa: E402
from _common import BASE_OK  # noqa: E402

# owner/repo must survive all of these. The alias host (`github-lpjfit`) is the real one here: the
# SSH config maps it to github.com with a specific key, so the host cannot be pattern-matched.
URL_FORMS = [
    ("git@github-lpjfit:rimajj/LPJFIT_Emulator.git", "rimajj/LPJFIT_Emulator"),
    ("git@github.com:rimajj/LPJFIT_Emulator", "rimajj/LPJFIT_Emulator"),
    ("https://github.com/rimajj/LPJFIT_Emulator.git", "rimajj/LPJFIT_Emulator"),
    ("ssh://git@github.com:22/rimajj/LPJFIT_Emulator.git", "rimajj/LPJFIT_Emulator"),
]


@pytest.mark.parametrize(("url", "want"), URL_FORMS)
def test_remote_slug_keeps_the_owner_for_every_url_form(
    tmp_path: Path, url: str, want: str
) -> None:
    """A slug without its owner 404s forever, which the poller reported as a pending gate."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "--quiet"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)

    got = wait_gates.remote_slug(repo)
    assert got == want, f"{url} -> {got!r}; a slug missing the owner cannot be requested"


def _stub_a_triggered_gate(monkeypatch: pytest.MonkeyPatch, gates: list[str]) -> None:
    """A computable diff that triggers exactly `gates`, with no git history and no network."""
    monkeypatch.setattr(wait_gates, "diff_base", lambda ref: ("base-sha", BASE_OK))
    monkeypatch.setattr(wait_gates.expected_gates, "changed_vs", lambda ref: ["src/vegemu/x.py"])
    monkeypatch.setattr(wait_gates.expected_gates, "expected", lambda files, branch: (gates, []))


def test_a_permanent_api_refusal_is_not_a_timeout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """HTTP 404/401/403: exit 2 immediately, and never the words of a pending or green verdict."""
    _stub_a_triggered_gate(monkeypatch, ["types"])
    monkeypatch.setattr(wait_gates, "token", lambda: "a-token")
    monkeypatch.setattr(wait_gates, "remote_slug", lambda root: "owner/repo")

    def refuse(slug: str, sha: str, tok: str) -> dict[str, str]:
        raise urllib.error.HTTPError(
            url=f"https://api.github.com/repos/{slug}/commits/{sha}/check-runs",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )

    monkeypatch.setattr(wait_gates, "check_runs", refuse)

    # A timeout long enough that a retry loop would still be spinning when we assert.
    rc = wait_gates.main(["--timeout", "600", "--interval", "1"])
    text = "".join(capsys.readouterr())

    assert rc == 2, "an unanswerable request must be exit 2 (the checker could not run)"
    assert "REFUSED" in text and "404" in text
    assert "timed out" not in text, "a permanent refusal must not be reported as a slow gate"
    assert "all expected gates green" not in text


def test_no_triggered_gate_licenses_a_merge_without_a_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A prose-only commit triggers nothing, so the guard must pass at once rather than block.

    This is the property that keeps the merge refusal from being a blanket stop: most commits here
    are documents, and a workflow skipped by its path filter reports no status at all, so waiting
    for one would hang forever.
    """
    _stub_a_triggered_gate(monkeypatch, [])
    monkeypatch.setattr(wait_gates, "token", lambda: None)  # not even reached
    rc = wait_gates.main(["--timeout", "600"])
    assert rc == 0
    assert "NO gate" in "".join(capsys.readouterr())


# ---------------------------------------------------------------------------
# An ABSENT gate is not a slow gate.
#
# `expected_gates` computes what a merge must verify from the whole BRANCH diff; GitHub decides
# what to RUN from the push diff. They disagree whenever a branch is pushed more than once, which
# is every branch here, because protocol commits the handoff last and that final push is
# documentation-only. The gate then never runs on the head sha and reports NO STATUS AT ALL, so a
# poll for it used to hang for the full 900 s and then fail -- three merges lost in one session on
# 2026-09-09. The two cases below are the ones that must never be confused.
# ---------------------------------------------------------------------------


def _stub_history(monkeypatch: pytest.MonkeyPatch, *, touched: list[str]) -> None:
    """One ancestor, `anc-sha`, with `touched` changed between it and HEAD."""
    monkeypatch.setattr(wait_gates, "ancestors", lambda root, sha, limit: ["anc-sha"])
    monkeypatch.setattr(wait_gates, "files_between", lambda root, a, b: touched)


def test_a_gate_that_did_not_rerun_inherits_its_still_valid_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Green on an ancestor + nothing since touching its paths = green here, and no waiting.

    This is the merge that used to cost 15 minutes and then need `--allow-red`, whose reason had to
    explain a gate that was not red but absent.
    """
    _stub_a_triggered_gate(monkeypatch, ["lint"])
    monkeypatch.setattr(wait_gates, "token", lambda: "a-token")
    monkeypatch.setattr(wait_gates, "remote_slug", lambda root: "owner/repo")
    monkeypatch.setattr(wait_gates, "ABSENT_GRACE_S", 0)
    # Only documents changed since the sha that ran `lint`, so its verdict still fits this tree.
    _stub_history(monkeypatch, touched=["PLAN.md"])
    monkeypatch.setattr(
        wait_gates,
        "check_runs",
        lambda slug, sha, tok: {} if sha != "anc-sha" else {"lint": "success"},
    )

    rc = wait_gates.main(["--timeout", "30", "--interval", "1"])
    text = "".join(capsys.readouterr())

    assert rc == 0, "a verdict nothing since could have changed must license the merge"
    assert "inherited from anc-sha" in text
    assert "timed out" not in text


def test_a_gate_whose_paths_changed_since_is_never_inherited(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The safety direction: if the gate's own paths moved, the old green says nothing.

    Inheriting here would be the failure this whole mechanism exists to prevent -- reporting green
    for code CI has never seen. It must refuse instead, and name the dispatch that gets a verdict.
    """
    _stub_a_triggered_gate(monkeypatch, ["lint"])
    monkeypatch.setattr(wait_gates, "token", lambda: "a-token")
    monkeypatch.setattr(wait_gates, "remote_slug", lambda root: "owner/repo")
    monkeypatch.setattr(wait_gates, "ABSENT_GRACE_S", 0)
    monkeypatch.setattr(wait_gates, "ABSENT_VERDICT_S", 0)
    # A .py moved since the ancestor, so `lint` genuinely has to run again.
    _stub_history(monkeypatch, touched=["src/vegemu/x.py"])
    monkeypatch.setattr(
        wait_gates,
        "check_runs",
        lambda slug, sha, tok: {} if sha != "anc-sha" else {"lint": "success"},
    )

    rc = wait_gates.main(["--timeout", "30", "--interval", "1"])
    text = "".join(capsys.readouterr())

    assert rc == 1, "an unverified gate must refuse, never inherit"
    assert "all expected gates green" not in text
    assert "gh workflow run lint.yml" in text, "a refusal must say how to get a real verdict"


def test_a_gate_that_appears_late_is_not_refused_for_having_been_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CI can create a check-run minutes after the push; absence must be forgotten when it ends.

    Without this the refusal is the original bug pointed the other way: a gate recorded as absent on
    an early poll stays on the refusal list after it has appeared and gone green, so a merely slow
    gate becomes a blocked merge.
    """
    # TWO gates are required to exhibit this, which is why the obvious one-gate version of this test
    # passes with or without the fix: a single gate that goes green leaves `pending` empty, so the
    # refusal is never reached. The bug bites when one gate's stale absence is still on the refusal
    # list while a DIFFERENT gate is legitimately pending -- then the oldest absence times out and
    # refuses a merge over a gate that has already reported success.
    _stub_a_triggered_gate(monkeypatch, ["lint", "test"])
    monkeypatch.setattr(wait_gates, "token", lambda: "a-token")
    monkeypatch.setattr(wait_gates, "remote_slug", lambda root: "owner/repo")
    monkeypatch.setattr(wait_gates, "ABSENT_GRACE_S", 0)
    monkeypatch.setattr(wait_gates, "ABSENT_VERDICT_S", 2)
    _stub_history(monkeypatch, touched=["src/vegemu/x.py"])  # so nothing can be inherited

    head_polls = {"n": 0}

    def late(slug: str, sha: str, tok: str) -> dict[str, str]:
        if sha == "anc-sha":
            return {}  # no ancestor verdict either, so absence is all we have at first
        head_polls["n"] += 1
        # `lint` is absent on the first poll and green thereafter; `test` runs on for a while.
        lint = {} if head_polls["n"] < 2 else {"lint": "success"}
        return {**lint, "test": "in_progress" if head_polls["n"] < 4 else "success"}

    monkeypatch.setattr(wait_gates, "check_runs", late)

    rc = wait_gates.main(["--timeout", "30", "--interval", "1"])
    text = "".join(capsys.readouterr())

    assert rc == 0, "a gate that showed up green must not be refused for having been slow"
    assert "REFUSING" not in text


def test_an_inherited_failure_is_still_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inheritance carries RED forward too -- it resolves absence, it does not launder a result."""
    _stub_a_triggered_gate(monkeypatch, ["lint"])
    monkeypatch.setattr(wait_gates, "token", lambda: "a-token")
    monkeypatch.setattr(wait_gates, "remote_slug", lambda root: "owner/repo")
    monkeypatch.setattr(wait_gates, "ABSENT_GRACE_S", 0)
    _stub_history(monkeypatch, touched=["PLAN.md"])
    monkeypatch.setattr(
        wait_gates,
        "check_runs",
        lambda slug, sha, tok: {} if sha != "anc-sha" else {"lint": "failure"},
    )

    rc = wait_gates.main(["--timeout", "30", "--interval", "1"])
    assert rc == 1
    assert "FAILED" in "".join(capsys.readouterr())
