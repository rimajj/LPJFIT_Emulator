# The ssp370 second seed exists on disk; the configured path points at the clone

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** D
- **Scope:** provenance only (D3). Verifies, from the runs' own logs and file sizes, the two claims
  the corpus v2 rebuild is blocked on. **Changes no config and rebuilds no corpus** — both of those
  decisions belong to the integrator and to line X respectively, and are requested, not taken.

## What was verified

`config/paths.yaml:118` maps `ground_truth.ssp370_seed2` to
`…/ssp370/…/transient_2020_2100_npatch25_random_seed2`. That directory is **not** an independent
second realisation, and it carries an in-tree marker saying so
(`INVALID_NOT_A_SECOND_SEED.md`, written 2026-08-03 by the predecessor project).

Re-measured today, from the filesystem and from each run's own banner:

| leg / member | `restart_2100.lpj` bytes | build stamped in its log |
|---|---|---|
| ssp370 seed1 | 133,559,375,490 | Feb 5 2026 |
| ssp370 "seed2" (configured) | **133,559,375,490** — identical | Feb 5 2026 |
| ssp370 seed2 `_from_hist_seed2` | 133,580,962,759 — differs | **Jul 21 2026** |
| Historical seed1 | — | Feb 5 2026 |
| Historical seed2 | — | Feb 5 2026 |

The corrected member **completed**: `lpjml successfully terminated, 67420 grid cells processed.`
appears exactly once, anchored at line start, in a non-empty log (job 1684567), satisfying the
standing rule that a C run is judged by that line and not by an exit code. Its three `stderr` lines
are the usual `WARNING027`/`WARNING036` config-default notices, not errors.

## Why the clone happened, and why nothing warned

Recorded in full in the on-disk marker; the mechanism matters because it will recur. Under
`-DFROM_RESTART` with `new_seed: false`, per-cell RNG seeds are **restored from the restart file**,
and the branch that would apply `random_seed` instead is gated off. `random_seed` is therefore
**inert in any `FROM_RESTART` run**. The configured member set `random_seed: 2` but pointed
`restart_filename` at the historical **seed 1** file, so it inherited seed 1's RNG and vegetation
state exactly.

⚠ **The silent part:** because `new_seed` is false the log never prints `Random seed: 2` — it prints
`Reading random seeds from restart file.` Bumping `random_seed` alone thus produces a byte-identical
clone with no warning anywhere, and a "seed 3" made the same way would fail identically. The
independence of the *historical* pair comes from their spin-ups, which ran without `-DFROM_RESTART`
and took an ungated `setseed` branch.

## The guard already holds, so this is blocked, not silently wrong

`check_seeds_differ` in `scripts/corpus_build.py` fails a build whose two seed members record the
same RNG triple, share no comparable column, have zero cell overlap, or are equal in every compared
column and cell. Its six tests pass (`tests/test_corpus_seed_gate.py`). The reason it must exist:
the acceptance tolerance is `max(10 %, |s1−s2|/|mean|)`, so with `s1 == s2` the band collapses to
exactly the 10 % floor in every cell **while still reading as "10 % or the model's own spread"** —
the floor wearing the band's name, which would inflate every skill margin measured against it.

No corpus was built from the clone. `ind_ssp370_seed2_all.parquet` (91,882,788,995 B, written
2026-08-04 09:12) differs in size from the seed1 table and postdates the corrected run's completion
by 14 hours, consistent with the marker's statement that nothing was derived from the bad directory.
That is mtime-and-size evidence, not a decode — it is **not** proof, and if that table is ever
scored, decode it and check its RNG triples first.

## The two things this does NOT decide

1. **The config change is the integrator's.** `config/**` is integrator-exclusive, and
   `tools/inbound.py` can only address lines D/T/X, so this is requested via a changelog fragment —
   the same fallback line T used when D's state file was at budget. What is needed is a
   `ssp370_seed2_from_hist_seed2` key; **repointing the existing key in place would silently change
   what three sealed pre-registrations cite.**
2. **Whether to rebuild at all, and on what basis, is line X's.** A corrected ssp370 pair is
   **Feb-05 seed1 vs Jul-21 seed2**, so its two-seed spread conflates stochastic seed difference
   with a build difference, and the builds are not interchangeable (the build date is compiled in).
   That confound must be disclosed wherever the corrected band is quoted. The pre-existing
   `build-provenance` warning is exactly this shape.

⚠ **One rebuild or the other, never two.** Each is a new corpus version, and a changed corpus is a
changed question. v0/v1 hashes are untouched either way.

## What is still unmeasured

- **No decode of the corrected member.** Sizes and log banners were read; no vegetation variable
  was decoded from either restart, so "differs" here means *differs in bytes*, not "differs by the
  model's own noise". The magnitude of the true two-seed spread on this leg remains unmeasured.
- **The Jul-21 build is undocumented in `config/paths.yaml`**, whose comment names only the Feb-05
  and Aug-12 builds. A third build produced stored ground truth. Integrator-owned; noted, not fixed.
</content>
</invoke>
