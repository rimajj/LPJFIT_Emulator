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
`spread_across_climates` breaks it the other way, from the SAME cell's other climates, and is what
the worst-quantity score (C1, the section at the end of this module) uses on the pilot ensemble.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import polars as pl

FLOOR = 0.10  # the 10 % in max(10 %, two-seed spread)

# --------------------------------------------------------------------------------------------
# THE ADDITIVE FLOOR. A RELATIVE band is meaningless for a quantity that lives near zero: a type
# whose true share is 0.002 gets a band of 0.0002, and nothing -- including a second run of the
# model itself -- can land inside it. So the band is `max(rel_spread * |truth|, abs_floor)`, and
# `abs_floor` carries the units of the quantity.
#
# ⚠ THERE IS NO DEFAULT, DELIBERATELY, AND THAT IS THE WHOLE DESIGN. The measured value below is
# in UNITS OF STEM SHARE and is meaningful for `pft_frac_*` and nothing else -- an absolute floor
# of 0.0384 would be absurd on soil carbon (gC/m2) and merely wrong on LAI. A default would leak
# a floor measured for one quantity onto every other, silently, which is the shape this repo keeps
# getting bitten by. Every call site must therefore say what floor applies to ITS quantities;
# `abs_floor=0.0` recovers the old purely-relative band exactly, and is the right answer for the
# 22 quantities of `SCORED_CONJUNCTIVE`.
#
# MEASURED, NOT CHOSEN (`MEMORY.md:abs-floor-measured`, `20260915-X` record): the p90 of the
# model's OWN absolute two-seed disagreement on type shares, over the pilot's perturbed pairs.
# Median 0.0027, p90 0.0384, p99 0.1148. Taking p90 means the floor admits the disagreement the
# model has with itself in 90 % of cell-quantities and no more.
#
# ⚠ NEVER RAISE IT TO RESCUE A FAILING TEST. A threshold chosen after seeing the values is not a
# threshold. X4 was retired as the wrong instrument rather than rescued by a wider floor, and that
# precedent is the reason this constant states its own provenance.
ABS_FLOOR_COMPOSITION = 0.0384

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

# --------------------------------------------------------------------------------------------
# COMPOSITION -- which tree types the cell holds, as a share of its stems.
#
# ⚠ A SEPARATE TUPLE, DELIBERATELY NOT AN EXTENSION OF `RESPONSE_QUANTITIES`. That tuple IS the
# estimand of a sealed pre-registration (`X-20260909-pilot-warming-response`, "the unweighted mean
# of the seven"), and its recorded model score of 0.5453 is reproducible only while the tuple has
# exactly those seven members. Appending to it would silently redefine what that sealed experiment
# measures and make its own result unreproducible -- so composition is scored as its OWN arm,
# against its own nulls, and the two numbers are quoted separately.
#
# WHY THIS IS WORTH SCORING AT ALL. `models/synth.py` COPIES tree type from the target cell's
# template roster, so an emulated warmed forest is structurally forbidden from shifting its species
# mix; that limit is disclosed in the synthesiser's own docstring and is waiting on these columns
# entering a scored set. On the pilot ensemble the truth moves a great deal -- a type's stem share
# shifts with an RMS of 0.15-0.22 and more than 5 percentage points in ~30 % of (cell, climate)
# pairs -- so there is real variance here to explain or fail to explain.
#
# WHAT THE NUMBER IS: the share of the cell's STEMS carried by tree type i, counted per individual
# and NOT weighted by biomass (`corpus/state.py` builds it with `np.bincount(ids) / ids.size`). A
# type that is numerically rare but holds the canopy therefore scores small. That is a property of
# the definition, not of the emulator, and it must be stated with any number derived from it.
#
# THE SUM IS 1, SO ONLY SIX OF THE SEVEN ARE FREE. Measured on the pilot, the seven sum to 1 on
# every treed row to within 2e-16. A skill score that is the unweighted mean of seven terms whose
# changes sum to zero is therefore mildly redundant -- it is still a legitimate statistic and every
# null is scored under the identical redundancy, but no term should be read as independent evidence.
COMPOSITION_QUANTITIES: tuple[str, ...] = tuple(f"pft_frac_{i}" for i in range(7))


def blank_treeless_composition(state: pl.DataFrame) -> pl.DataFrame:
    """`pft_frac_*` -> NaN on every row with no stems. Apply before any composition contrast.

    ⚠ WITHOUT THIS THE COLLAPSE IS DOUBLE-COUNTED AND MASQUERADES AS A COMPOSITION SHIFT.
    `corpus/state.py:_empty_summary` writes 0.0 into every `pft_frac_*` of a treeless cell, because
    it zeroes all of `STATE_COLUMNS` and then re-blanks only the trait quantiles. For a LEVEL that
    is defensible; for a CHANGE it is not. A cell that goes treeless then reads as "type 3's share
    fell from 0.81 to 0.00", which is not a shift in the mix -- there is no mix -- and it is the
    same event `stems_per_patch` already scores in full. Measured on pilot-v1 it inflates the total
    squared change by 15-18 % on most types.

    The rule this restores is the one the trait medians already use, for the identical reason: a
    wood density of zero is not light wood, it is no wood, and a type share of zero is not a rare
    type, it is no forest. A pair drops per quantity when the arm OR the control has no stems --
    542 of 5,800 pilot pairs, 493 of them from the 17 cells already treeless under their control.

    Not fixed at source because `src/vegemu/corpus/**` is line D's exclusively, and every cached
    state table already on disk carries the zeros; masking here is idempotent and needs no
    re-decode.
    """
    missing = [c for c in ("stems_total", *COMPOSITION_QUANTITIES) if c not in state.columns]
    if missing:
        raise ValueError(f"state table has no composition to blank: missing {missing}")
    treeless = pl.col("stems_total") <= 0
    return state.with_columns(
        [pl.when(treeless).then(None).otherwise(pl.col(c)).alias(c) for c in COMPOSITION_QUANTITIES]
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
    seed1: npt.NDArray[np.float64],
    seed2: npt.NDArray[np.float64],
    floor: float = FLOOR,
    *,
    abs_floor: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(truth, band) from the two seeds. `band` is an ABSOLUTE tolerance, per cell per quantity.

    truth = the two-seed mean; band = max(max(floor, |s1-s2|/|truth|) * |truth|, abs_floor).

    `abs_floor` is REQUIRED and keyword-only: it carries the units of the quantities in `seed1`,
    so no default can be right for all of them. Pass `0.0` for the purely relative band -- which
    is byte-identical to this function before the additive floor existed -- or
    `ABS_FLOOR_COMPOSITION` for `pft_frac_*`. See that constant for why there is no default.
    """
    truth = (seed1 + seed2) / 2.0
    band: npt.NDArray[np.float64] = np.maximum(
        relative_spread(seed1, seed2, floor) * np.abs(truth), abs_floor
    )
    return truth, band


def acceptance_band_transferred(
    seed1: npt.NDArray[np.float64],
    seed2: npt.NDArray[np.float64],
    ref_seed1: npt.NDArray[np.float64],
    ref_seed2: npt.NDArray[np.float64],
    floor: float = FLOOR,
    *,
    abs_floor: float,
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

    `abs_floor` is REQUIRED and keyword-only, for the reason given on `ABS_FLOOR_COMPOSITION`. It
    is applied to the transferred band exactly as to the same-leg one, so the two stay comparable.
    """
    truth = (seed1 + seed2) / 2.0
    band: npt.NDArray[np.float64] = np.maximum(
        relative_spread(ref_seed1, ref_seed2, floor) * np.abs(truth), abs_floor
    )
    return truth, band


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


BASIS_KINDS: frozenset[str] = frozenset({"level", "ratio"})


def describe_basis(
    leg: str,
    state_year: int,
    window: tuple[int, int],
    ncell: int,
    *,
    npatch: int = 25,
    seeds: Sequence[int] = (1, 2),
    kind: str = "level",
    units: str = "dimensionless fraction",
) -> str:
    """One sentence carrying the reference basis, so a number can be quoted with it.

    Invariant 4: state the basis in the same sentence as the number -- source, leg, years, patch
    count, cell count, and whether it is a level or a ratio. The patch count is in here because a
    tolerance derived at 25 patches largely evaporates at acceptance grade (~125-192).

    `kind` used to be the literal "(level)" whatever the caller scored, so a response statistic --
    a CHANGE between two legs -- was labelled a level. It is now the caller's to state, from
    `BASIS_KINDS`. The defaults reproduce the old sentence byte for byte, so every basis string
    already written into a metrics file is unchanged (pinned in `tests/test_band.py`).
    """
    if kind not in BASIS_KINDS:
        raise ValueError(f"kind must be one of {sorted(BASIS_KINDS)}, got {kind!r}")
    return (
        f"LPJmL-FIT {leg} leg, state at {state_year} from the restart file, climate window "
        f"{window[0]}-{window[1]}, npatch={npatch}, "
        f"truth = mean of seeds {'+'.join(map(str, seeds))}, "
        f"{ncell} tree-bearing cells, {units} ({kind})"
    )


# --------------------------------------------------------------------------------------------
# THE WORST-QUANTITY SCORE ("C1") -- the replacement for the retired emitted-restart statistic.
#
# WHY THE CONJUNCTIVE FRACTION COULD NOT RANK ANYTHING. `band_frac_conjunctive` asks one yes/no
# question per row -- inside the band on all 22 at once? -- and on the pilot's 5,800 perturbed
# targets every null answered "no" on more than 99.5 % of them. Six competitors pinned within 0.004
# of zero cannot be ranked: a shuffled cell tied first and the cell's own forest ranked below
# chance (`docs/decisions/20260915-X-x4-is-not-sealable-*`). The band was not too tight by mistake:
# the model's own two-run spread is measured flat under perturbation (median 0.030), so the 10 %
# floor genuinely binds in ~80 % of cell-quantities, and widening it is forbidden.
#
# WHAT C1 KEEPS. The band, unchanged -- max(10 %, the model's own two-run spread) x |truth|, plus
# the additive floor wherever the scorer uses one -- and the conjunctive logic: a row is only as
# good as its WORST quantity, so no model can buy a score by nailing soil carbon while missing
# every trait. What changes is that the per-row answer is a NUMBER instead of a bit:
#
#     e_row = max over the scored quantities of |pred - truth| / band
#
# e_row <= 1 is exactly "inside the band on every quantity", so the ACCEPTANCE NUMBER is still the
# share of rows with e_row <= 1 (`share_within_band`), quoted with its ceiling. But e_row also says
# HOW FAR outside the band the worst quantity sits -- 1.3 bands and 40 bands are both "fail" to the
# fraction and are very different to a model -- and that is what gives the decision statistic
# power in a regime where almost nothing passes.
#
# THE DECISION STATISTIC, CHOSEN BEFORE ANY ARM WAS SCORED UNDER IT (2026-09-23), NOT TUNED:
#
#     worst_quantity_skill = -log(lower median over rows of e_row)          higher is better
#
# Why the median of the log and not the alternative on the table, mean(-log(max(e, eps))):
#   * it has NO FREE PARAMETER. The mean needs an `eps` for a perfect row (e = 0) and a cap for a
#     missing prediction (e = inf); both are thresholds, and a threshold picked after seeing the
#     values is exactly what this module refuses elsewhere. A median is a rank statistic: 0 and
#     inf are legitimate values that sort to the ends and move it by one position each.
#   * it cannot be bought by a few rows. A mean of logs is decided by its tails, and the tails of a
#     max-over-19 are the near-zero-band cell-quantities; the median is decided by the typical row.
#   * it reads in band units: exp(-skill) IS the median row's worst-quantity error, in bands. And
#     skill >= 0 exactly when at least half the rows are inside the band on every quantity, so its
#     sign ties back to the acceptance number.
# The LOWER median (an actual order statistic, never an average of two) keeps it well defined when
# the middle rows include an infinity, and makes it exactly reproducible.
#
# SCORED ROWS AND MISSING VALUES -- one rule, stated once:
#   * a quantity is scored on a row only where the TRUTH exists. A treeless run has no wood
#     density, so that row is scored on the quantities it has: stems, biomass, leaf area and soil
#     carbon. `band_frac_conjunctive` instead counts such a row as a miss for every arm, even a
#     perfect one -- the one place the two statistics differ, and why `share_within_band` reads
#     slightly higher on a set with treeless targets.
#   * a missing PREDICTION where the truth exists is e = inf, never a pass (the `band_hits` rule).
#   * a band of exactly zero (a relative band around a truth of exactly zero, e.g. no stems) passes
#     only an exact prediction: e = 0 if pred == truth, else inf. Predicting a forest where the
#     truth has none is the collapse event, and it must not be scored as "close".
#   * a row with no scored quantity at all is e = inf -- never credited.
# --------------------------------------------------------------------------------------------

# Constant in every tree-bearing run of both pilot corpora: fine-root conductivity takes ONE value
# (0.02, spread ~1e-18 over 5,620 runs of pilot-v2-constco2) in this configuration, so its three
# quantiles carry nothing to predict and every arm matches them for free. Excluded from C1's max;
# `assert_constant_quantities` refuses a table on which they vary, so the exclusion cannot go stale
# silently.
CONSTANT_ON_PILOT: tuple[str, ...] = ("k_root_p10", "k_root_p50", "k_root_p90")

# The 19 quantities C1 takes its maximum over: SCORED_CONJUNCTIVE, in its own order, minus the
# three that do not vary. A NEW tuple -- SCORED_CONJUNCTIVE itself is pinned by sealed experiments.
SCORED_VARYING: tuple[str, ...] = tuple(q for q in SCORED_CONJUNCTIVE if q not in CONSTANT_ON_PILOT)

# The conjunctive set WITH the species mix: the 22, then the seven type shares. A new name, never
# an extension of SCORED_CONJUNCTIVE (whose 22 members are pinned by sealed experiments). Scored
# with a per-quantity floor vector (`abs_floor_vector`): 0 on the 22, ABS_FLOOR_COMPOSITION on the
# shares. The plain 22-quantity number is always reported beside it (`band_frac_with_composition`).
SCORED_WITH_COMPOSITION: tuple[str, ...] = (*SCORED_CONJUNCTIVE, *COMPOSITION_QUANTITIES)


def assert_constant_quantities(
    truth: npt.NDArray[np.float64],
    names: Sequence[str],
    constant: Sequence[str] = CONSTANT_ON_PILOT,
) -> None:
    """Refuse, rather than silently exclude, a quantity that turns out to vary on this table."""
    flat = truth.reshape(-1, truth.shape[-1])
    for q in constant:
        if q not in names:
            continue
        v = flat[:, list(names).index(q)]
        v = v[np.isfinite(v)]
        if not v.size:
            continue
        spread = float(v.max() - v.min())
        if spread > 1e-9 * max(abs(float(v.mean())), 1.0):
            raise ValueError(f"{q} varies on this table (range {spread:g}); it cannot be excluded")


def abs_floor_vector(names: Sequence[str]) -> npt.NDArray[np.float64]:
    """The per-quantity additive floor: ABS_FLOOR_COMPOSITION on `pft_frac_*`, 0.0 on the rest.

    The one sanctioned way to mix units in one band: the floor is measured in STEM SHARES and means
    nothing on soil carbon, so it is attached by NAME, never by position, and never as a default.
    """
    comp = set(COMPOSITION_QUANTITIES)
    return np.array([ABS_FLOOR_COMPOSITION if n in comp else 0.0 for n in names], dtype=np.float64)


def band_from_spread(
    truth: npt.NDArray[np.float64],
    rel_spread: npt.NDArray[np.float64],
    *,
    abs_floor: float | npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """The absolute band from an already-floored relative spread: max(spread * |truth|, abs_floor).

    The same arithmetic `acceptance_band_transferred` applies, factored out so a spread that did
    not come from a second leg -- the same cell under its other climates (`spread_across_climates`)
    -- builds its band bit-identically. `abs_floor` is a scalar or a per-quantity vector
    (`abs_floor_vector`); still required and keyword-only, for the reason on ABS_FLOOR_COMPOSITION.
    """
    band: npt.NDArray[np.float64] = np.maximum(rel_spread * np.abs(truth), abs_floor)
    return band


def spread_across_climates(
    seed1: npt.NDArray[np.float64], seed2: npt.NDArray[np.float64], floor: float = FLOOR
) -> npt.NDArray[np.float64]:
    """A band transferred across the climates of the SAME cell, leaving the scored climate out.

    Inputs are (cells, climates, quantities): two runs of each cell under each climate. For target
    (cell i, climate j) the relative spread is the MEDIAN of |s1 - s2| / |mean| over cell i's OTHER
    climates k != j, then floored: max(floor, that median). Returned in the input's shape.

    WHY THIS AND NOT THE SAME-CLIMATE SPREAD. The same-climate band is circular: it is built from
    the two runs whose mean is the truth, so "predict run 1" sits at exactly half a band and cannot
    fail (`test_one_seed_always_passes_its_own_band_and_that_is_the_circularity`). Leaving the
    scored climate out breaks that circle while keeping everything else about the tolerance local:
    same cell, same quantity, same model, same seed pair.

    WHY THE TRANSFER IS LEGITIMATE. The model's own run-to-run spread does not change under climate
    perturbation -- measured on pilot-v1/pilot-v1-s2, 20 cells x 30 climates: median 0.0301 at the
    perturbed climates vs 0.0310 at the control, 20.4 % above the 10 % floor at both
    (`docs/decisions/20260915-X-the-perturbed-spread-does-not-widen-*`). So a cell's other
    climates estimate the spread at this one.

    WHY THE MEDIAN. A climate that drives a cell nearly treeless puts a near-zero mean in the
    denominator and a relative spread of 1-2 in the sample; a mean over climates would hand that
    to every other climate's band. The median is the typical pair. A climate with a zero mean has
    no relative spread and is skipped; a cell-quantity with none left gets the bare floor, which is
    what `relative_spread` does for a zero mean too.
    """
    if seed1.shape != seed2.shape or seed1.ndim != 3:
        raise ValueError(f"need two (cells, climates, quantities) arrays, got {seed1.shape}")
    mean = (seed1 + seed2) / 2.0
    denom = np.abs(mean)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(denom > 0, np.abs(seed1 - seed2) / denom, np.nan)
    out = np.full_like(raw, floor)
    for j in range(raw.shape[1]):
        others = np.delete(raw, j, axis=1)
        have = np.isfinite(others).any(axis=1)
        # nanmedian warns on an all-NaN slice; those are exactly the slices `have` excludes, so
        # they are filled with a dummy value and then overwritten by the floor.
        med = np.nanmedian(np.where(have[:, None, :], others, 0.0), axis=1)
        out[:, j, :] = np.where(have, np.maximum(floor, med), floor)
    return out


def _ratio_matrix(
    pred: npt.NDArray[np.float64], truth: npt.NDArray[np.float64], band: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """(|pred - truth| / band with the C1 conventions, scored mask, inside-the-band mask).

    The inside mask is `band_hits`' own comparison, |pred - truth| <= band, never `ratio <= 1`: a
    division rounds, and an acceptance number must not move by one ulp at the band's edge.
    """
    scored = np.isfinite(truth)
    with np.errstate(invalid="ignore"):
        diff = np.abs(pred - truth)
    ok_pred = np.isfinite(pred) & np.isfinite(band) & (band >= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(band > 0, diff / band, np.where(diff == 0, 0.0, np.inf))
    ratio = np.where(ok_pred & scored, ratio, np.inf)
    ratio = np.where(scored, ratio, np.nan)
    with np.errstate(invalid="ignore"):
        inside = np.where(scored, ok_pred & (diff <= band), True)
    return ratio, scored, inside


def worst_quantity_error(
    pred: npt.NDArray[np.float64], truth: npt.NDArray[np.float64], band: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """e per row: the largest |pred - truth| / band over the quantities scored on that row.

    Inputs are (rows, quantities); the conventions for missing values and zero bands are in the
    section comment above. 0 means perfect, 1 is the edge of the band, inf is never credited.
    """
    ratio, scored, _ = _ratio_matrix(pred, truth, band)
    e = np.where(scored, ratio, -np.inf).max(axis=1, initial=-np.inf)
    out: npt.NDArray[np.float64] = np.where(scored.any(axis=1), e, np.inf)
    return out


def worst_quantity_skill(e: npt.NDArray[np.float64]) -> float:
    """THE decision statistic: -log(lower median of e). Higher is better; see the section comment.

    +inf when more than half the rows are exact, -inf when more than half are never credited --
    both honest answers, and neither can occur for an arm that predicts anything at all.
    """
    if e.size == 0:
        return float("nan")
    med = float(np.sort(e)[(e.size - 1) // 2])
    if med == 0.0:
        return float("inf")
    return float(-np.log(med))


def score_worst_quantity(
    pred: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    band: npt.NDArray[np.float64],
    names: Sequence[str],
) -> dict[str, object]:
    """Everything C1 reports for one arm: the decision statistic, the acceptance number, and why.

    `binding` counts which quantity sets e on how many rows -- the question a failing arm raises
    first ("which quantity is it always out on?") and the one a conjunctive bit cannot answer.
    """
    if pred.shape != truth.shape or truth.shape != band.shape or truth.shape[-1] != len(names):
        raise ValueError(f"shape mismatch: {pred.shape} {truth.shape} {band.shape}, {len(names)}")
    ratio, scored, inside = _ratio_matrix(pred, truth, band)
    e = worst_quantity_error(pred, truth, band)
    any_scored = scored.any(axis=1)
    rows_inside = inside.all(axis=1) & any_scored
    arg = np.where(scored, ratio, -np.inf).argmax(axis=1)
    binding = {n: int(((arg == i) & any_scored).sum()) for i, n in enumerate(names)}
    quantiles = {
        f"p{p}": float(np.quantile(e, p / 100.0, method="lower")) if e.size else float("nan")
        for p in (10, 25, 50, 75, 90)
    }
    return {
        "worst_quantity_skill": worst_quantity_skill(e),
        "share_within_band": float(rows_inside.mean()) if e.size else float("nan"),
        "n_rows": int(e.size),
        "n_rows_never_credited": int((~np.isfinite(e)).sum()),
        "e_quantiles": quantiles,
        "binding": {n: c for n, c in binding.items() if c},
    }


def ceiling_arm(
    run: npt.NDArray[np.float64],
    other: npt.NDArray[np.float64],
    rel_spread: npt.NDArray[np.float64],
    *,
    abs_floor: float | npt.NDArray[np.float64],
    truth_is: str,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(pred, truth, band) for THE CEILING: one real run of the model, scored as if it were an arm.

    Shared by every scorer, so a ceiling is always computed with the arithmetic its arms use:
    `band_frac_conjunctive(*ceiling_arm(...))`, `score_worst_quantity(*ceiling_arm(...), names)`.

    `truth_is` must be stated, because the two cases bound different things:
      "mean"   truth = (run + other) / 2, the two-run expectation the arms are scored against when a
               second run exists. |run - truth| = |run - other| / 2 has the same mean and
               covariance as a PERFECT expectation-predictor's error against a two-run truth (the
               same distribution when the run-to-run noise is symmetric, e.g. Gaussian; only
               approximately for a skewed quantity such as stems near collapse), so this is,
               approximately, the score a perfect emulator attains -- not merely a bound on it.
      "other"  truth = the other run alone, for a single-seed truth. One run predicting another
               carries both runs' noise, so this is a LOWER bound on the attainable score.

    ⚠ NEITHER IS THE OWNER'S "AS GOOD AS A RERUN" REFERENCE (2026-09-24). That rule compares the
    emulator's pass rate with an INDEPENDENT real run's against the two-run truth. In "mean" the
    run is one of the two the truth averages, so its error variance is half one run's (sigma^2/2);
    an independent third run's is 1.5 sigma^2, and "other" is 2 sigma^2. The rerun reference
    therefore lies between the two modes and needs a third run to be measured -- quote "mean" as
    the perfect-emulator score, never as what a rerun achieves.

    ⚠ `rel_spread` must not come from this same pair at these same rows -- that band is circular
    and the ceiling is 1.0 by arithmetic. The literal mistake (passing `relative_spread(run,
    other)`) is refused here; any other same-pair construction is the caller's to avoid.
    """
    if truth_is not in ("mean", "other"):
        raise ValueError(f"truth_is must be 'mean' or 'other', got {truth_is!r}")
    if rel_spread.shape == run.shape and np.array_equal(
        rel_spread, relative_spread(run, other), equal_nan=True
    ):
        raise ValueError(
            "circular ceiling: the band's spread was built from the scored pair itself"
        )
    truth = (run + other) / 2.0 if truth_is == "mean" else other.copy()
    return run, truth, band_from_spread(truth, rel_spread, abs_floor=abs_floor)


def band_frac_with_composition(
    pred: npt.NDArray[np.float64],
    truth: npt.NDArray[np.float64],
    band: npt.NDArray[np.float64],
    names: Sequence[str],
) -> dict[str, float]:
    """The conjunctive fraction on the 22 AND the species mix, with the plain 22 beside it.

    `names` must contain all of SCORED_WITH_COMPOSITION. Both numbers are over the same rows, so
    the difference between them is exactly what adding the seven type shares costs. The band is
    expected to carry the per-quantity floor (`abs_floor_vector`); the truth's type shares should
    have been through `blank_treeless_composition` first.
    """
    missing = [q for q in SCORED_WITH_COMPOSITION if q not in names]
    if missing:
        raise ValueError(f"names lacks {missing}")
    idx = [list(names).index(q) for q in SCORED_WITH_COMPOSITION]
    idx22 = idx[: len(SCORED_CONJUNCTIVE)]
    return {
        "conjunctive_with_composition": band_frac_conjunctive(
            pred[:, idx], truth[:, idx], band[:, idx]
        ),
        "conjunctive_22": band_frac_conjunctive(pred[:, idx22], truth[:, idx22], band[:, idx22]),
    }


def acceptance_band_with_composition(
    seed1: npt.NDArray[np.float64], seed2: npt.NDArray[np.float64], names: Sequence[str]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """(truth, band) over a mixed set, each quantity carrying ITS OWN additive floor.

    `acceptance_band`'s arithmetic with the floor attached by name (`abs_floor_vector`), so on the
    22 of SCORED_CONJUNCTIVE it is bit-identical to `acceptance_band(..., abs_floor=0.0)` and on the
    type shares to `acceptance_band(..., abs_floor=ABS_FLOOR_COMPOSITION)`.
    """
    truth = (seed1 + seed2) / 2.0
    return truth, band_from_spread(
        truth, relative_spread(seed1, seed2), abs_floor=abs_floor_vector(names)
    )
