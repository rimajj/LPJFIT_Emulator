"""The composition arm's two load-bearing claims, as executable assertions.

WHY THESE TWO AND NOT A NUMBER. The values the composition nulls must return are derived on the
cluster from a 6,000-run corpus that CI has no access to, so this file cannot check them. What it
CAN check is the two properties that would silently corrupt those values if they broke, and both
are properties of code that ships in this repository:

  * `derive_nulls` was split into `build_null_predictions` + the scorer so the composition arm could
    reuse the null arithmetic instead of re-implementing it. That split is only safe if it changed
    nothing. A sealed pre-registration's seven null values were measured by the pre-split code, so a
    drift here would invalidate `X-20260909-pilot-warming-response` without touching its files.
  * a treeless cell's `pft_frac_*` is written as 0.0 by `corpus/state.py`, and reading that as a
    composition CHANGE double-counts the forest collapse that `stems_per_patch` already scores. The
    masking is the whole reason the composition estimand is honest, so it is tested, not trusted.

Also asserted: that the sealed tuple still has exactly the seven members its pre-registration names.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_derive_nulls_composition import impute_no_change
from exp_derive_nulls_pilot import (
    _per_level_and_pooled,
    build_null_predictions,
    derive_nulls,
)
from vegemu.score import (
    COMPOSITION_QUANTITIES,
    RESPONSE_QUANTITIES,
    blank_treeless_composition,
)

N_CELLS, N_POINTS = 60, 5


def _fake_case(seed: int = 11) -> tuple[np.ndarray, np.ndarray, pl.DataFrame, list[str]]:
    """A corpus-shaped case with the awkward parts present: NaNs, and a zero control level."""
    rng = np.random.default_rng(seed)
    q = len(COMPOSITION_QUANTITIES)
    dtrue = rng.normal(size=(N_CELLS, N_POINTS, q))
    dtrue[rng.random(dtrue.shape) < 0.08] = np.nan  # undefined pairs, as the real corpus has
    control = rng.uniform(0.0, 1.0, size=(N_CELLS, q))
    control[:3, 0] = 0.0  # a zero control makes the proportional null's fraction undefined
    analogue = ("z_tas_ann", "z_pr_ann", "z_pr_seasonality", "z_rsds_ann", "z_tas_iav")
    cells = pl.DataFrame(
        {
            "lon": rng.uniform(-180, 180, N_CELLS),
            "lat": rng.uniform(-56, 84, N_CELLS),
            **{f: rng.normal(size=N_CELLS) for f in analogue},
        }
    )
    return dtrue, control, cells, [f"p{j}" for j in range(N_POINTS)]


def test_splitting_derive_nulls_changed_nothing() -> None:
    """`derive_nulls` must equal scoring `build_null_predictions`, arm for arm, bit for bit.

    This is the guard on a sealed experiment: `X-20260909-pilot-warming-response` records seven null
    values measured before the split, and nothing in its own directory would go red if they drifted.
    """
    dtrue, control, cells, points = _fake_case()
    q = COMPOSITION_QUANTITIES
    direct = derive_nulls(dtrue, control, cells, points, quantities=q, k=5, degrees=15.0)
    viasplit = {
        name: _per_level_and_pooled(pred, dtrue, points, q)
        for name, pred in build_null_predictions(
            dtrue, control, cells, points, k=5, degrees=15.0
        ).items()
    }
    assert direct.keys() == viasplit.keys()
    for name in direct:
        a, b = direct[name]["pooled"], viasplit[name]["pooled"]
        assert a == b or (np.isnan(a) and np.isnan(b)), f"{name} drifted: {a} vs {b}"
        assert direct[name]["per_quantity"] == viasplit[name]["per_quantity"], name


def test_no_response_null_is_pinned_at_zero_after_imputation() -> None:
    """Imputing missing predictions as no-change must not move the analytic floor off 0.0.

    The whole point of the imputation is a common denominator across arms; it would be worthless if
    it also shifted the one null whose value is known exactly rather than measured.
    """
    dtrue, _control, _cells, points = _fake_case()
    filled, counts = impute_no_change(np.zeros_like(dtrue), dtrue)
    assert sum(counts.values()) == 0, "an all-zero prediction is finite and needs no filling"
    scored = _per_level_and_pooled(filled, dtrue, points, COMPOSITION_QUANTITIES)
    assert scored["pooled"] == pytest.approx(0.0, abs=1e-12)


def test_imputation_puts_every_arm_on_the_same_denominator() -> None:
    """An arm that declines to answer must be charged for it, not scored on an easier subset."""
    dtrue, _control, _cells, _points = _fake_case()
    lazy = np.full_like(dtrue, np.nan)
    lazy[:, :, 0] = dtrue[:, :, 0]  # perfect where it answers, silent everywhere else
    filled, counts = impute_no_change(lazy, dtrue)
    scorable = np.isfinite(dtrue)
    assert np.isfinite(filled[scorable]).all(), "every scorable pair must carry a prediction"
    # Silent on six of seven quantities, so it is charged the no-change score on all six.
    assert counts[COMPOSITION_QUANTITIES[0]] == 0
    assert counts[COMPOSITION_QUANTITIES[1]] == int(scorable[:, :, 1].sum())


def test_treeless_composition_is_blanked_not_zeroed() -> None:
    """A cell with no stems has no mix; 0.0 there is a collapse wearing a composition's clothes."""
    frame = pl.DataFrame(
        {
            "cell": [1, 2, 3],
            "stems_total": [120.0, 0.0, 44.0],
            **{c: [0.5, 0.0, 0.25] for c in COMPOSITION_QUANTITIES},
        }
    )
    masked = blank_treeless_composition(frame)
    values = masked.select(COMPOSITION_QUANTITIES).to_numpy().astype(np.float64)
    assert np.isfinite(values[0]).all(), "a treed row must be left exactly as it was"
    assert np.isnan(values[1]).all(), "the treeless row must be NaN in every type share"
    assert np.isfinite(values[2]).all()
    # Idempotent: the masking runs on cached tables that may already have been masked.
    assert blank_treeless_composition(masked).equals(masked)


def test_blanking_refuses_a_table_that_has_no_composition() -> None:
    """Silently returning an unmasked frame would be the failure this function exists to prevent."""
    with pytest.raises(ValueError, match="missing"):
        blank_treeless_composition(pl.DataFrame({"cell": [1], "stems_total": [3.0]}))


def test_the_sealed_response_tuple_is_untouched() -> None:
    """Composition is a separate arm. Appending to this tuple redefines a sealed experiment."""
    assert RESPONSE_QUANTITIES == (
        "stems_per_patch",
        "agb",
        "lai",
        "soilc",
        "height_p50",
        "wooddens_p50",
        "sla_p50",
    )
    assert not set(COMPOSITION_QUANTITIES) & set(RESPONSE_QUANTITIES)
    assert len(COMPOSITION_QUANTITIES) == 7
