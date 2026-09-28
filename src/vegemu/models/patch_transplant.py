"""A `synth_global` cell rule that transplants WHOLE PATCHES of the pilot's constant-CO2 stands.

    scripts/synth_global.py run ... --cell-rule vegemu.models.patch_transplant:PatchTransplant \\
        --synth-kwargs '{"stop_year": 1699, "litter_rule": "soilc"}' \\
        --donor-rule vegemu.models.pilot_donors:PilotBank --donor-opts '{"predictions": ...}'

WHY. LPJmL-FIT shares light per patch (`getfpar.c`), and a tree's pools are sized for the light it
had among the neighbours it grew with. Re-dealing the real 1999 stand's OWN trees to random patches,
nothing else changed, loses 9.7 % of its carbon in continuation year 5 at its own CO2, where the
unshuffled stand holds (journal/X/2026-09b.md, 2026-09-28) -- the whole of the emulated file's
die-off. Copying only the template's rank-to-patch layout (`synthesise_cell(patch_layout=
"template")`) did not help (-9.8 % against -9.4 %): stems of the right size RANK are still not the
neighbours a stem grew with. So the unit transplanted here is a real patch: every tree of it, with
its neighbours.

WHAT IS TAKEN FROM WHERE.
  * Everything but the trees is `SpinupRule`'s, unchanged: the climate buffer replayed to 1699,
    the allowed types, the soil carbon and the litter rule, the template's grass. `SpinupRule` is
    called with `match_vegc` off and the roster it places is discarded.
  * The trees of target patch p are all the trees of ONE donor patch, from the `n_runs` pilot
    constant-CO2 runs nearest the cell in the eight analogue features, outside its spatial fold
    (the `PilotBank` passed as `--donor-rule` supplies both; the target's own pilot runs are in
    its fold and so excluded). Stems of a type the target climate does not admit are dropped.
  * Which 25 patches: those whose tree carbon sums to `pred_vegc_target` minus the grass, within
    `tol`, by greedy swaps from a random draw; if the nearest runs cannot reach it, more runs are
    added (up to `max_runs`), then the closest reachable set is written and reported. No target (or
    a map-treeless cell, or a target at or below the grass): a random draw / no trees.
  * A moved tree's litter index is remapped to the target patch's slot for its type (appending an
    empty slot where missing, `synth.py` LITTER_BYTE_IN_TREE); every other byte is the donor's.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.restart import PFT_GRASS_BYTES, PFT_TREE_BYTES, TREE_DTYPE, Layout, RestartReader
from vegemu.corpus.vegc import cell_vegc, tree_vegc
from vegemu.models.pilot_donors import _scratch
from vegemu.models.spinup_rule import SpinupReport, SpinupRule
from vegemu.models.synth import (
    LITTER_BYTE_IN_TREE,
    LITTER_ITEM_REALS,
    DonorPool,
    _rebuild_pftlist,
)

PILOT_VERSION = "pilot-v2-constco2"
PILOT_SEED = 1


def pilot_restart(cell: int, point: str, root: Path | None = None) -> Path:
    base = root if root is not None else _scratch("runs") / PILOT_VERSION
    return base / f"c{cell}" / point / "restart" / f"restart_c{cell}-{point}-s{PILOT_SEED}.lpj"


@lru_cache(maxsize=512)
def donor_patches(path: str) -> tuple[npt.NDArray[np.uint8], ...]:
    """Each patch's tree entries (raw bytes, one row per stem) of a one-cell pilot restart."""
    rr = RestartReader(Path(path))
    rec = rr.read(0)
    out = []
    for patch in rec["stands"][0]["patches"]:
        pft = patch["pftlist"]
        buf = np.frombuffer(pft["raw"], dtype=np.uint8)
        offs = pft["tree_offsets"]
        out.append(buf[offs[:, None] + np.arange(PFT_TREE_BYTES)[None, :]].copy())
    return tuple(out)


def _carbon(rows: npt.NDArray[np.uint8]) -> float:
    if not rows.shape[0]:
        return 0.0
    return tree_vegc(np.ascontiguousarray(rows).view(TREE_DTYPE).reshape(-1))


def choose_patches(
    carbon: npt.NDArray[np.float64],
    k: int,
    want: float,
    rng: np.random.Generator,
    *,
    tol: float,
    max_iter: int = 1000,
) -> tuple[npt.NDArray[np.int64], float]:
    """`k` candidate indices whose carbon sums to `want` (relative `tol`), and the sum reached.

    A random draw (without replacement when there are enough candidates), then single swaps, each
    the one that most reduces |sum - want|, until inside `tol` or no swap helps."""
    n = carbon.size
    replace = n < k
    pick = rng.choice(n, size=k, replace=replace).astype(np.int64)
    if not math.isfinite(want):
        return pick, float(carbon[pick].sum())
    total = float(carbon[pick].sum())
    for _ in range(max_iter):
        err = total - want
        if abs(err) <= tol * max(abs(want), 1.0):
            break
        free = np.ones(n, dtype=bool)
        if not replace:
            free[pick] = False
        if not free.any():
            break
        cand = np.flatnonzero(free)
        # new error for swapping position j out and candidate i in: err - c_j + c_i
        new = np.abs(err - carbon[pick][:, None] + carbon[cand][None, :])
        j, i = np.unravel_index(int(np.argmin(new)), new.shape)
        if new[j, i] >= abs(err):
            break
        total += float(carbon[cand[i]] - carbon[pick[j]])
        pick[j] = cand[i]
    return pick, total


def place_patches(
    rec: dict[str, Any], chosen: list[npt.NDArray[np.uint8]], layout: Layout
) -> tuple[dict[str, Any], dict[int, int]]:
    """`rec` with patch p's trees replaced by `chosen[p]` (its grass kept), litter remapped."""
    stand = rec["stands"][0]
    new_patches = []
    types: dict[int, int] = {}
    for p, patch in enumerate(stand["patches"]):
        pft = patch["pftlist"]
        buf = np.frombuffer(pft["raw"], dtype=np.uint8)
        goffs = pft["grass_offsets"]
        grass_rows = buf[goffs[:, None] + np.arange(PFT_GRASS_BYTES)[None, :]]
        soil = dict(patch["soil"])
        lit = dict(soil["litter"])
        lit["pft_ids"] = np.array(lit["pft_ids"], dtype=np.uint8, copy=True)
        lit["items"] = np.array(lit["items"], dtype=np.float64, copy=True).reshape(
            -1, LITTER_ITEM_REALS
        )
        slot = {int(t): i for i, t in enumerate(lit["pft_ids"])}
        mine = chosen[p].copy()
        for k in range(mine.shape[0]):
            t = int(mine[k, 0])
            if t not in slot:
                slot[t] = int(lit["n"])
                lit["n"] = int(lit["n"]) + 1
                lit["pft_ids"] = np.append(lit["pft_ids"], np.uint8(t))
                lit["items"] = np.vstack([lit["items"], np.zeros((1, LITTER_ITEM_REALS))])
            mine[k, LITTER_BYTE_IN_TREE] = slot[t]
            types[t] = types.get(t, 0) + 1
        raw = (
            struct.pack("<i", mine.shape[0] + grass_rows.shape[0])
            + mine.tobytes()
            + np.ascontiguousarray(grass_rows).tobytes()
        )
        soil["litter"] = lit
        new_patches.append({**patch, "pftlist": _rebuild_pftlist(raw, layout), "soil": soil})
    return {**rec, "stands": [{**stand, "patches": new_patches}, *rec["stands"][1:]]}, types


@dataclass
class PatchReport(SpinupReport):
    """`SpinupReport` plus the patch transplant. Scalars only (`synth_global` tabulates them)."""

    patch_runs: int = 0
    patch_candidates: int = 0
    patch_tree_want: float = math.nan
    patch_tree_written: float = math.nan
    patch_why: str = ""
    patch_stems_dropped_type: int = 0


class PatchTransplant(SpinupRule):
    """`synth_global`'s `CellSynth`: SpinupRule's record, trees from whole donor patches."""

    def __init__(
        self,
        template: Path,
        first_cell: int,
        ncell: int,
        *,
        donors: Any,
        n_runs: int = 4,
        max_runs: int = 12,
        tol: float = 0.02,
        pilot_root: str | None = None,
        **kw: Any,
    ) -> None:
        if kw.get("match_vegc"):
            raise ValueError("patch transplant matches carbon by patch choice; drop match_vegc")
        super().__init__(template, first_cell, ncell, donors=donors, **kw)
        if not hasattr(donors, "_candidates"):
            raise ValueError("patch transplant needs the PilotBank donor rule (its analogue runs)")
        self.bank = donors
        self.n_runs, self.max_runs, self.tol = int(n_runs), int(max_runs), float(tol)
        self.pilot_root = Path(pilot_root) if pilot_root else None

    def _runs_near(self, cell: int) -> list[tuple[int, str]]:
        fold = int(self.bank._pred[cell]["fold"])
        cand, zc, mu, sd = self.bank._candidates(fold)
        zt = (self.bank._x[cell] - mu) / sd
        d = np.sqrt(((zc - zt[None, :]) ** 2).sum(axis=1))
        order = np.argsort(d, kind="stable")[: self.max_runs]
        cells, points = cand["cell"].to_numpy(), cand["point"].to_list()
        out = [(int(cells[i]), str(points[i])) for i in order]
        if any(c == cell for c, _ in out):
            raise AssertionError(f"cell {cell}: a donor run of the target cell itself")
        return out

    def _candidates_for(
        self, cell: int, want: float, allowed: set[int], npatch: int
    ) -> tuple[list[npt.NDArray[np.uint8]], npt.NDArray[np.float64], int, int]:
        """Donor patches (admitted types only) of the nearest runs, widened until `want` is
        reachable by the heaviest `npatch` of them or `max_runs` is used; their carbon."""
        runs = self._runs_near(cell)
        n = self.n_runs
        while True:
            rows: list[npt.NDArray[np.uint8]] = []
            dropped = 0
            for c, point in runs[:n]:
                for r in donor_patches(str(pilot_restart(c, point, self.pilot_root))):
                    keep = np.isin(r[:, 0], sorted(allowed))
                    dropped += int((~keep).sum())
                    rows.append(r[keep])
            carbon = np.array([_carbon(r) for r in rows])
            reach = float(np.sort(carbon)[::-1][:npatch].sum()) if carbon.size else 0.0
            if not math.isfinite(want) or reach >= want or n >= len(runs):
                return rows, carbon, n, dropped
            n = min(n * 2, len(runs))

    def __call__(
        self,
        template: dict[str, Any],
        prediction: dict[str, float],
        pool: DonorPool,
        layout: Layout,
        *,
        cell: int,
        seed: int,
    ) -> tuple[dict[str, Any], PatchReport]:
        rec, rep = super().__call__(template, prediction, pool, layout, cell=cell, seed=seed)
        out = PatchReport(**{f.name: getattr(rep, f.name) for f in fields(SpinupReport)})
        allowed = {int(t) for t in str(out.allowed).split(",") if t != ""}
        stand = rec["stands"][0]
        npatch, frac = int(stand["npatch"]), float(stand["frac"])
        target = float(prediction.get("vegc_target", math.nan))
        treeless = not float(prediction.get("stems_per_patch", 0.0)) > 0
        grass = cell_vegc(rec)["grass"]
        want = (target - grass) * npatch / frac if math.isfinite(target) else math.nan

        chosen: list[npt.NDArray[np.uint8]] = [np.zeros((0, PFT_TREE_BYTES), np.uint8)] * npatch
        if treeless or (math.isfinite(want) and want <= 0):
            out.patch_why = "treeless" if treeless else "below-grass"
        else:
            rows, carbon, n, dropped = self._candidates_for(cell, want, allowed, npatch)
            rng = np.random.default_rng(seed)
            pick, total = choose_patches(carbon, npatch, want, rng, tol=self.tol)
            chosen = [rows[i] for i in pick]
            out.patch_runs, out.patch_candidates = n, len(rows)
            out.patch_stems_dropped_type = dropped
            out.patch_tree_want = want / npatch * frac if math.isfinite(want) else math.nan
            out.patch_tree_written = total / npatch * frac
            if not math.isfinite(want):
                out.patch_why = "no-target"
            elif abs(total - want) <= self.tol * max(want, 1.0):
                out.patch_why = "matched"
            else:
                out.patch_why = "unreached"

        rec, types = place_patches(rec, chosen, layout)
        out.stems_placed = sum(types.values())
        out.type_achieved = types
        out.inadmissible_placed = sum(v for t, v in types.items() if t not in allowed)
        out.vegc_written = cell_vegc(rec)["total"]
        out.vegc_target = target
        out.vegc_why = out.patch_why
        return rec, out

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "rule": "patch-transplant",
            "n_runs": self.n_runs,
            "max_runs": self.max_runs,
            "tol": self.tol,
        }
