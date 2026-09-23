"""The emitted-restart C1 derivation's apparatus, on synthetic data.

The nulls' values are derived on the cluster from the pilot corpora, which CI does not have. What
CI can check is the machinery those values pass through: the grid loader refuses a missing target,
the separation summary ranks and measures what it says, the threshold rule always clears the gap
it is built from (so the sealed threshold can never be powerless by construction), and a tile
bootstrap is deterministic under its seed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_derive_nulls_restart_worst import (
    EXPECTED_ORDER,
    QUANTITIES,
    STATISTIC,
    load_model_arm,
    on_grid,
    row_errors,
    score_arm,
    separation,
    threshold_rule,
    tile_bootstrap,
)

N_C, N_P = 30, 4


def _grid_frame(cells: list[int], points: list[str], seed: int = 0) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    rows = [(c, p) for c in cells for p in points]
    data = {q: rng.uniform(1.0, 10.0, len(rows)) for q in QUANTITIES}
    return pl.DataFrame({"cell": [r[0] for r in rows], "point": [r[1] for r in rows], **data})


def test_on_grid_aligns_by_key_not_by_row_order() -> None:
    cells, points = [5, 2, 9], ["a", "b"]
    frame = _grid_frame(cells, points)
    shuffled = frame.sample(fraction=1.0, shuffle=True, seed=3)
    assert np.array_equal(on_grid(frame, cells, points), on_grid(shuffled, cells, points))


def test_on_grid_refuses_a_missing_target() -> None:
    frame = _grid_frame([1, 2], ["a", "b"]).filter(
        ~((pl.col("cell") == 2) & (pl.col("point") == "b"))
    )
    with pytest.raises(ValueError, match="missing"):
        on_grid(frame, [1, 2], ["a", "b"])


def _values(gaps: list[float]) -> dict[str, float]:
    v, out = 0.0, {}
    for name, g in zip(reversed(EXPECTED_ORDER), [0.0, *gaps], strict=True):
        v += g
        out[name] = v
    return out


def test_separation_measures_gaps_and_order() -> None:
    sep = separation(_values([0.3, 0.2, 0.1, 0.05, 0.02]))
    assert sep["order_as_expected"] and sep["kendall_tau_vs_expected"] == 1.0
    assert sep["best_null"] == EXPECTED_ORDER[0]
    assert sep["best_minus_runner_up"] == pytest.approx(0.02)
    assert sep["min_adjacent_gap"] == pytest.approx(0.02)

    swapped = _values([0.3, 0.2, 0.1, 0.05, 0.02])
    swapped["shuffled_target"] = 99.0  # chance first: the X4 failure
    s2 = separation(swapped)
    assert not s2["order_as_expected"] and s2["best_null"] == "shuffled_target"
    assert s2["kendall_tau_vs_expected"] < 1.0


def test_the_threshold_always_clears_the_gap_it_is_built_from() -> None:
    """E08 by construction: no null can satisfy `> threshold` against the best of the others."""
    rng = np.random.default_rng(4)
    for _ in range(20):
        sep15 = separation(_values(list(rng.uniform(0.0, 0.3, 5))))
        sep5 = separation(_values(list(rng.uniform(0.0, 0.3, 5))))
        draws = {n: rng.normal(0, 0.05, 50) for n in EXPECTED_ORDER}
        rule = threshold_rule(sep15, sep5, draws)
        assert rule["no_null_clears_it"]
        assert rule["threshold"] > max(sep15["best_minus_runner_up"], sep5["best_minus_runner_up"])
        assert rule["threshold"] == pytest.approx(round(rule["threshold"], 2))


def _arms() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    rng = np.random.default_rng(6)
    truth = rng.uniform(5.0, 10.0, size=(N_C, N_P, len(QUANTITIES)))
    band = 0.1 * truth
    preds = {
        n: truth * (1 + rng.normal(0, 0.05 * (i + 1), truth.shape))
        for i, n in enumerate(EXPECTED_ORDER)
    }
    return preds, truth, band


def test_score_arm_ranks_better_predictions_higher() -> None:
    preds, truth, band = _arms()
    points = [f"p{j}" for j in range(N_P)]
    vals = {n: score_arm(p, truth, band, points)[STATISTIC] for n, p in preds.items()}
    assert separation(vals)["order_as_expected"]


def test_the_tile_bootstrap_is_deterministic_under_its_seed() -> None:
    preds, truth, band = _arms()
    errors = {n: row_errors(p, truth, band) for n, p in preds.items()}
    rng = np.random.default_rng(8)
    lon, lat = rng.uniform(-180, 180, N_C), rng.uniform(-60, 80, N_C)
    a = tile_bootstrap(errors, lon, lat, degrees=15.0, n_boot=50, seed=1)
    b = tile_bootstrap(errors, lon, lat, degrees=15.0, n_boot=50, seed=1)
    for n in EXPECTED_ORDER:
        assert np.array_equal(a["draws"][n], b["draws"][n])
    assert 0.0 <= a["frac_full_expected_order"] <= 1.0


def test_a_failed_or_missing_model_target_is_never_credited(tmp_path: Path) -> None:
    """The synthesiser's table: `y0_` columns, a status, a fold. Failures are NOT dropped."""
    cells, points = [1, 2], ["a", "b"]
    frame = _grid_frame(cells, points).rename({q: f"y0_{q}" for q in QUANTITIES})
    frame = frame.with_columns(
        pl.Series("status", ["ok", "error", "ok", "ok"]), pl.Series("fold", [0, 0, 1, 1])
    ).filter(~((pl.col("cell") == 2) & (pl.col("point") == "b")))
    path = tmp_path / "synth_map.parquet"
    frame.write_parquet(path)
    basis = {"cell_ids": cells, "points": points}
    pred, cov = load_model_arm(path, basis, np.array([0, 1]), prefix="y0_")
    assert cov["targets_covered"] == 2 and cov["targets_missing_scored_as_never_credited"] == 2
    assert np.isnan(pred[0, 1]).all() and np.isnan(pred[1, 1]).all()
    truth = np.ones_like(pred)
    e = row_errors(pred, truth, np.full_like(pred, 0.1))
    assert np.isinf(e[0, 1]) and np.isinf(e[1, 1])
    with pytest.raises(ValueError, match="folds differ"):
        load_model_arm(path, basis, np.array([1, 1]), prefix="y0_")
