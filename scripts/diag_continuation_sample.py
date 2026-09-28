#!/usr/bin/env python
"""DEV DIAGNOSTIC, NO CLAIM: a continuation SAMPLE scored like the same-window test, on its cells.

    scripts/diag_continuation_sample.py --out <dir> --arm <label>=<root>/<arm> [--arm ...]
        [--every 20]

A sample continuation (`spinup_continuation.py build --every N`) runs only every N-th member, so
`harvest` refuses it and the sealed scorer cannot read it. This reads each arm's sampled members'
own VegC (the model's line must be in the log), forms the same windows (years 1-10, 21-30, year 1),
and scores them with the sealed test's code (`exp_continuation_window._setup` / `score`: the
stored truth, the sealed band, the real-run reference of the same window length) on the scored
cells those members cover -- folds 3-4 and all. Also the summed VegC by year over those cells.
Numbers here are about 5 % of the cells and are never a verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_continuation_window import WINDOWS, _setup, _with_reference
from exp_spinup_vegc import score
from spinup_continuation import NCELL, NYEAR, _member_vegc
from vegemu.binfmt.clm import read_grid
from vegemu.paths import path

DONE = re.compile(r"^lpjml successfully terminated", re.MULTILINE)
SPANS = {"y01_10": (1, 10), "y21_30": (21, 30), "y01": (1, 1)}


def load_arm(arm_dir: Path, every: int) -> tuple[np.ndarray, int]:
    plan = json.loads((arm_dir.parent / "members.json").read_text())
    coords = read_grid(path("inputs.coord"))
    vegc = np.full((NYEAR, NCELL), np.nan, dtype=np.float64)
    done = 0
    for m in plan["members"]:
        if m["k"] % every:
            continue
        rdir = arm_dir / m["name"]
        log = rdir / f"lpjml.{arm_dir.name}-{m['name']}.log"
        if not (log.exists() and DONE.search(log.read_text(errors="replace"))):
            raise RuntimeError(f"{rdir}: no completion line")
        cells = np.arange(m["first"], m["last"] + 1)
        block, years = _member_vegc(rdir, cells, coords)
        assert years == NYEAR, (rdir, years)
        vegc[:, cells] = block
        done += 1
    return vegc, done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arm", action="append", required=True, help="label=<root>/<arm>")
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument(
        "--static",
        action="append",
        default=[],
        help="label=<synth_global cells.parquet>: the file's own year-0 VegC (rep_vegc_written), "
        "scored on the cells the first --arm covers against the 1-year reference",
    )
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    sc, held, refs, info = _setup()
    mask = sc["mask"].astype(bool)
    out: dict[str, Any] = {"reference_all_cells": info["reference"]}
    for spec in a.arm:
        label, d = spec.split("=", 1)
        vegc, done = load_arm(Path(d), a.every)
        covered = np.isfinite(vegc[0])[mask]
        row: dict[str, Any] = {
            "members": done,
            "scored_cells": int(covered.sum()),
            "scored_cells_folds_3_4": int((covered & held).sum()),
        }
        for name, (lo, hi) in SPANS.items():
            x = np.nanmean(vegc[lo - 1 : hi], axis=0)[mask] if lo < hi else vegc[lo - 1][mask]
            length = WINDOWS[name]
            for sel_name, sel in (("folds_3_4", covered & held), ("all", covered)):
                s = score(x[sel], _with_reference(sc, sel, refs[length]))
                row[f"{name}_{sel_name}"] = {k: s[k] for k in ("frac", "frac_rerun", "D") if k in s}
        tot = np.nansum(vegc[:, np.flatnonzero(mask)[covered]], axis=1)
        row["vegc_sum_by_year"] = tot.tolist()
        row["y5_change"] = float(tot[4] / tot[3] - 1.0)
        out[label] = row
        print(
            label, json.dumps({k: v for k, v in row.items() if k != "vegc_sum_by_year"}), flush=True
        )
    first = load_arm(Path(a.arm[0].split("=", 1)[1]), a.every)[0]
    covered = np.isfinite(first[0])[mask]
    for spec in a.static:
        label, f = spec.split("=", 1)
        cells = pl.read_parquet(f).filter(pl.col("status") == "synthesised")
        full = np.full(NCELL, np.nan)
        full[cells["cell"].to_numpy()] = cells["rep_vegc_written"].to_numpy()
        x = full[mask]
        row = {}
        for sel_name, base in (("folds_3_4", covered & held), ("all", covered)):
            sel = base & np.isfinite(x)
            s = score(x[sel], _with_reference(sc, sel, refs[1]))
            row[f"y00_{sel_name}"] = {"cells": int(sel.sum()), "frac": s["frac"], "D": s["D"]}
        out[label] = row
        print(label, json.dumps(row), flush=True)
    (a.out / "sample_scores.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
