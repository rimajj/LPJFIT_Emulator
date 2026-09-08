"""The leakage checks the pre-registrations promise, as executable assertions.

A leakage check written in a pre-registration and nowhere else is a promise. These are the same
claims as tests, so a change that breaks one turns the build red instead of quietly invalidating
two sealed experiments.

What is checked, and which failure each one is aimed at:

  * a held-out cell's spatial BLOCK never appears in training -- otherwise "blocked_spatial" is
    kfold_by_cell with extra steps, and every per-cell score becomes a spatial-interpolation score;
  * the feature matrix contains no latitude, longitude, cell id, CO2 or state column -- the
    geographic address is a NULL in both experiments, and a feature set that quietly contains it
    is how the predecessor's 0.748 turned out to be a 0.654 address score;
  * the nulls are deterministic, because their pre-registered `expected.value` is only meaningful
    if re-running them returns the same number.
"""

from __future__ import annotations

import numpy as np
import pytest

from vegemu import nulls as null_mod
from vegemu.corpus.climate import CLIMATE_FEATURES, NON_FEATURE_COLUMNS
from vegemu.score import (
    RESPONSE_QUANTITIES,
    SCORED_CONJUNCTIVE,
    blocked_spatial_folds,
    spatial_blocks,
    unit_sphere,
)

FORBIDDEN_SUBSTRINGS = ("lon", "lat", "cell", "co2", "stems", "agb", "wooddens", "seed", "year")


def _fake_grid(n: int = 4000, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    return rng.uniform(-180, 180, n), rng.uniform(-56, 84, n)


def test_blocks_are_never_split_across_folds() -> None:
    """The defining property of blocked folds. If this fails, the split kind is a lie."""
    lon, lat = _fake_grid()
    for degrees in (15.0, 5.0):
        folds = blocked_spatial_folds(lon, lat, k=5, degrees=degrees, seed=42)
        blocks = spatial_blocks(lon, lat, degrees)
        for block in np.unique(blocks):
            assert np.unique(folds[blocks == block]).size == 1, (
                f"block {block} at {degrees} deg is split across folds"
            )


def test_every_cell_is_held_out_exactly_once() -> None:
    """The statistic is computed once over the assembled out-of-fold prediction."""
    lon, lat = _fake_grid()
    folds = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=42)
    assert set(np.unique(folds)) == set(range(5))
    assert folds.size == lon.size


def test_folds_are_reproducible_and_seed_sensitive() -> None:
    lon, lat = _fake_grid()
    a = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=42)
    b = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=42)
    c = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=43)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_feature_set_contains_no_address_no_state_no_co2() -> None:
    """The one leakage check that would silently invalidate both experiments."""
    for name in CLIMATE_FEATURES:
        low = name.lower()
        for bad in FORBIDDEN_SUBSTRINGS:
            assert bad not in low, f"feature {name!r} looks like {bad!r}: a null or a target"
    # And the address IS available -- stored, deliberately, outside the feature list.
    assert "lon" in NON_FEATURE_COLUMNS
    assert "lat" in NON_FEATURE_COLUMNS
    assert not set(NON_FEATURE_COLUMNS) & set(CLIMATE_FEATURES)


def test_scored_sets_are_disjointly_typed_and_cover_the_acceptance_clauses() -> None:
    """Counts AND trait medians AND trait distributions -- the criterion is conjunctive."""
    assert "stems_per_patch" in SCORED_CONJUNCTIVE, "the count clause"
    medians = [q for q in SCORED_CONJUNCTIVE if q.endswith("_p50")]
    tails = [q for q in SCORED_CONJUNCTIVE if q.endswith(("_p10", "_p90"))]
    assert len(medians) >= 6, "the trait-median clause"
    assert len(tails) >= 12, "the trait-distribution clause needs both tails"
    assert len(set(SCORED_CONJUNCTIVE)) == len(SCORED_CONJUNCTIVE), "no duplicate quantity"
    assert set(RESPONSE_QUANTITIES) <= set(SCORED_CONJUNCTIVE) | {"soilc"}


def test_nulls_are_deterministic() -> None:
    """A pre-registered expected.value is only meaningful if the null repeats exactly."""
    rng = np.random.default_rng(3)
    lon, lat = _fake_grid(600, seed=3)
    y = rng.normal(size=(600, 4))
    x = rng.normal(size=(600, 8))
    tr = np.zeros(600, dtype=bool)
    tr[:400] = True
    te = ~tr

    for fn, args in (
        (null_mod.nearest_geographic, (lon[tr], lat[tr], y[tr], lon[te], lat[te])),
        (null_mod.nearest_analogue, (x[tr], y[tr], x[te])),
    ):
        assert np.array_equal(fn(*args), fn(*args))
    assert np.array_equal(null_mod.shuffled(y[te], 11), null_mod.shuffled(y[te], 11))
    assert not np.array_equal(null_mod.shuffled(y[te], 11), null_mod.shuffled(y[te], 12))


def test_shuffled_null_preserves_marginals() -> None:
    """Rows are permuted whole, so every marginal survives and only cell identity is destroyed."""
    rng = np.random.default_rng(5)
    y = rng.normal(size=(200, 3))
    s = null_mod.shuffled(y, 99)
    assert np.allclose(np.sort(s, axis=0), np.sort(y, axis=0))


def test_nearest_geographic_uses_the_sphere_not_the_lonlat_plane() -> None:
    """Cells either side of the date line are neighbours, not the furthest apart on Earth."""
    lon = np.array([179.75, -179.75, 0.0])
    lat = np.array([0.0, 0.0, 0.0])
    xyz = unit_sphere(lon, lat)
    d_across = float(np.linalg.norm(xyz[0] - xyz[1]))
    d_far = float(np.linalg.norm(xyz[0] - xyz[2]))
    assert d_across < d_far / 100

    y = np.array([[1.0], [2.0], [3.0]])
    tr = np.array([True, False, True])
    got = null_mod.nearest_geographic(lon[tr], lat[tr], y[tr], lon[~tr], lat[~tr])
    assert got[0, 0] == pytest.approx(1.0), "should copy its across-the-date-line neighbour"
