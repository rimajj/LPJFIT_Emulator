# Imposing rooting depth works, removes the synthesiser's cap, and makes fidelity worse

- **Status:** accepted
- **Date:** 2026-09-09
- **Line:** T
- **Answers** the single next action of `20260909-T-the-height-tail-is-not-the-binding-constraint.md`
  ("rooting depth, two routes"). Route 1, imposition, is built, measured and **shipped switched
  off**. Route 2, predicting it better, is now the only one that helps. Nothing is retracted.
- **Basis:** cells 42480–42499, 20 of 54,020, temperate Europe, historical leg, 2000–2019, one task
  per arm, 25 patches, same band and ceiling arms as t3/t5. **Not the acceptance test.**

## The stated risk was the wrong risk

The prior handoff flagged one thing to check first: rooting depth is "derived from height inside
the model — check whether the model recomputes it at the first allocation before trusting an
imposed value." It does not. Every write to `tree->D95max` in the C is at tree BIRTH
(`tree/new_tree.c:124,179,209,233`), plus the sapling copy (`getsapling.c:94`) and the cell trait
template (`celldata.c:291`). `allocation_tree.c` computes `tree->D95` — a **different field** — and
never touches `D95max`. Rooting depth proper comes from `getrootdepth(height, k_root, model)`,
which takes `k_root`, not `D95max`.

So an imposed value persists, and it drives no physics. It is still load-bearing: offspring inherit
it from a parent with mutation (`new_tree.c:179-182`), so the roster's distribution seeds the next
generation's, and its three quantiles are 3 of the 22 scored.

## The mechanism works exactly as designed

`IMPOSED_TRAITS` writes the field into the transplanted stem's bytes — the template stem's own
value at that height rank, recalibrated onto the predicted knots, clamped to what real pool stems
exhibit. Median relative error of the emitted file **against its own input**:

| | before | after |
|---|---|---|
| `D95max_p10` | 0.119 | **0.003** |
| `D95max_p50` | 0.072 | **0.007** |
| `D95max_p90` | 0.062 | **0.002** |

The cap that donor selection provably could not pass — 0.127 even under a perfect prediction — is
gone. That is the whole of what imposition promised.

## And fidelity got worse, because the prediction is worse than the accident

Median relative error against the **truth**, same twenty cells:

| | inherited (v5) | imposed (v6) | the level model's own error |
|---|---|---|---|
| `D95max_p10` | 0.177 | 0.174 | **0.179** |
| `D95max_p50` | 0.119 | **0.133** | **0.141** |
| `D95max_p90` | 0.025 | **0.058** | **0.060** |

The old file was *closer to the truth than the emulator's own prediction was*. Its rooting depths
came from real donor stems in neighbouring present-day cells and happened to land better than the
level model's estimate. Imposition replaces that accident with the prediction, faithfully — and the
prediction is worse. At twenty years: **conjunctive 5 % → 0 %, median 18/22 → 17/22.** Every other
scored quantity is unchanged to three decimals; the entire effect is the three rooting-depth
quantiles.

## Shipped switched off, and the condition for switching it on is a number

`IMPOSED_TRAITS = ()`. Verified inert: synthesising with the default reproduces `synth-v5`
**byte-identically** (sha256 `1e856119…`), so the deliverable is unchanged and the machinery costs
nothing until it is wanted. `synthesise_cell(..., impose_traits=("D95max",))` turns it on for a
measurement without editing the constant.

Switch it on when the level model's `D95max` prediction beats roughly **|pred−true| = 0.12 at the
median**, and switch it on **regardless before any warmed-climate product is quoted**: a donor's
rooting depth is a present-day value from a neighbouring cell, so the accident that currently helps
cannot shift with climate — and the warming response is the acceptance criterion's binding clause.
Being right for a reason that cannot generalise is not skill, and it will not survive the test the
project actually has to pass.

## What this settles

1. **The synthesiser's rooting-depth cap is solved and is no longer anyone's next action.** It was
   named as such by the previous two handoffs. Both scored objects pointed at rooting depth; only
   one of them was the synthesiser's to fix, and that half is now done.
2. **Predicting `D95max` is the whole remaining gap** — |pred−true| of 0.141 and 0.179 against a
   two-seed floor that already runs at 22 %, so there is real room but the floor is close.
3. **"No individual stem is ever edited" is now a rule with one named exception**, gated on three
   tests read off the C source: the model never recomputes it, it drives no physics, it is still
   load-bearing. Leaf carbon looks similar and fails the second test.

## An unrelated defect this surfaced, and it is line D's

`scripts/sbatch_cmodel.sh` submits with `--export=ALL` and **no `module load` line**, so a C run
silently inherits the submitting shell's modules. A session whose shell has none submits a job that
dies in under a second on `libnetcdf.so.19`, then `libudunits2.so.0`, one library per attempt. Three
jobs were lost to it here. `20260908-X-build-provenance-of-the-low-emissions-leg.md` already
recorded that no job script pins its library set; this is that gap biting a caller. The durable fix
belongs in the wrapper, which line D owns — sent via `tools/inbound.py`. The working set is now
recorded in the new `cmodel-run` skill, which the deny hook has been advertising all along and
which did not exist.

⚠ Also measured: `grep -c 'successfully terminated'` returns **1 on a failed job**, because the
wrapper's own advice text contains the phrase. Anchor it: `grep '^lpjml successfully terminated'`.
