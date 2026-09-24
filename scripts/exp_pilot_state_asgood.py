"""The owner's pass rule on the FULL forest state: is the emulator as good as a rerun on the pilot?

THE QUESTION (owner, 2026-09-24): acceptance means tree counts AND trait distributions AND trait
medians inside max(10 %, the model's own two-run spread), per cell, and the emulator passes if it
does so as often as a SECOND RUN of the original model does ("as good as a rerun"). The stored
spin-up kept only vegetation carbon for its constant-CO2 years (`exp_spinup_vegc.py`), so the full
state can only be tested where both seeds of a constant-CO2 spin-up exist: the pilot, 200 cells x
30 climates, now with its full second seed.

THE ESTIMAND, per (cell, climate) row, on the 19 varying quantities of SCORED_CONJUNCTIVE (the three
fine-root-conductivity quantiles are one constant value and pass any arm, so they are left out):
  truth    T_k = seed k's end-of-spin-up state, k = 1, 2
  band     w = spread_across_climates(seed1, seed2): per quantity max(0.10, the median two-seed
           relative spread over the cell's OTHER 29 climates) -- so the pair being scored never sets
           its own tolerance
  pass     every quantity the truth defines is inside |x - T_k| <= w |T_k| (a trait of a treeless
           truth is not scored; a trait the arm leaves undefined where the truth has one fails)
  frac(x)  the mean over rows of the mean over k of pass; frac(rerun) scores T_2 against T_1 and T_1
           against T_2
  D(x)     frac(x) - frac(rerun); "as good as a rerun" is D >= -0.02 (pre-registered)

The model arm is the emulator's EMITTED prediction: the post-processed out-of-fold `pred_` heads of
the saved climate-only map (models/equimap-v1/oof_pilot.parquet: clipped, quantile-sorted, traits
blank where it predicts no trees). Its raw heads are reported beside.
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

from exp_equilibrium_map import NULLS, QUANTITIES, inverse, load, null_predictions
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import SCORED_VARYING, blocked_spatial_folds, spread_across_climates

Array = npt.NDArray[np.float64]

STATISTIC = "asgood_state_pilot"
VARYING = [QUANTITIES.index(q) for q in SCORED_VARYING]


def row_pass(pred: Array, truth: Array, w: Array) -> Array:
    """(cells, points) 0/1: every varying quantity the truth defines is inside the band."""
    scored = np.isfinite(truth)
    inside = np.abs(pred - truth) <= w * np.abs(truth)
    inside &= np.isfinite(pred)
    return np.all(inside | ~scored, axis=2).astype(np.float64)


def score(pred: Array, t1: Array, t2: Array, w: Array, rerun: Array) -> dict[str, object]:
    per_row = (row_pass(pred, t1, w) + row_pass(pred, t2, w)) / 2
    frac = float(per_row.mean())
    per_q = {}
    for j, q in enumerate(SCORED_VARYING):
        rates = []
        for t in (t1, t2):
            ok = np.isfinite(t[:, :, j])
            hit = np.abs(pred[:, :, j] - t[:, :, j]) <= w[:, :, j] * np.abs(t[:, :, j])
            rates.append(float((hit & np.isfinite(pred[:, :, j]))[ok].mean()))
        per_q[q] = float(np.mean(rates))
    treed = np.isfinite(t1[:, :, SCORED_VARYING.index("height_p50")]) & np.isfinite(
        t2[:, :, SCORED_VARYING.index("height_p50")]
    )
    return {
        "D": frac - float(rerun.mean()),
        "frac": frac,
        "frac_tree_bearing_both_seeds": float(per_row[treed].mean()),
        "per_quantity_band_rate": per_q,
    }


def _truth(
    frame: pl.DataFrame, soil_bin: Path
) -> tuple[Array, Array, Array, list[str], Array, Array]:
    _, x, y, raw, points, lon, lat = load(frame, soil_bin)
    return x, y, raw[:, :, VARYING], points, lon, lat


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arm", required=True, choices=("nulls", "model"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--exp-id", default="")
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    corpus = Path(str(paths()["scratch"]["corpus"]))
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    s1 = pl.read_parquet(corpus / "pilot-v2-constco2" / "corpus.parquet")
    s2 = pl.read_parquet(corpus / "pilot-v2-constco2-s2" / "replicate_s2.parquet")
    x, y1, t1, points, lon, lat = _truth(s1, soil_bin)
    _, _, t2, points2, lon2, lat2 = _truth(s2, soil_bin)
    assert points == points2 and np.array_equal(lon, lon2) and np.array_equal(lat, lat2)
    cells = s1.sort(["cell", "point"])["cell"].unique().sort().to_numpy()

    w = spread_across_climates(np.nan_to_num(t1, nan=0.0), np.nan_to_num(t2, nan=0.0))
    rerun = (row_pass(t2, t1, w) + row_pass(t1, t2, w)) / 2
    folds = blocked_spatial_folds(lon, lat, k=5, degrees=15.0, seed=42)

    arms: dict[str, Array] = {}
    if args.arm == "nulls":
        for name, z in null_predictions(x, y1, folds, lon, lat).items():
            nat = np.stack([inverse(q, z[:, :, j]) for j, q in enumerate(QUANTITIES)], axis=2)
            arms[name] = nat[:, :, VARYING]
    else:
        oof = pl.read_parquet(
            Path(str(paths()["scratch"]["models"])) / "equimap-v1" / "oof_pilot.parquet"
        )
        oof = oof.sort(["cell", "point"])
        assert np.array_equal(oof["cell"].unique().sort().to_numpy(), cells)
        assert (oof["fold"].to_numpy().reshape(len(cells), len(points))[:, 0] == folds).all()
        for prefix in ("pred_", "raw_"):
            a = np.stack(
                [
                    oof[prefix + q].to_numpy().astype(np.float64).reshape(len(cells), len(points))
                    for q in SCORED_VARYING
                ],
                axis=2,
            )
            arms["model" if prefix == "pred_" else "model_raw_heads"] = a

    scored = {n: score(p, t1, t2, w, rerun) for n, p in arms.items()}
    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "arm": args.arm,
        "statistic": STATISTIC,
        "rows": int(t1.shape[0] * t1.shape[1]),
        "frac_rerun": float(rerun.mean()),
        "band_is_floor_share": float((w == 0.10).mean()),
        "quantities": list(SCORED_VARYING),
        "arm_details": scored,
    }
    for n, a in scored.items():
        print(f"  {n:20s} D {a['D']:+.6f}  frac {a['frac']:.4f}")  # type: ignore[index]
    print(f"  rerun frac {float(rerun.mean()):.6f}")
    if args.arm == "model":
        prior = json.loads((out / "nulls.json").read_text())["arm_details"]
        report["decision"] = {"D": scored["model"]["D"], "threshold": args.threshold}
        report.update(
            append_result_block(
                statistic=STATISTIC,
                arms={
                    "model": float(scored["model"]["D"]),
                    **{n: float(prior[n]["D"]) for n in NULLS},
                },  # type: ignore[index]
                n=int(t1.shape[0] * t1.shape[1]),
            )
        )
    name = "metrics.json" if args.arm == "model" else "nulls.json"
    (out / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
