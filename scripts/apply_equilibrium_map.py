#!/usr/bin/env python
"""Apply a SAVED equilibrium map to any 30-year climate, without refitting anything.

    NCPUS=8 TIME=01:00:00 scripts/sbatch_py.sh T-eqm-apply-<name> \\
        scripts/apply_equilibrium_map.py --map <scratch.models>/equimap-v1 --held-out \\
        --window historical:1901:1930 --threads 8 \\
        --climate-out <dir>/climate_historical_1901_1930.parquet --out <dir>/pred_1901_1930.parquet

    ... --climate-table <scratch.corpus>/v0/climate_ssp126.parquet --out <dir>/pred_ssp126.parquet

WHY IT EXISTS. `fit_equilibrium_map.py` is the only other way to a prediction, and it refits every
model, overwrites the map of record, and knows only the three v0 legs. This reads the saved map,
builds or reads a climate table, joins the soil, and predicts.

THE CLIMATE. `--window LEG:FIRST:LAST` computes the 86 features with `vegemu.corpus.climate.
climate_table` -- the function every corpus table and every pilot run's features came from -- over
that leg's forcing files in config/paths.yaml, for every land cell; `--climate-out` keeps the
table. `--climate-table` reads one already built. Either way the soil is joined by the same adapter
the map was trained through (`fit_equilibrium_map.with_soil`).

--held-out. Without it every row comes from the final map, fitted on all 200 pilot cells, whose
15-degree tiles cover every tree-bearing land cell: those predictions are not held out anywhere in
the forest and must not be scored as if they were. With it each row comes from the fold map that
never saw its tile (`HeldOutMaps`), the setting the sealed 0.607582 was measured in.

WRITES --out with the columns of `fit_equilibrium_map.prediction_frame`, and `<out>.json` beside it:
the map's and the climate's provenance, the rows each map made, and what post-processing changed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import polars as pl

from fit_equilibrium_map import _git, _sha256, prediction_frame, with_soil
from vegemu.corpus.climate import Window, climate_table
from vegemu.corpus.climate import basis as climate_basis
from vegemu.models.equilibrium import EquilibriumMap, HeldOutMaps
from vegemu.paths import paths


def parse_window(spec: str) -> Window:
    """`LEG:FIRST:LAST`, e.g. `historical:1901:1930`; the state year is the window's last year."""
    leg, first, last = spec.split(":")
    window = Window(leg, int(first), int(last), int(last))
    if window.nyear != 30:
        raise ValueError(f"{spec}: the map was trained on 30-year windows, not {window.nyear}")
    return window


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--map", required=True, help="a saved map directory, e.g. equimap-v1")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--window", help="LEG:FIRST:LAST, computed from that leg's forcing")
    src.add_argument("--climate-table", help="a climate table with the 86 features and soildepth")
    ap.add_argument("--climate-out", help="with --window: also write the computed climate table")
    ap.add_argument("--held-out", action="store_true", help="predict with the per-fold maps")
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=1, help="prediction threads (cannot change it)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing --out")
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists; pass --force to replace it")
    if args.climate_out and not args.window:
        ap.error("--climate-out needs --window")
    map_dir = Path(args.map)
    held = HeldOutMaps.load(map_dir) if args.held_out else None
    final = held.final if held is not None else EquilibriumMap.load(map_dir)
    for m in (final, *(held.folds.values() if held is not None else ())):
        m.predict_threads = args.threads

    climate: dict[str, Any]
    if args.window:
        window = parse_window(args.window)
        clim = climate_table(window)
        climate = {"window": window.describe(), "basis": climate_basis(window)}
        if args.climate_out:
            Path(args.climate_out).parent.mkdir(parents=True, exist_ok=True)
            clim.write_parquet(args.climate_out)
            climate |= {"table": args.climate_out, "sha256": _sha256(Path(args.climate_out))}
    else:
        clim = pl.read_parquet(args.climate_table)
        climate = {"table": args.climate_table, "sha256": _sha256(Path(args.climate_table))}
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    frame, info = prediction_frame(with_soil(clim.sort("cell"), soil_bin), final, held)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(out)

    folds_json = map_dir / "folds" / "folds.json"
    sidecar = {
        "map": str(map_dir),
        "final_manifest_sha256": _sha256(map_dir / "manifest.json"),
        "folds_json_sha256": _sha256(folds_json) if held is not None else None,
        "climate": climate,
        "soil": str(soil_bin),
        **info,
        "out": str(out),
        "out_sha256": _sha256(out),
        "code_commit": _git("rev-parse", "HEAD"),
        "code_dirty": bool(
            _git("status", "--porcelain", "--untracked-files=no", "--", "src", "scripts", "config")
        ),
        "seconds": time.time() - t0,
    }
    Path(f"{out}.json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(
        f"wrote {out}: {frame.height} cells, held out {held is not None}, rows by map "
        f"{info['rows_by_fold']}, treeless {info['predicted_treeless_share']:.3f}, "
        f"{sidecar['seconds']:.0f} s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
