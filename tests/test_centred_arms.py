"""The centred kill tests' arm assembly, end to end on a synthetic corpus-shaped case.

The real run needs the 6,000-run pilot table, which CI does not have. What CI can check is that the
assembly the two model scripts share produces exactly the arms the pre-registrations declare, that
the three within-cell-constant arms (no change, the per-cell-mean oracle and the BLIND model) come
out at exactly 0.0 through the real learner and fold code, that the placebo-only mode never fits the
model, and that the result block carries every null beside the model. The learner is shrunk to ten
trees so the test is quick; nothing else about the path is replaced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import exp_model_pilot_response
from centred_arms import EXTRA_NULLS, Problem, assert_constant_within_cell, run_all_radii
from exp_derive_nulls_pilot import _per_level_and_pooled, centred_nulls
from exp_model_pilot_composition import FORCING_FEATURES

N_CELLS, N_POINTS = 60, 6
INFO_FREE = (
    "no_response",
    "level_mean_response",
    "proportional_median_response",
    "proportional_mean_response",
    "nearest_cell_response",
    "nearest_analogue_response",
    "shuffled_cells",
)


def _problem() -> Problem:
    rng = np.random.default_rng(21)
    names = ["ctl_a", "ctl_b", "tas_ann", *FORCING_FEATURES]
    x = np.zeros((N_CELLS, N_POINTS, len(names)))
    cell_part = rng.normal(size=(N_CELLS, 3))
    design = rng.normal(size=(N_POINTS, len(FORCING_FEATURES)))
    x[:, :, :3] = cell_part[:, None, :]
    x[:, :, 3:] = design[None, :, :] + 0.1 * cell_part[:, None, 2:3]
    q = ("q0", "q1")
    dtrue = np.stack(
        [
            cell_part[:, None, 0] + design[None, :, 0] * cell_part[:, None, 1],
            2.0 * cell_part[:, None, 1] - design[None, :, 1],
        ],
        axis=2,
    ) + rng.normal(scale=0.1, size=(N_CELLS, N_POINTS, 2))
    dtrue[:4, :2, 1] = np.nan  # undefined pairs, as the real corpus has
    analogue = ("z_tas_ann", "z_pr_ann", "z_pr_seasonality", "z_rsds_ann", "z_tas_iav")
    cells = pl.DataFrame(
        {
            "lon": rng.uniform(-180, 180, N_CELLS),
            "lat": rng.uniform(-56, 84, N_CELLS),
            **{f: rng.normal(size=N_CELLS) for f in analogue},
        }
    )
    control = rng.uniform(0.5, 2.0, size=(N_CELLS, 2))
    return Problem(x, names, dtrue, control, cells, [f"p{j}" for j in range(N_POINTS)], q)


@pytest.fixture(autouse=True)
def _small_learner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(exp_model_pilot_response.PARAMS, "n_estimators", 10)
    monkeypatch.setitem(exp_model_pilot_response.PARAMS, "min_child_samples", 5)


def _run(placebos_only: bool) -> dict[str, object]:
    return run_all_radii(
        _problem(),
        k=5,
        radii=(15.0,),
        threshold=0.05,
        statistic="skill_response_centred_mean",
        uncentred=_per_level_and_pooled,
        placebos_only=placebos_only,
    )


def test_the_arms_are_exactly_the_declared_ones_and_the_constant_ones_are_exactly_zero() -> None:
    out = _run(placebos_only=False)
    arms = out["by_blocking"]["15deg"]["arms"]  # type: ignore[index]
    assert set(arms) == {"model", *INFO_FREE, *EXTRA_NULLS}
    for name in ("no_response", "cell_mean_oracle", "blind_model"):
        assert arms[name]["pooled"] == 0.0, name
    assert set(out["arms"]) == set(arms)  # type: ignore[arg-type]
    assert out["statistic"] == "skill_response_centred_mean"
    assert "decision" in out
    diag = out["by_blocking"]["15deg"]["uncentred_diagnostics"]  # type: ignore[index]
    assert set(diag) == {"model", "blind_model", "scrambled_forcing"}


def test_placebos_only_never_fits_the_model_and_writes_no_result_block() -> None:
    out = _run(placebos_only=True)
    arms = out["by_blocking"]["15deg"]["arms"]  # type: ignore[index]
    assert "model" not in arms
    assert {"blind_model", "scrambled_forcing"} <= set(arms)
    assert "arms" not in out and "decision" not in out


def test_the_null_derivation_matches_the_model_run_arm_for_arm() -> None:
    """The values sealed from the derivation must be the values the model job recomputes."""
    p = _problem()
    derived = centred_nulls(
        p.dtrue,
        p.control,
        p.scored_cells,
        p.points,
        quantities=p.quantities,
        k=5,
        radii=(15.0,),
        uncentred=_per_level_and_pooled,
    )["15deg"]["nulls"]  # type: ignore[index]
    arms = _run(placebos_only=True)["by_blocking"]["15deg"]["arms"]  # type: ignore[index]
    for name, v in derived.items():
        assert arms[name]["pooled"] == v["pooled"], name


def test_a_prediction_that_varies_within_a_cell_is_refused_as_blind() -> None:
    pred = np.ones((3, 4, 2))
    assert_constant_within_cell(pred, "ok")
    pred[1, 2, 0] = 2.0
    with pytest.raises(AssertionError, match="vary within the cell"):
        assert_constant_within_cell(pred, "bad")
