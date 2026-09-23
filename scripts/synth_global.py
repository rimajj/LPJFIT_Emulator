#!/usr/bin/env python
"""Write the emulated restart file for the WHOLE GLOBE, as a task farm over cell blocks.

    scripts/synth_global.py plan     --out-dir <D> [--pred <parquet>] [--block-size 500] ...
    scripts/synth_global.py shards   --out-dir <D> [--blocks all|a:b] [--workers 64]
    scripts/synth_global.py assemble --out-dir <D>
    scripts/synth_global.py verify   --out-dir <D> [--workers 64]
    scripts/synth_global.py run      --out-dir <D> ...          # all four, in one job
    scripts/synth_global.py farm     --out-dir <D> --jobs 4     # prints the multi-job submission
    scripts/synth_global.py t0       --out <file> [--first-cell F --ncell N]   # the scale proof

WHAT THIS IS. `synth_restart.py` writes one contiguous block and holds it in RAM; the product is a
restart file for all 67,420 cells, ~119 GiB, in the model's grid order (latitude row, then
longitude). So the globe is cut into blocks; each block is read from the TEMPLATE global restart,
each cell with a prediction is synthesised by `models.synth.synthesise_cell` exactly as
`synth_restart.py` does it, and the block is written as a SHARD -- itself a valid restart file with
`firstcell` = the block's first cell. `assemble` stitches the shards into one file by byte-range
copies (`binfmt.restart.assemble_restart`), and `verify` reads every record of the result back.

A BLOCK WITH NOTHING TO SYNTHESISE WRITES NO SHARD. Its records are the template's, verbatim, so
the assembler copies them straight out of the template. Cells with no prediction, a NaN in a
required prediction, or a `skip` template pass through unchanged -- as in `synth_restart.py`,
because substituting a guess there would put a fabricated forest into the deliverable.

⚠ WHAT THE PRODUCT OF THIS SCRIPT IS NOT. It is not a fidelity measurement. The template of every
cell is that cell's OWN real `restart_1999` record (the synthesiser's design: soil water, climate
buffer and tree types are copied from it), so scoring this file against `restart_1999` would score
the truth against a copy of itself. Fidelity is measured by the sealed experiments, never here.
What this script measures is cost, framing, and whether the model loads the file.

THE DONOR POOL IS PLUGGABLE. `--donor-rule proximity-band` (the default) is the current rule of
`synth_restart.py`, imported from it, not re-implemented: the biome spanners plus a band of cells
either side of the BLOCK, the block itself excluded. So the pool depends on where the block
boundaries fall, and that is disclosed in the plan. Any other rule is `--donor-rule module:factory`,
where `factory(template_path, first_cell, ncell, **donor_opts)` returns an object with
`pool_for(cell) -> DonorPool` and `describe() -> dict` -- which is all a per-cell climate-analogue
pool needs. A rule must never hand a cell a donor pool built from that cell's own record.

THE PROCESSES ARE SPAWNED, NOT FORKED (`docs/reference/cluster.md` trap 7: a forked worker that
touches polars hangs forever). Predictions are read once, in the parent, and handed to each block
as plain dicts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import multiprocessing as mp
import os
import resource
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl  # parent-side only: workers are SPAWNED, and receive plain dicts

from synth_restart import BIOME_DONORS, DONOR_BAND, _donor_cells
from vegemu.binfmt.restart import (
    PREFIX_BYTES,
    Layout,
    RestartReader,
    RestartWriter,
    Segment,
    assemble_restart,
    grasses_of,
    read_cell,
    trees_of,
    write_cell,
)
from vegemu.models.synth import (
    MATCH_TRAITS,
    DonorPool,
    build_donor_pool,
    synthesise_cell,
    type_ladder,
)
from vegemu.paths import path, paths

PLAN_VERSION = 1
DEFAULT_BLOCK = 500
DEFAULT_SEED = 20260908  # synth_restart.py's, so a block synthesised by either agrees per cell
OUTPUT_NAME = "restart_1999_emulated.lpj"


def _template_default() -> Path:
    return path("ground_truth.historical_seed1") / "restart/restart_1999.lpj"


def _pred_default() -> Path:
    # The v0 out-of-fold map predictions, which `synth_restart.py` also defaults to. The production
    # input is `--pred <models>/equimap-v1/pred_<leg>.parquet` once that model exists.
    return Path(str(paths()["scratch"]["exp"])) / "map-response-v0" / "oof_map.parquet"


def _sha256(p: Path, chunk: int = 64 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _maxrss_mb() -> float:
    """Peak resident set of THIS process, in MB (Linux reports KiB)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _write_json(dest: Path, obj: Any) -> None:
    tmp = dest.with_name(dest.name + ".partial")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=_jsonable))
    tmp.replace(dest)


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, Path):
        return str(v)
    raise TypeError(f"not JSON-serialisable: {type(v).__name__}")


# --------------------------------------------------------------------------------------------
# Donor pools. The interface is one method, so a per-cell rule needs nothing a per-block one does
# not: `pool_for(cell)`.
# --------------------------------------------------------------------------------------------
class DonorSource(Protocol):
    def pool_for(self, cell: int) -> DonorPool: ...

    def describe(self) -> dict[str, Any]: ...


class ProximityBand:
    """`synth_restart.py`'s rule, applied per block: biome spanners + a band, the block excluded."""

    def __init__(
        self, template: Path, first_cell: int, ncell: int, band: int | None = None
    ) -> None:
        self.band = DONOR_BAND if band is None else int(band)
        self.template = Path(template)
        ntotal = RestartReader(self.template).ncell
        # `_donor_cells` bounds the band below by 0 but not above by the grid, which never mattered
        # for one block in Europe and does for the last block of the globe.
        self.cells = [c for c in _donor_cells(first_cell, ncell, self.band) if c < ntotal]
        self.biome = BIOME_DONORS
        self._pool: DonorPool | None = None

    def pool_for(self, cell: int) -> DonorPool:
        if cell in self.cells:
            raise AssertionError(f"cell {cell} is in its own donor pool")
        if self._pool is None:
            # A fresh reader: build_donor_pool opens and CLOSES the reader it is given, which would
            # close the handle the block loop is reading through.
            self._pool = build_donor_pool(RestartReader(self.template), self.cells)
        return self._pool

    def describe(self) -> dict[str, Any]:
        return {
            "rule": "proximity-band",
            "band": self.band,
            "donor_cells": list(self.cells),
            "donor_stems": None if self._pool is None else self._pool.n,
        }


DONOR_RULES: dict[str, Callable[..., DonorSource]] = {"proximity-band": ProximityBand}


def make_donor_source(
    rule: str, template: Path, first_cell: int, ncell: int, opts: dict[str, Any]
) -> DonorSource:
    """A named rule, or `module:factory` for one this file does not know about."""
    if rule in DONOR_RULES:
        return DONOR_RULES[rule](template, first_cell, ncell, **opts)
    if ":" not in rule:
        raise ValueError(f"unknown donor rule {rule!r}; known: {sorted(DONOR_RULES)} or mod:attr")
    mod, attr = rule.split(":", 1)
    factory = getattr(importlib.import_module(mod), attr)
    src: DonorSource = factory(template, first_cell, ncell, **opts)
    return src


# --------------------------------------------------------------------------------------------
# Predictions.
# --------------------------------------------------------------------------------------------
def required_quantities(match_traits: tuple[str, ...]) -> tuple[str, ...]:
    """What `synthesise_cell` cannot do without. Everything else it reads is optional."""
    return ("stems_per_patch", *(f"{t}_p{q}" for t in match_traits for q in (10, 50, 90)))


def load_predictions(
    pred_path: Path, lo: int, hi: int, match_traits: tuple[str, ...]
) -> tuple[dict[int, dict[str, float]], dict[str, Any]]:
    """`cell` + `pred_<q>` columns -> {cell: {q: value}} for cells in [lo, hi).

    A NaN in a REQUIRED quantity drops the cell (it then passes through). A NaN in an optional one
    drops only that key -- passing it on would be worse than absent: `_rescale_soil` tests
    `want <= 0`, which a NaN fails, and would scale every soil pool by NaN.

    A cell the prediction marks TREELESS (`pred_treeless` true, as the equilibrium map writes it:
    its stem count fell below the model's own treeless cut, and its trait quantiles are NaN
    because a stand with no trees has no trait distribution) is a prediction, not a gap. It is
    kept with `stems_per_patch = 0`, so the synthesiser writes the template's grasses, soil and
    buffers with no tree in it. Passing the template through instead would keep a present-day
    forest in a cell the emulator says has none -- under a warmed climate, exactly the wrong way.
    """
    df = pl.read_parquet(pred_path)
    cols = [c for c in df.columns if c.startswith("pred_")]
    names = [c.removeprefix("pred_") for c in cols]
    need = required_quantities(match_traits)
    missing = [q for q in need if q not in names]
    if missing:
        raise ValueError(f"{pred_path}: no pred_ column for {missing}")
    cells = df["cell"].to_numpy().astype(np.int64)
    if np.unique(cells).size != cells.size:
        raise ValueError(f"{pred_path}: duplicate cell ids")
    mat = df.select(pl.col(cols).cast(pl.Float64)).to_numpy()
    req = np.array([names.index(q) for q in need])
    k_treeless = names.index("treeless") if "treeless" in names else None
    out: dict[int, dict[str, float]] = {}
    dropped = 0
    treeless = 0
    for i, cell in enumerate(int(c) for c in cells):
        if not lo <= cell < hi:
            continue
        row = mat[i]
        vals = {q: float(v) for q, v in zip(names, row.tolist(), strict=True) if np.isfinite(v)}
        if k_treeless is not None and np.isfinite(row[k_treeless]) and row[k_treeless] >= 0.5:
            vals["stems_per_patch"] = 0.0
            treeless += 1
        elif not np.all(np.isfinite(row[req])):
            dropped += 1
            continue
        out[cell] = vals
    info = {
        "path": str(pred_path),
        "sha256": _sha256(pred_path),
        "rows": int(df.height),
        "quantities": names,
        "required": list(need),
        "cells_in_range": len(out),
        "predicted_treeless": treeless,
        "dropped_nan_required": dropped,
    }
    return out, info


# --------------------------------------------------------------------------------------------
# The plan: every block, fixed before any work, and hashed so a shard can prove which plan it
# belongs to.
# --------------------------------------------------------------------------------------------
def _parse_range(text: str | None, lo: int, hi: int) -> tuple[int, int]:
    if not text or text == "all":
        return lo, hi
    a, b = text.split(":")
    return int(a or lo), int(b or hi)


def make_plan(args: argparse.Namespace) -> tuple[dict[str, Any], dict[int, dict[str, float]]]:
    """The plan, and the predictions it will synthesise (kept out of the plan: they are data)."""
    template = Path(args.template) if args.template else _template_default()
    reader = RestartReader(template)
    first = int(args.first_cell)
    ncell = reader.ncell - first if args.ncell is None else int(args.ncell)
    if not (first >= 0 and ncell >= 1 and first + ncell <= reader.ncell):
        raise ValueError(f"range [{first}, +{ncell}) outside the template's {reader.ncell} cells")
    match_traits = tuple(t for t in args.match_traits.split(",") if t)
    synth_kwargs = json.loads(args.synth_kwargs) if args.synth_kwargs else {}
    accepted = set(inspect.signature(synthesise_cell).parameters)
    reserved = {"template", "prediction", "pool", "layout", "cell", "template_cell", "seed"}
    bad = sorted((set(synth_kwargs) - accepted) | (set(synth_kwargs) & reserved))
    if bad:
        raise ValueError(f"--synth-kwargs: synthesise_cell does not take (or reserves) {bad}")

    pred_info: dict[str, Any] = {}
    preds: dict[int, dict[str, float]] = {}
    if args.mode == "synth":
        lo, hi = _parse_range(args.only, first, first + ncell)
        preds, pred_info = load_predictions(
            Path(args.pred) if args.pred else _pred_default(),
            max(lo, first),
            min(hi, first + ncell),
            match_traits,
        )
        pred_info["only"] = [lo, hi]

    blocks = []
    for k, a in enumerate(range(first, first + ncell, args.block_size)):
        n = min(args.block_size, first + ncell - a)
        todo = sum(1 for c in range(a, a + n) if c in preds)
        kind = "shard" if (args.mode == "identity" or todo) else "template"
        blocks.append({"k": k, "first": a, "ncell": n, "predicted": todo, "kind": kind})

    plan = {
        "version": PLAN_VERSION,
        "mode": args.mode,
        "template": str(template),
        "template_bytes": reader.filesize,
        "template_ncell": reader.ncell,
        "first_cell": first,
        "ncell": ncell,
        "block_size": args.block_size,
        "predictions": pred_info,
        "donor_rule": args.donor_rule,
        "donor_opts": json.loads(args.donor_opts) if args.donor_opts else {},
        "seed": args.seed,
        "match_traits": list(match_traits),
        "synth_kwargs": synth_kwargs,
        "on_error": args.on_error,
        "treeless_template": args.treeless_template,
        "blocks": blocks,
    }
    plan["plan_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan, preds


def _plan_path(out_dir: Path) -> Path:
    return out_dir / "plan.json"


def _load_plan(out_dir: Path) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(_plan_path(out_dir).read_text())
    return plan


def _preds_path(out_dir: Path) -> Path:
    return out_dir / "predictions.json"


# --------------------------------------------------------------------------------------------
# One block -> one shard. Runs in a spawned worker; takes and returns plain data only.
# --------------------------------------------------------------------------------------------
def _shard_path(out_dir: Path, k: int) -> Path:
    return out_dir / "shards" / f"shard_{k:05d}.lpj"


def _synth_one(
    plan: dict[str, Any], cell: int, blob: bytes, *, tmpl: dict[str, Any],
    pred: dict[str, float], pool: DonorPool, lay: Layout,
) -> tuple[bytes, dict[str, Any]]:  # fmt: skip
    """One cell through `synthesise_cell`, round-trip checked. Returns (record, report fields)."""
    try:
        rec, rep = synthesise_cell(
            tmpl,
            pred,
            pool,
            lay,
            cell=cell,
            template_cell=cell,
            seed=int(plan["seed"]) + cell,
            match_traits=tuple(plan["match_traits"]),
            **plan["synth_kwargs"],
        )
        out = write_cell(rec, lay)
        # t0 on the SYNTHESISED record, per record, before it is committed.
        if write_cell(read_cell(out, lay), lay) != out:
            raise AssertionError(f"cell {cell}: synthesised record does not round-trip")
    except Exception as exc:
        if plan["on_error"] == "raise":
            raise
        return blob, {"status": f"error-passed-through: {type(exc).__name__}: {exc}"}
    return out, {
        "status": "synthesised",
        "stems_requested": rep.stems_requested,
        "stems_placed": rep.stems_placed,
        "inadmissible_placed": rep.inadmissible_placed,
        "type_fallbacks": rep.type_fallbacks,
        "treeless_template": not rep.type_admissible,
        "predicted_treeless": pred["stems_per_patch"] <= 0,
        "shape_source": ",".join(f"{k}={v}" for k, v in rep.shape_source.items()),
        "soil_scale": rep.soil_scale,
    }


def run_block(job: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0915 -- one linear pass
    """Synthesise (or, in identity mode, decode and re-encode) one block into its shard."""
    wall0, cpu0 = time.perf_counter(), time.process_time()
    plan, blk, preds = job["plan"], job["block"], job["preds"]
    out_dir = Path(job["out_dir"])
    template = Path(plan["template"])
    first, ncell = int(blk["first"]), int(blk["ncell"])
    dest = _shard_path(out_dir, int(blk["k"]))
    reader = RestartReader(template)
    lay = reader.layout
    donors: DonorSource | None = None
    if plan["mode"] == "synth" and preds:
        donors = make_donor_source(plan["donor_rule"], template, first, ncell, plan["donor_opts"])
    synth_treeless_templates = plan["treeless_template"] == "synthesise"

    body = hashlib.sha256()
    rows: list[dict[str, Any]] = []
    t_pool = 0.0
    with reader, RestartWriter(dest, reader.generic, reader.restart, ncell, firstcell=first) as w:
        for cell in range(first, first + ncell):
            c_wall, c_cpu = time.perf_counter(), time.process_time()
            blob = reader.cell_bytes(cell)
            row: dict[str, Any] = {"cell": cell, "bytes_in": len(blob)}
            out = blob
            pred = preds.get(str(cell))
            if plan["mode"] == "identity":
                out = write_cell(read_cell(blob, lay), lay)
                if out != blob:
                    raise AssertionError(f"cell {cell}: decode -> encode is not byte-identical")
                row["status"] = "identity"
            elif pred is None:
                row["status"] = "passed-through"
            else:
                tmpl = read_cell(blob, lay)
                if tmpl["skip"]:
                    row["status"] = "passed-through-skip"
                elif (
                    pred["stems_per_patch"] > 0
                    and not type_ladder(tmpl).size
                    and not synth_treeless_templates
                ):
                    # No tree in the template means no admissible tree TYPE to copy, and the
                    # synthesiser would then draw types from the whole pool -- the fault that
                    # killed half the first roster within a year. Kept as the template, counted.
                    row["status"] = "passed-through-treeless-template"
                else:
                    assert donors is not None
                    # Timed apart from the cell: a per-block pool is built on its first call, and
                    # folding that into one cell's cost would make the per-cell numbers lie.
                    p_wall, p_cpu = time.perf_counter(), time.process_time()
                    pool = donors.pool_for(cell)
                    p_wall, p_cpu = time.perf_counter() - p_wall, time.process_time() - p_cpu
                    t_pool += p_wall
                    c_wall += p_wall
                    c_cpu += p_cpu
                    out, fields = _synth_one(
                        plan, cell, blob, tmpl=tmpl, pred=pred, pool=pool, lay=lay
                    )
                    row.update(fields)
            w.append(out)
            body.update(out)
            row["bytes_out"] = len(out)
            row["wall_s"] = time.perf_counter() - c_wall
            row["cpu_s"] = time.process_time() - c_cpu
            rows.append(row)

    report = {
        "k": blk["k"],
        "first": first,
        "ncell": ncell,
        "plan_sha256": plan["plan_sha256"],
        "shard": str(dest),
        "shard_bytes": dest.stat().st_size,
        "body_sha256": body.hexdigest(),
        "wall_s": time.perf_counter() - wall0,
        "cpu_s": time.process_time() - cpu0,
        "pool_build_s": t_pool,
        "maxrss_mb": _maxrss_mb(),
        "donors": None if donors is None else donors.describe(),
        "host": os.uname().nodename,
        "complete": True,
        "cells": rows,
    }
    _write_json(dest.with_suffix(".json"), report)
    return {k: v for k, v in report.items() if k != "cells"}


def _shard_done(out_dir: Path, plan: dict[str, Any], blk: dict[str, Any]) -> bool:
    rep_path = _shard_path(out_dir, blk["k"]).with_suffix(".json")
    if not rep_path.exists() or not _shard_path(out_dir, blk["k"]).exists():
        return False
    rep = json.loads(rep_path.read_text())
    return bool(rep.get("complete")) and rep.get("plan_sha256") == plan["plan_sha256"]


def _farm(
    fn: Callable[[dict[str, Any]], dict[str, Any]], jobs: list[dict[str, Any]], workers: int
) -> Iterator[dict[str, Any]]:
    """`fn(job)` for every job, yielded as each finishes.

    SPAWNED workers, one block per process (`max_tasks_per_child=1`), so each block's peak memory
    is its own and a block that leaks cannot poison the next. `workers <= 1` runs in this process
    instead -- the tests' path, and a debugger's.
    """
    if workers <= 1:
        for job in jobs:
            yield fn(job)
        return
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx, max_tasks_per_child=1) as ex:
        for fut in as_completed([ex.submit(fn, job) for job in jobs]):
            yield fut.result()


def cmd_shards(out_dir: Path, blocks_arg: str | None, workers: int) -> dict[str, Any]:
    plan = _load_plan(out_dir)
    preds_all: dict[str, dict[str, float]] = (
        json.loads(_preds_path(out_dir).read_text()) if _preds_path(out_dir).exists() else {}
    )
    (out_dir / "shards").mkdir(parents=True, exist_ok=True)
    lo, hi = _parse_range(blocks_arg, 0, len(plan["blocks"]))
    todo = [b for b in plan["blocks"][lo:hi] if b["kind"] == "shard"]
    skipped = [b["k"] for b in todo if _shard_done(out_dir, plan, b)]
    todo = [b for b in todo if b["k"] not in set(skipped)]
    print(
        f"shards: {len(todo)} to write, {len(skipped)} already done, blocks [{lo},{hi})", flush=True
    )
    wall0 = time.perf_counter()
    done: list[dict[str, Any]] = []
    jobs = []
    for b in todo:
        mine = {
            str(c): preds_all[str(c)]
            for c in range(b["first"], b["first"] + b["ncell"])
            if str(c) in preds_all
        }
        jobs.append({"plan": plan, "block": b, "preds": mine, "out_dir": str(out_dir)})
    for r in _farm(run_block, jobs, workers):
        done.append(r)
        print(
            f"  shard {r['k']:5d}  cells {r['first']}+{r['ncell']}  {r['wall_s']:.1f} s wall  "
            f"{r['cpu_s']:.1f} s cpu  {r['maxrss_mb']:.0f} MB  ({len(done)}/{len(todo)})",
            flush=True,
        )
    return {
        "written": len(done),
        "skipped": skipped,
        "wall_s": time.perf_counter() - wall0,
        "workers": workers,
    }


# --------------------------------------------------------------------------------------------
# Assembly.
# --------------------------------------------------------------------------------------------
def segments_for(out_dir: Path, plan: dict[str, Any]) -> list[Segment]:
    """Shard blocks from their shard; runs of template blocks as ONE template segment each."""
    template = Path(plan["template"])
    segs: list[Segment] = []
    for b in plan["blocks"]:
        if b["kind"] == "shard":
            if not _shard_done(out_dir, plan, b):
                raise FileNotFoundError(f"shard {b['k']} is missing or belongs to another plan")
            segs.append(Segment(_shard_path(out_dir, b["k"]), 0, b["ncell"]))
        elif segs and segs[-1].path == template and segs[-1].first + segs[-1].ncell == b["first"]:
            segs[-1] = Segment(template, segs[-1].first, segs[-1].ncell + b["ncell"])
        else:
            segs.append(Segment(template, b["first"], b["ncell"]))
    return segs


def _output(out_dir: Path) -> Path:
    return out_dir / "restart" / OUTPUT_NAME


def cmd_assemble(out_dir: Path) -> dict[str, Any]:
    plan = _load_plan(out_dir)
    dest = _output(out_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    segs = segments_for(out_dir, plan)
    wall0 = time.perf_counter()
    info = assemble_restart(dest, segs, firstcell=plan["first_cell"])
    wall = time.perf_counter() - wall0
    info.update(
        dest=str(dest),
        wall_s=wall,
        mb_per_s=info["bytes"] / 1e6 / max(wall, 1e-9),
        shard_segments=sum(1 for s in segs if s.path != Path(plan["template"])),
        template_segments=sum(1 for s in segs if s.path == Path(plan["template"])),
        maxrss_mb=_maxrss_mb(),
    )
    _write_json(out_dir / "assembly.json", info)
    print(f"assembled {dest}: {info['bytes'] / 2**30:.2f} GiB in {wall:.0f} s", flush=True)
    return info


# --------------------------------------------------------------------------------------------
# Verification: read EVERY record of the assembled file back, independently of the writer.
# --------------------------------------------------------------------------------------------
def _independent_checks(rec: dict[str, Any], tmpl: dict[str, Any]) -> dict[str, int]:
    """Re-derived from the WRITTEN record, not from the synthesiser's own report.

    * every stem and grass entry's litter index is inside its patch's litter list -- the condition
      `freadpft.c:71` aborts on with ERROR195, which a byte round-trip can never see;
    * how many stems are of a tree type the template cell's own real state never holds.
    """
    bad_litter = 0
    stems = 0
    types: set[int] = set()
    for patch in tmpl["stands"][0]["patches"]:
        types.update(int(t) for t in trees_of(patch["pftlist"])["id"])
    foreign = 0
    for patch in rec["stands"][0]["patches"]:
        n_lit = int(patch["soil"]["litter"]["n"])
        tr = trees_of(patch["pftlist"])
        gr = grasses_of(patch["pftlist"])
        bad_litter += int(np.count_nonzero(tr["litter"] >= n_lit))
        bad_litter += int(np.count_nonzero(gr["litter"] >= n_lit))
        stems += int(tr.size)
        if types:
            foreign += int(np.count_nonzero(~np.isin(tr["id"], list(types))))
    return {"bad_litter_index": bad_litter, "stems": stems, "foreign_type_stems": foreign}


def verify_block(job: dict[str, Any]) -> dict[str, Any]:
    wall0 = time.perf_counter()
    plan, blk = job["plan"], job["block"]
    out = RestartReader(Path(job["output"]))
    tmpl_reader = RestartReader(Path(plan["template"]))
    lay = out.layout
    base = int(plan["first_cell"])
    synth = set(job["synthesised"])
    body = hashlib.sha256()
    tot: dict[str, Any] = {
        "records": 0,
        "identical_to_template": 0,
        "synthesised_checked": 0,
        "bad_litter_index": 0,
        "foreign_type_stems": 0,
        "stems": 0,
    }
    with out, tmpl_reader:
        for cell in range(blk["first"], blk["first"] + blk["ncell"]):
            got = out.cell_bytes(cell - base)
            body.update(got)
            rec = read_cell(got, lay)
            if write_cell(rec, lay) != got:
                raise AssertionError(f"cell {cell}: assembled record does not round-trip")
            tot["records"] += 1
            want = tmpl_reader.cell_bytes(cell)
            if cell in synth:
                chk = _independent_checks(rec, read_cell(want, lay))
                tot["synthesised_checked"] += 1
                for key, v in chk.items():
                    tot[key] += v
            elif got != want:
                raise AssertionError(f"cell {cell}: passed through, yet differs from the template")
            else:
                tot["identical_to_template"] += 1
    tot["body_sha256"] = body.hexdigest()
    if blk["kind"] == "shard" and tot["body_sha256"] != job["shard_sha256"]:
        raise AssertionError(f"block {blk['k']}: assembled bytes differ from shard {blk['k']}")
    tot.update(k=blk["k"], wall_s=time.perf_counter() - wall0, maxrss_mb=_maxrss_mb())
    return tot


def cmd_verify(out_dir: Path, workers: int, cmp_template: bool) -> dict[str, Any]:
    plan = _load_plan(out_dir)
    dest = _output(out_dir)
    wall0 = time.perf_counter()
    out = RestartReader(dest)
    tmpl = RestartReader(Path(plan["template"]))
    framing = {
        "ncell": out.ncell == plan["ncell"],
        "firstcell": out.generic.firstcell == plan["first_cell"],
        "headers": {**out.generic.__dict__, "ncell": 0, "firstcell": 0}
        == {**tmpl.generic.__dict__, "ncell": 0, "firstcell": 0}
        and out.restart == tmpl.restart,
        "index0": int(out.index[0]) == PREFIX_BYTES + 8 * out.ncell,
    }
    if not all(framing.values()):
        raise AssertionError(f"framing check failed: {framing}")
    jobs = []
    for b in plan["blocks"]:
        synth: list[int] = []
        sha = None
        if b["kind"] == "shard":
            rep = json.loads(_shard_path(out_dir, b["k"]).with_suffix(".json").read_text())
            synth = [r["cell"] for r in rep["cells"] if r["status"] == "synthesised"]
            sha = rep["body_sha256"]
        jobs.append(
            {
                "plan": plan,
                "block": b,
                "output": str(dest),
                "synthesised": synth,
                "shard_sha256": sha,
            }
        )
    results = list(_farm(verify_block, jobs, workers))
    keys = (
        "records",
        "identical_to_template",
        "synthesised_checked",
        "bad_litter_index",
        "foreign_type_stems",
        "stems",
    )
    summary: dict[str, Any] = {k: int(sum(r[k] for r in results)) for k in keys}
    summary["framing"] = framing
    summary["bytes"] = dest.stat().st_size
    if cmp_template and summary["synthesised_checked"]:
        # A synthesised cell MUST differ from its template, so a cmp would only report that.
        summary["cmp_template"] = {"skipped": "cells were synthesised; the file must differ"}
    elif cmp_template:
        summary["cmp_template"] = _cmp(Path(plan["template"]), dest, plan)
    summary["wall_s"] = time.perf_counter() - wall0
    summary["max_worker_rss_mb"] = max(r["maxrss_mb"] for r in results)
    # PASS/FAIL is about whether the model can LOAD the file. A stem of a type its cell never holds
    # loads fine and dies within a simulated year, so it is a loud warning, not a framing failure.
    summary["verdict"] = (
        "PASS"
        if summary["records"] == plan["ncell"]
        and summary["bad_litter_index"] == 0
        and summary.get("cmp_template", {}).get("identical", True)
        else "FAIL"
    )
    summary["warnings"] = (
        [f"{summary['foreign_type_stems']} stems of a type their cell's own state never holds"]
        if summary["foreign_type_stems"]
        else []
    )
    _write_json(out_dir / "verify.json", summary)
    print(json.dumps(summary, indent=1, default=_jsonable), flush=True)
    return summary


def _cmp(src: Path, dest: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """GNU `cmp` of the output against the template: the whole file when the plan is the whole
    template, else the record region against the template's own byte range for those cells."""
    wall0 = time.perf_counter()
    whole = plan["first_cell"] == 0 and plan["ncell"] == plan["template_ncell"]
    if whole:
        cmd = ["cmp", str(src), str(dest)]
    else:
        tr = RestartReader(src)
        start, _ = tr.extent(plan["first_cell"])
        _, end = tr.extent(plan["first_cell"] + plan["ncell"] - 1)
        skip_out = PREFIX_BYTES + 8 * plan["ncell"]
        cmd = [
            "cmp",
            f"--ignore-initial={start}:{skip_out}",
            f"--bytes={end - start}",
            str(src),
            str(dest),
        ]
    rc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "command": " ".join(cmd),
        "whole_file": whole,
        "identical": rc.returncode == 0,
        "stdout": rc.stdout.strip(),
        "stderr": rc.stderr.strip(),
        "wall_s": time.perf_counter() - wall0,
    }


# --------------------------------------------------------------------------------------------
# The cost report and the full-globe projection.
# --------------------------------------------------------------------------------------------
def cmd_summary(out_dir: Path) -> dict[str, Any]:
    plan = _load_plan(out_dir)
    rows: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    for b in plan["blocks"]:
        p = _shard_path(out_dir, b["k"]).with_suffix(".json")
        if b["kind"] == "shard" and p.exists():
            rep = json.loads(p.read_text())
            rows.extend(rep["cells"])
            blocks.append({k: v for k, v in rep.items() if k != "cells"})
    if not rows:
        out0: dict[str, Any] = {"blocks": 0, "note": "no shard was written; nothing to cost"}
        _write_json(out_dir / "summary.json", out0)
        return out0
    cells = pl.DataFrame(rows, infer_schema_length=None)
    cells.write_parquet(out_dir / "cells.parquet")
    by = cells.group_by("status").agg(
        pl.len().alias("n"),
        pl.col("cpu_s").mean().alias("cpu_s_mean"),
        pl.col("cpu_s").median().alias("cpu_s_median"),
        pl.col("cpu_s").quantile(0.99).alias("cpu_s_p99"),
        pl.col("wall_s").mean().alias("wall_s_mean"),
        pl.col("bytes_out").mean().alias("bytes_out_mean"),
    )
    status = {r["status"]: r for r in by.to_dicts()}
    out: dict[str, Any] = {"by_status": status, "blocks": len(blocks)}
    if blocks:
        out["block_wall_s"] = {
            "max": max(b["wall_s"] for b in blocks),
            "mean": float(np.mean([b["wall_s"] for b in blocks])),
        }
        out["block_cpu_s_total"] = float(sum(b["cpu_s"] for b in blocks))
        out["block_pool_build_s_total"] = float(sum(b["pool_build_s"] for b in blocks))
        out["worker_maxrss_mb"] = max(b["maxrss_mb"] for b in blocks)
    synth = cells.filter(pl.col("status") == "synthesised")
    if synth.height:
        out["synthesised"] = {
            "cells": synth.height,
            "stems_requested": int(synth["stems_requested"].sum()),
            "stems_placed": int(synth["stems_placed"].sum()),
            "inadmissible_placed": int(synth["inadmissible_placed"].sum()),
            "type_fallbacks": int(synth["type_fallbacks"].sum()),
            "treeless_template_cells": int(synth["treeless_template"].sum()),
            "predicted_treeless_cells": int(synth["predicted_treeless"].sum()),
        }
        out["projection"] = _project(plan, synth, blocks)
    for name in ("assembly.json", "verify.json"):
        if (out_dir / name).exists():
            out[name.removesuffix(".json")] = json.loads((out_dir / name).read_text())
    _write_json(out_dir / "summary.json", out)
    print(json.dumps(out, indent=1, default=_jsonable), flush=True)
    return out


def _project(plan: dict[str, Any], synth: pl.DataFrame, blocks: list[dict[str, Any]]) -> Any:
    """Full-globe synthesis cost, extrapolated from this run's cells by the STEMS each one gets.

    A cell's cost is dominated by its roster: the donor match is one distance row per placed stem.
    The number of stems a cell will be given is known in advance for EVERY cell -- it is the
    predicted `stems_per_patch` times the patch count -- so the per-cell CPU is regressed on stems
    placed here and summed over every cell the prediction file covers. One mean times a count
    would carry the dry-run block's own density straight into the projection; record size is a
    worse proxy (measured: correlation 0.74 against 0.88 for stems on the first dry run, and a
    record-size line through a block of dense cells goes NEGATIVE for a treeless one).

    The line is floored at the cheapest cell actually observed, so an extrapolation below the
    sampled range can never price a cell at zero or less. The plain mean-times-count figure is
    reported alongside, as the naive bound.
    """
    tmpl = RestartReader(Path(plan["template"]))
    sizes = tmpl.cell_sizes()
    all_preds, _ = load_predictions(
        Path(plan["predictions"]["path"]), 0, tmpl.ncell, tuple(plan["match_traits"])
    )
    npatch = 25  # every leg of the ground truth; the per-cell reports carry the real counts
    per_patch = np.array([all_preds[c]["stems_per_patch"] for c in sorted(all_preds)])
    stems_all = np.maximum(per_patch, 0.0) * npatch
    x = synth["stems_placed"].to_numpy().astype(np.float64)
    y = synth["cpu_s"].to_numpy().astype(np.float64)
    slope, intercept = np.polyfit(x, y, 1) if np.ptp(x) > 0 else (0.0, float(np.mean(y)))
    cpu_cells = float(np.sum(np.maximum(intercept + slope * stems_all, float(y.min()))))
    pooled = [b["pool_build_s"] for b in blocks if b.get("donors")]
    nblock = -(-tmpl.ncell // int(plan["block_size"]))
    cpu_pools = float(np.mean(pooled)) * nblock if pooled else 0.0
    cpu_h = (cpu_cells + cpu_pools) / 3600.0
    return {
        "basis": (
            f"{synth.height} cells synthesised in this run; CPU regressed linearly on stems "
            f"placed, floored at the cheapest observed cell, summed over the {per_patch.size} "
            f"cells the prediction file covers (of {tmpl.ncell}) at their PREDICTED stem count "
            f"x {npatch} patches; one donor pool per block of {plan['block_size']} ({nblock} "
            "blocks); pass-through cells cost ~nothing (a template byte-range copy); CPU only -- "
            "shard writing, assembly and verification are I/O and are measured separately"
        ),
        "cpu_s_vs_stems": {"intercept_s": float(intercept), "per_1000_stems_s": 1e3 * slope},
        "stems_sampled": {"min": float(x.min()), "max": float(x.max())},
        "stems_globe": {"median": float(np.median(stems_all)), "max": float(stems_all.max())},
        "cells_to_synthesise": int(per_patch.size),
        "cpu_hours_synthesis": cpu_cells / 3600.0,
        "cpu_hours_naive_mean_times_count": float(np.mean(y)) * per_patch.size / 3600.0,
        "cpu_hours_donor_pools": cpu_pools / 3600.0,
        "cpu_hours_total": cpu_h,
        "wall_hours_at_64_workers": cpu_h / 64.0,
        "bytes_to_write": int(np.sum(sizes)),
    }


# --------------------------------------------------------------------------------------------
# t0 at scale: reader -> streaming writer -> cmp against the source.
# --------------------------------------------------------------------------------------------
def cmd_t0(args: argparse.Namespace) -> dict[str, Any]:
    src = Path(args.template) if args.template else _template_default()
    reader = RestartReader(src)
    first = int(args.first_cell)
    ncell = reader.ncell - first if args.ncell is None else int(args.ncell)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wall0, cpu0 = time.perf_counter(), time.process_time()
    with reader, RestartWriter(dest, reader.generic, reader.restart, ncell, firstcell=first) as w:
        for i, cell in enumerate(range(first, first + ncell)):
            w.append(reader.cell_bytes(cell))
            if (i + 1) % 5000 == 0:
                el = time.perf_counter() - wall0
                print(
                    f"  {i + 1} cells, {w.bytes_written / 2**30:.1f} GiB, "
                    f"{w.bytes_written / 1e6 / el:.0f} MB/s",
                    flush=True,
                )
    wall_write = time.perf_counter() - wall0
    cpu_write = time.process_time() - cpu0
    size = dest.stat().st_size
    plan = {"first_cell": first, "ncell": ncell, "template_ncell": reader.ncell}
    c = _cmp(src, dest, plan)
    back = RestartReader(dest)
    index_ok = bool(
        np.array_equal(
            back.index,
            reader.index[first : first + ncell] - reader.index[first] + PREFIX_BYTES + 8 * ncell,
        )
    )
    report = {
        "source": str(src),
        "dest": str(dest),
        "first_cell": first,
        "ncell": ncell,
        "bytes": size,
        "write_wall_s": wall_write,
        "write_cpu_s": cpu_write,
        "write_mb_per_s": size / 1e6 / wall_write,
        "cmp": c,
        "cmp_mb_per_s_each_side": size / 1e6 / max(c["wall_s"], 1e-9),
        "index_rebased_equal": index_ok,
        "maxrss_mb": _maxrss_mb(),
        "host": os.uname().nodename,
        "verdict": "BYTE-IDENTICAL" if (c["identical"] and index_ok) else "DIFFERS",
    }
    if not args.keep and report["verdict"] == "BYTE-IDENTICAL":
        dest.unlink()
        report["dest_deleted_after_cmp"] = True
    rep_path = Path(args.report) if args.report else dest.with_suffix(".t0.json")
    _write_json(rep_path, report)
    print(json.dumps(report, indent=1, default=_jsonable), flush=True)
    return report


# --------------------------------------------------------------------------------------------
# The command line.
# --------------------------------------------------------------------------------------------
def cmd_plan(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan, preds = make_plan(args)
    _write_json(_preds_path(out_dir), {str(c): v for c, v in preds.items()})
    if _plan_path(out_dir).exists():
        old = _load_plan(out_dir)
        if old["plan_sha256"] != plan["plan_sha256"] and any((out_dir / "shards").glob("*.json")):
            print("  NOTE: replacing a plan whose shards exist; they will be rewritten", flush=True)
    _write_json(_plan_path(out_dir), plan)
    n_shard = sum(1 for b in plan["blocks"] if b["kind"] == "shard")
    print(
        f"plan: {plan['ncell']} cells from {plan['first_cell']} in {len(plan['blocks'])} blocks "
        f"of {plan['block_size']}; {n_shard} to write as shards, the rest straight from the "
        f"template; mode={plan['mode']}; plan {plan['plan_sha256'][:12]}",
        flush=True,
    )
    return plan


def cmd_farm(out_dir: Path, jobs: int, workers: int) -> None:
    """Print the multi-job submission: shard jobs over disjoint block ranges, then assemble+verify
    after all of them. Printed, not run, so the wrapper and its ledger rows stay visible."""
    plan = _load_plan(out_dir)
    nb = len(plan["blocks"])
    step = -(-nb // jobs)
    me = "scripts/synth_global.py"
    print("# run from the repo root; every submission goes through the wrapper (ledger rows)")
    print("deps=''")
    for j, a in enumerate(range(0, nb, step)):
        b = min(a + step, nb)
        print(
            f"jid=$(PARTITION=priority NCPUS={workers} TIME=04:00:00 scripts/sbatch_py.sh "
            f"D-glb-shards-{j} {me} shards --out-dir {out_dir} --blocks {a}:{b} "
            f"--workers {workers} | awk '/submitted/{{print $5}}'); deps=\"$deps:$jid\""
        )
    print(
        f"DEPENDENCY=afterok$deps PARTITION=priority NCPUS={workers} TIME=04:00:00 "
        f"scripts/sbatch_py.sh D-glb-assemble {me} finish --out-dir {out_dir} "
        f"--workers {workers}"
    )


def _allocated_cpus() -> int:
    """The CPUs this process may run on -- SLURM's allocation, not the node's 128."""
    return len(os.sched_getaffinity(0))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def planning(p: argparse.ArgumentParser) -> None:
        p.add_argument("--template", default=None, help="global restart to read (default: 1999)")
        p.add_argument("--first-cell", type=int, default=0)
        p.add_argument("--ncell", type=int, default=None, help="default: to the end of the grid")
        p.add_argument("--block-size", type=int, default=DEFAULT_BLOCK)
        p.add_argument("--mode", choices=("synth", "identity"), default="synth")
        p.add_argument("--pred", default=None, help="parquet with cell + pred_<q> (natural scale)")
        p.add_argument("--only", default=None, help="synthesise only cells a:b; the rest pass")
        p.add_argument("--donor-rule", default="proximity-band")
        p.add_argument("--donor-opts", default=None, help='JSON, e.g. {"band": 20}')
        p.add_argument("--seed", type=int, default=DEFAULT_SEED)
        p.add_argument("--match-traits", default=",".join(MATCH_TRAITS))
        p.add_argument("--synth-kwargs", default=None, help="JSON of extra synthesise_cell kwargs")
        p.add_argument("--on-error", choices=("raise", "pass"), default="raise")
        p.add_argument(
            "--treeless-template",
            choices=("pass", "synthesise"),
            default="pass",
            help="a forest predicted where the template holds no tree: keep the template "
            "(default; the synthesiser has no admissible tree type to copy) or synthesise anyway",
        )

    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--out-dir", required=True)
        planning(p)
        if name == "run":
            p.add_argument("--workers", type=int, default=_allocated_cpus())
            p.add_argument("--cmp-template", action="store_true")
            p.add_argument("--keep-shards", action="store_true")
    p = sub.add_parser("shards")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--blocks", default="all", help="plan block range a:b (default all)")
    p.add_argument("--workers", type=int, default=_allocated_cpus())
    for name in ("assemble", "verify", "finish", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--out-dir", required=True)
        p.add_argument("--workers", type=int, default=_allocated_cpus())
        p.add_argument("--cmp-template", action="store_true")
        p.add_argument("--keep-shards", action="store_true")
    p = sub.add_parser("farm")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--workers", type=int, default=64)
    p = sub.add_parser("t0")
    p.add_argument("--out", required=True)
    p.add_argument("--template", default=None)
    p.add_argument("--first-cell", type=int, default=0)
    p.add_argument("--ncell", type=int, default=None)
    p.add_argument("--report", default=None)
    p.add_argument("--keep", action="store_true", help="keep the copy after a clean cmp")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "t0":
        return 0 if cmd_t0(args)["verdict"] == "BYTE-IDENTICAL" else 1
    out_dir = Path(args.out_dir)
    if args.cmd == "plan":
        cmd_plan(args)
        return 0
    if args.cmd == "farm":
        cmd_farm(out_dir, args.jobs, args.workers)
        return 0
    if args.cmd == "run":
        cmd_plan(args)
        cmd_shards(out_dir, "all", args.workers)
    if args.cmd == "shards":
        cmd_shards(out_dir, args.blocks, args.workers)
        return 0
    if args.cmd in ("run", "finish", "assemble"):
        cmd_assemble(out_dir)
    if args.cmd == "assemble":
        return 0
    verdict = "PASS"
    if args.cmd in ("run", "finish", "verify"):
        verdict = cmd_verify(out_dir, args.workers, args.cmp_template)["verdict"]
    cmd_summary(out_dir)
    if args.cmd in ("run", "finish") and not args.keep_shards and verdict == "PASS":
        # The shard BODIES are now inside the assembled file, byte for byte (verify checked each
        # one's hash). The per-block reports are small and are the cost record, so they stay.
        for shard in sorted((out_dir / "shards").glob("shard_*.lpj")):
            shard.unlink()
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
