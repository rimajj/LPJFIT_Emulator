# The high-emissions leg has no second seed: its two "seeds" are the same run twice

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** X
- **Governs:** corpus v0's `state_ssp370_seed*` tables; qualifies the sealed
  `X-20260908-warming-response` (whose verdict stands — see below)
- **Found while** discharging the build-provenance gate
  (`docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md`), not while looking for
  it.

## The finding

Corpus v0's two high-emissions state tables are **exactly equal** — all 22 scored quantities, all
67,420 cells, zero cells differing. The other two legs are not: the historical and low-emissions
seed pairs differ in 63,372 and 63,586 cells respectively.

| leg | two seed tables differ? | relative two-seed spread (median) | cells differing |
|---|---|---|---|
| historical | yes | 0.0303 | 63,372 |
| **high emissions** | **no — identical** | **0.0000** | **0** |
| low emissions | yes | 0.0321 | 63,586 |

The cause is upstream and unambiguous. The run directory named `..._random_seed2` reads its starting
state from the **historical seed 1** restart, exactly as `..._random_seed1` does, and the model reads
its random seeds from that restart. Same build, same input, same seeds, therefore the same output —
identical file size and identical checksum, from two jobs run two hours apart. The recorded seed
triple is the same in both, `(10901, 14779, 51459)`, where the historical and low-emissions legs each
carry two distinct triples.

**A genuine second realisation does exist on disk**, in a third directory
(`..._random_seed2_from_hist_seed2`), which starts from the historical *seed 2* restart and writes a
restart of a different size. Corpus v0 does not use it. It was produced by the **Jul-21 2026** build
rather than the Feb-05 one, so a corrected high-emissions seed pair would itself straddle a build
boundary — the pair would no longer be build-matched, which is the property the sealed kill test
chose that leg for.

## Why it matters, stated exactly

Anything that averages or differences the two high-emissions seeds silently uses **one draw**:

1. **A two-seed mean is a single realisation.** The sealed kill test's target was
   `truth(high, 2100) − truth(historical, 1999)` with each end declared to be a two-seed mean. The
   base end is; the future end is not. Variance of the target is therefore
   `σ² + σ²/2 = 1.5σ²` rather than the declared `σ²/2 + σ²/2 = σ²` — **50 % more realisation noise
   than the pre-registration says it carries.** Its leakage check "dtrue is a difference of two-seed
   MEANS … so it carries one unit of realisation noise rather than two" is false as applied to the
   future end.
2. **A band from this leg is not a band, it is the floor.** `max(10 %, |s1−s2|/|mean|)` with
   `s1 = s2` collapses to exactly 10 % in every cell, so the acceptance criterion's stochasticity
   allowance silently vanishes while still looking like it is there. Any tolerance derived from the
   high-emissions leg is the bare 10 % floor and must never be described as
   `max(10 %, the two-seed spread)`.
3. **"Tree-bearing in both seeds" is a one-seed filter** for this leg, so its scored cell set is
   slightly more permissive than the other legs'.

## The sealed verdict stands, and is not re-run

`X-20260908-warming-response` scored **−0.7271** against a best null of **+0.0162** and a gate of
+0.050. Reducing the target's noise by a third moves the number; it does not plausibly move it
across a margin of −0.743, and the decisive null is pinned at exactly 0.0 by construction whatever
the noise. The verdict is a `fail` and it remains a `fail`.

**So the sealed pre-registration is not edited, and the experiment is not re-run with a corrected
corpus.** That is invariant 2 doing its job: a changed corpus is a changed question, and a changed
question is a new `exp_id` naming the old one in `supersedes:`. What is owed instead is disclosure —
this record, cited wherever that experiment's numbers are quoted.

## Consequences

1. **Line D owes a corpus rebuild** pointing the high-emissions seed 2 at
   `..._random_seed2_from_hist_seed2`, under a **new corpus version** (the hash of v0's manifest is
   cited by two sealed pre-registrations and must not change). The rebuild must record that the
   corrected pair spans the Feb-05 and Jul-21 builds.
2. **The corpus builder should refuse this class of defect rather than record it.** It already writes
   the per-leg seed triples and checksums into `provenance.json`, which is how this was caught; it
   should *assert* that a leg's two seed files differ, and fail loudly if they do not. A defect that
   is merely logged is a defect that gets used.
3. **`X-20260908-heldout-forcing-leg` avoids the leg entirely** — it uses the historical and
   low-emissions legs, both of which were checked for seed distinctness in the same script that
   derived its nulls, and both passed.
4. **The non-circular acceptance band is now available and its source is fixed by this finding.** A
   band built from the high-emissions leg would have been the 10 % floor in disguise; the
   low-emissions leg's two seeds are genuine, so that is the leg the transferred band comes from.
5. **`MEMORY.md` needs a new integrator row.** Requested: *"corpus v0's two ssp370 state tables are
   byte-identical — that leg has no second realisation; the genuine one is
   `..._random_seed2_from_hist_seed2` (Jul-21 build). Never derive a band or a two-seed mean from
   ssp370."*
