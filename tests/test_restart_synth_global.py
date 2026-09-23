"""The global task farm: plan -> shards -> assemble -> verify, on a small synthetic globe.

What must hold, and why each is its own test:

  * cells with no prediction, a NaN in a required prediction, or a `skip` template come out
    BYTE-IDENTICAL to the template -- the deliverable must never carry a fabricated forest;
  * a synthesised cell is exactly what `synthesise_cell` makes of it with the same pool and seed,
    so the farm adds framing and nothing else;
  * `--mode identity` (decode, re-encode, stitch) reproduces the template file byte for byte, which
    is the whole pipeline's own round-trip;
  * spawned workers produce the same bytes as the in-process path;
  * the donor rule is pluggable by `module:factory`, and the default one never offers a cell its
    own record or a cell past the end of the grid.

The template here is a 40-cell restart file with real-shaped records and sane stems; the scale
version runs on SLURM against the real 67,420-cell file.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from vegemu.binfmt.restart import (
    PFT_TREE_BYTES,
    GenericHeader,
    RestartHeader,
    RestartReader,
    RestartWriter,
    read_cell,
    write_cell,
)
from vegemu.models.synth import DonorPool, build_donor_pool, synthesise_cell

from .test_restart_roundtrip import _synth_record
from .test_synth_admissibility import _stem

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import synth_global as sg

NCELL = 40
SKIP = {5, 25}
GENERIC = GenericHeader(1, 1999, 1, 0, NCELL, 22, 0.5, 1.0, 0.5, 4)
RESTART = RestartHeader(False, False, 0, False, False, (11, 22, 33), True)


def _record(cell: int) -> bytes:
    if cell in SKIP:
        rec = {"skip": 1, "seed": np.array([cell, 2, 3], dtype="<u2"), "mevap": 0.1 * cell}
        return write_cell(rec, _synth_record(0)[1])
    rec, lay = _synth_record(cell, npatch=2, ntree=0, ngrass=0, litter_n=3, buf_n=3, nsapling=1)
    rng = np.random.default_rng(cell)
    for patch in rec["stands"][0]["patches"]:
        stems = [
            _stem(int(t), float(h), 2.0e5 + 1e4 * int(t), litter=i % 3)
            for i, (t, h) in enumerate(
                zip(rng.choice([1, 3], size=6), rng.uniform(1.0, 20.0, size=6), strict=True)
            )
        ]
        patch["pftlist"] = {
            "raw": struct.pack("<i", len(stems))
            + b"".join(s.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for s in stems)
        }
    return write_cell(rec, lay)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("globe")
    template = root / "template.lpj"
    with RestartWriter(template, GENERIC, RESTART, ncell=NCELL) as w:
        for c in range(NCELL):
            w.append(_record(c))
    cells = np.arange(10, 30)
    n = cells.size
    pred = {
        "cell": cells,
        "pred_stems_per_patch": np.full(n, 3.4),
        "pred_height_p10": np.full(n, 4.0),
        "pred_height_p50": np.full(n, 8.0),
        "pred_height_p90": np.full(n, 14.0),
        "pred_wooddens_p10": np.full(n, 2.0e5),
        "pred_wooddens_p50": np.full(n, 2.1e5),
        "pred_wooddens_p90": np.full(n, 2.3e5),
        "pred_soilc": np.full(n, 5000.0),
        "truth_height_p50": np.full(n, 99.0),  # not a pred_ column: must be ignored
    }
    pred["pred_soilc"][2] = np.nan  # cell 12: optional NaN -> key dropped, cell still synthesised
    pred["pred_height_p50"][3] = np.nan  # cell 13: required NaN -> passes through
    pred_path = root / "pred.parquet"
    pl.DataFrame(pred).write_parquet(pred_path)
    return {"root": root, "template": template, "pred": pred_path}


def _plan_args(world: dict[str, Path], out: Path, *extra: str) -> list[str]:
    return [
        "--out-dir", str(out), "--template", str(world["template"]), "--pred", str(world["pred"]),
        "--block-size", "10", *extra,
    ]  # fmt: skip


@pytest.fixture(scope="module")
def synth_run(world: dict[str, Path]) -> Path:
    out = world["root"] / "synth"
    assert sg.main(["run", *_plan_args(world, out, "--only", "10:30"), "--workers", "1"]) == 0
    return out


def test_plan_marks_only_blocks_with_work_as_shards(synth_run: Path) -> None:
    plan = json.loads((synth_run / "plan.json").read_text())
    assert [b["kind"] for b in plan["blocks"]] == ["template", "shard", "shard", "template"]
    assert plan["predictions"]["cells_in_range"] == 19
    assert plan["predictions"]["dropped_nan_required"] == 1
    assert "truth_height_p50" not in plan["predictions"]["quantities"]
    preds = json.loads((synth_run / "predictions.json").read_text())
    assert "13" not in preds
    assert "soilc" not in preds["12"] and preds["11"]["soilc"] == 5000.0


def test_pass_through_is_byte_identical_and_synthesis_is_not(
    world: dict[str, Path], synth_run: Path
) -> None:
    tmpl = RestartReader(world["template"])
    out = RestartReader(synth_run / "restart" / sg.OUTPUT_NAME)
    assert out.ncell == NCELL and out.generic.firstcell == 0
    assert out.restart == tmpl.restart
    changed = set(range(10, 30)) - {13} - SKIP
    with out, tmpl:
        for c in range(NCELL):
            same = out.cell_bytes(c) == tmpl.cell_bytes(c)
            assert same == (c not in changed), f"cell {c}"
    verify = json.loads((synth_run / "verify.json").read_text())
    assert verify["verdict"] == "PASS"
    assert verify["records"] == NCELL
    assert verify["synthesised_checked"] == len(changed)
    assert verify["bad_litter_index"] == 0 and verify["foreign_type_stems"] == 0
    # The shard bodies were deleted after a clean verify; their cost reports were kept.
    assert not list((synth_run / "shards").glob("*.lpj"))
    assert len(list((synth_run / "shards").glob("*.json"))) == 2
    summary = json.loads((synth_run / "summary.json").read_text())
    assert summary["synthesised"]["cells"] == len(changed)
    assert summary["synthesised"]["inadmissible_placed"] == 0
    assert summary["projection"]["cells_to_synthesise"] == 19


def test_a_synthesised_cell_is_exactly_synthesise_cell(
    world: dict[str, Path], synth_run: Path
) -> None:
    """The farm adds framing and nothing else: same template, pool and seed -> same bytes."""
    tmpl = RestartReader(world["template"])
    donors = sg.ProximityBand(world["template"], 10, 10)
    assert all(0 <= c < NCELL and not 10 <= c < 20 for c in donors.cells)
    pool = build_donor_pool(RestartReader(world["template"]), donors.cells)
    preds = json.loads((synth_run / "predictions.json").read_text())
    rec, _ = synthesise_cell(
        tmpl.read(15), preds["15"], pool, tmpl.layout, cell=15, template_cell=15,
        seed=sg.DEFAULT_SEED + 15,
    )  # fmt: skip
    out = RestartReader(synth_run / "restart" / sg.OUTPUT_NAME)
    assert out.cell_bytes(15) == write_cell(rec, tmpl.layout)


def test_identity_mode_reproduces_the_template(world: dict[str, Path]) -> None:
    out = world["root"] / "identity"
    args = ["run", *_plan_args(world, out, "--mode", "identity"), "--workers", "1"]
    assert sg.main([*args, "--cmp-template"]) == 0
    verify = json.loads((out / "verify.json").read_text())
    assert verify["cmp_template"]["whole_file"] and verify["cmp_template"]["identical"]
    assert (out / "restart" / sg.OUTPUT_NAME).read_bytes() == world["template"].read_bytes()


def test_spawned_workers_write_the_same_bytes(world: dict[str, Path], synth_run: Path) -> None:
    out = world["root"] / "spawned"
    assert sg.main(["run", *_plan_args(world, out, "--only", "10:30"), "--workers", "2"]) == 0
    a = (out / "restart" / sg.OUTPUT_NAME).read_bytes()
    assert a == (synth_run / "restart" / sg.OUTPUT_NAME).read_bytes()


def test_a_sub_range_is_framed_at_its_own_firstcell(world: dict[str, Path]) -> None:
    out = world["root"] / "subrange"
    args = ["run", *_plan_args(world, out, "--first-cell", "8", "--ncell", "17")]
    assert sg.main([*args, "--workers", "1", "--cmp-template"]) == 0
    back = RestartReader(out / "restart" / sg.OUTPUT_NAME)
    assert back.generic.firstcell == 8 and back.ncell == 17
    tmpl = RestartReader(world["template"])
    assert back.cell_bytes(0) == tmpl.cell_bytes(8)  # cell 8 has no prediction
    verify = json.loads((out / "verify.json").read_text())
    assert verify["verdict"] == "PASS" and "skipped" in verify["cmp_template"]
    # The same sub-range in identity mode is the template's own byte range, cmp'd as such.
    out = world["root"] / "subrange-identity"
    args = [
        "run",
        *_plan_args(world, out, "--first-cell", "8", "--ncell", "17", "--mode", "identity"),
    ]
    assert sg.main([*args, "--workers", "1", "--cmp-template"]) == 0
    verify = json.loads((out / "verify.json").read_text())
    assert not verify["cmp_template"]["whole_file"] and verify["cmp_template"]["identical"]


def test_shards_resume_and_assembly_refuses_a_foreign_plan(world: dict[str, Path]) -> None:
    out = world["root"] / "resume"
    assert sg.main(["plan", *_plan_args(world, out, "--only", "10:30")]) == 0
    first = sg.cmd_shards(out, "all", 1)
    again = sg.cmd_shards(out, "all", 1)
    assert first["written"] == 2 and again["written"] == 0 and again["skipped"] == [1, 2]
    # A new plan (different seed) must not be assembled out of the old plan's shards.
    assert sg.main(["plan", *_plan_args(world, out, "--only", "10:30", "--seed", "7")]) == 0
    with pytest.raises(FileNotFoundError, match="another plan"):
        sg.cmd_assemble(out)


class ExplicitDonors:
    """A stand-in for a climate-analogue rule: a fixed donor list, recorded in the report."""

    def __init__(self, template: Path, first_cell: int, ncell: int, cells: list[int]) -> None:
        self.template, self.cells = Path(template), [int(c) for c in cells]
        self.block = range(first_cell, first_cell + ncell)
        self._pool: DonorPool | None = None

    def pool_for(self, cell: int) -> DonorPool:
        assert cell in self.block and cell not in self.cells
        if self._pool is None:
            self._pool = build_donor_pool(RestartReader(self.template), self.cells)
        return self._pool

    def describe(self) -> dict[str, Any]:
        return {"rule": "explicit", "donor_cells": self.cells}


def test_the_donor_rule_is_pluggable(world: dict[str, Path]) -> None:
    out = world["root"] / "plugged"
    rule = f"{__name__}:ExplicitDonors"
    args = _plan_args(world, out, "--only", "10:20", "--donor-rule", rule)
    assert sg.main(["run", *args, "--donor-opts", '{"cells": [0, 1, 2]}', "--workers", "1"]) == 0
    rep = json.loads((out / "shards" / "shard_00001.json").read_text())
    assert rep["donors"] == {"rule": "explicit", "donor_cells": [0, 1, 2]}


def test_unknown_synth_kwargs_are_refused(world: dict[str, Path]) -> None:
    with pytest.raises(ValueError, match="bogus"):
        sg.main(
            ["plan", *_plan_args(world, world["root"] / "bad", "--synth-kwargs", '{"bogus": 1}')]
        )
    with pytest.raises(ValueError, match="seed"):
        sg.main(
            ["plan", *_plan_args(world, world["root"] / "bad", "--synth-kwargs", '{"seed": 1}')]
        )


def test_t0_streams_the_whole_file_and_a_block_byte_identically(world: dict[str, Path]) -> None:
    whole = world["root"] / "t0" / "copy.lpj"
    assert sg.main(["t0", "--template", str(world["template"]), "--out", str(whole), "--keep"]) == 0
    assert whole.read_bytes() == world["template"].read_bytes()
    rep = json.loads(whole.with_suffix(".t0.json").read_text())
    assert rep["cmp"]["whole_file"] and rep["verdict"] == "BYTE-IDENTICAL"
    part = world["root"] / "t0" / "part.lpj"
    args = ["t0", "--template", str(world["template"]), "--out", str(part)]
    assert sg.main([*args, "--first-cell", "7", "--ncell", "11"]) == 0
    assert not part.exists(), "a clean copy is deleted unless --keep"
    rep = json.loads(part.with_suffix(".t0.json").read_text())
    assert not rep["cmp"]["whole_file"] and rep["index_rebased_equal"]


def test_read_cell_of_the_fixture_is_sane(world: dict[str, Path]) -> None:
    """Guard on the fixture itself: a template the synthesiser cannot use proves nothing."""
    rec = read_cell(
        RestartReader(world["template"]).cell_bytes(15), RestartReader(world["template"]).layout
    )
    assert rec["skip"] == 0 and len(rec["stands"][0]["patches"]) == 2
