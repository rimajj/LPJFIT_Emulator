"""The cell rule of the constant-CO2 product (`vegemu.models.spinup_rule`), on synthetic cells.

What must hold:
  * the written climate buffer is exactly the stored protocol's replay STOPPED AT 1699 on the
    cell's own first 30 forcing years, at the albedo solved from the template's 1999 buffer --
    not the template's buffer, and not a replay to 1999;
  * the allowed types are the bioclimatic verdict of that same replay, and the report says which
    template types they removed;
  * the predicted shares are used when all seven are finite and not all on removed types, else the
    template's mix (restricted) is, and the report says which;
  * the litter follows predicted / template soil carbon (rule "soilc");
  * a template that the stored 1999 protocol did not write (header year or RNG state) is refused,
    and so are `--synth-kwargs` keys the rule sets itself.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from vegemu.binfmt.restart import (
    PFT_TREE_BYTES,
    GenericHeader,
    RestartHeader,
    RestartReader,
    RestartWriter,
    trees_of,
    write_cell,
)
from vegemu.corpus.state import summarise_cell
from vegemu.corpus.vegc import cell_vegc
from vegemu.models import climbuf as cb
from vegemu.models import spinup_rule as sr
from vegemu.models.synth import build_donor_pool

from .test_restart_roundtrip import _synth_record
from .test_synth_admissibility import _stem

NCELL = 3
NYEAR = 99
STORED_SEED = (10901, 14779, 51459)
FRAC = 0.9
AETP = 4.5


def _forcing(k: int) -> cb.Forcing:
    """Cell k: a seasonal cycle, distinct per year and per cell, at 45 N."""
    day = np.arange(cb.NDAYYEAR)
    base = 6.0 + 3.0 * k + 12.0 * np.sin(2 * np.pi * (day - 100) / cb.NDAYYEAR)
    temp = base[None, :] + 0.05 * np.arange(NYEAR, dtype=np.float64)[:, None]
    return cb.Forcing(
        temp=temp,
        prec=np.full((NYEAR, cb.NDAYYEAR), 1.8 + 0.1 * k),
        swdown=np.full((NYEAR, cb.NDAYYEAR), 160.0) + 60.0 * np.sin(np.pi * day / 365)[None, :],
        lwnet=np.full((NYEAR, cb.NDAYYEAR), -55.0),
        lat=45.0,
        firstyear=1901,
    )


def _record(k: int) -> tuple[bytes, Any]:
    rec, lay = _synth_record(k, npatch=2, ntree=0, ngrass=0, litter_n=3, buf_n=3, nsapling=1)
    rng = np.random.default_rng(k)
    for patch in rec["stands"][0]["patches"]:
        stems = [
            _stem(int(t), float(h), 2.0e5 + 1e4 * int(t), litter=i % 3)
            for i, (t, h) in enumerate(
                zip(rng.choice([1, 3], size=6), rng.uniform(1.0, 20.0, size=6), strict=True)
            )
        ]
        patch["pftlist"] = {
            "raw": struct.pack("<i", len(stems))
            + b"".join(s.view(np.uint8).reshape(PFT_TREE_BYTES).tobytes() for s in stems)
        }
        pool = np.array(patch["soil"]["pool"], dtype=np.float64, copy=True)
        pool[:, 0] = pool[:, 2] = 4000.0 / (2 * pool.shape[0])
        pool[:, 1] = pool[:, 3] = 10.0
        patch["soil"]["pool"] = pool
        lit = dict(patch["soil"]["litter"])
        lit["items"] = np.abs(np.asarray(lit["items"], dtype=np.float64)) % 50.0
        patch["soil"]["litter"] = lit
    rec["stands"][0]["frac"] = FRAC
    # The template's buffer is what the STORED run leaves at 1999, at a known albedo.
    rec["climbuf"], _ = cb.climate_buffer_from_forcing(
        _forcing(k), protocol=cb.STORED_SPINUP, albedo=0.21, aetp_mean=AETP, stand_frac=FRAC
    )
    return write_cell(rec, lay), lay


def _write(dest: Path, *, year: int = 1999, seed: tuple[int, int, int] = STORED_SEED) -> Path:
    generic = GenericHeader(1, year, 1, 0, NCELL, 22, 0.5, 1.0, 0.5, 4)
    head = RestartHeader(False, False, 0, False, False, seed, True)
    with RestartWriter(dest, generic, head, ncell=NCELL) as w:
        for k in range(NCELL):
            w.append(_record(k)[0])
    return dest


def _block() -> sr.BlockForcing:
    fs = [_forcing(k) for k in range(NCELL)]
    return sr.BlockForcing(
        first_cell=0,
        firstyear=1901,
        temp=np.stack([f.temp for f in fs]),
        prec=np.stack([f.prec for f in fs]),
        swdown=np.stack([f.swdown for f in fs]),
        lwnet=np.stack([f.lwnet for f in fs]),
        lat=np.full(NCELL, 45.0),
    )


def _prediction(**extra: float) -> dict[str, float]:
    pred = {
        "stems_per_patch": 5.0,
        "height_p10": 3.0,
        "height_p50": 8.0,
        "height_p90": 15.0,
        "wooddens_p10": 2.0e5,
        "wooddens_p50": 2.1e5,
        "wooddens_p90": 2.3e5,
        "soilc": 6000.0,
        "litterc": 1.0,
    }
    pred.update({f"pft_frac_{i}": 0.0 for i in range(7)})
    pred.update(pft_frac_1=0.25, pft_frac_3=0.75)
    pred.update(extra)
    return pred


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _write(tmp_path_factory.mktemp("spinrule") / "restart_1999.lpj")


def _run(template: Path, cell: int, pred: dict[str, float]) -> tuple[dict[str, Any], Any]:
    reader = RestartReader(template)
    rule = sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block())
    pool = build_donor_pool(RestartReader(template), [c for c in range(NCELL) if c != cell])
    with reader:
        tmpl = reader.read(cell)
    return rule(tmpl, pred, pool, reader.layout, cell=cell, seed=7), tmpl


def test_the_buffer_is_the_1699_replay_at_the_templates_own_albedo(template: Path) -> None:
    (rec, rep), tmpl = _run(template, 1, _prediction())
    f = _forcing(1)
    alb = cb.effective_albedo(tmpl["climbuf"], f, protocol=cb.STORED_SPINUP, stand_frac=FRAC)
    assert np.allclose(alb, 0.21, atol=1e-6)
    want, trace = cb.climate_buffer_from_forcing(
        cb.Forcing(f.temp[:30], f.prec[:30], f.swdown[:30], f.lwnet[:30], f.lat, 1901),
        protocol=cb.STORED_SPINUP.until(1699),
        albedo=alb,
        aetp_mean=AETP,
        stand_frac=FRAC,
    )
    err = cb.compare_climbuf(rec["climbuf"], want)
    assert all(v["max_abs"] == 0.0 for v in err.values()), err
    # ...and it is NOT the template's 1999 buffer: the ordered 1901-1999 years moved it.
    moved = cb.compare_climbuf(rec["climbuf"], tmpl["climbuf"])
    assert moved["mtemp20"]["max_abs"] > 0.0
    assert rep.climbuf_source == "forcing"
    assert rep.climbuf_seed_after == ",".join(map(str, trace.seed_after))


def test_allowed_types_and_the_shares_come_from_the_rule(template: Path) -> None:
    (_rec, rep), _tmpl = _run(template, 0, _prediction())
    assert rep.composition == "predicted" and rep.shares_from == "prediction"
    allowed = tuple(int(t) for t in rep.allowed.split(",") if t)
    assert allowed == rep.type_admissible
    assert set(rep.type_achieved) <= set(allowed)
    assert rep.template_types == "1,3"
    assert rep.template_types_removed == len({1, 3} - set(allowed))


def test_the_litter_follows_predicted_over_template_soil_carbon(template: Path) -> None:
    (_rec, rep), tmpl = _run(template, 2, _prediction())
    reader = RestartReader(template)
    state = summarise_cell(tmpl, 2, reader.layout)
    assert rep.litter_target == pytest.approx(state["litterc"] * 6000.0 / state["soilc"])
    assert sr.litter_target("none", state, _prediction()) is None
    assert sr.litter_target("predicted", state, _prediction()) == 1.0
    assert sr.litter_target("soilc", {**state, "soilc": 0.0}, _prediction()) is None


def test_shares_fall_back_to_the_template_mix_when_the_prediction_cannot_be_used() -> None:
    nan = _prediction(pft_frac_2=float("nan"))
    assert sr.predicted_shares(nan, (1, 3)) == (None, "no-prediction")
    only_removed = _prediction(pft_frac_1=0.0, pft_frac_3=0.0, pft_frac_0=1.0)
    assert sr.predicted_shares(only_removed, (1, 3)) == (None, "all-on-removed-types")
    shares, why = sr.predicted_shares(_prediction(), (3,))
    assert why == "prediction" and shares is not None and shares[3] == 0.75


def test_a_template_the_stored_protocol_did_not_write_is_refused(tmp_path: Path) -> None:
    wrong_seed = _write(tmp_path / "seed.lpj", seed=(1, 2, 3))
    with pytest.raises(ValueError, match="stored spin-up's protocol"):
        sr.SpinupRule(wrong_seed, 0, NCELL, donors=None, forcing=_block())
    wrong_year = _write(tmp_path / "year.lpj", year=2019)
    with pytest.raises(ValueError, match="stored spin-up's protocol"):
        sr.SpinupRule(wrong_year, 0, NCELL, donors=None, forcing=_block())


def test_the_rule_owns_its_options(template: Path) -> None:
    for key in ("climbuf", "allowed_types", "type_shares", "rescale_litter", "cell"):
        with pytest.raises(ValueError, match="rule sets"):
            sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block(), **{key: None})
    with pytest.raises(ValueError, match="litter rule"):
        sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block(), litter_rule="x")
    short = _block()
    short.temp = short.temp[:, :30]
    with pytest.raises(ValueError, match="rule needs"):
        sr.SpinupRule(template, 0, NCELL, donors=None, forcing=short)


def _run_matched(
    template: Path, cell: int, pred: dict[str, float], **opts: Any
) -> tuple[dict[str, Any], Any]:
    reader = RestartReader(template)
    rule = sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block(), match_vegc=True, **opts)
    pool = build_donor_pool(RestartReader(template), [c for c in range(NCELL) if c != cell])
    with reader:
        tmpl = reader.read(cell)
    return rule(tmpl, pred, pool, reader.layout, cell=cell, seed=7)


def test_match_vegc_off_changes_nothing(template: Path) -> None:
    (plain, _rep), _ = _run(template, 0, _prediction())
    (with_target, rep2), _ = _run(template, 0, _prediction(vegc_target=1.0))
    assert write_cell(plain, RestartReader(template).layout) == write_cell(
        with_target, RestartReader(template).layout
    )
    assert rep2.vegc_why == "" and math.isnan(rep2.vegc_target)
    rule = sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block())
    assert "match_vegc" not in rule.describe()


def test_match_vegc_moves_the_stem_count_toward_the_target(template: Path) -> None:
    (base, _), _ = _run(template, 1, _prediction())
    first = cell_vegc(base)["total"]
    for scale in (2.0, 0.5):
        want = cell_vegc(base)["grass"] + scale * cell_vegc(base)["tree"]
        rec, rep = _run_matched(template, 1, _prediction(vegc_target=want), vegc_tol=0.05)
        got = cell_vegc(rec)["total"]
        assert rep.vegc_first == pytest.approx(first)
        assert rep.vegc_written == pytest.approx(got)
        assert abs(got - want) < abs(first - want), (scale, first, got, want)
        assert rep.vegc_passes >= 1
        assert (rep.vegc_stems_factor > 1) == (scale > 1)


def test_match_vegc_edges(template: Path) -> None:
    (base, _), _ = _run(template, 1, _prediction())
    grass = cell_vegc(base)["grass"]
    rec, rep = _run_matched(template, 1, _prediction(vegc_target=0.5 * grass))
    assert rep.vegc_why == "below-grass" and cell_vegc(rec)["tree"] == 0.0
    _rec, rep = _run_matched(template, 1, _prediction())
    assert rep.vegc_why == "no-target" and rep.vegc_passes == 0
    _rec, rep = _run_matched(template, 1, _prediction(vegc_target=1e9), vegc_max_factor=1.5)
    assert rep.vegc_why == "capped" and rep.vegc_stems_factor == pytest.approx(1.5)
    _rec, rep = _run_matched(template, 1, _prediction(stems_per_patch=0.0, vegc_target=1e4))
    assert rep.vegc_why == "treeless-prediction" and rep.vegc_passes == 0
    with pytest.raises(ValueError, match="match_vegc needs"):
        sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block(), vegc_passes=0)


def test_reset_counters_zeroes_the_counter_and_nothing_else(template: Path) -> None:
    (rec, _rep), _ = _run(template, 1, _prediction())
    lay = RestartReader(template).layout
    before = write_cell(rec, lay)
    at = sr._COUNTER_BYTE
    patch = rec["stands"][0]["patches"][0]
    raw = bytearray(patch["pftlist"]["raw"])
    for off in patch["pftlist"]["tree_offsets"][:2]:
        raw[int(off) + at : int(off) + at + 4] = (3).to_bytes(4, "little")
    patch["pftlist"] = {**patch["pftlist"], "raw": bytes(raw)}
    assert trees_of(patch["pftlist"])["bm_inc_counter"][:2].tolist() == [3, 3]
    assert sr.reset_counters(rec) == 2
    assert write_cell(rec, lay) == before
    rule = sr.SpinupRule(template, 0, NCELL, donors=None, forcing=_block(), reset_counters=True)
    assert rule.describe()["reset_counters"] is True
