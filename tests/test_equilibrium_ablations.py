"""The soil-ablation and learning-curve apparatus for the climate-only equilibrium map.

The two sealed follow-ups run on the 6,000-run corpus, which CI does not have. What CI can check
is what their verdicts rest on:

  * the recipe options are ADDITIONS: the default recipe fits exactly what the sealed run fitted,
    and the subsampled path at 100 % returns the same array bit for bit;
  * the ablation removes exactly the five soil-texture columns and nothing else, and the placebo
    shuffles whole soil vectors between cells while leaving every other column alone;
  * the subsamples are nested, never touch the held-out fold, and are fixed by their seed;
  * the placebo stage reports differences only -- never the level whose value would be the answer;
  * the analytic nulls are computed as exactly 0.0.

The learner is shrunk to a few trees so this is quick; nothing else about the path is replaced.
That the job's single-threaded worker processes reproduce the sealed one-CPU fit is NOT tested here
(a spawned worker does not inherit a monkeypatched learner): the model stage checks it on the real
corpus, by requiring the sealed recipe to score 0.6075822354370696 again.
"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import exp_model_pilot_response
from exp_equilibrium_ablations import curve_report, recipes, soil_report
from exp_equilibrium_map import (
    FEATURES,
    QUANTITIES,
    SOIL_FEATURES,
    SOIL_INDEX,
    Recipe,
    fit_predict_oof,
    fit_predict_subsampled,
    model_features,
    model_predictions,
    training_cells,
)
from vegemu.score import blocked_spatial_folds

N_CELLS, N_POINTS, N_Q = 40, 4, 3


@pytest.fixture(autouse=True)
def _small_learner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(exp_model_pilot_response.PARAMS, "n_estimators", 8)
    monkeypatch.setitem(exp_model_pilot_response.PARAMS, "min_child_samples", 5)


def _case() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(3)
    x = rng.normal(size=(N_CELLS, N_POINTS, len(FEATURES)))
    x[:, :, list(SOIL_INDEX)] = rng.normal(size=(N_CELLS, 1, len(SOIL_INDEX)))  # soil per cell
    y = x[:, :, :N_Q] * 2.0 + rng.normal(scale=0.1, size=(N_CELLS, N_POINTS, N_Q))
    y[:2, :1, 2] = np.nan
    folds = blocked_spatial_folds(
        rng.uniform(-180, 180, N_CELLS), rng.uniform(-56, 84, N_CELLS), k=5, degrees=15.0, seed=42
    )
    return x, y, folds


def test_the_default_recipe_is_the_sealed_fit() -> None:
    x, y, folds = _case()
    assert Recipe().is_sealed and not Recipe(drop_soil=True).is_sealed
    assert model_features(x, Recipe()) is x
    sealed = fit_predict_oof(x, y, folds, QUANTITIES[:N_Q])
    np.testing.assert_array_equal(model_predictions(x, y, folds), sealed)
    np.testing.assert_array_equal(fit_predict_subsampled(x, y, folds, frac=1.0, seed=9), sealed)


def test_the_ablation_removes_exactly_the_five_soil_texture_columns() -> None:
    x, _, _ = _case()
    dropped = model_features(x, Recipe(drop_soil=True))
    assert dropped.shape[2] == len(FEATURES) - 5
    kept = [f for f in FEATURES if f not in SOIL_FEATURES]
    np.testing.assert_array_equal(dropped, x[:, :, [FEATURES.index(f) for f in kept]])
    assert "soildepth" in kept  # soil DEPTH stays: the question is about texture


def test_the_placebo_moves_whole_soil_vectors_between_cells_and_nothing_else() -> None:
    x, _, _ = _case()
    moved = model_features(x, Recipe(permute_soil_seed=4))
    other = [i for i in range(len(FEATURES)) if i not in SOIL_INDEX]
    np.testing.assert_array_equal(moved[:, :, other], x[:, :, other])
    soil_in, soil_out = x[:, 0, list(SOIL_INDEX)], moved[:, 0, list(SOIL_INDEX)]
    perm = np.random.default_rng(4).permutation(N_CELLS)
    np.testing.assert_array_equal(soil_out, soil_in[perm])
    assert (moved[:, :, list(SOIL_INDEX)] == moved[:, :1, list(SOIL_INDEX)]).all()
    with pytest.raises(ValueError, match="two different arms"):
        model_features(x, Recipe(drop_soil=True, permute_soil_seed=1))


def test_subsamples_are_nested_seeded_and_never_touch_the_held_out_fold() -> None:
    _, _, folds = _case()
    for fold in np.unique(folds):
        pool = int((folds != fold).sum())
        masks = [training_cells(folds, int(fold), f, seed=3) for f in (0.25, 0.5, 0.75, 1.0)]
        for small, big in pairwise(masks):
            assert (small <= big).all()
        assert all(not (m & (folds == fold)).any() for m in masks)
        assert [int(m.sum()) for m in masks] == [
            max(1, round(f * pool)) for f in (0.25, 0.5, 0.75, 1)
        ]
        again = training_cells(folds, int(fold), 0.5, seed=3)
        np.testing.assert_array_equal(again, masks[1])
        assert not np.array_equal(training_cells(folds, int(fold), 0.5, seed=4), masks[1])


def _fake_scored(todo: list[Recipe]) -> dict[Recipe, dict[str, object]]:
    rng = np.random.default_rng(1)
    out: dict[Recipe, dict[str, object]] = {}
    for rec in todo:
        v = float(rng.uniform(0.4, 0.6))
        out[rec] = {
            "pooled": v,
            "per_quantity": {q: v for q in QUANTITIES},
            "per_level": {"p0": v},
            "band": {"conjunctive": 0.0, "per_quantity": {q: 0.5 for q in QUANTITIES}},
        }
    return out


@pytest.mark.parametrize("study", ["soil", "curve"])
def test_the_placebo_stage_reports_differences_only(study: str) -> None:
    todo = recipes(study, "placebo")
    assert Recipe() not in todo  # the sealed recipe is never refitted before the seal
    build = soil_report if study == "soil" else curve_report
    rep = build(_fake_scored(todo), "placebo")
    assert "levels" not in rep and "curve" not in rep and "model" not in rep["arms"]
    text = repr(rep)
    for rec, scored in _fake_scored(todo).items():
        assert repr(scored["pooled"]) not in text, rec


def test_the_model_stage_computes_the_analytic_nulls_as_exactly_zero() -> None:
    soil = soil_report(_fake_scored(recipes("soil", "model")), "model")
    assert soil["arms"]["no_soil_texture"] == 0.0  # type: ignore[index]
    assert set(soil["arms"]) == {"model", "no_soil_texture", "soil_texture_permuted_max"}  # type: ignore[arg-type]
    curve = curve_report(_fake_scored(recipes("curve", "model")), "model")
    assert curve["arms"]["no_further_gain"] == 0.0  # type: ignore[index]
    assert set(curve["arms"]) == {"model", "no_further_gain", "subsample_noise"}  # type: ignore[arg-type]
    assert curve["arms"]["subsample_noise"] >= 0.0  # type: ignore[index]
