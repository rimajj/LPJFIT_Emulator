#!/usr/bin/env python
"""DEV DIAGNOSTIC, NO CLAIM: is a placed stand's year-5 die-off a within-patch LIGHT defect?

    scripts/diag_patch_light.py --out <dir> [--probe <runs>/contdiag-counter]
        [--emulated <restart_1699_emulated.lpj>] [--pilot-runs <runs>/pilot-v2-constco2]

WHY. The carbon-matched emulated restart loses ~10 % of its vegetation carbon in continuation
year 5, and the stems killed are mid-canopy (height rank 40-80 %), whatever their count, size or
inherited bad-years counter (journal/X/2026-09b.md, 2026-09-25 night). LPJmL-FIT kills a tree
after five straight years of negative biomass increment (`mortality_tree_ind.c:135`), and a
tree's increment is set by the light it gets, which is computed PER PATCH in 2-m height layers
(`getfpar.c`). The synthesiser draws ranks across the cell and deals stems to patches AT RANDOM
(`models/synth.py`), so each of the 25 patches is a random sample of the stand; a real stand's
patches are independent gap-dynamics replicates at different stages. A stem that was a canopy tree
in a young donor patch lands under tall trees in every placed patch.

WHAT THIS MEASURES, from files already on disk (no model run):
  A. per-patch heterogeneity per cell (CV across the 25 patches of tree leaf area and of the
     tallest stem) -- real constant-CO2 pilot stands, restart_1999, the emulated file;
  B. each stem's leaf-on absorbed light share, recomputed with getfpar.c's own layer algorithm,
     per unit of its own leaf carbon ("light per leaf"), by cell height-rank bin, per file;
  C. in the 4-year probe (contdiag-counter), each year-0 stem matched to year 4 by (patch, type,
     index): the share doomed (counter >= 4 at year 4, i.e. killed in year 5) or already dead, by
     light-per-leaf quintile within each height-rank bin, for the emulated file and restart_1999.

Light is leaf-on and ignores snow and phenology (the C's `fpar_leafon`); the grass layer sits
below every tree and does not shade one. Crown length 0.3334 for every tree type
(par/pft_lpjmlfit.js), VSTEP 2 m and the 40 cap on leaf area per crown metre as in getfpar.c.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from vegemu.binfmt.restart import RestartReader, trees_of
from vegemu.paths import path

VSTEP = 2.0
CROWNLENGTH = 0.3334
K_LAMBERT = 0.5
ATOH_MAX = 40.0
RANK_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001)
PROBE_MEMBERS = ("m0000", "m0200", "m0400", "m0600", "m0800")

Array = npt.NDArray[np.float64]


def patch_fpar(height: Array, leaf_c: Array, sla: Array, nind: Array) -> Array:
    """Leaf-on absorbed PAR fraction per tree of one patch, exactly as getfpar.c's layer loop."""
    n = height.size
    fpar = np.zeros(n)
    if n == 0:
        return fpar
    bole = (1.0 - CROWNLENGTH) * height
    depth = height - bole
    ok = depth > 1e-9
    atoh = np.where(ok, np.minimum(leaf_c * sla / np.where(ok, depth, 1.0), ATOH_MAX), 0.0)
    top = int(height.max() / VSTEP - 1e-9)
    plai = 0.0
    bottom = 1.0
    for layer in range(top, -1, -1):
        lo, hi = layer * VSTEP, layer * VSTEP + VSTEP
        inl = ok & (height > lo) & (bole < hi)
        frac = np.ones(n)
        frac -= np.where(height < hi, (hi - height) / VSTEP, 0.0)
        frac -= np.where(bole > lo, (bole - lo) / VSTEP, 0.0)
        lai = np.where(inl, atoh * frac * VSTEP * nind, 0.0)
        layer_lai = float(lai.sum())
        plai += layer_lai
        top_f, bottom = bottom, float(np.exp(-K_LAMBERT * plai))
        if layer_lai > 1e-9:
            fpar += (top_f - bottom) * lai / layer_lai
    return fpar


def cell_stems(rec: dict[str, Any]) -> dict[str, Array] | None:
    """Every stem of a cell's natural stand with its patch, light and cell height rank."""
    if rec.get("skip") or not rec.get("stands"):
        return None
    cols: dict[str, list[Array]] = {
        k: []
        for k in ("patch", "id", "index", "height", "leaf_c", "nind", "fpar", "counter", "vegc")
    }
    for st in rec["stands"]:
        for p, patch in enumerate(st["patches"]):
            t = trees_of(patch["pftlist"])
            if t.size == 0:
                continue
            h = t["height"].astype(float)
            lc = t["ind_leaf_c"].astype(float)
            fp = patch_fpar(h, lc, t["sla"].astype(float), t["nind"].astype(float))
            vegc = sum(
                t[f"ind_{part}_c"].astype(float)
                for part in ("leaf", "sapwood", "heartwood", "root", "sapwood_bg", "heartwood_bg")
            )
            vegc = vegc - t["ind_debt_c"].astype(float)
            for k, v in (
                ("patch", np.full(t.size, p)),
                ("id", t["id"]),
                ("index", t["index"]),
                ("height", h),
                ("leaf_c", lc),
                ("nind", t["nind"]),
                ("fpar", fp),
                ("counter", t["bm_inc_counter"]),
                ("vegc", vegc * t["nind"]),
            ):
                cols[k].append(np.asarray(v, dtype=float))
    if not cols["height"]:
        return None
    out = {k: np.concatenate(v) for k, v in cols.items()}
    order = np.argsort(np.argsort(out["height"], kind="stable"), kind="stable")
    out["rank"] = (order + 0.5) / order.size
    out["lpl"] = out["fpar"] / np.maximum(out["leaf_c"] * out["nind"], 1e-12)
    return out


def heterogeneity(s: dict[str, Array], npatch: int = 25) -> tuple[float, float, float]:
    """CV across patches of tree leaf area, of the tallest stem, and of the stem count."""
    lai = np.zeros(npatch)
    hmax = np.zeros(npatch)
    cnt = np.zeros(npatch)
    p = s["patch"].astype(int)
    np.add.at(lai, p, s["leaf_c"] * s["nind"])
    np.maximum.at(hmax, p, s["height"])
    np.add.at(cnt, p, 1.0)

    def cv(x: Array) -> float:
        return float(x.std() / x.mean()) if x.mean() > 0 else float("nan")

    return cv(lai), cv(hmax), cv(cnt)


def open_cells(rr: RestartReader, cells: list[int]) -> dict[int, dict[str, Array]]:
    first = rr.generic.firstcell
    out = {}
    with rr:
        for c in cells:
            s = cell_stems(rr.read(c - first))
            if s is not None:
                out[c] = s
    return out


def rank_bin(r: Array) -> npt.NDArray[np.int64]:
    return np.digitize(r, RANK_EDGES[1:-1])


def summarise_light(stems: dict[int, dict[str, Array]]) -> dict[str, Any]:
    """Per height-rank bin: median light-per-leaf, median fpar, stems; plus the CVs."""
    h = np.array([heterogeneity(s) for s in stems.values()])
    rows = {}
    allr = np.concatenate([s["rank"] for s in stems.values()])
    lpl = np.concatenate([s["lpl"] for s in stems.values()])
    fp = np.concatenate([s["fpar"] for s in stems.values()])
    b = rank_bin(allr)
    for k in range(len(RANK_EDGES) - 1):
        m = b == k
        rows[f"rank_{RANK_EDGES[k]:.1f}"] = {
            "stems": int(m.sum()),
            "light_per_leaf_p50": float(np.median(lpl[m])) if m.any() else None,
            "fpar_p50": float(np.median(fp[m])) if m.any() else None,
        }
    return {
        "cells": len(stems),
        "stems_per_patch_mean": float(np.mean([s["height"].size / 25 for s in stems.values()])),
        "cv_patch_leaf_p50": float(np.nanmedian(h[:, 0])),
        "cv_patch_hmax_p50": float(np.nanmedian(h[:, 1])),
        "cv_patch_count_p50": float(np.nanmedian(h[:, 2])),
        "by_rank": rows,
    }


def fate_table(y0: dict[int, dict[str, Array]], y4: dict[int, dict[str, Array]]) -> dict[str, Any]:
    """Year-0 stems matched to year 4: doomed (counter >= 4) / dead, by rank bin x light quintile.

    Light quintiles are taken WITHIN each rank bin across the arm's pooled stems, so the table
    separates "mid-canopy" from "mid-canopy AND shaded"."""
    rank, lpl, carbon, fate = [], [], [], []
    dup = 0
    for c, s0 in y0.items():
        s4 = y4.get(c)
        key0 = s0["patch"] * 1e9 + s0["id"] * 1e7 + s0["index"]
        if np.unique(key0).size != key0.size:
            dup += 1
            continue
        if s4 is None:
            f = np.full(key0.size, 2)
        else:
            key4 = s4["patch"] * 1e9 + s4["id"] * 1e7 + s4["index"]
            lut = dict(zip(key4.tolist(), s4["counter"].tolist(), strict=True))
            f = np.array([2 if k not in lut else (1 if lut[k] >= 4 else 0) for k in key0.tolist()])
        rank.append(s0["rank"])
        lpl.append(s0["lpl"])
        carbon.append(s0["vegc"])
        fate.append(f)
    r, lp, cb, ft = (np.concatenate(x) for x in (rank, lpl, carbon, fate))
    b = rank_bin(r)
    out: dict[str, Any] = {
        "cells_with_duplicate_keys": dup,
        "stems": int(r.size),
        "doomed_share": float(np.mean(ft == 1)),
        "dead_by_y4_share": float(np.mean(ft == 2)),
        "doomed_carbon_share": float(cb[ft == 1].sum() / cb.sum()),
        "by_rank": {},
    }
    for k in range(len(RANK_EDGES) - 1):
        m = b == k
        if not m.any():
            continue
        q = np.quantile(lp[m], [0.2, 0.4, 0.6, 0.8])
        qi = np.digitize(lp[m], q)
        cells = {}
        for j in range(5):
            mm = qi == j
            cells[f"light_q{j + 1}"] = {
                "stems": int(mm.sum()),
                "light_per_leaf_p50": float(np.median(lp[m][mm])),
                "doomed": float(np.mean(ft[m][mm] == 1)),
                "dead_by_y4": float(np.mean(ft[m][mm] == 2)),
            }
        out["by_rank"][f"rank_{RANK_EDGES[k]:.1f}"] = {
            "stems": int(m.sum()),
            "doomed": float(np.mean(ft[m] == 1)),
            "dead_by_y4": float(np.mean(ft[m] == 2)),
            "quintiles": cells,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    runs = Path(str(path("scratch.runs")))
    ap.add_argument("--probe", type=Path, default=runs / "contdiag-counter")
    ap.add_argument(
        "--emulated",
        type=Path,
        default=runs / "spinup-product-v3vegc" / "restart_1699_emulated.lpj",
    )
    ap.add_argument("--pilot-runs", type=Path, default=runs / "pilot-v2-constco2")
    ap.add_argument("--pilot-max", type=int, default=200)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    arms: dict[str, Any] = {}
    y4: dict[str, dict[int, dict[str, Array]]] = {"emulated": {}, "null": {}}
    for arm, got in y4.items():
        for m in PROBE_MEMBERS:
            rr = RestartReader(a.probe / arm / m / "restart" / "restart_1900.lpj")
            f = rr.generic.firstcell
            got.update(open_cells(rr, list(range(f, f + rr.generic.ncell))))
    cells = sorted(set(y4["emulated"]) | set(y4["null"]))
    template = Path(str(path("ground_truth.restart_spinup_end")))
    y0 = {
        "emulated": open_cells(RestartReader(a.emulated), cells),
        "null": open_cells(RestartReader(template), cells),
    }
    for arm, start in y0.items():
        arms[f"{arm}_y0"] = summarise_light(start)
        arms[f"{arm}_y4"] = summarise_light(y4[arm])
        arms[f"{arm}_fate"] = fate_table(start, y4[arm])

    pilot: dict[int, dict[str, Array]] = {}
    for i, f in enumerate(sorted(a.pilot_runs.glob("c*/control/restart/*.lpj"))[: a.pilot_max]):
        rr = RestartReader(f)
        with rr:
            s = cell_stems(rr.read(0))
        if s is not None:
            pilot[i] = s
    arms["pilot_constco2_control"] = summarise_light(pilot)

    (a.out / "patch_light.json").write_text(json.dumps(arms, indent=1))
    print(
        json.dumps(
            {k: {kk: vv for kk, vv in v.items() if kk != "by_rank"} for k, v in arms.items()},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
