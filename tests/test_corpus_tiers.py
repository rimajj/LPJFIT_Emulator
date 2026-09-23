"""Mid-tier readiness: the CO2 level, the nested design, the tile cap, the plan-vs-CLI refusals.

Each of these was a way for a larger corpus to come out silently different from what its plan says:

* `test_a_non_default_co2_file_starts_by_model_year_1000` -- before a CO2 file's first year LPJmL
  substitutes its own 276.59 ppm (getco2.c:47). The historical file starts in 1700, harmless only
  at 276.59; at any other level it would put a CO2 step 700 years into a "constant" spin-up.
* `test_the_nested_design_contains_the_pilot_design_exactly` -- a mid tier drawn afresh would share
  no hypercube climate with the pilot, so no pilot row could be checked against it.
* `test_the_tile_cap_does_not_truncate_a_large_tier` -- a fixed cap of 3 silently returned 472 cells
  for a 1,000-cell request.
* `test_the_build_refuses_a_co2_mode_the_plan_does_not_have` -- the build used to take CO2 from the
  command line, so forgetting a flag built transient configs under a constant plan.

Like `test_pilot_replicate.py`, nothing here may create a directory under the scratch root: CI has
no /p. Filesystem-touching stages are exercised with their path helpers monkeypatched to tmp_path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import polars as pl
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vegemu.corpus.perturb import AXIS_RANGE, nested_design, pilot_design  # noqa: E402
from vegemu.corpus.select import MAX_PER_TILE, tile_cap  # noqa: E402
from vegemu.paths import paths  # noqa: E402


def _script(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------
# write_constant_co2
# ------------------------------------------------------------------------------------------------


def test_the_existing_call_is_byte_identical(tmp_path: Path) -> None:
    cfg = _script("corpus_spinup_config")
    f = cfg.write_constant_co2(tmp_path / "co2.txt")
    assert f.read_text() == "".join(f"{y}  276.59\n" for y in range(1700, 2101))


def test_a_non_default_co2_file_starts_by_model_year_1000(tmp_path: Path) -> None:
    cfg = _script("corpus_spinup_config")

    f = cfg.write_constant_co2(tmp_path / "co2.txt", ppm=350.0)
    assert f.read_text().splitlines()[0] == "1000  350.00"
    seen = cfg.co2_seen_by_model(f, range(1000, 2000))
    assert set(seen.values()) == {350.0}, "some spin-up year fell back to the 276.59 clamp"


def test_the_clamp_really_bites_on_a_late_file(tmp_path: Path) -> None:
    """The failure the rule prevents, reproduced: what the model would see from a 1700 file."""
    cfg = _script("corpus_spinup_config")
    f = tmp_path / "late.txt"
    f.write_text("".join(f"{y}  350.00\n" for y in range(1700, 2101)))
    seen = cfg.co2_seen_by_model(f, range(1000, 2000))
    assert seen[1000] == 276.59 and seen[1699] == 276.59 and seen[1700] == 350.0


def test_the_truth_builders_keyword_call_works(tmp_path: Path) -> None:
    """Another stream calls it with exactly these keyword names."""
    cfg = _script("corpus_spinup_config")
    f = cfg.write_constant_co2(tmp_path / "c.txt", ppm=400.0, first_year=900, last_year=2019)
    lines = f.read_text().splitlines()
    assert (lines[0], lines[-1], len(lines)) == ("900  400.00", "2019  400.00", 1120)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"ppm": 350.0, "first_year": 1700}, "not be constant"),
        ({"ppm": 350.0, "last_year": 1990}, "must reach model year 1999"),
        ({"ppm": 350.125}, "two decimals"),
        ({"ppm": -1.0}, "positive"),
    ],
)
def test_bad_co2_files_are_refused(tmp_path: Path, kwargs: dict[str, float], match: str) -> None:
    cfg = _script("corpus_spinup_config")
    with pytest.raises(ValueError, match=match):
        cfg.write_constant_co2(tmp_path / "c.txt", **kwargs)


def test_276_59_may_start_anywhere(tmp_path: Path) -> None:
    cfg = _script("corpus_spinup_config")
    f = cfg.write_constant_co2(tmp_path / "c.txt", ppm=276.59, first_year=1000)
    assert f.read_text().splitlines()[0] == "1000  276.59"


def test_read_co2_input_finds_exactly_one_entry(tmp_path: Path) -> None:
    cfg = _script("corpus_spinup_config")
    f = tmp_path / "input.js"
    f.write_text('  "co2" :          { "fmt" : "txt",  "name" : "/x/co2.txt"},\n')
    assert cfg.read_co2_input(f) == "/x/co2.txt"
    f.write_text("nothing here\n")
    with pytest.raises(AssertionError, match="0 co2 entries"):
        cfg.read_co2_input(f)


# ------------------------------------------------------------------------------------------------
# The nested design
# ------------------------------------------------------------------------------------------------


def test_the_nested_design_contains_the_pilot_design_exactly() -> None:
    base, full = pilot_design(30), nested_design(100)
    assert len(full) == 100
    assert full[:30] == base
    assert len({p.name for p in full}) == 100
    assert [p.name for p in full[30:32]] == ["lhs18", "lhs19"]


def test_the_nested_design_stays_in_range_and_is_reproducible() -> None:
    full = nested_design(100)
    assert full == nested_design(100)
    for p in full:
        for key, (lo, hi) in AXIS_RANGE.items():
            v = {"dtemp": p.dtemp, "fprec": p.fprec, "sprec": p.sprec, "frad": p.frad}.get(
                key, p.fiav
            )
            assert lo <= v <= hi, (p.name, key, v)
    assert not any(p.hold_huss_diagnostic for p in full)


def test_the_union_is_nearly_one_hypercube() -> None:
    """Per axis, the 88 free points should fill (almost) all 88 strata: the new points take only
    strata the pilot's 18 left empty."""
    free = [p for p in nested_design(100) if p.name.startswith("lhs")]
    assert len(free) == 88
    for j, (lo, hi) in enumerate(AXIS_RANGE.values()):
        vals = np.array([(p.dtemp, p.fprec, p.sprec, p.frad, p.fiav)[j] for p in free])
        strata = np.clip(((vals - lo) / (hi - lo) * 88).astype(int), 0, 87)
        assert np.unique(strata).size >= 86, f"axis {j}: {np.unique(strata).size} of 88 strata"


def test_a_nested_design_of_the_base_size_is_the_base() -> None:
    assert nested_design(30) == pilot_design(30)
    with pytest.raises(ValueError, match="smaller than"):
        nested_design(20)


# ------------------------------------------------------------------------------------------------
# The tile cap
# ------------------------------------------------------------------------------------------------


def _tiles(sizes: list[int]) -> np.ndarray:
    return np.repeat(np.arange(len(sizes)), sizes)


def test_the_tile_cap_is_the_pilots_at_200() -> None:
    tiles = _tiles([1, 2, 5, 40, 400] * 33)
    assert tile_cap(200, tiles) == MAX_PER_TILE == 3


def test_the_tile_cap_does_not_truncate_a_large_tier() -> None:
    sizes = [1, 2, 5, 40, 400] * 33
    tiles = _tiles(sizes)
    assert int(np.minimum(sizes, 3).sum()) < 1000, "the premise: a cap of 3 cannot hold 1,000"
    cap = tile_cap(1000, tiles)
    assert cap >= 15
    assert int(np.minimum(sizes, cap).sum()) >= 1000


def test_an_explicit_cap_is_honoured_and_too_many_cells_are_refused() -> None:
    tiles = _tiles([10, 10])
    assert tile_cap(15, tiles, explicit=2) == 2
    with pytest.raises(ValueError, match="exceeds"):
        tile_cap(25, tiles)
    with pytest.raises(ValueError, match="at least 1"):
        tile_cap(5, tiles, explicit=0)


# ------------------------------------------------------------------------------------------------
# corpus_pilot: tiers, CO2 bookkeeping, the table comparison
# ------------------------------------------------------------------------------------------------


def test_tier_directories() -> None:
    m = _script("corpus_pilot")
    assert m._vdir("v2-constco2", 1) == "pilot-v2-constco2"
    assert m._vdir("dryrun", 1, "mid") == "mid-dryrun"
    assert m._vdir("dryrun", 2, "mid") == "mid-dryrun-s2"
    assert m.run_dir("v1", 42490, "control", 2, "mid").parts[-3] == "mid-v1-s2"
    assert m.forcing_dir("v1", 42490, "control", "mid").parts[-3] == "mid-v1"
    with pytest.raises(ValueError, match="unknown tier"):
        m._vdir("v1", 1, "huge")


def test_the_mid_tier_defaults() -> None:
    mid = _script("corpus_pilot").TIERS["mid"]
    assert (mid.ncell, mid.npoint, mid.design, mid.nest_in, mid.const_co2) == (
        1000,
        100,
        "nested",
        "pilot-v2-constco2",
        True,
    )


def test_co2_from_provenance_and_cli() -> None:
    m = _script("corpus_pilot")
    co2 = m.Co2
    assert co2.of_provenance({"co2_constant": True}) == co2(True, 276.59)  # a pre-ppm plan
    assert co2.of_provenance({"co2_constant": False}) == co2(False, None)
    assert co2.of_provenance({"co2_constant": True, "co2_ppm": 350.0}) == co2(True, 350.0)
    assert m.co2_from_cli(None, None) is None
    assert m.co2_from_cli(True, None) == co2(True, 276.59)
    assert m.co2_from_cli(None, 350.0) == co2(True, 350.0)
    assert m.co2_from_cli(False, None) == co2(False, None)
    with pytest.raises(SystemExit):
        m.co2_from_cli(False, 350.0)


def _fake_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, prov: dict[str, object]) -> None:
    m = _script("corpus_pilot")
    (tmp_path / "provenance.json").write_text(json.dumps(prov))
    monkeypatch.setattr(m, "meta_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(m, "_meta_path", lambda *a, **k: tmp_path)


def test_the_build_refuses_a_co2_mode_the_plan_does_not_have(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    m = _script("corpus_pilot")
    _fake_plan(monkeypatch, tmp_path, {"co2_constant": True, "co2": "CONSTANT", "npoint": 30})
    with pytest.raises(SystemExit, match="the plan says"):
        m.stage_build("v9", 1, 0, 1, co2=m.Co2(False, None))
    with pytest.raises(SystemExit, match="the plan says"):
        m.stage_build("v9", 1, 0, 1, co2=m.Co2(True, 350.0))


def test_the_build_refuses_a_point_count_the_plan_does_not_have(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    m = _script("corpus_pilot")
    _fake_plan(monkeypatch, tmp_path, {"co2_constant": False, "co2": "T", "npoint": 30})
    with pytest.raises(SystemExit, match="--npoint 100"):
        m.stage_build("v9", 1, 0, 1, 100)


def test_every_stage_refuses_a_plan_of_another_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    m = _script("corpus_pilot")
    _fake_plan(monkeypatch, tmp_path, {"tier": "mid", "co2_constant": True, "npoint": 100})
    with pytest.raises(SystemExit, match="planned as tier 'mid'"):
        m.stage_build("v9", 1, 0, 1, tier="pilot")


def test_a_derived_version_cannot_be_built(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    m = _script("corpus_pilot")
    _fake_plan(monkeypatch, tmp_path, {"derived_from": {"corpus_dir": "pilot-v2-constco2"}})
    with pytest.raises(SystemExit, match="no spin-ups of its own"):
        m.stage_build("v9", 1, 0, 1)


def test_in_place_decode_refuses_another_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    m = _script("corpus_pilot")
    _fake_plan(monkeypatch, tmp_path, {"co2_constant": True, "plan_sha256": "x"})
    with pytest.raises(SystemExit, match="Use --out-version"):
        m.stage_decode("v9", 1, None, schema=3)


def _table(n: int = 6) -> pl.DataFrame:
    rng = np.random.default_rng(0)
    stems = np.array([0.0, 5.0, 0.0, 9.0, 3.0, 0.0])[:n]
    cols: dict[str, object] = {"name": [f"r{i}" for i in range(n)], "stems_total": stems}
    for i in range(7):
        cols[f"pft_frac_{i}"] = np.where(stems > 0, rng.random(n), 0.0)
    cols["agb"] = rng.random(n)
    return pl.DataFrame(cols)


def test_compare_tables_accepts_the_schema_change_and_nothing_else() -> None:
    m = _script("corpus_pilot")
    old = _table()
    pft = [f"pft_frac_{i}" for i in range(7)]
    treeless = pl.col("stems_total") <= 0
    new = old.with_columns(
        [pl.when(treeless).then(float("nan")).otherwise(pl.col(c)).alias(c) for c in pft]
    ).with_columns(*(pl.lit(1.0).alias(c) for c in m.SOIL_FEATURES))
    ok = m.compare_tables(old, new.reverse(), 2, 3)  # row order must not matter
    assert ok["ok"], ok["unexpected"]
    assert ok["differing_columns"] == dict.fromkeys(pft, 3)
    assert ok["treeless_rows"] == 3

    assert m.compare_tables(old, old, 2, 2)["ok"]
    moved = old.with_columns(pl.col("agb") + 1e-12)
    assert not m.compare_tables(old, moved, 2, 2)["ok"]
    # a share that moved on a TREED row is not the schema change
    bad = new.with_columns(
        pl.when(pl.col("name") == "r1")
        .then(0.5)
        .otherwise(pl.col("pft_frac_0"))
        .alias("pft_frac_0")
    )
    assert not m.compare_tables(old, bad, 2, 3)["ok"]
    # the shares turning NaN WITHOUT a schema bump is a defect, not the fix
    assert not m.compare_tables(old, new.drop(list(m.SOIL_FEATURES)), 2, 2)["ok"]
    # ...and the fix left undone on ONE treeless row (r2 keeps its 0.0) is refused too, although
    # every row that does differ differs exactly as the schema says
    half = new.with_columns(
        pl.when(pl.col("name") == "r2")
        .then(0.0)
        .otherwise(pl.col("pft_frac_4"))
        .alias("pft_frac_4")
    )
    res = m.compare_tables(old, half, 2, 3)
    assert not res["ok"]
    assert res["unexpected"] == ["pft_frac_4: 1 treeless rows are not NaN under schema 3"]


def _two_versions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, prov: dict[str, object]
) -> ModuleType:
    """`meta_dir`/`_meta_path` resolved per version under tmp_path, the source one planned."""
    m = _script("corpus_pilot")

    def where(version: str, seed: int = 1, tier: str = "pilot") -> Path:
        d = tmp_path / m._vdir(version, seed, tier)
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(m, "meta_dir", where)
    monkeypatch.setattr(m, "_meta_path", where)
    (where("v9") / "provenance.json").write_text(json.dumps(prov))
    return m


def test_a_re_decode_without_a_source_table_is_refused_before_decoding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """It used to decode, skip the diff with `ok: True`, and print DECODED -- compared with nothing.
    No runs.csv exists here, so reaching the decode at all would fail differently."""
    m = _two_versions(monkeypatch, tmp_path, {"co2_constant": True, "plan_sha256": "x"})
    with pytest.raises(SystemExit, match="Decode it in place first"):
        m.stage_decode("v9", 1, None, out_version="v10")
    (tmp_path / "pilot-v9-s2").mkdir()
    (tmp_path / "pilot-v9-s2" / "provenance.json").write_text(json.dumps({"seed": 2}))
    with pytest.raises(SystemExit, match=r"--seed 2\)"):
        m.stage_decode("v9", 1, None, 2, out_version="v10")
    assert not (tmp_path / "pilot-v10" / "provenance.json").exists(), "claimed nothing"


def test_a_replicate_plan_must_take_its_first_seeds_co2_and_design(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Seed 2 planned without `--const-co2` under a constant seed 1 used to be accepted, and the
    build -- which reads CO2 from the plan -- then built a transient-CO2 "replicate"."""
    first = {"co2_constant": True, "co2": "CONSTANT 276.59", "npoint": 30, "plan_sha256": "x"}
    m = _two_versions(monkeypatch, tmp_path, first)
    monkeypatch.setattr(m, "pilot_cells", lambda *a, **k: pytest.fail("got past the guard"))
    for co2, npoint, kind in (
        (m.Co2(False, None), 30, "pilot"),
        (m.Co2(True, 350.0), 30, "pilot"),
        (m.Co2(True, 276.59), 100, "nested"),
    ):
        with pytest.raises(SystemExit, match="must replicate seed 1"):
            m.stage_plan("v9", 200, npoint, 250, seed=2, co2=co2, design_kind=kind)
    assert not (tmp_path / "pilot-v9-s2" / "provenance.json").exists()
    # the matching replicate goes on to the selection (a pre-`co2_ppm` plan counts as 276.59)
    with pytest.raises(pytest.fail.Exception, match="got past the guard"):
        m.stage_plan("v9", 200, 30, 250, seed=2, co2=m.Co2(True, 276.59))
# ------------------------------------------------------------------------------------------------
# Real files
# ------------------------------------------------------------------------------------------------


def _v2() -> Path:
    return Path(str(paths()["scratch"]["corpus"])) / "pilot-v2-constco2"


@pytest.mark.needs_real_data
def test_the_nested_base_is_the_pilot_that_actually_ran() -> None:
    f = _v2() / "design.csv"
    if not f.is_file():
        pytest.skip("pilot-v2-constco2 is not on disk")
    pilot = _script("corpus_pilot")
    assert pilot._check_design_nests(nested_design(100), f) == 30


@pytest.mark.needs_real_data
def test_the_constant_co2_file_on_disk_is_what_the_default_writes(tmp_path: Path) -> None:
    on_disk = Path(str(paths()["scratch"]["root"])) / "forcing" / "pilot-v2-constco2"
    if not (on_disk / "co2_constant.txt").is_file():
        pytest.skip("pilot-v2-constco2 forcing is not on disk")
    cfg = _script("corpus_spinup_config")
    mine = cfg.write_constant_co2(tmp_path / "co2.txt")
    digest = [
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (mine, on_disk / "co2_constant.txt")
    ]
    assert digest[0] == digest[1]


# ------------------------------------------------------------------------------------------------
# corpus_convergence: the trend window inside constant CO2
# ------------------------------------------------------------------------------------------------


def test_a_constant_run_keeps_the_last_200_year_window() -> None:
    conv = _script("corpus_convergence")
    first, last, years = conv.constant_co2_rows([276.59] * 1000)
    assert (first, last, years) == (771, 970, 1000)  # rows 771..970 = smooth[-200:]


def test_the_ground_truths_ramp_moves_the_window_before_it(tmp_path: Path) -> None:
    """The ground truth's file: 276.59 from 1700 (and clamped before), rising from 1701."""
    cfg, conv = _script("corpus_spinup_config"), _script("corpus_convergence")
    f = tmp_path / "co2.txt"
    f.write_text(
        "1700  276.59\n"
        + "".join(f"{y}  {276.59 + (y - 1700) * 0.3:.2f}\n" for y in range(1701, 2023))
    )
    seen = cfg.co2_seen_by_model(f, range(1000, 2000))
    first, last, years = conv.constant_co2_rows([seen[y] for y in sorted(seen)])
    assert years == 701  # model years 1000-1700
    assert last + 30 == 701 and last - first + 1 == 200


def test_too_short_a_constant_stretch_is_refused() -> None:
    conv = _script("corpus_convergence")
    with pytest.raises(ValueError, match="constant for only 100"):
        conv.constant_co2_rows([1.0] * 100 + [2.0] * 900)
