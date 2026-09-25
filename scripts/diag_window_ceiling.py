#!/usr/bin/env python
"""DEV DIAGNOSTIC, NO CLAIM: how often does an L-year mean of a REAL run land in the band?

    scripts/diag_window_ceiling.py --out <dir> --members <root>/members.json [--sample-every 20]

The continuation test (X-20260925-spinup-restart-continuation) scores a 10-year mean of ONE run
against the stored truth, a 250-year mean (model years 1450-1699), and reads it against a rerun's
0.858711 -- which compares one 250-year mean with another. A 10-year mean carries far more of the
model's year-to-year noise, so that is not the attainable value for a 10-year window. This measures
it on the stored run itself: for each seed k and every non-overlapping L-year window inside
1450-1699, the window mean X_k is scored against the OTHER seed's truth T_(3-k) with the sealed
band w (`exp_spinup_vegc.scored_set`), and the per-cell score is averaged over both seeds and all
windows. L = 250 is exactly the rerun (a check). Reported on all scored cells, on folds 3-4, and on
the 51-member continuation sample's cells (every 20th member).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_convergence import cell_index_map, read_trajectory
from exp_spinup_vegc import _inputs, _passes, global_folds, scored_set
from vegemu.paths import path

FIRST_MODEL_YEAR = 1000
LO, HI = 1450, 1699  # the truth window (inclusive)
LENGTHS = (1, 5, 10, 20, 30, 50, 125, 250)
NCELL = 67420


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--members", required=True, help="a continuation root's members.json")
    ap.add_argument("--sample-every", type=int, default=20)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    inp = _inputs()
    sc = scored_set(inp)
    mask = sc["mask"].astype(bool)
    folds = global_folds(inp["lon_p"], inp["lat_p"], inp["lon_g"], inp["lat_g"])[mask]  # type: ignore[arg-type]
    members = json.loads(Path(args.members).read_text())["members"]
    sample_cells = np.array(
        [
            c
            for m in members
            if m["k"] % args.sample_every == 0
            for c in range(m["first"], m["last"] + 1)
        ]
    )
    in_sample = np.isin(np.flatnonzero(mask), sample_cells)
    subsets = {
        "all": np.ones(int(mask.sum()), bool),
        "folds_3_4": np.isin(folds, [3, 4]),
        "sample": in_sample,
    }

    lat_i, lon_i = cell_index_map(path("ground_truth.grid_nc"), ncell=NCELL)
    key = "ground_truth.spinup_trajectory_seed"
    traj = [read_trajectory(path(f"{key}{k}"), lat_i, lon_i)[:, mask] for k in (1, 2)]
    t = (sc["t1"], sc["t2"])
    w = sc["w"]
    a, b = LO - FIRST_MODEL_YEAR, HI - FIRST_MODEL_YEAR + 1
    # The check that this reads the same numbers the truth was built from.
    for k in (0, 1):
        got = traj[k][a:b].astype(np.float64).mean(axis=0)
        err = float(np.nanmax(np.abs(got - t[k]) / np.maximum(np.abs(t[k]), 1.0)))
        assert err < 1e-5, f"seed {k + 1}: trajectory 1450-1699 mean differs from truth by {err}"

    report: dict[str, object] = {"frac_rerun": sc["frac_rerun"], "lengths": {}}
    for L in LENGTHS:
        starts = list(range(a, b - L + 1, L))
        cell = np.zeros(int(mask.sum()))
        for s0 in starts:
            for k in (0, 1):
                x = traj[k][s0 : s0 + L].astype(np.float64).mean(axis=0)
                cell += _passes(x, t[1 - k], w)
        cell /= 2 * len(starts)
        row = {name: float(cell[m].mean()) for name, m in subsets.items()}
        row["windows"] = len(starts)
        report["lengths"][str(L)] = row  # type: ignore[index]
        print(
            f"L={L:4d} windows {len(starts):3d}  " + "  ".join(f"{n} {row[n]:.3f}" for n in subsets)
        )
    report["n"] = {n: int(m.sum()) for n, m in subsets.items()}
    (out / "window_ceiling.json").write_text(json.dumps(report, indent=2))
    print(f"wrote {out / 'window_ceiling.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
