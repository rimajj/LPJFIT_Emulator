#!/usr/bin/env python3
"""Seal a pre-registration: validate it, freeze it, and record its hash.

    tools/seal_experiment.py <exp_id>

After sealing, the file is immutable. A launcher refuses to submit unless the pre-registration is
sealed AND committed AND its live hash still equals the sealed one, and it stamps that hash into the
job so the result carries proof of what it actually ran under.

This is the mechanism that makes "pre-registered" a fact rather than a promise: any later edit
changes the hash, and the mismatch turns CI red (E03/E04). A changed question is a NEW exp_id with
`supersedes:` naming this one -- the same discipline that keeps decision records immutable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_experiments as chk
from _common import Report, repo_root
from _experiments import load_experiment, sha256_file


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root()), *args], capture_output=True, text=True, check=False
    ).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("exp_id")
    ap.add_argument(
        "--allow-dirty",
        action="store_true",
        help="seal even though the file has uncommitted changes (you almost never want this)",
    )
    args = ap.parse_args(argv)

    root = repo_root()
    directory = root / "experiments" / args.exp_id
    prereg = directory / "preregistration.yaml"
    if not prereg.exists():
        print(f"seal: no such pre-registration: {prereg}", file=sys.stderr)
        return 2

    exp = load_experiment(directory)

    # 1. It must be valid BEFORE it is frozen. Sealing an invalid record just freezes the mistake.
    rep = Report("seal")
    chk.check_schema(exp, rep)
    if rep.findings:
        rep.emit()
        print("\nseal: refusing to seal an invalid pre-registration.", file=sys.stderr)
        return 1

    if str(exp.prereg.get("status")) == "sealed":
        print(f"seal: {args.exp_id} is already sealed (nothing to do)")
        return 0

    # 2. Freeze the status, then hash the FROZEN bytes -- the hash must describe what will be read
    # back later, so it has to be computed after the flip, not before.
    text = prereg.read_text(encoding="utf-8")
    if "\nstatus: draft" not in text and not text.startswith("status: draft"):
        print("seal: could not find a `status: draft` line to flip", file=sys.stderr)
        return 2
    prereg.write_text(text.replace("status: draft", "status: sealed", 1), encoding="utf-8")

    rel = str(prereg.relative_to(root))
    digest = sha256_file(prereg)

    # 3. Commit it, so the seal exists in history before the run it governs (E12).
    if not args.allow_dirty:
        git("add", rel)
        msg = f"exp({args.exp_id}): seal pre-registration\n\nprereg_sha256: {digest}\n"
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                msg,
                "--",
                rel,
            ],
            check=False,
        )
    seal_commit = git("rev-parse", "HEAD").strip()

    # 4. Append the ledger row.
    row = {
        "exp_id": args.exp_id,
        "line": exp.prereg.get("line"),
        "prereg_sha256": digest,
        "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seal_commit": seal_commit,
        "statistic": exp.statistic,
        "nulls": exp.null_ids,
    }
    registry = root / "experiments" / "registry.jsonl"
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"sealed {args.exp_id}")
    print(f"  prereg_sha256 {digest}")
    print(f"  seal_commit   {seal_commit[:12]}")
    print(f"  nulls         {', '.join(exp.null_ids) or '(none!)'}")
    print("\nNow commit experiments/registry.jsonl, then launch with:")
    print(f"  scripts/sbatch_py.sh --exp {args.exp_id} <tag> <script.py>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
