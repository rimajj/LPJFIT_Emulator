#!/usr/bin/env python
"""The current figures: what the emulator does and does not do, as of the latest results.

    NCPUS=1 scripts/sbatch_py.sh INT-figures scripts/plot_current.py --out figures

Reads only files that already exist -- the sealed experiments' metrics, the dev screen's saved
predictions, the dev diagnostics' JSON -- and fits nothing. Every figure states its basis (cells,
reference, whether sealed or a development diagnostic) in its own subtitle, because a figure is
quoted without the text around it.

Style, palette and map helpers are `plot_validation.py`'s, unchanged, so the two sets read as one.
That script drew the FIRST experiment on the scenario runs (one climate per place, CO2 rising);
its figures 1-10 are superseded and live in `figures/archive/`. Its spin-up figure is redrawn here
because its title was corrected on 2026-09-15 and the image never was.

⚠ Numbers that exist only in a verdict's prose (each test's attainable maximum and the blind arm's
score) are the constants in VERDICT_NUMBERS, each with the verdict it comes from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import polars as pl
from matplotlib.colors import ListedColormap, TwoSlopeNorm
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, PercentFormatter

from plot_validation import (
    DIV,
    GRID,
    INK,
    INK_2,
    INK_MUTED,
    OCEAN,
    S1,
    S2,
    S3,
    S4,
    SEQ,
    SURFACE,
    despine,
    draw_map,
    fig_spinup,
    rasterise,
    style,
)
from vegemu.paths import paths

Array = npt.NDArray[np.float64]
REPO = Path(__file__).resolve().parent.parent

# Numbers that live only in verdict prose. Each is quoted there to six places.
VERDICT_NUMBERS: dict[str, dict[str, float]] = {
    # X-20260921-pilot-warming-response-constco2-resealed/verdict.md; blind arm: the same verdict,
    # "The blind arm" section (job in X-ablation-blind-constco2).
    "response": {"bar": 0.257725, "ceiling": 0.848545, "blind": 0.362322},
    # X-20260921-pilot-composition-response-constco2-resealed/verdict.md; blind arm:
    # X-20260923-pilot-composition-blind-arm (its `model` arm IS the blind model).
    "composition": {"bar": 0.300203, "ceiling": 0.862853, "blind": 0.307940},
    # X-20260923-equilibrium-from-climate/verdict.md (bar = best null + 0.125).
    "equilibrium": {"bar": 0.222666, "ceiling": 0.950},
}


def title(fig: plt.Figure, head: str, sub: str, y: float = 0.995) -> None:
    fig.suptitle(head, x=0.012, y=y, ha="left", fontsize=12, fontweight="semibold", color=INK)
    fig.text(0.012, y - 0.045, sub, fontsize=8.8, color=INK_2, va="top")


def hbars(
    ax: plt.Axes,
    rows: list[tuple[str, float, str]],
    *,
    xmax: float,
    fmt: str = "{:.1%}",
) -> None:
    """Horizontal bars, top to bottom in the given order, value labelled at the bar end."""
    names = [r[0] for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    cols = [r[2] for r in rows][::-1]
    ax.barh(names, vals, color=cols, height=0.62)
    for y, (v, c) in enumerate(zip(vals, cols, strict=True)):
        ax.text(
            v + 0.012 * xmax,
            y,
            fmt.format(v),
            va="center",
            ha="left",
            fontsize=8.5,
            color=INK if c == S1 else INK_2,
            fontweight="semibold" if c == S1 else "normal",
        )
    ax.set_xlim(0, xmax)
    if "%" in fmt:
        ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    despine(ax, ("bottom",))


# ---------------------------------------------------------------------------------------------
# 01 -- the acceptance test: as good as a rerun of the model?
# ---------------------------------------------------------------------------------------------
def _fracs(m: dict[str, Any]) -> dict[str, float]:
    """Each arm's share of cells in band: the stored statistic is frac(arm) - frac(rerun)."""
    fr = float(m["frac_rerun"])
    return {k: float(v) + fr for k, v in m["arms"].items()}


def fig_acceptance(exp: Path, out: Path) -> None:
    pilot = json.loads((exp / "X-20260924-spinup-vegc-from-pilot" / "metrics.json").read_text())
    spin = json.loads((exp / "X-20260924-spinup-vegc-from-spinup" / "metrics.json").read_text())
    rec = json.loads((exp / "X-20260925-spinup-vegc-recipe-v2" / "metrics.json").read_text())
    state = json.loads((exp / "X-20260924-pilot-state-asgood" / "metrics.json").read_text())
    fp, fs, fr, fst = _fracs(pilot), _fracs(spin), _fracs(rec), _fracs(state)

    fig, axes = plt.subplots(
        3, 1, figsize=(8.6, 8.4), gridspec_kw={"height_ratios": [5, 5, 4], "hspace": 0.62}
    )
    hbars(
        axes[0],
        [
            ("a second run of the model", float(spin["frac_rerun"]), INK),
            ("emulator, trained on the stored spin-up", fs["model"], S1),
            ("emulator, trained on the 200-cell pilot only", fp["model"], S1),
            ("copy the most similar climate", fs["nearest_analogue"], INK_MUTED),
            ("copy the nearest cell", fs["nearest_geographic"], INK_MUTED),
            ("the average forest", fs["training_mean"], INK_MUTED),
        ],
        xmax=1.0,
    )
    axes[0].set_title(
        f"A. All {spin['scored_cells']:,} cells with trees, the first (sealed) map",
        loc="left",
    )
    hbars(
        axes[1],
        [
            ("a second run of the model", float(rec["frac_rerun"]), INK),
            ("emulator, best recipe found so far", fr["model"], S1),
            (
                "emulator, first recipe",
                float(rec["arm_details"]["sealed_recipe_beside"]["frac"]),
                S1,
            ),
            ("copy the most similar climate", fr["nearest_analogue"], INK_MUTED),
            ("copy the nearest cell", fr["nearest_geographic"], INK_MUTED),
            ("the average forest", fr["training_mean"], INK_MUTED),
        ],
        xmax=1.0,
    )
    axes[1].set_title(
        f"B. The {rec['scored_cells']:,} cells of the two region folds the recipe search never "
        "scored (sealed, 2026-09-25)",
        loc="left",
    )
    hbars(
        axes[2],
        [
            ("a second run of the model", float(state["frac_rerun"]), INK),
            ("emulator", fst["model"], S1),
            ("copy the nearest cell", fst["nearest_geographic"], INK_MUTED),
            ("copy the most similar climate", fst["nearest_analogue"], INK_MUTED),
        ],
        xmax=0.16,
    )
    axes[2].set_title(
        f"C. The whole forest at once (19 quantities, every one in band), {state['rows']:,} pilot "
        "runs",
        loc="left",
    )
    axes[2].set_xlabel("share of cells inside the tolerance band")
    title(
        fig,
        "Not yet as good as a rerun: the emulator's vegetation carbon against the model's own",
        "Tolerance = max(10 %, the model's own run-to-run spread), per cell. Truth: the stored "
        "global spin-up at constant CO₂ (276.59 ppm),\nmean of model years 1450-1699, both seeds. "
        "Every emulator number is for cells in 15° regions it never trained on. Higher is better.",
        y=0.998,
    )
    fig.subplots_adjust(left=0.36, right=0.97, top=0.88, bottom=0.06)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 02 / 03 -- where the best map is wrong, and by how much.
# ---------------------------------------------------------------------------------------------
def load_predictions(exp: Path, corpus: Path) -> pl.DataFrame:
    p = pl.read_parquet(exp / "T-screen-spinup-vegc-r2" / "predictions.parquet")
    c = pl.read_parquet(corpus / "spinup-constco2" / "climate_spinup.parquet").sort("cell")
    assert np.array_equal(c["cell"].to_numpy(), np.arange(c.height))
    cell = p["cell"].to_numpy()
    t1, t2, w = (p[k].to_numpy() for k in ("t1", "t2", "w"))
    pred = p["pred_best"].to_numpy()

    def passes(x: Array) -> Array:
        a = (np.abs(x - t1) <= w * np.abs(t1)).astype(np.float64)
        b = (np.abs(x - t2) <= w * np.abs(t2)).astype(np.float64)
        return (a + b) / 2

    return p.with_columns(
        lon=pl.Series(c["lon"].to_numpy()[cell]),
        lat=pl.Series(c["lat"].to_numpy()[cell]),
        tm=pl.Series((t1 + t2) / 2),
        pass_map=pl.Series(passes(pred)),
        pass_rerun=pl.Series(
            (
                (np.abs(t1 - t2) <= w * np.abs(t2)).astype(float)
                + (np.abs(t2 - t1) <= w * np.abs(t1)).astype(float)
            )
            / 2
        ),
    )


def fig_error_map(d: pl.DataFrame, out: Path) -> None:
    lon, lat = d["lon"].to_numpy(), d["lat"].to_numpy()
    tm, pred = d["tm"].to_numpy(), d["pred_best"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(tm > 0, np.log(np.maximum(pred, 1e-9) / tm), np.nan)
    pct = np.clip(np.expm1(r), -0.5, 0.5)

    pm, pr = d["pass_map"].to_numpy() >= 0.5, d["pass_rerun"].to_numpy() >= 0.5
    cat = np.select([pm & pr, pr & ~pm, pm & ~pr], [0.0, 1.0, 2.0], 3.0)

    fig, axes = plt.subplots(2, 1, figsize=(8.6, 8.2), gridspec_kw={"hspace": 0.18})
    draw_map(
        axes[0],
        lon,
        lat,
        pct,
        title="A. emulator minus the model, relative (clipped at ±50 %)",
        cmap=DIV,
        norm=TwoSlopeNorm(vcenter=0.0, vmin=-0.5, vmax=0.5),
        label="emulator / model - 1",
    )
    cmap = ListedColormap([S1, S2, S3, "#d3d2ce"])
    ax = axes[1]
    ax.set_facecolor(OCEAN)
    ax.imshow(
        rasterise(lon, lat, cat),
        origin="lower",
        extent=(-180, 180, -90, 90),
        cmap=cmap,
        vmin=-0.5,
        vmax=3.5,
        interpolation="nearest",
    )
    ax.set_ylim(-60, 85)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    despine(ax, ())
    shares = [float((cat == k).mean()) for k in range(4)]
    labels = [
        f"both in band ({shares[0]:.0%})",
        f"a rerun is in band, the emulator is not ({shares[1]:.0%})",
        f"the emulator is in band, a rerun is not ({shares[2]:.0%})",
        f"neither ({shares[3]:.0%})",
    ]
    ax.legend(
        handles=[
            Patch(color=c, label=lab)
            for c, lab in zip([S1, S2, S3, "#d3d2ce"], labels, strict=True)
        ],
        loc="lower left",
        fontsize=8,
        labelcolor=INK_2,
        bbox_to_anchor=(0.0, -0.2),
        ncol=2,
    )
    ax.set_title("B. where the emulator falls short of a rerun", loc="left")
    title(
        fig,
        "Where the best vegetation-carbon map is wrong",
        f"{d.height:,} cells with trees, each predicted by a model that never saw its 15° region "
        "(best recipe from the development search).\nTruth: the stored constant-CO₂ spin-up, "
        "mean of both seeds over model years 1450-1699. 'In band': against at least one seed.",
    )
    fig.subplots_adjust(top=0.9)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def fig_scatter(d: pl.DataFrame, out: Path) -> None:
    tm, pred = d["tm"].to_numpy(), d["pred_best"].to_numpy()
    ok = (tm > 0) & (pred > 0)
    x, y = np.log10(tm[ok]), np.log10(pred[ok])
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.6, 4.4), gridspec_kw={"width_ratios": [1.15, 1]})
    hb = ax.hexbin(x, y, gridsize=90, bins="log", cmap=SEQ, mincnt=1, linewidths=0)
    lo, hi = np.percentile(x, 0.2), x.max()
    g = np.array([lo, hi])
    ax.plot(g, g, color=INK, lw=1.0)
    for f in (0.9, 1.1):
        ax.plot(g, g + np.log10(f), color=S2, lw=1.0, ls=(0, (4, 3)))
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("the model: vegetation carbon (log₁₀ gC m⁻²)")
    ax.set_ylabel("the emulator (log₁₀ gC m⁻²)")
    ax.set_title("A. cell by cell; dashed = ±10 %", loc="left")
    cb = fig.colorbar(hb, ax=ax, fraction=0.04, pad=0.02)
    cb.outline.set_visible(False)
    cb.set_label("cells", color=INK_2, fontsize=8)
    despine(ax)

    rel = np.clip(pred[ok] / tm[ok] - 1, -0.6, 0.6)
    ax2.hist(rel, bins=121, color=S1)
    for v in (-0.1, 0.1):
        ax2.axvline(v, color=S2, lw=1.4, ls=(0, (4, 3)))
    inside = float(np.mean(np.abs(pred[ok] / tm[ok] - 1) <= 0.1))
    ax2.set_title(f"B. relative error; {inside:.0%} within ±10 % of the two-seed mean", loc="left")
    ax2.set_xlabel("emulator / model - 1 (clipped at ±60 %)")
    ax2.set_ylabel("cells")
    despine(ax2)
    title(
        fig,
        "The broad pattern is right; the cell-level precision is not",
        "Same predictions as the map figure. The emulator explains 98 % of the variation in log "
        "carbon, but a rerun-grade map needs most cells inside ±10 %.",
        y=1.06,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 04 -- the learning curve: coverage, not density.
# ---------------------------------------------------------------------------------------------
def fig_learning_curve(lc: dict[str, Any], rerun: float, out: Path) -> None:
    rows = lc["rows"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.8, 4.3))
    full = next(r for r in rows if r["frac"] == 1.0)
    series = (
        ("tiles", S1, "fewer 15° regions (less of the climate range)"),
        ("cells", S2, "every region, fewer cells in each"),
    )
    for mode, col, lab in series:
        pts = sorted([r for r in rows if r["mode"] == mode] + [full], key=lambda r: r["frac"])
        fr = sorted({r["frac"] for r in pts})
        n = [np.mean([r["train_cells_total"] for r in pts if r["frac"] == f]) for f in fr]
        for a, key in ((ax, "dev_frac"), (ax2, "median_abs_log_err")):
            m = [np.mean([r[key] for r in pts if r["frac"] == f]) for f in fr]
            a.plot(n, m, color=col, lw=2.0, label=lab)
            a.plot(
                [r["train_cells_total"] for r in pts],
                [r[key] for r in pts],
                "o",
                color=col,
                markersize=5,
                markeredgecolor=SURFACE,
                markeredgewidth=1.2,
            )
    ax.axhline(rerun, color=INK, lw=1.2, ls=(0, (4, 3)))
    ax.text(
        5200, rerun + 0.012, f"a second run of the model, {rerun:.0%}", color=INK_2, fontsize=8.5
    )
    ax.set_ylim(0, 0.95)
    ax.set_ylabel("share of cells inside the band")
    ax.set_title("A. share of cells in band", loc="left")
    ax.legend(loc="lower right", fontsize=8, labelcolor=INK_2)
    slopes = lc.get("slopes", {})
    ax2.set_yscale("log")
    pct = FuncFormatter(lambda v, _: f"{v:.0%}")
    ax2.yaxis.set_major_formatter(pct)
    ax2.yaxis.set_minor_formatter(pct)
    ax2.set_ylabel("typical error (median |log ratio|, about relative)")
    ax2.set_title(
        f"B. typical error ~ $N^{{{slopes.get('tiles', float('nan')):.2f}}}$ by region, "
        f"~ $N^{{{slopes.get('cells', float('nan')):.2f}}}$ by density",
        loc="left",
    )
    for a in (ax, ax2):
        a.set_xscale("log")
        a.set_xlabel("cells the map was trained on")
        despine(a)
    title(
        fig,
        "More places help, more cells in the same places barely do",
        "Development diagnostic, not a sealed test: 36,863 cells with trees in folds 0-2, the best "
        "recipe, trained on the stored spin-up only, one fit per point.\nThe map is limited by how "
        "much of the climate-soil range it has seen: new climates, not denser sampling, "
        "would move it.",
        y=1.07,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 05 -- near-identical neighbours.
# ---------------------------------------------------------------------------------------------
def fig_twins(tw: dict[str, Any], out: Path) -> None:
    b = tw["by_distance"]
    names = ["closest 10 %", "10-25 %", "25-50 %", "50-75 %", "furthest 25 %"][: len(b)]
    xs = np.arange(len(b))
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.3), gridspec_kw={"width_ratios": [1.2, 1]})
    for key, col, lab in (
        ("rerun", INK, "a second run of the same cell"),
        ("map", S1, "the emulator"),
        ("twin", S2, "copying the neighbour's true value"),
    ):
        v = [r[key] for r in b]
        ax.plot(
            xs,
            v,
            color=col,
            lw=2.0,
            marker="o",
            markersize=6,
            markeredgecolor=SURFACE,
            markeredgewidth=1.2,
            label=lab,
        )
    ax.set_xticks(xs, names)
    ax.set_ylim(0, 1)
    ax.set_xlabel(
        f"how alike the two neighbours' inputs are ({tw['inputs']} climate and soil inputs)"
    )
    ax.set_ylabel("share of cells inside the band")
    ax.set_title("A. neighbours on the same soil, by input similarity", loc="left")
    ax.legend(loc="lower left", fontsize=8, labelcolor=INK_2)
    despine(ax)

    parts = tw["difference_decomposition"]
    lab2 = ["near-identical\ninputs", "similar\ninputs", "all\nneighbours"][: len(parts)]
    noise = np.array([p["seed_noise_share"] for p in parts])
    mapx = np.array([max(p["map"], 0.0) for p in parts])
    rest = np.clip(1 - noise - mapx, 0, None)
    y = np.arange(len(parts))[::-1]
    ax2.barh(y, noise, color="#bdbcb8", height=0.6, label="the model's run-to-run noise")
    ax2.barh(y, mapx, left=noise, color=S1, height=0.6, label="explained by the emulator")
    ax2.barh(y, rest, left=noise + mapx, color=S4, height=0.6, label="explained by neither")
    for yy, a, m in zip(y, noise, mapx, strict=True):
        ax2.text(
            a + m / 2,
            yy,
            f"{m:.0%}",
            ha="center",
            va="center",
            color=SURFACE,
            fontsize=8.5,
            fontweight="semibold",
        )
    ax2.set_yticks(y, lab2)
    ax2.set_xlim(0, 1)
    ax2.set_xlabel("share of the variance of the carbon difference between neighbours")
    ax2.set_title("B. what the difference between neighbours is made of", loc="left")
    ax2.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=8, labelcolor=INK_2, ncol=1
    )
    ax2.grid(axis="y", visible=False)
    ax2.tick_params(axis="y", length=0)
    despine(ax2, ("bottom",))
    title(
        fig,
        "Cells that look identical to the emulator differ more than two runs of one cell",
        "Development diagnostic: adjacent 0.5° cells on the same soil type, stored constant-CO₂ "
        "spin-up. Even an almost identical neighbour's true carbon\nlands in the band less often "
        "than a rerun does, so a map of these inputs must resolve finer differences than "
        "neighbours show.",
        y=1.07,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 06 -- the climate-response tests.
# ---------------------------------------------------------------------------------------------
def _result(exp_id: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in (REPO / "experiments" / exp_id / "result.jsonl").read_text().splitlines():
        r = json.loads(line)
        out[r["arm"]] = float(r["value"])
    return out


def fig_warming_tests(out: Path) -> None:
    resp = _result("X-20260921-pilot-warming-response-constco2-resealed")
    comp = _result("X-20260921-pilot-composition-response-constco2-resealed")
    equi = _result("X-20260923-equilibrium-from-climate")
    panels = (
        (
            "A. how the forest's state CHANGES under a new climate",
            resp,
            VERDICT_NUMBERS["response"],
        ),
        ("B. how the species mix changes", comp, VERDICT_NUMBERS["composition"]),
        ("C. the settled forest from climate and soil alone", equi, VERDICT_NUMBERS["equilibrium"]),
    )
    fig, axes = plt.subplots(3, 1, figsize=(8.6, 7.6), gridspec_kw={"hspace": 0.75})
    for ax, (head, res, vn) in zip(axes, panels, strict=True):
        best_null = max(v for k, v in res.items() if k != "model")
        rows = [("the emulator", res["model"], S1)]
        if "blind" in vn:
            rows.append(("an emulator that never sees the climate change", vn["blind"], S4))
        rows.append(("best simple comparison (copy or average)", best_null, INK_MUTED))
        hbars(ax, rows, xmax=1.0, fmt="{:.3f}")
        ax.axvline(vn["bar"], color=S2, lw=1.6, ls=(0, (4, 3)))
        ax.text(vn["bar"], len(rows) - 0.35, f" pass bar {vn['bar']:.3f}", color=S2, fontsize=8)
        ax.axvline(vn["ceiling"], color=INK, lw=1.2, ls=(0, (1, 2)))
        ax.text(
            vn["ceiling"],
            len(rows) - 0.35,
            f"best reachable {vn['ceiling']:.2f} ",
            color=INK_2,
            fontsize=8,
            ha="right",
        )
        ax.set_title(head, loc="left")
        ax.set_ylim(-0.6, len(rows) - 0.1)
    axes[-1].set_xlabel("skill (0 = no better than the simplest guess, 1 = perfect)")
    title(
        fig,
        "The climate response is learnable where the data can show it — with a large caveat",
        "Sealed tests on the constant-CO₂ pilot: 200 cells x 30 designed climates (5,800-6,000 "
        "runs), 15° regions held out.\nAll three pass their bar. But an emulator that never sees "
        "the climate change already scores 0.36 and 0.31: only +0.20 and +0.14\nof the scores "
        "read the forcing. Not a fidelity claim: 200 of 54,020 tree-bearing cells.",
        y=1.02,
    )
    fig.subplots_adjust(left=0.36, right=0.97, top=0.86)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 07 / 08 -- the emulated restart file, continued in the real model.
# ---------------------------------------------------------------------------------------------
def _rel(series: list[float]) -> Array:
    a = np.asarray(series, dtype=np.float64)
    return 100 * (a / a[0] - 1)


def fig_continuation(exp: Path, glob_scores: dict[str, Any] | None, out: Path) -> None:
    m = json.loads((exp / "X-20260925-continuation-same-window" / "metrics.json").read_text())
    ref = m["reference"]
    md = m["arm_details"]["model"]
    null_10 = float(m["arms"]["restart_1999_continuation"]) + float(ref["real_10yr"]["folds_3_4"])
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.3), gridspec_kw={"width_ratios": [1.2, 1]})
    if glob_scores is not None:
        years = np.arange(1, 31)
        for key, col, lab in (
            ("emulated", S1, "emulated restart (constant CO₂)"),
            ("restart_1999", S2, "the model's own 1999 forest (grown at 367 ppm)"),
        ):
            ax.plot(years, _rel(glob_scores[key]["vegc_sum_by_year"]), color=col, lw=2.0, label=lab)
        ax.axhline(0, color=INK_MUTED, lw=0.8)
        ax.set_xlabel("year of the continuation run")
        ax.set_ylabel("vegetation carbon, % change from year 1")
        ax.legend(loc="center right", fontsize=8, labelcolor=INK_2)
        ax.set_title("A. total carbon, all cells, year by year", loc="left")
    else:
        ax.text(0.5, 0.5, "global series not yet computed", ha="center", color=INK_MUTED)
    despine(ax)

    groups = ["year 1", "years 1-10", "years 21-30"]
    emu = [md["y01"]["frac"], md["y01_10"]["frac"], md["y21_30"]["frac"]]
    real = [
        ref["real_1yr"]["folds_3_4"],
        ref["real_10yr"]["folds_3_4"],
        ref["real_10yr"]["folds_3_4"],
    ]
    xs = np.arange(3)
    wd = 0.36
    ax2.bar(xs - wd / 2, real, wd, color=INK_MUTED, label="a real run, same window")
    ax2.bar(xs + wd / 2, emu, wd, color=S1, label="the emulated restart")
    for x, a, b in zip(xs, real, emu, strict=True):
        ax2.text(x - wd / 2, a + 0.01, f"{a:.0%}", ha="center", fontsize=8, color=INK_2)
        ax2.text(
            x + wd / 2,
            b + 0.01,
            f"{b:.0%}",
            ha="center",
            fontsize=8,
            color=INK,
            fontweight="semibold",
        )
    ax2.axhline(
        null_10,
        color=S2,
        lw=1.4,
        ls=(0, (4, 3)),
        label=f"the model's own 1999 forest, years 1-10 ({null_10:.0%})",
    )
    ax2.set_xticks(xs, groups)
    ax2.set_ylim(0, 0.8)
    ax2.set_ylabel("share of cells inside the band")
    ax2.set_title(f"B. in band, {m['scored_cells']:,} cells of held-out regions", loc="left")
    ax2.legend(loc="upper left", fontsize=8, labelcolor=INK_2)
    ax2.grid(axis="x", visible=False)
    despine(ax2)
    title(
        fig,
        "The emulated restart file runs in the real model, and falls short over ten years",
        "Sealed test (2026-09-25): the emulator's restart continued 30 years in LPJmL-FIT at "
        "276.59 ppm, against a real run over the same window.\nYear 1 is as good as a real run; "
        "years 1-10 are not (49 % vs 62 %), mostly because of a die-off in year 5 (next figure).",
        y=1.07,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def fig_die_off(shuffle: dict[str, Any] | None, fixes: dict[str, Any], out: Path) -> None:
    years = np.arange(1, 31)
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.2, 4.3), sharey=True)
    if shuffle is not None:
        for key, col, lab in (
            ("r1999_367", S1, "the model's own 1999 forest"),
            ("shuffle_equal", S2, "same trees, dealt to random patches"),
            ("shuffle_keep", S3, "same, each patch keeps its tree count"),
        ):
            ax.plot(years, _rel(shuffle[key]["vegc_sum_by_year"]), color=col, lw=2.0, label=lab)
        ax.legend(loc="lower right", fontsize=8, labelcolor=INK_2)
    ax.set_title("A. cause: the model's own trees, re-dealt (367 ppm)", loc="left")
    for key, col, lab in (
        ("v3vegc", S2, "emulated: trees dealt at random"),
        ("v6layout", S3, "emulated: copy the real layout by tree size"),
        ("v7patches", S1, "emulated: move whole real patches"),
    ):
        ax2.plot(years, _rel(fixes[key]["vegc_sum_by_year"]), color=col, lw=2.0, label=lab)
    ax2.legend(loc="lower right", fontsize=8, labelcolor=INK_2)
    ax2.set_title("B. fixes tried (276.59 ppm)", loc="left")
    for a in (ax, ax2):
        a.axhline(0, color=INK_MUTED, lw=0.8)
        a.axvline(5, color=GRID, lw=6, zorder=0)
        a.set_xlabel("year of the continuation run")
        despine(a)
    ax.set_ylabel("vegetation carbon, % change from year 1")
    title(
        fig,
        "The year-5 die-off comes from mixing trees between forest patches",
        "Development diagnostic on a 51-run sample (2,904 cells). Light is shared within a patch; "
        "dealing trees to random patches puts trees under strangers,\nwhere they starve for five "
        "years and die together. Moving whole patches cuts the drop from about 12 % to about "
        "3.5 %, but not the "
        "per-cell carbon error.",
        y=1.07,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# 09 -- the band, on the current basis.
# ---------------------------------------------------------------------------------------------
def fig_band(corpus: Path, d: pl.DataFrame, out: Path) -> None:
    t = pl.read_parquet(corpus / "spinup-constco2" / "spinup_truth.parquet").sort("cell")
    h1 = t["vegc_half1_s1"].to_numpy().astype(float)[d["cell"].to_numpy()]
    h2 = t["vegc_half1_s2"].to_numpy().astype(float)[d["cell"].to_numpy()]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.abs(h1 - h2) / ((h1 + h2) / 2)
    s = s[np.isfinite(s)]
    w = d["w"].to_numpy()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.9))
    ax.hist(np.clip(s, 0, 0.6), bins=90, color=S1)
    ax.axvline(0.10, color=S2, lw=1.6, ls=(0, (4, 3)))
    ax.text(0.106, ax.get_ylim()[1] * 0.9, "the 10 % floor", color=S2, fontsize=8.5)
    for q, yy in ((50, 0.7), (90, 0.5)):
        v = float(np.percentile(s, q))
        ax.axvline(v, color=INK_MUTED, lw=1.0)
        ax.text(v + 0.006, ax.get_ylim()[1] * yy, f"p{q} = {v:.1%}", color=INK_2, fontsize=8)
    ax.set_xlabel("relative difference between two runs (model years 1200-1449)")
    ax.set_ylabel("cells")
    ax.set_title("A. the model's own reproducibility", loc="left")
    despine(ax)
    wide = w[w > 0.10]
    ax2.hist(np.clip(wide, 0, 0.6), bins=60, color=S3)
    ax2.set_xlabel("the tolerance band used, where it is wider than 10 %")
    ax2.set_ylabel("cells")
    ax2.set_title(
        f"B. band = max(10 %, spread): wider than 10 % in {np.mean(w > 0.10):.0%} of cells",
        loc="left",
    )
    despine(ax2)
    title(
        fig,
        "Why the tolerance is not simply 10 %",
        f"The stored global spin-up at constant CO₂, {d.height:,} cells with trees. The two seeds' "
        "vegetation carbon over an earlier window sets each cell's band,\nso the band never "
        "charges the emulator for noise no emulator could predict.",
        y=1.08,
    )
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def _maybe(p: Path) -> dict[str, Any] | None:
    return json.loads(p.read_text()) if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()
    style()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    exp = Path(str(paths()["scratch"]["exp"]))
    corpus = Path(str(paths()["scratch"]["corpus"]))

    fig_acceptance(exp, out / "01_acceptance_vegc.png")
    d = load_predictions(exp, corpus)
    fig_error_map(d, out / "02_vegc_error_map.png")
    fig_scatter(d, out / "03_vegc_scatter.png")
    lc = json.loads((exp / "T-vegc-learning-curve" / "learning_curve.json").read_text())
    fig_learning_curve(lc, 0.8528, out / "04_learning_curve.png")
    fig_twins(
        json.loads((exp / "T-vegc-twins" / "twins.json").read_text()), out / "05_near_twins.png"
    )
    fig_warming_tests(out / "06_climate_response_tests.png")
    fig_continuation(
        exp,
        _maybe(exp / "X-fig-contglobal" / "sample_scores.json"),
        out / "07_restart_continuation.png",
    )
    fixes = json.loads((exp / "X-diag-contsample-v6v7" / "sample_scores.json").read_text())
    fig_die_off(
        _maybe(exp / "X-fig-contsample-shuffle" / "sample_scores.json"),
        fixes,
        out / "08_year5_die_off.png",
    )
    fig_band(corpus, d, out / "09_tolerance_band.png")
    v0 = corpus / "v0"
    fig_spinup(
        pl.read_parquet(v0 / "spin_global_trajectory.parquet"),
        json.loads((v0 / "spin_convergence.json").read_text()),
        out / "10_spinup_convergence.png",
    )
    for p in sorted(out.glob("[0-9][0-9]_*.png")):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
