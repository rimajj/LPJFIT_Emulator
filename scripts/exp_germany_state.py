#!/usr/bin/env python
"""Germany: predict the settled FOREST -- tree counts AND trait medians AND trait distributions --
under a climate the model never trained on. Is that as good as a second run of the model?

    NCPUS=16 scripts/sbatch_py.sh X-ger-state-nulls scripts/exp_germany_state.py \\
        --arm nulls --out <dir>
    NCPUS=32 scripts/sbatch_py.sh --exp X-20260930-germany-state-new-climate X-ger-state-model \\
        scripts/exp_germany_state.py --arm model --threads 32 \\
        --out <scratch.exp>/X-20260930-germany-state-new-climate

THE QUESTION. The Germany carbon test (`exp_germany_vegc.py`) scored settled carbon only. The
owner's acceptance clause is tree counts AND trait distributions AND trait medians, per cell. This
is that clause on the Germany corpus: the state of every cell's 3070 restart (the last full state
inside the clean segment; `germany_corpus.py restart|state`, proven byte-identical and equal to the
model's own 3070 VegC), 9,067 cells x six climates x two seeds.

ESTIMAND `asgood_state_germany_newclimate` -- the global full-state test's construction
(`exp_pilot_state_asgood.py`) moved onto this corpus, unchanged in every rule:
  * a row is (cell, climate); the 19 quantities of `score.SCORED_VARYING` (stems per patch; above-
    ground biomass, LAI, soil carbon; p10/p50/p90 of wood density, SLA, D95max, leaf longevity and
    height). Fine-root conductivity is one constant value in every row here too and is left out;
    `assert_constant_quantities` refuses the run if it varies;
  * truth T_k = seed k's 3070 restart state;
  * band w = `score.spread_across_climates`: per cell and quantity, max(0.10, the median two-seed
    relative spread over the cell's OTHER five climates) -- the scored pair never sets its own
    tolerance;
  * pass = every quantity the truth defines is inside |x - T_k| <= w |T_k| (a trait of a treeless
    truth is not scored; an arm that leaves a defined quantity undefined fails it);
  * frac = mean over rows of the mean over k; rerun = seed 2 scored against seed 1 and vice versa;
  * D = frac(arm) - frac(rerun). The owner's rule: D >= -0.02.
FOLDS: leave-one-climate-out, six folds, as the carbon test.

THE MODEL ARM, fixed before any Germany state number was seen: per quantity, one LightGBM with the
carbon test's frozen settings (`exp_germany_vegc.LEARNER`, chosen on the GLOBAL spin-up dev folds),
L1 loss, fitted on both seeds' rows of the five training climates where that seed defines the
quantity; log1p target for the four count/stock quantities (`LOG_QUANTITIES`), natural scale for
traits. Emitted = clipped at 0 and each trait's three quantiles sorted, as the global emitted map
does. Inputs: the same 258 climate + soil columns; never cell, place, ESM, SSP, seed or CO2.

THE NULLS (information-free about the held-out climate's truth), each a whole 19-vector:
  * same_cell_nearest_climate: the cell's own two-seed mean state under the training climate
    nearest in the 85 standardised forcing features;
  * same_cell_mean: the mean of the cell's own state over its five training climates (geometric for
    the four log quantities);
  * nearest_analogue: the nearest training ROW, any cell, in the eight analogue features;
  * training_mean: the per-quantity mean of the training rows (log scale for the log quantities);
  * shuffled: the held-out climate's two-seed mean states permuted across its rows (seed 20260930).
REPORTED BESIDE, NEVER DECIDED ON: frac per held-out climate; per-quantity band rates; the ceiling
(the two-seed mean as a predictor); a BLIND arm, the same learner on the six soil columns; frac
without ssp245; the flat-10 % conjunctive rate; frac on the rows where both seeds bear trees.

`--exclude ESM/ssp` drops a whole run first (rows, folds AND every band), so "six climates" above
becomes the number left. Used for MPI-ESM1-2-HR/ssp245, the one run held at 401.63 ppm CO2 where
the other ten held 415.78 (its input file reads the RCP8.5 series constant from 2015, not 2020).
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.spatial import cKDTree

from exp_germany_vegc import FEATURES, FORCING, LEARNER, SHUFFLE_SEED, SOIL
from exp_germany_vegc import load as load_climate
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import (
    CONSTANT_ON_PILOT,
    FLOOR,
    SCORED_VARYING,
    assert_constant_quantities,
    spread_across_climates,
)

Array = npt.NDArray[np.float64]

STATISTIC = "asgood_state_germany_newclimate"
THRESHOLD = -0.02
Q: tuple[str, ...] = SCORED_VARYING
LOG_QUANTITIES: frozenset[str] = frozenset({"stems_per_patch", "agb", "lai", "soilc"})
TRAIT_TRIPLES: tuple[tuple[str, str, str], ...] = tuple(
    (f"{t}_p10", f"{t}_p50", f"{t}_p90")
    for t in ("wooddens", "sla", "D95max", "longevity", "height")
)
NCELL = 9067


ROW_KEYS: tuple[str, ...] = ("x", "t1", "t2", "w", "cell", "ssp", "scored", "s1", "s2")


def load(exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """The carbon test's inputs and folds, plus both seeds' 3070 states in the same row order.

    `exclude` names whole runs ("ESM/ssp") to drop BEFORE anything is built from them: their rows
    neither train, nor are scored, nor enter any other climate's band, and the folds are the
    remaining climates. The default drops nothing and is the sealed six-climate test, unchanged.
    """
    d = load_climate()
    unknown = set(exclude) - set(d["names"])
    assert not unknown, f"unknown climates to exclude: {sorted(unknown)}"
    corpus = Path(str(paths()["scratch"]["corpus"])) / "germany-eq-v1"
    st = pl.read_parquet(corpus / "germany_state_3070.parquet")
    meta = json.loads((corpus / "germany_state_3070.json").read_text())
    clim = pl.read_parquet(corpus / "germany_climate.parquet", columns=["esm", "ssp", "cell"]).sort(
        ["esm", "ssp", "cell"]
    )
    tk: list[Array] = []
    for seed in (1, 2):
        s = st.filter(pl.col("seed") == seed).sort(["esm", "ssp", "cell"])
        for k in ("esm", "ssp", "cell"):
            assert (s[k] == clim[k]).all(), (seed, k)
        tk.append(s.select(Q).to_numpy().astype(np.float64))
        full = s.select([*Q, *CONSTANT_ON_PILOT]).to_numpy().astype(np.float64)
        assert_constant_quantities(full, [*Q, *CONSTANT_ON_PILOT])
    assert np.array_equal(d["cell"], clim["cell"].to_numpy())
    d["s1"], d["s2"] = tk
    if exclude:
        keep_names = [n for n in d["names"] if n not in exclude]
        keep = np.isin(np.array(d["names"])[d["fold"]], keep_names)
        d["fold"] = np.array([keep_names.index(d["names"][f]) for f in d["fold"][keep]])
        for k in ROW_KEYS:
            d[k] = d[k][keep]
        d["names"] = keep_names
    ncl = len(d["names"])
    # (rows, q) -> (cells, climates, q): rows are climate-major (esm, ssp, cell), cells 0..9066
    cube = [d[k].reshape(ncl, NCELL, len(Q)).transpose(1, 0, 2) for k in ("s1", "s2")]
    w = spread_across_climates(np.nan_to_num(cube[0], nan=0.0), np.nan_to_num(cube[1], nan=0.0))
    d["w_state"] = w.transpose(1, 0, 2).reshape(-1, len(Q))
    d["sha"]["state"] = meta["output_sha256"]
    d["excluded"] = list(exclude)
    return d


def row_pass(pred: Array, truth: Array, w: Array) -> Array:
    """(rows,) 0/1: every quantity the truth defines is inside the band (exp_pilot_state_asgood)."""
    scored = np.isfinite(truth)
    inside = (np.abs(pred - truth) <= w * np.abs(truth)) & np.isfinite(pred)
    out: Array = np.all(inside | ~scored, axis=1).astype(np.float64)
    return out


def score(pred: Array, d: dict[str, Any], sel: npt.NDArray[np.bool_]) -> dict[str, Any]:
    s1, s2, w = d["s1"][sel], d["s2"][sel], d["w_state"][sel]
    p = pred[sel]
    rerun = (row_pass(s2, s1, w) + row_pass(s1, s2, w)) / 2
    per_row = (row_pass(p, s1, w) + row_pass(p, s2, w)) / 2
    flat = np.full_like(w, FLOOR)
    flat_row = (row_pass(p, s1, flat) + row_pass(p, s2, flat)) / 2
    treed = np.isfinite(s1[:, Q.index("height_p50")]) & np.isfinite(s2[:, Q.index("height_p50")])
    per_q: dict[str, float] = {}
    per_q_rerun: dict[str, float] = {}
    for j, q in enumerate(Q):
        rates, rr = [], []
        for t, o in ((s1, s2), (s2, s1)):
            ok = np.isfinite(t[:, j])
            hit = (np.abs(p[:, j] - t[:, j]) <= w[:, j] * np.abs(t[:, j])) & np.isfinite(p[:, j])
            rates.append(float(hit[ok].mean()))
            hr = (np.abs(o[:, j] - t[:, j]) <= w[:, j] * np.abs(t[:, j])) & np.isfinite(o[:, j])
            rr.append(float(hr[ok].mean()))
        per_q[q] = float(np.mean(rates))
        per_q_rerun[q] = float(np.mean(rr))
    return {
        "rows": int(sel.sum()),
        "frac": float(per_row.mean()),
        "frac_rerun": float(rerun.mean()),
        "D": float(per_row.mean() - rerun.mean()),
        "frac_tree_bearing_both_seeds": float(per_row[treed].mean()),
        "rerun_tree_bearing_both_seeds": float(rerun[treed].mean()),
        "flat10_conjunctive": float(flat_row.mean()),
        "per_quantity_band_rate": per_q,
        "per_quantity_rerun_rate": per_q_rerun,
    }


def breakdown(pred: Array, d: dict[str, Any], base: npt.NDArray[np.bool_]) -> dict[str, Any]:
    out = {"all": score(pred, d, base)}
    for i, n in enumerate(d["names"]):
        out[n] = score(pred, d, base & (d["fold"] == i))
    return out


def two_seed_mean(d: dict[str, Any]) -> Array:
    with warnings.catch_warnings():  # both seeds treeless: the trait stays NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        out: Array = np.nanmean(np.stack([d["s1"], d["s2"]]), axis=0)
    return out


def _to_log(y: Array) -> Array:
    out = y.copy()
    for j, q in enumerate(Q):
        if q in LOG_QUANTITIES:
            out[..., j] = np.log1p(np.maximum(y[..., j], 0.0))
    return out


def _from_log(z: Array) -> Array:
    out = z.copy()
    for j, q in enumerate(Q):
        if q in LOG_QUANTITIES:
            out[..., j] = np.expm1(z[..., j])
    return out


def nulls(d: dict[str, Any]) -> dict[str, Array]:
    x, fold, cell = d["x"], d["fold"], d["cell"]
    y = two_seed_mean(d)
    ly = _to_log(y)
    nq = len(Q)
    ncl = len(d["names"])
    by = np.full((NCELL, ncl, nq), np.nan)
    by[cell, fold] = ly
    xf = np.full((NCELL, ncl, len(FORCING)), np.nan)
    xf[cell, fold] = x[:, : len(FORCING)]
    a_idx = [FEATURES.index(f) for f in ANALOGUE_FEATURES]
    names = (
        "same_cell_nearest_climate",
        "same_cell_mean",
        "nearest_analogue",
        "training_mean",
        "shuffled",
    )
    out = {k: np.full(y.shape, np.nan) for k in names}
    rng = np.random.default_rng(SHUFFLE_SEED)
    nf = len(FORCING)
    for f in range(ncl):
        te = fold == f
        tr = ~te
        mu, sd = x[tr].mean(axis=0), x[tr].std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        others = [g for g in range(ncl) if g != f]
        ct = cell[te]
        q = (xf[ct, f] - mu[:nf]) / sd[:nf]
        dist = np.stack(
            [np.linalg.norm((xf[ct, g] - mu[:nf]) / sd[:nf] - q, axis=1) for g in others], axis=1
        )
        pick = np.array(others)[dist.argmin(axis=1)]
        out["same_cell_nearest_climate"][te] = _from_log(by[ct, pick])
        with warnings.catch_warnings():  # an all-NaN trait column: a treeless cell, left NaN
            warnings.simplefilter("ignore", RuntimeWarning)
            out["same_cell_mean"][te] = _from_log(np.nanmean(by[ct][:, others], axis=1))
            out["training_mean"][te] = _from_log(np.nanmean(ly[tr], axis=0))[None, :]
        a_tr = (x[tr][:, a_idx] - mu[a_idx]) / sd[a_idx]
        a_te = (x[te][:, a_idx] - mu[a_idx]) / sd[a_idx]
        out["nearest_analogue"][te] = y[tr][cKDTree(a_tr).query(a_te, k=1)[1]]
        idx = np.flatnonzero(te)
        out["shuffled"][idx] = y[rng.permutation(idx)]
    return out


def emit(z: Array) -> Array:
    """Raw per-quantity predictions -> the emitted state: >= 0, each trait's quantiles sorted."""
    out = np.maximum(z, 0.0)
    for trip in TRAIT_TRIPLES:
        j = [Q.index(c) for c in trip]
        out[:, j] = np.sort(out[:, j], axis=1)
    return out


def fit_predict(
    d: dict[str, Any],
    cols: list[int],
    folds: list[int],
    keep: npt.NDArray[np.bool_] | None = None,
    threads: int = 8,
) -> Array:
    from lightgbm import LGBMRegressor  # noqa: PLC0415

    x = d["x"][:, cols]
    keep = np.ones(x.shape[0], dtype=bool) if keep is None else keep
    raw = np.full((x.shape[0], len(Q)), np.nan)
    for f in folds:
        tr = (d["fold"] != f) & keep
        te = d["fold"] == f
        for j, q in enumerate(Q):
            xt = np.concatenate([x[tr], x[tr]])
            yt = np.concatenate([d["s1"][tr, j], d["s2"][tr, j]])
            ok = np.isfinite(yt)
            lg = q in LOG_QUANTITIES
            m = LGBMRegressor(**LEARNER, n_jobs=threads)
            m.fit(xt[ok], np.log1p(np.maximum(yt[ok], 0.0)) if lg else yt[ok])
            p = m.predict(x[te])
            raw[te, j] = np.expm1(p) if lg else p
        print(f"  fold {f} ({d['names'][f]}): {len(Q)} quantities fitted", flush=True)
    return emit(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="drop a whole run, ESM/ssp (repeatable); its rows never train, score or set a band",
    )
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = load(tuple(a.exclude))
    base = np.ones(d["fold"].size, dtype=bool)
    tm = two_seed_mean(d)
    report: dict[str, Any] = {
        "statistic": STATISTIC,
        "rows": int(base.size),
        "quantities": list(Q),
        "climates": d["names"],
        "excluded": d["excluded"],
        "inputs_sha256": d["sha"],
        "band_is_floor_share": float((d["w_state"] == FLOOR).mean()),
        "band_quantiles": {
            q: [float(v) for v in np.quantile(d["w_state"][:, j], [0.5, 0.9, 0.99])]
            for j, q in enumerate(Q)
        },
        "ceiling_two_seed_mean": breakdown(tm, d, base),
    }
    nl = nulls(d)
    report["nulls"] = {k: breakdown(v, d, base) for k, v in nl.items()}
    if a.arm == "nulls":
        (out / "nulls.json").write_text(json.dumps(report, indent=2))
        summary = {
            k: {"D": v["all"]["D"], "frac": v["all"]["frac"]} for k, v in report["nulls"].items()
        }
        print(json.dumps(summary, indent=2), flush=True)
        print("rerun+ceiling", json.dumps(report["ceiling_two_seed_mean"]["all"], indent=1))
        return 0

    all_cols = list(range(len(FEATURES)))
    soil_cols = [FEATURES.index(c) for c in SOIL]
    pred = fit_predict(d, all_cols, list(range(len(d["names"]))), threads=a.threads)
    blind = fit_predict(d, soil_cols, list(range(len(d["names"]))), threads=a.threads)
    no245 = d["ssp"] != "ssp245"
    folds_same_build = [i for i, n in enumerate(d["names"]) if not n.endswith("ssp245")]
    pred_nb = fit_predict(d, all_cols, folds_same_build, keep=no245, threads=a.threads)
    report["arm"] = "model"
    report["learner"] = LEARNER
    report["features"] = len(FEATURES)
    report["arm_details"] = {
        "model": breakdown(pred, d, base),
        "blind_soil_only": breakdown(blind, d, base),
        "model_without_ssp245": score(pred_nb, d, base & no245),
    }
    arms = {"model": report["arm_details"]["model"]["all"]["D"]}
    arms.update({k: v["all"]["D"] for k, v in report["nulls"].items()})
    report.update(append_result_block(statistic=STATISTIC, arms=arms, n=int(base.sum())))
    report["decision"] = {
        "D": arms["model"],
        "threshold": THRESHOLD,
        "verdict": "pass" if arms["model"] >= THRESHOLD else "fail",
    }
    cols: dict[str, Any] = {"cell": d["cell"], "fold": d["fold"]}
    for j, q in enumerate(Q):
        cols[f"pred_{q}"] = pred[:, j]
        cols[f"blind_{q}"] = blind[:, j]
    pl.DataFrame(cols).write_parquet(out / "predictions.parquet")
    (out / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"model": report["arm_details"]["model"]["all"], "arms": arms}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
