#!/usr/bin/env python3
"""Lex a Bash command for the deny hooks: strip prose, classify the verbs.

Reads the raw command on stdin. Prints TWO things:

    line 1      SAFE | UNSAFE   -- does EVERY segment start with a verb that cannot execute a file?
    line 2..    the scan string -- the command with the ARGUMENTS OF PROSE-CARRYING FLAGS removed

WHY THIS FILE EXISTS RATHER THAN A SECOND COPY. `slurm-guard.sh` grew this lexer on 2026-09-14 to
stop reading other people's prose as commands. `commit-guard.sh` needed exactly the same thing and
had grown its own weaker version instead -- a `sed` that strips EVERY quoted string -- and the two
then drifted: the sed version is used by one rule in that file and not by the rule above it, which
is the defect measured on 2026-09-15 (a commit whose MESSAGE mentions staging was refused as if it
staged). Two copies of one idea is how that happened, so there is now one copy.

THE BUG SHAPE THIS WHOLE FILE EXISTS TO PREVENT: A GUARD MATCHING TEXT THAT IS NOT WHAT IT GUARDS.
Five measured instances in this repository, every one of them a guard grepping a whole command
string. Before adding a rule to either hook, ask what INPUT it judges.

WHY BY FLAG AND NOT BY QUOTING, which is the distinction the sed version got wrong. Stripping every
quoted string is wrong because a quoted string can BE the program:

    python3 -c "import torch; torch.zeros(1)"      <- must stay DENIED
    bash -c "git add x && git commit -m y"         <- must stay DENIED

So the prose list is closed and explicit, and every entry takes free text by construction -- no job
can be launched through `--body`. It is every prose-carrying flag in the repo, checked 2026-09-15:
-m (git), --message, --body and --subject (tools/inbound.py), --reason (tools/campaigns.py),
--allow-red (tools/merge.sh).

FAILS CLOSED. A command that will not lex prints UNSAFE and its own raw text, so the caller falls
back to the old broad matching rather than to a bypass. Callers must also treat a crashed or empty
result, or a first line that is neither word verbatim, as UNSAFE.
"""

from __future__ import annotations

import re
import shlex
import sys

PROSE = {"--message", "--body", "--subject", "--reason", "--allow-red"}

# Verbs that READ, COMPARE or MOVE a file and cannot execute one. Closed and explicit, the same
# discipline as PROSE: anything not on it keeps the hooks' old keyword behaviour, so an unknown
# verb is never assumed harmless.
#
# DELIBERATELY WITHOUT `find` AND `xargs`: `-exec` and piping into a runner are their ordinary use,
# not an exotic one. Also without `bash`, `sh`, `env`, `nohup`, `time` and `sudo`, each of which
# exists to run something else.
SAFE_VERBS = frozenset(
    [
        # read and inspect
        "cat", "head", "tail", "less", "more", "wc", "nl", "file", "stat", "du", "tree", "column",
        # search, compare, slice
        "grep", "egrep", "fgrep", "rg", "diff", "cmp", "sed", "awk", "cut", "sort", "uniq",
        # paths and digests
        "ls", "realpath", "dirname", "basename", "readlink", "md5sum", "sha256sum",
        # move and edit the tree, which is not the same as running what is in it
        "cp", "mv", "rm", "mkdir", "touch", "chmod", "ln",
        # the two tools this repo drives constantly, neither of which can launch a job
        "git", "ruff",
    ]
)  # fmt: skip


def is_prose_arg(flag: str, arg: str) -> bool:
    """Is `arg` free text belonging to `flag`, rather than something that runs?"""
    if flag in PROSE:
        return True
    # -m is a git message here, but a MODULE in `python3 -m torch.distributed.run`. A commit
    # message has whitespace; a module name never does. That is the whole difference.
    return flag == "-m" and any(c.isspace() for c in arg)


def strip_prose(tokens: list[str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        head, sep, _ = t.partition("=")
        if sep and head in PROSE:  # --body=...
            out.append(head)
            i += 1
            continue
        if i + 1 < len(tokens) and is_prose_arg(t, tokens[i + 1]):
            out.append(t)
            i += 2
            continue
        out.append(t)
        i += 1
    return " ".join(out)


def all_verbs_are_safe(scan: str, raw: str) -> bool:
    """True only if EVERY segment of the command starts with a verb that cannot run a file."""
    # A substitution can put any program at all behind a safe-looking verb.
    if "$(" in raw or "`" in raw or "<(" in raw:
        return False
    # Split the SCAN, not the raw text: it is already lexed, so an operator sitting inside somebody
    # else's prose is gone by now, while `cat a.py&&python3 b.py` -- which has no whitespace around
    # its operator and so survives shlex as one token -- still splits into its two real segments.
    for segment in re.split(r"[;&|]+", scan):
        for tok in segment.split():
            name, sep, _ = tok.partition("=")
            if sep and name.isidentifier():
                continue  # a leading VAR=value assignment, not the verb
            # Executing a script is not reading it, however the path is spelled.
            if tok.endswith(".py") or tok.rsplit("/", 1)[-1] not in SAFE_VERBS:
                return False
            break  # the verb of this segment was fine; the rest are its arguments
    return True


def main() -> None:
    raw = sys.stdin.read()
    try:
        tokens = shlex.split(raw)
    except ValueError:
        # Unbalanced quotes: hand back the raw command so the caller keeps its old broad matching.
        print("UNSAFE")
        print(raw)
        return
    scan = strip_prose(tokens)
    print("SAFE" if all_verbs_are_safe(scan, raw) else "UNSAFE")
    print(scan)


if __name__ == "__main__":
    main()
