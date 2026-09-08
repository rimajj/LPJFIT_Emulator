"""The perturbation design: the invariants that make a perturbed forcing file trustworthy.

Each test here is one of the physical-coherence rules in `PLAN.md` turned into something that can
FAIL. The two that matter most:

* `test_neutral_is_bitwise_identity` -- a neutral design point must be a structural no-op, because
  that is what makes the byte-identity check on a written file a real proof of the writer rather
  than a coincidence of two float paths.
* `test_relative_humidity_is_held_exactly_fixed` -- rule 2, under the MODEL's own definition of
  relative humidity. A version of this that used a textbook formula instead would pass while the
  model saw a drifting relative humidity.

The real-data tests write a subset `.clm` for one real cell out of the real 11.7 GB forcing files
and compare the bytes against the slice they came from. That is invariant 7 for the perturbed
writer; it is skipped when `/p` is not mounted and runs in CI on the cluster runner.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from vegemu.binfmt.clm import ClmReader
from vegemu.corpus.perturb import (
    AXIS_RANGE,
    MONTH_LEN,
    MONTH_START,
    NDAYYEAR,
    VARS,
    CellPattern,
    Perturbation,
    apply_perturbation,
    design_by_name,
    huss_at_fixed_rh,
    model_relative_humidity,
    pilot_design,
)
from vegemu.paths import paths

NYEAR = 30
HAINICH = 42490


def _writer() -> ModuleType:
    """Load `scripts/corpus_perturb_clm.py` as a module: it is a CLI, not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "corpus_perturb_clm",
        Path(__file__).resolve().parent.parent / "scripts" / "corpus_perturb_clm.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _monthly_totals(pr: np.ndarray) -> np.ndarray:
    return np.array(
        [
            pr[:, MONTH_START[m] : MONTH_START[m] + MONTH_LEN[m]].sum(axis=1).mean()
            for m in range(12)
        ]
    )


def _synthetic_base(seed: int = 7) -> dict[str, np.ndarray]:
    """A plausible mid-latitude cell: a seasonal cycle, intermittent rain, year-to-year spread."""
    rng = np.random.default_rng(seed)
    doy = np.arange(NDAYYEAR)
    season = np.cos(2 * np.pi * (doy - 195) / NDAYYEAR)
    tas = 9.0 - 10.0 * season + rng.normal(0, 2.5, (NYEAR, NDAYYEAR))
    tas += rng.normal(0, 0.8, (NYEAR, 1))  # interannual spread
    wet = rng.random((NYEAR, NDAYYEAR)) < 0.45
    pr = np.where(wet, rng.gamma(1.3, 3.5, (NYEAR, NDAYYEAR)), 0.0)
    rsds = np.maximum(115.0 - 75.0 * season + rng.normal(0, 20, (NYEAR, NDAYYEAR)), 1.0)
    lwnet = -48.0 + rng.normal(0, 8, (NYEAR, NDAYYEAR))
    huss = np.clip(0.0035 * np.exp(0.06 * tas) + rng.normal(0, 2e-4, (NYEAR, NDAYYEAR)), 1e-5, None)
    return {"tas": tas, "pr": pr, "rsds": rsds, "lwnet": lwnet, "huss": huss}


def _pattern(base: dict[str, np.ndarray], flat: bool = False) -> CellPattern:
    """A pattern with a real seasonal shape (winter-amplified warming), or a flat one."""
    tshape = np.ones(12)
    pshape = np.ones(12)
    if not flat:
        raw = np.array([1.6, 1.5, 1.3, 1.1, 0.8, 0.7, 0.7, 0.7, 0.8, 1.0, 1.3, 1.5])
        tshape = raw / np.average(raw, weights=np.asarray(MONTH_LEN, dtype=float))
        praw = np.array([1.4, 1.3, 1.1, 0.9, 0.6, 0.3, 0.2, 0.3, 0.7, 1.0, 1.2, 1.4])
        clim = _monthly_totals(base["pr"])
        pshape = praw / np.average(praw, weights=clim)
    return CellPattern(
        cell=1,
        dtemp_gcm=2.4,
        fprec_gcm=1.05,
        tshape=tshape,
        pshape=pshape,
        lwnet_per_k=np.full(12, 0.7),
        prclim=_monthly_totals(base["pr"]),
    )


# ------------------------------------------------------------------------------------------------
# The structural no-op
# ------------------------------------------------------------------------------------------------


def test_neutral_is_bitwise_identity() -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation.neutral())
    for var in VARS:
        assert out[var].tobytes() == base[var].tobytes(), f"{var} moved under a neutral point"


def test_neutral_flag_agrees_with_the_axes() -> None:
    assert Perturbation.neutral().is_neutral
    assert not Perturbation("x", dtemp=0.1).is_neutral
    assert not Perturbation("x", fprec=1.01).is_neutral
    assert not Perturbation("x", sprec=0.1).is_neutral
    assert not Perturbation("x", frad=1.01).is_neutral
    assert not Perturbation("x", fiav=1.01).is_neutral


# ------------------------------------------------------------------------------------------------
# Rule 2 — relative humidity is held fixed, under the model's own definition
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dtemp", [-2.0, 0.5, 4.0, 8.0])
def test_relative_humidity_is_held_exactly_fixed(dtemp: float) -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("t", dtemp=dtemp))
    before = model_relative_humidity(base["tas"], base["huss"])
    after = model_relative_humidity(out["tas"], out["huss"])
    assert np.abs(after - before).max() < 1e-12


def test_humidity_actually_moves_when_temperature_does() -> None:
    """The fixed-RH rule must not be satisfied by simply not touching humidity."""
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("t", dtemp=4.0))
    ratio = out["huss"].mean() / base["huss"].mean()
    assert ratio > 1.2, f"specific humidity only moved by x{ratio:.3f} under +4 K"


def test_fixed_rh_matches_clausius_clapeyron_scale() -> None:
    """About 6-7 % more moisture per kelvin is the physical expectation; check the order."""
    temp = np.array([[0.0, 10.0, 20.0, 30.0]])
    huss = np.full_like(temp, 0.006)
    per_k = huss_at_fixed_rh(huss, temp, temp + 1.0) / huss
    assert np.all((per_k > 1.05) & (per_k < 1.08))


# ------------------------------------------------------------------------------------------------
# The precipitation axes
# ------------------------------------------------------------------------------------------------


def test_dry_days_stay_dry_across_the_whole_design() -> None:
    """LPJmL-FIT reads the daily sequence, so the wet-day count is an invariant of the design."""
    base = _synthetic_base()
    pattern = _pattern(base)
    dry = base["pr"] == 0
    for pert in pilot_design(30):
        out = apply_perturbation(base, pattern, pert)
        assert np.all(out["pr"][dry] == 0.0), f"{pert.name} wetted a dry day"
        assert np.all(out["pr"] >= 0.0), f"{pert.name} produced negative precipitation"


@pytest.mark.parametrize("fprec", [0.5, 0.8, 1.3, 1.75])
def test_fprec_scales_the_annual_total_exactly_with_a_flat_shape(fprec: float) -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base, flat=True), Perturbation("p", fprec=fprec))
    got = out["pr"].sum(axis=1) / base["pr"].sum(axis=1)
    assert np.allclose(got, fprec, rtol=1e-12)


@pytest.mark.parametrize("fprec", [0.6, 1.4])
def test_fprec_scales_the_climatological_total_with_the_gcm_shape(fprec: float) -> None:
    """With a seasonal change shape the identity holds on the climatology, not year by year."""
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("p", fprec=fprec))
    got = out["pr"].sum() / base["pr"].sum()
    assert abs(got - fprec) < 1e-9


@pytest.mark.parametrize("sprec", [-0.5, 0.5, 1.0])
def test_sprec_preserves_the_annual_total_and_changes_the_seasonality(sprec: float) -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("s", sprec=sprec))
    assert abs(out["pr"].sum() / base["pr"].sum() - 1.0) < 1e-9
    before = _monthly_totals(base["pr"])
    after = _monthly_totals(out["pr"])
    cv_before = before.std() / before.mean()
    cv_after = after.std() / after.mean()
    if sprec > 0:
        assert cv_after > cv_before
    else:
        assert cv_after < cv_before


# ------------------------------------------------------------------------------------------------
# The temperature, radiation and variability axes
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dtemp", [-2.0, 2.0, 8.0])
def test_dtemp_delivers_exactly_that_annual_mean_warming(dtemp: float) -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("t", dtemp=dtemp))
    assert abs(float((out["tas"] - base["tas"]).mean()) - dtemp) < 1e-12


def test_dtemp_carries_the_seasonal_shape_not_a_uniform_shift() -> None:
    base = _synthetic_base()
    delta = apply_perturbation(base, _pattern(base), Perturbation("t", dtemp=4.0))["tas"] - base[
        "tas"
    ]
    monthly = np.array(
        [delta[:, MONTH_START[m] : MONTH_START[m] + MONTH_LEN[m]].mean() for m in range(12)]
    )
    assert monthly.max() - monthly.min() > 1.0, "the warming shape was flattened"


def test_lwnet_follows_the_applied_temperature_change() -> None:
    base = _synthetic_base()
    pattern = _pattern(base)
    out = apply_perturbation(base, pattern, Perturbation("t", dtemp=4.0))
    expected = base["lwnet"] + 0.7 * (out["tas"] - base["tas"])
    assert np.allclose(out["lwnet"], expected, rtol=0, atol=1e-12)


def test_frad_scales_shortwave_and_leaves_the_rest_alone() -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("r", frad=1.15))
    assert np.allclose(out["rsds"], base["rsds"] * 1.15)
    assert np.array_equal(out["tas"], base["tas"])
    assert np.array_equal(out["pr"], base["pr"])


@pytest.mark.parametrize("fiav", [0.5, 2.0])
def test_fiav_changes_interannual_spread_but_not_the_mean(fiav: float) -> None:
    base = _synthetic_base()
    out = apply_perturbation(base, _pattern(base), Perturbation("v", fiav=fiav))
    before = base["tas"].mean(axis=1)
    after = out["tas"].mean(axis=1)
    assert abs(after.mean() - before.mean()) < 1e-10
    assert abs(after.std() / before.std() - fiav) < 1e-10


# ------------------------------------------------------------------------------------------------
# The design itself
# ------------------------------------------------------------------------------------------------


def test_pilot_design_shape_and_ranges() -> None:
    design = pilot_design(30)
    assert len(design) == 30
    assert len({p.name for p in design}) == 30
    assert design[0].is_neutral and design[0].name == "control"
    assert sum(p.is_neutral for p in design) == 1
    for pert in design:
        for axis in AXIS_RANGE:
            lo, hi = AXIS_RANGE[axis]
            assert lo - 1e-9 <= getattr(pert, axis) <= hi + 1e-9, f"{pert.name}.{axis} out of range"


def test_pilot_design_is_reproducible_from_the_seed_alone() -> None:
    assert pilot_design(30) == pilot_design(30)
    assert pilot_design(30) != pilot_design(30, seed=1)


def test_design_spans_beyond_todays_envelope() -> None:
    """Rule 4: the design must reach warmer than end-of-century, or it cannot test extrapolation."""
    assert max(p.dtemp for p in pilot_design(30)) >= 6.0
    assert min(p.fprec for p in pilot_design(30)) <= 0.7


def test_design_by_name_round_trips() -> None:
    for pert in pilot_design(30):
        assert design_by_name(pert.name) == pert
    with pytest.raises(KeyError):
        design_by_name("no-such-point")


def test_axes_are_not_collinear_across_the_design() -> None:
    """The whole point is decollinearisation: no two axes may be near-perfectly correlated."""
    design = pilot_design(30)
    mat = np.array([[getattr(p, a) for a in AXIS_RANGE] for p in design])
    corr = np.corrcoef(mat, rowvar=False)
    off = corr[~np.eye(len(AXIS_RANGE), dtype=bool)]
    assert np.abs(off).max() < 0.6, f"two axes correlate at {np.abs(off).max():.2f} in the design"


# ------------------------------------------------------------------------------------------------
# Real files: the subset writer, and the byte identity that proves it
# ------------------------------------------------------------------------------------------------


def _have_inputs() -> bool:
    try:
        return Path(str(paths()["inputs"]["historical"]["tas"])).exists()
    except (KeyError, TypeError):
        return False


real_data = pytest.mark.skipif(not _have_inputs(), reason="needs the LPJmL-FIT inputs under /p")


@real_data
@pytest.mark.needs_real_data
def test_neutral_subset_clm_is_byte_identical_to_the_source_slice(tmp_path: Path) -> None:
    """Invariant 7 for the PERTURBED writer: a zero perturbation reproduces the source bytes."""
    record = _writer().build(range(HAINICH, HAINICH + 1), Perturbation.neutral(), tmp_path)
    for var in VARS:
        assert record["files"][var]["neutral_byte_identity"] == "PASS"
    # And the header a subset file must declare for the model to seek into it correctly.
    header = ClmReader(tmp_path / "tas_pert.clm").header
    assert (header.firstcell, header.ncell, header.nyear) == (HAINICH, 1, 30)
    assert header.firstyear == 1970


@real_data
@pytest.mark.needs_real_data
def test_perturbed_subset_clm_moves_and_stays_readable(tmp_path: Path) -> None:
    record = _writer().build(range(HAINICH, HAINICH + 1), Perturbation("w4", dtemp=4.0), tmp_path)
    before, after = record["diagnostics"]["tas_ann_c"]
    assert abs((after - before) - 4.0) < 1e-6
    rh_before, rh_after = record["diagnostics"]["model_rh_mean"]
    assert abs(rh_after - rh_before) < 1e-12
    wet_before, wet_after = record["diagnostics"]["wet_days_per_year"]
    assert wet_before == wet_after


# ------------------------------------------------------------------------------------------------
# The attribution arm — it must be impossible to reach it from the design
# ------------------------------------------------------------------------------------------------


def test_no_design_point_carries_the_hold_huss_flag() -> None:
    assert not any(p.hold_huss_diagnostic for p in pilot_design(30))


def test_hold_huss_arm_lets_relative_humidity_fall() -> None:
    base = _synthetic_base()
    pert = Perturbation("t4_nofixrh", dtemp=4.0, hold_huss_diagnostic=True)
    out = apply_perturbation(base, _pattern(base), pert)
    assert np.array_equal(out["huss"], base["huss"]), "the arm must leave humidity untouched"
    before = model_relative_humidity(base["tas"], base["huss"]).mean()
    after = model_relative_humidity(out["tas"], out["huss"]).mean()
    assert after < before * 0.9, "relative humidity should drop sharply when humidity is held"
    # ... and the temperature perturbation itself is unaffected by the flag.
    real = apply_perturbation(base, _pattern(base), Perturbation("t4", dtemp=4.0))
    assert np.array_equal(out["tas"], real["tas"])
    assert np.array_equal(out["lwnet"], real["lwnet"])


def test_hold_huss_arm_refuses_to_be_a_no_op() -> None:
    """With no warming the arm would be a duplicate of the real one, which is worse than useless."""
    base = _synthetic_base()
    pert = Perturbation("p_nofixrh", fprec=1.2, hold_huss_diagnostic=True)
    with pytest.raises(ValueError, match="not a diagnostic of anything"):
        apply_perturbation(base, _pattern(base), pert)


def test_hold_huss_arm_is_loud_in_its_own_description() -> None:
    pert = Perturbation("x", dtemp=4.0, hold_huss_diagnostic=True)
    assert "rule 2" in pert.describe()
    assert "NOT HELD FIXED" in pert.as_dict()["relative_humidity"]
