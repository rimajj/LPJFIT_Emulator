"""The climate buffer is DERIVED from the forcing, and must be derived the way the C derives it.

Two layers, as for the restart round-trip:
  * SYNTHETIC (runs anywhere). The spin-up year sequence, the ring-buffer arithmetic, the
    exponential means and the bioclimatic rule, each on a forcing whose answer is known.
  * REAL FILE (`needs_real_data`). Three pilot runs, replayed from their own forcing and compared
    with their own end-of-spin-up restart field by field; and the parameter tables re-read from the
    model's own `par/pft_lpjmlfit.js`, so a transcription slip cannot survive.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from vegemu.binfmt.clm import read_grid
from vegemu.binfmt.restart import RestartReader
from vegemu.models import climbuf as cb
from vegemu.models.spinup_rule import forcing_files
from vegemu.paths import path, paths

NYEAR = 30
CONTROL = "control"


def _forcing(temp: float | np.ndarray, *, lat: float = 50.0, prec: float = 2.0) -> cb.Forcing:
    t = np.broadcast_to(np.asarray(temp, dtype=np.float64), (NYEAR, cb.NDAYYEAR)).copy()
    return cb.Forcing(
        temp=t,
        prec=np.full((NYEAR, cb.NDAYYEAR), prec),
        swdown=np.full((NYEAR, cb.NDAYYEAR), 150.0),
        lwnet=np.full((NYEAR, cb.NDAYYEAR), -50.0),
        lat=lat,
        firstyear=1970,
    )


# ---------------------------------------------------------------------------------------------
# The spin-up year sequence.
# ---------------------------------------------------------------------------------------------
def test_the_schedule_is_970_shuffled_years_then_the_file_in_order() -> None:
    idx, _ = cb.PILOT_PROTOCOL.schedule()
    assert idx.size == 1000
    assert idx.min() >= 0 and idx.max() < NYEAR
    assert list(idx[-NYEAR:]) == list(range(NYEAR))
    # Shuffled, not cycled: a cycle would repeat with period 30.
    assert not np.array_equal(idx[:30], idx[30:60])


def test_the_rng_state_left_behind_is_the_one_every_pilot_header_records() -> None:
    """(22144, 14021, 77) is `config->seed` in the header of every pilot restart (random_seed 1).

    This pins the whole shuffle: a wrong multiplier, increment, seeding or draw count lands on a
    different 48-bit state, and the check needs no file.
    """
    _, seed = cb.PILOT_PROTOCOL.schedule()
    assert seed == (22144, 14021, 77)


def test_without_shuffle_the_spinup_cycles() -> None:
    idx, _ = cb.SpinupProtocol(shuffle=False).schedule()
    assert list(idx[:3]) == [0, 1, 2]
    assert np.array_equal(idx[:30], idx[30:60])


def test_the_stored_run_is_901_shuffled_years_then_1901_1999_in_order() -> None:
    """The stored global spin-up's protocol, and the RNG state its restart_1999 header records.

    (10901, 14779, 51459) is `config->seed` in `ground_truth.restart_spinup_end`'s header: 901
    draws from random_seed 1. Pinned here so the protocol needs no file to be checked.
    """
    idx, seed = cb.STORED_SPINUP.schedule()
    assert idx.size == 1000
    assert (idx[:901] < NYEAR).all()
    assert list(idx[901:]) == list(range(99))
    assert seed == (10901, 14779, 51459)
    assert cb.STORED_SPINUP.years_needed() == 99


def test_stopping_early_is_the_prefix_of_the_full_run() -> None:
    full, _ = cb.STORED_SPINUP.schedule()
    stop = cb.STORED_SPINUP.until(1699)
    idx, seed = stop.schedule()
    assert idx.size == 700 and np.array_equal(idx, full[:700])
    assert stop.years_needed() <= NYEAR
    # 700 draws, not 901: the state a 1699 restart would have carried.
    assert seed != cb.STORED_SPINUP.schedule()[1]
    with pytest.raises(ValueError, match="before the run"):
        cb.STORED_SPINUP.until(999)


def _long_forcing(nyear: int, firstyear: int = 1901) -> cb.Forcing:
    """A forcing whose every year is distinguishable, so a wrong year index cannot hide."""
    base = 10.0 + 8.0 * np.sin(2 * np.pi * (np.arange(cb.NDAYYEAR) - 100) / cb.NDAYYEAR)
    temp = base[None, :] + 0.37 * np.arange(nyear, dtype=np.float64)[:, None]
    return cb.Forcing(
        temp=temp,
        prec=np.full((nyear, cb.NDAYYEAR), 2.0) + 0.01 * np.arange(nyear)[:, None],
        swdown=np.full((nyear, cb.NDAYYEAR), 150.0),
        lwnet=np.full((nyear, cb.NDAYYEAR), -50.0),
        lat=50.0,
        firstyear=firstyear,
    )


def test_the_1999_replay_reads_the_file_years_in_order_and_needs_all_of_them() -> None:
    f = _long_forcing(99)
    buf, trace = cb.climate_buffer_from_forcing(f, protocol=cb.STORED_SPINUP)
    # The last simulated year is 1999 = forcing index 98, so the daily registers are its last days.
    assert np.array_equal(buf["temp"], f.temp[98, -31:])
    assert list(trace.climate_index[-3:]) == [96, 97, 98]
    with pytest.raises(ValueError, match="reads 99"):
        cb.climate_buffer_from_forcing(_long_forcing(30), protocol=cb.STORED_SPINUP)
    with pytest.raises(ValueError, match="starts in 1970"):
        cb.climate_buffer_from_forcing(_long_forcing(99, 1970), protocol=cb.STORED_SPINUP)


def test_the_1699_buffer_needs_only_the_first_30_years() -> None:
    """Stopped at 1699 every year is a shuffled draw of 1901-1930, so extra years change nothing."""
    stop = cb.STORED_SPINUP.until(1699)
    short, t_short = cb.climate_buffer_from_forcing(_long_forcing(30), protocol=stop)
    long, t_long = cb.climate_buffer_from_forcing(_long_forcing(99), protocol=stop)
    err = cb.compare_climbuf(short, long)
    assert all(v["max_abs"] == 0.0 for v in err.values()), err
    assert t_short.seed_after == t_long.seed_after == stop.schedule()[1]


def test_effective_albedo_on_the_stored_protocol_recovers_the_albedo() -> None:
    f = _long_forcing(99)
    made, _ = cb.climate_buffer_from_forcing(f, protocol=cb.STORED_SPINUP, albedo=0.23)
    got = cb.effective_albedo(made, f, protocol=cb.STORED_SPINUP)
    assert np.allclose(got, 0.23, atol=1e-6)
    # The year weights cover the file's years, and those the schedule never reads weigh nothing.
    w = cb.ema_year_weights(cb.STORED_SPINUP, 119)
    assert w.size == 119 and w[99:].sum() == 0.0 and w.sum() == pytest.approx(1.0)


# ---------------------------------------------------------------------------------------------
# The buffer arithmetic.
# ---------------------------------------------------------------------------------------------
def test_a_constant_climate_gives_a_constant_buffer() -> None:
    buf, trace = cb.climate_buffer_from_forcing(_forcing(12.5))
    temp_max, temp_min, atemp_mean, _, atemp_mean20, fix, gdd5 = buf["scalars"]
    assert temp_max == temp_min == 12.5
    assert np.allclose(buf["mtemp20"], 12.5)
    assert abs(atemp_mean20 - 12.5) < 1e-9 and fix == atemp_mean20
    assert abs(atemp_mean - 12.5) < 1e-9
    assert gdd5 == 365.0
    assert buf["min"]["n"] == buf["max"]["n"] == cb.CLIMBUF_SIZE
    assert buf["min"]["sum"] / buf["min"]["n"] == pytest.approx(12.5)
    assert trace.temp_min20[-1] == pytest.approx(12.5)
    # Monthly precipitation is a SUM of the days, not a mean.
    assert np.allclose(buf["mprec20"], 2.0 * np.array(cb.NDAYMONTH))
    assert buf["dval_prec0"] == 0.0


def test_the_ring_index_after_1000_years_is_where_the_c_leaves_it() -> None:
    """20 slots filled, then 980 replacements: the next slot to replace is 980 % 20 = 0."""
    buf, _ = cb.climate_buffer_from_forcing(_forcing(5.0))
    assert buf["min"]["index"] == (1000 - cb.CLIMBUF_SIZE) % cb.CLIMBUF_SIZE
    assert buf["min"]["size"] == cb.CLIMBUF_SIZE


def test_the_daily_registers_hold_the_last_31_days_of_the_last_year() -> None:
    temp = np.tile(np.arange(cb.NDAYYEAR, dtype=np.float64), (NYEAR, 1))
    temp[-1] += 100.0  # only the LAST forcing year is shifted
    buf, _ = cb.climate_buffer_from_forcing(_forcing(temp))
    assert np.array_equal(buf["temp"], temp[-1, -31:])


def test_vernalisation_follows_the_crop_table() -> None:
    """At 20 C no month is cold: temperate cereals get 0 days, soybean (1000/1000) its full 70."""
    buf, _ = cb.climate_buffer_from_forcing(_forcing(20.0))
    assert buf["V_req_a"][0] == 0.0
    assert buf["V_req_a"][8] == pytest.approx(70.0)
    assert buf["V_req"][8] == pytest.approx(70.0)


def test_effective_albedo_recovers_the_albedo_that_made_the_buffer() -> None:
    f = _forcing(15.0)
    made, _ = cb.climate_buffer_from_forcing(f, albedo=0.31)
    got = cb.effective_albedo(made, f)
    assert np.allclose(got, 0.31, atol=1e-6)


# ---------------------------------------------------------------------------------------------
# The bioclimatic rule.
# ---------------------------------------------------------------------------------------------
def test_a_hot_climate_admits_tropical_and_bars_boreal_establishment() -> None:
    f = _forcing(28.0)
    _, trace = cb.climate_buffer_from_forcing(f)
    v = cb.bioclimatic_verdict(f, trace)
    assert v.survive_final[0] and v.establish_window_frac[0] == 1.0
    # Boreal types SURVIVE any warmth (cold limit -80 C) but cannot ESTABLISH above 0 C.
    assert v.survive_final[4] and v.establish_window_frac[4] == 0.0
    allowed = v.admissible(min_establish_frac=1 / 30, max_mort_temp=0.5)
    assert 0 in allowed and 4 not in allowed


def test_a_cold_climate_kills_tropical_evergreen() -> None:
    f = _forcing(-5.0)
    _, trace = cb.climate_buffer_from_forcing(f)
    v = cb.bioclimatic_verdict(f, trace)
    assert not v.survive_final[0]  # coldest month -5 C < 2.5 C
    assert v.mort_temp_mean[0] == 1.0  # every day below 12.5 C
    assert 0 not in v.admissible(min_establish_frac=0.0, max_mort_temp=1.0)


def test_stress_days_restart_on_the_hemisphere_coldest_day() -> None:
    temp = np.full((NYEAR, cb.NDAYYEAR), 20.0)
    temp[:, : cb.COLDEST_DAY_NH] = -50.0  # cold only before the northern reset
    north = cb.stress_days(_forcing(temp, lat=45.0), -45.0, 54.0)
    south = cb.stress_days(_forcing(temp, lat=-45.0), -45.0, 54.0)
    assert north.max() == 0.0  # wiped by the reset on day 14
    assert south.max() == 0.0  # the southern count starts on day 196


# ---------------------------------------------------------------------------------------------
# Layer 2 -- real files.
# ---------------------------------------------------------------------------------------------
def _pilot(cell: int, point: str) -> tuple[Path, dict[str, Path]]:
    runs = Path(str(paths()["scratch"]["runs"])) / "pilot-v2-constco2" / f"c{cell}" / point
    base = Path(str(paths()["scratch"]["root"])) / "forcing" / "pilot-v2-constco2"
    files = {
        "temp": "tas_pert.clm",
        "prec": "pr_pert.clm",
        "swdown": "rsds_pert.clm",
        "lwnet": "lwnet_pert.clm",
    }
    restart = runs / "restart" / f"restart_c{cell}-{point}-s1.lpj"
    return restart, {k: base / f"c{cell}" / point / v for k, v in files.items()}


EXACT = (
    "temp_max",
    "temp_min",
    "atemp_mean",
    "atemp_mean20",
    "atemp_mean20_fix",
    "gdd5",
    "dval_prec0",
    "temp",
    "prec",
    "mprec20",
    "mtemp20",
    "min.sum",
    "min.data",
    "min.bookkeeping",
    "max.sum",
    "max.data",
    "max.bookkeeping",
)


@pytest.mark.needs_real_data
@pytest.mark.parametrize(("cell", "point"), [(10069, "core_t+4_p07"), (98, "lhs14"), (98, CONTROL)])
def test_a_pilot_buffer_is_reproduced_exactly_from_its_own_forcing(cell: int, point: str) -> None:
    restart, files = _pilot(cell, point)
    if not restart.exists():
        pytest.skip("pilot corpus not present")
    table = pl.read_csv(Path(str(paths()["scratch"]["corpus"])) / "pilot-v2-constco2" / "cells.csv")
    lat = float(table.filter(pl.col("cell") == cell)["lat"][0])
    reader = RestartReader(restart)
    real = reader.read(0)["climbuf"]
    f = cb.read_forcing(files, cell, lat)
    ours, trace = cb.climate_buffer_from_forcing(f, aetp_mean=float(real["scalars"][3]))
    assert trace.seed_after == tuple(reader.restart.seed)
    err = cb.compare_climbuf(ours, real)
    for name in EXACT:
        assert err[name]["max_abs"] == 0.0, f"{name}: {err[name]}"
    # The crop vernalisation terms agree to the last bit or two, not to the bit: the C's partial
    # term `pvd_max/N*(1-(t-low)/(high-low))` is compiled under icx's default fast floating-point
    # model, which may reassociate it. Crops only; nothing natural reads these.
    for name in ("V_req", "V_req_a"):
        assert err[name]["max_rel"] <= 1e-12, f"{name}: {err[name]}"


@pytest.mark.needs_real_data
def test_the_parameter_tables_match_the_model_parameter_file() -> None:
    cpp = shutil.which("cpp")
    par = path("lpjml.pft_params")
    if cpp is None or not par.exists():
        pytest.skip("needs cpp and the LPJmL parameter file")
    text = subprocess.run(
        [cpp, "-P", f"-I{par.parent.parent}", f"-I{par.parent}", str(par)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    blocks = re.split(r'\n\s*\{\s*\n\s*"name"\s*:', text)[1:]

    def num(block: str, key: str) -> float:
        m = re.search(rf'"{key}"\s*:\s*(-?[0-9.]+)', block)
        assert m, key
        return float(m.group(1))

    def pair(block: str, key: str) -> tuple[float, float]:
        m = re.search(
            rf'"{key}"\s*:\s*\{{\s*"low"\s*:\s*(-?[0-9.]+)\s*,\s*"high"\s*:\s*(-?[0-9.]+)', block
        )
        assert m, key
        return float(m.group(1)), float(m.group(2))

    for t, want in enumerate(cb.TREE_BIOCLIM):
        b = blocks[t]
        assert (want.temp_low, want.temp_high) == pair(b, "temp")
        assert (want.stressed_low, want.stressed_high) == pair(b, "temp_stressed")
        assert want.min_temprange == num(b, "min_temprange")
        assert want.gdd5min == num(b, "gdd5min")
        assert want.gddbase == num(b, "gddbase")
        assert want.aprec_min == num(b, "aprec_min")
        assert want.mort_temp_factor == num(b, "mort_temp_factor")
    crops = blocks[10:22]
    for c, (low, high, pvd) in enumerate(cb.CROP_VERNALISATION):
        assert (low, high) == pair(crops[c], "tv_opt")
        assert pvd == num(crops[c], "pvd_max")


@pytest.mark.needs_real_data
@pytest.mark.parametrize("cell", [42490, 12045, 52059])
def test_a_stored_restart_1999_buffer_is_reproduced_from_the_global_forcing(cell: int) -> None:
    """The stored spin-up's protocol, replayed from the global forcing to 1999, against its own
    restart_1999 record: bit-exact on every forcing-determined field, and the header's RNG state.
    Three of the biome reference cells (temperate, tropical, boreal); the SLURM check in
    `scripts/spinup_product.py --stage climbuf-check` does a stratified sample of the globe."""

    restart = path("ground_truth.restart_spinup_end")
    if not restart.exists():
        pytest.skip("the stored spin-up restart is not present")
    reader = RestartReader(restart)
    with reader:
        rec = reader.read(cell)
    real, frac = rec["climbuf"], float(rec["stands"][0]["frac"])
    lat = float(read_grid(path("inputs.coord"))[cell, 1])
    f = cb.read_forcing(forcing_files(), cell, lat)
    own = cb.effective_albedo(real, f, protocol=cb.STORED_SPINUP, stand_frac=frac)
    ours, trace = cb.climate_buffer_from_forcing(
        f, protocol=cb.STORED_SPINUP, albedo=own, aetp_mean=float(real["scalars"][3]),
        stand_frac=frac,
    )  # fmt: skip
    assert trace.seed_after == tuple(reader.restart.seed)
    err = cb.compare_climbuf(ours, real)
    for name in EXACT:
        assert err[name]["max_abs"] == 0.0, f"{name}: {err[name]}"
    for name in ("V_req", "V_req_a"):
        assert err[name]["max_rel"] <= 1e-12, f"{name}: {err[name]}"
