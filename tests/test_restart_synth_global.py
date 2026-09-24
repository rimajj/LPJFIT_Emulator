"""The global task farm: plan -> shards -> assemble -> verify, on a small synthetic globe.

What must hold, and why each is its own test:

  * cells with no prediction, a NaN in a required prediction, or a `skip` template come out
    BYTE-IDENTICAL to the template -- the deliverable must never carry a fabricated forest;
  * a synthesised cell is exactly what `synthesise_cell` makes of it with the same pool and seed,
    so the farm adds framing and nothing else;
  * `--mode identity` (decode, re-encode, stitch) reproduces the template file byte for byte, which
    is the whole pipeline's own round-trip;
  * spawned workers produce the same bytes as the in-process path;
  * the donor rule and the per-cell synthesis are pluggable by `module:factory`, and the default
    donor rule never offers a cell its own record or a cell past the end of the grid;
  * a template holding no tree passes through whatever is predicted for it (the product
    synthesises the cells with any stem, and only those);
  * shard writing is RESTARTABLE: a task that failed is re-run alone, writes only what it owns and
    is missing, and the result is byte-identical to a run that never failed.

The template here is a 40-cell restart file with real-shaped records and sane stems; the scale
version runs on SLURM against the real 67,420-cell file.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import Any, ClassVar

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
from vegemu.models.synth import DonorPool, SynthReport, build_donor_pool, synthesise_cell

from .test_restart_roundtrip import _synth_record
from .test_synth_admissibility import _stem

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import synth_global as sg

NCELL = 40
SKIP = {5, 25}
TREELESS_TEMPLATE = 16  # a real-shaped record with no tree in it, but a forest predicted
TREELESS_BOTH = 18  # no tree in the template, and none predicted either
TREELESS_PREDICTED = 14  # a forested template the prediction says holds no tree
GENERIC = GenericHeader(1, 1999, 1, 0, NCELL, 22, 0.5, 1.0, 0.5, 4)
RESTART = RestartHeader(False, False, 0, False, False, (11, 22, 33), True)


def _record(cell: int) -> bytes:
    if cell in SKIP:
        rec = {"skip": 1, "seed": np.array([cell, 2, 3], dtype="<u2"), "mevap": 0.1 * cell}
        return write_cell(rec, _synth_record(0)[1])
    rec, lay = _synth_record(cell, npatch=2, ntree=0, ngrass=0, litter_n=3, buf_n=3, nsapling=1)
    rng = np.random.default_rng(cell)
    nstem = 0 if cell in (TREELESS_TEMPLATE, TREELESS_BOTH) else 6
    for patch in rec["stands"][0]["patches"]:
        stems = [
            _stem(int(t), float(h), 2.0e5 + 1e4 * int(t), litter=i % 3)
            for i, (t, h) in enumerate(
                zip(rng.choice([1, 3], size=nstem), rng.uniform(1.0, 20.0, size=nstem), strict=True)
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
    # cells 14 and 18: the equilibrium map's treeless form -- a flag, a sub-threshold count, NaN
    # traits. 14 has a forested template (its trees are removed), 18 a treeless one (kept as is).
    pred["pred_treeless"] = np.isin(cells, [TREELESS_PREDICTED, TREELESS_BOTH])
    for i in (TREELESS_PREDICTED - 10, TREELESS_BOTH - 10):
        pred["pred_stems_per_patch"][i] = 0.5
        for q in ("height", "wooddens"):
            for k in (10, 50, 90):
                pred[f"pred_{q}_p{k}"][i] = np.nan
    pred_path = root / "pred.parquet"
    pl.DataFrame(pred).write_parquet(pred_path)
    return {"root": root, "template": template, "pred": pred_path}


class Run:
    """Where one farm run writes: the product `out`, and its work directory."""

    def __init__(self, root: Path, name: str) -> None:
        self.out = root / name / "restart_emulated.lpj"
        self.work = sg.work_dir_for(self.out)


def _plan_args(world: dict[str, Path], run: Run, *extra: str) -> list[str]:
    return [
        "--out", str(run.out), "--template", str(world["template"]),
        "--predictions", str(world["pred"]), "--block-size", "10", *extra,
    ]  # fmt: skip


@pytest.fixture(scope="module")
def synth_run(world: dict[str, Path]) -> Run:
    run = Run(world["root"], "synth")
    assert sg.main(["run", *_plan_args(world, run, "--only", "10:30"), "--workers", "1"]) == 0
    return run


CHANGED = set(range(10, 30)) - {13, TREELESS_TEMPLATE, TREELESS_BOTH} - SKIP


def test_plan_marks_only_blocks_with_work_as_shards(synth_run: Run) -> None:
    plan = json.loads((synth_run.work / "plan.json").read_text())
    assert [b["kind"] for b in plan["blocks"]] == ["template", "shard", "shard", "template"]
    assert plan["out"] == str(synth_run.out.resolve())
    assert plan["predictions"]["cells_in_range"] == 19
    assert plan["predictions"]["dropped_nan_required"] == 1
    assert plan["predictions"]["predicted_treeless"] == 2
    assert "truth_height_p50" not in plan["predictions"]["quantities"]
    preds = json.loads((synth_run.work / "predictions.json").read_text())
    assert "13" not in preds
    assert "soilc" not in preds["12"] and preds["11"]["soilc"] == 5000.0


def test_pass_through_is_byte_identical_and_synthesis_is_not(
    world: dict[str, Path], synth_run: Run
) -> None:
    tmpl = RestartReader(world["template"])
    out = RestartReader(synth_run.out)
    assert out.ncell == NCELL and out.generic.firstcell == 0
    assert out.restart == tmpl.restart
    with out, tmpl:
        for c in range(NCELL):
            same = out.cell_bytes(c) == tmpl.cell_bytes(c)
            assert same == (c not in CHANGED), f"cell {c}"
    verify = json.loads((synth_run.work / "verify.json").read_text())
    assert verify["verdict"] == "PASS"
    assert verify["records"] == NCELL
    assert verify["synthesised_checked"] == len(CHANGED)
    assert verify["bad_litter_index"] == 0 and verify["foreign_type_stems"] == 0
    # The shard bodies were deleted after a clean verify; their cost reports were kept.
    assert not list((synth_run.work / "shards").glob("*.lpj"))
    assert len(list((synth_run.work / "shards").glob("*.json"))) == 2
    summary = json.loads((synth_run.work / "summary.json").read_text())
    assert summary["synthesised"]["cells"] == len(CHANGED)
    assert summary["synthesised"]["inadmissible_placed"] == 0
    assert summary["projection"]["cells_to_synthesise"] == 19
    # A whole-template plan: assembly and verification were measured on the whole file.
    assert summary["projection"]["io_wall_s_assemble_plus_verify"] is not None


def test_a_treeless_prediction_removes_the_trees_and_keeps_the_rest(
    world: dict[str, Path], synth_run: Run
) -> None:
    """A predicted-treeless cell is WRITTEN treeless -- not passed through with its old forest."""
    tmpl = RestartReader(world["template"]).read(TREELESS_PREDICTED)
    out = RestartReader(synth_run.out).read(TREELESS_PREDICTED)
    assert sum(p["pftlist"]["tree_offsets"].size for p in tmpl["stands"][0]["patches"]) > 0
    assert all(p["pftlist"]["tree_offsets"].size == 0 for p in out["stands"][0]["patches"])
    assert np.array_equal(out["climbuf"]["temp"], tmpl["climbuf"]["temp"])
    cells = pl.read_parquet(synth_run.work / "cells.parquet")
    row = cells.filter(pl.col("cell") == TREELESS_PREDICTED).to_dicts()[0]
    assert row["status"] == "synthesised" and row["predicted_treeless"] and row["stems_placed"] == 0


def test_a_treeless_template_passes_through_whatever_is_predicted(
    world: dict[str, Path], synth_run: Run
) -> None:
    """The product synthesises the cells with any stem. A template holding none is kept byte for
    byte -- a forest predicted there (no admissible tree type to copy) and no forest predicted
    there (only its soil would change) alike -- unless `--treeless-template synthesise`."""
    cells = pl.read_parquet(synth_run.work / "cells.parquet")
    for c, treeless_pred in ((TREELESS_TEMPLATE, False), (TREELESS_BOTH, True)):
        row = cells.filter(pl.col("cell") == c).to_dicts()[0]
        assert row["status"] == "passed-through-treeless-template", c
        assert row["predicted_treeless"] == treeless_pred
    run = Run(world["root"], "forced")
    args = _plan_args(world, run, "--only", "10:20", "--treeless-template", "synthesise")
    assert sg.main(["run", *args, "--workers", "1"]) == 0
    forced = pl.read_parquet(run.work / "cells.parquet")
    for c in (TREELESS_TEMPLATE, TREELESS_BOTH):
        row = forced.filter(pl.col("cell") == c).to_dicts()[0]
        assert row["status"] == "synthesised" and row["treeless_template"], c


def test_a_synthesised_cell_is_exactly_synthesise_cell(
    world: dict[str, Path], synth_run: Run
) -> None:
    """The farm adds framing and nothing else: same template, pool and seed -> same bytes."""
    tmpl = RestartReader(world["template"])
    donors = sg.ProximityBand(world["template"], 10, 10)
    assert all(0 <= c < NCELL and not 10 <= c < 20 for c in donors.cells)
    pool = build_donor_pool(RestartReader(world["template"]), donors.cells)
    preds = json.loads((synth_run.work / "predictions.json").read_text())
    rec, _ = synthesise_cell(
        tmpl.read(15), preds["15"], pool, tmpl.layout, cell=15, template_cell=15,
        seed=sg.DEFAULT_SEED + 15,
    )  # fmt: skip
    out = RestartReader(synth_run.out)
    assert out.cell_bytes(15) == write_cell(rec, tmpl.layout)


def test_identity_mode_reproduces_the_template(world: dict[str, Path]) -> None:
    run = Run(world["root"], "identity")
    args = ["run", *_plan_args(world, run, "--mode", "identity"), "--workers", "1"]
    assert sg.main([*args, "--cmp-template"]) == 0
    verify = json.loads((run.work / "verify.json").read_text())
    assert verify["cmp_template"]["whole_file"] and verify["cmp_template"]["identical"]
    assert run.out.read_bytes() == world["template"].read_bytes()


def test_identity_mode_needs_no_predictions_and_synthesis_does(world: dict[str, Path]) -> None:
    run = Run(world["root"], "nopred")
    base = ["--out", str(run.out), "--template", str(world["template"])]
    with pytest.raises(ValueError, match="--predictions is required"):
        sg.main(["plan", *base])
    assert sg.main(["plan", *base, "--mode", "identity"]) == 0


def test_spawned_workers_write_the_same_bytes(world: dict[str, Path], synth_run: Run) -> None:
    run = Run(world["root"], "spawned")
    assert sg.main(["run", *_plan_args(world, run, "--only", "10:30"), "--workers", "2"]) == 0
    assert run.out.read_bytes() == synth_run.out.read_bytes()


def test_a_sub_range_is_framed_at_its_own_firstcell(world: dict[str, Path]) -> None:
    run = Run(world["root"], "subrange")
    args = ["run", *_plan_args(world, run, "--first-cell", "8", "--ncell", "17")]
    assert sg.main([*args, "--workers", "1", "--cmp-template"]) == 0
    back = RestartReader(run.out)
    assert back.generic.firstcell == 8 and back.ncell == 17
    tmpl = RestartReader(world["template"])
    assert back.cell_bytes(0) == tmpl.cell_bytes(8)  # cell 8 has no prediction
    verify = json.loads((run.work / "verify.json").read_text())
    assert verify["verdict"] == "PASS" and "skipped" in verify["cmp_template"]
    summary = json.loads((run.work / "summary.json").read_text())
    assert summary["projection"]["io_wall_s_assemble_plus_verify"] is None  # not the whole file
    # The same sub-range in identity mode is the template's own byte range, cmp'd as such.
    run = Run(world["root"], "subrange-identity")
    args = [
        "run",
        *_plan_args(world, run, "--first-cell", "8", "--ncell", "17", "--mode", "identity"),
    ]
    assert sg.main([*args, "--workers", "1", "--cmp-template"]) == 0
    verify = json.loads((run.work / "verify.json").read_text())
    assert not verify["cmp_template"]["whole_file"] and verify["cmp_template"]["identical"]


def test_shards_resume_and_assembly_refuses_a_foreign_plan(world: dict[str, Path]) -> None:
    run = Run(world["root"], "resume")
    assert sg.main(["plan", *_plan_args(world, run, "--only", "10:30")]) == 0
    first = sg.cmd_shards(run.work, 1)
    again = sg.cmd_shards(run.work, 1)
    assert first["written"] == 2 and again["written"] == 0 and again["skipped"] == [1, 2]
    # A new plan (different seed) must not be assembled out of the old plan's shards.
    assert sg.main(["plan", *_plan_args(world, run, "--only", "10:30", "--seed", "7")]) == 0
    with pytest.raises(FileNotFoundError, match="another plan"):
        sg.cmd_assemble(run.work)


def test_later_commands_find_the_plan_by_out_and_refuse_a_crossed_one(
    world: dict[str, Path],
) -> None:
    a, b = Run(world["root"], "cross-a"), Run(world["root"], "cross-b")
    assert sg.main(["plan", *_plan_args(world, a, "--only", "10:30")]) == 0
    assert sg.main(["shards", "--out", str(a.out), "--workers", "1"]) == 0
    with pytest.raises(SystemExit, match="writes"):
        sg.main(["assemble", "--work-dir", str(a.work), "--out", str(b.out)])
    assert sg.main(["finish", "--work-dir", str(a.work), "--workers", "1"]) == 0
    assert RestartReader(a.out).ncell == NCELL


# --------------------------------------------------------------------------------------------
# Restartability: a task that failed is re-run alone.
# --------------------------------------------------------------------------------------------
class Flaky(sg.CurrentApi):
    """`current-api`, except that it raises on the cells in `FAIL` -- a task dying mid-block."""

    FAIL: ClassVar[set[int]] = set()

    def __call__(self, template: Any, prediction: Any, pool: Any, layout: Any, **kw: Any) -> Any:
        if kw["cell"] in self.FAIL:
            raise RuntimeError(f"injected failure at cell {kw['cell']}")
        return super().__call__(template, prediction, pool, layout, **kw)


def test_task_blocks_are_disjoint_cover_and_are_fixed_by_the_plan(synth_run: Run) -> None:
    plan = json.loads((synth_run.work / "plan.json").read_text())
    shard_ks = [b["k"] for b in plan["blocks"] if b["kind"] == "shard"]
    for n in (1, 2, 3, 5):
        owned = [sg.task_blocks(plan, t, n) for t in range(n)]
        assert sorted(itertools.chain(*owned)) == shard_ks, n
        assert owned == [sg.task_blocks(plan, t, n) for t in range(n)]  # a pure function
    with pytest.raises(ValueError, match="outside"):
        sg.task_blocks(plan, 2, 2)


def test_a_failed_task_is_rerun_alone_and_the_result_is_unchanged(
    world: dict[str, Path], synth_run: Run
) -> None:
    run = Run(world["root"], "flaky")
    rule = f"{__name__}:Flaky"
    assert sg.main(["plan", *_plan_args(world, run, "--only", "10:30", "--cell-rule", rule)]) == 0
    loc = ["--out", str(run.out)]
    Flaky.FAIL = {23}  # in block 2, which task 1 of 2 owns
    try:
        assert sg.main(["shards", *loc, "--task", "0", "--ntasks", "2", "--workers", "1"]) == 0
        assert sg.main(["shards", *loc, "--task", "1", "--ntasks", "2", "--workers", "1"]) == 1
    finally:
        Flaky.FAIL = set()
    status = sg.cmd_status(run.work, 2)
    assert status["missing"] == [2] and status["rerun_tasks"] == [1]
    assert not status["partial_files"], "a failed shard must leave no half-written file"
    with pytest.raises(FileNotFoundError, match="missing"):
        sg.cmd_assemble(run.work)
    # A stale half-written file and a truncated body, as a node crash would leave them.
    (run.work / "shards" / "shard_00002.lpj.partial").write_bytes(b"junk")
    done = run.work / "shards" / "shard_00001.lpj"
    before = done.stat().st_mtime_ns
    # Re-run ONLY the failed task: it writes its missing shard and nothing it does not own.
    res = sg.cmd_shards(run.work, 1, task=1, ntasks=2)
    assert res["written"] == 1 and res["skipped"] == [] and not res["failed"]
    assert done.stat().st_mtime_ns == before, "task 0's shard was rewritten"
    assert sg.main(["finish", *loc, "--workers", "1"]) == 0
    # Same bytes as a run that never failed: the rule delegates to current-api.
    assert run.out.read_bytes() == synth_run.out.read_bytes()


def test_a_truncated_or_foreign_shard_is_rewritten_not_trusted(world: dict[str, Path]) -> None:
    run = Run(world["root"], "truncated")
    assert sg.main(["plan", *_plan_args(world, run, "--only", "10:30")]) == 0
    assert sg.cmd_shards(run.work, 1)["written"] == 2
    shard = run.work / "shards" / "shard_00001.lpj"
    body = shard.read_bytes()
    shard.write_bytes(body[:-7])
    assert sg.cmd_status(run.work, None)["missing"] == [1]
    res = sg.cmd_shards(run.work, 1)
    assert res["written"] == 1 and res["skipped"] == [2]
    assert shard.read_bytes() == body


def test_farm_prints_one_rerunnable_line_per_task(world: dict[str, Path], synth_run: Run) -> None:
    lines = sg.cmd_farm(synth_run.work, 2, 8, time_limit="00:30:00", tag_prefix="D-glb-test")
    jobs = [ln for ln in lines if "sbatch_py.sh" in ln]
    assert len(jobs) == 3
    for t in range(2):
        assert f"D-glb-test-t{t} " in jobs[t] and f"--task {t} --ntasks 2" in jobs[t]
    assert "DEPENDENCY=afterok$deps" in jobs[2] and " finish " in jobs[2]


def test_the_disk_check_refuses_before_anything_is_written(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Run(world["root"], "full-disk")
    tiny = shutil._ntuple_diskusage(10**12, 10**12 - 1000, 1000)  # type: ignore[attr-defined]
    monkeypatch.setattr(sg.shutil, "disk_usage", lambda _p: tiny)
    with pytest.raises(OSError, match="not enough free disk"):
        sg.main(["plan", *_plan_args(world, run, "--only", "10:30")])
    assert not (run.work / "plan.json").exists()
    assert sg.main(["plan", *_plan_args(world, run, "--only", "10:30", "--skip-disk-check")]) == 0


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
    run = Run(world["root"], "plugged")
    rule = f"{__name__}:ExplicitDonors"
    args = _plan_args(world, run, "--only", "10:20", "--donor-rule", rule)
    assert sg.main(["run", *args, "--donor-opts", '{"cells": [0, 1, 2]}', "--workers", "1"]) == 0
    rep = json.loads((run.work / "shards" / "shard_00001.json").read_text())
    assert rep["donors"] == {"rule": "explicit", "donor_cells": [0, 1, 2]}


@dataclasses.dataclass
class LaterReport(SynthReport):
    """A report with a field today's `SynthReport` lacks, as the synthesiser will grow them."""

    shares_source: str = "predicted"


class Recording:
    """A stand-in for a cell rule that wires in more than `synthesise_cell`'s current options.

    It sees what the contract promises -- the block, its donors, every finite prediction of the
    cell, the pool, the seed -- and returns an unchanged template and a report."""

    SEEN: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, template: Path, first_cell: int, ncell: int, **kw: Any) -> None:
        self.block = (first_cell, ncell)
        self.kw = kw

    def __call__(self, template: Any, prediction: Any, pool: Any, layout: Any, **kw: Any) -> Any:
        Recording.SEEN.append({"prediction": dict(prediction), **kw, "block": self.block})
        rep = LaterReport(cell=kw["cell"], template_cell=kw["cell"], stems_requested=0,
                          stems_placed=0, donors_available=pool.n)  # fmt: skip
        return template, rep

    def describe(self) -> dict[str, Any]:
        return {"rule": "recording", "opts": {k: v for k, v in self.kw.items() if k != "donors"}}


def test_the_cell_rule_is_pluggable_and_sees_the_whole_prediction(
    world: dict[str, Path],
) -> None:
    run = Run(world["root"], "cell-rule")
    Recording.SEEN.clear()
    args = _plan_args(world, run, "--only", "10:20", "--cell-rule", f"{__name__}:Recording")
    assert sg.main(["run", *args, "--synth-kwargs", '{"knob": 3}', "--workers", "1"]) == 0
    seen = {s["cell"]: s for s in Recording.SEEN}
    assert 11 in seen and seen[11]["seed"] == sg.DEFAULT_SEED + 11 and seen[11]["block"] == (10, 10)
    assert seen[11]["prediction"]["soilc"] == 5000.0  # an OPTIONAL quantity arrives too
    rows = pl.read_parquet(run.work / "cells.parquet").filter(pl.col("cell") == 11).to_dicts()
    assert rows[0]["status"] == "synthesised" and rows[0]["rep_shares_source"] == "predicted"
    # Plugin kwargs are the plugin's business; the default rule's are checked against the API.
    assert sg.main(["plan", *args, "--synth-kwargs", '{"bogus": 1}']) == 0


def test_unknown_synth_kwargs_are_refused(world: dict[str, Path]) -> None:
    bad = Run(world["root"], "bad")
    with pytest.raises(ValueError, match="bogus"):
        sg.main(["plan", *_plan_args(world, bad, "--synth-kwargs", '{"bogus": 1}')])
    for reserved in ("seed", "match_traits", "template_cell"):
        with pytest.raises(ValueError, match=reserved):
            sg.main(["plan", *_plan_args(world, bad, "--synth-kwargs", f'{{"{reserved}": 1}}')])


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


def test_the_census_counts_stems_and_makes_the_plan_exact(
    world: dict[str, Path], synth_run: Run
) -> None:
    """The census is the synthesiser's own stem test over every template record; with it the plan
    says, before any work, exactly how many cells it will synthesise -- the count verify sees."""
    census = world["root"] / "census" / "census.parquet"
    args = ["census", "--template", str(world["template"]), "--out", str(census)]
    assert sg.main([*args, "--workers", "1", "--block-size", "7"]) == 0
    df = pl.read_parquet(census)
    assert df["cell"].to_list() == list(range(NCELL))
    assert set(df.filter(pl.col("skip"))["cell"].to_list()) == SKIP
    no_stem = df.filter(~pl.col("skip") & (pl.col("stems") == 0))["cell"].to_list()
    assert set(no_stem) == {TREELESS_TEMPLATE, TREELESS_BOTH}
    assert set(df.filter(pl.col("stems") > 0)["stems"].to_list()) == {12}  # 2 patches x 6
    info = json.loads(census.with_suffix(".json").read_text())
    assert info["any_stem"] == NCELL - len(SKIP) - 2

    run = Run(world["root"], "with-census")
    plan_args = _plan_args(world, run, "--only", "10:30", "--census", str(census))
    assert sg.main(["run", *plan_args, "--workers", "1"]) == 0
    plan = json.loads((run.work / "plan.json").read_text())
    assert plan["census"]["predicted_with_stem"] == len(CHANGED)
    assert plan["census"]["predicted_without_stem"] == 2
    verify = json.loads((run.work / "verify.json").read_text())
    assert verify["synthesised_checked"] == len(CHANGED)
    proj = json.loads((run.work / "summary.json").read_text())["projection"]
    assert proj["cells_to_synthesise"] == len(CHANGED) and proj["cells_to_synthesise_exact"]
    assert run.out.read_bytes() == synth_run.out.read_bytes()  # the census changes no byte
    other = world["root"] / "census" / "three_cells.lpj"
    with RestartWriter(other, GENERIC, RESTART, ncell=3) as w:
        for c in range(3):
            w.append(_record(c))
    with pytest.raises(ValueError, match="not a census of this template"):
        sg.census_counts(census, RestartReader(other), set())
