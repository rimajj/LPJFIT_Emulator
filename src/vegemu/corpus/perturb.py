"""The delta-change climate perturbation design — the thing that makes the corpus identifiable.

WHY THIS EXISTS. Every existing ground-truth leg holds exactly ONE climate per location, so climate
and geography are collinear and a warming response is not separately identified
(`MEMORY.md:ident-limit`; the kill test failed on precisely this). The fix is to spin the SAME cell
up under MANY climates. This module is the design of those many climates.

THE FIVE AXES (`PLAN.md`), each an independent scalar coefficient:

    dtemp   K          annual-mean temperature change
    fprec   x          annual precipitation multiplier
    sprec   -          seasonality amplification of precipitation, annual total preserved
    frad    x          shortwave multiplier
    fiav    x          interannual-variability multiplier

Two more fields MOVE but are NOT axes, because they are responses rather than forcings:

    lwnet              tied to the applied temperature change at a per-cell, per-month sensitivity
                       (W/m2/K) read off the climate model itself
    huss               set so the model's OWN relative humidity is held EXACTLY fixed

THE PHYSICAL-COHERENCE RULES ARE NOT OPTIONAL (`PLAN.md` §Perturbation design rules)

1. Directions are calibrated on real climate-model deltas, so a perturbed climate lies on the
   manifold a climate model actually produces. The calibration contrast is late-minus-early WITHIN
   ONE SCENARIO LEG of MPI-ESM1-2-HR (2071-2100 minus 2015-2044), never scenario-minus-historical:
   the historical forcing is observational (GSWP3-W5E5) and the scenario legs are a GCM, so that
   difference would be a model bias, not a climate change.
2. Relative humidity is held FIXED when temperature is scaled. Adding 6 K while leaving specific
   humidity alone produces impossible relative humidity. And it is held fixed under the MODEL'S OWN
   definition of relative humidity -- the Bolton form in `src/spitfire/getvpd.c:38`, at 1013.25 hPa,
   which is what LPJmL-FIT's tree water stress actually reads (`src/tree/waterstress_tree.c:36`) --
   not under some other textbook formula that would leave a residual RH drift behind.
3. Only the coefficients are free; the SHAPES (which month warms most, which month gets the extra
   rain) come from the climate model, per cell.
4. The ranges deliberately span beyond today's envelope, where space-for-time is known to be
   sign-wrong.
5. CO2 is untouched and is not an axis. The emulator does not see CO2 and must not respond to it
   (`MEMORY.md:co2-closed`). No CO2 file is written by this module at all.

⚠ A NEUTRAL PERTURBATION IS A STRUCTURAL NO-OP, NOT AN APPROXIMATE ONE. Every axis is guarded by an
explicit `if`, so `Perturbation.neutral()` returns the base arrays unchanged bit-for-bit. That is
what makes "write a perturbed file with zero perturbation and byte-compare it against the slice of
the source file it came from" a real round-trip proof of the writer (invariant 7) rather than a
proof that two float paths happen to agree today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import ClmReader

NDAYYEAR = 365
NMONTH = 12
MONTH_LEN: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
MONTH_START: tuple[int, ...] = tuple(int(x) for x in np.cumsum((0, *MONTH_LEN[:-1])))
# Day-of-year index -> 0-based month. Precomputed because it is used on every array in every axis.
MONTH_OF_DAY: npt.NDArray[np.int64] = np.repeat(np.arange(NMONTH), MONTH_LEN)

VARS: tuple[str, ...] = ("tas", "pr", "rsds", "lwnet", "huss")

# --- calibration guards ---------------------------------------------------------------------
# Below this much warming in the calibration contrast, a per-month RATIO is dividing by noise, so
# the shape is replaced by "flat" rather than by an amplified artefact.
MIN_CALIB_DTEMP_K = 0.5
# Same for precipitation: below a 2 % annual change the per-month fractional change carries no
# usable shape.
MIN_CALIB_FPREC = 0.02
# A single month may not carry more than this multiple of the annual mean change. Without it one
# dry desert month with a 900 % precipitation ratio would set the whole cell's shape.
SHAPE_CLIP = (-1.0, 3.0)
# Net longwave sensitivity, W/m2 per K. The climate model's own value is under ~1 W/m2/K at four of
# five biome test cells and +3.2 at the fifth; anything beyond this range is a ratio of two small
# numbers, not a physical sensitivity.
LWNET_PER_K_CLIP = 3.0

# The model's own saturation-vapour-pressure form, from getvpd.c:38. Keep the literals here rather
# than importing a "nicer" formula: the point is that OUR relative humidity is the model's.
_BOLTON_A = 17.67
_BOLTON_B = 29.65
_T0_K = 273.16
# 0.263 * 1013.25 hPa, i.e. p/(0.622*6.112) with p at sea level. getvpd.c writes it as a product.
_RH_COEFF = 0.263 * 1013.25


def model_esat_factor(temp_c: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """`exp(17.67*T/(T+273.16-29.65))`: the model's saturation term, up to a constant.

    Only ratios of this are ever used, so the constant 6.112 hPa cancels and is left out.
    """
    return np.exp(_BOLTON_A * temp_c / (temp_c + _T0_K - _BOLTON_B))


def model_relative_humidity(
    temp_c: npt.NDArray[np.float64], huss: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Relative humidity (0-1) exactly as LPJmL-FIT computes it in `getvpd.c`, before its `>1` clip.

    Reproduced rather than approximated because it is the quantity rule 2 holds fixed. If this
    drifts from the C, the fixed-RH guarantee becomes a claim about a formula nobody uses.
    """
    return _RH_COEFF * huss / model_esat_factor(temp_c)


def huss_at_fixed_rh(
    huss: npt.NDArray[np.float64],
    temp_c: npt.NDArray[np.float64],
    temp_c_new: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Specific humidity that leaves the model's relative humidity unchanged at the new temperature.

    RH = k*q/esat(T), so holding RH fixed is exactly q' = q * esat(T')/esat(T). Nothing about the
    constant k, the pressure, or the `>1` clip enters, which is why this is exact rather than a
    linearisation.
    """
    return huss * (model_esat_factor(temp_c_new) / model_esat_factor(temp_c))


@dataclass(frozen=True)
class Perturbation:
    """One point of the design: five coefficients and a name that goes into every filename."""

    name: str
    dtemp: float = 0.0
    fprec: float = 1.0
    sprec: float = 0.0
    frad: float = 1.0
    fiav: float = 1.0
    hold_huss_diagnostic: bool = False
    """⚠ DELIBERATELY BREAKS RULE 2. Leaves specific humidity at its baseline value, so warming
    raises the temperature WITHOUT raising the vapour-pressure deficit -- relative humidity falls
    instead of staying put. Its only purpose is attribution: run it beside the real arm and the
    difference is how much of a response the fixed-humidity rule is responsible for. **No point of
    any design carries it**, `pilot_design` refuses to emit one, and every file it writes says so
    in its own provenance. Never use it to generate corpus rows."""

    @classmethod
    def neutral(cls, name: str = "control") -> Perturbation:
        return cls(name)

    @property
    def is_neutral(self) -> bool:
        """True when every axis is its identity value, so `apply` is a structural no-op."""
        return (
            self.dtemp == 0.0
            and self.fprec == 1.0
            and self.sprec == 0.0
            and self.frad == 1.0
            and self.fiav == 1.0
        )

    def describe(self) -> str:
        """The basis line: a perturbed number must never be quoted without its coefficients."""
        warn = "  ⚠ HOLD-HUSS DIAGNOSTIC, rule 2 disabled" if self.hold_huss_diagnostic else ""
        return (
            f"{self.name}: dtemp={self.dtemp:+.2f}K fprec=x{self.fprec:.3f} "
            f"sprec={self.sprec:+.2f} frad=x{self.frad:.3f} fiav=x{self.fiav:.2f}{warn}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtemp_k": self.dtemp,
            "fprec": self.fprec,
            "sprec": self.sprec,
            "frad": self.frad,
            "fiav": self.fiav,
            "co2": "untouched; not an axis (MEMORY.md:co2-closed)",
            "relative_humidity": (
                "NOT HELD FIXED -- hold-huss diagnostic arm, rule 2 deliberately disabled; "
                "not corpus-eligible"
                if self.hold_huss_diagnostic
                else "held fixed under the model's own definition (getvpd.c:38)"
            ),
        }


@dataclass(frozen=True)
class CellPattern:
    """Per-cell perturbation SHAPES, calibrated on the climate model. Not the amplitudes.

    `tshape` and `pshape` are normalised, so multiplying them by a coefficient gives a change of
    exactly that coefficient's annual size while keeping the climate model's seasonal structure.
    """

    cell: int
    dtemp_gcm: float
    """The climate model's own annual-mean warming over the calibration contrast, K."""
    fprec_gcm: float
    """The climate model's own annual precipitation factor over the same contrast."""
    tshape: npt.NDArray[np.float64] = field(repr=False)
    """(12,) monthly warming shape, day-weighted mean 1; `dtemp * tshape[m]` is a month's change."""
    pshape: npt.NDArray[np.float64] = field(repr=False)
    """(12,) monthly precipitation-change weight, precipitation-weighted mean 1."""
    lwnet_per_k: npt.NDArray[np.float64] = field(repr=False)
    """(12,) net-longwave response to the APPLIED temperature change, W/m2/K."""
    prclim: npt.NDArray[np.float64] = field(repr=False)
    """(12,) baseline monthly precipitation climatology, mm/month. Drives the seasonality axis."""
    flags: tuple[str, ...] = ()
    """Which guards fired, so a flat shape is visible in the provenance rather than silent."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell": self.cell,
            "dtemp_gcm_k": round(self.dtemp_gcm, 4),
            "fprec_gcm": round(self.fprec_gcm, 4),
            "tshape": [round(float(x), 4) for x in self.tshape],
            "pshape": [round(float(x), 4) for x in self.pshape],
            "lwnet_per_k": [round(float(x), 4) for x in self.lwnet_per_k],
            "flags": list(self.flags),
        }


def _monthly(daily: npt.NDArray[np.float64], reduce_sum: bool) -> npt.NDArray[np.float64]:
    """(nyear, 365) -> (12,), averaged over years; summed or averaged within each month."""
    out = np.empty(NMONTH, dtype=np.float64)
    for m in range(NMONTH):
        block = daily[:, MONTH_START[m] : MONTH_START[m] + MONTH_LEN[m]]
        out[m] = block.sum(axis=1).mean() if reduce_sum else block.mean()
    return out


def _day_weighted_mean(monthly: npt.NDArray[np.float64]) -> float:
    return float(np.average(monthly, weights=np.asarray(MONTH_LEN, dtype=np.float64)))


def calibrate_cell(
    cell: int,
    base_pr_monthly: npt.NDArray[np.float64],
    calib_files: dict[str, str],
    early: tuple[int, int] = (2015, 2044),
    late: tuple[int, int] = (2071, 2100),
) -> CellPattern:
    """Read one cell's calibration contrast out of a scenario leg and reduce it to shapes.

    The contrast is late-minus-early WITHIN ONE LEG, so both terms come from the same climate model
    and the same file, and the model's bias against the observational baseline cancels exactly.

    Cost is 4 variables x 60 years x one seek each, i.e. small enough to run per cell rather than
    over a precomputed global field. `tas`, `pr`, `lwnet` are read; `rsds` is not, because the
    shortwave axis is free rather than tied (see the module docstring).
    """
    flags: list[str] = []
    got: dict[str, tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}
    for var in ("tas", "pr", "lwnet"):
        reader = ClmReader(calib_files[var])
        with reader:
            got[var] = (
                reader.cell_years(cell, early[0], early[1]),
                reader.cell_years(cell, late[0], late[1]),
            )

    t_early, t_late = (_monthly(a, reduce_sum=False) for a in got["tas"])
    dtemp_m = t_late - t_early
    dtemp_ann = _day_weighted_mean(dtemp_m)
    tshape: npt.NDArray[np.float64] = np.ones(NMONTH, dtype=np.float64)
    if abs(dtemp_ann) < MIN_CALIB_DTEMP_K:
        flags.append(f"tshape_flat: |dtemp_gcm|={abs(dtemp_ann):.2f}K < {MIN_CALIB_DTEMP_K}K")
    else:
        clipped = np.clip(dtemp_m / dtemp_ann, SHAPE_CLIP[0], SHAPE_CLIP[1])
        tshape = np.asarray(clipped / _day_weighted_mean(clipped), dtype=np.float64)

    p_early, p_late = (_monthly(a, reduce_sum=True) for a in got["pr"])
    ann_early, ann_late = float(p_early.sum()), float(p_late.sum())
    fprec_gcm = ann_late / ann_early if ann_early > 0 else 1.0
    frac_ann = fprec_gcm - 1.0
    pshape: npt.NDArray[np.float64] = np.ones(NMONTH, dtype=np.float64)
    if abs(frac_ann) < MIN_CALIB_FPREC or float(base_pr_monthly.sum()) <= 0.0:
        flags.append(f"pshape_flat: |fprec_gcm-1|={abs(frac_ann):.3f} < {MIN_CALIB_FPREC}")
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            frac_m = np.where(p_early > 0, (p_late - p_early) / np.maximum(p_early, 1e-12), 0.0)
        clipped = np.clip(frac_m / frac_ann, SHAPE_CLIP[0], SHAPE_CLIP[1])
        # Precipitation-weighted so that pr * (1 + (fprec-1)*pshape) has annual total exactly
        # fprec x the baseline total. An unweighted normalisation would silently change the total.
        norm = float(np.average(clipped, weights=base_pr_monthly))
        if abs(norm) > 1e-9:
            pshape = np.asarray(clipped / norm, dtype=np.float64)
        else:
            flags.append("pshape_flat: the precipitation-weighted normaliser came out zero")

    l_early, l_late = (_monthly(a, reduce_sum=False) for a in got["lwnet"])
    lwnet_per_k: npt.NDArray[np.float64] = np.zeros(NMONTH, dtype=np.float64)
    if abs(dtemp_ann) < MIN_CALIB_DTEMP_K:
        flags.append("lwnet_tie_off: calibration warming too small to divide by")
    else:
        lwnet_per_k = np.asarray(
            np.clip((l_late - l_early) / dtemp_ann, -LWNET_PER_K_CLIP, LWNET_PER_K_CLIP),
            dtype=np.float64,
        )

    return CellPattern(
        cell=cell,
        dtemp_gcm=dtemp_ann,
        fprec_gcm=fprec_gcm,
        tshape=tshape,
        pshape=pshape,
        lwnet_per_k=lwnet_per_k,
        prclim=base_pr_monthly,
        flags=tuple(flags),
    )


def _annual_anomaly(daily: npt.NDArray[np.float64], reduce_sum: bool) -> npt.NDArray[np.float64]:
    """(nyear,) departure of each year from the block mean; a total for sums, a mean otherwise.

    Annotated rather than returned directly: `ndarray.sum(axis=...)` is typed `Any` in the numpy
    stubs, so returning the expression straight out silently defeats the declared return type.
    """
    per_year = daily.sum(axis=1) if reduce_sum else daily.mean(axis=1)
    out: npt.NDArray[np.float64] = per_year - per_year.mean()
    return out


def _iav_factor(
    daily: npt.NDArray[np.float64], k: float, reduce_sum: bool
) -> npt.NDArray[np.float64]:
    """(nyear, 1) multiplier that scales a non-negative field's year-to-year departures by `1+k`.

    Multiplicative rather than additive so a dry year cannot be driven below zero, and so a dry DAY
    stays exactly dry -- the wet-day count is an invariant of the whole design.
    """
    per_year = daily.sum(axis=1) if reduce_sum else daily.mean(axis=1)
    mean = float(per_year.mean())
    rel = (per_year - mean) / mean if mean > 0 else np.zeros_like(per_year)
    # Annotated for the same reason as `_annual_anomaly`: a numpy ufunc's `__call__` is typed `Any`.
    out: npt.NDArray[np.float64] = np.maximum(1.0 + k * rel, 0.0)[:, None]
    return out


def apply_perturbation(
    base: dict[str, npt.NDArray[np.float64]],
    pattern: CellPattern,
    pert: Perturbation,
) -> dict[str, npt.NDArray[np.float64]]:
    """Perturb one cell's 30-year daily forcing block. Each input is (nyear, 365) float64.

    Order matters and is fixed: interannual variability first (it is a property of the baseline
    climate), then the mean-state axes. `lwnet` and `huss` are computed LAST, from the temperature
    change that actually came out, so they can never disagree with it.

    Precipitation is only ever multiplied, so a dry day stays exactly dry and the wet-day count is
    an invariant of the whole design. That matters: LPJmL-FIT's fire and phenology read the daily
    sequence, not a monthly total.
    """
    for var in VARS:
        if base[var].shape[1] != NDAYYEAR:
            raise ValueError(f"{var}: expected 365 days per year, got {base[var].shape[1]}")
    if pert.is_neutral:
        return {var: base[var].copy() for var in VARS}

    tas = base["tas"].copy()
    pr = base["pr"].copy()
    rsds = base["rsds"].copy()

    # --- axis 5: interannual variability -----------------------------------------------------
    # Scales each YEAR's departure from the 30-year block, leaving the within-year weather alone.
    # Additive for temperature; multiplicative for the two non-negative fields, so a year cannot be
    # driven below zero and a dry day stays dry.
    if pert.fiav != 1.0:
        k = pert.fiav - 1.0
        tas = tas + k * _annual_anomaly(base["tas"], reduce_sum=False)[:, None]
        pr = pr * _iav_factor(base["pr"], k, reduce_sum=True)
        rsds = rsds * _iav_factor(base["rsds"], k, reduce_sum=False)

    # --- axis 1: temperature, with the climate model's seasonal warming shape ------------------
    if pert.dtemp != 0.0:
        tas = tas + pert.dtemp * pattern.tshape[MONTH_OF_DAY][None, :]

    # --- axis 2: annual precipitation, with the climate model's seasonal change shape ----------
    if pert.fprec != 1.0:
        mult = np.maximum(1.0 + (pert.fprec - 1.0) * pattern.pshape, 0.0)
        pr = pr * mult[MONTH_OF_DAY][None, :]

    # --- axis 3: precipitation seasonality, at a preserved annual total ------------------------
    # Amplifies each month's departure from the cell's own flat-year mean. The renormalisation is a
    # single scalar over the block, so the CLIMATOLOGICAL annual total is preserved exactly and
    # individual years still differ from one another.
    if pert.sprec != 0.0:
        clim = pattern.prclim
        flat = clim.mean()
        if flat > 0:
            season = np.maximum(1.0 + pert.sprec * (clim / flat - 1.0), 0.0)
            before = float(clim.sum())
            after = float((clim * season).sum())
            if after > 0:
                season = season * (before / after)
            pr = pr * season[MONTH_OF_DAY][None, :]

    # --- axis 4: shortwave ---------------------------------------------------------------------
    if pert.frad != 1.0:
        rsds = np.maximum(rsds * pert.frad, 0.0)

    # --- responses, from the temperature change that actually came out -------------------------
    dtas = tas - base["tas"]
    lwnet = base["lwnet"] + pattern.lwnet_per_k[MONTH_OF_DAY][None, :] * dtas
    huss = (
        base["huss"].copy()
        if pert.hold_huss_diagnostic
        else huss_at_fixed_rh(base["huss"], base["tas"], tas)
    )

    out = {"tas": tas, "pr": pr, "rsds": rsds, "lwnet": lwnet, "huss": huss}
    _assert_physical(out, base, hold_huss=pert.hold_huss_diagnostic)
    return out


def _assert_physical(
    out: dict[str, npt.NDArray[np.float64]],
    base: dict[str, npt.NDArray[np.float64]],
    hold_huss: bool = False,
) -> None:
    """Refuse to emit a forcing block the model would either reject or silently mis-read.

    These are cheap and they fire before a 1000-year spin-up burns, not after. The relative-humidity
    check is the load-bearing one: it is the executable form of rule 2.
    """
    for var, arr in out.items():
        if not np.isfinite(arr).all():
            raise ValueError(f"{var}: non-finite values after perturbation")
    if (out["pr"] < 0).any():
        raise ValueError("pr: negative precipitation after perturbation")
    if (out["rsds"] < 0).any():
        raise ValueError("rsds: negative shortwave after perturbation")
    if bool((out["huss"] <= 0).any()) and bool((base["huss"] > 0).any()):
        raise ValueError("huss: non-positive specific humidity after perturbation")
    tmin, tmax = float(out["tas"].min()), float(out["tas"].max())
    if tmin <= -95.0 or tmax >= 80.0:
        raise ValueError(f"tas: {tmin:.1f}..{tmax:.1f} C is outside anything physical")
    rh_before = model_relative_humidity(base["tas"], base["huss"])
    rh_after = model_relative_humidity(out["tas"], out["huss"])
    drift = float(np.abs(rh_after - rh_before).max())
    if hold_huss:
        # The diagnostic arm exists precisely to move relative humidity. If it did not move, the
        # arm is a duplicate of the real one and would be reported as a null difference.
        if drift < 1e-12:
            raise ValueError(
                "the hold-huss diagnostic arm left relative humidity unchanged, so it is not a "
                "diagnostic of anything. Was the temperature perturbation zero?"
            )
        return
    if drift > 1e-9:
        raise ValueError(
            f"relative humidity moved by {drift:.3e} under the perturbation. Rule 2 says it is "
            "held fixed; a drift here means the humidity was scaled against a different "
            "temperature than the one written."
        )


# ------------------------------------------------------------------------------------------------
# The design: a full-factorial core plus a Latin hypercube (PLAN.md rule 3).
# ------------------------------------------------------------------------------------------------

# Deliberately wider than today's envelope (rule 4). The upper temperature bound is roughly three
# times the climate model's own 2015-2044 -> 2071-2100 warming at the biome test cells
# (+2.0..+2.7 K) and comfortably past end-of-century ssp370, because space-for-time is known to be
# sign-wrong exactly where we cannot interpolate.
AXIS_RANGE: dict[str, tuple[float, float]] = {
    "dtemp": (-2.0, 8.0),
    "fprec": (0.50, 1.75),
    "sprec": (-0.5, 1.0),
    "frad": (0.85, 1.15),
    "fiav": (0.5, 2.0),
}

# The interpretable core: temperature x precipitation on a grid, every other axis neutral. It is
# what gives a readable marginal response surface without having to fit anything.
CORE_DTEMP: tuple[float, ...] = (0.0, 2.0, 4.0, 6.0)
CORE_FPREC: tuple[float, ...] = (0.7, 1.0, 1.3)

DESIGN_SEED = 20260908


def _latin_hypercube(n: int, rng: np.random.Generator) -> npt.NDArray[np.float64]:
    """(n, 5) stratified uniform draws, one permutation per axis. Hand-rolled so it is reproducible.

    Rolled here rather than taken from scipy so the design depends on nothing but the seed and this
    file -- a pre-registration cites the design by hash and must be able to regenerate it.
    """
    axes = len(AXIS_RANGE)
    cut = (np.arange(n)[:, None] + rng.random((n, axes))) / n
    for j in range(axes):
        cut[:, j] = cut[rng.permutation(n), j]
    return cut


def pilot_design(n: int = 30, seed: int = DESIGN_SEED) -> list[Perturbation]:
    """The pilot corpus's `n` climates per cell: 1 control + a factorial core + a filling hypercube.

    The control is first and is exactly neutral, which is what makes the per-cell contrast
    "same cell, same seed, same everything but the climate" available for free.
    """
    core = [
        Perturbation(f"core_t{dt:+.0f}_p{fp:.1f}".replace(".", ""), dtemp=dt, fprec=fp)
        for dt in CORE_DTEMP
        for fp in CORE_FPREC
        if not (dt == 0.0 and fp == 1.0)  # that point IS the control; do not duplicate it
    ]
    design = [Perturbation.neutral(), *core]
    if any(p.hold_huss_diagnostic for p in design):  # pragma: no cover -- structural guard
        raise AssertionError("a design point must never carry the hold-huss diagnostic flag")
    remaining = n - len(design)
    if remaining < 0:
        raise ValueError(f"n={n} is smaller than the control plus the {len(core)}-point core")
    if remaining:
        rng = np.random.default_rng(seed)
        cube = _latin_hypercube(remaining, rng)
        names = list(AXIS_RANGE)
        for i in range(remaining):
            vals: dict[str, float] = {}
            for j, key in enumerate(names):
                lo, hi = AXIS_RANGE[key]
                vals[key] = round(float(lo + cube[i, j] * (hi - lo)), 4)
            design.append(
                Perturbation(
                    f"lhs{i:02d}",
                    dtemp=vals["dtemp"],
                    fprec=vals["fprec"],
                    sprec=vals["sprec"],
                    frad=vals["frad"],
                    fiav=vals["fiav"],
                )
            )
    return design


def design_by_name(name: str, n: int = 30, seed: int = DESIGN_SEED) -> Perturbation:
    """One design point by name, so a run directory can be rebuilt from its own provenance file."""
    for pert in pilot_design(n, seed):
        if pert.name == name:
            return pert
    raise KeyError(f"no design point {name!r} in the {n}-point pilot design (seed {seed})")
