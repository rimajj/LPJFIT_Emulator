# Composition IS scored conjunctively — and that forces the band to gain an additive floor

- **Status:** accepted
- **Date:** 2026-09-14
- **Line:** X
- **Supersedes the decision of** `20260910-X-composition-is-a-response-not-a-level.md`, which
  answered line D "no". The owner answered **yes** on 2026-09-14
  (`20260914-INT-both-open-corpus-decisions-are-answered-by-the-owner.md`). That record is accepted
  and immutable, so this is a new one rather than an edit.
- **Retracts** the outbound message of 2026-09-10 sitting in `lines/D/STATE.md`. D has both that and
  the integrator's opposite answer in the same file; a correction has been sent.

## What the earlier record got wrong, and what it got right

**Wrong: the decision.** It treated "should composition be scored?" as a metric-design question line
X could settle on the evidence. It is not — the owner's answer is that composition is plausibly on
the critical path for the project's central failure, because the synthesiser *copies* composition
from the template, a copied composition cannot shift, and so an emulated forest under a warmed
climate is structurally forbidden from changing its species mix at all. That is a capability
decision, and it outranks a scoring preference.

**Right, and still binding: the measurement.** The reason the earlier record gave for "no" was not a
preference. It was a measured degeneracy in the band, and **the owner's decision does not remove it —
it makes it load-bearing.** The band is multiplicative in the level (`src/vegemu/score.py`,
`acceptance_band`):

    truth = (s1 + s2) / 2 ;  band = max(0.10, |s1 - s2| / |truth|) * |truth|

so **a quantity whose truth is 0 gets a band of exactly 0**, and only an exactly-`0.0` prediction
passes — `1e-9` misses. Composition is structurally zero: a cell holds a few tree types out of
seven. On `corpus/pilot-v1`, over the **5,620 treed rows** (39,340 cell–PFT pairs; the treeless 380
rows are excluded because `blank_treeless_composition` NaNs them, and a NaN is a miss):

| fact | value |
|---|---|
| cell–PFT pairs exactly zero | **42.0 %** |
| rows with ≥1 exactly-zero `pft_frac` | 100 % |
| cells holding all 7 types | 0 |

*(The earlier record's 45.6 % is the same quantity over all 6,000 rows including treeless. State the
basis with the number; they are not interchangeable.)*

Left as-is, adding the seven columns to `SCORED_CONJUNCTIVE` would make the statistic
**anti-correlated with the capability it is being added to measure**: a continuous learner never
emits exact zeros so it scores ~0 regardless of composition skill, while the template-copying
synthesiser reproduces the template's zeros exactly and passes all seven trivially. Under invariant
3 that is a metric without power and its verdict would be `invalid`. The owner's decision is
therefore implementable **only together with the band change below.**

## What changes

`pft_frac_0…6` join `SCORED_CONJUNCTIVE` at corpus v2, and the band for those columns becomes

    band_i = max( relative_spread * |truth_i| , ABS_FLOOR )

an additive floor beside the multiplicative one. A relative tolerance on a **bounded fraction** is
the category error already recorded one level up in `score.py` for changes; it applies verbatim to
shares as levels. The floor restores a finite width at `truth = 0` — which is where composition
carries its sharpest information, since "this type is absent and the emulator invented it" is
exactly the error worth catching.

## ⚠ Do NOT reuse `FLOOR = 0.10` as the additive floor

It is the number sitting in the file and it is the wrong one by a wide margin. Composition shares are
strongly skewed — a cell is dominated by one or two types beside a long tail of rare ones. Over the
same 39,340 pairs, the **non-zero** shares are distributed:

| p1 | p5 | p10 | p25 | p50 | p75 | p90 | mean |
|---|---|---|---|---|---|---|---|
| 0.0022 | 0.0045 | 0.0072 | 0.0167 | **0.0776** | 0.3144 | 0.8920 | 0.2462 |

A floor makes any type whose share is below it **indistinguishable from absent** in both directions.
So the cost of each candidate is:

| additive floor | share of genuinely-present types it blinds the test to |
|---|---|
| 0.005 | 6.2 % |
| 0.010 | 15.6 % |
| 0.020 | 28.3 % |
| 0.050 | 43.2 % |
| **0.100 (= today's `FLOOR`)** | **53.9 %** |

Reusing 0.10 would hide more than half the composition signal — it would trade a metric that is
degenerate at zero for one that is blind to the majority of the types actually present. The
workable magnitude is of order **0.01, not 0.10**, and at that size the multiplicative term still
governs the dominant types (at a share of 0.89 the relative band is 0.089 and the floor never
binds).

## The floor is a measured quantity, not a chosen one — and that blocks the number, not the build

Invariant 5 sets the tolerance at `max(10 %, the model's own two-seed spread)`. The additive analogue
is `max(ABS_FLOOR, |s1 - s2|)` in share units, and **`ABS_FLOOR` must come from the model's own
absolute two-seed spread on composition, pre-registered with the value it must return — not from the
table above, which only bounds what is defensible.** The pilot carries one seed, so it cannot be
measured there today.

⚠ **This upgrades the ask already standing on line D.** A second seed for 20 pilot cells (~34
core-hours) was listed as "cheap, high value". It is now a **prerequisite**: no conjunctive
composition number may be read until the additive floor has been measured from a real two-seed
absolute spread. The same second seed also turns the pilot kill test's ceiling from a bound into a
measurement and attributes the soil-carbon offset, so one job discharges three asks.

**v2's build is unaffected and is not held by any of this.** The seven columns are already in the
state table; what changes is the scored set and the band, both in shared scoring code. D should
build.

## What is unchanged

- **`RESPONSE_QUANTITIES` does not move.** It is the sealed estimand of
  `X-20260909-pilot-warming-response`, whose 0.545304 reproduces only while that tuple has exactly
  seven members. Composition is scored as its own arm against its own nulls.
- **`comp_shift` survives as a response statistic**, not as a replacement for the conjunctive
  columns. The two answer different questions — "does the mix move as it should?" against "is the
  mix right?" — and line T's derived composition kill test is the first.
- **Three reporting constraints carried from the owner's record**, all binding on the first v2
  number: report the v1-scope score on the same model beside it, since widening a conjunction can
  only lower the pass rate; re-measure the ceiling arm rather than carrying 0.5585 across, since a
  wider conjunction has a lower one; and disclose that 3 of the current 22 pass for any prediction
  (fine-root conductivity is constant), so the honest count is 19 today and must be restated for v2.
