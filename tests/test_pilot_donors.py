"""The pilot-bank donor rule: constant-CO2 stems, only wanted types, never the target's own fold."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vegemu.binfmt.restart import read_cell, trees_of
from vegemu.models import pilot_donors as pd
from vegemu.paths import path

PRED = Path(str(path("scratch.models"))) / "equimap-v1" / "pred_1901_1930_heldout.parquet"
NEEDS = (
    Path(str(path("ground_truth.restart_spinup_end"))),
    PRED,
    pd.default_bank_dir() / "runs.parquet",
    pd.default_pilot_features(),
    pd.default_global_climate(),
)
real_data = pytest.mark.skipif(
    not all(p.exists() for p in NEEDS), reason="needs the restart, the bank and the map under /p"
)
FIRST, NCELL = 28337, 58  # member m0400 of the continuation run, a temperate block


@pytest.fixture(scope="module")
def source() -> pd.PilotBank:
    return pd.PilotBank(
        Path(str(path("ground_truth.restart_spinup_end"))), FIRST, NCELL, predictions=str(PRED)
    )


@real_data
def test_a_pool_holds_only_wanted_types_from_outside_the_fold(source: pd.PilotBank) -> None:
    cell = 28380
    wanted = source.wanted(cell)
    pool = source.pool_for(cell)
    assert pool.n > 0
    assert set(np.nonzero(np.bincount(pool.raw[:, 0]))[0]) <= set(wanted)
    fold = int(source._pred[cell]["fold"])
    folds = set(source.runs.filter(source.runs["cell"].is_in(pool.source_cells))["fold"])
    assert fold not in folds
    assert cell not in pool.source_cells


@real_data
def test_every_type_the_template_holds_is_wanted(source: pd.PilotBank) -> None:
    cell = 28350
    rec = read_cell(source._reader.cell_bytes(cell), source._reader.layout)
    held = {
        int(t)
        for p in rec["stands"][0]["patches"]
        for t in np.asarray(trees_of(p["pftlist"])["id"])
    }
    assert held <= set(source.wanted(cell))
