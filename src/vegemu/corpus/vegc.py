"""A cell's TOTAL vegetation carbon out of a restart record, as the model's own `VegC` output.

WHY NOT `state.summarise_cell`'s `vegc`. That column is the trees' allometric pools only --
`nind x (leaf + sapwood + heartwood + root + the two below-ground woods)` -- and it is pinned by the
corpus tables' hashes, so it stays what it is. The netCDF `VegC` every stored spin-up wrote is a
different sum (`lpj/fwriteoutput.c`, the VEGC block): every PFT of every patch of every stand,
trees AND grasses, each through its own `vegc_sum`, weighted by the stand's fraction of the cell:

    VegC = sum_stands frac / npatch * sum_patches sum_pfts vegc_sum(pft)
    tree   (leaf + root + heartwood + sapwood + sapwood_bg + heartwood_bg - debt + excess_carbon)
           * nind - turn_litt.leaf.carbon - turn_litt.root.carbon + fruit.carbon
                                                           (tree/veg_sum_tree.c, tree.h:257)
    grass  (leaf + root + excess_carbon) * nind            (grass/veg_sum_grass.c, grass.h:103)

`fruit` is zero for every natural tree (`fread_tree.c` sets it unless the type is an annual tree),
and a tree read from a restart is never `isdead`, so neither needs a field here. This is what a
synthesised restart must be compared with when the reference is the stored `VegC`: using the
tree-only corpus column would put the grass layer -- most of the carbon in a savanna -- on one side
of the comparison only. The cross-check that this reproduces the model's own number is
`scripts/spinup_product.py --stage crosscheck` (restart_1999 against `VegC` at model year 1999).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from vegemu.binfmt.restart import grasses_of, trees_of

_TREE_POOLS = ("leaf", "root", "heartwood", "sapwood", "sapwood_bg", "heartwood_bg")


def tree_vegc(stems: Any) -> float:
    """`vegc_sum_tree` summed over a patch's stems (a structured array from `trees_of`)."""
    if not stems.size:
        return 0.0
    phys = sum(stems[f"ind_{p}_c"].astype(np.float64) for p in _TREE_POOLS)
    per_ind = phys - stems["ind_debt_c"] + stems["excess_carbon"]
    per_pft = per_ind * stems["nind"] - stems["turn_litt_leaf_c"] - stems["turn_litt_root_c"]
    return float(np.sum(per_pft))


def grass_vegc(grasses: Any) -> float:
    """`vegc_sum_grass` summed over a patch's grasses (a structured array from `grasses_of`)."""
    if not grasses.size:
        return 0.0
    per_ind = grasses["ind_leaf_c"] + grasses["ind_root_c"] + grasses["excess_carbon"]
    return float(np.sum(per_ind * grasses["nind"]))


def cell_vegc(rec: dict[str, Any]) -> dict[str, float]:
    """The cell's `VegC` (gC/m2 of cell), split into its tree and grass parts. NaN for a skip cell,
    as the model writes its missing value there."""
    if rec["skip"]:
        return {"tree": math.nan, "grass": math.nan, "total": math.nan}
    tree = grass = 0.0
    for stand in rec["stands"]:
        weight = float(stand["frac"]) / int(stand["npatch"])
        for patch in stand["patches"]:
            tree += weight * tree_vegc(trees_of(patch["pftlist"]))
            grass += weight * grass_vegc(grasses_of(patch["pftlist"]))
    return {"tree": tree, "grass": grass, "total": tree + grass}
