### Added

- **Line X, ADR 0311 — round 2 of the data-driven-emulator exploration: three pre-registered measurements, two
  adversarially verified.** A direct, non-autoregressive 20-yr-climatology → 20-yr-window-state map beats a
  coordinates-only null under spatially blocked folds by +0.162…+0.715 on a clean 20-vs-20-yr response target,
  with climate subsuming the address rather than proxying it ⇒ **ADR 0310's "zero positive evidence for the
  warming response" no longer holds** (its kill was a hash-fold artifact on a drift-contaminated target). The
  same map passes only **7.2 %** of cells on ADR 0106's conjunctive per-cell basis and **loses to persistence**
  on the future state, and space-for-time transfer is **sign-wrong** in the 3.7 % of genuinely extrapolating
  cells. Deepest result: **within one scenario a cell's warming increment is 76.4 % predictable from its own
  baseline climate**, so forcing response and place sensitivity are not separately identified — a counterfactual
  with warming scaled to zero still reproduces 76–110 % of the predicted per-cell change. Also: the per-tree
  growth-failure counter is **exactly recoverable** from the printed roster table (1.000000 on 694 662
  stem-years) and **propagable** through a self-fed rollout by an operator that produces next year's per-tree
  state (recall 0.9023, certain-death population 1.054 at lead 10) but **not** by a one-year-ahead forecast
  (2.063, worse than doing nothing from lead 3) — ⚠ this item's verifier did not run. And **per tree, climate
  adds nothing beyond the stand** (+0.0030, below the pre-registered 0.005; within noise under blocking).
  **Exploratory — no decision, nothing implemented, nothing raised with any line.**
- **Line X exploration note `docs/notes/exploration_data_driven_literature.md`** — the literature review ADR
  0310 §6 said had to happen before designing anything. Pre-registered counts both came back **0**: no
  published work reports a skill number for a *distributional* target under a *held-out forcing* with a stated
  null, and no work anywhere in earth-system science reproduces a response to a forcing *outside* its training
  range (all three successes are bracketed interpolation; every extrapolation attempt in those same papers
  failed). Corrects our own summary of the closest precedent in three places — it is 95 % not 97 %, its neural
  net beats its random forest only for vegetation carbon in the warmer scenarios, and it is **not a state
  operator at all** but a static map, so it carries no information about the rollout question. Supplies the
  first named mechanism for this project's measured response inversion: in 339 ponderosa pines the
  climate–growth relationship read off geography has the **opposite sign** to the one read off time.
