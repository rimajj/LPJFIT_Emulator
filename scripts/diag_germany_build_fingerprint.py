#!/usr/bin/env python
"""Does the ssp245 build leave a fingerprint in the Germany 3070 forests? DEV ONLY, no claim.

    scripts/sbatch_py.sh X-diag-germany-build scripts/diag_germany_build_fingerprint.py \\
        --out <scratch.exp>/X-diag-germany-build --workers 64

Read-only over the twelve 3070 restarts. Produces no skill number.

THE QUESTION. The Germany full-state test fails worst on MPI ssp245 (0.289 vs a rerun's 0.510),
and the ssp245 runs are the only ones on the 2026-02-05 build. The whole code difference between
the builds (lpjml56fit fcd3a30..b2e5ca9) is one line in new_tree.c's inheritance branch:

    pft->par=config->pftpar+treelist[index].id;
  + treepar=pft->par->data;

A newborn takes a random parent from the cell's tree list, of ANY type, and becomes the parent's
type. `treepar` is the per-type tree parameters; without the line it still points at the type of
the slot that called new_tree, so the newborn's wood density and D95max are perturbed and then
CLIPPED to the WRONG type's [low, high]. Everything else (sla, emax, k_root, ...) reads pft->par,
which was already updated. So on the old build:
  * a lineage's wood density and D95max can walk outside its own type's range (bounded only by
    the union of the types' ranges), and
  * a type with a wide range (temperate needleleaf, D95max up to 1000) is pulled toward the
    narrower ranges of the types it shares a cell with (500, 300), and vice versa.
On the new build every newborn is clipped to its own type's range, and by 3070 (1056 years after
the 2015 branch from the old-build historical run) essentially every stem is a new-build newborn.

THE FINGERPRINT, per file and tree type: the share of stems whose wood density or D95max lies
outside that type's own range in pft_lpjmlfit.js (unchanged since 2025-11-26), plus each type's
trait quantiles. Predicted: near zero on ssp245, clearly non-zero on ssp126 / ssp370. If that
holds, the two builds sample different trait distributions and ssp245 is not the same model as
the other four climates -- which the state test's training set silently mixed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from germany_corpus import ESMS, SEEDS, SSPS, restart_file

# pft_lpjmlfit.js, the seven tree types in id order (lpjml56fit, unchanged since 8bd29c8).
TREE_TYPES: tuple[str, ...] = ("TrBE", "TeNE", "TeBE", "TeBS", "BoNE", "BoBS", "BoNS")
WOODDENS = np.array(
    [
        (0.7e5, 6.5e5),
        (117000, 418500),
        (145600, 637000),
        (147870, 637000),
        (117000, 418500),
        (147870, 418500),
        (117000, 418500),
    ]
)
D95MAX = np.array(
    [(51, 1800.0), (51, 1000.0), (51, 1000.0), (51, 500.0), (51, 500.0), (51, 500.0), (51, 300.0)]
)
REL = 1e-5  # float32 storage: a value on its bound may read a hair outside it
QS = (1, 10, 50, 90, 99)
NCELL = 9067


def _task(args: tuple[str, str, int, int, int, int]) -> dict[str, Any]:
    from vegemu.binfmt.restart import RestartReader, trees_of  # noqa: PLC0415

    esm, ssp, seed, c0, c1, stride = args
    n = np.zeros(7, np.int64)
    wd_out = np.zeros(7, np.int64)
    d95_out = np.zeros(7, np.int64)
    wd_vals: list[list[np.ndarray]] = [[] for _ in range(7)]
    d95_vals: list[list[np.ndarray]] = [[] for _ in range(7)]
    cells_with_out = 0
    cells_with_trees = 0
    r = RestartReader(restart_file(esm, ssp, seed))
    with r:
        for c in range(c0, c1, stride):
            rec = r.read(c)
            if rec["skip"]:
                continue
            per = [trees_of(p["pftlist"]) for p in rec["stands"][0]["patches"]]
            per = [a for a in per if a.size]
            if not per:
                continue
            cells_with_trees += 1
            s = np.concatenate(per)
            ids = s["id"].astype(np.int64)
            wd = s["wooddens"].astype(np.float64)
            d95 = s["D95max"].astype(np.float64)
            lo_w, hi_w = WOODDENS[ids, 0], WOODDENS[ids, 1]
            hi_d = D95MAX[ids, 1]
            bad_w = (wd < lo_w * (1 - REL)) | (wd > hi_w * (1 + REL))
            bad_d = d95 > hi_d * (1 + REL)
            cells_with_out += int((bad_w | bad_d).any())
            n += np.bincount(ids, minlength=7)
            wd_out += np.bincount(ids[bad_w], minlength=7)
            d95_out += np.bincount(ids[bad_d], minlength=7)
            for t in np.unique(ids):
                m = ids == t
                wd_vals[t].append(wd[m].astype(np.float32))
                d95_vals[t].append(d95[m].astype(np.float32))
    return {
        "key": (esm, ssp, seed),
        "n": n,
        "wd_out": wd_out,
        "d95_out": d95_out,
        "wd": [np.concatenate(v) if v else np.zeros(0, np.float32) for v in wd_vals],
        "d95": [np.concatenate(v) if v else np.zeros(0, np.float32) for v in d95_vals],
        "cells_with_trees": cells_with_trees,
        "cells_with_out": cells_with_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--stride", type=int, default=1, help="every k-th cell (1 = all)")
    ap.add_argument("--chunk", type=int, default=256)
    ap.add_argument("--ncell", type=int, default=NCELL, help="first n cells only (smoke test)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    tasks = [
        (e, s, sd, c0, min(c0 + a.chunk, a.ncell), a.stride)
        for e in ESMS
        for s in SSPS
        for sd in SEEDS
        for c0 in range(0, a.ncell, a.chunk)
    ]
    acc: dict[tuple[str, str, int], dict[str, Any]] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, part in enumerate(ex.map(_task, tasks), 1):
            k = part.pop("key")
            if k not in acc:
                acc[k] = part
                continue
            g = acc[k]
            for f in ("n", "wd_out", "d95_out", "cells_with_trees", "cells_with_out"):
                g[f] = g[f] + part[f]
            for f in ("wd", "d95"):
                g[f] = [np.concatenate([x, y]) for x, y in zip(g[f], part[f], strict=True)]
            if i % 50 == 0:
                print(f"  {i}/{len(tasks)} chunks, {time.time() - t0:.0f} s", flush=True)

    rows: list[dict[str, Any]] = []
    for (esm, ssp, seed), g in sorted(acc.items()):
        for t in range(7):
            if not g["n"][t]:
                continue
            row: dict[str, Any] = {
                "esm": esm,
                "ssp": ssp,
                "seed": seed,
                "build": "2026-02-05" if ssp == "ssp245" else "2025-12-17",
                "type": TREE_TYPES[t],
                "stems": int(g["n"][t]),
                "share_stems": float(g["n"][t] / g["n"].sum()),
                "wooddens_outside_own_range": float(g["wd_out"][t] / g["n"][t]),
                "D95max_above_own_high": float(g["d95_out"][t] / g["n"][t]),
            }
            for q, v in zip(QS, np.percentile(g["wd"][t], QS), strict=True):
                row[f"wooddens_p{q}"] = float(v)
            for q, v in zip(QS, np.percentile(g["d95"][t], QS), strict=True):
                row[f"D95max_p{q}"] = float(v)
            rows.append(row)
        print(
            f"{esm:14s} {ssp} s{seed}: {g['cells_with_out']}/{g['cells_with_trees']} tree cells "
            f"hold a stem outside its own type's range; stems out (wd, d95) = "
            f"{g['wd_out'].sum() / g['n'].sum():.4f}, {g['d95_out'].sum() / g['n'].sum():.4f}",
            flush=True,
        )
    summary = {
        "rows": rows,
        "per_file": {
            f"{e}/{s}/{sd}": {
                "stems": int(g["n"].sum()),
                "cells_with_trees": int(g["cells_with_trees"]),
                "cells_with_out_of_range_stem": int(g["cells_with_out"]),
                "wooddens_outside": float(g["wd_out"].sum() / g["n"].sum()),
                "D95max_above": float(g["d95_out"].sum() / g["n"].sum()),
            }
            for (e, s, sd), g in sorted(acc.items())
        },
        "stride": a.stride,
        "ncell": a.ncell,
        "seconds": time.time() - t0,
    }
    (a.out / "fingerprint.json").write_text(json.dumps(summary, indent=2))
    try:
        import polars as pl  # noqa: PLC0415

        pl.DataFrame(rows).write_csv(a.out / "fingerprint_by_type.csv")
    except ImportError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
