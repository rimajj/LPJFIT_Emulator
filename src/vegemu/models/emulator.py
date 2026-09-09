"""The emulator: a 30-year climate summary in, a forest state out.

WHY THIS MODEL, AND WHY NOT THE FANCIER ONE. `PLAN.md` names a permutation-equivariant set network
with a stochastic per-tree head as the TARGET architecture, and a size-structured distribution head
as the interpretable baseline. This is neither: it is one gradient-boosted regressor per scored
quantity. That is deliberate, and it is the cheapest honest model that can settle the question the
kill test asks.

Three reasons it is the right first model rather than a shortcut:

1. **The scored quantities ARE the distribution.** The acceptance criterion is counts and trait
   medians and trait distributions, and the corpus carries the distributions as quantiles. Directly
   predicting the 10th, 50th and 90th percentile of each trait IS a non-parametric distribution
   head; going through a parametric kernel first would add a modelling assumption and an
   indirection without adding information.
2. **A kill test wants the cheapest model that could pass, not the best one.** If a boosted tree on
   90 climate features cannot beat "the forest next door", a set network is very unlikely to, and
   we would have spent a week finding out.
3. **It is what the restart synthesis needs.** Emitting a state means drawing stems whose trait and
   size distributions match a prediction; predicted quantiles are exactly the input for that.

What it CANNOT do, stated so nobody quotes it for more than it is: it predicts marginal quantiles
independently, so it does not model the joint dependence between traits within a cell, and it has
no stochastic per-stem head, so it predicts the ensemble expectation and not a draw. The first is a
real limitation for the roster product; the second is correct on purpose, because ~28 % of residual
variance is the model's own realisation noise and the right target is the expectation.

THE TARGET TRANSFORM MATTERS AND IS NOT COSMETIC. Above-ground biomass, soil carbon and wood
density span orders of magnitude across the globe, so a squared-error loss on the raw scale spends
almost all of its attention on the wet tropics. Strictly positive targets are therefore fitted in
logs and mapped back, which makes the loss relative rather than absolute -- and the acceptance band
is itself relative, so this aligns the loss with the test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
from lightgbm import LGBMRegressor

# Targets fitted in logs. Every one is a strictly positive stock, density or count whose global
# range covers orders of magnitude. `stems_per_patch` is here too: a boreal cell with 100 small
# stems and a tropical cell with 5 large ones differ by 20x, and a relative error is the meaningful
# one for both.
LOG_TARGETS: frozenset[str] = frozenset(
    {
        "stems_per_patch",
        "agb",
        "vegc",
        "lai",
        "soilc",
        "litterc",
        "crown_cover",
        "wooddens_p10",
        "wooddens_p50",
        "wooddens_p90",
        "sla_p10",
        "sla_p50",
        "sla_p90",
        "k_root_p10",
        "k_root_p50",
        "k_root_p90",
        "D95max_p10",
        "D95max_p50",
        "D95max_p90",
        "longevity_p10",
        "longevity_p50",
        "longevity_p90",
        "height_p10",
        "height_p50",
        "height_p90",
        "crownarea_p10",
        "crownarea_p50",
        "crownarea_p90",
    }
)


@dataclass(frozen=True)
class EmulatorConfig:
    """Hyperparameters, fixed in advance. Not tuned on the held-out folds.

    They are ordinary gradient-boosting defaults, chosen once for a 45,000-row x 90-feature problem
    and left alone. Tuning them against the held-out score would make the reported number an
    optimistically selected maximum rather than an out-of-sample estimate -- which is a subtler
    version of the same mistake as reporting a skill without its null.
    """

    n_estimators: int = 500
    learning_rate: float = 0.05
    num_leaves: int = 63
    min_child_samples: int = 40
    subsample: float = 0.8
    subsample_freq: int = 1
    colsample_bytree: float = 0.7
    reg_lambda: float = 1.0
    n_jobs: int = 8
    seed: int = 20260908


@dataclass
class Emulator:
    """One fitted head per quantity. Fitted on a training fold, applied to any climate."""

    quantities: tuple[str, ...]
    config: EmulatorConfig = field(default_factory=EmulatorConfig)
    heads: dict[str, object] = field(default_factory=dict)
    logged: set[str] = field(default_factory=set)

    def fit(self, x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]) -> Emulator:
        cfg = self.config
        for j, name in enumerate(self.quantities):
            target = y[:, j]
            ok = np.isfinite(target) & np.isfinite(x).all(axis=1)
            use_log = name in LOG_TARGETS and bool(np.all(target[ok] > 0))
            if use_log:
                self.logged.add(name)
                target = np.log(target)
            model = LGBMRegressor(
                objective="regression",
                n_estimators=cfg.n_estimators,
                learning_rate=cfg.learning_rate,
                num_leaves=cfg.num_leaves,
                min_child_samples=cfg.min_child_samples,
                subsample=cfg.subsample,
                subsample_freq=cfg.subsample_freq,
                colsample_bytree=cfg.colsample_bytree,
                reg_lambda=cfg.reg_lambda,
                n_jobs=cfg.n_jobs,
                random_state=cfg.seed,
                verbose=-1,
            )
            model.fit(x[ok], target[ok])
            self.heads[name] = model
        return self

    def predict(self, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        out = np.full((x.shape[0], len(self.quantities)), np.nan)
        for j, name in enumerate(self.quantities):
            model = self.heads[name]
            pred = np.asarray(model.predict(x))  # type: ignore[attr-defined]
            out[:, j] = np.exp(pred) if name in self.logged else pred
        return out

    def importances(self) -> dict[str, npt.NDArray[np.float64]]:
        """Split-gain importance per head. A diagnostic, never a claim about mechanism."""
        return {
            name: np.asarray(model.booster_.feature_importance(importance_type="gain"))  # type: ignore[attr-defined]
            for name, model in self.heads.items()
        }


def fit_out_of_fold(
    x_train_source: npt.NDArray[np.float64],
    y_train_source: npt.NDArray[np.float64],
    folds: npt.NDArray[np.int64],
    quantities: Sequence[str],
    apply_to: Sequence[npt.NDArray[np.float64]],
    *,
    config: EmulatorConfig | None = None,
    verbose: bool = True,
) -> tuple[list[npt.NDArray[np.float64]], dict[int, Emulator]]:
    """Fit once per fold and predict every held-out row, for one or more feature matrices.

    `apply_to` is a LIST of feature matrices with the same rows, so the SAME fitted head produces
    both ends of a response test -- a model fitted on the present-day climate, asked for a state
    under a warmed one. Predicting the two ends with two differently fitted models would let the
    fitting noise leak into the difference, which is precisely the quantity under test.

    Every row is held out exactly once, so the returned matrices are complete out-of-fold
    predictions and the statistic can be computed once over all of them.
    """
    cfg = config or EmulatorConfig()
    quantities = tuple(quantities)
    # Annotated rather than inferred: `np.full` comes back with a concrete 2-D shape type, which
    # `strict` will not accept for the declared shape-agnostic float64 return.
    preds: list[npt.NDArray[np.float64]] = [
        np.full((m.shape[0], len(quantities)), np.nan, dtype=np.float64) for m in apply_to
    ]
    models: dict[int, Emulator] = {}
    for f in np.unique(folds):
        test = folds == f
        train = ~test
        if verbose:
            print(
                f"  fold {f}: fit on {int(train.sum())} cells, predict {int(test.sum())}",
                flush=True,
            )
        model = Emulator(quantities, cfg).fit(x_train_source[train], y_train_source[train])
        models[int(f)] = model
        for i, features in enumerate(apply_to):
            preds[i][test] = model.predict(features[test])
    return preds, models
