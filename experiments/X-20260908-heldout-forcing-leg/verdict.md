# Verdict — X-20260908-heldout-forcing-leg
outcome: fail
**Question.** A map fitted on the 1970-1999 climate and the 1999 forest is handed the 2071-2100 climate of the LOW-emissions leg -- a leg whose state it has never seen, in any cell -- and asked for the year-2100 forest. Does it land inside the acceptance band on stem count AND every scored trait median AND both tails of every scored trait distribution, simultaneously, in more held-out cells than PERSISTENCE does: that is, than simply handing back the same cell's own present-day forest?
Persistence is the competitor that matters, and it is why this rung exists. The emulator's whole claim is that it maps climate to state; if a changed climate cannot be told from the present one on this metric, then what has been measured is the band, not the model.

**Estimand.** `band_frac_conjunctive` — The fraction of scored cells in which EVERY one of 22 quantities lands inside its own acceptance band -- the same statistic, the same 22 quantities and the same code as X-20260908-climate-state-map, deliberately unchanged so that the two numbers are directly comparable: that experiment scored the leg the map was fitted on, this one scores a leg it never saw. The 22 are: stems per patch; above-ground biomass, leaf area index and soil carbon; the median of each of wood density, specific leaf area, fine-root conductivity, the 95th-percentile rooting depth, leaf longevity and stem height; and the 10th and 90th percentile of each of those six traits. Aggregation is per cell, unweighted, computed once over the assembled out-of-fold prediction -- every cell is held out exactly once. A NaN on either side counts as a MISS. THE BAND IS NOT DERIVED FROM THE SEEDS IT SCORES, and that is the one deliberate difference from the map experiment. The truth is the mean of the ssp126 leg's two seeds; the band is max(10 %, the HISTORICAL leg's own two-seed relative spread for that cell and quantity) times |truth|. Taking the tolerance from a different leg breaks the circularity disclosed in the map experiment, where the same two seeds set both the truth and the tolerance so that a single realisation sat at exactly half a band and could not fail. Here it can: one draw of the real model scores 0.538490 against this band rather than 1.000000, and that 0.538490 -- NOT 1.0 -- is what perfect means on this metric. The transfer is licensed by measurement, not convenience: over these 56,950 cells the two legs' relative two-seed spreads agree to within 6 % on every summary (median 0.03027 vs 0.03207, p90 0.16350 vs 0.16529, 19.30 % vs 20.01 % of cell-quantities above the 10 % floor). The same-leg band is the pre-declared sensitivity arm; it is reported, never substituted. DISCLOSED DEGENERACY: fine-root conductivity at all three percentiles is inside the band for every arm in 100 % of cells -- it varies less across cells and legs than a 10 % tolerance -- so the conjunctive test is in practice over 19 informative quantities, not 22. The 22 are kept anyway, because changing the quantity set would forfeit comparability with the map experiment, which is the main reason to run this one. The binding quantities are the stocks and the count: persistence passes above-ground biomass in 32.8 %, leaf area index in 40.7 % and stems per patch in 39.2 % of cells, against 83-100 % for most trait percentiles.

**Reference basis.** LPJmL-FIT 5.6.004. Training truth = the historical leg's state at 1999 from restart_1999.lpj (1000-year spin-up plus the 1901-1999 transient -- NOT a converged equilibrium, see docs/decisions/20260908-D-spinup-is-not-converged.md), climate window 1970-1999, produced by the 2026-02-05 binary build. Scored truth = the ssp126 leg's state at 2100 from restart_2100.lpj, climate window 2071-2100, produced by the Aug-12-2026 build; truth is the mean of random_seed1 and random_seed2, which for this leg are two GENUINE realisations (they start from the historical leg's seed-1 and seed-2 restarts respectively and their state tables differ in 63,586 of 67,420 cells). npatch=25, tree PFTs only, constant CO2 throughout by design. 56,950 cells tree-bearing (>= 0.5 stems per patch) in both seeds of both legs; the historical tree-bearing set is a strict subset of the ssp126 one (56,950 of 59,202), so no cell is lost by requiring both. Dimensionless fraction, a level not a ratio. BUILD PROVENANCE, GATED BEFORE THIS WAS WRITTEN. The two legs come from different binary builds, so this comparison crosses a build boundary and says so. What that boundary contains is no longer unquantified: the model's tracked history has no commit between the two builds, so the difference is exactly 19 modified working-tree files, and every behavioural change in them is gated behind a rung-2 environment variable that the ssp126 job scripts do not set. The two added tree-struct fields are deliberately absent from the restart serialisation, so the restart layout is unchanged; the random-deviate generator changed only by hoisting a function-scope static to file scope; the remaining changes add output accumulators. Compiler flags are unchanged (Makefile.inc predates both builds). What is NOT proven is byte-equality: the decisive test -- one cell, one year, one restart, both binaries, byte-compare -- has not been run, because the Feb-05 binary is preserved but no wrapper exists yet to run it. Full record: docs/decisions/20260908-X-build-provenance-of-the-low-emissions-leg.md. ⚠ CORRECTION 2026-09-17, AND IT DOES NOT MOVE THE SCORE. This basis cites `20260908-D-spinup-is-not-converged.md`, which has since been SUPERSEDED by `20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md`. The disclosure "NOT a converged equilibrium" stands, but the reason it gave does not: the spin-up was not failing to converge. It covers model years 1000-1999 against a TRANSIENT CO2 file, so its last 300 years carry the real historical CO2 rise, and the trend read as drift was CO2 fertilization; with CO2 pinned the curve is flat to +0.15 %/century. The training truth is still not an equilibrium -- it is the state the spin-up reaches THROUGH that CO2 rise. Consequently "constant CO2 throughout by design" must not be read as "CO2 is constant in time": it is at least wrong of the spin-up behind the training truth. ⚠ Whether it holds for the two TRANSIENT legs scored here has not been re-checked and is NOT asserted either way by this correction -- only that the phrase cannot be relied on. None of this bears on the outcome, which is `fail` at pre-named outcome (c) and is about the scenario legs' inability to identify a warming response.

## What this means

A map fitted on the 1970–1999 climate, handed a climate leg it has never seen and asked for the
year-2100 forest, lands inside the acceptance band on all 22 quantities at once in **0.54 %** of
held-out cells. Handing back the cell's own present-day forest does it in **3.37 %**. The model is
beaten by persistence **six-fold**: margin **−0.028306** against a required +0.050.

**This is pre-named outcome (c) of three — "actively harmed by a climate it has not seen".** Not a
near-miss and not a tuning shortfall: at 0.005443 the model sits *between* `geographic_address`
(0.005426) and `nearest_analogue` (0.004688), so **statistically it IS the copy-a-neighbour null**.
⚠ **The sealed document pre-committed the consequence: only outcome (a) would have licensed
continuing to look for a warming response in this corpus** — so (c) directs that search to the
designed perturbation ensemble, which is where `X-20260909-pilot-warming-response` found it.

**All five nulls reproduced their sealed values exactly** (`[OK]`), so this is the apparatus sealed
on 2026-09-08, not a re-specified test. At 5° blocks the model scores 0.006040, ordering unchanged;
the pre-declared same-leg sensitivity band — reported, never substituted — gives 0.005198, so the
non-circular band is not what produced the failure. **Apparatus validation:** the same run scored
the map on the leg it was *fitted* on and returned 0.036067, reproducing the 0.0361 of
`X-20260908-climate-state-map`. It reproduces a known number and disagrees only where the question
changes.
**Both pre-registered framings.** Against the non-circular ceiling, one draw of the real model scores
0.538490 — that, not 1.0, is what perfect means here — so the model reaches **1.0 % of attainable**
and persistence 6.3 %. Against the map experiment's 0.0361 on the leg it was fitted on, this asked
the model to more than double that score on a leg it was not; it returned a sixth of it.

## What this does and does not license

**It does not license "the emulator cannot learn a warming response."** The pilot ensemble passed
the response question the same day with a margin of +0.399614. The two are consistent, and the
reconciliation is identification, not model quality: in the pilot one cell is spun up under 30
climates, so the response is separated by construction; in these scenario legs every cell holds
exactly one climate, so climate and geography are collinear and the response is **not identified at
all**. Line T's record of 2026-09-14 reaches the same place. **What this licenses is a statement
about the scenario legs as training data, not about the emulator's ceiling.**
**Three of the 22 quantities pass for any prediction** — fine-root conductivity varies less across
cells and legs than a 10 % tolerance at all three percentiles — so the honest count is **19
informative quantities**; the 22 are kept only to stay comparable with the map experiment. The
binding quantities are the stocks and the count: persistence passes above-ground biomass in 32.8 %,
leaf area index in 40.7 % and stems per patch in 39.2 % of cells, against 83–100 % for most traits.

**The clone-seed correction does not reach this result.** The sealed leakage checks declare the
high-emissions leg **unused in any arm**, and the two legs used were checked for distinctness when
the nulls were derived — the low-emissions pair differs in 63,586 of 67,420 cells. Its one live
consequence for line X is `X-20260908-warming-response`, noted in that verdict. One sealed statement
is superseded as *stated* though not as *applied*: the leakage check says the high-emissions leg
"has no second realisation", true of the configured path and false of the leg. The genuine run
exists and is wired up on `main` as of 2026-09-14.

⚠ **Still not proven: byte-equality across the two binary builds.** The decisive test — one cell,
one year, one restart, both binaries, byte-compare — has still not been run; everything short of it
is in the reference basis above. A build difference cannot plausibly explain a six-fold loss to
persistence, but it is not excluded by measurement, and it stays owed by line D.

## Metrics

<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->
| arm | band_frac_conjunctive | vs best null | pre-registered null return |
|---|---|---|---|
| model | 0.00544337 | -0.0283055 | — |
| same_cell_persistence | 0.0337489 | — | 0.033749 +/- 0.001 [OK] |
| nearest_analogue | 0.00468832 | — | 0.004688 +/- 0.001 [OK] |
| geographic_address | 0.00542581 | — | 0.005426 +/- 0.001 [OK] |
| climatological_mean | 0 | — | 0 +/- 0.002 [OK] |
| shuffled_target | 0.000632133 | — | 0.000632 +/- 0.002 [OK] |
| **DECISION** | pass_if > 0.05 | **FAIL** | -0.0283055 |

- margin -0.0283055 does not satisfy > 0.05
<!-- END GENERATED -->
