#!/usr/bin/env python
"""Fit the emulator and score every arm of both sealed experiments.

    NCPUS=16 PARTITION=priority TIME=02:00:00 scripts/sbatch_py.sh \\
        --exp X-20260908-climate-state-map T-map-v0 scripts/train_emulator.py --version v0

One script runs BOTH experiments because they share the same fitted heads: the map test scores the
model's state prediction on the historical climate, and the response test differences that same
model's answers for the historical and the high-emissions climate of each cell. Fitting twice would
let fitting noise leak into the difference, which is the quantity the kill test is about.

WHAT IS WRITTEN, and why it is split in two
    <scratch.exp>/<exp_id>/metrics.json
                      the append_result-shaped file for ONE experiment, carrying the
                      `prereg_sha256` the LAUNCHER stamped into this job. That stamp is the whole
                      point: it proves which version of the pre-registration governed the run, so
                      a later edit is detectable rather than invisible. The launcher stamps one
                      hash per job, so `--only` selects which experiment this run is reporting and
                      the script is submitted once per sealed experiment.
    diagnostics.json  the full combined report: both experiments, per-quantity breakdowns, the
                      5-degree block sensitivity check, feature importances. Not a result row --
                      the material a verdict's prose and the figures are built from.
    oof_map.parquet, oof_response.parquet
                      the full out-of-fold prediction and truth, per cell. Kept because a verdict
                      that cannot be re-plotted cannot be checked.

The model never sees latitude, longitude, a cell id, CO2, or any state -- the pre-registrations'
leakage checks, asserted here before fitting rather than promised.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu import nulls as null_mod
from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.dataset import assemble, load_leg, response_pair
from vegemu.models import EmulatorConfig, fit_out_of_fold
from vegemu.paths import paths
from vegemu.score import (
    RESPONSE_QUANTITIES,
    SCORED_CONJUNCTIVE,
    band_frac_conjunctive,
    band_frac_per_quantity,
    describe_basis,
    skill_response_mean,
    skill_vs_no_change,
)

SHUFFLE_SEED = 20260908  # must match scripts/exp_derive_nulls.py, or the nulls are not the nulls
MAP_EXP = "X-20260908-climate-state-map"
RESPONSE_EXP = "X-20260908-warming-response"
FORBIDDEN = ("lon", "lat", "cell", "co2", "stems", "agb", "wooddens", "seed", "year")


def assert_no_leakage() -> None:
    """The pre-registrations' leakage checks, executed. A promise in YAML is not a check."""
    for name in CLIMATE_FEATURES:
        low = name.lower()
        for bad in FORBIDDEN:
            if bad in low:
                raise AssertionError(
                    f"feature {name!r} contains {bad!r}: that is a null or a target, not an input"
                )
    print(f"leakage: {len(CLIMATE_FEATURES)} features, none containing "
          f"{'/'.join(FORBIDDEN)}", flush=True)


def _analogue(features: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    idx = [CLIMATE_FEATURES.index(n) for n in null_mod.ANALOGUE_FEATURES]
    return features[:, idx]


def oof_nulls(
    lon: npt.NDArray[np.float64],
    lat: npt.NDArray[np.float64],
    features: npt.NDArray[np.float64],
    folds: npt.NDArray[np.int64],
    y: npt.NDArray[np.float64],
) -> dict[str, npt.NDArray[np.float64]]:
    """Out-of-fold predictions of every null. Identical code path to the derivation script."""
    xa = _analogue(features)
    names = ("climatological_mean", "geographic_address", "nearest_analogue", "shuffled_target")
    out = {name: np.full_like(y, np.nan) for name in names}
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        out["climatological_mean"][te] = null_mod.training_mean(y[tr], int(te.sum()))
        out["geographic_address"][te] = null_mod.nearest_geographic(
            lon[tr], lat[tr], y[tr], lon[te], lat[te]
        )
        out["nearest_analogue"][te] = null_mod.nearest_analogue(xa[tr], y[tr], xa[te])
        out["shuffled_target"][te] = null_mod.shuffled(y[te], SHUFFLE_SEED + int(f))
    return out


def run(version: str, block_degrees: float, k: int, out: Path) -> dict[str, object]:
    hist = load_leg("historical", version)
    ssp = load_leg("ssp370", version)

    # ---- the map experiment ---------------------------------------------------------------
    a = assemble(hist, SCORED_CONJUNCTIVE, k=k, block_degrees=block_degrees)
    print(f"\nmap: {a.n} cells, {len(SCORED_CONJUNCTIVE)} quantities, {k} folds "
          f"at {block_degrees} deg", flush=True)
    t0 = time.time()
    (pred_map,), models = fit_out_of_fold(
        a.features, a.truth, a.folds, SCORED_CONJUNCTIVE, [a.features], config=EmulatorConfig()
    )
    print(f"  fitted in {time.time() - t0:.0f} s", flush=True)

    null_map = oof_nulls(a.lon, a.lat, a.features, a.folds, a.truth)
    map_arms = {"model": band_frac_conjunctive(pred_map, a.truth, a.band)}
    map_arms.update(
        {name: band_frac_conjunctive(p, a.truth, a.band) for name, p in null_map.items()}
    )
    map_per_q = {"model": band_frac_per_quantity(pred_map, a.truth, a.band, SCORED_CONJUNCTIVE)}
    map_per_q.update(
        {
            name: band_frac_per_quantity(p, a.truth, a.band, SCORED_CONJUNCTIVE)
            for name, p in null_map.items()
        }
    )
    print("  band_frac_conjunctive:")
    for name, v in sorted(map_arms.items(), key=lambda kv: -kv[1]):
        print(f"    {name:22s} {v:.6f}")

    frame = {"cell": a.cells, "lon": a.lon, "lat": a.lat, "fold": a.folds}
    for j, q in enumerate(SCORED_CONJUNCTIVE):
        frame[f"truth_{q}"] = a.truth[:, j]
        frame[f"band_{q}"] = a.band[:, j]
        frame[f"pred_{q}"] = pred_map[:, j]
        frame[f"addr_{q}"] = null_map["geographic_address"][:, j]
        frame[f"analog_{q}"] = null_map["nearest_analogue"][:, j]
    pl.DataFrame(frame).write_parquet(out / "oof_map.parquet")

    # ---- the response experiment --------------------------------------------------------
    base, future, delta = response_pair(
        hist, ssp, RESPONSE_QUANTITIES, k=k, block_degrees=block_degrees
    )
    print(f"\nresponse: {base.n} cells tree-bearing in both legs", flush=True)
    # Fitted on the HISTORICAL leg only; the ssp370 state is never a training target.
    if base.truth.shape != future.truth.shape:
        raise AssertionError("the two legs are not aligned")
    t0 = time.time()
    (pred_base, pred_future), _ = fit_out_of_fold(
        base.features, base.truth, base.folds, RESPONSE_QUANTITIES,
        [base.features, future.features], config=EmulatorConfig(),
    )
    print(f"  fitted in {time.time() - t0:.0f} s", flush=True)
    pred_delta = pred_future - pred_base

    null_delta = oof_nulls(base.lon, base.lat, base.features, base.folds, delta)
    resp_arms = {
        "model": skill_response_mean(pred_delta, delta),
        "no_response": skill_response_mean(np.zeros_like(delta), delta),
        "mean_response": skill_response_mean(null_delta["climatological_mean"], delta),
        "geographic_address_response": skill_response_mean(
            null_delta["geographic_address"], delta
        ),
        "shuffled_response": skill_response_mean(null_delta["shuffled_target"], delta),
    }
    resp_per_q = {
        "model": dict(zip(RESPONSE_QUANTITIES,
                          [float(v) for v in skill_vs_no_change(pred_delta, delta)], strict=True)),
        "analogue_response": dict(
            zip(RESPONSE_QUANTITIES,
                [float(v) for v in skill_vs_no_change(null_delta["nearest_analogue"], delta)],
                strict=True)
        ),
    }
    print("  skill_response_mean:")
    for name, v in sorted(resp_arms.items(), key=lambda kv: -kv[1]):
        print(f"    {name:30s} {v:+.6f}")

    rframe = {"cell": base.cells, "lon": base.lon, "lat": base.lat, "fold": base.folds}
    for j, q in enumerate(RESPONSE_QUANTITIES):
        rframe[f"base_truth_{q}"] = base.truth[:, j]
        rframe[f"future_truth_{q}"] = future.truth[:, j]
        rframe[f"delta_truth_{q}"] = delta[:, j]
        rframe[f"delta_pred_{q}"] = pred_delta[:, j]
        rframe[f"base_pred_{q}"] = pred_base[:, j]
        rframe[f"future_pred_{q}"] = pred_future[:, j]
    pl.DataFrame(rframe).write_parquet(out / "oof_response.parquet")

    # ---- feature importance, as a diagnostic only ----------------------------------------
    imp = models[0].importances()
    total = np.zeros(len(CLIMATE_FEATURES))
    for values in imp.values():
        s = values.sum()
        if s > 0:
            total += values / s
    order = np.argsort(-total)[:15]
    top = {CLIMATE_FEATURES[int(i)]: float(total[int(i)] / len(imp)) for i in order}

    return {
        "corpus_version": version,
        "split": {"kind": "blocked_spatial", "k": k, "block_degrees": block_degrees,
                  "fold_seed": 42},
        "shuffle_seed": SHUFFLE_SEED,
        "hyperparameters": EmulatorConfig().__dict__,
        "map": {
            "exp_id": MAP_EXP,
            "statistic": "band_frac_conjunctive",
            "n_cells": a.n,
            "basis": describe_basis("historical", 1999, (1970, 1999), a.n),
            "arms": map_arms,
            "per_quantity": map_per_q,
        },
        "response": {
            "exp_id": RESPONSE_EXP,
            "statistic": "skill_response_mean",
            "n_cells": base.n,
            "basis": describe_basis("historical->ssp370", 2100, (2071, 2100), base.n),
            "arms": resp_arms,
            "per_quantity": resp_per_q,
        },
        "top_features_by_mean_gain_share": top,
    }


def write_result_metrics(report: dict[str, object], section: str) -> Path:
    """The append_result-shaped file for one experiment, carrying the launcher's own stamp.

    `VEGEMU_PREREG_SHA256` is read from the ENVIRONMENT, never recomputed from the working tree:
    recomputing it would make the row agree with whatever the pre-registration says now, which is
    exactly the check it exists to perform.
    """
    block = dict(report[section])  # type: ignore[arg-type]
    exp_id = str(block["exp_id"])
    stamp = os.environ.get("VEGEMU_PREREG_SHA256", "")
    if not stamp:
        print(
            f"WARNING no VEGEMU_PREREG_SHA256 in the environment, so {exp_id}'s metrics file "
            "cannot prove which pre-registration governed this run. Submit through "
            "scripts/sbatch_py.sh --exp <id>.",
            file=sys.stderr,
        )
    dest = Path(str(paths()["scratch"]["exp"])) / exp_id
    dest.mkdir(parents=True, exist_ok=True)
    payload = {
        "prereg_sha256": stamp,
        "statistic": block["statistic"],
        "n": block["n_cells"],
        "job_ids": [int(os.environ["SLURM_JOB_ID"])] if os.environ.get("SLURM_JOB_ID") else [],
        "arms": block["arms"],
        "reference_basis": block["basis"],
        "per_quantity": block["per_quantity"],
    }
    path = dest / "metrics.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"wrote {path}  (stamp {stamp[:12] or 'MISSING'})")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--block-degrees", type=float, default=15.0)
    ap.add_argument("--sensitivity-degrees", type=float, default=5.0)
    ap.add_argument(
        "--only",
        choices=("map", "response"),
        default=None,
        help="which sealed experiment this run reports; the launcher stamps one hash per job",
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    assert_no_leakage()
    root = Path(args.out) if args.out else Path(str(paths()["scratch"]["exp"])) / "map-response-v0"
    root.mkdir(parents=True, exist_ok=True)

    report = run(args.version, args.block_degrees, args.k, root)

    # The pre-declared sensitivity check. Reported beside the primary number, never instead of it:
    # a tighter block is an EASIER test, because the nearest training cell is closer.
    print(f"\n=== sensitivity: {args.sensitivity_degrees} deg blocks ===", flush=True)
    sens_dir = root / f"blocks_{int(args.sensitivity_degrees)}deg"
    sens_dir.mkdir(parents=True, exist_ok=True)
    sens = run(args.version, args.sensitivity_degrees, args.k, sens_dir)
    report["sensitivity_blocks"] = {
        "block_degrees": args.sensitivity_degrees,
        "map_arms": sens["map"]["arms"],  # type: ignore[index]
        "response_arms": sens["response"]["arms"],  # type: ignore[index]
    }

    (root / "diagnostics.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nwrote {root / 'diagnostics.json'}")
    if args.only:
        write_result_metrics(report, args.only)
    else:
        print(
            "\nNo --only given, so no stamped result file was written. Submit once per sealed "
            "experiment:\n"
            "  scripts/sbatch_py.sh --exp X-20260908-climate-state-map  T-map-v0      "
            "scripts/train_emulator.py --only map\n"
            "  scripts/sbatch_py.sh --exp X-20260908-warming-response   T-response-v0 "
            "scripts/train_emulator.py --only response",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
