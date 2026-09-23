#!/usr/bin/env python
"""The daily-forcing features of `vegemu.corpus.features_v3`, for the pilot runs and the three legs.

    # every pilot run, from its OWN (perturbed) forcing, plus the hard check against the global file
    NCPUS=16 PARTITION=priority TIME=00:40:00 scripts/sbatch_py.sh T-fea-pilot \\
        scripts/build_features_v3.py --stage pilot --workers 16

    # all 67,420 cells on historical 1970-1999, ssp126 2071-2100 and ssp370 2071-2100
    NCPUS=32 PARTITION=priority TIME=01:30:00 scripts/sbatch_py.sh T-fea-legs \\
        scripts/build_features_v3.py --stage legs --workers 32

Writes, under `scratch.exp/T-features-v3/`:
    features_v3_pilot.parquet        keyed (cell, point), one row per pilot run
    features_v3_<leg>.parquet        keyed cell, one row per grid cell
    features_v3_<what>.json          the basis: files and headers, window, rows, hashes, checks

⚠ THE HARD CHECK. The pilot's control forcing is an unperturbed copy of the global historical
file (its perturbation.json records `neutral_byte_identity: PASS` per variable), so the features of
every control run, computed from its single-cell files, must EQUAL those computed from the global
historical file for that cell. The pilot stage computes both and refuses to write the table unless
they agree; the legs stage repeats the comparison against its own historical table, which reads the
global file by a different path (whole row slabs rather than one cell at a time). A disagreement
means a reader, an index or a unit is wrong, and every downstream number would inherit it.

Workers compute with numpy only and return arrays; the table is built in the parent. The pool is
`spawn`ed, not forked, so no polars thread pool is ever inherited by a child.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.clm import ClmReader
from vegemu.corpus import features_v3 as fv3
from vegemu.corpus.climate import VARS, WINDOWS
from vegemu.paths import paths

Array = npt.NDArray[np.float64]

PILOT_WINDOW = (1970, 1999)  # corpus_perturb_clm.BASE_WINDOW; asserted against every run's header
PERT_NAME = "{var}_pert.clm"  # corpus_perturb_clm.OUT_NAME
LEGS = ("historical", "ssp126", "ssp370")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _commit() -> str:
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return r.stdout.strip()


def _static() -> tuple[npt.NDArray[np.int64], Array]:
    """(soil code, soil depth in m) for every global cell, straight from the model's inputs."""
    cfg = paths()["inputs"]
    codes = np.fromfile(str(cfg["soil"]), dtype=np.uint8).astype(np.int64)
    reader = ClmReader(str(cfg["soildepth"]))
    with reader:
        depth = np.asarray(reader.year(reader.header.firstyear)[:, 0], dtype=np.float64)
    if codes.size != depth.size:
        raise AssertionError(f"soil has {codes.size} cells, soil depth {depth.size}")
    return codes, depth


def _global_files(leg: str) -> dict[str, str]:
    return {v: str(paths()["inputs"][leg][v]) for v in VARS}


# -- workers (numpy only) -----------------------------------------------------------------------


def _pilot_chunk(
    args: tuple[list[str], list[int], list[str], list[int], list[float]],
) -> dict[str, Any]:
    """A batch of pilot runs: each run's own single-cell files, stacked, then one feature call."""
    names, cells, forcing_dirs, codes, depths = args
    first, last = PILOT_WINDOW
    stacks: dict[str, list[Array]] = {v: [] for v in VARS}
    for name, cell, fdir in zip(names, cells, forcing_dirs, strict=True):
        files = {v: str(Path(fdir) / PERT_NAME.format(var=v)) for v in VARS}
        daily, ids = fv3.read_rows(files, first, last, 0, 1)
        if ids.size != 1 or int(ids[0]) != cell:
            raise AssertionError(
                f"{name}: forcing declares cells {ids.tolist()}, the run is {cell}"
            )
        for v in VARS:
            stacks[v].append(daily[v][0])
    daily_all = {v: np.stack(stacks[v], axis=0) for v in VARS}
    cols = fv3.v3_columns(daily_all, np.asarray(codes), np.asarray(depths))
    return {"names": names, "cols": cols}


def _cells_chunk(args: tuple[str, list[int], list[int], list[float]]) -> dict[str, Any]:
    """Arbitrary global cells of one leg, read one cell at a time (the hard check's path)."""
    leg, cells, codes, depths = args
    w = WINDOWS[leg]
    daily = fv3.read_cells(_global_files(leg), w.first, w.last, cells)
    cols = fv3.v3_columns(daily, np.asarray(codes), np.asarray(depths))
    return {"cells": cells, "cols": cols, "daily": daily}


def _rows_chunk(args: tuple[str, int, int, list[int], list[float]]) -> dict[str, Any]:
    """A contiguous row range of one leg's global files, read as whole slabs."""
    leg, row0, row1, codes, depths = args
    w = WINDOWS[leg]
    t0 = time.time()
    daily, ids = fv3.read_rows(_global_files(leg), w.first, w.last, row0, row1)
    cols = fv3.v3_columns(daily, np.asarray(codes), np.asarray(depths))
    return {"cells": ids, "cols": cols, "seconds": time.time() - t0}


# -- comparison ---------------------------------------------------------------------------------


def compare(a: dict[str, Array], b: dict[str, Array]) -> dict[str, Any]:
    """Exact comparison of two feature dicts over the same rows. NaN equals NaN."""
    per: dict[str, dict[str, float | int]] = {}
    worst_abs, worst_rel, n_unequal = 0.0, 0.0, 0
    for k in fv3.V3_FEATURES:
        x, y = np.asarray(a[k]), np.asarray(b[k])
        same = (x == y) | (np.isnan(x) & np.isnan(y))
        bad = int((~same).sum())
        if bad:
            d = np.abs(x - y)[~same]
            scale = np.maximum(np.abs(x), np.abs(y))[~same]
            rel = float(np.nanmax(d / np.where(scale > 0, scale, 1.0)))
            per[k] = {"rows_unequal": bad, "max_abs": float(np.nanmax(d)), "max_rel": rel}
            worst_abs = max(worst_abs, float(np.nanmax(d)))
            worst_rel = max(worst_rel, rel)
            n_unequal += bad
    return {
        "rows": len(next(iter(a.values()))),
        "features": len(fv3.V3_FEATURES),
        "exactly_equal": n_unequal == 0,
        "cells_x_features_unequal": n_unequal,
        "max_abs_diff": worst_abs,
        "max_rel_diff": worst_rel,
        "unequal_features": per,
    }


# -- stages -------------------------------------------------------------------------------------


def _pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))


def stage_pilot(version: str, out: Path, workers: int, chunk: int, limit: int) -> int:
    corpus = Path(str(paths()["scratch"]["corpus"])) / version
    runs = pl.read_csv(corpus / "runs.csv").sort(["cell", "point"])
    if limit:
        runs = runs.head(limit)  # a smoke test; the table name says so
    codes_all, depth_all = _static()
    names = runs["name"].to_list()
    cells = [int(c) for c in runs["cell"].to_list()]
    fdirs = runs["forcing"].to_list()
    print(f"{len(names)} pilot runs, {len(set(cells))} cells", flush=True)

    jobs = [
        (
            names[i : i + chunk],
            cells[i : i + chunk],
            fdirs[i : i + chunk],
            [int(codes_all[c]) for c in cells[i : i + chunk]],
            [float(depth_all[c]) for c in cells[i : i + chunk]],
        )
        for i in range(0, len(names), chunk)
    ]
    t0 = time.time()
    by_name: dict[str, dict[str, float]] = {}
    with _pool(workers) as pool:
        for k, res in enumerate(pool.map(_pilot_chunk, jobs), 1):
            for i, nm in enumerate(res["names"]):
                by_name[nm] = {f: float(res["cols"][f][i]) for f in fv3.V3_FEATURES}
            print(f"  chunk {k}/{len(jobs)} done, {time.time() - t0:.0f} s", flush=True)
    feats = {f: np.array([by_name[nm][f] for nm in names]) for f in fv3.V3_FEATURES}

    # THE HARD CHECK: the control runs against the global historical file, cell by cell.
    ctrl = [i for i, p in enumerate(runs["point"].to_list()) if p == "control"]
    ctrl_cells = [cells[i] for i in ctrl]
    split = [ctrl_cells[i : i + 25] for i in range(0, len(ctrl_cells), 25)]
    glob_cols: dict[str, list[Array]] = {f: [] for f in fv3.V3_FEATURES}
    forcing_unequal = 0
    with _pool(workers) as pool:
        res_all = list(
            pool.map(
                _cells_chunk,
                [
                    (
                        "historical",
                        s,
                        [int(codes_all[c]) for c in s],
                        [float(depth_all[c]) for c in s],
                    )
                    for s in split
                ],
            )
        )
    for s, res in zip(split, res_all, strict=True):
        for f in fv3.V3_FEATURES:
            glob_cols[f].append(res["cols"][f])
        # The forcing itself, too: a feature can only disagree if the bytes do.
        for j, c in enumerate(s):
            run_dir = fdirs[ctrl[ctrl_cells.index(c)]]
            files = {v: str(Path(run_dir) / PERT_NAME.format(var=v)) for v in VARS}
            mine, _ = fv3.read_rows(files, *PILOT_WINDOW, 0, 1)
            for v in VARS:
                forcing_unequal += int(not np.array_equal(mine[v][0], res["daily"][v][j]))
    glob = {f: np.concatenate(glob_cols[f]) for f in fv3.V3_FEATURES}
    mine = {f: feats[f][ctrl] for f in fv3.V3_FEATURES}
    check = compare(mine, glob)
    check["forcing_arrays_unequal"] = forcing_unequal
    check["basis"] = (
        f"{len(ctrl)} control runs of {version}: features from the run's own single-cell forcing "
        "vs from the global historical file, 1970-1999, read one cell at a time"
    )
    print(
        f"HARD CHECK: {len(ctrl)} control cells x {len(fv3.V3_FEATURES)} features, "
        f"exactly equal = {check['exactly_equal']}, max |diff| = {check['max_abs_diff']:.3g}, "
        f"forcing arrays unequal = {forcing_unequal}",
        flush=True,
    )

    out.mkdir(parents=True, exist_ok=True)
    prov: dict[str, Any] = {
        "what": "pilot",
        "version": version,
        "window": list(PILOT_WINDOW),
        "rows": len(names),
        "features": list(fv3.V3_FEATURES),
        "code_commit": _commit(),
        "soil": str(paths()["inputs"]["soil"]),
        "soildepth": str(paths()["inputs"]["soildepth"]),
        "hard_check": check,
        "co2": "never read; not a feature (invariant 8)",
    }
    if not check["exactly_equal"] or forcing_unequal:
        (out / "features_v3_pilot.FAILED.json").write_text(json.dumps(prov, indent=2))
        print("HARD CHECK FAILED -- the table is NOT written", flush=True)
        return 1
    table = pl.DataFrame(
        {
            "cell": np.asarray(cells, dtype=np.int32),
            "point": runs["point"].to_list(),
            **{f: feats[f] for f in fv3.V3_FEATURES},
        }
    )
    stem = "features_v3_pilot" + (f"_smoke{limit}" if limit else "")
    dest = out / f"{stem}.parquet"
    table.write_parquet(dest)
    prov["sha256"] = _sha256(dest)
    (out / f"{stem}.json").write_text(json.dumps(prov, indent=2))
    print(f"wrote {dest} {table.shape} sha256 {prov['sha256']}", flush=True)
    return 0


def stage_legs(legs: Sequence[str], out: Path, workers: int, chunk: int, max_cells: int) -> int:
    codes_all, depth_all = _static()
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for leg in legs:
        w = WINDOWS[leg]
        files = _global_files(leg)
        ncell = ClmReader(files["tas"]).header.ncell
        first_cell = ClmReader(files["tas"]).header.firstcell
        if first_cell != 0 or ncell != codes_all.size:
            raise AssertionError(f"{leg}: files hold {first_cell}+{ncell}, soil {codes_all.size}")
        if max_cells:
            ncell = min(ncell, max_cells)  # a smoke test; the table name says so
        jobs = [
            (
                leg,
                r0,
                min(r0 + chunk, ncell),
                codes_all[r0 : min(r0 + chunk, ncell)].tolist(),
                depth_all[r0 : min(r0 + chunk, ncell)].tolist(),
            )
            for r0 in range(0, ncell, chunk)
        ]
        print(f"=== {w.describe()}: {ncell} cells in {len(jobs)} chunks", flush=True)
        t0 = time.time()
        parts: list[dict[str, Any]] = []
        with _pool(workers) as pool:
            for k, res in enumerate(pool.map(_rows_chunk, jobs), 1):
                parts.append(res)
                if k % 5 == 0 or k == len(jobs):
                    print(
                        f"  {k}/{len(jobs)} chunks, {time.time() - t0:.0f} s wall, "
                        f"last chunk {res['seconds']:.0f} s",
                        flush=True,
                    )
        ids = np.concatenate([p["cells"] for p in parts])
        if not np.array_equal(ids, np.arange(ncell)):
            raise AssertionError(f"{leg}: assembled cells are not 0..{ncell - 1} in order")
        feats = {f: np.concatenate([p["cols"][f] for p in parts]) for f in fv3.V3_FEATURES}
        table = pl.DataFrame({"cell": ids.astype(np.int32), **feats})
        stem = f"features_v3_{leg}" + (f"_smoke{max_cells}" if max_cells else "")
        dest = out / f"{stem}.parquet"
        table.write_parquet(dest)
        prov: dict[str, Any] = {
            "what": leg,
            "window": [w.first, w.last],
            "rows": int(ncell),
            "features": list(fv3.V3_FEATURES),
            "code_commit": _commit(),
            "files": {
                v: {"path": files[v], "header": ClmReader(files[v]).header.describe()} for v in VARS
            },
            "soil": str(paths()["inputs"]["soil"]),
            "soildepth": str(paths()["inputs"]["soildepth"]),
            "co2": "never read; not a feature (invariant 8)",
            "nan_cells_per_feature": {f: int(np.isnan(feats[f]).sum()) for f in fv3.V3_FEATURES},
            "sha256": _sha256(dest),
        }
        pilot = out / "features_v3_pilot.parquet"
        if leg == "historical" and pilot.exists():
            p = pl.read_parquet(pilot).filter(pl.col("point") == "control").sort("cell")
            p = p.filter(pl.col("cell") < ncell)
            c = p["cell"].to_numpy().astype(np.int64)
            check = compare(
                {f: p[f].to_numpy() for f in fv3.V3_FEATURES},
                {f: feats[f][c] for f in fv3.V3_FEATURES},
            )
            check["basis"] = (
                "pilot control rows vs the historical table's rows for the same cells (global file "
                "read in whole row slabs)"
            )
            prov["hard_check_vs_pilot_control"] = check
            print(
                f"HARD CHECK vs pilot control: {len(c)} cells, exactly equal = "
                f"{check['exactly_equal']}, max |diff| = {check['max_abs_diff']:.3g}",
                flush=True,
            )
            rc = rc or (0 if check["exactly_equal"] else 1)
        (out / f"{stem}.json").write_text(json.dumps(prov, indent=2))
        print(f"wrote {dest} {table.shape} sha256 {prov['sha256']}", flush=True)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("pilot", "legs"), required=True)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--legs", nargs="+", default=list(LEGS), choices=LEGS)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=0, help="runs (pilot) or cells (legs) per task")
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0, help="pilot smoke test: first N runs only")
    ap.add_argument("--max-cells", type=int, default=0, help="legs smoke test: first N cells")
    args = ap.parse_args()
    out = Path(args.out) if args.out else Path(str(paths()["scratch"]["exp"])) / "T-features-v3"
    if args.stage == "pilot":
        return stage_pilot(args.version, out, args.workers, args.chunk or 250, args.limit)
    return stage_legs(args.legs, out, args.workers, args.chunk or 1500, args.max_cells)


if __name__ == "__main__":
    raise SystemExit(main())
