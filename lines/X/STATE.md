# Line X — experiments: pre-registrations, nulls, verdicts

> Durable state for THIS line. Cross-cutting facts: `MEMORY.md`. Runbook: `CLAUDE.md`. Roadmap and
> the rung ladder: `PLAN.md`. Narrative: newest `journal/X/<YYYY-MM>*.md` (never read at start).
> Budget: 120 lines, of which the NEXT block is 60. `tools/rotate_state.py X` when it fills.

## Scope

Line X owns the **claims**: pre-registrations with every null and the value it must return, sealing,
harvesting, and saying plainly what a result does and does not license — including "invalid", which
is not a soft "fail" but a statement that the comparison licenses no conclusion either way. Line X
does not build models (T) or generate data (D).

## NEXT — start here

**As of 2026-09-23** — rotated by the integrator (the outbound block and all 7 message blocks
triaged, a disposition each, into `journal/X/2026-09b.md`); the integrator refreshes this block at
session end. Basis of every number: pilot corpus v2-constco2 (200 cells × 30 climates × 1 seed,
CO₂ 276.59 ppm), 200 of 54,020 tree-bearing cells — no fidelity claim, acceptance untouched.

| experiment | model | bar | best null | ceiling | blind arm |
|---|---|---|---|---|---|
| warming response `…-warming-response-constco2-resealed` | 0.558968 | 0.257725 | 0.162725 | 0.848545 | 0.362322 |
| composition `…-composition-response-constco2-resealed` | 0.445852 | 0.300203 | 0.160203 | 0.862853 | 0.307940 |
| Product A, climate + soil only `X-20260923-equilibrium-from-climate` | 0.607582 | 0.222666 | 0.097666 | 0.950 | — |

All eighteen nulls returned their pre-registered values exactly. Quote each against its own
ceiling (65.9 %, 51.7 %, 64 %), never against 1.0, never summed; a bar compares only within its
own corpus and estimand.

**WHAT MUST TRAVEL WITH THOSE NUMBERS.**
1. **Blind arms.** Response: 64.8 % blind skill, forcing-attributable +0.196646. Composition
   (`X-20260923-pilot-composition-blind-arm`): the blind model CLEARS the 0.300203 bar by itself at
   15° (fails at 5°, 0.296620 vs 0.305348), so only ~+0.138 reads the forcing (blind 69 %). Its
   apparatus re-fit was off by 1.5e-6 against a 1e-6 tolerance — disclosed in that verdict.
2. **Composition loses to no-change at 2 of 29 levels**, both cold (`core_t+0_p13` −0.0882,
   `lhs10` −0.0665); the response arm wins 29 of 29.
3. **Every ceiling borrows its noise from the two TRANSIENT-CO₂ ground-truth spin-ups.** The
   integrator's full constant-CO₂ second seed (running: jobs 2280660/2280661 + 24 spin-up
   manifests) is what can re-derive them on the right basis — under a NEW exp_id, never by editing
   a sealed one.
4. **Product A rarely lands within 10 %**: 0.0 % of 5,620 tree-bearing runs inside a flat 10 % on
   all 22 (one real run predicting another: 4.9 %); the weakest traits (0.29–0.60) are the gap.

**THIS LINE'S NEXT ACTIONS, in order:**
1. **A new estimand to replace X4** — the only open design question here, unblocked, needs no new
   corpus. X4 is retired as unsealable, not failed (`MEMORY.md:x4-wrong-instrument`). ⚠ Do NOT
   widen the 10 % floor.
2. **Move the forcing-attributable part** (+0.196646 response, ~+0.138 composition): the BLIND arm
   is the competitor that matters. Making it the decision competitor needs its own exp_id.
3. **When the second seed lands**, pre-register the constant-CO₂ band and ceilings before anything
   is scored against them.
4. **Parallel integrator branches (`int/*`) are building new scoring, the equilibrium model and the
   global writer.** Any new skill number from them needs its own sealed pre-registration with every
   null; check `experiments/` on main before sealing a duplicate.

**Standing:** X3 `fail` at outcome (c) — no warmed climate may be quoted from the scenario-leg map.
A sealed experiment is abandoned with `tools/abandon_experiment.py` (a registry row, never an edit).
The band floor is in `score.py`, `abs_floor` required. Never pass `corpus.parquet` to an arm using
`build_features` (`MEMORY.md:never-cache-corpus-parquet`).

## Milestones

**OPEN.** **X4 — the emitted restart file. RETIRED 2026-09-15 as UNSEALABLE, not failed**: the
second seed measured the perturbed two-seed spread flat at ~0.03, so the 10 % floor dominates and
the conjunctive level statistic has no power (`MEMORY.md:x4-wrong-instrument`). Its replacement
needs a new estimand — NEXT item 1. Nothing is waiting on a measurement.

**CLOSED, verdicts are the record.** X5 `pass` 2026-09-14 at 0.545304 (bar 0.225690) — the first
positive result in this project — re-passed at constant CO₂ 2026-09-21 (0.558968). X6 `pass`
2026-09-15 at 0.425610 (bar 0.337858), re-passed 2026-09-21 (0.445852); its blind arm ran
2026-09-23. X3 `fail` at pre-named outcome (c).
