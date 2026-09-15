# The spin-up DID converge: the late rise is transient CO2, not drift

- **Status:** accepted
- **Date:** 2026-09-15
- **Line:** D
- **Supersedes:** `20260908-D-spinup-is-not-converged.md`. That record's MEASUREMENTS stand; its
  headline, its mechanism and everything derived from "not converged" are withdrawn.
- **Found by:** the owner, asking why a single cell in `ncview` showed no late rise, whether the
  spin-up had been confused with the transient run, whether CO2 was constant, and whether the
  climate was really shuffled. Three of those four questions were the right thread.

## The correction in one line

The 1000-year spin-up runs **model years 1000–1999**, and its CO2 input is a **transient** file
(`global_co2_ann_1700_2022.txt`). LPJmL holds CO2 at the file's first value for any year before
1700, so the first 700 spin-up years are at a constant 276.59 ppm and **the last 300 carry the real
historical CO2 rise** to 367.26 ppm. The "still rising at +6.5 %/century" is CO2 fertilization. Under
constant CO2 this spin-up is flat.

| spin-up window | model years | CO2 | trend in global vegetation carbon |
|---|---|---|---|
| 200–700 | 1200–1699 | 276.59 ppm, **exactly constant** | **+0.15 %/century** |
| 700–1000 | 1700–1999 | 276.59 → 367.26 ppm, **+32.8 %** | **+5.53 %/century** |

Correlation of CO2 with global vegetation carbon over the rising window: **+0.9873**. Vegetation
carbon rises **+21.2 %** while CO2 rises **+32.8 %**.

## Why this was not caught for a week

**The trend was fitted over exactly the wrong window.** `corpus_convergence.py` sets
`TREND_YEARS = 200` and fits the slope over the LAST 200 years of the run — a window that lies
entirely inside the CO2 ramp. The statistic was well defined and correctly computed; it measured a
forced response and reported it as residual drift.

**The mechanism offered was a guess, and it was labelled as one.** The superseded record proposed
`inherit_startyear: 200` and slow trait sorting, and said in terms "this attribution is not
established here — only the trajectory is measured". That honesty is why this is a correction and
not a discovery: the guess was recorded as a guess and then quoted downstream as if it were the
finding.

**Nothing in the repository read the CO2 input.** The corpus builder's provenance says `"co2":
"untouched and never written"`, which is TRUE and was mistaken for "constant". Never written and
never varying are different claims, and only the first was checked.

**The shape was visible and was described without being questioned.** The superseded record itself
writes that the curve "sits between 728 and 736 Pg C from year 200 to about year 800, and then rises
again". A system stationary for 600 years does not spontaneously resume growing under unchanged
forcing. That sentence was the finding, written down and not followed.

## What the owner's single-cell observation was telling us

It was right, and it is the fastest route to the same conclusion. The cells that hold the carbon are
flat or declining over the last 200 years; the rise is in sparse cells, where the relative response
is large but the absolute stock is small.

| cell | yr 600–800 mean | yr 800–1000 mean | change |
|---|---|---|---|
| 42490 (Hainich, dense) | 4587.7 | 4408.9 | **−3.9 %** |
| 25363 (dense) | 2830.4 | 2759.8 | **−2.5 %** |
| 44030 | 818.3 | 995.5 | +21.6 % |
| 15233 (sparse) | 227.8 | 295.5 | +29.8 % |

So "I looked at a cell and saw no rise" is not a contradiction of the global curve — it is the
signature of a forced response acting most strongly where there is least to lose.

## The one question whose answer was already right

**The climate IS shuffled.** LPJmL prints `shuffle climate` in its own run banner, and the cycle
length is `nspinyear: 30`. Nothing here changes that.

## What this changes

**1. "Converged" and "equilibrium" are now two different questions, and only one was ever answered.**
Under constant CO2 the spin-up is stationary from about year 200 (+0.15 %/century). So the target
IS, to a good approximation, the stationary forest the cycled climate supports **at 276.59 ppm** —
right up until model year 1700, after which the run is a CO2-forced transient. The stored
`restart_1999.lpj` is therefore best described as *the forest the cycled climate supports, carried
through the historical CO2 rise to 1999 levels*. It is still protocol-defined and it is still
exactly what a model user gets, so the practical framing is unchanged — but the REASON is CO2, not
unconverged drift, and the two imply different things about shortening the run.

**2. The 3.3x budget saving is back on the table as a QUESTION, not as a refutation.** The
superseded record refuted it with "a 300-year run would differ by 22 %". That 22 % is the CO2 ramp.
Under constant CO2 the state at year 300 and the state at year 1000 differ by the drift measured
above, which is small. ⚠ **This does NOT license shortening anything yet**: a shorter run that ends
before 1700 ends at pre-industrial CO2 and is a DIFFERENT state from `restart_1999.lpj`, which is
what all ground truth is. The question is now "which CO2 level is the target", and that is an owner
question, not a measurement. **No budget changes on this record.**

**3. Every "the spin-up is not converged" disclosure in a verdict or record is now wrong**, and they
are listed in the changelog fragment beside this record. They travelled into two verdicts' reference
bases. None of them changes a SCORE: every corpus run shares the identical CO2 path, so CO2 is a
constant across the corpus and cannot confound a contrast between design points.

**4. But "constant CO2" as written in the verdicts' reference basis is wrong and must be restated.**
The correct statement is: **CO2 is identical in every run and is never written by us, but it is not
constant in time within a run.** Invariant 8 is intact in the sense that matters — the emulator sees
no CO2 input and there is no CO2 variation between design points for it to respond to — but the
states it is trained on are post-CO2-ramp states, and a reader told "constant CO2" would conclude
something false about what the target is.

**5. `corpus_convergence.py` must not fit its trend inside the ramp.** The fix is to fit over a
constant-CO2 window (model years 1200–1699, i.e. spin-up years 200–700) and to report the ramp
window separately and labelled as a forced response. Until that lands, no number from that script's
`trend_pct_per_century` may be quoted.

## What is NOT claimed here

The per-cell convergence statistics (57.9 % "not settled", 73.3 % "rising faster than 1 %/century")
have **not** been recomputed on a constant-CO2 window. They are fitted over the same last-200-year
window and are therefore suspect in the same way, but the correction above is demonstrated on the
global curve, not on them. They should be assumed wrong and re-measured, not inverted and quoted.

The **noise-floor** numbers from that campaign are unaffected: they are two-seed spreads at a single
year, not trends, and both seeds run the identical CO2 path.
