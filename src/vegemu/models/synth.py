"""Turning a predicted state into a restart file LPJmL-FIT will load.

THE DESIGN, AND WHY IT IS NOT "PREDICT 1.9 MB OF FLOATS". A cell's restart record is ~1.9 MB of
mutually constrained state: per-stem carbon pools that must satisfy the allometry, a soil water and
enthalpy block that must be internally consistent, a 20-year climate ring buffer. The model is
built with `-DSAFE`, so it ABORTS a cell whose water balance is off by more than 1.5 mm/yr -- an
inconsistent synthesised state fails loudly rather than silently, which is a gift. But generating
consistency from scratch is not the way to earn it.

So: **template-conditioned synthesis with rank-matched stem transplant.** Every field is one of

    LEARNED   the stem COUNT per patch, and which stems are present
    DERIVED   soil and litter carbon, rescaled to the predicted totals along the template's
              own vertical profile
    COPIED    the whole fast soil block, the climate buffer, the crop and nitrogen fields, the
              sapling pool -- taken from a real record for the same cell
    FREE      per-stem index numbers, renumbered

and crucially **no individual stem is ever edited**. Each transplanted stem is a byte-exact copy of
a stem the real model itself produced, so its height, crown area, sapwood and heartwood carbon,
bad-years counter and trait values are consistent with each other by construction. What the
emulator controls is HOW MANY stems there are and WHICH ONES -- the count and the distribution --
which is exactly what it predicts.

The price, stated plainly: the achievable distribution is limited to what the donor pool contains.
A cell predicted to hold trees taller than anything in the pool cannot get them. That is why the
pool is assembled from many real cells rather than one, and why `pool_shortfall` is reported with
every synthesised cell instead of being silently absorbed.

WHAT THIS DOES NOT DO YET. The fast soil water/ice/enthalpy block is copied wholesale, so the
water state belongs to the template's climate rather than the predicted one. `PLAN.md` classifies
that block as RELAXED for exactly this reason, and the sanctioned fallback -- letting the C relax it
for a few years -- is a disclosed post-processing step, not part of this function.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.restart import (
    PFT_GRASS_BYTES,
    PFT_TREE_BYTES,
    Layout,
    RestartReader,
    _Cursor,
    _read_pftlist,
    trees_of,
)

# ⚠ THE ONE FIELD A ROUND-TRIP TEST CANNOT VALIDATE. The last byte of a PFT entry, `pft->litter`,
# is NOT a self-contained value -- it is an INDEX into that patch's own litter list, and
# `freadpft.c:71` rejects it with ERROR195 if it is >= `patch->soil.litter.n`. Within one record
# it is always consistent, so reading and rewriting a record byte-identically proves nothing about
# it. It only breaks when a stem is MOVED BETWEEN PATCHES, which is exactly what a transplant does.
#
# Found by the validation ladder rather than by inspection: the first synthesised file failed t2
# with `ERROR195: Invalid value 7 for litter index, must be in [0,5]` -- a donor whose home patch
# had eight litter pools landed in a patch with six. So every transplanted stem's index is remapped
# to the TARGET patch's slot for the same PFT, and a slot is appended if that PFT has none.
LITTER_BYTE_IN_TREE = 553
LITTER_ITEM_REALS = 22  # ag(10) + agsub(10) + bg(2), all Reals

# The quantiles the emulator predicts, and which the transplant matches.
QUANTILE_LEVELS: tuple[float, ...] = (0.10, 0.50, 0.90)
# Traits matched jointly when choosing a donor. Height first: it carries the size structure, and
# the per-tree output's 5 m censoring threshold sits inside its range.
MATCH_TRAITS: tuple[str, ...] = ("height", "wooddens")


@dataclass
class DonorPool:
    """Real stems, pooled from several real cells, with their raw bytes kept alongside.

    The bytes are the point. A donor is transplanted verbatim, so nothing about it can be
    internally inconsistent -- it came out of the model.
    """

    raw: npt.NDArray[np.uint8]  # (n_donor, PFT_TREE_BYTES)
    fields: Any  # structured array, one row per donor
    source_cells: tuple[int, ...]

    @property
    def n(self) -> int:
        return int(self.raw.shape[0])

    def trait(self, name: str) -> npt.NDArray[np.float64]:
        return np.asarray(self.fields[name], dtype=np.float64)


def build_donor_pool(reader: RestartReader, cells: list[int]) -> DonorPool:
    """Pool every tree of every patch of the given cells."""
    raws: list[npt.NDArray[np.uint8]] = []
    fields: list[Any] = []
    with reader:
        for cell in cells:
            rec = reader.read(cell)
            if rec["skip"]:
                continue
            for patch in rec["stands"][0]["patches"]:
                pft = patch["pftlist"]
                offs = pft["tree_offsets"]
                if offs.size == 0:
                    continue
                buf = np.frombuffer(pft["raw"], dtype=np.uint8)
                rows = buf[offs[:, None] + np.arange(PFT_TREE_BYTES, dtype=np.int64)[None, :]]
                raws.append(np.ascontiguousarray(rows))
                fields.append(trees_of(pft))
    if not raws:
        raise ValueError(f"no stems in donor cells {cells}")
    return DonorPool(
        raw=np.concatenate(raws, axis=0),
        fields=np.concatenate(fields),
        source_cells=tuple(cells),
    )


def quantile_function(
    p10: float, p50: float, p90: float, u: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """A monotone quantile function through three predicted points.

    Linear between the knots; beyond them the last interior slope is continued, which keeps the
    function monotone without inventing a tail shape the prediction says nothing about. The three
    knots are sorted first: the three heads are fitted independently, so nothing guarantees the
    predicted 10th percentile comes out below the predicted 90th, and a crossed pair would produce
    a decreasing quantile function and a nonsense roster.
    """
    lo, mid, hi = sorted((float(p10), float(p50), float(p90)))
    knots_u = np.array([0.10, 0.50, 0.90])
    knots_v = np.array([lo, mid, hi])
    out = np.interp(u, knots_u, knots_v)
    slope_lo = (mid - lo) / 0.40
    slope_hi = (hi - mid) / 0.40
    below = u < 0.10
    above = u > 0.90
    out[below] = lo + (u[below] - 0.10) * slope_lo
    out[above] = hi + (u[above] - 0.90) * slope_hi
    return np.maximum(out, 1e-9)


@dataclass
class SynthReport:
    """What the synthesis actually achieved, per cell. Reported, never absorbed."""

    cell: int
    template_cell: int
    stems_requested: int
    stems_placed: int
    donors_available: int
    pool_shortfall: dict[str, float] = field(default_factory=dict)
    soil_scale: float = 1.0
    litter_scale: float = 1.0
    achieved: dict[str, float] = field(default_factory=dict)
    requested: dict[str, float] = field(default_factory=dict)


def _choose_donors(
    pool: DonorPool,
    targets: dict[str, npt.NDArray[np.float64]],
    rng: np.random.Generator,
) -> npt.NDArray[np.int64]:
    """Nearest donor in standardised trait space, one per target stem.

    Standardised over the POOL so no trait dominates by unit: wood density is ~2e5 gC/m3 and height
    is ~10 m, so an unstandardised distance would be a wood-density match with height as noise.
    """
    n_target = len(next(iter(targets.values())))
    cost = np.zeros((n_target, pool.n))
    for name, want in targets.items():
        have = pool.trait(name)
        scale = float(np.std(have)) or 1.0
        cost += ((want[:, None] - have[None, :]) / scale) ** 2
    # A tiny random jitter breaks ties, so a pool with many identical stems does not hand back the
    # same donor for every target and collapse the roster onto one tree.
    cost += rng.uniform(0.0, 1e-6, size=cost.shape)
    return np.asarray(np.argmin(cost, axis=1), dtype=np.int64)


def synthesise_cell(
    template: dict[str, Any],
    prediction: dict[str, float],
    pool: DonorPool,
    layout: Layout,
    *,
    cell: int,
    template_cell: int,
    seed: int = 0,
) -> tuple[dict[str, Any], SynthReport]:
    """Replace a template record's roster and soil totals with a predicted state.

    `prediction` needs `stems_per_patch`, `<trait>_p10/_p50/_p90` for the matched traits, and
    optionally `soilc` and `litterc`.
    """
    if template["skip"]:
        raise ValueError(f"template cell {template_cell} is a skip cell; nothing to condition on")
    rng = np.random.default_rng(seed)
    rec = {k: v for k, v in template.items()}
    stand = template["stands"][0]
    npatch = int(stand["npatch"])

    want_per_patch = max(float(prediction["stems_per_patch"]), 0.0)
    report = SynthReport(
        cell=cell,
        template_cell=template_cell,
        stems_requested=0,
        stems_placed=0,
        donors_available=pool.n,
        requested={k: float(v) for k, v in prediction.items()},
    )

    new_patches: list[dict[str, Any]] = []
    placed_fields: list[Any] = []
    for patch in stand["patches"]:
        # Stochastic rounding: a predicted 23.4 stems per patch must not become 23 in every patch,
        # or the cell mean comes out 23.0 and the count the emulator predicted is not the count
        # that was written.
        n = int(np.floor(want_per_patch) + (rng.random() < (want_per_patch % 1.0)))
        report.stems_requested += n

        pft = patch["pftlist"]
        grass_offs = pft["grass_offsets"]
        grass_bytes = b""
        if grass_offs.size:
            buf = np.frombuffer(pft["raw"], dtype=np.uint8)
            rows = buf[grass_offs[:, None] + np.arange(PFT_GRASS_BYTES, dtype=np.int64)[None, :]]
            grass_bytes = np.ascontiguousarray(rows).tobytes()

        # The target patch's litter list, copied so it can grow, and its PFT -> slot map.
        soil = dict(patch["soil"])
        lit = dict(soil["litter"])
        lit["pft_ids"] = np.array(lit["pft_ids"], dtype=np.uint8, copy=True)
        lit["items"] = np.array(lit["items"], dtype=np.float64, copy=True).reshape(
            -1, LITTER_ITEM_REALS
        )
        slot = {int(p): i for i, p in enumerate(lit["pft_ids"])}

        parts: list[bytes] = []
        if n > 0:
            u = (np.arange(n) + 0.5) / n
            targets = {
                name: quantile_function(
                    prediction[f"{name}_p10"], prediction[f"{name}_p50"],
                    prediction[f"{name}_p90"], u,
                )
                for name in MATCH_TRAITS
                if f"{name}_p50" in prediction
            }
            picks = _choose_donors(pool, targets, rng)
            chosen = pool.raw[picks]
            for k in range(n):
                row = chosen[k].copy()
                # FREE field: renumber `index` so two copies of one donor are distinct.
                row[325:329] = np.frombuffer(struct.pack("<i", k + 1), dtype=np.uint8)
                # CROSS-REFERENCE field: remap the donor's litter index to THIS patch's slot for
                # the same PFT, appending an empty slot if the PFT has none here. Zero stocks is
                # the right initial content -- a PFT that has just arrived has shed no litter yet.
                pft_id = int(row[0])
                if pft_id not in slot:
                    slot[pft_id] = int(lit["n"])
                    lit["n"] = int(lit["n"]) + 1
                    lit["pft_ids"] = np.append(lit["pft_ids"], np.uint8(pft_id))
                    lit["items"] = np.vstack(
                        [lit["items"], np.zeros((1, LITTER_ITEM_REALS), dtype=np.float64)]
                    )
                row[LITTER_BYTE_IN_TREE] = slot[pft_id]
                parts.append(row.tobytes())
            placed_fields.append(pool.fields[picks])
            report.stems_placed += n

        soil["litter"] = lit
        raw = struct.pack("<i", n + int(grass_offs.size)) + b"".join(parts) + grass_bytes
        new_pft = _rebuild_pftlist(raw, layout)
        new_patches.append({**patch, "pftlist": new_pft, "soil": soil})

    # DERIVED: rescale soil and litter carbon to the predicted totals, keeping the template's
    # vertical profile. A profile is not predicted, so inventing one would be a free parameter.
    soil_scale = _rescale_soil(new_patches, stand, prediction, report)
    report.soil_scale = soil_scale

    rec["stands"] = [{**stand, "patches": new_patches}]

    if placed_fields:
        allf = np.concatenate(placed_fields)
        report.achieved = {
            "stems_per_patch": report.stems_placed / npatch,
            **{
                f"{name}_p{int(q * 100)}": float(np.percentile(allf[name].astype(float), q * 100))
                for name in MATCH_TRAITS
                for q in QUANTILE_LEVELS
            },
        }
        for name in MATCH_TRAITS:
            key = f"{name}_p50"
            if prediction.get(key):
                report.pool_shortfall[name] = float(
                    (report.achieved[key] - prediction[key]) / prediction[key]
                )
    return rec, report


def _rebuild_pftlist(raw: bytes, layout: Layout) -> dict[str, Any]:
    """Re-derive the offset bookkeeping for a freshly built PFT list."""
    cur = _Cursor(raw)
    return _read_pftlist(cur, layout)


def _rescale_soil(
    patches: list[dict[str, Any]],
    stand: dict[str, Any],
    prediction: dict[str, float],
    report: SynthReport,
) -> float:
    """Scale the carbon pools so the cell's total matches the prediction. Nitrogen scales with it.

    Nitrogen is scaled by the same factor rather than left alone, because the C:N ratio of a soil
    pool is a physical quantity the model uses; scaling carbon alone would hand it an unphysical
    ratio, and `-DSAFE` would be entitled to complain.
    """
    want = prediction.get("soilc")
    if want is None or want <= 0:
        return 1.0
    have = 0.0
    for patch in patches:
        pool = patch["soil"]["pool"]
        have += float(pool[:, 0].sum() + pool[:, 2].sum())
    have /= len(patches)
    if have <= 0:
        return 1.0
    scale = float(want / have)
    for patch in patches:
        soil = dict(patch["soil"])
        soil["pool"] = soil["pool"] * scale
        soil["k_mean"] = soil["k_mean"]
        patch["soil"] = soil
    report.litter_scale = 1.0
    _ = stand
    return scale
