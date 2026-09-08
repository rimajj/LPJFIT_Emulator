"""Resolved access to `config/paths.yaml` from inside the package.

The `pathsafety` gate forbids an absolute cluster path anywhere but `config/paths.yaml`, so every
module that needs one asks here. `${a.b}` references are expanded against the same document, which
is why the config can carry one canonical root with derived entries beneath it.

    from vegemu.paths import paths
    paths["ground_truth"]["restart_spinup_end"]
    path("ground_truth.restart_spinup_end")          # dotted, resolved, as a Path

A missing key raises rather than returning an empty string: an empty path silently substituted into
a file open is how a job comes to run "successfully" over no data at all.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REF = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")
_MAX_DEPTH = 10


def repo_root() -> Path:
    """The worktree this package was imported from.

    Walks up from this file rather than from the process CWD, so a script launched from a job's
    scratch directory still finds its own line's checkout and not the integration one. That exact
    confusion -- a script resolving the repo root from CWD and writing its output into the shared
    integration worktree -- is why `config/paths.yaml` exists in the first place.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "paths.yaml").is_file():
            return parent
    raise FileNotFoundError(f"no config/paths.yaml above {here}")


def _get(tree: dict[str, Any], dotted: str) -> Any:
    node: Any = tree
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def _resolve(value: Any, tree: dict[str, Any], depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("paths.yaml: reference nesting too deep (a cycle?)")
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            return str(_resolve(_get(tree, m.group(1)), tree, depth + 1))

        return _REF.sub(repl, value)
    if isinstance(value, dict):
        return {k: _resolve(v, tree, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, tree, depth + 1) for v in value]
    return value


@lru_cache(maxsize=1)
def paths() -> dict[str, Any]:
    """The whole of `config/paths.yaml`, with every `${a.b}` reference already expanded."""
    raw = yaml.safe_load((repo_root() / "config" / "paths.yaml").read_text(encoding="utf-8")) or {}
    resolved = _resolve(raw, raw)
    assert isinstance(resolved, dict)
    return resolved


def path(dotted: str) -> Path:
    """One entry, as a `Path`. Raises `KeyError` naming the nearest valid prefix if absent."""
    try:
        value = _get(paths(), dotted)
    except KeyError:
        parts = dotted.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            try:
                node = _get(paths(), prefix)
            except KeyError:
                continue
            keys = ", ".join(sorted(node)) if isinstance(node, dict) else "(not a mapping)"
            raise KeyError(f"no path {dotted!r}; {prefix!r} exists with: {keys}") from None
        raise KeyError(f"no path {dotted!r}; top level has: {', '.join(sorted(paths()))}") from None
    if not isinstance(value, str):
        raise TypeError(f"{dotted!r} is a {type(value).__name__}, not a single path")
    return Path(value)


def scratch(*parts: str) -> Path:
    """A directory under the large-file scratch root, created if absent.

    Nothing large is ever committed, so every corpus shard, checkpoint and metrics file lands here.
    """
    out = path("scratch.root").joinpath(*parts)
    out.mkdir(parents=True, exist_ok=True)
    return out
