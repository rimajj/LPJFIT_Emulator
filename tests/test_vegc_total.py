"""A cell's total vegetation carbon from a restart record must be the model's own `VegC`.

* SYNTHETIC: the tree and grass sums follow `vegc_sum_tree` / `vegc_sum_grass` term by term --
  debt subtracted, excess carbon added, the litter-bound turnover of a tree subtracted once (not
  per individual), grass counted -- and the stand fraction weights the cell.
* REAL FILE (`needs_real_data`): a pilot run's end-of-spin-up restart against the same run's
  own netCDF `VegC` for that year (model year 1999), to float32 rounding.
"""

from __future__ import annotations

import struct
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from vegemu.binfmt.restart import (
    GRASS_DTYPE,
    PFT_GRASS_BYTES,
    PFT_TREE_BYTES,
    TREE_DTYPE,
    RestartReader,
)
from vegemu.corpus.vegc import cell_vegc, grass_vegc, tree_vegc
from vegemu.paths import paths


def _tree(nind: float, **pools: float) -> np.ndarray:
    row = np.zeros(1, dtype=TREE_DTYPE)
    row["id"] = 3
    row["nind"] = nind
    for k, v in pools.items():
        row[k] = v
    return row


def _grass(nind: float, leaf: float, root: float, excess: float = 0.0) -> np.ndarray:
    row = np.zeros(1, dtype=GRASS_DTYPE)
    row["id"] = 8
    row["nind"] = nind
    row["ind_leaf_c"] = leaf
    row["ind_root_c"] = root
    row["excess_carbon"] = excess
    return row


def test_a_tree_is_its_pools_less_debt_plus_excess_times_nind_less_litter_turnover() -> None:
    t = _tree(
        0.01,
        ind_leaf_c=10.0,
        ind_root_c=5.0,
        ind_sapwood_c=100.0,
        ind_heartwood_c=300.0,
        ind_sapwood_bg_c=20.0,
        ind_heartwood_bg_c=40.0,
        ind_debt_c=15.0,
        excess_carbon=2.0,
        turn_litt_leaf_c=0.3,
        turn_litt_root_c=0.1,
    )
    want = (10 + 5 + 100 + 300 + 20 + 40 - 15 + 2) * 0.01 - 0.3 - 0.1
    assert tree_vegc(t) == pytest.approx(want)
    assert tree_vegc(np.zeros(0, dtype=TREE_DTYPE)) == 0.0


def test_a_grass_is_leaf_plus_root_plus_excess_times_nind() -> None:
    g = _grass(1.0, 120.0, 80.0, 3.0)
    assert grass_vegc(g) == pytest.approx(203.0)


def _pftlist(trees: list[np.ndarray], grasses: list[np.ndarray]) -> dict[str, object]:
    blobs = [t.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for t in trees]
    blobs += [g.view(np.uint8).reshape(PFT_GRASS_BYTES).tobytes() for g in grasses]
    raw = struct.pack("<i", len(blobs)) + b"".join(blobs)
    offs, pos = [], 4
    for b in blobs:
        offs.append(pos)
        pos += len(b)
    offs_a = np.array(offs, dtype=np.int64)
    return {
        "raw": raw,
        "n": len(blobs),
        "tree_offsets": offs_a[: len(trees)],
        "grass_offsets": offs_a[len(trees) :],
    }


def test_the_cell_is_the_stand_fraction_times_the_patch_mean() -> None:
    tree = _tree(0.02, ind_leaf_c=50.0, ind_sapwood_c=500.0)
    grass = _grass(1.0, 100.0, 60.0)
    patches = [
        {"pftlist": _pftlist([tree], [grass])},
        {"pftlist": _pftlist([], [grass])},
    ]
    rec = {"skip": 0, "stands": [{"frac": 0.8, "npatch": 2, "patches": patches}]}
    got = cell_vegc(rec)
    assert got["tree"] == pytest.approx(0.8 * (550.0 * 0.02) / 2)
    assert got["grass"] == pytest.approx(0.8 * (160.0 + 160.0) / 2)
    assert got["total"] == pytest.approx(got["tree"] + got["grass"])
    assert np.isnan(cell_vegc({"skip": 1})["total"])


@pytest.mark.needs_real_data
@pytest.mark.parametrize(("cell", "point"), [(10069, "control"), (98, "lhs14")])
def test_a_pilot_restart_gives_the_runs_own_vegc_of_that_year(cell: int, point: str) -> None:

    run = Path(str(paths()["scratch"]["runs"])) / "pilot-v2-constco2" / f"c{cell}" / point
    tag = f"c{cell}-{point}-s1"
    restart = run / "restart" / f"restart_{tag}.lpj"
    nc = run / "output" / f"vegc_{'spin' + 'up'}_{tag}.nc"
    if not restart.exists() or not nc.exists():
        pytest.skip("pilot corpus not present")
    with netCDF4.Dataset(nc) as ds:
        series = np.asarray(ds.variables["VegC"][:], dtype=np.float64).reshape(-1)
    reader = RestartReader(restart)
    with reader:
        got = cell_vegc(reader.read(0))
    # The restart is written after the last year's output; VegC is stored as float32.
    assert got["total"] == pytest.approx(series[-1], rel=1e-6, abs=1e-3)
