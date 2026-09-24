"""The continuation run's plan and config (`scripts/spinup_continuation.py`).

* the members are contiguous, cover every cell exactly once, and balance the projected cost;
* the member config is the stored run's saved config with exactly the continuation's changes:
  its own input list (constant CO2), a 30-year spin-up continuation at model years 1871-1900
  from the named restart, no restart written, the four outputs, and the member's cell range --
  and the spin-up branch the stored run itself compiled is left as it was (`needs_real_data`).
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from vegemu.paths import path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import spinup_continuation as sc


def test_members_are_contiguous_cover_every_cell_and_balance_the_cost() -> None:
    rng = np.random.default_rng(3)
    cost = rng.gamma(0.8, 1.0, size=5000)
    ranges = sc.partition(cost, 64)
    assert len(ranges) == 64
    assert ranges[0][0] == 0 and ranges[-1][1] == cost.size - 1
    assert all(b[0] == a[1] + 1 for a, b in itertools.pairwise(ranges))
    per = np.array([cost[a : b + 1].sum() for a, b in ranges])
    # Greedy cut: every member but the last reaches the target, and none overshoots by more than
    # its heaviest cell.
    assert per[:-1].min() >= cost.sum() / 64 - 1e-9
    assert per.max() <= cost.sum() / 64 + cost.max() + 1e-9


def test_the_cost_model_floors_a_bare_cell_and_prices_a_skip_at_almost_nothing() -> None:
    c = sc.cell_cost(np.array([100_000, 2_216_864, 3_546_287]), np.array([False, False, True]))
    assert c[0] == pytest.approx(sc.COST_FLOOR_S)
    assert c[1] == pytest.approx(sc.COST_INTERCEPT_S + sc.COST_PER_MB_S * 2.216864)
    assert c[2] < sc.COST_FLOOR_S


@pytest.mark.needs_real_data
def test_the_member_config_is_the_stored_config_with_only_the_continuation_changes(
    tmp_path: Path,
) -> None:
    saved = path("ground_truth.historical_seed1") / sc.SAVED_CONFIG_SUBDIR
    if not saved.exists():
        pytest.skip("the stored run's saved config is not present")
    restart = tmp_path / "restart_x.lpj"
    base = sc.arm_config_text(tmp_path / "input_continuation.js", restart)
    text = sc.member_config(base, 100, 199)
    original = saved.read_text(encoding="utf-8")
    assert text.count(f'#include "{tmp_path / "input_continuation.js"}"') == 2
    assert '"startgrid" : 100,' in text and '"endgrid" : 199,' in text
    tail = text.split("#else")[-1]
    for want in (
        '"nspinup" : 30,',
        '"nspinyear" : 30,',
        '"firstyear": 1901,',
        '"lastyear" : 1900,',
        '"outputyear": 1871,',
        '"restart" :  true,',
        f'"restart_filename" : "{restart}",',
        '"write_restart" : false',
    ):
        assert want in tail, want
    outputs = re.search(r'#ifdef FROM_RESTART\s*\n\s*"output"(.*?)#else', text, re.S)
    assert outputs is not None
    ids = re.findall(r'"id" : "(\w+)"', outputs.group(1))
    assert ids == ["grid", "globalflux", "vegc", "climatyear"]
    # The spin-up branch (what the stored run compiled) is untouched, byte for byte.
    spin = re.compile(r"#ifndef FROM_RESTART\n(.*?)\n#else\n", re.S)
    m_new, m_old = spin.search(text), spin.search(original)
    assert m_new is not None and m_old is not None and m_new.group(1) == m_old.group(1)
    # Everything outside the patched pieces is the saved file's.
    for key in ('"npatch" : 25,', '"random_seed" : 1,', '"shuffle_climate" : true,'):
        assert key in text and key in original
