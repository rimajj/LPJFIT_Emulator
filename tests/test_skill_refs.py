"""A named skill must exist: the pointer and the page are checked against each other.

WHY THIS TEST EXISTS. `CLAUDE.md` named five skills and exactly one of them existed. Two of those
names were printed at RUNTIME by hooks -- `session-line-context.sh` at every session start, and
`slurm-guard.sh` inside the body of a DENY, so a blocked agent was told to consult a page that was
not there. Line T recorded the hole on 2026-09-09 ("referenced everywhere and enforced nowhere") and
line X hit the same edge on 2026-09-15 from the other side, when E12 changed behaviour and its
documented home turned out not to exist. Nothing failed in between, because nothing was watching.

That is precisely the shape invariant 9 rules out -- a chore with a triggering event but no failing
gate -- and it is this repository's recurring bug once more: documentation that asserts a fact
nothing verifies. B08 makes the assertion checkable.

The tests build their own tree in a tmp dir rather than asserting about the real one, so they keep
testing the CHECK after someone legitimately adds or removes a skill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_budgets as cb  # noqa: E402
from _common import Report  # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A fake repo root, with check_budgets resolving paths inside it."""
    monkeypatch.setattr(cb, "repo_root", lambda: tmp_path)
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


def skill(tree: Path, name: str) -> None:
    d = tree / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")


def findings(code: str = "B08") -> list[str]:
    """Reads `rep.findings` directly rather than via a defaulted getattr, so that a renamed
    attribute cannot make the "no findings" assertions pass vacuously."""
    rep = Report("t")
    cb.check_skill_refs(rep)
    return [f.render() for f in rep.findings if f.code == code]


def test_a_pointer_to_a_missing_skill_is_a_finding(tree):
    (tree / "CLAUDE.md").write_text("Skill: `commit-and-merge`.\n", encoding="utf-8")
    out = findings()
    assert len(out) == 1
    assert "commit-and-merge" in out[0]
    assert "CLAUDE.md:1" in out[0]


def test_a_pointer_that_resolves_is_silent(tree):
    skill(tree, "commit-and-merge")
    (tree / "CLAUDE.md").write_text("Skill: `commit-and-merge`.\n", encoding="utf-8")
    assert findings() == []


def test_hooks_are_scanned_because_a_deny_message_names_a_skill(tree):
    """The costliest instance was a DENY body: blocked, and sent to a page that did not exist."""
    (tree / ".claude" / "hooks" / "slurm-guard.sh").write_text(
        'deny "...\n\nSkill: experiment-registry. If this is not an experiment, rename the tag."\n',
        encoding="utf-8",
    )
    out = findings()
    assert len(out) == 1
    assert "experiment-registry" in out[0]


def test_skills_cross_referencing_each_other_are_scanned(tree):
    skill(tree, "cmodel-run")
    (tree / ".claude" / "skills" / "cmodel-run" / "SKILL.md").write_text(
        "See also. Skill: slurm-campaign\n", encoding="utf-8"
    )
    assert [f for f in findings() if "slurm-campaign" in f]


def test_two_pointers_on_one_line_are_both_caught(tree):
    """The real CLAUDE.md line carried `Skill: X ... Method: Y`, and a search that stopped at the
    first match on a line would have reported one of them and hidden the other."""
    (tree / "CLAUDE.md").write_text(
        "Skill: `experiment-registry` (codes). Method: `method-discipline`.\n", encoding="utf-8"
    )
    out = findings()
    assert len(out) == 2
    assert any("experiment-registry" in f for f in out)
    assert any("method-discipline" in f for f in out)


@pytest.mark.parametrize(
    "text",
    [
        "The method: take the median over patches.",  # prose, no kebab name
        "Method: compute it per cell.",  # ditto
        "`experiment-registry` is the home of the codes.",  # a name with no pointer marker
        "See docs/reference/cluster.md for skill-free facts.",  # incidental hyphenated word
    ],
)
def test_ordinary_prose_does_not_match(tree, text):
    """The kebab requirement is what keeps this from flagging every colon in the runbook. A gate
    that cries wolf gets routed around -- the lesson E12 had already had to learn."""
    (tree / "CLAUDE.md").write_text(text + "\n", encoding="utf-8")
    assert findings() == []


def test_the_real_repository_has_no_dangling_pointers(tree, monkeypatch):
    """The regression proper. Runs against the ACTUAL tree, so re-introducing a dangling name in
    CLAUDE.md or a hook fails here as well as in CI."""
    monkeypatch.setattr(cb, "repo_root", lambda: ROOT)
    assert findings() == []
