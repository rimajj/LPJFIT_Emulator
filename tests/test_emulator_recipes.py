"""A per-head recipe must be inert by default and must respect the trait's bounds when set.

WHY THIS TEST EXISTS. `Emulator` gained a way to fit one head differently from the rest -- a
bounded target and an absolute-error objective for rooting depth, because the trait lives in
[51, 1800] mm and the band test scores a median rather than a mean. Two things can go wrong with
that shape of change, and only one of them would ever crash:

  * THE DEFAULT STOPS BEING THE DEFAULT. Every score on the record was produced by the log-target
    squared-error fit. If adding the capability perturbs that path at all, the reported numbers
    quietly stop describing the shipped model. So the first assertion is byte-equality of the
    predictions with and without an empty recipe map -- the same check that let the imposed-trait
    work ship switched off with confidence.
  * A TRANSFORM IS APPLIED TWICE. `predict` used to decide by membership of a `logged` set. A head
    with a recipe already maps back through its own inverse, so if it were also in `logged` the
    result would be exponentiated again -- a plausible-looking number, not an exception. The
    constructor is asserted to keep the two bookkeeping paths disjoint.

⚠ WHAT THE BOUNDED RECIPE IS *NOT* FOR, stated because the first version of this test asserted it
and the assertion was false. A boosted tree's prediction is built from averages of training
targets, so it can only just barely leave their range: the shipped unbounded fit puts 0.19 % of
cells below 51 mm on `D95max_p10` and none above 1800. Keeping predictions inside the interval is
therefore a real but marginal effect, and a small synthetic fit does not reproduce it at all. The
recipe earns its place by RESHAPING THE LOSS -- the logit stretches the region next to the floor,
where the pile-up lives and where the score was worst -- not by clipping. So the assertions here
are that the transform round-trips and that the inverse cannot escape the interval by
construction, which is what the code actually guarantees.
"""

from __future__ import annotations

import numpy as np
import pytest

from vegemu.models import (
    D95MAX_BOUNDS,
    ROOTING_DEPTH_RECIPES,
    Emulator,
    EmulatorConfig,
    Recipe,
)

QUANTITIES = ("D95max_p10", "D95max_p50", "height_p50")
CFG = EmulatorConfig(n_estimators=40, n_jobs=1)


def _problem(n: int = 400, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """A small positive-target problem whose rooting-depth columns hug the trait's floor."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 6))
    low, high = D95MAX_BOUNDS
    # A pile-up at the floor plus a long upper tail -- the shape the recipe exists for.
    p10 = np.clip(low + np.abs(rng.gamma(1.2, 30.0, n)), low, high - 1.0)
    p50 = np.clip(p10 * (1.0 + np.abs(rng.gamma(2.0, 1.0, n))), low, high - 1.0)
    height = 5.0 + 2.0 * x[:, 0] ** 2 + np.abs(rng.normal(size=n))
    return x, np.stack([p10, p50, height], axis=1)


def test_an_empty_recipe_map_changes_nothing() -> None:
    x, y = _problem()
    plain = Emulator(QUANTITIES, CFG).fit(x, y).predict(x)
    empty = Emulator(QUANTITIES, CFG, recipes={}).fit(x, y).predict(x)
    assert np.array_equal(plain, empty), (
        "an empty recipe map must reproduce the shipped fit exactly"
    )


def test_a_recipe_head_is_not_also_logged() -> None:
    """The two ways of undoing a transform must never both apply to the same head."""
    x, y = _problem()
    model = Emulator(QUANTITIES, CFG, recipes=dict(ROOTING_DEPTH_RECIPES)).fit(x, y)
    assert set(model.logged) & set(model.recipes) == set()
    # height_p50 has no recipe, so it keeps the default path.
    assert "height_p50" in model.logged


def test_the_bounded_transform_round_trips() -> None:
    """`inverse(forward(y)) == y` over the whole interior. A transform that does not is a bug."""
    low, high = D95MAX_BOUNDS
    recipe = Recipe(bounds=D95MAX_BOUNDS)
    y = np.linspace(low + 1.0, high - 1.0, 5000)
    back = recipe.inverse(recipe.forward(y))
    assert np.allclose(back, y, rtol=1e-9, atol=1e-6)


def test_the_bounded_inverse_cannot_escape_the_interval() -> None:
    """Whatever a head emits -- including the +-inf a saturated logit could produce."""
    low, high = D95MAX_BOUNDS
    recipe = Recipe(bounds=D95MAX_BOUNDS)
    z = np.array([-np.inf, -1e6, -40.0, 0.0, 40.0, 1e6, np.inf])
    out = recipe.inverse(z)
    assert np.all(np.isfinite(out))
    assert np.all(out >= low) and np.all(out <= high)
    assert out[0] == pytest.approx(low, abs=1e-9)
    assert out[-1] == pytest.approx(high, abs=1e-9)


def test_a_bounded_head_predicts_inside_the_interval() -> None:
    x, y = _problem()
    low, high = D95MAX_BOUNDS
    recipes = dict(ROOTING_DEPTH_RECIPES)
    model = Emulator(QUANTITIES, CFG, recipes=recipes).fit(x, y)
    # Far outside the training range in every direction, so the heads extrapolate as freely as a
    # tree ensemble ever does.
    rng = np.random.default_rng(11)
    far = rng.normal(scale=50.0, size=(500, x.shape[1]))
    pred = model.predict(far)
    for j, name in enumerate(QUANTITIES):
        if name in recipes:
            assert np.all(pred[:, j] > low), f"{name} predicted at or below the trait floor"
            assert np.all(pred[:, j] < high), f"{name} predicted at or above the trait ceiling"


def test_a_recipe_on_a_non_positive_head_is_refused() -> None:
    """A recipe assumes a positive quantity on a transformed scale; silence here would be a bug."""
    x, y = _problem()
    y[:, 2] = -1.0  # height_p50 is a log target, but now it is not positive
    with pytest.raises(ValueError, match="not a positive log target"):
        Emulator(QUANTITIES, CFG, recipes={"height_p50": Recipe()}).fit(x, y)
