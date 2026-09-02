#!/usr/bin/env python3
"""Read a value out of config/paths.yaml.

    tools/_paths.py cluster.python
    tools/_paths.py ground_truth.restart_spinup_end
    tools/_paths.py --all                    # dump the resolved tree as JSON

Exists so that a shell script can obtain a path without hardcoding one, which is what the
`pathsafety` gate requires of it. `${a.b}` references are resolved against the same document, so
the file can be written with one canonical root and derived entries beneath it.

Missing key -> exit 3 with a message naming the nearest valid prefix, because a silent empty string
substituted into an sbatch line is exactly the kind of failure that shows up as a job that ran
"successfully" over no data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REF = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")


def _load() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "config" / "paths.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _get(tree: dict[str, Any], dotted: str) -> Any:
    node: Any = tree
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def _resolve(value: Any, tree: dict[str, Any], depth: int = 0) -> Any:
    """Expand ${a.b} references. Depth-limited so a cyclic reference fails loudly."""
    if depth > 10:
        raise ValueError("paths.yaml: reference nesting too deep (a cycle?)")
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            return str(_resolve(_get(tree, m.group(1)), tree, depth + 1))

        return REF.sub(repl, value)
    if isinstance(value, dict):
        return {k: _resolve(v, tree, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, tree, depth + 1) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    tree = _load()

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--all":
        print(json.dumps(_resolve(tree, tree), indent=2, sort_keys=True))
        return 0

    key = args[0]
    try:
        value = _resolve(_get(tree, key), tree)
    except KeyError:
        # Name the nearest valid prefix, so the message is actionable rather than just "no".
        parts = key.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            try:
                node = _get(tree, prefix)
            except KeyError:
                continue
            keys = sorted(node) if isinstance(node, dict) else []
            print(
                f"_paths: no key {key!r}; {prefix!r} exists with: {', '.join(keys)}",
                file=sys.stderr,
            )
            return 3
        print(f"_paths: no key {key!r}; top level has: {', '.join(sorted(tree))}", file=sys.stderr)
        return 3

    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
