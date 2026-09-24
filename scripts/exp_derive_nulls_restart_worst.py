#!/usr/bin/env python
"""The emitted-restart nulls under the WORST-QUANTITY score (C1): does it have the power X4 lacked?

    scripts/exp_derive_nulls_restart_worst.py --basis x4          --out <dir>   # the retired X4
    scripts/exp_derive_nulls_restart_worst.py --basis v2-seed1    --out <dir>
    scripts/exp_derive_nulls_restart_worst.py --basis v2-two-seed --out <dir>   # needs seed 2
    scripts/exp_derive_nulls_restart_worst.py --basis v2-two-seed --arm model \\
        --pred <decoded read-back states.parquet> --threshold <sealed> --exp-id <id> --out <dir>

WHAT THIS RE-ASKS. X4 -- "is the forest read back from an emitted restart inside the acceptance
band, on all 22 scored quantities at once?" -- was retired as the wrong instrument: at the 10 %
floor its six nulls collapsed to 0.000-0.004 and a shuffled cell tied first
(`docs/decisions/20260915-X-x4-is-not-sealable-*`). The floor stays 10 %, no quantity is dropped,
no perturbation is excluded. Only the per-row answer changes, from a bit to a number: C1 scores
each (cell, climate) target by its WORST quantity in band units, e = max_q |pred - truth| / band,
and decides on -log(median e). Rationale and the missing-value rules: `vegemu.score`, the C1
section. The acceptance number is still the share of targets with e <= 1, quoted with its ceiling.

THE NULL PREDICTIONS ARE X4's OWN. `build_targets` and `build_null_predictions` are imported from
`exp_derive_nulls_restart_pilot.py` unchanged, so the six arms are the same deterministic functions
of the corpus and the folds that X4 scored; on `--basis x4` this script re-derives X4's conjunctive
numbers from them and checks them against the committed derivation (`--reproduce`) before scoring
anything under C1. The predictions were never saved -- they are recomputed, and the check is what
makes "the existing predictions" a measurement rather than a promise.

THE THREE BASES, and what each can and cannot say:
  x4           pilot-v1 (transient CO2), truth = the single seed, band transferred per cell from
               corpus v0's ssp126 leg at present-day climate. Exactly X4's apparatus.
  v2-seed1     pilot-v2-constco2 (CO2 pinned, the corpus the equilibrium map and the synthesiser
               are built from), same single-seed truth and v0-transferred band.
  v2-two-seed  pilot-v2-constco2 with its full second seed: truth = the two-run MEAN, band =
               max(10 %, the same cell's two-run spread over its OTHER 29 climates)
               (`spread_across_climates`), ceiling = one real run against that mean. The only
               basis on which the ceiling is the attainable score rather than a bound, and the one
               a pre-registration should be sealed on.

THE SCORED TARGETS are the 29 perturbed climates of every cell complete over all 30; the control
climate is the template the synthesiser and the `same_cell_template` null start from, so scoring it
would score the template against itself (X4's design, kept).

THE POWER ARITHMETIC, FIXED HERE BEFORE ANY C1 VALUE WAS SEEN. Under `model_minus_best_null` a null
has no power iff its value minus the best OTHER null clears the threshold, so the threshold must
exceed the gap between the best null and the runner-up. It is set as

    threshold = ceil_0.01( max(gap at 15 deg, gap at 5 deg) + 2 x SE )

where SE is the whole-tile bootstrap standard error of (best null - runner-up) at 15 deg: the gap,
plus two standard errors of how much that gap moves when the ~160 independent tiles are resampled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import numpy.typing as npt
import polars as pl
import yaml

from exp_derive_nulls_restart_pilot import (
    CONTROL_POINT,
    build_null_predictions,
    build_targets,
    transferred_spreads,
)
from vegemu.paths import paths
from vegemu.results import append_result_block
from vegemu.score import (
    FLOOR,
    SCORED_CONJUNCTIVE,
    SCORED_VARYING,
    assert_constant_quantities,
    band_frac_conjunctive,
    band_frac_per_quantity,
    band_from_spread,
    blocked_spatial_folds,
    ceiling_arm,
    matrix,
    score_worst_quantity,
    spatial_blocks,
    spread_across_climates,
    worst_quantity_error,
    worst_quantity_skill,
)

Array = npt.NDArray[np.float64]
REPO = Path(__file__).resolve().parent.parent

STATISTIC = "worst_quantity_skill"
QUANTITIES = SCORED_CONJUNCTIVE
VARYING_IDX = [QUANTITIES.index(q) for q in SCORED_VARYING]
# The order physics predicts, best first, stated before C1 was computed (and the order the
# retired X4's floor sweep found at every floor >= 15 %): the cell's own forest, the most similar
# climate anywhere, the same climate elsewhere, the forest next door, the average forest, chance.
EXPECTED_ORDER: tuple[str, ...] = (
    "same_cell_template",
    "nearest_analogue_any_climate",
    "nearest_analogue_same_point",
    "geographic_address",
    "climatological_mean",
    "shuffled_target",
)
BOOT_SEED = 20260924
N_BOOT = 2000


# ------------------------------------------------------------------------------------------------
# Loading -- every table is put on ONE (cell, point) grid, asserted, never trusted.
# ------------------------------------------------------------------------------------------------
def on_grid(frame: pl.DataFrame, cell_ids: list[int], points: list[str]) -> Array:
    """(cells, points, 22) from any table keyed by (cell, point). Missing rows are an error."""
    index = {
        (int(c), str(p)): i
        for i, (c, p) in enumerate(zip(frame["cell"], frame["point"], strict=True))
    }
    missing = [(c, p) for c in cell_ids for p in points if (c, p) not in index]
    if missing:
        raise ValueError(f"{len(missing)} (cell, point) rows missing, e.g. {missing[:3]}")
    values = matrix(frame, QUANTITIES)
    rows = np.array([index[(c, p)] for c in cell_ids for p in points], dtype=np.int64)
    return values[rows].reshape(len(cell_ids), len(points), len(QUANTITIES))


def load_basis(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(str(paths()["scratch"]["corpus"]))
    corpus = root / args.version
    state = pl.read_parquet(corpus / "corpus.parquet")
    cells_all = pl.read_csv(corpus / "cells.csv")
    targets = build_targets(state, cells_all, QUANTITIES)
    cell_ids: list[int] = targets["cell_ids"]
    points: list[str] = targets["points"]
    cells = cells_all.filter(pl.col("cell").is_in(cell_ids)).sort("cell")
    s1 = np.asarray(targets["truth"], dtype=np.float64)
    out: dict[str, Any] = {
        "targets": targets,
        "cells": cells,
        "cell_ids": cell_ids,
        "points": points,
        "seed1": s1,
        "corpus": str(corpus),
    }
    if args.basis in ("x4", "v2-seed1"):
        sp = transferred_spreads(cell_ids, args.gt_version, QUANTITIES, FLOOR)
        spread = np.repeat(np.asarray(sp["ssp126"])[:, None, :], len(points), axis=1)
        out.update(truth=s1.copy(), spread=spread, band_coverage=sp["coverage"])
        out["band_basis"] = (
            f"relative two-seed spread of corpus {args.gt_version}'s ssp126 leg, per cell per "
            "quantity at present-day climate, floored at 10 %, applied to every design climate"
        )
        out["truth_basis"] = f"{args.version} seed 1 alone (one realisation)"
    else:
        rep = (
            Path(args.replicate)
            if args.replicate
            else root / f"{args.version}-s2" / "replicate_s2.parquet"
        )
        s2_frame = pl.read_parquet(rep)
        all_points = [CONTROL_POINT, *points]
        both1 = on_grid(state, cell_ids, all_points)
        both2 = on_grid(s2_frame, cell_ids, all_points)
        # The replicate must be a DIFFERENT realisation, not a copy (the v0 ssp370 lesson).
        if np.array_equal(both1, both2, equal_nan=True):
            raise ValueError("seed 2 equals seed 1 on every scored value: a clone, not a replicate")
        if not np.array_equal(both1[:, 1:, :], s1, equal_nan=True):
            raise ValueError("the grid loader and build_targets disagree on seed 1")
        spread_all = spread_across_climates(both1, both2)
        out.update(
            seed2=both2[:, 1:, :],
            seed2_control=both2[:, 0, :],
            truth=(both1[:, 1:, :] + both2[:, 1:, :]) / 2.0,
            spread=spread_all[:, 1:, :],
            replicate=str(rep),
            band_coverage={
                "median_floored_spread": float(np.median(spread_all)),
                "frac_above_floor": float(np.mean(spread_all > FLOOR)),
            },
        )
        out["band_basis"] = (
            "max(10 %, median over the same cell's OTHER 29 climates of |s1-s2|/|mean|), per cell "
            "per quantity -- the scored climate's own pair never sets its band"
        )
        out["truth_basis"] = f"{args.version}: mean of seed 1 and seed 2 ({rep.name})"
    return out


# ------------------------------------------------------------------------------------------------
# Scoring.
# ------------------------------------------------------------------------------------------------
def flat(a: Array) -> Array:
    return a.reshape(-1, a.shape[-1])


def score_arm(pred: Array, truth: Array, band: Array, points: list[str]) -> dict[str, Any]:
    """C1 on the 19 varying quantities, plus X4's conjunctive-22 beside it for continuity."""
    v = VARYING_IDX
    res = score_worst_quantity(
        flat(pred)[:, v], flat(truth)[:, v], flat(band)[:, v], SCORED_VARYING
    )
    res["per_level_skill"] = {
        p: worst_quantity_skill(
            worst_quantity_error(pred[:, j][:, v], truth[:, j][:, v], band[:, j][:, v])
        )
        for j, p in enumerate(points)
    }
    res["conjunctive_22_x4_statistic"] = band_frac_conjunctive(flat(pred), flat(truth), flat(band))
    res["band_frac_per_quantity"] = band_frac_per_quantity(
        flat(pred), flat(truth), flat(band), QUANTITIES
    )
    return res


def row_errors(pred: Array, truth: Array, band: Array) -> Array:
    """e per target, shaped (cells, points), on the 19 varying quantities."""
    v = VARYING_IDX
    n_c, n_p, _ = truth.shape
    return worst_quantity_error(flat(pred)[:, v], flat(truth)[:, v], flat(band)[:, v]).reshape(
        n_c, n_p
    )


def separation(values: dict[str, float]) -> dict[str, Any]:
    names = sorted(values, key=lambda n: -values[n])
    gaps = {f"{a} - {b}": values[a] - values[b] for a, b in pairwise(names)}
    rank = {n: i for i, n in enumerate(names)}
    concordant = discordant = 0
    for i, a in enumerate(EXPECTED_ORDER):
        for b in EXPECTED_ORDER[i + 1 :]:
            if rank[a] < rank[b]:
                concordant += 1
            else:
                discordant += 1
    return {
        "ranked": {n: values[n] for n in names},
        "adjacent_gaps": gaps,
        "min_adjacent_gap": min(gaps.values()),
        "best_null": names[0],
        "runner_up": names[1],
        "best_minus_runner_up": values[names[0]] - values[names[1]],
        "order_as_expected": tuple(names) == EXPECTED_ORDER,
        "kendall_tau_vs_expected": (concordant - discordant) / (concordant + discordant),
        "spread_best_to_worst": values[names[0]] - values[names[-1]],
    }


def tile_bootstrap(
    errors: dict[str, Array], lon: Array, lat: Array, *, degrees: float, n_boot: int, seed: int
) -> dict[str, Any]:
    """Resample whole 15-degree tiles, recompute every arm's statistic, report what moves.

    The nulls' PREDICTIONS are held fixed; only the scored targets are resampled. That is the
    sampling uncertainty of the statistic on ~160 independent tiles, which is what a threshold has
    to clear -- not a model-refitting uncertainty, which no null has.
    """
    tiles = spatial_blocks(lon, lat, degrees)
    uniq = np.unique(tiles)
    members = [np.flatnonzero(tiles == t) for t in uniq]
    rng = np.random.default_rng(seed)
    draws = {n: np.empty(n_boot) for n in errors}
    for b in range(n_boot):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        idx = np.concatenate([members[i] for i in pick])
        for n, e in errors.items():
            draws[n][b] = worst_quantity_skill(e[idx].reshape(-1))
    order_holds = np.ones(n_boot, dtype=bool)
    for a, b_ in pairwise(EXPECTED_ORDER):
        order_holds &= draws[a] > draws[b_]
    pairs = {}
    for a, b_ in pairwise(EXPECTED_ORDER):
        d = draws[a] - draws[b_]
        pairs[f"{a} - {b_}"] = {"se": float(d.std(ddof=1)), "frac_positive": float((d > 0).mean())}
    return {
        "n_boot": n_boot,
        "seed": seed,
        "n_tiles": len(uniq),
        "se": {n: float(v.std(ddof=1)) for n, v in draws.items()},
        "p05_p95": {
            n: [float(np.quantile(v, 0.05)), float(np.quantile(v, 0.95))] for n, v in draws.items()
        },
        "expected_adjacent_pairs": pairs,
        "frac_full_expected_order": float(order_holds.mean()),
        "draws": draws,
    }


def threshold_rule(
    sep15: dict[str, Any], sep5: dict[str, Any], draws: dict[str, Array]
) -> dict[str, Any]:
    """The construction in the module docstring, evaluated. Never tuned: it is arithmetic."""
    best, second = sep15["best_null"], sep15["runner_up"]
    se = float((draws[best] - draws[second]).std(ddof=1))
    gap = max(float(sep15["best_minus_runner_up"]), float(sep5["best_minus_runner_up"]))
    raw = gap + 2.0 * se
    threshold = math.ceil(raw * 100.0 - 1e-9) / 100.0
    return {
        "best_null": best,
        "runner_up": second,
        "gap_15deg": sep15["best_minus_runner_up"],
        "gap_5deg": sep5["best_minus_runner_up"],
        "se_boot_best_minus_runner_up_15deg": se,
        "raw": raw,
        "threshold": threshold,
        "bar_at_15deg": float(sep15["ranked"][best]) + threshold,
        "no_null_clears_it": gap < threshold,
    }


def ceilings(args: argparse.Namespace, basis: dict[str, Any]) -> dict[str, Any]:
    """One real run of the model, scored with its arms' arithmetic; which run, by basis."""
    points: list[str] = basis["points"]
    out: dict[str, Any] = {}
    if args.basis == "v2-two-seed":
        pred, truth, band = ceiling_arm(
            flat(basis["seed1"]),
            flat(basis["seed2"]),
            flat(basis["spread"]),
            abs_floor=0.0,
            truth_is="mean",
        )
        shape = basis["truth"].shape
        res = score_arm(pred.reshape(shape), truth.reshape(shape), band.reshape(shape), points)
        res["basis"] = (
            "seed 1 of each perturbed spin-up against the two-run mean, band from the same cell's "
            "other climates: the error of a perfect expectation-predictor, i.e. ATTAINABLE"
        )
        out["one_run_vs_two_run_mean"] = res
        return out
    # A single-seed truth: the only second runs of perturbed spin-ups are pilot-v1-s2's 20 cells.
    root = Path(str(paths()["scratch"]["corpus"]))
    rep = pl.read_parquet(root / args.ceiling_replicate / "replicate_s2.parquet")
    base = pl.read_parquet(root / args.ceiling_base / "corpus.parquet")
    rep_cells = sorted(set(rep["cell"].to_list()) & set(basis["cell_ids"]))
    run = on_grid(base, rep_cells, points)
    other = on_grid(rep, rep_cells, points)
    rows = [basis["cell_ids"].index(c) for c in rep_cells]
    spread = basis["spread"][rows]
    pred, truth, band = ceiling_arm(
        flat(run), flat(other), flat(spread), abs_floor=0.0, truth_is="other"
    )
    shape = run.shape
    res = score_arm(pred.reshape(shape), truth.reshape(shape), band.reshape(shape), points)
    res["basis"] = (
        f"{args.ceiling_base} seed 1 predicting {args.ceiling_replicate} seed 2, {len(rep_cells)} "
        "cells x 29 perturbed climates, same transferred band: one run predicting ANOTHER single "
        "run carries both runs' noise, so this is a LOWER bound on the attainable score"
        + ("; ⚠ that pair ran the TRANSIENT CO2 path" if args.version != args.ceiling_base else "")
    )
    out["one_run_vs_another_run"] = res
    return out


def reproduce_x4(path: Path, scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """X4's committed conjunctive numbers, recomputed from the recomputed predictions."""
    old = json.loads(path.read_text(encoding="utf-8"))["results"]["ssp126"]["nulls"]
    rows = {
        n: {
            "committed": float(old[n]["conjunctive"]),
            "recomputed": s["conjunctive_22_x4_statistic"],
        }
        for n, s in scores.items()
    }
    ok = all(abs(r["committed"] - r["recomputed"]) < 1e-12 for r in rows.values())
    return {"source": str(path), "arms": rows, "identical": ok}


# ------------------------------------------------------------------------------------------------
# The model arm: a table of states DECODED from the emitted restarts, scored beside every null.
# ------------------------------------------------------------------------------------------------
def check_folds(
    frame: pl.DataFrame, basis: dict[str, Any], folds15: npt.NDArray[np.int64], *, what: str
) -> None:
    """Refuse a table whose per-cell `fold` is not the scorer's: its out-of-fold claim is void."""
    want = dict(zip(basis["cell_ids"], folds15.tolist(), strict=True))
    got: dict[int, set[int]] = {}
    for c, f in zip(frame["cell"].to_list(), frame["fold"].to_list(), strict=True):
        got.setdefault(int(c), set()).add(int(f))
    bad = [c for c in basis["cell_ids"] if c in got and got[c] != {want[c]}]
    if bad:
        raise ValueError(f"{what}: folds differ from the scorer's on {len(bad)} cells")


def load_model_arm(
    path: Path,
    basis: dict[str, Any],
    folds15: npt.NDArray[np.int64],
    *,
    prefix: str,
    arm: str,
) -> tuple[Array, dict[str, Any]]:
    """(cells, points, 22) decoded read-back states, and what the table actually covered.

    Accepts the synthesiser's own table (`scripts/synth_pilot.py --stage synth` writes
    `synth_<arm>.parquet` with `y0_<quantity>` columns, a `status` and a `fold`) or any table keyed
    by (cell, point) with the 22 columns under `prefix`. ⚠ A target the harness failed on, or never
    wrote, is NOT dropped: it is a missing prediction and scores e = inf, exactly as a missing
    value does in `score.py`. Dropping it would score the model on an easier subset than its nulls.

    READ BACK, NOT INTENDED. The harness decodes the synthesised record with the corpus decoder and
    separately proves the file on disk decodes to that same record (`t0_roundtrip`). A row whose
    round-trip failed is not a state the file holds, so it is treated as a failed target too.
    A table holding several arms (the harness's one-year table carries `arm` = map / oracle /
    truth) is cut to `arm`, and a row whose C run did not succeed (`success`) is a failed target.
    """
    frame = pl.read_parquet(path)
    if "arm" in frame.columns:
        frame = frame.filter(pl.col("arm") == arm)
        if frame.height == 0:
            raise ValueError(f"{path.name} holds no rows of arm {arm!r}")
    if "fold" in frame.columns:
        check_folds(frame, basis, folds15, what=path.name)
    n_rows = frame.height
    if "status" in frame.columns:
        frame = frame.filter(pl.col("status") == "ok")
    for flag in ("t0_roundtrip", "success"):
        if flag in frame.columns:
            frame = frame.filter(pl.col(flag).fill_null(False))
    missing_cols = [q for q in QUANTITIES if f"{prefix}{q}" not in frame.columns]
    if missing_cols:
        raise ValueError(
            f"{path.name} lacks {prefix}{missing_cols[0]} and {len(missing_cols) - 1} more"
        )
    # Two usable rows for one target would be resolved silently by whichever the index kept last;
    # which state the file holds is then a matter of row order. Refused instead.
    dup = frame.select(["cell", "point"]).is_duplicated()
    if dup.any():
        raise ValueError(f"{path.name}: {int(dup.sum())} rows share a (cell, point) target")
    frame = frame.select(
        [pl.col("cell").cast(pl.Int64), pl.col("point").cast(pl.Utf8)]
        + [pl.col(f"{prefix}{q}").cast(pl.Float64).alias(q) for q in QUANTITIES]
    )
    index = {
        (int(c), str(p)): i
        for i, (c, p) in enumerate(zip(frame["cell"], frame["point"], strict=True))
    }
    values = matrix(frame, QUANTITIES)
    out = np.full((len(basis["cell_ids"]), len(basis["points"]), len(QUANTITIES)), np.nan)
    covered = np.zeros(out.shape[:2], dtype=bool)
    for i, c in enumerate(basis["cell_ids"]):
        for j, p in enumerate(basis["points"]):
            if (c, p) in index:
                out[i, j] = values[index[(c, p)]]
                covered[i, j] = True
    coverage = {
        "path": str(path),
        "rows_in_table": n_rows,
        "rows_ok": frame.height,
        "targets_covered": int(covered.sum()),
        "targets_missing_scored_as_never_credited": int((~covered).sum()),
        "covered": covered,
    }
    return out, coverage


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def input_hashes(args: argparse.Namespace, basis: dict[str, Any]) -> dict[str, str]:
    """sha256 of every table this run scores from, so the verdict names exactly what was read.

    ⚠ WHY. The synthesiser's table records neither which map table it consumed nor its hash, and
    the map's out-of-fold table can be rewritten after the restarts were built from it; `--map-oof`
    is checked for its FOLDS only. The hashes are what lets a later reader match the scored files
    to the files that produced them.
    """
    files = {"corpus": Path(basis["corpus"]) / "corpus.parquet"}
    if "replicate" in basis:
        files["replicate"] = Path(basis["replicate"])
    for key in ("pred", "map_oof", "pred_year1"):
        if getattr(args, key):
            files[key] = Path(getattr(args, key))
    for spec in args.report_arm:
        label, _, path = spec.partition("=")
        files[f"report_arm:{label}"] = Path(path)
    hashes = {k: sha256_of(p) for k, p in files.items()}
    if args.exp_id:
        check_sealed_inputs(args.exp_id, hashes)
    return hashes


def check_sealed_inputs(exp_id: str, hashes: dict[str, str]) -> None:
    """Refuse a run whose corpus or seed-2 table is not the one its pre-registration sealed.

    The sealed basis names both files by sha256 (`data.corpus_sha256`,
    `data.replicate_table_sha256`); a different table -- including a content-equal re-decode with
    other bytes -- is a different basis and needs a new seal, not a quiet substitution.
    """
    prereg = REPO / "experiments" / exp_id / "preregistration.yaml"
    data = yaml.safe_load(prereg.read_text(encoding="utf-8")).get("data", {})
    for key, field in (("corpus", "corpus_sha256"), ("replicate", "replicate_table_sha256")):
        sealed = data.get(field)
        if sealed and hashes.get(key) != sealed:
            raise ValueError(
                f"{exp_id} sealed {field} {sealed[:12]}..., this run read "
                f"{str(hashes.get(key, 'nothing'))[:12]}... -- not the sealed basis"
            )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--basis", choices=("x4", "v2-seed1", "v2-two-seed"), required=True)
    ap.add_argument(
        "--version", default=None, help="default: pilot-v1 for x4, else pilot-v2-constco2"
    )
    ap.add_argument(
        "--replicate", default="", help="seed-2 table (v2-two-seed); default <version>-s2"
    )
    ap.add_argument("--gt-version", default="v0", help="corpus holding the donor legs of the band")
    ap.add_argument("--ceiling-base", default="pilot-v1")
    ap.add_argument("--ceiling-replicate", default="pilot-v1-s2")
    ap.add_argument("--reproduce", default="", help="X4's committed derivation JSON (--basis x4)")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--also-degrees", type=float, default=5.0)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--arm", choices=("nulls", "model"), default="nulls")
    ap.add_argument("--pred", default="", help="decoded read-back states, keyed by (cell, point)")
    ap.add_argument("--pred-prefix", default="y0_", help="column prefix in --pred")
    ap.add_argument(
        "--pred-arm", default="map", help="the `arm` value to score, if the table has one"
    )
    ap.add_argument(
        "--pred-year1", default="", help="the same after a 1-year C run (reported only)"
    )
    ap.add_argument("--pred-year1-prefix", default="y1_", help="column prefix in --pred-year1")
    ap.add_argument(
        "--report-arm",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="an extra arm scored beside the decision and never in it, e.g. the synthesiser's "
        "oracle arm (true state in, restart out): what the synthesis alone loses",
    )
    ap.add_argument(
        "--map-oof",
        default="",
        help="the map's out-of-fold table the synthesiser consumed; its folds are verified",
    )
    ap.add_argument("--threshold", type=float, help="the SEALED pass margin (model arm only)")
    ap.add_argument("--exp-id", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.version is None:
        args.version = "pilot-v1" if args.basis == "x4" else "pilot-v2-constco2"
    if args.arm == "model" and (args.threshold is None or not args.pred):
        ap.error("the model arm needs --pred and the sealed --threshold")
    return args


def score_blockings(
    args: argparse.Namespace, basis: dict[str, Any], band: Array, model: Array | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Array], dict[str, Array]]:
    """Every arm under both blockings; the nulls' predictions and errors at the primary one."""
    truth, points = basis["truth"], basis["points"]
    by_blocking: dict[str, Any] = {}
    seps: dict[str, dict[str, Any]] = {}
    errors: dict[str, Array] = {}
    primary_preds: dict[str, Array] = {}
    for degrees in (args.degrees, args.also_degrees):
        # Seed-1 states are the donors: every null is a REAL restart (or its training mean), never
        # the two-run mean, because an emitted restart is one realisation too.
        preds, fold_basis = build_null_predictions(
            basis["targets"], basis["cells"], k=args.k, degrees=degrees
        )
        primary = degrees == args.degrees
        # The model arm was fitted on the PRIMARY folds only; scoring it under a blocking it was
        # not fitted for would score a leak, so at the sensitivity radius only the nulls are scored.
        if model is not None and primary:
            preds["model"] = model
        scores = {n: score_arm(p, truth, band, points) for n, p in preds.items()}
        sep = separation({n: float(scores[n][STATISTIC]) for n in EXPECTED_ORDER})
        seps[f"{degrees:g}"] = sep
        entry: dict[str, Any] = {"folds": fold_basis, "arms": scores, "separation": sep}
        if args.basis == "x4" and args.reproduce and primary:
            entry["reproduces_x4"] = reproduce_x4(
                Path(args.reproduce), {n: scores[n] for n in EXPECTED_ORDER}
            )
            print(f"reproduces X4's committed numbers: {entry['reproduces_x4']['identical']}")
        by_blocking[f"{degrees:g}deg"] = entry
        if primary:
            errors = {n: row_errors(preds[n], truth, band) for n in EXPECTED_ORDER}
            primary_preds = {n: preds[n] for n in EXPECTED_ORDER}
        print_blocking(degrees, scores, sep)
    return by_blocking, seps, errors, primary_preds


def score_subset(pred: Array, truth: Array, band: Array, mask: npt.NDArray[np.bool_]) -> Any:
    """C1 on the targets under `mask` only -- for a model arm that covers part of the grid."""
    v = VARYING_IDX
    return score_worst_quantity(
        pred[mask][:, v], truth[mask][:, v], band[mask][:, v], SCORED_VARYING
    )


def print_blocking(degrees: float, scores: dict[str, Any], sep: dict[str, Any]) -> None:
    print(f"\n=== {degrees:g} deg: {STATISTIC}, median e, share within band, X4's conj-22 ===")
    for n in [*sep["ranked"], *(["model"] if "model" in scores else [])]:
        s = scores[n]
        print(
            f"  {n:30s} {s[STATISTIC]:+.6f}  e50 {s['e_quantiles']['p50']:9.3f}  "
            f"within {s['share_within_band']:.6f}  conj22 {s['conjunctive_22_x4_statistic']:.6f}"
        )
    print(
        f"  order as expected: {sep['order_as_expected']}, "
        f"tau {sep['kendall_tau_vs_expected']:+.3f}, min gap {sep['min_adjacent_gap']:.6f}, "
        f"best - runner-up {sep['best_minus_runner_up']:.6f}",
        flush=True,
    )


def decide_model(
    args: argparse.Namespace,
    report: dict[str, Any],
    basis: dict[str, Any],
    band: Array,
    folds15: npt.NDArray[np.int64],
    *,
    null_preds: dict[str, Array],
) -> None:
    """The sealed rule, applied, and the result block `tools/append_result.py` reads."""
    primary = report["by_blocking"][f"{args.degrees:g}deg"]["arms"]
    best = max(EXPECTED_ORDER, key=lambda n: primary[n][STATISTIC])
    margin = primary["model"][STATISTIC] - primary[best][STATISTIC]
    report["decision"] = {
        "best_null": best,
        "margin": margin,
        "threshold": args.threshold,
        "verdict": "pass" if margin > args.threshold else "fail",
    }
    if args.pred_year1:
        # After one year of the real model, on whatever targets were run: the model AND every null
        # on that same subset, against the same truth. Reported beside the decision, never in it.
        y1, cov = load_model_arm(
            Path(args.pred_year1),
            basis,
            folds15,
            prefix=args.pred_year1_prefix,
            arm=args.pred_arm,
        )
        mask = cov.pop("covered")
        truth = basis["truth"]
        report["after_one_c_year_REPORTED_NOT_DECIDED"] = {
            "coverage": cov,
            "model": score_subset(y1, truth, band, mask),
            "nulls_on_the_same_targets": {
                n: score_subset(p, truth, band, mask) for n, p in null_preds.items()
            },
        }
    report.update(
        append_result_block(
            statistic=STATISTIC,
            arms={n: float(primary[n][STATISTIC]) for n in ("model", *EXPECTED_ORDER)},
            n=int(report["n_targets"]),
        )
    )


def main() -> int:
    args = _parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    basis = load_basis(args)
    hashes = input_hashes(args, basis)  # refuses a basis other than the sealed one (--exp-id)
    truth = basis["truth"]
    assert_constant_quantities(truth, QUANTITIES)
    band = band_from_spread(truth, basis["spread"], abs_floor=0.0)
    lon = basis["cells"]["lon"].to_numpy().astype(np.float64)
    lat = basis["cells"]["lat"].to_numpy().astype(np.float64)
    n_c, n_p, _ = truth.shape
    print(f"basis {args.basis}: {n_c} cells x {n_p} perturbed climates = {n_c * n_p} targets")
    print(f"  truth: {basis['truth_basis']}\n  band:  {basis['band_basis']}", flush=True)
    stems = truth[:, :, QUANTITIES.index("stems_per_patch")]
    report: dict[str, Any] = {
        "exp_id": args.exp_id,
        "arm": args.arm,
        "statistic": STATISTIC,
        "basis": args.basis,
        "version": args.version,
        "corpus": basis["corpus"],
        "truth_basis": basis["truth_basis"],
        "band_basis": basis["band_basis"],
        "band_coverage": basis["band_coverage"],
        "inputs_sha256": hashes,
        "quantities_max_over": list(SCORED_VARYING),
        "n_cells": n_c,
        "n_points": n_p,
        "n_targets": n_c * n_p,
        "n_targets_treeless_truth": int((stems <= 0).sum()),
        "expected_order": list(EXPECTED_ORDER),
    }
    folds15 = blocked_spatial_folds(lon, lat, k=args.k, degrees=args.degrees, seed=42)
    model = None
    if args.arm == "model":
        model, cov = load_model_arm(
            Path(args.pred), basis, folds15, prefix=args.pred_prefix, arm=args.pred_arm
        )
        cov.pop("covered")
        report["model_coverage"] = cov
        if args.map_oof:
            oof = pl.read_parquet(args.map_oof, columns=["cell", "fold"])
            check_folds(oof, basis, folds15, what=Path(args.map_oof).name)
            report["map_oof_folds_verified"] = args.map_oof
        print(f"model arm: {cov}", flush=True)
    report["by_blocking"], seps, errors15, null_preds = score_blockings(args, basis, band, model)

    boot = tile_bootstrap(
        errors15, lon, lat, degrees=args.degrees, n_boot=args.n_boot, seed=BOOT_SEED
    )
    rule = threshold_rule(
        seps[f"{args.degrees:g}"], seps[f"{args.also_degrees:g}"], boot.pop("draws")
    )
    report["tile_bootstrap_15deg"] = boot
    report["threshold_rule"] = rule
    report["ceiling"] = ceilings(args, basis)
    print(f"\nbootstrap: full expected order in {boot['frac_full_expected_order']:.3f} of draws")
    for pair, v in boot["expected_adjacent_pairs"].items():
        print(f"  {pair:62s} se {v['se']:.4f}  positive {v['frac_positive']:.3f}")
    print(f"threshold rule: {rule}")
    for name, c in report["ceiling"].items():
        print(f"ceiling {name}: {c[STATISTIC]:+.6f}, within band {c['share_within_band']:.6f}")

    if model is not None:
        decide_model(args, report, basis, band, folds15, null_preds=null_preds)
    extra: dict[str, Any] = {}
    for spec in args.report_arm:
        label, _, path = spec.partition("=")
        arm, cov = load_model_arm(Path(path), basis, folds15, prefix=args.pred_prefix, arm=label)
        cov.pop("covered")
        extra[label] = {"coverage": cov, **score_arm(arm, truth, band, basis["points"])}
        print(f"reported arm {label}: {extra[label][STATISTIC]:+.6f} (never decided on)")
    if extra:
        report["reported_arms_NOT_DECIDED"] = extra
    name = "metrics.json" if model is not None else f"nulls_worst_{args.basis}.json"
    (out / name).write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(f"\nwrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
