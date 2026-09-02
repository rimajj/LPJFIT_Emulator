#!/usr/bin/env python3
"""Append result rows to an experiment. The ONLY sanctioned writer of result.jsonl.

    tools/append_result.py --exp <exp_id> --from <metrics.json>

The metrics JSON is produced by the job itself and must look like:

    {
      "prereg_sha256": "3a9f...",          # stamped into the job by the launcher
      "statistic": "r2_oos_count",
      "n": 12400000,
      "job_ids": [1772586],
      "arms": {"model": 0.9711, "persistence": 0.9623, "shuffled_target": 0.0041}
    }

Why a tool rather than a hand-edited file: the `prereg_sha256` is copied out of the JOB'S OWN stamp,
never out of the current working tree. That is the whole point -- it proves which version of the
pre-registration the run was actually governed by, so editing the pre-registration afterwards is
detectable (E04) instead of invisible.

The model row also carries every null's value alongside it, so a number and its nulls are physically
in the same record. There is no way to append a claim without them (E06).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root
from _experiments import load_experiment, registry_lookup


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--exp", required=True)
    ap.add_argument("--from", dest="src", required=True, help="metrics JSON emitted by the job")
    ap.add_argument("--harvested-by", default="", help="session or campaign tag doing the harvest")
    args = ap.parse_args(argv)

    root = repo_root()
    directory = root / "experiments" / args.exp
    if not (directory / "preregistration.yaml").exists():
        print(f"append_result: no such experiment {args.exp!r}", file=sys.stderr)
        return 2

    exp = load_experiment(directory)
    metrics = json.loads(Path(args.src).read_text(encoding="utf-8"))

    arms = metrics.get("arms") or {}
    if not arms:
        print("append_result: metrics JSON has no `arms` object", file=sys.stderr)
        return 2

    statistic = str(metrics.get("statistic") or exp.statistic)
    stamp = str(metrics.get("prereg_sha256", ""))
    if not stamp:
        print(
            "append_result: metrics JSON carries no prereg_sha256.\n"
            "  The launcher stamps VEGEMU_PREREG_SHA256 into every job; write it into the metrics\n"
            "  file. Without it the result cannot prove which pre-registration governed the run.",
            file=sys.stderr,
        )
        return 2

    sealed = registry_lookup(root, args.exp)
    if sealed and stamp != sealed:
        print(
            f"append_result: WARNING the job ran under prereg {stamp[:12]} but the sealed hash is\n"
            f"  {sealed[:12]}. The row is appended verbatim -- it is evidence, not a draft --\n"
            f"  and the experiments gate reports this as E04 (prereg edited after the run).",
            file=sys.stderr,
        )

    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    nulls = {k: v for k, v in arms.items() if k != "model"}

    rows = []
    for arm, value in arms.items():
        row = {
            "schema_version": 1,
            "exp_id": args.exp,
            "prereg_sha256": stamp,
            "arm": arm,
            "statistic": statistic,
            "value": value,
            "n": metrics.get("n"),
            "job_ids": metrics.get("job_ids", []),
            "code_commit": commit,
            "artifact_sha256": metrics.get("artifact_sha256"),
            "harvested_at": now,
            "harvested_by": args.harvested_by or metrics.get("harvested_by", ""),
        }
        if arm == "model":
            # The claim and every null it was measured against, in one record.
            row["nulls"] = nulls
        rows.append(row)

    out = directory / "result.jsonl"
    with out.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"appended {len(rows)} row(s) to {out.relative_to(root)}")
    for arm, value in arms.items():
        print(f"  {arm:24s} {value}")
    print(f"\nNow render the verdict:  tools/render_verdict.py {args.exp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
