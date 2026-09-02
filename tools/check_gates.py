#!/usr/bin/env python3
"""Verify that the workflow YAML agrees with .github/gates.toml.

    G01  a gate declared in gates.toml has no workflow file
    G02  a workflow's job name does not match the gate's declared `job`
    G03  a workflow's `paths:` filter disagrees with the gate's `paths`
    G04  a workflow's push branch list disagrees with the gate's `branches`
    G05  a workflow exists that is declared in no gate

WHY. `tools/expected_gates.py` tells an agent which check-runs to wait for, computed from
gates.toml.
If a workflow's real filter drifts away from that declaration, the agent either waits for a gate
will never appear -- and a skipped workflow reports no status at all, so it waits forever -- or,
worse,
merges without waiting for a gate that did run. The declaration and the reality have to be pinned
together by a gate of their own, or the whole scheme is only advisory.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Report, repo_root

try:
    import yaml
except ImportError:  # pragma: no cover
    print("check_gates: needs pyyaml", file=sys.stderr)
    raise SystemExit(2) from None

# Filters every workflow carries so that a change to the gate machinery re-runs everything. They are
# not part of a gate's declared `paths`, so they are excluded before comparing.
MACHINERY = {".github/gates.toml", "tools/check_gates.py"}


def _workflow_on(doc: dict) -> dict:
    """The `on:` block. PyYAML parses a bare `on:` key as the boolean True, so accept both."""
    on = doc.get("on")
    if on is None:
        on = doc.get(True)
    return on if isinstance(on, dict) else {}


def main() -> int:
    root = repo_root()
    with (root / ".github" / "gates.toml").open("rb") as fh:
        gates = list(tomllib.load(fh).get("gate", []))

    rep = Report("check_gates")
    wf_dir = root / ".github" / "workflows"
    seen: set[str] = set()

    for g in gates:
        name = str(g["name"])
        wf = wf_dir / f"{name}.yml"
        if not wf.exists():
            rep.add(f".github/workflows/{name}.yml", "G01", f"gate {name!r} has no workflow file")
            continue
        seen.add(wf.name)

        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        jobs = list((doc.get("jobs") or {}).keys())
        if str(g["job"]) not in jobs:
            rep.add(
                f".github/workflows/{name}.yml",
                "G02",
                f"declared job {g['job']!r} is not among the workflow's jobs {jobs}",
                hint=(
                    "the job name is the check-run name an agent polls — it is an interface, keep "
                    "it stable"
                ),
            )

        declared = sorted(set(g.get("paths", [])))
        on = _workflow_on(doc)
        for event in ("push", "pull_request"):
            spec = on.get(event)
            if not isinstance(spec, dict):
                continue
            actual = sorted(set(spec.get("paths") or []) - MACHINERY)
            if actual and actual != declared:
                rep.add(
                    f".github/workflows/{name}.yml",
                    "G03",
                    f"{event}.paths disagrees with gates.toml",
                    hint=f"gates.toml: {declared}\n       workflow: {actual}",
                )
            if event == "push":
                want = sorted(g.get("branches", ["main"]))
                have = sorted(spec.get("branches") or [])
                if have and have != want:
                    rep.add(
                        f".github/workflows/{name}.yml",
                        "G04",
                        f"push.branches {have} disagrees with gates.toml {want}",
                    )

    for wf in sorted(wf_dir.glob("*.yml")):
        if wf.name not in seen:
            rep.add(
                f".github/workflows/{wf.name}",
                "G05",
                "workflow is declared in no gate",
                hint=(
                    "add a [[gate]] entry so expected_gates.py knows about it, or delete the "
                    "workflow"
                ),
            )

    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
