#!/usr/bin/env python
"""Where the climate-only equilibrium map is right and where it is wrong, from its out-of-fold file.

    scripts/sbatch_py.sh T-eqm-diag scripts/diag_equilibrium_map.py \\
        --oof <scratch.models>/equimap-v1/oof_pilot.parquet --out <scratch.exp>/T-equimap-diag

⚠ DEVELOPMENT DIAGNOSTICS, NOT CLAIMS. Nothing here is pre-registered and no number here may be
quoted as a skill of the emulator. The one number on the record is `X-20260923-equilibrium-from-
climate`'s 0.607582, and the first block below re-derives it from the file only as a check that the
file is the one that number came from. Everything else says where the error lives, so the next
sealed experiment can be aimed at it.

READ-ONLY. It reads the out-of-fold file, the decoded state table (the truth) and the corpus table
(the eight analogue features, for the dev nulls of the type-share heads). It fits nothing except
those two lookups, and writes only into --out.

WHAT IT REPORTS, every skill on the sealed formula -- `1 - SSE / SS(truth about its pooled mean)`,
per quantity, over the rows where the truth exists, log1p for forest-scale quantities, raw for the
rest -- and every number on the pilot basis: pilot-v2-constco2, 200 cells x 30 climates x 1 seed,
held out in whole 15-degree tiles, 5 folds, seed 42.

  sealed_check        the 22 raw heads rescored; must return the sealed per-quantity values
  postprocess_effect  the same after sorting/clipping, and what the treeless rule costs
  within_between      how much of each quantity's error is a per-CELL offset (the same wrong
                      answer under all 30 climates) and how much varies across a cell's climates;
                      and the within-cell skill, which is the part that carries a climate response
  implied_response    the change from the cell's control climate, predicted minus predicted,
                      against true minus true: the response this level model implies
  forest_rows_only    forest-scale skill on tree-bearing rows only, so the treeless/forest split
                      cannot carry the score
  bias_by_decile      mean error and 10 %-band rate per decile of the truth: shrinkage or not
  per_climate_level   skill per design climate
  error_correlation   whether the heads' errors move together, on tree-bearing rows
  shares              the type-share heads' skill and composition summaries, beside two dev nulls
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.spatial import cKDTree

from vegemu.models.equilibrium import (
    HEADS,
    LOG1P_HEADS,
    SEALED_HEADS,
    SHARE_HEADS,
    targets_from_frame,
    transformed,
)
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths
from vegemu.score import ABS_FLOOR_COMPOSITION

Array = npt.NDArray[np.float64]

BAND = 0.10
DECILES = 10
FOREST_SCALE: tuple[str, ...] = ("stems_per_patch", "agb", "lai", "soilc", "litterc")
SEALED_METRICS = "X-20260923-equilibrium-from-climate"


def var_explained(p: Array, t: Array) -> tuple[float, int]:
    """`(1 - SSE/SS, rows)` over rows where the truth exists; NaN when the truth does not vary.

    A missing prediction on a scored row is refused, exactly as the sealed scorer refuses it.
    """
    m = np.isfinite(t)
    assert np.isfinite(p[m]).all(), "a scored row has no prediction"
    ss = float(((t[m] - t[m].mean()) ** 2).sum())
    if ss <= 1e-12 * max(float(np.abs(t[m]).mean()) ** 2, 1.0) * max(int(m.sum()), 1):
        return float("nan"), int(m.sum())
    return 1.0 - float(((p[m] - t[m]) ** 2).sum()) / ss, int(m.sum())


def varies(v: Array) -> bool:
    """False for fine-root conductivity, whose spread is ~1e-18: one value, not a varying trait."""
    v = v[np.isfinite(v)]
    return bool(v.size) and float(np.ptp(v)) > 1e-9 * max(abs(float(v.mean())), 1.0)


def skills(p: Array, t: Array, heads: tuple[str, ...]) -> dict[str, float]:
    return {h: var_explained(p[:, j], t[:, j])[0] for j, h in enumerate(heads)}


def _mean(d: dict[str, float], keys: tuple[str, ...]) -> float:
    v = [d[k] for k in keys if np.isfinite(d[k])]
    return float(np.mean(v)) if v else float("nan")


def fitted_scale(raw: Array) -> Array:
    """Raw head outputs back onto the scale they were fitted on, EXACTLY: log1p with no clip.

    `transformed` clips at zero first, which is right for a truth and wrong here -- a head that
    predicted log1p(stems) = -0.02 would be scored as if it had said 0, and 115 rows of the pilot
    did. That clip is post-processing step 1, and is measured as such, not folded into the check.
    """
    return np.stack(
        [np.log1p(raw[:, j]) if h in LOG1P_HEADS else raw[:, j] for j, h in enumerate(HEADS)],
        axis=1,
    )


def load(oof_path: Path, state_path: Path, corpus_path: Path) -> dict[str, Any]:
    oof = pl.read_parquet(oof_path).sort(["cell", "point"])
    state = pl.read_parquet(state_path).sort(["cell", "point"])
    corpus = pl.read_parquet(corpus_path).sort(["cell", "point"])
    for other in (state, corpus):
        assert other["cell"].to_list() == oof["cell"].to_list(), "cell order differs"
        assert other["point"].to_list() == oof["point"].to_list(), "point order differs"
    y = targets_from_frame(state, HEADS)
    raw = oof.select([f"raw_{h}" for h in HEADS]).to_numpy().astype(np.float64)
    pred = oof.select([f"pred_{h}" for h in HEADS]).to_numpy().astype(np.float64)
    return {
        "oof": oof,
        "y": y,
        "raw": raw,
        "pred": pred,
        "zt": transformed(HEADS, y),
        "zr": fitted_scale(raw),
        "treed": state["stems_total"].to_numpy() > 0,
        "analogue": corpus.select(list(ANALOGUE_FEATURES)).to_numpy().astype(np.float64),
        "cell": oof["cell"].to_numpy(),
        "point": oof["point"].to_numpy(),
        "fold": oof["fold"].to_numpy(),
    }


def sealed_check(d: dict[str, Any], sealed_block: dict[str, Any]) -> dict[str, Any]:
    n = len(SEALED_HEADS)
    mine = skills(d["zr"][:, :n], d["zt"][:, :n], SEALED_HEADS)
    diffs = {
        q: abs(mine[q] - float(sealed_block["per_quantity"][q]))
        for q in SEALED_HEADS
        if np.isfinite(mine[q])
    }
    return {
        "mean_over_varying": _mean(mine, SEALED_HEADS),
        "sealed_mean": float(sealed_block["pooled"]),
        "max_abs_diff_per_quantity": max(diffs.values()),
        "note": "raw_ columns went through expm1 then log1p, so agreement is to ~1e-12, not bits",
    }


def postprocess_effect(d: dict[str, Any]) -> dict[str, Any]:
    """Sorting and clipping, scored on the same rows; the treeless rule's cost, counted."""
    n = len(SEALED_HEADS)
    zp = transformed(HEADS, d["pred"])
    filled = np.where(np.isfinite(zp), zp, d["zr"])  # a treeless-blanked row keeps its raw value
    before = skills(d["zr"][:, :n], d["zt"][:, :n], SEALED_HEADS)
    after = skills(filled[:, :n], d["zt"][:, :n], SEALED_HEADS)
    pred_treeless = d["oof"]["pred_treeless"].to_numpy()
    return {
        "mean_before": _mean(before, SEALED_HEADS),
        "mean_after_sort_and_clip": _mean(after, SEALED_HEADS),
        "per_quantity_change": {q: after[q] - before[q] for q in SEALED_HEADS},
        "treeless_confusion": {
            "true_treeless_predicted_treeless": int((~d["treed"] & pred_treeless).sum()),
            "true_treeless_predicted_forest": int((~d["treed"] & ~pred_treeless).sum()),
            "true_forest_predicted_treeless": int((d["treed"] & pred_treeless).sum()),
            "true_forest_predicted_forest": int((d["treed"] & ~pred_treeless).sum()),
        },
        "note": "a true-forest row predicted treeless loses its trait prediction in pred_; "
        "it is scored here on its raw value so the rows are the same as before",
    }


def within_between(d: dict[str, Any]) -> dict[str, Any]:
    """Error and truth split into a per-cell mean and the departure from it, per quantity."""
    out = {}
    for j, h in enumerate(HEADS):
        t, p = d["zt"][:, j], d["zr"][:, j]
        m = np.isfinite(t)
        if not varies(t[m]):
            continue
        cells = d["cell"][m]
        e, tt = p[m] - t[m], t[m]
        uniq, inv = np.unique(cells, return_inverse=True)
        cnt = np.bincount(inv).astype(np.float64)
        e_bar = np.bincount(inv, e) / cnt
        t_bar = np.bincount(inv, tt) / cnt
        sse_b = float((cnt * e_bar**2).sum())
        sse_w = float(((e - e_bar[inv]) ** 2).sum())
        ss_b = float((cnt * (t_bar - tt.mean()) ** 2).sum())
        ss_w = float(((tt - t_bar[inv]) ** 2).sum())
        if ss_b + ss_w <= 0:
            continue
        out[h] = {
            "error_share_between_cells": sse_b / (sse_b + sse_w),
            "truth_share_between_cells": ss_b / (ss_b + ss_w),
            "skill_between_cells": 1.0 - sse_b / ss_b if ss_b > 0 else float("nan"),
            "skill_within_cell": 1.0 - sse_w / ss_w if ss_w > 0 else float("nan"),
            "cells": int(uniq.size),
        }
    return out


def implied_response(d: dict[str, Any]) -> dict[str, Any]:
    """Change from the control climate: `1 - SUM(dpred - dtrue)^2 / SUM(dtrue^2)`, per quantity.

    The response kill tests' own formula, applied to the difference of two LEVEL predictions. The
    model was never shown the control forest, so this is what it implies, not what it was asked.
    """
    ctl = d["point"] == "control"
    ctl_row = {int(c): i for i, c in enumerate(d["cell"]) if ctl[i]}
    idx = np.array([ctl_row[int(c)] for c in d["cell"]])
    arm = ~ctl
    out = {}
    for j, h in enumerate(HEADS):
        dt = (d["zt"][:, j] - d["zt"][idx, j])[arm]
        dp = (d["zr"][:, j] - d["zr"][idx, j])[arm]
        m = np.isfinite(dt)
        den = float((dt[m] ** 2).sum())
        if den <= 1e-12 or not varies(d["zt"][:, j]):
            continue
        out[h] = {"skill": 1.0 - float(((dp[m] - dt[m]) ** 2).sum()) / den, "pairs": int(m.sum())}
    return out


def forest_rows_only(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for h in FOREST_SCALE:
        j = HEADS.index(h)
        t, p = d["zt"][d["treed"], j], d["zr"][d["treed"], j]
        out[h] = {
            "skill_log1p": var_explained(p, t)[0],
            "skill_natural": var_explained(np.expm1(p), np.expm1(t))[0],
            "rows": int(d["treed"].sum()),
        }
    return out


def bias_by_decile(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for j, h in enumerate(SEALED_HEADS):
        t, zp = d["zt"][:, j], d["zr"][:, j]
        m = np.isfinite(t) & (d["treed"] if h not in LOG1P_HEADS else True)
        if not varies(t[m]):
            continue
        edges = np.quantile(t[m], np.linspace(0, 1, DECILES + 1))
        k = np.clip(np.searchsorted(edges, t[m], side="right") - 1, 0, DECILES - 1)
        nat_t, nat_p = d["y"][m, j], d["raw"][m, j]
        rows = []
        for b in range(DECILES):
            s = k == b
            if not s.any():
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                rel = (nat_p[s] - nat_t[s]) / np.abs(nat_t[s])
            rows.append(
                {
                    "decile": b + 1,
                    "rows": int(s.sum()),
                    "truth_mid": float(np.median(t[m][s])),
                    "mean_error_fitted_scale": float((zp[m][s] - t[m][s]).mean()),
                    "median_rel_error": float(np.nanmedian(rel)),
                    "band10_rate": float(
                        (np.abs(nat_p[s] - nat_t[s]) <= BAND * np.abs(nat_t[s])).mean()
                    ),
                }
            )
        out[h] = rows
    return out


def per_climate_level(d: dict[str, Any], design: pl.DataFrame) -> dict[str, Any]:
    n = len(SEALED_HEADS)
    axes = {str(r["point"]): r for r in design.iter_rows(named=True)}
    out = {}
    for pt in np.unique(d["point"]):
        m = d["point"] == pt
        sk = skills(d["zr"][m, :n], d["zt"][m, :n], SEALED_HEADS)
        a = axes[str(pt)]
        out[str(pt)] = {
            "mean_over_varying": _mean(sk, SEALED_HEADS),
            "dtemp_k": float(a["dtemp_k"]),
            "fprec": float(a["fprec"]),
            "treeless_rows": int((~d["treed"][m]).sum()),
            "per_quantity": sk,
        }
    return out


def error_correlation(d: dict[str, Any]) -> dict[str, Any]:
    n = len(SEALED_HEADS)
    varying = [j for j in range(n) if varies(d["zt"][d["treed"], j])]
    names = [SEALED_HEADS[j] for j in varying]
    e = d["zr"][d["treed"]][:, varying] - d["zt"][d["treed"]][:, varying]
    r = np.corrcoef(e, rowvar=False)
    pairs = [
        (names[a], names[b], float(r[a, b]))
        for a in range(len(names))
        for b in range(a + 1, len(names))
    ]
    pairs.sort(key=lambda p: -abs(p[2]))
    off = np.abs(r[np.triu_indices(len(names), 1)])
    return {
        "rows": int(d["treed"].sum()),
        "quantities": names,
        "mean_abs_offdiagonal": float(off.mean()),
        "top_pairs": [{"a": a, "b": b, "r": v} for a, b, v in pairs[:15]],
        "matrix": r.tolist(),
    }


def _share_nulls(d: dict[str, Any], cols: list[int]) -> dict[str, Array]:
    """Two dev nulls for the shares, per fold: the training mean and the nearest analogue."""
    t = d["y"][:, cols]
    ok = np.isfinite(t).all(axis=1)
    mean = np.full_like(t, np.nan)
    analogue = np.full_like(t, np.nan)
    for f in np.unique(d["fold"]):
        te, tr = d["fold"] == f, (d["fold"] != f) & ok
        mean[te] = t[tr].mean(axis=0)
        a = d["analogue"]
        mu, sd = a[tr].mean(axis=0), a[tr].std(axis=0)
        _, idx = cKDTree((a[tr] - mu) / sd).query((a[te] - mu) / sd, k=1)
        analogue[te] = t[tr][np.asarray(idx, dtype=np.int64)]
    return {"training_mean": mean, "nearest_analogue": analogue}


def _composition(p: Array, t: Array) -> dict[str, Any]:
    m = np.isfinite(t).all(axis=1) & np.isfinite(p).all(axis=1)
    p, t = p[m], t[m]
    within = np.abs(p - t) <= ABS_FLOOR_COMPOSITION
    return {
        "rows": int(m.sum()),
        "dominant_type_agreement": float((p.argmax(axis=1) == t.argmax(axis=1)).mean()),
        "mean_l1_distance": float(np.abs(p - t).sum(axis=1).mean()),
        "all_types_within_abs_floor": float(within.all(axis=1).mean()),
        "per_type_within_abs_floor": within.mean(axis=0).tolist(),
    }


def shares(d: dict[str, Any]) -> dict[str, Any]:
    cols = [HEADS.index(h) for h in SHARE_HEADS]
    t = d["y"][:, cols]
    arms = {"model_raw": d["raw"][:, cols], **_share_nulls(d, cols)}
    # The post-processed shares (clipped, renormalised) exist only where the row is not predicted
    # treeless; scored against the raw heads on the rest so the rows match every other arm.
    post = d["pred"][:, cols]
    arms["model_renormalised"] = np.where(np.isfinite(post), post, d["raw"][:, cols])
    out: dict[str, Any] = {
        "abs_floor": ABS_FLOOR_COMPOSITION,
        "rows_scored": int(np.isfinite(t).all(axis=1).sum()),
        "arms": {},
    }
    for name, p in arms.items():
        sk = skills(p, t, SHARE_HEADS)
        out["arms"][name] = {
            "mean_skill_level": _mean(sk, SHARE_HEADS),
            "per_type_skill_level": sk,
            **_composition(p, t),
        }
    return out


PROPOSAL = {
    "status": "PROPOSAL to the scoring stream; not pre-registered, not sealed",
    "question": "From the 30-year climate and the soil alone, can a model predict the settled "
    "forest's MIX OF TREE TYPES at places it has never seen?",
    "estimand": "skill_composition_level_mean: per type, 1 - SSE/SS(truth about its pooled "
    "mean) of the stem share pft_frac_i over tree-bearing (cell, climate) rows of "
    "pilot-v2-constco2, on the assembled out-of-fold prediction; unweighted mean over the "
    "seven types (six are free: the shares sum to one, stated beside the number)",
    "rows": "truth-defined rows only (stems_total > 0); the arm must predict every one -- use the "
    "raw heads, not the treeless-blanked ones, so no arm declines the hard rows",
    "folds": "blocked_spatial_folds(lon, lat, 5, 15, 42) primary, 5 degrees reported beside",
    "features": "the 91 of the equilibrium map (86 climate + 5 soil); nothing from any restart",
    "nulls": "training_mean, nearest_analogue (the eight vegemu.nulls analogue features, "
    "standardised on training rows, nearest training row with defined shares), "
    "nearest_geographic (nearest training cell under the same design climate), shuffled; "
    "each derived by a nulls-only job BEFORE the seal, values written into the file",
    "threshold": "the kill tests' construction: the gap between the best null and the runner-up, "
    "plus ~0.012 of headroom, at the larger of the two blockings",
    "ceiling": "from the constant-CO2 second seed now being run (pilot-v2-constco2-s2): "
    "0.5*mean((seed1-seed2)^2) over the shared rows divided by the scored variance -- the first "
    "ceiling on the SAME CO2 path, which the equilibrium experiment did not have",
    "beside_it_never_instead": "dominant-type agreement, mean L1 distance, and the share of rows "
    "with every type within ABS_FLOOR_COMPOSITION (0.0384) of the truth, per arm and for the "
    "ceiling",
    "why_it_matters": "synth.py copies each stem's TYPE from the template, so a warmed forest "
    "cannot change its mix unless a composition head exists and is shown to be right",
    # ⚠ Invariant 2 is "pre-register before you run", and on these rows the model arm HAS run.
    "not_blind": "THE MODEL ARM HAS ALREADY BEEN SCORED ON THESE EXACT ROWS AND FOLDS -- the "
    "'shares' block of this file, which a pre-registration author will have read. A test "
    "sealed on pilot-v2-constco2 would be sealed after its outcome was seen, and must say so "
    "in its question. A blind test needs places the map has never been scored on (new cells, "
    "e.g. the mid-size corpus). The constant-CO2 second seed does not supply one: it repeats "
    "the same cells and climates, so the map's predictions are identical and only the truth's "
    "noise differs -- it gives the ceiling, not an independent test",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--oof", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--state-table", default=None)
    args = ap.parse_args()
    cfg = paths()
    corpus_root = Path(str(cfg["scratch"]["corpus"])) / args.version
    exp_root = Path(str(cfg["scratch"]["exp"]))
    state = Path(
        args.state_table or exp_root / "X-pilot-decode-v2corpus" / f"state_{args.version}.parquet"
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sealed_block = json.loads((exp_root / SEALED_METRICS / "metrics.json").read_text("utf-8"))[
        "by_blocking"
    ]["15deg"]["model"]

    d = load(Path(args.oof), state, corpus_root / "corpus.parquet")
    design = pl.read_csv(corpus_root / "design.csv")
    n = len(SEALED_HEADS)
    all_skill = skills(d["zr"], d["zt"], HEADS)
    report: dict[str, Any] = {
        "status": "DEVELOPMENT DIAGNOSTICS -- not pre-registered, not a claim",
        "basis": f"{args.version}: 200 cells x 30 climates x 1 seed, out-of-fold at 15-degree "
        "tiles (5 folds, seed 42); log1p for forest-scale quantities, raw otherwise; levels",
        "oof_file": args.oof,
        "sealed_check": sealed_check(d, sealed_block),
        "skill_every_head": all_skill,
        "skill_extra_heads_mean": _mean(all_skill, tuple(h for h in HEADS[n:])),
        "postprocess_effect": postprocess_effect(d),
        "within_between": within_between(d),
        "implied_response": implied_response(d),
        "forest_rows_only": forest_rows_only(d),
        "bias_by_decile": bias_by_decile(d),
        "per_climate_level": per_climate_level(d, design),
        "error_correlation": error_correlation(d),
        "shares": shares(d),
        "proposal_composition_level_experiment": PROPOSAL,
    }
    (out / "diag.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    sc = report["sealed_check"]
    print(f"sealed check: {sc['mean_over_varying']:.6f} vs {sc['sealed_mean']:.6f}")
    wb = report["within_between"]
    ir = report["implied_response"]
    print(
        f"{'quantity':18s} {'skill':>7s} {'err%btw':>8s} {'tru%btw':>8s} "
        f"{'within':>7s} {'resp':>7s}"
    )
    for h in HEADS:
        if h in wb:
            print(
                f"{h:18s} {all_skill[h]:+7.3f} {wb[h]['error_share_between_cells']:8.3f} "
                f"{wb[h]['truth_share_between_cells']:8.3f} {wb[h]['skill_within_cell']:+7.3f} "
                f"{ir.get(h, {}).get('skill', float('nan')):+7.3f}"
            )
    for name, a in report["shares"]["arms"].items():
        print(
            f"shares {name:20s} mean skill {a['mean_skill_level']:+.3f}  dominant "
            f"{a['dominant_type_agreement']:.3f}  L1 {a['mean_l1_distance']:.3f}  all-within-floor "
            f"{a['all_types_within_abs_floor']:.3f}"
        )
    print(f"wrote {out / 'diag.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
