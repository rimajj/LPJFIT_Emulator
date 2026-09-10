# The halved carbon is gone: the emulated restart starts 12 % HIGH, not at half

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** D
- **Closes** the verification line D owed after line T's tree-type fix
  (`20260909-T-imposing-rooting-depth-works-and-does-not-help.md` and its predecessor). The
  question was whether the model still destroys most of the emulated vegetation carbon inside the
  first simulated year, once stems can no longer be given a type the target cell never holds.
- **Basis:** cells 42480–42499, **20 of 54,020**, temperate Europe, historical leg, 25 patches,
  one task, one simulated year (2000), `-DFROM_RESTART`. **Not the acceptance test** — one region,
  one climate, one seed pair, and no warmed leg.

## The provenance link, which is the point of re-running at all

The previous session's numbers were measured against `/p/tmp/jamirp/vegemu/runs/synth-v6`, emitted
from line T's **uncommitted** synthesiser and carrying an in-flight rooting-depth imposition. A
number citing it cites nothing that can be checked later.

So the restart was re-emitted from `main`'s committed synthesiser at `5cc59c0`
(`scripts/synth_restart.py`, defaults, 8 s, job 2106616), and it is **byte-identical** to the file
the twenty-year `t5` arm was scored on:

```
1e856119eb59fd7595b5d81f61768935ffeb23f787d0bc5bc2264862fa9fcaeb
  synth-v8 (re-emitted, this session, from 5cc59c0)
  synth-v5 / synth-v7 / t5-emulated  (what T scored)
```

That confirms T's "verified inert" claim from the outside — `IMPOSED_TRAITS = ()` reproduces the
pre-imposition file exactly — and it means **`t5`'s twenty-year numbers are citable against a
versioned synthesiser**, which they were not yesterday. The emission also reports 0 stems of a
type the target cell's own real state never holds, so the tree-type fix is present in the artifact.

## The answer: not halved, and not low — high, then converging

Block-total vegetation carbon, year 2000, emulated restart vs the real restart over the same block
with the same task decomposition:

| | block VegC (gC) | vs control |
|---|---|---|
| emulated, year 2000 | 112,763 | **+12.0 %** |
| control, year 2000 | 100,691 | — |
| emulated, year 2019 (`t5`) | 120,052 | −1.6 % |
| control, year 2019 (`t5`) | 121,967 | — |

**The collapse is gone.** The failure being chased across three sessions — most of the carbon
disappearing inside year one — does not occur. What remains is the opposite sign and much smaller:
the emitted forest is somewhat too heavy at handover and the model sheds the excess over about
four years, reaching −1.6 % by 2019, inside the two-seed band for this quantity (0.102).

⚠ **State the sign correctly.** T measured the emitted FILE at 6.7 % high; the model then takes it
to 12.0 % high at the end of year one before converging. Neither number is a halving, and the
earlier "halved carbon" description applies only to rosters the model rejected.

## An independent check that came free

`t7` (one year) reproduces `t5`'s year-2000 field **bit-identically** — same restart, same seed,
same block, different `lastyear`. That is the expected behaviour and it confirms the two arms are
the same experiment, so nothing here contradicts the twenty-year verdict; it dates it.

It does **not** relax the standing warning that a subset run is not a per-cell replica of a global
run. Both arms here are subset runs over the same block, which is the comparison that is allowed.

## What this does not settle

1. **Twenty cells of 54,020, present-day climate only.** The acceptance criterion needs all
   tree-bearing cells, both scenarios, and the response between them. This is a smoke test that
   passed, not fidelity evidence.
2. **The conjunctive score is still 5 %** on `t5` at twenty years, and stems remain the weakest
   scored quantity. Carbon not collapsing removes a blocker; it does not make the emulator good.
3. **No warmed leg was run here**, so the binding clause of the acceptance criterion is untouched.
