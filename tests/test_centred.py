"""The within-cell centred response statistic, and the property the two centred kill tests rest on.

THE PROPERTY. Any prediction that is constant within a cell -- "no change", the perfect per-cell
average change, or a model that cannot see which perturbation it is asked about -- must score
EXACTLY 0.0, not approximately. The blind model is the competitor these tests exist to beat, and it
is declared as a null whose pre-registered value is 0.0; if the arithmetic let it drift to 1e-16 the
claim would still hold, but "by construction" would be a figure of speech. So equality is asserted
with `==`, and the blind case is checked on a real LightGBM fit, not on a stand-in.

Also pinned: a perfect prediction scores 1; adding any per-cell offset to a prediction changes
nothing (that is what centring means); the statistic is the ordinary no-change skill applied to the
centred arrays; a missing prediction is filled neutrally and counted; an unscored pair cannot move
the score; and the noise ceiling is 1 without noise and matches a simulation with it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from lightgbm import LGBMRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vegemu.centred import (
    cell_mean_oracle,
    centre_within_cell,
    centred_ceiling,
    centred_per_level_and_pooled,
    skill_centred,
    skill_centred_mean,
)
from vegemu.score import skill_vs_no_change

N_CELLS, N_POINTS, N_Q = 30, 9, 4


def _truth(seed: int = 3, holes: float = 0.1) -> np.ndarray:
    """A corpus-shaped truth with per-cell offsets (what centring removes) and undefined pairs."""
    rng = np.random.default_rng(seed)
    offset = rng.normal(scale=3.0, size=(N_CELLS, 1, N_Q))
    pattern = rng.normal(size=(1, N_POINTS, N_Q))
    t = offset + pattern * rng.uniform(0.5, 2.0, size=(N_CELLS, 1, N_Q))
    t = t + rng.normal(scale=0.3, size=t.shape)
    t[rng.random(t.shape) < holes] = np.nan
    t[0, :, 1] = np.nan  # a cell with no scored pair for one quantity
    t[1, 1:, 2] = np.nan  # a cell with ONE scored pair: centred truth is identically 0
    return t


def test_any_within_cell_constant_prediction_scores_exactly_zero() -> None:
    t = _truth()
    rng = np.random.default_rng(8)
    # Awkward constants on purpose: 29 copies of 0.1 do not average to 0.1 in floating point.
    constants = rng.normal(size=(N_CELLS, 1, N_Q)) * 0.1 + 0.1
    for pred in (
        np.zeros_like(t),  # no change
        np.broadcast_to(constants, t.shape).copy(),
        cell_mean_oracle(t),  # the perfect per-cell average
    ):
        assert skill_centred_mean(pred, t) == 0.0
        assert (skill_centred(pred, t)[np.isfinite(skill_centred(pred, t))] == 0.0).all()
        per_level = centred_per_level_and_pooled(
            pred, t, [f"p{j}" for j in range(N_POINTS)], "abcd"
        )
        assert per_level["pooled"] == 0.0
        assert all(v == 0.0 for v in per_level["per_level"].values())  # type: ignore[attr-defined]


def test_a_constant_prediction_with_holes_still_scores_exactly_zero() -> None:
    """A missing prediction is filled with the cell's own mean prediction, so it stays constant."""
    t = _truth()
    pred = np.full_like(t, 0.3)
    pred[np.random.default_rng(1).random(t.shape) < 0.2] = np.nan
    assert skill_centred_mean(pred, t) == 0.0


def test_a_blind_lightgbm_model_scores_exactly_zero() -> None:
    """Identical features within a cell -> identical predictions -> exactly 0, on a real fit."""
    t = _truth(holes=0.0)
    rng = np.random.default_rng(4)
    cell_features = rng.normal(size=(N_CELLS, 3))
    x = np.repeat(cell_features[:, None, :], N_POINTS, axis=1).reshape(-1, 3)
    pred = np.empty_like(t)
    for q in range(N_Q):
        y = np.nan_to_num(t[:, :, q]).reshape(-1)
        model = LGBMRegressor(n_estimators=20, min_child_samples=5, verbose=-1).fit(x, y)
        pred[:, :, q] = model.predict(x).reshape(N_CELLS, N_POINTS)
    assert skill_centred_mean(pred, t) == 0.0


def test_a_perfect_prediction_scores_one() -> None:
    t = _truth()
    assert skill_centred_mean(t.copy(), t) == pytest.approx(1.0, abs=1e-12)


def test_a_per_cell_offset_changes_nothing() -> None:
    t = _truth()
    rng = np.random.default_rng(6)
    pred = t + rng.normal(scale=0.5, size=t.shape)
    shifted = pred + rng.normal(scale=10.0, size=(N_CELLS, 1, N_Q))
    np.testing.assert_allclose(skill_centred(shifted, t), skill_centred(pred, t), rtol=1e-10)


def test_it_is_the_no_change_skill_of_the_centred_arrays() -> None:
    t = _truth(holes=0.0)
    pred = t + np.random.default_rng(2).normal(size=t.shape)
    pc, tc, _ = centre_within_cell(pred, t)
    ref = skill_vs_no_change(pc.reshape(-1, N_Q), tc.reshape(-1, N_Q))
    np.testing.assert_allclose(skill_centred(pred, t), ref, rtol=1e-12)
    with np.errstate(invalid="ignore"):
        cell_means = np.nansum(tc, axis=1) / np.isfinite(tc).sum(axis=1)
    np.testing.assert_allclose(cell_means[np.isfinite(cell_means)], 0.0, atol=1e-12)


def test_a_missing_prediction_is_filled_with_the_cells_mean_and_counted() -> None:
    t = _truth(holes=0.0)
    pred = t + np.random.default_rng(9).normal(size=t.shape)
    holed = pred.copy()
    holed[5, 2, 0] = np.nan
    filled = pred.copy()
    others = np.delete(pred[5, :, 0], 2)
    filled[5, 2, 0] = others.mean()
    _, _, n_filled = centre_within_cell(holed, t)
    assert n_filled.tolist() == [1, 0, 0, 0]
    np.testing.assert_allclose(skill_centred(holed, t), skill_centred(filled, t), rtol=1e-12)


def test_an_unscored_pair_cannot_move_the_score() -> None:
    t = _truth()
    pred = t + np.random.default_rng(10).normal(size=t.shape)
    i, j, q = np.argwhere(~np.isfinite(t))[5]
    moved = pred.copy()
    moved[i, j, q] = 1e6
    np.testing.assert_allclose(skill_centred(moved, t), skill_centred(pred, t), rtol=1e-12)


def test_shapes_must_agree() -> None:
    with pytest.raises(ValueError, match="equal 3-d shapes"):
        centre_within_cell(np.zeros((2, 3, 4)), np.zeros((2, 3, 5)))


def test_the_ceiling_is_one_without_noise_and_matches_a_simulation_with_it() -> None:
    rng = np.random.default_rng(12)
    mu = rng.normal(size=(400, 1, 2)) * 5.0 + rng.normal(size=(400, 12, 2))
    sigma_sq = np.full((400, 2), 0.25)
    noisy = mu + rng.normal(scale=0.5, size=mu.shape)
    noisy = noisy - (
        mu[:, :1, :] + rng.normal(scale=0.5, size=(400, 1, 2))
    )  # minus a noisy control
    zero = centred_ceiling(noisy, np.zeros_like(sigma_sq), ("a", "b"))
    assert zero["rho0_independent"]["mean"] == pytest.approx(1.0)  # type: ignore[index]
    bound = centred_ceiling(noisy, sigma_sq, ("a", "b"))["rho0_independent"]["mean"]  # type: ignore[index]
    # A noise-free emulator predicts mu - mu_control; its centred score is what the bound bounds.
    achieved = skill_centred_mean(mu - mu[:, :1, :], noisy)
    assert bound == pytest.approx(achieved, abs=0.01)
