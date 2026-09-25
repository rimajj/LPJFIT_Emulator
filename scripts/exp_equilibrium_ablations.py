#!/usr/bin/env python
"""THE TWO OWED FOLLOW-UPS TO THE CLIMATE-ONLY EQUILIBRIUM MAP, as paired comparisons.

    scripts/exp_equilibrium_ablations.py --study soil  --stage placebo --out <dir>    # pre-seal
    scripts/exp_equilibrium_ablations.py --study soil  --stage model --threshold <sealed> \
        --exp-id <id> --out <dir>
    scripts/exp_equilibrium_ablations.py --study curve --stage placebo --out <dir>    # pre-seal
    scripts/exp_equilibrium_ablations.py --study curve --stage model --threshold <sealed> \
        --exp-id <id> --out <dir>

`X-20260923-equilibrium-from-climate` passed at 0.607582: from a run's 30-year climate, its soil
depth and its soil texture, a model explains 0.608 of the variation in the settled forest at
held-out 15-degree tiles. Its verdict names two things it did not measure, and this script measures
both, with every arm fitted by the SEALED recipe except for the one thing each arm changes
(`exp_equilibrium_map.Recipe`), on the same folds, scored on the same rows by the same `score_arm`.

SOIL -- does soil texture add skill? The statistic is a PAIRED DIFFERENCE,
    gain = S(sealed recipe) - S(the same recipe without the five soil-texture columns),
because the gate's comparators compare a model with nulls whose values are known BEFORE the run,
and "the model without soil" cannot be known before the run without running the answer. So the
difference itself is the estimand (`model_absolute`), and its nulls are differences too:
    no_soil_texture            the ablated recipe against itself: exactly 0, analytic
    soil_texture_permuted_max  the LARGEST gain that five uninformative soil assignments buy -- the
                               same five columns, each cell handed another cell's whole soil vector
                               (five fixed shuffles). What adding five cell-constant columns buys by
                               chance, which a real soil effect has to exceed.

CURVE -- is skill still rising at 100 % of the training cells? Each training fold is subsampled to
25 / 50 / 75 % of its cells (whole cells, nested per seed), the held-out cells unchanged. The
statistic is the last step of the curve,
    gain = S(100 %) - mean over seeds 1-5 of S(75 %),
and its nulls:
    no_further_gain   the 100 % recipe against itself: exactly 0, analytic
    subsample_noise   |mean S(75 %) over seeds 1-5 - mean over seeds 6-10|: how far two estimates of
                      the SAME quantity land apart by the luck of the subsample alone.

⚠ THE PLACEBO STAGE NEVER WRITES A LEVEL. It fits the ablated or subsampled recipes to derive the
placebo nulls before the seal, and writes ONLY their differences: the level of the no-soil recipe
or of the 75 % curve, beside the already-known 0.607582, would be the answer itself.

⚠ ONE THREAD PER FIT, SO THE SEALED NUMBER REPRODUCES -- AND OMP_NUM_THREADS DOES NOT DO IT.
The sealed run fitted on one CPU. LightGBM's scikit-learn wrapper turns `n_jobs=None` (what PARAMS
leaves it at) into the number of physical cores in the process's CPU AFFINITY, ignoring
OMP_NUM_THREADS. The first launch of this script trusted that variable: every worker ran 12
threads on 12 shared cores, ~10x slower than one thread, and not the sealed arithmetic. So each
worker is now PINNED to one CPU of the job's allocation, the thread count every fit saw is recorded
in the output, and the sealed recipe's score must come back as 0.6075822354370696 at 15 deg: that
is the apparatus check the model stage reports.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl

from exp_equilibrium_map import (
    QUANTITIES,
    Recipe,
    assert_constant,
    load,
    model_predictions,
    score_arm,
)
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import blocked_spatial_folds

Array = npt.NDArray[np.float64]

SEALED_SCORE = {"15deg": 0.6075822354370696, "5deg": 0.6102604219342509}  # job 2280571
PERMUTE_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
FRACTIONS: tuple[float, ...] = (0.25, 0.5, 0.75)
CURVE_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
NOISE_SEEDS: tuple[int, ...] = (6, 7, 8, 9, 10)
STATISTIC = {"soil": "skill_gain_soil_texture", "curve": "skill_gain_last_quarter"}

_SHARED: dict[str, object] = {}


def _init(
    x: Array, y: Array, folds: dict[str, npt.NDArray[np.int64]], slots: object = None
) -> None:
    """Share the arrays with a worker and, in a pool, pin it to ONE CPU (see the docstring)."""
    if slots is not None:
        os.sched_setaffinity(0, {slots.get()})  # type: ignore[attr-defined]
    _SHARED.update(x=x, y=y, folds=folds)


def _fit(task: tuple[str, Recipe]) -> tuple[str, Recipe, Array, int]:
    radius, recipe = task
    x, y = _SHARED["x"], _SHARED["y"]
    folds: dict[str, npt.NDArray[np.int64]] = _SHARED["folds"]  # type: ignore[assignment]
    pred = model_predictions(x, y, folds[radius], recipe)  # type: ignore[arg-type]
    return radius, recipe, pred, len(os.sched_getaffinity(0))


def recipes(study: str, stage: str) -> list[Recipe]:
    """Every recipe a (study, stage) fits. The placebo stage is a strict subset of the model's."""
    if study == "soil":
        out = [Recipe(drop_soil=True)] + [Recipe(permute_soil_seed=s) for s in PERMUTE_SEEDS]
    else:
        out = [Recipe(train_cell_frac=0.75, subsample_seed=s) for s in CURVE_SEEDS + NOISE_SEEDS]
        if stage == "model":
            out += [
                Recipe(train_cell_frac=f, subsample_seed=s)
                for f in FRACTIONS[:-1]
                for s in CURVE_SEEDS
            ]
    return [*out, Recipe()] if stage == "model" else out


def fit_all(
    x: Array, y: Array, folds: dict[str, npt.NDArray[np.int64]], todo: list[Recipe], nproc: int
) -> tuple[dict[tuple[str, Recipe], Array], list[int]]:
    """Every (radius, recipe) prediction, each fitted on ONE CPU, and the CPU count each fit saw.

    With `nproc <= 1` the fits run in this process, on however many CPUs it has -- which is one
    only if the job was given one.
    """
    tasks = [(r, rec) for r in folds for rec in todo]
    cpus = sorted(os.sched_getaffinity(0))
    nproc = min(nproc, len(cpus))
    print(f"{len(tasks)} fits on {nproc} processes", flush=True)
    if nproc <= 1:
        _init(x, y, folds)
        done = [_fit(t) for t in tasks]
    else:
        # Spawn, not fork: polars' thread pool is not fork-safe (see exp_derive_nulls_pilot.decode).
        ctx = mp.get_context("spawn")
        slots = ctx.Queue()
        for c in cpus[:nproc]:
            slots.put(c)
        with ctx.Pool(nproc, initializer=_init, initargs=(x, y, folds, slots)) as pool:
            done = pool.map(_fit, tasks, chunksize=1)
    return {(r, rec): p for r, rec, p, _ in done}, sorted({n for *_, n in done})


def _diff(a: dict[str, object], b: dict[str, object]) -> dict[str, object]:
    """`a - b` on the pooled score, per quantity and per level -- differences only, never levels."""
    pq_a: dict[str, float] = a["per_quantity"]  # type: ignore[assignment]
    pq_b: dict[str, float] = b["per_quantity"]  # type: ignore[assignment]
    pl_a: dict[str, float] = a["per_level"]  # type: ignore[assignment]
    pl_b: dict[str, float] = b["per_level"]  # type: ignore[assignment]
    return {
        "pooled": float(a["pooled"]) - float(b["pooled"]),  # type: ignore[arg-type]
        "per_quantity": {q: pq_a[q] - pq_b[q] for q in pq_a},
        "per_level": {p: pl_a[p] - pl_b[p] for p in pl_a},
    }


def _spread(values: list[float]) -> dict[str, float]:
    v = np.asarray(values)
    return {
        "max": float(v.max()),
        "min": float(v.min()),
        "mean": float(v.mean()),
        "sd": float(v.std(ddof=1)),
    }


def soil_report(scored: dict[Recipe, dict[str, object]], stage: str) -> dict[str, object]:
    base = scored[Recipe(drop_soil=True)]
    placebo = {s: _diff(scored[Recipe(permute_soil_seed=s)], base) for s in PERMUTE_SEEDS}
    gains = [float(v["pooled"]) for v in placebo.values()]  # type: ignore[arg-type]
    out: dict[str, object] = {
        "placebo_gain_per_seed": placebo,
        "placebo_gain_pooled": _spread(gains),
        "arms": {"no_soil_texture": 0.0, "soil_texture_permuted_max": max(gains)},
    }
    if stage == "model":
        full = scored[Recipe()]
        out["levels"] = {
            "sealed_recipe": full,
            "no_soil_texture": base,
            **{
                f"soil_permuted_seed{s}": scored[Recipe(permute_soil_seed=s)] for s in PERMUTE_SEEDS
            },
        }
        out["gain"] = _diff(full, base)
        band_f: dict[str, float] = full["band"]["per_quantity"]  # type: ignore[index]
        band_b: dict[str, float] = base["band"]["per_quantity"]  # type: ignore[index]
        out["band_gain"] = {
            "conjunctive": full["band"]["conjunctive"] - base["band"]["conjunctive"],  # type: ignore[index]
            "per_quantity": {q: band_f[q] - band_b[q] for q in band_f},
        }
        # The no-soil recipe against itself, computed rather than typed.
        out["arms"] = {
            "model": float(out["gain"]["pooled"]),  # type: ignore[index]
            "no_soil_texture": float(base["pooled"]) - float(base["pooled"]),  # type: ignore[arg-type]
            "soil_texture_permuted_max": max(gains),
        }
    return out


def curve_report(scored: dict[Recipe, dict[str, object]], stage: str) -> dict[str, object]:
    def pooled(f: float, seeds: tuple[int, ...]) -> list[float]:
        return [float(scored[Recipe(train_cell_frac=f, subsample_seed=s)]["pooled"]) for s in seeds]  # type: ignore[arg-type]

    s75, s75b = pooled(0.75, CURVE_SEEDS), pooled(0.75, NOISE_SEEDS)
    noise = abs(float(np.mean(s75)) - float(np.mean(s75b)))
    out: dict[str, object] = {
        "subsample_noise": noise,
        "sd_of_ten_75pct_seeds": float(np.std(s75 + s75b, ddof=1)),
        "arms": {"no_further_gain": 0.0, "subsample_noise": noise},
    }
    if stage == "model":
        full = float(scored[Recipe()]["pooled"])  # type: ignore[arg-type]
        curve: dict[str, object] = {}
        for f in FRACTIONS:
            vals = pooled(f, CURVE_SEEDS)
            per_q = {
                q: float(
                    np.mean(
                        [
                            scored[Recipe(train_cell_frac=f, subsample_seed=s)]["per_quantity"][q]  # type: ignore[index]
                            for s in CURVE_SEEDS
                        ]
                    )
                )
                for q in QUANTITIES
            }
            curve[f"{f:g}"] = {"per_seed": vals, **_spread(vals), "per_quantity_mean": per_q}
        curve["1"] = {
            "per_seed": [full],
            "mean": full,
            "per_quantity": scored[Recipe()]["per_quantity"],
        }
        out["curve"] = curve
        m = {f: float(np.mean(pooled(f, CURVE_SEEDS))) for f in FRACTIONS}
        out["gain_per_doubling"] = {"25_to_50": m[0.5] - m[0.25], "50_to_100": full - m[0.5]}
        out["arms"] = {
            "model": full - m[0.75],
            "no_further_gain": full - full,
            "subsample_noise": noise,
        }
    return out


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", choices=("soil", "curve"), required=True)
    ap.add_argument("--stage", choices=("placebo", "model"), required=True)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--also-degrees", type=float, default=5.0)
    ap.add_argument("--nproc", type=int, default=1)
    ap.add_argument("--threshold", type=float, help="the SEALED pass margin (model stage only)")
    ap.add_argument("--exp-id", default="")
    args = ap.parse_args()
    if args.stage == "model" and args.threshold is None:
        ap.error("--threshold is required for the model stage: it must match the sealed rule")
    return args


def main() -> int:
    args = _parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(str(paths()["scratch"]["corpus"]))
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    _, x, y, raw, points, lon, lat = load(
        pl.read_parquet(root / args.version / "corpus.parquet"), soil_bin
    )
    assert_constant(y)
    folds = {
        f"{d:g}deg": blocked_spatial_folds(lon, lat, k=args.k, degrees=d, seed=42)
        for d in (args.degrees, args.also_degrees)
    }
    todo = recipes(args.study, args.stage)
    preds, cpus_per_fit = fit_all(x, y, folds, todo, args.nproc)

    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "study": args.study,
        "stage": args.stage,
        "statistic": STATISTIC[args.study],
        "version": args.version,
        "n_cells": int(y.shape[0]),
        "n_rows": int(y.shape[0] * y.shape[1]),
        "recipes": [asdict(r) for r in todo],
        "cpus_visible_to_each_fit": cpus_per_fit,
        "by_blocking": {},
    }
    build = soil_report if args.study == "soil" else curve_report
    for radius in folds:
        scored = {rec: score_arm(preds[(radius, rec)], y, raw, points) for rec in todo}
        block = build(scored, args.stage)
        if args.stage == "model":
            sealed = float(scored[Recipe()]["pooled"])  # type: ignore[arg-type]
            block["apparatus_sealed_recipe"] = {
                "score": sealed,
                "sealed_value": SEALED_SCORE.get(radius),
                "abs_difference": abs(sealed - SEALED_SCORE[radius])
                if radius in SEALED_SCORE
                else None,
            }
        report["by_blocking"][radius] = block  # type: ignore[index]
        arms: dict[str, float] = block["arms"]  # type: ignore[assignment]
        print(f"\n=== {radius} ===")
        for n, v in arms.items():
            print(f"  {n:28s} {v:+.6f}")

    primary = report["by_blocking"][f"{args.degrees:g}deg"]  # type: ignore[index]
    if args.stage == "model":
        arms = primary["arms"]
        report["decision"] = {
            "model": arms["model"],
            "threshold": args.threshold,
            "verdict": "pass" if arms["model"] > args.threshold else "fail",
        }
        report.update(
            append_result_block(
                statistic=STATISTIC[args.study], arms=dict(arms), n=int(report["n_rows"])
            )  # type: ignore[arg-type]
        )
    name = "metrics.json" if args.stage == "model" else "placebo.json"
    (out / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
