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

...AND THE SAME SHAPE TWICE MORE, MEASURED 2026-09-16 — instances 7 and 8. Stripping prose by FLAG
closed the flag door and left two others open, both of which let somebody else's text back in as
shell. Neither command runs anything:

    git commit -F - <<'MSG' … MSG     a commit message containing "…20 h ago; the result is…"
    grep -n 'def test|python3 -c' …   a search whose PATTERN contains a vertical bar

The cause was one line: the segmenter split the already-lexed string on separator CHARACTERS, and a
character cannot tell an operator from the same character sitting inside a quoted argument or a
heredoc body. An English semicolon opened a segment whose first word was "the", "the" is not a safe
verb, and the command was refused. Fixed here two ways, neither of which weakens a pinned case:

  1. SEGMENT ON SEPARATOR TOKENS, NOT CHARACTERS. `shlex` with `punctuation_chars=True` splits real
     operators out as their own tokens while leaving quoted text whole, so prose stops producing
     fake segments. `cat a.py&&python3 b.py`, which has no whitespace around its operator, still
     splits into its two real commands.
     ⚠ ONLY COMMAND SEPARATORS SPLIT A SEGMENT — see SEPARATORS. Redirections (`>`, `<`, `<<`) do
     not start a new command, and treating them as if they did would newly deny `cat a > b.py`.
  2. A HEREDOC BODY IS DATA ONLY WHEN THE COMMAND RECEIVING IT CANNOT EXECUTE IT. Same by-capability
     discipline as the prose list, and for the same reason. `git commit -F - <<'MSG'` hands its body
     to `git`, which cannot run it. `python3 - <<'PY'` and `bash <<EOF` keep their bodies and stay
     denied, because there the body IS the program.

Applied 2026-09-16 on an explicit owner decision, after being written, verified and deliberately
NOT applied the same day: relaxing a safety guard is not something an agent does on its own
initiative, however good the argument. Record:
`docs/decisions/20260916-INT-the-command-lexer-resplits-prose-on-shell-operators.md`.
"""

from __future__ import annotations

import re
import shlex
import sys

PROSE = {"--message", "--body", "--subject", "--reason", "--allow-red"}

# What starts a NEW command, and therefore a new segment whose first word must be a safe verb.
# Deliberately NOT `<`, `>`, `<<`, `>>`, `(`, `)`: a redirection continues the command it belongs
# to, so splitting on one would newly deny `cat notes.md > out.py`, which runs nothing. A `(` is
# not on the list either, and needs none -- it is not a safe verb, so a subshell fails closed.
SEPARATORS = frozenset({";", ";;", "&", "&&", "|", "||", "|&"})

# `<<` or `<<-`, then an optionally-quoted delimiter word. The quoting of the delimiter decides
# whether the SHELL expands the body; it makes no difference to whether the body is a program, so
# it is matched and discarded here.
#
# ⚠ THIS PATTERN IS ONLY EVER RUN ON A COMMAND ALREADY KNOWN TO CONTAIN A REAL `<<` OPERATOR — see
# `HEREDOC_OPS` and its use in `main`. Run on any raw string it is the bug this file exists to
# prevent, and it was: on 2026-09-16, minutes after the fix above, it matched a `<<'MSG'` being
# TALKED ABOUT inside a quoted `--body` argument, cut the command at that line, left an unbalanced
# quote, and so failed closed onto the raw text — denying an `inbound.py` call that runs nothing.
# Instance 9, in the half of the fix that was written to close instances 7 and 8. A regex over raw
# text cannot tell an operator from the same characters inside somebody's prose; only the lexer can.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# `<<` as the LEXER emits it, which is the only evidence that a heredoc is real. Inside a quoted
# argument the same two characters stay part of that argument's token and never appear here.
HEREDOC_OPS = frozenset({"<<", "<<-"})

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


def operator_tokens(raw: str) -> list[str]:
    """Lex `raw` with real shell operators split out as their own tokens.

    A quoted `a; b` stays ONE token, so nobody's prose can pose as a separator; an unquoted
    `a.py&&python3` splits, so no real second command can hide in one token.
    """
    lexer = shlex.shlex(raw, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def split_heredoc(raw: str) -> tuple[str, list[str]]:
    """`(command_text, bodies)` — the heredoc bodies lifted out of `raw`.

    Returns `(raw, [])` when there is no heredoc. The caller decides whether the bodies are data or
    a program; this only separates them.

    ⚠ SCANNING RESUMES AFTER THE BODY JUST TAKEN, never from the start. The `<<DELIM` stays in the
    command text -- it is part of the command -- so a rescan would match it again, find no second
    terminator, and swallow everything after the first one as a body. `… <<'MSG' … MSG && python3
    heavy.py` would then have its second command hidden from the verb check instead of denied.
    """
    bodies: list[str] = []
    text = raw
    pos = 0
    while True:
        m = HEREDOC.search(text, pos)
        if m is None:
            return text, bodies
        eol = text.find("\n", m.end())
        if eol == -1:
            return text, bodies  # the redirection is there but no body followed
        delimiter = m.group(2)
        lines = text[eol + 1 :].split("\n")
        for i, line in enumerate(lines):
            if line.strip() == delimiter:  # `<<-` allows the terminator to be indented
                bodies.append("\n".join(lines[:i]))
                text = text[: eol + 1] + "\n".join(lines[i + 1 :])
                pos = eol + 1
                break
        else:
            # Unterminated: treat the whole remainder as body rather than as command text.
            bodies.append(text[eol + 1 :])
            return text[: eol + 1], bodies


def all_verbs_are_safe(tokens: list[str], raw: str) -> bool:
    """True only if EVERY segment of the command starts with a verb that cannot run a file."""
    # A substitution can put any program at all behind a safe-looking verb.
    if "$(" in raw or "`" in raw or "<(" in raw:
        return False
    segment: list[str] = []
    for token in [*tokens, ";"]:  # the trailing separator flushes the last segment
        if token in SEPARATORS:
            for tok in segment:
                name, sep, _ = tok.partition("=")
                if sep and name.isidentifier():
                    continue  # a leading VAR=value assignment, not the verb
                # Executing a script is not reading it, however the path is spelled.
                if tok.endswith(".py") or tok.rsplit("/", 1)[-1] not in SAFE_VERBS:
                    return False
                break  # the verb of this segment was fine; the rest are its arguments
            segment = []
            continue
        segment.append(token)
    return True


def main() -> None:
    raw = sys.stdin.read()
    try:
        # ASK THE LEXER WHETHER THERE IS A HEREDOC AT ALL, before any pattern touches the raw text.
        # A `<<` inside a quoted argument is part of that argument's token and never shows up as an
        # operator, so a command that merely TALKS about a heredoc is left entirely alone.
        raw_tokens = operator_tokens(raw)
        if HEREDOC_OPS.isdisjoint(raw_tokens):
            command_text, bodies = raw, []
        else:
            command_text, bodies = split_heredoc(raw)
        # Judge the COMMAND LINE first, with any heredoc body held back. If every verb on it is one
        # that cannot execute what it is handed, the body is data -- a commit message -- and must
        # not be read as shell OR keyword-matched. If any verb could execute it, the body may BE
        # the program, so it goes back in and is judged with the rest.
        if bodies and all_verbs_are_safe(operator_tokens(command_text), command_text):
            text, safe = command_text, True
        else:
            text, safe = raw, all_verbs_are_safe(raw_tokens, raw)
        tokens = shlex.split(text)
    except ValueError:
        # Unbalanced quotes: hand back the raw command so the caller keeps its old broad matching.
        print("UNSAFE")
        print(raw)
        return
    print("SAFE" if safe else "UNSAFE")
    print(strip_prose(tokens))


if __name__ == "__main__":
    main()
