---
name: experiment-registry
description: The experiment lifecycle and every gate code E01–E14 with its fix — pre-register, seal, run, append, render a verdict. Use whenever `tools/check_experiments.py` or the `experiments` CI gate reports a code, when `slurm-guard` denies a submission for having no `--exp`, when `seal_experiment.py` refuses to seal, when a verdict says `invalid` rather than `fail`, or before writing a new `preregistration.yaml`.
---

# The experiment registry

The scientific gate. `tools/check_experiments.py` is the authority; this page is the map from the
code it prints to the thing you should do. **Every code below is emitted by real branches in that
file** — if you hit one that is not here, the file changed and this page did not: fix this page.

## The lifecycle — five commands, in this order

```bash
cp -r experiments/_template experiments/<L>-$(date +%Y%m%d)-<slug>
$EDITOR experiments/<id>/preregistration.yaml     # status: draft
tools/seal_experiment.py <id>                     # validates, hashes, appends the registry row, commits
scripts/sbatch_py.sh --exp <id> <tag> <script.py> # refuses unless sealed AND committed AND hash matches
tools/append_result.py --exp <id> --from <metrics.json>
tools/render_verdict.py <id>                      # the metrics block is GENERATED, never typed
```

The order is the whole point: sealing writes a hash, the launcher stamps that hash into the job, and
the result row carries it back. That is what makes "pre-registered" a fact rather than a promise.

**A sealed pre-registration is immutable.** A changed question is a NEW `exp_id` carrying
`supersedes:` — never an edit. Editing after the run is exactly what E03/E04 exist to catch.

## The codes

### Writing the pre-registration — E01, E02, E14

| Code | What it says | The fix |
|---|---|---|
| **E01** | a required key is missing, an enum is unknown, `exp_id` ≠ directory name, `pass_if` unparseable, or `decision_rule.statistic` ≠ `estimand.name` | fill the key. For the statistic mismatch: *a pre-registered threshold on a different statistic is not a pre-registered verdict* — make them the same name. `pass_if` must be `> 0.02`, `>= 0.5`, `< 0.1` or `abs < 0.1`; a decision rule must not be arbitrary code |
| **E02** | `nulls` is empty, or a null lacks `expected.value` / `expected.tolerance` / `expected.derivation` | declare at least one null and **derive what it must return before the run**. A null that silently returned the wrong value is indistinguishable from one that agreed with you. This is invariant 1, mechanised |
| **E14** | `estimand.reference_basis` or `data.leakage_checks` is empty | name the reference source, leg, years, PFT set, patch count and binary build; and name the leakage checks you actually ran. Cross-validation by cell holds out **space, not time**, so a lagged-truth feature makes the score teacher-forced and the gate cannot see that for you |

### The seal — E03, E04, E13

| Code | What it says | The fix |
|---|---|---|
| **E03** | has results but is not sealed; or sealed but absent from `registry.jsonl`; or the live file's hash ≠ the sealed hash | seal *before* you run. Seal via `tools/seal_experiment.py`, which appends the ledger row — never flip `status:` by hand. If the live hash moved, you edited a sealed file: restore it, and raise a new `exp_id` with `supersedes:` |
| **E04** | a result row's `prereg_sha256` ≠ the sealed hash | **the pre-registration was edited after the run.** The job stamped the hash it actually ran under, and the two no longer agree. The result stands; the file moved under it. Restore the sealed bytes |
| **E13** | sealed >30 days with no results and no recorded abandonment; **or** abandoned and then produced results anyway | harvest it, or run `tools/abandon_experiment.py <id> --reason '<why>'`. An unfinished experiment with no reason is the shape of a chore that rots — this is the gate that refuses to let it. ⚠ **Do NOT write `abandoned:` into a sealed file** — see below |

#### Where an abandonment is recorded, and why it is not in the pre-registration

**A sealed experiment is abandoned by appending to the registry, never by editing the file:**

```bash
tools/abandon_experiment.py <exp_id> --reason "superseded by <new id>; nothing ran"
```

E13's remedy used to be "add `abandoned: <reason>`" to the pre-registration. **That could not be
done**: E03 hashes the sealed bytes, so adding the key trips E03, and the remedy was available only
for a *draft* — the one state in which E13 can never fire, because E13 keys off `sealed_at`. The
remedy and the condition were disjoint by construction, and a gate whose remedy is impossible is a
gate people learn to route around.

So the reason goes where every other correction here goes: an appended row on an append-only ledger,
written by a tool. The sealed bytes stay genuinely immutable and E03 is untouched. The rejected
alternative was to exempt an `abandoned:` block from the E03 hash — *"immutable except for one key"*
is a rule with an exception parsed by the code that enforces the rule, which is what E03 exists to
catch. Record: `docs/decisions/20260921-INT-a-sealed-experiment-cannot-be-marked-abandoned-*.md`.

`abandoned:` **inside the pre-registration is still honoured**, and is still right for a draft, or
for a file that carried the key before it was sealed. It is only unreachable *after* sealing.

⚠ **Abandoning is not a way to close something that ran.** A finished experiment is closed with a
verdict; the tool refuses, and E13 reports the contradiction if the rows appear later.

### Results and the verdict — E05 ... E10

| Code | What it says | The fix |
|---|---|---|
| **E05** | a result row reports a statistic that is not the blessed one | only the pre-registered estimand may be reported. Anything else is a different question — give it its own `exp_id` |
| **E06** | a `model`-arm row's `nulls` object omits a declared null | **a reported number with no null.** Every declared null must appear beside the model's value, in the same row. Re-run the missing null arm; do not drop the declaration |
| **E07** | a null returned a value outside its pre-registered `value ± tolerance` | the apparatus did not do what you declared it would. The verdict is **`invalid`, not `fail`** — you have not measured the thing yet. Fix the apparatus and re-run |
| **E08** | a null arm also satisfies `pass_if` | **the estimand has no power.** Your metric cannot tell the model from the null, so its verdict is `invalid` whatever the model scored. Invariant 3: this is never a `pass`. Change the statistic or the basis |
| **E09** | `verdict.md`'s `outcome:` disagrees with the checker's evaluation | the outcome is **computed, never typed**. Run `tools/render_verdict.py <id>` and record what it says |
| **E10** | `verdict.md` exists with zero result rows, or its generated metrics block is missing/stale | harvest first — a verdict on no data is an opinion. Then `tools/render_verdict.py <id>`, so the number and its null land in the same table by construction rather than by discipline |

### The ledgers — E11, E12

| Code | What it says | The fix |
|---|---|---|
| **E11** | `registry.jsonl` or a `result.jsonl` changed non-append-only versus the merge base, or was deleted | results and seals are an immutable record. **Append a correction row; never rewrite history** |
| **E12** | the sealed pre-registration bytes do not appear in history before the first result row | see below — this one changed on 2026-09-15 and the failure modes are worth knowing apart |

## E12 in detail — it resolves the seal by CONTENT

**Changed 2026-09-15.** E12 asks one question: *did the exact sealed bytes exist in committed
history before the run they govern?* It answers it by finding the earliest commit whose
`preregistration.yaml` hashes to the recorded `prereg_sha256`, and testing that commit for ancestry
against the first result-bearing commit.

⚠ **`seal_commit` is no longer read by any check.** It used to be, and that was the bug: `CLAUDE.md`
requires `git pull --rebase origin main` before merging, a rebase rewrites every not-yet-merged
commit on the line, and so an experiment sealed and merged in one session **always** ends up with a
`seal_commit` naming an object on no branch. Ancestry of an orphan is false for everything, so the
gate fired on three correctly sealed experiments in a single session and each was silenced by
appending a correction row to an append-only ledger. A real integrity gate that cries wolf is one
people learn to route around — the workaround was the bug, not the symptom.

✅ **So: never "correct" a stale `seal_commit`, and never edit a registry row to chase it.** It
stays as a breadcrumb. `tools/seal_experiment.py` says the same thing in its own docstring.

**This is stricter than what it replaced, not a relaxation.** The old check never opened the commit
it named — it proved only that *some commit id* preceded the result. The new one cannot pass unless
the sealed bytes are genuinely in history first, which means it catches a case the old one was blind
to: a pre-registration **edited after sealing** leaves no commit carrying the sealed bytes at all.

Three distinct messages, three different causes:

| Message | Cause | Fix |
|---|---|---|
| `no commit in history carries the sealed pre-registration bytes (prereg_sha256 …)` | the sealed content was never committed, **or was altered after sealing** | commit the seal; or, if it was altered, restore the sealed bytes. Check E03 first — it usually fires too and names the live/sealed hash pair |
| `the sealed pre-registration first appears in <sha>, which is not an ancestor of the first result commit <sha>` | the seal really does postdate its own run | the run happened before the question was fixed. That experiment is not pre-registered; re-seal and re-run |
| `cannot verify the seal: this is a SHALLOW clone …` | **not a finding.** The commit carrying the seal may simply not have been fetched | check out with full history (`fetch-depth: 0`). CI already does this in `.github/workflows/experiments.yml` |

That third row is the rule this repository has had to learn twice in hooks: **a checker that cannot
run must say so, never report a finding it did not measure.**

## Three things that are not errors

- **A stale `seal_commit`.** Expected after any rebase. Leave it.
- **`verdict: invalid`.** Not a failure of the model — a failure of the apparatus or the metric.
  Reporting it honestly is the point; E07 and E08 exist so the reason names itself rather than
  hiding inside the word.
- **A result that does not pass.** `fail` is a real answer. Only `invalid` means you must re-run.

## Where the rest lives

`tools/check_experiments.py` — the checker, whose module docstring lists all fourteen codes and is
the authority if this page and it ever disagree. `tools/seal_experiment.py` — sealing, and why
`seal_commit` must not be corrected. `docs/decisions/20260915-X-the-seal-check-resolves-by-content-not-by-commit-hash.md`
— the full record of the E12 change, including the before/after table of what each check catches.
