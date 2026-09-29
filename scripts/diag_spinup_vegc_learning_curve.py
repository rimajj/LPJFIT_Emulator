#!/usr/bin/env python
"""Is the spin-up vegetation-carbon map still DATA-LIMITED? A learning curve. DEV ONLY, NOT A CLAIM.

    NCPUS=64 PARTITION=priority TIME=06:00:00 scripts/sbatch_py.sh T-vegc-lcurve \\
        scripts/diag_spinup_vegc_learning_curve.py \\
        --screen <scratch.exp>/T-screen-spinup-vegc-r2/screen.json \\
        --out <scratch.exp>/T-vegc-learning-curve

WHY. The best recipe the dev screen found (`screen_spinup_vegc.py`, round 2) lands inside the band
in 62 % of the dev cells where a rerun lands in 85 %; closing that gap needs each cell's error cut
to about 0.4 of what it is (a residual-shrink check on the saved predictions, 2026-09-29). Two
very different remedies are on the table -- more training data (the owner has said more will come
"when that works") or a different model -- and they are told apart by one curve: how the dev
score moves as the TRAINING set shrinks. A curve still climbing steeply at the full set says data;
a flat one says the recipe.

WHAT IT FITS. The screen's round-2 best recipe, read from its `screen.json`, with two changes that
are the point: the pool is the stored spin-up only (so the training size is one number), and one
bag (five bags cost 5x for about +0.01). The full-size point of THIS recipe is the anchor, not the
screen's number. Training rows are thinned two ways, each at fractions 1/16 .. 1:
  * "tiles": drop whole 15-degree tiles -- fewer climates covered (what new places would add);
  * "cells": drop random cells inside every tile -- the same coverage, sparser.
Two draws per fraction below 1. A dropped cell only leaves the TRAINING rows (its target is set
to NaN, which `training_rows` already excludes); the scored set, the band and the rerun reference
are the sealed code's, untouched.

⚠ DEV FOLDS 0-2 ONLY. Folds 3-4 are what a sealed confirmation scores; they are not fitted,
predicted or printed here. ⚠ The tuned settings were chosen on these dev folds at full size, so
every point is mildly optimistic and the small-N points most of all -- the SLOPE is the reading.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from exp_spinup_vegc import score
from screen_spinup_vegc import DEV_FOLDS, Data, load, predict_all, recipe_of, subset
from vegemu.paths import paths

FRACTIONS: tuple[float, ...] = (1 / 16, 1 / 8, 1 / 4, 1 / 2, 1.0)
DRAWS = 2


def thinned(d: Data, target: str, mode: str, frac: float, draw: int) -> tuple[Data, int]:
    """`d` with the training target NaN outside a `frac` sample of cells (by tile or by cell)."""
    y = d.yg[target].copy()
    finite = np.isfinite(y).all(axis=1) if y.ndim == 2 else np.isfinite(y)
    if frac < 1.0:
        rng = np.random.default_rng(
            10_000 * draw + round(1000 * frac) + (0 if mode == "tiles" else 7)
        )
        if mode == "tiles":
            tiles = np.unique(d.tiles_g[finite])
            keep_t = rng.choice(tiles, size=max(1, round(frac * tiles.size)), replace=False)
            keep = np.isin(d.tiles_g, keep_t)
        else:
            keep = rng.random(y.shape[0]) < frac
        y[~keep] = np.nan
    n = int((np.isfinite(y).all(axis=1) if y.ndim == 2 else np.isfinite(y)).sum())
    return dataclasses.replace(d, yg={**d.yg, target: y}), n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--screen", required=True, help="the round-2 screen.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=20, help="LightGBM threads per fold fit")
    ap.add_argument("--quick", action="store_true", help="plumbing smoke: 1/16 and 1, one draw")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    exp = Path(str(paths()["scratch"]["exp"]))

    spec = json.loads(Path(args.screen).read_text())["best"]["recipe"]
    r = dataclasses.replace(recipe_of(spec), name="lcurve", pool="spinup", bag=1)
    if args.quick:
        r = dataclasses.replace(
            r, params=tuple((k, 60 if k == "n_estimators" else v) for k, v in r.params)
        )
    d = load(exp / "T-features-v3x", exp / "T-features-v3p")
    mask = d.sc["mask"].astype(bool)
    fold = np.asarray(d.sc["fold"])
    dev = np.isin(fold, DEV_FOLDS)
    sub = subset(d.sc, dev)
    tm = np.asarray(sub["tm"])
    print(f"recipe: {json.dumps(dataclasses.asdict(r), default=str)}", flush=True)
    print(
        f"dev scored cells {int(dev.sum())}; rerun frac there {sub['frac_rerun']:.4f}", flush=True
    )

    fracs = (1 / 16, 1.0) if args.quick else FRACTIONS
    rows: list[dict[str, Any]] = []
    for mode in ("tiles", "cells"):
        for frac in fracs:
            for draw in range(1 if frac == 1.0 or args.quick else DRAWS):
                if frac == 1.0 and mode == "cells":
                    continue  # the same fit as tiles at 1
                t0 = time.time()
                dd, n = thinned(d, r.target, mode, frac, draw)
                pred, info = predict_all(dd, r, DEV_FOLDS, len(DEV_FOLDS), args.threads)
                p = pred[mask][dev]
                s = score(p, sub)
                ok = tm > 0
                err = np.abs(np.log(np.maximum(p[ok], 1e-9)) - np.log(tm[ok]))
                row = {
                    "mode": mode,
                    "frac": frac,
                    "draw": draw,
                    "train_cells_total": n,
                    "rows_fold0": info["0"]["rows"],
                    "dev_D": s["D"],
                    "dev_frac": s["frac"],
                    "skill_log1p": s["skill_log1p"],
                    "median_abs_log_err": float(np.median(err)),
                    "seconds": time.time() - t0,
                }
                rows.append(row)
                print(
                    f"  {mode:5s} {frac:6.4f} draw {draw}: cells {n:6d} "
                    f"rows(f0) {row['rows_fold0']:6d}  dev D {s['D']:+.4f} frac {s['frac']:.4f} "
                    f"med|logerr| {row['median_abs_log_err']:.4f}  ({row['seconds']:.0f} s)",
                    flush=True,
                )
                (out / "learning_curve.json").write_text(
                    json.dumps(
                        {"recipe": dataclasses.asdict(r), "rows": rows}, indent=2, default=str
                    )
                )
    # The slope: log(median error) against log(training cells), per mode, over fractions >= 1/8.
    fits: dict[str, float] = {}
    for mode in ("tiles", "cells"):
        pts = [
            (x["train_cells_total"], x["median_abs_log_err"])
            for x in rows
            if (x["mode"] == mode or x["frac"] == 1.0) and x["frac"] >= 1 / 8
        ]
        if len(pts) >= 3:
            a = np.log(np.array(pts, dtype=np.float64))
            fits[mode] = float(np.polyfit(a[:, 0], a[:, 1], 1)[0])
    print(f"slope of log median error vs log training cells (>= 1/8): {fits}", flush=True)
    (out / "learning_curve.json").write_text(
        json.dumps(
            {"recipe": dataclasses.asdict(r), "rows": rows, "slopes": fits}, indent=2, default=str
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
