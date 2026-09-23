"""The table schema: schema 3 fixes the treeless tree-type shares, schema 2 stays bit-for-bit.

The load-bearing property is the second one. Every existing table is cited by sha256 in a sealed
pre-registration, so the only acceptable way to fix `_empty_summary` was to make the fix a new
schema and keep the old output reachable exactly -- same values AND same dict key order, because
the key order is the column order a caller's `pl.DataFrame(rows)` produces.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from vegemu.corpus import schema
from vegemu.corpus.state import (
    NTREE_PFT,
    STATE_COLUMNS,
    _empty_summary,
    single_cell_state,
    summarise_cell,
)
from vegemu.paths import paths
from vegemu.score import COMPOSITION_QUANTITIES

PFT = tuple(f"pft_frac_{i}" for i in range(NTREE_PFT))


def test_the_library_default_is_the_legacy_schema() -> None:
    """Callers outside the corpus pipeline re-decode pinned versions without passing a schema."""
    assert (schema.LEGACY, schema.CURRENT) == (2, 3)
    default, legacy = _empty_summary(1, 25, 0), _empty_summary(1, 25, 0, schema.LEGACY)
    assert list(default) == list(legacy)
    assert np.array_equal(list(default.values()), list(legacy.values()), equal_nan=True)


def test_schema_2_writes_zero_shares_on_a_treeless_row() -> None:
    row = _empty_summary(42490, 25, 0, schema=2)
    assert all(row[c] == 0.0 for c in PFT)


def test_schema_3_writes_nan_shares_on_a_treeless_row() -> None:
    row = _empty_summary(42490, 25, 0, schema=3)
    assert all(np.isnan(row[c]) for c in PFT)


def test_the_shares_are_the_only_difference_and_the_key_order_is_identical() -> None:
    old, new = _empty_summary(7, 25, 0, 2), _empty_summary(7, 25, 0, 3)
    assert list(old) == list(new) == list(STATE_COLUMNS)
    for key in STATE_COLUMNS:
        a, b = old[key], new[key]
        same = a == b or (np.isnan(a) and np.isnan(b))
        assert same == (key not in PFT), key


def test_the_shares_are_exactly_the_scored_composition_columns() -> None:
    assert PFT == COMPOSITION_QUANTITIES


def test_a_skipped_cell_follows_the_schema_too() -> None:
    rec = {"skip": True}
    lay = None  # never touched on the skip path
    assert summarise_cell(rec, 3, lay, schema=2)["pft_frac_0"] == 0.0  # type: ignore[arg-type]
    assert np.isnan(summarise_cell(rec, 3, lay, schema=3)["pft_frac_0"])  # type: ignore[arg-type]


def test_an_unknown_schema_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown corpus schema"):
        _empty_summary(1, 25, 0, schema=4)


def test_provenance_without_a_schema_is_schema_2() -> None:
    assert schema.of_provenance({}) == 2
    assert schema.of_provenance({"schema": 3}) == 3
    with pytest.raises(ValueError):
        schema.of_provenance({"schema": "3"})


# ------------------------------------------------------------------------------------------------
# A real treeless restart and a real treed one, from pilot-v2-constco2
# ------------------------------------------------------------------------------------------------


def _run(name: str) -> Path | None:
    cell, point = name.split("-", 1)[0], name.split("-", 1)[1].rsplit("-", 1)[0]
    root = Path(str(paths()["scratch"]["runs"])) / "pilot-v2-constco2" / cell / point
    f = root / "restart" / f"restart_{name}.lpj"
    return f if f.is_file() else None


def _pinned_row(name: str) -> dict[str, object]:
    table = Path(str(paths()["scratch"]["corpus"])) / "pilot-v2-constco2" / "corpus.parquet"
    return pl.read_parquet(table).filter(pl.col("name") == name).to_dicts()[0]


@pytest.mark.needs_real_data
@pytest.mark.parametrize("name", ["c3552-control-s1", "c4355-lhs00-s1"])
def test_a_real_restart_decodes_as_pinned_under_schema_2(name: str) -> None:
    """One treeless and one treed run: schema 2 reproduces the pinned table's row exactly, and
    schema 3 differs only in the shares, only on the treeless one."""
    f = _run(name)
    if f is None:
        pytest.skip("pilot-v2-constco2 runs are not on disk")
    pinned = _pinned_row(name)
    cell = int(name.split("-", maxsplit=1)[0][1:])
    v2 = single_cell_state(f, cell, schema=2)
    v3 = single_cell_state(f, cell, schema=3)
    treeless = v2["stems_total"] <= 0
    for key in STATE_COLUMNS:
        if key == "cell":
            continue
        want = float(pinned[key])  # type: ignore[arg-type]
        assert v2[key] == want or (np.isnan(v2[key]) and np.isnan(want)), key
        if key in PFT and treeless:
            assert np.isnan(v3[key]), key
        else:
            assert v3[key] == v2[key] or (np.isnan(v3[key]) and np.isnan(v2[key])), key
