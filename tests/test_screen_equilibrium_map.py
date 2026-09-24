"""The dev screen's apparatus (`scripts/screen_equilibrium_map.py`), on synthetic data.

The screen's numbers come from the cluster. What CI can check is the part a selection rule rests
on: the dev folds are never trained on the held-out folds, the held-out regime is the sealed
out-of-fold construction restricted to folds 3-4, every target form decodes back to the sealed
scale, a learning-curve subsample keeps whole cells, the two-stage inputs of a row never come from
a model that saw its cell, and the bar arithmetic reproduces the sealed experiment's own bar.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import screen_equilibrium_map as scr
from exp_equilibrium_map import FEATURES, LOG_QUANTITIES, QUANTITIES, forward
from vegemu.corpus.features_v3 import V3_FEATURES

N_CELLS, N_POINTS = 40, 6
TINY = (("n_estimators", 5), ("min_child_samples", 5))


def _data() -> scr.Data:
    rng = np.random.default_rng(1)
    raw = np.exp(rng.normal(size=(N_CELLS, N_POINTS, len(QUANTITIES))))
    for t in scr.TRAITS:  # a real run's quantiles are ordered, so the synthetic ones are too
        cols = [QUANTITIES.index(f"{t}_{p}") for p in ("p10", "p50", "p90")]
        raw[..., cols] = np.sort(raw[..., cols], axis=-1)
    raw[:2, :2, 4:] = np.nan  # treeless rows: traits undefined
    y = np.stack([forward(q, raw[..., j]) for j, q in enumerate(QUANTITIES)], axis=-1)
    return scr.Data(
        x_base=rng.normal(size=(N_CELLS, N_POINTS, len(FEATURES))),
        x_v3=rng.normal(size=(N_CELLS, N_POINTS, len(V3_FEATURES))),
        y=y,
        raw=raw,
        shares=rng.dirichlet(np.ones(7), size=(N_CELLS, N_POINTS)),
        folds=np.arange(N_CELLS, dtype=np.int64) % 5,
        lon=rng.uniform(-180, 180, N_CELLS),
        lat=rng.uniform(-50, 70, N_CELLS),
        points=[f"p{i}" for i in range(N_POINTS)],
        soil_bin=Path("unused"),
    )


@pytest.mark.parametrize("mode", ["sealed", "log", "gaps"])
def test_every_target_form_decodes_to_the_sealed_scale(mode: str) -> None:
    d = _data()
    z, names = scr.encode(d.raw, d.y, mode)
    assert z.shape[-1] == len(names) == len(QUANTITIES)
    back = scr.decode(z.reshape(-1, z.shape[-1]), mode).reshape(d.y.shape)
    ok = np.isfinite(d.y)
    np.testing.assert_allclose(back[ok], d.y[ok], rtol=1e-10)


def test_gap_form_can_never_cross_its_quantiles() -> None:
    rng = np.random.default_rng(2)
    z = rng.normal(size=(500, len(QUANTITIES)))
    out = scr.decode(z, "gaps")
    for t in scr.TRAITS:
        p10, p50, p90 = (out[:, QUANTITIES.index(f"{t}_{p}")] for p in ("p10", "p50", "p90"))
        assert (p10 <= p50).all() and (p50 <= p90).all()


def test_dev_regime_never_trains_on_the_held_out_folds() -> None:
    folds = np.arange(N_CELLS, dtype=np.int64) % 5
    held = np.isin(folds, scr.HELD_FOLDS)
    for f, train, test in scr.splits(folds, "dev"):
        assert f in scr.DEV_FOLDS
        assert not (train & held).any()
        assert not (train & test).any()
        assert (test == (folds == f)).all()


def test_held_regime_is_the_sealed_out_of_fold_split_restricted() -> None:
    folds = np.arange(N_CELLS, dtype=np.int64) % 5
    got = scr.splits(folds, "held")
    assert [f for f, _, _ in got] == list(scr.HELD_FOLDS)
    for f, train, test in got:
        assert (train == (folds != f)).all() and (test == (folds == f)).all()


def test_learning_curve_subsample_keeps_whole_cells() -> None:
    train = np.zeros(100, dtype=bool)
    train[:80] = True
    sub = scr._subsample(train, 0.25, seed=0, fold=3)
    assert sub.sum() == 20 and not (sub & ~train).any()
    rows = scr._rows(sub, N_POINTS)
    assert rows.size == 20 * N_POINTS
    assert (scr._subsample(train, 1.0, 0, 3) == train).all()


def test_bar_rule_reproduces_the_sealed_bar() -> None:
    """The sealed record: analogue beat training mean by 0.112026 at 5 deg, plus 0.0118 of
    headroom, rounded up to 0.125."""
    nulls = {
        "training_mean": {"pooled": -0.007914},
        "nearest_analogue": {"pooled": 0.104112},
        "nearest_geographic": {"pooled": -0.138043},
        "shuffled": {"pooled": -0.927463},
    }
    b = scr.bar_rule(nulls)
    assert b["best_null"] == "nearest_analogue" and b["runner_up"] == "training_mean"
    assert b["bar"] == pytest.approx(0.125)


def test_two_stage_inputs_never_come_from_a_model_that_saw_the_cell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = _data()
    eng = scr.Engine(d, workers=1)
    seen: list[tuple[np.ndarray, np.ndarray]] = []

    def fake(tasks: list[tuple[Any, ...]]) -> list[np.ndarray]:
        for t in tasks:
            seen.append((t[2], t[3]))
        return [np.zeros(t[3].size) for t in tasks]

    monkeypatch.setattr(eng, "_run", fake)
    recipe = scr.Recipe("t", stage2=True, params=TINY)
    for _, train, test in scr.splits(d.folds, "dev"):
        eng._stage1(scr.features(d, recipe)[0], train, test, recipe)
    assert seen
    for tr, te in seen:
        assert not set(tr // N_POINTS) & set(te // N_POINTS)


def test_engine_predicts_exactly_the_regimes_test_cells() -> None:
    d = _data()
    eng = scr.Engine(d, workers=1)
    for recipe in (scr.Recipe("a", params=TINY), scr.Recipe("b", target="gaps", params=TINY)):
        pred = eng.predict(recipe, "dev")
        dev = np.isin(d.folds, scr.DEV_FOLDS)
        j = QUANTITIES.index("agb")
        assert np.isfinite(pred[dev][..., j]).all()
        assert np.isnan(pred[~dev]).all()
        s = scr.score(d, pred, dev)
        assert s["cells"] == int(dev.sum()) and np.isfinite(s["pooled"])


def test_no_forbidden_column_in_any_feature_list() -> None:
    d = _data()
    for r in (scr.Recipe("a"), scr.Recipe("b", v3=True), scr.Recipe("c", v3=True, soil=False)):
        _, names = scr.features(d, r)
        assert not scr.FORBIDDEN & set(names)
    assert set(scr.FOREST) == set(LOG_QUANTITIES)
