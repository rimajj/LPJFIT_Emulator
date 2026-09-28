"""`vegemu.models.patch_transplant`: the trees of each target patch are ONE real donor patch.

What must hold:
  * `choose_patches` reaches a reachable carbon sum within its tolerance, never reusing a
    candidate when there are enough, and returns a plain random draw when there is no target;
  * every target patch's trees are, byte for byte apart from the litter index, the trees of one
    donor patch of a donor run; each litter index names the target patch's slot for its type;
  * the written tree carbon is the target minus the grass, within the tolerance;
  * everything but the trees is `SpinupRule`'s record; a donor run of the target cell is refused.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import polars as pl
import pytest

from vegemu.binfmt.restart import (
    PFT_TREE_BYTES,
    GenericHeader,
    RestartHeader,
    RestartReader,
    RestartWriter,
    trees_of,
)
from vegemu.corpus.vegc import cell_vegc, tree_vegc
from vegemu.models import patch_transplant as pt
from vegemu.models import spinup_rule as sr
from vegemu.models.synth import LITTER_BYTE_IN_TREE, build_donor_pool

from .test_spinup_rule import NCELL, STORED_SEED, _block, _prediction, _record, _write

DONORS = [(100 + k, f"lhs{k:02d}") for k in range(4)]


def test_choose_patches_reaches_the_target_without_reuse() -> None:
    rng = np.random.default_rng(0)
    carbon = rng.gamma(2.0, 50.0, size=100)
    want = float(np.sort(carbon)[-25:].sum() * 0.8)
    pick, total = pt.choose_patches(carbon, 25, want, np.random.default_rng(1), tol=0.01)
    assert np.unique(pick).size == 25
    assert abs(total - want) <= 0.01 * want
    assert total == pytest.approx(carbon[pick].sum())
    pick, total = pt.choose_patches(carbon, 25, math.nan, np.random.default_rng(1), tol=0.01)
    assert pick.size == 25 and total == pytest.approx(carbon[pick].sum())


class _Bank:
    """The three things `PatchTransplant` reads off a `PilotBank`."""

    def __init__(self, runs: list[tuple[int, str]]) -> None:
        self._pred = {c: {"fold": 0} for c in range(NCELL)}
        self._x = {c: np.full(8, float(c)) for c in range(NCELL)}
        self.runs = runs

    def _candidates(self, fold: int) -> tuple[pl.DataFrame, Any, Any, Any]:
        df = pl.DataFrame({"cell": [c for c, _ in self.runs], "point": [p for _, p in self.runs]})
        z = np.array([np.full(8, 0.1 * i) for i in range(len(self.runs))])
        return df, z, np.zeros(8), np.ones(8)


@pytest.fixture(scope="module")
def setup(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("patchtx")
    template = _write(root / "restart_1999.lpj")
    pilot = root / "pilot"
    for k, (c, point) in enumerate(DONORS):
        dest = pt.pilot_restart(c, point, pilot)
        dest.parent.mkdir(parents=True)
        generic = GenericHeader(1, 1999, 1, c, 1, 22, 0.5, 1.0, 0.5, 4)
        head = RestartHeader(False, False, 0, False, False, STORED_SEED, True)
        with RestartWriter(dest, generic, head, ncell=1) as w:
            w.append(_record(10 + k)[0])
    return {"template": template, "pilot": pilot}


def _run(setup: dict[str, Any], pred: dict[str, float], runs: list[tuple[int, str]] = DONORS):
    template = setup["template"]
    rule = pt.PatchTransplant(
        template,
        0,
        NCELL,
        donors=_Bank(runs),
        forcing=_block(),
        n_runs=2,
        tol=0.05,
        pilot_root=str(setup["pilot"]),
    )
    reader = RestartReader(template)
    pool = build_donor_pool(RestartReader(template), [1, 2])
    with reader:
        tmpl = reader.read(0)
    return rule(tmpl, pred, pool, reader.layout, cell=0, seed=3), tmpl


def _no_litter(rows: np.ndarray) -> bytes:
    b = rows.view(np.uint8).reshape(-1, PFT_TREE_BYTES)[:, :LITTER_BYTE_IN_TREE]
    return b.tobytes()


def test_each_patch_is_one_donor_patch_and_the_carbon_is_matched(setup: dict[str, Any]) -> None:
    donor = [
        _no_litter(np.asarray(trees_of(p["pftlist"])))
        for c, point in DONORS
        for p in RestartReader(pt.pilot_restart(c, point, setup["pilot"])).read(0)["stands"][0][
            "patches"
        ]
    ]
    probe, _ = _run(setup, _prediction(vegc_target=1e9))  # unreachable: the heaviest set
    heaviest = probe[1].patch_tree_written
    grass = cell_vegc(probe[0])["grass"]
    (rec, rep), tmpl = _run(setup, _prediction(vegc_target=grass + 0.9 * heaviest))
    assert rep.patch_why == "matched", rep
    assert cell_vegc(rec)["tree"] == pytest.approx(0.9 * heaviest, rel=0.05)
    for patch in rec["stands"][0]["patches"]:
        trees = trees_of(patch["pftlist"])
        assert _no_litter(np.asarray(trees)) in donor
        ids = np.asarray(patch["soil"]["litter"]["pft_ids"])
        assert np.all(ids[trees["litter"]] == trees["id"])
    # Everything but the trees is the spin-up rule's record.
    base, _ = sr.SpinupRule(setup["template"], 0, NCELL, donors=None, forcing=_block())(
        tmpl,
        _prediction(),
        build_donor_pool(RestartReader(setup["template"]), [1, 2]),
        RestartReader(setup["template"]).layout,
        cell=0,
        seed=3,
    )
    assert rec["climbuf"] is not None
    for key in ("mtemp20", "atemp_mean"):
        if key in base["climbuf"]:
            np.testing.assert_array_equal(rec["climbuf"][key], base["climbuf"][key])
    assert rep.stems_placed == sum(trees_of(p["pftlist"]).size for p in rec["stands"][0]["patches"])
    assert rep.patch_runs >= 2
    assert tree_vegc(trees_of(rec["stands"][0]["patches"][0]["pftlist"])) >= 0.0


def test_a_donor_run_of_the_target_cell_is_refused(setup: dict[str, Any]) -> None:
    with pytest.raises(AssertionError, match="target cell itself"):
        _run(setup, _prediction(vegc_target=1e9), runs=[(0, "lhs00"), *DONORS])


def test_below_grass_places_no_tree(setup: dict[str, Any]) -> None:
    (rec, rep), _ = _run(setup, _prediction(vegc_target=0.0))
    assert rep.patch_why == "below-grass"
    assert all(trees_of(p["pftlist"]).size == 0 for p in rec["stands"][0]["patches"])
