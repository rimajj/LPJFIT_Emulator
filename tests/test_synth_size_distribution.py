"""The roster must span the CELL's size distribution, tails included, not one patch's middle.

WHY THIS TEST EXISTS. The synthesised restart hit the predicted `stems_per_patch` to 0.2 %, the
predicted `height_p50` to 0.3 % and reported a pool shortfall of 0.02 %, and its twenty-year run
still came last on leaf area -- 15 % of cells inside the acceptance band against the 90 % a real run
attains. Every summary number said the roster was right. It was not: the true state of the block
holds 382 stems above 16 m and the synthesised file held none, its tallest tree being 13.3 m where
the truth reaches 23.0 m, and those missing tall trees carried 36 % of the stand's leaf.

Two independent causes, both invisible to a median:

  * THE RANKS WERE DRAWN PER PATCH. The predicted quantiles are cell-level -- `corpus/state.py`
    pools all patches before taking a percentile -- but the roster was built from
    `u = (arange(n) + 0.5) / n` inside each patch with n ~ 19, so every patch received the same
    nineteen ranks spanning 0.026 to 0.974 and the cell received twenty-five copies of one
    truncated ladder. Nothing ever addressed the 0.99 rank, so nothing ever placed the tree
    that lives there.
  * THE TAIL WAS A STRAIGHT LINE. Continuing the p50-p90 slope past the 90th percentile reaches
    14.3 m at rank 0.999 against a real 23.0 m. A stand's height distribution is strongly
    right-skewed and three knots joined by straight lines cannot make one.

So the assertions here are about the TAILS and about the CELL, and they are deliberately not
assertions about a median -- a median is exactly what stayed correct while this was broken.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np

from vegemu.binfmt.restart import PFT_TREE_BYTES, TREE_DTYPE, Layout, trees_of
from vegemu.models.synth import (
    DonorPool,
    _rank_index,
    quantile_function,
    recalibrate,
    synthesise_cell,
    template_ladder,
)


def _stem(pft_id: int, height: float, wooddens: float = 2.0e5, d95: float = 0.0) -> np.ndarray:
    row = np.zeros(1, dtype=TREE_DTYPE)
    row["id"] = pft_id
    row["height"] = height
    row["wooddens"] = wooddens
    row["nind"] = 1.0 / 225.0
    row["sla"] = 0.03
    row["ind_leaf_c"] = height
    row["ind_sapwood_c"] = 100.0 * height
    row["ind_heartwood_c"] = 200.0 * height
    # Rooting depth defaults to zero so that DONORS carry none: any non-zero value in an emitted
    # record then proves a byte was written rather than inherited. Templates pass a real spread.
    row["D95max"] = d95
    return row


def _pftlist(stems: list[np.ndarray]) -> dict[str, Any]:
    raw = struct.pack("<i", len(stems)) + b"".join(
        s.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for s in stems
    )
    return {
        "raw": raw,
        "n": len(stems),
        "tree_offsets": np.array(
            [4 + i * PFT_TREE_BYTES for i in range(len(stems))], dtype=np.int64
        ),
        "grass_offsets": np.zeros(0, dtype=np.int64),
    }


def _template(per_patch: list[list[tuple[int, float]]]) -> dict[str, Any]:
    patches = []
    for stems in per_patch:
        patches.append(
            {
                "soil": {
                    "pool": np.zeros((5, 4)),
                    "k_mean": np.zeros(5),
                    "litter": {
                        "n": 1,
                        "pft_ids": np.array([3], dtype=np.uint8),
                        "items": np.zeros(22),
                    },
                },
                # Template stems carry a real rooting-depth spread, correlated with height the way
                # a real stand's is, so the imposition exercises the template path rather than the
                # degenerate-sample fallback.
                "pftlist": _pftlist([_stem(t, h, d95=0.5 + 0.1 * h) for t, h in stems]),
                "frac_g": np.zeros(6),
            }
        )
    return {
        "skip": 0,
        "stands": [{"landusetype": 0, "npatch": len(patches), "patches": patches, "frac": 1.0}],
    }


def _pool(heights: list[float], d95_spread: bool = False) -> DonorPool:
    # Donors carry a DIFFERENT rooting-depth law from the template's, so a placed value that
    # matches the prediction cannot have been inherited. Off by default: with every donor at zero
    # the imposition clamp (which is bounded by what real pool stems exhibit) pins everything to
    # zero, which is the clamp working, not the write failing.
    stems = [_stem(3, h, d95=(0.1 + 0.2 * h) if d95_spread else 0.0) for h in heights]
    raw = np.stack([s.view(np.uint8).reshape(PFT_TREE_BYTES) for s in stems])
    return DonorPool(raw=raw, fields=np.concatenate(stems), source_cells=(0,))


# A right-skewed stand: many small stems, a thin tall tail -- the shape a real forest has, and the
# shape three knots and a straight line cannot draw.
SKEWED = [1.0, 1.2, 1.5, 1.8, 2.2, 2.6, 3.1, 3.8, 4.6, 5.5, 7.0, 9.0, 12.0, 17.0, 24.0]
# And the tail lives in ONE patch of four, which is the whole point: a 24 m tree is one tree in the
# stand, not one tree per patch. A stand built from four identical patches would hide the defect,
# because its four tallest rungs are the same height and both rank schemes then reach it.
SHORT = [1.0, 1.2, 1.5, 1.8, 2.2, 2.6, 3.1, 3.8, 4.6, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0]
STAND = [[(3, h) for h in lst] for lst in (SKEWED, SHORT, SHORT, SHORT)]


def _prediction(n_per_patch: float, p10: float, p50: float, p90: float) -> dict[str, float]:
    return {
        "stems_per_patch": n_per_patch,
        "height_p10": p10,
        "height_p50": p50,
        "height_p90": p90,
        "wooddens_p10": 2.0e5,
        "wooddens_p50": 2.0e5,
        "wooddens_p90": 2.0e5,
    }


def _placed_trait(rec: dict[str, Any], name: str) -> np.ndarray:
    out = [
        trees_of(p["pftlist"])[name].astype(float)
        for p in rec["stands"][0]["patches"]
        if trees_of(p["pftlist"]).size
    ]
    return np.concatenate(out) if out else np.zeros(0)


def _placed_heights(rec: dict[str, Any]) -> np.ndarray:
    out = []
    for patch in rec["stands"][0]["patches"]:
        arr = trees_of(patch["pftlist"])
        if arr.size:
            out.append(arr["height"].astype(float))
    return np.concatenate(out) if out else np.zeros(0)


# ---------------------------------------------------------------------------------------------
# The recalibration itself.
# ---------------------------------------------------------------------------------------------
def test_recalibrate_is_exact_at_the_three_knots() -> None:
    """The predicted quantiles are the contract: a template stem AT a knot lands ON it."""
    sample = np.array(SKEWED)
    knots = np.percentile(sample, [10.0, 50.0, 90.0])
    out = recalibrate(knots, sample, 2.0, 6.0, 20.0)
    assert out is not None
    assert np.allclose(out, [2.0, 6.0, 20.0])


def test_the_mapped_sample_reproduces_the_predicted_quantiles() -> None:
    """And the roster built from it carries those quantiles, to within the discretisation.

    Not exact, and the reason is worth stating: `np.percentile` interpolates between neighbouring
    order statistics, and at p10 and p90 that bracket straddles a kink in the map, so the empirical
    percentile of the mapped sample sits a fraction off the knot. On this fifteen-point fixture
    that is 0.5 %; on a real cell's ~490 stems it is far smaller. It is a property of measuring a
    percentile, not a bias in the map -- the test above pins the map itself.
    """
    sample = np.array(SKEWED)
    out = recalibrate(sample, sample, 2.0, 6.0, 20.0)
    assert out is not None
    got = np.percentile(out, [10.0, 50.0, 90.0])
    assert np.allclose(got, [2.0, 6.0, 20.0], rtol=0.01)


def test_recalibrate_is_monotone_and_keeps_the_shape() -> None:
    """Location and spread come from the prediction; the SKEW stays the template's."""
    sample = np.array(SKEWED)
    out = recalibrate(np.sort(sample), sample, 2.0, 6.0, 20.0)
    assert out is not None
    assert np.all(np.diff(out) >= 0)
    # A right-skewed sample stays right-skewed: the gap above the median dwarfs the one below.
    p10, p50, p90 = np.percentile(out, [10.0, 50.0, 90.0])
    assert (p90 - p50) > 3 * (p50 - p10)


def test_recalibrate_refuses_a_template_with_no_spread() -> None:
    """A degenerate template cannot supply a shape, and must say so rather than divide by zero."""
    assert recalibrate(np.ones(10), np.ones(10), 1.0, 2.0, 3.0) is None


def test_the_tail_does_not_amplify_the_prediction_error() -> None:
    """Past the top knot the map must not magnify the error the prediction already has.

    The measured failure: a level model 5 % high at the 90th percentile, extrapolated along the
    interior slope, came out 13 % high at the 99.9th and put above-ground biomass 21 % over the
    truth. So the contract is that the relative error at the far end of the tail is no worse than
    the relative error at the knot it is anchored to.
    """
    sample = np.array(SKEWED)
    t10, t50, t90 = np.percentile(sample, [10.0, 50.0, 90.0])
    over = 1.05  # the prediction is 5 % high at p90 and right at p10/p50
    out = recalibrate(np.sort(sample), sample, t10, t50, t90 * over)
    assert out is not None
    far = np.sort(sample) > t90
    assert far.any(), "the fixture must have stems beyond the top knot"
    worst = float(np.max(out[far] / np.sort(sample)[far]))
    assert worst <= over + 1e-9, f"the tail amplified {over:.3f} to {worst:.3f}"


def test_recalibrate_is_the_identity_when_the_prediction_is_right() -> None:
    """The sharpest statement of correctness: a perfect prediction must change nothing."""
    sample = np.array(SKEWED)
    t10, t50, t90 = np.percentile(sample, [10.0, 50.0, 90.0])
    out = recalibrate(np.sort(sample), sample, t10, t50, t90)
    assert out is not None
    assert np.allclose(out, np.sort(sample))


def test_recalibrate_survives_crossed_knots() -> None:
    """The three heads are fitted independently, so the knots can arrive out of order."""
    sample = np.array(SKEWED)
    out = recalibrate(np.sort(sample), sample, 20.0, 6.0, 2.0)
    assert out is not None
    assert np.all(np.diff(out) >= 0)
    assert out.min() > 0


# ---------------------------------------------------------------------------------------------
# The tail the old mechanism could not reach.
# ---------------------------------------------------------------------------------------------
def test_the_straight_tail_falls_short_of_the_template_tail() -> None:
    """The regression, stated as arithmetic and with no file involved.

    This is the defect itself: at the highest rank a 19-stem patch can address, the three-knot
    linear function asks for a tree far shorter than the stand's real tallest. It is pinned as a
    test so that a future change back to the straight tail fails here rather than in a 20-year run.
    """
    sample = np.array(SKEWED)
    p10, p50, p90 = np.percentile(sample, [10.0, 50.0, 90.0])
    u_patch = (np.arange(19) + 0.5) / 19
    straight = quantile_function(p10, p50, p90, u_patch)
    assert straight.max() < 0.75 * sample.max(), "the straight tail should be badly short"
    shaped = recalibrate(np.sort(sample), sample, p10, p50, p90)
    assert shaped is not None
    assert np.isclose(shaped.max(), sample.max())


def test_the_ladder_is_the_whole_cell_sorted_by_height() -> None:
    rungs = template_ladder(_template(STAND))
    assert rungs.size == 4 * len(SKEWED), "all four patches, pooled"
    assert np.all(np.diff(rungs["height"].astype(float)) >= 0)


# ---------------------------------------------------------------------------------------------
# End to end through synthesise_cell.
# ---------------------------------------------------------------------------------------------
def test_the_roster_reaches_the_top_of_the_donor_pool() -> None:
    """A cell whose template holds a 24 m tree must be given one, not a 13 m stand-in."""
    tmpl = _template(STAND)
    pool = _pool([*SKEWED, 20.0, 22.0, 26.0, 30.0])
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    rec, report = synthesise_cell(
        tmpl,
        _prediction(len(SKEWED), p10, p50, p90),
        pool,
        Layout(),
        cell=1,
        template_cell=1,
        seed=0,
    )
    heights = _placed_heights(rec)
    assert report.shape_source["height"] == "template"
    assert report.ranks_drawn_over == "cell"
    assert heights.max() >= 20.0, f"the upper tail is missing: tallest placed {heights.max():.1f} m"
    assert report.tallest_placed == heights.max()
    assert report.tallest_in_template == max(SKEWED)


def test_per_patch_ranks_cannot_address_the_top_of_the_cell_ladder() -> None:
    """The bug, stated exactly: the top per-patch rank indexes BELOW the cell's tallest rung.

    Four patches of fifteen stems. The cell's top rank is 59.5/60 = 0.992, which lands on rung 59 --
    the stand's tallest tree. Any single patch's top rank is 14.5/15 = 0.967, which lands on rung
    58. So under per-patch ranks the tallest tree in the cell was not merely unlikely to be placed;
    it was unaddressable, in every patch, however good the prediction was.
    """
    rungs = template_ladder(_template(STAND))
    n = len(SKEWED)
    heights = np.asarray(rungs["height"], dtype=np.float64)
    top_patch = heights[_rank_index(rungs.size, (np.arange(n) + 0.5) / n)].max()
    top_cell = heights[_rank_index(rungs.size, (np.arange(4 * n) + 0.5) / (4 * n))].max()
    assert top_cell == heights.max() == max(SKEWED)
    assert top_patch < top_cell, "the per-patch ceiling must sit below the stand's tallest tree"


def test_a_predicted_shift_moves_the_whole_distribution() -> None:
    """The template supplies the shape; the prediction must still control where it sits."""
    tmpl = _template(STAND)
    # Ample headroom on purpose: a pool that runs out of tall stems would clip both arms to the
    # same ceiling and the test would be measuring the pool rather than the mechanism.
    pool = _pool([h * f for f in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0) for h in SKEWED])
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    base, _ = synthesise_cell(
        tmpl,
        _prediction(len(SKEWED), p10, p50, p90),
        pool,
        Layout(),
        cell=1,
        template_cell=1,
        seed=0,
    )
    taller, _ = synthesise_cell(
        tmpl,
        _prediction(len(SKEWED), p10 * 1.5, p50 * 1.5, p90 * 1.5),
        pool,
        Layout(),
        cell=1,
        template_cell=1,
        seed=0,
    )
    hb, ht = _placed_heights(base), _placed_heights(taller)
    assert np.median(ht) > np.median(hb)
    assert np.percentile(ht, 90) > np.percentile(hb, 90), "the tail must move with the prediction"


def test_a_treeless_template_falls_back_to_the_knots_and_says_so() -> None:
    """No shape available: the straight tail is used, and the report records that it was."""
    tmpl = _template([[(3, 5.0)], [(3, 5.0)]])
    for patch in tmpl["stands"][0]["patches"]:
        patch["pftlist"] = _pftlist([])
    pool = _pool([1.0, 5.0, 9.0])
    _, report = synthesise_cell(
        tmpl, _prediction(3.0, 2.0, 5.0, 9.0), pool, Layout(), cell=1, template_cell=1, seed=0
    )
    assert report.shape_source["height"] == "knots"
    assert report.stems_placed == 6


def test_the_cell_total_count_is_unchanged_by_cell_level_ranks() -> None:
    """The count clause must be untouched: this change is about WHICH stems, not how many."""
    tmpl = _template(STAND)
    pool = _pool(SKEWED)
    _, report = synthesise_cell(
        tmpl, _prediction(15.4, 1.5, 3.5, 12.0), pool, Layout(), cell=1, template_cell=1, seed=7
    )
    assert report.stems_placed == report.stems_requested
    # 15.4 per patch over 4 patches: stochastic rounding gives 61 or 62, never 60 in every patch.
    assert 60 <= report.stems_placed <= 64


# ---------------------------------------------------------------------------------------------
# Imposed traits: written into the stem's bytes rather than obtained by choosing a donor.
# ---------------------------------------------------------------------------------------------
def test_an_imposed_trait_is_actually_written_into_the_stem_bytes() -> None:
    """The donor's own rooting depth must not survive into the emitted record.

    The point of imposition is that donor selection provably cannot deliver this quantity: with a
    perfect prediction the match still leaves D95max_p50 at 0.127. So the test is on the BYTES of
    the placed stem, not on the target that was requested.
    """
    tmpl = _template(STAND)
    pool = _pool(SKEWED, d95_spread=True)
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    pred = _prediction(len(SKEWED), p10, p50, p90)
    pred |= {"D95max_p10": 1.5, "D95max_p50": 2.5, "D95max_p90": 4.0}
    rec, report = synthesise_cell(
        tmpl, pred, pool, Layout(), cell=1, template_cell=1, seed=0, impose_traits=("D95max",)
    )
    placed = _placed_trait(rec, "D95max")
    assert report.imposed == {"D95max": "template"}
    # A handful of the very shallowest stems hit the pool's own floor; that is the clamp working.
    assert report.imposed_clamped <= 5, f"{report.imposed_clamped} of 60 clamped, expected a few"
    # THE CONTRACT: the PLACED marginal carries the predicted quantiles. Donors follow a different
    # rooting-depth law entirely, so this cannot have been inherited. p10 is excluded because it is
    # the one the floor touches.
    got = np.percentile(placed, [50.0, 90.0])
    assert np.allclose(got, [2.5, 4.0], rtol=0.05), f"placed median/p90 {got}"


def test_the_report_describes_what_was_written_not_the_donor() -> None:
    """`achieved` must read back the imposed value, or the report lies about its own file.

    Reading a donor's value back after overwriting it is exactly the mistake that once made a
    whole decision record's diagnosis wrong, so it gets its own assertion.
    """
    tmpl = _template(STAND)
    pool = _pool(SKEWED, d95_spread=True)
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    pred = _prediction(len(SKEWED), p10, p50, p90)
    pred |= {"D95max_p10": 1.5, "D95max_p50": 2.5, "D95max_p90": 4.0}
    rec, report = synthesise_cell(
        tmpl,
        pred,
        pool,
        Layout(),
        cell=1,
        template_cell=1,
        seed=0,
        match_traits=("height", "wooddens", "D95max"),
        impose_traits=("D95max",),
    )
    placed = _placed_trait(rec, "D95max")
    assert np.isclose(report.achieved["D95max_p50"], float(np.percentile(placed, 50)))


def test_imposing_nothing_leaves_the_stem_byte_identical_to_its_donor() -> None:
    """The escape hatch must be exact: an empty tuple is the old no-edit behaviour."""
    tmpl = _template(STAND)
    pool = _pool(SKEWED)
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    pred = _prediction(len(SKEWED), p10, p50, p90)
    pred |= {"D95max_p10": 1.5, "D95max_p50": 2.5, "D95max_p90": 4.0}
    rec, report = synthesise_cell(
        tmpl, pred, pool, Layout(), cell=1, template_cell=1, seed=0, impose_traits=()
    )
    placed = np.concatenate(
        [
            trees_of(p["pftlist"])["D95max"].astype(float)
            for p in rec["stands"][0]["patches"]
            if trees_of(p["pftlist"]).size
        ]
    )
    assert report.imposed == {}
    assert placed.max() == 0.0, "with imposition off, the donor's own value must survive"


def test_an_imposed_value_is_clamped_to_what_real_stems_exhibit() -> None:
    """A stretched prediction must not write a rooting depth no tree in the pool has."""
    tmpl = _template(STAND)
    pool = _pool(SKEWED, d95_spread=True)  # real stems reach 4.9 at most
    p10, p50, p90 = np.percentile(np.array(SKEWED), [10.0, 50.0, 90.0])
    pred = _prediction(len(SKEWED), p10, p50, p90)
    # Asks for 5-20 m of rooting depth, which no stem in the pool exhibits: all must clamp.
    pred |= {"D95max_p10": 5.0, "D95max_p50": 9.0, "D95max_p90": 20.0}
    rec, report = synthesise_cell(
        tmpl, pred, pool, Layout(), cell=1, template_cell=1, seed=0, impose_traits=("D95max",)
    )
    # THE CONTRACT: nothing written may exceed what a real stem in the pool exhibits, however far
    # the prediction reaches. Most stems clamp here; the few that do not are the shallow tail.
    ceiling = float(np.max(pool.trait("D95max")))
    assert float(np.max(_placed_trait(rec, "D95max"))) <= ceiling + 1e-9
    assert report.imposed_clamped > 0.8 * report.stems_placed, (
        f"only {report.imposed_clamped} of {report.stems_placed} clamped"
    )
