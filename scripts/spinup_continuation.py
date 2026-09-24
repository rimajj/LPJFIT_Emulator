#!/usr/bin/env python
"""The continuation run: does the real model HOLD a restart at the stored constant-CO2 equilibrium?

    scripts/spinup_continuation.py plan    --root <dir> [--members 1024]
    scripts/spinup_continuation.py build   --root <dir> --arm null     --restart <restart_1999.lpj>
    scripts/spinup_continuation.py build   --root <dir> --arm emulated --restart <product.lpj>
    scripts/spinup_continuation.py harvest --root <dir> --arm null
    scripts/spinup_continuation.py asgood  --root <dir> --arm null

THE TEST. An equilibrium restart is one the model does not walk away from. So each arm starts the
real LPJmL-FIT FROM a restart (`-DFROM_RESTART`) and continues the stored spin-up's OWN protocol for
30 model years -- shuffled draws of 1901-1930, CO2 at 276.59 ppm, npatch 25, every other setting
the stored run's -- writing annual VegC (netCDF), the global flux table and the drawn climate year.
The mean VegC of continuation years 1-10 (and, beside it, 21-30) is then scored against the stored
constant-CO2 truth with `exp_spinup_vegc`'s own scorer, so D and frac mean what they mean in the
sealed X-20260924-spinup-vegc-* tests.

  null      continue `restart_1999`: the stored run's own end state, which carries the carbon of
            the 1700-1999 CO2 ramp (368 ppm at its end). Its D is what the model does from a
            state that is the right forest at the wrong CO2 -- the bar the emulated arm is read
            against, measured before the emulated arm runs.
  emulated  continue the emulated 1699 restart (`synth_global.py` with the spin-up cell rule).

THE CONFIG IS THE STORED RUN'S OWN SAVED CONFIG, PATCHED, every patch asserted to hit
(`corpus_cmodel_config.patch`): the `#include` names an input list that differs from the stored
one only in its CO2 file (constant 276.59 ppm, `corpus_spinup_config.write_constant_co2`), the
FROM_RESTART run block becomes a 30-year spin-up continuation at model years 1871-1900
(`firstyear 1901, lastyear 1900, nspinup 30, nspinyear 30`: every year is before the forcing's
1901, so every year draws a shuffled one of the first 30 -- `iterate.c:102-119`), no restart is
written, and the output list is VegC (cdf), globalflux (txt, the spin-up's 1e-9 scale), grid (cdf)
and climatyear (txt). The global RNG state that shuffles the years is restored from the restart
header (`openrestart.c:139`), and the emulated file carries restart_1999's header, so both arms
draw the SAME 30 years: a paired comparison. `climatyear` records them, and `harvest` checks every
member drew the same sequence.

⚠ THE GLOBE RUNS IN PIECES, AND WHY THAT IS THE SAME RUN. `plan` cuts the 67,420 cells into
contiguous ranges (`startgrid`..`endgrid`) of about equal projected cost, each an independent
single-task run in one task farm (`sbatch_cmodel.sh --manifest`, NTASKS below the member count so
the allocation tracks the CPU used -- the stored run's 2048-task MPI job was charged 12.8
core-hours per model year for ~4 of work). LPJmL-FIT cells do not interact here (no river routing):
the only shared state is the year-shuffle generator, which every member restores from the same
header and draws on its rank 0 exactly as the global run's root does, and each cell's own
generator comes from its record. So a member is the global run restricted to its cells.
`MEMORY.md:subset-diverges` was measured on runs from scratch and on blocks scored against global
truth; both arms here are run with the same members, so whatever a partition does, it does to both.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

from corpus_cmodel_config import SAVED_CONFIG_SUBDIR, patch
from corpus_spinup_config import (
    CO2_PREINDUSTRIAL_PPM,
    SAVED_INPUT,
    co2_seen_by_model,
    read_co2_input,
    write_constant_co2,
)
from vegemu.binfmt.clm import read_grid
from vegemu.binfmt.restart import RestartReader
from vegemu.models import climbuf as cb
from vegemu.paths import path, paths
from vegemu.results import append_result_block

NCELL = 67420
NYEAR = 30
# Model year of continuation year 1. `firstyear` must be >= the forcing's first year (1901) or the
# pre-flight refuses (filesexist.c ERROR237, measured on the first build at 1700-1729), and every
# run year must be < 1901 to be a shuffled spin-up draw: so firstyear 1901, lastyear 1900, nspinup
# 30 = model years 1871-1900. CO2 there is the constant file's 276.59 ppm, and nothing else in this
# configuration reads the year number (no land use, no fixed-year switches before 1970).
FIRST_YEAR = 1871
WINDOWS = {"y01_10": (1, 10), "y21_30": (21, 30)}  # continuation years, inclusive
DEFAULT_MEMBERS = 1024
CALIBRATION_EVERY = 8  # piece 0 = every 8th member, run first; its CPU prices the rest
# Projected CPU of one cell-year from its restart record size: the pilot's 200 control spin-ups
# (pilot-v2-constco2, Aug-12 binary, npatch 25) give wall = -10.5 s + 114.3 s/MB per 1000 years,
# fitted 2026-09-24; floored at 20 s per 1000 years for a vegetation-free cell. Only BALANCES the
# pieces and prices the plan; the calibration piece measures the real number before the rest runs.
COST_INTERCEPT_S = -0.0105
COST_PER_MB_S = 0.11427
COST_FLOOR_S = 0.020


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------------
# plan: the members
# --------------------------------------------------------------------------------------------
def cell_cost(
    nbytes: npt.NDArray[np.int64], skip: npt.NDArray[np.bool_]
) -> npt.NDArray[np.float64]:
    """Projected CPU seconds per model year of each cell."""
    mb = nbytes.astype(np.float64) / 1e6
    c = np.maximum(COST_INTERCEPT_S + COST_PER_MB_S * mb, COST_FLOOR_S)
    out: npt.NDArray[np.float64] = np.where(skip, 0.1 * COST_FLOOR_S, c)
    return out


def partition(cost: npt.NDArray[np.float64], members: int) -> list[tuple[int, int]]:
    """Contiguous [first, last] cell ranges of about `total / members` projected cost each."""
    target = float(cost.sum()) / members
    out: list[tuple[int, int]] = []
    start, acc = 0, 0.0
    for i, c in enumerate(cost):
        acc += float(c)
        if acc >= target and len(out) < members - 1:
            out.append((start, i))
            start, acc = i + 1, 0.0
    if start < cost.size:
        out.append((start, cost.size - 1))
    return out


def stage_plan(args: argparse.Namespace) -> int:
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    census = pl.read_parquet(args.census).sort("cell")
    if census.height != NCELL or census["cell"].to_list() != list(range(NCELL)):
        raise ValueError(f"{args.census}: not a {NCELL}-cell census in cell order")
    cost = cell_cost(census["bytes"].to_numpy(), census["skip"].to_numpy())
    ranges = partition(cost, args.members)
    per = np.array([cost[a : b + 1].sum() for a, b in ranges])
    members = [
        {"k": k, "name": f"m{k:04d}", "first": a, "last": b, "cost_s_per_year": float(per[k])}
        for k, (a, b) in enumerate(ranges)
    ]
    assert members[0]["first"] == 0 and members[-1]["last"] == NCELL - 1
    assert all(m["first"] == p["last"] + 1 for p, m in itertools.pairwise(members))
    plan = {
        "census": str(args.census),
        "census_sha256": _sha(Path(args.census)),
        "cost_model": (
            f"cpu_s/yr = max({COST_INTERCEPT_S} + {COST_PER_MB_S} * restart_MB, {COST_FLOOR_S}); "
            "pilot-v2-constco2 control spin-ups, 200 runs"
        ),
        "projected_cpu_core_hours_per_arm": float(cost.sum() * NYEAR / 3600.0),
        "members": members,
        "pieces": {
            "p0": [m["k"] for m in members if m["k"] % CALIBRATION_EVERY == 0],
            "p1": [m["k"] for m in members if m["k"] % CALIBRATION_EVERY != 0],
        },
    }
    (root / "members.json").write_text(json.dumps(plan, indent=1))
    print(
        json.dumps(
            {
                "members": len(members),
                "cells_per_member": [
                    int(min(m["last"] - m["first"] + 1 for m in members)),
                    int(max(m["last"] - m["first"] + 1 for m in members)),
                ],
                "member_cost_s_per_year_max": float(per.max()),
                "projected_cpu_core_hours_per_arm": plan["projected_cpu_core_hours_per_arm"],
            },
            indent=1,
        ),
        flush=True,
    )
    return 0


# --------------------------------------------------------------------------------------------
# build: configs and manifests
# --------------------------------------------------------------------------------------------
RUN_BLOCK = re.compile(r"(#ifndef FROM_RESTART\n)(.*?)(\n#else\n)(.*?)(\n#endif\n\}\s*)$", re.S)
OUTPUT_BLOCK = re.compile(r'(#ifdef FROM_RESTART\s*\n\s*"output" :\s*\n\s*\[)(.*?)(\],\s*\n)', re.S)


def continuation_block(restart: Path) -> str:
    return (
        "\n"
        f'  "nspinup" : {NYEAR},   /* a {NYEAR}-year continuation of the spin-up */\n'
        '  "nspinyear" : 30,  /* cycle length during spinup (yr)*/\n'
        f'  "firstyear": {FIRST_YEAR + NYEAR}, /* every year < 1901: all shuffled draws */\n'
        f'  "lastyear" : {FIRST_YEAR + NYEAR - 1},\n'
        f'  "outputyear": {FIRST_YEAR},\n'
        '  "restart" :  true, /* start from restart file */\n'
        f'  "restart_filename" : "{restart}",\n'
        '  "write_restart" : false\n'
    )


OUTPUTS = """
    { "id" : "grid",       "file" : { "fmt" : "cdf", "name" : "output/grid.nc" }},
    { "id" : "globalflux", "file" : { "fmt" : "txt", "scale" : 1e-9,
                                      "name" : "output/globalflux.csv"}},
    { "id" : "vegc",       "file" : { "fmt" : "cdf", "name" : "output/vegc.nc"}},
    { "id" : "climatyear", "file" : { "fmt" : "txt", "name" : "output/climatyear.csv"}},
  """
DONE = re.compile(r"^lpjml successfully terminated", re.M)


def arm_config_text(input_js: Path, restart: Path) -> str:
    """The stored run's saved config with exactly the continuation's changes, each asserted."""
    saved = path("ground_truth.historical_seed1") / SAVED_CONFIG_SUBDIR
    text = saved.read_text(encoding="utf-8")
    text = patch(
        text, r'^\s*#include "[^"]*input_2000_2019\.js".*$', f'  #include "{input_js}"', expect=2
    )
    m = RUN_BLOCK.search(text)
    if m is None or '"nspinup" : 0' not in m.group(4) or '"restart" :  true' not in m.group(4):
        raise AssertionError("the saved config's FROM_RESTART run block changed shape")
    text = text[: m.start(4)] + continuation_block(restart) + text[m.end(4) :]
    o = OUTPUT_BLOCK.search(text)
    if o is None or "vegc_2000_2019.nc" not in o.group(2):
        raise AssertionError("the saved config's FROM_RESTART output list changed shape")
    text = text[: o.start(2)] + OUTPUTS + text[o.end(2) :]
    return text


def member_config(base: str, first: int, last: int) -> str:
    return patch(
        base,
        r'^\s*"startgrid" : "all",.*$',
        f'  "startgrid" : {first},\n  "endgrid" : {last},',
    )


def stage_build(args: argparse.Namespace) -> int:
    root = Path(args.root)
    plan = json.loads((root / "members.json").read_text())
    restart = Path(args.restart).resolve()
    head = RestartReader(restart)
    if head.ncell != NCELL or head.generic.firstcell != 0:
        raise ValueError(f"{restart}: {head.ncell} cells from {head.generic.firstcell}")
    # Both arms must draw the same years: the state that shuffles them is the header's.
    want_seed = cb.STORED_SPINUP.schedule()[1]
    if tuple(head.restart.seed) != tuple(want_seed):
        raise ValueError(f"{restart}: header RNG state {head.restart.seed}, not {want_seed}")
    co2 = root / f"co2_const_{CO2_PREINDUSTRIAL_PPM:.2f}.txt"
    if not co2.exists():
        write_constant_co2(co2)
    seen = co2_seen_by_model(co2, range(FIRST_YEAR, FIRST_YEAR + NYEAR))
    assert set(seen.values()) == {CO2_PREINDUSTRIAL_PPM}, seen
    saved_input = path("ground_truth.historical_seed1") / SAVED_INPUT
    input_js = root / "input_continuation.js"
    text = patch(
        saved_input.read_text(encoding="utf-8"),
        r'^(\s*"co2"\s*:\s*\{\s*"fmt"\s*:\s*"txt",\s*"name"\s*:\s*)"[^"]+"',
        rf'\g<1>"{co2}"',
    )
    input_js.write_text(text, encoding="utf-8")
    assert read_co2_input(input_js) == str(co2)
    base = arm_config_text(input_js, restart)
    arm_dir = root / args.arm
    (arm_dir / "manifests").mkdir(parents=True, exist_ok=True)
    rows: dict[int, str] = {}
    for m in plan["members"]:
        rdir = arm_dir / m["name"]
        (rdir / "output").mkdir(parents=True, exist_ok=True)
        (rdir / "restart").mkdir(parents=True, exist_ok=True)
        cfg = rdir / f"lpjml_{args.arm}_{m['name']}.js"
        cfg.write_text(member_config(base, m["first"], m["last"]), encoding="utf-8")
        rows[m["k"]] = f"{args.arm}-{m['name']}\t{cfg}\t{rdir}\n"
    for piece, ks in plan["pieces"].items():
        # Most expensive first, so the farm's tail is its cheapest members.
        order = sorted(ks, key=lambda k: -plan["members"][k]["cost_s_per_year"])
        (arm_dir / "manifests" / f"manifest_{piece}.tsv").write_text(
            "".join(rows[k] for k in order)
        )
    check = [plan["members"][0], plan["members"][len(plan["members"]) // 2], plan["members"][-1]]
    (arm_dir / "manifests" / "manifest_check.tsv").write_text("".join(rows[m["k"]] for m in check))
    meta = {
        "arm": args.arm,
        "restart": str(restart),
        "restart_bytes": restart.stat().st_size,
        "restart_header_seed": list(head.restart.seed),
        "co2_file": str(co2),
        "co2_sha256": _sha(co2),
        "input_js_sha256": _sha(input_js),
        "base_config_sha256": hashlib.sha256(base.encode()).hexdigest(),
        "model_years": [FIRST_YEAR, FIRST_YEAR + NYEAR - 1],
        "members": len(plan["members"]),
        "pieces": {p: len(ks) for p, ks in plan["pieces"].items()},
    }
    (arm_dir / "build.json").write_text(json.dumps(meta, indent=1))
    (arm_dir / "base_config.js").write_text(base, encoding="utf-8")
    print(json.dumps(meta, indent=1), flush=True)
    return 0


# --------------------------------------------------------------------------------------------
# harvest: merge the members
# --------------------------------------------------------------------------------------------
def _member_vegc(rdir: Path, cells: npt.NDArray[np.int64], coords: npt.NDArray[np.float64]) -> Any:
    with netCDF4.Dataset(rdir / "output" / "vegc.nc") as ds:
        lat = np.asarray(ds.variables["lat"][:], dtype=np.float64)
        lon = np.asarray(ds.variables["lon"][:], dtype=np.float64)
        v = ds.variables["VegC"][:]
        years = np.asarray(ds.variables["time"][:]).size
        block = np.asarray(v.filled(np.nan) if hasattr(v, "filled") else v, dtype=np.float32)
    li = np.abs(lat[None, :] - coords[cells, 1][:, None]).argmin(axis=1)
    lo = np.abs(lon[None, :] - coords[cells, 0][:, None]).argmin(axis=1)
    off = np.maximum(np.abs(lat[li] - coords[cells, 1]), np.abs(lon[lo] - coords[cells, 0]))
    if not (off < 1e-6).all():
        raise ValueError(f"{rdir}: {int((off >= 1e-6).sum())} cells not on the file's grid")
    return block[:, li, lo], years


def _member_tables(
    rdir: Path,
) -> tuple[npt.NDArray[np.float64], list[str], tuple[tuple[int, int], ...]]:
    """A member's global-flux table (its cells' totals), its header, and its drawn years."""
    csv = (rdir / "output" / "globalflux.csv").read_text().splitlines()
    f = np.array([[float(x) for x in ln.split(",")] for ln in csv[2:] if ln.strip()])
    if f.shape[0] != NYEAR:
        raise ValueError(f"{rdir}: {f.shape[0]} flux years")
    cy: list[tuple[int, int]] = []
    for ln in (rdir / "output" / "climatyear.csv").read_text().split():
        parts = ln.split(",")
        if len(parts) == 2 and all(p.strip().lstrip("-").isdigit() for p in parts):
            cy.append((int(parts[0]), int(parts[1])))
    return f, csv[0].split(","), tuple(cy)


def stage_harvest(args: argparse.Namespace) -> int:
    root = Path(args.root)
    plan = json.loads((root / "members.json").read_text())
    arm_dir = root / args.arm
    coords = read_grid(path("inputs.coord"))
    vegc = np.full((NYEAR, NCELL), np.nan, dtype=np.float32)
    flux: npt.NDArray[np.float64] | None = None
    header: list[str] = []
    seqs: set[tuple[tuple[int, int], ...]] = set()
    missing: list[str] = []
    for m in plan["members"]:
        rdir = arm_dir / m["name"]
        log = rdir / f"lpjml.{args.arm}-{m['name']}.log"
        # The model's own line, anchored (cmodel-run skill): never an exit code.
        done = log.exists() and DONE.search(log.read_text(errors="replace")) is not None
        if not done:
            missing.append(m["name"])
            continue
        cells = np.arange(m["first"], m["last"] + 1)
        block, years = _member_vegc(rdir, cells, coords)
        if years != NYEAR:
            raise ValueError(f"{rdir}: {years} years of VegC, expected {NYEAR}")
        vegc[:, cells] = block
        f, header, cy = _member_tables(rdir)
        flux = f.copy() if flux is None else flux + np.c_[np.zeros(NYEAR), f[:, 1:]]
        seqs.add(cy)
    out: dict[str, Any] = {
        "arm": args.arm,
        "members": len(plan["members"]),
        "members_done": len(plan["members"]) - len(missing),
        "missing": missing[:50],
    }
    if missing:
        (arm_dir / "harvest.json").write_text(json.dumps(out, indent=1))
        print(json.dumps(out, indent=1), flush=True)
        return 1
    assert flux is not None
    out["climate_year_sequences"] = len(seqs)
    seq = next(iter(seqs))
    out["climate_years"] = [c for _, c in seq]
    out["model_years"] = [y for y, _ in seq]
    # The replay's prediction of the draws: 30 more from the header's state.
    predicted = [
        cb.STORED_SPINUP.climate_firstyear + i
        for i in cb.continue_draws(cb.STORED_SPINUP.schedule()[1], NYEAR)
    ]
    out["climate_years_predicted"] = predicted
    out["climate_years_match_replay"] = out["climate_years"] == predicted
    np.save(arm_dir / "vegc_continuation.npy", vegc)
    cols = {"cell": np.arange(NCELL)}
    for name, (a, b) in WINDOWS.items():
        cols[f"vegc_{name}"] = np.nanmean(vegc[a - 1 : b], axis=0).astype(np.float64)
    cols["vegc_y01"] = vegc[0].astype(np.float64)
    cols["vegc_y30"] = vegc[-1].astype(np.float64)
    pl.DataFrame(cols).write_parquet(arm_dir / "vegc_windows.parquet")
    pl.DataFrame({h: flux[:, i] for i, h in enumerate(header)}).write_csv(
        arm_dir / "globalflux_merged.csv"
    )
    out["global_vegc_pgc_by_year"] = [float(x) / 1e6 for x in flux[:, header.index("VegC")]]
    (arm_dir / "harvest.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1), flush=True)
    return 0 if len(seqs) == 1 else 1


# --------------------------------------------------------------------------------------------
# asgood: the windows against the stored truth, with the sealed tests' scorer
# --------------------------------------------------------------------------------------------
def stage_asgood(args: argparse.Namespace) -> int:
    import exp_spinup_vegc as esv  # noqa: PLC0415 -- heavy (lightgbm), only this stage needs it

    root = Path(args.root)
    arm_dir = root / args.arm
    win = pl.read_parquet(arm_dir / "vegc_windows.parquet").sort("cell")
    vegc = np.load(arm_dir / "vegc_continuation.npy")
    inp = esv._inputs()
    sc = esv.scored_set(inp)
    mask = sc["mask"].astype(bool)
    out: dict[str, Any] = {
        "note": "DEV numbers until the pre-registration is sealed; the scorer is exp_spinup_vegc's",
        "arm": args.arm,
        "scored_cells": int(mask.sum()),
        "frac_rerun": float(sc["frac_rerun"]),
    }
    for name in WINDOWS:
        x = win[f"vegc_{name}"].to_numpy().astype(np.float64)
        out[name] = esv.score(x[mask], sc)
    out["D_by_year"] = [
        float(esv.score(vegc[y].astype(np.float64)[mask], sc)["D"]) for y in range(NYEAR)
    ]
    t = ((sc["t1"] + sc["t2"]) / 2).sum()
    out["scored_total_vegc_ratio_to_truth_by_year"] = [
        float(vegc[y].astype(np.float64)[mask].sum() / t) for y in range(NYEAR)
    ]
    (arm_dir / "asgood.json").write_text(json.dumps(out, indent=1))
    for name in WINDOWS:
        a = out[name]
        print(
            f"{args.arm} {name}: D {a['D']:+.6f} frac {a['frac']:.4f} skill {a['skill_log1p']:+.4f}"
        )
    return 0


# --------------------------------------------------------------------------------------------
# metrics: the pre-registered experiment's decision values (X-20260925-spinup-restart-continuation)
# --------------------------------------------------------------------------------------------
STATISTIC = "asgood_vegc_spinup"
PRIMARY = "y01_10"
MAP_NULLS_FROM = "X-20260924-spinup-vegc-from-pilot"  # its sealed nulls, reused by value
MAP_NULLS = ("training_mean", "nearest_analogue", "nearest_geographic", "shuffled")
CONTINUATION_NULL = "restart_1999_continuation"


def stage_metrics(args: argparse.Namespace) -> int:
    """model = the emulated continuation's D on the years 1-10 mean; nulls = the restart_1999
    continuation (the null arm, harvested before the model arm ran) and the map-level nulls of the
    sealed map test, read from its own nulls.json. 21-30 and the yearly D are reported beside."""
    import exp_spinup_vegc as esv  # noqa: PLC0415 -- heavy (lightgbm), only this stage needs it

    root = Path(args.root)
    inp = esv._inputs()
    sc = esv.scored_set(inp)
    mask = sc["mask"].astype(bool)
    arms: dict[str, dict[str, Any]] = {}
    for arm, label in (("emulated", "model"), ("null", CONTINUATION_NULL)):
        win = pl.read_parquet(root / arm / "vegc_windows.parquet").sort("cell")
        harvest = json.loads((root / arm / "harvest.json").read_text())
        if harvest.get("members_done") != harvest.get("members"):
            raise RuntimeError(f"{arm}: {harvest.get('members_done')}/{harvest.get('members')}")
        arms[label] = {
            name: esv.score(win[f"vegc_{name}"].to_numpy().astype(np.float64)[mask], sc)
            for name in WINDOWS
        }
        arms[label]["climate_years"] = harvest["climate_years"]
    if arms["model"]["climate_years"] != arms[CONTINUATION_NULL]["climate_years"]:
        raise RuntimeError("the two arms drew different climate years: not a paired comparison")
    prior = json.loads(
        (Path(str(paths()["scratch"]["exp"])) / MAP_NULLS_FROM / "nulls.json").read_text()
    )
    map_nulls = prior.get("arm_details", prior.get("arms"))
    decision = {"model": float(arms["model"][PRIMARY]["D"])}
    decision[CONTINUATION_NULL] = float(arms[CONTINUATION_NULL][PRIMARY]["D"])
    decision.update({n: float(map_nulls[n]["D"]) for n in MAP_NULLS})
    report: dict[str, Any] = {
        "exp_id": args.exp_id,
        "statistic": STATISTIC,
        "primary_window": PRIMARY,
        "scored_cells": int(mask.sum()),
        "frac_rerun": float(sc["frac_rerun"]),
        "arm_details": arms,
        "map_nulls_from": MAP_NULLS_FROM,
        "decision": {
            "D": decision["model"],
            "threshold": args.threshold,
            "verdict": "pass" if decision["model"] >= args.threshold else "fail",
        },
    }
    report.update(append_result_block(statistic=STATISTIC, arms=decision, n=int(mask.sum())))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for k, v in decision.items():
        print(f"  {k:28s} D {v:+.6f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--root", required=True)
    p.add_argument("--members", type=int, default=DEFAULT_MEMBERS)
    p.add_argument("--census", required=True)
    p = sub.add_parser("build")
    p.add_argument("--root", required=True)
    p.add_argument("--arm", required=True, choices=("null", "emulated"))
    p.add_argument("--restart", required=True)
    for name in ("harvest", "asgood"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        p.add_argument("--arm", required=True, choices=("null", "emulated"))
    p = sub.add_parser("metrics")
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--exp-id", default="")
    p.add_argument("--threshold", type=float, default=-0.02)
    args = ap.parse_args()
    return {
        "plan": stage_plan,
        "build": stage_build,
        "harvest": stage_harvest,
        "asgood": stage_asgood,
        "metrics": stage_metrics,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
