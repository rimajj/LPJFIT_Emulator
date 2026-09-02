# Line T — training: models, GPU, inference

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/T/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py T` when it fills.

## Scope

Everything that learns or predicts:

* `src/vegemu/models/`, `src/vegemu/train/`, `scripts/train_*.py`, `scripts/sbatch_train.sh`
* the state-synthesis side of the restart file: given a predicted roster and soil carbon, fill in
  what is DERIVED (per-tree carbon pools from the pipe model, the climate buffer straight from the
  forcing, the sapling pool from the roster) — line D owns the *bytes*, line T owns the *content*
* inference: turning a climate summary into a state, and a state into an emitted restart file

Not line T's: the binary formats and the corpus (D), pre-registrations and verdicts (X).

## NEXT — start here

**You are blocked on line D's rung 0 (the restart round-trip) and on the pilot corpus. Do not start
building a model against data that does not exist yet.** What is genuinely useful now, in order:

**1. Read the two documents that decide the architecture, and write down what they imply.**
`docs/reference/inherited.md` — especially §2 (the identification limit), §3 (the one piece of
positive evidence, which is for *our* estimand), and §4's paragraph on the per-tree bad-years
counter. Then `PLAN.md`'s model-class section. The load-bearing constraints:

* the target is a **joint distribution over a variable-length roster** in
  (trait × size × age × growth-failure-class) space, not a per-cell mean;
* the correct target is the **ensemble expectation/distribution**, because ~2.4 % of next-year count
  variance is the model's own per-patch Bernoulli noise and a single-draw R² barely discriminates
  arms — so no arm may be guarded on an R² floor alone;
* a state summary that averages away the per-tree bad-years counter **reverses the trait-selection
  sign in 3–4 of the 7 tree types**. Whatever you build must be able to carry it, and it is exactly
  recoverable from the printed table by algebra, so labels for it exist today.

**2. Write the baseline that can pass rung 1 cheaply.** Start with the size-structured distribution
head (integral-projection style: a learned kernel over size and trait plus a recruitment boundary
term) rather than the set network. Reasons: it is interpretable, it is the canonical published form
of exactly this question, and rung 1 is a *kill test* — it needs the cheapest honest model, not the
best one. The permutation-equivariant set network with a stochastic per-tree head (binomial-survival
/ Poisson-birth, conservative by construction) is the target architecture, not the first one.

**3. Set up the GPU path and prove it, before you need it.** `scripts/sbatch_train.sh` does not exist
yet — write it as a sibling of `scripts/sbatch_py.sh` (copy its four traps verbatim: self-location,
the env-forward list and its mirror trap, the `/tmp` refusal, the partition envelope) plus
`--gres=gpu:1` and a `gpu*` QOS. Checkpoint to `/p/tmp/jamirp/vegemu/models` every N steps: a job that
dies mid-epoch must not lose the run. Then submit a two-minute job that just prints the visible
device, so the path is proven while it is cheap to debug.

⚠ Anything you score is an experiment and needs a sealed pre-registration first — the launcher
refuses without `--exp`, and the slurm guard denies a training submission that omits it. That is
deliberate: five of the predecessor's headline claims died to a missing null.

Housekeeping: none owed. Refresh this block before you end.

## Milestones

**T0 — read the constraints, write the baseline spec (OPEN).** No code required. Output: a short
design note in `journal/T/` naming the estimand, the state content, and what the baseline cannot do.

**T1 — the GPU launch path (OPEN, independent of D).** `scripts/sbatch_train.sh` + a proven
two-minute job. Do this early; it is the only thing here not blocked on the corpus.

**T2 — the rung-1 baseline (blocked on D2, the pilot corpus).** Predict per-cell equilibrium tree
count and trait medians from a climate summary. Its job is to be beaten by, or to beat, the
same-cell-baseline null — nothing more.

**T3 — the roster model (blocked on T2).** The set network with a stochastic per-tree head.

**T4 — state synthesis (blocked on D0 + T3).** Fill a template restart with a predicted roster; the
classification of every field into learned / derived / copied / relaxed / free is in `PLAN.md`.

## Line T gotchas

*(none yet)*
