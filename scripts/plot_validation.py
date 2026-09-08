#!/usr/bin/env python
"""Every figure that says what the emulator does and does not do.

    scripts/plot_validation.py --exp-dir /p/tmp/jamirp/vegemu/exp/map-response-v0 --out figures/

The figures are the argument, so they are built to be read rather than to look busy. Rules applied
throughout, from the project's data-visualisation guidance:

  * form follows the data's job -- magnitude across identities is a bar chart, a spatial field is a
    map, a paired comparison is a scatter with the 1:1 line and the acceptance band drawn on it;
  * one hue light-to-dark for MAGNITUDE, two hues with a neutral GRAY midpoint for POLARITY
    (an error that can go either way), never a rainbow;
  * categorical colours are assigned in a fixed order and never cycled, and the three-colour
    all-pairs-validated subset is used wherever marks can land next to each other (scatter, maps);
  * one axis per panel, no dual scales; recessive grid and axes; values labelled directly on bars
    rather than left to the reader;
  * text always in ink colours, never in a series colour.

Palette values are the documented reference instance. `node` is absent on this cluster, so the
validator could not be re-run here; the three-slot subset used for all-pairs forms is the one the
reference documents as passing every gate in both modes, and no colour was chosen by eye.

⚠ The figures are LIGHT MODE ONLY, deliberately: they are static PNGs for a research repo and a
paper, not a themed web page, and an automatic inversion is not a designed dark mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import polars as pl
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from vegemu.paths import paths

# ---------------------------------------------------------------------------------------------
# Design tokens. Roles, not raw hex, everywhere below.
# ---------------------------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#7a7975"
GRID = "#e5e4e0"
# Categorical, fixed order. Slots 1-3 are the all-pairs-validated subset.
S1, S2, S3, S4, S5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
# Sequential: one hue, light -> dark.
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#256abf", "#184f95", "#0d366b"]
)
# Diverging: two hues, NEUTRAL GRAY midpoint -- the midpoint must read as "nothing".
DIV = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#0d366b", "#2a78d6", "#9ec5f4", "#f0efec", "#f2b0b0", "#e34948", "#8f2222"]
)
OCEAN = "#f4f3f0"

BIOME = {
    "Amazon": 12045,
    "Sahel": 18371,
    "Iberia": 33335,
    "Hainich": 42490,
    "Siberia": 52059,
}
LABELS = {
    "stems_per_patch": "stems per patch",
    "agb": "above-ground biomass\n(gC m$^{-2}$)",
    "lai": "leaf area index",
    "soilc": "soil carbon (gC m$^{-2}$)",
    "height_p50": "median stem height (m)",
    "wooddens_p50": "median wood density\n(gC m$^{-3}$)",
    "sla_p50": "median specific leaf area\n(m$^{2}$ gC$^{-1}$)",
    "k_root_p50": "median root conductivity",
    "D95max_p50": "median rooting depth (mm)",
    "longevity_p50": "median leaf longevity (yr)",
}
ARM_LABEL = {
    "model": "the emulator",
    "nearest_analogue": "nearest climate analogue",
    "geographic_address": "nearest cell (address only)",
    "climatological_mean": "the average forest",
    "shuffled_target": "shuffled (chance)",
    "no_response": "predict no change",
    "mean_response": "everywhere changes the same",
    "geographic_address_response": "nearest cell's change",
    "shuffled_response": "shuffled (chance)",
}


def style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelcolor": INK_2,
            "ytick.labelcolor": INK_2,
            "text.color": INK,
            "font.size": 9,
            "axes.titlesize": 10.5,
            "axes.titleweight": "semibold",
            "legend.frameon": False,
            "figure.dpi": 140,
            "lines.linewidth": 2.0,
            "lines.markersize": 4,
        }
    )


def despine(ax: plt.Axes, keep: tuple[str, ...] = ("left", "bottom")) -> None:
    for side, spine in ax.spines.items():
        spine.set_visible(side in keep)


def rasterise(
    lon: npt.NDArray[np.float64], lat: npt.NDArray[np.float64], value: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Scatter cell values onto the 0.5-degree lon/lat raster. NaN where there is no cell."""
    grid = np.full((360, 720), np.nan)
    iy = np.clip(((lat + 90.0) / 0.5).astype(int), 0, 359)
    ix = np.clip(((lon + 180.0) / 0.5).astype(int), 0, 719)
    grid[iy, ix] = value
    return grid


def draw_map(
    ax: plt.Axes,
    lon: npt.NDArray[np.float64],
    lat: npt.NDArray[np.float64],
    value: npt.NDArray[np.float64],
    *,
    title: str,
    cmap: object,
    norm: object | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
    label: str = "",
) -> object:
    grid = rasterise(lon, lat, value)
    ax.set_facecolor(OCEAN)
    im = ax.imshow(
        grid,
        origin="lower",
        extent=(-180, 180, -90, 90),
        cmap=cmap,
        norm=norm,
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
    )
    ax.set_title(title, loc="left")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    despine(ax, ())
    ax.set_ylim(-60, 85)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.028, pad=0.012)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=INK_MUTED, labelsize=7.5, length=2)
    if label:
        cb.set_label(label, color=INK_2, fontsize=8)
    return im


# ---------------------------------------------------------------------------------------------
# Figure 1 & 2 -- every arm beside every null. Invariant 1, drawn.
# ---------------------------------------------------------------------------------------------
def fig_arms(
    arms: dict[str, float],
    *,
    threshold: float,
    best_null: float,
    title: str,
    subtitle: str,
    xlabel: str,
    out: Path,
    zero_line: bool = False,
) -> None:
    order = sorted(arms.items(), key=lambda kv: kv[1])
    names = [ARM_LABEL.get(k, k) for k, _ in order]
    values = [v for _, v in order]
    colours = [S1 if k == "model" else INK_MUTED for k, _ in order]

    fig, ax = plt.subplots(figsize=(7.6, 0.52 * len(order) + 2.1))
    ax.barh(names, values, color=colours, height=0.6)
    span = max(values) - min(*values, 0.0)
    for y, (k, v) in enumerate(order):
        offset = 0.012 * span if v >= 0 else -0.012 * span
        ax.text(
            v + offset,
            y,
            f"{v:+.4f}" if zero_line else f"{v:.4f}",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=8.5,
            color=INK if k == "model" else INK_2,
            fontweight="semibold" if k == "model" else "normal",
        )
    gate = best_null + threshold
    ax.axvline(gate, color=S2, lw=1.6, ls=(0, (4, 3)))
    ax.text(
        gate,
        len(order) - 0.35,
        f"  pre-registered gate {gate:.3f}\n  (best null + {threshold:.3f})",
        color=S2,
        fontsize=8,
        va="top",
    )
    if zero_line:
        ax.axvline(0.0, color=INK_MUTED, lw=1.0)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    despine(ax, ("bottom",))
    ax.tick_params(axis="y", length=0)
    fig.suptitle(title, x=0.012, ha="left", fontsize=12, fontweight="semibold", color=INK)
    ax.set_title(subtitle, loc="left", fontsize=9, color=INK_2, fontweight="normal", pad=26)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 3 -- per quantity, the emulator against the strongest null.
# ---------------------------------------------------------------------------------------------
def fig_per_quantity(per_q: dict[str, dict[str, float]], best_null: str, out: Path) -> None:
    quantities = list(per_q["model"].keys())
    model = np.array([per_q["model"][q] for q in quantities])
    null = np.array([per_q[best_null][q] for q in quantities])
    order = np.argsort(-model)
    quantities = [quantities[i] for i in order]
    model, null = model[order], null[order]

    y = np.arange(len(quantities))
    fig, ax = plt.subplots(figsize=(7.8, 0.34 * len(quantities) + 2.0))
    ax.barh(y + 0.19, model, height=0.34, color=S1, label="the emulator")
    ax.barh(y - 0.19, null, height=0.34, color=S3, label=ARM_LABEL.get(best_null, best_null))
    ax.set_yticks(y, [q.replace("_", " ") for q in quantities], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("fraction of held-out cells inside the acceptance band")
    ax.set_xlim(0, 1)
    ax.grid(axis="y", visible=False)
    despine(ax, ("bottom",))
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right", fontsize=8.5, labelcolor=INK_2)
    fig.suptitle(
        "Per quantity the emulator is good; ALL 22 at once is the hard part",
        x=0.012,
        ha="left",
        fontsize=12,
        fontweight="semibold",
        color=INK,
    )
    ax.set_title(
        "Each bar is one quantity on its own. The acceptance test requires every bar to hit in the "
        "SAME cell.",
        loc="left",
        fontsize=9,
        color=INK_2,
        fontweight="normal",
        pad=24,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 4 -- the map the emulator is FOR: truth, prediction, and the signed relative error.
# ---------------------------------------------------------------------------------------------
def fig_maps(frame: pl.DataFrame, quantity: str, out: Path) -> None:
    lon = frame["lon"].to_numpy()
    lat = frame["lat"].to_numpy()
    truth = frame[f"truth_{quantity}"].to_numpy()
    pred = frame[f"pred_{quantity}"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(np.abs(truth) > 0, (pred - truth) / np.abs(truth), np.nan)

    hi = float(np.nanpercentile(truth, 99))
    fig, axes = plt.subplots(3, 1, figsize=(8.4, 9.2))
    draw_map(axes[0], lon, lat, truth, title="LPJmL-FIT (the truth)", cmap=SEQ, vmin=0, vmax=hi,
             label=LABELS.get(quantity, quantity).replace("\n", " "))
    draw_map(axes[1], lon, lat, pred, title="the emulator, on held-out spatial blocks", cmap=SEQ,
             vmin=0, vmax=hi, label=LABELS.get(quantity, quantity).replace("\n", " "))
    draw_map(axes[2], lon, lat, rel, title="relative error (emulator - truth) / truth",
             cmap=DIV, norm=TwoSlopeNorm(vcenter=0.0, vmin=-1.0, vmax=1.0),
             label="fraction of the truth")
    fig.suptitle(
        f"{LABELS.get(quantity, quantity).replace(chr(10), ' ')}: climate alone, no coordinates",
        x=0.012, ha="left", fontsize=12, fontweight="semibold", color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 5 -- predicted against true, with the acceptance band drawn on it.
# ---------------------------------------------------------------------------------------------
def fig_scatter(frame: pl.DataFrame, quantities: list[str], out: Path) -> None:
    ncol = 3
    nrow = int(np.ceil(len(quantities) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.1 * ncol, 3.05 * nrow))
    axes = np.atleast_1d(axes).ravel()
    for ax, q in zip(axes, quantities, strict=False):
        truth = frame[f"truth_{q}"].to_numpy()
        pred = frame[f"pred_{q}"].to_numpy()
        band = frame[f"band_{q}"].to_numpy()
        ok = np.isfinite(truth) & np.isfinite(pred) & (truth > 0) & (pred > 0)
        t, p, b = truth[ok], pred[ok], band[ok]
        lo = float(np.nanpercentile(t, 0.5))
        hi = float(np.nanpercentile(t, 99.5))
        ax.hexbin(t, p, gridsize=44, bins="log", cmap=SEQ, mincnt=1, xscale="log", yscale="log",
                  extent=(np.log10(lo), np.log10(hi), np.log10(lo), np.log10(hi)),
                  linewidths=0)
        xs = np.geomspace(lo, hi, 60)
        ax.plot(xs, xs, color=INK_2, lw=1.2)
        rel = float(np.nanmedian(b / np.maximum(t, 1e-12)))
        ax.plot(xs, xs * (1 + rel), color=S2, lw=1.2, ls=(0, (4, 3)))
        ax.plot(xs, xs * (1 - rel), color=S2, lw=1.2, ls=(0, (4, 3)))
        inside = float(np.mean(np.abs(p - t) <= b))
        ax.set_title(f"{LABELS.get(q, q)}\n{inside:.0%} inside the band", loc="left", fontsize=9)
        ax.set_xlabel("LPJmL-FIT")
        ax.set_ylabel("the emulator")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        despine(ax)
    for ax in axes[len(quantities) :]:
        ax.set_visible(False)
    fig.suptitle(
        "Held-out cells, one quantity per panel. Dashed lines: the median acceptance band.",
        x=0.012, ha="left", fontsize=11.5, fontweight="semibold", color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 6 -- the trait DISTRIBUTIONS, which a median-only test would miss.
# ---------------------------------------------------------------------------------------------
def fig_distributions(frame: pl.DataFrame, out: Path) -> None:
    traits = ["height", "wooddens", "sla", "D95max"]
    fig, axes = plt.subplots(1, len(traits), figsize=(3.2 * len(traits), 3.7))
    quant = [10, 50, 90]
    for ax, trait in zip(np.atleast_1d(axes).ravel(), traits, strict=True):
        for i, (name, cell) in enumerate(BIOME.items()):
            row = frame.filter(pl.col("cell") == cell)
            if row.height == 0:
                continue
            t = [float(row[f"truth_{trait}_p{q}"][0]) for q in quant]
            p = [float(row[f"pred_{trait}_p{q}"][0]) for q in quant]
            colour = [S1, S2, S3, S4, S5][i % 5]
            tag = name if trait == "height" else None
            ax.plot(quant, t, color=colour, lw=2.0, marker="o", label=tag)
            ax.plot(quant, p, color=colour, lw=1.6, ls=(0, (3, 2)), marker="s", markersize=3.5)
        heading = LABELS.get(f"{trait}_p50", trait).replace("median ", "")
        ax.set_title(heading, loc="left", fontsize=9)
        ax.set_xticks(quant, [f"p{q}" for q in quant])
        ax.set_xlabel("quantile of the stem population")
        despine(ax)
    axes[0].set_ylabel("value")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncols=5, fontsize=8.5, labelcolor=INK_2,
               bbox_to_anchor=(0.995, 0.995))
    fig.suptitle(
        "Trait distributions at five biome cells — solid: LPJmL-FIT, dashed: the emulator",
        x=0.012, ha="left", fontsize=11.5, fontweight="semibold", color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 7 -- the kill test. The figure that says what FAILED.
# ---------------------------------------------------------------------------------------------
def fig_response(frame: pl.DataFrame, quantities: list[str], out: Path) -> None:
    ncol = 2
    nrow = int(np.ceil(len(quantities) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.0 * ncol, 3.7 * nrow))
    axes = np.atleast_1d(axes).ravel()
    for ax, q in zip(axes, quantities, strict=False):
        dt = frame[f"delta_truth_{q}"].to_numpy()
        dp = frame[f"delta_pred_{q}"].to_numpy()
        ok = np.isfinite(dt) & np.isfinite(dp)
        dt, dp = dt[ok], dp[ok]
        lim = float(np.nanpercentile(np.abs(dt), 99.5))
        ax.hexbin(dt, dp, gridsize=48, bins="log", cmap=SEQ, mincnt=1,
                  extent=(-lim, lim, -lim, lim), linewidths=0)
        ax.plot([-lim, lim], [-lim, lim], color=INK_2, lw=1.2)
        ax.axhline(0, color=S2, lw=1.4, ls=(0, (4, 3)))
        denom = float((dt**2).sum())
        skill = 1 - float(((dp - dt) ** 2).sum()) / denom if denom > 0 else np.nan
        ax.set_title(
            f"{LABELS.get(q, q)}\nskill {skill:+.3f}  (predicting no change scores 0.000)",
            loc="left", fontsize=9,
        )
        ax.set_xlabel("true change, 1999 → 2100")
        ax.set_ylabel("predicted change")
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        despine(ax)
    for ax in axes[len(quantities) :]:
        ax.set_visible(False)
    fig.suptitle(
        "THE KILL TEST FAILED: the predicted change is worse than predicting no change",
        x=0.012, ha="left", fontsize=12, fontweight="semibold", color=INK,
    )
    fig.text(
        0.012, 0.955,
        "Dashed orange line: the no-change null. Grey diagonal: a perfect prediction.",
        fontsize=9, color=INK_2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.945))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def fig_response_map(frame: pl.DataFrame, quantity: str, out: Path) -> None:
    lon = frame["lon"].to_numpy()
    lat = frame["lat"].to_numpy()
    dt = frame[f"delta_truth_{quantity}"].to_numpy()
    dp = frame[f"delta_pred_{quantity}"].to_numpy()
    lim = float(np.nanpercentile(np.abs(dt), 98))
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 6.3))
    norm = TwoSlopeNorm(vcenter=0.0, vmin=-lim, vmax=lim)
    draw_map(axes[0], lon, lat, dt, title="LPJmL-FIT's own change, 1999 → 2100 (high emissions)",
             cmap=DIV, norm=norm, label=LABELS.get(quantity, quantity).replace("\n", " "))
    draw_map(axes[1], lon, lat, dp, title="the emulator's predicted change",
             cmap=DIV, norm=norm, label=LABELS.get(quantity, quantity).replace("\n", " "))
    fig.suptitle(
        "The pattern of change is not reproduced — this is what the failed skill score looks like",
        x=0.012, ha="left", fontsize=12, fontweight="semibold", color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 8 -- the spin-up that never converged.
# ---------------------------------------------------------------------------------------------
def fig_spinup(traj: pl.DataFrame, summary: dict[str, object], out: Path) -> None:
    year = traj["year"].to_numpy()
    g1 = traj["global_vegc_pgc_seed1"].to_numpy()
    g2 = traj["global_vegc_pgc_seed2"].to_numpy()
    k = 30
    rm = np.convolve(g1, np.ones(k) / k, mode="valid")
    rm_year = year[k - 1 :]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    ax.plot(year, g1, color=SEQ(0.28), lw=0.9, label="annual, seed 1")
    ax.plot(year, g2, color=SEQ(0.14), lw=0.9, label="annual, seed 2")
    ax.plot(rm_year, rm, color=S1, lw=2.4, label="30-year running mean (seed 1)")
    for y in (200, 500, 1000):
        ax.plot([y], [g1[y - 1]], marker="o", color=S2, markersize=6, zorder=5)
        ax.annotate(
            f"year {y}\n{g1[y - 1]:.0f} Pg C",
            (y, g1[y - 1]),
            textcoords="offset points",
            xytext=(-6, -34 if y == 1000 else 12),
            fontsize=8.5,
            color=S2,
            ha="right" if y == 1000 else "left",
        )
    trend = float(summary["global_trend_pct_per_century_last200"])  # type: ignore[arg-type]
    ax.set_xlabel("year of the 1000-year spin-up")
    ax.set_ylabel("global vegetation carbon (Pg C)")
    ax.legend(loc="lower right", fontsize=8.5, labelcolor=INK_2)
    despine(ax)
    fig.suptitle(
        "The 1000-year spin-up has not converged", x=0.012, ha="left", fontsize=12,
        fontweight="semibold", color=INK,
    )
    ax.set_title(
        f"Still rising at {trend:+.1f} % per century at the end of the run; the two seeds "
        f"agree on it to {float(summary['global_two_seed_diff_pct']):.2f} %.\n"
        "So the stored state is what the standard spin-up protocol reaches, not an equilibrium.",
        loc="left", fontsize=9, color=INK_2, fontweight="normal", pad=26,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 9 -- what the acceptance band is made of.
# ---------------------------------------------------------------------------------------------
def fig_noise_floor(conv: pl.DataFrame, out: Path) -> None:
    veg = conv.filter(pl.col("vegetated"))
    spread = veg["two_seed_spread"].to_numpy()
    spread = spread[np.isfinite(spread)]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.9))

    ax.hist(np.clip(spread, 0, 0.6), bins=70, color=S1, alpha=0.95)
    ax.axvline(0.10, color=S2, lw=1.8, ls=(0, (4, 3)))
    ax.text(0.105, ax.get_ylim()[1] * 0.92, " the 10 % floor", color=S2, fontsize=8.5)
    for q, dy in ((50, 0.72), (90, 0.56), (99, 0.40)):
        v = float(np.percentile(spread, q))
        ax.axvline(v, color=INK_MUTED, lw=1.0)
        ax.text(v + 0.006, ax.get_ylim()[1] * dy, f"p{q} = {v:.1%}", color=INK_2, fontsize=8)
    ax.set_xlabel("relative difference between two identical runs")
    ax.set_ylabel("cells")
    ax.set_title("The model's own reproducibility", loc="left")
    despine(ax)

    binding = np.where(spread > 0.10, spread, 0.10)
    ax2.hist(np.clip(binding, 0, 0.6), bins=70, color=S3, alpha=0.95)
    ax2.set_xlabel("the acceptance band actually used")
    ax2.set_ylabel("cells")
    frac = float(np.mean(spread <= 0.10))
    ax2.set_title(
        f"max(10 %, that spread): the floor binds in {frac:.0%} of cells", loc="left"
    )
    despine(ax2)

    fig.suptitle(
        "Why the tolerance is not simply 10 %", x=0.012, ha="left", fontsize=12,
        fontweight="semibold", color=INK,
    )
    fig.text(
        0.012, 0.925,
        "LPJmL-FIT is stochastic. Two runs differing only in random seed disagree by this much, so "
        "a tighter band would charge the emulator for noise no emulator can predict.",
        fontsize=9, color=INK_2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# Figure 10 -- where the conjunctive test passes, and how close it comes elsewhere.
# ---------------------------------------------------------------------------------------------
def fig_hits_map(frame: pl.DataFrame, quantities: list[str], out: Path) -> None:
    truth = np.stack([frame[f"truth_{q}"].to_numpy() for q in quantities], axis=1)
    pred = np.stack([frame[f"pred_{q}"].to_numpy() for q in quantities], axis=1)
    band = np.stack([frame[f"band_{q}"].to_numpy() for q in quantities], axis=1)
    hits = (np.abs(pred - truth) <= band) & np.isfinite(pred) & np.isfinite(truth)
    n_hit = hits.sum(axis=1).astype(float)
    lon = frame["lon"].to_numpy()
    lat = frame["lat"].to_numpy()

    fig, axes = plt.subplots(2, 1, figsize=(8.4, 6.6),
                             gridspec_kw={"height_ratios": [2.1, 1.0]})
    draw_map(axes[0], lon, lat, n_hit, title="", cmap=SEQ, vmin=0, vmax=len(quantities),
             label=f"quantities inside the band (of {len(quantities)})")
    counts = np.bincount(n_hit.astype(int), minlength=len(quantities) + 1)
    xs = np.arange(len(counts))
    colours = [S1 if i == len(quantities) else INK_MUTED for i in xs]
    axes[1].bar(xs, counts / counts.sum(), color=colours, width=0.72)
    axes[1].set_xlabel(f"number of the {len(quantities)} quantities inside the band")
    axes[1].set_ylabel("share of cells")
    axes[1].set_xticks(xs[::2])
    frac_all = counts[-1] / counts.sum()
    axes[1].annotate(
        f"all {len(quantities)} at once: {frac_all:.1%} of cells",
        (len(quantities), counts[-1] / counts.sum()),
        textcoords="offset points", xytext=(-8, 26), ha="right", fontsize=8.5, color=S1,
        arrowprops={"arrowstyle": "-", "color": S1, "lw": 1.0},
    )
    despine(axes[1])
    fig.suptitle(
        "The conjunctive acceptance test, cell by cell", x=0.012, ha="left", fontsize=12,
        fontweight="semibold", color=INK,
    )
    fig.text(
        0.012, 0.955,
        "A cell counts as accepted only if all 22 quantities land inside their own band. Most "
        "cells get most of the way there.",
        fontsize=9, color=INK_2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.945))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp-dir", default=None)
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()

    style()
    exp = Path(args.exp_dir) if args.exp_dir else Path(
        str(paths()["scratch"]["exp"])
    ) / "map-response-v0"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    corpus = Path(str(paths()["scratch"]["corpus"])) / "v0"

    metrics = json.loads((exp / "diagnostics.json").read_text())
    m = metrics["map"]
    r = metrics["response"]
    oof = pl.read_parquet(exp / "oof_map.parquet")
    resp = pl.read_parquet(exp / "oof_response.parquet")

    quantities = [c[len("truth_") :] for c in oof.columns if c.startswith("truth_")]
    resp_q = [c[len("delta_truth_") :] for c in resp.columns if c.startswith("delta_truth_")]

    best_map = max((v for k, v in m["arms"].items() if k != "model"))
    best_null_name = max(
        ((k, v) for k, v in m["arms"].items() if k != "model"), key=lambda kv: kv[1]
    )[0]
    fig_arms(
        m["arms"],
        threshold=0.050,
        best_null=best_map,
        title="Can climate alone reproduce the forest state? Every arm, beside every null.",
        subtitle=(
            f"{m['n_cells']:,} held-out cells, 22 quantities conjunctively, 15-degree spatial "
            "blocks. Higher is better."
        ),
        xlabel="fraction of cells inside the acceptance band on ALL 22 quantities",
        out=out / "fig01_map_arms.png",
    )
    best_resp = max((v for k, v in r["arms"].items() if k != "model"))
    fig_arms(
        r["arms"],
        threshold=0.050,
        best_null=best_resp,
        title="THE KILL TEST: can it predict the CHANGE under warming?",
        subtitle=(
            f"{r['n_cells']:,} cells. The emulator never saw a warmed forest. "
            "0.000 = predicting no change; 1.000 = perfect."
        ),
        xlabel="skill on the change, relative to predicting no change",
        out=out / "fig02_response_arms.png",
        zero_line=True,
    )
    fig_per_quantity(m["per_quantity"], best_null_name, out / "fig03_per_quantity.png")
    fig_maps(oof, "agb", out / "fig04_map_agb.png")
    fig_maps(oof, "stems_per_patch", out / "fig05_map_stems.png")
    fig_scatter(
        oof,
        ["stems_per_patch", "agb", "lai", "soilc", "height_p50", "wooddens_p50"],
        out / "fig06_scatter.png",
    )
    fig_distributions(oof, out / "fig07_distributions.png")
    fig_hits_map(oof, quantities, out / "fig08_hits.png")
    fig_response(resp, resp_q[:4], out / "fig09_response_scatter.png")
    fig_response_map(resp, "agb", out / "fig10_response_map.png")

    traj_path = corpus / "spin_global_trajectory.parquet"
    if traj_path.exists():
        summary = json.loads((corpus / "spin_convergence.json").read_text())
        fig_spinup(pl.read_parquet(traj_path), summary, out / "fig11_spinup.png")
        fig_noise_floor(
            pl.read_parquet(corpus / "spin_convergence.parquet"), out / "fig12_noise_floor.png"
        )

    made = sorted(p.name for p in out.glob("*.png"))
    print(f"wrote {len(made)} figures to {out}:")
    for name in made:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
