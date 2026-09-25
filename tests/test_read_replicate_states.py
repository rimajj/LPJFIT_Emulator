"""`exp_read_replicate_states.py --compare` says "equal" only when every column it wrote agrees."""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_read_replicate_states import compare_tables


def _mine() -> pl.DataFrame:
    return pl.DataFrame(
        {"name": ["a", "b"], "cell": [1, 2], "point": ["p", "p"], "stems_per_patch": [3.0, 4.0]}
    ).with_columns(pl.col("cell").cast(pl.Int64))


def test_equal_tables_compare_equal_whatever_the_row_order(tmp_path: Path) -> None:
    other = tmp_path / "replicate_s2.parquet"
    _mine().drop("name").reverse().with_columns(pl.lit(2).alias("seed")).write_parquet(other)
    assert compare_tables(_mine(), other)["equal"]


def test_an_overlap_on_the_keys_alone_is_not_equality(tmp_path: Path) -> None:
    other = tmp_path / "replicate_s2.parquet"
    _mine().rename({"stems_per_patch": "stems"}).write_parquet(other)
    got = compare_tables(_mine(), other)
    assert not got["equal"] and got["missing_in_other"] == ["stems_per_patch"]


def test_a_differing_value_or_a_missing_table_is_not_equal(tmp_path: Path) -> None:
    other = tmp_path / "replicate_s2.parquet"
    _mine().with_columns(pl.Series("stems_per_patch", [3.0, 4.5])).write_parquet(other)
    assert not compare_tables(_mine(), other)["equal"]
    assert not compare_tables(_mine(), tmp_path / "absent.parquet")["equal"]
