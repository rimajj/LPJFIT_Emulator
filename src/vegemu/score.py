"""The metrics, the acceptance band, and the spatial folds — one implementation, shared.

WHY THIS IS A SHARED MODULE AND NOT PART OF THE TRAINING CODE. Line X derives what each null must
return; line T measures what the model returns. If those two used different code the comparison
would be worthless, and the pre-registration's `expected.value` would be checking the wrong thing.

THE ACCEPTANCE TEST, in the project's own terms (invariant 5, `MEMORY.md:acceptance`):

    tolerance per cell per quantity = max(10 %, the model's own two-seed spread for that cell)
    a cell PASSES only if every scored quantity is inside its band -- conjunctively
    the truth is the MEAN of the two seeds, not one of them

The truth being the two-seed mean is not cosmetic. LPJmL-FIT is stochastic: ~2.4 % of next-year
count variance is its own per-patch Bernoulli noise and the exact floor is ~28 % of residual
variance, so the correct target is the ensemble expectation and not a single draw
(`MEMORY.md:target-is-expectation`). Scoring against one seed would charge the emulator for noise
no emulator can predict.

⚠ THE CIRCULARITY, DISCLOSED. The band is derived from the same two seeds whose mean is the truth,
so "predict seed 1" sits at exactly half a band by construction and always passes. That arm is
therefore a CEILING, not a null, and it is reported as such. Using it as a declared null would set
an unbeatable bar and guarantee a failing verdict for arithmetic reasons.
`acceptance_band_transferred` breaks that circle by taking the tolerance from a DIFFERENT leg's two
seeds; it is available for any leg whose two seeds are genuinely two realisations, which on corpus
v0 means historical and ssp126 but NOT ssp370 (whose two seed tables are byte-identical).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import polars as pl

FLOOR = 0.10  # the 10 % in max(10 %, two-seed spread)

# --------------------------------------------------------------------------------------------
# The conjunctive scored set: counts AND trait medians AND trait distributions, which is what
# the acceptance criterion demands. 22 quantities.
# --------------------------------------------------------------------------------------------
COUNT_QUANTITIES: tuple[str, ...] = ("stems_per_patch",)
STOCK_QUANTITIES: tuple[str, ...] = ("agb", "lai", "soilc")
TRAITS_SCORED: tuple[str, ...] = ("wooddens", "sla", "k_root", "D95max", "longevity", "height")
MEDIAN_QUANTITIES: tuple[str, ...] = tuple(f"{t}_p50" for t in TRAITS_SCORED)
# The "distributions" clause: the tails, not just the centre. A model can match every median and
# still have the wrong distribution, which is exactly the failure a median-only test misses.
DISTRIBUTION_QUANTITIES: tuple[str, ...] = tuple(
    f"{t}_p{q}" for t in TRAITS_SCORED for q in (10, 90)
)

SCORED_CONJUNCTIVE: tuple[str, ...] = (
    *COUNT_QUANTITIES,
    *STOCK_QUANTITIES,
    *MEDIAN_QUANTITIES,
    *DISTRIBUTION_QUANTITIES,
)

# The response test uses a smaller headline set: seven integrative quantities. A conjunctive band
# test is meaningless on a CHANGE, because a relative band around a change that is near zero is
# near zero too -- so the response is scored by variance explained instead.
RESPONSE_QUANTITIES: tuple[str, ...] = (
    "stems_per_patch",
    "agb",
    "lai",
    "soilc",
    "height_p50",
    "wooddens_p50",
    "sla_p50",
)


def unit_sphere(
    lon: npt.NDArray[np.float64], lat: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """(x, y, z) on the unit sphere — the geographic-address null's only features.

    Unit-sphere rather than raw latitude/longitude on purpose: it has no wrap-around discontinuity
    at the date line and no pole singularity, so the address null is as STRONG as it can be. A weak
    null is worse than no null.
    """
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=1)


def relative_spread(
    seed1: npt.NDArray[np.float64], seed2: npt.NDArray[np.float64], floor: float = FLOOR
) -> npt.NDArray[np.float64]:
    """The floored RELATIVE two-seed spread, per cell per quantity: max(floor, |s1-s2|/|mean|).

    Factored out so that a band can be built from one leg's spread and applied to another leg's
    level (`acceptance_band_transferred`) using byte-identical arithmetic to the same-leg case.
    A cell-quantity whose mean is zero has no defined relative spread and falls back to the floor.
    """
    mean = (seed1 + seed2) / 2.0
    denom = np.abs(mean)
    with np.errstate(divide="ignore", invalid="ignore"):
        spread = np.where(denom > 0, np.abs(seed1 - seed2) / denom, np.nan)
    # Annotated rather than returned directly: a numpy ufunc's `__call__` is typed `Any` in the
    # stubs, so `return np.maximum(...)` defeats the declared return type under mypy `strict`.
    out: npt.NDArray[np.float64] = np.maximum(floor, np.nan_to_num(spread, nan=floor))
    return out


def acceptance_band(
    seed1: npt.NDArray[np.float64], seed2: npt.NDArray[np.float64], floor: float = FLOOR
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(truth, band) from the two seeds. `band` is an ABSOLUTE tolerance, per cell per quantity.

    truth = the two-seed mean; band = max(floor, |s1-s2|/|truth|) * |truth|.
    """
    truth = (seed1 + seed2) / 2.0
    return truth, relative_spread(seed1, seed2, floor) * np.abs(truth)


def acceptance_band_transferred(
    seed1: npt.NDArray[np.float64],
    seed2: npt.NDArray[np.float64],
    ref_seed1: npt.NDArray[np.float64],
    ref_seed2: npt.NDArray[np.float64],
    floor: float = FLOOR,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(truth, band) where the tolerance's SIZE comes from a different leg than the truth.

    THIS IS THE ANSWER TO THE CIRCULARITY DISCLOSED ABOVE. `acceptance_band` derives the tolerance
    from the same two seeds whose mean is the truth, so "predict seed 1" sits at exactly half a band
    by construction and cannot fail. Here the truth is `(seed1+seed2)/2` of the leg being scored,
    while the RELATIVE spread is taken from `ref_seed1`/`ref_seed2` -- a different leg, same cell,
    same quantity -- so nothing about the scored realisation pair sets its own tolerance.

    The transfer is only legitimate because the two legs' spreads are the same size, which is a
    MEASURED claim and not an assumption: over the 56,950 cells tree-bearing in both seeds of both
    legs on corpus v0, the historical and ssp126 relative two-seed spreads agree to within 6 % on
    every summary -- median 0.03027 vs 0.03207, p90 0.16350 vs 0.16529, and 19.30 % vs 20.01 % of
    cell-quantities above the 10 % floor. State it with the number whenever a transferred band is
    used, and report the same-leg band beside it.
    """
    truth = (seed1 + seed2) / 2.0
    return truth, relative_spread(ref_seed1, ref_seed2, floor) * np.abs(truth)


def band_hits(
    pred: npt.NDArray[np.float64], truth: npt.NDArray[np.float64], band: npt.NDArray[np.float64]
) -> npt.NDArray[np.bool_]:
    """Per-cell per-quantity: is the prediction inside the band?

    A NaN on either side counts as a MISS, never as a pass. A quantity that has no value (a trait
    median in a cell with no stems) must not be silently credited.
    """
    ok = np.abs(pred - truth) <= band
    return np.where(np.isfinite(pred) & np.isfinite(truth) & np.isfinite(band), ok, False)


def band_frac_conjunctive(
    pred: npt.NDArray[np.float64], truth: npt.NDArray[np.float64], band: npt.NDArray[np.float64]
) -> float:
    """The blessed statistic of the map experiment: fraction of cells inside the band on ALL of it.

    Conjunctive, per invariant 5 -- a mean over quantities would let a model buy a good score by
    nailing soil carbon while getting every trait wrong.
    """
    hits = band_hits(pred, truth, band)
    return float(hits.all(axis=1).mean()) if hits.size else float("nan")


def band_frac_per_quantity(
    pred: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    band: npt.NDArray[np.float64],
    names: Sequence[str],
) -> dict[str, float]:
    """Per-quantity pass rates. Reported beside the conjunctive number, never instead of it."""
    hits = band_hits(pred, truth, band)
    return {n: float(hits[:, i].mean()) for i, n in enumerate(names)}


def skill_vs_no_change(
    pred_delta: npt.NDArray[np.float64], true_delta: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Per-quantity `1 - SSE(pred) / SS(true)`, i.e. skill relative to predicting NO CHANGE.

    Chosen so that the decisive null is pinned analytically: predicting zero change gives exactly
    0.0, a perfect prediction gives 1.0, and a prediction uncorrelated with the truth gives about
    -1.0. That removes the need to guess what the kill-test null "should" return -- which is the
    step the predecessor got wrong five times.
    """
    good = np.isfinite(pred_delta) & np.isfinite(true_delta)
    out = np.full(true_delta.shape[1], np.nan)
    for j in range(true_delta.shape[1]):
        m = good[:, j]
        denom = float((true_delta[m, j] ** 2).sum())
        if denom <= 0:
            continue
        sse = float(((pred_delta[m, j] - true_delta[m, j]) ** 2).sum())
        out[j] = 1.0 - sse / denom
    return out


def skill_response_mean(
    pred_delta: npt.NDArray[np.float64], true_delta: npt.NDArray[np.float64]
) -> float:
    """The blessed statistic of the response experiment: the unweighted mean of the above.

    Unweighted so that no single quantity's variance dominates. Each term is already dimensionless
    and each is exactly 0 for the no-change null, so the mean is exactly 0 for it too.
    """
    per = skill_vs_no_change(pred_delta, true_delta)
    return float(np.nanmean(per))


# --------------------------------------------------------------------------------------------
# Folds. Random folds by cell would turn every per-cell score into a spatial-interpolation
# score: the effective independent spatial sample is ~161 populated 15-degree tiles, not 54,020
# cells, so row counts overstate independent evidence by roughly four orders of magnitude.
# --------------------------------------------------------------------------------------------
def spatial_blocks(
    lon: npt.NDArray[np.float64], lat: npt.NDArray[np.float64], degrees: float
) -> npt.NDArray[np.int64]:
    """A block id per cell, on a `degrees`-wide lon/lat lattice."""
    bx = np.floor((lon + 180.0) / degrees).astype(np.int64)
    by = np.floor((lat + 90.0) / degrees).astype(np.int64)
    return bx * 10_000 + by


def blocked_spatial_folds(
    lon: npt.NDArray[np.float64],
    lat: npt.NDArray[np.float64],
    k: int = 5,
    degrees: float = 15.0,
    seed: int = 42,
) -> npt.NDArray[np.int64]:
    """Fold index per cell, with whole blocks held out together.

    Blocks are shuffled and dealt round-robin so the folds stay balanced in block COUNT. They will
    not be exactly balanced in cell count, which is correct: a fold containing the Amazon has more
    cells but not more independent evidence.
    """
    blocks = spatial_blocks(lon, lat, degrees)
    uniq = np.unique(blocks)
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    assign = {int(b): i % k for i, b in enumerate(uniq)}
    return np.array([assign[int(b)] for b in blocks], dtype=np.int64)


def matrix(frame: pl.DataFrame, columns: Sequence[str]) -> npt.NDArray[np.float64]:
    """A (rows, len(columns)) float64 matrix, in the given column order."""
    # Annotated rather than returned directly: polars is in mypy's ignore_missing_imports list, so
    # `to_numpy()` is typed Any and returning it straight out defeats the declared return type
    # under `strict`. `.astype` is kept over `np.asarray` because it always copies, so a caller
    # cannot end up aliasing polars' own buffer.
    out: npt.NDArray[np.float64] = frame.select(list(columns)).to_numpy().astype(np.float64)
    return out


def describe_basis(
    leg: str,
    state_year: int,
    window: tuple[int, int],
    ncell: int,
    *,
    npatch: int = 25,
    seeds: Sequence[int] = (1, 2),
) -> str:
    """One sentence carrying the reference basis, so a number can be quoted with it.

    Invariant 4: state the basis in the same sentence as the number -- source, leg, years, patch
    count, cell count, and whether it is a level or a ratio. The patch count is in here because a
    tolerance derived at 25 patches largely evaporates at acceptance grade (~125-192).
    """
    return (
        f"LPJmL-FIT {leg} leg, state at {state_year} from the restart file, climate window "
        f"{window[0]}-{window[1]}, npatch={npatch}, "
        f"truth = mean of seeds {'+'.join(map(str, seeds))}, "
        f"{ncell} tree-bearing cells, dimensionless fraction (level)"
    )
