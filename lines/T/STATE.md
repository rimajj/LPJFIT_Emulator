# Line T — training: models, GPU, inference

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: `journal/T/<YYYY-MM>.md` (append; never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py T` when it fills.

## Scope

Everything that learns or predicts: `src/vegemu/models/`, `scripts/train_*.py`, and the content
side of state synthesis — given a predicted roster and soil carbon, produce a valid restart record.
Line D owns the bytes; line T owns what goes in them. Not line T's: the formats and the corpus (D),
pre-registrations and verdicts (X).

## NEXT — start here

**A working emulator exists, it is scored against every null, and it emits a state file the real
LPJmL-FIT loads and runs.** Two pre-registered experiments came back FAIL. Read
`experiments/*/verdict.md` and the two decision records below before changing anything.

**Where it stands, in numbers:**

* **Level map:** 0.0361 of held-out cells inside the acceptance band on all 22 quantities at once,
  against 0.0212 for the climatically nearest analogue and 0.0187 for the nearest cell — it beats
  every null by 1.7×, but the pre-registered gate wanted a margin of 0.050 and it delivered 0.0149.
  Per quantity it is much better than that number suggests: 41–100 % of cells inside the band, and
  the distribution of "how many of the 22 hit" peaks at 17–18. The 3.6 % is the conjunction.
* **Warming response:** **−0.727** against 0.000 for predicting no change. Stem count carries real
  skill (+0.35) and leaf area some (+0.10); soil carbon is four times worse than nothing.
* **The emitted restart file:** loads and runs (`-DSAFE` included), but its vegetation carbon is
  2,561 against the control's 5,035 gC/m² — a median relative difference of 0.534.

**Next, in order, cheapest first:**

1. **Add `agb` to `MATCH_TRAITS` in `src/vegemu/models/synth.py`.** This is the highest
   value-per-minute item in the repo. The emulator predicts above-ground biomass to 12 % on the
   test block, so the halved carbon is entirely a synthesis fault: donors are matched on height and
   wood density, and a stem with the right height and density can still carry the wrong mass.
   Verify with a 20-cell one-year subset run, which costs 8 seconds.
   Record: `docs/decisions/20260908-T-restart-loads-but-carbon-is-halved.md`.
2. **Widen the donor pool.** It is 6,745 stems from 10 cells. `pool_shortfall` is already reported
   per cell, so the ceiling this imposes is measurable rather than hypothetical.
3. **Do NOT tune the current model to chase the map gate.** The pre-registration is sealed; a
   changed model is a new `exp_id`. Retuning against a held-out score you have already seen turns
   the reported number into a selected maximum, which is a subtler form of the same mistake as
   reporting a skill without its null.
4. **The response model must predict the CHANGE directly, and is blocked on line D's pilot
   corpus.** The current architecture obtains a response by DIFFERENCING two level predictions,
   which only works where the true change is large compared with the level error — that is the
   whole −0.727, and it is arithmetic rather than a hyperparameter.
   `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
5. **T1, the GPU path, is still not built** and is still unblocked. It was not needed: the current
   model is gradient-boosted trees on 16 CPU cores and fits in ~4 minutes. Build
   `scripts/sbatch_train.sh` when a model actually needs a GPU, not before.

⚠ `origin` points at the predecessor's GitHub repository and shares no ancestor with this history,
so nothing has been pushed; everything is merged into LOCAL `main`. Owner decision needed.

Housekeeping: none owed. Every campaign in `campaigns/T/ledger.jsonl` is harvested.

## Milestones

**T0 — the constraints, and the baseline spec. DONE**, in the module docstrings rather than a
separate note: `src/vegemu/models/emulator.py` states why a per-quantity boosted head is the right
FIRST model and what it cannot do (marginal quantiles predicted independently; no stochastic
per-stem head, which is correct on purpose because the target is the ensemble expectation).

**T1 — the GPU launch path (OPEN, still unblocked, still not needed).**

**T2 — the level model. DONE and scored.** See NEXT.

**T3 — the roster model (set network with a stochastic per-tree head).** Blocked on nothing
technical, but pointless before the pilot corpus: the joint trait dependence it would add is not
what either failure is about.

**T4 — state synthesis. DONE to t2 on the ladder** (format round-trip, config pre-flight, the C
loads and runs a year), FAILING at t4 (the state distribution). t3 and t5 are not worth running
until item 1 above is done.

## Line T gotchas

* **Fit ONE model and apply it to both climates** when scoring a response. Fitting twice lets the
  fitting noise leak into the difference, which is the quantity under test — `fit_out_of_fold`
  takes a LIST of feature matrices for exactly this reason.
* **Log-transform the strictly positive stock targets.** The acceptance band is relative, so a
  squared error on the raw scale would spend nearly all its attention on the wet tropics.
* `k_root` comes out at 1.000 inside the band for all three of its quantiles — it is nearly
  constant across the domain, so it contributes nothing to the conjunctive test either way. Worth
  disclosing whenever the 22-quantity number is quoted.
