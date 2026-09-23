"""The streaming restart writer and the shard assembler.

The global product is 67,420 records and ~119 GiB, so the writer can no longer hold every record in
RAM until `close()`, and the file is built by many tasks as SHARDS that are then stitched. Neither
change may alter one byte of the output. So every test here compares against a REFERENCE: the old
in-memory writer, transcribed verbatim below as `_reference_file`. A writer that is wrong the same
way the reference is wrong would still pass, which is why the real-file layer compares against the
model's own file instead.

  * SYNTHETIC. Random record blobs (the framing never looks inside a record) and real-shaped
    records from the round-trip test's generator. Pins streaming == reference, shards + assembly ==
    one writer, and that a failure leaves no file behind.
  * REAL FILE (`needs_real_data`). A contiguous block of the ground-truth restart streamed through
    the writer, and re-assembled from shards plus a template segment, compared against the SOURCE
    bytes. The full-globe version of this runs as a SLURM job (`scripts/synth_global.py t0`).
"""

from __future__ import annotations

import itertools
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from vegemu.binfmt import restart as rs
from vegemu.binfmt.restart import (
    PREFIX_BYTES,
    RESTART_MAGIC,
    RESTART_VERSION,
    GenericHeader,
    RestartHeader,
    RestartReader,
    RestartWriter,
    Segment,
    assemble_restart,
    read_cell,
    write_cell,
)
from vegemu.paths import path

from .test_restart_roundtrip import _synth_record

GENERIC = GenericHeader(1, 1999, 1, 0, 0, 22, 0.5, 1.0, 0.5, 4)
RESTART = RestartHeader(False, False, 0, False, False, (11, 22, 33), True)


def _reference_file(
    records: list[bytes], generic: GenericHeader, restart: RestartHeader, firstcell: int | None
) -> bytes:
    """The in-memory writer as it was before streaming, kept as the oracle. Do not "fix" it."""
    g = GenericHeader(**{**generic.__dict__})
    g.ncell = len(records)
    if firstcell is not None:
        g.firstcell = firstcell
    offsets = np.empty(len(records), dtype="<i8")
    pos = PREFIX_BYTES + 8 * len(records)
    for i, rec in enumerate(records):
        offsets[i] = pos
        pos += len(rec)
    return (
        RESTART_MAGIC
        + struct.pack("<i", RESTART_VERSION)
        + g.pack()
        + restart.pack()
        + offsets.tobytes()
        + b"".join(records)
    )


def _blobs(seed: int, n: int, lo: int = 15, hi: int = 5000) -> list[bytes]:
    rng = np.random.default_rng(seed)
    return [
        rng.integers(0, 256, size=int(rng.integers(lo, hi)), dtype=np.uint8).tobytes()
        for _ in range(n)
    ]


def _write(dest: Path, records: list[bytes], firstcell: int | None = None) -> Path:
    with RestartWriter(dest, GENERIC, RESTART, ncell=len(records), firstcell=firstcell) as w:
        for rec in records:
            w.append(rec)
    return dest


# ---------------------------------------------------------------------------------------------
# The streaming writer against the reference.
# ---------------------------------------------------------------------------------------------
@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    seed=st.integers(0, 2**31 - 1), n=st.integers(0, 30), first=st.none() | st.integers(0, 67419)
)
def test_stream_equals_reference(tmp_path: Path, seed: int, n: int, first: int | None) -> None:
    records = _blobs(seed, n)
    got = _write(tmp_path / f"s{seed}_{n}.lpj", records, first).read_bytes()
    assert got == _reference_file(records, GENERIC, RESTART, first)


def test_stream_real_shaped_records_roundtrip(tmp_path: Path) -> None:
    """Real-shaped records (litter lists, ring buffers, interleaved trees and grasses, a skip cell)
    survive the writer and decode again under the new file's own headers."""
    records = []
    for seed in range(6):
        rec, lay = _synth_record(seed, npatch=1 + seed % 3, ntree=seed * 2, ngrass=seed % 2)
        records.append(write_cell(rec, lay))
    records.insert(
        3, write_cell({"skip": 1, "seed": np.array([1, 2, 3], "<u2"), "mevap": 0.5}, lay)
    )
    out = _write(tmp_path / "real_shaped.lpj", records, firstcell=1000)
    assert out.read_bytes() == _reference_file(records, GENERIC, RESTART, 1000)
    back = RestartReader(out)
    assert back.ncell == len(records) and back.generic.firstcell == 1000
    with back:
        for i, want in enumerate(records):
            got = back.cell_bytes(i)
            assert got == want
            assert write_cell(read_cell(got, back.layout), back.layout) == want


def test_records_go_to_disk_as_appended(tmp_path: Path) -> None:
    """The point of the change: a record is on disk after `append`, not held until `close`."""
    dest = tmp_path / "streamed.lpj"
    big = _blobs(1, 3, lo=3_000_000, hi=3_000_001)
    w = RestartWriter(dest, GENERIC, RESTART, ncell=3)
    w.append(big[0])
    w.append(big[1])
    partial = dest.with_name(dest.name + ".partial")
    assert partial.stat().st_size >= PREFIX_BYTES + 8 * 3 + 2 * 3_000_000
    assert not dest.exists(), "nothing appears at the final path before close()"
    assert not hasattr(w, "_records")
    w.append(big[2])
    w.close()
    assert not partial.exists()
    assert dest.read_bytes() == _reference_file(big, GENERIC, RESTART, None)


def test_exception_leaves_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "boom.lpj"
    with pytest.raises(RuntimeError), RestartWriter(dest, GENERIC, RESTART, ncell=3) as w:
        w.append(b"x" * 100)
        raise RuntimeError("synthesis failed half-way")
    assert not dest.exists()
    assert not dest.with_name(dest.name + ".partial").exists()


def test_short_or_long_count_is_an_error_and_keeps_the_old_file(tmp_path: Path) -> None:
    dest = tmp_path / "keep.lpj"
    dest.write_bytes(b"the previous file")
    w = RestartWriter(dest, GENERIC, RESTART, ncell=3)
    w.append(b"a" * 20)
    with pytest.raises(ValueError, match="declared ncell=3 but appended 1"):
        w.close()
    assert dest.read_bytes() == b"the previous file"

    w = RestartWriter(dest, GENERIC, RESTART, ncell=1)
    w.append(b"a" * 20)
    with pytest.raises(ValueError, match="appended more"):
        w.append(b"b" * 20)
    assert dest.read_bytes() == b"the previous file"
    assert not dest.with_name(dest.name + ".partial").exists()


def test_empty_file_matches_reference(tmp_path: Path) -> None:
    out = _write(tmp_path / "empty.lpj", [])
    assert out.read_bytes() == _reference_file([], GENERIC, RESTART, None)


# ---------------------------------------------------------------------------------------------
# Shards + assembly against one writer.
# ---------------------------------------------------------------------------------------------
def _shards(tmp_path: Path, records: list[bytes], cuts: list[int], base: int = 0) -> list[Segment]:
    segs = []
    edges = [0, *cuts, len(records)]
    for k, (a, b) in enumerate(itertools.pairwise(edges)):
        shard = _write(tmp_path / f"shard_{k:03d}.lpj", records[a:b], firstcell=base + a)
        segs.append(Segment(shard, 0, b - a))
    return segs


@settings(
    max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(seed=st.integers(0, 2**31 - 1), n=st.integers(1, 40), data=st.data())
def test_assembly_equals_one_writer(tmp_path: Path, seed: int, n: int, data: Any) -> None:
    records = _blobs(seed, n)
    cuts = sorted(set(data.draw(st.lists(st.integers(1, max(n - 1, 1)), max_size=6))))
    cuts = [c for c in cuts if 0 < c < n]
    d = tmp_path / f"a{seed}_{n}"
    d.mkdir(exist_ok=True)
    segs = _shards(d, records, cuts, base=500)
    out = d / "global.lpj"
    info = assemble_restart(out, segs)
    assert info["ncell"] == n and info["firstcell"] == 500
    assert out.read_bytes() == _reference_file(records, GENERIC, RESTART, 500)


def test_assembly_mixes_shards_and_template_segments(tmp_path: Path) -> None:
    """Pass-through cells are copied straight from the TEMPLATE; only changed blocks are shards."""
    template_records = _blobs(7, 30)
    template = _write(tmp_path / "template.lpj", template_records, firstcell=0)
    changed = _blobs(8, 10)  # cells 10..19 replaced
    shard = _write(tmp_path / "shard.lpj", changed, firstcell=10)
    segs = [Segment(template, 0, 10), Segment(shard, 0, 10), Segment(template, 20, 10)]
    out = tmp_path / "global.lpj"
    assemble_restart(out, segs)
    want = template_records[:10] + changed + template_records[20:]
    assert out.read_bytes() == _reference_file(want, GENERIC, RESTART, 0)
    # and a sub-range of the template alone reproduces the old writer's subset file exactly
    assemble_restart(tmp_path / "cut.lpj", [Segment(template, 5, 7)])
    ref = _reference_file(template_records[5:12], GENERIC, RESTART, 5)
    assert (tmp_path / "cut.lpj").read_bytes() == ref


def test_assembly_refuses_gaps_overlaps_and_foreign_shards(tmp_path: Path) -> None:
    records = _blobs(9, 12)
    a = _write(tmp_path / "a.lpj", records[:6], firstcell=0)
    b = _write(tmp_path / "b.lpj", records[6:], firstcell=6)
    gap = _write(tmp_path / "gap.lpj", records[6:], firstcell=7)
    with pytest.raises(ValueError, match="gap/overlap"):
        assemble_restart(tmp_path / "x.lpj", [Segment(a, 0, 6), Segment(gap, 0, 6)])
    with pytest.raises(ValueError, match="gap/overlap"):
        assemble_restart(tmp_path / "x.lpj", [Segment(b, 0, 6), Segment(a, 0, 6)])
    foreign_generic = GenericHeader(1, 2019, 1, 6, 6, 22, 0.5, 1.0, 0.5, 4)
    with RestartWriter(tmp_path / "f.lpj", foreign_generic, RESTART, ncell=6) as w:
        for rec in records[6:]:
            w.append(rec)
    with pytest.raises(ValueError, match="generic header differs"):
        assemble_restart(tmp_path / "x.lpj", [Segment(a, 0, 6), Segment(tmp_path / "f.lpj", 0, 6)])
    with pytest.raises(ValueError, match="outside"):
        assemble_restart(tmp_path / "x.lpj", [Segment(a, 3, 6)])
    assert not (tmp_path / "x.lpj").exists()


@pytest.mark.parametrize("chunk", [1, 777, 12_345, 1 << 26])
def test_assembly_is_independent_of_the_copy_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chunk: int
) -> None:
    """A segment copied in chunks that never line up with a record boundary is the same bytes."""
    records = _blobs(10, 25, lo=10, hi=40_000)
    segs = _shards(tmp_path, records, [5, 17])
    monkeypatch.setattr(rs, "COPY_CHUNK", chunk)
    out = tmp_path / "global.lpj"
    assemble_restart(out, segs)
    assert out.read_bytes() == _reference_file(records, GENERIC, RESTART, 0)


# ---------------------------------------------------------------------------------------------
# The real file.
# ---------------------------------------------------------------------------------------------
def _restart_path() -> Path:
    return path("ground_truth.restart_spinup_end")


real_data = pytest.mark.skipif(
    not _restart_path().exists(), reason="needs the ground-truth restart file under /p"
)
FIRST, N = 42480, 24


@real_data
@pytest.mark.needs_real_data
def test_real_block_streams_byte_identical_to_source(tmp_path: Path) -> None:
    """A contiguous real block, streamed record by record, is the SOURCE's bytes with a new prefix.

    The record region must be the source's own byte range verbatim and the offset table the
    source's own offsets rebased -- compared against the model's file, not against our reference.
    """
    src = RestartReader(_restart_path())
    with src:
        records = [src.cell_bytes(c) for c in range(FIRST, FIRST + N)]
    out = tmp_path / "block.lpj"
    with RestartWriter(out, src.generic, src.restart, ncell=N, firstcell=FIRST) as w:
        for rec in records:
            w.append(rec)
    start, _ = src.extent(FIRST)
    _, end = src.extent(FIRST + N - 1)
    with _restart_path().open("rb") as fh:
        fh.seek(start)
        region = fh.read(end - start)
        fh.seek(PREFIX_BYTES)
        index = np.frombuffer(fh.read(8 * src.ncell), dtype="<i8")
    body = out.read_bytes()
    assert body[PREFIX_BYTES + 8 * N :] == region
    got_index = np.frombuffer(body[PREFIX_BYTES : PREFIX_BYTES + 8 * N], dtype="<i8")
    want_index = index[FIRST : FIRST + N] - index[FIRST] + PREFIX_BYTES + 8 * N
    assert np.array_equal(got_index, want_index)
    assert body == _reference_file(records, src.generic, src.restart, FIRST)


@real_data
@pytest.mark.needs_real_data
def test_real_block_assembled_from_shards_and_template(tmp_path: Path) -> None:
    """Shards cut from the real file, re-decoded, plus a template segment == the streamed block."""
    src = RestartReader(_restart_path())
    with src:
        records = [src.cell_bytes(c) for c in range(FIRST, FIRST + N)]
    decoded = [write_cell(read_cell(r, src.layout), src.layout) for r in records[8:16]]
    assert decoded == records[8:16]
    with RestartWriter(tmp_path / "s.lpj", src.generic, src.restart, 8, FIRST + 8) as w:
        for rec in decoded:
            w.append(rec)
    segs = [
        Segment(_restart_path(), FIRST, 8),
        Segment(tmp_path / "s.lpj", 0, 8),
        Segment(_restart_path(), FIRST + 16, N - 16),
    ]
    out = tmp_path / "assembled.lpj"
    assemble_restart(out, segs)
    assert out.read_bytes() == _reference_file(records, src.generic, src.restart, FIRST)
    back = RestartReader(out)
    assert back.generic.firstcell == FIRST and back.ncell == N
