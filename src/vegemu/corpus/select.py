"""Which cells the corpus spins up, and why those.

WHY A MODULE AND NOT A RANDOM SAMPLE. The corpus's whole purpose is to decollinearise climate from
place (`PLAN.md` §Why this can work), and a uniform random draw of cells would defeat that twice
over. It would concentrate cells where cells are dense -- boreal Eurasia and the Amazon carry
hundreds of cells per 15-degree tile, an oceanic island carries one -- so the fit would be dominated
by two biomes. And it would put most held-out cells within a few hundred kilometres of a training
cell, which turns every per-cell score into a spatial-interpolation score: the effective independent
spatial sample is ~161 populated 15-degree tiles, not 54,020 cells (`MEMORY.md:eff-sample`).

THE DESIGN, in three stages, all deterministic:

  1. FORCED. The five biome reference cells (`config/paths.yaml: cells.biome`). They are the cells
     the direction test characterised, including the two results nobody has explained -- the Amazon
     bioclimatic cliff and the Sahel carbon gain -- so the corpus must contain them or those two
     findings sit outside the training data that has to reproduce them.
  2. ONE PER TILE, the tile's climate MEDOID: the cell closest to its tile's coordinate-wise median
     in standardised design space. Every populated tile gets a cell, and the cell it gets is the
     typical one rather than a lucky one. This is the stage that makes a blocked spatial fold mean
     something -- hold out a tile and you hold out a climate you have no near neighbour for.
  3. MAXIMIN FILL for the remaining budget: greedily add the cell whose nearest already-chosen cell
     is farthest away. That is standard space-filling design, and it spends the last cells on the
     climates the first two stages left thinnest instead of on another boreal cell.

THE DESIGN COORDINATES ARE THE FIVE PERTURBATION AXES' OWN BASELINES, one each:

    tas_ann          the temperature axis's baseline
    log1p(pr_ann)    the precipitation axis's baseline (logged: the range is 0 to 9243 mm)
    pr_seasonality   the precipitation-seasonality axis's baseline
    rsds_ann         the shortwave axis's baseline
    tas_iav          the interannual-variability axis's baseline

That is a choice, not a default, and it is the one that makes the corpus a product design: a cell
contributes a baseline for every axis the perturbation then moves, so cells x climates covers the
joint space rather than a slice of it. Adding a sixth coordinate would dilute all five -- in five
dimensions a maximin fill is already close to picking corners.

⚠ TILE COVERAGE IS NOT CELL-COUNT COVERAGE, AND THAT IS DELIBERATE. A tile holding 900 tree-bearing
cells and a tile holding 1 both get one cell in stage 2. Weighting by cell count would restore
exactly the density bias the stratification exists to remove: 900 boreal cells are not 900 pieces of
independent evidence.

⚠ ELIGIBILITY IS MEASURED ON THE RESTART FILE'S OWN STEM COUNT, WHICH IS UNCENSORED, so it gives
56,986 tree-bearing cells and NOT the 54,020 of the acceptance criterion. That figure came from the
predecessor's per-tree text table, which drops every stem at or below 5 m
(`MEMORY.md:ind-censored`), so it counts cells with at least one VISIBLE tree. Ours counts cells
with at least one tree. The larger set is the right basis for a corpus whose target is the restart
file, but the two are not interchangeable and neither may be quoted without saying which it is.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.paths import paths
from vegemu.score import spatial_blocks

# One coordinate per perturbation axis. `pr_ann` enters logged; the rest as they are.
DESIGN_COORDS: tuple[str, ...] = ("tas_ann", "pr_ann", "pr_seasonality", "rsds_ann", "tas_iav")
LOG_COORDS: frozenset[str] = frozenset({"pr_ann"})

TILE_DEGREES = 15.0
# No tile may contribute more than this many cells, so the maximin fill cannot spend its whole
# budget inside one climate it happens to find empty.
MAX_PER_TILE = 3


@dataclass(frozen=True)
class Selection:
    """The chosen cells and the basis every number about them must be quoted against."""

    table: pl.DataFrame
    """cell, lon, lat, tile, stage, the design coordinates, and their standardised values."""
    eligible: int
    """Tree-bearing cells the choice was made from."""
    tiles_populated: int
    """Populated tiles among those, at `TILE_DEGREES`."""
    tiles_covered: int
    """Tiles the selection actually touches."""

    def cells(self) -> list[int]:
        return [int(c) for c in self.table["cell"].to_list()]

    def as_dict(self) -> dict[str, Any]:
        by_stage = Counter(str(s) for s in self.table["stage"].to_list())
        return {
            "ncell": self.table.height,
            "by_stage": {k: int(v) for k, v in sorted(by_stage.items())},
            "eligible_cells": self.eligible,
            "eligibility": (
                "stems_total > 0 in the historical seed-1 end-of-spin-up restart; UNCENSORED, so "
                "56,986 and not the acceptance criterion's 54,020 (MEMORY.md:ind-censored)"
            ),
            "tile_degrees": TILE_DEGREES,
            "tiles_populated": self.tiles_populated,
            "tiles_covered": self.tiles_covered,
            "max_per_tile": MAX_PER_TILE,
            "design_coords": list(DESIGN_COORDS),
            "log_coords": sorted(LOG_COORDS),
            "why_these_coords": "one baseline per perturbation axis, so cells x climates covers "
            "the joint space",
        }


def _corpus_dir(version: str) -> Path:
    return Path(str(paths()["scratch"]["corpus"])) / version


def eligible_cells(version: str = "v0") -> pl.DataFrame:
    """Tree-bearing cells with their design coordinates, from the v0 per-cell tables.

    Reads the climate summary for the coordinates and the decoded end-of-spin-up state for
    eligibility. Both are per-cell tables this line already produced, so cell choice introduces no
    new data path -- and no new chance for the two to be paired by position rather than by `cell`,
    which is how a grid mix-up gets in (`MEMORY.md:hainich-cell`).
    """
    root = _corpus_dir(version)
    clim = pl.read_parquet(
        root / "climate_historical.parquet", columns=["cell", "lon", "lat", *DESIGN_COORDS]
    )
    state = pl.read_parquet(
        root / "state_historical_seed1.parquet", columns=["cell", "skip", "stems_total"]
    )
    df = clim.join(state, on="cell", how="inner")
    if df.height != clim.height:
        raise ValueError(
            f"the climate table has {clim.height} cells and the join kept {df.height}. The two "
            "per-cell tables do not cover the same cells; joining them by position would relabel "
            "every cell."
        )
    out = df.filter((pl.col("stems_total") > 0) & (pl.col("skip") == 0)).drop("skip")
    for col in DESIGN_COORDS:
        v = out[col].to_numpy()
        if not np.isfinite(v).all():
            raise ValueError(f"{col}: non-finite values among eligible cells; the design needs all")
    return out.with_columns(
        tile=pl.Series(
            spatial_blocks(out["lon"].to_numpy(), out["lat"].to_numpy(), TILE_DEGREES)
        )
    ).sort("cell")


def standardise(df: pl.DataFrame) -> npt.NDArray[np.float64]:
    """(ncell, 5) design coordinates on a robust common scale.

    Median and inter-quartile range rather than mean and standard deviation: `pr_ann` spans 0 to
    9243 mm and `tas_iav` 0.05 to 1.5, and a mean/sd scaling lets one long tail decide which cells a
    maximin fill considers far apart.
    """
    cols: list[npt.NDArray[np.float64]] = []
    for name in DESIGN_COORDS:
        v = df[name].to_numpy().astype(np.float64)
        if name in LOG_COORDS:
            v = np.log1p(np.maximum(v, 0.0))
        q25, med, q75 = (float(np.percentile(v, q)) for q in (25.0, 50.0, 75.0))
        scale = q75 - q25
        cols.append(np.asarray((v - med) / (scale if scale > 0 else 1.0), dtype=np.float64))
    return np.asarray(np.column_stack(cols), dtype=np.float64)


def _tile_medoids(
    df: pl.DataFrame, coords: npt.NDArray[np.float64], exclude: set[int]
) -> list[int]:
    """One row index per tile: the cell closest to that tile's coordinate-wise median.

    A medoid rather than the median point itself, because the design has to name a real cell that a
    real spin-up can be run for. Ties break on the lower cell index, so the answer is a function of
    the data alone.
    """
    tiles = df["tile"].to_numpy()
    cell = df["cell"].to_numpy()
    chosen: list[int] = []
    for tile in np.unique(tiles):
        rows = np.flatnonzero(tiles == tile)
        if any(int(cell[r]) in exclude for r in rows):
            continue  # a forced cell already represents this tile
        block = coords[rows]
        dist = np.linalg.norm(block - np.median(block, axis=0), axis=1)
        best = rows[np.lexsort((cell[rows], dist))[0]]
        chosen.append(int(best))
    return chosen


def _maximin_fill(
    coords: npt.NDArray[np.float64],
    cell: npt.NDArray[np.int64],
    tiles: npt.NDArray[np.int64],
    chosen: list[int],
    want: int,
) -> list[int]:
    """Greedily add `want` rows, each maximising the distance to its nearest already-chosen row.

    Kept as an explicit nearest-distance vector updated in place: it is O(ncell) per added cell
    rather than O(ncell x nchosen), which matters because `ncell` here is 56,986 and the same
    routine has to serve the 3,000-cell full tier.

    With `chosen` empty every candidate is equally far from nothing, so the tie-break decides and
    the first pick is the lowest cell index. `pilot_cells` never takes that path -- it starts from
    the forced cells and the tile medoids -- but the behaviour is defined, not accidental.
    """
    added: list[int] = []
    if want <= 0:
        return added
    per_tile: dict[int, int] = {}
    for row in chosen:
        per_tile[int(tiles[row])] = per_tile.get(int(tiles[row]), 0) + 1

    nearest = np.full(coords.shape[0], np.inf)
    for row in chosen:
        nearest = np.minimum(nearest, np.linalg.norm(coords - coords[row], axis=1))

    blocked = np.zeros(coords.shape[0], dtype=bool)
    for row in chosen:
        blocked[row] = True
    for tile, count in per_tile.items():
        if count >= MAX_PER_TILE:
            blocked |= tiles == tile

    for _ in range(want):
        if bool(blocked.all()):
            break  # every tile is at its cap; the budget cannot be spent without breaking it
        # ⚠ The exhaustion test is `blocked`, NOT `isfinite(score)`. An unvisited candidate's
        # nearest distance is +inf, which is also not finite, so a finiteness test reported
        # "exhausted" on the very first pick whenever `chosen` was empty and added nothing at all.
        score = np.where(blocked, -np.inf, nearest)
        # Ties break on the lower cell index, for the same reason as in `_tile_medoids`.
        row = int(np.lexsort((cell, -score))[0])
        added.append(row)
        blocked[row] = True
        tile = int(tiles[row])
        per_tile[tile] = per_tile.get(tile, 0) + 1
        if per_tile[tile] >= MAX_PER_TILE:
            blocked |= tiles == tile
        nearest = np.minimum(nearest, np.linalg.norm(coords - coords[row], axis=1))
    return added


def pilot_cells(n: int = 200, version: str = "v0", force_biome: bool = True) -> Selection:
    """The `n` cells of a corpus tier: forced biome cells, then tile medoids, then a maximin fill.

    Deterministic: no random number is drawn anywhere. The design is a function of the per-cell
    tables and `n` alone, which is what lets a pre-registration cite it by hash and regenerate it.
    """
    df = eligible_cells(version)
    coords = standardise(df)
    cell = df["cell"].to_numpy()
    tiles = df["tile"].to_numpy()
    row_of = {int(c): i for i, c in enumerate(cell)}

    forced: list[int] = []
    if force_biome:
        for name, want in sorted(paths()["cells"]["biome"].items()):
            if int(want) not in row_of:
                raise ValueError(
                    f"biome reference cell {name}={want} is not tree-bearing in the eligibility "
                    "basis, so it cannot be forced into the design. Check the grid ordering."
                )
            forced.append(row_of[int(want)])

    stage: dict[int, str] = {row: "biome" for row in forced}
    if n < len(forced):
        raise ValueError(f"n={n} is smaller than the {len(forced)} forced biome cells")

    medoids = _tile_medoids(df, coords, exclude={int(cell[r]) for r in forced})
    if len(forced) + len(medoids) > n:
        raise ValueError(
            f"n={n} cannot cover {len(medoids)} populated tiles plus {len(forced)} forced cells. "
            f"A tier smaller than {len(forced) + len(medoids)} cells would leave whole tiles with "
            "no cell at all, which is the density bias this design exists to remove -- raise n or "
            "widen TILE_DEGREES deliberately, do not drop tiles silently."
        )
    for row in medoids:
        stage[row] = "tile_medoid"

    chosen = [*forced, *medoids]
    for row in _maximin_fill(coords, cell, tiles, chosen, n - len(chosen)):
        stage[row] = "maximin"
        chosen.append(row)

    order = sorted(chosen, key=lambda r: int(cell[r]))
    table = (
        df[order]
        .with_columns(
            stage=pl.Series([stage[r] for r in order]),
            **{
                f"z_{name}": pl.Series(coords[order, j])
                for j, name in enumerate(DESIGN_COORDS)
            },
        )
        .sort("cell")
    )
    return Selection(
        table=table,
        eligible=df.height,
        tiles_populated=int(np.unique(tiles).size),
        tiles_covered=int(table["tile"].n_unique()),
    )
