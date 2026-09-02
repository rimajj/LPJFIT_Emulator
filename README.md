# vegemu

A purely data-driven emulator of the **LPJmL-FIT** dynamic global vegetation model.

Given a climate, `vegemu` predicts the vegetation state directly and writes it out as

1. a **byte-loadable LPJmL-FIT restart file**, so the model's 1000-year spin-up can be skipped, and
2. the model's **own output files** — including the complete per-tree table with every tree's traits.

The primary target is the **equilibrium forest under any climate**, including warmed climates, which
makes the long-term warming response the central scientific question rather than an afterthought. A
second product predicts the actual year-2100 forest, which still lags its climate.

There is no coupled physics core and no year-by-year rollout: the emulator is a direct map from a
climate summary to a state. It is offline tooling for a vegetation modeller, not a land component.

## Status

Early. The gate ladder and its current rung are in [PLAN.md](PLAN.md).

## Layout

| Path | What |
|---|---|
| `src/vegemu/` | the package: binary formats, corpus building, models |
| `scripts/` | cluster entry points (SLURM wrappers, corpus and training drivers) |
| `tools/` | repository checkers and the experiment/campaign machinery |
| `experiments/` | one directory per pre-registered experiment, with its nulls and verdict |
| `docs/decisions/` | decision records, immutable once accepted |
| `docs/reference/` | deep reference: the cluster, the file formats, inherited findings |

## Working on it

Read [CLAUDE.md](CLAUDE.md) first — it is short by design and holds the nine invariants, the doc map
and the line protocol. The one that matters most: **no reported number without the null it was measured
against**, and that is enforced by a CI gate rather than by convention.

Development runs on the PIK cluster; heavy work goes to SLURM through the `scripts/sbatch_*.sh`
wrappers, which record every submission so a later session can always find and harvest it.

## Provenance

Derived from work in the retired `esm_land_emulator` project, which pursued a hybrid physics/ML land
component for an Earth system model. What carries over — and what was measured and refuted there — is
recorded in [docs/reference/inherited.md](docs/reference/inherited.md). LPJmL-FIT itself is cited in
`CITATION.cff`.
