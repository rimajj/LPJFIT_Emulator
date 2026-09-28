"""`synthesise_cell(patch_layout=...)`: which patch each placed stem stands in.

What must hold:
  * the default ("random") is the path that existed before the option: same bytes;
  * "template" puts roster stem k, at cell rank (k + 0.5) / n, into the patch holding the
    template's stem at that rank -- so patch counts follow the template's, and the tallest placed
    stem stands where the template's tallest does -- on both the copy and the composition paths;
  * an unknown layout is refused.
"""

from __future__ import annotations

import numpy as np
import pytest

from vegemu.binfmt.restart import Layout, trees_of
from vegemu.models.synth import synthesise_cell, template_ladder, template_patch_ladder

from .test_synth_composition import PREDICTION, _digest, _pool, _template


def _counts(rec: dict) -> list[int]:
    return [trees_of(p["pftlist"]).size for p in rec["stands"][0]["patches"]]


def _tallest_patch(rec: dict) -> int:
    tops = [
        float(np.max(trees_of(p["pftlist"])["height"])) if trees_of(p["pftlist"]).size else -1.0
        for p in rec["stands"][0]["patches"]
    ]
    return int(np.argmax(tops))


def test_the_patch_ladder_matches_the_template_ladder() -> None:
    tpl = _template()
    rows = template_ladder(tpl)
    homes = template_patch_ladder(tpl)
    assert homes.size == rows.size
    for p, patch in enumerate(tpl["stands"][0]["patches"]):
        mine = np.sort(np.asarray(trees_of(patch["pftlist"])["height"], dtype=float))
        np.testing.assert_array_equal(np.sort(np.asarray(rows["height"])[homes == p]), mine)


def test_default_is_the_old_path() -> None:
    a, _ = synthesise_cell(_template(), PREDICTION, _pool(), Layout(), cell=0, template_cell=0)
    b, rep = synthesise_cell(
        _template(), PREDICTION, _pool(), Layout(), cell=0, template_cell=0, patch_layout="random"
    )
    assert _digest(a) == _digest(b)
    assert rep.patch_layout == "random"


@pytest.mark.parametrize("shares", [None, [0.0, 0.3, 0.0, 0.5, 0.2, 0.0, 0.0]])
def test_template_layout_follows_the_template_patches(shares: list[float] | None) -> None:
    tpl = _template()
    want = [trees_of(p["pftlist"]).size for p in tpl["stands"][0]["patches"]]
    n_tpl = sum(want)
    pred = {**PREDICTION, "stems_per_patch": 2.0 * n_tpl / len(want)}  # twice the template's
    rec, rep = synthesise_cell(
        tpl,
        pred,
        _pool(),
        Layout(),
        cell=0,
        template_cell=0,
        type_shares=shares,
        patch_layout="template",
    )
    got = _counts(rec)
    assert rep.patch_layout == "template"
    assert sum(got) == rep.stems_placed
    np.testing.assert_allclose(got, np.array(want) * sum(got) / n_tpl, atol=2.0)
    assert _tallest_patch(rec) == _tallest_patch(tpl)


def test_unknown_layout_is_refused() -> None:
    with pytest.raises(ValueError, match="patch_layout"):
        synthesise_cell(
            _template(), PREDICTION, _pool(), Layout(), cell=0, template_cell=0, patch_layout="x"
        )
