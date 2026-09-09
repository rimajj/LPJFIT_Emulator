#!/usr/bin/env python
"""D1's verdict: did the state move in the expected direction, and by more than the model's noise?

    scripts/sbatch_py.sh D-d1-direction scripts/corpus_d1_direction.py

WHAT IS BEING ASKED. Not "is the emulator right" -- nothing is being emulated here. The question is
whether a PERTURBED forcing file, written by our own writer and read by the real C model, produces
the state change the physics says it should. If it does not, the perturbation writer is broken and
every spin-up of the pilot corpus would be wasted.

THE EXPECTATION, WRITTEN DOWN BEFORE THE RUNS FINISHED so it cannot be fitted afterwards:

  boreal Siberia (-8.3 C)      cold-limited      warming -> MORE vegetation carbon
  temperate Hainich (8.0 C)    mildly limited    warming -> small change, sign not predicted
  Mediterranean Iberia (14.6)  water-limited     warming -> LESS (fixed RH means rising VPD)
  semi-arid Sahel (29.2 C)     hot and dry       warming -> LESS
  tropical Amazon (27.2 C)     already hot       warming -> LESS

Two cells expected to move in OPPOSITE directions is the part that matters: a writer that merely
scaled everything would move them the same way.

THE NULL, AND WHY IT IS NOT OPTIONAL. LPJmL-FIT is stochastic, so "the state moved" means nothing
without knowing how far it moves when NOTHING is changed. Every cell was therefore spun up twice at
zero perturbation with different random seeds, and that gap is reported beside every response
(invariant 1). The response is only called real where it exceeds `max(10 %, the two-seed gap)`,
which is the standing tolerance (invariant 5).

⚠ THIS IS FIVE CELLS. It is a direction test on a paired difference, and it is NOT fidelity
evidence: the acceptance criterion is all 54,020 cells (`MEMORY.md:acceptance`). Nothing here may be
quoted as agreement with anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import numpy.typing as npt
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.corpus.state import state_table
from vegemu.paths import scratch

# The last N spin-up years averaged, rather than the final year. The 1000-year spin-up is NOT
# converged (`docs/decisions/20260908-D-spinup-is-not-converged.md`), so the endpoint carries the
# last year's weather; a 30-year mean is the same convention that measurement used.
TAIL_YEARS = 30
# The floor of the acceptance band. The other term is this cell's own two-seed gap.
TOLERANCE_FLOOR = 0.10

CELLS: dict[str, int] = {
    "boreal_siberia": 52059,
    "temperate_hainich": 42490,
    "mediterranean_iberia": 33335,
    "semiarid_sahel": 18371,
    "tropical_amazon": 12045,
}
EXPECTED: dict[str, str] = {
    "boreal_siberia": "up",
    "temperate_hainich": "unpredicted",
    "mediterranean_iberia": "down",
    "semiarid_sahel": "down",
    "tropical_amazon": "down",
}
LADDER: dict[str, float] = {
    "control": 0.0,
    "core_t+2_p10": 2.0,
    "core_t+4_p10": 4.0,
    "core_t+6_p10": 6.0,
}
NULL_SEED = 2
# The attribution arm: the same +4 K with specific humidity left alone, so relative humidity falls
# instead of holding. Its gap against the real +4 K arm is the part of the response that belongs to
# `PLAN.md` rule 2 rather than to the model's temperature response. Diagnostics only, never corpus.
ATTRIB_POINT = "core_t+4_p10_nofixrh"

# The state columns the direction is judged on. Vegetation carbon is the headline; the stem count
# and the height distribution are there because the acceptance criterion is conjunctive and a
# response that moved carbon without moving the roster would be suspicious.
REPORT: tuple[str, ...] = (
    "vegc",
    "agb",
    "stems_total",
    "lai",
    "height_p50",
    "wooddens_p50",
    "sla_p50",
    "hbin_30p",
)


def _run_dir(cell: int, point: str, seed: int) -> Path:
    return scratch("runs", "d1", f"c{cell}-{point}-s{seed}")


def _tag(cell: int, point: str, seed: int) -> str:
    return f"c{cell}-{point}-s{seed}"


def _series(run: Path, tag: str) -> npt.NDArray[np.float64]:
    with netCDF4.Dataset(run / "output" / f"vegc_spinup_{tag}.nc") as ds:
        return np.asarray(ds.variables["VegC"][:]).reshape(-1).astype(np.float64)


def _trajectory(run: Path, tag: str) -> dict[str, Any]:
    """Window means of the spin-up vegetation-carbon trajectory, plus a coarse shape.

    ⚠ THE LAST 30 YEARS ARE NOT LIKE THE REST. The spin-up shuffles years at random until it
    reaches the forcing file's own first year and then runs the file IN ORDER, so with a 30-year
    file the tail is 30 years of a FIXED climate sequence that every arm and every seed shares. A
    window mean taken over the tail therefore has far less climate noise in it than one taken over
    the shuffled part -- and comparing the two is comparing different things, which is why several
    windows are reported side by side rather than one.
    """
    series = _series(run, tag)
    out: dict[str, Any] = {"spinup_years": int(series.size)}
    for w in (30, 100, 300):
        out[f"tail{w}"] = float(series[-w:].mean())
    # A coarse shape: the mean of each 100-year block, so a collapse or a recovery is visible.
    blocks = series[: (series.size // 100) * 100].reshape(-1, 100).mean(axis=1)
    out["blocks100"] = [round(float(x), 1) for x in blocks]
    return out


def _state(run: Path, tag: str) -> dict[str, float]:
    restart = run / "restart" / f"restart_{tag}.lpj"
    row = state_table(restart, cells=[0]).to_dicts()[0]
    return {k: float(v) if v is not None else float("nan") for k, v in row.items()}


def _attrib_present() -> bool:
    """The attribution arm is optional: the direction table stands without it."""
    return all(
        (
            _run_dir(c, ATTRIB_POINT, 1) / "restart" / f"restart_{_tag(c, ATTRIB_POINT, 1)}.lpj"
        ).exists()
        for c in CELLS.values()
    )


def collect() -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    points = {**LADDER, ATTRIB_POINT: 4.0} if _attrib_present() else LADDER
    for biome, cell in CELLS.items():
        for point, dtemp in points.items():
            seeds = [1, NULL_SEED] if point == "control" else [1]
            for seed in seeds:
                tag = _tag(cell, point, seed)
                run = _run_dir(cell, point, seed)
                traj = _trajectory(run, tag)
                rows.append(
                    {
                        "biome": biome,
                        "cell": cell,
                        "point": point,
                        "dtemp": dtemp,
                        "seed": seed,
                        "vegc_traj_gCm2": traj[f"tail{TAIL_YEARS}"],
                        "tail30": traj["tail30"],
                        "tail100": traj["tail100"],
                        "tail300": traj["tail300"],
                        "spinup_years": traj["spinup_years"],
                        "blocks100": traj["blocks100"],
                        **{k: v for k, v in _state(run, tag).items() if k in REPORT},
                    }
                )
    return pl.DataFrame(rows)


def _rel(a: float, b: float) -> float:
    """Relative difference on the mean of the two, so it is symmetric and has no privileged arm."""
    mid = (abs(a) + abs(b)) / 2.0
    return float("nan") if mid == 0 else (a - b) / mid


def analyse(table: pl.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"cells": {}, "tail_years": TAIL_YEARS}
    for biome, cell in CELLS.items():
        sub = table.filter(pl.col("cell") == cell)
        ctrl_arm = sub.filter(pl.col("point") == "control")
        ctl = ctrl_arm.filter(pl.col("seed") == 1).to_dicts()[0]
        null = ctrl_arm.filter(pl.col("seed") == NULL_SEED).to_dicts()[0]
        entry: dict[str, Any] = {
            "cell": cell,
            "expected": EXPECTED[biome],
            "control_vegc_gCm2": ctl["vegc_traj_gCm2"],
            "spinup_years": ctl["spinup_years"],
            "control_blocks100": ctl["blocks100"],
            "two_seed_gap": {},
            "response": {},
        }
        for col in ("vegc_traj_gCm2", "tail30", "tail100", "tail300", *REPORT):
            entry["two_seed_gap"][col] = abs(_rel(ctl[col], null[col]))

        for point, dtemp in LADDER.items():
            if point == "control":
                continue
            warm = sub.filter(pl.col("point") == point).to_dicts()[0]
            band = max(TOLERANCE_FLOOR, entry["two_seed_gap"]["vegc_traj_gCm2"])
            rel = _rel(warm["vegc_traj_gCm2"], ctl["vegc_traj_gCm2"])
            entry["response"][f"+{dtemp:.0f}K"] = {
                "vegc_gCm2": warm["vegc_traj_gCm2"],
                "rel_vs_control": rel,
                "band": band,
                "exceeds_band": bool(abs(rel) > band),
                "direction": "up" if rel > 0 else "down",
                "blocks100": warm["blocks100"],
                **{f"rel_tail{w}": _rel(warm[f"tail{w}"], ctl[f"tail{w}"]) for w in (30, 100, 300)},
                **{f"rel_{c}": _rel(warm[c], ctl[c]) for c in REPORT if c != "vegc"},
            }
        attrib = sub.filter(pl.col("point") == ATTRIB_POINT).to_dicts()
        if attrib:
            real = entry["response"]["+4K"]["rel_vs_control"]
            held = _rel(attrib[0]["vegc_traj_gCm2"], ctl["vegc_traj_gCm2"])
            entry["attribution_+4K"] = {
                "rel_with_fixed_rh": real,
                "rel_with_humidity_held": held,
                "share_owed_to_rule2": (float("nan") if real == 0 else float((real - held) / real)),
                "vegc_gCm2": attrib[0]["vegc_traj_gCm2"],
            }

        ladder = [entry["response"][f"+{d:.0f}K"]["vegc_gCm2"] for d in (2.0, 4.0, 6.0)]
        seq = [entry["control_vegc_gCm2"], *ladder]
        diffs = np.diff(seq)
        entry["monotone"] = bool(np.all(diffs > 0) or np.all(diffs < 0))
        entry["observed_direction"] = "up" if seq[-1] > seq[0] else "down"
        entry["matches_expectation"] = (
            EXPECTED[biome] == "unpredicted" or entry["observed_direction"] == EXPECTED[biome]
        )
        out["cells"][biome] = entry
    return out


def main() -> int:
    table = collect()
    verdict = analyse(table)
    out_dir = scratch("runs", "d1")
    table.write_parquet(out_dir / "d1_states.parquet")
    (out_dir / "d1_direction.json").write_text(json.dumps(verdict, indent=2) + "\n", "utf-8")

    print(f"D1 direction test -- {TAIL_YEARS}-year tail mean of the spin-up vegetation carbon")
    print(
        f"basis: 5 cells, 1 patch-set of 25, seed 1; the null is seed {NULL_SEED} at zero "
        f"perturbation; band = max({TOLERANCE_FLOOR:.0%}, that gap)"
    )
    print()
    header = (
        f"{'biome':22s} {'ctl gC/m2':>10s} {'null gap':>9s} "
        f"{'+2K':>9s} {'+4K':>9s} {'+6K':>9s}  {'mono':>5s} {'expect':>11s} {'ok':>4s}"
    )
    print(header)
    print("-" * len(header))
    for biome in CELLS:
        e = verdict["cells"][biome]
        r = e["response"]
        marks = []
        for key in ("+2K", "+4K", "+6K"):
            star = "*" if r[key]["exceeds_band"] else " "
            marks.append(f"{r[key]['rel_vs_control'] * 100:+8.1f}%{star}")
        print(
            f"{biome:22s} {e['control_vegc_gCm2']:10.1f} "
            f"{e['two_seed_gap']['vegc_traj_gCm2'] * 100:8.1f}% "
            f"{' '.join(marks)}  {e['monotone']!s:>5s} {e['expected']:>11s} "
            f"{'yes' if e['matches_expectation'] else 'NO':>4s}"
        )
    print()
    print("* = the change exceeds max(10 %, this cell's own two-seed gap)")
    print()
    print("Roster and structure at +4 K (relative to this cell's own control):")
    cols = [c for c in REPORT if c != "vegc"]
    print(f"{'biome':22s} " + " ".join(f"{c:>13s}" for c in cols))
    for biome in CELLS:
        r = verdict["cells"][biome]["response"]["+4K"]
        print(f"{biome:22s} " + " ".join(f"{r[f'rel_{c}'] * 100:+12.1f}%" for c in cols))
    print()
    print("Window sensitivity -- the same response measured over three tail lengths, and the")
    print("two-seed gap on each. A response that flips with the window is a window artefact.")
    print(f"{'biome':22s} {'window':>7s} {'null':>7s} {'+2K':>8s} {'+4K':>8s} {'+6K':>8s}")
    for biome in CELLS:
        e = verdict["cells"][biome]
        for w in (30, 100, 300):
            cells_row = " ".join(
                f"{e['response'][k][f'rel_tail{w}'] * 100:+7.1f}%" for k in ("+2K", "+4K", "+6K")
            )
            print(
                f"{biome if w == 30 else '':22s} {w:7d} "
                f"{e['two_seed_gap'][f'tail{w}'] * 100:6.1f}% {cells_row}"
            )
    if "attribution_+4K" in verdict["cells"][next(iter(CELLS))]:
        print()
        print("Attribution at +4 K: how much of the response belongs to holding relative")
        print("humidity fixed (PLAN.md rule 2) rather than to temperature itself. The second")
        print("column warms the same +4 K but leaves humidity alone, so relative humidity falls.")
        print(f"{'biome':22s} {'fixed RH':>10s} {'RH falls':>20s} {'share of rule 2':>17s}")
        for biome in CELLS:
            a = verdict["cells"][biome]["attribution_+4K"]
            print(
                f"{biome:22s} {a['rel_with_fixed_rh'] * 100:+9.1f}% "
                f"{a['rel_with_humidity_held'] * 100:+19.1f}% "
                f"{a['share_owed_to_rule2'] * 100:+16.0f}%"
            )
    print()
    print("Spin-up trajectory, mean per 100-year block (control | +4 K), gC/m2:")
    for biome in CELLS:
        e = verdict["cells"][biome]
        print(f"  {biome}")
        print("    ctl  " + " ".join(f"{x:8.0f}" for x in e["control_blocks100"]))
        print("    +4K  " + " ".join(f"{x:8.0f}" for x in e["response"]["+4K"]["blocks100"]))
    print()
    print(f"table:   {out_dir / 'd1_states.parquet'}")
    print(f"verdict: {out_dir / 'd1_direction.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
