"""The WITHIN-CELL CENTRED response skill: a score a model blind to the perturbation cannot pass.

WHY THIS EXISTS. Both kill tests score `1 - SUM(dpred - dtrue)^2 / SUM(dtrue^2)` on the change of a
cell's forest between its control climate and each of its 29 perturbed climates. Both pass. But a
model that is shown the cell's starting forest and NOT told which perturbation it is being asked
about scores 64.8 % of the warming headline (0.362322 of 0.558968) and 69 % of the species-mix one
(0.307940 of 0.445852) -- and on the species mix that blind model clears the bar by itself. Most of
each headline is "knowing what kind of forest this is lets you guess its typical change", which
every one of the information-free nulls is denied. So the competitor the model actually has to beat
is BLINDNESS, and the uncentred statistic cannot express that without a bar near the blind arm.

THE CONSTRUCTION. For each cell and quantity, subtract the cell's own MEAN change over its scored
design points from every change, on both sides:

    dtrue~[i, j] = dtrue[i, j] - mean_j dtrue[i, j]        dpred~ likewise, over the SAME points
    skill       = 1 - SUM (dpred~ - dtrue~)^2 / SUM dtrue~^2

What survives is how the response DIFFERS between perturbations at one place. Any prediction that
is constant within a cell -- a model blind to the perturbation (its 29 rows per cell have identical
features, so identical predictions), "no change", or even the PERFECT per-cell average change --
scores exactly 0.0. That is the property the tests pin, bit for bit, not to a tolerance.

⚠ THE DISCLOSURE THAT TRAVELS WITH EVERY CENTRED NUMBER. By construction the centring throws
away the response to the DESIGN-AVERAGE perturbation: a model that got every cell's average change
exactly right and nothing else scores 0, and one that got it badly wrong but the differences right
scores 1. So a centred score is never a replacement for the uncentred headline. It is quoted BESIDE
it, as the part of the response that no knowledge of the starting forest alone can buy.

TWO RULES FIXED HERE, NOT BY EACH CALLER.

* THE SCORED SET IS WHERE THE TRUTH EXISTS. A trait median or a type share is undefined in a
  treeless arm; those (cell, point) pairs are not scored and do not enter either cell mean.
* A MISSING PREDICTION ON A SCORED PAIR IS FILLED WITH THE CELL'S OWN MEAN PREDICTION over its other
  scored points. That is the NEUTRAL filling under centring -- the filled pair then contributes
  exactly zero to the centred prediction -- exactly as "no change" is the neutral filling of the
  uncentred composition score. Dropping the pair instead would let an arm that declines the hard
  pairs be scored on an easier subset than its competitors. The fill count is returned, so it can be
  reported beside the score.

EXACTNESS. A plain `x - mean(x)` of a constant vector is not exactly zero in floating point (29
copies of 0.1 do not average to 0.1). So the prediction is first shifted by one of its own values:
a constant vector then becomes exactly zero BEFORE any mean is taken, and stays exactly zero.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


def _first_finite(values: Array, finite: npt.NDArray[np.bool_]) -> Array:
    """Along axis 1, the first value where `finite` holds; 0.0 where it never does."""
    first = np.argmax(finite, axis=1)  # (cells, quantities); 0 where no True, masked below
    picked = np.take_along_axis(values, first[:, None, :], axis=1)[:, 0, :]
    out: Array = np.where(finite.any(axis=1), picked, 0.0)
    return out


def centre_within_cell(pred: Array, true: Array) -> tuple[Array, Array, npt.NDArray[np.int64]]:
    """`(pred~, true~, n_filled)`, centred per (cell, quantity) over the pairs where TRUE exists.

    Shapes: `pred` and `true` are (cells, points, quantities); the centred arrays have the same
    shape and are NaN exactly where `true` is not finite. `n_filled` is the per-quantity count of
    scored pairs whose prediction was missing and was filled neutrally (see the module docstring).
    """
    if pred.shape != true.shape or true.ndim != 3:
        raise ValueError(f"pred {pred.shape} and true {true.shape} must be equal 3-d shapes")
    scored = np.isfinite(true)
    n = scored.sum(axis=1)  # (cells, quantities)

    with np.errstate(invalid="ignore", divide="ignore"):
        t_sum = np.where(scored, true, 0.0).sum(axis=1)
        t_mean = np.where(n > 0, t_sum / np.maximum(n, 1), 0.0)
        true_c: Array = np.where(scored, true - t_mean[:, None, :], np.nan)

        have = scored & np.isfinite(pred)
        k = have.sum(axis=1)
        ref = _first_finite(pred, have)
        shifted = np.where(have, pred - ref[:, None, :], 0.0)
        fill = np.where(k > 0, shifted.sum(axis=1) / np.maximum(k, 1), 0.0)
        # A constant prediction is exactly 0 here already, so `fill` and the mean below are exactly
        # 0 too, and the centred prediction stays exactly 0 -- the whole point of the shift.
        filled = np.where(have, shifted, np.where(scored, fill[:, None, :], 0.0))
        p_mean = np.where(n > 0, filled.sum(axis=1) / np.maximum(n, 1), 0.0)
        pred_c: Array = np.where(scored, filled - p_mean[:, None, :], np.nan)

    n_filled: npt.NDArray[np.int64] = (scored & ~have).sum(axis=(0, 1)).astype(np.int64)
    return pred_c, true_c, n_filled


def _ratio_skill(pred_c: Array, true_c: Array) -> Array:
    """Per last-axis column, `1 - SUM(p - t)^2 / SUM t^2` over the finite pairs; NaN if the
    denominator is 0.

    Takes arrays of any leading shape, flattened, so the pooled and the per-level scores are the
    SAME arithmetic on different slices.
    """
    p = pred_c.reshape(-1, pred_c.shape[-1])
    t = true_c.reshape(-1, true_c.shape[-1])
    out = np.full(t.shape[1], np.nan)
    for j in range(t.shape[1]):
        m = np.isfinite(t[:, j])
        denom = float((t[m, j] ** 2).sum())
        if denom <= 0.0:
            continue
        out[j] = 1.0 - float(((p[m, j] - t[m, j]) ** 2).sum()) / denom
    return out


def skill_centred(pred: Array, true: Array) -> Array:
    """Per-quantity centred skill, shape (quantities,); NaN for a quantity with no within-cell
    spread at all."""
    pred_c, true_c, _ = centre_within_cell(pred, true)
    return _ratio_skill(pred_c, true_c)


def skill_centred_mean(pred: Array, true: Array) -> float:
    """The unweighted mean over quantities of `skill_centred`: the blessed statistic of both
    centred kill tests. Unweighted for the uncentred statistic's reason: no quantity's variance
    rules."""
    return float(np.nanmean(skill_centred(pred, true)))


def centred_per_level_and_pooled(
    pred: Array, true: Array, points: Sequence[str], quantities: Sequence[str]
) -> dict[str, object]:
    """The centred statistic pooled, per quantity, and per design point, plus the fill count.

    The same report shape as the uncentred `_per_level_and_pooled` of the kill-test scripts, so
    the decision arithmetic (`decide`) reads either. The per-level score at point j is the ratio
    over the cells' centred pairs AT j -- the centring itself always uses every scored point of the
    cell, so a level's score is never computed about a different mean from the pooled one.
    """
    pred_c, true_c, n_filled = centre_within_cell(pred, true)
    per_q = _ratio_skill(pred_c, true_c)
    return {
        "pooled": float(np.nanmean(per_q)),
        "per_quantity": {q: float(v) for q, v in zip(quantities, per_q, strict=True)},
        "per_level": {
            point: float(np.nanmean(_ratio_skill(pred_c[:, [j]], true_c[:, [j]])))
            for j, point in enumerate(points)
        },
        "predictions_filled_neutrally": {
            q: int(v) for q, v in zip(quantities, n_filled, strict=True)
        },
    }


def cell_mean_oracle(true: Array) -> Array:
    """Every pair gets the cell's TRUE mean change over its scored points. A demonstration.

    It reads the held-out truth, by design: it is the best any prediction that is constant within a
    cell can possibly do, and under the centred statistic it scores exactly 0.0. Declared as a null
    so that "even a perfect per-cell average buys nothing here" is a measured row of the result
    table, not a sentence.
    """
    scored = np.isfinite(true)
    n = scored.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, np.where(scored, true, 0.0).sum(axis=1) / np.maximum(n, 1), np.nan)
    out: Array = np.repeat(mean[:, None, :], true.shape[1], axis=1)
    return out


def centred_ceiling(true: Array, sigma_sq: Array, quantities: Sequence[str]) -> dict[str, object]:
    """The most a noise-free emulator could score on the CENTRED target. A bound, not a number.

    Write each run as X = mu + eps. The paired change is dtrue[i, j] = dmu[i, j] + eps[i, j] -
    eps[i, 0]; the CONTROL's noise eps[i, 0] is the same in all of a cell's pairs, so the centring
    removes it exactly. What is left is eps[i, j] - mean_j eps[i, j], whose expected sum of squares
    over a cell's n scored points is sigma^2 (1 - rho)(n - 1), with rho the correlation between two
    ARMS' noise (they share a seed). So

        ceiling(rho) = 1 - SUM_i sigma_i^2 (1 - rho)(n_i - 1) / SUM dtrue~^2 .

    `sigma_sq` is (cells, quantities), the per-run noise variance; a cell with no estimate is left
    out of the noise sum AND of the denominator, so the bound is taken over one set of cells.
    rho = 0 is the conservative lower bound.
    """
    _, true_c, _ = centre_within_cell(np.zeros_like(true), true)
    scored = np.isfinite(true)
    n = scored.sum(axis=1)
    out: dict[str, object] = {}
    for rho, name in ((0.0, "rho0_independent"), (0.5, "rho0.5_partial")):
        per_q = np.full(len(quantities), np.nan)
        for j in range(len(quantities)):
            ok = np.isfinite(sigma_sq[:, j]) & (n[:, j] > 1)
            ss = float(np.nansum(true_c[ok, :, j] ** 2))
            if ss <= 0.0:
                continue
            noise = float((sigma_sq[ok, j] * (1.0 - rho) * (n[ok, j] - 1)).sum())
            per_q[j] = 1.0 - noise / ss
        out[name] = {
            "mean": float(np.nanmean(per_q)),
            "per_quantity": {q: float(v) for q, v in zip(quantities, per_q, strict=True)},
        }
    return out
