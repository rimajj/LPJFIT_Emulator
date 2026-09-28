"""A `synth_global` cell rule that only RE-DEALS a cell's own trees among its patches.

    scripts/synth_global.py run ... --cell-rule vegemu.models.shuffle_rule:PatchShuffle \\
        --synth-kwargs '{"mode": "equal"}'

WHY THIS EXISTS. The emulated restart loses ~10 % of its vegetation carbon in continuation year 5,
killed by the five-bad-years rule (`mortality_tree_ind.c:135`), and the stems it kills are
mid-canopy whatever their count, size or inherited counter (journal/X/2026-09b.md). A tree's
growth is set by its light, and LPJmL-FIT computes light PER PATCH (`getfpar.c`). `synthesise_cell`
deals its stems to the 25 patches at random with equal counts, so each patch is a random sample of
the stand; a real stand's patches are independent gap-dynamics replicates, at different stages,
with very different stem counts. This rule makes that one change and nothing else, to a REAL
stand: the trees, soil, litter, grass and climate buffer are the template's own, byte for byte;
only which patch each tree stands in changes. Continued at the template's own CO2, where the real
stand is known to hold (restart_1999 at 367.26 ppm: year-5 change -0.000), any die-off is caused by
the re-dealing alone.

MODES.
    equal        what `synthesise_cell` does: patch counts differ by at most one, stems dealt at
                 random (the cell's total is kept exactly)
    keep_counts  every patch keeps its own stem count; which stems stand in it is random
    identity     nothing moves: the record is re-encoded from its own stems, a check of the path

A moved stem's litter index is remapped to the target patch's slot for its type, appending an empty
slot if the patch has none (`synth.py`, LITTER_BYTE_IN_TREE). Its `index` is kept: it is unique
per type across the cell. The prediction and the donor pool are ignored.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.restart import PFT_GRASS_BYTES, PFT_TREE_BYTES, Layout
from vegemu.models.synth import (
    LITTER_BYTE_IN_TREE,
    LITTER_ITEM_REALS,
    DonorPool,
    SynthReport,
    _rebuild_pftlist,
)

MODES = ("equal", "keep_counts", "identity")


def _rows(
    pft: dict[str, Any], offsets: npt.NDArray[np.int64], nbytes: int
) -> npt.NDArray[np.uint8]:
    buf = np.frombuffer(pft["raw"], dtype=np.uint8)
    rows: npt.NDArray[np.uint8] = buf[offsets[:, None] + np.arange(nbytes)[None, :]].copy()
    return rows


def shuffle_patches(
    template: dict[str, Any], layout: Layout, *, mode: str, seed: int
) -> tuple[dict[str, Any], dict[str, int]]:
    """The template record with its trees re-dealt among its patches, and what moved."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; one of {MODES}")
    rng = np.random.default_rng(seed)
    stand = template["stands"][0]
    patches = stand["patches"]
    trees = [_rows(p["pftlist"], p["pftlist"]["tree_offsets"], PFT_TREE_BYTES) for p in patches]
    home = np.repeat(np.arange(len(patches)), [t.shape[0] for t in trees])
    stems = np.concatenate(trees) if home.size else np.zeros((0, PFT_TREE_BYTES), np.uint8)
    n = int(home.size)
    if mode == "identity":
        owner = home
    elif mode == "keep_counts":
        owner = home[rng.permutation(n)]
    else:
        base, extra = divmod(n, len(patches))
        counts = np.full(len(patches), base)
        counts[rng.permutation(len(patches))[:extra]] += 1
        owner = rng.permutation(np.repeat(np.arange(len(patches)), counts))

    new_patches = []
    for p_index, patch in enumerate(patches):
        pft = patch["pftlist"]
        grass = _rows(pft, pft["grass_offsets"], PFT_GRASS_BYTES)
        soil = dict(patch["soil"])
        lit = dict(soil["litter"])
        lit["pft_ids"] = np.array(lit["pft_ids"], dtype=np.uint8, copy=True)
        lit["items"] = np.array(lit["items"], dtype=np.float64, copy=True).reshape(
            -1, LITTER_ITEM_REALS
        )
        slot = {int(t): i for i, t in enumerate(lit["pft_ids"])}
        mine = stems[owner == p_index]
        moved = home[owner == p_index] != p_index
        for k in np.flatnonzero(moved):
            pft_id = int(mine[k, 0])
            if pft_id not in slot:
                slot[pft_id] = int(lit["n"])
                lit["n"] = int(lit["n"]) + 1
                lit["pft_ids"] = np.append(lit["pft_ids"], np.uint8(pft_id))
                lit["items"] = np.vstack([lit["items"], np.zeros((1, LITTER_ITEM_REALS))])
            mine[k, LITTER_BYTE_IN_TREE] = slot[pft_id]
        if mode == "identity":
            raw = pft["raw"]
        else:
            raw = (
                struct.pack("<i", mine.shape[0] + grass.shape[0]) + mine.tobytes() + grass.tobytes()
            )
        soil["litter"] = lit
        new_patches.append({**patch, "pftlist": _rebuild_pftlist(raw, layout), "soil": soil})
    rec = {**template, "stands": [{**stand, "patches": new_patches}, *template["stands"][1:]]}
    return rec, {"stems": n, "moved": int(np.sum(owner != home))}


@dataclass
class ShuffleReport(SynthReport):
    """`SynthReport` plus how many trees changed patch (scalars: `synth_global` tabulates them)."""

    mode: str = ""
    stems_moved: int = 0


class PatchShuffle:
    """The `--cell-rule` factory (contract: `synth_global.CellSynth`)."""

    def __init__(
        self,
        template: Any,
        first_cell: int,
        ncell: int,
        *,
        donors: Any,
        match_traits: tuple[str, ...] = (),
        mode: str = "equal",
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; one of {MODES}")
        self.mode = mode

    def __call__(
        self,
        template: dict[str, Any],
        prediction: dict[str, float],
        pool: DonorPool,
        layout: Layout,
        *,
        cell: int,
        seed: int,
    ) -> tuple[dict[str, Any], ShuffleReport]:
        rec, moved = shuffle_patches(template, layout, mode=self.mode, seed=seed)
        return rec, ShuffleReport(
            cell=cell,
            template_cell=cell,
            stems_requested=moved["stems"],
            stems_placed=moved["stems"],
            donors_available=0,
            mode=self.mode,
            stems_moved=moved["moved"],
        )

    def describe(self) -> dict[str, Any]:
        return {"rule": "patch-shuffle", "mode": self.mode}
