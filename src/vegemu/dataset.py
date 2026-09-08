"""Assembling the corpus into the arrays an experiment scores — one loader, one basis.

Both experiments need the same three things and must agree on them exactly, or the nulls derived by
line X are not the nulls line T measures:

    the FEATURE matrix        the climate summary, with the address and the fold keys excluded
    the TRUTH and the BAND    the two-seed mean, and max(10 %, that cell's own two-seed spread)
    the FOLDS                 whole spatial blocks held out together

THE CELL SET IS AN EXPLICIT CHOICE AND IT IS NOT "ALL 67,420". A cell with no trees has no trait
median, so a conjunctive trait test is undefined there; including such cells would let a model
score by predicting "no forest" in the Sahara, which is a real skill but not the one under test.
The scored set is therefore the cells that are TREE-BEARING IN BOTH SEEDS of the relevant leg, and
that count is reported with every number.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.paths import paths
from vegemu.score import acceptance_band, blocked_spatial_folds, matrix

MIN_STEMS_PER_PATCH = 0.5  # a cell needs at least this in BOTH seeds to be scored


def corpus_dir(version: str = "v0") -> Path:
    return Path(str(paths()["scratch"]["corpus"])) / version


@dataclass
class Leg:
    """One forcing leg's climate, its two state seeds, and the cells worth scoring."""

    name: str
    climate: pl.DataFrame
    seed1: pl.DataFrame
    seed2: pl.DataFrame

    @property
    def cells(self) -> npt.NDArray[np.int64]:
        return np.asarray(self.climate["cell"].to_numpy(), dtype=np.int64)


def load_leg(leg: str, version: str = "v0") -> Leg:
    d = corpus_dir(version)
    climate = pl.read_parquet(d / f"climate_{leg}.parquet").sort("cell")
    seed1 = pl.read_parquet(d / f"state_{leg}_seed1.parquet").sort("cell")
    seed2 = pl.read_parquet(d / f"state_{leg}_seed2.parquet").sort("cell")
    for name, frame in (("seed1", seed1), ("seed2", seed2)):
        if not np.array_equal(frame["cell"].to_numpy(), climate["cell"].to_numpy()):
            raise ValueError(f"{leg}/{name}: cell order does not match the climate table")
    return Leg(leg, climate, seed1, seed2)


def tree_bearing(leg: Leg) -> npt.NDArray[np.bool_]:
    """Cells with a forest in BOTH seeds. Requiring both is what makes the band meaningful."""
    a = leg.seed1["stems_per_patch"].to_numpy()
    b = leg.seed2["stems_per_patch"].to_numpy()
    return np.asarray((a >= MIN_STEMS_PER_PATCH) & (b >= MIN_STEMS_PER_PATCH))


@dataclass
class Scored:
    """Everything an arm needs, already aligned. Nothing here knows about any model."""

    cells: npt.NDArray[np.int64]
    lon: npt.NDArray[np.float64]
    lat: npt.NDArray[np.float64]
    features: npt.NDArray[np.float64]
    feature_names: tuple[str, ...]
    truth: npt.NDArray[np.float64]
    band: npt.NDArray[np.float64]
    quantity_names: tuple[str, ...]
    folds: npt.NDArray[np.int64]

    @property
    def n(self) -> int:
        return self.cells.size


def assemble(
    leg: Leg,
    quantities: tuple[str, ...],
    *,
    k: int = 5,
    block_degrees: float = 15.0,
    fold_seed: int = 42,
    mask: npt.NDArray[np.bool_] | None = None,
) -> Scored:
    """Align one leg into feature/truth/band/fold arrays over the scored cells."""
    keep = tree_bearing(leg) if mask is None else mask
    climate = leg.climate.filter(pl.Series(keep))
    s1 = matrix(leg.seed1.filter(pl.Series(keep)), quantities)
    s2 = matrix(leg.seed2.filter(pl.Series(keep)), quantities)
    truth, band = acceptance_band(s1, s2)
    lon = np.asarray(climate["lon"].to_numpy(), dtype=np.float64)
    lat = np.asarray(climate["lat"].to_numpy(), dtype=np.float64)
    return Scored(
        cells=np.asarray(climate["cell"].to_numpy(), dtype=np.int64),
        lon=lon,
        lat=lat,
        features=matrix(climate, CLIMATE_FEATURES),
        feature_names=CLIMATE_FEATURES,
        truth=truth,
        band=band,
        quantity_names=quantities,
        folds=blocked_spatial_folds(lon, lat, k=k, degrees=block_degrees, seed=fold_seed),
    )


def seed_mean(
    frame_a: pl.DataFrame, frame_b: pl.DataFrame, quantities: tuple[str, ...]
) -> npt.NDArray[np.float64]:
    """The ensemble expectation of a state: the mean of the two seeds."""
    return (matrix(frame_a, quantities) + matrix(frame_b, quantities)) / 2.0


def response_pair(
    base: Leg,
    future: Leg,
    quantities: tuple[str, ...],
    *,
    k: int = 5,
    block_degrees: float = 15.0,
    fold_seed: int = 42,
) -> tuple[Scored, Scored, npt.NDArray[np.float64]]:
    """The two ends of a response test, on the cells that are tree-bearing in BOTH legs.

    Returns (base, future, true_delta). The delta is between the two legs' two-seed MEANS, so the
    quantity under test is a change in the ensemble expectation and not a difference of two single
    draws -- which would carry twice the realisation noise and nothing extra.

    ⚠ BUILD PROVENANCE. `historical` and `ssp370` seed 1 both came from the 2026-02-05 LPJmL-FIT
    build, so that pair is build-matched. The `ssp126` leg came from an Aug-12 build, so any delta
    involving it carries an unquantified build confound and must say so.
    """
    if not np.array_equal(base.cells, future.cells):
        raise ValueError("the two legs do not cover the same cells")
    keep = tree_bearing(base) & tree_bearing(future)
    a = assemble(base, quantities, k=k, block_degrees=block_degrees, fold_seed=fold_seed, mask=keep)
    b = assemble(
        future, quantities, k=k, block_degrees=block_degrees, fold_seed=fold_seed, mask=keep
    )
    return a, b, b.truth - a.truth
