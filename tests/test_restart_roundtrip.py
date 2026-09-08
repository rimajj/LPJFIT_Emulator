"""Rung 0: the restart-file round-trip.

Invariant 7 -- "round-trip before you trust a format" -- in its strongest form. Three layers, and
they prove different things, which is why all three are here:

  * REAL FILE (`needs_real_data`). Read a cell out of the 119 GiB ground-truth file, write it back,
    compare bytes. This is the only test that proves the LAYOUT is right: a reader and a writer that
    are wrong in the same way still agree with each other.
  * PROPERTY (hypothesis). Synthetic records with shapes the sampled real cells do not contain --
    an empty litter list, a zero-length climate ring buffer, a patch with no stems, a stand with one
    patch. The variable-length parts are where an off-by-one hides, and it hides precisely in the
    shapes the real file happens not to have.
  * FILE FRAMING. Write a subset file with our own writer and read it back, so the index vector and
    the 84-byte prefix are exercised end to end rather than only parsed.

The real-file tests are skipped where `/p` is not mounted so the suite still runs anywhere, but they
DO run on the cluster CI runner: a format proven only against synthetic data is not proven.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from vegemu.binfmt.restart import (
    _SOIL_VECTORS,
    _SOIL_VECTORS_2,
    _SOIL_VECTORS_3,
    GRASS_DTYPE,
    LASTLAYER,
    NFUELCLASS,
    NSOILLAYER,
    PFT_GRASS_BYTES,
    PFT_TREE_BYTES,
    PREFIX_BYTES,
    TREE_DTYPE,
    GenericHeader,
    Layout,
    RestartHeader,
    RestartReader,
    RestartWriter,
    read_cell,
    trees_of,
    write_cell,
)
from vegemu.paths import path

# The five biome reference cells plus Hainich. A five-cell result is never fidelity evidence, but
# for a FORMAT round-trip a hand-picked cell set is exactly right: these exercise a dense tropical
# roster and a near-empty boreal one.
BIOME_CELLS = [42490, 52059, 33335, 18371, 12045]
LITTER_ITEM_REALS = 2 * (1 + NFUELCLASS) * 2 + 2  # ag(10) + agsub(10) + bg(2)


def _restart_path() -> Path:
    return path("ground_truth.restart_spinup_end")


real_data = pytest.mark.skipif(
    not _restart_path().exists(), reason="needs the ground-truth restart file under /p"
)


# ---------------------------------------------------------------------------------------------
# Layer 1 -- the real file.
# ---------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def reader() -> RestartReader:
    return RestartReader(_restart_path())


@real_data
@pytest.mark.needs_real_data
def test_framing(reader: RestartReader) -> None:
    """The prefix, the index and the configuration flags, all read out of the file itself."""
    assert reader.generic.ncell == 67420
    assert reader.generic.nbands == 22, "7 trees + 3 grasses + 12 crops"
    assert reader.generic.datatype == 4, "Real is double; the v3 codes are 0-based"
    assert reader.generic.firstyear == 1999, "this is the END OF SPIN-UP file, not restart_2019"
    assert reader.restart.individual is True, "LPJmL-FIT: every tree is its own PFT entry"
    assert reader.restart.river_routing is False
    assert reader.restart.landuse is False
    # index[0] lands exactly after the prefix and the offset table -- checked in __post_init__,
    # asserted here so the number is visible in the test rather than only in the reader.
    assert int(reader.index[0]) == PREFIX_BYTES + 8 * reader.ncell
    assert reader.layout.ntotpft == 22


@real_data
@pytest.mark.needs_real_data
def test_one_cell_byte_identical(reader: RestartReader) -> None:
    """Step 2 of the rung: one cell, read -> write -> compare. Stop here if it fails."""
    raw = reader.cell_bytes(42490)
    rec = read_cell(raw, reader.layout)
    assert write_cell(rec, reader.layout) == raw


@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_100_cells_byte_identical(reader: RestartReader) -> None:
    """Step 3: 100 cells spanning 360 KB to 3.5 MB.

    A vegetation-free cell (empty PFT list) and the densest cell (2,551 stems) take different
    branches; sampling by SIZE rather than at random is what guarantees both are in the set.
    """
    sizes = reader.cell_sizes()
    order = np.argsort(sizes)
    picks = sorted({int(order[i]) for i in np.linspace(0, len(order) - 1, 95).astype(int)})
    picks += BIOME_CELLS
    with reader:
        for cell in picks:
            raw = reader.cell_bytes(cell)
            rec = read_cell(raw, reader.layout)
            assert write_cell(rec, reader.layout) == raw, f"cell {cell} ({len(raw)} B)"


@real_data
@pytest.mark.needs_real_data
def test_stem_fields_are_physical(reader: RestartReader) -> None:
    """Byte-identity proves the framing, NOT the field map. This checks the field map.

    A wrong offset inside the 554-byte stride survives the round-trip untouched -- the bytes go
    back exactly as they came -- and then reports plausible-looking nonsense downstream. The check
    that bites is the last one: the fraction of stems above the per-tree writer's 5 m cut is an
    INDEPENDENTLY measured quantity (~47 % at a temperate cell), so it cross-checks `height`
    against a number nothing in this repo produced.
    """
    rec = read_cell(reader.cell_bytes(42490), reader.layout)
    stems = np.concatenate([trees_of(p["pftlist"]) for p in rec["stands"][0]["patches"]])
    assert stems.size > 100

    assert stems["id"].max() < reader.layout.ntree, "a tree entry must carry a tree PFT id"
    assert (stems["height"] > 0).all() and stems["height"].max() < 80, "height in m"
    assert (stems["crownarea"] > 0).all(), "crown area in m2"
    assert 5e4 < np.median(stems["wooddens"]) < 1e6, "wood density in gC/m3"
    assert 1e-3 < np.median(stems["sla"]) < 1e-1, "specific leaf area in m2/gC"
    assert (stems["age"] >= 0).all() and stems["age"].max() < 2000, "age in years"
    assert (stems["ind_sapwood_c"] > 0).all(), "sapwood carbon per individual"

    # The bad-years counter hard-kills at 5, so a value of 5 or more cannot survive to a restart.
    counter = stems["bm_inc_counter"]
    assert counter.min() >= 0 and counter.max() <= 4, "counter kills at 5, so 0..4 in a saved state"

    tall = float((stems["height"] > 5.0).mean())
    assert 0.35 < tall < 0.65, (
        f"{tall:.1%} of stems above the 5 m per-tree-output cut; the predecessor measured ~47 % "
        "at a temperate cell. A number far from that means `height` is at the wrong offset."
    )


@real_data
@pytest.mark.needs_real_data
def test_subset_file_framing(tmp_path: Path, reader: RestartReader) -> None:
    """Write our own restart file for a handful of cells, then read it back with our own reader."""
    out = tmp_path / "subset.lpj"
    with reader:
        records = [reader.cell_bytes(c) for c in BIOME_CELLS]
    with RestartWriter(out, reader.generic, reader.restart, ncell=len(BIOME_CELLS)) as writer:
        for rec in records:
            writer.append(rec)

    back = RestartReader(out)
    assert back.ncell == len(BIOME_CELLS)
    assert int(back.index[0]) == PREFIX_BYTES + 8 * len(BIOME_CELLS)
    assert back.generic.nbands == reader.generic.nbands
    assert back.restart == reader.restart
    with back:
        for i, want in enumerate(records):
            assert back.cell_bytes(i) == want
            # and it still decodes, with the layout derived from the new file's own headers
            assert write_cell(read_cell(back.cell_bytes(i), back.layout), back.layout) == want


# ---------------------------------------------------------------------------------------------
# Layer 2 -- the property test. Reader against writer, on shapes the real file may not contain.
# ---------------------------------------------------------------------------------------------
def _reals(rng: np.random.Generator, n: int) -> Any:
    """Finite doubles spanning the model's real dynamic range (1e-8 to 1e8, both signs)."""
    mag = 10.0 ** rng.uniform(-8, 8, size=n)
    return mag * rng.choice([-1.0, 1.0], size=n)


def _synth_soil(rng: np.random.Generator, lay: Layout, litter_n: int) -> dict[str, Any]:
    soil: dict[str, Any] = {
        "pool": _reals(rng, LASTLAYER * 4).reshape(LASTLAYER, 4),
        "c_shift": _reals(rng, LASTLAYER * lay.ntotpft * 2).reshape(LASTLAYER, lay.ntotpft, 2),
        "litter": {
            "avg_fbd": _reals(rng, NFUELCLASS + 1),
            "n": litter_n,
            "pft_ids": rng.integers(0, lay.ntotpft, size=litter_n, dtype=np.uint8),
            "items": _reals(rng, litter_n * LITTER_ITEM_REALS).reshape(-1, LITTER_ITEM_REALS)
            if litter_n
            else np.zeros((0, LITTER_ITEM_REALS)),
            "agtop": _reals(rng, 4),
        },
    }
    for name, count in (*_SOIL_VECTORS, *_SOIL_VECTORS_2, *_SOIL_VECTORS_3):
        soil[name] = _reals(rng, count)
    for name in ("w_evap", "snowpack", "snowheight", "snowfraction"):
        soil[name] = float(_reals(rng, 1)[0])
    soil["state"] = rng.integers(-3, 4, size=NSOILLAYER).astype("<i2")
    for name in ("mean_maxthaw", "alag", "amp", "rw_buffer", "meanw1"):
        soil[name] = float(_reals(rng, 1)[0])
    soil["k_mean"] = _reals(rng, LASTLAYER * 2).reshape(LASTLAYER, 2)
    soil["decay_rate"] = _reals(rng, LASTLAYER * 2).reshape(LASTLAYER, 2)
    soil["decomp_litter_mean"] = _reals(rng, 2)
    soil["decomp_litter_pft"] = _reals(rng, lay.ntotpft * 2).reshape(lay.ntotpft, 2)
    soil["count"] = int(rng.integers(0, 400))
    return soil


def _synth_pftlist(
    rng: np.random.Generator, lay: Layout, ntree: int, ngrass: int
) -> dict[str, Any]:
    """Trees and grasses INTERLEAVED -- the case a single fixed stride gets wrong."""
    kinds = np.array([1] * ntree + [0] * ngrass)
    rng.shuffle(kinds)
    parts: list[bytes] = [struct.pack("<i", int(kinds.size))]
    for kind in kinds:
        if kind:
            pft_id = int(rng.integers(0, lay.ntree))
            body = rng.integers(0, 256, size=PFT_TREE_BYTES, dtype=np.uint8)
        else:
            pft_id = int(rng.integers(lay.ntree, lay.npft))
            body = rng.integers(0, 256, size=PFT_GRASS_BYTES, dtype=np.uint8)
        body[0] = pft_id
        parts.append(body.tobytes())
    return {"raw": b"".join(parts)}


def _synth_climbuf(rng: np.random.Generator, lay: Layout, buf_n: int) -> dict[str, Any]:
    return {
        "scalars": _reals(rng, 7),
        "dval_prec0": float(_reals(rng, 1)[0]),
        "temp": _reals(rng, 31),
        "prec": _reals(rng, 31),
        "mpet20": _reals(rng, 12),
        "mprec20": _reals(rng, 12),
        "mtemp20": _reals(rng, 12),
        "V_req": _reals(rng, lay.ncft),
        "V_req_a": _reals(rng, lay.ncft),
        "min": {
            "size": 20,
            "n": buf_n,
            "index": int(rng.integers(0, 20)),
            "sum": float(_reals(rng, 1)[0]),
            "data": _reals(rng, buf_n),
        },
        "max": {
            "size": 20,
            "n": buf_n,
            "index": int(rng.integers(0, 20)),
            "sum": float(_reals(rng, 1)[0]),
            "data": _reals(rng, buf_n),
        },
    }


def _synth_record(
    seed: int,
    npatch: int = 1,
    ntree: int = 3,
    ngrass: int = 1,
    *,
    litter_n: int = 4,
    buf_n: int = 5,
    nsapling: int = 2,
) -> tuple[dict[str, Any], Layout]:
    rng = np.random.default_rng(seed)
    lay = Layout()
    patches = [
        {
            "soil": _synth_soil(rng, lay, litter_n),
            "pftlist": _synth_pftlist(rng, lay, ntree, ngrass),
            "frac_g": _reals(rng, NSOILLAYER),
        }
        for _ in range(npatch)
    ]
    rec: dict[str, Any] = {
        "skip": 0,
        "seed": rng.integers(0, 65536, size=3).astype("<u2"),
        "mevap": float(_reals(rng, 1)[0]),
        "estab_storage_tree": _reals(rng, 4),
        "estab_storage_grass": _reals(rng, 4),
        "nesterov_accum": float(_reals(rng, 1)[0]),
        "nesterov_max": float(_reals(rng, 1)[0]),
        "nesterov_day": int(rng.integers(0, 366)),
        "excess_water": float(_reals(rng, 1)[0]),
        "waterdeficit": float(_reals(rng, 1)[0]),
        "gdd": _reals(rng, lay.npft),
        "stands": [
            {
                "landusetype": 0,
                "npatch": npatch,
                "patches": patches,
                "frac": float(_reals(rng, 1)[0]),
            }
        ],
        "cropfrac_rf": float(_reals(rng, 1)[0]),
        "cropfrac_ir": float(_reals(rng, 1)[0]),
        "climbuf": _synth_climbuf(rng, lay, buf_n),
        "cropdates": rng.integers(-999, 366, size=(lay.ncft, 8)).astype("<i4"),
        "sowing_month": rng.integers(0, 13, size=2 * lay.ncft).astype("<i4"),
        "gs": rng.integers(0, 366, size=2 * lay.ncft).astype("<i4"),
        "nsapling": nsapling,
        "saplings": rng.integers(0, 256, size=nsapling * 88, dtype=np.uint8).tobytes(),
    }
    return rec, lay


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 2**31 - 1),
    npatch=st.integers(1, 3),
    ntree=st.integers(0, 12),
    ngrass=st.integers(0, 3),
    litter_n=st.integers(0, 22),
    buf_n=st.integers(0, 20),
    nsapling=st.integers(0, 7),
)
def test_property_roundtrip(
    seed: int,
    npatch: int,
    ntree: int,
    ngrass: int,
    *,
    litter_n: int,
    buf_n: int,
    nsapling: int,
) -> None:
    """read(write(x)) == write(x), over every variable-length shape the record has.

    The four independent lengths are the whole point: the litter list (a leading byte count), the
    PFT list (a leading int and a per-entry size that depends on the id), the two 20-year ring
    buffers (which carry `n` values, not `size`), and the sapling pool.
    """
    rec, lay = _synth_record(
        seed, npatch, ntree, ngrass, litter_n=litter_n, buf_n=buf_n, nsapling=nsapling
    )
    blob = write_cell(rec, lay)
    again = write_cell(read_cell(blob, lay), lay)
    assert again == blob


def test_property_roundtrip_skipped_cell() -> None:
    """A `skip` cell carries only the flag, the seed and mevap. 10,434 cells are near-empty."""
    lay = Layout()
    rec: dict[str, Any] = {
        "skip": 1,
        "seed": np.array([1, 2, 3], dtype="<u2"),
        "mevap": 0.25,
    }
    blob = write_cell(rec, lay)
    assert len(blob) == 1 + 6 + 8
    assert write_cell(read_cell(blob, lay), lay) == blob


def test_truncated_record_is_an_error() -> None:
    """A short record must raise, not return a half-decoded state."""
    rec, lay = _synth_record(7, 1, 3, 1, litter_n=4, buf_n=5, nsapling=2)
    blob = write_cell(rec, lay)
    with pytest.raises((ValueError, EOFError, IndexError)):
        read_cell(blob[:-64], lay)


def test_trailing_bytes_are_an_error() -> None:
    """So must a record that decodes to fewer bytes than it has: that means a layout mismatch."""
    rec, lay = _synth_record(8, 1, 2, 1, litter_n=3, buf_n=4, nsapling=1)
    blob = write_cell(rec, lay)
    with pytest.raises(ValueError, match="does not match this file"):
        read_cell(blob + b"\x00" * 16, lay)


def test_layout_rejects_a_different_pft_set() -> None:
    """`nbands` pins the PFT set, so a file from another configuration fails here, not silently."""
    generic = GenericHeader(1, 1999, 1, 0, 10, 19, 0.5, 1.0, 0.5, 4)
    restart = RestartHeader(False, False, 0, False, False, (1, 2, 3), True)
    with pytest.raises(ValueError, match="nbands=19"):
        Layout.from_headers(generic, restart)


def test_pft_entry_strides_are_the_documented_ones() -> None:
    """The two strides ARE the specification; a wrong one walks into the next stem's fields."""
    assert TREE_DTYPE.itemsize == PFT_TREE_BYTES == 554
    assert GRASS_DTYPE.itemsize == PFT_GRASS_BYTES == 342
    # No field may overhang its entry.
    for dt, size in ((TREE_DTYPE, PFT_TREE_BYTES), (GRASS_DTYPE, PFT_GRASS_BYTES)):
        fields = dt.fields
        assert fields is not None
        for name, (sub, offset) in fields.items():
            assert offset + sub.itemsize <= size, name
