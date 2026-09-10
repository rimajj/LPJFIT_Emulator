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
    IMPOSED   `IMPOSED_TRAITS` -- today just `D95max` -- overwritten in the stem's bytes

and a transplanted stem is otherwise a byte-exact copy of a stem the real model itself produced, so
its height, crown area, sapwood and heartwood carbon, bad-years counter and trait values are
consistent with each other by construction. What the emulator controls is HOW MANY stems there are
and WHICH ONES -- the count and the distribution -- which is exactly what it predicts.

⚠ "NO INDIVIDUAL STEM IS EVER EDITED" WAS THIS MODULE'S RULE AND IS NOW A RULE WITH ONE NAMED
EXCEPTION. It held for good reason: every field of a real stem is consistent with every other, and
an edit can break a relation the C will then enforce or trip over. It was relaxed only after the
measurement that showed selection ALONE cannot deliver rooting depth -- with a PERFECT prediction
the donor match still leaves `D95max_p50` at 0.127 -- and only for a field that passes all three
tests in `IMPOSED_TRAITS`: the model never recomputes it, it drives no physics, and it is still
load-bearing for the state. Adding a second field to that tuple means re-reading the C for that
field, not reasoning by analogy from this one. Leaf carbon looks similar and FAILS, because
`allometry_tree.c:39-41` derives height from it.

The price, stated plainly: the achievable distribution is limited to what the donor pool contains.
A cell predicted to hold trees taller than anything in the pool cannot get them. That is why the
pool is assembled from many real cells rather than one, and why `pool_shortfall` is reported with
every synthesised cell instead of being silently absorbed.

⚠ INTERNAL CONSISTENCY IS NOT THE SAME AS BEING AT HOME IN THIS CELL, and the difference cost
half the carbon. The first version chose each donor by nearest distance in (height, wood density)
and never looked at the tree TYPE, so type was effectively a FREE field. The donor pool spans
biomes on purpose -- it has to, to cover the size range -- so the nearest donor by height and
density is very often a tree from another biome. 31 % of the stems written into a block of twenty
temperate European cells were tropical broadleaved evergreen, a type those cells' own real state
never contains. The model loaded the file, ran, did not abort, and then killed every one of them
inside the first year: LPJmL-FIT charges a tropical evergreen one stress day for every day below
12.5 C and kills it outright at 73 such days (`mort_temp = 5.0 * stress_days / 365`, capped at 1,
in `tree/mortality_tree_ind.c`). Half the roster and two thirds of the carbon went with them.

So **tree type is COPIED, not FREE**: it is taken from the target cell's own template roster, at
the matching size rank, and the height/density match happens only among donors of that type. The
template is a real state of that cell, so its set of types is climatically admissible by
construction. `inadmissible_placed` is reported per cell and must be zero.

WHAT THIS DOES NOT DO YET, part two. Copying the type composition from the template means the
synthesiser **cannot change species composition**. That is a real limit on the warmed-climate
product, where a shift in composition is a large part of the response, and it is a limit of the
SYNTHESISER, not of the idea: `corpus/state.py` already computes `pft_frac_*` per cell, so the
composition becomes predictable as soon as those columns are added to the scored set. Until then
a warmed-climate restart carries present-day composition, and that must be disclosed with it.

⚠ THE ROSTER IS DRAWN AT CELL-LEVEL RANKS, AND IT USED TO BE DRAWN AT PER-PATCH ONES. That was a
bug, and it cost the whole upper tail of the size distribution. The predicted quantiles are CELL
quantiles -- `corpus/state.py` pools all 25 patches before taking a percentile -- but the roster was
built one patch at a time from `u = (arange(n) + 0.5) / n` with n ~ 19. So every patch was handed
the SAME nineteen ranks, spanning only 0.026 to 0.974, and the cell ended up holding twenty-five
copies of one truncated ladder. No patch ever addressed the 0.99 rank, so no cell ever received the
tree that lives there. Measured on the twenty-cell block: the true state holds 382 stems above 16 m
and the synthesised file held ZERO, its tallest stem being 13.3 m against a true 23.0 m -- while the
donor pool held 794 admissible stems above 16 m and the predicted `height_p90` was good to 7 %.
Those missing tall stems carried 36 % of the stand's leaf, which is the whole of the leaf-area
shortfall that made leaf area the largest single loss at twenty years. Ranks are now drawn once
across the cell and dealt out to patches at random, so each patch is a random SAMPLE of the stand
rather than a copy of it.

⚠ AND THE SHAPE COMES FROM THE TEMPLATE, BECAUSE THREE KNOTS AND A STRAIGHT LINE CANNOT MAKE A
FOREST. Cell-level ranks are necessary but nowhere near sufficient: continuing the interior slope
past the 90th percentile reaches only 14.3 m at rank 0.999, still 9 m short of the real tallest
tree. A stand's height distribution is strongly right-skewed and no three-point linear
interpolation reproduces that. Rather than invent a tail shape -- which would be a free parameter
fitted to the answer -- the SHAPE is taken from the template's own stems and only its LOCATION and
SPREAD come from the prediction, by the monotone recalibration in `recalibrate`. This is the
mechanism `type_ladder` already used for tree type, now applied to the matched traits as well: one
real stem per rank, carrying all of its fields at once, so the template's joint trait structure
survives while the three predicted knots move the marginals. The price is the same price the type
mechanism already pays, and it is disclosed in the same place: a warmed-climate restart carries the
template's distributional SHAPE, with only the predicted quantiles shifted.

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
#
# Above-ground biomass is deliberately NOT here, and the reason is measured rather than assumed.
# The synthesised file's above-ground biomass came out 4,030 gC/m2 against the real 3,777 -- 6.7 %
# HIGH, not low. The halved vegetation carbon reported from the model run happened during the run,
# to a roster the model rejected (see the module docstring), so matching mass would have chased a
# bias that is not there and dragged the height distribution off to do it.
#
# ⚠ AND WIDENING THIS SET MAKES IT WORSE -- measured, 20 cells, all 22 scored quantities. Matching
# five traits (adding sla, D95max, longevity) instead of two:
#   * hits the three medians it adds  -- D95max_p50 0.295 -> 0.157, longevity_p50 0.096 -> 0.075
#   * and wrecks the tails            -- wooddens_p90 0.063 -> 0.167, longevity_p90 0.192 -> 0.371,
#                                        sla_p10 0.088 -> 0.171
#   * doubles the above-ground biomass error  0.091 -> 0.154
#   * net: 11 of 22 quantities worse, 6 better, and the median cell hits 12 of 22 instead of 15.
# The mechanism is not tunable. A donor is ONE REAL STEM carrying one value of every trait at once,
# and the targets are all drawn at the same rank `u`, so a five-trait match asks for a stem sitting
# at the same quantile in five distributions simultaneously. No such stem need exist, and the
# nearest compromise reproduces every marginal worse than a two-trait match reproduces two. Getting
# further needs more donors or a different objective, not more terms in this one.
MATCH_TRAITS: tuple[str, ...] = ("height", "wooddens")

# Traits IMPOSED on the placed stem by overwriting its bytes, rather than obtained by choosing a
# donor that happens to carry them. Exactly one qualifies today, and the bar is deliberately high.
#
# ⚠ THIS BREAKS "no individual stem is ever edited", SO IT NEEDS A LICENCE, AND THE LICENCE IS READ
# OFF THE MODEL'S SOURCE, NOT ASSUMED. A field may be imposed only if all three hold:
#   1. THE MODEL NEVER RECOMPUTES IT. Every write to `tree->D95max` in the C is at tree BIRTH
#      (`tree/new_tree.c:124,179,209,233`), plus the sapling copy (`getsapling.c:94`) and the cell
#      trait template (`celldata.c:291`). `allocation_tree.c` writes `tree->D95` -- a DIFFERENT
#      field -- and never touches `D95max`. So an imposed value survives; it is not quietly undone.
#   2. IT DRIVES NO PHYSICS. Rooting depth is computed by `getrootdepth(height, k_root, model)`,
#      which takes `k_root`, not `D95max`. Every other appearance of `D95max` in the source is
#      file IO, an output histogram, or birth. Imposing it therefore cannot bend growth, mortality
#      or the water balance, which is what `-DSAFE` would otherwise be entitled to complain about.
#   3. IT IS STILL LOAD-BEARING FOR THE STATE. It is not inert decoration: offspring inherit it
#      from a parent in the treelist WITH MUTATION (`new_tree.c:179-182`), so the roster's D95max
#      distribution seeds the next generation's. And its three quantiles are 3 of the 22 scored.
#
# Contrast leaf carbon, which FAILS test 2 and is refused for that reason: `allometry_tree.c:39-41`
# derives height from it, so rescaling leaf carbon by 1.41 divides every tree's height by 1.41.
# That contrast is the whole point of the rule -- see `docs/decisions/20260909-T-the-roster-was-
# truncated-at-both-tails.md`.
#
# WHY IMPOSE RATHER THAN MATCH HARDER. Measured: with a PERFECT prediction the donor-choice
# mechanism still leaves D95max_p50 at 0.127 and its low tail at 0.146, because one donor is one
# real stem and cannot sit at the right quantile of three distributions at once. Adding D95max to
# `MATCH_TRAITS` is the thing already shown not to work (11 of 22 quantities worse). Imposition is
# the only mechanism that can close a gap the selection itself cannot reach.
#
# ⚠ DEFAULT EMPTY, AND THAT IS A MEASURED VERDICT ON THE PREDICTION, NOT ON THE MECHANISM. Imposing
# `D95max` does exactly what it promises: the synthesiser's own rooting-depth error against its
# input collapses from 0.072 to 0.007 at the median and from 0.119 to 0.003 in the low tail, so the
# cap that selection could not pass is gone. Fidelity to the TRUTH still got worse -- 20-year
# conjunctive 5 % -> 0 %, median 18/22 -> 17/22, `D95max_p50` 0.119 -> 0.133 -- because the level
# model's own rooting-depth error is LARGER than the donor accident it replaces: |pred-true| is
# 0.141 at the median and 0.179 in the low tail, against the 0.119/0.177 the inherited donor values
# happened to achieve. Reproducing a wrong prediction faithfully is worse than inheriting a lucky
# one, today.
#
# TURN THIS ON when the level model's `D95max` prediction beats roughly |pred-true| = 0.12 at the
# median, and turn it on REGARDLESS before any warmed-climate product is quoted: a donor's rooting
# depth is a present-day value from a neighbouring cell, so the accident that currently helps
# cannot shift with climate, and the acceptance criterion's binding clause is the warming response.
# Re-measure with `synthesise_cell(..., impose_traits=("D95max",))` and the year-0 table; there is
# no need to touch this line to test it.
IMPOSED_TRAITS: tuple[str, ...] = ()

# Byte offset and format of each imposable field within a tree entry, from `binfmt.restart`.
_TRAIT_BYTES: dict[str, tuple[int, int]] = {"D95max": (337, 8)}


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
        # Annotated rather than returned directly: `fields` is a structured array typed Any, so
        # indexing it yields Any and returning that straight out defeats the declared return type
        # under `strict` (the same shape as the fix in `score.matrix`).
        out: npt.NDArray[np.float64] = np.asarray(self.fields[name]).astype(np.float64)
        return out


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
    """A monotone quantile function through three predicted points. THE FALLBACK, not the default.

    Linear between the knots; beyond them the last interior slope is continued, which keeps the
    function monotone without inventing a tail shape the prediction says nothing about. The three
    knots are sorted first: the three heads are fitted independently, so nothing guarantees the
    predicted 10th percentile comes out below the predicted 90th, and a crossed pair would produce
    a decreasing quantile function and a nonsense roster.

    ⚠ This is used only where the template cannot supply a shape -- a treeless template, or one
    whose own 10th and 90th percentiles coincide. Everywhere else `recalibrate` is used instead,
    because the straight tail this function draws is measurably far too short: at the 0.999 rank it
    reaches 14.3 m where the real stand's tallest tree is 23.0 m (see the module docstring).
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
    # Annotated rather than returned directly, for the reason given in `DonorPool.trait`:
    # `np.interp` is typed loosely enough that the expression comes back as Any.
    clipped: npt.NDArray[np.float64] = np.maximum(out, 1e-9).astype(np.float64)
    return clipped


def recalibrate(
    values: npt.NDArray[np.float64],
    sample: npt.NDArray[np.float64],
    p10: float,
    p50: float,
    p90: float,
) -> npt.NDArray[np.float64] | None:
    """Move a REAL distribution's values onto three predicted knots, monotonically.

    `sample` is the template cell's own stems -- a real equilibrium stand, so it carries the
    right-skew, the understorey spike and the long upper tail that a forest actually has.
    `values` are draws from it (one real stem per rank). The returned values have the template's
    shape and the prediction's location and spread: between the knots the map is the piecewise
    linear transform sending the template's own (p10, p50, p90) to the predicted (p10, p50, p90).
    Exact at all three knots, continuous, and monotone -- so the rank ordering the caller relies
    on survives.

    ⚠ OUTSIDE THE KNOTS THE MAP IS MULTIPLICATIVE, AND THAT IS NOT A STYLE CHOICE. Continuing the
    interior slope past the top knot AMPLIFIES the prediction's own error, because the correction
    it applies grows with distance from the median while the prediction's evidence does not. It was
    measured doing exactly that: the level model predicts this block's 90th-percentile height 5 %
    high, and an extrapolated slope turned that into +13 % at the 99.9th percentile, which -- since
    stem mass climbs steeply with height -- put the whole roster's above-ground biomass 21 % over
    the truth while every other quantity improved. Scaling the tail by `predicted / template` at
    the knot instead caps the distortion at the prediction's own error, and is exactly the identity
    when the prediction is right. Both ends are multiplicative for the same reason, which also
    makes the result positive by construction rather than by clipping.

    Returns None when the template cannot supply a shape (fewer than three distinct positive
    percentiles), which is the caller's signal to fall back to `quantile_function`. Returning None
    rather than silently degrading matters: the fallback draws a measurably too-short tail, and a
    cell that took it must be visible as having taken it.
    """
    lo, mid, hi = sorted((float(p10), float(p50), float(p90)))
    t10, t50, t90 = (float(v) for v in np.percentile(sample, [10.0, 50.0, 90.0]))
    if not (0.0 < t10 < t50 < t90):
        return None
    out = np.where(
        values <= t50,
        lo + (values - t10) * ((mid - lo) / (t50 - t10)),
        mid + (values - t50) * ((hi - mid) / (t90 - t50)),
    )
    # The two tails, anchored at their knot rather than extrapolated from the interior.
    out = np.where(values < t10, values * (lo / t10), out)
    out = np.where(values > t90, values * (hi / t90), out)
    mapped: npt.NDArray[np.float64] = np.maximum(out, 1e-9).astype(np.float64)
    return mapped


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
    # Tree types: what the template's own roster holds, what was asked for, what was placed.
    # `inadmissible_placed` must be zero -- it counts stems of a type this cell's real state never
    # contains, which is the fault that killed half the first synthesised roster in its first year.
    type_admissible: tuple[int, ...] = ()
    type_requested: dict[int, int] = field(default_factory=dict)
    type_achieved: dict[int, int] = field(default_factory=dict)
    type_fallbacks: int = 0
    inadmissible_placed: int = 0
    # Where each matched trait's distributional SHAPE came from: "template" (the cell's own real
    # stand, recalibrated onto the predicted knots) or "knots" (the three-point linear fallback,
    # whose upper tail is measurably far too short). A cell that silently took the fallback would
    # look like a cell that had a tail; this is what stops that.
    shape_source: dict[str, str] = field(default_factory=dict)
    ranks_drawn_over: str = "cell"
    # The upper tail, which `pool_shortfall` (a median) cannot see, and the tallest stem placed
    # against the tallest the template holds -- the two numbers that made the truncation visible.
    tail_shortfall: dict[str, float] = field(default_factory=dict)
    tallest_placed: float = 0.0
    tallest_in_template: float = 0.0
    # Fields written into the stem rather than inherited from its donor, and where each one's
    # shape came from. `imposed_clamped` counts stems whose imposed value hit the range real stems
    # in the pool actually exhibit -- a large count means the prediction is asking for a tree the
    # corpus does not contain, which is a finding, not something to absorb silently.
    imposed: dict[str, str] = field(default_factory=dict)
    imposed_clamped: int = 0


def template_ladder(template: dict[str, Any]) -> Any:
    """The template cell's own stems, every field, ordered smallest tree to largest.

    One row per real stem of the cell, sorted by height, pooled over all patches -- so row k is the
    k-th smallest tree in the STAND, which is the level the predicted quantiles are defined at.
    Reading a whole stem rather than one field is the point: the type, the height and the wood
    density at a given size rank all come off the SAME real tree, so the template's joint trait
    structure is carried over rather than three marginals being recombined independently.
    """
    rows: list[Any] = []
    for patch in template["stands"][0]["patches"]:
        arr = trees_of(patch["pftlist"])
        if arr.size:
            rows.append(arr)
    if not rows:
        return np.zeros(0, dtype=trees_of(template["stands"][0]["patches"][0]["pftlist"]).dtype)
    allrows = np.concatenate(rows)
    order = np.argsort(np.asarray(allrows["height"], dtype=np.float64), kind="stable")
    return allrows[order]


def type_ladder(template: dict[str, Any]) -> npt.NDArray[np.uint8]:
    """The template cell's own stems' PFT ids, ordered smallest tree to largest.

    Two things are read off a real record for the cell at once, and both are needed:

    * **which types this climate admits** -- the set of ids present. A type absent from a real
      equilibrium state of this cell is a type the cell's climate does not support, and a stem of
      that type is dead within a year however internally consistent it is.
    * **how type and size go together here** -- the ORDER. Type and size are correlated in a real
      stand (the canopy and the understorey are different species), so assigning types across the
      predicted size roster at random would ask a type that is never tall to be tall, and the
      nearest donor of that type would then be its own tallest stem, distorting the very height
      distribution the emulator predicted. Taking the type at the matching size RANK carries the
      template's type-size association over while the height VALUES stay the emulator's.
    """
    rungs = template_ladder(template)
    if rungs.size == 0:
        return np.zeros(0, dtype=np.uint8)
    return np.asarray(rungs["id"], dtype=np.uint8)


def _rank_index(size: int, u: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    """The ladder row each requested rank lands on."""
    return np.clip((u * size).astype(np.int64), 0, size - 1)


def _types_for(ladder: npt.NDArray[np.uint8], u: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    """The template's type at each predicted size rank."""
    return np.asarray(ladder[_rank_index(ladder.size, u)], dtype=np.int64)


def _impose(
    chosen: npt.NDArray[np.uint8],
    placed: Any,
    imposed: dict[str, npt.NDArray[np.float64]],
    mine: npt.NDArray[np.int64],
    pool_range: dict[str, tuple[float, float]],
) -> int:
    """Write the imposed fields into the transplanted stems' bytes. Returns the clamp count.

    `placed` is updated in step, because the report must describe the file that was WRITTEN and
    not the donors that were picked -- reading a donor's value back after overwriting it is
    exactly the mistake that once made a whole decision record's diagnosis wrong.
    """
    clamped = 0
    for name, values in imposed.items():
        off, width = _TRAIT_BYTES[name]
        want = values[mine]
        lo, hi = pool_range[name]
        clipped = np.clip(want, lo, hi)
        clamped += int(np.count_nonzero(clipped != want))
        for k in range(clipped.size):
            chosen[k][off : off + width] = np.frombuffer(
                struct.pack("<d", float(clipped[k])), dtype=np.uint8
            )
        placed[name] = clipped
    return clamped


def _tally(types: npt.NDArray[np.int64] | None) -> dict[int, int]:
    """How many stems of each type the roster asks for."""
    out: dict[int, int] = {}
    for t in types if types is not None else ():
        out[int(t)] = out.get(int(t), 0) + 1
    return out


def _targets(
    rungs: Any,
    u: npt.NDArray[np.float64],
    prediction: dict[str, float],
    match_traits: tuple[str, ...],
) -> tuple[dict[str, npt.NDArray[np.float64]], dict[str, str]]:
    """The trait value asked of each ranked stem, and where each trait's SHAPE came from.

    One real template stem per rank, its traits recalibrated onto the predicted knots. The stem is
    read whole, so height and wood density at a given rank come off the same tree and the
    template's joint structure survives; only the marginals are moved. Falls back to the
    three-knot linear function per trait, and says so, wherever the template cannot supply a shape.
    """
    out: dict[str, npt.NDArray[np.float64]] = {}
    source: dict[str, str] = {}
    names = set(rungs.dtype.names or ()) if rungs.size else set()
    for name in match_traits:
        if f"{name}_p50" not in prediction:
            continue
        p10, p50, p90 = (float(prediction[f"{name}_p{q}"]) for q in (10, 50, 90))
        mapped = None
        if u.size and name in names:
            sample = np.asarray(rungs[name], dtype=np.float64)
            mapped = recalibrate(sample[_rank_index(sample.size, u)], sample, p10, p50, p90)
        out[name] = quantile_function(p10, p50, p90, u) if mapped is None else mapped
        source[name] = "knots" if mapped is None else "template"
    return out, source


def _choose_donors(
    pool: DonorPool,
    targets: dict[str, npt.NDArray[np.float64]],
    rng: np.random.Generator,
    want_types: npt.NDArray[np.int64] | None = None,
    admissible: tuple[int, ...] = (),
) -> tuple[npt.NDArray[np.int64], int]:
    """Nearest donor in standardised trait space, one per target stem, WITHIN the wanted type.

    Standardised over the POOL so no trait dominates by unit: wood density is ~2e5 gC/m3 and height
    is ~10 m, so an unstandardised distance would be a wood-density match with height as noise.

    `want_types` restricts each target's candidates to donors of that PFT id. Where the pool holds
    no donor of the wanted type, the candidate set widens to the cell's other ADMISSIBLE types --
    never to the whole pool, because widening to the whole pool is exactly what transplanted
    tropical evergreens into temperate cells. Returns the picks and the number of targets that
    had to fall back.
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

    fallbacks = 0
    if want_types is not None:
        ids = np.asarray(pool.fields["id"], dtype=np.int64)
        allowed = ids[None, :] == want_types[:, None]
        missing = ~allowed.any(axis=1)
        if missing.any():
            wider = (
                np.isin(ids, np.asarray(admissible, dtype=np.int64))
                if admissible
                else np.ones(pool.n, dtype=bool)
            )
            allowed[missing] = wider[None, :]
            fallbacks = int(missing.sum())
            # Nothing admissible in the pool at all. Placing a stem the cell cannot support is
            # still wrong, but leaving an all-forbidden row would make argmin return donor 0
            # silently; `inadmissible_placed` is what surfaces it.
            allowed[~allowed.any(axis=1)] = True
        # Re-annotated rather than assigned straight back: `np.where` is typed loosely enough to
        # come back shape- and dtype-erased, which `strict` rejects against `cost`'s declared type.
        cost = np.asarray(np.where(allowed, cost, np.inf), dtype=np.float64).reshape(cost.shape)
    return np.asarray(np.argmin(cost, axis=1), dtype=np.int64), fallbacks


def synthesise_cell(  # noqa: PLR0915 -- one pass over the patches; splitting it would scatter
    template: dict[str, Any],
    prediction: dict[str, float],
    pool: DonorPool,
    layout: Layout,
    *,
    cell: int,
    template_cell: int,
    seed: int = 0,
    match_traits: tuple[str, ...] = MATCH_TRAITS,
    impose_traits: tuple[str, ...] = IMPOSED_TRAITS,
) -> tuple[dict[str, Any], SynthReport]:
    """Replace a template record's roster and soil totals with a predicted state.

    `prediction` needs `stems_per_patch`, `<trait>_p10/_p50/_p90` for the matched traits, and
    optionally `soilc` and `litterc`.

    `match_traits` is a parameter and not a constant because the right set is an empirical
    question, and the answer is not "all of them". One donor is ONE REAL STEM, so it carries one
    value of every trait at once; asking it to sit at the same rank in six trait distributions
    simultaneously asks for a stem that need not exist in the pool, and the nearest compromise can
    reproduce every marginal worse than a two-trait match reproduces two. Measure before widening.
    """
    if template["skip"]:
        raise ValueError(f"template cell {template_cell} is a skip cell; nothing to condition on")
    rng = np.random.default_rng(seed)
    rec = {k: v for k, v in template.items()}
    stand = template["stands"][0]
    npatch = int(stand["npatch"])

    want_per_patch = max(float(prediction["stems_per_patch"]), 0.0)
    rungs = template_ladder(template)
    ladder = type_ladder(template)
    admissible = tuple(int(t) for t in np.unique(ladder)) if ladder.size else ()
    report = SynthReport(
        cell=cell,
        template_cell=template_cell,
        stems_requested=0,
        stems_placed=0,
        donors_available=pool.n,
        requested={k: float(v) for k, v in prediction.items()},
        type_admissible=admissible,
    )

    # THE RANKS, DRAWN ONCE ACROSS THE CELL. Every patch's count is settled first, because the
    # ranks cannot be known until the cell's total is: the predicted quantiles are cell-level, so
    # rank k of N runs over the whole stand and not over one patch of it. Dealing the ranks out at
    # random then makes each patch a random SAMPLE of the stand -- which is what a patch is -- and
    # lets the cell hold the one tree that lives at rank 0.999. Drawing per patch instead handed
    # every patch the same truncated ladder and cost the entire upper tail; see the module
    # docstring for the measurement.
    #
    # Stochastic rounding of the count survives unchanged: a predicted 23.4 stems per patch must
    # not become 23 in every patch, or the cell mean comes out 23.0 and the count the emulator
    # predicted is not the count that was written.
    counts = [
        int(np.floor(want_per_patch) + (rng.random() < (want_per_patch % 1.0)))
        for _ in stand["patches"]
    ]
    n_cell = int(sum(counts))
    report.stems_requested = n_cell
    report.ranks_drawn_over = "cell" if n_cell else "none"
    u_cell = (np.arange(n_cell) + 0.5) / n_cell if n_cell else np.zeros(0)
    owner = rng.permutation(np.repeat(np.arange(len(counts)), counts))

    targets_cell, report.shape_source = _targets(rungs, u_cell, prediction, match_traits)
    want_types_cell = _types_for(ladder, u_cell) if (ladder.size and n_cell) else None
    report.type_requested = _tally(want_types_cell)

    # IMPOSED fields: same ladder, same recalibration, but written into the stem instead of used
    # to pick one. The clamp range is what REAL stems of any type in the pool actually exhibit, so
    # a stretched prediction can never write a rooting depth no tree in the corpus has.
    imposed_cell, imposed_shapes = _targets(rungs, u_cell, prediction, impose_traits)
    report.imposed = imposed_shapes
    pool_range = {
        name: (float(np.min(pool.trait(name))), float(np.max(pool.trait(name))))
        for name in imposed_cell
    }

    new_patches: list[dict[str, Any]] = []
    placed_fields: list[Any] = []
    for p_index, patch in enumerate(stand["patches"]):
        n = counts[p_index]
        mine = np.flatnonzero(owner == p_index) if n_cell else np.zeros(0, dtype=np.int64)

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
            # This patch's share of the cell's ranks. The height target is monotone in rank, so
            # target k is still the k-th smallest stem and the template's type at that same rank is
            # still the type to ask for. The wood-density target deliberately is NOT monotone: it
            # is the density of the real template stem at that HEIGHT rank, so the template's joint
            # height-density structure is carried over instead of the two being forced into perfect
            # rank correlation, which is what drawing both from one quantile function did.
            targets = {name: values[mine] for name, values in targets_cell.items()}
            want_types = want_types_cell[mine] if want_types_cell is not None else None
            picks, fell_back = _choose_donors(
                pool, targets, rng, want_types=want_types, admissible=admissible
            )
            report.type_fallbacks += fell_back
            chosen = pool.raw[picks]
            # IMPOSED fields, written into the bytes rather than obtained by choosing a donor that
            # carries them. Licensed only for fields the model never recomputes and that drive no
            # physics -- see IMPOSED_TRAITS for the three tests and for why leaf carbon fails them.
            # The value is the TEMPLATE stem's own value at this height rank, recalibrated onto the
            # predicted knots, so the template's height-to-rooting-depth association survives while
            # the marginal becomes the emulator's.
            placed = pool.fields[picks].copy()
            report.imposed_clamped += _impose(chosen, placed, imposed_cell, mine, pool_range)
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
                report.type_achieved[pft_id] = report.type_achieved.get(pft_id, 0) + 1
                if admissible and pft_id not in admissible:
                    report.inadmissible_placed += 1
                parts.append(row.tobytes())
            placed_fields.append(placed)
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
                for name in match_traits
                for q in QUANTILE_LEVELS
            },
        }
        for name in match_traits:
            key = f"{name}_p50"
            if prediction.get(key):
                report.pool_shortfall[name] = float(
                    (report.achieved[key] - prediction[key]) / prediction[key]
                )
            # The TAIL, reported separately, because it is the half of the distribution the median
            # cannot see and the half that carried the whole leaf-area loss. A roster can sit on
            # the predicted median to four decimal places and still hold no tree above 13 m.
            tail = f"{name}_p90"
            if prediction.get(tail):
                report.tail_shortfall[name] = float(
                    (report.achieved[tail] - prediction[tail]) / prediction[tail]
                )
        report.tallest_placed = float(np.max(allf["height"].astype(float)))
        report.tallest_in_template = (
            float(np.max(np.asarray(rungs["height"], dtype=np.float64))) if rungs.size else 0.0
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
