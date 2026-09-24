"""The restart's climate buffer, DERIVED from the forcing -- and the tree types that climate admits.

WHY THIS MATTERS MORE THAN ITS SIZE. The climate buffer is ~1 kB of a ~1.9 MB record, and the
synthesiser used to copy it from the template. For a cell synthesised under a climate it has never
been run under, that copy hands the model the TEMPLATE's climate memory, and the model acts on it:
`survive()` (`lpj/survive.c`) kills every tree whose type's cold limit the 20-year mean coldest
month violates, and `establish()` (`lpj/establish.c`) decides recruitment from the same two ring
buffers. Those two buffers are the only climate-buffer fields natural vegetation reads at all
(plus the last 31 daily temperatures and `atemp_mean`, for soil temperature, and `temp_max`, which
`mortality_tree_ind` receives and ignores). Everything else in the buffer feeds crops or nitrogen
fixation, both off in this configuration.

THE BUFFER IS EXACTLY REPRODUCIBLE, AND THE REASON IS A PIECE OF LUCK WORTH STATING. The spin-up
recycles its 30-year forcing for 1000 years, and with `shuffle_climate` on the order is RANDOM
(`lpj/iterate.c:104-110`), so the buffer's exponential memory reaches back into a random sequence
of years. But that randomness comes from ONE global generator, `config->seed`, which is seeded from
`random_seed` alone (`setseed`, `numeric/setseed.c`) and consumed by nothing else in this
configuration -- the per-cell generators are separate. So every pilot run with `random_seed 1`
draws the SAME year sequence, and it can be replayed here: glibc's `erand48` is the 48-bit linear
congruential generator `x' = (0x5DEECE66D x + 11) mod 2^48`. The check that this is right is
free and exact: the restart header stores `config->seed` as it was when the file was written, and
the state after 970 replayed draws matches it in every pilot run.

WHAT CANNOT BE DERIVED, and what is done instead -- both are inert for natural vegetation:
  * `mpet20` (20-year monthly potential evapotranspiration) depends on the patch ALBEDO
    (`numeric/petpar2.c`: the net shortwave is `(1-albedo) * swdown`), i.e. on the vegetation. An
    effective monthly albedo is solved from a REAL buffer and its own forcing (`effective_albedo`)
    and applied to the target forcing. Read only by crop sowing (`crop/calc_seasonality.c`).
  * `aetp_mean` (20-year mean actual evapotranspiration) is a vegetation flux. Copied from the
    template. Read only by biological nitrogen fixation, which `with_nitrogen "no"` switches off.

The field-by-field source map is in `climate_buffer_from_forcing`'s docstring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import ClmReader

Array = npt.NDArray[np.float64]

NDAYYEAR = 365
NDAYMONTH: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
NMONTH = 12
NDAYS = 31  # climbuf.h: the daily shift registers hold one month
CLIMBUF_SIZE = 20  # climbuf.h: the min/max ring buffers hold 20 years
NTREE = 7

# climbuf.c `#define k (1.0/12.0)` and `#define kk 0.05`. Written as the C writes them, so that
# `1 - _K` and `1 - _KK` round exactly as the compiler folds them.
_K = 1.0 / 12.0
_KK = 0.05
_UNSET = -9999.0  # new_climbuf's "never written" value; the C tests `< -9998`
_UNSET_TEST = -9998.0

PRIESTLEY_TAYLOR = 1.32  # soil.h
_DAYSECONDS = 86400.0  # petpar2.c

# `setseed` (numeric/setseed.c) with USE_RAND48: the 48-bit state is (13070, start % 65536,
# start / 65536), low word first. `erand48` is glibc's: the multiplier and increment below, and the
# double it returns is exactly the new 48-bit state divided by 2^48.
_RAND48_A = 0x5DEECE66D
_RAND48_C = 0xB
_RAND48_MASK = (1 << 48) - 1
_RAND48_LOW = 13070

# Vernalisation parameters of the twelve crops, (tv_opt.low, tv_opt.high, pvd_max), in the order
# `par/pft_lpjmlfit.js` lists them after the ten natural PFTs: temperate cereals, rice, maize,
# tropical cereals, pulses, temperate roots, tropical roots, sunflower, soybean, groundnut,
# rapeseed, sugarcane. Read off `cpp -P par/pft_lpjmlfit.js`; the test suite re-reads the file.
# They feed only `V_req`/`V_req_a`, which only crops read -- carried so the buffer is complete.
CROP_VERNALISATION: tuple[tuple[float, float, float], ...] = (
    (3.0, 10.0, 70.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 0.0),
    (1000.0, 1000.0, 70.0),
    (1000.0, 1000.0, 70.0),
    (3.0, 10.0, 70.0),
    (1000.0, 1000.0, 0.0),
)
_VERNAL_MONTHS = 5  # update_annual.c `#define N 5`


@dataclass(frozen=True)
class TreeBioclim:
    """The climate limits LPJmL-FIT applies to one tree type, from `par/pft_lpjmlfit.js`.

    temp_low / temp_high  "temp" {low, high}: `survive()` needs the 20-year mean coldest month
                          >= low; `establish()` additionally needs it <= high
    min_temprange         `survive()` needs warmest20 - coldest20 >= this
    gdd5min, gddbase      `establish()` needs this year's degree-days above gddbase >= gdd5min
    aprec_min             establishment needs this year's precipitation >= this (mm)
    stressed_low/high     "temp_stressed": each day outside this range is a temperature-stress day
    mort_temp_factor      mortality_tree_ind: mort_temp = factor * stress_days / 365, capped at 1
    """

    name: str
    temp_low: float
    temp_high: float
    min_temprange: float
    gdd5min: float
    gddbase: float
    aprec_min: float
    stressed_low: float
    stressed_high: float
    mort_temp_factor: float


# In PFT-id order. Every value read off `cpp -P par/pft_lpjmlfit.js`; the test suite re-reads it.
TREE_BIOCLIM: tuple[TreeBioclim, ...] = (
    TreeBioclim(
        "tropical broadleaved evergreen", 2.5, 1000.0, -1000.0, 0.0, 5.0, 100.0, 12.5, 54.0, 5.0
    ),
    TreeBioclim(
        "temperate needleleaved evergreen",
        -30.0,
        1000.0,
        -1000.0,
        900.0,
        5.0,
        100.0,
        -15.0,
        54.0,
        5.0,
    ),
    TreeBioclim(
        "temperate broadleaved evergreen",
        -15.0,
        1000.0,
        -1000.0,
        1200.0,
        5.0,
        100.0,
        -10.0,
        54.0,
        5.0,
    ),
    TreeBioclim(
        "temperate broadleaved summergreen",
        -30.0,
        1000.0,
        -1000.0,
        1200.0,
        5.0,
        100.0,
        -20.0,
        54.0,
        5.0,
    ),
    TreeBioclim(
        "boreal needleleaved evergreen", -80.0, 0.0, -1000.0, 350.0, 5.0, 100.0, -45.0, 54.0, 5.0
    ),
    TreeBioclim(
        "boreal broadleaved summergreen", -80.0, 0.0, -1000.0, 350.0, 5.0, 100.0, -45.0, 54.0, 5.0
    ),
    TreeBioclim(
        "boreal needleleaved summergreen", -80.0, 0.0, 30.0, 350.0, 5.0, 100.0, -70.0, 54.0, 5.0
    ),
)

# climate.h: the day each hemisphere's temperature-stress counter is zeroed (tempstress_tree.c).
COLDEST_DAY_NH = 14
COLDEST_DAY_SH = 195


@dataclass(frozen=True)
class SpinupProtocol:
    """How the spin-up walked through its forcing years. Defaults are the pilot's.

    `iterate.c`: the loop runs over `firstyear - nspinup .. lastyear`; a year before the forcing
    file's own first year is a spin-up year and, with `shuffle`, draws a random one of the first
    `nspinyear` stored years; every later year reads its own year from the file. With the pilot's
    firstyear 2000, lastyear 1999, nspinup 1000 and a 1970-1999 file that is 970 shuffled years and
    then the 30 file years in order, and the restart is written at the end of 1999.

    `v_req_every_year` is the sowing-date switch in `update_annual.c`: the restart header of every
    pilot run records `sdate_option 0` (NO_FIXED_SDATE, whatever the config text says), under which
    `V_req` and `atemp_mean20_fix` are updated every year. Measured, not assumed: with it the
    replayed `atemp_mean20_fix` equals the restart's.
    """

    nspinup: int = 1000
    nspinyear: int = 30
    random_seed: int = 1
    shuffle: bool = True
    firstyear: int = 2000
    lastyear: int = 1999
    climate_firstyear: int = 1970
    v_req_every_year: bool = True

    def until(self, year: int) -> SpinupProtocol:
        """The same run, stopped at the END of model year `year`: the buffer the model held then.

        `lastyear` is where `iterate.c`'s loop ends, so a replay with an earlier `lastyear` is the
        prefix of the full one -- the same draws in the same order, cut short. That is how the
        stored global spin-up's state at the end of its constant-CO2 stretch (model year 1699) is
        recovered, although that run only ever wrote a restart at 1999.
        """
        if not self.firstyear - self.nspinup <= year:
            raise ValueError(
                f"year {year} is before the run's first year {self.firstyear - self.nspinup}"
            )
        return replace(self, lastyear=int(year))

    def years_needed(self) -> int:
        """How many forcing years, from `climate_firstyear`, the schedule reads (max index + 1)."""
        idx, _ = self.schedule()
        return int(idx.max()) + 1 if idx.size else 0

    def schedule(self) -> tuple[npt.NDArray[np.int64], tuple[int, int, int]]:
        """The forcing-year INDEX read in every simulated year, and the RNG state left behind.

        The second value is what `fwriterestart.c:93` writes into the restart header, so comparing
        it with a real file's header proves the replayed sequence without looking at a single
        climate value.
        """
        x = _RAND48_LOW | ((self.random_seed % 65536) << 16) | ((self.random_seed // 65536) << 32)
        out: list[int] = []
        for year in range(self.firstyear - self.nspinup, self.lastyear + 1):
            if year < self.climate_firstyear:
                if self.shuffle:
                    x = (_RAND48_A * x + _RAND48_C) & _RAND48_MASK
                    out.append(int((x / float(1 << 48)) * self.nspinyear))
                else:
                    out.append((year - self.firstyear + self.nspinup) % self.nspinyear)
            else:
                out.append(year - self.climate_firstyear)
        seed = (x & 0xFFFF, (x >> 16) & 0xFFFF, (x >> 32) & 0xFFFF)
        return np.asarray(out, dtype=np.int64), seed


PILOT_PROTOCOL = SpinupProtocol()

# THE STORED GLOBAL SPIN-UP (`ground_truth.historical_seed1`), read off its own saved config
# (`scripts_for_running_the_model/lpjml_2000_2019.js`: nspinup 1000, nspinyear 30, firstyear 2000,
# lastyear 1999, random_seed 1, shuffle_climate true) and its log ("Spinup using climate starting
# from year 1901"). Same loop as the pilot's, different split: the forcing file starts in 1901, so
# model years 1000-1900 are 901 shuffled draws of 1901-1930 and 1901-1999 are the file's own years
# in order -- 901 + 99, where the pilot's 1970-1999 files give 970 + 30. Its restart header records
# `sdate_option 0`, so V_req is updated every year as in the pilot. Checked, not assumed: 901 draws
# from seed 1 leave the 48-bit state (10901, 14779, 51459), which is what `restart_1999`'s header
# holds. `STORED_SPINUP.until(1699)` is its buffer at the end of the constant-CO2 stretch.
STORED_SPINUP = SpinupProtocol(
    nspinup=1000,
    nspinyear=30,
    random_seed=1,
    shuffle=True,
    firstyear=2000,
    lastyear=1999,
    climate_firstyear=1901,
    v_req_every_year=True,
)


@dataclass
class Forcing:
    """One cell's daily forcing, (nyear, 365) each, in the units the model reads."""

    temp: Array  # deg C
    prec: Array  # mm/day
    swdown: Array  # W/m2
    lwnet: Array  # W/m2, net longwave (the "radiation" setting: not downward)
    lat: float
    firstyear: int

    @property
    def nyear(self) -> int:
        return int(self.temp.shape[0])


def read_forcing(files: dict[str, Any], cell: int, lat: float) -> Forcing:
    """Read the four forcing inputs the buffer needs for one cell, every year of the files.

    `files` maps "temp", "prec", "swdown", "lwnet" to `.clm` paths. The header is always parsed
    (the input set is MIXED between float32 and scaled int16), and a float32 value widens to a
    double exactly, which is what makes an exact replay possible at all.
    """
    readers = {k: ClmReader(files[k]) for k in ("temp", "prec", "swdown", "lwnet")}
    first = {r.header.firstyear for r in readers.values()}
    last = {r.header.lastyear for r in readers.values()}
    if len(first) != 1 or len(last) != 1:
        raise ValueError(f"forcing files cover different years: {first} .. {last}")
    y0, y1 = first.pop(), last.pop()
    data = {k: r.cell_years(cell, y0, y1) for k, r in readers.items()}
    for k, v in data.items():
        if v.shape[1] != NDAYYEAR:
            raise ValueError(f"{k}: {v.shape[1]} bands, expected daily ({NDAYYEAR})")
    return Forcing(
        temp=data["temp"],
        prec=data["prec"],
        swdown=data["swdown"],
        lwnet=data["lwnet"],
        lat=float(lat),
        firstyear=y0,
    )


def _month_bounds() -> list[tuple[int, int]]:
    edges = np.cumsum((0, *NDAYMONTH))
    return [(int(edges[m]), int(edges[m + 1])) for m in range(NMONTH)]


_MONTHS = _month_bounds()


def _sequential_sum(x: Array) -> float:
    """A left-to-right double sum, as the C accumulates a month day by day. `np.sum` is pairwise
    and would round differently in the last place; `cumsum` is the sequential recurrence."""
    return float(np.cumsum(x)[-1]) if x.size else 0.0


def daily_pet(forcing: Forcing, albedo: Array) -> Array:
    """`petpar2.c` equilibrium evapotranspiration x Priestley-Taylor, (nyear, 365), for a given
    MONTHLY albedo. The model uses each patch's own daily albedo; this uses one value per month."""
    day = np.arange(1, NDAYYEAR + 1, dtype=np.float64)
    delta = np.deg2rad(-23.4 * np.cos(2.0 * math.pi * (day + 10.0) / NDAYYEAR))
    u = math.sin(math.radians(forcing.lat)) * np.sin(delta)
    v = math.cos(math.radians(forcing.lat)) * np.cos(delta)
    with np.errstate(invalid="ignore", divide="ignore"):
        hh = np.arccos(np.clip(-u / v, -1.0, 1.0))
    daylength = np.where(u >= v, 24.0, np.where(u <= -v, 0.0, 24.0 * hh / math.pi))
    t = forcing.temp
    s = 2.503e6 * np.exp(17.269 * t / (237.3 + t)) / ((237.3 + t) * (237.3 + t))
    gamma = 65.05 + t * 0.064
    lam = 2.495e6 - t * 2380.0
    beta = np.empty(NDAYYEAR)
    for m, (a, b) in enumerate(_MONTHS):
        beta[a:b] = float(np.asarray(albedo, dtype=np.float64).reshape(-1)[m % np.size(albedo)])
    rad = (1.0 - beta)[None, :] * forcing.swdown + forcing.lwnet * (daylength / 24.0)[None, :]
    eeq = _DAYSECONDS * (s / (s + gamma) / lam) * rad
    out: Array = np.maximum(eeq, 0.0) * PRIESTLEY_TAYLOR
    return out


@dataclass
class YearAggregates:
    """Everything the buffer needs from ONE forcing year, computed the way the C computes it."""

    mtemp: Array  # (nyear, 12) monthly mean temperature: sequential daily sum / days
    mprec: Array  # (nyear, 12) monthly precipitation sum
    temp_min: Array  # (nyear,) coldest monthly mean
    temp_max: Array  # (nyear,) warmest monthly mean
    gdd5: Array  # (nyear,) days above 5 C
    aprec: Array  # (nyear,) annual precipitation (establishment's `aprec`)


def year_aggregates(forcing: Forcing) -> YearAggregates:
    n = forcing.nyear
    mtemp = np.empty((n, NMONTH))
    mprec = np.empty((n, NMONTH))
    for y in range(n):
        for m, (a, b) in enumerate(_MONTHS):
            mtemp[y, m] = _sequential_sum(forcing.temp[y, a:b]) / NDAYMONTH[m]
            mprec[y, m] = _sequential_sum(forcing.prec[y, a:b])
    aprec = np.array([_sequential_sum(forcing.prec[y]) for y in range(n)])
    return YearAggregates(
        mtemp=mtemp,
        mprec=mprec,
        temp_min=mtemp.min(axis=1),
        temp_max=mtemp.max(axis=1),
        gdd5=(forcing.temp > 5.0).sum(axis=1).astype(np.float64),
        aprec=aprec,
    )


class _Ring:
    """`numeric/buffer.c`, operation for operation, so `sum` carries the C's own rounding."""

    def __init__(self, size: int) -> None:
        self.size = size
        self.n = 0
        self.index = 0
        self.sum = 0.0
        self.data = np.zeros(size)

    def update(self, val: float) -> None:
        if self.n < self.size:
            self.data[self.n] = val
            self.n += 1
            self.sum += val
        else:
            self.sum -= float(self.data[self.index])
            self.data[self.index] = val
            self.index = (self.index + 1) % self.size
            self.sum += val

    def avg(self) -> float:
        return self.sum / self.n

    def as_record(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "n": self.n,
            "index": self.index,
            "sum": self.sum,
            "data": self.data[: self.n].astype(np.float64).copy(),
        }


@dataclass
class ClimbufTrace:
    """The buffer's history over the simulated years, for the bioclimatic rule."""

    climate_index: npt.NDArray[np.int64]  # forcing-year index read in each simulated year
    temp_min20: Array  # getbufferavg(min) after each year's annual update
    temp_max20: Array
    seed_after: tuple[int, int, int]


def _five_coldest(mtemp20: Array) -> list[float]:
    """`getmintemp20_n` with n = 5: the selection sort's output is the five smallest, ascending."""
    return [float(v) for v in np.sort(mtemp20)[:_VERNAL_MONTHS]]


def climate_buffer_from_forcing(
    forcing: Forcing,
    *,
    protocol: SpinupProtocol = PILOT_PROTOCOL,
    albedo: Array | float = 0.17,
    aetp_mean: float = 0.0,
    stand_frac: float = 1.0,
) -> tuple[dict[str, Any], ClimbufTrace]:
    """The end-of-spin-up climate buffer, replayed from the forcing year by year.

    Source of each field of the record (`_read_climbuf` layout):

      temp_max, temp_min      EXACT  last year's warmest / coldest monthly mean (init_annual resets)
      atemp_mean              EXACT  monthly exponential mean, weight 1/12
      aetp_mean               GIVEN  vegetation flux; pass the template's (inert without nitrogen)
      atemp_mean20            EXACT  annual exponential mean (weight 0.05) of the annual mean temp
      atemp_mean20_fix        EXACT  = atemp_mean20 under the pilot's sowing-date setting
      gdd5                    EXACT  last year's count of days above 5 C
      dval_prec[0]            EXACT  0: written only by the monthly weather generator, which is off
      temp[31], prec[31]      EXACT  the last 31 daily values of the last year
      mprec20, mtemp20        EXACT  per-month exponential means, weight 0.05
      mpet20                  APPROX needs the vegetation's albedo; `albedo` is one value per month
      V_req, V_req_a          EXACT  crop vernalisation from mtemp20 and CROP_VERNALISATION
      min, max ring buffers   EXACT  20-year coldest / warmest month; `sum` accumulated as in C

    "EXACT" is a claim about the arithmetic and the year sequence; it is checked against every
    pilot restart by `scripts/synth_pilot.py --stage bank`, which reports the residual per field.

    The forcing must START at `protocol.climate_firstyear` and cover every year the schedule reads:
    the first `nspinyear` for a run that stops inside its shuffled years (the pilot; the stored
    spin-up stopped at 1699), more for one that goes on into the file's own years in order (the
    stored spin-up to 1999 reads 1901-1999). Extra years at the end are ignored.
    """
    check_forcing_covers(forcing, protocol)
    idx, seed = protocol.schedule()
    agg = year_aggregates(forcing)
    pet = daily_pet(forcing, np.asarray(albedo, dtype=np.float64)) * stand_frac
    mpet = np.array(
        [[_sequential_sum(pet[y, a:b]) for a, b in _MONTHS] for y in range(forcing.nyear)]
    )
    ncft = len(CROP_VERNALISATION)

    atemp_mean = 0.0
    atemp_mean20 = _UNSET
    atemp_mean20_fix = 0.0
    mprec20 = np.full(NMONTH, _UNSET)
    mpet20 = np.full(NMONTH, _UNSET)
    mtemp20 = np.full(NMONTH, _UNSET)
    v_req = np.full(ncft, _UNSET)
    v_req_a = np.zeros(ncft)
    ring_min, ring_max = _Ring(CLIMBUF_SIZE), _Ring(CLIMBUF_SIZE)
    tmin20 = np.empty(idx.size)
    tmax20 = np.empty(idx.size)

    for n, cy in enumerate(idx):
        atemp = 0.0
        v_req_a = np.zeros(ncft)
        for m in range(NMONTH):
            mt, mp, me = float(agg.mtemp[cy, m]), float(agg.mprec[cy, m]), float(mpet[cy, m])
            atemp_mean = (1 - _K) * atemp_mean + _K * mt
            mprec20[m] = mp if mprec20[m] < _UNSET_TEST else (1 - _KK) * mprec20[m] + _KK * mp
            mpet20[m] = me if mpet20[m] < _UNSET_TEST else (1 - _KK) * mpet20[m] + _KK * me
            mtemp20[m] = mt if mtemp20[m] < _UNSET_TEST else (1 - _KK) * mtemp20[m] + _KK * mt
            atemp += mt * _K
        # update_annual.c: vernalisation from the five coldest 20-year months, THEN annual_climbuf.
        if protocol.v_req_every_year:
            for mint in _five_coldest(mtemp20):
                for c, (low, high, pvd) in enumerate(CROP_VERNALISATION):
                    if mint <= low and mint > _UNSET:
                        v_req_a[c] += pvd / _VERNAL_MONTHS
                    elif low < mint < high:
                        v_req_a[c] += pvd / _VERNAL_MONTHS * (1 - (mint - low) / (high - low))
        ring_min.update(float(agg.temp_min[cy]))
        ring_max.update(float(agg.temp_max[cy]))
        atemp_mean20 = (
            atemp if atemp_mean20 < _UNSET_TEST else (1 - _KK) * atemp_mean20 + _KK * atemp
        )
        if protocol.v_req_every_year:
            for c in range(ncft):
                v_req[c] = (
                    v_req_a[c]
                    if v_req[c] < _UNSET_TEST
                    else (1 - _KK) * v_req[c] + _KK * v_req_a[c]
                )
            atemp_mean20_fix = atemp_mean20
        tmin20[n] = ring_min.avg()
        tmax20[n] = ring_max.avg()

    last = int(idx[-1])
    buf = {
        "scalars": np.array(
            [
                float(agg.temp_max[last]),
                float(agg.temp_min[last]),
                atemp_mean,
                float(aetp_mean),
                atemp_mean20,
                atemp_mean20_fix,
                float(agg.gdd5[last]),
            ],
            dtype=np.float64,
        ),
        "dval_prec0": 0.0,
        "temp": forcing.temp[last, -NDAYS:].astype(np.float64).copy(),
        "prec": forcing.prec[last, -NDAYS:].astype(np.float64).copy(),
        "mpet20": mpet20.copy(),
        "mprec20": mprec20.copy(),
        "mtemp20": mtemp20.copy(),
        "V_req": v_req.copy(),
        "V_req_a": v_req_a.copy(),
        "min": ring_min.as_record(),
        "max": ring_max.as_record(),
    }
    return buf, ClimbufTrace(idx, tmin20, tmax20, seed)


def check_forcing_covers(forcing: Forcing, protocol: SpinupProtocol) -> None:
    """Refuse a forcing that does not start where the protocol's file starts, or is too short.

    Both faults would otherwise replay silently: an index into the wrong year, or an IndexError
    deep in the loop. The old rule was "exactly `nspinyear` years", which is right for the pilot
    and wrong for a run that reads the file's own years after its shuffled ones.
    """
    if forcing.firstyear != protocol.climate_firstyear:
        raise ValueError(
            f"forcing starts in {forcing.firstyear}; the protocol's climate starts in "
            f"{protocol.climate_firstyear}"
        )
    need = max(protocol.years_needed(), protocol.nspinyear if protocol.shuffle else 0)
    if forcing.nyear < need:
        raise ValueError(
            f"forcing has {forcing.nyear} years; the protocol reads {need} "
            f"({protocol.climate_firstyear}-{protocol.climate_firstyear + need - 1})"
        )


def ema_year_weights(protocol: SpinupProtocol = PILOT_PROTOCOL, nyear: int | None = None) -> Array:
    """Weight of each FORCING year in a 0.05-exponential mean at the end of the spin-up.

    The first simulated year initialises the mean (the `< -9998` branch) and every later one decays
    it by 0.95, so the end value is linear in the per-year inputs with these weights (summing to 1).
    Used only for the albedo solve, where a linear model is what is wanted; the exact replay above
    never uses it. One weight per forcing year: `nyear` of them (default `nspinyear`), and never
    fewer than the schedule reads.
    """
    idx, _ = protocol.schedule()
    n = idx.size
    w_sim = _KK * (1 - _KK) ** (n - 1 - np.arange(n, dtype=np.float64))
    w_sim[0] = (1 - _KK) ** (n - 1)
    length = protocol.nspinyear if nyear is None else int(nyear)
    if length < protocol.years_needed():
        raise ValueError(f"{length} forcing years; the schedule reads {protocol.years_needed()}")
    out: Array = np.bincount(idx, weights=w_sim, minlength=length).astype(np.float64)
    return out


def effective_albedo(
    climbuf: dict[str, Any],
    forcing: Forcing,
    *,
    protocol: SpinupProtocol = PILOT_PROTOCOL,
    stand_frac: float = 1.0,
) -> Array:
    """The monthly albedo at which a REAL buffer's own forcing reproduces its own `mpet20`.

    Bisection per month on [0, 1]: `mpet20` decreases monotonically in the albedo (more reflected
    shortwave, less available energy). A month whose value cannot be matched inside [0, 1] -- a
    polar night with no shortwave at all, where the albedo does not matter -- keeps the bound it
    reached. This is a calibration of the TEMPLATE's vegetation and snow, carried to the target's
    forcing: the approximation is that the albedo does not change with the climate.

    `protocol` must be the one that made `climbuf`: its year weights are what the solve inverts.
    """
    check_forcing_covers(forcing, protocol)
    w = ema_year_weights(protocol, forcing.nyear)
    want = np.asarray(climbuf["mpet20"], dtype=np.float64)
    lo: Array = np.zeros(NMONTH)
    hi: Array = np.ones(NMONTH)

    def monthly(beta: Array) -> Array:
        pet = daily_pet(forcing, beta) * stand_frac
        per_year = np.stack([pet[:, a:b].sum(axis=1) for a, b in _MONTHS], axis=1)
        out: Array = (w[:, None] * per_year).sum(axis=0)
        return out

    for _ in range(40):
        mid = 0.5 * (lo + hi)
        too_high = monthly(mid) > want  # PET still above target -> need a higher albedo
        lo = np.asarray(np.where(too_high, mid, lo), dtype=np.float64)
        hi = np.asarray(np.where(too_high, hi, mid), dtype=np.float64)
    solved: Array = 0.5 * (lo + hi)
    return solved


@dataclass
class BioclimVerdict:
    """Per tree type, what the target climate lets it do. All arrays are length NTREE."""

    survive_final: npt.NDArray[np.bool_]  # survive() on the end-of-spin-up buffer
    survive_window_frac: Array  # fraction of the last `window` years in which survive() held
    establish_window_frac: Array  # fraction of the last `window` years establish() held
    mort_temp_mean: Array  # mean annual temperature-stress mortality over the forcing years
    temp_min20: float
    temp_max20: float

    def admissible(self, *, min_establish_frac: float, max_mort_temp: float) -> tuple[int, ...]:
        ok = (
            self.survive_final
            & (self.establish_window_frac >= min_establish_frac)
            & (self.mort_temp_mean <= max_mort_temp)
        )
        return tuple(int(t) for t in np.flatnonzero(ok))


def stress_days(forcing: Forcing, low: float, high: float) -> Array:
    """Temperature-stress days counted at the year-end mortality check (`tempstress_tree.c`).

    The counter is zeroed on the hemisphere's coldest day, AFTER that day's increment, so what the
    annual mortality sees is the count over the days after it: 15..365 north, 196..365 south.
    """
    reset = COLDEST_DAY_NH if forcing.lat >= 0.0 else COLDEST_DAY_SH
    t = forcing.temp[:, reset:]
    out: Array = ((t < low) | (t > high)).sum(axis=1).astype(np.float64)
    return out


def bioclimatic_verdict(
    forcing: Forcing, trace: ClimbufTrace, *, window: int | None = None
) -> BioclimVerdict:
    """Apply the model's own climate limits (`survive.c`, `establish.c`, `mortality_tree_ind.c`).

    Establishment in simulated year n reads that year's degree-days and precipitation and the ring
    buffers AFTER that year's annual update -- `update_annual` runs `annual_climbuf` before
    `annual_stand` -- which is exactly what `trace` records.

    ⚠ THE WINDOW IS THE WHOLE SPIN-UP BY DEFAULT, AND THAT WAS MEASURED, NOT CHOSEN. Over only the
    last 30 years -- the forcing years read in order -- types that ARE in the true end state come
    out as never able to establish, because a marginal type's 20-year coldest-month mean sits near
    its limit and the shuffled centuries before 1970 contained windows the ordered one does not. A
    type that could establish at any point of the replayed spin-up can hold long-lived stems now.
    """
    agg = year_aggregates(forcing)
    n = trace.climate_index.size
    w = n if window is None else min(window, n)
    tail = slice(n - w, n)
    cy = trace.climate_index[tail]
    tmin, tmax = trace.temp_min20[tail], trace.temp_max20[tail]
    surv_final = np.zeros(NTREE, dtype=bool)
    surv_frac = np.zeros(NTREE)
    est_frac = np.zeros(NTREE)
    mort = np.zeros(NTREE)
    for t, par in enumerate(TREE_BIOCLIM):
        surv = (tmin >= par.temp_low) & (tmax - tmin >= par.min_temprange)
        gdd = np.clip(forcing.temp - par.gddbase, 0.0, None).sum(axis=1)[cy]
        est = (
            (agg.aprec[cy] >= par.aprec_min)
            & (tmin >= par.temp_low)
            & (tmin <= par.temp_high)
            & (gdd >= par.gdd5min)
            & ~(tmax <= 10.0)
        )
        surv_final[t] = bool(surv[-1])
        surv_frac[t] = float(surv.mean())
        est_frac[t] = float(est.mean())
        days = stress_days(forcing, par.stressed_low, par.stressed_high)
        mort[t] = float(np.minimum(1.0, par.mort_temp_factor * days / NDAYYEAR).mean())
    return BioclimVerdict(
        survive_final=surv_final,
        survive_window_frac=surv_frac,
        establish_window_frac=est_frac,
        mort_temp_mean=mort,
        temp_min20=float(trace.temp_min20[-1]),
        temp_max20=float(trace.temp_max20[-1]),
    )


def compare_climbuf(ours: dict[str, Any], real: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Per field, the max absolute and max relative difference between two buffers.

    Relative is |a-b| / max(|b|, 1e-12). The ring buffers are compared on `sum`, `data` and the
    integer bookkeeping, because `survive()` reads `sum / n` and not the data.
    """
    out: dict[str, dict[str, float]] = {}

    def put(name: str, ours_v: Any, real_v: Any) -> None:
        a = np.asarray(ours_v, dtype=np.float64).reshape(-1)
        b = np.asarray(real_v, dtype=np.float64).reshape(-1)
        if a.shape != b.shape:
            out[name] = {"max_abs": math.inf, "max_rel": math.inf}
            return
        d = np.abs(a - b)
        rel = d / np.maximum(np.abs(b), 1e-12)
        out[name] = {
            "max_abs": float(d.max()) if d.size else 0.0,
            "max_rel": float(rel.max()) if rel.size else 0.0,
        }

    names = ("temp_max", "temp_min", "atemp_mean", "aetp_mean", "atemp_mean20", "atemp_mean20_fix")
    for i, name in enumerate((*names, "gdd5")):
        put(name, ours["scalars"][i], real["scalars"][i])
    for key in ("dval_prec0", "temp", "prec", "mpet20", "mprec20", "mtemp20", "V_req", "V_req_a"):
        put(key, ours[key], real[key])
    for ring in ("min", "max"):
        put(f"{ring}.sum", ours[ring]["sum"], real[ring]["sum"])
        put(f"{ring}.data", ours[ring]["data"], real[ring]["data"])
        put(
            f"{ring}.bookkeeping",
            [ours[ring]["size"], ours[ring]["n"], ours[ring]["index"]],
            [real[ring]["size"], real[ring]["n"], real[ring]["index"]],
        )
    return out
