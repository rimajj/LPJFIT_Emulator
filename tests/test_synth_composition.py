"""Predicted composition, the climate-driven type rule, analogue donors and the litter rescale.

The first test is the one that protects the deliverable: with none of the new options, the
synthesiser must emit exactly the bytes it emitted before they existed. The pinned digests were
computed with the synthesiser at commit cf11a5c on the fixture below; any change to the default
path's arithmetic or its random-number sequence changes them.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

import numpy as np

from vegemu.binfmt.restart import PFT_TREE_BYTES, TREE_DTYPE, Layout, trees_of
from vegemu.models.synth import (
    DonorPool,
    choose_analogue_runs,
    largest_remainder,
    pool_from_rows,
    synthesise_cell,
    weighted_percentile,
)


def _stem(pft_id: int, height: float, wooddens: float, d95: float) -> np.ndarray:
    row = np.zeros(1, dtype=TREE_DTYPE)
    row["id"] = pft_id
    row["height"] = height
    row["wooddens"] = wooddens
    row["nind"] = 1.0 / 225.0
    row["sla"] = 0.02 + 0.001 * pft_id
    row["longevity"] = 0.6
    row["ind_leaf_c"] = height
    row["ind_sapwood_c"] = 100.0 * height
    row["ind_heartwood_c"] = 200.0 * height
    row["age"] = int(4 * height) + 1
    row["D95max"] = d95
    row["litter"] = 0
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


def _soil(p: int) -> dict[str, Any]:
    return {
        "pool": np.full((5, 4), 10.0 + p),
        "k_mean": np.zeros(5),
        "litter": {
            "n": 2,
            "pft_ids": np.array([1, 3], dtype=np.uint8),
            "items": np.full((2, 22), 1.0 + p),
            "agtop": np.array([0.1, 0.05, 0.3, 5.0]),
            "avg_fbd": np.zeros(5),
        },
        "w_fw": np.zeros(23),
    }


def _template(treeless: bool = False) -> dict[str, Any]:
    """Four patches of types 1, 3, 3, 4, with type 3 the tall one -- a type-size association."""
    rng = np.random.default_rng(7)
    patches = []
    for p in range(4):
        stems = []
        for k in range(0 if treeless else 12 + p):
            t = (1, 3, 3, 4)[k % 4]
            h = float(rng.gamma(2.0, 3.0) + (4.0 if t == 3 else 0.0))
            wd = float(2.0e5 + 1e4 * t + rng.normal(0, 1e4))
            stems.append(_stem(t, h, wd, 0.5 + 0.05 * h))
        patches.append({"soil": _soil(p), "pftlist": _pftlist(stems), "frac_g": np.zeros(6)})
    return {
        "skip": 0,
        "climbuf": {"marker": 1},
        "stands": [{"landusetype": 0, "npatch": 4, "patches": patches, "frac": 1.0}],
    }


def _pool() -> DonorPool:
    """Types 0, 1, 3, 4, 5 -- including type 0, which the template never holds."""
    rng = np.random.default_rng(11)
    stems = []
    for k in range(400):
        t = (0, 1, 3, 4, 5)[k % 5]
        h = float(rng.gamma(2.0, 4.0) + 0.5)
        stems.append(_stem(t, h, float(1.8e5 + 1.2e4 * t + rng.normal(0, 2e4)), 0.2 + 0.1 * h))
    raw = np.stack([s.view(np.uint8).reshape(PFT_TREE_BYTES) for s in stems])
    return DonorPool(raw=raw, fields=np.concatenate(stems), source_cells=(0,))


PREDICTION = {
    "stems_per_patch": 14.4,
    "height_p10": 2.0,
    "height_p50": 6.5,
    "height_p90": 15.0,
    "wooddens_p10": 1.9e5,
    "wooddens_p50": 2.3e5,
    "wooddens_p90": 2.8e5,
    "D95max_p10": 0.6,
    "D95max_p50": 0.9,
    "D95max_p90": 1.4,
    "soilc": 300.0,
}


def _digest(rec: dict[str, Any]) -> str:
    h = hashlib.sha256()
    for p in rec["stands"][0]["patches"]:
        h.update(p["pftlist"]["raw"])
        h.update(np.ascontiguousarray(p["soil"]["pool"]).tobytes())
        lit = p["soil"]["litter"]
        h.update(np.ascontiguousarray(lit["pft_ids"]).tobytes())
        h.update(np.ascontiguousarray(lit["items"]).tobytes())
    return h.hexdigest()


def _placed(rec: dict[str, Any]) -> Any:
    rows = [trees_of(p["pftlist"]) for p in rec["stands"][0]["patches"]]
    rows = [r for r in rows if r.size]
    return np.concatenate(rows) if rows else np.zeros(0, dtype=TREE_DTYPE)


def _run(**kw: Any) -> tuple[dict[str, Any], Any]:
    template = kw.pop("template", None) or _template()
    return synthesise_cell(
        template, dict(PREDICTION), _pool(), Layout(), cell=1, template_cell=1, seed=5, **kw
    )


# ---------------------------------------------------------------------------------------------
# The default path is untouched.
# ---------------------------------------------------------------------------------------------
PIN_DEFAULT = "ec108418367e8891a044026dc27f6195ae6cf2e97bea535c2fb8d0c090f93afd"
PIN_IMPOSED = "38a2136eb91488db1df9ec64afd5529bb8644b418e877a420bb300305b1c9f92"


def test_the_default_path_emits_the_bytes_it_emitted_before_the_options_existed() -> None:
    rec, rep = _run()
    assert _digest(rec) == PIN_DEFAULT
    assert rep.composition == "template" and rep.climbuf_source == "template"
    assert rec["climbuf"] == {"marker": 1}


def test_the_imposed_path_is_untouched_too() -> None:
    rec, _ = _run(impose_traits=("D95max",))
    assert _digest(rec) == PIN_IMPOSED


# ---------------------------------------------------------------------------------------------
# Composition.
# ---------------------------------------------------------------------------------------------
def test_largest_remainder_is_exact_and_proportional() -> None:
    counts = largest_remainder([0.5, 0.3, 0.2, 0, 0, 0, 0], 57)
    assert counts.sum() == 57
    assert list(counts[:3]) == [29, 17, 11]  # 28.5, 17.1, 11.4 -> the .5 wins the spare stem
    assert largest_remainder([0.0] * 7, 10).sum() == 0
    assert largest_remainder([np.nan, 1.0, -1.0, 0, 0, 0, 0], 5).tolist()[:3] == [0, 5, 0]


def test_the_written_mix_is_the_requested_mix_to_the_stem() -> None:
    shares = [0.0, 0.2, 0.0, 0.5, 0.3, 0.0, 0.0]
    rec, rep = _run(type_shares=shares, allowed_types=(1, 3, 4))
    ids = np.asarray(_placed(rec)["id"], dtype=int)
    want = largest_remainder(shares, rep.stems_requested)
    assert np.bincount(ids, minlength=7).tolist() == want.tolist()
    assert rep.inadmissible_placed == 0
    assert rep.composition == "predicted" and rep.shares_source == "given"


def test_the_type_size_association_survives_a_new_mix() -> None:
    """Type 3 is the tall type in the template; it must stay the tall type in the new roster."""
    rec, _ = _run(type_shares=[0, 0.5, 0, 0.5, 0, 0, 0], allowed_types=(1, 3))
    placed = _placed(rec)
    h = np.asarray(placed["height"], dtype=float)
    ids = np.asarray(placed["id"], dtype=int)
    assert h[ids == 3].mean() > h[ids == 1].mean()


def test_a_type_the_template_lacks_takes_its_ladder_from_the_donors() -> None:
    rec, rep = _run(type_shares=[0.4, 0.3, 0, 0.3, 0, 0, 0], allowed_types=(0, 1, 3))
    assert rep.ladder_source[0] == "donors" and rep.ladder_source[3] == "template"
    assert (np.asarray(_placed(rec)["id"]) == 0).sum() > 0


def test_a_type_the_target_climate_forbids_is_dropped_even_if_asked_for() -> None:
    rec, rep = _run(type_shares=[0.5, 0.25, 0, 0.25, 0, 0, 0], allowed_types=(1, 3))
    ids = set(np.asarray(_placed(rec)["id"], dtype=int).tolist())
    assert ids <= {1, 3}
    assert abs(rep.share_mass_removed - 0.5) < 1e-12
    assert rep.inadmissible_placed == 0 and rep.type_fallbacks == 0


def test_a_treeless_template_no_longer_switches_the_type_rule_off() -> None:
    """THE HOLE: with no template ladder, the old rule admitted every type in the pool."""
    template = _template(treeless=True)
    old, _ = synthesise_cell(
        template, dict(PREDICTION), _pool(), Layout(), cell=1, template_cell=1, seed=5
    )
    assert len(set(np.asarray(_placed(old)["id"], dtype=int).tolist())) > 2  # anything goes
    rec, rep = _run(template=_template(treeless=True), allowed_types=(4, 5))
    ids = set(np.asarray(_placed(rec)["id"], dtype=int).tolist())
    assert ids and ids <= {4, 5}
    assert rep.shares_source == "donor-pool"
    assert rep.inadmissible_placed == 0


def test_the_climate_buffer_is_replaced_only_when_given() -> None:
    new = {"marker": 2}
    rec, rep = _run(allowed_types=(1, 3, 4), climbuf=new)
    assert rec["climbuf"] is new and rep.climbuf_source == "forcing"


def test_the_litter_is_rescaled_with_its_derived_properties_and_no_water_is_lost() -> None:
    template = _template()
    before = sum(
        float(p["soil"]["litter"]["agtop"][1] + p["soil"]["w_fw"][0])
        for p in template["stands"][0]["patches"]
    )
    pred = {**PREDICTION, "litterc": 2.0}
    rec, rep = synthesise_cell(
        template, pred, _pool(), Layout(), cell=1, template_cell=1, seed=5, rescale_litter=True
    )
    patches = rec["stands"][0]["patches"]
    litter = np.mean(
        [
            float(
                p["soil"]["litter"]["items"][:, 0:20:2].sum()
                + p["soil"]["litter"]["items"][:, 20].sum()
            )
            for p in patches
        ]
    )
    assert abs(litter - 2.0) < 1e-12
    for p in patches:
        lit = p["soil"]["litter"]
        dm = float(lit["items"][:, 0].sum()) / 0.42
        assert abs(lit["agtop"][0] - 2e-3 * dm) < 1e-15
        assert lit["agtop"][1] <= lit["agtop"][0] + 1e-15
    after = sum(float(p["soil"]["litter"]["agtop"][1] + p["soil"]["w_fw"][0]) for p in patches)
    assert abs(after - before) < 1e-12
    assert rep.litter_target == 2.0
    # C:N preserved: carbon and nitrogen scale together. Only the template's own two slots; a slot
    # appended for a newly placed type starts empty.
    old = template["stands"][0]["patches"][0]["soil"]["litter"]["items"]
    ratio = patches[0]["soil"]["litter"]["items"][: old.shape[0]] / old
    assert np.allclose(ratio, ratio.flat[0])


def test_weighted_percentile_with_equal_weights_brackets_the_sample() -> None:
    x = np.arange(1.0, 11.0)
    q = weighted_percentile(x, np.ones_like(x), [5.0, 50.0, 95.0])
    assert q[0] == 1.0 and q[1] == 5.5 and q[2] == 10.0


# ---------------------------------------------------------------------------------------------
# Analogue donors.
# ---------------------------------------------------------------------------------------------
def test_analogue_runs_are_nearest_first_and_hold_the_wanted_type() -> None:
    z = np.array([[0.0], [1.0], [2.0], [3.0], [4.0]])
    counts = np.zeros((5, 7), dtype=np.int64)
    counts[:, 3] = [0, 150, 150, 150, 150]  # the nearest run holds none of type 3
    counts[:, 1] = [500, 0, 0, 0, 0]
    got = choose_analogue_runs(np.array([0.0]), z, counts, {3: 10, 1: 10}, min_stems=200)
    assert got[3].tolist() == [1, 2]  # 150 + 150 >= 200; the empty nearest run is skipped
    assert got[1].tolist() == [0]
    capped = choose_analogue_runs(np.array([0.0]), z, counts, {3: 1000}, max_runs=3)
    assert capped[3].tolist() == [1, 2, 3]


def test_a_pool_built_from_raw_rows_decodes_them() -> None:
    raw = _pool().raw[:7]
    pool = pool_from_rows(raw, (5,))
    assert pool.n == 7 and pool.source_cells == (5,)
    assert np.array_equal(np.asarray(pool.fields["id"]), raw[:, 0])
