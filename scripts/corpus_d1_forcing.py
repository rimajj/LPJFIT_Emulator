#!/usr/bin/env python
"""D1: generate the perturbed forcing sets and spin-up configs for the direction test.

    scripts/sbatch_py.sh D-d1-forcing scripts/corpus_d1_forcing.py

WHAT THIS BUILDS, and why in this shape.

D1 asks one engineering question -- does the model read a perturbed `.clm` without complaint -- and
one physical question: does the state move in the expected direction. A single warm run answers
neither convincingly, so the design is a **paired temperature ladder with its own noise null**:

  * five cells, one per biome, each spun up under dtemp = 0, +2, +4, +6 K at unchanged
    precipitation. Four points make a CURVE, and a monotone curve is far harder to get by accident
    than a single displaced point.
  * the same five cells run a SECOND time at dtemp = 0 with a different random seed. That is the
    null: it is how far apart two runs land when only the model's own stochasticity differs. A
    warming response smaller than that gap is not a response (invariant 1 -- no claim without its
    null; invariant 5 -- the tolerance is max(10 %, the model's own two-seed spread)).

The pairing is what makes five cells enough here. Control and warmed share the cell, the config,
the forcing window and the random seed, so the shuffle order of the spin-up years and every
stochastic draw are the same sequence in both arms; the ONLY difference is the climate. This is a
direction test on a paired difference, not a five-cell fidelity claim -- a five-cell result is
never fidelity evidence (`MEMORY.md:acceptance`).

The warming points are real points of the pilot design (`vegemu.corpus.perturb.pilot_design`), not
ad-hoc numbers, so D1 exercises the machinery D2 will run 6,000 times.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.corpus.perturb import Perturbation, design_by_name
from vegemu.paths import paths, scratch

REPO = Path(__file__).resolve().parent.parent

# One cell per biome. Boreal and tropical are expected to move in OPPOSITE directions under
# warming, which is a far stronger test than five cells that should all move the same way.
CELLS: dict[str, int] = {
    "boreal_siberia": 52059,
    "temperate_hainich": 42490,
    "mediterranean_iberia": 33335,
    "semiarid_sahel": 18371,
    "tropical_amazon": 12045,
}

# The temperature ladder, as named points of the pilot design. `control` is the neutral point.
LADDER: tuple[str, ...] = ("control", "core_t+2_p10", "core_t+4_p10", "core_t+6_p10")
# The two-seed null: the same neutral forcing, a different random seed.
NULL_SEED = 2
SMOKE_NSPINUP = 30

# ⚠ THE ATTRIBUTION ARM, and the only place in this repo that breaks `PLAN.md` rule 2 on purpose.
# Holding relative humidity fixed makes vapour-pressure deficit rise steeply with temperature, and
# LPJmL-FIT's tree water stress reads that deficit directly (`waterstress_tree.c:36`). So a large
# response to warming could be the model's physics OR could be our humidity rule, and the two are
# not separable from the real arm alone. This arm warms by the same +4 K while leaving specific
# humidity untouched -- relative humidity falls instead. The DIFFERENCE between the two arms is how
# much of the response the rule owns. These runs are diagnostics and never corpus rows.
NOFIXRH = "_nofixrh"
ATTRIBUTION_POINT = "core_t+4_p10"


def forcing_dir(cell: int, point: str) -> Path:
    return scratch("forcing", "d1", f"c{cell}", point)


def run_dir(cell: int, point: str, seed: int) -> Path:
    return scratch("runs", "d1", f"c{cell}-{point}-s{seed}")


def _build_forcing(cell: int, point: str) -> dict[str, object]:
    # ⚠ The `sys.modules` registration is load-bearing: annotations here are strings (the
    # `__future__` import), and `@dataclass` resolves them through `sys.modules[cls.__module__]`,
    # which is `None` for a module loaded by path and never registered. Without it the script
    # raises an `AttributeError` inside `dataclasses.py` the moment it defines a dataclass.
    name = "corpus_perturb_clm"
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    if point.endswith(NOFIXRH):
        base: Perturbation = design_by_name(point[: -len(NOFIXRH)])
        pert = replace(base, name=point, hold_huss_diagnostic=True)
    else:
        pert = design_by_name(point)
    out = forcing_dir(cell, point)
    record = mod.build(range(cell, cell + 1), pert, out)
    return {"point": point, "dir": str(out), "diagnostics": record["diagnostics"]}


def _build_config(cell: int, point: str, seed: int, nspinup: int, tag: str) -> Path:
    rd = run_dir(cell, point, seed) if nspinup == 1000 else scratch("runs", "d1-smoke", tag)
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "corpus_spinup_config.py"),
        "--cell", str(cell),
        "--forcing", str(forcing_dir(cell, point)),
        "--run-dir", str(rd),
        "--tag", tag,
        "--seed", str(seed),
        "--nspinup", str(nspinup),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return rd / f"lpjml_spinup_{tag}.js"


def main() -> int:
    manifest: list[dict[str, str]] = []
    forcing: list[dict[str, object]] = []

    for biome, cell in CELLS.items():
        for point in LADDER:
            forcing.append({"cell": cell, "biome": biome, **_build_forcing(cell, point)})
            tag = f"c{cell}-{point}-s1"
            cfg = _build_config(cell, point, 1, 1000, tag)
            manifest.append(
                {"name": tag, "config": str(cfg), "run_dir": str(run_dir(cell, point, 1))}
            )
        # the noise null: neutral forcing, second seed
        tag = f"c{cell}-control-s{NULL_SEED}"
        cfg = _build_config(cell, "control", NULL_SEED, 1000, tag)
        manifest.append(
            {"name": tag, "config": str(cfg), "run_dir": str(run_dir(cell, "control", NULL_SEED))}
        )

    # The attribution arm: +4 K with humidity left alone, so relative humidity falls.
    attrib: list[dict[str, str]] = []
    for biome, cell in CELLS.items():
        point = ATTRIBUTION_POINT + NOFIXRH
        forcing.append({"cell": cell, "biome": biome, **_build_forcing(cell, point)})
        tag = f"c{cell}-{point}-s1"
        cfg = _build_config(cell, point, 1, 1000, tag)
        attrib.append({"name": tag, "config": str(cfg), "run_dir": str(run_dir(cell, point, 1))})

    # A two-run smoke manifest at 30 model years: it proves the model READS the perturbed file and
    # that the batch runner works, in about fifteen seconds, before 25 spin-ups are committed.
    smoke: list[dict[str, str]] = []
    for point in ("control", "core_t+4_p10"):
        cell = CELLS["temperate_hainich"]
        tag = f"smoke-c{cell}-{point}"
        cfg = _build_config(cell, point, 1, SMOKE_NSPINUP, tag)
        smoke.append({"name": tag, "config": str(cfg), "run_dir": str(cfg.parent)})

    out = scratch("runs", "d1")
    _write_manifest(out / "manifest.tsv", manifest)
    _write_manifest(out / "manifest_smoke.tsv", smoke)
    _write_manifest(out / "manifest_nofixrh.tsv", attrib)
    (out / "forcing_index.json").write_text(
        json.dumps(
            {
                "cells": CELLS,
                "ladder": list(LADDER),
                "null_seed": NULL_SEED,
                "base_window": [1970, 1999],
                "inputs_root": str(paths()["inputs"]["inpath"]),
                "forcing": forcing,
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )

    print(f"{len(manifest)} spin-up runs, {len(attrib)} attribution runs, {len(smoke)} smoke runs")
    print(f"manifest:         {out / 'manifest.tsv'}")
    print(f"manifest_nofixrh: {out / 'manifest_nofixrh.tsv'}  (rule 2 disabled; diagnostics only)")
    print(f"manifest_smoke:   {out / 'manifest_smoke.tsv'}")
    for item in forcing:
        diag = item["diagnostics"]  # type: ignore[index]
        tas = diag["tas_ann_c"]  # type: ignore[index]
        pr = diag["pr_ann_mm"]  # type: ignore[index]
        print(
            f"  {item['biome']:22s} {item['point']:14s} "
            f"tas {tas[0]:7.2f} -> {tas[1]:7.2f} C   pr {pr[0]:8.1f} -> {pr[1]:8.1f} mm"
        )
    return 0


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(
        "".join(f"{r['name']}\t{r['config']}\t{r['run_dir']}\n" for r in rows), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
