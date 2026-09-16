# The commit guard's escape hatch never opened, and a crashed checker was reported as a finding

- **Status:** accepted; applied, tested, full suite green
- **Date:** 2026-09-16
- **Line:** INT
- **Governs:** `.claude/hooks/commit-guard.sh`, `_lex_command.py`, `session-campaigns.sh`,
  `session-open-loops.sh`, `tests/test_commit_guard.py`
- **Discharges** the two integrator asks in `20260910-X-the-commit-guard-cannot-be-unblocked-from-
  inside.md` and `20260910-X-the-open-loops-hook-misreads-a-crash.md`, both open for six days.
- **Widening A below was put to the owner and approved**, because it lets a permission hook allow
  something it refused. Nothing else here widens anything.

## The two defects, both reported on 2026-09-10 and both still live on 2026-09-16

**A. The hatch the guard advertises could not be used.** `commit-guard.sh:22` read
`ALLOW_COMMIT_GUARD_SKIP` from the environment. A PreToolUse hook runs in the *harness's*
environment, never in the shell of the command it is judging, so the
`ALLOW_COMMIT_GUARD_SKIP=1 git commit ...` printed in its own refusal set nothing it could see. The
guard could not be lifted at all, while telling you how to lift it.

This is `MEMORY.md:hook-env-blind` for the third time. That row records the fix, on 2026-09-08, for
"both slurm-guard hatches" — the third, in the sibling file, was never touched. A defect named,
fixed and written up in one file, still live in the file next door.

**B. A checker that could not start was denied as if the repo were at fault.** `run()` folded both
non-zero outcomes into `FINDINGS`, so a crash became "The commit guard refused this commit" followed
by a traceback. On 2026-09-10 four checkers died on one import and every commit of that session was
refused that way — with A making it unliftable, which is how the two defects compose.

## What it cost, which is the part that matters

Blocked by both at once, that session committed anyway, on a command line reworded until the
guard's own filter stopped matching it. That is the worst available outcome: the designed hatch
leaves a `Guard-skip:` trailer that CI counts and reports, and the workaround leaves nothing. **A
hatch that does not open does not produce caution; it produces an unaudited bypass.**

## What was changed

**A** — the prefix is read off the lexed command text, exactly as `slurm-guard.sh:86` already does.
The exported form is kept; it costs nothing and works from a shell the caller controls.

**⚠ And only off text that LEXED, which is the half that is easy to get wrong.** When the lexer
fails it hands back the raw command, prose and all. Every other rule in that file may read the
fallback safely, because they all *deny* and raw text can only make them deny more. This rule
*allows*: on the fallback, a commit whose message merely quoted the prefix would open the guard.
So `_lex_command.py` now exits **3** when it falls back to raw, and the hatch requires exit 0.
Deny-rules ignore the status and are unchanged — which is why adding it broke no caller.

That would have been instance 11 of `MEMORY.md:guard-reads-wrong-input`, avoided only because the
shape was already named and looked for. It is pinned by a test that feeds the prefix in as prose.

**B** — a crash is told from a finding by the one thing only a crash prints, and reported as
`THE COMMIT GUARD IS BROKEN. This is not a finding about your commit.` It still **denies**: a commit
whose checks did not run is unchecked, not clean. The 2026-09-10 cause is already fixed at the
source — `tools/_common.py` re-execs under the interpreter in `config/paths.yaml`, pinned by
`tests/test_checker_bootstrap.py` — so this is the remaining half, for every other way a checker
can die.

**C, from the second record** — `session-campaigns.sh` and `session-open-loops.sh` ended their
checker calls in `2>/dev/null || true`, so a crash and a clean sweep printed the same nothing. The
campaigns one is the serious case: that hook is the only thing carrying a launched job across the
session boundary that launched it, and there are **38 open rows right now** that block every merge
from 2026-09-22. Both now say when they could not run. Non-zero is *not* the signal — `check_flags`
exits non-zero when it has findings — so the discriminator is a traceback, as in B.

## Measured

| basis | before | after |
|---|---|---|
| the hatch, written as the refusal advertises | never opens | opens |
| the prefix quoted inside a commit message, both quote styles | n/a | stays shut |
| the prefix present but the command will not lex | n/a | stays shut |
| a checker that crashes | denies as a finding, with a traceback | denies as a broken hook |
| `tests/test_commit_guard.py` | 16 cases | **22**, all green |
| full suite | — | **295 passed, 11 skipped, 0 failed** |

`tests/test_band.py` and `tests/test_clm_roundtrip.py` do not collect in this shell — `vegemu` is
not installed in it — and fail identically with these changes stashed. Pre-existing, not measured
here.

## Consequences

1. **A latent hole of the same shape is left OPEN in `slurm-guard.sh:86-87`, deliberately.** Both
   of its hatches read the scan string without checking whether it lexed, so a command that both
   fails to lex and mentions `ALLOW_LOGIN_HEAVY=`/`ALLOW_RAW_SBATCH=` in prose opens them. The
   one-line repair is the same `LEX_RC == 0`, but it *narrows* a hatch — it can newly deny a command
   that used to be allowed, which is the direction this repo has been bitten by ten times. **Owner
   decision, not taken here.** Reported in the same session it was found.
2. **The 2026-09-10 records stay as written.** Both say the fix is for the integrator to make and
   neither is edited; this record is the decision that made it.
3. **Every line may now use the hatch as documented**, and must still run the checkers by hand and
   say so in the `Guard-skip:` trailer. A trailer whose reason is untrue is worse than a denial.
