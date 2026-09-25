#!/usr/bin/env python
"""Checks and dev diagnostics for the constant-CO2 equilibrium product (the emulated 1699 restart).

    scripts/spinup_product.py --stage climbuf-check --cells 240 --workers 32 --out <dir>
    scripts/spinup_product.py --stage vegc --restart <global.lpj> --out <file.parquet> --workers 64
    scripts/spinup_product.py --stage crosscheck --vegc <restart_1999.parquet> --out <file.json>
    scripts/spinup_product.py --stage year0 --vegc <a.parquet> [--vegc <b.parquet>] --out <json>

STAGES
  climbuf-check  THE PROTOCOL, PROVEN BEFORE IT IS TRUSTED. The cell rule writes each cell's climate
                 buffer as the stored spin-up left it at the end of model year 1699, which no file
                 holds. What a file does hold is the same run at 1999 (`restart_1999`). So the
                 stored protocol (`climbuf.STORED_SPINUP`: 901 shuffled draws of 1901-1930, then
                 1901-1999 in order) is replayed to 1999 from the global forcing, for a stratified
                 sample of cells, and compared with each cell's own restart_1999 buffer, field by
                 field, at the albedo solved from that buffer -- the same test the synth stream
                 passed on all 6,000 pilot runs. The 1699 stop is the prefix of this replay.
  vegc           every cell's TOTAL vegetation carbon (`corpus.vegc.cell_vegc`: trees + grass, the
                 model's own VegC definition) from a global restart, plus the corpus decoder's
                 tree-only `vegc` beside it -> parquet (cell, vegc_total, vegc_tree, vegc_grass,
                 vegc_tree_decoder, stems_per_patch)
  crosscheck     restart_1999's decoded total against the stored `VegC` of model year 1999 (seed
                 1, `vegc_spinup_1999.nc`), which must agree to float32 rounding
  year0          DEV DIAGNOSTIC, NO CLAIM: a restart's year-0 vegetation carbon scored against the
                 stored constant-CO2 truth with exactly `exp_spinup_vegc.scored_set` / `.score`, so
                 D and frac mean what they mean in the sealed X-20260924-spinup-vegc-* tests

⚠ EVERY NUMBER HERE IS A DEV DIAGNOSTIC. The emitted file's template is each cell's own
restart_1999 record and its year-0 carbon is largely the synthesiser's reproduction of the map's
prediction; the test of the restart as an equilibrium is the continuation run
(`scripts/spinup_continuation.py`), pre-registered separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

import exp_spinup_vegc as esv
from corpus_convergence import cell_index_map
from vegemu.binfmt.clm import read_grid
from vegemu.binfmt.restart import RestartReader
from vegemu.corpus.state import summarise_cell
from vegemu.corpus.vegc import cell_vegc
from vegemu.models import climbuf as cb
from vegemu.models.spinup_rule import STOP_YEAR, forcing_files
from vegemu.paths import path

Array = npt.NDArray[np.float64]

NCELL = 67420
FIRST_MODEL_YEAR = 1000  # time index 0 of vegc_spinup_1999.nc
BLOCK = 500
# The fields the forcing determines exactly (tests/test_synth_climbuf.py EXACT), and the two crop
# vernalisation terms that agree to the last bit or two (icx's fast floating-point model).
EXACT = (
    "temp_max",
    "temp_min",
    "atemp_mean",
    "atemp_mean20",
    "atemp_mean20_fix",
    "gdd5",
    "dval_prec0",
    "temp",
    "prec",
    "mprec20",
    "mtemp20",
    "min.sum",
    "min.data",
    "min.bookkeeping",
    "max.sum",
    "max.data",
    "max.bookkeeping",
)
NEAR = ("V_req", "V_req_a")
BIOME_CELLS = (52059, 42490, 33335, 18371, 12045)


def _pool(workers: int) -> ProcessPoolExecutor:
    # SPAWNED, one task per process: a forked worker that touches polars hangs (cluster.md trap 7).
    return ProcessPoolExecutor(
        max_workers=workers, mp_context=mp.get_context("spawn"), max_tasks_per_child=1
    )


# --------------------------------------------------------------------------------------------
# climbuf-check
# --------------------------------------------------------------------------------------------
def sample_cells(n: int, ncell: int = NCELL) -> list[int]:
    """Evenly spaced over the grid's order (which runs by latitude row), plus the biome cells."""
    even = np.linspace(0, ncell - 1, max(n - len(BIOME_CELLS), 1)).round().astype(int)
    return sorted({*map(int, even), *BIOME_CELLS})


def _check_cells(job: dict[str, Any]) -> list[dict[str, Any]]:
    reader = RestartReader(Path(job["restart"]))
    grid = read_grid(path("inputs.coord"))
    files = forcing_files()
    stop = cb.STORED_SPINUP.until(STOP_YEAR)
    rows: list[dict[str, Any]] = []
    with reader:
        header_seed = tuple(int(s) for s in reader.restart.seed)
        for cell in job["cells"]:
            rec = reader.read(cell)
            if rec["skip"]:
                rows.append({"cell": cell, "skip": True})
                continue
            real = rec["climbuf"]
            frac = float(rec["stands"][0]["frac"])
            f = cb.read_forcing(files, cell, float(grid[cell, 1]))
            own = cb.effective_albedo(real, f, protocol=cb.STORED_SPINUP, stand_frac=frac)
            ours, trace = cb.climate_buffer_from_forcing(
                f,
                protocol=cb.STORED_SPINUP,
                albedo=own,
                aetp_mean=float(real["scalars"][3]),
                stand_frac=frac,
            )
            buf_1699, trace_1699 = cb.climate_buffer_from_forcing(
                f, protocol=stop, albedo=own, aetp_mean=float(real["scalars"][3]), stand_frac=frac
            )
            err = cb.compare_climbuf(ours, real)
            rows.append(
                {
                    "cell": cell,
                    "skip": False,
                    "lat": float(grid[cell, 1]),
                    "stems": int(
                        sum(p["pftlist"]["tree_offsets"].size for p in rec["stands"][0]["patches"])
                    ),
                    "seed_match": tuple(trace.seed_after) == header_seed,
                    "err": err,
                    # How far the 1699 buffer is from the 1999 one: what copying it would cost.
                    "tmin20_1699_minus_1999": float(
                        trace_1699.temp_min20[-1] - trace.temp_min20[-1]
                    ),
                    "tmax20_1699_minus_1999": float(
                        trace_1699.temp_max20[-1] - trace.temp_max20[-1]
                    ),
                    "atemp_mean20_1699_minus_1999": float(
                        buf_1699["scalars"][4] - real["scalars"][4]
                    ),
                }
            )
    return rows


def stage_climbuf_check(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    restart = Path(args.restart) if args.restart else path("ground_truth.restart_spinup_end")
    cells = sample_cells(args.cells)
    chunks = [cells[i :: args.workers] for i in range(args.workers)]
    jobs = [{"restart": str(restart), "cells": c} for c in chunks if c]
    with _pool(args.workers) as ex:
        rows = [r for part in ex.map(_check_cells, jobs) for r in part]
    live = [r for r in rows if not r["skip"]]
    fields = list(live[0]["err"])
    per_field = {
        f: {
            "max_abs": float(max(r["err"][f]["max_abs"] for r in live)),
            "max_rel": float(max(r["err"][f]["max_rel"] for r in live)),
            "cells_bit_exact": int(sum(r["err"][f]["max_abs"] == 0.0 for r in live)),
        }
        for f in fields
    }
    exact_ok = all(per_field[f]["max_abs"] == 0.0 for f in EXACT)
    near_ok = all(per_field[f]["max_rel"] <= 1e-12 for f in NEAR)
    seed_ok = all(r["seed_match"] for r in live)
    d = {
        k: np.array([r[k] for r in live])
        for k in (
            "tmin20_1699_minus_1999",
            "tmax20_1699_minus_1999",
            "atemp_mean20_1699_minus_1999",
        )
    }
    out = {
        "basis": (
            f"{restart} (seed 1, model year 1999) vs the stored protocol replayed from the global "
            f"1901-2019 forcing ({', '.join(str(p) for p in forcing_files().values())}); "
            f"{len(live)} cells ({len(cells)} sampled, evenly over the grid order + the 5 biome "
            "cells); albedo solved per cell from its own 1999 buffer"
        ),
        "protocol": {
            k: getattr(cb.STORED_SPINUP, k) for k in cb.STORED_SPINUP.__dataclass_fields__
        },
        "stop_year": STOP_YEAR,
        "stop_seed_after": list(cb.STORED_SPINUP.until(STOP_YEAR).schedule()[1]),
        "cells": len(live),
        "seed_matches_header": int(sum(r["seed_match"] for r in live)),
        "per_field": per_field,
        "verdict": "PASS" if (exact_ok and near_ok and seed_ok) else "FAIL",
        "verdict_rule": "every EXACT field max_abs == 0, V_req/V_req_a max_rel <= 1e-12, and the "
        "replayed RNG state equals the header's, on every sampled cell",
        "info_1699_vs_1999": {
            k: {
                "mean": float(v.mean()),
                "p05": float(np.quantile(v, 0.05)),
                "p95": float(np.quantile(v, 0.95)),
            }
            for k, v in d.items()
        },
        "wall_s": time.perf_counter() - t0,
    }
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "climbuf_check.json").write_text(json.dumps(out, indent=1))
    (dest / "climbuf_check_cells.json").write_text(json.dumps(rows, indent=0, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "per_field"}, indent=1), flush=True)
    print(json.dumps(per_field, indent=1), flush=True)
    return 0 if out["verdict"] == "PASS" else 1


# --------------------------------------------------------------------------------------------
# vegc
# --------------------------------------------------------------------------------------------
def _vegc_block(job: dict[str, Any]) -> dict[str, list[float]]:
    reader = RestartReader(Path(job["restart"]))
    out: dict[str, list[float]] = {
        k: []
        for k in (
            "cell",
            "vegc_total",
            "vegc_tree",
            "vegc_grass",
            "vegc_tree_decoder",
            "stems_per_patch",
        )
    }
    with reader:
        for cell in range(job["first"], job["first"] + job["ncell"]):
            rec = reader.read(cell)
            v = cell_vegc(rec)
            s = summarise_cell(rec, cell, reader.layout)
            out["cell"].append(cell)
            out["vegc_total"].append(v["total"])
            out["vegc_tree"].append(v["tree"])
            out["vegc_grass"].append(v["grass"])
            out["vegc_tree_decoder"].append(float(s["vegc"]))
            out["stems_per_patch"].append(float(s["stems_per_patch"]))
    return out


def _file_sha256(p: Path, chunk: int = 64 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def stage_vegc(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    restart = Path(args.restart)
    ncell = RestartReader(restart).ncell
    jobs = [
        {"restart": str(restart), "first": a, "ncell": min(BLOCK, ncell - a)}
        for a in range(0, ncell, BLOCK)
    ]
    with _pool(args.workers) as ex:
        parts = list(ex.map(_vegc_block, jobs))
    df = (
        pl.DataFrame({k: [v for p in parts for v in p[k]] for k in parts[0]})
        .with_columns(pl.col("cell").cast(pl.Int64))
        .sort("cell")
    )
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)
    meta = {
        "restart": str(restart),
        "restart_bytes": restart.stat().st_size,
        "ncell": int(df.height),
        "vegc_total_mean": float(df["vegc_total"].mean() or np.nan),
        "vegc_grass_share_of_total": float(df["vegc_grass"].sum() / df["vegc_total"].sum()),
        "wall_s": time.perf_counter() - t0,
    }
    if args.sha256:
        meta["restart_sha256"] = _file_sha256(restart)
    dest.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1), flush=True)
    return 0


# --------------------------------------------------------------------------------------------
# crosscheck
# --------------------------------------------------------------------------------------------
def stored_vegc(year: int, seed: int = 1) -> npt.NDArray[np.float64]:
    """The stored spin-up's VegC of one model year, in cell order."""

    lat_i, lon_i = cell_index_map(path("ground_truth.grid_nc"), ncell=NCELL)
    key = "ground_truth." + "spin" + f"up_trajectory_seed{seed}"
    with netCDF4.Dataset(path(key)) as ds:
        block = np.asarray(ds.variables["VegC"][year - FIRST_MODEL_YEAR, :, :])
        if hasattr(block, "filled"):
            block = block.filled(np.nan)
    return block[lat_i, lon_i].astype(np.float64)


def stage_crosscheck(args: argparse.Namespace) -> int:

    df = pl.read_parquet(args.vegc[0]).sort("cell")
    nc = stored_vegc(1999)
    ours = df["vegc_total"].to_numpy()
    tree_dec = df["vegc_tree_decoder"].to_numpy() + df["vegc_grass"].to_numpy()
    ok = np.isfinite(nc) & np.isfinite(ours)
    diff = np.abs(ours[ok] - nc[ok])
    f32 = np.abs(ours[ok].astype(np.float32).astype(np.float64) - nc[ok])
    rel = diff / np.maximum(np.abs(nc[ok]), 1e-9)
    dec_rel = np.abs(tree_dec[ok] - nc[ok]) / np.maximum(np.abs(nc[ok]), 1e-9)
    out = {
        "basis": "restart_1999 (seed 1) decoded total VegC vs vegc_spinup_1999.nc, model year 1999",
        "cells_compared": int(ok.sum()),
        "max_abs_diff_gC_m2": float(diff.max()),
        "max_rel_diff": float(rel.max()),
        "cells_equal_after_float32_rounding": int((f32 == 0.0).sum()),
        "share_within_rel_1e-6": float((rel <= 1e-6).mean()),
        "corpus_decoder_tree_plus_grass": {
            "median_rel_diff": float(np.median(dec_rel)),
            "p99_rel_diff": float(np.quantile(dec_rel, 0.99)),
            "share_within_rel_1e-6": float((dec_rel <= 1e-6).mean()),
        },
    }
    out["verdict"] = "PASS" if out["share_within_rel_1e-6"] == 1.0 else "FAIL"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1), flush=True)
    return 0 if out["verdict"] == "PASS" else 1


# --------------------------------------------------------------------------------------------
# year0
# --------------------------------------------------------------------------------------------
def rate_against_stored(values: Array) -> dict[str, Any]:
    """`exp_spinup_vegc`'s scored set and score for one per-cell VegC array (cell order)."""

    inp = esv._inputs()
    sc = esv.scored_set(inp)
    mask = sc["mask"].astype(bool)
    if values.shape != mask.shape:
        raise ValueError(f"{values.shape} values for {mask.shape} cells")
    got = esv.score(values[mask], sc)
    got["scored_cells"] = int(mask.sum())
    got["frac_rerun"] = float(sc["frac_rerun"])
    got["missing_in_scored_set"] = int((~np.isfinite(values[mask])).sum())
    return got


def stage_year0(args: argparse.Namespace) -> int:

    out: dict[str, Any] = {
        "note": "DEV DIAGNOSTIC, NO CLAIM: a restart's year-0 VegC vs the constant-CO2 truth",
        "scorer": "scripts/exp_spinup_vegc.py scored_set/score (the sealed tests' own)",
    }
    for p in args.vegc:
        df = pl.read_parquet(p).sort("cell")
        if df.height != NCELL or df["cell"].to_list() != list(range(NCELL)):
            raise ValueError(f"{p}: not a {NCELL}-cell table in cell order")
        out[str(p)] = rate_against_stored(df["vegc_total"].to_numpy().astype(np.float64))
        a = out[str(p)]
        print(
            f"{p}: D {a['D']:+.6f} frac {a['frac']:.4f} skill {a['skill_log1p']:+.4f}", flush=True
        )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--stage", required=True, choices=("climbuf-check", "vegc", "crosscheck", "year0")
    )
    ap.add_argument("--restart", default=None)
    ap.add_argument("--vegc", action="append", default=[])
    ap.add_argument("--cells", type=int, default=240)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--sha256", action="store_true", help="vegc: also hash the whole restart")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    return {
        "climbuf-check": stage_climbuf_check,
        "vegc": stage_vegc,
        "crosscheck": stage_crosscheck,
        "year0": stage_year0,
    }[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
