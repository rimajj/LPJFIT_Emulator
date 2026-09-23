"""The daily-forcing feature set (`vegemu.corpus.features_v3`), on synthetic climates.

What CI can check without the cluster: the model formulas transcribed here (the root distribution
of getrootdist.c, the beta of getbetaroot.c) do what the C does, including its off-by-one; the
features respond in the direction the physics says; and -- the property the pilot's hard check
rests on -- a row's features do not depend on which other rows share its batch. The real-data
tests compare the transcribed parameter tables against LPJmL-FIT's own files, and the two forcing
readers against each other on the global historical file.
"""

from __future__ import annotations

import itertools
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from screen_d95max import SOILPAR
from vegemu.binfmt.clm import LPJ_FLOAT, LPJ_SHORT, ClmHeader, write_clm
from vegemu.corpus import features_v3 as fv3
from vegemu.corpus.climate import NDAYYEAR, VARS
from vegemu.paths import paths

NY = 3


def _climate(n: int, seed: int = 0) -> dict[str, np.ndarray]:
    """n synthetic cells with a seasonal cycle, a wet and a dry season, and weather noise."""
    rng = np.random.default_rng(seed)
    day = np.arange(NDAYYEAR)[None, None, :]
    season = np.sin(2 * np.pi * (day - 100) / NDAYYEAR)
    base = rng.uniform(-5, 25, (n, 1, 1))
    amp = rng.uniform(2, 15, (n, 1, 1))
    tas = base + amp * season + rng.normal(0, 2, (n, NY, NDAYYEAR))
    wet_season = (np.cos(2 * np.pi * (day - 200) / NDAYYEAR) > 0).astype(float)
    rain_scale = rng.uniform(0.5, 8, (n, 1, 1))
    raining = rng.random((n, NY, NDAYYEAR)) < 0.2 + 0.5 * wet_season
    pr = np.where(raining, rng.exponential(1.0, (n, NY, NDAYYEAR)) * rain_scale * 3, 0.0)
    rsds = 180 + 100 * season + rng.normal(0, 20, (n, NY, NDAYYEAR))
    lwnet = -60 + rng.normal(0, 10, (n, NY, NDAYYEAR))
    huss = 0.004 + 0.003 * (season + 1) + 0.0 * tas
    return {"tas": tas, "pr": pr, "rsds": np.maximum(rsds, 5), "lwnet": lwnet, "huss": huss}


def _soil(n: int) -> tuple[np.ndarray, np.ndarray]:
    codes = np.array([(7, 12, 1, 9, 4)[i % 5] for i in range(n)])
    depth = np.array([(9.0, 0.8, 2.5, 30.0, 1.4)[i % 5] for i in range(n)])
    return codes, depth


# -- transcribed model formulas ---------------------------------------------------------------


@pytest.mark.parametrize("d95", [51.0, 150.0, 400.0, 900.0, 1800.0])
def test_beta_puts_95_percent_of_roots_above_d95(d95: float) -> None:
    b = fv3.beta_root(d95)
    share = (1 - b**d95) / (1 - b**fv3.ROOT_BOTTOM_CM)
    assert share == pytest.approx(0.95, abs=1e-9)


def test_deeper_d95_means_larger_beta() -> None:
    betas = [fv3.beta_root(d) for d in fv3.ROOT_PROFILES_CM]
    assert all(a < b for a, b in itertools.pairwise(betas))


@pytest.mark.parametrize("depth_m", [0.1, 0.4, 1.5, 3.0, 12.0, 50.0])
def test_root_fractions_sum_to_one_at_every_soil_depth(depth_m: float) -> None:
    for d in fv3.ROOT_PROFILES_CM:
        r = fv3.root_layer_fractions(d, np.array([depth_m * 1000.0]))
        assert r.shape == (1, fv3.ROOT_LAYERS)
        assert r.sum() == pytest.approx(1.0, abs=1e-12)
        assert (r >= 0).all()


def test_truncated_roots_go_where_getrootdist_puts_them() -> None:
    """At 1.5 m, layers 4.. (tops 2 m and below) give up their roots, and getrootdist.c adds them
    to layer `num_layer_new - removed - 1` = 21 - 18 - 1 = 2, one ABOVE the last kept layer (3)."""
    full = fv3.root_layer_fractions(900.0, np.array([1e9]))[0]
    cut = fv3.root_layer_fractions(900.0, np.array([1500.0]))[0]
    assert (cut[4:] == 0).all()
    assert cut[3] == pytest.approx(full[3])
    assert cut[2] == pytest.approx(full[2] + full[4:].sum())


def test_untruncated_soil_leaves_the_beta_distribution_alone() -> None:
    a = fv3.root_layer_fractions(400.0, np.array([25_000.0]))
    b = fv3.root_layer_fractions(400.0, np.array([1e9]))
    np.testing.assert_array_equal(a, b)


def test_soil_table_matches_the_d95max_screen_except_code_13() -> None:
    """Codes 1-12 agree with the transcription the sealed experiment used; code 13 is rock and ice
    in the model's soilmap, which that transcription reads as light clay (module docstring)."""
    for code in range(1, 13):
        whc, sand, clay = SOILPAR[code]
        st = fv3.SOIL_TYPES[code]
        assert st.whc == pytest.approx(whc)
        assert (st.sand, st.clay) == pytest.approx((sand, clay))
    assert fv3.SOIL_TYPES[13].name == "rock and ice"
    assert fv3.SOIL_TYPES[13].whc < 0.01 < SOILPAR[13][0]


def test_unknown_soil_code_is_nan_not_zero() -> None:
    whc = fv3.soil_whc([0, 7, 99])
    assert np.isnan(whc[0]) and np.isnan(whc[2]) and whc[1] > 0


def test_vpd_is_zero_at_saturation_and_rises_with_dryness() -> None:
    t = np.array([20.0, 20.0, 20.0])
    q = np.array([0.0147, 0.008, 0.002])  # ~saturated at 20 C, then drier
    v = fv3.vpd_pa(t, q)
    assert v[0] < 50 and v[0] < v[1] < v[2]


# -- the feature row --------------------------------------------------------------------------


def test_every_feature_is_computed_once_in_order() -> None:
    n = 5
    codes, depth = _soil(n)
    cols = fv3.v3_columns(_climate(n), codes, depth)
    assert tuple(cols) == fv3.V3_FEATURES
    assert len(set(fv3.V3_FEATURES)) == len(fv3.V3_FEATURES)
    for k, v in cols.items():
        assert v.shape == (n,), k
        assert np.isfinite(v).all(), k


def test_a_rows_features_do_not_depend_on_its_batch() -> None:
    """The property behind the pilot's hard check: row i computed alone equals row i computed
    among others, bit for bit, whatever the batch size."""
    n = 6
    clim = _climate(n, seed=3)
    codes, depth = _soil(n)
    together = fv3.v3_columns(clim, codes, depth)
    for i in (0, 4):
        alone = fv3.v3_columns(
            {v: clim[v][i : i + 1] for v in VARS}, codes[i : i + 1], depth[i : i + 1]
        )
        for k in fv3.V3_FEATURES:
            assert alone[k][0] == together[k][i] or (
                np.isnan(alone[k][0]) and np.isnan(together[k][i])
            ), k


def test_more_rain_means_less_water_stress() -> None:
    clim = _climate(1, seed=1)
    codes, depth = np.array([7]), np.array([5.0])
    dry = fv3.v3_columns(clim, codes, depth)
    wet = fv3.v3_columns({**clim, "pr": clim["pr"] * 3.0}, codes, depth)
    for d in fv3.ROOT_PROFILES_CM:
        p = f"d{d:g}"
        assert wet[f"wscal_{p}"][0] >= dry[f"wscal_{p}"][0]
        assert wet[f"wstress_{p}_0p5"][0] <= dry[f"wstress_{p}_0p5"][0]
        assert wet[f"aet_{p}"][0] >= dry[f"aet_{p}"][0]
    assert wet["cwb_ann"][0] > dry["cwb_ann"][0]


def test_a_shallow_soil_takes_away_the_deep_profiles_advantage() -> None:
    clim = _climate(1, seed=2)
    deep = fv3.v3_columns(clim, np.array([7]), np.array([30.0]))
    shallow = fv3.v3_columns(clim, np.array([7]), np.array([0.3]))
    assert shallow["aet_gain_deep"][0] <= deep["aet_gain_deep"][0] + 1e-9
    assert shallow["awc_rootzone"][0] < deep["awc_rootzone"][0]


def test_cold_and_establishment_counts_on_a_constructed_series() -> None:
    """A constant 20 C climate: no cold days, every tree type's survival rule holds, and only the
    boreal types fail to establish (their coldest month must be at or below 0 C)."""
    shape = (1, NY, NDAYYEAR)
    clim = {
        "tas": np.full(shape, 20.0),
        "pr": np.full(shape, 3.0),
        "rsds": np.full(shape, 200.0),
        "lwnet": np.full(shape, -50.0),
        "huss": np.full(shape, 0.01),
    }
    c = fv3.v3_columns(clim, np.array([7]), np.array([5.0]))
    assert c["tcmin20_mean"][0] == pytest.approx(20.0)
    assert c["days_below_12p5"][0] == 0 and c["days_below_m45_max"][0] == 0
    assert c["days_above_25"][0] == 0
    assert c["gdd5_ge_1200"][0] == 1.0  # 15 * 365 = 5475 degree days
    for name in ("est_trbe", "est_tene", "est_tebe", "est_tebs"):
        assert c[name][0] == 1.0, name
    assert c["est_bone"][0] == 0.0 and c["est_bons"][0] == 0.0
    assert c["surv_tc_ge_2p5"][0] == 1.0 and c["surv_bons"][0] == 0.0
    assert c["snow_days"][0] == 0 and c["frost_number"][0] == 0.0


def test_cyclic_running_mean_wraps_like_the_recycled_spinup() -> None:
    per_year = np.arange(30, dtype=float)[None, :]
    rm = fv3._cyclic_running_mean(per_year, 20)
    # Window ending at year 5 covers years 16..29 and 0..5.
    expect = np.mean([*range(16, 30), *range(0, 6)])
    assert rm[0, 5] == pytest.approx(expect)
    assert rm[0, 29] == pytest.approx(np.mean(range(10, 30)))


def test_longest_run() -> None:
    m = np.array([[True, True, False, True, True, True, False]])
    assert fv3.longest_run(m)[0] == 3


# -- the readers ------------------------------------------------------------------------------


def _write_forcing(tmp: Path, firstcell: int, ncell: int, datatype: int) -> dict[str, str]:
    rng = np.random.default_rng(9)
    files = {}
    for v in VARS:
        h = ClmHeader(
            "LPJCLIM",
            3,
            1,
            2000,
            NY,
            firstcell,
            ncell,
            NDAYYEAR,
            scalar=0.1 if datatype == LPJ_SHORT else 1.0,
            datatype=datatype,
        )
        dt = "<i2" if datatype == LPJ_SHORT else "<f4"
        blocks = [rng.integers(-300, 300, (ncell, NDAYYEAR)).astype(dt) for _ in range(NY)]
        path = tmp / f"{v}.clm"
        write_clm(path, h, blocks)
        files[v] = str(path)
    return files


@pytest.mark.parametrize("datatype", [LPJ_FLOAT, LPJ_SHORT])
def test_row_reader_and_cell_reader_agree(tmp_path: Path, datatype: int) -> None:
    files = _write_forcing(tmp_path, firstcell=40, ncell=7, datatype=datatype)
    whole, ids = fv3.read_rows(files, 2000, 2000 + NY - 1, 0, 7)
    part, pids = fv3.read_rows(files, 2001, 2002, 2, 5)
    np.testing.assert_array_equal(ids, np.arange(40, 47))
    np.testing.assert_array_equal(pids, np.arange(42, 45))
    by_cell = fv3.read_cells(files, 2000, 2000 + NY - 1, [46, 41])
    for v in VARS:
        assert whole[v].shape == (7, NY, NDAYYEAR)
        np.testing.assert_array_equal(part[v], whole[v][2:5, 1:3])
        np.testing.assert_array_equal(by_cell[v], whole[v][[6, 1]])


def test_cells_are_global_ids_not_rows(tmp_path: Path) -> None:
    files = _write_forcing(tmp_path, firstcell=40, ncell=7, datatype=LPJ_FLOAT)
    with pytest.raises(ValueError, match="outside"):
        fv3.read_cells(files, 2000, 2002, [3])


# -- against the model's own files ------------------------------------------------------------


def _lpjroot() -> Path | None:
    try:
        root = Path(str(paths()["lpjml"]["lpjroot"]))
    except (KeyError, FileNotFoundError):
        return None
    return root if (root / "par" / "pft_lpjmlfit.js").exists() else None


real_lpj = pytest.mark.skipif(_lpjroot() is None, reason="needs the LPJmL-FIT source tree")


@real_lpj
@pytest.mark.needs_real_data
def test_tree_limits_match_pft_lpjmlfit() -> None:
    root = _lpjroot()
    assert root is not None
    if shutil.which("cpp") is None:
        pytest.skip("cpp not available")
    text = subprocess.run(
        ["cpp", "-P", f"-I{root}", str(root / "par" / "pft_lpjmlfit.js")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    blocks = re.split(r'"name"\s*:', text)[1 : 1 + len(fv3.TREE_TYPES)]

    def num(block: str, pattern: str) -> float:
        m = re.search(pattern, block)
        assert m is not None, pattern
        return float(m.group(1))

    for lim, block in zip(fv3.TREE_TYPES, blocks, strict=True):
        assert '"type" : "tree"' in block
        assert num(block, r'"temp"\s*:\s*\{\s*"low"\s*:\s*(-?[\d.]+)') == lim.temp_low
        assert num(block, r'"temp"\s*:\s*\{[^}]*"high"\s*:\s*(-?[\d.]+)') == lim.temp_high
        assert num(block, r'"gdd5min"\s*:\s*(-?[\d.]+)') == lim.gdd5min
        assert num(block, r'"min_temprange"\s*:\s*(-?[\d.]+)') == lim.min_temprange
        assert num(block, r'"temp_stressed"\s*:\s*\{\s*"low"\s*:\s*(-?[\d.]+)') == (
            lim.temp_stressed_low
        )
        assert num(block, r'"tmin"\s*:\s*\{[^}]*"base"\s*:\s*(-?[\d.]+)') == lim.tmin_base
        assert num(block, r'"tmax"\s*:\s*\{[^}]*"base"\s*:\s*(-?[\d.]+)') == lim.tmax_base
        assert num(block, r'"aprec_min"\s*:\s*(-?[\d.]+)') == fv3.APREC_MIN


@real_lpj
@pytest.mark.needs_real_data
def test_soil_table_matches_soil_20m() -> None:
    root = _lpjroot()
    assert root is not None
    text = (root / "par" / "soil_20m.js").read_text()
    names = [s.name for s in fv3.SOIL_TYPES.values()]
    for st in fv3.SOIL_TYPES.values():
        m = re.search(
            r'"name"\s*:\s*"' + re.escape(st.name) + r'".*?"Ks"\s*:\s*([\d.]+).*?"sand"\s*:\s*'
            r'([\d.]+).*?"clay"\s*:\s*([\d.]+).*?"w_pwp"\s*:\s*([\d.]+).*?"w_fc"\s*:\s*([\d.]+)'
            r'.*?"w_sat"\s*:\s*([\d.]+)',
            text,
        )
        assert m is not None, st.name
        ks, sand, clay, pwp, fc, sat = (float(g) for g in m.groups())
        assert (st.ks, st.sand, st.clay, st.w_pwp, st.w_fc, st.w_sat) == (
            ks,
            sand,
            clay,
            pwp,
            fc,
            sat,
        )
    assert names[12] == "rock and ice"
    layers = re.search(r'"soildepth"\s*:\s*\[(.*?)\]', text, re.S)
    assert layers is not None
    vals = [float(x) for x in re.findall(r"([\d.]+)\s*[,/]", layers.group(1) + ",")]
    assert tuple(vals[: len(fv3.LAYER_MM)]) == fv3.LAYER_MM


def _historical_files() -> dict[str, str] | None:
    try:
        files = {v: str(paths()["inputs"]["historical"][v]) for v in VARS}
    except KeyError:
        return None
    return files if all(Path(f).exists() for f in files.values()) else None


@pytest.mark.skipif(_historical_files() is None, reason="needs the global forcing under /p")
@pytest.mark.needs_real_data
def test_row_and_cell_readers_agree_on_the_global_file() -> None:
    files = _historical_files()
    assert files is not None
    rows, ids = fv3.read_rows(files, 1998, 1999, 42489, 42492)
    cells = fv3.read_cells(files, 1998, 1999, [42490])
    for v in VARS:
        np.testing.assert_array_equal(rows[v][1], cells[v][0])
    assert ids[1] == 42490
