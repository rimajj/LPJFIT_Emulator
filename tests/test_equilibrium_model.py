"""The persisted equilibrium map, on synthetic data.

What CI cannot check is the sealed number itself -- that needs the 6,000-run corpus, and
`scripts/fit_equilibrium_map.py` reproduces it on the cluster. What CI can check is everything
that number's reproduction rests on: the recipe is the sealed one (same hyperparameters, same
features, same transforms, same treeless rule), a held-out fold's own truth never reaches its
prediction, a saved map loads back to bit-identical predictions, spreading fits across processes
changes nothing, and post-processing does exactly the four things it claims and reports each.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diag_equilibrium_map as diag
import exp_equilibrium_map as sealed
from exp_model_pilot_response import PARAMS as SEALED_PARAMS
from fit_equilibrium_map import nn_rms, outside
from vegemu.corpus.state import STATE_COLUMNS
from vegemu.models.equilibrium import (
    FEATURES,
    HEADS,
    LOG1P_HEADS,
    PARAMS,
    SEALED_HEADS,
    SHARE_HEADS,
    TREED_HEADS,
    EquilibriumMap,
    feature_matrix,
    fit_out_of_fold,
    forward,
    postprocess,
    targets_from_frame,
    treeless_threshold,
)
from vegemu.score import SCORED_CONJUNCTIVE

SMALL = {**PARAMS, "n_estimators": 15, "min_child_samples": 5}
SUBSET = ("stems_per_patch", "agb", "height_p10", "height_p50", "height_p90", *SHARE_HEADS)


def _problem(n: int = 240, seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Features in FEATURES order and natural-scale targets for SUBSET, with some treeless rows."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(FEATURES)))
    stems = np.exp(1.5 + x[:, 0] + 0.3 * rng.normal(size=n))
    stems[:20] = 0.0
    h50 = 10 + 3 * x[:, 1] + rng.normal(size=n)
    shares = rng.dirichlet(np.ones(len(SHARE_HEADS)), size=n)
    y = np.column_stack(
        [stems, 100 * stems, h50 - 4, h50, h50 + 4, *(shares[:, i] for i in range(shares.shape[1]))]
    )
    y[:20, 2:] = np.nan  # treeless: traits and shares undefined
    return x, y


def test_the_recipe_is_the_sealed_one() -> None:
    assert PARAMS == SEALED_PARAMS
    assert FEATURES == sealed.FEATURES
    assert SEALED_HEADS == SCORED_CONJUNCTIVE == sealed.QUANTITIES
    assert HEADS[: len(SEALED_HEADS)] == SEALED_HEADS
    assert LOG1P_HEADS & set(SEALED_HEADS) == sealed.LOG_QUANTITIES
    y = np.array([-1.0, 0.0, 0.5, 3.0, 1e4])
    for h in SEALED_HEADS:
        np.testing.assert_array_equal(forward(h, y), sealed.forward(h, y))


def test_a_forbidden_or_state_feature_is_refused() -> None:
    for bad in ("lat", "dtemp_k", "cell", "point", "tile", "agb", "co2_ppm"):
        with pytest.raises(AssertionError):
            EquilibriumMap(features=(*FEATURES, bad))
    frame = pl.DataFrame({f: [0.0] for f in (*FEATURES, "lon")})
    assert feature_matrix(frame).shape == (1, len(FEATURES))  # extra columns are simply not read
    with pytest.raises(AssertionError):
        feature_matrix(frame, (*FEATURES, "lon"))


@pytest.mark.parametrize(
    "col",
    sorted(
        (set(STATE_COLUMNS) | {"truth_stems_total", "restart_year", "restart_bytes", "name"})
        - set(FEATURES)
    ),
)
def test_every_state_and_bookkeeping_column_is_refused(col: str) -> None:
    """Not only the 42 heads: `stems_total`, `vegc`, the height bins and the age quantiles are the
    forest itself, and a guard that listed only the heads let all of them through."""
    with pytest.raises(AssertionError):
        EquilibriumMap(features=(*FEATURES, col))
    EquilibriumMap(features=FEATURES[:10])  # a subset of the climate and soil is still allowed


def test_treeless_rows_have_no_traits_and_no_shares() -> None:
    frame = pl.DataFrame(
        {
            "stems_total": [0.0, 5.0],
            **{h: [0.0, 1.0] for h in HEADS},
        }
    )
    y = targets_from_frame(frame)
    for j, h in enumerate(HEADS):
        assert np.isnan(y[0, j]) == (h in TREED_HEADS), h
        assert y[1, j] == 1.0
    assert set(SHARE_HEADS) <= TREED_HEADS
    assert not {"stems_per_patch", "agb", "lai", "soilc", "litterc"} & TREED_HEADS


def test_the_treeless_threshold_sits_between_zero_and_the_sparsest_forest() -> None:
    t = treeless_threshold(np.array([0.0, 0.0, 3.28, 40.0]))
    assert 0.0 < t < 3.28
    assert np.log1p(t) == pytest.approx(0.5 * np.log1p(3.28))


def test_postprocess_does_four_things_and_reports_each() -> None:
    heads = SUBSET
    raw = np.array(
        [
            # stems agb   p10  p50  p90   seven shares
            [20.0, -5.0, 12.0, 10.0, 15.0, -0.1, 0.3, 0.3, 0.2, 0.1, 0.1, 0.2],
            [0.5, 3.0, 9.0, 10.0, 11.0, 0.2, 0.2, 0.2, 0.1, 0.1, 0.1, 0.1],
        ]
    )
    out, rep = postprocess(raw, heads, treeless_below=1.0)
    assert out[0, 1] == 0.0 and rep.negative_clipped["agb"] == 1  # 1. clip
    assert rep.treeless_rows == 1 and np.isnan(out[1, 2:]).all()  # 2. treeless
    assert out[1, 1] == 3.0  # ... but a forest-scale head is left alone
    np.testing.assert_array_equal(out[0, 2:5], [10.0, 12.0, 15.0])  # 3. sorted
    assert rep.crossed_3_knots["height"] == 1
    shares = out[0, 5:]
    assert (shares >= 0).all() and shares.sum() == pytest.approx(1.0)  # 4. renormalised
    assert rep.share_negative_clipped == 1
    np.testing.assert_array_equal(raw[0, 2:5], [12.0, 10.0, 15.0])  # the input is untouched


def test_a_negative_trait_quantile_is_floored_at_zero_after_its_crossing_is_counted() -> None:
    """A negative leaf longevity or rooting depth has no meaning; the heads produce them where they
    extrapolate. The crossing count must still describe the heads, not the floored values."""
    heads = SUBSET
    #                 stems agb  p10   p50   p90   seven shares
    raw = np.array([[20.0, 5.0, -0.5, -1.0, 15.0, 0.2, 0.2, 0.2, 0.1, 0.1, 0.1, 0.1]])
    out, rep = postprocess(raw, heads, treeless_below=1.0)
    np.testing.assert_array_equal(out[0, 2:5], [0.0, 0.0, 15.0])
    assert rep.trait_negative_clipped == {"height_p10": 1, "height_p50": 1, "height_p90": 0}
    assert rep.crossed_3_knots["height"] == 1  # -0.5 > -1.0 crossed before anything was floored
    only_median, rep1 = postprocess(np.array([[20.0, -2.0]]), ("stems_per_patch", "height_p50"), 1)
    assert only_median[0, 1] == 0.0 and rep1.trait_negative_clipped == {"height_p50": 1}


def test_a_held_out_fold_never_sees_its_own_truth() -> None:
    x, y = _problem()
    folds = np.arange(x.shape[0]) % 4
    base = fit_out_of_fold(x, y, folds, heads=SUBSET, params=SMALL)
    poisoned = y.copy()
    poisoned[folds == 0] *= 7.0
    moved = fit_out_of_fold(x, poisoned, folds, heads=SUBSET, params=SMALL)
    np.testing.assert_array_equal(moved[folds == 0], base[folds == 0])
    assert not np.array_equal(moved[folds != 0], base[folds != 0])
    assert np.isfinite(base).all()  # every held-out row predicted, treeless ones included


def test_a_saved_map_loads_back_to_identical_predictions(tmp_path: Path) -> None:
    x, y = _problem()
    em = EquilibriumMap(heads=SUBSET, params=SMALL).fit(x, y)
    assert em.text_roundtrip_max_abs == 0.0
    em.save(tmp_path, basis={"what": "synthetic"})
    back = EquilibriumMap.load(tmp_path)
    assert back.heads == em.heads and back.features == em.features
    assert back.treeless_below == em.treeless_below
    np.testing.assert_array_equal(back.predict_raw(x), em.predict_raw(x))
    a, _ = back.predict(x)
    b, _ = em.predict(x)
    np.testing.assert_array_equal(a, b)
    head = tmp_path / "heads" / "agb.txt"
    head.write_text(head.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        EquilibriumMap.load(tmp_path)


@pytest.mark.slow
def test_spreading_fits_across_processes_changes_nothing() -> None:
    x, y = _problem()
    folds = np.arange(x.shape[0]) % 3
    one = fit_out_of_fold(x, y, folds, heads=SUBSET[:3], params=SMALL, workers=1)
    two = fit_out_of_fold(x, y, folds, heads=SUBSET[:3], params=SMALL, workers=2)
    np.testing.assert_array_equal(one, two)


def test_the_envelope_distance_is_the_nearest_neighbour_distance() -> None:
    rng = np.random.default_rng(11)
    ref, query = rng.normal(size=(300, 9)), rng.normal(size=(50, 9)) * 2
    want, _ = cKDTree(ref).query(query, k=1)
    np.testing.assert_allclose(nn_rms(query, ref, chunk=7), want / np.sqrt(9), rtol=1e-9)
    lo, hi = ref.min(axis=0), ref.max(axis=0)
    flags = outside(np.array([[np.nan, *lo[1:]], [*hi[:-1], hi[-1] + 1]]), lo, hi)
    assert flags.sum(axis=1).tolist() == [0, 1]  # a missing value is not an extrapolation


def test_the_within_cell_split_adds_up_to_the_whole_error() -> None:
    rng = np.random.default_rng(2)
    cells = np.repeat(np.arange(20), 6)
    t = rng.normal(size=cells.size) + cells * 0.3
    p = t + rng.normal(size=cells.size) * 0.5 + (cells % 3) * 0.2
    zt = np.full((cells.size, len(HEADS)), np.nan)
    zr = np.zeros_like(zt)
    zt[:, 0], zr[:, 0] = t, p
    wb = diag.within_between({"zt": zt, "zr": zr, "cell": cells})["stems_per_patch"]
    whole, _ = diag.var_explained(p, t)
    share = wb["truth_share_between_cells"]
    parts = share * wb["skill_between_cells"] + (1 - share) * wb["skill_within_cell"]
    assert parts == pytest.approx(whole)
    assert 0.0 < wb["error_share_between_cells"] < 1.0
