# The emulator's restart file loads and runs in the real model; its carbon stock is half right

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** T
- **Artifact:** `/p/tmp/jamirp/vegemu/runs/synth-v0/restart/restart_1999_emulated.lpj`, 47.9 MB,
  cells 42480–42499, 9,506 stems.

## The validation ladder, as far as it got

| rung | what it asks | result |
|---|---|---|
| **t0** | does the format round-trip byte-identically? | **PASS** — 100 real cells, and every synthesised record |
| **t1** | does the model's own config pre-flight accept it? | **PASS** — `lpjcheck`, 20 cells, year 2000, all inputs found |
| **t2** | does the C load it and run a year without aborting? | **PASS** — *"lpjml successfully terminated, 20 grid cells processed."* |
| **t4** | does the state it carries match? | **FAIL** — vegetation carbon 2,561 vs 5,035 gC/m², median relative difference **0.534** |
| t3, t5 | 20-year drift; end to end | not attempted |

t2 is the one that matters for the deliverable's existence: the model is built with `-DSAFE`, so it
aborts a cell whose water balance is off by more than 1.5 mm/yr. It did not abort. **A state file
produced by the emulator is loadable and runnable by the real model.**

The control arm — the same 20 cells cut byte-exactly out of the real restart and run with the same
config and the same one task — also succeeded, which is what makes the comparison legitimate: a
subset re-run is not a per-cell replica of the global run, so both arms have to be subset runs.

## The one failure on the way, and why no round-trip test could have caught it

The first synthesised file failed t2 with

```
ERROR195: Invalid value 7 for litter index, must be in [0,5]
```

**The last byte of a PFT entry is not a self-contained value. It is an INDEX into that patch's own
litter list**, validated in `freadpft.c:71` against `patch->soil.litter.n`. Within one record it is
always consistent, so reading a record and writing it back byte-identically proves nothing about
it. It breaks only when a stem is *moved between patches* — which is exactly what a transplant
does. A donor whose home patch had eight litter pools landed in a patch with six.

Every transplanted stem's index is now remapped to the target patch's slot for the same PFT, with
an empty slot appended where that PFT has none. Recorded in `docs/reference/binfmt.md`.

**The general lesson: a byte-identical round-trip validates a LAYOUT, not a cross-reference.** Any
field that indexes into another part of the same record needs its own check, and the only test that
finds one is running the real model.

## Why the carbon is half right, attributed rather than guessed

It is the transplant, not the prediction. For these same 20 cells:

| quantity | truth (mean) | the emulator predicted | median relative error |
|---|---|---|---|
| above-ground biomass | 3,879 gC/m² | 4,197 | **0.121** |
| stems per patch | 19.35 | 19.02 | 0.062 |
| median stem height | 5.14 m | 5.00 | 0.036 |

So the emulator asked for roughly the right biomass and the synthesis delivered about half of it.
The cause is in the matching objective: donors are chosen to match the predicted **height** and
**wood density** quantiles, and they do — the achieved distributions come within 0.3 % of the
request — but **carbon is not a matching target**. A stem's sapwood, heartwood and leaf carbon come
along with whichever donor was picked, and a donor that has the right height and the right wood
density can still carry the wrong mass, because mass also depends on crown area, age and the
allometric state the donor happened to be in.

## What follows

1. **Add above-ground biomass to the donor-matching objective.** The emulator already predicts it,
   the corpus already carries it, and the change is confined to `MATCH_TRAITS`. This is the next
   thing to do on this line, and it is cheap.
2. A residual mismatch after that is expected and bounded by the donor pool: the pool is 6,745
   stems from 10 cells, and `pool_shortfall` is already reported per cell for exactly this reason.
   Widening the pool is the second lever.
3. **Do not quote t2 as fidelity.** "The real model loads and runs it" and "the state is right" are
   different claims, and only the first is currently supported. The 0.534 must travel with any
   statement about the emitted file.
4. t3 (20-year drift within the two-seed spread) is not worth running until t4 is closer: a state
   that starts 53 % low in carbon will drift for a reason that is already known.
