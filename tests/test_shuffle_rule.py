"""`vegemu.models.shuffle_rule`: re-dealing a cell's own trees among its patches, nothing else.

What must hold:
  * `identity` re-encodes the record byte for byte;
  * `keep_counts` keeps every patch's stem count and `equal` makes them differ by at most one;
  * both keep the cell's multiset of tree entries exactly, apart from the litter byte of a moved
    stem, which must index the target patch's slot for its own type;
  * soil, grass and everything outside the tree entries are the template's.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np
import pytest

from vegemu.binfmt.restart import PFT_TREE_BYTES, grasses_of, read_cell, trees_of, write_cell
from vegemu.models.shuffle_rule import shuffle_patches
from vegemu.models.synth import LITTER_BYTE_IN_TREE, LITTER_ITEM_REALS

from .test_restart_roundtrip import _synth_record
from .test_synth_admissibility import _stem

NPATCH = 6


def _record() -> tuple[dict[str, Any], Any]:
    """Six patches of types 1 and 3; the odd patches have no litter slot for type 3, so a type-3
    stem moved into one must get a slot appended."""
    rec, lay = _synth_record(7, npatch=NPATCH, ntree=0, ngrass=0, litter_n=2)
    rng = np.random.default_rng(7)
    for p, patch in enumerate(rec["stands"][0]["patches"]):
        lit = dict(patch["soil"]["litter"])
        lit["pft_ids"] = np.array([1, 3] if p % 2 == 0 else [1, 9], dtype=np.uint8)
        lit["items"] = np.abs(np.asarray(lit["items"], dtype=np.float64)) % 50.0
        patch["soil"]["litter"] = lit
        types = [1] * (1 + p) if p % 2 else list(rng.choice([1, 3], size=2 + p))
        stems = [
            _stem(int(t), float(rng.uniform(1.0, 20.0)), 3.0e5, litter=0 if t == 1 else 1)
            for t in types
        ]
        for i, st in enumerate(stems):
            st["index"] = 100 * p + i
        patch["pftlist"] = {
            "raw": struct.pack("<i", len(stems))
            + b"".join(st.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for st in stems)
        }
    rec = read_cell(write_cell(rec, lay), lay)
    return rec, lay


def _stems(rec: dict[str, Any]) -> list[np.ndarray]:
    return [trees_of(p["pftlist"]) for p in rec["stands"][0]["patches"]]


def _no_litter(rows: np.ndarray) -> list[bytes]:
    b = rows.view(np.uint8).reshape(-1, PFT_TREE_BYTES)[:, :LITTER_BYTE_IN_TREE]
    return sorted(r.tobytes() for r in b)


def test_identity_is_byte_exact() -> None:
    rec, lay = _record()
    out, moved = shuffle_patches(rec, lay, mode="identity", seed=1)
    assert moved["moved"] == 0
    assert write_cell(out, lay) == write_cell(rec, lay)


@pytest.mark.parametrize("mode", ["keep_counts", "equal"])
def test_shuffle_keeps_the_trees_and_fixes_the_litter_index(mode: str) -> None:
    rec, lay = _record()
    out, moved = shuffle_patches(rec, lay, mode=mode, seed=3)
    back = read_cell(write_cell(out, lay), lay)
    before, after = _stems(rec), _stems(back)
    assert moved["stems"] == sum(t.size for t in before)
    assert moved["moved"] > 0
    counts = [t.size for t in after]
    if mode == "keep_counts":
        assert counts == [t.size for t in before]
    else:
        assert max(counts) - min(counts) <= 1
    assert _no_litter(np.concatenate(before)) == _no_litter(np.concatenate(after))
    for p0, p1, trees in zip(
        rec["stands"][0]["patches"], back["stands"][0]["patches"], after, strict=True
    ):
        ids = np.asarray(p1["soil"]["litter"]["pft_ids"])
        assert np.all(ids[trees["litter"]] == trees["id"])
        n0 = int(p0["soil"]["litter"]["n"])
        np.testing.assert_array_equal(
            np.asarray(p1["soil"]["litter"]["items"]).reshape(-1, LITTER_ITEM_REALS)[:n0],
            np.asarray(p0["soil"]["litter"]["items"]).reshape(-1, LITTER_ITEM_REALS),
        )
        assert grasses_of(p1["pftlist"]).tobytes() == grasses_of(p0["pftlist"]).tobytes()
        assert p1["soil"]["litter"]["n"] >= n0
    grown = [int(p["soil"]["litter"]["n"]) > 2 for p in back["stands"][0]["patches"]]
    assert any(grown), "no type-3 stem moved into a patch without its slot: the case is untested"
