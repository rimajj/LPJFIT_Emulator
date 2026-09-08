"""The nulls — every one of them computable from the data alone, with no learner.

WHY THAT MATTERS, AND WHY IT WAS A DESIGN CHOICE RATHER THAN A CONVENIENCE. A pre-registration has
to record the value each null MUST return, derived before the run: a null that silently returned
the wrong thing is otherwise indistinguishable from a null that agreed with you, and that is how
five of the predecessor's headline claims died. But you can only pre-derive a null's value if the
null has no free parameters. So each null here is a deterministic function of the corpus and the
fold assignment:

    training_mean       the mean state over the training folds -- "the average forest"
    nearest_geographic  the state of the geographically nearest TRAINING cell
    nearest_analogue    the state of the climatically nearest TRAINING cell -- space-for-time
    shuffled            the held-out truth, permuted within the fold

`nearest_geographic` replaces the more usual "fit a regression on latitude and longitude". It is a
STRONGER address null -- a spatial nearest neighbour is about the best pure interpolator there is --
and, unlike a regression, its value can be derived before any model exists. A weak null is worse
than no null, so the stronger form is also the more honest one.

Under blocked spatial folds the nearest training cell is necessarily outside the held-out block,
which is the entire point: it measures how much of an apparent per-cell skill is just "the forest
next door", on a sample whose effective size is ~161 independent 15-degree tiles rather than 54,020
cells.

`nearest_analogue` is the space-for-time null and the honest competitor for the warming claim. Its
distance is measured over a FIXED, pre-registered eight-feature climate subset rather than all 90
features, for two reasons: a nearest-neighbour search in 90 standardised dimensions is dominated by
the 78 nearly-redundant monthly columns, and the eight below are the variables a climate analogue is
conventionally defined on -- so the null is the one a reviewer would actually propose.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from vegemu.score import unit_sphere

# The analogue distance's feature set. Pre-registered, so it cannot be tuned after the fact.
ANALOGUE_FEATURES: tuple[str, ...] = (
    "tas_ann",
    "pr_ann",
    "tas_coldest_month",
    "tas_warmest_month",
    "gdd5",
    "pr_seasonality",
    "vpd_ann",
    "aridity",
)


def training_mean(y_train: npt.NDArray[np.float64], n_test: int) -> npt.NDArray[np.float64]:
    """The climatological-mean null: every held-out cell gets the training-fold mean state.

    `nanmean` because a trait median is undefined in a cell with no stems, and those cells must not
    drag the mean to zero -- zero wood density is not "the average forest", it is a missing value.
    """
    mean = np.nanmean(y_train, axis=0)
    return np.repeat(mean[None, :], n_test, axis=0)


def _nearest(
    train_points: npt.NDArray[np.float64],
    test_points: npt.NDArray[np.float64],
    y_train: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    tree = cKDTree(train_points)
    _, idx = tree.query(test_points, k=1)
    return y_train[np.asarray(idx, dtype=np.int64)]


def nearest_geographic(
    lon_train: npt.NDArray[np.float64],
    lat_train: npt.NDArray[np.float64],
    y_train: npt.NDArray[np.float64],
    lon_test: npt.NDArray[np.float64],
    lat_test: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Copy the state of the geographically nearest training cell.

    Distance is Euclidean on the UNIT SPHERE, which is monotone in great-circle distance and has no
    date-line wrap or pole singularity -- a lon/lat plane would make two cells either side of the
    date line the two furthest apart on Earth.
    """
    return _nearest(unit_sphere(lon_train, lat_train), unit_sphere(lon_test, lat_test), y_train)


def nearest_analogue(
    x_train: npt.NDArray[np.float64],
    y_train: npt.NDArray[np.float64],
    x_test: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Copy the state of the climatically nearest training cell. THE space-for-time null.

    Features are standardised by the TRAINING fold's own mean and spread. Using the pooled spread
    would leak the held-out block's distribution into the null, which is a small leak but exactly
    the kind that makes a null look better than it is.
    """
    mu = np.nanmean(x_train, axis=0)
    sd = np.nanstd(x_train, axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return _nearest((x_train - mu) / sd, (x_test - mu) / sd, y_train)


def shuffled(y_test: npt.NDArray[np.float64], seed: int) -> npt.NDArray[np.float64]:
    """The held-out truth, permuted across cells within the fold. The sanity null.

    Rows are permuted whole rather than each column independently: that keeps every marginal
    distribution and every cross-quantity correlation intact and destroys only the cell identity,
    so what it measures is exactly "how often does the right answer land on the wrong cell".
    """
    rng = np.random.default_rng(seed)
    return y_test[rng.permutation(y_test.shape[0])]
