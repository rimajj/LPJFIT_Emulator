#!/usr/bin/env python
"""D2: the pilot corpus -- 200 cells x 30 climates x 1 seed, planned, generated and harvested.

    # 1. the plan: choose the cells, fix the design, write every manifest. Cheap, deterministic.
    scripts/sbatch_py.sh D-pilot-plan scripts/corpus_pilot.py --stage plan --version v1

    # 2. the forcing and the configs: 6,000 forcing sets and 6,000 spin-up configs.
    NCPUS=16 TIME=02:00:00 scripts/sbatch_py.sh D-pilot-build scripts/corpus_pilot.py \\
        --stage build --version v1 --workers 16

    # 3. check every file the manifests promise actually exists, before 670 core-hours burn.
    scripts/sbatch_py.sh D-pilot-verify scripts/corpus_pilot.py --stage verify --version v1

    # 4. the spin-ups, one job per manifest shard (LPJ_DEFINES="" selects the SPIN-UP branch).
    LPJ_DEFINES="" PARTITION=standard TIME=01:00:00 scripts/sbatch_cmodel.sh \\
        --manifest <manifests>/manifest_s00.tsv D-pilot-v1-s00

    # 5. the single harvest command for the whole campaign, however many shards it took.
    scripts/sbatch_py.sh D-pilot-harvest scripts/corpus_pilot.py --stage harvest --version v1

    # 6. the corpus table itself: every restart record and its own forcing, decoded and joined.
    NCPUS=16 TIME=00:30:00 scripts/sbatch_py.sh D-pilot-decode scripts/corpus_pilot.py \\
        --stage decode --version v1 --workers 16

WHAT THIS IS. The corpus rung 1 is scored on. Every existing ground-truth leg holds exactly ONE
climate per location, so climate and geography are collinear and a warming response is not
separately identified (`MEMORY.md:ident-limit`) -- the predecessor's kill test failed on precisely
that. This spins the SAME cell up under THIRTY climates, which decollinearises them by construction
and is the experiment the predecessor could never run.

THE THREE THINGS THAT MAKE IT A DESIGN RATHER THAN A PILE OF RUNS

  * The cells are stratified over the populated 15-degree tiles and space-filling in the five
    perturbation axes' own baselines (`vegemu.corpus.select`), so a spatially blocked fold holds out
    a climate with no near neighbour instead of holding out an interpolation.
  * The thirty climates are THE SAME thirty at every cell (`pilot_design(30)`). That is what makes
    "held-out perturbation level" a meaningful test at all -- a per-cell random design would cover
    the axis space better but there would be no level to hold out. The cost is disclosed: 30 shared
    points sample the five-dimensional axis space at 11 factorial-core points and 18 free ones, and
    that coverage is what the mid tier's 100 climates buys, not more cells.
  * The control is design point one and is EXACTLY neutral, so "same cell, same seed, same config,
    same forcing window, only the climate differs" is available for free at every cell. That paired
    contrast is rung 1's decisive null (the same-cell baseline).

⚠ SPIN-UP LENGTH IS 1000 YEARS AND IS NOT NEGOTIABLE HERE. The hoped-for 3.3x saving from a shorter
spin-up is refuted: global vegetation carbon is 728 Pg C at year 300 against 890 at year 1000, so a
shortened spin-up produces a systematically DIFFERENT state, not a cheaper version of the same one
(`docs/decisions/20260908-D-spinup-is-not-converged.md`). Every run here is the full protocol.

⚠ AND THE TARGET IS PROTOCOL-DEFINED, NOT AN EQUILIBRIUM. What comes out is "the state LPJmL-FIT
reaches after its own standard 1000-year spin-up", which is still drifting at +6.8 %/century in the
median cell. That is the right target -- it is exactly what a user of the model gets, and skipping
it is exactly the saving on offer -- but it must never be called an equilibrium.

⚠ EVERY CONFIG IS BUILT BY PATCHING THE GROUND TRUTH'S OWN SAVED CONFIGURATION, and every
replacement is asserted (`corpus_spinup_config.py`). A fresh config would be a second, unvalidated
configuration whose differences from the truth nobody has enumerated.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import polars as pl

from vegemu.binfmt.restart import RestartReader
from vegemu.corpus import climate as climate_mod
from vegemu.corpus import state as state_mod
from vegemu.corpus.perturb import DESIGN_SEED, VARS, pilot_design
from vegemu.corpus.select import pilot_cells
from vegemu.paths import paths, scratch

REPO = Path(__file__).resolve().parent.parent

NCELL = 200
NPOINT = 30
SEED = 1
NSPINUP = 1000
# One SLURM job per this many single-cell spin-ups. Each member is ~6 minutes, so a shard of 250 is
# a job of well under an hour -- short enough to requeue cheaply, few enough steps that SLURM
# launches them all promptly. ⚠ PARTITION=priority is capped at 64 CPU per job, so a shard larger
# than 64 must go to PARTITION=standard (up to 2048).
SHARD_SIZE = 250
# The smallest restart record the format admits: 25 patches with no vegetation in any of them
# (`MEMORY.md:restart-size`, measured on the real 119 GiB file). A run whose record is this size
# grew nothing, and a run that grew a forest is nearer 1.9 MB. Used only as a proxy in `harvest`.
TREELESS_RESTART_BYTES = 380_000


def _load(name: str) -> ModuleType:
    """Import a sibling script by path. They are scripts, not package modules, by ownership.

    ⚠ THE `sys.modules` REGISTRATION IS LOAD-BEARING, and its absence fails nowhere near itself.
    Every module here opens with `from __future__ import annotations`, so all annotations are
    strings; `@dataclass` then resolves them through `sys.modules[cls.__module__]`, which is `None`
    for a module loaded by path and never registered. The symptom is an `AttributeError` inside
    `dataclasses.py` the moment the loaded script merely DEFINES a dataclass, so it reads as a
    broken standard library rather than a broken loader.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def meta_dir(version: str) -> Path:
    return scratch("corpus", f"pilot-{version}")


def manifest_dir(version: str) -> Path:
    """Manifests live with the runs: `sbatch_cmodel.sh` writes its task-farm runner beside them."""
    return scratch("runs", f"pilot-{version}", "manifests")


def _under(kind: str, version: str, cell: int, point: str) -> Path:
    """A per-run directory. `Path`, not `scratch()`: the plan stage must not create 12,000 dirs."""
    root = Path(str(paths()["scratch"]["root"]))
    return root / kind / f"pilot-{version}" / f"c{cell}" / point


def forcing_dir(version: str, cell: int, point: str) -> Path:
    return _under("forcing", version, cell, point)


def run_dir(version: str, cell: int, point: str) -> Path:
    return _under("runs", version, cell, point)


def run_tag(cell: int, point: str) -> str:
    return f"c{cell}-{point}-s{SEED}"


def config_path(version: str, cell: int, point: str) -> Path:
    """Where `corpus_spinup_config.py` puts this run's config. Named once, used by every stage."""
    tag = run_tag(cell, point)
    return run_dir(version, cell, point) / f"lpjml_spinup_{tag}.js"


# ------------------------------------------------------------------------------------------------
# stage: plan
# ------------------------------------------------------------------------------------------------


def stage_plan(version: str, ncell: int, npoint: int, shard_size: int) -> int:
    out = meta_dir(version)
    sel = pilot_cells(ncell)
    design = pilot_design(npoint)
    if design[0].name != "control" or not design[0].is_neutral:
        raise AssertionError("design point one must be the exactly-neutral control")
    if any(p.hold_huss_diagnostic for p in design):
        raise AssertionError(
            "a design point carries the hold-huss diagnostic flag. That arm deliberately breaks "
            "the fixed-relative-humidity rule and is for attribution only, never a corpus row."
        )

    cells = sel.cells()
    sel.table.write_parquet(out / "cells.parquet")
    sel.table.write_csv(out / "cells.csv")
    pl.DataFrame(
        [
            {
                "point": p.name,
                "dtemp_k": p.dtemp,
                "fprec": p.fprec,
                "sprec": p.sprec,
                "frad": p.frad,
                "fiav": p.fiav,
                "kind": "control"
                if p.is_neutral
                else ("core" if p.name.startswith("core_") else "lhs"),
            }
            for p in design
        ]
    ).write_csv(out / "design.csv")

    rows = [
        {
            "name": run_tag(cell, p.name),
            "cell": cell,
            "point": p.name,
            "config": str(config_path(version, cell, p.name)),
            "run_dir": str(run_dir(version, cell, p.name)),
            "forcing": str(forcing_dir(version, cell, p.name)),
        }
        for cell in cells
        for p in design
    ]
    pl.DataFrame(rows).write_csv(out / "runs.csv")

    mdir = manifest_dir(version)
    for old in sorted(mdir.glob("manifest_s*.tsv")):
        old.unlink()
    shards: list[Path] = []
    for i in range(0, len(rows), shard_size):
        chunk = rows[i : i + shard_size]
        path = mdir / f"manifest_s{i // shard_size:02d}.tsv"
        path.write_text(
            "".join(f"{r['name']}\t{r['config']}\t{r['run_dir']}\n" for r in chunk), "utf-8"
        )
        shards.append(path)

    prov = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_pilot.py --stage plan",
        "tier": "pilot",
        "corpus_version": version,
        "git_commit": _git_commit(),
        "nrun": len(rows),
        "ncell": len(cells),
        "npoint": len(design),
        "seed": SEED,
        "nspinup": NSPINUP,
        "spinup_note": (
            "1000 years, the full protocol. The target state is PROTOCOL-DEFINED and still "
            "drifting at ~+6.8 %/century in the median cell; it is not an equilibrium "
            "(docs/decisions/20260908-D-spinup-is-not-converged.md)."
        ),
        "design_seed": DESIGN_SEED,
        "design_shared_across_cells": True,
        "design_note": (
            "the same 30 climates at every cell, which is what makes a held-out perturbation LEVEL "
            "a meaningful test; the cost is that the five-dimensional axis space is sampled at 18 "
            "free points, not 200 x 18"
        ),
        "selection": sel.as_dict(),
        "base_window": [1970, 1999],
        "co2": "untouched and never written (MEMORY.md:co2-closed)",
        "shards": [str(p) for p in shards],
        "shard_size": shard_size,
        "sources": _source_provenance(),
        "binary": _binary_provenance(),
        "plan_sha256": "",
    }
    # The hash a pre-registration cites. Over the PLAN -- the cell list and the design -- and the
    # identity of every source file, not over the 11.7 GB inputs themselves: hashing five global
    # `.clm` files would read 60 GB to restate what size and mtime already pin down. Said plainly
    # here rather than left for a reader to assume it is a content hash of everything.
    prov["plan_sha256"] = hashlib.sha256(
        (out / "cells.csv").read_bytes()
        + (out / "design.csv").read_bytes()
        + json.dumps(prov["sources"], sort_keys=True).encode()
    ).hexdigest()
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", "utf-8")

    print(f"pilot corpus {version}: {len(cells)} cells x {len(design)} climates = {len(rows)} runs")
    print(f"  eligible tree-bearing cells   {sel.eligible}")
    print(
        f"  populated {int(sel.as_dict()['tile_degrees'])}-degree tiles      "
        f"{sel.tiles_populated}, of which covered {sel.tiles_covered}"
    )
    for stage, count in sorted(sel.as_dict()["by_stage"].items()):
        print(f"  cells chosen by {stage:12s}  {count}")
    print(
        f"  design: {sum(1 for p in design if p.is_neutral)} control, "
        f"{sum(1 for p in design if p.name.startswith('core_'))} factorial core, "
        f"{sum(1 for p in design if p.name.startswith('lhs'))} hypercube"
    )
    print(f"  plan_sha256 {prov['plan_sha256']}")
    print(f"  tables      {out}")
    print(f"  manifests   {len(shards)} shards of <= {shard_size} in {mdir}")
    if shard_size > 64:
        print(
            "  ⚠ a shard larger than 64 must go to PARTITION=standard; priority is capped at "
            "64 CPU per job and refuses at submit time."
        )
    return 0


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _source_provenance() -> dict[str, Any]:
    """Every forcing file this corpus reads, with the identity that pins the build it came from."""
    cfg = paths()
    perturb = _load("corpus_perturb_clm")
    out: dict[str, Any] = {}
    for leg in ("historical", perturb.CALIB_LEG):
        for var, p in cfg["inputs"][leg].items():
            st = Path(str(p)).stat()
            out[f"{leg}.{var}"] = {
                "path": str(p),
                "bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
            }
    return out


def _binary_provenance() -> dict[str, Any]:
    """Which LPJmL-FIT build will run. Two builds are never byte-identical, so this is recorded."""
    p = Path(str(paths()["lpjml"]["binary"]))
    st = p.stat()
    return {
        "path": str(p),
        "bytes": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
        "version": str(paths()["lpjml"]["version"]),
        "note": (
            "generate the WHOLE corpus with ONE binary. The stored historical ground truth came "
            "from the 2026-02-05 build; this is the 2026-08-12 one, so corpus runs are comparable "
            "to each other and NOT to the stored global output (MEMORY.md:subset-diverges)."
        ),
    }


# ------------------------------------------------------------------------------------------------
# stage: build -- the forcing sets and the configs
# ------------------------------------------------------------------------------------------------


def _build_cell(args: tuple[str, int, int]) -> dict[str, Any]:
    """One cell: read its baseline once, then write all `npoint` forcing sets and configs.

    Runs in a worker process, so it imports what it needs itself and returns only small summaries.
    """
    version, cell, npoint = args
    perturb = _load("corpus_perturb_clm")
    cfgmod = _load("corpus_spinup_config")
    design = pilot_design(npoint)

    # The one read that must not be repeated per point: the 30-year baseline block plus the
    # calibration contrast out of the scenario leg.
    cb = perturb.load_base(range(cell, cell + 1))
    wrote: list[dict[str, Any]] = []
    for pert in design:
        fdir = forcing_dir(version, cell, pert.name)
        record = perturb.write_point(cb, pert, fdir)
        rdir = run_dir(version, cell, pert.name)
        (rdir / "output").mkdir(parents=True, exist_ok=True)
        (rdir / "restart").mkdir(parents=True, exist_ok=True)
        tag = run_tag(cell, pert.name)
        input_js = cfgmod.build_input_js(fdir, rdir, tag)
        config = cfgmod.build_config(cell, input_js, rdir, tag=tag, seed=SEED, nspinup=NSPINUP)
        wrote.append(
            {
                "point": pert.name,
                "config": str(config),
                "bytes": sum(int(record["files"][v]["bytes"]) for v in VARS),
                "neutral_byte_identity": all(
                    "neutral_byte_identity" in record["files"][v] for v in VARS
                )
                if pert.is_neutral
                else None,
                "tas_ann_c": record["diagnostics"]["tas_ann_c"],
                "pr_ann_mm": record["diagnostics"]["pr_ann_mm"],
            }
        )
    return {"cell": cell, "npoint": len(wrote), "points": wrote}


def _build_cell_guarded(args: tuple[str, int, int]) -> dict[str, Any]:
    try:
        return _build_cell(args)
    # One bad cell must not lose the other 199, so the traceback is returned rather than raised --
    # and `stage_build` exits non-zero on any of them, so a partial corpus is never silently green.
    except Exception:
        return {"cell": args[1], "error": traceback.format_exc(limit=6)}


def stage_build(version: str, workers: int, shard: int, nshard: int, npoint: int) -> int:
    out = meta_dir(version)
    runs = pl.read_csv(out / "runs.csv")
    cells = sorted(set(int(c) for c in runs["cell"].to_list()))
    mine = cells[shard::nshard] if nshard > 1 else cells
    print(
        f"building {len(mine)} of {len(cells)} cells x {npoint} climates "
        f"(shard {shard}/{nshard}, {workers} workers)"
    )

    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    jobs = [(version, cell, npoint) for cell in mine]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_build_cell_guarded, j): j[1] for j in jobs}
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                (failed if "error" in res else done).append(res)
                if i % 20 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} cells  ({len(failed)} failed)", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            res = _build_cell_guarded(j)
            (failed if "error" in res else done).append(res)
            if i % 20 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} cells  ({len(failed)} failed)", flush=True)

    total_bytes = sum(int(p["bytes"]) for r in done for p in r["points"])
    neutral = [p for r in done for p in r["points"] if p["neutral_byte_identity"] is not None]
    summary = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "shard": shard,
        "nshard": nshard,
        "cells_built": len(done),
        "cells_failed": len(failed),
        "forcing_bytes": total_bytes,
        "neutral_points_checked": len(neutral),
        "neutral_byte_identity_all_pass": all(bool(p["neutral_byte_identity"]) for p in neutral),
        "failures": failed,
    }
    (out / f"build_s{shard:02d}of{nshard:02d}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    print(f"forcing written: {total_bytes / 1e9:.2f} GB over {len(done)} cells")
    print(
        f"neutral byte identity: {len(neutral)} control points checked, "
        f"all pass = {summary['neutral_byte_identity_all_pass']}"
    )
    if not summary["neutral_byte_identity_all_pass"]:
        print(
            "  ⚠ a control point did NOT reproduce the source bytes. The writer is not a no-op "
            "on the identity design point, so no perturbed file it produced can be trusted."
        )
        return 1
    if failed:
        print(f"⚠ {len(failed)} cells FAILED; the corpus is incomplete:", file=sys.stderr)
        for f in failed[:5]:
            print(f"  cell {f['cell']}:\n{f['error']}", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------------------------------------
# stage: verify -- does every file the manifests promise exist, before 670 core-hours burn
# ------------------------------------------------------------------------------------------------


def stage_verify(version: str) -> int:
    out = meta_dir(version)
    runs = pl.read_csv(out / "runs.csv")
    filenames = list(_load("corpus_perturb_clm").OUT_NAME.values())
    missing_cfg: list[str] = []
    missing_forcing: list[str] = []
    sizes: dict[int, int] = {}
    for name, config, forcing in zip(
        runs["name"].to_list(), runs["config"].to_list(), runs["forcing"].to_list(), strict=True
    ):
        if not Path(config).is_file():
            missing_cfg.append(name)
        for fname in filenames:
            f = Path(forcing) / fname
            if not f.is_file():
                missing_forcing.append(f"{name}/{fname}")
            else:
                size = f.stat().st_size
                sizes[size] = sizes.get(size, 0) + 1

    total = runs.height
    print(f"pilot corpus {version}: {total} runs promised by the manifests")
    print(f"  configs present        {total - len(missing_cfg)}/{total}")
    print(f"  forcing files present  {sum(sizes.values())}/{total * 5}")
    print(f"  distinct forcing sizes {sorted(sizes.items(), reverse=True)[:4]}")
    if len(sizes) > 1:
        print(
            "  ⚠ forcing files are NOT all the same size. A `.clm` size mismatch means the "
            "dtype or the year count is wrong and every value read is silently shifted."
        )
    for label, items in (("configs", missing_cfg), ("forcing files", missing_forcing)):
        if items:
            print(f"  ⚠ {len(items)} missing {label}, first few: {items[:5]}", file=sys.stderr)
    ok = not missing_cfg and not missing_forcing and len(sizes) == 1
    print(f"verdict: {'READY to submit' if ok else 'NOT READY -- do not submit'}")
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------
# stage: harvest -- the one command that judges the whole campaign, however many shards it took
# ------------------------------------------------------------------------------------------------


def stage_harvest(version: str) -> int:
    """Count the runs that printed the MODEL'S OWN completion line, and the restarts they wrote.

    Never the exit codes: the stock job files always exit 0, so a run that died mid-spin-up leaves a
    plausible truncated output behind a green row (`MEMORY.md:c-log-truth`).
    """
    out = meta_dir(version)
    runs = pl.read_csv(out / "runs.csv")
    ok, no_line, no_log, no_restart = 0, [], [], []
    sizes: list[int] = []
    treeless: list[str] = []
    for name, rdir in zip(runs["name"].to_list(), runs["run_dir"].to_list(), strict=True):
        log = Path(rdir) / f"lpjml.{name}.log"
        if not log.is_file() or log.stat().st_size == 0:
            no_log.append(name)
            continue
        if "successfully terminated" in log.read_text(errors="replace"):
            ok += 1
        else:
            no_line.append(name)
        restart = Path(rdir) / "restart" / f"restart_{name}.lpj"
        if not restart.is_file() or restart.stat().st_size == 0:
            no_restart.append(name)
            continue
        size = restart.stat().st_size
        sizes.append(size)
        if size <= TREELESS_RESTART_BYTES:
            treeless.append(name)

    total = runs.height
    print(f"pilot corpus {version}: {total} runs")
    print(f"  printed the model's own completion line  {ok}/{total}")
    print(f"  no log at all (never started, or dead)   {len(no_log)}")
    print(f"  log without the completion line          {len(no_line)}")
    print(f"  no restart file written                  {len(no_restart)}")
    for label, items in (
        ("never started", no_log),
        ("did not complete", no_line),
        ("wrote no restart", no_restart),
    ):
        if items:
            print(f"  first few {label}: {items[:5]}")

    # ⚠ A COMPLETE CAMPAIGN IS NOT THE SAME AS A USABLE CORPUS. A restart record is ~1.9 MB with a
    # forest and bottoms out near 360 KB with no vegetation at all (`MEMORY.md:restart-size`), so
    # the size distribution is a free first look at how many design points killed the forest. It is
    # a PROXY, not the stem count -- that comes from decoding the records into the corpus table --
    # but it is the number that says whether rung 1 would be scoring forests or scoring emptiness.
    if sizes:
        arr = np.sort(np.asarray(sizes, dtype=np.int64))
        pct = [int(np.percentile(arr, q)) for q in (5, 25, 50, 75, 95)]
        print(f"  restart bytes p5/p25/p50/p75/p95         {'/'.join(f'{p:,}' for p in pct)}")
        print(
            f"  at or below the treeless floor           {len(treeless)}/{len(sizes)} "
            f"({100 * len(treeless) / len(sizes):.1f} %, floor {TREELESS_RESTART_BYTES:,} B)"
        )
        if len(treeless) > len(sizes) // 2:
            print(
                "  ⚠ MORE THAN HALF the runs produced a vegetation-free state. The campaign can be "
                "complete and the corpus still be mostly empty -- report this fraction with every "
                "number the corpus supports, and check the axis ranges before scoring anything."
            )

    complete = ok == total and not no_restart
    print(
        f"verdict: {'COMPLETE' if complete else 'INCOMPLETE'} -- "
        f"{'harvestable' if complete else 'rerun the missing members before scoring anything'}"
    )
    return 0 if complete else 1


# ------------------------------------------------------------------------------------------------
# stage: decode -- the 6,000 restarts and their forcing become the corpus table
# ------------------------------------------------------------------------------------------------

# The state a run produces is the end of 1000 spin-up years that CYCLE these 30 forcing years, and
# LPJmL-FIT labels the restart it writes with the last of them. So `state_year` is bookkeeping, not
# a date: nothing here is "the state of 1999", and the climate summary is over the whole window
# rather than any single year. Asserted per run against the restart's own header.
STATE_YEAR = 1999


def _decode_run(args: tuple[str, int, str, str, str]) -> dict[str, Any]:
    """One run: its restart record and its own perturbed forcing, as one corpus row."""
    name, cell, point, rdir, fdir = args
    perturb = _load("corpus_perturb_clm")
    restart = Path(rdir) / "restart" / f"restart_{name}.lpj"

    # Two opens of the same file on purpose. The year label is a header read of 92 bytes, and doing
    # it here keeps the "a per-cell restart holds ONE record" assertion in `single_cell_state`,
    # where every future caller gets it, instead of copied into this script.
    restart_year = RestartReader(restart).generic.firstyear
    row: dict[str, Any] = {
        "name": name,
        "cell": cell,
        "point": point,
        "seed": SEED,
        "restart_year": restart_year,
        "restart_bytes": restart.stat().st_size,
    }
    row.update(state_mod.single_cell_state(restart, cell))

    # ⚠ `climate_columns`, NEVER `climate_table`: this runs in a forked worker, and polars' thread
    # pool does not survive a fork -- a DataFrame touched here hangs the child forever with no
    # error, so the job burns its whole wall-clock limit and produces nothing.
    window = climate_mod.Window("pilot", *perturb.BASE_WINDOW, STATE_YEAR)
    files = {v: str(Path(fdir) / perturb.OUT_NAME[v]) for v in climate_mod.VARS}
    cl = climate_mod.climate_columns(window, files=files)
    if cl["cell"].size != 1:
        raise AssertionError(f"{name}: forcing describes {cl['cell'].size} cells, expected 1")
    if int(cl["cell"][0]) != cell:
        raise AssertionError(
            f"{name}: forcing declares cell {int(cl['cell'][0])}, the run is cell {cell}. The "
            "`.clm` header's firstcell is the only record of which cell a subset file holds."
        )
    row["lon"] = float(cl["lon"][0])
    row["lat"] = float(cl["lat"][0])
    row["leg"] = str(cl["leg"][0])
    row["state_year"] = int(cl["state_year"][0])
    for feat in climate_mod.CLIMATE_FEATURES:
        row[feat] = float(cl[feat][0])
    return row


def _decode_run_guarded(args: tuple[str, int, str, str, str]) -> dict[str, Any]:
    # One unreadable restart must not lose the other 5,999, and `stage_decode` exits non-zero on
    # any of them, so a partial corpus table is never silently green.
    try:
        return _decode_run(args)
    except Exception:
        return {"name": args[0], "cell": args[1], "error": traceback.format_exc(limit=6)}


def _decode_all(
    jobs: list[tuple[str, int, str, str, str]], nproc: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every run decoded, split into the rows that worked and the ones that raised."""
    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    if nproc > 1:
        with ProcessPoolExecutor(max_workers=nproc) as pool:
            results = pool.map(_decode_run_guarded, jobs, chunksize=8)
            for i, res in enumerate(results, 1):
                (failed if "error" in res else done).append(res)
                if i % 500 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} runs  ({len(failed)} failed)", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            res = _decode_run_guarded(j)
            (failed if "error" in res else done).append(res)
            if i % 500 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} runs  ({len(failed)} failed)", flush=True)
    return done, failed


def _corpus_frame(
    done: list[dict[str, Any]], design: pl.DataFrame, cells: pl.DataFrame
) -> pl.DataFrame:
    """The decoded rows joined to the design and the cell table, in the corpus column order.

    Column order is the contract: the keys a fold is built from, then the design coefficients that
    NAME the climate a row was grown under, then the features a model may see, then the targets.
    `cell`, `lon` and `lat` sit with the keys because the geographic address is a pre-registered
    NULL, not a feature (`vegemu.corpus.climate` header) -- a feature set that quietly contains it
    turns any per-cell score into a spatial-interpolation score.
    """
    keys = ("name", "cell", "point", "kind", "tile", "stage", "seed", "leg", "state_year")
    coeff = ("dtemp_k", "fprec", "sprec", "frad", "fiav")
    targets = tuple(c for c in state_mod.STATE_COLUMNS if c != "cell")
    # `truth_stems_total` is the stem count the STORED GROUND TRUTH holds at this cell, carried in
    # so the control point can be checked against it. It is a diagnostic, never a feature: it is a
    # lagged truth, and a model that saw it would score beautifully on a held-out cell.
    from_cells = cells.select("cell", "tile", "stage", "stems_total").rename(
        {"stems_total": "truth_stems_total"}
    )
    # `summarise_cell` reports every state column as a float, `cell` included, so the raw rows
    # carry a f64 cell number and joining it against an integer key is a `SchemaError`.
    return (
        pl.DataFrame(done)
        .with_columns(pl.col("cell").cast(pl.Int32))
        .join(design, on="point", how="left")
        .join(from_cells, on="cell", how="left")
        .select(
            [
                *keys,
                *coeff,
                "lon",
                "lat",
                *climate_mod.CLIMATE_FEATURES,
                *targets,
                "restart_year",
                "restart_bytes",
                "truth_stems_total",
            ]
        )
    )


def _decode_parts(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """The three slices every decode number is quoted against: treeless, control, treeless control.

    ⚠ THE CONTROL POINT IS THE CORPUS'S OWN SANITY CHECK, and it is the first number to look at.
    Its forcing is byte-identical to the historical baseline, so a control run should grow roughly
    the forest the stored ground truth holds at that cell. It does NOT have to match exactly -- the
    ground truth ran a 1000-year spin-up plus a historical transient with the real year-by-year
    climate under the 2026-02-05 binary, while this cycles 30 years under the 2026-08-12 one
    (`MEMORY.md:subset-diverges`) -- but a control that is EMPTY where the truth has a forest means
    the corpus is not describing the same model, and no rung-1 score computed on it would mean
    anything.
    """
    treeless = frame.filter(pl.col("stems_total") <= 0)
    control = frame.filter(pl.col("point") == "control")
    return treeless, control, control.filter(pl.col("stems_total") <= 0)


def _report_decode(frame: pl.DataFrame, summary: dict[str, Any], dest: Path) -> None:
    treeless, control, ctrl_treeless = _decode_parts(frame)
    print(f"\ncorpus table: {frame.height} rows x {frame.width} cols in {summary['seconds']} s")
    print(f"  features / targets              {summary['nfeature']} / {summary['ntarget']}")
    print(
        f"  treeless rows (stems_total = 0) {treeless.height}/{frame.height} "
        f"({100 * treeless.height / frame.height:.1f} %)"
    )
    print(
        f"  treeless CONTROL rows           {ctrl_treeless.height}/{control.height} "
        f"({summary['treeless_control_cells_treed_in_ground_truth']} of those cells are "
        "tree-bearing in the stored ground truth)"
    )
    if ctrl_treeless.height:
        print(
            "  ⚠ a control point is byte-identical forcing, so an EMPTY control at a cell the "
            "ground truth holds a forest at is a corpus defect, not a climate response. First "
            f"few: {ctrl_treeless['name'].to_list()[:5]}"
        )
    alive = frame.filter(pl.col("stems_total") > 0)
    for col in ("stems_total", "agb", "vegc", "height_p50", "soilc"):
        qs = "/".join(f"{alive[col].quantile(q):,.3g}" for q in (0.05, 0.5, 0.95))
        print(f"  {col:14s} p5/p50/p95 over the {alive.height} tree-bearing rows  {qs}")
    print(f"  table         {dest}")
    print(f"  corpus_sha256 {summary['corpus_sha256']}")


def stage_decode(version: str, nproc: int, limit: int | None) -> int:
    out = meta_dir(version)
    runs = pl.read_csv(out / "runs.csv")
    design = pl.read_csv(out / "design.csv")
    cells = pl.read_csv(out / "cells.csv")
    if limit:
        runs = runs.head(limit)

    jobs = [
        (str(n), int(c), str(p), str(r), str(f))
        for n, c, p, r, f in zip(
            runs["name"].to_list(),
            runs["cell"].to_list(),
            runs["point"].to_list(),
            runs["run_dir"].to_list(),
            runs["forcing"].to_list(),
            strict=True,
        )
    ]
    print(f"decoding {len(jobs)} runs of pilot corpus {version} on {nproc} processes", flush=True)

    t0 = time.time()
    done, failed = _decode_all(jobs, nproc)
    if failed:
        print(f"⚠ {len(failed)} runs FAILED to decode:", file=sys.stderr)
        for f in failed[:5]:
            print(f"  {f['name']}:\n{f['error']}", file=sys.stderr)
    if not done:
        print("no run decoded; nothing to write", file=sys.stderr)
        return 1

    frame = _corpus_frame(done, design, cells)
    bad_year = frame.filter(pl.col("restart_year") != STATE_YEAR).height
    if bad_year:
        raise AssertionError(
            f"{bad_year} restarts are not labelled year {STATE_YEAR}; the window a row's climate "
            "summary covers would not be the window its state came from"
        )

    # A smoke run writes its own filenames. `is_smoke` in the JSON is not enough on its own: the
    # table is the artefact a pre-registration cites by hash, and a 30-row file sitting at the name
    # the corpus lives under is one `--limit` away from being cited as the corpus.
    stem = "corpus_smoke" if limit else "corpus"
    dest = out / f"{stem}.parquet"
    frame.write_parquet(dest)
    treeless, control, ctrl_treeless = _decode_parts(frame)
    truth_treed = ctrl_treeless.filter(pl.col("truth_stems_total") > 0).height

    summary: dict[str, Any] = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_pilot.py --stage decode",
        "corpus_version": version,
        "plan_sha256": json.loads((out / "provenance.json").read_text())["plan_sha256"],
        "git_commit": _git_commit(),
        "is_smoke": limit is not None,
        "limit": limit,
        "rows": frame.height,
        "cols": frame.width,
        "runs_promised": runs.height,
        "runs_failed": len(failed),
        "failures": failed,
        "seconds": round(time.time() - t0, 1),
        "nfeature": len(climate_mod.CLIMATE_FEATURES),
        "ntarget": len(state_mod.STATE_COLUMNS) - 1,
        "state_year": STATE_YEAR,
        "state_year_note": (
            "the label LPJmL-FIT writes on a spin-up restart, not a date: the state is the end of "
            f"{NSPINUP} years CYCLING the {perturb_window()[0]}-{perturb_window()[1]} forcing"
        ),
        "treeless_rows": treeless.height,
        "treeless_control_rows": ctrl_treeless.height,
        "control_rows": control.height,
        "treeless_control_cells_treed_in_ground_truth": truth_treed,
        "corpus_sha256": sha256_of(dest),
        "co2": "untouched, not a feature (MEMORY.md:co2-closed)",
    }
    report = out / ("decode_smoke.json" if limit else "decode.json")
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    _report_decode(frame, summary, dest)
    if failed:
        print("verdict: INCOMPLETE -- fix the failures before any score cites this table")
        return 1
    print("verdict: DECODED -- this table is what rung 1 is scored on")
    return 0


def perturb_window() -> tuple[int, int]:
    return tuple(_load("corpus_perturb_clm").BASE_WINDOW)  # type: ignore[return-value]


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stage", choices=("plan", "build", "verify", "harvest", "decode"), required=True
    )
    ap.add_argument("--version", default="v1", help="corpus version; a new design is a new version")
    ap.add_argument("--ncell", type=int, default=NCELL)
    ap.add_argument("--npoint", type=int, default=NPOINT)
    ap.add_argument("--shard-size", type=int, default=SHARD_SIZE, help="runs per SLURM job")
    ap.add_argument("--shard", type=int, default=0, help="build stage: which slice of cells")
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")),
        help="build and decode stages: worker processes; defaults to the job's own cpus-per-task",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="decode stage: first N runs only -- a smoke test, never a corpus",
    )
    args = ap.parse_args()

    if args.stage == "plan":
        return stage_plan(args.version, args.ncell, args.npoint, args.shard_size)
    if args.stage == "build":
        return stage_build(args.version, args.workers, args.shard, args.nshard, args.npoint)
    if args.stage == "verify":
        return stage_verify(args.version)
    if args.stage == "decode":
        return stage_decode(args.version, args.workers, args.limit)
    return stage_harvest(args.version)


if __name__ == "__main__":
    raise SystemExit(main())
