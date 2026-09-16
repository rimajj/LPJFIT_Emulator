# Restart synthesis — the approach, the field classes, and the validation ladder

Moved out of `PLAN.md` on 2026-09-16 under its 150-line budget, verbatim except where marked. The
roadmap keeps a four-line summary and points here; this file is the authority on how a restart file
is synthesised and on what has to be true before one is believed. Lines D and T own the code
(`src/vegemu/binfmt/**` is D's, `src/vegemu/models/**` is T's); this page is shared.

## Template-conditioned synthesis

Do **not** predict 1.9 MB of consistent state from scratch. We always hold a real, valid restart for
the same cell under a nearby climate, so: **template-conditioned synthesis.** Every field is LEARNED
(roster, per-tree bad-years counter, soil carbon, litter), DERIVED (carbon pools from the pipe model;
the 20-year climate buffer straight from the climate input; the sapling gene pool), COPIED (inert
crop/nitrogen), RELAXED (the fast soil water/ice/enthalpy/temperature block, from the template — it
must be *mutually* consistent and nothing validates it), or FREE (random seed, tree IDs).

⚠ **Species composition is COPIED today and that is now a measured defect** — not a free
simplification. The species-mix response is learnable at 0.425610 against a sealed bar of 0.337858
(rung 8, `MEMORY.md:composition-is-learnable`), so an emulated warmed forest cannot yet shift its
species mix, and that gap is now measured rather than assumed harmless.

**Why the classes matter more than they look.** RELAXED is the dangerous one: nothing in the model
validates the fast soil block, so an internally inconsistent copy fails loudly only if it trips the
`-DSAFE` water-balance abort (`MEMORY.md:restart-safe-abort`), and otherwise runs on silently. The
restart reader has no checksum, no build stamp and no parameter hash, and treats the year as a
warning only (`MEMORY.md:restart-no-checksum`) — so "the model loaded it" is not evidence that the
state is right. That is the whole reason the ladder below exists.

⚠ **A stem that moves patches must have its litter cross-reference remapped.** The last byte of a PFT
entry indexes that patch's litter list (`freadpft.c:71`); a byte-identical round-trip cannot validate
it, because it only breaks when a stem is transplanted (`MEMORY.md:litter-index-xref`).

## The validation ladder, cheapest first

The steps, as the roadmap defines them:

| step | what it proves |
|---|---|
| **t0** | byte round-trip: our reader/writer reproduce a real file exactly |
| **t1** | the config pre-flight accepts the synthesised file |
| **t2** | the C loads it and runs 1 year without aborting |
| **t3** | 20 years with no drift beyond the two-seed spread |
| **t4** | the state distribution matches |
| **t5** | = rung 4, end-to-end: emulated restart → real transient vs real restart → real transient |

Status is kept in `PLAN.md`, not here, and as of 2026-09-16 it reads: t0 **PASSED 2026-09-08** (that
is rung 0); the synthesised file is **valid** and the C ran 20 cells for a year with `-DSAFE` on
(`MEMORY.md:restart-loads`), which is t1 and t2; rung 3 as a whole **still fails conjunctively, 5 %
against a 25 % ceiling**, and rung 4 (= t5) is blocked on that.

⚠ **t3 is scored on a WINDOW MEAN, and its ceiling is not 1.0.** A REAL restart passes the same test
in only **90.9 %** of cells, so that is the ceiling and the arm that measures it is mandatory
(`MEMORY.md:ceiling-arm`). Scoring a single year instead of the window charges the model for the
model's own interannual noise.

⚠ **Those two ceilings — 90.9 % and 25 % — are different statistics, and nothing on record
reconciles them.** Both are carried here exactly as `PLAN.md` states them. Whoever next touches t3
should say in one line which statistic each belongs to; a page that carries two ceilings for one
rung without distinguishing them is how a number gets quoted against the wrong basis (invariant 4).

## What is measured about the current synthesiser

- **It loads, and its carbon starts HIGH, never halved.** The file is 6.7 % high, 12.0 % after year
  one, and sheds to −1.6 % by year 20 — inside the two-seed band. 20 of 54,020 cells.
  (`MEMORY.md:restart-loads`, `restart-starts-high`.)
- **It is still beaten by a random neighbouring cell's real forest**: 0.702 against a 0.786 bar, 20
  cells, 22 quantities. Matching marginals does not make a self-consistent forest
  (`MEMORY.md:neighbour-bar`). This is the sharpest statement of what t3/t4 are still missing.

## The short polish run is dead, and not for the expected reason

Letting the C model relax the fast state for N years was the obvious fallback. **At N = 1 it is a
no-op** (+0.016 and −0.005). The model neither repairs the state nor rejects it — it *carries* it.
So the lever has to be applied at year 0, in the synthesis itself; there is no downstream step that
will clean up an inconsistent state for us.

## Records

- `docs/decisions/20260908-T-restart-loads-but-carbon-is-halved.md` (superseded on the halving —
  see `20260910-D-the-halved-carbon-is-gone-verified-from-the-committed-synthesiser.md`)
- `docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md`
- `docs/decisions/20260909-T-the-roster-was-valid-but-not-viable.md`,
  `20260909-T-the-roster-was-truncated-at-both-tails.md`
- `docs/decisions/20260910-T-rooting-depth-route-2-is-small-and-the-ceiling-is-0.56.md`
- Binary layout and the round-trip proof: `docs/reference/binfmt.md`
- The t3 ceiling in full: `docs/reference/band-test-ceiling.md`
