# 20260902-INT — the agent operating system: no invariant is expressed only in prose

* **Status:** accepted
* **Line:** integrator
* **Context:** the bootstrap of `vegemu`, replacing the retired `esm_land_emulator`

## The decision

Every invariant in this repository has (a) a triggering **event**, (b) a **visibility** mechanism, and
(c) a **failing gate**. Nothing is expressed only as prose in a document that a session is asked to
read and honour.

## Why — this is measured, not a preference

The predecessor ran 887 commits in 34 days, almost entirely agent-authored. The pattern across it is
unambiguous:

**Every rule that was prose was violated.**

| the rule | what happened |
|---|---|
| "MEMORY.md is capped at 400 lines" — stated in MEMORY.md's own header | reached 647 lines (+62 %) |
| the always-loaded runbook holds only the essentials | reached 1,255 lines |
| "STATE.md is durable state, not narrative" | one line's reached 3,924 lines |
| "the integrator collates changelog fragments at an integration point" | 56 fragments sat 13 days; nothing ever convened an integration point, because each line merges itself |
| "anything over a few seconds goes to SLURM" | violated until a deny hook existed |
| "opt-in, default byte-identical" | three flags with known-wrong defaults sat unflipped for weeks, one already measured correct |
| "report the null beside the number" | five headline claims died to adversarial review for exactly this |
| a consolidation procedure existed for the doc caps | never ran, because nothing made it run |

**Every rule that was a deny hook or a CI gate held.** The login-node guard held. The changelog gate,
once it existed, held. That asymmetry is the entire design input.

The generalised lesson the predecessor itself drew, from the changelog rot, is the one worth keeping:
**an owned chore with no triggering event and no visibility mechanism silently rots.** This record
applies that to the whole protocol rather than to one chore.

## What follows from it

**Document budgets** (`config/budgets.toml`) are enforced three ways, deliberately redundantly,
because one layer of *asking* is zero layers: a warning at each edit that prints the headroom, a
**denied commit** at the limit, and a CI gate. Rotation is mechanical (`tools/rotate_*.py`), not a
judgement call — the predecessor's caps failed partly because compaction required an essay rewrite.
Onboarding is 180 + 120 + 150 lines against up to 5,800 before.

**MEMORY.md's row format is checked**, so the file cannot become a narrative. Shape, not just size.

**Raising a budget requires an owner-approval trailer.** Without this the scheme is circular: the
agent bound by a cap can edit the cap.

**Claims are mechanised** (`experiments/`). A pre-registration is sealed, hashed, recorded in an
append-only ledger, and its hash is stamped into the job by the launcher — which refuses to submit
anything unsealed. The verdict's metrics table is generated and diffed by CI, so a number and its
nulls are in the same table by construction and the pass/fail line is computed rather than typed.
Fourteen error codes; the load-bearing one is **E08: any null that itself satisfies the pass
threshold means the estimand has no power, and the verdict is `invalid`**. Fed the predecessor's real
numbers — 0.9824 against a persistence null of 0.9622 — the gate returns `invalid`.

**Long jobs cannot be lost** (`campaigns/`). Results arrive hours to days after the launching session
ends, so the launch row is written by the submission wrapper itself, raw `sbatch` is denied so there
is no path around it, a login-node timer appends liveness, and every session start replays the open
campaigns. Liveness comes from `sacct` CPU time, never log length, because Python block-buffers to a
file and a healthy job's log is empty.

**The handoff is enforced at the event.** A `Stop` hook blocks once if a session committed work
without refreshing its `## NEXT` block, and a `PreCompact` hook warns at the other place handoffs were
lost. The predecessor asked twice, politely, in two documents; a session that runs out of context
reads neither.

**The infinite-poll trap is closed mechanically.** Path-filtered CI is right, but a skipped workflow
reports *no status at all*, so "wait for check X" hangs forever on a prose commit — which is most
commits. `.github/gates.toml` is the single source of truth, `tools/check_gates.py` fails if a
workflow drifts from it, and `tools/expected_gates.py` computes the poll list from the actual diff.

## What was deliberately deleted

* **the ADR number-block allocation scheme** — four tiers × five lines, ~35 lines of index
  bookkeeping, three exhausted blocks, and a self-allocation rule, all to stop two lines picking the
  same number. A `<date>-<line>-<slug>` filename does that for free.
* **the fifteen-row prose ownership map** — replaced by six machine-read rules with `unowned = deny`.
  The map grew to fifteen rows *because* nothing enforced it and ~60 % of the source was unowned;
  denying on an unowned path forces a rule at the first write, so the map stays short and stays true.
* **seven partially-superseding root planning documents** (~1,584 lines) — one `PLAN.md`, with a
  root-level allowlist in CI so a new one is a red build rather than a judgement call.
* **the declared-but-unused data-versioning tool** — the predecessor's ignore file claimed data was
  versioned through it; there was no metadata and no pointer for the repo's entire life. Provenance
  here is a per-shard `provenance.json` plus the corpus manifest hash a pre-registration cites.
* **the Julia test/format/docs/registry gates** — the language rationale (automatic differentiation,
  ESM coupling) died with the hybrid design.

## What was carried forward unchanged, because it worked

Branch-per-line in separate git worktrees (the rationale is mechanical: two sessions in one checkout
destroy each other via untracked litter git never warns about). **Per-line files, never per-line
sections of a shared file** — the single most reliable structural lesson, now extended to the ledgers
and the journals. The `## NEXT` handoff replayed verbatim at session start, with line identity
resolved from the launch directory so nobody has to state it. Self-locating SLURM wrappers with a
greppable `=== JOB DONE ===` sentinel. The changelog-fragment pattern. Decision records as an
immutable trail. The skill system with its capture prompt and usage log — now capped at 14 skills and
2,000 lines, with depth pushed into `references/` loaded on demand; the predecessor's 9,324 lines of
skills were valuable content in the wrong place.

## Verification

Every gate was proven red-then-green against a deliberately bad fixture before being trusted:
B01 B02 B04 P01 P02 P03 P04 S01 O01 O02 O04 G03 E03 E04 E06 E08 E09 E11 F02, plus a
no-false-positive check on the secret scanner and on the path checker's line marker.

The operating system's own acceptance test passed on a real compute node: a job submitted through the
wrapper ran, forwarded its environment, propagated its line identity, emitted its sentinel and wrote
its ledger row; the sweeper probed it; and a **new** session's start hook surfaced it with liveness,
its harvest command and a push-inbox note.

⚠ Two of the bugs found during that verification are recorded in the code because they are the same
class of defect the gates exist to catch: the append-only checker **silently passed** when
`origin/main` did not resolve, so the test meant to prove it proved nothing; and the owner-approval
guard fired on every clean full-repo run, and a gate that cries wolf gets bypassed. **An unverified
gate is a claim, not a gate** — the first attempt at the verification above was itself vacuous,
because the probe files were untracked and the checkers only walk tracked files.
