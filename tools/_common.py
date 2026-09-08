"""Shared helpers for the repository checkers.

Every checker in this directory follows the same contract, because they are all called from three
places (a commit-deny hook, a git pre-commit hook, and CI) and the caller must not have to care:

    exit 0  -> clean
    exit 1  -> findings, printed one per line as "<path>:<line>: <code> <message>"
    exit 2  -> the checker itself could not run (bad config, missing file)

`--staged` restricts the check to files staged for commit, which is what makes the commit guard fast
enough to run on every `git commit` without being resented.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------------------
# Repo location. Derived from THIS FILE, never from the working directory and never hardcoded.
#
# This is not style. In the predecessor several scripts opened with a literal repo path, so running
# one from a line's worktree silently emitted its output into the shared integration checkout --
# dirtying the one checkout every line depends on and losing the result from the branch that made
# it.
# The `pathsafety` gate exists to make that impossible; this function is what it points people at.
# --------------------------------------------------------------------------------------------------


def repo_root() -> Path:
    """The root of the worktree containing this file."""
    return Path(__file__).resolve().parent.parent


def config(name: str) -> dict:
    """Load `config/<name>.toml`. Raises SystemExit(2) if it is missing or malformed."""
    path = repo_root() / "config" / f"{name}.toml"
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        print(f"{path}: cannot run: config file is missing", file=sys.stderr)
        raise SystemExit(2) from None
    except tomllib.TOMLDecodeError as exc:
        print(f"{path}: cannot run: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


# --------------------------------------------------------------------------------------------------
# Glob matching.
#
# We translate to regex rather than using pathlib.PurePath.match or fnmatch, because we need the
# distinction those blur and the whole ownership model rests on it:
#     *   matches within ONE path segment  ("lines/*/STATE.md" must not match
# "lines/D/sub/STATE.md")
#     **  matches any number of segments   ("lines/D/**" matches everything beneath lines/D)
# fnmatch's `*` crosses `/`, which would make every exclusive ownership rule quietly too broad.
# --------------------------------------------------------------------------------------------------


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    out: list[str] = ["^"]
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern.startswith("**", i):
                i += 2
                # "a/**" matches "a/b" and "a/b/c"; a trailing slash is optional.
                if pattern.startswith("/", i):
                    i += 1
                    out.append("(?:.*/)?")
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    out.append("$")
    return re.compile("".join(out))


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_match(pattern: str, path: str) -> bool:
    """True if `path` (repo-relative, forward slashes) matches the glob `pattern`."""
    rx = _GLOB_CACHE.get(pattern)
    if rx is None:
        rx = _GLOB_CACHE[pattern] = _glob_to_regex(pattern)
    return rx.match(path) is not None


# --------------------------------------------------------------------------------------------------
# File selection
# --------------------------------------------------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root()), *args],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def staged_files() -> list[str]:
    """Repo-relative paths staged for commit, excluding deletions.

    Deletions are excluded deliberately: a checker must never block a commit that REMOVES an
    offending file, which is the usual way an over-budget document gets fixed.
    """
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def tracked_files() -> list[str]:
    return [ln.strip() for ln in _git("ls-files").splitlines() if ln.strip()]


# The three states a comparison base can be in. They must stay distinguishable, because two of them
# produce an EMPTY change list for opposite reasons -- see diff_base().
BASE_OK = "ok"
BASE_UNKNOWN = "unknown"
BASE_UNRELATED = "unrelated"


def diff_base(ref: str = "origin/main") -> tuple[str | None, str]:
    """The merge base with `ref`, and why there isn't one when there isn't.

    Returns `(base, status)`:

        BASE_OK         `base` is the merge base; a diff against it means what it says.
        BASE_UNKNOWN    `ref` does not resolve -- a fresh clone, or before the first push.
        BASE_UNRELATED  `ref` resolves but shares NO commit with HEAD, so there is no base and
                        `git diff` against it cannot be computed at all.

    THE DISTINCTION IS THE POINT, and it is not hypothetical: this repo's `origin` pointed at the
    PREDECESSOR's GitHub repository, which shares no ancestor with this history. A single "no base"
    answer collapsed that case into the bootstrap one, every caller read the resulting empty list as
    "nothing changed", and `expected_gates.py` therefore printed "no gate will run -- merge when
    ready" for every commit on every branch. A latent `pathsafety` violation sat on `main` behind
    that for as long as it was true. An empty diff must never be reachable by accident.
    """
    if not _git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip():
        return None, BASE_UNKNOWN
    base = _git("merge-base", ref, "HEAD").strip()
    if not base:
        return None, BASE_UNRELATED
    return base, BASE_OK


def changed_vs(ref: str = "origin/main") -> list[str]:
    """Repo-relative paths changed against `ref`, via the merge base.

    Falls back to the staged set when the ref is unknown, which is what happens in a fresh clone or
    before the first push -- a checker that crashed there would block the bootstrap.

    When the ref exists but shares no history, falls back to EVERY TRACKED FILE. That direction is
    deliberate: the honest answer to "which files changed" is then "cannot tell", and the safe
    reading of "cannot tell" is all of them, never none of them. Under-checking is the failure mode
    that lets a violation reach `main`; over-checking only costs seconds.
    """
    base, status = diff_base(ref)
    if status == BASE_UNKNOWN:
        return staged_files()
    if status == BASE_UNRELATED:
        return tracked_files()
    out = _git("diff", "--name-only", "--diff-filter=ACMR", str(base), "HEAD")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def select_files(args: argparse.Namespace) -> list[str]:
    """Resolve the standard --staged / --changed / explicit-paths selection."""
    if getattr(args, "paths", None):
        return [str(Path(p).as_posix()) for p in args.paths]
    if getattr(args, "staged", False):
        return staged_files()
    if getattr(args, "changed", False):
        return changed_vs(getattr(args, "ref", "origin/main"))
    return tracked_files()


def read_lines(rel: str) -> list[str] | None:
    """Read a repo-relative text file, or None if it is absent or not text."""
    path = repo_root() / rel
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------------------------------


@dataclass
class Finding:
    path: str
    code: str
    message: str
    line: int = 0
    hint: str = ""

    def render(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        text = f"{loc}: {self.code} {self.message}"
        if self.hint:
            text += f"\n    -> {self.hint}"
        return text


@dataclass
class Report:
    name: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, *a: object, **kw: object) -> None:
        self.findings.append(Finding(*a, **kw))  # type: ignore[arg-type]

    def emit(self) -> int:
        if not self.findings:
            return 0
        print(f"{self.name}: {len(self.findings)} finding(s)", file=sys.stderr)
        for f in self.findings:
            print(f.render(), file=sys.stderr)
        return 1


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("paths", nargs="*", help="explicit repo-relative paths to check")
    p.add_argument("--staged", action="store_true", help="check only files staged for commit")
    p.add_argument("--changed", action="store_true", help="check only files changed vs --ref")
    p.add_argument("--ref", default="origin/main")
    return p


def iter_text_files(
    paths: Iterable[str], suffixes: Sequence[str]
) -> Iterator[tuple[str, list[str]]]:
    """Yield (relpath, lines) for existing text files whose suffix is in `suffixes`."""
    for rel in paths:
        if suffixes and not rel.endswith(tuple(suffixes)):
            continue
        lines = read_lines(rel)
        if lines is not None:
            yield rel, lines


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() not in ("", "0", "false", "False")
