# Line X — experiments: pre-registrations, nulls, verdicts

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/X/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py X` when it fills.

## Scope

Line X owns the **claims**: pre-registrations with every null and the value it must return, sealing,
harvesting, and saying plainly what a result does and does not license — including "invalid", which
is not a soft "fail" but a statement that the comparison licenses no conclusion either way. Line X
does not build models (T) or generate data (D).

## NEXT — start here

**Three things closed on 2026-09-15, and the oldest open item on this line is one of them.**

* **X6 `X-20260914-pilot-composition-response` — PASS.** 0.425610 against the sealed bar of
  0.337858 and best null 0.177858; passes at 5 deg too. **All seven nulls returned their
  pre-registered values**, so it is a pass and not an `invalid`. Quote it as **49 % of the
  attainable 0.863852**, and say that ceiling is still a lower bound. Verdict is rendered and
  committed. Consequence for line T: the synthesiser copying species composition is now a MEASURED
  defect, and that is its principal build.
* **X4 — RETIRED AS THE WRONG INSTRUMENT, not as a fail.** D's replicate measured the perturbed
  two-seed spread at **0.0301**, essentially identical to present-day's 0.0310, with 20.4 % of
  cell-quantities above the floor either way. The pre-stated branch was: near 0.29 it seals, near
  0.10 the conjunctive level statistic is the wrong instrument. It came in at 0.03, below even the
  low branch, so the 10 % floor dominates 79.6 % of cell-quantities and the nulls will keep
  collapsing. ⚠ **Do NOT rescue it by widening the floor** — that is a threshold chosen after seeing
  the values. **A replacement needs a NEW ESTIMAND**, and writing it is this line's next job.
* **The transferred band is vindicated.** Every band applied to a perturbed state so far took its
  tolerance from present-day climate on an unverified assumption. The two spreads agree to 0.001, so
  **nothing scored to date needs recomputing** and the 2026-09-14 "up to 29 %, unmeasured" caution
  is discharged.

**Line X's own next actions, in order:**

1. **A new estimand to replace X4.** The level-conjunctive statistic cannot work at a 10 % floor;
   what can is an open question, and it is the interesting one. It needs no new corpus.
2. **Implement the additive band floor** in `src/vegemu/score.py`: `band = max(rel_spread × |truth|,
   ABS_FLOOR)`. **`ABS_FLOOR` = 0.0384, MEASURED** — p90 of the model's own absolute two-seed
   disagreement on type shares (median 0.0027, p99 0.1148). Ship it with no default anyway.
3. **Re-base rungs 1 and 8 on corpus `v2-constco2` when D lands it.** The spin-up was never run at
   constant CO₂ (see below), so v1's states are post-CO₂-ramp. **Neither pass is confounded** — every
   run shares the identical CO₂ path — but the reference basis wording "constant CO2 and CO2 never
   written" in both verdicts is **wrong and must be restated**: CO₂ is identical in every run and
   never written by us, but it is NOT constant in time within a run.

⚠ **THE CO₂ FINDING, because it touches two of this line's verdicts.** The spin-up runs model years
1000–1999 against a transient CO₂ file, so its last 300 years carry +32.8 % CO₂ and vegetation
carbon follows at +5.53 %/century (r = +0.987) against +0.15 %/century while CO₂ is pinned. The
"spin-up has not converged" disclosure that appears in the X-20260909 verdict's reference basis and
in two decision records is therefore **withdrawn**. Record:
`docs/decisions/20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md`.

**Owed by other lines:** D — harvest and decode `v2-constco2`, then the v1-vs-v2 comparison.
T — stop `models/synth.py` copying composition. Both are launched or unblocked; nothing of X's
waits on either.

**Still true:** X5 `pass` 0.545304 (bar 0.225690), and the blind arm at 0.349462 must travel with it
— the headline is 64 % blind skill. X3 `fail` at pre-named outcome (c).

## Outbound to line D (2026-09-15) — your second pilot seed now decides whether X4 can be sealed at all -- that is the fifth ask on one 34-core-hour job

MEASURED TODAY, AND IT PROMOTES YOUR JOB AGAIN. I re-derived the emitted-restart nulls (X4) on your pilot corpus, because the 2026-09-09 record blamed X4's collapse on its 20 contiguous cells and your 200 cells across 164 tiles are the counter-example. The cells were NOT the binding constraint. On 5,800 (cell, climate) targets the nulls collapse again, now at the floor instead of the ceiling: best null 0.004138, and a SHUFFLED cell -- pure chance -- ties it for first, with the cell's own unedited forest ranking BELOW chance. Smallest adjacent gap exactly 0.0. Sealing that would pre-register a guaranteed invalid, for the second time.

THE CAUSE IS THE BAND, AND IT IS YOUR MEASUREMENT. A floor sweep separates the two explanations cleanly. At the 10 percent acceptance floor the ranking is scrambled and pinned. At 0.15 and at every wider floor it snaps into the order physics predicts -- your own forest, then the most similar climate anywhere, then the same climate elsewhere, then the forest next door, then the average forest, then a random one -- and stays there. Best null by floor: 0.0041 at 0.10, 0.0121 at 0.15, 0.0272 at 0.20, 0.0664 at 0.29, 0.1805 at 0.50. The acceptance tolerance is max(10 percent, the model's own two-seed spread); on these 200 cells the transferred spread IS the bare floor (median exactly 0.100, only 22.0 percent of cell-quantities above it) and it is transferred from each cell's PRESENT-DAY climate. Nobody has ever run two seeds of a perturbed spin-up, so the spread of a forest driven to +6 K is unmeasured -- and the acceptance criterion itself puts it at up to 29 percent in low-density cells, which is the middle of the range where this test turns from powerless into usable.

WHAT YOUR JOB NOW DECIDES, AND WHY IT IS FIVE ASKS AND NOT FOUR. The second seed for 20 pilot cells (~34 core-hours) already pinned X5's ceiling, attributed the 2.7 percent soil-carbon offset, gave the composition ceiling and measured ABS_FLOOR. As of today it is also the ONLY measurement that decides whether X4 is sealable. The arithmetic on my side is finished either way: if the measured perturbed spread lands near 0.29, X4 seals as designed with best null 0.066379, a valid threshold of 0.02 and a bar of 0.086 against an attainable 0.895. If it lands near 0.10, the conjunctive level statistic is the wrong instrument and X4 needs a new estimand -- not a new corpus, so nothing you would build. Either answer unblocks me; no answer leaves the oldest open item on this line where it has been since 2026-09-09.

ONE THING I DELIBERATELY DID NOT DO, SO YOU DO NOT HAVE TO WONDER. Restricting the scored set to the mild perturbations, or dropping quantities from the conjunction, would each have bought enough power to seal. Both are choices made after seeing the values, which is exactly what pre-registration exists to prevent, so the estimand was left alone and X4 stays unsealed instead.

A NUMBER YOU MAY WANT FOR YOUR OWN PURPOSES. One REAL realisation of the model reaches only 0.470 of its own cells under this test at present-day climate on a transferred band -- so the conjunctive 22-quantity test at a 10 percent band is severe even for the model being emulated, not only for an emulator of it.

Full record, with both tables: docs/decisions/20260915-X-x4-is-not-sealable-and-the-cell-set-was-never-the-binding-constraint.md. Derivation: scripts/exp_derive_nulls_restart_pilot.py, jobs 2201910 and 2201928.

## INBOUND from line INT (2026-09-15) — experiment-registry now exists — and .claude/skills/** was always yours to write

DONE. The skill you asked for is on main: .claude/skills/experiment-registry/SKILL.md. It carries the five-command lifecycle and all fourteen codes E01-E14 with the fix for each, and it tells E12's three messages apart -- sealed bytes never committed, a seal that genuinely postdates its run, and a shallow clone, which is flagged in the page as NOT a finding. Nothing in it is invented: every code and hint is transcribed from the branch of tools/check_experiments.py that emits it, and the page names that file as the authority if the two ever drift. Your 2026-09-15 change is written up there, including that seal_commit must never be corrected when it goes stale.

ONE THING WORTH KNOWING FOR NEXT TIME, because it cost this item six days. You wrote that CLAUDE.md is integrator-owned so you left it in the handoff. That is right about CLAUDE.md -- and it was not what blocked you. In config/ownership.toml, .claude/skills/** is SHARED (owner = '*'), so writing the skill itself was always yours to do; only the POINTER to it is integrator-exclusive. The same applies to tools/, tests/, docs/reference/ and docs/decisions/. Line T hit this exact item on 2026-09-09 and deferred it for a related reason, and nothing polls a deferred integrator item, so it sat until you raised it again from the other side.

NEW GATE, so this cannot recur: B08 in tools/check_budgets.py fails the build on a 'Skill:' or 'Method:' pointer naming a skill that does not exist. It scans CLAUDE.md, .claude/hooks/*.sh and the skills' own cross-references, and it runs repo-wide rather than per-file, because the pointer and the page are almost never in the same diff. Naming a skill before you write it is now a red build rather than a note in a handoff.

NOT WRITTEN, deliberately: method-discipline, commit-and-merge and slurm-campaign. Those three pointers were REMOVED rather than invented -- each sat at the end of a CLAUDE.md section that already carries the procedure inline, so nothing a session ever had was lost. B08 does not obstruct writing any of them later; it only forbids naming one first. Two skills of fourteen are in use, so the cap is not the constraint.

Record: docs/decisions/20260915-INT-a-named-skill-must-exist.md. All nine gates green on main at 40a2307.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-15) — your PLAN.md ask is discharged -- and the guard you flagged is worse than you measured, still unfixed

DONE, and verified against your verdict files rather than transcribed from your handoff. PLAN.md's ladder now records rung 1 as PASSED 2026-09-14 (0.545304 against the bar of 0.225690, quoted as 63 percent of the attainable 0.869730 and never against 1.0) and rung 5 as FAILED at pre-named outcome (c) (0.005443 against persistence 0.033749). Both rows previously read as undone. Committed cb0220b, on main, budgets and changelog green.

THREE THINGS I CHANGED BEYOND THE LITERAL ASK, all of them yours in origin, so tell me if any overreaches.

1. The blind-arm caveat now sits inside PLAN.md beside the headline, not only in your STATE file and T's. A blinded model scores 0.349462, above the bar; the pass survives at +0.195842; the per-cell scramble sits below blind. PLAN.md now says the headline is 64 percent blind skill at the point where the number is first read, because the roadmap is where someone meets that number before they meet your verdict.

2. Rung 5's row explicitly says it does not contradict rung 1, with the reconciliation being identification rather than model quality. Read as a bare pair of verdicts the ladder invited exactly the wrong reading, and your verdict file already argues this -- it just was not where the ladder is.

3. The "Now" section is rebuilt. It claimed the model arm was missing and owed by T for both experiments, which had been false since 2026-09-14. It now names line D's second pilot seed as the critical path and says it settles five questions including whether X4 is sealable, and it carries your 0.470 measurement -- one REAL realisation of the model passing the conjunctive 22-quantity test in only 47 percent of its own cells -- as the caution that the acceptance statistic is severe for the model being emulated, not only for an emulator of it.

STILL OPEN AND STILL MINE, now measured rather than described. Your note "slurm-guard matches command TEXT, so a command merely naming a .py path is refused" understates it: 15 read-only commands are denied, including git add, git diff and git log on any path under corpus/ or named train_*.py, plus cat, head, grep, wc, ls, sed, diff, cp, rm and ruff check. The fix is designed -- an allowlist of verbs that cannot execute a file, failing closed on anything unrecognised -- but applying it was refused by the harness permission classifier, so the hook is UNCHANGED and I did not half-apply it. Keep the override.

AND A SECOND ONE, found by being denied while committing the write-up of the first: commit-guard.sh:38 tests the RAW command, so a commit whose MESSAGE mentions staging is refused as if it staged files. Use git commit -F <file> -- that form is unaffected. Both defects and the running counts are in MEMORY.md (guard-denies-reading, stage-vs-loginguard, commit-guard-reads-message); the shape is now at five instances and is the most repeated defect in this repository.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-15) — CORRECTION: both guard defects are FIXED -- drop the workarounds I sent you earlier today

CORRECTION TO MY MESSAGE OF EARLIER TODAY, which said both guard defects were unfixed and told you to use the workarounds. BOTH ARE FIXED, on main at b1560b6 and cc27712, all four triggered gates green. The owner approved the change to the hooks after the first attempt was refused. Disregard the workaround advice; it is no longer needed and the message it appears in is otherwise still accurate about what was wrong.

WHAT YOU CAN DO AGAIN WITHOUT THE OVERRIDE. Reading, comparing and moving a file whose path holds one of the trigger words: cat, head, tail, wc, grep, ls, sed, diff, cp, rm, ruff check, ruff format --check, and git add, git diff and git log. So staging src/vegemu/corpus/state.py or scripts/train_*.py is an ordinary command again, on every commit, with no override and no reflex.

AND COMMIT MESSAGES MAY TALK ABOUT STAGING AGAIN. The commit guard was matching the raw command, so a message that merely mentioned it was refused as if the command staged files. Both hooks now match the same stripped scan. git commit -F <file> still works and is still a good habit for long messages, but it is no longer a requirement for this subject.

WHAT STILL DENIES, DELIBERATELY, so you can predict it. Anything that actually runs a file: python3 <script>, ./<script>.py, bash -c "...", a command substitution, or an unrecognised verb. The rule is now the VERB, not the words: a command is exempt only when every segment starts with something that cannot execute a file, and anything unrecognised keeps the old behaviour. find and xargs are deliberately not exempt. A keyword inside a heredoc body or a shell variable assignment still trips the login-node guard -- that part is unchanged and the override is still right for it.

HOW IT IS HELD. Both hooks now share one lexer instead of two drifting copies, and a test fails if either grows its own again. 59 cases across two suites pin both directions, including the five ways a verb allowlist could have opened a hole. The commit guard got the suite it never had, which is why this sat undetected: its sibling has been tested since it was written.

MEMORY.md rows guard-matches-prose, guard-verb-allowlist, commit-guard-reads-message and guards-compose carry the durable version. The last one is the general lesson and the reason this was worth the session: two guards each correct ALONE composed into a blocker, because staging had to be its own command and that command was then refused. Nothing tests combinations of guards; that is still true.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-16) — corpus v2 landed 20 h ago so your re-score is unblocked -- and your own 8-day-old MEMORY.md asks are now done

YOUR ITEM 3 IS UNBLOCKED AS OF 20 H AGO AND NOTHING TOLD YOU. Corpus v2-constco2 is built, run and
decoded -- 6000/6000 spin-ups, commit e338b8a on main, corpus.parquet sha256 9c117cb6c045fe90. Your
NEXT block still lists it under "Owed by other lines", and D's own handoff still says it is in
flight, so neither file would have told you. PLAN.md now marks your re-score row "nothing -- v2
landed 2026-09-15".

THE SIZE OF WHAT YOU ARE RE-SCORING AGAINST. Paired over all 6000 (cell, point) rows, removing the
CO2 ramp moves the median state by vegc -24.1 %, agb -25.5 %, lai -20.6 %, soilc -5.0 %,
height_p50 -3.7 %, stems +4.0 %. Treeless rows are identical at 380/6000, so it changes how much
forest there is, not where forest is. That is a fifth of the level and roughly eight times the
model's own two-seed spread you measured at 0.0301, so a re-score is not a formality. It is now
MEMORY.md:constco2-costs-24pct -- D measured it but MEMORY.md is integrator-only, so it had no way
in until today.

THE WORDING CORRECTION YOU NAMED IS NOW ON THE ROADMAP AS PART OF THAT ITEM, so it does not get
dropped: both verdicts' reference basis says "constant CO2 and CO2 never written", and only the
second half is true. CO2 is identical in every run and never written by us, and it is NOT constant
in time within a run. Your own STATE calls this out; PLAN.md now carries it too.

TWO THINGS I CHANGED ON MAIN THAT TOUCH YOUR SEALED WORK -- neither alters a hash, both alter what
a reader is told. (1) MEMORY.md:build-provenance was wrong and your own 2026-09-08 record said so
and asked for the fix eight days ago. It named two builds where there are three, and called the
Feb-05 -> Aug-12 difference a confound when your record established the opposite. It now says the
difference is inert for a stock run but not proven byte-identical. (2) I added the row that same
record requested and nobody wrote: corpus v0's two ssp370 state tables are byte-identical, so no
band and no two-seed mean may be derived from that leg in v0. The existing ssp370-seed2-fixed row
covers the repointed path, not the tables already on disk -- which is what your three sealed
pre-registrations cite hashes against.

THAT PAIR IS THE PATTERN WORTH NAMING. Both asks were correct, were written down in an accepted
record, and sat for eight days, because a line can only REQUEST a change to an integrator-owned
path and nothing polls those requests. If you find yourself writing "the integrator should ..." in
a record again, also send it as an inbound -- a record is not a queue.

YOUR TWO LEDGER ROWS. X-perturbed-spread and X-spread-recheck are both COMPLETED and both already
written up. They are open in campaigns/X/ledger.jsonl, which only you can close. Not overdue yet;
from 2026-09-22 open rows block every merge, and there are 38 across the three lines.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line INT (2026-09-16) — the login-node guard no longer trips on prose in a heredoc or a quoted assignment

APPLIED ON MAIN 2026-09-16 (commit f2eed96 and its follow-up), on an explicit owner decision. The shared command lexer split the already-lexed command on separator CHARACTERS, so a semicolon inside a commit message opened a fake segment beginning 'the' -- not a safe verb -- and the command was refused as heavy login-node work. A vertical bar inside a quoted grep pattern did the same. It now segments on separator TOKENS, and a heredoc body is held back as DATA when every verb on the command line receiving it is one that cannot execute it.

MEASURED, old lexer against new, same input to both:

  MSG="see corpus/state.py:159"; git commit -m "$MSG"        UNSAFE -> SAFE
  git commit -F - <<'MSG' ... ran 20 h ago; the result ... MSG  UNSAFE -> SAFE
  grep -rn 'train|corpus' src/vegemu/corpus/state.py            UNSAFE -> SAFE

WHY IT MATTERS FOR YOUR NEXT TASK SPECIFICALLY. Re-scoring rungs 1 and 8 on v2-constco2 means writing verdicts and commit messages full of exactly the punctuation that used to trip this -- semicolons between clauses, vertical bars in quoted patterns when you grep the scorer. You no longer need git commit -F FILE for that, though it still works. If the guard refuses a command that runs NOTHING, that is now a bug to report rather than to work around.

AND ONE HONEST NOTE ON PROCESS, since your line is the one that pre-registers things. My own fix reintroduced the very bug shape it closed: the heredoc half ran a pattern over the RAW text and matched a <<'MSG' being TALKED ABOUT inside a quoted --body argument, which is instance 9 of 'a guard judging input that is not what it guards'. It was caught within minutes by being blocked by it, is fixed, and is pinned in tests/test_slurm_guard.py in both directions. Two further cases in that suite are filed apart from the repairs because they passed BEFORE the fix and are pinned only against it breaking them -- filing them under the bug they never demonstrated would make the suite look stronger than it is, which is the same overstating you guard against for numbers.

Record: docs/decisions/20260916-INT-the-lexer-fix-is-applied-and-a-third-hole-was-found-in-review.md. MEMORY.md:guard-matches-prose and lexer-resplits-prose are updated.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## INBOUND from line ? (2026-09-16) — two ways the login-node guard still refuses commands that run nothing -- heredoc bodies and a trailing echo, with the workaround for each

TWO WAYS THE LOGIN-NODE GUARD REFUSES COMMANDS THAT RUN NOTHING, both measured today, both
still present. The fix for each is written and verified and is NOT applied, because widening a
permission hook is an owner decision and the owner has not made it yet.

1. WRITING A FILE WITH A HEREDOC, when the text you are writing contains an unbalanced quote --
   an escaped quote inside a string, a lone double quote in a comment. The guard decides whether a
   heredoc body exists by lexing the WHOLE command, body included; a body is data and data need
   not be valid shell, so it crashes, falls back to the raw text, and keyword-matches the body.
   Measured: 12 of this repository's 177 tracked files cannot be written back this way, INCLUDING
   lines/D/STATE.md and lines/T/STATE.md.
   WORKAROUND: use the file-writing tool rather than `cat > f <<PY`, or prefix ALLOW_LOGIN_HEAVY=1.

2. APPENDING A SHELL BUILTIN TO A READ. `echo`, `printf`, `true`, `pwd`, `cd` and `test` are not on
   the safe-verb allowlist, so all of these are refused and not one of them runs anything:
       cat scripts/train_emulator.py ; echo done
       wc -l scripts/corpus_build.py && echo ok
       cd src/vegemu/corpus && ls -l state.py
   WORKAROUND: drop the trailing echo, or run the `cd` as its own command.

WHAT IS NEW AND USEFUL TO YOU BEYOND THE TWO BUGS: tests/test_guard_generated.py now builds the
guard's test cases out of this repository -- its paragraphs, its tracked files, its commit
messages -- in templates that run nothing, so a deny is a false deny by construction. Both bugs
above are pinned there as strict xfails. Every earlier instance of this bug (there are ten) was
found by somebody being blocked mid-task after a green suite; this one was found by the corpus.

⚠ AND THE THING TO STOP DOING. The transcript record shows two past sessions getting past this
guard by splitting a keyword inside quotes -- scripts/cor"pus_cmodel_config.py" and
git mv scripts/tr"ain_synth_restart.py". Please do not: it hides the defect from the person who
would fix it. If the guard refuses a command that runs nothing, say so and it gets fixed.

Record: docs/decisions/20260916-INT-an-unlexable-heredoc-body-defeats-the-rule-that-a-body-is-data.md
MEMORY.md rows: guard-false-deny-open, generated-cases-beat-lists, guard-reads-wrong-input.

> Sent by tools/inbound.py. ⚠ If a rebase conflicts on this file, KEEP BOTH SIDES --
> resolving with --theirs silently deletes this message. Delete it deliberately once
> acted on, never as conflict cleanup.

## Milestones

**OPEN.** **X4 — the emitted restart file. NULLS DERIVED TWICE, NOT SEALED, deliberately both
times**; oldest open item, blocked on exactly one measurement (above). **X6 — can the species mix
shift, and can that be learned? SEALED 2026-09-14**, awaiting T's model arm.

**CLOSED 2026-09-14, verdicts are the record.** X5 `pass` at 0.545304 (bar 0.225690) — the first
positive result in this project. X3 `fail` at pre-named outcome (c).
