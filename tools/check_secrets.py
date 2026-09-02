#!/usr/bin/env python3
"""Refuse to commit credentials.

    S01  a token, key or password literal

WHY IT MATTERS HERE SPECIFICALLY. This project needs a GitHub token to poll its own CI, and the token
lives OUTSIDE every worktree on purpose (in the user's `gh` config), so that rotating it covers every
work line at once with nothing to commit. A well-meaning session that "helpfully" records it in a
state file does not just violate policy -- GitHub's secret scanning auto-revokes a pushed token, so
the helpful act breaks CI polling for every line simultaneously.

Deliberately narrow. A checker that cries wolf gets bypassed, and a bypassed checker is worse than
none, so this looks for high-confidence shapes only and ignores obvious placeholders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Report, base_parser, iter_text_files, select_files  # noqa: E402

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("OpenSSH private key", re.compile(r"-----BEGIN (?:RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("generic API key", re.compile(r"""(?i)\b(api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*['"]([^'"\s]{12,})['"]""")),
]

# Placeholders, examples and the checker's own vocabulary.
BENIGN = re.compile(
    r"(?i)(xxx+|\.\.\.|<[^>]+>|\$\{?[A-Z_]+\}?|example|placeholder|redacted|dummy|changeme|your[_-]?token|None|null)"
)


def main(argv: list[str] | None = None) -> int:
    ap = base_parser(__doc__ or "")
    args = ap.parse_args(argv)
    rep = Report("check_secrets")
    for rel, lines in iter_text_files(select_files(args), ()):
        if rel == "tools/check_secrets.py":
            continue
        for i, ln in enumerate(lines, start=1):
            for label, rx in PATTERNS:
                m = rx.search(ln)
                if not m:
                    continue
                captured = m.group(len(m.groups())) if m.groups() else m.group(0)
                if BENIGN.search(str(captured)):
                    continue
                rep.add(
                    rel,
                    "S01",
                    f"possible {label} literal",
                    line=i,
                    hint="keep credentials outside every worktree — a pushed token is auto-revoked, which breaks CI for all lines at once",
                )
    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
