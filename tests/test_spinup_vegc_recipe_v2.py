"""The spin-up recipe-v2 confirmation reads its recipe from the pre-registration, strictly.

Checks that a recipe block builds exactly the screen's `Recipe` (every field, the tuned settings
as a sorted tuple), that a missing or extra field is refused rather than defaulted, that the
feature-table pin names one of the two known table sets, and -- once the draft exists -- that its
recipe block parses and its statistic is the one the script reports.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_spinup_vegc_recipe_v2 import DEFAULT_EXP, STATISTIC, pinned_tables, recipe_from
from screen_spinup_vegc import Recipe

PREREG = (
    Path(__file__).resolve().parent.parent / "experiments" / DEFAULT_EXP / "preregistration.yaml"
)


def _spec() -> dict[str, Any]:
    r = Recipe(
        "x",
        feats="v3x",
        target="half2_seeds",
        gate="soft",
        objective="l1",
        capacity="tuned",
        params=(("learning_rate", 0.05), ("num_leaves", 63)),
        pool="both",
        bag=5,
    )
    spec = dataclasses.asdict(r)
    spec["params"] = dict(r.params)
    return spec


def test_a_recipe_block_builds_the_screens_recipe() -> None:
    r = recipe_from({"recipe": _spec()})
    assert r.feats == "v3x" and r.gate == "soft" and r.bag == 5 and r.pool == "both"
    assert r.params == (("learning_rate", 0.05), ("num_leaves", 63))


def test_a_recipe_with_a_missing_or_extra_field_is_refused() -> None:
    spec = _spec()
    for broken in ({k: v for k, v in spec.items() if k != "bag"}, {**spec, "train_frac": 0.5}):
        with pytest.raises(ValueError, match="recipe fields"):
            recipe_from({"recipe": broken})


def test_the_feature_pin_must_name_a_known_table_set() -> None:
    bad = {"data": {"features": {"tag": "v4", "dir": "/nowhere"}}}
    with pytest.raises(SystemExit, match="v3x or v3p"):
        pinned_tables(bad)


@pytest.mark.skipif(not PREREG.exists(), reason="the draft is written after the screen")
def test_the_draft_parses_and_names_this_statistic() -> None:
    p = yaml.safe_load(PREREG.read_text())
    if "recipe" not in p:
        pytest.skip("the draft has no recipe yet")
    recipe_from(p)
    assert p["estimand"]["name"] == STATISTIC
    assert p["decision_rule"]["statistic"] == STATISTIC
    assert p["decision_rule"]["pass_if"] == ">= -0.02"
