#!/usr/bin/env python3
"""Record that a sealed experiment will never be run, without touching its sealed bytes.

    tools/abandon_experiment.py <exp_id> --reason "superseded by <new id>; nothing ran"

WHY THIS TOOL EXISTS, AND WHY THE REASON DOES NOT GO IN THE PRE-REGISTRATION.

E13 fires when a pre-registration has been sealed for more than 30 days with no results, and its
hint used to say: add `abandoned: <reason>`. But E03 hashes the sealed file and reports any change,
so adding that key trips E03 -- measured both ways on 2026-09-21. The remedy was therefore available
only for a DRAFT, which is the one state in which E13 can never fire, because E13 keys off
`sealed_at`. The remedy and the condition were disjoint by construction.

A gate whose remedy is impossible is a gate people learn to route around, so the fix is not to carve
an exception into E03 ("immutable except for one key" is a rule with an exception, parsed by the
same code that enforces the rule). The abandonment is recorded where every other correction in this
repository goes: an APPENDED ROW on an append-only ledger, written by a tool rather than by hand.
The sealed bytes stay genuinely immutable and E03 is untouched.

`abandoned:` in the YAML is still honoured by E13 and is still the right home for a draft.

Record: docs/decisions/20260921-INT-a-sealed-experiment-cannot-be-marked-abandoned-*.md, repair (A).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_experiments as chk
from _common import repo_root
from _experiments import load_experiment


def refuse(exp_id: str, exp) -> int | None:
    """Every reason this abandonment must not be written, or None if it may be.

    Split out of main() so each refusal stays one short, quotable paragraph: these messages are the
    only thing the caller sees, and a checker that refuses without saying which of five states it is
    in is the failure this repository keeps re-finding.
    """
    # A draft has a cheaper and better home for this: its own bytes, which are not yet frozen.
    # Sending it here instead would scatter the reason across two places for no gain.
    if str(exp.prereg.get("status", "draft")) != "sealed":
        print(
            f"abandon: {exp_id} is not sealed, so its bytes are still editable.\n"
            "  Add `abandoned: <reason>` to the pre-registration itself; E13 honours it there.",
            file=sys.stderr,
        )
        return 2

    # Abandoning something that produced results would be a self-contradicting record, and E13 now
    # reports exactly that. Refuse to create it rather than writing it and flagging it afterwards.
    if exp.results:
        print(
            f"abandon: {exp_id} has {len(exp.results)} result row(s) -- it ran.\n"
            "  A finished experiment is closed with a verdict, not an abandonment.",
            file=sys.stderr,
        )
        return 1

    if exp_id not in chk.registry_index():
        print(
            f"abandon: {exp_id} is sealed but absent from experiments/registry.jsonl.\n"
            "  Fix that first (E03) -- abandoning a seal the ledger never\n"
            "  recorded records nothing.",
            file=sys.stderr,
        )
        return 1

    already = chk.abandonment_index().get(exp_id)
    if already is not None:
        print(
            f"abandon: {exp_id} was already abandoned on {str(already.get('at', ''))[:10]}:\n"
            f"  {already.get('reason', '')}"
        )
        return 0

    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("exp_id")
    ap.add_argument(
        "--reason",
        required=True,
        help="why it will never run. A superseding exp_id belongs here by name",
    )
    args = ap.parse_args(argv)

    root = repo_root()
    directory = root / "experiments" / args.exp_id
    prereg = directory / "preregistration.yaml"
    if not prereg.exists():
        print(f"abandon: no such pre-registration: {prereg}", file=sys.stderr)
        return 2

    reason = args.reason.strip()
    if len(reason) < 10:
        print("abandon: give a real reason -- that is the entire point of the row", file=sys.stderr)
        return 2

    exp = load_experiment(directory)
    refused = refuse(args.exp_id, exp)
    if refused is not None:
        return refused

    row = {
        "exp_id": args.exp_id,
        "event": "abandoned",
        "reason": reason,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    registry = root / "experiments" / "registry.jsonl"
    with registry.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"abandoned {args.exp_id}")
    print(f"  reason {reason}")
    print("\nThe sealed pre-registration was NOT touched -- its hash still matches the seal row.")
    print("Now commit experiments/registry.jsonl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
