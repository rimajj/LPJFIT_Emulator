"""The spin-up vegetation-carbon DEV screen (`scripts/screen_spinup_vegc.py`), on synthetic cells.

What CI can check without the cluster: no feature set carries a location or CO2 column; a fold's
training rows never include a cell of that fold, whatever the pool or target; the rerun reference
of a subset is recomputed on that subset; the greedy choice reads the dev statistic only; and the
fitting paths (early stopping, the two-stage gate, bagging, the zero floor) predict every cell of
the held-out fold and nothing else.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import screen_spinup_vegc as scr
from exp_equilibrium_map import FORBIDDEN

N_G, N_P, N_PT, F = 300, 20, 3, 6


def _data(seed: int = 0) -> scr.Data:
    rng = np.random.default_rng(seed)
    xg = rng.normal(size=(N_G, F))
    xp = rng.normal(size=(N_P, N_PT, F))
    lg = 5.0 + xg[:, 0] + 0.3 * xg[:, 1]
    lp = 5.0 + xp[..., 0] + 0.3 * xp[..., 1]
    s_g = np.stack([np.expm1(lg), np.expm1(lg + rng.normal(0, 0.05, N_G))], axis=1)
    s_p = np.stack([np.expm1(lp), np.expm1(lp + rng.normal(0, 0.05, lp.shape))], axis=2)
    tiles_g = np.arange(N_G) // 3
    folds_g = tiles_g % 5  # whole tiles, as the sealed tile -> fold map
    folds_g[tiles_g < 4] = -1  # tiles no pilot cell covers: they train every fold, never scored
    tb_g = xg[:, 2] > -1.0
    sel = (folds_g >= 0) & tb_g
    t1, t2 = s_g[sel, 1], s_g[sel, 0]
    w = np.full(sel.sum(), 0.10)
    rerun = ((np.abs(t2 - t1) <= w * t1).astype(float) + (np.abs(t1 - t2) <= w * t2)) / 2
    sc = {
        "mask": sel,
        "t1": t1,
        "t2": t2,
        "tm": (t1 + t2) / 2,
        "w": w,
        "lat": rng.uniform(-50, 70, sel.sum()),
        "tile": tiles_g[sel],
        "rerun_cell": rerun,
        "frac_rerun": float(rerun.mean()),
        "fold": folds_g[sel].astype(float),
    }
    feats = {"base": xg, "v3": xg, "v3x": xg}
    pfeats = {"base": xp, "v3": xp, "v3x": xp}
    return scr.Data(
        xg=feats,
        xp=pfeats,
        yg={
            "win": s_g.mean(axis=1),
            "half2": s_g.mean(axis=1),
            "win_seeds": s_g,
            "half2_seeds": s_g,
        },
        yp={
            "win": s_p.mean(axis=2),
            "half2": s_p.mean(axis=2),
            "win_seeds": s_p,
            "half2_seeds": s_p,
        },
        tb_g=tb_g,
        tb_p=np.ones((N_P, N_PT), dtype=bool),
        folds_g=folds_g.astype(np.int64),
        folds_p=(np.arange(N_P) % 5).astype(np.int64),
        tiles_g=tiles_g.astype(np.int64),
        tiles_p=(np.arange(N_P) + 1000).astype(np.int64),
        sc=sc,
        extra={
            "tree_share": np.full(sel.sum(), 0.8),
            "trend": np.zeros(sel.sum()),
            "spread": np.zeros(sel.sum()),
            "cell": np.flatnonzero(sel).astype(float),
        },
    )


@pytest.fixture(autouse=True)
def _small_learner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(scr.PARAMS, "n_estimators", 30)
    monkeypatch.setitem(scr.BIG, "n_estimators", 120)
    monkeypatch.setattr(scr, "PATIENCE", 10)


def test_no_feature_set_carries_a_location_or_co2() -> None:
    for name, cols in scr.FEATURE_SETS.items():
        assert not FORBIDDEN & set(cols), name
        assert not any("co2" in c.lower() for c in cols), name
        assert len(set(cols)) == len(cols), name
    assert scr.FEATURE_SETS["v3x"][: len(scr.FEATURE_SETS["v3"])] == scr.FEATURE_SETS["v3"]


@pytest.mark.parametrize("pool", ["spinup", "pilot", "both"])
@pytest.mark.parametrize("target", scr.TARGETS)
def test_a_folds_training_rows_never_include_that_fold(pool: str, target: str) -> None:
    d = _data()
    r = scr.Recipe("t", pool=pool, target=target, pilot_weight=0.25)
    for f in range(5):
        x, y, w, tiles, tb = scr.training_rows(d, r, f)
        held_tiles = set(d.tiles_g[d.folds_g == f]) | set(d.tiles_p[d.folds_p == f])
        assert not held_tiles & set(tiles.tolist())
        n_g = int((d.folds_g != f).sum()) if pool != "pilot" else 0
        n_p = int((d.folds_p != f).sum()) * N_PT if pool != "spinup" else 0
        reps = 2 if target.endswith("_seeds") else 1
        assert y.size == x.shape[0] == w.size == tb.size == reps * (n_g + n_p)
        assert np.isfinite(y).all()
        # The source is a weight, never a column.
        assert x.shape[1] == F
        assert set(np.unique(w)) <= {1.0, 0.25}
        assert (w == 0.25).sum() == reps * n_p


def test_subset_recomputes_the_rerun_reference_on_its_own_cells() -> None:
    d = _data()
    sel = np.asarray(d.sc["fold"]) == 3
    sub = scr.subset(d.sc, sel)
    assert sub["frac_rerun"] == pytest.approx(np.asarray(d.sc["rerun_cell"])[sel].mean())
    assert sub["t1"].size == int(sel.sum())


def test_the_choice_reads_dev_only_and_needs_more_than_min_gain() -> None:
    assert scr.choose(-0.40, {"a": -0.40 + scr.MIN_GAIN / 2, "b": -0.41}) is None
    assert scr.choose(-0.40, {"a": -0.38, "b": -0.39}) == "a"
    assert scr.choose(-0.40, {}) is None


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"capacity": "big"},
        {"gate": "hard"},
        {"gate": "soft", "target": "half2_seeds"},
        {"objective": "huber", "bag": 2},
        {"objective": "l1", "zero_floor": 1e9},
        {"pool": "both", "pilot_weight": 0.25},
        {"objective": "l1+l2", "gate": "soft"},
        {"objective": "l1+huber", "capacity": "big"},
    ],
)
def test_every_fitting_path_predicts_exactly_the_held_out_fold(change: dict[str, object]) -> None:
    d = _data(1)
    r = dataclasses.replace(scr.Recipe("t"), **change)  # type: ignore[arg-type]
    pred, info = scr.predict_all(d, r, (0, 1, 2, 3, 4), workers=2, threads=1)
    assert np.isfinite(pred[d.folds_g >= 0]).all()
    assert np.isnan(pred[d.folds_g < 0]).all()
    assert (pred[d.folds_g >= 0] >= 0).all()
    if change.get("zero_floor"):
        assert (pred[d.folds_g >= 0] == 0).all()
    ev = scr.evaluate(pred[d.sc["mask"]], d.sc)
    assert set(ev) == {"dev", "held", "all"}
    assert ev["dev"]["cells"] + ev["held"]["cells"] == ev["all"]["cells"]
    assert set(info) == {"0", "1", "2", "3", "4"}


def test_a_learnable_signal_beats_the_mean() -> None:
    d = _data(2)
    pred, _ = scr.predict_all(d, scr.Recipe("t"), (0, 1, 2, 3, 4), workers=2, threads=1)
    ev = scr.evaluate(pred[d.sc["mask"]], d.sc)
    assert ev["all"]["skill_log1p"] > 0.5


def test_error_structure_bins_cover_the_cells() -> None:
    d = _data(3)
    pred, _ = scr.predict_all(d, scr.Recipe("t"), (0, 1, 2, 3, 4), workers=2, threads=1)
    es = scr.error_structure(pred[d.sc["mask"]], d, scr.DEV_FOLDS)
    n = sum(row["cells"] for row in es["carbon_gC_m2"])
    assert n == es["cells"]
    assert 0.0 <= es["frac"] <= 1.0


def test_a_recipe_survives_its_json_round_trip() -> None:
    r = scr.Recipe(
        "x",
        feats="v3x",
        target="half2_seeds",
        gate="soft",
        objective="l1",
        capacity="tuned",
        params=(("learning_rate", 0.05), ("num_leaves", 63)),
        pool="both",
        bag=5,
    )
    back = scr.recipe_of(json.loads(json.dumps(dataclasses.asdict(r))))
    assert back == r and back.key() == r.key()


def test_a_recipe_is_deterministic_whatever_the_parallelism() -> None:
    """Round 2 re-runs round 1's best and must get round 1's number, so a fit may not depend on
    how many folds run at once (the round-2 job itself checks the number)."""
    d = _data(4)
    a, _ = scr.predict_all(d, scr.Recipe("t", objective="l1", gate="soft"), (0, 1), 1, 1)
    b, _ = scr.predict_all(d, scr.Recipe("t", objective="l1", gate="soft"), (0, 1), 2, 1)
    np.testing.assert_array_equal(a, b)
