"""The synthesised roster may only contain tree types the target cell's own real state contains.

WHY THIS TEST EXISTS, AND WHY NO EXISTING TEST COULD HAVE CAUGHT IT. The first synthesised restart
file passed every check there was: it round-tripped byte-identically, the model's config pre-flight
accepted it, and the real model loaded it and ran a year without aborting even with `-DSAFE` on. Its
above-ground biomass was within 6.7 % of the truth. And then the model killed half its stems inside
that one year, because 31 % of them were tropical broadleaved evergreen transplanted into temperate
European cells -- a type whose temperature-stress limit (12.5 C, `par/pft_lpjmlfit.js`) makes death
certain there within ten weeks.

Every stem was individually valid; the ROSTER was not viable. A round-trip test compares bytes and
a run test asks whether the model aborts, so neither can see this. It needs its own assertion, and
the assertion is cheap: a type absent from a real equilibrium state of a cell is a type that cell
cannot support.

Two layers, for the same reason the round-trip test has two:
  * SYNTHETIC (runs anywhere). A hand-built template and donor pool with a type the template does
    not contain. This is the layer that pins the LOGIC.
  * REAL FILE (`needs_real_data`). The real 20-cell block and the real biome-spanning donor pool,
    i.e. the exact configuration that failed. This is the layer that pins the REGRESSION.
"""

from __future__ import annotations

import struct
from typing import Any

import numpy as np
import pytest

from vegemu.binfmt.restart import (
    PFT_TREE_BYTES,
    TREE_DTYPE,
    Layout,
    RestartReader,
    trees_of,
)
from vegemu.models.synth import (
    DonorPool,
    build_donor_pool,
    quantile_function,
    synthesise_cell,
    type_ladder,
)
from vegemu.paths import path

FIRST_CELL, NCELL = 42480, 20
DONOR_CELLS = [12045, 18371, 33335, 42490, 52059, 35599, 16447, 25000, 47721, 7216]

real_data = pytest.mark.skipif(
    not path("ground_truth.restart_spinup_end").exists(),
    reason="needs the ground-truth restart file under /p",
)


# ---------------------------------------------------------------------------------------------
# Layer 1 -- synthetic. Pins the logic with no cluster file.
# ---------------------------------------------------------------------------------------------
def _stem(pft_id: int, height: float, wooddens: float, litter: int = 0) -> np.ndarray:
    row = np.zeros(1, dtype=TREE_DTYPE)
    row["id"] = pft_id
    row["height"] = height
    row["wooddens"] = wooddens
    row["nind"] = 1.0 / 225.0
    row["sla"] = 0.03
    row["longevity"] = 0.6
    row["ind_leaf_c"] = 10.0
    row["ind_sapwood_c"] = 100.0 * height
    row["ind_heartwood_c"] = 200.0 * height
    row["age"] = int(height * 4)
    row["litter"] = litter
    return row


def _pftlist(stems: list[np.ndarray]) -> dict[str, Any]:
    raw = struct.pack("<i", len(stems)) + b"".join(
        s.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for s in stems
    )
    offs = np.array([4 + i * PFT_TREE_BYTES for i in range(len(stems))], dtype=np.int64)
    return {
        "raw": raw,
        "n": len(stems),
        "tree_offsets": offs,
        "grass_offsets": np.zeros(0, dtype=np.int64),
    }


def _template(types_and_heights: list[tuple[int, float]], npatch: int = 2) -> dict[str, Any]:
    """A minimal decoded record: `type_ladder` and `synthesise_cell` only read these keys."""
    patches = []
    for _ in range(npatch):
        stems = [_stem(t, h, 2.0e5) for t, h in types_and_heights]
        patches.append(
            {
                "soil": {
                    "pool": np.zeros((5, 4)),
                    "k_mean": np.zeros(5),
                    "litter": {
                        "n": 1,
                        "pft_ids": np.array([types_and_heights[0][0]], dtype=np.uint8),
                        "items": np.zeros(22),
                    },
                },
                "pftlist": _pftlist(stems),
                "frac_g": np.zeros(6),
            }
        )
    return {
        "skip": 0,
        "stands": [{"landusetype": 0, "npatch": npatch, "patches": patches, "frac": 1.0}],
    }


def _pool(types_and_heights: list[tuple[int, float]]) -> DonorPool:
    stems = [_stem(t, h, 2.0e5 + 1e4 * t) for t, h in types_and_heights]
    raw = np.stack([s.view(np.uint8).reshape(PFT_TREE_BYTES) for s in stems])
    return DonorPool(raw=raw, fields=np.concatenate(stems), source_cells=(0,))


def test_type_ladder_is_ordered_by_height() -> None:
    """The ladder carries the template's type-by-size association, smallest first."""
    ladder = type_ladder(_template([(3, 9.0), (1, 2.0), (4, 5.0)], npatch=1))
    assert ladder.tolist() == [1, 4, 3]


def test_ladder_of_a_treeless_template_is_empty() -> None:
    tmpl = _template([(3, 5.0)], npatch=1)
    tmpl["stands"][0]["patches"][0]["pftlist"] = _pftlist([])
    assert type_ladder(tmpl).size == 0


def test_an_inadmissible_type_is_never_placed_even_when_it_is_the_nearest_donor() -> None:
    """The regression, in miniature.

    The template holds only type 3. The pool's type-0 donor is a far better match on height and
    wood density than any type-3 donor, so the unconstrained nearest-donor rule would take it --
    which is exactly what happened on the real file.
    """
    tmpl = _template([(3, 4.0), (3, 6.0), (3, 8.0)])
    pool = _pool([(0, 6.0), (3, 1.0), (3, 20.0)])
    prediction = {
        "stems_per_patch": 3.0,
        "height_p10": 5.0,
        "height_p50": 6.0,
        "height_p90": 7.0,
        "wooddens_p10": 2.0e5,
        "wooddens_p50": 2.0e5,
        "wooddens_p90": 2.0e5,
    }
    _, report = synthesise_cell(tmpl, prediction, pool, Layout(), cell=1, template_cell=1, seed=0)
    assert report.stems_placed == 6
    assert report.type_admissible == (3,)
    assert report.inadmissible_placed == 0
    assert set(report.type_achieved) == {3}
    assert report.type_fallbacks == 0


def test_a_type_absent_from_the_pool_falls_back_within_the_admissible_set() -> None:
    """A missing type widens the candidates to the cell's OTHER types, never to the whole pool."""
    tmpl = _template([(1, 4.0), (3, 6.0), (3, 8.0)])
    pool = _pool([(0, 6.0), (3, 5.0), (3, 7.0)])  # no type 1 donor; type 0 is inadmissible here
    prediction = {
        "stems_per_patch": 3.0,
        "height_p10": 4.0,
        "height_p50": 6.0,
        "height_p90": 8.0,
        "wooddens_p10": 2.0e5,
        "wooddens_p50": 2.0e5,
        "wooddens_p90": 2.0e5,
    }
    _, report = synthesise_cell(tmpl, prediction, pool, Layout(), cell=1, template_cell=1, seed=0)
    assert report.type_fallbacks > 0, "the type-1 targets had no donor of their type"
    assert report.inadmissible_placed == 0, "and must still not have been given the type-0 donor"
    assert set(report.type_achieved) == {3}


def test_the_size_ordering_of_the_requested_types_follows_the_template() -> None:
    """A type that is only ever small in the template must not be asked to be the tallest stem."""
    tmpl = _template([(1, 1.0), (1, 2.0), (3, 10.0), (3, 12.0)])
    pool = _pool([(1, 1.5), (3, 11.0)])
    prediction = {
        "stems_per_patch": 4.0,
        "height_p10": 1.0,
        "height_p50": 6.0,
        "height_p90": 12.0,
        "wooddens_p10": 2.0e5,
        "wooddens_p50": 2.0e5,
        "wooddens_p90": 2.0e5,
    }
    _, report = synthesise_cell(tmpl, prediction, pool, Layout(), cell=1, template_cell=1, seed=0)
    # Half the roster small (type 1), half tall (type 3) -- the template's own split.
    assert report.type_requested == {1: 4, 3: 4}
    assert report.inadmissible_placed == 0


def test_quantile_function_is_monotone_even_with_crossed_knots() -> None:
    """The three heads are fitted independently, so a crossed p10/p90 pair must not invert."""
    u = (np.arange(20) + 0.5) / 20
    out = quantile_function(9.0, 5.0, 1.0, u)  # deliberately reversed
    assert np.all(np.diff(out) >= 0)
    assert out.min() > 0


# ---------------------------------------------------------------------------------------------
# Layer 2 -- the real file, in the exact configuration that failed.
# ---------------------------------------------------------------------------------------------
@real_data
@pytest.mark.needs_real_data
@pytest.mark.slow
def test_real_block_places_no_inadmissible_stem() -> None:
    """The 20 temperate cells and the biome-spanning donor pool that produced the 31 % fault."""
    restart = path("ground_truth.restart_spinup_end")
    reader = RestartReader(restart)
    pool = build_donor_pool(RestartReader(restart), DONOR_CELLS)
    pool_types = set(np.unique(np.asarray(pool.fields["id"], dtype=int)).tolist())
    assert {0, 6} <= pool_types, (
        "the pool must still span biomes -- if it no longer contains the types that caused the "
        "fault, this test has stopped testing anything"
    )

    prediction = {
        "stems_per_patch": 19.0,
        "height_p10": 2.5,
        "height_p50": 5.0,
        "height_p90": 12.4,
        "wooddens_p10": 1.69e5,
        "wooddens_p50": 2.32e5,
        "wooddens_p90": 3.48e5,
    }
    with reader:
        for cell in range(FIRST_CELL, FIRST_CELL + 5):
            template = reader.read(cell)
            if template["skip"]:
                continue
            admissible = {int(t) for t in np.unique(type_ladder(template))}
            assert not ({0, 6} & admissible), (
                f"cell {cell} is supposed to be a temperate cell holding neither type"
            )
            rec, report = synthesise_cell(
                template,
                prediction,
                pool,
                reader.layout,
                cell=cell,
                template_cell=cell,
                seed=cell,
            )
            assert report.inadmissible_placed == 0, (
                f"cell {cell}: {report.inadmissible_placed} of {report.stems_placed} stems are of "
                f"a type the cell's own state never holds (placed {report.type_achieved}, "
                f"admissible {report.type_admissible})"
            )
            # And check the WRITTEN record, not only the report -- the report is a claim about it.
            placed = np.concatenate(
                [
                    trees_of(p["pftlist"])["id"]
                    for p in rec["stands"][0]["patches"]
                    if trees_of(p["pftlist"]).size
                ]
            )
            assert set(np.unique(placed).tolist()) <= admissible
