"""Cell selection: the properties that make the corpus a design rather than a pile of runs.

The load-bearing ones, in order of what they would cost if they broke:

* `test_every_populated_tile_gets_a_cell` -- if a tile can be left out, the corpus reinherits the
  density bias the stratification exists to remove, and a spatially blocked fold silently becomes a
  spatial-interpolation score.
* `test_selection_is_deterministic` -- a pre-registration cites the design by hash and has to be
  able to regenerate it. Nothing here may draw a random number.
* `test_no_tile_exceeds_the_cap` -- the maximin fill must not spend its budget inside one climate.

The synthetic tests build a small frame by hand, so the geometry is checkable by eye. The real-data
tests run the actual 200-cell pilot choice against the per-cell tables on `/p` and are skipped when
they are not mounted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from vegemu.corpus.select import (
    DESIGN_COORDS,
    MAX_PER_TILE,
    TILE_DEGREES,
    Selection,
    _maximin_fill,
    _tile_medoids,
    eligible_cells,
    pilot_cells,
    standardise,
)
from vegemu.paths import paths
from vegemu.score import spatial_blocks


def _frame(n: int = 60, ntile: int = 6) -> pl.DataFrame:
    """A synthetic eligible-cell frame: `n` cells dealt round-robin over `ntile` tiles."""
    rng = np.random.default_rng(0)
    return pl.DataFrame(
        {
            "cell": np.arange(n),
            "lon": rng.uniform(-180, 180, n),
            "lat": rng.uniform(-60, 70, n),
            "tile": np.arange(n) % ntile,
            "stems_total": np.full(n, 100.0),
            **{name: rng.uniform(1.0, 50.0, n) for name in DESIGN_COORDS},
        }
    )


def test_standardise_is_robust_to_a_long_tail() -> None:
    """One extreme value must not decide which cells a maximin fill considers far apart."""
    df = _frame()
    z_before = standardise(df)
    spiked = df.with_columns(
        pr_ann=pl.when(pl.col("cell") == 0).then(1e6).otherwise(pl.col("pr_ann"))
    )
    z_after = standardise(spiked)
    # Every cell but the spiked one keeps its coordinate: median and IQR ignore the tail.
    assert np.allclose(z_before[1:], z_after[1:], atol=1e-9)


def test_standardise_centres_and_scales_each_coordinate() -> None:
    z = standardise(_frame(200, 8))
    assert z.shape == (200, len(DESIGN_COORDS))
    assert np.allclose(np.median(z, axis=0), 0.0, atol=1e-9)
    for j in range(z.shape[1]):
        iqr = np.percentile(z[:, j], 75) - np.percentile(z[:, j], 25)
        assert iqr == pytest.approx(1.0, abs=1e-9)


def test_pr_ann_enters_logged() -> None:
    """Precipitation spans 0 to 9243 mm; unlogged it would dominate the other four coordinates."""
    df = _frame().with_columns(pr_ann=pl.Series(np.linspace(0.0, 9000.0, 60)))
    z = standardise(df)
    j = DESIGN_COORDS.index("pr_ann")
    # A logged coordinate is concave in the raw value: equal raw steps give shrinking z steps.
    steps = np.diff(np.sort(z[:, j]))
    assert steps[0] > steps[-1] * 2


def test_tile_medoids_pick_one_per_tile_and_it_is_central() -> None:
    df = _frame(60, 6)
    coords = standardise(df)
    rows = _tile_medoids(df, coords, exclude=set())
    tiles = df["tile"].to_numpy()
    assert len(rows) == 6
    assert sorted(tiles[r] for r in rows) == list(range(6))
    # The medoid must be no farther from its tile's median than the tile's mean member is.
    for r in rows:
        block = coords[tiles == tiles[r]]
        med = np.median(block, axis=0)
        assert np.linalg.norm(coords[r] - med) <= np.linalg.norm(block - med, axis=1).mean()


def test_tile_medoids_skip_a_tile_a_forced_cell_already_covers() -> None:
    df = _frame(60, 6)
    coords = standardise(df)
    forced_cell = int(df["cell"][0])
    forced_tile = int(df["tile"][0])
    rows = _tile_medoids(df, coords, exclude={forced_cell})
    tiles = df["tile"].to_numpy()
    assert forced_tile not in [int(tiles[r]) for r in rows]
    assert len(rows) == 5


def test_maximin_fill_spreads_out() -> None:
    """The fill must add the cell farthest from what is already chosen, not the next cell along.

    `pr_ann` is held CONSTANT here so the geometry is the plain linear one and the answer can be
    read off by eye. Left on the same ramp as the others it enters logged, which stretches the low
    end and pulls the midpoint down to a quarter of the range -- correct behaviour, but it makes the
    test a test of the log transform rather than of the fill.
    """
    n = 40
    ramp = {name: pl.Series(np.linspace(0.0, 100.0, n)) for name in DESIGN_COORDS}
    ramp["pr_ann"] = pl.Series(np.full(n, 500.0))
    df = _frame(n, ntile=1).with_columns(**ramp)
    coords = standardise(df)
    cell = df["cell"].to_numpy()
    tiles = np.zeros(n, dtype=np.int64)
    # Start from one end; the farthest point is the other end.
    added = _maximin_fill(coords, cell, tiles, chosen=[0], want=2)
    assert added[0] == n - 1
    # The second addition is the midpoint of the remaining gap, not a neighbour of either end.
    assert abs(added[1] - (n - 1) / 2) <= 1


def test_no_tile_exceeds_the_cap() -> None:
    n, ntile = 80, 4
    df = _frame(n, ntile)
    coords = standardise(df)
    cell, tiles = df["cell"].to_numpy(), df["tile"].to_numpy()
    added = _maximin_fill(coords, cell, tiles, chosen=[], want=n)
    counts = np.bincount(tiles[added], minlength=ntile)
    assert counts.max() <= MAX_PER_TILE
    # And it stops rather than breaking the cap to spend the budget.
    assert len(added) == ntile * MAX_PER_TILE


def test_maximin_fill_is_deterministic() -> None:
    df = _frame(80, 4)
    coords = standardise(df)
    cell, tiles = df["cell"].to_numpy(), df["tile"].to_numpy()
    first = _maximin_fill(coords, cell, tiles, chosen=[3], want=8)
    second = _maximin_fill(coords, cell, tiles, chosen=[3], want=8)
    assert first == second


def test_maximin_fill_of_nothing_is_nothing() -> None:
    df = _frame()
    coords = standardise(df)
    assert _maximin_fill(coords, df["cell"].to_numpy(), df["tile"].to_numpy(), [0], 0) == []


# ------------------------------------------------------------------------------------------------
# Real files: the actual 200-cell pilot choice
# ------------------------------------------------------------------------------------------------


def _have_tables() -> bool:
    try:
        root = Path(str(paths()["scratch"]["corpus"])) / "v0"
        return (root / "climate_historical.parquet").exists()
    except (KeyError, TypeError):
        return False


real_data = pytest.mark.skipif(not _have_tables(), reason="needs the v0 per-cell tables under /p")


@real_data
@pytest.mark.needs_real_data
def test_eligible_cells_are_tree_bearing_and_carry_every_coordinate() -> None:
    df = eligible_cells()
    assert df.height > 50_000
    assert (df["stems_total"] > 0).all()
    for name in DESIGN_COORDS:
        assert np.isfinite(df[name].to_numpy()).all()


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_pilot_selection_has_the_promised_shape() -> None:
    sel = pilot_cells(200)
    assert isinstance(sel, Selection)
    assert sel.table.height == 200
    assert sel.table["cell"].n_unique() == 200


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_every_populated_tile_gets_a_cell() -> None:
    """The whole point of the stratification: no tile may be left with no cell at all."""
    sel = pilot_cells(200)
    assert sel.tiles_covered == sel.tiles_populated


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_the_biome_reference_cells_are_in_the_design() -> None:
    """The direction test's five cells, including the two results nobody has explained."""
    sel = pilot_cells(200)
    chosen = set(sel.cells())
    for name, cell in paths()["cells"]["biome"].items():
        assert int(cell) in chosen, f"{name}={cell} missing from the pilot design"


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_selection_is_deterministic() -> None:
    """A pre-registration cites the design by hash, so it must be a function of the data alone."""
    assert pilot_cells(200).cells() == pilot_cells(200).cells()


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_tiles_agree_with_the_scorer_that_will_make_the_folds() -> None:
    """The corpus and the folds must compute a tile the same way, or blocking means nothing."""
    sel = pilot_cells(200)
    want = spatial_blocks(
        sel.table["lon"].to_numpy(), sel.table["lat"].to_numpy(), TILE_DEGREES
    )
    assert np.array_equal(sel.table["tile"].to_numpy(), want)


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_a_tier_too_small_to_cover_the_tiles_is_refused() -> None:
    """Silently dropping tiles would be exactly the density bias the design exists to remove."""
    with pytest.raises(ValueError, match="cannot cover"):
        pilot_cells(50)
