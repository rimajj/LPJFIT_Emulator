#!/usr/bin/env python
"""D: the acceptance truth -- 1000-year single-cell spin-ups of EVERY cell under three climates.

⚠ PARKED -- DO NOT LAUNCH THE FULL CAMPAIGN (owner, 2026-09-24). The owner ruled that no new
all-cell reference runs are needed: the stored spin-up (only its years before the onset of rising
CO2), the stored ssp126 and the stored ssp370 runs are the reference, and the SSP runs are short
transients (2020-2100), so no equilibrium is claimed for them. This builder is kept because it is
tested end to end and its smoke test (`truth-smoke1`, 24 runs) is the proof that a single-cell
rerun with the pilot's protocol reproduces a pilot control restart byte for byte. `WHY IT EXISTS`
below is the ORIGINAL rationale, superseded by that ruling -- read it as history, not a live plan.

    # 1. the plan: flag every cell, fix the runs, write the manifests, project the cost. Cheap.
    scripts/sbatch_py.sh D-tru-v1-plan scripts/corpus_truth.py --stage plan --version v1

    # 2. the forcing and the configs (forcing is seed-independent; configs are one per seed).
    NCPUS=32 TIME=04:00:00 scripts/sbatch_py.sh D-tru-v1-build scripts/corpus_truth.py \\
        --stage build --version v1 --workers 32

    # 3. every promised file exists, and the historical forcing IS the pilot's, before any burn.
    NCPUS=8 scripts/sbatch_py.sh D-tru-v1-verify scripts/corpus_truth.py --stage verify \\
        --version v1 --workers 8

    # 4. the spin-ups: one PACKED task farm per manifest. `manifests.json` carries each one's
    #    exact command, its member count, NTASKS, TIME and estimated core-hours.
    LPJ_DEFINES="" PARTITION=standard NTASKS=<n> TIME=<t> scripts/sbatch_cmodel.sh \\
        --manifest <runs>/truth-v1/manifests/s1/manifest_historical_00.tsv D-tru-v1-s1-hist-00

    # 5. + 6. per seed: judge by the model's own completion line, then decode.
    scripts/sbatch_py.sh D-tru-v1-s1-harvest scripts/corpus_truth.py --stage harvest \\
        --version v1 --seed 1
    NCPUS=32 scripts/sbatch_py.sh D-tru-v1-s1-decode scripts/corpus_truth.py --stage decode \\
        --version v1 --seed 1 --workers 32

WHY IT EXISTS. The owner's acceptance criterion is proof on ALL tree-bearing cells, under BOTH
scenarios, and on the response between them -- counts and trait distributions and trait medians,
inside `max(10 %, the model's own two-run spread)`, conjunctively per cell. Nothing on disk is that
truth for the equilibrium product. The stored spin-up is not at constant CO2 (its last 300 years
carry the historical ramp, `20260915-D-the-spinup-did-converge-...`), and the stored scenario runs
are TRANSIENTS from the 2019 state at 409.63 ppm, i.e. not the settled forest under the 2090s
climate at all. So the truth is a new set of spin-ups, and there is exactly one design that makes it
comparable to the training corpus: THE PILOT'S PROTOCOL, UNCHANGED.

  * Same config builder, patching the ground truth's own saved config (`corpus_spinup_config.py`).
  * Same 1000 years, 30 cycled forcing years LABELLED 1970-1999 whatever window they came from
    (`vegemu.corpus.scenario` explains why the labels are part of the protocol).
  * Same constant-CO2 mechanism (a file with one value every year), at a level that is a PARAMETER
    of this campaign and recorded in its plan hash -- which level is the owner's open question.
  * Same binary, same single-cell task shape (one CPU per member), same seeds.

⚠ AND THAT EQUIVALENCE IS TESTED, NOT ASSUMED. For every planned cell that is also a pilot cell,
the build stage byte-compares its historical forcing against the pilot's control forcing, and the
harvest stage byte-compares its historical RESTART against the pilot control's restart. A pilot
control is an unperturbed copy of the same 30 years under the same config and seed, so any
difference means the truth and the corpus are not the same simulation and nothing may be scored
across them until it is explained.

⚠ THE THREE CELL SETS ARE NOT INTERCHANGEABLE, and the plan table carries all three as flags:
  * `any_stem_1999`   stems_total > 0 in the stored end-of-spin-up restart (uncensored) -- 56,986.
  * `tree_ge5m_1999`  at least one stem in the >= 5 m height bins of that same restart -- 52,198.
  * `in_acceptance_set` cells holding a LIVING TREE individual in the predecessor's per-tree table,
    which drops every stem at or below 5 m and covers the 2000-2019 transient -- exactly the owner's
    54,020 (the table's bare distinct-cell count is 63,119: it lists grasses too).
The plan PLANS all 67,420 land cells by default (`--population all`): a treeless cell today can
become a forested one under warming, and the acceptance population under climate change is not
knowable before the truth exists.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
import traceback
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl
import pyarrow.parquet as pq

from vegemu.binfmt.clm import read_grid
from vegemu.binfmt.restart import RestartReader
from vegemu.corpus import climate as climate_mod
from vegemu.corpus import scenario
from vegemu.corpus import state as state_mod
from vegemu.paths import path, paths, scratch
from vegemu.score import spatial_blocks

REPO = Path(__file__).resolve().parent.parent

LEGS: tuple[str, ...] = ("historical", "ssp126", "ssp370")
SEEDS: tuple[int, ...] = (1, 2)
NSPINUP = 1000
# The protocol's model years: `firstyear 2000 - nspinup 1000` to `lastyear 1999` (iterate.c:85).
FIRST_MODEL_YEAR = 2000 - NSPINUP
STATE_YEAR = 1999
# The pilot corpus this truth must be the same simulation as. Its control point at a shared cell is
# the byte-identity reference, and its member logs are the cost model's calibration data.
REFERENCE = "pilot-v2-constco2"
POPULATIONS: tuple[str, ...] = ("all", "any_stem", "tree_ge5m", "acceptance")
# Members per manifest. A packed farm runs NTASKS of them at a time, so the manifest length is
# bounded by ledger legibility (one row per manifest) and requeue cost, not by CPU count.
SHARD_SIZE = 8000
# Forcing cells read per worker task: 500 x 30 years x 365 days x 4 B = 22 MB per variable.
CHUNK = 500
# The SMALLEST record a 25-patch restart can be (vegetation-free), and so the size below which a
# run grew nothing. Same proxy and same number as `corpus_pilot.TREELESS_RESTART_BYTES`.
TREELESS_RESTART_BYTES = 380_000
# Measured on the reference campaign, 6,000 members, all 24 shards: the members' own "Total wall
# clock time" lines sum to 364.34 h, sacct's per-step Elapsed to 364.67 h, and TotalCPU to 361.25 h.
# A packed farm is charged for the time each member HOLDS its CPU, which is the step's Elapsed, so
# the projection multiplies the model's own clock by this. Stated so it can be re-measured.
ELAPSED_PER_LOG_SECOND = 1.001
# Packed-farm sizing: aim for about this wall time per job, then add the longest member as tail.
TARGET_WALL_H = 2.0
STANDARD_MAX_CPUS = 2048


def _load(name: str) -> ModuleType:
    """Import a sibling script by path. Same registration rule as `corpus_pilot._load` -- read its
    docstring before removing the `sys.modules` line: a path-loaded module that defines a dataclass
    fails inside `dataclasses.py` without it."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------
# naming. Plain `Path`s below the version root: `scratch()` creates what it names, and the plan
# must not create 400,000 directories.
# ------------------------------------------------------------------------------------------------


def _vdir(version: str) -> str:
    return f"truth-{version}"


def _root() -> Path:
    return Path(str(paths()["scratch"]["root"]))


def meta_dir(version: str) -> Path:
    return scratch("corpus", _vdir(version))


def manifest_dir(version: str, seed: int) -> Path:
    """Manifests live with the runs: `sbatch_cmodel.sh` writes its task-farm runner beside them."""
    return scratch("runs", _vdir(version), "manifests", f"s{seed}")


def forcing_dir(version: str, cell: int, leg: str) -> Path:
    """SEED-INDEPENDENT, as in the pilot: a seed changes the model's draws, never its input."""
    return _root() / "forcing" / _vdir(version) / f"c{cell}" / leg


def run_dir(version: str, cell: int, leg: str, seed: int) -> Path:
    """Every seed under its own `s<n>`: both seeds are the truth -- the tolerance needs the pair."""
    return _root() / "runs" / _vdir(version) / f"s{seed}" / f"c{cell}" / leg


def run_tag(cell: int, leg: str, seed: int) -> str:
    return f"c{cell}-{leg}-s{seed}"


def config_path(version: str, cell: int, leg: str, seed: int) -> Path:
    """Where `corpus_spinup_config.build_config` writes this run's config."""
    return run_dir(version, cell, leg, seed) / f"lpjml_spinup_{run_tag(cell, leg, seed)}.js"


def co2_path(version: str) -> Path:
    return _root() / "forcing" / _vdir(version) / "co2_constant.txt"


def reference_meta(seed: int) -> Path:
    """The reference corpus's table directory for a seed, by the pilot's own naming rule."""
    name = REFERENCE if seed == 1 else f"{REFERENCE}-s{seed}"
    return _root() / "corpus" / name


# ------------------------------------------------------------------------------------------------
# CO2. A thin wrapper, because the level is an open owner question and the writer is not ours.
# ------------------------------------------------------------------------------------------------


def write_co2(cfgmod: ModuleType, dest: Path, ppm: float) -> Path:
    """Write the campaign's constant-CO2 file through the corpus's own writer.

    ⚠ AT THE PILOT LEVEL THE CALL IS THE PILOT'S OWN, `write_constant_co2(dest)`, so the file is
    byte-for-byte the pilot's (1700-2100, one value) and a historical truth run is the pilot
    control's simulation exactly.

    ⚠ AT ANY OTHER LEVEL THE FILE MUST START BY YEAR 1000, AND THIS IS THE TRAP IT CLOSES. The model
    uses `param.co2_p` = 276.59 for every year BEFORE the CO2 file's first year (getco2.c:47), and
    the spin-up runs model years 1000-1999. A 1700-2100 file at 409.63 ppm would therefore give 700
    years at 276.59 and then 300 at 409.63 -- a CO2 step labelled "constant". The corpus writer is
    being generalised to take `first_year`/`last_year`; until it does, a non-default level refuses
    here rather than writing that step.
    """
    if ppm == float(cfgmod.CO2_PREINDUSTRIAL_PPM):
        return Path(cfgmod.write_constant_co2(dest))
    try:
        return Path(
            cfgmod.write_constant_co2(
                dest, ppm=ppm, first_year=FIRST_MODEL_YEAR, last_year=int(cfgmod.CO2_CONST_LASTYEAR)
            )
        )
    except TypeError as exc:
        raise NotImplementedError(
            f"a constant CO2 of {ppm} ppm needs `write_constant_co2(..., first_year=...)`, which "
            "corpus_spinup_config.py does not have yet. Without it the first 700 spin-up years "
            f"would run at the model's built-in {cfgmod.CO2_PREINDUSTRIAL_PPM} ppm, not {ppm}."
        ) from exc


def check_co2_file(dest: Path, ppm: float) -> dict[str, Any]:
    """Read the CO2 file back: every year one value, and the first year no later than year 1000
    unless the value IS the model's built-in pre-file one (so the clamp and the file agree)."""
    rows = [ln.split() for ln in dest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    years = [int(r[0]) for r in rows]
    values = {float(r[1]) for r in rows}
    if years != list(range(years[0], years[0] + len(years))):
        raise AssertionError(f"{dest}: CO2 years are not consecutive")
    if len(values) != 1 or abs(next(iter(values)) - ppm) > 0.005:
        raise AssertionError(f"{dest}: CO2 values {sorted(values)[:3]} are not the constant {ppm}")
    clamp = float(_load("corpus_spinup_config").CO2_PREINDUSTRIAL_PPM)
    if abs(ppm - clamp) > 0.005 and years[0] > FIRST_MODEL_YEAR:
        raise AssertionError(
            f"{dest}: a {ppm} ppm file starting in {years[0]} leaves model years "
            f"{FIRST_MODEL_YEAR}-{years[0] - 1} at the model's built-in {clamp} ppm (getco2.c:47)"
        )
    return {
        "file": str(dest),
        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "first_year": years[0],
        "last_year": years[-1],
        "ppm": next(iter(values)),
    }


# ------------------------------------------------------------------------------------------------
# pure helpers the plan is built from (tested without any filesystem)
# ------------------------------------------------------------------------------------------------


def contiguous_chunks(cells: Iterable[int], chunk: int) -> list[range]:
    """Sorted cells as contiguous ranges of at most `chunk`: each is one read per forcing year."""
    ordered = sorted({int(c) for c in cells})
    out: list[range] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1 and j + 1 - i < chunk:
            j += 1
        out.append(range(ordered[i], ordered[j] + 1))
        i = j + 1
    return out


def deal_shards(est: Sequence[float], shard_size: int) -> list[list[int]]:
    """Indices into `est`, dealt LONGEST FIRST round-robin into ceil(n / shard_size) shards.

    Two properties a packed farm needs and a cell-order split does not have. Every shard carries
    about the same total cost, so one manifest's NTASKS/TIME suit them all. And each shard is
    ordered longest-first, so the members still running when the queue drains are the SHORT ones:
    a 9-minute forest member started last would hold the whole allocation for its tail.
    """
    n = len(est)
    if n == 0:
        return []
    nshard = max(1, math.ceil(n / shard_size))
    order = sorted(range(n), key=lambda i: (-float(est[i]), i))
    shards: list[list[int]] = [[] for _ in range(nshard)]
    for k, i in enumerate(order):
        shards[k % nshard].append(i)
    return shards


def suggest_resources(
    total_s: float,
    longest_s: float,
    nmember: int,
    *,
    target_wall_h: float = TARGET_WALL_H,
    max_cpus: int = STANDARD_MAX_CPUS,
) -> dict[str, Any]:
    """NTASKS and TIME for one packed manifest, from its members' projected CPU seconds.

    Wall ~ total / NTASKS plus the longest member as the drain tail; TIME adds 50 % headroom on top
    and rounds up to a quarter hour, because an allocation that times out loses the in-flight
    members and a requeue costs more than the headroom does.
    """
    ntasks = max(1, min(nmember, max_cpus, math.ceil(total_s / (target_wall_h * 3600.0))))
    wall_s = total_s / ntasks + longest_s
    limit_min = max(15, math.ceil(wall_s * 1.5 / 60.0 / 15.0) * 15)
    return {
        "ntasks": ntasks,
        "time": f"{limit_min // 60:02d}:{limit_min % 60:02d}:00",
        "est_wall_h": round(wall_s / 3600.0, 3),
        "est_core_hours": round(total_s / 3600.0, 2),
        "alloc_core_hours_at_est_wall": round(ntasks * wall_s / 3600.0, 2),
    }


def fit_cost(
    restart_bytes: npt.NDArray[np.float64], seconds: npt.NDArray[np.float64], nbin: int = 20
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """A monotone lookup restart-bytes -> member seconds: per-quantile-bin medians, interpolated.

    Binned medians rather than a line, because the relation is not linear at the treeless end: a
    line fitted over the forests predicts a NEGATIVE time for an empty cell, which is exactly the
    cell a whole-grid campaign has most of in the deserts and the ice.
    """
    order = np.argsort(restart_bytes)
    xs, ys = restart_bytes[order], seconds[order]
    edges = np.linspace(0, xs.size, nbin + 1).astype(int)
    bins = [(int(a), int(b)) for a, b in pairwise(edges) if b > a]
    bx = np.array([np.median(xs[a:b]) for a, b in bins])
    by = np.array([np.median(ys[a:b]) for a, b in bins])
    return bx, np.maximum.accumulate(by)


def predict_cost(
    model: tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]], restart_bytes: npt.NDArray[Any]
) -> npt.NDArray[np.float64]:
    bx, by = model
    return np.interp(np.asarray(restart_bytes, dtype=np.float64), bx, by)


# ------------------------------------------------------------------------------------------------
# stage: plan
# ------------------------------------------------------------------------------------------------


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


def _identity(p: Path) -> dict[str, Any]:
    st = p.stat()
    return {
        "path": str(p),
        "bytes": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
    }


# The tree PFTs are types 0-6 (`pft_lpjmlfit.js`: 7 trees, then 3 grasses). The per-tree table's
# rows are individuals of EITHER kind, so "a cell with a tree" is a filter on `Type`, not a count.
NTREE_TYPE = 7
# The variants of "a cell in the per-tree table", every one computed and recorded; the acceptance
# flag is the one named here, chosen because it is the one that reproduces the owner's 54,020.
# Measured 2026-09-23 (job 2281333): any_row 63,119, tree 54,144, tree_alive 54,020 -- exactly.
PERTREE_VARIANTS: tuple[str, ...] = ("any_row", "tree", "tree_alive")
ACCEPTANCE_VARIANT = "tree_alive"


def acceptance_cells(pertree: Path, cache_dir: Path) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Which cells the predecessor's per-tree table holds, under each reading of "holds a tree".

    ⚠ THE BARE DISTINCT-CELL COUNT IS NOT THE OWNER'S 54,020 -- it is 63,119, because the table
    carries GRASS individuals too (types 7-9), so a grass-only cell appears in it; restricting to
    tree types gives 54,144, and to LIVING tree individuals exactly 54,020. The variants are all
    computed and all recorded, so the choice of `ACCEPTANCE_VARIANT` is visible, not implicit.

    Streamed one row group at a time over three columns -- the table is 246 M rows -- and cached
    against the file's identity, because it never changes and the plan may be re-run.
    """
    ident = _identity(pertree)
    cache = cache_dir / "pertree_cells.parquet"
    meta = cache_dir / "pertree_cells.json"
    if cache.is_file() and meta.is_file():
        info = json.loads(meta.read_text())
        if info["source"] == ident:
            return pl.read_parquet(cache), dict(info)
    pf = pq.ParquetFile(str(pertree))
    seen: dict[str, set[int]] = {v: set() for v in PERTREE_VARIANTS}
    types: dict[int, int] = {}
    for rg in range(pf.metadata.num_row_groups):
        t = pf.read_row_group(rg, columns=["Cell", "Type", "isdead"])
        cell = t.column("Cell").to_numpy()
        typ = t.column("Type").to_numpy()
        dead = t.column("isdead").to_numpy()
        tree = typ < NTREE_TYPE
        seen["any_row"].update(np.unique(cell).tolist())
        seen["tree"].update(np.unique(cell[tree]).tolist())
        seen["tree_alive"].update(np.unique(cell[tree & (dead == 0)]).tolist())
        for k, n in zip(*np.unique(typ, return_counts=True), strict=True):
            types[int(k)] = types.get(int(k), 0) + int(n)
    allc = np.array(sorted(seen["any_row"]), dtype=np.int64)
    frame = pl.DataFrame(
        {"cell": allc, **{f"in_{v}": np.isin(allc, sorted(seen[v])) for v in PERTREE_VARIANTS}}
    )
    info = {
        "source": ident,
        "rows": pf.metadata.num_rows,
        "ncell": {v: len(seen[v]) for v in PERTREE_VARIANTS},
        "rows_by_type": {str(k): v for k, v in sorted(types.items())},
        "definition": (
            "cells present in the predecessor's per-tree table (historical seed 1, the 2000-2019 "
            "transient, stems at or below 5 m dropped by its writer): any_row = any individual, "
            f"tree = an individual of Type < {NTREE_TYPE}, tree_alive = such an individual with "
            "isdead == 0"
        ),
    }
    frame.write_parquet(cache)
    meta.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n", "utf-8")
    return frame, info


def _proxy_restart(leg: str) -> Path:
    """The stored restart whose per-cell record size stands in for a leg's cost.

    ⚠ A PROXY, AND AN UPPER-LEANING ONE. Historical is the end of the stored spin-up, whose last 300
    years carried the CO2 ramp (+24 % carbon over constant CO2); the scenario legs are the stored
    2100 transients at 409.63 ppm. Both hold more vegetation than a constant-CO2 spin-up grows, and
    member time rises with vegetation.
    """
    if leg == "historical":
        return path("ground_truth.restart_spinup_end")
    return path(f"ground_truth.{leg}_seed1") / "restart" / "restart_2100.lpj"


def _reference_members() -> tuple[
    npt.NDArray[np.float64], npt.NDArray[np.float64], dict[str, Any], dict[int, float]
]:
    """(restart bytes, log seconds) of every reference-corpus member: the cost model's data. Also
    each CONTROL member's seconds by cell, which is what the stored-restart proxy is checked on."""
    runs = pl.read_csv(reference_meta(1) / "runs.csv")
    pat = re.compile(r"Total wall clock time:\s*(\d+) sec")
    xs: list[float] = []
    ys: list[float] = []
    control: dict[int, float] = {}
    missing = 0
    for name, rdir, cell, point in zip(
        runs["name"].to_list(),
        runs["run_dir"].to_list(),
        runs["cell"].to_list(),
        runs["point"].to_list(),
        strict=True,
    ):
        log = Path(rdir) / f"lpjml.{name}.log"
        restart = Path(rdir) / "restart" / f"restart_{name}.lpj"
        if not log.is_file() or not restart.is_file():
            missing += 1
            continue
        with log.open("rb") as fh:
            fh.seek(max(0, log.stat().st_size - 512))
            m = pat.search(fh.read().decode(errors="replace"))
        if m is None:
            missing += 1
            continue
        xs.append(float(restart.stat().st_size))
        ys.append(float(m.group(1)))
        if point == "control":
            control[int(cell)] = ys[-1]
    info = {
        "reference": REFERENCE,
        "members": len(xs),
        "missing": missing,
        "log_hours_total": round(sum(ys) / 3600.0, 2),
        "elapsed_per_log_second": ELAPSED_PER_LOG_SECOND,
    }
    return np.asarray(xs), np.asarray(ys), info, control


def _cell_table(cache_dir: Path) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Every land cell with its flags, coordinates, cost proxies and projected member seconds."""
    grid = read_grid(path("inputs.coord"))
    ncell = grid.shape[0]
    cells = np.arange(ncell, dtype=np.int64)
    v0 = scratch("corpus", "v0") / "state_historical_seed1.parquet"
    st = pl.read_parquet(
        v0,
        columns=[
            "cell",
            "skip",
            "stems_total",
            "hbin_5_10",
            "hbin_10_20",
            "hbin_20_30",
            "hbin_30p",
        ],
    ).sort("cell")
    if st.height != ncell or not bool((st["cell"].to_numpy() == cells).all()):
        raise AssertionError(f"{v0} does not hold exactly cells 0..{ncell - 1} in order")
    tall = (st["hbin_5_10"] + st["hbin_10_20"] + st["hbin_20_30"] + st["hbin_30p"]).to_numpy() > 0
    any_stem = (st["stems_total"].to_numpy() > 0) & (st["skip"].to_numpy() == 0)

    pertree, acc_info = acceptance_cells(path("predecessor_data.ind_historical_seed1"), cache_dir)
    pcells = pertree["cell"].to_numpy()
    if pcells.size and (pcells.min() < 0 or pcells.max() >= ncell):
        raise AssertionError(f"per-tree cells span {pcells.min()}..{pcells.max()}, grid is {ncell}")
    variant: dict[str, npt.NDArray[np.bool_]] = {}
    for v in PERTREE_VARIANTS:
        flag = np.zeros(ncell, dtype=bool)
        flag[pcells[pertree[f"in_{v}"].to_numpy()]] = True
        variant[v] = flag
    in_acc = variant[ACCEPTANCE_VARIANT]

    pilot = pl.read_csv(reference_meta(1) / "cells.csv")["cell"].to_numpy().astype(np.int64)
    in_pilot = np.zeros(ncell, dtype=bool)
    in_pilot[pilot] = True

    xs, ys, cost_info, control = _reference_members()
    model = fit_cost(xs, ys)
    pred_ref = predict_cost(model, xs)
    ss_res = float(((ys - pred_ref) ** 2).sum())
    ss_tot = float(((ys - ys.mean()) ** 2).sum())
    cost_info["r2_on_reference"] = round(1.0 - ss_res / ss_tot, 3) if ss_tot > 0 else None
    cost_info["model"] = "per-quantile-bin median log seconds vs restart bytes, interpolated"

    cols: dict[str, Any] = {
        "cell": cells.astype(np.int32),
        "lon": grid[:, 0],
        "lat": grid[:, 1],
        "tile": spatial_blocks(grid[:, 0], grid[:, 1], 15.0),
        "any_stem_1999": any_stem,
        "tree_ge5m_1999": tall,
        "in_acceptance_set": in_acc,
        **{f"pertree_{v}": variant[v] for v in PERTREE_VARIANTS},
        "in_pilot": in_pilot,
        # The stored ground truth's own stem count, carried as the corpus does, as a DIAGNOSTIC.
        "stems_total_1999": st["stems_total"].to_numpy(),
    }
    proxies: dict[str, Any] = {}
    for leg in LEGS:
        rp = _proxy_restart(leg)
        sizes = RestartReader(rp).cell_sizes()
        if sizes.size != ncell:
            raise AssertionError(f"{rp} holds {sizes.size} cells, grid is {ncell}")
        cols[f"proxy_bytes_{leg}"] = sizes
        cols[f"est_core_s_{leg}"] = predict_cost(model, sizes) * ELAPSED_PER_LOG_SECOND
        proxies[leg] = _identity(rp)
    cost_info["proxies"] = proxies
    # ⚠ THE PROXY CHECKED WHERE IT CAN BE: at the pilot cells, the historical projection (from the
    # STORED restart's record size) against what the pilot's own control member actually took --
    # the same cell, the same 30 years, the same protocol, at constant CO2. Its ratio is the bias
    # the proxy carries; it is reported, not silently corrected.
    ctl_cells = np.array(sorted(control), dtype=np.int64)
    if ctl_cells.size:
        pred = cols["est_core_s_historical"][ctl_cells] / ELAPSED_PER_LOG_SECOND
        actual = np.array([control[int(c)] for c in ctl_cells])
        ratio = pred / np.maximum(actual, 1.0)
        cost_info["proxy_check_pilot_controls"] = {
            "cells": int(ctl_cells.size),
            "predicted_over_actual_median": round(float(np.median(ratio)), 3),
            "predicted_over_actual_sum": round(float(pred.sum() / actual.sum()), 3),
            "p10_p90": [round(float(np.percentile(ratio, q)), 3) for q in (10, 90)],
        }
    flags = {
        "ncell": ncell,
        "any_stem_1999": int(any_stem.sum()),
        "tree_ge5m_1999": int(tall.sum()),
        "in_acceptance_set": int(in_acc.sum()),
        "acceptance_variant": ACCEPTANCE_VARIANT,
        "pertree_variants": {v: int(variant[v].sum()) for v in PERTREE_VARIANTS},
        "in_pilot": int(in_pilot.sum()),
        "acceptance_not_any_stem": int((in_acc & ~any_stem).sum()),
        "acceptance_not_tree_ge5m": int((in_acc & ~tall).sum()),
        "sources": {
            "v0_state": _identity(v0),
            "acceptance": acc_info,
            "grid": _identity(path("inputs.coord")),
        },
        "tree_ge5m_note": (
            "hbin_5_10 is [5, 10) m, so a stem of exactly 5.0 m counts here and is dropped by the "
            "per-tree writer; and this is the 1999 end-of-spin-up state, not the 2000-2019 years "
            "the per-tree table covers. So this flag is NOT the acceptance set (in_acceptance_set)."
        ),
    }
    return pl.DataFrame(cols), {"flags": flags, "cost": cost_info}


def _population_mask(table: pl.DataFrame, population: str) -> npt.NDArray[np.bool_]:
    if population == "all":
        return np.ones(table.height, dtype=bool)
    column = {
        "any_stem": "any_stem_1999",
        "tree_ge5m": "tree_ge5m_1999",
        "acceptance": "in_acceptance_set",
    }[population]
    return np.asarray(table[column].to_numpy(), dtype=bool)


def stage_plan(
    version: str,
    *,
    legs: Sequence[str],
    seeds: Sequence[int],
    co2_ppm: float,
    population: str,
    cells: Sequence[int] | None,
    shard_size: int,
    harvest_days: int,
) -> int:
    out = meta_dir(version)
    for leg in legs:
        if leg not in scenario.TRUTH_WINDOWS:
            raise ValueError(f"unknown leg {leg!r}; known: {sorted(scenario.TRUTH_WINDOWS)}")
    table, info = _cell_table(scratch("corpus", "reference"))
    mask = _population_mask(table, population)
    if cells:
        pick = np.zeros(table.height, dtype=bool)
        pick[np.asarray(sorted(set(cells)), dtype=np.int64)] = True
        mask &= pick
    table = table.with_columns(pl.Series("planned", mask))
    table.write_parquet(out / "cells.parquet")
    table.write_csv(out / "cells.csv")
    planned = table.filter(pl.col("planned"))

    mdir_root = scratch("runs", _vdir(version), "manifests")
    manifests: list[dict[str, Any]] = []
    # Evaluated by the shell AT LAUNCH, not now: the plan is made days before an owner approves the
    # compute, and a deadline stamped at plan time would make every row overdue on arrival.
    harvest_by = f"$(date -u -d '+{harvest_days} days' +%Y-%m-%dT%H:%M:%SZ)"
    for seed in seeds:
        rows = [
            {
                "name": run_tag(int(c), leg, seed),
                "cell": int(c),
                "leg": leg,
                "seed": seed,
                "config": str(config_path(version, int(c), leg, seed)),
                "run_dir": str(run_dir(version, int(c), leg, seed)),
                "forcing": str(forcing_dir(version, int(c), leg)),
                "est_core_s": float(e),
            }
            for leg in legs
            for c, e in zip(
                planned["cell"].to_list(), planned[f"est_core_s_{leg}"].to_list(), strict=True
            )
        ]
        pl.DataFrame(rows).write_csv(out / f"runs_s{seed}.csv")
        mdir = manifest_dir(version, seed)
        for old in sorted(mdir.glob("manifest_*.tsv")):
            old.unlink()
        for leg in legs:
            leg_rows = [r for r in rows if r["leg"] == leg]
            for k, idx in enumerate(deal_shards([r["est_core_s"] for r in leg_rows], shard_size)):
                members = [leg_rows[i] for i in idx]
                mpath = mdir / f"manifest_{leg}_{k:02d}.tsv"
                mpath.write_text(
                    "".join(f"{r['name']}\t{r['config']}\t{r['run_dir']}\n" for r in members),
                    "utf-8",
                )
                est = [r["est_core_s"] for r in members]
                res = suggest_resources(sum(est), max(est), len(members))
                tag = f"D-tru-{version}-s{seed}-{leg}-{k:02d}"
                manifests.append(
                    {
                        "manifest": str(mpath),
                        "seed": seed,
                        "leg": leg,
                        "nmember": len(members),
                        "tag": tag,
                        **res,
                        "command": (
                            f'LPJ_DEFINES="" PARTITION=standard NTASKS={res["ntasks"]} '
                            f"TIME={res['time']} EST_CORE_HOURS={res['est_core_hours']} "
                            f"HARVEST_BY={harvest_by} scripts/sbatch_cmodel.sh --manifest "
                            f"{mpath} {tag}"
                        ),
                    }
                )
    (mdir_root / "manifests.json").write_text(json.dumps(manifests, indent=2) + "\n", "utf-8")

    windows = {leg: list(scenario.TRUTH_WINDOWS[leg]) for leg in legs}
    prov: dict[str, Any] = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_truth.py --stage plan",
        "tier": "truth",
        "truth_version": version,
        "git_commit": _git_commit(),
        "legs": list(legs),
        "seeds": list(seeds),
        "population": population,
        "explicit_cells": sorted(set(int(c) for c in cells)) if cells else None,
        "ncell_planned": planned.height,
        "nrun": planned.height * len(legs) * len(seeds),
        "nspinup": NSPINUP,
        "source_windows": windows,
        "label_window": [scenario.LABEL_FIRST, scenario.LABEL_FIRST + scenario.NYEAR - 1],
        "protocol": (
            f"identical to the {REFERENCE} corpus: its config builder, its 1000-year single-cell "
            "spin-up, 30 cycled forcing years labelled 1970-1999, one CPU per member, its binary"
        ),
        # ⚠ THE CO2 LEVEL IS AN OPEN OWNER QUESTION, so it is a parameter and part of the hash.
        "co2": {
            "mode": "constant",
            "ppm": co2_ppm,
            "file": str(co2_path(version)),
            "is_pilot_level": co2_ppm == float(_load("corpus_spinup_config").CO2_PREINDUSTRIAL_PPM),
            "note": "the emulator never sees CO2 (MEMORY.md:co2-closed); this fixes the TARGET",
        },
        "reference": REFERENCE,
        "flags": info["flags"],
        "cost_model": info["cost"],
        "shard_size": shard_size,
        "manifests": str(mdir_root / "manifests.json"),
        "sources": {
            f"{leg}.{v}": _identity(Path(p))
            for leg in legs
            for v, p in scenario.source_files(leg).items()
        },
        "binary": _identity(path("lpjml.binary")),
        "plan_sha256": "",
    }
    digest = hashlib.sha256((out / "cells.csv").read_bytes())
    for seed in seeds:
        digest.update((out / f"runs_s{seed}.csv").read_bytes())
    digest.update(
        json.dumps(
            {k: prov[k] for k in ("co2", "source_windows", "sources", "legs", "seeds")},
            sort_keys=True,
        ).encode()
    )
    prov["plan_sha256"] = digest.hexdigest()
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", "utf-8")
    _report_plan(prov, info, manifests, mdir_root)
    return 0


def _report_plan(
    prov: dict[str, Any], info: dict[str, Any], manifests: list[dict[str, Any]], mdir_root: Path
) -> None:
    fl = info["flags"]
    print(
        f"truth {prov['truth_version']}: {prov['ncell_planned']} cells x {len(prov['legs'])} legs "
        f"x {len(prov['seeds'])} seeds"
    )
    print(
        f"  = {prov['nrun']} runs, population '{prov['population']}', CO2 constant "
        f"{prov['co2']['ppm']} ppm"
    )
    print(
        f"  land cells {fl['ncell']}: any stem {fl['any_stem_1999']}, tree >=5 m "
        f"{fl['tree_ge5m_1999']}, acceptance set {fl['in_acceptance_set']}, pilot {fl['in_pilot']}"
    )
    print(
        f"  acceptance cells with no stem in 1999 {fl['acceptance_not_any_stem']}, "
        f"with none >=5 m {fl['acceptance_not_tree_ge5m']}"
    )
    print(
        f"  per-tree table cells by reading: {fl['pertree_variants']} "
        f"(acceptance flag = '{fl['acceptance_variant']}')"
    )
    cost = info["cost"]
    print(
        f"  cost model: {cost['members']} reference members, R^2 {cost['r2_on_reference']}, "
        f"x{ELAPSED_PER_LOG_SECOND} log->held core-s"
    )
    if "proxy_check_pilot_controls" in cost:
        print(f"  proxy check on the pilot controls: {cost['proxy_check_pilot_controls']}")
    for seed in prov["seeds"]:
        mine = [m for m in manifests if m["seed"] == seed]
        cpu_h = sum(m["est_core_hours"] for m in mine)
        alloc_h = sum(m["alloc_core_hours_at_est_wall"] for m in mine)
        print(
            f"  seed {seed}: {len(mine)} manifests, est {cpu_h:,.0f} core-h held by members, "
            f"{alloc_h:,.0f} core-h allocated at the projected wall"
        )
    print(f"  plan_sha256 {prov['plan_sha256']}")
    print(f"  manifests   {mdir_root / 'manifests.json'}")


# ------------------------------------------------------------------------------------------------
# stage: build -- forcing (per cell and leg) and configs (per cell, leg and seed)
# ------------------------------------------------------------------------------------------------


def _reference_forcing(cell: int) -> Path:
    return _root() / "forcing" / REFERENCE / f"c{cell}" / "control"


def _build_chunk(
    args: tuple[str, str, int, int, tuple[int, ...], tuple[int, ...], bool],
) -> dict[str, Any]:
    """One contiguous cell block of one leg: read the window once, write every cell's forcing and
    every seed's config. Runs in a worker; returns only small summaries."""
    version, leg, start, stop, wanted, seeds, in_pilot_any = args
    cfgmod = _load("corpus_spinup_config")
    block = scenario.load_block(leg, range(start, stop))
    co2 = co2_path(version)
    wrote = 0
    nbytes = 0
    identity: list[dict[str, Any]] = []
    for cell in wanted:
        fdir = forcing_dir(version, cell, leg)
        rec = scenario.write_cell(block, cell, fdir)
        wrote += 1
        nbytes += sum(int(rec[v]["bytes"]) for v in scenario.VARS)
        if leg == "historical" and in_pilot_any:
            ref = _reference_forcing(cell)
            if (ref / scenario.FORCING_NAME["tas"]).is_file():
                same = {
                    v: (fdir / scenario.FORCING_NAME[v]).read_bytes()
                    == (ref / scenario.FORCING_NAME[v]).read_bytes()
                    for v in scenario.VARS
                }
                identity.append({"cell": cell, "identical": all(same.values()), "per_var": same})
        for seed in seeds:
            rdir = run_dir(version, cell, leg, seed)
            (rdir / "output").mkdir(parents=True, exist_ok=True)
            (rdir / "restart").mkdir(parents=True, exist_ok=True)
            tag = run_tag(cell, leg, seed)
            input_js = cfgmod.build_input_js(fdir, rdir, tag, co2_file=co2)
            cfgmod.build_config(cell, input_js, rdir, tag=tag, seed=seed, nspinup=NSPINUP)
    return {
        "leg": leg,
        "start": start,
        "stop": stop,
        "cells": wrote,
        "bytes": nbytes,
        "identity": identity,
    }


def _build_chunk_guarded(
    args: tuple[str, str, int, int, tuple[int, ...], tuple[int, ...], bool],
) -> dict[str, Any]:
    try:
        return _build_chunk(args)
    # One bad block must not lose the rest; the stage exits non-zero on any, never silently green.
    except Exception:
        return {"leg": args[1], "start": args[2], "error": traceback.format_exc(limit=6)}


def _prov(version: str) -> dict[str, Any]:
    return dict(json.loads((meta_dir(version) / "provenance.json").read_text()))


def stage_build(version: str, workers: int, shard: int, nshard: int) -> int:
    out = meta_dir(version)
    prov = _prov(version)
    cfgmod = _load("corpus_spinup_config")
    co2 = write_co2(cfgmod, co2_path(version), float(prov["co2"]["ppm"]))
    co2_info = check_co2_file(co2, float(prov["co2"]["ppm"]))
    print(
        f"constant CO2 forcing: {co2}  ({co2_info['ppm']} ppm, {co2_info['first_year']}-"
        f"{co2_info['last_year']})"
    )

    table = pl.read_parquet(out / "cells.parquet").filter(pl.col("planned"))
    pilot = set(table.filter(pl.col("in_pilot"))["cell"].to_list())
    seeds = tuple(int(s) for s in prov["seeds"])
    jobs: list[tuple[str, str, int, int, tuple[int, ...], tuple[int, ...], bool]] = []
    for leg in prov["legs"]:
        for r in contiguous_chunks(table["cell"].to_list(), CHUNK):
            wanted = tuple(r)
            jobs.append((version, leg, r.start, r.stop, wanted, seeds, bool(pilot & set(wanted))))
    mine = jobs[shard::nshard] if nshard > 1 else jobs
    print(f"building {len(mine)} of {len(jobs)} blocks ({workers} workers), seeds {list(seeds)}")

    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_build_chunk_guarded, j) for j in mine]
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            (failed if "error" in res else done).append(res)
            if i % 20 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} blocks  ({len(failed)} failed)", flush=True)

    identity = [x for r in done for x in r["identity"]]
    summary = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "shard": shard,
        "nshard": nshard,
        "blocks_built": len(done),
        "blocks_failed": len(failed),
        "cell_legs_written": sum(int(r["cells"]) for r in done),
        "forcing_bytes": sum(int(r["bytes"]) for r in done),
        "co2": co2_info,
        "pilot_forcing_identity": identity,
        "pilot_forcing_identity_all_pass": all(x["identical"] for x in identity),
        "failures": failed,
    }
    (out / f"build_s{shard:02d}of{nshard:02d}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    print(
        f"forcing written: {summary['forcing_bytes'] / 1e9:.3f} GB, "
        f"{summary['cell_legs_written']} cell-legs"
    )
    if not identity:
        print("pilot forcing identity: NOT CHECKED HERE -- no planned pilot cell in this shard")
    else:
        print(
            f"pilot forcing identity: {len(identity)} historical cells byte-compared against "
            f"{REFERENCE} control, all identical = {summary['pilot_forcing_identity_all_pass']}"
        )
    if not summary["pilot_forcing_identity_all_pass"]:
        print("  ⚠ the historical truth forcing is NOT the pilot's -- nothing may be run from it")
        return 1
    if failed:
        print(f"⚠ {len(failed)} blocks FAILED:", file=sys.stderr)
        for f in failed[:5]:
            print(f"  {f['leg']} block at {f['start']}:\n{f['error']}", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------------------------------------
# stage: verify
# ------------------------------------------------------------------------------------------------


def stage_verify(version: str, sample: int) -> int:
    prov = _prov(version)
    ok = _verify_files(version, prov)
    ok &= _verify_co2(version, prov)
    ok &= _verify_decode(version, prov, sample)
    ok &= _verify_pilot_identity(version, prov)
    print(f"verdict: {'READY to submit' if ok else 'NOT READY -- do not submit'}")
    return 0 if ok else 1


def _verify_files(version: str, prov: dict[str, Any]) -> bool:
    """Every config and every forcing file the manifests promise, and ONE forcing file size."""
    out = meta_dir(version)
    ok = True
    for seed in prov["seeds"]:
        runs = pl.read_csv(out / f"runs_s{seed}.csv")
        missing_cfg = [
            n for n, c in zip(runs["name"], runs["config"], strict=True) if not Path(c).is_file()
        ]
        sizes: dict[int, int] = {}
        missing_forcing: list[str] = []
        for name, fdir in zip(runs["name"].to_list(), runs["forcing"].to_list(), strict=True):
            for fname in scenario.FORCING_NAME.values():
                f = Path(fdir) / fname
                if not f.is_file():
                    missing_forcing.append(f"{name}/{fname}")
                else:
                    sizes[f.stat().st_size] = sizes.get(f.stat().st_size, 0) + 1
        print(f"seed {seed}: {runs.height} runs promised")
        print(f"  configs present        {runs.height - len(missing_cfg)}/{runs.height}")
        print(f"  forcing files present  {sum(sizes.values())}/{runs.height * 5}")
        print(f"  distinct forcing sizes {sorted(sizes.items(), reverse=True)[:4]}")
        ok &= not missing_cfg and not missing_forcing and len(sizes) == 1
        for label, items in (("configs", missing_cfg), ("forcing files", missing_forcing)):
            if items:
                print(f"  ⚠ {len(items)} missing {label}, first few: {items[:5]}", file=sys.stderr)
    return ok


def _verify_co2(version: str, prov: dict[str, Any]) -> bool:
    """At the pilot level the CO2 file must BE the pilot's; at any other, start by year 1000."""
    ppm = float(prov["co2"]["ppm"])
    co2 = check_co2_file(co2_path(version), ppm)
    ref_co2 = _root() / "forcing" / REFERENCE / "co2_constant.txt"
    if prov["co2"]["is_pilot_level"]:
        same = ref_co2.is_file() and ref_co2.read_bytes() == co2_path(version).read_bytes()
        print(f"  CO2 file byte-identical to {REFERENCE}'s: {same}")
        return bool(same)
    print(f"  CO2 {co2['ppm']} ppm from {co2['first_year']}: NOT the pilot level, so no identity")
    return bool(co2["first_year"] <= FIRST_MODEL_YEAR)


def _verify_decode(version: str, prov: dict[str, Any], sample: int) -> bool:
    """The independent-path decode check, on a sample: the written file decoded by per-cell seeks
    must equal the SOURCE decoded by per-cell seeks and rounded once to float32."""
    table = pl.read_parquet(meta_dir(version) / "cells.parquet").filter(pl.col("planned"))
    rng = np.random.default_rng(20260923)
    cells = table["cell"].to_numpy()
    pick = rng.choice(cells, size=min(sample, cells.size), replace=False) if cells.size else []
    bad: list[str] = []
    for leg in prov["legs"]:
        src = scenario.source_files(leg)
        window = scenario.TRUTH_WINDOWS[leg]
        for cell in pick:
            for v in scenario.VARS:
                f = forcing_dir(version, int(cell), leg) / scenario.FORCING_NAME[v]
                if not scenario.decoded_matches_source(
                    f, src[v], int(cell), window, scenario.LABEL_FIRST
                ):
                    bad.append(f"{leg}/c{cell}/{v}")
    print(
        f"  decoded == source x scale, independent path: {len(pick)} cells x {len(prov['legs'])} "
        f"legs x 5 vars, {len(bad)} mismatches {bad[:5]}"
    )
    return not bad


def _verify_pilot_identity(version: str, prov: dict[str, Any]) -> bool:
    """The identity that makes this truth the corpus's simulation, for every planned pilot cell."""
    table = pl.read_parquet(meta_dir(version) / "cells.parquet").filter(pl.col("planned"))
    pilot = table.filter(pl.col("in_pilot"))["cell"].to_list()
    ident_bad = []
    for cell in pilot if "historical" in prov["legs"] else []:
        for v in scenario.VARS:
            a = forcing_dir(version, int(cell), "historical") / scenario.FORCING_NAME[v]
            b = _reference_forcing(int(cell)) / scenario.FORCING_NAME[v]
            if a.read_bytes() != b.read_bytes():
                ident_bad.append(f"c{cell}/{v}")
    print(
        f"  historical forcing byte-identical to {REFERENCE} control: {len(pilot)} pilot cells, "
        f"{len(ident_bad)} differ {ident_bad[:5]}"
    )
    return not ident_bad


# ------------------------------------------------------------------------------------------------
# stage: harvest -- the model's own completion line, and the pilot restart identity
# ------------------------------------------------------------------------------------------------


def _reference_restart(cell: int, seed: int) -> Path | None:
    meta = reference_meta(seed)
    name = f"c{cell}-control-s{seed}"
    vdir = meta.name
    p = _root() / "runs" / vdir / f"c{cell}" / "control" / "restart" / f"restart_{name}.lpj"
    return p if p.is_file() else None


def restart_identity(version: str, seed: int, cells: Iterable[int]) -> list[dict[str, Any]]:
    """Our historical restart against the pilot control's, byte for byte, where both exist."""
    out: list[dict[str, Any]] = []
    for cell in cells:
        ref = _reference_restart(int(cell), seed)
        name = run_tag(int(cell), "historical", seed)
        mine = run_dir(version, int(cell), "historical", seed) / "restart" / f"restart_{name}.lpj"
        if ref is None or not mine.is_file():
            out.append({"cell": int(cell), "identical": None, "reason": "missing"})
            continue
        same = mine.read_bytes() == ref.read_bytes()
        out.append(
            {
                "cell": int(cell),
                "identical": same,
                "bytes": mine.stat().st_size,
                "reference": str(ref),
            }
        )
    return out


def stage_harvest(version: str, seed: int) -> int:
    out = meta_dir(version)
    runs = pl.read_csv(out / f"runs_s{seed}.csv")
    # The model's own line starts with the binary's FILE NAME (`sbatch_cmodel.sh` trap 6), and the
    # binary this plan was made for is in its provenance.
    binary = Path(str(_prov(version)["binary"]["path"])).name
    done = re.compile(rf"^{re.escape(binary)} successfully terminated", flags=re.MULTILINE)
    ok, no_line, no_log, no_restart, treeless = 0, [], [], [], []
    sizes: list[int] = []
    for name, rdir in zip(runs["name"].to_list(), runs["run_dir"].to_list(), strict=True):
        log = Path(rdir) / f"lpjml.{name}.log"
        if not log.is_file() or log.stat().st_size == 0:
            no_log.append(name)
            continue
        text = log.read_text(errors="replace")
        if done.search(text):
            ok += 1
        else:
            no_line.append(name)
        restart = Path(rdir) / "restart" / f"restart_{name}.lpj"
        if not restart.is_file() or restart.stat().st_size == 0:
            no_restart.append(name)
            continue
        sizes.append(restart.stat().st_size)
        if sizes[-1] <= TREELESS_RESTART_BYTES:
            treeless.append(name)
    total = runs.height
    print(f"truth {version} seed {seed}: {total} runs")
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
    if sizes:
        print(f"  at or below the treeless floor           {len(treeless)}/{len(sizes)}")

    cells = pl.read_parquet(out / "cells.parquet").filter(pl.col("planned") & pl.col("in_pilot"))
    ident = restart_identity(version, seed, cells["cell"].to_list())
    checked = [x for x in ident if x["identical"] is not None]
    print(
        f"  historical restart byte-identical to {REFERENCE} control (seed {seed}): "
        f"{sum(1 for x in checked if x['identical'])}/{len(checked)} checked, "
        f"{len(ident) - len(checked)} without a reference"
    )
    (out / f"harvest_s{seed}.json").write_text(
        json.dumps(
            {
                "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "ok": ok,
                "total": total,
                "no_log": no_log[:50],
                "no_line": no_line[:50],
                "no_restart": no_restart[:50],
                "treeless": len(treeless),
                "restart_identity": ident,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "utf-8",
    )
    if checked and not all(x["identical"] for x in checked):
        print(
            "  ⚠ a historical truth restart DIFFERS from the pilot control at the same cell. The "
            "truth and the corpus are not the same simulation; explain it before scoring anything."
        )
    complete = ok == total and not no_restart
    print(f"verdict: {'COMPLETE' if complete else 'INCOMPLETE'}")
    return 0 if complete and all(x["identical"] for x in checked) else 1


# ------------------------------------------------------------------------------------------------
# stage: decode -- the same decoder and the same columns as the pilot corpus table
# ------------------------------------------------------------------------------------------------


def _decode_run(args: tuple[str, int, str, str, str, int]) -> dict[str, Any]:
    """One run's restart record and its own forcing window, as one row. Fork-safe: numpy only."""
    name, cell, leg, rdir, fdir, seed = args
    restart = Path(rdir) / "restart" / f"restart_{name}.lpj"
    row: dict[str, Any] = {
        "name": name,
        "cell": cell,
        "point": leg,
        "seed": seed,
        "restart_year": RestartReader(restart).generic.firstyear,
        "restart_bytes": restart.stat().st_size,
    }
    row.update(state_mod.single_cell_state(restart, cell))
    # The window is the LABEL window the files carry; `leg` names where the climate came from.
    window = climate_mod.Window(
        leg, scenario.LABEL_FIRST, scenario.LABEL_FIRST + scenario.NYEAR - 1, STATE_YEAR
    )
    files = {v: str(Path(fdir) / scenario.FORCING_NAME[v]) for v in climate_mod.VARS}
    cl = climate_mod.climate_columns(window, files=files)
    if cl["cell"].size != 1 or int(cl["cell"][0]) != cell:
        raise AssertionError(f"{name}: forcing does not describe exactly cell {cell}")
    row["lon"] = float(cl["lon"][0])
    row["lat"] = float(cl["lat"][0])
    row["leg"] = str(cl["leg"][0])
    row["state_year"] = int(cl["state_year"][0])
    for feat in climate_mod.CLIMATE_FEATURES:
        row[feat] = float(cl[feat][0])
    return row


def _decode_run_guarded(args: tuple[str, int, str, str, str, int]) -> dict[str, Any]:
    try:
        return _decode_run(args)
    except Exception:
        return {"name": args[0], "cell": args[1], "error": traceback.format_exc(limit=6)}


def stage_decode(version: str, seed: int, nproc: int) -> int:
    out = meta_dir(version)
    prov = _prov(version)
    runs = pl.read_csv(out / f"runs_s{seed}.csv")
    cells = pl.read_parquet(out / "cells.parquet")
    jobs = [
        (str(n), int(c), str(g), str(r), str(f), seed)
        for n, c, g, r, f in zip(
            runs["name"], runs["cell"], runs["leg"], runs["run_dir"], runs["forcing"], strict=True
        )
    ]
    print(
        f"decoding {len(jobs)} runs of truth {version} seed {seed} on {nproc} processes", flush=True
    )
    t0 = time.time()
    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=max(1, nproc)) as pool:
        for i, res in enumerate(pool.map(_decode_run_guarded, jobs, chunksize=8), 1):
            (failed if "error" in res else done).append(res)
            if i % 2000 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} runs  ({len(failed)} failed)", flush=True)
    if not done:
        print("no run decoded; nothing to write", file=sys.stderr)
        return 1

    # ⚠ THE PILOT'S OWN FRAME BUILDER, so the column set and order are the corpus's by construction.
    # The perturbation coefficients do not apply to a truth run and are NULL, never 0/1: a neutral
    # coefficient would claim the scenario legs were the historical climate.
    pilot = _load("corpus_pilot")
    design = pl.DataFrame({"point": list(prov["legs"])}).with_columns(
        *(
            pl.lit(None, dtype=pl.Float64).alias(c)
            for c in ("dtemp_k", "fprec", "sprec", "frad", "fiav")
        ),
        pl.lit("truth").alias("kind"),
    )
    cell_info = cells.select(
        pl.col("cell").cast(pl.Int32),
        pl.col("tile"),
        pl.lit(None, dtype=pl.Utf8).alias("stage"),
        pl.col("stems_total_1999").alias("stems_total"),
    )
    frame = pilot._corpus_frame(done, design, cell_info)
    bad_year = frame.filter(pl.col("restart_year") != STATE_YEAR).height
    if bad_year:
        raise AssertionError(f"{bad_year} restarts are not labelled year {STATE_YEAR}")
    dest = out / f"truth_s{seed}.parquet"
    frame.write_parquet(dest)
    state_dest = out / f"state_{_vdir(version)}_s{seed}.parquet"
    frame.select(*state_mod.STATE_COLUMNS, "point").write_parquet(state_dest)

    treeless = frame.filter(pl.col("stems_total") <= 0)
    summary = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_truth.py --stage decode",
        "truth_version": version,
        "plan_sha256": prov["plan_sha256"],
        "git_commit": _git_commit(),
        "seed": seed,
        "rows": frame.height,
        "cols": frame.width,
        "runs_promised": runs.height,
        "runs_failed": len(failed),
        "failures": failed[:20],
        "seconds": round(time.time() - t0, 1),
        "treeless_rows": treeless.height,
        "by_leg": {
            leg: {
                "rows": frame.filter(pl.col("leg") == leg).height,
                "treeless": treeless.filter(pl.col("leg") == leg).height,
                "source_window": list(scenario.TRUTH_WINDOWS[leg]),
            }
            for leg in prov["legs"]
        },
        "state_year_note": (
            "the label a spin-up restart carries, not a date; every leg's forcing is labelled "
            "1970-1999 and `leg` names the window it was cut from"
        ),
        "truth_sha256": _sha256(dest),
        "state_sha256": _sha256(state_dest),
        "co2": prov["co2"],
    }
    (out / f"decode_s{seed}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    print(f"truth table: {frame.height} rows x {frame.width} cols -> {dest}")
    print(f"  state table {state_dest} ({frame.width and len(state_mod.STATE_COLUMNS) + 1} cols)")
    for leg, s in summary["by_leg"].items():
        print(f"  {leg:10s} {s['rows']} rows, {s['treeless']} treeless")
    print(f"  truth_sha256 {summary['truth_sha256']}")
    if failed:
        print(f"⚠ {len(failed)} runs FAILED to decode", file=sys.stderr)
        for f in failed[:5]:
            print(f"  {f['name']}:\n{f['error']}", file=sys.stderr)
        return 1
    return 0


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _cells_arg(text: str) -> list[int]:
    return [int(x) for x in text.replace(",", " ").split()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--stage", choices=("plan", "build", "verify", "harvest", "decode"), required=True
    )
    ap.add_argument(
        "--version", required=True, help="truth version; directories are truth-<version>"
    )
    ap.add_argument("--legs", nargs="+", default=list(LEGS))
    ap.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS), help="plan stage")
    ap.add_argument("--seed", type=int, default=1, help="harvest and decode stages")
    ap.add_argument(
        "--co2-ppm",
        type=float,
        default=None,
        help="plan stage: the constant CO2 level. Default is the pilot's 276.59 ppm. WHICH LEVEL "
        "THE TRUTH TARGETS IS AN OPEN OWNER QUESTION; it is recorded in the plan and its hash.",
    )
    ap.add_argument("--population", choices=POPULATIONS, default="all", help="plan stage")
    ap.add_argument(
        "--cells",
        type=_cells_arg,
        default=None,
        help="plan stage: an explicit cell list (a smoke test), intersected with --population",
    )
    ap.add_argument("--shard-size", type=int, default=SHARD_SIZE, help="members per manifest")
    ap.add_argument(
        "--harvest-days", type=int, default=7, help="plan stage: HARVEST_BY in the commands"
    )
    ap.add_argument("--shard", type=int, default=0, help="build stage: which slice of blocks")
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument("--sample", type=int, default=24, help="verify stage: cells per leg re-decoded")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
    a = ap.parse_args()
    print(
        "⚠ PARKED (owner, 2026-09-24): the full truth campaign is NOT to be launched; the stored "
        "spin-up, ssp126 and ssp370 runs are the reference. See this script's docstring.",
        file=sys.stderr,
    )

    if a.stage == "plan":
        ppm = (
            a.co2_ppm
            if a.co2_ppm is not None
            else float(_load("corpus_spinup_config").CO2_PREINDUSTRIAL_PPM)
        )
        return stage_plan(
            a.version,
            legs=a.legs,
            seeds=a.seeds,
            co2_ppm=ppm,
            population=a.population,
            cells=a.cells,
            shard_size=a.shard_size,
            harvest_days=a.harvest_days,
        )
    if a.stage == "build":
        return stage_build(a.version, a.workers, a.shard, a.nshard)
    if a.stage == "verify":
        return stage_verify(a.version, a.sample)
    if a.stage == "harvest":
        return stage_harvest(a.version, a.seed)
    return stage_decode(a.version, a.seed, a.workers)


if __name__ == "__main__":
    raise SystemExit(main())
