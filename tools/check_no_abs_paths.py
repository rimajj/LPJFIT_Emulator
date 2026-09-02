#!/usr/bin/env python3
"""Path-safety checks for scripts, tools and the package.

Four defects, each of which cost the predecessor real work:

    P01  a hardcoded absolute cluster path outside config/paths.yaml
         Several predecessor scripts opened with a literal repo root, so running one from a work
         line's worktree silently wrote its output into the SHARED integration checkout -- dirtying
         the one checkout every line depends on, and losing the result from the branch that produced
         it. Derive the root from the file: `Path(__file__).resolve().parent.parent` / `${BASH_SOURCE}`.

    P02  a shell script under scripts/ that does not self-locate its repo root
         Same defect, other language. The wrapper must submit against ITS OWN worktree.

    P03  an sbatch heredoc with no completion sentinel, or no --account
         Without a greppable last line, a later session cannot tell a finished job from a dead one,
         and results here arrive after the launching session has ended. Without --account the job is
         rejected at submit time on this cluster.

    P04  a job input/output path under /tmp or $TMPDIR
         Compute nodes cannot read the login node's local /tmp, so a job that names one fails in a
         way whose error message points nowhere near the cause. Job files live on shared /p.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Report, base_parser, iter_text_files, select_files  # noqa: E402

# Paths that may legitimately be absolute, anywhere.
ALLOWED_FILES = {
    "config/paths.yaml",  # by construction the one place paths live
    "tools/check_no_abs_paths.py",  # this file names the patterns it forbids
}

# Absolute cluster roots that must not be hardcoded.
ABS_RE = re.compile(r"(?<![\w/])(/p/(?:projects|tmp)/|/home/[a-z][\w-]*)")

# A /tmp path used as a job file. We only flag it in a SLURM context (see below), because a genuine
# scratch temp file inside a single process is fine.
TMP_RE = re.compile(r"(?<![\w/])(/tmp/|\$TMPDIR|\$\{TMPDIR\})")

SELF_LOCATE_RE = re.compile(r'BASH_SOURCE\[0\]|\$\{BASH_SOURCE')
SBATCH_RE = re.compile(r"\bsbatch\b|#SBATCH")
SENTINEL_RE = re.compile(r"===\s*JOB DONE\s+tag=")
ACCOUNT_RE = re.compile(r"--account|#SBATCH\s+-A\b|SBATCH_ACCOUNT")

# A line that is clearly documentation rather than code. Comments still count for P01: a stale path
# in a comment is exactly how the predecessor's config drifted out of truth. But a line that is
# pointing AT config/paths.yaml is the fix, not the defect.
POINTS_AT_CONFIG = re.compile(r"config/paths\.ya?ml")


def check_file(rel: str, lines: list[str], rep: Report) -> None:
    if rel in ALLOWED_FILES:
        return

    text = "\n".join(lines)
    is_shell = rel.endswith(".sh")
    # The SLURM checks apply to job scripts only. Matching on content alone was wrong: a config or
    # doc that merely NAMES sbatch (for instance the gate registry, which describes what the
    # pathsafety gate blocks) is not a job script, and demanding a completion sentinel in it is
    # nonsense. Require the file to be a shell/job file AND to mention sbatch.
    is_slurm = (is_shell or rel.endswith(".jcf")) and bool(SBATCH_RE.search(text))

    for i, ln in enumerate(lines, start=1):
        if POINTS_AT_CONFIG.search(ln):
            continue
        m = ABS_RE.search(ln)
        if m:
            rep.add(
                rel,
                "P01",
                f"hardcoded absolute path {m.group(1)!r}",
                line=i,
                hint="read it from config/paths.yaml; derive the repo root from the file itself",
            )
        if is_slurm:
            t = TMP_RE.search(ln)
            if t:
                rep.add(
                    rel,
                    "P04",
                    f"job path under {t.group(1)!r}",
                    line=i,
                    hint="compute nodes cannot read the login node's /tmp — put it on shared /p",
                )

    if is_shell and rel.startswith("scripts/") and not SELF_LOCATE_RE.search(text):
        rep.add(
            rel,
            "P02",
            "shell script does not self-locate its repo root",
            hint='add: REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" so a worktree copy submits against its own tree',
        )

    if is_slurm:
        if not SENTINEL_RE.search(text):
            rep.add(
                rel,
                "P03",
                "no completion sentinel",
                hint='the job\'s last line must be: echo "=== JOB DONE tag=<tag> exit=$rc ===" — it is how a later session harvests it',
            )
        if not ACCOUNT_RE.search(text):
            rep.add(
                rel,
                "P03",
                "no --account",
                hint="this cluster rejects a submission without an account; take it from config/paths.yaml cluster.account",
            )


def main(argv: list[str] | None = None) -> int:
    ap = base_parser(__doc__ or "")
    args = ap.parse_args(argv)
    rep = Report("check_no_abs_paths")
    for rel, lines in iter_text_files(select_files(args), (".py", ".sh", ".jcf", ".toml", ".yaml", ".yml")):
        if rel.startswith("config/"):
            continue
        check_file(rel, lines, rep)
    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
