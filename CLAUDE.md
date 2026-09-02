# CLAUDE.md — `vegemu` runbook (budget: 180 lines, enforced)

**What this project is.** A purely data-driven emulator of the dynamic global vegetation model
LPJmL-FIT. Given a climate, predict the vegetation state, and emit it as (a) a byte-loadable LPJmL-FIT
restart file and (b) the model's own output files — so the model's 1000-year spin-up can be skipped and
the equilibrium forest under any climate (including warmed climates) obtained directly.
Offline only. **No** hybrid physics core, **no** ESM coupling, **no** daily fluxes, **no** year-by-year
rollout. Those belong to the retired predecessor (see `docs/reference/inherited.md`).

---

## The nine invariants

1. **No claim without its null.** Every reported skill number is accompanied, in the same table, by
   every null pre-registered for it. Enforced by the `experiments` gate, not by good intent.
2. **Pre-register before you run.** Estimand, reference basis, folds, leakage checks, and each null
   *with the value it must return*, sealed and committed before the job is submitted. The launcher
   refuses otherwise.
3. **A null that passes your threshold means your metric has no power.** The verdict is `invalid`,
   never `pass`.
4. **State the basis in the same sentence as the number** — reference source, patch count, cell count,
   scenario leg, and whether it is a level or a ratio.
5. **The tolerance is `max(10 %, the model's own two-seed spread)`.** LPJmL-FIT is stochastic; two
   identical runs differ by up to 29 % in low-density cells. A mean score is not an acceptance test —
   report the fraction of cells inside the band on the conjunctive basis.
6. **Anything over a few seconds goes to SLURM**, via a `scripts/sbatch_*.sh` wrapper. Enforced by a
   deny hook. Raw `sbatch` is denied so the campaign ledger cannot be bypassed.
7. **Round-trip before you trust a format.** A binary reader/writer is proven by writing a real file
   back byte-identically, never by assertion.
8. **The emulator does not see CO₂ and must not respond to it.** LPJmL-FIT runs constant CO₂
   deliberately. Never add a CO₂ feature, never list its absence as a defect. Standing owner decision.
9. **Capture knowledge where it belongs, at the moment it appears** — see the doc map. Every chore in
   this repo has a triggering event and a failing gate; if you find one that does not, that is a bug.

---

## Doc map — where each kind of thing is written

| Kind | Destination | Budget |
|---|---|---|
| Always-loaded runbook | `CLAUDE.md` | 180 |
| Cross-cutting durable fact | `MEMORY.md` — **one fixed-column table row**, prose is rejected | 120 |
| The roadmap / rung status | `PLAN.md` | 150 |
| Durable line state + the handoff | `lines/<L>/STATE.md`, handoff in `## NEXT — start here` | 120 / 60 |
| Session narrative | `journal/<L>/<YYYY-MM>.md` (append; **never read at session start**) | 800 |
| A decision | `docs/decisions/<YYYYMMDD>-<L>-<slug>.md`, immutable once accepted | 120 |
| An experiment | `experiments/<L>-<YYYYMMDD>-<slug>/` (see §Experiments) | 80 verdict |
| A procedure | a skill in `.claude/skills/` — prefer updating one | 200 / 2000 total / 14 max |
| Deep detail behind a skill | that skill's `references/*.md` | 400 |
| A general deep fact | `docs/reference/<topic>.md` | 300 |
| Changelog entry | a **new** `changelog.d/<L>-<slug>.md`; never edit `CHANGELOG.md` from a line | — |

`CLAUDE.md` must not contain: physics, cluster procedures, gotchas, ownership tables, or any number
that could go stale. Those go to skills and `docs/reference/`. Root-level `.md` files are allowlisted
in `config/budgets.toml` — a new one is a red build, not a judgement call.

Budgets are enforced three ways: a warning at each edit, a **denied commit** at the limit, and CI.
Raising a budget requires the trailer `Budget-change-approved-by: owner`.
Rotation is mechanical: `tools/rotate_state.py <L>`, `tools/rotate_memory.py`.

---

## Work lines

| Line | Branch · worktree | Scope |
|---|---|---|
| **D** | `line/D` · `/p/projects/open/Jamir/vg-D` | data: the binary formats, corpus generation, provenance |
| **T** | `line/T` · `/p/projects/open/Jamir/vg-T` | training: models, GPU, inference |
| **X** | `line/X` · `/p/projects/open/Jamir/vg-X` | experiments: pre-registrations, nulls, verdicts |
| — | `main` · `/p/projects/open/Jamir/vegemu` | integration only |

One session per line at a time; your line is the branch of the directory you launched in. Ownership is
`config/ownership.toml` (machine-read, `unowned = deny`) — not a prose table. The only sanctioned
cross-line write is `tools/inbound.py`.

**Per-line files, never per-line sections of a shared file.** Sections still conflict; files never do.

Before your session ends — or when context runs low — refresh `## NEXT — start here` in your line's
`STATE.md` and commit it. That block *is* the handoff; the next session's start is generated from it.
A `Stop` hook blocks once if you committed work without it.

---

## Experiments

```
experiments/<L>-<YYYYMMDD>-<slug>/
  preregistration.yaml   # draft -> sealed. Immutable once sealed; supersede with a new id.
  result.jsonl           # append-only, written by tools/append_result.py only
  verdict.md             # <=80 lines; its metrics block is GENERATED and diffed by CI
```

```bash
tools/seal_experiment.py <exp_id>       # validates, seals, hashes, appends to the registry
scripts/sbatch_py.sh --exp <exp_id> …   # refuses unless sealed + committed; stamps the hash into the job
tools/append_result.py --exp <exp_id> --from <metrics.json>
tools/render_verdict.py <exp_id>
```

Skill: `experiment-registry` (every error code E01–E14 and its fix). Method: `method-discipline`.

---

## Commit and merge

```bash
git pull --rebase origin main            # at session start, and again before merging
# work; commit (Conventional Commits, one logical change; the commit guard runs the checkers)
git push --force-with-lease origin line/<L>     # the rebase rewrites pushed commits; a plain push is rejected
tools/expected_gates.py                  # prints EXACTLY which gates this diff triggers
tools/wait_gates.py                      # polls only those; never poll a gate that will not run
tools/merge.sh <L>                       # flock'd: ff-only pull, --no-ff merge of origin/line/<L>,
                                         # collate changelog fragments, check the campaign ledger, push
```

⚠ **A skipped workflow reports no status at all, not "skipped"** — so polling for a gate that will not
run hangs forever. `expected_gates.py` computes the list from the diff; if it prints none, merge now.
Never `git switch main` in a line worktree (`main` is checked out in the integration worktree; git
refuses). Drive it with `git -C`, which `tools/merge.sh` does. Skill: `commit-and-merge`.

---

## Long jobs

Results arrive hours to days after the session that launched them has ended, so every submission is
recorded in `campaigns/<L>/ledger.jsonl` by the wrapper itself, and every session start replays the
open ones. A campaign stays open until it is harvested, declared dead, or abandoned **with a reason**;
an overdue one blocks the merge.

⚠ **Judge a silent job by `sacct` CPU time, never by its log** — Python block-buffers stdout to a
file, so a healthy job's log is empty until it exits. Cluster facts: `docs/reference/cluster.md`.
Skill: `slurm-campaign`.

---

## Before you start a task

Check whether a skill covers it and invoke it; re-deriving a procedure a skill already describes means
that skill's description is too weak — sharpen it. If a recurring task has no skill, create one
(`skill-creator`), and pay for it by merging or deleting another if the cap is reached.
