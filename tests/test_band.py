"""The acceptance band, and the circularity that the transferred band removes.

The band IS the acceptance test (`MEMORY.md:acceptance`), so its arithmetic is worth pinning down
rather than trusting. Three claims are checked here, each aimed at a specific way a band can lie:

  * the floor really is a floor -- max(10 %, spread), never the spread alone;
  * `acceptance_band_transferred` with the scored leg as its OWN reference reproduces
    `acceptance_band` exactly, so introducing it cannot have moved any committed number;
  * under a same-leg band, "predict one seed" is inside the band in EVERY cell by construction --
    which is why that arm is a ceiling and not a null -- and under a transferred band it is not.

That last pair is the whole reason the transferred band exists, and it is a property of the
arithmetic rather than of any particular corpus, so it belongs in a test and not only in a verdict.
"""

from __future__ import annotations

import numpy as np

from vegemu.score import (
    ABS_FLOOR_COMPOSITION,
    FLOOR,
    acceptance_band,
    acceptance_band_transferred,
    band_frac_conjunctive,
    band_hits,
    relative_spread,
)


def _pair(n: int = 500, m: int = 6, spread: float = 0.3, seed: int = 11):
    """Two 'seeds' of a positive state, differing by a controllable relative amount."""
    rng = np.random.default_rng(seed)
    level = rng.uniform(1.0, 100.0, size=(n, m))
    delta = level * rng.uniform(-spread, spread, size=(n, m))
    return level + delta / 2, level - delta / 2


def test_the_floor_is_a_floor() -> None:
    """A quiet cell gets 10 %, not its own tiny spread."""
    s1, s2 = _pair(spread=1e-6)
    rel = relative_spread(s1, s2)
    assert np.all(rel >= FLOOR)
    assert np.allclose(rel, FLOOR), "a near-identical pair must fall back to the floor exactly"

    # And a noisy cell keeps its own, larger spread.
    n1, n2 = _pair(spread=0.8, seed=12)
    assert relative_spread(n1, n2).max() > FLOOR


def test_a_zero_mean_falls_back_to_the_floor_instead_of_dividing_by_zero() -> None:
    z = np.zeros((3, 2))
    assert np.allclose(relative_spread(z, z), FLOOR)
    assert np.all(np.isfinite(relative_spread(z, z)))


def test_transferring_a_leg_onto_itself_is_the_same_leg_band() -> None:
    """The refactor-safety property: no committed number can have moved."""
    s1, s2 = _pair()
    truth_a, band_a = acceptance_band(s1, s2, abs_floor=0.0)
    truth_b, band_b = acceptance_band_transferred(s1, s2, s1, s2, abs_floor=0.0)
    assert np.array_equal(truth_a, truth_b)
    assert np.array_equal(band_a, band_b), "must be bit-identical, not merely close"


def test_one_seed_always_passes_its_own_band_and_that_is_the_circularity() -> None:
    """|s1 - mean| = |s1 - s2| / 2, and the band is at least |s1 - s2|. So it cannot fail."""
    s1, s2 = _pair(spread=0.9)
    truth, band = acceptance_band(s1, s2, abs_floor=0.0)
    assert band_frac_conjunctive(s1, truth, band) == 1.0
    assert band_frac_conjunctive(s2, truth, band) == 1.0
    assert band_hits(s1, truth, band).all()


def test_a_transferred_band_lets_a_single_realisation_fail() -> None:
    """The point of the transferred band: the ceiling stops being 1.0 by arithmetic.

    Scored leg is noisy, reference leg is quiet, so the tolerance is the 10 % floor while the
    scored pair disagrees by far more than that -- and one seed then lands outside the band.
    """
    s1, s2 = _pair(spread=0.9, seed=21)
    ref1, ref2 = _pair(spread=1e-6, seed=22)
    truth, band = acceptance_band_transferred(s1, s2, ref1, ref2, abs_floor=0.0)
    assert np.allclose(band, FLOOR * np.abs(truth))
    ceiling = band_frac_conjunctive(s1, truth, band)
    assert ceiling < 1.0, "a single realisation must be able to miss a band it did not set"


def test_a_transferred_band_keeps_the_truth_of_the_leg_it_scores() -> None:
    """Only the tolerance travels between legs; the truth never does."""
    s1, s2 = _pair(seed=31)
    ref1, ref2 = _pair(spread=0.5, seed=32)
    truth, _ = acceptance_band_transferred(s1, s2, ref1, ref2, abs_floor=0.0)
    assert np.array_equal(truth, (s1 + s2) / 2.0)


# --- the ADDITIVE floor, for quantities that live near zero -------------------------------------
#
# WHY IT EXISTS. A relative band collapses with the level it is a fraction of, so a tree type whose
# true share is 0.002 gets a band of 0.0002 and NOTHING can land inside it -- not the emulator, and
# not a second run of the model itself. The conjunctive test then reports a failure that is a
# property of the arithmetic rather than of the prediction.


def test_the_additive_floor_binds_exactly_where_the_relative_band_collapses() -> None:
    """Near zero the floor decides the band; far from zero the relative spread still does."""
    tiny1 = np.full((4, 3), 0.002)
    tiny2 = np.full((4, 3), 0.0021)
    _, band = acceptance_band(tiny1, tiny2, abs_floor=ABS_FLOOR_COMPOSITION)
    assert np.allclose(band, ABS_FLOOR_COMPOSITION), "the relative band is ~2e-4 and must not win"

    big1, big2 = _pair(spread=0.9, seed=41)  # levels of 1..100, so 10 % is >> 0.0384
    _, band_big = acceptance_band(big1, big2, abs_floor=ABS_FLOOR_COMPOSITION)
    _, band_rel = acceptance_band(big1, big2, abs_floor=0.0)
    assert np.array_equal(band_big, band_rel), "the floor must not touch a well-scaled quantity"


def test_abs_floor_zero_reproduces_every_number_committed_before_it_existed() -> None:
    """The refactor-safety property, and the reason `0.0` is spelled out at each old call site.

    `max(x, 0.0)` is `x` for any non-negative band, and a band is non-negative by construction.
    Pinned bit-for-bit, not approximately: if this drifts, every score in every sealed verdict
    derived from this module silently moved.
    """
    s1, s2 = _pair(spread=0.45, seed=51)
    _, floored = acceptance_band(s1, s2, abs_floor=0.0)
    assert np.array_equal(floored, relative_spread(s1, s2) * np.abs((s1 + s2) / 2.0))

    ref1, ref2 = _pair(spread=0.2, seed=52)
    _, t_floored = acceptance_band_transferred(s1, s2, ref1, ref2, abs_floor=0.0)
    assert np.array_equal(t_floored, relative_spread(ref1, ref2) * np.abs((s1 + s2) / 2.0)), (
        "the transferred band must be bit-identical too, or the two stop being comparable"
    )


def test_the_floor_is_required_and_has_no_default() -> None:
    """A default would leak a floor measured in STEM SHARES onto soil carbon, silently.

    Pinned because the whole design of this parameter is that the caller must decide. Somebody
    adding `= 0.0` back for convenience turns this red, which is the point.
    """
    s1, s2 = _pair()
    for fn, args in (
        (acceptance_band, (s1, s2)),
        (acceptance_band_transferred, (s1, s2, s1, s2)),
    ):
        try:
            fn(*args)  # type: ignore[operator]
        except TypeError as exc:
            assert "abs_floor" in str(exc), exc
        else:
            raise AssertionError(f"{fn.__name__} accepted no abs_floor; it must be required")


def test_the_measured_floor_is_the_one_that_was_measured() -> None:
    """0.0384 is the p90 of the model's own absolute two-seed disagreement on type shares.

    Pinned as a number because it is MEASURED, not chosen (`MEMORY.md:abs-floor-measured`), and
    because raising a floor to rescue a failing test is a threshold picked after seeing the values.
    """
    assert ABS_FLOOR_COMPOSITION == 0.0384


def test_a_nan_on_either_side_is_a_miss_never_a_pass() -> None:
    """A trait median that does not exist must not be silently credited."""
    truth = np.array([[1.0, 2.0]])
    band = np.array([[0.5, 0.5]])
    assert not band_hits(np.array([[np.nan, 2.0]]), truth, band)[0, 0]
    assert band_hits(np.array([[np.nan, 2.0]]), truth, band)[0, 1]
    assert not band_hits(np.array([[1.0, 2.0]]), np.array([[np.nan, 2.0]]), band)[0, 0]
    assert band_frac_conjunctive(np.array([[np.nan, 2.0]]), truth, band) == 0.0
