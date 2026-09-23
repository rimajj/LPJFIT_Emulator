"""Daily-forcing climate features, v3: soil water, drought spells, and the model's own limits.

WHY A THIRD FEATURE SET. The 86 `CLIMATE_FEATURES` are monthly means, SDs and a handful of derived
indices. In the climate-only equilibrium map (`X-20260923-equilibrium-from-climate`) they carry
the forest-scale quantities well and the trait quantiles badly -- rooting depth p10/p50, wood
density, the SLA lower tail, longevity. None of the 86 knows what the soil does with the rain, how
long a dry spell lasts, or how often a day crosses a threshold at which LPJmL-FIT stops a tree type
establishing or starts counting stress against it. Those are what this module computes, from the
DAILY forcing, for any 30-year window: a pilot perturbation, the historical leg, or a scenario.

WHAT IS COMPUTED, AND WHERE EACH PIECE COMES FROM IN THE C MODEL

* A soil-water bucket driven by precipitation and a Priestley-Taylor demand. The demand is the
  model's own equilibrium evapotranspiration (`numeric/petpar2.c`, radiation mode "radiation":
  shortwave down plus NET longwave) times `ALPHAM / (1 + GM*ALPHAM/gp)` (`lpj/water_stressed.c`,
  par/lpjparam_fit.js). Supply is `emax * wr`, where `wr` is the root-weighted relative wetness
  over the soil layers -- exactly the model's supply term -- so the bucket is run once for each of
  five fixed rooting profiles (95 % rooting depth 50, 150, 400, 900 and 1600 cm). The difference
  between a shallow and a deep profile is the selection pressure on rooting depth: rooting depth
  acts only through the root distribution in the water-stress calculation (`tree/new_tree.c`
  sets beta from D95, `lpj/getrootdist.c` distributes it, `lpj/water_stressed.c` uses it).
* The VPD-weighted water-stress sum that drives drought mortality (`tree/waterstress_tree.c`:
  counted only above 10 degrees, weighted by VPD in kPa and by how far the water scalar falls
  under a threshold), with VPD exactly as `lpj/getvpd.c` computes it from specific humidity.
* The bioclimatic limits LPJmL-FIT applies to its seven tree types (`par/pft_lpjmlfit.js`, read
  through `cpp -P`): the 20-year mean coldest-month temperature for survival and establishment
  (`lpj/survive.c`, `lpj/establish.c`, over a 20-entry ring buffer, `lpj/climbuf.c`), the degree
  days above 5, the minimum warmest-month temperature for trees, the temperature range of the
  boreal needle-leaved summergreen type, and the daily cold-stress band of `tree/tempstress_tree.c`.
* Degree days at several bases, frost and heat day counts at the thresholds those files use,
  interannual variability of the monthly means, precipitation seasonality and timing.

⚠ WHAT IS DELIBERATELY NOT HERE
* **CO2.** Never a feature (invariant 8); nothing below reads it.
* **Latitude.** The model's own daylength, and the hemisphere-dependent reset day of its stress
  counters, depend on latitude. Using them would hand the learner the address, which is a
  pre-registered NULL and a forbidden column in every experiment. So the demand weights the net
  longwave by a FIXED daylight fraction of one half instead of the model's daylength, and the
  stress counters are per calendar year. Both are approximations, named here rather than hidden.
* **Anything from a restart or a model output.** These are functions of the forcing and the soil
  input only, so they are the same whether the cell was ever run or not.

THE BUCKET IS A PROXY, NOT THE MODEL'S SOIL. Six lumped layers (0-0.2, 0.2-0.5, 0.5-1, 1-2, 2-5 and
5-20 m) with the model's per-soil-type available water capacity, tipping-bucket infiltration, a
degree-day snowpack (`soil/snow.c`, `snow_old`), no bare-soil evaporation, no interception, no
lateral flow, and a crude Stefan thaw depth standing in for the permafrost limit on roots. It is
run three times through the 30-year window -- two passes to forget the initial state, as the
spin-up recycles the same window -- and only the third is summarised. Its job is to rank climates
the way the model's water balance would, which is all a learned map needs; it is never compared
to the model's own soil moisture.

EVERY FUNCTION HERE IS PER-ROW ELEMENTWISE, so the features of one cell do not depend on which other
cells share its batch. That is what makes the pilot's hard check meaningful: the control run's
features computed from its own single-cell forcing file must equal those computed from the global
historical file, whatever batch either was computed in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import ClmReader
from vegemu.corpus.climate import MONTH_LEN, MONTH_START, NDAYYEAR, NMONTH, VARS

Array = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

# --------------------------------------------------------------------------------------------
# The soil input. soil.bin holds one byte per cell; the byte indexes the `soilmap` of the pilot's
# own input file (input_c<cell>-...-s1.js, identical to input_GSWP3-W5E5.js), whose names select a
# row of par/soil_20m.js. Code 0 is `null`.
#
# ⚠ CODE 13 IS "rock and ice", NOT "clay (light)". The soilmap has thirteen named entries and the
# thirteenth is rock and ice; "clay (light)" is the 13th row of soil_20m.js but no code maps to it.
# 3,180 of the 67,420 cells carry code 13. None of the 200 pilot cells does, so nothing sealed is
# affected, but a transcription keyed on the soil_20m.js row order reads those cells as clay.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SoilType:
    """One row of par/soil_20m.js: volumetric fractions at wilting point, field capacity and
    saturation, sand and clay fractions, saturated conductivity (mm/h)."""

    name: str
    w_pwp: float
    w_fc: float
    w_sat: float
    sand: float
    clay: float
    ks: float

    @property
    def whc(self) -> float:
        """Available water capacity per mm of soil: field capacity minus wilting point."""
        return self.w_fc - self.w_pwp


SOIL_TYPES: dict[int, SoilType] = {
    1: SoilType("clay", 0.284, 0.398, 0.468, 0.22, 0.58, 3.5),
    2: SoilType("silty clay", 0.259, 0.378, 0.468, 0.06, 0.47, 4.8),
    3: SoilType("sandy clay", 0.205, 0.295, 0.406, 0.52, 0.42, 26.0),
    4: SoilType("clay loam", 0.214, 0.345, 0.465, 0.32, 0.34, 8.8),
    5: SoilType("silty clay loam", 0.247, 0.387, 0.464, 0.10, 0.34, 7.3),
    6: SoilType("sandy clay loam", 0.143, 0.256, 0.404, 0.58, 0.27, 16.0),
    7: SoilType("loam", 0.139, 0.292, 0.439, 0.43, 0.18, 12.2),
    8: SoilType("silt loam", 0.177, 0.368, 0.476, 0.17, 0.13, 10.1),
    9: SoilType("sandy loam", 0.100, 0.228, 0.434, 0.58, 0.10, 18.8),
    10: SoilType("silt", 0.177, 0.368, 0.476, 0.10, 0.30, 10.1),
    11: SoilType("loamy sand", 0.060, 0.149, 0.421, 0.82, 0.06, 50.7),
    12: SoilType("sand", 0.022, 0.088, 0.339, 0.92, 0.03, 167.8),
    13: SoilType("rock and ice", 0.0001, 0.005, 0.006, 0.99, 0.01, 0.1),
}

# par/soil_20m.js "soildepth": the thickness of each of the 23 layers, mm. A GLOBAL, not per cell.
LAYER_MM: tuple[float, ...] = (200.0, 300.0, 500.0, *([1000.0] * 19), 3000.0)
LAYERBOUND: tuple[float, ...] = tuple(float(x) for x in np.cumsum(LAYER_MM))
# Roots reach layers 0..BOTTOMLAYER-1 = 0..21 (getrootdist.c caps num_layer_new there), and beta
# is solved against the bottom of layer 21 in cm (new_tree.c: layerbound[BOTTOMLAYER-1]*0.1).
ROOT_LAYERS = 22
ROOT_BOTTOM_CM = LAYERBOUND[ROOT_LAYERS - 1] / 10.0

# The six lumped bucket layers, as groups of the model's own layers.
GROUPS: tuple[tuple[int, ...], ...] = ((0,), (1,), (2,), (3,), (4, 5, 6), tuple(range(7, 22)))
GROUP_NAMES: tuple[str, ...] = ("0_20cm", "20_50cm", "50_100cm", "1_2m", "2_5m", "5_20m")
GROUP_MM: tuple[float, ...] = tuple(sum(LAYER_MM[i] for i in g) for g in GROUPS)

# The five fixed rooting profiles, as 95 % rooting depth in cm -- the unit of the D95max trait
# (getbetaroot.c solves in cm). They span the pilot's trait range, 51-1758 cm.
ROOT_PROFILES_CM: tuple[float, ...] = (50.0, 150.0, 400.0, 900.0, 1600.0)
MID_PROFILE = 2  # 400 cm: the profile whose layer wetness is reported

# Water-balance constants, each from the model's own parameter files or source.
EMAX = 10.0  # mm/day, par/pft_lpjmlfit.js "emax" of the broad-leaved types
ALPHAM = 1.391  # par/lpjparam_fit.js, Priestley-Taylor coefficient of the demand function
GM = 3.26  # par/lpjparam_fit.js, empirical parameter of the demand function
GP_REF = 10.0  # mm/s: a FIXED representative canopy conductance; the model's is dynamic
ALBEDO = 0.15  # a fixed stand albedo; the model's is computed from the vegetation
DAYLIGHT_FRACTION = 0.5  # stands in for daylength/24, which needs latitude (module docstring)
TSNOW = 0.0  # include/soil.h
STEFAN_E = 0.05  # m per sqrt(degree-day): an edaphic factor for the thaw-depth proxy
PERMAFROST_FROST_NUMBER = 0.5  # Nelson frost number above which permafrost is assumed
N_PASSES = 3  # two to forget the initial store, one to summarise

# waterstress_tree.c thresholds are `mort_water_res - minwscal`; with the median minwscal of the
# seven types those span 0.15-0.54, so two thresholds bracket them.
STRESS_THRESHOLDS: tuple[float, ...] = (0.2, 0.5)
DRY_WSCAL = 0.5  # a "dry" day for the spell statistics
STRESS_WSCAL = 0.3  # a "stressed" day for the stress-day count

# --------------------------------------------------------------------------------------------
# The seven tree types' bioclimatic limits, par/pft_lpjmlfit.js through cpp -P, in file order
# (= pft_frac_0..6 of the corpus). `temp` is (low, high) on the 20-year mean coldest month;
# `temp_stressed_low` is the daily cold-stress threshold of tempstress_tree.c; `tmin_base` and
# `tmax_base` are the GSI phenology limits. aprec_min is 100 mm for all seven.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TreeLimits:
    abbr: str
    temp_low: float
    temp_high: float
    gdd5min: float
    min_temprange: float
    temp_stressed_low: float
    tmin_base: float
    tmax_base: float


TREE_TYPES: tuple[TreeLimits, ...] = (
    TreeLimits("trbe", 2.5, 1000.0, 0.0, -1000.0, 12.5, 10.0, 38.64),
    TreeLimits("tene", -30.0, 1000.0, 900.0, -1000.0, -15.0, -30.0, 35.26),
    TreeLimits("tebe", -15.0, 1000.0, 1200.0, -1000.0, -10.0, -5.0, 41.12),
    TreeLimits("tebs", -30.0, 1000.0, 1200.0, -1000.0, -20.0, 8.5, 41.51),
    TreeLimits("bone", -80.0, 0.0, 350.0, -1000.0, -45.0, -80.0, 28.0),
    TreeLimits("bobs", -80.0, 0.0, 350.0, -1000.0, -45.0, 8.0, 28.0),
    TreeLimits("bons", -80.0, 0.0, 350.0, 30.0, -70.0, 7.0, 28.0),
)
APREC_MIN = 100.0
CLIMBUF_YEARS = 20  # include/climbuf.h CLIMBUFSIZE
TREE_MIN_TMAX20 = 10.0  # establish.c: no tree establishes where the 20-year warmest month <= 10

# Establishment and survival rules that are distinct across the seven types (BoNE and BoBS share
# every limit, so one column serves both).
EST_TYPES: tuple[str, ...] = ("trbe", "tene", "tebe", "tebs", "bone", "bons")
SURV_RULES: tuple[tuple[str, float, float], ...] = (
    # (name, temp_low, min_temprange)
    ("surv_tc_ge_2p5", 2.5, -1000.0),
    ("surv_tc_ge_m15", -15.0, -1000.0),
    ("surv_tc_ge_m30", -30.0, -1000.0),
    ("surv_bons", -80.0, 30.0),
)
GDD5_THRESHOLDS: tuple[float, ...] = (350.0, 900.0, 1200.0)

# Cold-day thresholds: the union of the cold-stress band's lower edges and the GSI tmin bases.
COLD_THRESHOLDS: tuple[float, ...] = (
    12.5,
    10.0,
    8.5,
    8.0,
    7.0,
    -5.0,
    -10.0,
    -15.0,
    -20.0,
    -30.0,
    -45.0,
    -70.0,
)
# The cold-stress thresholds of tempstress_tree.c, whose WORST year is also reported: that counter
# adds `mort_temp_factor * days / 365` to the annual mortality, so one bad year can clear a stand.
STRESS_COLD: tuple[float, ...] = (12.5, -10.0, -15.0, -20.0, -45.0, -70.0)
# Heat thresholds: twmax_daily of the boreal types, and the GSI tmax bases.
HOT_THRESHOLDS: tuple[float, ...] = (25.0, 28.0, 35.26, 38.64, 41.12)
# GSI light bases (W m-2) below which a day is dark for the phenology of most types.
DARK_THRESHOLDS: tuple[float, ...] = (40.0, 55.0)
WET_DAY_MM = 1.0
HEAVY_DAY_MM = 20.0


def _tag(x: float) -> str:
    """A threshold as a column-name fragment: 12.5 -> '12p5', -10 -> 'm10'."""
    s = f"{abs(x):g}".replace(".", "p")
    return f"m{s}" if x < 0 else s


def _feature_names() -> tuple[str, ...]:
    names: list[str] = []
    for d in ROOT_PROFILES_CM:
        p = f"d{d:g}"
        names += [f"aet_{p}", f"wscal_{p}"]
        names += [f"wstress_{p}_{_tag(t)}" for t in STRESS_THRESHOLDS]
        names += [f"stressdays_{p}", f"wspell_{p}_p50", f"wspell_{p}_p90"]
    names += ["aet_gain_deep", "wscal_gain_deep", "d95_best_log"]
    names += [f"wet_{g}" for g in GROUP_NAMES]
    names += ["pet_ann", "cwb_ann", "cwb_min_month", "cwb_neg_months", "moisture_index"]
    names += ["awc_1m", "awc_rootzone", "thaw_depth_proxy"]
    names += ["snow_max", "snow_days"]
    names += [
        "wetday_freq",
        "wetday_intensity",
        "heavy_frac",
        "dryspell_p50",
        "dryspell_p90",
        "dryspell_warm_p50",
    ]
    names += ["tcmin20_mean", "tcmin20_min", "tcmin20_max", "tcmax20_mean", "trange20_mean"]
    names += [r[0] for r in SURV_RULES]
    names += [f"est_{t}" for t in EST_TYPES]
    names += [f"gdd5_ge_{t:g}" for t in GDD5_THRESHOLDS]
    names += ["gdd10", "gdd5_cv", "gdd5_min"]
    names += [f"days_below_{_tag(t)}" for t in COLD_THRESHOLDS]
    names += [f"days_below_{_tag(t)}_max" for t in STRESS_COLD]
    names += ["tmin_abs", "tmin_ann_mean"]
    names += [f"days_above_{_tag(t)}" for t in HOT_THRESHOLDS]
    names += ["heat_dd25", "heat_dd25_max", "warm_month_gt23_frac"]
    names += ["fdd", "frost_number"]
    names += [f"days_rsds_below_{_tag(t)}" for t in DARK_THRESHOLDS]
    names += [
        "tas_iav_coldest",
        "tas_iav_warmest",
        "tas_miav",
        "pr_miav_cv",
        "pr_ann_cv",
        "pr_conc",
        "pr_warm_phase",
    ]
    return tuple(names)


V3_FEATURES: tuple[str, ...] = _feature_names()


# --------------------------------------------------------------------------------------------
# The model's own formulas, transcribed.
# --------------------------------------------------------------------------------------------


def beta_root(d95_cm: float, bottom_cm: float = ROOT_BOTTOM_CM) -> float:
    """getbetaroot.c: the beta with `(1 - beta^D95) / (1 - beta^bottom) = 0.95`, by bisection.

    The C bisects to 1e-4 in 20 steps; this bisects to machine precision. The difference is far
    below anything a feature can resolve, and a tighter solve makes the root table reproducible.
    """
    lo, hi = 1e-12, 0.9999
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f = (1.0 - mid**d95_cm) / (1.0 - mid**bottom_cm) - 0.95
        # f rises with beta: a larger beta puts roots deeper, so less is inside D95.
        if f > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def root_layer_fractions(d95_cm: float, depth_mm: Array) -> Array:
    """getrootdist.c for a tree at full rooting depth: (ncell, 22) root fractions per model layer.

    The beta distribution is spread over layers 0..21, then every layer whose TOP lies below the
    usable depth (soil depth, or the thaw depth where there is permafrost) gives its roots up, and
    they are added to layer `max(0, num_layer_new - removed - 1)` -- which, as the C is written, is
    the layer ABOVE the last one that keeps its roots. Transcribed as written, off-by-one included.
    """
    beta = beta_root(d95_cm)
    lb_cm = np.asarray(LAYERBOUND[:ROOT_LAYERS], dtype=np.float64) / 10.0
    total = 1.0 - beta ** lb_cm[-1]
    r = np.empty(ROOT_LAYERS, dtype=np.float64)
    r[0] = (1.0 - beta ** lb_cm[0]) / total
    r[1:] = (beta ** lb_cm[:-1] - beta ** lb_cm[1:]) / total

    depth = np.asarray(depth_mm, dtype=np.float64)
    tops = np.asarray(LAYERBOUND[: ROOT_LAYERS - 1], dtype=np.float64)  # top of layer l = lb[l-1]
    # Layers 0 and 1 are never removed; layer l >= 2 is removed when lb[l-1] > depth. Monotone, so
    # the kept layers are 0..first-1 with first = 2 + #{l in 2..21 : lb[l-1] <= depth}.
    first = 2 + (tops[None, 1:] <= depth[:, None]).sum(axis=1)
    removed = ROOT_LAYERS - first
    pos = np.maximum(0, (ROOT_LAYERS - 1) - removed - 1)
    layer = np.arange(ROOT_LAYERS)[None, :]
    keep = layer < first[:, None]
    out = np.where(keep, r[None, :], 0.0)
    excess = np.where(keep, 0.0, r[None, :]).sum(axis=1)
    out[np.arange(depth.size), pos] += excess
    return out


def root_group_fractions(d95_cm: float, depth_mm: Array) -> Array:
    """`root_layer_fractions` summed into the six bucket layers: (ncell, 6)."""
    per_layer = root_layer_fractions(d95_cm, depth_mm)
    return np.stack([per_layer[:, list(g)].sum(axis=1) for g in GROUPS], axis=1)


def equilibrium_et(tas: Array, rsds: Array, lwnet: Array) -> Array:
    """petpar2.c `eeq` in mm/day, with the daylength replaced by a fixed daylight fraction."""
    s = 2.503e6 * np.exp(17.269 * tas / (237.3 + tas)) / ((237.3 + tas) * (237.3 + tas))
    gamma = 65.05 + tas * 0.064
    lam = 2.495e6 - tas * 2380.0
    net = (1.0 - ALBEDO) * rsds + lwnet * DAYLIGHT_FRACTION
    return np.maximum(86400.0 * (s / (s + gamma) / lam) * net, 0.0)


def demand(eeq: Array) -> Array:
    """water_stressed.c's demand at a fixed canopy conductance, without the wet-canopy term."""
    return eeq * ALPHAM / (1.0 + (GM * ALPHAM) / GP_REF)


def vpd_pa(tas: Array, huss: Array) -> Array:
    """getvpd.c, `relative_humidity = false` as in the pilot config: Goff-Gratch, in Pa."""
    a, b, c, d, f, h, ts = -7.90298, 5.02808, -1.3816e-7, 11.344, 8.1328e-3, 3.49149, 373.16
    t = tas + 273.16
    z = (
        a * (ts / t - 1.0)
        + b * np.log10(ts / t)
        + c * (np.power(10.0, d * (1.0 - t / ts)) - 1.0)
        + f * (np.power(10.0, -h * (ts / t - 1.0)) - 1.0)
    )
    rh = np.minimum(0.263 * 1013.25 * huss / np.exp(17.67 * tas / (t - 29.65)), 1.0)
    out: Array = np.power(10.0, z) * (1.0 - rh) * 101324.6
    return out


# --------------------------------------------------------------------------------------------
# Small vectorised helpers.
# --------------------------------------------------------------------------------------------


def longest_run(mask: npt.NDArray[np.bool_]) -> Array:
    """Longest run of True along the LAST axis, per leading index. Loops over the last axis only."""
    run = np.zeros(mask.shape[:-1], dtype=np.int64)
    best = np.zeros(mask.shape[:-1], dtype=np.int64)
    for d in range(mask.shape[-1]):
        run = np.where(mask[..., d], run + 1, 0)
        np.maximum(best, run, out=best)
    return best.astype(np.float64)


def _monthly(daily: Array, reduce_sum: bool) -> Array:
    """(..., 365) -> (..., 12), summing or averaging within each month."""
    total = np.add.reduceat(daily, list(MONTH_START), axis=-1)
    if reduce_sum:
        return total
    out: Array = total / np.asarray(MONTH_LEN, dtype=np.float64)
    return out


def _cyclic_running_mean(per_year: Array, width: int) -> Array:
    """(n, ny) -> (n, ny): mean over the `width` years ending at each year, wrapping around.

    The spin-up recycles the same 30-year window, so the model's 20-entry ring buffer at year y of
    a cycle holds years y-19..y of the window, taken cyclically.
    """
    ny = per_year.shape[1]
    w = min(width, ny)
    idx = (np.arange(ny)[:, None] - np.arange(w)[None, :]) % ny
    out: Array = per_year[:, idx].mean(axis=2)
    return out


def _cv(x: Array, axis: int) -> Array:
    """Coefficient of variation (ddof=1), zero where the mean is zero."""
    m = x.mean(axis=axis)
    s = x.std(axis=axis, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out: Array = np.where(m > 0, s / np.where(m > 0, m, 1.0), 0.0)
    return out


def _phase(monthly: Array) -> tuple[Array, Array]:
    """Circular centroid of a 12-month cycle: (angle, concentration in 0..1)."""
    ang = 2.0 * np.pi * (np.arange(NMONTH) + 0.5) / NMONTH
    tot = monthly.sum(axis=-1)
    cx = (monthly * np.cos(ang)).sum(axis=-1)
    sy = (monthly * np.sin(ang)).sum(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        conc = np.where(tot > 0, np.hypot(cx, sy) / np.where(tot > 0, tot, 1.0), 0.0)
    return np.arctan2(sy, cx), conc


# --------------------------------------------------------------------------------------------
# Soil.
# --------------------------------------------------------------------------------------------


def soil_whc(codes: npt.ArrayLike) -> Array:
    """Available water capacity per mm for each soil code; NaN for code 0 or any unknown code."""
    c = np.asarray(codes, dtype=np.int64)
    table = np.full(max(SOIL_TYPES) + 1, np.nan)
    for k, st in SOIL_TYPES.items():
        table[k] = st.whc
    out: Array = np.where((c >= 0) & (c < table.size), table[np.clip(c, 0, table.size - 1)], np.nan)
    return out


def thaw_depth_mm(tdd: Array, frost_number: Array) -> Array:
    """A Stefan thaw depth where permafrost is likely, else +inf (no thaw limit on roots)."""
    stefan = STEFAN_E * np.sqrt(np.maximum(tdd, 0.0)) * 1000.0
    out: Array = np.where(frost_number >= PERMAFROST_FROST_NUMBER, stefan, np.inf)
    return out


# --------------------------------------------------------------------------------------------
# The bucket.
# --------------------------------------------------------------------------------------------


def run_bucket(  # noqa: PLR0915, PLR0917 -- one daily loop; splitting it costs a copy per day
    tas: Array,
    pr: Array,
    dem: Array,
    vpd: Array,
    whc: Array,
    depth_mm: Array,
    passes: int = N_PASSES,
) -> dict[str, Array]:
    """The multi-profile bucket over (n, nyear, 365) daily inputs; returns per-cell summaries.

    State is `W[group, cell, profile]` in mm, laid out so each group's slice is contiguous. The
    inputs are transposed to (day, cell) once, for the same reason: one day is one contiguous row.
    """
    n, ny, nd = tas.shape
    if nd != NDAYYEAR:
        raise ValueError(f"expected {NDAYYEAR} days per year, got {nd}")
    ng, npf = len(GROUPS), len(ROOT_PROFILES_CM)
    tt = np.ascontiguousarray(tas.reshape(n, ny * nd).T)
    pt = np.ascontiguousarray(pr.reshape(n, ny * nd).T)
    dt = np.ascontiguousarray(dem.reshape(n, ny * nd).T)
    vt = np.ascontiguousarray(vpd.reshape(n, ny * nd).T) / 1000.0  # kPa, as waterstress_tree.c

    cap = whc[None, :] * np.asarray(GROUP_MM, dtype=np.float64)[:, None]  # (G, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        inv_cap = np.where(cap > 0, 1.0 / np.where(cap > 0, cap, 1.0), 0.0)
    roots = np.stack([root_group_fractions(d, depth_mm) for d in ROOT_PROFILES_CM], axis=2)
    roots = np.ascontiguousarray(np.transpose(roots, (1, 0, 2)))  # (G, n, P)

    store = 0.5 * np.repeat(cap[:, :, None], npf, axis=2)
    snow = np.zeros(n)

    aet_sum = np.zeros((n, npf))
    wscal_grow = np.zeros((n, npf))
    grow_days = np.zeros(n)
    wstress = np.zeros((len(STRESS_THRESHOLDS), n, npf))
    stress_days = np.zeros((n, npf))
    run: Array = np.zeros((n, npf))
    spell_max = np.zeros((ny, n, npf))
    wet_grow = np.zeros((ng, n))
    snow_max = np.zeros((ny, n))
    snow_days = np.zeros(n)

    with np.errstate(invalid="ignore", divide="ignore"):
        for ip in range(passes):
            last = ip == passes - 1
            for t in range(ny * nd):
                temp, prec, dd = tt[t], pt[t], dt[t]
                cold = temp < TSNOW
                snowfall = np.where(cold, prec, 0.0)
                snow += snowfall
                melt = np.where(cold, 0.0, np.minimum(snow, (1.5 + 0.007 * prec) * temp))
                snow -= melt
                rem = np.repeat(((prec - snowfall) + melt)[:, None], npf, axis=1)
                for g in range(ng):
                    add = np.minimum(rem, cap[g][:, None] - store[g])
                    store[g] += add
                    rem -= add
                wet = store * inv_cap[:, :, None]
                rw = roots * wet
                wr = rw.sum(axis=0)
                supply = EMAX * wr
                aet = np.minimum(supply, dd[:, None])
                take = rw * (aet / np.maximum(wr, 1e-300))[None, :, :]
                store -= np.minimum(take, store)
                if not last:
                    continue
                y, day = divmod(t, nd)
                wscal = np.where(dd[:, None] > 0, np.minimum(supply / dd[:, None], 1.0), 1.0)
                grow = temp > 5.0
                warm = temp > 10.0
                aet_sum += aet
                wscal_grow += wscal * grow[:, None]
                grow_days += grow
                vk = np.where(warm, vt[t], 0.0)[:, None]
                for k, thr in enumerate(STRESS_THRESHOLDS):
                    wstress[k] += vk * np.maximum(thr - wscal, 0.0)
                stress_days += warm[:, None] & (wscal < STRESS_WSCAL)
                run = np.where(grow[:, None] & (wscal < DRY_WSCAL), run + 1.0, 0.0)
                np.maximum(spell_max[y], run, out=spell_max[y])
                if day == nd - 1:
                    run[:] = 0.0  # a spell does not cross the year boundary
                wet_grow += wet[:, :, MID_PROFILE] * grow[None, :]
                np.maximum(snow_max[y], snow, out=snow_max[y])
                snow_days += snow > 1.0

    out: dict[str, Array] = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        wmean = np.where(grow_days[:, None] > 0, wscal_grow / grow_days[:, None], 1.0)
        for j, d in enumerate(ROOT_PROFILES_CM):
            p = f"d{d:g}"
            out[f"aet_{p}"] = aet_sum[:, j] / ny
            out[f"wscal_{p}"] = wmean[:, j]
            for k, thr in enumerate(STRESS_THRESHOLDS):
                out[f"wstress_{p}_{_tag(thr)}"] = wstress[k, :, j] / ny
            out[f"stressdays_{p}"] = stress_days[:, j] / ny
            out[f"wspell_{p}_p50"] = np.quantile(spell_max[:, :, j], 0.5, axis=0)
            out[f"wspell_{p}_p90"] = np.quantile(spell_max[:, :, j], 0.9, axis=0)
        aet_all = aet_sum / ny
        out["aet_gain_deep"] = aet_all[:, -1] - aet_all[:, 0]
        out["wscal_gain_deep"] = wmean[:, -1] - wmean[:, 0]
        # argmax takes the FIRST maximum, i.e. the shallowest profile among ties.
        best = np.argmax(aet_all, axis=1)
        out["d95_best_log"] = np.where(
            np.isfinite(aet_all).all(axis=1),
            np.log(np.asarray(ROOT_PROFILES_CM))[best],
            np.nan,
        )
        for g, name in enumerate(GROUP_NAMES):
            out[f"wet_{name}"] = np.where(grow_days > 0, wet_grow[g] / grow_days, np.nan)
            out[f"wet_{name}"] = np.where(np.isfinite(whc), out[f"wet_{name}"], np.nan)
    out["snow_max"] = snow_max.mean(axis=0)
    out["snow_days"] = snow_days / ny
    return out


# --------------------------------------------------------------------------------------------
# The whole feature row.
# --------------------------------------------------------------------------------------------


def v3_columns(  # noqa: PLR0912, PLR0915 -- a flat sequence of independent feature definitions
    daily: Mapping[str, Array],
    soil_code: npt.ArrayLike,
    soildepth_m: npt.ArrayLike,
    passes: int = N_PASSES,
) -> dict[str, Array]:
    """Every V3 feature, one value per row, from (n, nyear, 365) daily arrays of the five VARS.

    `soil_code` is the soil.bin byte and `soildepth_m` the soil-depth input in metres, per row.
    Units follow the forcing: tas in deg C, pr in mm/day, rsds and lwnet in W m-2 (lwnet net,
    downward positive, so normally negative), huss in kg/kg.
    """
    for v in VARS:
        if v not in daily:
            raise KeyError(f"missing daily variable {v!r}")
    tas = np.asarray(daily["tas"], dtype=np.float64)
    pr = np.maximum(np.asarray(daily["pr"], dtype=np.float64), 0.0)
    rsds = np.asarray(daily["rsds"], dtype=np.float64)
    lwnet = np.asarray(daily["lwnet"], dtype=np.float64)
    huss = np.asarray(daily["huss"], dtype=np.float64)
    if tas.ndim != 3 or tas.shape[2] != NDAYYEAR:
        raise ValueError(f"daily arrays must be (n, nyear, {NDAYYEAR}), got {tas.shape}")
    for v, arr in (("pr", pr), ("rsds", rsds), ("lwnet", lwnet), ("huss", huss)):
        if arr.shape != tas.shape:
            raise ValueError(f"{v} has shape {arr.shape}, tas has {tas.shape}")
    n, ny, _ = tas.shape
    whc = soil_whc(soil_code)
    depth_m = np.asarray(soildepth_m, dtype=np.float64)
    if whc.shape != (n,) or depth_m.shape != (n,):
        raise ValueError("soil_code and soildepth_m must have one value per row")

    cols: dict[str, Array] = {}

    # -- temperature: the limits LPJmL-FIT applies ------------------------------------------
    tmon = _monthly(tas, reduce_sum=False)  # (n, ny, 12)
    tc_y, tw_y = tmon.min(axis=2), tmon.max(axis=2)
    tc20 = _cyclic_running_mean(tc_y, CLIMBUF_YEARS)
    tw20 = _cyclic_running_mean(tw_y, CLIMBUF_YEARS)
    range20 = tw20 - tc20
    gdd5_y = np.maximum(tas - 5.0, 0.0).sum(axis=2)
    gdd0_y = np.maximum(tas, 0.0).sum(axis=2)
    fdd_y = np.maximum(-tas, 0.0).sum(axis=2)
    pr_y = pr.sum(axis=2)
    aprec_ok = (pr_y.mean(axis=1) >= APREC_MIN)[:, None]

    cols["tcmin20_mean"] = tc20.mean(axis=1)
    cols["tcmin20_min"] = tc20.min(axis=1)
    cols["tcmin20_max"] = tc20.max(axis=1)
    cols["tcmax20_mean"] = tw20.mean(axis=1)
    cols["trange20_mean"] = range20.mean(axis=1)
    for name, low, trange in SURV_RULES:
        cols[name] = ((tc20 >= low) & (range20 >= trange)).mean(axis=1)
    by_abbr = {t.abbr: t for t in TREE_TYPES}
    for abbr in EST_TYPES:
        lim = by_abbr[abbr]
        ok = (
            (tc20 >= lim.temp_low)
            & (tc20 <= lim.temp_high)
            & (gdd5_y >= lim.gdd5min)
            & (tw20 > TREE_MIN_TMAX20)
            & (range20 >= lim.min_temprange)
            & aprec_ok
        )
        cols[f"est_{abbr}"] = ok.mean(axis=1)
    for thr in GDD5_THRESHOLDS:
        cols[f"gdd5_ge_{thr:g}"] = (gdd5_y >= thr).mean(axis=1)
    cols["gdd10"] = np.maximum(tas - 10.0, 0.0).sum(axis=2).mean(axis=1)
    cols["gdd5_cv"] = _cv(gdd5_y, axis=1)
    cols["gdd5_min"] = gdd5_y.min(axis=1)
    for thr in COLD_THRESHOLDS:
        cols[f"days_below_{_tag(thr)}"] = (tas < thr).sum(axis=2).mean(axis=1)
    for thr in STRESS_COLD:
        cols[f"days_below_{_tag(thr)}_max"] = (tas < thr).sum(axis=2).max(axis=1).astype(float)
    tmin_y = tas.min(axis=2)
    cols["tmin_abs"] = tmin_y.min(axis=1)
    cols["tmin_ann_mean"] = tmin_y.mean(axis=1)
    for thr in HOT_THRESHOLDS:
        cols[f"days_above_{_tag(thr)}"] = (tas > thr).sum(axis=2).mean(axis=1)
    heat_y = np.maximum(tas - 25.0, 0.0).sum(axis=2)
    cols["heat_dd25"] = heat_y.mean(axis=1)
    cols["heat_dd25_max"] = heat_y.max(axis=1)
    cols["warm_month_gt23_frac"] = (tw_y > 23.0).mean(axis=1)
    fdd, tdd = fdd_y.mean(axis=1), gdd0_y.mean(axis=1)
    cols["fdd"] = fdd
    with np.errstate(divide="ignore", invalid="ignore"):
        sf, st = np.sqrt(fdd), np.sqrt(tdd)
        cols["frost_number"] = np.where(sf + st > 0, sf / np.where(sf + st > 0, sf + st, 1.0), 0.0)
    for thr in DARK_THRESHOLDS:
        cols[f"days_rsds_below_{_tag(thr)}"] = (rsds < thr).sum(axis=2).mean(axis=1)

    # -- variability and seasonality -------------------------------------------------------
    pmon = _monthly(pr, reduce_sum=True)  # (n, ny, 12)
    cols["tas_iav_coldest"] = tc_y.std(axis=1, ddof=1)
    cols["tas_iav_warmest"] = tw_y.std(axis=1, ddof=1)
    cols["tas_miav"] = tmon.std(axis=1, ddof=1).mean(axis=1)
    cols["pr_miav_cv"] = _cv(pmon, axis=1).mean(axis=1)
    cols["pr_ann_cv"] = _cv(pr_y, axis=1)
    p_clim, t_clim = pmon.mean(axis=1), tmon.mean(axis=1)
    p_ang, p_conc = _phase(p_clim)
    t_ang, _ = _phase(t_clim - t_clim.min(axis=1, keepdims=True))
    cols["pr_conc"] = p_conc
    cols["pr_warm_phase"] = np.cos(p_ang - t_ang)

    # -- precipitation events --------------------------------------------------------------
    wet = pr >= WET_DAY_MM
    nwet = wet.sum(axis=(1, 2)).astype(np.float64)
    ptot = pr.sum(axis=(1, 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        cols["wetday_freq"] = nwet / (ny * NDAYYEAR)
        cols["wetday_intensity"] = np.where(nwet > 0, (pr * wet).sum(axis=(1, 2)) / nwet, 0.0)
        heavy = (pr * (pr >= HEAVY_DAY_MM)).sum(axis=(1, 2))
        cols["heavy_frac"] = np.where(ptot > 0, heavy / np.where(ptot > 0, ptot, 1.0), 0.0)
    dry_run = longest_run(~wet)  # (n, ny)
    cols["dryspell_p50"] = np.quantile(dry_run, 0.5, axis=1)
    cols["dryspell_p90"] = np.quantile(dry_run, 0.9, axis=1)
    cols["dryspell_warm_p50"] = np.quantile(longest_run(~wet & (tas > 10.0)), 0.5, axis=1)

    # -- water balance ---------------------------------------------------------------------
    dem = demand(equilibrium_et(tas, rsds, lwnet))
    dmon = _monthly(dem, reduce_sum=True).mean(axis=1)  # (n, 12)
    pet = dmon.sum(axis=1)
    pann = p_clim.sum(axis=1)
    cols["pet_ann"] = pet
    cols["cwb_ann"] = pann - pet
    cols["cwb_min_month"] = (p_clim - dmon).min(axis=1)
    cols["cwb_neg_months"] = (p_clim < dmon).sum(axis=1).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        cols["moisture_index"] = np.where(pet > 0, pann / np.where(pet > 0, pet, 1.0), 0.0)

    thaw = thaw_depth_mm(tdd, cols["frost_number"])
    usable = np.minimum(depth_m * 1000.0, thaw)
    cols["thaw_depth_proxy"] = np.where(np.isfinite(thaw), thaw / 1000.0, depth_m)
    cols["awc_1m"] = whc * 1000.0
    cols["awc_rootzone"] = whc * np.minimum(usable, LAYERBOUND[ROOT_LAYERS - 1])

    cols.update(run_bucket(tas, pr, dem, vpd_pa(tas, huss), whc, usable, passes=passes))

    missing = set(V3_FEATURES) - set(cols)
    extra = set(cols) - set(V3_FEATURES)
    if missing or extra:
        raise AssertionError(f"feature list out of step: missing {missing}, extra {extra}")
    return {k: np.asarray(cols[k], dtype=np.float64) for k in V3_FEATURES}


# --------------------------------------------------------------------------------------------
# Reading the forcing.
# --------------------------------------------------------------------------------------------


def _check_readers(readers: Mapping[str, ClmReader], first: int, last: int) -> tuple[int, int]:
    """The five files must describe the same cells, daily, over the window. Returns (ncell,
    firstcell)."""
    h0 = readers[VARS[0]].header
    for var, r in readers.items():
        h = r.header
        if (h.ncell, h.firstcell) != (h0.ncell, h0.firstcell):
            raise ValueError(
                f"{var} holds cells {h.firstcell}+{h.ncell}, {VARS[0]} holds "
                f"{h0.firstcell}+{h0.ncell}: the five variables do not describe the same cells"
            )
        if h.nbands != NDAYYEAR:
            raise ValueError(f"{var} has nbands={h.nbands}, expected {NDAYYEAR} (daily)")
        if not (h.firstyear <= first and last <= h.lastyear):
            raise ValueError(f"{var} covers {h.firstyear}-{h.lastyear}, window is {first}-{last}")
    return h0.ncell, h0.firstcell


def read_rows(
    files: Mapping[str, str | Path], first: int, last: int, row0: int, row1: int
) -> tuple[dict[str, Array], IntArray]:
    """Daily forcing for the contiguous ROWS [row0, row1) of the files, over years first..last.

    Returns ({var: (n, nyear, 365)}, global cell index per row). One contiguous read per variable
    per year -- a year is `value[cell][band]`, so a row range is one slab -- and one read per
    variable when the range is the whole file, because then the years are contiguous too.
    """
    readers = {v: ClmReader(files[v]) for v in VARS}
    ncell, firstcell = _check_readers(readers, first, last)
    if not 0 <= row0 < row1 <= ncell:
        raise ValueError(f"rows {row0}..{row1} outside the file's {ncell} cells")
    n, ny = row1 - row0, last - first + 1
    out: dict[str, Array] = {}
    for v, r in readers.items():
        h = r.header
        stride = h.nbands * h.itemsize
        raw: npt.NDArray[np.generic]
        with Path(files[v]).open("rb") as fh:
            if row0 == 0 and row1 == ncell:
                fh.seek(h.year_offset(first))
                blob = fh.read(ny * h.year_bytes)
                raw = np.frombuffer(blob, dtype=h.dtype).reshape(ny, ncell, h.nbands)
                raw = np.transpose(raw, (1, 0, 2))
            else:
                slabs = []
                for yr in range(first, last + 1):
                    fh.seek(h.year_offset(yr) + row0 * stride)
                    blob = fh.read(n * stride)
                    slabs.append(np.frombuffer(blob, dtype=h.dtype).reshape(n, h.nbands))
                raw = np.stack(slabs, axis=1)
        out[v] = raw.astype(np.float64) * h.scalar
    return out, np.arange(firstcell + row0, firstcell + row1, dtype=np.int64)


def read_cells(
    files: Mapping[str, str | Path], first: int, last: int, cells: Sequence[int]
) -> dict[str, Array]:
    """Daily forcing for an arbitrary list of GLOBAL cell ids: {var: (len(cells), nyear, 365)}.

    ⚠ `cells` are GLOBAL ids, never row numbers; the row is `cell - firstcell` (see
    `vegemu.corpus.climate.climate_columns` for the defect this distinction once caused).
    """
    readers = {v: ClmReader(files[v]) for v in VARS}
    ncell, firstcell = _check_readers(readers, first, last)
    ids = np.asarray(cells, dtype=np.int64)
    if ids.size and (ids.min() < firstcell or ids.max() >= firstcell + ncell):
        raise ValueError(f"cells outside {firstcell}..{firstcell + ncell - 1}")
    out: dict[str, Array] = {}
    for v, r in readers.items():
        with r:
            out[v] = np.stack([r.cell_years(int(c), first, last) for c in ids], axis=0)
    return out
