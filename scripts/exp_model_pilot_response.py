#!/usr/bin/env python
"""THE MODEL ARM of the response kill test, on the PILOT corpus.

    scripts/exp_model_pilot_response.py --out <dir> [--cache <state.parquet>]

This is the arm `X-20260909-pilot-warming-response` was sealed around and has never been run. The
nulls were derived first (`exp_derive_nulls_pilot.py`) and are re-derived here from the SAME arrays
the model is scored on, so the comparison cannot drift: invariant 1 is that no skill number is
reported without every null pre-registered for it, in the same table.

WHAT THE MODEL IS GIVEN, AND WHY THAT IS THE HONEST SET. Per the pre-registration: the held-out
cell's CONTROL state, its baseline climate, and the design point's five axis coefficients. The
control state is deliberately an input -- in production a real restart for the cell under its
present climate always exists, so withholding it would test a task nobody has to solve -- and it is
exactly the information the proportional nulls use, which is what makes them fair competitors
rather than a handicap. Coordinates are NOT given; only the spatial nulls see those.

⚠ THE LOSS IS ABSOLUTE HERE, AND THAT IS A REVERSAL OF THE LEVEL MODEL. `models/emulator.py` fits
its targets in logs, on purpose, because the acceptance band is RELATIVE and a log loss aligns with
it. This estimand is the opposite: `1 - SUM((dpred-dtrue)^2) / SUM(dtrue^2)` pooled over cells, an
absolute ratio of sums of squares, so squared error on the raw change IS the metric being scored.
Fitting the response in logs would optimise something the test does not measure -- and a change is
signed, so it has no log. One regressor per quantity, each on its own absolute change, means each
of the seven terms is fitted by exactly the loss that scores it.

WHY THE FORCING DELTAS ARE CONSTRUCTED EXPLICITLY. The design gives multiplicative coefficients
(`fprec` = 0.7 means 30 % less rain), so the ACTUAL forcing change at a cell is `pr_ann*(fprec-1)`,
not `fprec`. A tree can only reach that through many deep splits on two features at once. Handing
it the product costs nothing, invents no information -- both factors are already inputs -- and is
the difference between asking the model about a fraction and asking it about millimetres.

HYPERPARAMETERS ARE FIXED A PRIORI AND NOT TUNED. There is no inner search: selecting them against
the same blocked folds that produce the score would be exactly the leakage the blocking exists to
prevent, and with ~160 training cells per fold it would be easy to do accidentally.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
from lightgbm import LGBMRegressor

from exp_derive_nulls_pilot import (
    CONTROL_POINT,
    _per_level_and_pooled,
    build_deltas,
    decode,
    derive_nulls,
)
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import RESPONSE_QUANTITIES, blocked_spatial_folds, matrix

# The five baseline climate coordinates, raw and standardised. These are the axes the design
# perturbs, so "where this cell starts" is expressed in the same currency as "how far it is moved".
CLIMATE_BASE: tuple[str, ...] = ("tas_ann", "pr_ann", "pr_seasonality", "rsds_ann", "tas_iav")
CLIMATE_Z: tuple[str, ...] = tuple(f"z_{c}" for c in CLIMATE_BASE)

# The design point's five axis coefficients, exactly as line D wrote them.
DESIGN_AXES: tuple[str, ...] = ("dtemp_k", "fprec", "sprec", "frad", "fiav")

# Never features, and asserted so below. `cell`/`tile` are identity, `lon`/`lat` are the address the
# spatial nulls own, `stage` is a build-order label, `skip` is a decode flag.
FORBIDDEN: frozenset[str] = frozenset({"cell", "lon", "lat", "tile", "stage", "skip", "point"})

# Fixed a priori. Conservative depth and strong row/column subsampling because the independent
# sample is ~160 CELLS per fold, not 4,640 rows: every cell contributes 29 highly correlated rows.
PARAMS: dict[str, object] = {
    "n_estimators": 600,
    "learning_rate": 0.04,
    "num_leaves": 31,
    "min_child_samples": 40,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.7,
    "reg_lambda": 1.0,
    "verbose": -1,
}


def build_features(
    state: pl.DataFrame,
    cells: pl.DataFrame,
    design: pl.DataFrame,
    cell_ids: list[int],
    points: list[str],
) -> tuple[npt.NDArray[np.float64], list[str]]:
    """`(X, names)` with X shaped (n_cells, n_points, n_features), aligned to `build_deltas`.

    Aligned by CONSTRUCTION to the `(cell_ids, points)` order the target array uses, rather than by
    a join whose row order would have to be trusted. A silent misalignment here would look exactly
    like a model with no skill, which is the one result this experiment must not produce by
    accident.
    """
    ctl_cols = [c for c in state.columns if c not in FORBIDDEN]
    ctl = state.filter(pl.col("point") == CONTROL_POINT)
    ctl_by_cell = {int(c): i for i, c in enumerate(ctl["cell"])}
    ctl_values = matrix(ctl, tuple(ctl_cols))

    cell_by_id = {int(c): i for i, c in enumerate(cells["cell"])}
    clim_values = matrix(cells, CLIMATE_BASE + CLIMATE_Z)

    design_by_point = {str(p): i for i, p in enumerate(design["point"])}
    design_values = matrix(design, DESIGN_AXES)

    names = (
        [f"ctl_{c}" for c in ctl_cols]
        + list(CLIMATE_BASE + CLIMATE_Z)
        + list(DESIGN_AXES)
        # The forcing change in physical units, not as a coefficient. See the module docstring.
        + ["d_tas_abs", "d_pr_abs", "d_rsds_abs", "pert_tas_ann", "pert_pr_ann", "pert_rsds_ann"]
    )

    x = np.full((len(cell_ids), len(points), len(names)), np.nan)
    for i, cell in enumerate(cell_ids):
        ctl_row = ctl_values[ctl_by_cell[cell]]
        clim = clim_values[cell_by_id[cell]]
        tas, pr, _seas, rsds, _iav = clim[: len(CLIMATE_BASE)]
        for j, point in enumerate(points):
            axes = design_values[design_by_point[point]]
            dtemp, fprec, _sprec, frad, _fiav = axes
            derived = np.array(
                [
                    dtemp,
                    pr * (fprec - 1.0),
                    rsds * (frad - 1.0),
                    tas + dtemp,
                    pr * fprec,
                    rsds * frad,
                ]
            )
            x[i, j] = np.concatenate([ctl_row, clim, axes, derived])
    return x, names


def assert_no_leakage(names: list[str], folds: npt.NDArray[np.int64], n_cells: int) -> None:
    """The pre-registration's leakage checks, asserted BEFORE anything is fitted.

    Pre-registered as "asserted in the training script", so they are assertions and not comments.
    """
    bare = {n.removeprefix("ctl_") for n in names}
    for banned in ("lon", "lat", "cell", "tile"):
        assert banned not in bare, f"coordinate/identity feature leaked in: {banned}"
    assert not any("co2" in n.lower() for n in names), "CO2 is never a feature (invariant 8)"
    # One fold label per CELL, so a cell's 29 perturbed arms are held out together with it.
    assert folds.shape == (n_cells,), f"folds must be per cell, got {folds.shape} for {n_cells}"


def fit_predict_oof(
    x: npt.NDArray[np.float64],
    dtrue: npt.NDArray[np.float64],
    folds: npt.NDArray[np.int64],
    quantities: tuple[str, ...],
) -> npt.NDArray[np.float64]:
    """Out-of-fold predicted change, shaped like `dtrue`.

    Each cell is held out exactly once and the statistic is computed on the ASSEMBLED prediction,
    not averaged over folds -- the same construction `derive_nulls` uses for every null, so the
    model and its competitors are scored by identical arithmetic.

    A non-finite target row is dropped FROM TRAINING for that quantity only. That is the
    pre-registered treeless rule: a treeless arm has no trait median at all, while its stem count
    and stocks are legitimate zeros, so the two classes cannot share a handling rule and the drop
    has to be per quantity rather than per row.
    """
    n_cells, n_points, n_q = dtrue.shape
    flat_x = x.reshape(n_cells * n_points, x.shape[2])
    flat_y = dtrue.reshape(n_cells * n_points, n_q)
    row_fold = np.repeat(folds, n_points)
    dpred = np.full_like(dtrue, np.nan)

    for fold in np.unique(folds):
        test = row_fold == fold
        train = ~test
        for q in range(n_q):
            usable = train & np.isfinite(flat_y[:, q])
            if usable.sum() < 50 or not np.isfinite(flat_y[test, q]).any():
                dpred.reshape(-1, n_q)[test, q] = 0.0
                continue
            model = LGBMRegressor(**PARAMS)
            model.fit(flat_x[usable], flat_y[usable, q])
            dpred.reshape(-1, n_q)[test, q] = model.predict(flat_x[test])
        print(f"  fold {fold}: {int(test.sum())} rows predicted", flush=True)
    return dpred


def scorable_pairs(
    dtrue: npt.NDArray[np.float64], quantities: tuple[str, ...]
) -> dict[str, object]:
    """How many (cell, climate) pairs actually score, per quantity.

    The pre-registration requires the surviving count beside every trait number, not in a footnote:
    a pair drops out when the arm OR the control has no stems, so the trait medians are scored on
    cells where vegetation SURVIVED, which selects toward the milder perturbations. Reporting the
    count is what keeps that selection visible next to the score it produced.
    """
    total = int(dtrue.shape[0] * dtrue.shape[1])
    per_q = {q: int(np.isfinite(dtrue[:, :, k]).sum()) for k, q in enumerate(quantities)}
    return {
        "total_pairs": total,
        "scorable_pairs_per_quantity": per_q,
        "dropped_pairs_per_quantity": {q: total - n for q, n in per_q.items()},
    }


def decide(
    model: dict[str, object],
    nulls: dict[str, dict[str, object]],
    threshold: float = 0.080,
    statistic: str = "skill_response_mean",
) -> dict[str, object]:
    """The pre-registered decision rule, computed rather than eyeballed.

    Also counts the levels at which the model fails to beat the best null, because the
    pre-registration requires it: the response is not monotone in temperature, and a pass on the
    pooled statistic accompanied by a fail at more than half of the 29 levels MUST be reported as
    such in the verdict rather than summarised away.

    `threshold` and `statistic` default to the values `X-20260909-pilot-warming-response` was sealed
    with, so this script's own behaviour is unchanged. They are parameters only so that the
    composition arm -- a different estimand, with its own pre-registration and its own bar -- can
    reuse this exact arithmetic instead of restating it and risking a different rule.
    """
    ranked = sorted(((float(v["pooled"]), k) for k, v in nulls.items()), reverse=True)
    best_value, best_name = ranked[0]
    pooled = float(model["pooled"])
    margin = pooled - best_value

    per_level = model["per_level"]
    null_level = nulls[best_name]["per_level"]
    beaten = {p: float(per_level[p]) - float(null_level[p]) for p in per_level}  # type: ignore[index]
    n_lose = sum(1 for v in beaten.values() if v <= 0.0)

    return {
        "statistic": statistic,
        "model_pooled": pooled,
        "best_null": best_name,
        "best_null_value": best_value,
        "margin_model_minus_best_null": margin,
        "threshold": threshold,
        "required_model_value": best_value + threshold,
        "verdict": "pass" if margin > threshold else "fail",
        "levels_total": len(beaten),
        "levels_model_not_above_best_null": n_lose,
        "levels_majority_fail": n_lose > len(beaten) / 2,
        "per_level_margin": beaten,
    }


def _parser() -> argparse.ArgumentParser:
    """Split out of `main` so the option list can grow without pushing it over PLR0915.

    The statement-count limit is worth keeping on `main` -- it is the function that does the
    fitting and the scoring -- and argparse calls are the cheapest statements in it.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=None, help="decoded state parquet to reuse")
    ap.add_argument("--nproc", type=int, default=1)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0, help="primary blocking radius")
    ap.add_argument(
        "--also-degrees", type=float, default=5.0, help="reported alongside, never instead"
    )
    # ⚠ THE ID USED TO BE HARDCODED to the v1 experiment, so a re-score on another corpus stamped
    # the WRONG pre-registration into its own metrics and `append_result.py` would have filed the
    # result under an experiment that did not govern it. The default keeps every existing
    # invocation byte-identical; a re-score passes its own id.
    ap.add_argument(
        "--exp-id",
        default="X-20260909-pilot-warming-response",
        help="stamped into the output for append_result.py",
    )
    # ⚠ THE THREE OPTIONS BELOW ARE ADDITIONS ONLY. Without them this script is exactly the arm
    # three sealed experiments ran, and `decide` keeps its historical 0.080 default.
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.080,
        help="the pre-registered pass margin printed in metrics.json; MUST match the sealed rule",
    )
    ap.add_argument(
        "--centred",
        action="store_true",
        help=(
            "score the WITHIN-CELL CENTRED response (vegemu.centred), with the blind and scrambled "
            "models as declared nulls -- see scripts/centred_arms.py"
        ),
    )
    ap.add_argument(
        "--placebos-only",
        action="store_true",
        help="with --centred: fit only the nulls and the two learned placebos, NOT the model",
    )
    return ap


def main_centred(
    args: argparse.Namespace,
    report: dict[str, object],
    *,
    x: npt.NDArray[np.float64],
    names: list[str],
    dtrue: npt.NDArray[np.float64],
    control: npt.NDArray[np.float64],
    scored_cells: pl.DataFrame,
    points: list[str],
) -> int:
    """The `--centred` arm: the same model, re-read by the within-cell centred statistic.

    The uncentred scorer handed to the shared driver is `_per_level_and_pooled` unchanged, so the
    full model's uncentred diagnostic must reproduce the sealed kill test's 0.558968, and the blind
    and scrambled ones the 0.362322 and 0.331019 of the earlier blind-arm diagnostic.
    """
    # centred_arms imports this module, so a top-level import would be circular.
    from centred_arms import Problem, run_all_radii  # noqa: PLC0415

    problem = Problem(x, names, dtrue, control, scored_cells, points, RESPONSE_QUANTITIES)
    report.update(
        run_all_radii(
            problem,
            k=args.k,
            radii=(args.degrees, args.also_degrees),
            threshold=args.threshold,
            statistic="skill_response_centred_mean",
            uncentred=_per_level_and_pooled,
            placebos_only=args.placebos_only,
        )
    )
    report["arm"] = "placebos" if args.placebos_only else "model"
    name = "placebos.json" if args.placebos_only else "metrics.json"
    (Path(args.out) / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {Path(args.out) / name}")
    return 0


def main() -> int:
    args = _parser().parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / args.version

    cache = Path(args.cache) if args.cache else out / f"state_{args.version}.parquet"
    if cache.is_file():
        print(f"reusing decoded state: {cache}", flush=True)
        state = pl.read_parquet(cache)
    else:
        state = decode(args.version, args.nproc, None)
        state.write_parquet(cache)
        print(f"wrote decoded state: {cache}", flush=True)

    cells = pl.read_csv(corpus / "cells.csv")
    design = pl.read_csv(corpus / "design.csv")
    quantities = RESPONSE_QUANTITIES

    dtrue, control, cell_ids, points = build_deltas(state, cells, quantities)
    scored_cells = cells.filter(pl.col("cell").is_in(cell_ids)).sort("cell")
    x, names = build_features(state, scored_cells, design, cell_ids, points)
    print(f"features: {len(names)} over {len(cell_ids)} cells x {len(points)} points", flush=True)

    lon = scored_cells["lon"].to_numpy().astype(np.float64)
    lat = scored_cells["lat"].to_numpy().astype(np.float64)

    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "arm": "model",
        "version": args.version,
        "corpus": str(corpus),
        "quantities": list(quantities),
        "n_cells": len(cell_ids),
        "n_points": len(points),
        "n_pairs": int(dtrue.shape[0] * dtrue.shape[1]),
        "n_features": len(names),
        "features": names,
        "treeless_bookkeeping": scorable_pairs(dtrue, quantities),
        "model": {"kind": "LGBMRegressor", "one_per_quantity": True, "params": PARAMS},
        "by_blocking": {},
    }
    if args.placebos_only and not args.centred:
        raise SystemExit("--placebos-only has a meaning only with --centred")
    if args.centred:
        report["cache"] = str(cache)
        return main_centred(
            args,
            report,
            x=x,
            names=names,
            dtrue=dtrue,
            control=control,
            scored_cells=scored_cells,
            points=points,
        )

    for degrees in (args.degrees, args.also_degrees):
        folds = blocked_spatial_folds(lon, lat, k=args.k, degrees=degrees, seed=42)
        assert_no_leakage(names, folds, len(cell_ids))
        print(f"\n=== blocking {degrees:g} deg, {len(np.unique(folds))} folds ===", flush=True)

        dpred = fit_predict_oof(x, dtrue, folds, quantities)
        model_score = _per_level_and_pooled(dpred, dtrue, points, quantities)
        nulls = derive_nulls(
            dtrue,
            control,
            scored_cells,
            points,
            quantities=quantities,
            k=args.k,
            degrees=degrees,
        )
        decision = decide(model_score, nulls, threshold=args.threshold)
        report["by_blocking"][f"{degrees:g}deg"] = {  # type: ignore[index]
            "blocking_degrees": degrees,
            "k_folds": args.k,
            "model": model_score,
            "nulls": nulls,
            "decision": decision,
        }
        print(f"  model pooled      {decision['model_pooled']:+.6f}")
        print(f"  best null         {decision['best_null']} {decision['best_null_value']:+.6f}")
        print(f"  margin            {decision['margin_model_minus_best_null']:+.6f}")
        print(f"  needs             > {decision['required_model_value']:.6f}")
        print(f"  VERDICT           {decision['verdict']}")

    primary = report["by_blocking"][f"{args.degrees:g}deg"]  # type: ignore[index]
    report["decision"] = primary["decision"]
    # The flat block `tools/append_result.py` reads. Built from the PRIMARY blocking only: the
    # 5-degree arm is a pre-declared sensitivity check and is reported beside it, never as the
    # number of record.
    report.update(
        append_result_block(
            statistic="skill_response_mean",
            arms={
                "model": float(primary["model"]["pooled"]),
                **{n: float(v["pooled"]) for n, v in primary["nulls"].items()},
            },
            n=int(report["n_pairs"]),  # type: ignore[arg-type]
        )
    )
    (out / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / 'metrics.json'}")

    print("\n=== per quantity (primary blocking) ===")
    for q, v in primary["model"]["per_quantity"].items():
        print(f"  {q:20s} {v:+.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
