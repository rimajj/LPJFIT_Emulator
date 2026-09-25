"""The cell rule of the constant-CO2 equilibrium product: every cell's restart at model year 1699.

    scripts/synth_global.py run --cell-rule vegemu.models.spinup_rule:SpinupRule \\
        --template <restart_1999> --predictions <pred_1901_1930_heldout.parquet> ...

WHAT THE PRODUCT IS (owner, 2026-09-24: "make the emulator work for the spinup with constant co2").
The target is the stored global spin-up at the end of its constant-CO2 stretch, model year 1699,
where CO2 is still the 276.59 ppm clamp and the climate is 700 shuffled draws of 1901-1930. That
run wrote a restart only at 1999, after the CO2 ramp, so the file this rule helps write is the
first restart of the 1699 state that has ever existed. The template of each cell is still its own
`restart_1999` record (`synth_global.py`'s design), and every field the rule can DERIVE for 1699
instead of copying from 1999 is derived:

    type_shares     the equilibrium map's predicted stem shares `pft_frac_0..6` for the cell's
                    1901-1930 climate (held-out per fold); a cell whose prediction has none, or
                    whose predicted mix sits entirely on types the climate rule removes, falls back
                    to the template's own mix restricted to the allowed types (`shares_fallback`)
    allowed_types   the model's own survive()/establish()/temperature-stress limits
                    (`climbuf.bioclimatic_verdict`) under the replayed 1699 buffer, over the whole
                    700-year replay, with the pilot's thresholds (`scripts/synth_pilot.py`)
    climbuf         `climbuf.climate_buffer_from_forcing` on the cell's own 1901-1930 forcing, for
                    the STORED run's protocol (`climbuf.STORED_SPINUP`) stopped at 1699: 700 draws,
                    all shuffled. `mpet20` needs an albedo: the template's effective albedo, solved
                    from its own 1999 buffer against its own 1901-1999 forcing under the 1999
                    protocol, exactly as the pilot's synth stream solved its control's
    rescale_litter  on, rule "soilc": the template's litter times predicted / template soil carbon
                    (the rule the pilot's bank stage chose, `synth_pilot.LITTER_RULE`)
    stems_per_patch OPTIONAL, `match_vegc` (off by default, and off the output is unchanged): the
                    cell's total VegC is pinned to `prediction["vegc_target"]` (gC/m2 of cell, the
                    model's own `VegC` sum, `corpus.vegc.cell_vegc`) by rescaling the stem count
                    and re-synthesising, see `match_vegc`

WHAT STAYS 1999 AND IS DISCLOSED, NOT HIDDEN. The restart HEADER (`synth_global` copies it, and its
`verify` requires it): its year reads 1999 and its global RNG state is the one after 901 draws, not
700, so a continuation run from this file draws the same 30 years as one from `restart_1999` --
which is what makes the two continuation arms a paired comparison. `aetp_mean` (a vegetation flux,
read only by nitrogen fixation, which is off), the soil water/ice/enthalpy block, and every cell
`synth_global` passes through (no stem in the template, or no prediction) are the 1999 record.

The forcing is read ONCE per block (`read_block_forcing`), four variables, the block's cells, from
`config/paths.yaml: inputs.historical` -- the files the stored run itself read.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vegemu.binfmt.clm import ClmReader, read_grid
from vegemu.binfmt.restart import Layout, RestartReader, trees_of
from vegemu.corpus.state import summarise_cell
from vegemu.corpus.vegc import cell_vegc
from vegemu.models import climbuf as cb
from vegemu.models.synth import (
    MATCH_TRAITS,
    NTREE_TYPES,
    DonorPool,
    SynthReport,
    synthesise_cell,
)
from vegemu.paths import path

Array = npt.NDArray[np.float64]

STOP_YEAR = 1699  # the last model year whose CO2 is the 276.59 ppm clamp (getco2.c:47)
LITTER_RULE = "soilc"
# `scripts/synth_pilot.py`'s admission thresholds: a type is allowed if survive() holds at the end
# and it could establish in at least one replayed year, whatever its temperature-stress mortality.
ADMIT_MIN_ESTABLISH_FRAC = 1e-9
ADMIT_MAX_MORT_TEMP = 1.0
SHARE_COLUMNS: tuple[str, ...] = tuple(f"pft_frac_{i}" for i in range(NTREE_TYPES))
# The config keys of the four inputs the buffer reads, and their `inputs.historical` entries.
FORCING_KEYS: dict[str, str] = {"temp": "tas", "prec": "pr", "swdown": "rsds", "lwnet": "lwnet"}
# Set by the rule itself; a `--synth-kwargs` key may not override them.
RULE_OWNED = frozenset({"type_shares", "allowed_types", "climbuf", "rescale_litter"})
_FARM_OWNED = frozenset(
    {"template", "prediction", "pool", "layout", "cell", "template_cell", "seed", "match_traits"}
)


# --------------------------------------------------------------------------------------------
# The block's forcing, read once.
# --------------------------------------------------------------------------------------------
@dataclass
class BlockForcing:
    """Daily forcing of a contiguous run of cells, (ncell, nyear, 365) per variable."""

    first_cell: int
    firstyear: int
    temp: Array
    prec: Array
    swdown: Array
    lwnet: Array
    lat: Array

    @property
    def ncell(self) -> int:
        return int(self.temp.shape[0])

    @property
    def nyear(self) -> int:
        return int(self.temp.shape[1])

    def forcing(self, cell: int, nyear: int | None = None) -> cb.Forcing:
        """One cell's `Forcing`, its first `nyear` years (all by default)."""
        k = cell - self.first_cell
        if not 0 <= k < self.ncell:
            raise IndexError(f"cell {cell} is not in this block [{self.first_cell}, +{self.ncell})")
        n = self.nyear if nyear is None else int(nyear)
        if n > self.nyear:
            raise ValueError(f"{n} years asked, the block holds {self.nyear}")
        return cb.Forcing(
            temp=self.temp[k, :n],
            prec=self.prec[k, :n],
            swdown=self.swdown[k, :n],
            lwnet=self.lwnet[k, :n],
            lat=float(self.lat[k]),
            firstyear=self.firstyear,
        )


def forcing_files() -> dict[str, Path]:
    """The four global forcing files the stored spin-up read, by the model's config key."""
    return {k: path(f"inputs.historical.{v}") for k, v in FORCING_KEYS.items()}


def read_block_forcing(
    first_cell: int,
    ncell: int,
    first_year: int,
    last_year: int,
    *,
    files: dict[str, Path] | None = None,
    grid: Path | None = None,
) -> BlockForcing:
    """Read the block's four forcing variables once, and each cell's latitude from the grid."""
    files = forcing_files() if files is None else files
    data: dict[str, Array] = {}
    for key in FORCING_KEYS:
        with ClmReader(files[key]) as reader:
            if reader.header.nbands != cb.NDAYYEAR:
                raise ValueError(f"{files[key]}: {reader.header.nbands} bands, expected daily")
            data[key] = reader.block_years(first_cell, ncell, first_year, last_year)
    coords = read_grid(path("inputs.coord") if grid is None else grid)
    return BlockForcing(
        first_cell=first_cell,
        firstyear=first_year,
        temp=data["temp"],
        prec=data["prec"],
        swdown=data["swdown"],
        lwnet=data["lwnet"],
        lat=coords[first_cell : first_cell + ncell, 1].astype(np.float64),
    )


# --------------------------------------------------------------------------------------------
# The per-cell derivations, each a pure function so the tests can drive them without a farm.
# --------------------------------------------------------------------------------------------
@dataclass
class CellClimate:
    climbuf: dict[str, Any]
    allowed: tuple[int, ...]
    verdict: cb.BioclimVerdict
    albedo: Array
    seed_after: tuple[int, int, int]


def cell_climate(
    template_climbuf: dict[str, Any],
    stand_frac: float,
    f_template: cb.Forcing,
    f_target: cb.Forcing,
    *,
    template_protocol: cb.SpinupProtocol,
    target_protocol: cb.SpinupProtocol,
    min_establish_frac: float = ADMIT_MIN_ESTABLISH_FRAC,
    max_mort_temp: float = ADMIT_MAX_MORT_TEMP,
) -> CellClimate:
    """The target buffer and the allowed types, from the template's own albedo."""
    albedo = cb.effective_albedo(
        template_climbuf, f_template, protocol=template_protocol, stand_frac=stand_frac
    )
    buf, trace = cb.climate_buffer_from_forcing(
        f_target,
        protocol=target_protocol,
        albedo=albedo,
        aetp_mean=float(template_climbuf["scalars"][3]),
        stand_frac=stand_frac,
    )
    verdict = cb.bioclimatic_verdict(f_target, trace)
    allowed = verdict.admissible(min_establish_frac=min_establish_frac, max_mort_temp=max_mort_temp)
    return CellClimate(buf, allowed, verdict, albedo, trace.seed_after)


def litter_target(
    rule: str, template_state: dict[str, float], prediction: dict[str, float]
) -> float | None:
    """The litter carbon to rescale to, or None to keep the template's (`synth_pilot` rule).

    `rule` names the quantity whose predicted / template ratio scales the template's litter, or
    "predicted" (the map's own litter head), or "none".
    """
    if rule == "none":
        return None
    if rule == "predicted":
        want = prediction.get("litterc")
        return None if want is None or not math.isfinite(want) else float(want)
    base, want = template_state.get(rule), prediction.get(rule)
    if base is None or want is None or not math.isfinite(want) or not base > 0:
        return None
    return float(template_state["litterc"] * want / base)


def predicted_shares(
    prediction: dict[str, float], allowed: tuple[int, ...]
) -> tuple[Array | None, str]:
    """The seven predicted shares, or None (the template's mix, restricted) and why."""
    vals = [prediction.get(c, math.nan) for c in SHARE_COLUMNS]
    if not all(math.isfinite(v) for v in vals):
        return None, "no-prediction"
    shares = np.asarray(vals, dtype=np.float64)
    keep = np.zeros(NTREE_TYPES, dtype=bool)
    keep[list(allowed)] = True
    if not float(np.where(keep & (shares > 0), shares, 0.0).sum()) > 0:
        return None, "all-on-removed-types"
    return shares, "prediction"


@dataclass
class SpinupReport(SynthReport):
    """`SynthReport` plus what this rule decided. Scalars only, so `synth_global`'s per-cell
    table picks every field up (as `rep_<name>`) without that file changing."""

    allowed: str = ""
    shares_from: str = ""
    template_types: str = ""
    template_types_removed: int = 0
    template_stems_removed_type: int = 0
    tmin20: float = math.nan
    tmax20: float = math.nan
    albedo_mean: float = math.nan
    climbuf_seed_after: str = ""
    # `match_vegc` only; NaN / 0 / "" when it is off or the cell is not rescaled.
    vegc_target: float = math.nan
    vegc_first: float = math.nan
    vegc_written: float = math.nan
    vegc_passes: int = 0
    vegc_stems_factor: float = math.nan
    vegc_why: str = ""


@dataclass
class VegcMatch:
    target: float = math.nan
    first: float = math.nan
    written: float = math.nan
    passes: int = 0
    stems_factor: float = math.nan
    why: str = ""


def match_vegc(
    synth: Any,
    pred: dict[str, float],
    *,
    passes: int,
    tol: float,
    max_factor: float,
) -> tuple[dict[str, Any], SynthReport, VegcMatch]:
    """Synthesise, then rescale `stems_per_patch` until the cell's VegC is `pred["vegc_target"]`.

    WHY THE STEM COUNT. The equilibrium map this rule was built for predicts no carbon: a cell's
    carbon falls out of how many stems are placed and at what sizes, and that product came out
    20 % low globally (year 0 of `restart_1699_emulated.lpj`: 0.80 of the stored equilibrium's
    total), where a dedicated carbon map is within 2 %. The sizes are the map's (height and
    wood-density quantiles), so the count is the one free lever; a stand's carbon is close to
    linear in it because the placement draws the same size quantiles whatever the count.

    `synth(pred) -> (rec, rep)` is one synthesis. Grass carbon is the template's and does not move,
    so the trees are asked for `target - grass`; at or below the grass, the cell gets no tree. At
    most `passes` re-syntheses, stopping inside `tol` (relative, on the total); the stem count never
    exceeds `max_factor` times the map's, so a cell whose placed stems carry almost no carbon is
    reported (`why`), not filled with thousands of saplings. A cell the map calls treeless
    (`stems_per_patch` 0) is left treeless.
    """
    rec, rep = synth(pred)
    v = cell_vegc(rec)
    target = pred.get("vegc_target", math.nan)
    m = VegcMatch(target=target, first=v["total"], written=v["total"])
    spp0 = float(pred["stems_per_patch"])
    if not math.isfinite(target):
        m.why = "no-target"
        return rec, rep, m
    if not spp0 > 0:
        m.why = "treeless-prediction"
        return rec, rep, m
    spp = spp0
    m.why = "passes-exhausted"
    for _ in range(passes):
        if abs(v["total"] - target) <= tol * max(target, 1.0):
            m.why = "matched"
            break
        tree_want = target - v["grass"]
        if tree_want <= 0:
            spp = 0.0
        elif v["tree"] > 0:
            spp = min(spp * tree_want / v["tree"], max_factor * spp0)
        else:
            m.why = "no-tree-carbon"
            break
        rec, rep = synth({**pred, "stems_per_patch": spp})
        v = cell_vegc(rec)
        m.passes += 1
        if spp == 0.0:
            m.why = "below-grass"
            break
        if spp >= max_factor * spp0:
            m.why = "capped"
            break
    else:
        if abs(v["total"] - target) <= tol * max(target, 1.0):
            m.why = "matched"
    m.written = v["total"]
    m.stems_factor = spp / spp0
    return rec, rep, m


def _extend(rep: SynthReport, **extra: Any) -> SpinupReport:
    base = {f.name: getattr(rep, f.name) for f in fields(SynthReport)}
    return SpinupReport(**base, **extra)


class SpinupRule:
    """`synth_global.py`'s `CellSynth` for the 1699 product. Built once per block.

    Options (all recorded by `describe`, and part of the plan through `--synth-kwargs`):
      stop_year           the model year whose buffer is written (1699)
      litter_rule         "soilc" (default), "predicted" or "none"
      min_establish_frac, max_mort_temp   the admission thresholds (the pilot's)
      match_vegc          pin each cell's VegC to `pred_vegc_target` (off; `match_vegc`), with
                          vegc_passes (3), vegc_tol (0.02) and vegc_max_factor (4.0)
    Anything else in `--synth-kwargs` is passed to `synthesise_cell`, which must accept it.
    """

    def __init__(
        self,
        template: Path,
        first_cell: int,
        ncell: int,
        *,
        donors: Any,
        match_traits: tuple[str, ...] = MATCH_TRAITS,
        stop_year: int = STOP_YEAR,
        litter_rule: str = LITTER_RULE,
        min_establish_frac: float = ADMIT_MIN_ESTABLISH_FRAC,
        max_mort_temp: float = ADMIT_MAX_MORT_TEMP,
        match_vegc: bool = False,
        vegc_passes: int = 3,
        vegc_tol: float = 0.02,
        vegc_max_factor: float = 4.0,
        forcing: BlockForcing | None = None,
        **synth_kwargs: Any,
    ) -> None:
        accepted = set(inspect.signature(synthesise_cell).parameters)
        bad = sorted(
            (set(synth_kwargs) - accepted) | (set(synth_kwargs) & (RULE_OWNED | _FARM_OWNED))
        )
        if bad:
            raise ValueError(f"spinup rule: synthesise_cell does not take (or the rule sets) {bad}")
        if litter_rule not in ("soilc", "vegc", "agb", "lai", "predicted", "none"):
            raise ValueError(f"unknown litter rule {litter_rule!r}")
        self.template_path = Path(template)
        self.match_traits = tuple(match_traits)
        self.litter_rule = litter_rule
        self.min_establish_frac = float(min_establish_frac)
        self.max_mort_temp = float(max_mort_temp)
        if vegc_passes < 1 or not 0 < vegc_tol < 1 or not vegc_max_factor >= 1:
            raise ValueError(
                f"match_vegc needs passes >= 1, 0 < tol < 1, max_factor >= 1; got "
                f"{vegc_passes}, {vegc_tol}, {vegc_max_factor}"
            )
        self.match_vegc = bool(match_vegc)
        self.vegc_passes = int(vegc_passes)
        self.vegc_tol = float(vegc_tol)
        self.vegc_max_factor = float(vegc_max_factor)
        self.synth_kwargs = dict(synth_kwargs)
        self.template_protocol = cb.STORED_SPINUP
        self.target_protocol = cb.STORED_SPINUP.until(int(stop_year))
        # THE TEMPLATE MUST BE WHAT THE 1999 PROTOCOL WROTE, or the albedo solve inverts the wrong
        # year weights. Its header proves it for free: the year, and the RNG state after the draws.
        head = RestartReader(self.template_path)
        want_seed = self.template_protocol.schedule()[1]
        if head.generic.firstyear != self.template_protocol.lastyear or tuple(
            head.restart.seed
        ) != tuple(want_seed):
            raise ValueError(
                f"{template}: year {head.generic.firstyear}, seed {tuple(head.restart.seed)}; the "
                f"stored spin-up's protocol writes year {self.template_protocol.lastyear} with "
                f"seed {want_seed}. This rule is for that run's restart only."
            )
        self.n_template_years = self.template_protocol.years_needed()
        self.n_target_years = max(
            self.target_protocol.years_needed(), self.target_protocol.nspinyear
        )
        nyear = max(self.n_template_years, self.n_target_years)
        first = self.template_protocol.climate_firstyear
        self.forcing = (
            read_block_forcing(first_cell, ncell, first, first + nyear - 1)
            if forcing is None
            else forcing
        )
        if self.forcing.firstyear != first or self.forcing.nyear < nyear:
            raise ValueError(
                f"block forcing covers {self.forcing.firstyear}+{self.forcing.nyear} years; the "
                f"rule needs {first}+{nyear}"
            )

    def __call__(
        self,
        template: dict[str, Any],
        prediction: dict[str, float],
        pool: DonorPool,
        layout: Layout,
        *,
        cell: int,
        seed: int,
    ) -> tuple[dict[str, Any], SynthReport]:
        stand_frac = float(template["stands"][0]["frac"])
        clim = cell_climate(
            template["climbuf"],
            stand_frac,
            self.forcing.forcing(cell, self.n_template_years),
            self.forcing.forcing(cell, self.n_target_years),
            template_protocol=self.template_protocol,
            target_protocol=self.target_protocol,
            min_establish_frac=self.min_establish_frac,
            max_mort_temp=self.max_mort_temp,
        )
        shares, shares_from = predicted_shares(prediction, clim.allowed)
        pred = {k: v for k, v in prediction.items() if k not in ("litterc", "vegc_target")}
        state = summarise_cell(template, cell, layout)
        lit = litter_target(self.litter_rule, state, prediction)
        if lit is not None:
            pred["litterc"] = lit

        def synth(p: dict[str, float]) -> tuple[dict[str, Any], SynthReport]:
            return synthesise_cell(
                template,
                p,
                pool,
                layout,
                cell=cell,
                template_cell=cell,
                seed=seed,
                match_traits=self.match_traits,
                type_shares=shares,
                allowed_types=clim.allowed,
                climbuf=clim.climbuf,
                rescale_litter=lit is not None,
                **self.synth_kwargs,
            )

        if self.match_vegc:
            want = {**pred, "vegc_target": prediction.get("vegc_target", math.nan)}
            rec, rep, vm = match_vegc(
                synth,
                want,
                passes=self.vegc_passes,
                tol=self.vegc_tol,
                max_factor=self.vegc_max_factor,
            )
        else:
            (rec, rep), vm = synth(pred), VegcMatch()
        ids = np.concatenate(
            [np.asarray(trees_of(p["pftlist"])["id"]) for p in template["stands"][0]["patches"]]
        ).astype(np.int64)
        held = sorted({int(t) for t in ids})
        removed = [t for t in held if t not in clim.allowed]
        return rec, _extend(
            rep,
            allowed=",".join(map(str, clim.allowed)),
            shares_from=shares_from,
            template_types=",".join(map(str, held)),
            template_types_removed=len(removed),
            template_stems_removed_type=int(np.isin(ids, removed).sum()) if removed else 0,
            tmin20=clim.verdict.temp_min20,
            tmax20=clim.verdict.temp_max20,
            albedo_mean=float(np.mean(clim.albedo)),
            climbuf_seed_after=",".join(map(str, clim.seed_after)),
            **{f"vegc_{f.name}": getattr(vm, f.name) for f in fields(VegcMatch)},
        )

    def describe(self) -> dict[str, Any]:
        return {
            "rule": "vegemu.models.spinup_rule:SpinupRule",
            "template_protocol": vars_of(self.template_protocol),
            "target_protocol": vars_of(self.target_protocol),
            "target_seed_after": list(self.target_protocol.schedule()[1]),
            "forcing_years": [
                self.forcing.firstyear,
                self.forcing.firstyear + self.forcing.nyear - 1,
            ],
            "litter_rule": self.litter_rule,
            "min_establish_frac": self.min_establish_frac,
            "max_mort_temp": self.max_mort_temp,
            # Off, the description is what it was before the option existed, so is a plan's.
            **(
                {
                    "match_vegc": True,
                    "vegc_passes": self.vegc_passes,
                    "vegc_tol": self.vegc_tol,
                    "vegc_max_factor": self.vegc_max_factor,
                }
                if self.match_vegc
                else {}
            ),
            "synth_kwargs": self.synth_kwargs,
        }


def vars_of(protocol: cb.SpinupProtocol) -> dict[str, Any]:
    return {f.name: getattr(protocol, f.name) for f in fields(protocol)}
