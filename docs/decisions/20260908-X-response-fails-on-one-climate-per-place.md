# The kill test failed, and the arithmetic of WHY it failed is the argument for the designed ensemble

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** X
- **Governs:** `X-20260908-warming-response` (FAIL), `X-20260908-climate-state-map` (FAIL)
- **Nothing here was tuned after the fact.** Both pre-registrations were sealed and committed
  before the model was fitted, both blessed statistics came out on the first run, and no
  hyperparameter, feature or threshold was touched afterwards. A changed model is a new `exp_id`.

## The two results, with every null beside them

**The kill test** — a model fitted on the historical leg only, shown the same cell's climate for
1970–1999 and for 2071–2100 under high emissions, its two answers differenced. 56,950 cells that
are tree-bearing in both legs, 15° spatially blocked folds, both legs from the same 2026-02-05
binary build.

| arm | `skill_response_mean` | pre-registered value |
|---|---|---|
| everywhere changes by the average amount | **+0.0162** | +0.016215 ✓ |
| **predict no change** | **0.0000** | 0.0 ✓ (analytic) |
| copy the nearest cell's change | −0.1424 | −0.142351 ✓ |
| **the emulator** | **−0.7271** | — |
| shuffled | −0.9129 | −0.912870 ✓ |

Gate: beat the best null by 0.050, i.e. reach 0.066. Margin **−0.743**. **FAIL.**

**The map test** — can a 30-year climate summary alone, with no coordinates, put the state inside
`max(10 %, the two-seed spread)` on all 22 quantities at once?

| arm | `band_frac_conjunctive` | pre-registered value |
|---|---|---|
| **the emulator** | **0.0361** | — |
| nearest climate analogue | 0.0212 | 0.021247 ✓ |
| nearest cell (address only) | 0.0187 | 0.018683 ✓ |
| shuffled | 0.0007 | 0.00072 ✓ |
| the average forest | 0.0000 | 0.0 ✓ |

Gate: beat the best null by 0.050, i.e. reach 0.071. Margin **+0.0149**. **FAIL** — though the
emulator does beat every null, by 1.7× the best one.

**Every null returned its pre-registered value.** So neither verdict is `invalid`: the apparatus
did exactly what was declared, and these are clean failures of the model, not of the measurement.

## Where the response failure comes from, quantity by quantity

The blessed statistic is the unweighted mean of seven. The seven are not alike:

| quantity | response skill | true change / level | band fraction (level) |
|---|---|---|---|
| stems per patch | **+0.349** | −2.12 on 23.1 (−9.2 %) | 0.53 |
| leaf area index | **+0.098** | −0.055 on 2.10 (−2.6 %) | 0.48 |
| median stem height | **+0.041** | +0.051 on 4.44 (+1.2 %) | 0.72 |
| above-ground biomass | −0.001 | −194 on 4,043 (−4.8 %) | 0.41 |
| median wood density | −0.692 | +1,356 on 259,700 (+0.5 %) | 0.79 |
| median specific leaf area | −0.863 | −0.00059 on 0.0243 (−2.4 %) | 0.67 |
| soil carbon | **−4.022** | −399 on 11,250 (−3.5 %) | 0.56 |

**Stem count carries real, non-trivial warming-response skill (+0.35).** Leaf area carries some.
Everything else is worse than nothing, and soil carbon is four times worse.

The pattern is not random, and it is arithmetic rather than biology. The emulator predicts a
LEVEL; the response is the DIFFERENCE of two level predictions. Differencing does not cancel the
level error — it roughly doubles its variance — so the skill on the change is positive only where
the true change is large compared with the model's own level error. Soil carbon is the extreme
case: a slow pool whose simulated change is 3.5 % of its level, against a level error far larger
than that. No amount of level accuracy recovers a change that small by subtraction.

**This is a general result about the architecture, not about this hyperparameter set.** Any model
whose target is the level and whose response is obtained by subtraction inherits it.

## What the failure does and does not license

**It does NOT show that a data-driven emulator cannot capture the warming response.** It shows
that a model trained on **one climate per location** cannot. That is the identification limit
(`MEMORY.md:ident-limit`) — and this is the first time it has been measured on the actual target
rather than inferred from a feature-importance argument. In training, climate and place are
collinear: the model learned a spatial climate→state map, and when a cell is moved along a climate
axis it extrapolates in whatever direction its splits encode, which need not be the direction the
model itself would move in time.

**It does show that the level product is viable and the response product is not yet.** Per
quantity the emulator puts 41–100 % of held-out cells inside the acceptance band, and it beats
both the space-for-time analogue and the nearest-neighbour address. The conjunctive 3.6 % is what
happens when 22 such tests must hit in the same cell — the distribution of "how many of the 22
land inside the band" peaks at 17–18, so most cells get most of the way there.

**It makes the designed climate-perturbation ensemble the only identified path, not an
optimisation.** `PLAN.md` argues for it from the collinearity of the existing corpus; this adds
the measured consequence and points at the fix the argument implies: with the same cell spun up
under many climates, the training target can be the CHANGE itself rather than the difference of
two level predictions — which removes the error-amplification above by construction.

## The sensitivity check, which is not a footnote

The 5° blocked-fold arm was pre-declared. At 5° the nearest available training cell is closer, and:

* the map test's nulls strengthen (address 0.0187 → 0.0375, analogue 0.0212 → 0.0371) and so does
  the model (0.0361 → 0.0582); the margin improves to +0.0207 but still fails;
* on the RESPONSE, the address null flips from **−0.142 to +0.120** — and would then beat every
  other null by 0.097, tripping the no-power rule and making that arm's verdict `invalid`.

So the blocking radius is load-bearing rather than cosmetic: at 5° this experiment would have
measured spatial interpolation and said so. The 15° primary is what makes the result mean anything.

## Consequences

1. `PLAN.md` rung 1 stands as written and is now **mandatory**: the pilot corpus of 200 cells × 30
   climates is the only way to identify the response. Its budget does not shrink — see
   `docs/decisions/20260908-D-spinup-is-not-converged.md`.
2. The next model arm must **predict the change directly**, which is impossible without paired
   climates and is therefore blocked on that corpus. It will be a new `exp_id`.
3. The level product may be reported now, with its basis and its 3.6 % conjunctive number, and
   must never be described as capturing a warming response.
4. Both verdicts are rendered from the result rows by `tools/render_verdict.py`; the outcome is
   recomputed by the checker, not asserted here.
