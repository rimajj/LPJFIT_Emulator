#!/usr/bin/env python
"""The daily-forcing features of `vegemu.corpus.features_v3`, for the pilot runs and the legs.

    # every pilot run, from its OWN (perturbed) forcing, plus the hard check against the global file
    NCPUS=16 PARTITION=priority TIME=00:40:00 scripts/sbatch_py.sh T-fea-pilot \\
        scripts/build_features_v3.py --stage pilot --workers 16

    # all 67,420 cells on the stored spin-up's recycled window 1901-1930, historical 1970-1999,
    # ssp126 2071-2100 and ssp370 2071-2100
    NCPUS=32 PARTITION=priority TIME=01:30:00 scripts/sbatch_py.sh T-fea-legs \\
        scripts/build_features_v3.py --stage legs --workers 32 --legs spinup historical

THREE FEATURE SETS (`--set`), each written under its own name and directory so no run overwrites
a table something else pinned:
    base  the 120 `V3_FEATURES`                      features_v3_*   scratch.exp/T-features-v3/
    x     + the extension `V3X_FEATURES` (151)       features_v3x_*  scratch.exp/T-features-v3x/
    p     + the productivity columns `V3P_FEATURES`  features_v3p_*  scratch.exp/T-features-v3p/
A run of a larger set re-checks, cell for cell, every column it shares with each smaller set's
existing table, so an extension provably moved nothing it was appended to.

Writes:
    features_v3[x]_pilot.parquet     keyed (cell, point), one row per pilot run
    features_v3[x]_<leg>.parquet     keyed cell, one row per grid cell
    features_v3[x]_<what>.json       the basis: files and headers, window, rows, hashes, checks

THE SPIN-UP LEG is the historical files over 1901-1930: the stored global spin-up draws each of its
years from the first 30 forcing years (`scripts/spinup_target.py`), so this is the climate it saw.

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
from dataclasses import dataclass
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
from vegemu.corpus.climate import VARS, WINDOWS, Window
from vegemu.paths import paths

Array = npt.NDArray[np.float64]

PILOT_WINDOW = (1970, 1999)  # corpus_perturb_clm.BASE_WINDOW; asserted against every run's header
PERT_NAME = "{var}_pert.clm"  # corpus_perturb_clm.OUT_NAME
LEGS = ("spinup", "historical", "ssp126", "ssp370")
# The stored spin-up's recycled window, read from the historical files (as spinup_target.py does).
LEG_WINDOWS: dict[str, Window] = {**WINDOWS, "spinup": Window("historical", 1901, 1930, 1699)}


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
    src = LEG_WINDOWS[leg].leg  # "spinup" reads the historical files
    return {v: str(paths()["inputs"][src][v]) for v in VARS}


# -- workers (numpy only) -----------------------------------------------------------------------


def _pilot_chunk(
    args: tuple[list[str], list[int], list[str], list[int], list[float], bool, bool],
) -> dict[str, Any]:
    """A batch of pilot runs: each run's own single-cell files, stacked, then one feature call."""
    names, cells, forcing_dirs, codes, depths, extras, prod = args
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
    cols = fv3.v3_columns(
        daily_all, np.asarray(codes), np.asarray(depths), extras=extras, productivity=prod
    )
    return {"names": names, "cols": cols}


def _cells_chunk(
    args: tuple[str, list[int], list[int], list[float], bool, bool],
) -> dict[str, Any]:
    """Arbitrary global cells of one leg, read one cell at a time (the hard check's path)."""
    leg, cells, codes, depths, extras, prod = args
    w = LEG_WINDOWS[leg]
    daily = fv3.read_cells(_global_files(leg), w.first, w.last, cells)
    cols = fv3.v3_columns(
        daily, np.asarray(codes), np.asarray(depths), extras=extras, productivity=prod
    )
    return {"cells": cells, "cols": cols, "daily": daily}


def _rows_chunk(args: tuple[str, int, int, list[int], list[float], bool, bool]) -> dict[str, Any]:
    """A contiguous row range of one leg's global files, read as whole slabs."""
    leg, row0, row1, codes, depths, extras, prod = args
    w = LEG_WINDOWS[leg]
    t0 = time.time()
    daily, ids = fv3.read_rows(_global_files(leg), w.first, w.last, row0, row1)
    cols = fv3.v3_columns(
        daily, np.asarray(codes), np.asarray(depths), extras=extras, productivity=prod
    )
    return {"cells": ids, "cols": cols, "seconds": time.time() - t0}


# -- comparison ---------------------------------------------------------------------------------


def compare(
    a: dict[str, Array], b: dict[str, Array], names: Sequence[str] = fv3.V3_FEATURES
) -> dict[str, Any]:
    """Exact comparison of two feature dicts over the same rows. NaN equals NaN."""
    per: dict[str, dict[str, float | int]] = {}
    worst_abs, worst_rel, n_unequal = 0.0, 0.0, 0
    for k in names:
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
        "features": len(names),
        "exactly_equal": n_unequal == 0,
        "cells_x_features_unequal": n_unequal,
        "max_abs_diff": worst_abs,
        "max_rel_diff": worst_rel,
        "unequal_features": per,
    }


# -- stages -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureSet:
    """Which columns a run writes, under which file prefix, and what it regresses against."""

    names: tuple[str, ...]
    extras: bool
    productivity: bool
    prefix: str  # features_v3 | features_v3x | features_v3p
    regress: tuple[tuple[str, Path], ...]  # (prefix, directory) of the smaller sets' tables


def _pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))


def regress(table: pl.DataFrame, fs: FeatureSet, what: str, keys: Sequence[str]) -> dict[str, Any]:
    """Every column shared with each smaller set's table of the same rows, exactly.

    `exactly_equal` is False if any compared table disagrees, True otherwise (also when there was
    nothing to compare, which the per-table entries then say).
    """
    out: dict[str, Any] = {"exactly_equal": True, "tables": {}}
    mine = table.sort(list(keys))
    for prefix, root in fs.regress:
        ref_path = root / f"{prefix}_{what}.parquet"
        if not ref_path.exists():
            out["tables"][prefix] = {"skipped": f"{ref_path} does not exist"}
            continue
        ref = pl.read_parquet(ref_path).sort(list(keys))
        if ref.select(keys).to_dicts() != mine.select(keys).to_dicts():
            out["tables"][prefix] = {"exactly_equal": False, "error": "different rows"}
            out["exactly_equal"] = False
            continue
        names = [f for f in fs.names if f in ref.columns]
        check = compare(
            {f: mine[f].to_numpy() for f in names}, {f: ref[f].to_numpy() for f in names}, names
        )
        check["basis"] = f"{len(names)} shared columns vs {ref_path} (sha256 {_sha256(ref_path)})"
        out["tables"][prefix] = check
        out["exactly_equal"] = out["exactly_equal"] and check["exactly_equal"]
        print(
            f"REGRESSION vs {prefix}_{what}: {mine.height} rows x {len(names)} shared features, "
            f"exactly equal = {check['exactly_equal']}",
            flush=True,
        )
    return out


def stage_pilot(  # noqa: PLR0917 -- the stage's knobs, passed straight from the command line
    version: str, out: Path, workers: int, chunk: int, limit: int, fs: FeatureSet
) -> int:
    corpus = Path(str(paths()["scratch"]["corpus"])) / version
    runs = pl.read_csv(corpus / "runs.csv").sort(["cell", "point"])
    if limit:
        runs = runs.head(limit)  # a smoke test; the table name says so
    codes_all, depth_all = _static()
    names = runs["name"].to_list()
    cells = [int(c) for c in runs["cell"].to_list()]
    fdirs = runs["forcing"].to_list()
    print(f"{len(names)} pilot runs, {len(set(cells))} cells, {len(fs.names)} features", flush=True)

    jobs = [
        (
            names[i : i + chunk],
            cells[i : i + chunk],
            fdirs[i : i + chunk],
            [int(codes_all[c]) for c in cells[i : i + chunk]],
            [float(depth_all[c]) for c in cells[i : i + chunk]],
            fs.extras,
            fs.productivity,
        )
        for i in range(0, len(names), chunk)
    ]
    t0 = time.time()
    by_name: dict[str, dict[str, float]] = {}
    with _pool(workers) as pool:
        for k, res in enumerate(pool.map(_pilot_chunk, jobs), 1):
            for i, nm in enumerate(res["names"]):
                by_name[nm] = {f: float(res["cols"][f][i]) for f in fs.names}
            print(f"  chunk {k}/{len(jobs)} done, {time.time() - t0:.0f} s", flush=True)
    feats = {f: np.array([by_name[nm][f] for nm in names]) for f in fs.names}

    # THE HARD CHECK: the control runs against the global historical file, cell by cell.
    ctrl = [i for i, p in enumerate(runs["point"].to_list()) if p == "control"]
    ctrl_cells = [cells[i] for i in ctrl]
    split = [ctrl_cells[i : i + 25] for i in range(0, len(ctrl_cells), 25)]
    glob_cols: dict[str, list[Array]] = {f: [] for f in fs.names}
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
                        fs.extras,
                        fs.productivity,
                    )
                    for s in split
                ],
            )
        )
    for s, res in zip(split, res_all, strict=True):
        for f in fs.names:
            glob_cols[f].append(res["cols"][f])
        # The forcing itself, too: a feature can only disagree if the bytes do.
        for j, c in enumerate(s):
            run_dir = fdirs[ctrl[ctrl_cells.index(c)]]
            files = {v: str(Path(run_dir) / PERT_NAME.format(var=v)) for v in VARS}
            mine, _ = fv3.read_rows(files, *PILOT_WINDOW, 0, 1)
            for v in VARS:
                forcing_unequal += int(not np.array_equal(mine[v][0], res["daily"][v][j]))
    glob = {f: np.concatenate(glob_cols[f]) for f in fs.names}
    mine = {f: feats[f][ctrl] for f in fs.names}
    check = compare(mine, glob, fs.names)
    check["forcing_arrays_unequal"] = forcing_unequal
    check["basis"] = (
        f"{len(ctrl)} control runs of {version}: features from the run's own single-cell forcing "
        "vs from the global historical file, 1970-1999, read one cell at a time"
    )
    print(
        f"HARD CHECK: {len(ctrl)} control cells x {len(fs.names)} features, "
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
        "features": list(fs.names),
        "code_commit": _commit(),
        "soil": str(paths()["inputs"]["soil"]),
        "soildepth": str(paths()["inputs"]["soildepth"]),
        "hard_check": check,
        "co2": "never read; not a feature (invariant 8)",
    }
    stem = f"{fs.prefix}_pilot" + (f"_smoke{limit}" if limit else "")
    if not check["exactly_equal"] or forcing_unequal:
        (out / f"{stem}.FAILED.json").write_text(json.dumps(prov, indent=2))
        print("HARD CHECK FAILED -- the table is NOT written", flush=True)
        return 1
    table = pl.DataFrame(
        {
            "cell": np.asarray(cells, dtype=np.int32),
            "point": runs["point"].to_list(),
            **{f: feats[f] for f in fs.names},
        }
    )
    reg = regress(table, fs, "pilot", ["cell", "point"]) if not limit else {"skipped": "smoke"}
    prov["regression_vs_pinned_v3"] = reg
    dest = out / f"{stem}.parquet"
    table.write_parquet(dest)
    prov["sha256"] = _sha256(dest)
    (out / f"{stem}.json").write_text(json.dumps(prov, indent=2))
    print(f"wrote {dest} {table.shape} sha256 {prov['sha256']}", flush=True)
    return 0 if reg.get("exactly_equal", True) else 1


def stage_legs(  # noqa: PLR0917 -- one flat pass per leg
    legs: Sequence[str], out: Path, workers: int, chunk: int, max_cells: int, fs: FeatureSet
) -> int:
    codes_all, depth_all = _static()
    out.mkdir(parents=True, exist_ok=True)
    rc = 0
    for leg in legs:
        w = LEG_WINDOWS[leg]
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
                fs.extras,
                fs.productivity,
            )
            for r0 in range(0, ncell, chunk)
        ]
        print(f"=== {leg}: {w.describe()}: {ncell} cells in {len(jobs)} chunks", flush=True)
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
        feats = {f: np.concatenate([p["cols"][f] for p in parts]) for f in fs.names}
        table = pl.DataFrame({"cell": ids.astype(np.int32), **feats})
        stem = f"{fs.prefix}_{leg}" + (f"_smoke{max_cells}" if max_cells else "")
        dest = out / f"{stem}.parquet"
        table.write_parquet(dest)
        prov: dict[str, Any] = {
            "what": leg,
            "window": [w.first, w.last],
            "forcing_leg": w.leg,
            "rows": int(ncell),
            "features": list(fs.names),
            "code_commit": _commit(),
            "files": {
                v: {"path": files[v], "header": ClmReader(files[v]).header.describe()} for v in VARS
            },
            "soil": str(paths()["inputs"]["soil"]),
            "soildepth": str(paths()["inputs"]["soildepth"]),
            "co2": "never read; not a feature (invariant 8)",
            "nan_cells_per_feature": {f: int(np.isnan(feats[f]).sum()) for f in fs.names},
            "sha256": _sha256(dest),
        }
        pilot = out / f"{fs.prefix}_pilot.parquet"
        if leg == "historical" and pilot.exists():
            p = pl.read_parquet(pilot).filter(pl.col("point") == "control").sort("cell")
            p = p.filter(pl.col("cell") < ncell)
            c = p["cell"].to_numpy().astype(np.int64)
            check = compare(
                {f: p[f].to_numpy() for f in fs.names},
                {f: feats[f][c] for f in fs.names},
                fs.names,
            )
            check["basis"] = (
                "pilot control rows vs the historical table's rows for the same cells (global file "
                "read in whole row slabs)"
            )
            prov["hard_check_vs_pilot_control"] = check
            print(
                f"HARD CHECK vs pilot control: {len(c)} cells x {len(fs.names)} features, exactly "
                f"equal = {check['exactly_equal']}, max |diff| = {check['max_abs_diff']:.3g}",
                flush=True,
            )
            rc = rc or (0 if check["exactly_equal"] else 1)
        if not max_cells:
            reg = regress(table, fs, leg, ["cell"])
            prov["regression_vs_pinned_v3"] = reg
            rc = rc or (0 if reg.get("exactly_equal", True) else 1)
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
    ap.add_argument("--set", choices=("base", "x", "p"), default="x", help="module docstring")
    args = ap.parse_args()
    exp = Path(str(paths()["scratch"]["exp"]))
    v3, v3x = ("features_v3", exp / "T-features-v3"), ("features_v3x", exp / "T-features-v3x")
    fs = {
        "base": FeatureSet(fv3.V3_FEATURES, False, False, "features_v3", ()),
        "x": FeatureSet(fv3.V3_ALL, True, False, "features_v3x", (v3,)),
        "p": FeatureSet(fv3.V3_ALLP, True, True, "features_v3p", (v3, v3x)),
    }[args.set]
    default_out = (
        exp / {"base": "T-features-v3", "x": "T-features-v3x", "p": "T-features-v3p"}[args.set]
    )
    out = Path(args.out) if args.out else default_out
    if args.stage == "pilot":
        return stage_pilot(args.version, out, args.workers, args.chunk or 250, args.limit, fs)
    return stage_legs(args.legs, out, args.workers, args.chunk or 1500, args.max_cells, fs)


if __name__ == "__main__":
    raise SystemExit(main())
