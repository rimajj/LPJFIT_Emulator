"""A sealed experiment must be abandonable WITHOUT editing its sealed bytes.

WHY THIS TEST EXISTS. E13 fires when a pre-registration has been sealed >30 days with no results,
and its remedy was "add `abandoned: <reason>`". E03 hashes the sealed file and reports any change.
So the remedy tripped the other gate, and it was available only for a DRAFT -- the one state in
which E13 can never fire, because E13 keys off `sealed_at`. The remedy and the condition were
disjoint by construction, which is how a real integrity gate gets taught to be ignored:
`docs/decisions/20260921-INT-a-sealed-experiment-cannot-be-marked-abandoned-*.md`.

The repair records the abandonment as an appended registry row instead. These tests pin the four
properties that make it a repair rather than a silencer:

  * E13 is cleared by the row -- the reason is machine-readable, which a commit message is not;
  * E03 stays green THROUGH the abandonment, because the sealed bytes are never touched. This is
    the property the rejected repair (B) would have given up;
  * the seal row is still found afterwards. An event row carries no `prereg_sha256`, so a registry
    index that folded both kinds together by recency would let the abandonment shadow its own seal
    and report the experiment as never sealed at all -- the repository's recurring bug, a check
    reading input that is not the thing it checks;
  * abandoning and then running anyway is REPORTED, not silently accepted. That contradiction only
    became reachable when abandonment became possible, so it is closed in the same change.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_experiments as ce  # noqa: E402
from _common import Report  # noqa: E402
from _experiments import load_experiment  # noqa: E402

EXP = "X-20260101-abandoned-example"

# Sealed >30 days before any plausible run of this test, so E13's age condition is always met.
PREREG = """schema_version: 1
exp_id: X-20260101-abandoned-example
line: X
status: sealed
title: an example
question: does the example work
estimand:
  name: skill_response_mean
  reference_basis: 200 cells, one binary
data:
  leakage_checks: [spatially blocked folds]
nulls:
  - id: no_response
    expected:
      value: 0.0
      tolerance: 0.001
    derivation: analytic
decision_rule:
  statistic: skill_response_mean
  comparator: model_minus_best_null
  pass_if: "> 0.03"
"""
SEALED_SHA = hashlib.sha256(PREREG.encode()).hexdigest()

SEAL_ROW = {
    "exp_id": EXP,
    "line": "X",
    "prereg_sha256": SEALED_SHA,
    "sealed_at": "2026-01-01T00:00:00Z",
    "seal_commit": "0" * 40,
    "statistic": "skill_response_mean",
    "nulls": ["no_response"],
}
ABANDON_ROW = {
    "exp_id": EXP,
    "event": "abandoned",
    "reason": "superseded within the hour; nothing ran",
    "at": "2026-01-02T00:00:00Z",
}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal repo whose experiment is sealed, stale, and result-free."""
    (tmp_path / "experiments" / EXP).mkdir(parents=True)
    (tmp_path / "experiments" / EXP / "preregistration.yaml").write_text(PREREG, encoding="utf-8")
    monkeypatch.setattr(ce, "repo_root", lambda: tmp_path)
    return tmp_path


def write_registry(root: Path, *rows: dict) -> None:
    (root / "experiments" / "registry.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
    )


def codes(root: Path) -> list[str]:
    exp = load_experiment(root / "experiments" / EXP)
    rep = Report("test")
    ce.check_seal(exp, ce.registry_index(), ce.abandonment_index(), rep)
    return [f.code for f in rep.findings]


def test_a_stale_seal_with_no_reason_is_reported(repo: Path) -> None:
    """The gate must still fire, or the test below proves only that nothing is checked."""
    write_registry(repo, SEAL_ROW)
    assert codes(repo) == ["E13"]


def test_the_registry_row_clears_e13_without_touching_the_sealed_bytes(repo: Path) -> None:
    write_registry(repo, SEAL_ROW, ABANDON_ROW)
    assert codes(repo) == []

    # The property the whole repair is for: the file on disk is byte-identical to what was sealed.
    live = (repo / "experiments" / EXP / "preregistration.yaml").read_bytes()
    assert hashlib.sha256(live).hexdigest() == SEALED_SHA


def test_an_event_row_does_not_shadow_the_seal_it_refers_to(repo: Path) -> None:
    """The abandonment is appended AFTER the seal, so recency alone would pick the wrong row."""
    write_registry(repo, SEAL_ROW, ABANDON_ROW)
    assert ce.registry_index()[EXP]["prereg_sha256"] == SEALED_SHA
    assert ce.abandonment_index()[EXP]["reason"] == ABANDON_ROW["reason"]


def test_abandoned_in_the_yaml_is_still_honoured_when_it_is_part_of_the_sealed_bytes(
    repo: Path,
) -> None:
    """The old home is not withdrawn; it is only unreachable AFTER sealing.

    ⚠ This has to be tested with the key inside the SEALED bytes, so that the hash still matches.
    An earlier version of this test flipped the status to `draft` instead -- which passes whatever
    the E13 branch does, because check_seal returns before reaching it for anything unsealed. It
    asserted nothing, in exactly the way this repository keeps finding tests assert nothing.
    """
    text = PREREG + 'abandoned: "never launched"\n'
    prereg = repo / "experiments" / EXP / "preregistration.yaml"
    prereg.write_text(text, encoding="utf-8")
    write_registry(repo, {**SEAL_ROW, "prereg_sha256": hashlib.sha256(text.encode()).hexdigest()})
    assert codes(repo) == []


def test_e13_cannot_fire_for_a_draft_at_all(repo: Path) -> None:
    """The fact that made the old remedy unreachable: E13's condition needs a seal.

    So "add `abandoned:` to the pre-registration" was only ever available in the state where the
    gate it answers can never fire. Pinned because it is the premise of the whole repair.
    """
    prereg = repo / "experiments" / EXP / "preregistration.yaml"
    prereg.write_text(PREREG.replace("status: sealed", "status: draft"), encoding="utf-8")
    write_registry(repo)
    assert "E13" not in codes(repo)


def test_abandoning_something_that_ran_is_a_contradiction_and_is_reported(repo: Path) -> None:
    write_registry(repo, SEAL_ROW, ABANDON_ROW)
    (repo / "experiments" / EXP / "result.jsonl").write_text(
        json.dumps(
            {
                "arm": "model",
                "statistic": "skill_response_mean",
                "value": 0.5,
                "prereg_sha256": SEALED_SHA,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    found = codes(repo)
    assert "E13" in found, "an abandoned experiment that produced results must not pass silently"
