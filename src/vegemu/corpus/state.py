"""Per-cell state summaries out of a restart file — the emulator's targets.

WHAT A "STATE" IS HERE, AND WHY IT IS NOT A MEAN. The acceptance criterion is conjunctive: tree
counts **and** trait distributions **and** trait medians, per cell. So the summary carries all
three, and the distributions are carried as QUANTILES rather than as a mean and a spread, because
LPJmL-FIT's trait distributions are neither symmetric nor unimodal and a mean would hide exactly
the selection signal the emulator has to reproduce.

Two things are deliberately kept that a tidier summary would drop:

* **the consecutive-bad-growth-years counter.** Averaging it away reverses the trait-selection sign
  in 3-4 of the 7 tree types (`MEMORY.md:bad-years-counter`), so `counter_frac_nonzero` and
  `counter_mean` are first-class columns, not diagnostics.
* **the per-patch spread of the stem count.** LPJmL-FIT is stochastic and the acceptance tolerance
  is `max(10 %, the model's own two-seed spread)`; the within-cell across-patch spread is the
  cheapest honest scale to compare a per-cell error against, and it is available for free.

Everything here is read from the RESTART file, not from the per-tree text output, because that
output drops every stem at or below 5 m -- roughly half of them at a temperate cell -- and so cannot
be inverted into a state (`MEMORY.md:ind-censored`).
"""

from __future__ import annotations

import multiprocessing as mp
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.restart import Layout, RestartReader, trees_of

# The five traits LPJmL-FIT samples per individual, plus the three size/age variables that make the
# roster a roster. `age` is included because a forest at equilibrium is defined as much by its age
# structure as by its biomass.
TRAITS: tuple[str, ...] = (
    "wooddens",
    "sla",
    "k_root",
    "D95max",
    "longevity",
    "height",
    "crownarea",
    "age",
)
QUANTILES: tuple[int, ...] = (10, 25, 50, 75, 90)

# Fixed height bins, in metres. The 5 m edge is deliberate: it is the per-tree output's censoring
# threshold, so `hbin_0_5` is exactly the part of the roster that output cannot see.
HEIGHT_BINS: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0, 30.0, np.inf)
HEIGHT_BIN_NAMES: tuple[str, ...] = (
    "hbin_0_5",
    "hbin_5_10",
    "hbin_10_20",
    "hbin_20_30",
    "hbin_30p",
)

NTREE_PFT = 7


def _quantile_names() -> list[str]:
    return [f"{t}_p{q}" for t in TRAITS for q in QUANTILES]


STATE_COLUMNS: tuple[str, ...] = (
    "cell",
    "skip",
    "npatch",
    # counts
    "stems_total",
    "stems_per_patch",
    "stems_patch_sd",
    "patches_with_trees",
    "grass_entries",
    # stocks and structure, per m2 of ground
    "agb",
    "vegc",
    "lai",
    "fpc_sum",
    "crown_cover",
    "soilc",
    "litterc",
    # the growth-failure counter
    "counter_mean",
    "counter_frac_nonzero",
    *HEIGHT_BIN_NAMES,
    *(f"pft_frac_{i}" for i in range(NTREE_PFT)),
    *_quantile_names(),
    *(f"{t}_mean" for t in TRAITS),
)


def _empty_summary(cell: int, npatch: int, skip: int) -> dict[str, float]:
    """A vegetation-free cell. Zeros, not NaN: "no trees" is a state, not a missing measurement."""
    out: dict[str, float] = dict.fromkeys(STATE_COLUMNS, 0.0)
    out["cell"] = float(cell)
    out["skip"] = float(skip)
    out["npatch"] = float(npatch)
    # A trait has no value where there is no stem, and a zero median would be a lie a model would
    # happily fit. Those columns stay NaN and every downstream score must mask them.
    for name in (*_quantile_names(), *(f"{t}_mean" for t in TRAITS)):
        out[name] = float("nan")
    return out


def summarise_cell(rec: dict[str, Any], cell: int, lay: Layout) -> dict[str, float]:
    """Reduce one decoded cell record to the state vector. Pure; no I/O."""
    if rec["skip"]:
        return _empty_summary(cell, 0, 1)

    stand = rec["stands"][0]
    npatch = int(stand["npatch"])
    per_patch = [trees_of(p["pftlist"]) for p in stand["patches"]]
    counts = np.array([a.size for a in per_patch], dtype=np.float64)
    n_grass = sum(int(p["pftlist"]["grass_offsets"].size) for p in stand["patches"])

    # Soil and litter carbon are present whether or not there are trees.
    soilc = 0.0
    litterc = 0.0
    for p in stand["patches"]:
        soil = p["soil"]
        # pool columns are (fast.c, fast.n, slow.c, slow.n) per layer -> carbon is 0 and 2
        soilc += float(soil["pool"][:, 0].sum() + soil["pool"][:, 2].sum())
        lit = soil["litter"]
        if int(lit["n"]):
            items = lit["items"]
            # ag: Stocks leaf + Stocks wood[4] = reals 0..9 ; agsub: 10..19 ; bg: 20..21
            # carbon sits at every even index of each Stocks pair
            litterc += float(items[:, 0:20:2].sum() + items[:, 20].sum())
    soilc /= npatch
    litterc /= npatch

    if counts.sum() == 0:
        out = _empty_summary(cell, npatch, 0)
        out["grass_entries"] = float(n_grass)
        out["soilc"] = soilc
        out["litterc"] = litterc
        return out

    stems = np.concatenate([a for a in per_patch if a.size])
    nind = stems["nind"].astype(np.float64)

    agb_ind = (
        stems["ind_leaf_c"].astype(np.float64)
        + stems["ind_sapwood_c"].astype(np.float64)
        + stems["ind_heartwood_c"].astype(np.float64)
    )
    bg_ind = (
        stems["ind_root_c"].astype(np.float64)
        + stems["ind_sapwood_bg_c"].astype(np.float64)
        + stems["ind_heartwood_bg_c"].astype(np.float64)
    )

    # Not annotated: `out` is already bound on the no-trees path above, with the same
    # `dict[str, float]` that `_empty_summary` returns. A second ANNOTATION on the same name is a
    # redefinition even though the two bindings sit on mutually exclusive paths -- that branch
    # returns -- so annotating once is the fix, and neither binding is dead.
    out = {
        "cell": float(cell),
        "skip": 0.0,
        "npatch": float(npatch),
        "stems_total": float(counts.sum()),
        "stems_per_patch": float(counts.mean()),
        "stems_patch_sd": float(counts.std(ddof=1)) if npatch > 1 else 0.0,
        "patches_with_trees": float((counts > 0).sum()),
        "grass_entries": float(n_grass),
        # nind is individuals per m2, so a sum over a patch's stems is already per m2; dividing the
        # pooled sum by npatch averages over patches.
        "agb": float((nind * agb_ind).sum() / npatch),
        "vegc": float((nind * (agb_ind + bg_ind)).sum() / npatch),
        "lai": float((nind * stems["ind_leaf_c"].astype(np.float64) * stems["sla"]).sum() / npatch),
        "fpc_sum": float(stems["fpc"].astype(np.float64).sum() / npatch),
        "crown_cover": float((nind * stems["crownarea"].astype(np.float64)).sum() / npatch),
        "soilc": soilc,
        "litterc": litterc,
    }

    counter = stems["bm_inc_counter"].astype(np.float64)
    out["counter_mean"] = float(counter.mean())
    out["counter_frac_nonzero"] = float((counter > 0).mean())

    height = stems["height"].astype(np.float64)
    binned = np.histogram(height, bins=np.array(HEIGHT_BINS))[0].astype(np.float64) / npatch
    for name, value in zip(HEIGHT_BIN_NAMES, binned, strict=True):
        out[name] = float(value)

    ids = stems["id"].astype(np.int64)
    frac = np.bincount(ids, minlength=NTREE_PFT).astype(np.float64) / ids.size
    for i in range(NTREE_PFT):
        out[f"pft_frac_{i}"] = float(frac[i])

    for trait in TRAITS:
        values = stems[trait].astype(np.float64)
        qs = np.percentile(values, QUANTILES)
        for q, value in zip(QUANTILES, qs, strict=True):
            out[f"{trait}_p{q}"] = float(value)
        out[f"{trait}_mean"] = float(values.mean())

    return out


def _chunk(reader: RestartReader, cells: Sequence[int]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with reader:
        for cell in cells:
            rows.append(summarise_cell(reader.read(cell), cell, reader.layout))
    return rows


def _worker(args: tuple[str, list[int]]) -> list[dict[str, float]]:
    path, cells = args
    return _chunk(RestartReader(Path(path)), cells)


def state_table(
    restart: Path | str,
    cells: Iterable[int] | None = None,
    nproc: int = 1,
    chunk: int = 256,
) -> pl.DataFrame:
    """Every requested cell of a restart file, as one table.

    `nproc > 1` forks workers over contiguous cell chunks. Contiguous on purpose: the records are
    laid out in cell order, so a chunk is a sequential read rather than 256 seeks scattered across
    119 GiB.
    """
    reader = RestartReader(Path(restart))
    cell_list = list(range(reader.ncell)) if cells is None else [int(c) for c in cells]
    chunks = [cell_list[i : i + chunk] for i in range(0, len(cell_list), chunk)]

    rows: list[dict[str, float]] = []
    if nproc <= 1:
        for part in chunks:
            rows.extend(_chunk(reader, part))
    else:
        payload = [(str(restart), part) for part in chunks]
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=nproc) as pool:
            for result in pool.imap(_worker, payload, chunksize=1):
                rows.extend(result)

    frame = pl.DataFrame(rows).select(STATE_COLUMNS)
    return frame.with_columns(pl.col("cell").cast(pl.Int32))


def basis(restart: Path | str) -> dict[str, Any]:
    """The reference basis of a state table: what file, what year, what patch count.

    Emitted beside every table so a downstream number can state its basis in the same sentence,
    which is invariant 4. `mtime` is in there because two ground-truth legs on this cluster were
    produced by different binary builds and the build is not recorded in the file itself
    (`MEMORY.md:restart-no-checksum`).
    """
    reader = RestartReader(Path(restart))
    stat = os.stat(restart)
    return {
        "file": str(restart),
        "bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "state_year": reader.generic.firstyear,
        "ncell": reader.ncell,
        "nbands": reader.generic.nbands,
        "seed": list(reader.restart.seed),
        "individual": reader.restart.individual,
        "npatch_expected": 25,
    }


def two_seed_spread(a: pl.DataFrame, b: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """The model's own noise: |a-b| / mean(a,b) per cell, for two runs that differ only in seed.

    This IS the tolerance floor. The acceptance band is `max(10 %, this)`, so a mean score that
    beats 10 % in a cell whose own two runs differ by 29 % has demonstrated nothing.
    """
    joined = a.join(b, on="cell", how="inner", suffix="_b")
    exprs: list[pl.Expr] = [pl.col("cell")]
    for col in columns:
        mean = (pl.col(col) + pl.col(f"{col}_b")) / 2.0
        rel = (pl.col(col) - pl.col(f"{col}_b")).abs() / mean
        exprs.append(pl.when(mean.abs() > 0).then(rel).otherwise(None).alias(f"spread_{col}"))
    return joined.select(exprs)


def _percentile(values: npt.NDArray[np.float64], q: float) -> float:
    return float(np.percentile(values, q))
