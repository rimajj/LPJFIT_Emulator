"""The climate-only equilibrium map's apparatus, on synthetic data.

The null values it must return are derived on the cluster from the 6,000-run corpus, which CI does
not have. What CI can check is the arithmetic those values rest on: the skill statistic pins the
mean predictor at exactly zero, a perfect predictor at one, every null predicts every scored row,
and none of the forbidden columns is a feature.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_equilibrium_map import (
    FEATURES,
    FORBIDDEN,
    NULLS,
    QUANTITIES,
    null_predictions,
    skill,
)
from vegemu.score import blocked_spatial_folds

N_CELLS, N_POINTS = 40, 6


def _case() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(5)
    x = rng.normal(size=(N_CELLS, N_POINTS, len(FEATURES)))
    y = rng.normal(size=(N_CELLS, N_POINTS, len(QUANTITIES)))
    y[:3, :2, 4:] = np.nan  # treeless rows: traits undefined, forest-scale quantities present
    lon = rng.uniform(-180, 180, N_CELLS)
    lat = rng.uniform(-56, 84, N_CELLS)
    return x, y, lon, lat


def test_skill_is_pinned_at_zero_for_the_mean_and_one_for_the_truth() -> None:
    _, y, _, _ = _case()
    np.testing.assert_allclose(skill(y.copy(), y), 1.0)
    flat = y.reshape(-1, y.shape[-1])
    mean = np.broadcast_to(np.nanmean(flat, axis=0), y.shape).copy()
    np.testing.assert_allclose(skill(mean, y), 0.0, atol=1e-12)


def test_skill_refuses_an_arm_that_skipped_a_scored_row() -> None:
    _, y, _, _ = _case()
    pred = y.copy()
    pred[10, 0, 0] = np.nan
    with pytest.raises(AssertionError, match="unpredicted"):
        skill(pred, y)


def test_every_null_predicts_every_scored_row() -> None:
    x, y, lon, lat = _case()
    folds = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=42)
    preds = null_predictions(x, y, folds, lon, lat)
    assert set(preds) == set(NULLS)
    for p in preds.values():
        skill(p, y)  # raises if any scored row is left unpredicted


def test_no_forbidden_column_is_a_feature() -> None:
    assert not FORBIDDEN & set(FEATURES)
    assert "soil_code" in FEATURES
    assert "soildepth" in FEATURES
