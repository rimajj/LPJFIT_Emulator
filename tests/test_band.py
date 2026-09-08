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
    truth_a, band_a = acceptance_band(s1, s2)
    truth_b, band_b = acceptance_band_transferred(s1, s2, s1, s2)
    assert np.array_equal(truth_a, truth_b)
    assert np.array_equal(band_a, band_b), "must be bit-identical, not merely close"


def test_one_seed_always_passes_its_own_band_and_that_is_the_circularity() -> None:
    """|s1 - mean| = |s1 - s2| / 2, and the band is at least |s1 - s2|. So it cannot fail."""
    s1, s2 = _pair(spread=0.9)
    truth, band = acceptance_band(s1, s2)
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
    truth, band = acceptance_band_transferred(s1, s2, ref1, ref2)
    assert np.allclose(band, FLOOR * np.abs(truth))
    ceiling = band_frac_conjunctive(s1, truth, band)
    assert ceiling < 1.0, "a single realisation must be able to miss a band it did not set"


def test_a_transferred_band_keeps_the_truth_of_the_leg_it_scores() -> None:
    """Only the tolerance travels between legs; the truth never does."""
    s1, s2 = _pair(seed=31)
    ref1, ref2 = _pair(spread=0.5, seed=32)
    truth, _ = acceptance_band_transferred(s1, s2, ref1, ref2)
    assert np.array_equal(truth, (s1 + s2) / 2.0)


def test_a_nan_on_either_side_is_a_miss_never_a_pass() -> None:
    """A trait median that does not exist must not be silently credited."""
    truth = np.array([[1.0, 2.0]])
    band = np.array([[0.5, 0.5]])
    assert not band_hits(np.array([[np.nan, 2.0]]), truth, band)[0, 0]
    assert band_hits(np.array([[np.nan, 2.0]]), truth, band)[0, 1]
    assert not band_hits(np.array([[1.0, 2.0]]), np.array([[np.nan, 2.0]]), band)[0, 0]
    assert band_frac_conjunctive(np.array([[np.nan, 2.0]]), truth, band) == 0.0
