"""`load_leg` refuses a leg whose two seeds are one realisation twice.

Corpus v0's ssp370 leg is the case that exists: its two state tables are byte-identical, so a band
built from them is the bare 10 % floor in every cell while still reading as "the model's own
spread". The guard is exercised on synthetic tables here, never on the real corpus, so it runs in
CI; the shapes mirror the real ones (a `cell` key, sorted on load).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
import pytest

import vegemu.dataset as ds


def _write_leg(root: Path, leg: str, seed2_mode: str) -> None:
    cells = [3, 1, 2]
    pl.DataFrame({"cell": cells, "lon": [0.0, 1.0, 2.0], "lat": [0.0, 0.0, 0.0]}).write_parquet(
        root / f"climate_{leg}.parquet"
    )
    s1 = pl.DataFrame({"cell": cells, "stems_per_patch": [1.0, 2.0, float("nan")]})
    s1.write_parquet(root / f"state_{leg}_seed1.parquet")
    p2 = root / f"state_{leg}_seed2.parquet"
    if seed2_mode == "copy":
        shutil.copyfile(root / f"state_{leg}_seed1.parquet", p2)
    elif seed2_mode == "rewritten_clone":
        # Same rows, different bytes: another row order and compression.
        s1.sort("cell", descending=True).write_parquet(p2, compression="uncompressed")
    else:
        pl.DataFrame({"cell": cells, "stems_per_patch": [1.1, 2.0, float("nan")]}).write_parquet(p2)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ds, "corpus_dir", lambda version="v0": tmp_path)
    return tmp_path


def test_two_genuine_seeds_load(corpus: Path) -> None:
    _write_leg(corpus, "hist", "genuine")
    leg = ds.load_leg("hist")
    assert not leg.seeds_identical
    assert leg.cells.tolist() == [1, 2, 3]


def test_byte_identical_seeds_are_refused(corpus: Path) -> None:
    _write_leg(corpus, "ssp370", "copy")
    with pytest.raises(ds.IdenticalSeedsError, match="byte-identical"):
        ds.load_leg("ssp370")


def test_a_clone_rewritten_with_other_bytes_is_refused_too(corpus: Path) -> None:
    _write_leg(corpus, "ssp370", "rewritten_clone")
    assert not ds.files_identical(
        corpus / "state_ssp370_seed1.parquet", corpus / "state_ssp370_seed2.parquet"
    )
    with pytest.raises(ds.IdenticalSeedsError, match="identical rows"):
        ds.load_leg("ssp370")


def test_the_explicit_opt_in_loads_the_clone_and_marks_it(corpus: Path) -> None:
    _write_leg(corpus, "ssp370", "copy")
    leg = ds.load_leg("ssp370", allow_identical_seeds=True)
    assert leg.seeds_identical


def test_files_identical_is_byte_equality(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"x" * 3_000_000)
    b.write_bytes(b"x" * 3_000_000)
    c.write_bytes(b"x" * 2_999_999 + b"y")
    assert ds.files_identical(a, b)
    assert not ds.files_identical(a, c)
