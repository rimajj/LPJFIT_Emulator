#!/usr/bin/env python
"""Derive what every null MUST return for the EMITTED-RESTART DRIFT experiment (t3).

    scripts/exp_derive_nulls_restart.py --out <dir> [--version v0]

Third companion to `exp_derive_nulls.py` and `exp_derive_nulls_leg.py`. Same job, same metric, a
different question: not "is the map right?" but "when the real model is run forward from the state
the emulator emitted, does that state move TOWARD the trajectory a real restart produces, or away
from it?"

WHY THIS NEEDS ITS OWN DERIVATION, AND WHY THE ROADMAP'S WORDING OF t3 CANNOT BE USED. The ladder in
`PLAN.md` words t3 as "20 years with no drift beyond the two-seed spread". Measured on the model
itself that is not a test: over the 61,700 vegetated cells of corpus v0 the interannual variability
of a cell's own annual series is a median 16.5 % of its level, while the acceptance band is a median
10.0 %, so a REAL restart compared year-to-year against its own start fails the criterion in 71 % of
cells. The drift of the state itself -- the 1000-year spin-up trend, +6.8 %/century median --
contributes a median 1.75 % over 20 years and is not the problem. The noise is. So the estimand has
to be a WINDOW MEAN, and the reference arm's pass rate is not 1.0; both are derived here.

THE ARMS, AND WHY EACH IS A COMPETITOR RATHER THAN A STRAW MAN. Every null is a real, valid,
loadable restart for the same 20 cells -- a thing you could hand the model instead of the emulator:

  geographic_address   the geographically nearest OTHER cell's real 1999 restart. The decisive one:
                       if handing the model a neighbouring cell's real forest scores as well as the
                       emulator's synthesised one, the synthesis has bought nothing.
  nearest_analogue     the climatically nearest other cell's real restart. Space-for-time.
  climatological_mean  the mean state over the scored cells.
  shuffled_target      each cell's control state permuted across cells -- the chance rate.

Beside them, per synthesis version, three measured arms: the emitted state at year 0, the same state
after ONE year of the real C model, and the state FROZEN at year 0 but scored against the year-1
truth. That last is what makes "did running it forward help?" answerable: year 1 below frozen means
the model moved the state away from the truth, above it means the model repaired it.

THE BAND IS TRANSFERRED FROM ssp126, NOT FROM THE HISTORICAL LEG. The truth here is the CONTROL ARM:
the real 1999 restart for the same cells, run forward under the same config. That control descends
from the historical seed-1 lineage, so a tolerance taken from the historical leg's own two seeds is
partly circular in the same way the map experiment's band was. The ssp126 leg's two seeds are
genuine (`docs/decisions/20260908-X-ssp370-has-no-second-seed.md` -- ssp370's are not, and are never
used for a band), and the two legs' spread distributions agree to within 6 %, which is what licenses
the transfer. The historical-band arm is reported beside it, never instead of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu import nulls as null_mod
from vegemu.corpus.state import basis, state_table
from vegemu.dataset import load_leg
from vegemu.paths import paths
from vegemu.score import (
    FLOOR,
    SCORED_CONJUNCTIVE,
    band_frac_conjunctive,
    band_frac_per_quantity,
    band_hits,
    matrix,
    relative_spread,
)

SHUFFLE_SEED = 20260909

# The two arms of the one-year t2 run that already exists on disk, and the state each one started
# from. Year 0 is the file the emulator emitted (and its byte-exact real counterpart); year 1 is
# what the C model wrote after running them both forward one year under the same config.
CONTROL = {
    "control_y0": ("t2-control", "restart/restart_1999_real.lpj"),
    "control_y1": ("t2-control", "restart/restart_2000_control.lpj"),
}

# Every synthesis version that has BOTH a year-0 file and a one-year run of the real model from it.
# Scoring all three answers the question a single version cannot: whether the widened donor pool of
# the later versions repairs the state, or whether the defect survives every fix tried so far.
VARIANTS = {
    "synth-v0": ("t2-emulated", "restart_1999_emulated.lpj", "restart_2000_emulated.lpj"),
    "synth-v1": ("t2b-emulated", "restart_1999_emulated.lpj", "restart_2000_emul2.lpj"),
    "synth-v2or3": ("t2c-emulated", "restart_1999_emulated.lpj", "restart_2000_emul3.lpj"),
}


def drift_reference(version: str) -> dict[str, float]:
    """The real model's OWN 20-year drift, and the pass rate a real restart achieves against it.

    This is the number that disqualifies the roadmap's wording of t3. `spin_convergence.parquet`
    carries, per cell, the two-seed spread of end-of-spin-up vegetation carbon, the interannual
    variability of the annual series as a fraction of the level, and the residual trend in
    %/century. A real restart run forward 20 years moves by the trend; a SINGLE YEAR sampled at the
    end differs from the start by the trend PLUS one draw of the interannual noise, and it is the
    noise that breaks the criterion.
    """
    frame = pl.read_parquet(
        Path(str(paths()["scratch"]["corpus"])) / version / "spin_convergence.parquet"
    )
    veg = frame.filter(pl.col("vegetated"))
    trend20 = np.abs(veg["trend_pct_per_century"].to_numpy()) / 100.0 * 0.2
    iav = veg["iav_frac"].to_numpy()
    band = np.maximum(FLOOR, veg["two_seed_spread"].to_numpy())
    single_year = np.sqrt(trend20**2 + iav**2)
    window_mean = np.sqrt(trend20**2 + (iav / np.sqrt(20.0)) ** 2)
    return {
        "n_vegetated_cells": int(veg.height),
        "median_two_seed_spread": float(np.median(veg["two_seed_spread"].to_numpy())),
        "median_iav_frac": float(np.median(iav)),
        "median_trend_pct_per_century": float(np.median(veg["trend_pct_per_century"].to_numpy())),
        "median_band": float(np.median(band)),
        "median_drift_20yr_trend_only": float(np.median(trend20)),
        "frac_inside_band_trend_only": float(np.mean(trend20 <= band)),
        "frac_inside_band_single_year": float(np.mean(single_year <= band)),
        "frac_inside_band_window_mean_20yr": float(np.mean(window_mean <= band)),
    }


def state_of(run: str, rel: str, cells: int, nproc: int) -> tuple[pl.DataFrame, dict[str, object]]:
    path = Path(str(paths()["scratch"]["runs"])) / run / rel
    return state_table(path, cells=range(cells), nproc=nproc), basis(path)


def read_states(nproc: int) -> tuple[dict[str, pl.DataFrame], dict[str, object]]:
    """The control pair plus every synthesis version's year-0 and year-1 state, with their bases."""
    states: dict[str, pl.DataFrame] = {}
    bases: dict[str, object] = {}
    for arm, (run, rel) in CONTROL.items():
        states[arm], bases[arm] = state_of(run, rel, cells=20, nproc=nproc)
    for variant, (run, y0, y1) in VARIANTS.items():
        for suffix, rel in (("y0", y0), ("y1", y1)):
            key = f"{variant}_{suffix}"
            states[key], bases[key] = state_of(run, f"restart/{rel}", cells=20, nproc=nproc)
    for arm, b in bases.items():
        print(f"read {arm:18s}: {b['bytes']} B, state_year {b['state_year']}")  # type: ignore[index]
    return states, bases


def mean_per_quantity(
    pred: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    band: npt.NDArray[np.float64],
) -> float:
    """Mean over the 22 quantities of the per-quantity pass rate.

    NOT a replacement for the conjunctive statistic and never quoted as acceptance: this is an
    ENGINEERING gate on 20 cells, where the conjunctive number is pinned at the 1/20 = 0.05
    granularity floor for every arm and therefore cannot separate anything. Averaging over 440
    cell-quantities instead of demanding all 22 at once is what buys the resolution to tell "the
    model repaired the state" from "the model wrecked it". The conjunctive number is reported
    beside it, always.
    """
    hits = band_hits(pred, truth, band)
    return float(hits.mean()) if hits.size else float("nan")


def score_band(
    band: npt.NDArray[np.float64],
    preds: dict[str, npt.NDArray[np.float64]],
    *,
    control0: npt.NDArray[np.float64],
    control1: npt.NDArray[np.float64],
    emulated: dict[str, tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    h1: npt.NDArray[np.float64],
    hist_truth: npt.NDArray[np.float64],
) -> dict[str, object]:
    """Every arm under ONE acceptance band: the nulls, the ceiling, and each synthesis version."""
    entry: dict[str, object] = {
        "nulls_conjunctive": {
            n: band_frac_conjunctive(p, control0, band) for n, p in preds.items()
        },
        "nulls_mean_per_quantity": {
            n: mean_per_quantity(p, control0, band) for n, p in preds.items()
        },
        # The ceiling: one realisation scored against the two-seed mean under this band.
        "ceiling_conjunctive": band_frac_conjunctive(h1, hist_truth, band),
        "ceiling_mean_per_quantity": mean_per_quantity(h1, hist_truth, band),
    }
    for variant, (e0, e1) in emulated.items():
        entry[variant] = {
            # Before and after ONE year of the real model, plus the arm that FREEZES the emitted
            # state and scores it against the year-1 truth. If year 1 is below the frozen arm,
            # running the model forward moved the state away from the truth rather than toward it.
            "conjunctive_year0": band_frac_conjunctive(e0, control0, band),
            "conjunctive_year1": band_frac_conjunctive(e1, control1, band),
            "mean_per_quantity_year0": mean_per_quantity(e0, control0, band),
            "mean_per_quantity_year1": mean_per_quantity(e1, control1, band),
            "mean_per_quantity_frozen_vs_year1_truth": mean_per_quantity(e0, control1, band),
            "per_quantity_year0": band_frac_per_quantity(e0, control0, band, SCORED_CONJUNCTIVE),
            "per_quantity_year1": band_frac_per_quantity(e1, control1, band, SCORED_CONJUNCTIVE),
        }
    return entry


def report_band(bname: str, entry: dict[str, object], n_sub: int) -> None:
    """Print one band's arms. The conjunctive number always travels beside the resolved one."""
    conj: dict[str, float] = entry["nulls_conjunctive"]  # type: ignore[assignment]
    mpq: dict[str, float] = entry["nulls_mean_per_quantity"]  # type: ignore[assignment]
    print(f"\n{bname} band, {n_sub} cells -- nulls (conjunctive / mean-per-quantity):")
    for n, v in sorted(conj.items(), key=lambda kv: -kv[1]):
        print(f"  {n:24s} {v:.4f}  {mpq[n]:.4f}")
    print(
        f"  {'(ceiling: one seed)':24s} {entry['ceiling_conjunctive']:.4f}  "
        f"{entry['ceiling_mean_per_quantity']:.4f}"
    )
    print(f"\n{bname} band -- each synthesis version, mean_per_quantity:")
    print(f"  {'version':14s} {'year0':>8s} {'year1':>8s} {'frozen':>8s}   verdict")
    for variant in VARIANTS:
        e: dict[str, float] = entry[variant]  # type: ignore[assignment]
        y0, y1 = e["mean_per_quantity_year0"], e["mean_per_quantity_year1"]
        frozen = e["mean_per_quantity_frozen_vs_year1_truth"]
        better = y1 - frozen
        verdict = "model REPAIRS it" if better > 0 else "model moves it AWAY"
        print(f"  {variant:14s} {y0:8.4f} {y1:8.4f} {frozen:8.4f}   {verdict} ({better:+.4f})")


def oof_nulls(
    corpus_state: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    lon: npt.NDArray[np.float64],
    lat: npt.NDArray[np.float64],
    climate: npt.NDArray[np.float64],
) -> dict[str, npt.NDArray[np.float64]]:
    """Every null's year-0 state, leave-one-cell-out within the scored block.

    Leave-one-out and not k-fold: the scored set is a single contiguous 20-cell block, so there is
    no spatial blocking to be had inside it and pretending otherwise would be theatre.

    ⚠ THAT IS ALSO WHY THERE IS NO PRE-REGISTRATION TO POINT AT. The whole block is one 15-degree
    tile, so these four nulls land within 0.786-0.845 of each other and cannot be told apart; an
    experiment sealed on this cell set would return `invalid` by construction, and X4 was therefore
    deliberately NOT sealed. This is an engineering gate on 20 of 54,020 cells, never fidelity
    evidence. See docs/decisions/20260909-X-synthesised-restart-is-beaten-by-a-random-neighbour.md.
    """
    n = corpus_state.shape[0]
    out = {
        k: np.full_like(corpus_state, np.nan)
        for k in (
            "geographic_address",
            "nearest_analogue",
            "climatological_mean",
            "shuffled_target",
        )
    }
    for i in range(n):
        others = np.array([j for j in range(n) if j != i])
        out["climatological_mean"][i] = corpus_state[others].mean(axis=0)
        out["geographic_address"][i] = null_mod.nearest_geographic(
            lon[others], lat[others], corpus_state[others], lon[i : i + 1], lat[i : i + 1]
        )[0]
        out["nearest_analogue"][i] = null_mod.nearest_analogue(
            climate[others], corpus_state[others], climate[i : i + 1]
        )[0]
    out["shuffled_target"] = null_mod.shuffled(truth, SHUFFLE_SEED)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v0")
    ap.add_argument("--out", default=None)
    ap.add_argument("--nproc", type=int, default=4)
    args = ap.parse_args()

    report: dict[str, object] = {
        "corpus_version": args.version,
        "shuffle_seed": SHUFFLE_SEED,
        "quantities": list(SCORED_CONJUNCTIVE),
    }

    # ---------------------------------------------------------------------------------- reference
    report["own_drift_of_the_real_model"] = drift_reference(args.version)
    ref = report["own_drift_of_the_real_model"]
    print("the real model's own 20-year drift, over its vegetated cells:")
    for k, v in ref.items():  # type: ignore[union-attr]
        print(f"  {k:38s} {v}")

    # -------------------------------------------------------------------------------- the arms
    states, bases = read_states(args.nproc)
    report["basis"] = bases

    first_cell = 42480
    n_sub = states["control_y0"].height
    global_cells = np.arange(first_cell, first_cell + n_sub, dtype=np.int64)
    report["cells"] = {
        "first": first_cell,
        "n": int(n_sub),
        "note": "20 of 54,020 tree-bearing cells",
    }

    # ------------------------------------------------------------------------------------- band
    hist = load_leg("historical", args.version)
    ssp = load_leg("ssp126", args.version)
    keep = np.isin(hist.cells, global_cells)
    if int(keep.sum()) != n_sub:
        raise ValueError(f"corpus holds {int(keep.sum())} of the {n_sub} scored cells")
    sel = pl.Series(keep)
    h1 = matrix(hist.seed1.filter(sel), SCORED_CONJUNCTIVE)
    h2 = matrix(hist.seed2.filter(sel), SCORED_CONJUNCTIVE)
    s1 = matrix(ssp.seed1.filter(sel), SCORED_CONJUNCTIVE)
    s2 = matrix(ssp.seed2.filter(sel), SCORED_CONJUNCTIVE)

    control0 = matrix(states["control_y0"], SCORED_CONJUNCTIVE)
    control1 = matrix(states["control_y1"], SCORED_CONJUNCTIVE)
    emulated = {
        v: (
            matrix(states[f"{v}_y0"], SCORED_CONJUNCTIVE),
            matrix(states[f"{v}_y1"], SCORED_CONJUNCTIVE),
        )
        for v in VARIANTS
    }

    # The truth is the control arm -- ONE realisation, so the band must not come from it. Both
    # candidate donors are reported; ssp126 is primary because the control descends from the
    # historical seed-1 lineage.
    bands = {
        "transferred_ssp126": relative_spread(s1, s2) * np.abs(control0),
        "own_historical": relative_spread(h1, h2) * np.abs(control0),
    }
    report["band_median_relative"] = {
        name: float(np.nanmedian(b / np.maximum(np.abs(control0), 1e-12)))
        for name, b in bands.items()
    }

    # ------------------------------------------------------------------------------------ nulls
    # ANALOGUE_FEATURES, not every climate column: the analogue distance's feature set is
    # pre-registered in `vegemu.nulls` precisely so it cannot be tuned after the fact.
    where = hist.climate.filter(sel)
    clim = matrix(where, null_mod.ANALOGUE_FEATURES)
    lon = np.asarray(where["lon"].to_numpy(), dtype=np.float64)
    lat = np.asarray(where["lat"].to_numpy(), dtype=np.float64)
    hist_truth = (h1 + h2) / 2.0
    preds = oof_nulls(hist_truth, control0, lon, lat, clim)

    results: dict[str, object] = {}
    for bname, band in bands.items():
        results[bname] = score_band(
            band,
            preds,
            control0=control0,
            control1=control1,
            emulated=emulated,
            h1=h1,
            hist_truth=hist_truth,
        )
        report_band(bname, results[bname], n_sub)  # type: ignore[arg-type]

    report["results"] = results

    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "derived_nulls_restart.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str)
        )
        print(f"\nwrote {dest / 'derived_nulls_restart.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
