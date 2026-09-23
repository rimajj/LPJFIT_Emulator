#!/usr/bin/env python
"""PRODUCT A, ASKED DIRECTLY: from the 30-year climate alone, which equilibrium forest emerges?

    scripts/exp_equilibrium_map.py --arm nulls --out <dir>          # safe before the seal
    scripts/exp_equilibrium_map.py --arm model --threshold <sealed> --exp-id <id> --out <dir>

THE QUESTION (owner, 2026-09-23). The spin-up takes a 30-year climate, recycles it for 1000 years,
and the forest settles. The emulator should see ONLY those 30 climate years -- plus the cell's soil
depth and soil texture, which the spin-up also reads and which are fixed per cell -- and predict the
settled forest. No present-day forest, no location, no statement of how the climate was perturbed.

WHY THIS IS NOT THE KILL TEST. Both kill tests hand the model the cell's own control forest and ask
for the CHANGE. That is the right question for a synthesiser that edits a template restart, and the
wrong one for Product A as the owner states it: here there is no template.

WHY IT IS NOT A REPEAT OF `X-20260908-climate-state-map`. That experiment asked the same question of
the EXISTING runs, where each place has exactly one climate, so climate and place are collinear, and
its target (restart_1999) carries a CO2 ramp and the historical transient. On `pilot-v2-constco2`
every cell was spun up under 30 climates with CO2 constant, so the target is a genuine equilibrium
and climate is separable from place by construction.

WHAT IS SCORED. The 22 quantities of `SCORED_CONJUNCTIVE`, as LEVELS. The four forest-scale
quantities (stems per patch, agb, lai, soil carbon) on log1p, because they span four orders of
magnitude and a raw sum of squares would be decided by the densest few cells; the eighteen trait
quantiles as they are. Per quantity `1 - SSE / SS(truth about its pooled mean)` over every
(cell, climate) row where the truth exists; the mean over the 19 that vary is the statistic (see
CONSTANT_QUANTITIES). Folds hold out WHOLE CELLS -- all 30 of a cell's climates together -- in
whole 15-degree tiles.

Reported beside it, never instead of it, because the owner's criterion is a 10 % band: the
fraction of tree-bearing rows inside +-10 % of the truth, per quantity and on all 22 at once, and
the same two numbers for one real run of the model predicting another (the ceiling).

THE NULLS, each a deterministic function of the corpus and the folds (`vegemu.nulls` explains why):
  training_mean       the average forest of the training cells
  nearest_analogue    the forest of the climatically nearest TRAINING row, over the pre-registered
                      eight-feature analogue set -- the honest competitor: a lookup, not a model
  nearest_geographic  the forest of the nearest TRAINING cell under the SAME design climate. It
                      sees coordinates, which the model is denied, so it is the strongest address
                      null available
  shuffled            the held-out truth permuted across the held-out rows
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
from scipy.spatial import cKDTree

from exp_model_pilot_response import fit_predict_oof
from screen_d95max import soil_columns
from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import SCORED_CONJUNCTIVE, blocked_spatial_folds, unit_sphere

Array = npt.NDArray[np.float64]

STATISTIC = "skill_equilibrium_mean"
QUANTITIES = SCORED_CONJUNCTIVE
LOG_QUANTITIES: frozenset[str] = frozenset({"stems_per_patch", "agb", "lai", "soilc"})
SOIL_FEATURES: tuple[str, ...] = ("soil_code", "soil_awc", "soil_w_avail", "soil_sand", "soil_clay")
FEATURES: tuple[str, ...] = (*CLIMATE_FEATURES, *SOIL_FEATURES)
NULLS: tuple[str, ...] = ("training_mean", "nearest_analogue", "nearest_geographic", "shuffled")
BAND = 0.10
SHUFFLE_SEED = 20260923

# ⚠ FINE-ROOT CONDUCTIVITY IS ONE VALUE IN EVERY TREE-BEARING RUN OF pilot-v2-constco2 (5,620 of
# 5,620, spread ~1e-18), so "variance explained" is 0/0 for its three quantiles: it is not a trait
# that varies in this configuration, and there is nothing to predict. Excluded from the skill mean,
# which is therefore over 19 quantities; KEPT in the band rates, where every arm passes it for free
# and that is disclosed. `assert_constant` refuses the run if a future corpus makes it vary.
CONSTANT_QUANTITIES: tuple[str, ...] = ("k_root_p10", "k_root_p50", "k_root_p90")

# Never features. Asserted, not trusted: any of these would hand the model the place, the forest
# it is meant to predict, or the perturbation it is meant to infer from the climate itself.
FORBIDDEN: frozenset[str] = frozenset(
    {"cell", "lon", "lat", "tile", "point", "dtemp_k", "fprec", "sprec", "frad", "fiav"}
)


def forward(q: str, y: Array) -> Array:
    return np.log1p(np.maximum(y, 0.0)) if q in LOG_QUANTITIES else y


def inverse(q: str, z: Array) -> Array:
    return np.expm1(z) if q in LOG_QUANTITIES else z


def load(
    frame: pl.DataFrame, soil_bin: Path
) -> tuple[pl.DataFrame, Array, Array, Array, list[str], Array, Array]:
    """`(frame, x, y, y_raw, points, lon, lat)`; x (cells, points, F), y (cells, points, 22).

    Aligned by CONSTRUCTION: the frame is sorted by (cell, point) and reshaped, after asserting that
    every cell carries the identical point list -- a join whose row order had to be trusted would
    look, if it went wrong, exactly like a model with no skill.
    """
    frame = frame.sort(["cell", "point"])
    cells = frame["cell"].unique().sort().to_numpy()
    points = frame.filter(pl.col("cell") == cells[0])["point"].to_list()
    n_c, n_p = len(cells), len(points)
    assert frame.height == n_c * n_p, "every cell must carry the same climates"
    assert (frame["point"].to_numpy().reshape(n_c, n_p) == np.array(points)[None, :]).all()

    soil = soil_columns(
        frame["cell"].to_numpy().astype(np.int64), soil_bin, frame["soildepth"].to_numpy()
    )
    codes = np.fromfile(soil_bin, dtype=np.uint8)[frame["cell"].to_numpy()].astype(np.float64)
    frame = frame.with_columns(
        pl.Series("soil_code", codes),
        *(pl.Series(n, soil[:, i]) for i, n in enumerate(SOIL_FEATURES[1:])),
    )
    assert not FORBIDDEN & set(FEATURES), "a forbidden column is in the feature set"

    x = frame.select(FEATURES).to_numpy().astype(np.float64).reshape(n_c, n_p, len(FEATURES))
    treeless = frame["stems_total"].to_numpy() <= 0
    raw = frame.select(QUANTITIES).to_numpy().astype(np.float64)
    # A trait quantile at zero stems is undefined, whatever the decode wrote there.
    for j, q in enumerate(QUANTITIES):
        if q not in LOG_QUANTITIES:
            raw[treeless, j] = np.nan
    y = np.stack([forward(q, raw[:, j]) for j, q in enumerate(QUANTITIES)], axis=1)
    first = frame.filter(pl.col("point") == points[0])
    lon = first["lon"].to_numpy().astype(np.float64)
    lat = first["lat"].to_numpy().astype(np.float64)
    return (
        frame,
        x,
        y.reshape(n_c, n_p, -1),
        raw.reshape(n_c, n_p, -1),
        points,
        lon,
        lat,
    )


def skill(pred: Array, y: Array) -> Array:
    """Per quantity `1 - SSE / SS about the pooled truth mean`, over rows where the truth exists.

    A missing prediction where the truth exists is an ERROR, not a skipped row: an arm that
    declined the hard rows would otherwise be scored on an easier subset than its competitors.
    """
    p, t = pred.reshape(-1, y.shape[-1]), y.reshape(-1, y.shape[-1])
    out = np.full(t.shape[1], np.nan)
    for j in range(t.shape[1]):
        m = np.isfinite(t[:, j])
        assert np.isfinite(p[m, j]).all(), f"arm left {QUANTITIES[j]} unpredicted on scored rows"
        if QUANTITIES[j] in CONSTANT_QUANTITIES:
            continue
        ss = float(((t[m, j] - t[m, j].mean()) ** 2).sum())
        out[j] = 1.0 - float(((p[m, j] - t[m, j]) ** 2).sum()) / ss
    return out


def assert_constant(y: Array) -> None:
    """Refuse, rather than silently drop, if an excluded quantity turns out to vary."""
    t = y.reshape(-1, y.shape[-1])
    for q in CONSTANT_QUANTITIES:
        v = t[np.isfinite(t[:, QUANTITIES.index(q)]), QUANTITIES.index(q)]
        spread = float(v.max() - v.min()) if v.size else 0.0
        assert spread <= 1e-9 * max(abs(float(v.mean())), 1.0), f"{q} varies; it cannot be excluded"


def band_stats(pred: Array, raw: Array, treed: npt.NDArray[np.bool_]) -> dict[str, object]:
    """Inside +-10 % of the truth on the RAW scale, over tree-bearing rows only. Reported, not
    decided on. A NaN on either side is a miss."""
    p = np.stack(
        [inverse(q, pred.reshape(-1, len(QUANTITIES))[:, j]) for j, q in enumerate(QUANTITIES)],
        axis=1,
    )
    t = raw.reshape(-1, len(QUANTITIES))
    rows = treed.reshape(-1)
    ok = np.abs(p - t) <= BAND * np.abs(t)
    hits = np.where(np.isfinite(p) & np.isfinite(t), ok, False)[rows]
    return {
        "rows": int(rows.sum()),
        "per_quantity": {q: float(hits[:, j].mean()) for j, q in enumerate(QUANTITIES)},
        "conjunctive": float(hits.all(axis=1).mean()),
    }


def _donor(train_pts: Array, y_train: Array, test_pts: Array) -> Array:
    """Per quantity, the value of the nearest training point WHERE THAT QUANTITY EXISTS."""
    out = np.full((test_pts.shape[0], y_train.shape[1]), np.nan)
    for j in range(y_train.shape[1]):
        ok = np.isfinite(y_train[:, j])
        _, idx = cKDTree(train_pts[ok]).query(test_pts, k=1)
        out[:, j] = y_train[ok, j][np.asarray(idx, dtype=np.int64)]
    return out


def null_predictions(
    x: Array, y: Array, folds: npt.NDArray[np.int64], lon: Array, lat: Array
) -> dict[str, Array]:
    _, n_p, n_q = y.shape
    a_idx = [FEATURES.index(f) for f in ANALOGUE_FEATURES]
    xs = x[:, :, a_idx]
    xyz = unit_sphere(lon, lat)
    out = {n: np.full_like(y, np.nan) for n in NULLS}
    rng = np.random.default_rng(SHUFFLE_SEED)
    for f in np.unique(folds):
        te, tr = folds == f, folds != f
        ytr = y[tr].reshape(-1, n_q)
        out["training_mean"][te] = np.nanmean(ytr, axis=0)
        # Standardised on the TRAINING rows only, so the held-out block sets nothing.
        a_tr = xs[tr].reshape(-1, len(a_idx))
        mu, sd = np.nanmean(a_tr, axis=0), np.nanstd(a_tr, axis=0)
        a_te = (xs[te].reshape(-1, len(a_idx)) - mu) / sd
        out["nearest_analogue"][te] = _donor((a_tr - mu) / sd, ytr, a_te).reshape(-1, n_p, n_q)
        for j in range(n_p):
            out["nearest_geographic"][te, j] = _donor(xyz[tr], y[tr, j], xyz[te])
        block = y[te].reshape(-1, n_q).copy()
        for q in range(n_q):
            block[:, q] = rng.permutation(block[:, q])
        out["shuffled"][te] = block.reshape(-1, n_p, n_q)
    # The permutation can move a missing truth onto a row where the truth exists; fill those with
    # the training mean so the arm is scored on the identical rows as every other.
    gap = ~np.isfinite(out["shuffled"])
    out["shuffled"][gap] = out["training_mean"][gap]
    return out


def ceiling(soil_bin: Path, base: Path, replicate: Path, y_scored: Array) -> dict[str, object]:
    """One real run of the model predicting another: the noise-limited skill and band rates.

    The skill ceiling is `1 - noise variance / variance of the SCORED truth`: the noise comes from
    the replicate pair, the variance from the rows actually being scored (all 200 cells), so the
    bound is on the same denominator as the arms it bounds -- the replicate's 20 cells are a stride
    through the design, not its spread.

    ⚠ The two seeds are pilot-v1 and pilot-v1-s2, spun up under the TRANSIENT CO2 path; no second
    seed of v2 exists. Applied to v2 as a bound with that caveat attached, as the kill tests do.
    """
    ys = y_scored.reshape(-1, len(QUANTITIES))
    s2 = pl.read_parquet(replicate)
    f1 = pl.read_parquet(base).filter(pl.col("cell").is_in(s2["cell"].unique().implode()))
    _, _, y1, r1, pts1, _, _ = load(f1, soil_bin)
    _, _, y2, _, pts2, _, _ = load(s2.filter(pl.col("point").is_in(pts1)), soil_bin)
    assert pts1 == pts2 and y1.shape == y2.shape, "the two seeds must cover the same rows"
    t1, t2 = y1.reshape(-1, len(QUANTITIES)), y2.reshape(-1, len(QUANTITIES))
    both = np.isfinite(t1) & np.isfinite(t2)
    per_q = {}
    for j, q in enumerate(QUANTITIES):
        if q in CONSTANT_QUANTITIES:
            continue
        m = both[:, j]
        noise = 0.5 * float(((t1[m, j] - t2[m, j]) ** 2).mean())
        scored = ys[np.isfinite(ys[:, j]), j]
        per_q[q] = 1.0 - noise / float(scored.var())
    treed = np.isfinite(r1[:, :, QUANTITIES.index("wooddens_p50")])
    return {
        "basis": "pilot-v1 seed 1 vs pilot-v1-s2 seed 2, transient-CO2 path",
        "n_cells": int(y1.shape[0]),
        "skill_per_quantity_rho0": per_q,
        "skill_mean_rho0": float(np.mean(list(per_q.values()))),
        "band_one_run_predicting_another": band_stats(y2, r1, treed),
    }


def score_arm(pred: Array, y: Array, raw: Array, points: list[str]) -> dict[str, object]:
    per_q = skill(pred, y)
    treed = np.isfinite(raw[:, :, QUANTITIES.index("wooddens_p50")])
    per_level = {p: float(np.nanmean(skill(pred[:, [j]], y[:, [j]]))) for j, p in enumerate(points)}
    return {
        "pooled": float(np.nanmean(per_q)),
        "n_quantities_in_mean": int(np.isfinite(per_q).sum()),
        "per_quantity": {q: float(v) for q, v in zip(QUANTITIES, per_q, strict=True)},
        "per_level": per_level,
        "band": band_stats(pred, raw, treed),
    }


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--also-degrees", type=float, default=5.0)
    ap.add_argument("--threshold", type=float, help="the SEALED pass margin (model arm only)")
    ap.add_argument("--exp-id", default="")
    ap.add_argument("--ceiling-base", default="pilot-v1")
    ap.add_argument("--ceiling-replicate", default="pilot-v1-s2")
    args = ap.parse_args()
    if args.arm == "model" and args.threshold is None:
        ap.error("--threshold is required for the model arm: it must match the sealed rule")
    return args


def main() -> int:
    args = _parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(str(paths()["scratch"]["corpus"]))
    soil_bin = Path(str(paths()["inputs"]["soil"]))
    table = root / args.version / "corpus.parquet"
    _, x, y, raw, points, lon, lat = load(pl.read_parquet(table), soil_bin)
    assert_constant(y)
    print(f"x {x.shape}, y {y.shape}, {len(points)} climates per cell", flush=True)

    report: dict[str, object] = {
        "exp_id": args.exp_id,
        "arm": args.arm,
        "statistic": STATISTIC,
        "version": args.version,
        "features": list(FEATURES),
        "quantities": list(QUANTITIES),
        "log1p_quantities": sorted(LOG_QUANTITIES),
        "n_cells": int(y.shape[0]),
        "n_rows": int(y.shape[0] * y.shape[1]),
        "scored_rows_per_quantity": {
            q: int(np.isfinite(y[:, :, j]).sum()) for j, q in enumerate(QUANTITIES)
        },
        "by_blocking": {},
    }
    for degrees in (args.degrees, args.also_degrees):
        folds = blocked_spatial_folds(lon, lat, k=args.k, degrees=degrees, seed=42)
        print(f"\n=== blocking {degrees:g} deg ===", flush=True)
        arms = {
            n: score_arm(p, y, raw, points)
            for n, p in null_predictions(x, y, folds, lon, lat).items()
        }
        if args.arm == "model":
            arms["model"] = score_arm(fit_predict_oof(x, y, folds, QUANTITIES), y, raw, points)
        for n, a in arms.items():
            print(f"  {n:20s} {a['pooled']:+.6f}   band conj {a['band']['conjunctive']:.4f}")  # type: ignore[index]
        report["by_blocking"][f"{degrees:g}deg"] = arms  # type: ignore[index]

    primary = report["by_blocking"][f"{args.degrees:g}deg"]  # type: ignore[index]
    if args.arm == "nulls":
        report["ceiling"] = ceiling(
            soil_bin,
            root / args.ceiling_base / "corpus.parquet",
            root / args.ceiling_replicate / "replicate_s2.parquet",
            y,
        )
        print(f"\n  ceiling (rho=0)      {report['ceiling']['skill_mean_rho0']:+.6f}")  # type: ignore[index]
    else:
        best = max(NULLS, key=lambda n: primary[n]["pooled"])
        margin = primary["model"]["pooled"] - primary[best]["pooled"]
        report["decision"] = {
            "best_null": best,
            "margin": margin,
            "threshold": args.threshold,
            "verdict": "pass" if margin > args.threshold else "fail",
        }
        report.update(
            append_result_block(
                statistic=STATISTIC,
                arms={n: float(primary[n]["pooled"]) for n in ("model", *NULLS)},
                n=int(report["n_rows"]),  # type: ignore[arg-type]
            )
        )
    name = "metrics.json" if args.arm == "model" else "nulls.json"
    (out / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
