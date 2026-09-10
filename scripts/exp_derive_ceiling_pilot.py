#!/usr/bin/env python
"""What is the MOST a perfect emulator could score on the pilot kill test, and is the bar reachable?

    scripts/exp_derive_ceiling_pilot.py --state <pilot state parquet> --out <dir>

WHY THIS HAS TO EXIST, AND WHY IT IS LATE. `X-20260909-pilot-warming-response` was sealed with a bar
of 0.225690 and no statement of what perfect means. That is the same omission line T caught in the
drift test -- a conjunctive pass rate quoted against an implied 100 % when a third real model seed
only reaches 25 % -- and the same one X3 already fixed for itself, where the non-circular ceiling is
0.538490 rather than 1.0. A bar without a ceiling cannot be read: 0.225690 is either a modest ask or
an impossible one depending on a number nobody had computed.

THE ARGUMENT. LPJmL-FIT is stochastic. Write a state as X = mu + eps, with eps the model's own
realisation noise. The target is a paired contrast of two single runs,

    dtrue = X_perturbed - X_control = dmu + (eps_p - eps_0),

so the target itself carries noise. A perfect emulator predicts the noise-free dmu -- it cannot know
which realisation the truth happened to draw -- so its residual is exactly -(eps_p - eps_0) and

    ceiling = 1 - SUM Var(eps_p - eps_0) / SUM dtrue^2.

⚠ THE SEED IS SHARED, WHICH IS WHY THIS IS A BOUND AND NOT A NUMBER. Line D's design gives the
control and the perturbed arm of a cell the SAME random seed, so eps_p and eps_0 are correlated to
an unknown degree and Var(eps_p - eps_0) = 2*sigma^2*(1 - rho). Two limits are reported:

  * rho = 0 (independent noise)  -> the CONSERVATIVE ceiling, a genuine lower bound;
  * rho = 1 (the seed cancels)   -> 1.0, no penalty at all.

The truth is between, and measuring it needs a second seed for a subset of the pilot -- which is a
concrete, cheap ask of line D, costed in the record rather than left as "more data would be nice".

sigma is estimated from the only two-seed pair that exists at these cells: the ground truth's
historical seed 1 and seed 2 end-of-spin-up restarts, where (s1 - s2) has variance 2*sigma^2.

SECOND THING MEASURED HERE, because the same two reads pay for it. Nobody has checked that the
pilot's SINGLE-CELL control spin-up reproduces the GLOBAL run's state at the same cell. Line D
proved the neutral design point is a structural no-op in the FORCING bytes; that is not the same as
proving the resulting STATE matches, because the model's random stream need not be identical when it
walks 1 cell instead of 67,420. If the pilot control sits outside the ground truth's own two-seed
spread, the corpus is not measuring the same model and every number derived from it needs that
caveat. This is an apparatus check, which is line X's job.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import multiprocessing as mp

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.corpus.state import state_table
from vegemu.paths import paths
from vegemu.score import RESPONSE_QUANTITIES, matrix

CONTROL_POINT = "control"


def _read_seed(args: tuple[str, list[int]]) -> pl.DataFrame:
    path, cells = args
    return state_table(Path(path), cells=cells, nproc=1)


def ground_truth_pair(cells: list[int], nproc: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The 200 pilot cells, decoded from both historical seeds' end-of-spin-up restart.

    Two 119 GiB files, read by seek through each file's own offset table -- never scanned. Spawn,
    not fork, for the same reason the pilot derivation uses it: polars' thread pool is not fork-safe
    and a forked worker sits at zero CPU with no error.
    """
    gt = paths()["ground_truth"]
    jobs = [(str(gt["restart_spinup_end"]), cells), (str(gt["restart_spinup_end_seed2"]), cells)]
    if nproc <= 1:
        frames = [_read_seed(j) for j in jobs]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=2) as pool:
            frames = list(pool.map(_read_seed, jobs))
    return frames[0].sort("cell"), frames[1].sort("cell")


def ceiling(
    dtrue: npt.NDArray[np.float64],
    sigma_sq: npt.NDArray[np.float64],
    quantities: tuple[str, ...],
) -> dict[str, object]:
    """`1 - SUM Var(eps_p - eps_0) / SUM dtrue^2`, per quantity and as the blessed mean.

    `sigma_sq` is per (cell, quantity) and is broadcast over the 29 perturbed levels: every arm of a
    cell is one run of the same model at the same place, so it carries the same realisation noise.
    """
    n_levels = dtrue.shape[1]
    out: dict[str, object] = {}
    for rho, name in ((0.0, "rho0_independent"), (0.5, "rho0.5_partial")):
        per_q = np.full(len(quantities), np.nan)
        for j in range(len(quantities)):
            finite = np.isfinite(dtrue[:, :, j])
            ss = float((dtrue[:, :, j][finite] ** 2).sum())
            if ss <= 0:
                continue
            # One sigma^2 per (cell, level) pair that actually scored.
            noise = float(
                (np.repeat(sigma_sq[:, j][:, None], n_levels, axis=1)[finite]).sum()
                * 2.0
                * (1.0 - rho)
            )
            per_q[j] = 1.0 - noise / ss
        out[name] = {
            "mean": float(np.nanmean(per_q)),
            "per_quantity": {q: float(v) for q, v in zip(quantities, per_q, strict=True)},
        }
    return out


def control_agreement(
    pilot_control: npt.NDArray[np.float64],
    s1: npt.NDArray[np.float64],
    s2: npt.NDArray[np.float64],
    quantities: tuple[str, ...],
) -> dict[str, object]:
    """Does the single-cell pilot control land inside the global run's own two-seed spread?

    The honest comparison is not "is it close to seed 1" but "is |pilot - s1| the size of |s1-s2|".
    Two runs of the same model already disagree; the pilot only has a case to answer if it disagrees
    by MORE than that.
    """
    gap_seeds = np.abs(s1 - s2)
    gap_pilot = np.abs(pilot_control - s1)
    scale = np.where(np.abs(s1) > 0, np.abs(s1), np.nan)
    with np.errstate(invalid="ignore"):
        inside = gap_pilot <= gap_seeds
    # SIGNED, and this is the discriminating measurement. If the pilot is merely a different draw
    # of the same model its signed offset is ~0 and only the scatter grows; a signed offset that
    # survives the median is a systematic difference of protocol, not of realisation. The seed1 -
    # seed2 column is the control: it must itself be ~0, and if it is not, the reference is drifting
    # and neither comparison means what it says.
    return {
        "median_signed_pilot_minus_seed1_frac": {
            q: float(np.nanmedian((pilot_control[:, j] - s1[:, j]) / scale[:, j]))
            for j, q in enumerate(quantities)
        },
        "median_signed_seed1_minus_seed2_frac": {
            q: float(np.nanmedian((s1[:, j] - s2[:, j]) / scale[:, j]))
            for j, q in enumerate(quantities)
        },
        "median_two_seed_gap_frac": {
            q: float(np.nanmedian(gap_seeds[:, j] / scale[:, j])) for j, q in enumerate(quantities)
        },
        "median_pilot_vs_seed1_gap_frac": {
            q: float(np.nanmedian(gap_pilot[:, j] / scale[:, j])) for j, q in enumerate(quantities)
        },
        "frac_cells_pilot_within_two_seed_gap": {
            q: float(np.nanmean(inside[:, j].astype(float))) for j, q in enumerate(quantities)
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", required=True, help="decoded pilot state parquet")
    ap.add_argument("--out", required=True)
    ap.add_argument("--nproc", type=int, default=2)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    quantities = RESPONSE_QUANTITIES

    state = pl.read_parquet(args.state)
    points = [p for p in state["point"].unique().sort().to_list() if p != CONTROL_POINT]
    per_cell = state.group_by("cell").len()
    cells = sorted(per_cell.filter(pl.col("len") == len(points) + 1)["cell"].to_list())
    print(f"{len(cells)} complete pilot cells, {len(points)} perturbed levels", flush=True)

    pairs = zip(state["cell"], state["point"], strict=True)
    index = {(int(c), str(p)): i for i, (c, p) in enumerate(pairs)}
    values = matrix(state, quantities)
    dtrue = np.full((len(cells), len(points), len(quantities)), np.nan)
    pilot_control = np.full((len(cells), len(quantities)), np.nan)
    for i, cell in enumerate(cells):
        base = values[index[(cell, CONTROL_POINT)]]
        pilot_control[i] = base
        for j, point in enumerate(points):
            dtrue[i, j] = values[index[(cell, point)]] - base

    print("reading both ground-truth seeds by seek...", flush=True)
    f1, f2 = ground_truth_pair(cells, args.nproc)
    got = f1["cell"].to_list()
    if got != cells:
        raise ValueError(f"cell mismatch: ground truth returned {len(got)} of {len(cells)}")
    s1, s2 = matrix(f1, quantities), matrix(f2, quantities)

    # Var(s1 - s2) = 2 sigma^2, so sigma^2 = (s1 - s2)^2 / 2.
    sigma_sq = (s1 - s2) ** 2 / 2.0

    report = {
        "n_cells": len(cells),
        "n_levels": len(points),
        "quantities": list(quantities),
        "bar_from_prereg": 0.225690,
        "best_null_from_prereg": 0.145690,
        "ceiling": ceiling(dtrue, sigma_sq, quantities),
        "control_agreement": control_agreement(pilot_control, s1, s2, quantities),
    }
    (out / "ceiling_pilot.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    c0 = report["ceiling"]["rho0_independent"]  # type: ignore[index]
    print(f"\nCEILING, rho=0 (conservative lower bound): {c0['mean']:+.6f}")
    for q, v in c0["per_quantity"].items():
        print(f"    {q:16s} {v:+10.4f}")
    print("\nbar to pass = 0.225690; best null = 0.145690")
    print(f"reachable at rho=0? {'YES' if c0['mean'] > 0.225690 else 'NO -- the bar exceeds it'}")
    print(f"\nwrote {out / 'ceiling_pilot.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
