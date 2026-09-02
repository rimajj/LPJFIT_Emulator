#!/usr/bin/env python3
"""Generate the verdict's metrics block and outcome from result.jsonl.

    tools/render_verdict.py <exp_id>          # write/refresh experiments/<id>/verdict.md
    tools/render_verdict.py <exp_id> --check  # exit 1 if the committed block is stale

The metrics table is GENERATED, and CI regenerates it and diffs (E10). Two consequences, and they
are the entire reason this tool exists rather than a convention:

  * a reported number and the nulls it was measured against are in the same table BY CONSTRUCTION --
    there is no way to write one without the others;
  * the pass/fail line is COMPUTED from the pre-registered decision rule, not typed by whoever is
    writing up the result. A verdict records an outcome; it cannot assert one (E09).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root
from _experiments import (
    evaluate,
    extract_metrics_block,
    load_experiment,
    render_metrics_block,
    splice_metrics_block,
)

SKELETON = """# Verdict — {exp_id}

outcome: {outcome}

**Question.** {question}

**Estimand.** `{statistic}` — {definition}

**Reference basis.** {basis}

## What this means

<!-- Two or three sentences in plain language. State what was measured, against what, and what is
     still unknown. If the outcome is `invalid`, say plainly which null misbehaved and why that
     voids the comparison rather than merely weakening it. -->

## Metrics

{block}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("exp_id")
    ap.add_argument("--check", action="store_true", help="do not write; fail if stale")
    args = ap.parse_args(argv)

    root = repo_root()
    directory = root / "experiments" / args.exp_id
    if not (directory / "preregistration.yaml").exists():
        print(f"render_verdict: no such experiment {args.exp_id!r}", file=sys.stderr)
        return 2

    exp = load_experiment(directory)
    if not exp.results:
        print(
            f"render_verdict: {args.exp_id} has no result rows yet — nothing to render",
            file=sys.stderr,
        )
        return 2

    ev = evaluate(exp)
    block = render_metrics_block(exp, ev)
    path = directory / "verdict.md"

    if args.check:
        if not path.exists():
            print(f"render_verdict: {path.relative_to(root)} does not exist", file=sys.stderr)
            return 1
        have = extract_metrics_block(path.read_text(encoding="utf-8"))
        if have is None or have.strip() != block.strip():
            print(
                f"render_verdict: {path.relative_to(root)} metrics block is stale", file=sys.stderr
            )
            return 1
        print(f"{path.relative_to(root)}: up to date ({ev.outcome})")
        return 0

    est = exp.prereg.get("estimand", {}) or {}
    if path.exists():
        text = splice_metrics_block(path.read_text(encoding="utf-8"), block)
        # Keep the recorded outcome in step with the computed one.
        text = re.sub(
            r"^\s*outcome\s*:\s*[a-z]+\s*$",
            f"outcome: {ev.outcome}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text = SKELETON.format(
            exp_id=args.exp_id,
            outcome=ev.outcome,
            question=str(exp.prereg.get("question", "")).strip(),
            statistic=ev.statistic,
            definition=" ".join(str(est.get("definition", "")).split()),
            basis=" ".join(str(est.get("reference_basis", "")).split()),
            block=block,
        )
    path.write_text(text, encoding="utf-8")

    print(f"wrote {path.relative_to(root)}")
    print(f"  outcome: {ev.outcome}")
    for r in ev.reasons:
        print(f"  - {r}")
    if ev.outcome == "invalid":
        print(
            "\n  NOTE: `invalid` is not a soft `fail`. It means the comparison does not license a"
        )
        print(
            "  conclusion either way — fix the apparatus or the metric, then run a NEW experiment."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
