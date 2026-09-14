#!/usr/bin/env python
"""FALSIFICATION ARMS for the pilot response model. Diagnostics, never nulls.

    scripts/diag_pilot_response_ablation.py --out <dir> --cache <state.parquet>

The model arm passed its kill test at 0.5453 against a bar of 0.2257 and beat the best null at all
29 levels. This project has been wrong about a result that looked exactly that good twice -- a band
whose tolerance came from the seeds that defined its truth, and an aggregate response whose sign was
inverted and went unnoticed for two months -- so the pass is not reported until somebody has tried
to break it.

THREE ARMS, EACH DESIGNED TO MAKE THE SCORE COLLAPSE IF THE SKILL IS AN ARTEFACT.

1. BLIND. Remove the five design axes and the derived forcing deltas. The model keeps the cell's
   whole control state and its baseline climate, but has no way to tell WHICH of the 29
   perturbations it is being asked about. Skill must fall to roughly what a single per-cell average
   response can buy. If a blinded model still scores near 0.5, the target is reachable without the
   forcing and something is leaking.

2. SCRAMBLED. Keep the forcing features but permute which design point's coefficients are attached
   to which of the cell's 29 arms, with an INDEPENDENT permutation per cell. The marginals are
   untouched and only the pairing dies. This separates "the model uses the forcing" from "the
   forcing columns happen to be informative".

   ⚠ A SHARED PERMUTATION DOES NOT WORK, and the first version of this arm used one. The 29 design
   points are identical at every cell, so one permutation applied everywhere is a pure relabelling:
   the map from features(perm[j]) to response(j) is a bijection that holds in the training cells
   and the held-out ones alike, the model learns the forcing under new names, and the arm scored
   0.4950 against the model's 0.5453 -- which reads as "the falsification nearly succeeded" when
   what actually happened is that nothing was falsified.

3. COLLAPSE DECOMPOSITION. Not an ablation: how much of the total squared change the metric is
   built from comes from arms that went treeless, where the change is simply minus the whole
   standing state. Predicting collapse IS a real and useful skill, but if the pooled number is
   mostly collapse then it means something narrower than it appears, and that has to be disclosed
   beside the score rather than discovered later.

None of these is a competitor the model must beat. They do not enter the decision rule and they do
not appear in the verdict as nulls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import polars as pl

from exp_derive_nulls_pilot import _per_level_and_pooled, build_deltas
from exp_model_pilot_response import DESIGN_AXES, build_features, fit_predict_oof
from vegemu.paths import paths
from vegemu.score import RESPONSE_QUANTITIES, blocked_spatial_folds, skill_vs_no_change

DERIVED = ("d_tas_abs", "d_pr_abs", "d_rsds_abs", "pert_tas_ann", "pert_pr_ann", "pert_rsds_ann")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version

    state = pl.read_parquet(args.cache)
    cells = pl.read_csv(corpus / "cells.csv")
    design = pl.read_csv(corpus / "design.csv")
    q = RESPONSE_QUANTITIES

    dtrue, _control, cell_ids, points = build_deltas(state, cells, q)
    scored = cells.filter(pl.col("cell").is_in(cell_ids)).sort("cell")
    x, names = build_features(state, scored, design, cell_ids, points)
    lon = scored["lon"].to_numpy().astype(np.float64)
    lat = scored["lat"].to_numpy().astype(np.float64)
    folds = blocked_spatial_folds(lon, lat, k=args.k, degrees=args.degrees, seed=42)

    forcing_idx = [names.index(n) for n in (*DESIGN_AXES, *DERIVED)]
    keep_idx = [i for i in range(len(names)) if i not in set(forcing_idx)]
    report: dict[str, object] = {
        "note": "DIAGNOSTIC ARMS. Not nulls, not part of the decision rule.",
        "blocking_degrees": args.degrees,
        "n_forcing_features_removed": len(forcing_idx),
        "arms": {},
    }

    print("=== arm 1: BLIND (no forcing features at all) ===", flush=True)
    blind = fit_predict_oof(x[:, :, keep_idx], dtrue, folds, q)
    report["arms"]["blind"] = _per_level_and_pooled(blind, dtrue, points, q)  # type: ignore[index]

    print("=== arm 2: SCRAMBLED (forcing re-paired independently per cell) ===", flush=True)
    # ⚠ THE PERMUTATION MUST BE DRAWN PER CELL. The first version of this arm used ONE permutation
    # for every cell and scored 0.4950 against the model's 0.5453, which looked like a failed
    # falsification and was actually a broken one: the 29 design points are identical at every
    # cell, so a permutation shared by all cells is a pure RELABELLING -- a bijection from
    # features(perm[j]) to response(j) that holds in the training cells and in the held-out ones
    # alike. The model simply learns the forcing under new names and loses almost nothing.
    # Drawing an independent permutation per cell is what actually destroys the pairing, because
    # then no consistent map from forcing features to response survives across cells.
    rng = np.random.default_rng(20260914)
    x_scram = x.copy()
    for i in range(x.shape[0]):
        p = rng.permutation(len(points))
        # Column by column rather than with a fancy index: mixing an integer, a slice and a list in
        # one subscript silently TRANSPOSES the result, and a transposed assignment here would be a
        # second broken falsification arm rather than a fixed one.
        for k in forcing_idx:
            x_scram[i, :, k] = x[i, p, k]
    scrambled = fit_predict_oof(x_scram, dtrue, folds, q)
    report["arms"]["scrambled"] = _per_level_and_pooled(scrambled, dtrue, points, q)  # type: ignore[index]

    # --- arm 3: how much of the metric is forest collapse -------------------------------------
    # A pair is a collapse if the perturbed arm has no stems at all. Its change is then minus the
    # entire standing state, which is the largest response the corpus contains.
    pairs = zip(state["cell"], state["point"], strict=True)
    idx = {(int(c), str(p)): i for i, (c, p) in enumerate(pairs)}
    stems = state["stems_total"].to_numpy()
    collapsed = np.zeros(dtrue.shape[:2], dtype=bool)
    for i, cell in enumerate(cell_ids):
        for j, point in enumerate(points):
            collapsed[i, j] = stems[idx[(cell, point)]] <= 0

    ss_total = np.nansum(dtrue**2, axis=(0, 1))
    ss_collapse = np.nansum(np.where(collapsed[:, :, None], dtrue, np.nan) ** 2, axis=(0, 1))
    metrics = json.loads((Path(args.out).parent / "metrics.json").read_text())
    # The model arm does not persist its predictions, so the full model is re-fitted here. Same
    # script, same features, same folds, same seed -- it must reproduce the scored number, and the
    # reference value is carried through from metrics.json so that agreement is checkable.
    print("=== arm 3: collapse decomposition (re-fitting the full model) ===", flush=True)
    model_pred = fit_predict_oof(x, dtrue, folds, q)

    survived = ~collapsed
    flat_keep = survived.reshape(-1)
    per_q_survivors = skill_vs_no_change(
        model_pred.reshape(-1, len(q))[flat_keep], dtrue.reshape(-1, len(q))[flat_keep]
    )
    report["arms"]["collapse_decomposition"] = {
        "n_collapsed_pairs": int(collapsed.sum()),
        "frac_collapsed_pairs": float(collapsed.mean()),
        "frac_of_total_squared_change_from_collapsed_pairs": {
            name: float(ss_collapse[j] / ss_total[j]) if ss_total[j] > 0 else float("nan")
            for j, name in enumerate(q)
        },
        "model_score_on_surviving_pairs_only": {
            "pooled": float(np.nanmean(per_q_survivors)),
            "per_quantity": {name: float(v) for name, v in zip(q, per_q_survivors, strict=True)},
        },
        "model_score_all_pairs_for_reference": float(
            metrics["by_blocking"][f"{args.degrees:g}deg"]["decision"]["model_pooled"]
        ),
    }

    (out / "ablation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    summarise(report)
    print(f"\nwrote {out / 'ablation.json'}")
    return 0


def summarise(report: dict[str, object]) -> None:
    """Print the three arms beside the number they are trying to break."""
    arms = report["arms"]
    cd = arms["collapse_decomposition"]  # type: ignore[index]
    surviving = cd["model_score_on_surviving_pairs_only"]["pooled"]

    print("\n=== RESULT ===")
    print(f"  full model (from metrics.json)   {cd['model_score_all_pairs_for_reference']:+.6f}")
    print(f"  arm 1 BLIND                      {arms['blind']['pooled']:+.6f}")  # type: ignore[index]
    print(f"  arm 2 SCRAMBLED                  {arms['scrambled']['pooled']:+.6f}")  # type: ignore[index]
    print(f"  collapsed pairs                  {cd['n_collapsed_pairs']}", end="")
    print(f" ({cd['frac_collapsed_pairs']:.4f})")
    print(f"  model on SURVIVING pairs only    {surviving:+.6f}")
    print("  share of squared change from collapsed pairs:")
    for name, v in cd["frac_of_total_squared_change_from_collapsed_pairs"].items():
        print(f"    {name:20s} {v:.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
