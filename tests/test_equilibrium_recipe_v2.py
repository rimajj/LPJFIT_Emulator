"""The recipe-v2 confirmation reads its recipe from the pre-registration, which the seal covers.

Checks that the draft's `recipe:` block builds the recipe the screen recommended (v3 features,
sealed targets, two stages, tuned settings, no bagging), that a missing or extra field is refused
rather than defaulted, and that the draft's statistic is the one the script reports.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from exp_equilibrium_recipe_v2 import DEFAULT_EXP, STATISTIC, recipe_from

PREREG = (
    Path(__file__).resolve().parent.parent / "experiments" / DEFAULT_EXP / "preregistration.yaml"
)


def _prereg() -> dict[str, object]:
    return dict(yaml.safe_load(PREREG.read_text()))


def test_the_draft_recipe_is_the_screened_one() -> None:
    r = recipe_from(_prereg())
    assert (r.v3, r.soil, r.target, r.stage2, r.bag) == (True, True, "sealed", True, 1)
    params = dict(r.params)
    assert params["n_estimators"] == 1281 and params["num_leaves"] == 31
    assert r.lgbm()["subsample_freq"] == 1  # inherited from the sealed settings


def test_a_recipe_with_a_missing_or_extra_field_is_refused() -> None:
    p = _prereg()
    spec = dict(p["recipe"])  # type: ignore[arg-type]
    for broken in ({k: v for k, v in spec.items() if k != "bag"}, {**spec, "train_frac": 0.5}):
        with pytest.raises(ValueError, match="recipe fields"):
            recipe_from({**p, "recipe": broken})


def test_statistic_matches_the_draft() -> None:
    p = _prereg()
    assert p["estimand"]["name"] == STATISTIC  # type: ignore[index]
    assert p["decision_rule"]["statistic"] == STATISTIC  # type: ignore[index]
