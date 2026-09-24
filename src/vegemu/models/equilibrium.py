"""The climate-only equilibrium map as a model you can save, load and run on any climate.

    from vegemu.models.equilibrium import EquilibriumMap, targets_from_frame
    em = EquilibriumMap().fit(x, targets_from_frame(frame))   # x: (rows, 91) in FEATURES order
    em.save(out_dir, basis={...})
    pred, report = EquilibriumMap.load(out_dir).predict(x_new)   # natural scale, post-processed

WHAT IT IS. `X-20260923-equilibrium-from-climate` asked whether the settled forest can be predicted
from the 30-year climate and the soil alone, at places held out in whole 15-degree tiles, and it
could: 0.607582 of the variance, mean over the 19 scored quantities that vary, against 0.097666 for
copying the climatically nearest training run. That experiment fitted its models inside the scoring
loop and threw them away. This module is the same recipe made persistent, so that a restart can be
synthesised for any cell under any climate without refitting anything.

THE RECIPE IS THE SEALED ONE, EXACTLY, FOR THE 22 SCORED HEADS. One LightGBM regressor per quantity,
with the hyperparameters of `fit_predict_oof` in `scripts/exp_model_pilot_response.py` (`PARAMS`
below is a copy; a test asserts the two are equal). log1p on the four forest-scale quantities, the
trait quantiles as they are, trait targets undefined -- and so dropped from training -- on treeless
rows. Nothing about it was tuned here: changing it would change what the sealed number describes.

    ⚠ `n_jobs` IS NOT A HYPERPARAMETER, BUT IT CAN CHANGE THE ANSWER. The sealed run had one CPU,
    so LightGBM ran single-threaded. With more threads LightGBM may sum histogram gradients in a
    different order and land on different trees, so the default here is one thread per fit and the
    parallelism is across heads (`workers`), where it cannot touch the arithmetic of any one fit.

THE HEADS BEYOND THE SEALED 22, and why each is here. These are NOT covered by the sealed
experiment and no skill number for them is on the record; `scripts/diag_equilibrium_map.py` reports
their out-of-fold skill as a development diagnostic only.

    litterc                 the synthesiser rescales litter carbon to it when it is present
    <trait>_p25, _p75       the state table carries them, and five knots describe a distribution
                            better than three; same transform and treeless rule as p10/p50/p90
    pft_frac_0..6           the share of the cell's stems of each tree type: LEVEL heads, as the
                            composition kill tests never had them (those scored a CHANGE)

POST-PROCESSING, applied by `predict` and never inside the fit, so the raw heads stay exactly the
sealed model's:

    1. forest-scale heads (log1p) are clipped at zero -- expm1 of a slightly negative fit is a
       negative stock, which has no meaning
    2. a row whose predicted stems per patch falls below `treeless_below` is TREELESS: its trait
       quantiles and type shares become NaN, because a trait quantile of no trees is undefined. The
       threshold is set at fit time from the TRAINING rows alone (see `treeless_threshold`)
    3. each trait's predicted quantiles are sorted into order, p10 <= p25 <= p50 <= p75 <= p90.
       Independent heads can cross; the number of rows where they did is reported, not hidden.
       Then each is floored at zero: every trait is a positive quantity, and a negative leaf
       longevity or rooting depth -- which the heads do produce where they extrapolate -- has no
       meaning. The count is reported per head. Zero is the physical floor, not a claim that zero
       is right: the corpus's smallest values are well above it
    4. type shares are clipped at zero and renormalised to sum to one

THE OUT-OF-FOLD INTERFACE. `scripts/fit_equilibrium_map.py` writes `oof_pilot.parquet`, one row per
(cell, climate) of the pilot corpus, every prediction made by a model that never saw that cell:

    cell           int64    global cell index (orderA)
    point          str      the design climate, e.g. "control", "core_t+2_p07"
    tile           int64    the cell's 15-degree block, `vegemu.score.spatial_blocks(lon, lat, 15)`
    fold           int64    the sealed fold, `blocked_spatial_folds(lon, lat, 5, 15, 42)`, 0..4
    lon, lat       float64  identity only -- never a feature
    pred_treeless  bool     post-processing step 2 fired on this row
    pred_<head>    float64  natural scale, post-processed (steps 1-4); NaN only where treeless
    raw_<head>     float64  natural scale, inverse transform only; never NaN. The sealed numbers
                            are computed from these, not from pred_

with `<head>` running over `HEADS`, in that order. The per-leg files `pred_<leg>.parquet` carry
`cell, lon, lat, pred_treeless, pred_<head>...` plus three extrapolation flags, `env_nn_dist`,
`env_nn_dist_analogue` and `env_n_outside`, documented in that script.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import warnings
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import polars as pl
from lightgbm import LGBMRegressor

from vegemu.corpus.climate import CLIMATE_FEATURES
from vegemu.score import SCORED_CONJUNCTIVE, TRAITS_SCORED

Array = npt.NDArray[np.float64]

FORMAT = "vegemu-equilibrium-map/1"

# The five soil columns the sealed experiment joined by cell id from the model's own soil input.
SOIL_FEATURES: tuple[str, ...] = ("soil_code", "soil_awc", "soil_w_avail", "soil_sand", "soil_clay")
FEATURES: tuple[str, ...] = (*CLIMATE_FEATURES, *SOIL_FEATURES)
# Everything the map may ever be given. A subset is allowed (an ablation); anything else is not.
ALLOWED_FEATURES: frozenset[str] = frozenset(FEATURES)

# Never features. The sealed script's set, plus the corpus's own bookkeeping columns: any of these
# would hand the model the place, the perturbation it is meant to infer from the climate, or a
# build-order label.
FORBIDDEN: frozenset[str] = frozenset(
    {"cell", "lon", "lat", "tile", "point", "dtemp_k", "fprec", "sprec", "frad", "fiav"}
    | {"name", "kind", "stage", "seed", "leg", "state_year", "skip"}
)

# THE SEALED HYPERPARAMETERS, copied from `scripts/exp_model_pilot_response.py`. A script cannot be
# imported from the package, so the copy is pinned by `tests/test_equilibrium_model.py` instead.
PARAMS: dict[str, object] = {
    "n_estimators": 600,
    "learning_rate": 0.04,
    "num_leaves": 31,
    "min_child_samples": 40,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.7,
    "reg_lambda": 1.0,
    "verbose": -1,
}

PFT_TYPES = 7
SHARE_HEADS: tuple[str, ...] = tuple(f"pft_frac_{i}" for i in range(PFT_TYPES))
QUANTILE_LEVELS: tuple[int, ...] = (10, 25, 50, 75, 90)
EXTRA_QUANTILE_HEADS: tuple[str, ...] = tuple(f"{t}_p{q}" for t in TRAITS_SCORED for q in (25, 75))
SEALED_HEADS: tuple[str, ...] = SCORED_CONJUNCTIVE
HEADS: tuple[str, ...] = (*SEALED_HEADS, "litterc", *EXTRA_QUANTILE_HEADS, *SHARE_HEADS)

# Fitted on log1p: stocks and counts spanning four orders of magnitude. The sealed four plus litter.
LOG1P_HEADS: frozenset[str] = frozenset({"stems_per_patch", "agb", "lai", "soilc", "litterc"})
# Undefined where there are no trees: every trait quantile, and every type share.
TREED_HEADS: frozenset[str] = frozenset(
    {f"{t}_p{q}" for t in TRAITS_SCORED for q in QUANTILE_LEVELS} | set(SHARE_HEADS)
)

# The sealed rule: a head with fewer usable training rows than this is not fitted. On the pilot
# every head has thousands, so here it is a refusal rather than the sealed script's silent zero.
MIN_TRAIN_ROWS = 50


def check_features(features: Sequence[str]) -> None:
    """Refuse a feature list that could leak the place, the design, the state or CO2.

    ⚠ THE LAST CHECK IS AN ALLOWLIST, AND IT IS THE ONE THAT CARRIES THE WEIGHT. The named refusals
    before it only give a clearer message: on their own they let through 36 of the corpus's state
    and bookkeeping columns -- `stems_total`, `vegc`, `truth_stems_total`, the height bins, the age
    quantiles -- none of which is a head, so none was in `FORBIDDEN | HEADS`. The map is defined on
    the climate and the soil; a column that is neither is refused, whatever it is called.
    """
    leaked = FORBIDDEN & set(features)
    assert not leaked, f"forbidden columns in the feature set: {sorted(leaked)}"
    state = set(HEADS) & set(features)
    assert not state, f"state columns in the feature set: {sorted(state)}"
    assert not any("co2" in f.lower() for f in features), "CO2 is never a feature (invariant 8)"
    foreign = [f for f in features if f not in ALLOWED_FEATURES]
    assert not foreign, f"not a climate or soil feature, so never an input: {foreign}"


check_features(FEATURES)


def forward(head: str, y: Array) -> Array:
    """Natural scale -> the scale the head is fitted on. Identical to the sealed script's."""
    return np.log1p(np.maximum(y, 0.0)) if head in LOG1P_HEADS else y


def inverse(head: str, z: Array) -> Array:
    return np.expm1(z) if head in LOG1P_HEADS else z


def transformed(heads: Sequence[str], y: Array) -> Array:
    return np.stack([forward(h, y[:, j]) for j, h in enumerate(heads)], axis=1)


def natural(heads: Sequence[str], z: Array) -> Array:
    return np.stack([inverse(h, z[:, j]) for j, h in enumerate(heads)], axis=1)


def feature_matrix(frame: pl.DataFrame, features: Sequence[str] = FEATURES) -> Array:
    """The (rows, features) input, selected BY NAME, so no other column of the frame can leak in."""
    check_features(features)
    out: Array = frame.select(list(features)).to_numpy().astype(np.float64)
    return out


def targets_from_frame(frame: pl.DataFrame, heads: Sequence[str] = HEADS) -> Array:
    """(rows, heads) on the natural scale, NaN where the quantity is undefined.

    The sealed rule: a trait quantile at zero stems is undefined whatever the decoder wrote there,
    and so is a type share -- `corpus/state.py` writes 0.0 into every share of a treeless cell,
    which as a level reads "none of the trees are type 3" when there are no trees.
    """
    treeless = frame["stems_total"].to_numpy() <= 0
    y: Array = frame.select(list(heads)).to_numpy().astype(np.float64)
    for j, h in enumerate(heads):
        if h in TREED_HEADS:
            y[treeless, j] = np.nan
    return y


def treeless_threshold(stems_per_patch: Array) -> float:
    """Where "predicted to hold no trees" starts, from the TRAINING targets alone.

    Half-way, on the log1p scale the head is fitted on, between zero and the sparsest tree-bearing
    training row. On pilot-v2-constco2 no tree-bearing run holds fewer than 3.28 stems per patch,
    so the gap between "no trees" and "some trees" is wide and the midpoint (about 1.07) sits in
    empty space rather than cutting through real forests.
    """
    treed = stems_per_patch[np.isfinite(stems_per_patch) & (stems_per_patch > 0)]
    if treed.size == 0:
        return 0.0
    return float(np.expm1(0.5 * np.log1p(float(treed.min()))))


# ------------------------------------------------------------------------------------------------
# The fitting. One task = one head on one set of training rows. Workers are SPAWNED, never forked:
# polars' thread pool and OpenMP both break across a fork, and the failure is a silent hang.
# ------------------------------------------------------------------------------------------------
_SHARED: dict[str, Any] = {}


def _init_worker(x: Array, z: Array, params: dict[str, object], features: tuple[str, ...]) -> None:
    _SHARED.update(x=x, z=z, params=params, features=features)


def _fit_task(
    spec: tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_] | None, int, bool],
) -> tuple[str, Array | None]:
    """Fit head `j` on `train & finite(target)`; return its model text and/or its predictions."""
    train, apply_to, j, keep_model = spec
    x, z = _SHARED["x"], _SHARED["z"]
    ok = train & np.isfinite(z[:, j])
    if int(ok.sum()) < MIN_TRAIN_ROWS:
        raise ValueError(f"head {j}: {int(ok.sum())} usable training rows < {MIN_TRAIN_ROWS}")
    model = LGBMRegressor(**_SHARED["params"])
    # Named so the saved model text is self-describing. Names are metadata only: they touch neither
    # the binning nor the splits, which the sealed-number reproduction on the cluster confirms.
    model.fit(x[ok], z[ok, j], feature_name=list(_SHARED["features"]))
    with warnings.catch_warnings():
        # sklearn's validator objects to an unnamed array after a named fit. Harmless: the columns
        # are FEATURES in order by construction, which `check_features` and the callers assert.
        warnings.filterwarnings("ignore", message="X does not have valid feature names")
        pred = None if apply_to is None else np.asarray(model.predict(x[apply_to]), np.float64)
    text = str(model.booster_.model_to_string()) if keep_model else ""
    return text, pred


Spec = tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_] | None, int, bool]


def _run(
    specs: Sequence[Spec],
    x: Array,
    z: Array,
    *,
    params: dict[str, object],
    features: tuple[str, ...],
    workers: int,
) -> list[tuple[str, Array | None]]:
    if workers <= 1:
        saved = dict(_SHARED)
        try:
            _init_worker(x, z, params, features)
            return [_fit_task(s) for s in specs]
        finally:
            _SHARED.clear()
            _SHARED.update(saved)
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=ctx,
        initializer=_init_worker,
        initargs=(x, z, params, features),
    ) as pool:
        return list(pool.map(_fit_task, specs))


def fit_out_of_fold(
    x: Array,
    y: Array,
    row_folds: npt.NDArray[np.int64],
    *,
    heads: Sequence[str] = HEADS,
    params: dict[str, object] | None = None,
    n_jobs: int = 1,
    workers: int = 1,
    features: Sequence[str] = FEATURES,
) -> Array:
    """Out-of-fold predictions ON THE FITTED SCALE (log1p where a head is logged), shaped like y.

    The sealed construction: each fold is held out once, every head is fitted on the other folds'
    rows where its own target exists, and ALL of the held-out rows are predicted -- treeless ones
    included, because the scorer decides which rows count, not the fit. Returned on the fitted scale
    because that is where the sealed skill is computed; `natural` maps it back.
    """
    heads = tuple(heads)
    check_features(features)
    z = transformed(heads, y)
    p = {**(params if params is not None else PARAMS), "n_jobs": n_jobs}
    specs: list[Spec] = []
    for f in np.unique(row_folds):
        test: npt.NDArray[np.bool_] = np.asarray(row_folds == f)
        specs += [(~test, test, j, False) for j in range(len(heads))]
    results = _run(specs, x, z, params=p, features=tuple(features), workers=workers)
    out = np.full_like(z, np.nan)
    for (_, held_out, j, _), (_, pred) in zip(specs, results, strict=True):
        assert held_out is not None
        assert pred is not None
        out[held_out, j] = pred
    return out


@dataclass
class PostReport:
    """What post-processing changed, so none of it is silent."""

    rows: int = 0
    treeless_rows: int = 0
    negative_clipped: dict[str, int] = field(default_factory=dict)
    crossed_3_knots: dict[str, int] = field(default_factory=dict)
    crossed_5_knots: dict[str, int] = field(default_factory=dict)
    trait_negative_clipped: dict[str, int] = field(default_factory=dict)
    share_negative_clipped: int = 0
    share_sum_raw: dict[str, float] = field(default_factory=dict)
    share_all_zero_rows: int = 0

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


def postprocess(
    raw: Array, heads: Sequence[str], treeless_below: float
) -> tuple[Array, PostReport]:
    """Natural-scale raw head outputs -> the deployable prediction. See the module docstring."""
    heads = tuple(heads)
    col = {h: j for j, h in enumerate(heads)}
    out = raw.copy()
    rep = PostReport(rows=int(raw.shape[0]))

    for h in heads:
        if h in LOG1P_HEADS:
            neg = out[:, col[h]] < 0
            rep.negative_clipped[h] = int(neg.sum())
            out[neg, col[h]] = 0.0

    treeless = (
        out[:, col["stems_per_patch"]] < treeless_below
        if "stems_per_patch" in col
        else np.zeros(out.shape[0], dtype=bool)
    )
    rep.treeless_rows = int(treeless.sum())
    for h in heads:
        if h in TREED_HEADS:
            out[treeless, col[h]] = np.nan

    for t in TRAITS_SCORED:
        knots = [col[f"{t}_p{q}"] for q in QUANTILE_LEVELS if f"{t}_p{q}" in col]
        if len(knots) < 2:
            continue
        block = out[:, knots]
        live = np.isfinite(block).all(axis=1)
        three = [col[f"{t}_p{q}"] for q in (10, 50, 90) if f"{t}_p{q}" in col]
        if len(three) >= 2:
            b3 = out[:, three]
            rep.crossed_3_knots[t] = int((live & (np.diff(b3, axis=1) < 0).any(axis=1)).sum())
        rep.crossed_5_knots[t] = int((live & (np.diff(block, axis=1) < 0).any(axis=1)).sum())
        block[live] = np.sort(block[live], axis=1)
        out[:, knots] = block

    # Step 3, second half: every trait here is a strictly positive physical quantity, and additive
    # boosting overshoots below zero where it extrapolates -- leaf longevity p10 in 427 of the
    # 67,420 historical cells of equimap-v1, rooting depth down to -84 under ssp126. Floored AFTER
    # the crossings are counted, so those counts still describe the heads, and after sorting, which
    # a floor at zero cannot undo (it is monotone). Covers single-knot traits too, which the sort
    # loop skips.
    for h in heads:
        if h in TREED_HEADS and h not in SHARE_HEADS:
            neg = out[:, col[h]] < 0  # NaN compares False, so treeless rows stay NaN
            rep.trait_negative_clipped[h] = int(neg.sum())
            out[neg, col[h]] = 0.0

    shares = [col[h] for h in SHARE_HEADS if h in col]
    if shares:
        s = out[:, shares]
        live_s: npt.NDArray[np.bool_] = np.asarray(np.isfinite(s).all(axis=1))
        sums = s[live_s].sum(axis=1)
        if sums.size:
            rep.share_sum_raw = {
                "min": float(sums.min()),
                "median": float(np.median(sums)),
                "max": float(sums.max()),
            }
        rep.share_negative_clipped = int((s[live_s] < 0).sum())
        s = np.where(live_s[:, None], np.maximum(s, 0.0), s)
        total = s.sum(axis=1)
        dead = live_s & (total <= 0)
        rep.share_all_zero_rows = int(dead.sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            s = np.where((live_s & ~dead)[:, None], s / total[:, None], s)
        s[dead] = np.nan
        out[:, shares] = s
    return out, rep


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _text_features(model_text: str) -> list[str]:
    """The feature names a LightGBM model text was fitted on, in order, from its header."""
    for line in model_text.splitlines():
        if line.startswith("feature_names="):
            return line.removeprefix("feature_names=").split(" ")
        if line.startswith("Tree="):
            break
    return []


def feature_stats(x: Array, features: Sequence[str]) -> dict[str, dict[str, float]]:
    """Per-feature training range and scale: the envelope inside which a prediction interpolates."""
    out: dict[str, dict[str, float]] = {}
    for j, f in enumerate(features):
        v = x[np.isfinite(x[:, j]), j]
        out[f] = {
            "min": float(v.min()) if v.size else float("nan"),
            "max": float(v.max()) if v.size else float("nan"),
            "mean": float(v.mean()) if v.size else float("nan"),
            "sd": float(v.std()) if v.size else float("nan"),
            "n_missing": int(x.shape[0] - v.size),
        }
    return out


@dataclass
class EquilibriumMap:
    """One LightGBM booster per head, fitted on every training row, applicable to any climate."""

    heads: tuple[str, ...] = HEADS
    features: tuple[str, ...] = FEATURES
    params: dict[str, object] = field(default_factory=lambda: dict(PARAMS))
    n_jobs: int = 1
    treeless_below: float = float("nan")
    models: dict[str, str] = field(default_factory=dict)  # head -> LightGBM model text
    stats: dict[str, dict[str, float]] = field(default_factory=dict)
    n_train: int = 0
    text_roundtrip_max_abs: float = float("nan")
    # Threads for PREDICTION only. A prediction is a per-row tree walk, so the thread count cannot
    # change it; the fit's thread count is `n_jobs`, which can.
    predict_threads: int = 1
    _boosters: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_features(self.features)
        unknown = [h for h in self.heads if h not in set(HEADS)]
        assert not unknown, f"no transform or support rule is defined for heads {unknown}"

    def fit(self, x: Array, y: Array, *, workers: int = 1) -> EquilibriumMap:
        """`y` is natural-scale, (rows, heads), NaN where undefined (see `targets_from_frame`)."""
        assert x.shape[1] == len(self.features), "x columns must be FEATURES, in order"
        assert y.shape == (x.shape[0], len(self.heads)), "y must be (rows, heads)"
        z = transformed(self.heads, y)
        p = {**self.params, "n_jobs": self.n_jobs}
        every = np.ones(x.shape[0], dtype=bool)
        specs: list[Spec] = [(every, every, j, True) for j in range(len(self.heads))]
        results = _run(specs, x, z, params=p, features=self.features, workers=workers)
        self.models = {h: text for h, (text, _) in zip(self.heads, results, strict=True)}
        self._boosters = {}
        if "stems_per_patch" in self.heads:
            self.treeless_below = treeless_threshold(y[:, self.heads.index("stems_per_patch")])
        self.stats = feature_stats(x, self.features)
        self.n_train = int(x.shape[0])
        # The model text must BE the model. Asserted rather than assumed: the in-memory fit's own
        # predictions on its training rows against the booster parsed back from its text.
        parsed = self.predict_fitted_scale(x)
        in_memory = np.stack([pred for _, pred in results if pred is not None], axis=1)
        self.text_roundtrip_max_abs = float(np.max(np.abs(parsed - in_memory)))
        if self.text_roundtrip_max_abs != 0.0:
            raise AssertionError(
                f"model text does not reproduce the fit: max |diff| {self.text_roundtrip_max_abs}"
            )
        return self

    def _booster(self, head: str) -> Any:
        # Every prediction goes through a booster parsed from the model TEXT, never through the
        # in-memory fit, so a freshly fitted map and a loaded one run literally the same code on
        # literally the same bytes.
        if head not in self._boosters:
            self._boosters[head] = lgb.Booster(model_str=self.models[head])
        return self._boosters[head]

    def predict_fitted_scale(self, x: Array) -> Array:
        assert x.shape[1] == len(self.features), "x columns must be FEATURES, in order"
        out = np.empty((x.shape[0], len(self.heads)), dtype=np.float64)
        for j, h in enumerate(self.heads):
            pred = self._booster(h).predict(x, num_threads=self.predict_threads)
            out[:, j] = np.asarray(pred, dtype=np.float64)
        return out

    def predict_raw(self, x: Array) -> Array:
        """Natural scale, inverse transform only: what the heads say before post-processing."""
        return natural(self.heads, self.predict_fitted_scale(x))

    def predict(self, x: Array) -> tuple[Array, PostReport]:
        return postprocess(self.predict_raw(x), self.heads, self.treeless_below)

    def predict_frame(self, frame: pl.DataFrame) -> tuple[Array, PostReport]:
        return self.predict(feature_matrix(frame, self.features))

    def save(self, out_dir: Path, *, basis: dict[str, object]) -> Path:
        """Model text per head plus `manifest.json`. Returns the manifest's path."""
        assert self.models, "fit before save"
        out_dir = Path(out_dir)
        (out_dir / "heads").mkdir(parents=True, exist_ok=True)
        heads = []
        for h in self.heads:
            rel = f"heads/{h}.txt"
            (out_dir / rel).write_text(self.models[h], encoding="utf-8")
            heads.append(
                {
                    "name": h,
                    "transform": "log1p" if h in LOG1P_HEADS else "identity",
                    "support": "tree-bearing rows" if h in TREED_HEADS else "all rows",
                    "sealed": h in SEALED_HEADS,
                    "file": rel,
                    "sha256": _sha256(out_dir / rel),
                }
            )
        manifest = {
            "format": FORMAT,
            "features": list(self.features),
            "heads": heads,
            "params": self.params,
            "n_jobs": self.n_jobs,
            "treeless_below_stems_per_patch": self.treeless_below,
            "n_train_rows": self.n_train,
            "text_roundtrip_max_abs": self.text_roundtrip_max_abs,
            "feature_stats": self.stats,
            "postprocess": [
                "log1p heads clipped at 0",
                "stems_per_patch < treeless_below -> trait quantiles and type shares NaN",
                "each trait's p10..p90 sorted into order, then floored at 0",
                "type shares clipped at 0 and renormalised to sum 1",
            ],
            "lightgbm_version": lgb.__version__,
            "basis": basis,
        }
        path = out_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, in_dir: Path) -> EquilibriumMap:
        """Read a saved map, refusing any head file whose bytes differ from the manifest's hash."""
        in_dir = Path(in_dir)
        manifest = json.loads((in_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != FORMAT:
            raise ValueError(f"not a {FORMAT} manifest: {manifest.get('format')!r}")
        features = tuple(manifest["features"])
        models = {}
        for head in manifest["heads"]:
            p = in_dir / head["file"]
            if _sha256(p) != head["sha256"]:
                raise ValueError(f"{p} does not match the manifest's sha256; refusing to load")
            models[head["name"]] = p.read_text(encoding="utf-8")
            # The hash covers the head files, not the manifest, and prediction takes a plain array:
            # a manifest whose feature list were reordered would feed every column to the wrong
            # split with no error. Each head's own text names the order it was fitted on.
            fitted_on = _text_features(models[head["name"]])
            if fitted_on != list(features):
                raise ValueError(
                    f"{p} was fitted on a different feature order than the manifest lists; "
                    "refusing to load"
                )
        return cls(
            heads=tuple(h["name"] for h in manifest["heads"]),
            features=features,
            params=dict(manifest["params"]),
            n_jobs=int(manifest["n_jobs"]),
            treeless_below=float(manifest["treeless_below_stems_per_patch"]),
            models=models,
            stats=manifest["feature_stats"],
            n_train=int(manifest["n_train_rows"]),
            text_roundtrip_max_abs=float(manifest["text_roundtrip_max_abs"]),
        )
