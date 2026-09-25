"""The worst-quantity score (C1), the cross-climate band, and the shared acceptance utilities.

C1 replaces a yes/no per row with a number per row, and the one thing it must NOT do while doing
so is move the acceptance number. So the load-bearing claims here are equivalences, not ranges:

  * on rows where every truth exists, "e <= 1" is exactly `band_frac_conjunctive`'s pass bit;
  * the decision statistic is a fixed, parameter-free function of e -- pinned on hand-computed
    cases, so a later "improvement" that adds an epsilon or a cap turns this red;
  * the missing-value rules are the ones the section comment in `score.py` states;
  * the cross-climate band never contains the scored climate's own disagreement, which is what
    stops the ceiling being 1.0 by arithmetic;
  * the new names leave every pinned old name byte-identical.
"""

from __future__ import annotations

import numpy as np
import pytest

from vegemu.score import (
    ABS_FLOOR_COMPOSITION,
    COMPOSITION_QUANTITIES,
    CONSTANT_ON_PILOT,
    FLOOR,
    SCORED_CONJUNCTIVE,
    SCORED_VARYING,
    SCORED_WITH_COMPOSITION,
    abs_floor_vector,
    acceptance_band,
    acceptance_band_transferred,
    acceptance_band_with_composition,
    assert_constant_quantities,
    band_frac_conjunctive,
    band_frac_with_composition,
    band_from_spread,
    band_hits,
    ceiling_arm,
    describe_basis,
    relative_spread,
    score_worst_quantity,
    spread_across_climates,
    worst_quantity_error,
    worst_quantity_skill,
)


def _pair(n: int = 400, m: int = 5, spread: float = 0.3, seed: int = 7):
    rng = np.random.default_rng(seed)
    level = rng.uniform(1.0, 100.0, size=(n, m))
    delta = level * rng.uniform(-spread, spread, size=(n, m))
    return level + delta / 2, level - delta / 2


# --- the pinned names --------------------------------------------------------------------------


def test_the_pinned_scored_set_is_unchanged() -> None:
    """Sealed experiments measure THESE 22, in THIS order. A new set is a new name."""
    assert SCORED_CONJUNCTIVE == (
        "stems_per_patch",
        "agb",
        "lai",
        "soilc",
        "wooddens_p50",
        "sla_p50",
        "k_root_p50",
        "D95max_p50",
        "longevity_p50",
        "height_p50",
        "wooddens_p10",
        "wooddens_p90",
        "sla_p10",
        "sla_p90",
        "k_root_p10",
        "k_root_p90",
        "D95max_p10",
        "D95max_p90",
        "longevity_p10",
        "longevity_p90",
        "height_p10",
        "height_p90",
    )


def test_the_varying_set_is_the_22_minus_fine_root_conductivity() -> None:
    assert len(SCORED_VARYING) == 19
    assert set(SCORED_CONJUNCTIVE) - set(SCORED_VARYING) == set(CONSTANT_ON_PILOT)
    assert [q for q in SCORED_CONJUNCTIVE if q in SCORED_VARYING] == list(SCORED_VARYING)


def test_the_composition_set_is_the_22_then_the_seven_shares() -> None:
    assert SCORED_WITH_COMPOSITION[:22] == SCORED_CONJUNCTIVE
    assert SCORED_WITH_COMPOSITION[22:] == COMPOSITION_QUANTITIES
    floors = abs_floor_vector(SCORED_WITH_COMPOSITION)
    assert np.all(floors[:22] == 0.0) and np.all(floors[22:] == ABS_FLOOR_COMPOSITION)


def test_describe_basis_defaults_reproduce_the_old_sentence_byte_for_byte() -> None:
    old = (
        "LPJmL-FIT historical leg, state at 1999 from the restart file, climate window "
        "1970-1999, npatch=25, truth = mean of seeds 1+2, 100 tree-bearing cells, "
        "dimensionless fraction (level)"
    )
    assert describe_basis("historical", 1999, (1970, 1999), 100) == old
    assert describe_basis("h->s", 2100, (2071, 2100), 5, kind="ratio").endswith("(ratio)")
    with pytest.raises(ValueError, match="kind"):
        describe_basis("h", 1999, (1970, 1999), 1, kind="change")


# --- C1: the per-row error ---------------------------------------------------------------------


def test_e_is_the_worst_quantity_in_band_units() -> None:
    truth = np.array([[10.0, 100.0, 1.0]])
    band = np.array([[1.0, 10.0, 0.1]])
    pred = np.array([[10.5, 130.0, 1.05]])  # 0.5, 3.0, 0.5 bands
    assert worst_quantity_error(pred, truth, band)[0] == pytest.approx(3.0)


def test_e_at_most_one_is_exactly_the_conjunctive_pass_bit_on_fully_defined_rows() -> None:
    """THE refactor-safety property: C1 does not move the acceptance number where both apply."""
    s1, s2 = _pair(spread=0.6, seed=3)
    ref1, ref2 = _pair(spread=0.05, seed=4)
    truth, band = acceptance_band_transferred(s1, s2, ref1, ref2, abs_floor=0.0)
    rng = np.random.default_rng(5)
    for scale in (0.02, 0.1, 0.3):
        pred = truth * (1 + rng.normal(0, scale, truth.shape))
        res = score_worst_quantity(pred, truth, band, [f"q{i}" for i in range(truth.shape[1])])
        assert res["share_within_band"] == band_frac_conjunctive(pred, truth, band)
        bits = band_hits(pred, truth, band).all(axis=1)
        e = worst_quantity_error(pred, truth, band)
        assert np.array_equal(bits, e <= 1.0)


def test_a_missing_prediction_is_never_credited() -> None:
    truth = np.array([[1.0, 2.0], [1.0, 2.0]])
    band = np.full((2, 2), 0.5)
    pred = np.array([[np.nan, 2.0], [1.0, 2.0]])
    e = worst_quantity_error(pred, truth, band)
    assert np.isinf(e[0]) and e[1] == 0.0


def test_a_quantity_the_truth_lacks_is_not_scored() -> None:
    """A treeless run has no wood density; it is scored on what it has, both ways round."""
    truth = np.array([[0.0, 500.0, np.nan]])  # stems, soil carbon, a trait quantile
    band = np.array([[0.0, 50.0, np.nan]])
    treeless_pred = np.array([[0.0, 520.0, np.nan]])
    assert worst_quantity_error(treeless_pred, truth, band)[0] == pytest.approx(0.4)
    forest_pred = np.array([[3.0, 500.0, 600.0]])  # a forest where there is none: the collapse
    assert np.isinf(worst_quantity_error(forest_pred, truth, band)[0])


def test_a_zero_band_passes_only_an_exact_prediction() -> None:
    truth = np.zeros((3, 1))
    band = np.zeros((3, 1))
    pred = np.array([[0.0], [1e-12], [np.nan]])
    e = worst_quantity_error(pred, truth, band)
    assert e[0] == 0.0 and np.isinf(e[1]) and np.isinf(e[2])


def test_a_row_with_nothing_scored_is_never_credited() -> None:
    truth = np.full((1, 3), np.nan)
    e = worst_quantity_error(np.zeros((1, 3)), truth, np.ones((1, 3)))
    assert np.isinf(e[0])


# --- C1: the decision statistic ----------------------------------------------------------------


def test_the_statistic_is_minus_log_of_the_lower_median() -> None:
    """Pinned on hand-computed values. No epsilon, no cap: an edit adding either turns this red."""
    assert worst_quantity_skill(np.array([1.0, 2.0, 4.0])) == pytest.approx(-np.log(2.0))
    # Even count: the LOWER median is the 2nd of 4, never the average of the middle two.
    assert worst_quantity_skill(np.array([4.0, 1.0, 2.0, 8.0])) == pytest.approx(-np.log(2.0))
    # Infinities sort to the end and move the median by one position, nothing more.
    assert worst_quantity_skill(np.array([0.5, 0.5, np.inf])) == pytest.approx(np.log(2.0))
    assert worst_quantity_skill(np.array([0.0, 0.0, 3.0])) == np.inf
    assert worst_quantity_skill(np.array([np.inf, np.inf, 3.0])) == -np.inf
    assert np.isnan(worst_quantity_skill(np.array([])))


def test_higher_is_better_and_the_sign_ties_to_the_acceptance_number() -> None:
    truth = np.ones((101, 2))
    band = np.full((101, 2), 0.1)
    rng = np.random.default_rng(9)
    good = truth + rng.normal(0, 0.03, truth.shape)
    bad = truth + rng.normal(0, 0.3, truth.shape)
    names = ["a", "b"]
    g = score_worst_quantity(good, truth, band, names)
    b = score_worst_quantity(bad, truth, band, names)
    assert g["worst_quantity_skill"] > b["worst_quantity_skill"]
    for r in (g, b):
        assert (r["worst_quantity_skill"] >= 0) == (r["share_within_band"] >= 0.5)


def test_binding_counts_say_which_quantity_sets_e() -> None:
    truth = np.ones((4, 2))
    band = np.full((4, 2), 0.1)
    pred = np.array([[1.0, 1.5], [1.0, 1.5], [1.5, 1.0], [1.0, 1.01]])
    res = score_worst_quantity(pred, truth, band, ["a", "b"])
    assert res["binding"] == {"b": 3, "a": 1}


# --- the cross-climate band --------------------------------------------------------------------


def test_the_cross_climate_band_leaves_the_scored_climate_out() -> None:
    """Change ONE climate's pair wildly: its own band must not move; its neighbours' may."""
    rng = np.random.default_rng(1)
    base = rng.uniform(10, 20, size=(3, 7, 2))
    s1 = base * (1 + rng.uniform(-0.1, 0.1, base.shape))
    s2 = base * (1 + rng.uniform(-0.1, 0.1, base.shape))
    before = spread_across_climates(s1, s2)
    s1b = s1.copy()
    s1b[:, 3, :] *= 5.0
    after = spread_across_climates(s1b, s2)
    assert np.array_equal(before[:, 3, :], after[:, 3, :])


def test_the_cross_climate_band_is_the_floored_median_of_the_other_climates() -> None:
    s1 = np.array([[[1.0], [1.0], [1.0], [1.0]]])
    s2 = np.array([[[1.0], [0.5], [0.8], [0.6]]])
    raw = np.abs(s1 - s2) / np.abs((s1 + s2) / 2)
    out = spread_across_climates(s1, s2)
    for j in range(4):
        others = np.delete(raw[0, :, 0], j)
        assert out[0, j, 0] == pytest.approx(max(FLOOR, float(np.median(others))))


def test_a_cell_quantity_with_no_defined_spread_gets_the_bare_floor() -> None:
    z = np.zeros((2, 3, 2))
    assert np.array_equal(spread_across_climates(z, z), np.full((2, 3, 2), FLOOR))


def test_the_ceiling_is_not_one_by_arithmetic_under_the_cross_climate_band() -> None:
    """The same-climate band makes one run pass everywhere; leaving the climate out must not."""
    rng = np.random.default_rng(2)
    base = rng.uniform(10, 20, size=(40, 10, 3))
    noise = rng.uniform(0.0, 0.8, size=(40, 10, 3))  # climate-to-climate varying disagreement
    s1, s2 = base * (1 + noise / 2), base * (1 - noise / 2)
    spread = spread_across_climates(s1, s2)
    pred, truth, band = ceiling_arm(
        s1.reshape(-1, 3), s2.reshape(-1, 3), spread.reshape(-1, 3), abs_floor=0.0, truth_is="mean"
    )
    assert band_frac_conjunctive(pred, truth, band) < 1.0
    # ...while under the same-climate band it is 1.0 exactly, which is why that band is refused.
    t_same, b_same = acceptance_band(s1.reshape(-1, 3), s2.reshape(-1, 3), abs_floor=0.0)
    assert band_frac_conjunctive(s1.reshape(-1, 3), t_same, b_same) == 1.0


def test_the_ceiling_refuses_the_circular_band() -> None:
    s1, s2 = _pair()
    with pytest.raises(ValueError, match="circular"):
        ceiling_arm(s1, s2, relative_spread(s1, s2), abs_floor=0.0, truth_is="mean")
    with pytest.raises(ValueError, match="truth_is"):
        ceiling_arm(s1, s2, np.full_like(s1, FLOOR), abs_floor=0.0, truth_is="seed1")


def test_the_ceiling_truth_is_stated_not_assumed() -> None:
    s1, s2 = _pair(seed=8)
    spread = np.full_like(s1, FLOOR)
    _, t_mean, _ = ceiling_arm(s1, s2, spread, abs_floor=0.0, truth_is="mean")
    _, t_other, _ = ceiling_arm(s1, s2, spread, abs_floor=0.0, truth_is="other")
    assert np.array_equal(t_mean, (s1 + s2) / 2) and np.array_equal(t_other, s2)


def test_band_from_spread_is_the_transferred_bands_own_arithmetic() -> None:
    s1, s2 = _pair(seed=12)
    r1, r2 = _pair(spread=0.5, seed=13)
    truth, band = acceptance_band_transferred(s1, s2, r1, r2, abs_floor=0.0)
    assert np.array_equal(band, band_from_spread(truth, relative_spread(r1, r2), abs_floor=0.0))


# --- composition with a per-quantity floor ------------------------------------------------------


def test_the_per_quantity_floor_matches_each_scalar_floor_bit_for_bit() -> None:
    names = SCORED_WITH_COMPOSITION
    s1, s2 = _pair(m=len(names), seed=14)
    s1[:, 22:] /= 200.0  # type shares live in [0, 1]; small values make the floor bind
    s2[:, 22:] /= 200.0
    _, band = acceptance_band_with_composition(s1, s2, names)
    _, b22 = acceptance_band(s1[:, :22], s2[:, :22], abs_floor=0.0)
    _, bc = acceptance_band(s1[:, 22:], s2[:, 22:], abs_floor=ABS_FLOOR_COMPOSITION)
    assert np.array_equal(band[:, :22], b22) and np.array_equal(band[:, 22:], bc)


def test_the_composition_number_reports_the_plain_22_beside_it() -> None:
    names = SCORED_WITH_COMPOSITION
    s1, s2 = _pair(m=len(names), spread=0.05, seed=15)
    truth, band = acceptance_band_with_composition(s1, s2, names)
    pred = truth.copy()
    pred[:5, 25] += 10 * band[:5, 25]  # five rows miss on one type share only
    res = band_frac_with_composition(pred, truth, band, names)
    assert res["conjunctive_22"] == 1.0
    assert res["conjunctive_with_composition"] == pytest.approx(1 - 5 / truth.shape[0])
    with pytest.raises(ValueError, match="lacks"):
        band_frac_with_composition(pred[:, :22], truth[:, :22], band[:, :22], SCORED_CONJUNCTIVE)


def test_a_constant_quantity_that_varies_is_refused_not_dropped() -> None:
    names = ("a", "k_root_p50")
    ok = np.array([[1.0, 0.02], [2.0, 0.02], [3.0, np.nan]])
    assert_constant_quantities(ok, names)
    bad = ok.copy()
    bad[1, 1] = 0.03
    with pytest.raises(ValueError, match="varies"):
        assert_constant_quantities(bad, names)
