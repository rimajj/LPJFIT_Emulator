# Rooting depth route 2 is small, and the band test's real ceiling is 0.56 — not 1.0

- **Status:** accepted
- **Date:** 2026-09-10
- **Line:** T
- **Answers** the single next action of
  `20260909-T-imposing-rooting-depth-works-and-does-not-help.md` ("predict `D95max` better").
  Route 2 is measured: it works, it is small, and it is no longer the largest thing available.
  Nothing there is retracted; one of its numbers is reframed, in §1.
- **Evidence:** the ceiling and the per-quantity worth are in `docs/reference/band-test-ceiling.md`,
  with their basis and the build confound they carry. The arm-by-arm screen is
  `exp/screen-d95max/screen.json`, sha256 `e1dad6b9…`, campaign `T-screen-d95max`, job 2106658.
- **Basis:** corpus v0, historical leg, state at 1999, climate window 1970–1999, npatch 25, truth =
  mean of seeds 1+2, **56,950 cells tree-bearing in both seeds**, 5 blocked folds at 15°,
  out-of-fold. Dimensionless fractions (levels). Not the acceptance test — one leg, no response.

## 1. The premise this line was working under was wrong, and it mattered

The band test appears to have no ceiling problem, and that appearance is an artefact of the
same-leg band. `docs/reference/band-test-ceiling.md` has the derivation; two numbers change the
decision:

- **The attainable conjunctive score is 0.5585, not 1.0**, once the tolerance's size comes from a
  leg other than the one being scored. The shipped model sits at 0.0351 — **6 % of attainable**.
- **Rooting depth lifted to that attainable ceiling is worth +0.0263**, not the +0.0419 the earlier
  record quoted. That earlier figure is arithmetically right and reproduces exactly (0.0779 −
  0.0361 = +0.0418), but it lifts the quantity to *perfection*, which the same-leg band makes look
  free because that band's ceiling is 1.0 by construction. Both numbers are correct about different
  questions; only the second is a budget for effort.

And no other quantity is bigger: the best single one (`soilc`) is worth +0.0084, and seven of the
22 made perfect still leaves 89 % of cells failing. **The lever is not a quantity at all.**

## 2. What improves the rooting-depth heads, measured

Seven arms, `scripts/screen_d95max.py`. Arms compared on blocked folds 0–2 and the winner quoted on
folds 3–4, so the choice was not made on the number reported. **The control arm reproduces the
sealed run's stored predictions to a maximum relative difference of 0.00e+00**, so this is the
harness that produced the reported score. Full table in the artifact; the ends of it:

| arm | `D95max_p10/_p50/_p90` pass, screen | conj., screen | conj., confirm |
|---|---|---|---|
| baseline (shipped recipe) | 0.5948 / 0.5514 / 0.6835 | 0.0392 | 0.0304 |
| bounded target + absolute error | 0.6231 / 0.5931 / 0.7277 | 0.0406 | 0.0321 |
| **that, plus soil texture and more capacity** | **0.6265 / 0.6016 / 0.7200** | **0.0412** | **0.0338** |

Read honestly: **all six non-baseline arms beat the baseline on both bases, and the differences
among the six are not resolvable** — with ~65 independent 15° blocks the sampling error on a 0.03
rate dwarfs the 0.0008 separating the middle arms. The consistent direction is the finding; the
ranking is not. Best arm over baseline: **+0.0034 confirm**, which is 13 % of what perfect rooting
depth is worth and 0.6 % of the gap to the ceiling.

Two mechanisms, both read off the model rather than guessed:

- **Shrinkage toward the middle, not scatter.** Mean log residual runs +0.576 in the lowest truth
  decile of `D95max_p50` to −0.294 in the highest, and that decile passes 16 % of cells. Squared
  error in logs returns the conditional *mean*; the band test scores a *median*, and near the
  trait's floor the conditional distribution is a pile-up with a long upper tail.
- **The trait is bounded and the fit was not.** In the parameter file the corpus runs actually used
  (`par/pft_lpjmlfit.js`, via `param_lpjmlfit.js` — **not** `par/pft.js`, which disagrees), the
  `D95max` floor is 51 mm for all seven PFT entries while the ceiling is PFT-dependent: 1800, 1000,
  1000, 500, 500, 500, 300. A scored quantity is a cell-level quantile over whatever PFTs live
  there, so [51, 1800] is the envelope and is looser than the truth in most cells. 3.3 % of cells
  sit within a millimetre of the floor on `D95max_p10`; the logit target stretches that region so
  the loss attends to it. *Not* about clipping — the unbounded fit already stays inside for all but
  0.19 % of cells, a boosted tree's output being assembled from averages of the training targets.

## 3. Three things it is NOT, each closed on a measurement

1. **Not underfitting.** 6× the trees at 0.4× the rate cut training error from sd(log) 0.134 to
   0.081 and moved the held-out score by nothing. `emulator.py`'s refusal to tune costs nothing.
2. **Not realisation noise.** An out-of-fold prediction is independent of the held-out cell's seed
   draw, so `Var(pred - truth) = Var(pred - mu) + sigma^2/2`; with `sigma` from the two seeds,
   **82 %** of `D95max_p50`'s error variance and 64 % of `D95max_p10`'s is reducible (sd 0.319
   against 0.150 irreducible, in logs).
3. **Not a shared per-cell factor.** The 19 non-degenerate residuals correlate strongly, but the
   leading component carries only 24.7 % of standardised residual variance, and removing it *with
   an oracle that has seen the truth* moves the conjunctive score 0.0361 → 0.0428.

What remains is generalisation across space: training sd(log err) 0.13 against 0.36–0.38 held out.
The geographic-address null already reaches 0.524 / 0.495 / 0.628 on the three rooting-depth
quantiles against the model's 0.611 / 0.564 / 0.713 — copying the nearest cell is most of the way
there, so the 30-year climate summary adds little over spatial smoothness.

## 4. A constraint in the C that the emulator already honours (null result)

Leaf longevity is not an independent trait. `tree/new_tree.c:215` runs unconditionally for every
newly born tree, in both the inheritance and the "everything is everywhere" branch:
`longevity = 10^(interc + slope*log10(sla) + eps)`, `|eps| <= 2 sigma` (`numeric/corr_corridor.c`;
`par/pft_lpjmlfit.js` gives slope −1.128 or −2.5 and sigma 0.05–0.1 by PFT). Three of the 22 scored
quantities are generated from three others, with crossed quantiles because the map decreases —
exactly the −0.92 residual correlation between `sla_p10` and `longevity_p90`.

**Imposing it makes things much worse and must not be attempted again.** Deriving longevity from
the model's own predicted SLA through a corridor fitted on the training folds drops
`longevity_p50` from 0.5910 to 0.3334 and the conjunctive score from 0.0361 to 0.0082; the reverse
direction gives 0.0129. A cell mixes PFTs with different corridor parameters, so the *cell-level*
relation carries 0.099 residual sd in log10 — 26 % scatter, far outside a 10 % band. And there is
nothing to enforce: the emulator already reproduces the relation, fitting slope −1.690 against the
truth's −1.685 and intercept −2.828 against −2.820.

## 5. What ships, and what is requested

`Emulator` gains a per-head `Recipe` (bounded target and/or absolute-error objective) and the
constant `ROOTING_DEPTH_RECIPES`. **Default empty, so the shipped model is byte-identical** and no
number on the record changes meaning; `tests/test_emulator_recipes.py` pins that, the transform's
round-trip, and the refusal to double-transform a head. Switch it on at the next full refit,
together with the soil-texture features requested from line D — the two were measured together and
the combination is what earned +0.0034 rather than +0.0017. Not worth a standalone rebuild alone.

Two requests go out with this record. To **line D**: add soil type to the corpus features. The
corpus carries soil *depth* but not soil *type*, and rooting depth is selected by how much water
the column holds; measured worth as a main effect is 2.5–3.0 % of the `D95max` residual variance.
To **line X**: the map verdict should quote the attainable ceiling beside the score, because a
conjunctive number against an unstated ceiling of 1.0 reads as a far worse result than it is.
