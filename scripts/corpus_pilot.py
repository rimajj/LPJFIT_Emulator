#!/usr/bin/env python
"""D2: the pilot corpus -- 200 cells x 30 climates x 1 seed, planned, generated and harvested.

    # 1. the plan: choose the cells, fix the design, write every manifest. Cheap, deterministic.
    scripts/sbatch_py.sh D-pilot-plan scripts/corpus_pilot.py --stage plan --version v1

    # 2. the forcing and the configs: 6,000 forcing sets and 6,000 spin-up configs.
    NCPUS=16 TIME=02:00:00 scripts/sbatch_py.sh D-pilot-build scripts/corpus_pilot.py \\
        --stage build --version v1 --workers 16

    # 3. check every file the manifests promise actually exists, before 670 core-hours burn.
    scripts/sbatch_py.sh D-pilot-verify scripts/corpus_pilot.py --stage verify --version v1

    # 4. the spin-ups, one job per manifest shard (LPJ_DEFINES="" selects the SPIN-UP branch).
    LPJ_DEFINES="" PARTITION=standard TIME=01:00:00 scripts/sbatch_cmodel.sh \\
        --manifest <manifests>/manifest_s00.tsv D-pilot-v1-s00

    # 5. the single harvest command for the whole campaign, however many shards it took.
    scripts/sbatch_py.sh D-pilot-harvest scripts/corpus_pilot.py --stage harvest --version v1

    # 6. the corpus table itself: every restart record and its own forcing, decoded and joined.
    NCPUS=16 TIME=00:30:00 scripts/sbatch_py.sh D-pilot-decode scripts/corpus_pilot.py \\
        --stage decode --version v1 --workers 16

A SECOND SEED ON A SUBSET -- the replicate. Same stages, `--seed 2 --subset 20`:

    scripts/sbatch_py.sh D-pilot-s2-plan scripts/corpus_pilot.py \\
        --stage plan --version v1 --seed 2 --subset 20

A NEW TABLE SCHEMA FROM EXISTING SPIN-UPS -- no model run at all. `--out-version` reads one
version's runs and writes the table under another, in the CURRENT schema (`vegemu.corpus.schema`),
then diffs it column by column against the source table and refuses anything the schema change
does not explain:

    NCPUS=16 TIME=00:30:00 scripts/sbatch_py.sh D-pilot-v3-decode scripts/corpus_pilot.py \\
        --stage decode --version v2-constco2 --out-version v3-constco2 --workers 16

A LARGER TIER. `--tier mid` is 1,000 cells x 100 climates, CONSTANT CO2, NESTED in the pilot: its
cells include all of `pilot-v2-constco2`'s 200 and its climates all of the pilot's 30. Directories
are named by tier (`mid-<version>`), every later stage takes the same `--tier`, and the build reads
the CO2 mode, the design and the point count from the PLAN, refusing a command line that disagrees.
`--co2-ppm X` pins CO2 at another constant level.

WHY IT EXISTS, AND IT IS NOT "more data". The acceptance tolerance is `max(10 %, THE MODEL'S OWN
TWO-RUN SPREAD)`, and that spread has never been measured on a PERTURBED spin-up -- only on
present-day climate, from which it is currently transferred. Its median there is exactly 0.100, i.e.
the bare floor, which is why the emitted-restart nulls collapse and that experiment cannot be
sealed. A replicate is a second draw of the SAME cell under the SAME climate, so the difference
between the two IS the model's noise. It is a denominator, never extra rows: appending it to the
corpus would double the pilot with re-runs and call it more evidence.

⚠ IT REUSES SEED 1'S FORCING BYTES RATHER THAN REBUILDING THEM. That is what makes the pair a
controlled contrast. It also means seed 1's build stage must have run for those cells first.

WHAT THIS IS. The corpus rung 1 is scored on. Every existing ground-truth leg holds exactly ONE
climate per location, so climate and geography are collinear and a warming response is not
separately identified (`MEMORY.md:ident-limit`) -- the predecessor's kill test failed on precisely
that. This spins the SAME cell up under THIRTY climates, which decollinearises them by construction
and is the experiment the predecessor could never run.

THE THREE THINGS THAT MAKE IT A DESIGN RATHER THAN A PILE OF RUNS

  * The cells are stratified over the populated 15-degree tiles and space-filling in the five
    perturbation axes' own baselines (`vegemu.corpus.select`), so a spatially blocked fold holds out
    a climate with no near neighbour instead of holding out an interpolation.
  * The thirty climates are THE SAME thirty at every cell (`pilot_design(30)`). That is what makes
    "held-out perturbation level" a meaningful test at all -- a per-cell random design would cover
    the axis space better but there would be no level to hold out. The cost is disclosed: 30 shared
    points sample the five-dimensional axis space at 11 factorial-core points and 18 free ones, and
    that coverage is what the mid tier's 100 climates buys, not more cells.
  * The control is design point one and is EXACTLY neutral, so "same cell, same seed, same config,
    same forcing window, only the climate differs" is available for free at every cell. That paired
    contrast is rung 1's decisive null (the same-cell baseline).

⚠ SPIN-UP LENGTH IS 1000 YEARS AND IS NOT NEGOTIABLE HERE. The hoped-for 3.3x saving from a shorter
spin-up is refuted: global vegetation carbon is 728 Pg C at year 300 against 890 at year 1000, so a
shortened spin-up produces a systematically DIFFERENT state, not a cheaper version of the same one
(`docs/decisions/20260908-D-spinup-is-not-converged.md`). Every run here is the full protocol.

⚠ AND THE TARGET IS PROTOCOL-DEFINED, NOT AN EQUILIBRIUM. What comes out is "the state LPJmL-FIT
reaches after its own standard 1000-year spin-up", which is still drifting at +6.8 %/century in the
median cell. That is the right target -- it is exactly what a user of the model gets, and skipping
it is exactly the saving on offer -- but it must never be called an equilibrium.

⚠ EVERY CONFIG IS BUILT BY PATCHING THE GROUND TRUTH'S OWN SAVED CONFIGURATION, and every
replacement is asserted (`corpus_spinup_config.py`). A fresh config would be a second, unvalidated
configuration whose differences from the truth nobody has enumerated.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.restart import RestartReader
from vegemu.corpus import climate as climate_mod
from vegemu.corpus import schema as schema_mod
from vegemu.corpus import state as state_mod
from vegemu.corpus.perturb import DESIGN_SEED, VARS, Perturbation, nested_design, pilot_design
from vegemu.corpus.select import pilot_cells
from vegemu.corpus.soil import SOIL_FEATURES
from vegemu.paths import path, paths, scratch

REPO = Path(__file__).resolve().parent.parent

NCELL = 200
NPOINT = 30
SEED = 1
NSPINUP = 1000


@dataclass(frozen=True)
class Tier:
    """A corpus tier's defaults. Each is overridable on the command line, and each is RECORDED."""

    ncell: int
    npoint: int
    design: str
    """`pilot` = `pilot_design(npoint)`; `nested` = `nested_design(npoint, base_n=30)`."""
    nest_in: str | None
    """The corpus directory whose cells (and design) this tier must contain, or None."""
    const_co2: bool


# ⚠ THE MID TIER IS CONSTANT-CO2 AND NESTED BY DEFAULT, and both are load-bearing. Constant CO2
# because Product A's target is a settled forest and a CO2 ramp in the last 300 spin-up years makes
# it a forced transient (`20260915-D-the-spinup-did-converge-*.md`). Nested because a mid tier that
# re-chose its cells and climates from scratch would share neither with the pilot, so no pilot
# result could be checked against it at the same place and climate.
TIERS: dict[str, Tier] = {
    "pilot": Tier(ncell=NCELL, npoint=NPOINT, design="pilot", nest_in=None, const_co2=False),
    "mid": Tier(
        ncell=1000, npoint=100, design="nested", nest_in="pilot-v2-constco2", const_co2=True
    ),
}
NESTED_BASE_NPOINT = 30

# PROJECTIONS, printed by the plan stage and recorded in its provenance -- never measurements of
# the tier being planned. Basis of each:
#   SPINUP_CPU_SECONDS   216 CPU-s per 1000-year single-cell spin-up, measured on the pilot
#                        (integrator, 2026-09-23); pilot-v1 cost 337 core-hours for 6,000, i.e. 202
#   ALLOCATION_FACTOR    ~1.9x: what one-core-per-member task farms have been billed over the CPU
#                        they used, unless the members are packed
#   RUN_DISK_BYTES       ~2.17 MB per run directory (restart, logs, two spin-up outputs), pilot mean
#   FORCING_SET_BYTES    1,315,530,000 B / 6,000 = 219,255 B per (cell, climate) forcing set,
#                        measured by pilot-v2-constco2's own build; a replicate seed writes none
SPINUP_CPU_SECONDS = 216.0
ALLOCATION_FACTOR = 1.9
RUN_DISK_BYTES = 2.17e6
FORCING_SET_BYTES = 219_255
# One SLURM job per this many single-cell spin-ups. Each member is ~6 minutes, so a shard of 250 is
# a job of well under an hour -- short enough to requeue cheaply, few enough steps that SLURM
# launches them all promptly. ⚠ PARTITION=priority is capped at 64 CPU per job, so a shard larger
# than 64 must go to PARTITION=standard (up to 2048).
SHARD_SIZE = 250
# The smallest restart record the format admits: 25 patches with no vegetation in any of them
# (`MEMORY.md:restart-size`, measured on the real 119 GiB file). A run whose record is this size
# grew nothing, and a run that grew a forest is nearer 1.9 MB. Used only as a proxy in `harvest`.
TREELESS_RESTART_BYTES = 380_000


def _load(name: str) -> ModuleType:
    """Import a sibling script by path. They are scripts, not package modules, by ownership.

    ⚠ THE `sys.modules` REGISTRATION IS LOAD-BEARING, and its absence fails nowhere near itself.
    Every module here opens with `from __future__ import annotations`, so all annotations are
    strings; `@dataclass` then resolves them through `sys.modules[cls.__module__]`, which is `None`
    for a module loaded by path and never registered. The symptom is an `AttributeError` inside
    `dataclasses.py` the moment the loaded script merely DEFINES a dataclass, so it reads as a
    broken standard library rather than a broken loader.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _vdir(version: str, seed: int, tier: str = "pilot") -> str:
    """The per-version directory name: `<tier>-<version>`, plus `-s<seed>` for a replicate.

    ⚠ SEED 1 IS DELIBERATELY UNSUFFIXED. The 6,000 runs of `pilot-v1` are on disk under that exact
    name and three pre-registrations cite a hash computed over them, so adding an `-s1` here would
    silently orphan the corpus this project's only positive result was scored on. A second seed gets
    its own tree; seed 1's paths are byte-for-byte what they were. The TIER prefix is the same rule:
    `pilot` keeps every existing path, and a new tier gets its own tree instead of a `pilot-` name.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; known: {sorted(TIERS)}")
    return f"{tier}-{version}" if seed == SEED else f"{tier}-{version}-s{seed}"


def meta_dir(version: str, seed: int = SEED, tier: str = "pilot") -> Path:
    return scratch("corpus", _vdir(version, seed, tier))


def _meta_path(version: str, seed: int = SEED, tier: str = "pilot") -> Path:
    """`meta_dir` without creating it -- for asking whether a version exists."""
    return Path(str(paths()["scratch"]["corpus"])) / _vdir(version, seed, tier)


def manifest_dir(version: str, seed: int = SEED, tier: str = "pilot") -> Path:
    """Manifests live with the runs: `sbatch_cmodel.sh` writes its task-farm runner beside them."""
    return scratch("runs", _vdir(version, seed, tier), "manifests")


def _under(
    kind: str, version: str, cell: int, point: str, *, seed: int = SEED, tier: str = "pilot"
) -> Path:
    """A per-run directory. `Path`, not `scratch()`: the plan stage must not create 12,000 dirs."""
    root = Path(str(paths()["scratch"]["root"]))
    return root / kind / _vdir(version, seed, tier) / f"c{cell}" / point


def forcing_dir(version: str, cell: int, point: str, tier: str = "pilot") -> Path:
    """SEED-INDEPENDENT ON PURPOSE, and this is the whole point of a second seed.

    The forcing IS the climate. A random seed changes the draws LPJmL-FIT makes, never the input it
    is driven by, so a second seed must read the SAME forcing bytes -- not an identical-looking
    rebuild of them. Sharing the directory makes that true by construction instead of by assertion,
    and it is why a second seed costs no forcing-generation time at all.
    """
    return _under("forcing", version, cell, point, tier=tier)


def run_dir(version: str, cell: int, point: str, seed: int = SEED, tier: str = "pilot") -> Path:
    return _under("runs", version, cell, point, seed=seed, tier=tier)


def run_tag(cell: int, point: str, seed: int = SEED) -> str:
    return f"c{cell}-{point}-s{seed}"


def constant_co2_path(version: str, tier: str = "pilot") -> Path:
    """Where a constant-CO2 corpus keeps its own CO2 forcing. One file for the whole version.

    A `Path`, not `scratch()`, so naming it creates nothing; the build stage makes the directory.
    """
    return (
        Path(str(paths()["scratch"]["root"]))
        / "forcing"
        / _vdir(version, SEED, tier)
        / ("co2_constant.txt")
    )


def config_path(version: str, cell: int, point: str, seed: int = SEED, tier: str = "pilot") -> Path:
    """Where `corpus_spinup_config.py` puts this run's config. Named once, used by every stage."""
    tag = run_tag(cell, point, seed)
    return run_dir(version, cell, point, seed, tier) / f"lpjml_spinup_{tag}.js"


def input_path(version: str, cell: int, point: str, seed: int = SEED, tier: str = "pilot") -> Path:
    """The run's input list, written by `corpus_spinup_config.build_input_js` beside its config."""
    return run_dir(version, cell, point, seed, tier) / f"input_{run_tag(cell, point, seed)}.js"


# ------------------------------------------------------------------------------------------------
# CO2: which mode a plan is in, said once, read by every later stage
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Co2:
    """A plan's CO2 forcing. `ppm` is None exactly when the mode is transient."""

    constant: bool
    ppm: float | None

    @classmethod
    def of_provenance(cls, prov: dict[str, Any]) -> Co2:
        """What a plan recorded. A plan from before `co2_ppm` existed and was constant is 276.59:
        that is the only constant level any such plan was ever built at."""
        constant = bool(prov.get("co2_constant", False))
        if not constant:
            return cls(False, None)
        ppm = prov.get("co2_ppm")
        return cls(True, float(ppm) if ppm is not None else _cfg().CO2_PREINDUSTRIAL_PPM)

    def describe(self, version: str, tier: str) -> str:
        if self.constant:
            return f"CONSTANT {self.ppm} ppm, own forcing file ({constant_co2_path(version, tier)})"
        return (
            "INHERITED FROM THE GROUND TRUTH AND THEREFORE TRANSIENT: "
            "global_co2_ann_1700_2022.txt over model years 1000-1999, so the last 300 spin-up "
            "years carry the historical CO2 rise 276.59 -> 367.26 ppm. Never PERTURBED and never "
            "written by us, and identical in every run, so it confounds no contrast between design "
            "points -- but the state is NOT an equilibrium under constant CO2 "
            "(20260915-D-the-spinup-did-converge-the-late-rise-is-transient-co2.md)."
        )


def co2_from_cli(const_co2: bool | None, co2_ppm: float | None) -> Co2 | None:
    """What the command line asked for, or None if it said nothing. `--co2-ppm` implies constant."""
    if co2_ppm is not None:
        if const_co2 is False:
            raise SystemExit("--transient-co2 and --co2-ppm contradict each other")
        return Co2(True, float(co2_ppm))
    if const_co2 is None:
        return None
    return Co2(True, _cfg().CO2_PREINDUSTRIAL_PPM) if const_co2 else Co2(False, None)


def _cfg() -> ModuleType:
    return _load("corpus_spinup_config")


# ------------------------------------------------------------------------------------------------
# stage: plan
# ------------------------------------------------------------------------------------------------


def _design(kind: str, npoint: int) -> list[Perturbation]:
    """The design a plan names, regenerated from its kind and size -- never from a CSV."""
    if kind == "pilot":
        return pilot_design(npoint)
    if kind == "nested":
        return nested_design(npoint, base_n=NESTED_BASE_NPOINT)
    raise ValueError(f"unknown design kind {kind!r}; known: pilot, nested")


def _plan_design(prov: dict[str, Any]) -> tuple[str, int, list[Perturbation]]:
    """`(kind, npoint, design)` as a plan recorded them; one older than `design_kind` is pilot."""
    kind = str(prov.get("design_kind", "pilot"))
    npoint = int(prov["npoint"])
    return kind, npoint, _design(kind, npoint)


def _nesting(nest_in: str | None) -> tuple[list[int], Path | None]:
    """The cells an earlier corpus directory ran, and that directory, or `([], None)`."""
    if not nest_in:
        return [], None
    base = Path(str(paths()["scratch"]["corpus"])) / nest_in
    cells_csv = base / "cells.csv"
    if not cells_csv.is_file():
        raise SystemExit(f"--nest-in {nest_in}: no {cells_csv}; nothing to nest in")
    return [int(c) for c in pl.read_csv(cells_csv)["cell"].to_list()], base


def _check_design_nests(design: list[Perturbation], base_csv: Path) -> int:
    """Every point of the earlier tier's design.csv is in `design`, in order, coefficient for
    coefficient. Returns how many. The regeneration is what runs, so it is what is checked."""
    base = pl.read_csv(base_csv)
    if base.height > len(design):
        raise SystemExit(
            f"{base_csv} holds {base.height} points; the new design only {len(design)}"
        )
    for i, row in enumerate(base.iter_rows(named=True)):
        p = design[i]
        got = (p.name, p.dtemp, p.fprec, p.sprec, p.frad, p.fiav)
        want = (row["point"], row["dtemp_k"], row["fprec"], row["sprec"], row["frad"], row["fiav"])
        if got != want:
            raise SystemExit(
                f"design point {i} is {got}, but the tier it must nest in ran {want} ({base_csv}). "
                "A nested design that does not reproduce its base exactly nests nothing."
            )
    return base.height


def _projection(nrun: int, nforcing: int) -> dict[str, Any]:
    """Cost and disk of a plan, from the pilot's measured unit costs. A PROJECTION, and says so."""
    cpu_h = nrun * SPINUP_CPU_SECONDS / 3600.0
    return {
        "is_projection": True,
        "basis": (
            f"{SPINUP_CPU_SECONDS:g} CPU-s per spin-up and {RUN_DISK_BYTES / 1e6:g} MB per run "
            f"directory (pilot means), {FORCING_SET_BYTES:,} B per forcing set (pilot-v2-constco2 "
            f"build), x{ALLOCATION_FACTOR:g} allocated over used unless members are packed"
        ),
        "spinups": nrun,
        "forcing_sets_written": nforcing,
        "cpu_core_hours": round(cpu_h, 1),
        "allocated_core_hours_unpacked": round(cpu_h * ALLOCATION_FACTOR, 1),
        "run_disk_gb": round(nrun * RUN_DISK_BYTES / 1e9, 1),
        "forcing_disk_gb": round(nforcing * FORCING_SET_BYTES / 1e9, 1),
    }


def _plan_schema(version: str, seed: int, tier: str) -> int:
    """The table schema a (re-)planned version decodes under.

    FIXED AT A VERSION'S FIRST PLAN. Re-planning an existing version keeps its recorded schema --
    otherwise re-running the plan stage over `pilot-v2-constco2` would silently promote it to schema
    3, and its next decode would overwrite a hash-pinned table with a different one. A replicate
    seed inherits seed 1's for the same reason: the pair is only a pair if both halves are decoded
    alike. Only a genuinely new version gets `schema.CURRENT`.
    """
    for d in (_meta_path(version, seed, tier), _meta_path(version, SEED, tier)):
        prov = d / "provenance.json"
        if prov.is_file():
            return schema_mod.of_provenance(json.loads(prov.read_text()))
    return schema_mod.CURRENT


def stage_plan(  # noqa: PLR0912, PLR0915 -- one flat pass: choose, write, record, report
    version: str,
    ncell: int,
    npoint: int,
    shard_size: int,
    *,
    seed: int = SEED,
    subset: int = 0,
    co2: Co2 | None = None,
    tier: str = "pilot",
    design_kind: str = "pilot",
    nest_in: str | None = None,
    max_per_tile: int | None = None,
) -> int:
    co2 = co2 or Co2(False, None)
    out = meta_dir(version, seed, tier)
    for d in (out, _meta_path(version, SEED, tier)):
        existing = d / "provenance.json"
        if existing.is_file() and json.loads(existing.read_text()).get("derived_from"):
            raise SystemExit(f"{d.name} is a re-decode of another version; plan the source instead")
    # ⚠ A PLAN MADE BEFORE HASH SCHEME 2 IS NEVER RE-PLANNED IN PLACE. Sealed pre-registrations cite
    # such a version's `plan_sha256` under the OLD formula (`pilot-v2-constco2`: `bad787ad...`), and
    # a re-plan here would rewrite that key under the new one -- the directory would stop matching
    # every citation of it, although neither its cells nor its climates changed. Under scheme 1 a
    # re-plan was harmless because it reproduced the same hash; now it cannot.
    here = out / "provenance.json"
    if here.is_file() and "plan_hash_scheme" not in json.loads(here.read_text()):
        raise SystemExit(
            f"{out.name} was planned under plan-hash scheme 1 and its plan_sha256 is cited by that "
            "value; re-planning it would rewrite the hash under scheme 2. Plan a new version."
        )
    # ⚠ A REPLICATE TAKES ITS FIRST SEED'S CO2 AND CLIMATES, OR IT IS NOT A REPLICATE. The build now
    # reads the CO2 mode from THIS plan, so a seed-2 plan made without `--const-co2` under a
    # constant-CO2 seed 1 builds transient-CO2 configs, verify passes them against their own plan,
    # and the "two-seed spread" then mixes the seed with a CO2 ramp. Refused here, before any file
    # is written, for the same reason `_plan_schema` makes a replicate inherit seed 1's schema.
    first = _meta_path(version, SEED, tier) / "provenance.json"
    if seed != SEED and first.is_file():
        first_prov = json.loads(first.read_text())
        first_co2 = Co2.of_provenance(first_prov)
        first_kind, first_npoint = str(first_prov.get("design_kind", "pilot")), first_prov["npoint"]
        if co2 != first_co2 or (design_kind, npoint) != (first_kind, first_npoint):
            raise SystemExit(
                f"seed {seed} of {version} must replicate seed {SEED}, which was planned with "
                f"{first_co2} and a {first_npoint}-point {first_kind} design; this plan asks for "
                f"{co2} and a {npoint}-point {design_kind} design. Give the same CO2 flags "
                f"(seed {SEED}: {first_prov.get('co2')})."
            )
    schema = _plan_schema(version, seed, tier)
    nest_cells, nest_dir = _nesting(nest_in)
    sel = pilot_cells(ncell, include=nest_cells, max_per_tile=max_per_tile)
    design = _design(design_kind, npoint)
    if design[0].name != "control" or not design[0].is_neutral:
        raise AssertionError("design point one must be the exactly-neutral control")
    if any(p.hold_huss_diagnostic for p in design):
        raise AssertionError(
            "a design point carries the hold-huss diagnostic flag. That arm deliberately breaks "
            "the fixed-relative-humidity rule and is for attribution only, never a corpus row."
        )

    cells = sel.cells()
    # ⚠ REFUSE A SHORT SELECTION HERE TOO. `pilot_cells` already raises, but the plan is what a
    # campaign is launched from, so the count it promises is asserted where it is written.
    if len(cells) != ncell:
        raise SystemExit(f"asked for {ncell} cells, the selection holds {len(cells)}; refusing")
    lost = sorted(set(nest_cells) - set(cells))
    if lost:
        raise SystemExit(
            f"{len(lost)} cells of {nest_in} are missing from the selection: {lost[:5]}"
        )
    nested_points = 0
    if nest_dir is not None and design_kind == "nested":
        nested_points = _check_design_nests(design, nest_dir / "design.csv")
    # ⚠ A SUBSET IS AN EVENLY SPACED SAMPLE OF THE FULL SELECTION, NEVER A RE-SELECTION AND NEVER
    # A PREFIX.
    #
    # Not a re-selection: `pilot_cells(20)` would run the stratifier again over 20 slots and return
    # a DIFFERENT set, and a second seed at cells the first seed never visited measures nothing.
    # The contrast being bought is same cell, same climate, same config, only the RNG draw differs,
    # so every cell here must be one seed 1 actually ran.
    #
    # And NOT A PREFIX, which is what this did first and was wrong. The selection is ordered by cell
    # index, and the grid runs south to north, so the first 20 of 200 are ALL between 52 S and 27 S
    # -- one temperate band, no tropics and no boreal, out of a full range of 52 S to 76 N. What a
    # replicate measures is the model's own two-run spread, and the acceptance criterion says that
    # spread is largest in LOW-DENSITY cells; sampling one latitude band would measure it where it
    # happens to be, then transfer it everywhere. A stride keeps the full range for the same cost.
    all_cells = cells
    if subset:
        if subset > len(cells):
            raise AssertionError(f"--subset {subset} exceeds the {len(cells)} cells selected")
        step = len(cells) // subset
        cells = cells[::step][:subset]
    sel.table.write_parquet(out / "cells.parquet")
    sel.table.write_csv(out / "cells.csv")
    design_rows = [
        {
            "point": p.name,
            "dtemp_k": p.dtemp,
            "fprec": p.fprec,
            "sprec": p.sprec,
            "frad": p.frad,
            "fiav": p.fiav,
            "kind": "control"
            if p.is_neutral
            else ("core" if p.name.startswith("core_") else "lhs"),
        }
        for p in design
    ]
    if design_kind == "nested":
        # Only a nested design gains the column, so a pilot design.csv -- and the hash over it --
        # is byte-for-byte what it always was.
        for i, row in enumerate(design_rows):
            row["base"] = i < NESTED_BASE_NPOINT
    pl.DataFrame(design_rows).write_csv(out / "design.csv")

    rows = [
        {
            "name": run_tag(cell, p.name, seed),
            "cell": cell,
            "point": p.name,
            "config": str(config_path(version, cell, p.name, seed, tier)),
            "run_dir": str(run_dir(version, cell, p.name, seed, tier)),
            "forcing": str(forcing_dir(version, cell, p.name, tier)),
        }
        for cell in cells
        for p in design
    ]
    pl.DataFrame(rows).write_csv(out / "runs.csv")

    mdir = manifest_dir(version, seed, tier)
    for old in sorted(mdir.glob("manifest_s*.tsv")):
        old.unlink()
    shards: list[Path] = []
    for i in range(0, len(rows), shard_size):
        chunk = rows[i : i + shard_size]
        mpath = mdir / f"manifest_s{i // shard_size:02d}.tsv"
        mpath.write_text(
            "".join(f"{r['name']}\t{r['config']}\t{r['run_dir']}\n" for r in chunk), "utf-8"
        )
        shards.append(mpath)

    nfree = sum(1 for p in design if p.name.startswith("lhs"))
    projection = _projection(len(rows), 0 if seed != SEED else len(cells) * len(design))
    prov: dict[str, Any] = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_pilot.py --stage plan",
        "tier": tier,
        "corpus_version": version,
        "git_commit": _git_commit(),
        "nrun": len(rows),
        "ncell": len(cells),
        "npoint": len(design),
        "seed": seed,
        "nspinup": NSPINUP,
        "schema": schema,
        "schema_note": schema_mod.SCHEMAS[schema],
        # A second seed is a REPLICATE, not a corpus. It exists to measure the model's own two-run
        # spread on PERTURBED climates -- which nobody has ever measured, while the acceptance
        # tolerance `max(10 %, that spread)` depends on it -- so it must never be concatenated onto
        # the seed-1 table and scored as extra rows.
        "replicate_of": None
        if seed == SEED
        else {
            "seed": SEED,
            "cells": cells,
            "ncell_full_selection": len(all_cells),
            "shares_forcing": True,
            "note": (
                f"same cells, same {len(design)} climates, same config, SAME forcing bytes; only "
                f'"random_seed" differs ({SEED} -> {seed}). Its purpose is the two-seed '
                "spread of a PERTURBED spin-up, which a single seed cannot give."
            ),
        },
        "spinup_note": (
            "1000 years, the full protocol. The target state is PROTOCOL-DEFINED and still "
            "drifting at ~+6.8 %/century in the median cell; it is not an equilibrium "
            "(docs/decisions/20260908-D-spinup-is-not-converged.md)."
        ),
        "design_seed": DESIGN_SEED,
        "design_kind": design_kind,
        "design_base_npoint": NESTED_BASE_NPOINT if design_kind == "nested" else None,
        "design_shared_across_cells": True,
        "design_note": (
            f"the same {len(design)} climates at every cell, which is what makes a held-out "
            "perturbation LEVEL a meaningful test; the cost is that the five-dimensional axis "
            f"space is sampled at {nfree} free points, not {len(all_cells)} x {nfree}"
        ),
        "nested_in": None
        if nest_dir is None
        else {
            "corpus_dir": nest_in,
            "cells": len(nest_cells),
            "cells_all_included": True,
            "design_points_reproduced": nested_points,
            "cells_csv_sha256": sha256_of(nest_dir / "cells.csv"),
            "design_csv_sha256": sha256_of(nest_dir / "design.csv"),
        },
        "selection": sel.as_dict(),
        "base_window": [1970, 1999],
        # ⚠ "untouched" IS NOT "constant", and this key used to say only the first. The ground
        # truth's CO2 input is transient (1700-2022) and the spin-up runs model years 1000-1999, so
        # an untouched corpus carries a +32.8 % CO2 rise over its last 300 years.
        "co2": co2.describe(version, tier),
        "co2_constant": co2.constant,
        "co2_ppm": co2.ppm,
        "co2_file": str(constant_co2_path(version, tier)) if co2.constant else None,
        "shards": [str(p) for p in shards],
        "shard_size": shard_size,
        "sources": _source_provenance(),
        "binary": _binary_provenance(),
        "projection": projection,
        "plan_hash_scheme": 2,
        "design_sha256": "",
        "plan_sha256": "",
    }
    # TWO HASHES, BECAUSE THEY ANSWER TWO QUESTIONS.
    #
    # `design_sha256` is what `plan_sha256` used to be, formula unchanged: the cell list, the design
    # and the identity of every source file -- not the 11.7 GB inputs themselves, since hashing five
    # global `.clm` files would read 60 GB to restate what size and mtime already pin down. It is
    # equal for any two plans over the same cells and climates, which is exactly the guarantee the
    # v1-vs-v2 comparisons cite ("same 200 cells, same 30 points, CO2 the only difference"). For
    # every plan made before scheme 2 it IS the recorded `plan_sha256`.
    #
    # `plan_sha256` now covers everything that makes two plans produce different runs: that, plus
    # the CO2 mode and level, the seed, the cells actually run (a subset is not in cells.csv), the
    # spin-up length and the table schema. Under scheme 1 a seed-2 replicate and a constant-CO2
    # re-run both carried their seed-1 transient twin's hash -- one hash for different corpora.
    prov["design_sha256"] = hashlib.sha256(
        (out / "cells.csv").read_bytes()
        + (out / "design.csv").read_bytes()
        + json.dumps(prov["sources"], sort_keys=True).encode()
    ).hexdigest()
    terms = {
        "design_sha256": prov["design_sha256"],
        "co2_constant": co2.constant,
        "co2_ppm": co2.ppm,
        "seed": seed,
        "run_cells": cells,
        "nspinup": NSPINUP,
        "schema": schema,
        "plan_hash_scheme": 2,
    }
    prov["plan_sha256"] = hashlib.sha256(json.dumps(terms, sort_keys=True).encode()).hexdigest()
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", "utf-8")

    print(
        f"{tier} corpus {version}: {len(cells)} cells x {len(design)} climates = {len(rows)} runs"
    )
    print(f"  eligible tree-bearing cells   {sel.eligible}")
    print(
        f"  populated {int(sel.as_dict()['tile_degrees'])}-degree tiles      "
        f"{sel.tiles_populated}, of which covered {sel.tiles_covered}"
    )
    print(f"  per-tile cap                  {sel.max_per_tile}")
    for stage, count in sorted(sel.as_dict()["by_stage"].items()):
        print(f"  cells chosen by {stage:12s}  {count}")
    if nest_dir is not None:
        print(
            f"  nested in {nest_in}: all {len(nest_cells)} of its cells included"
            + (f", its {nested_points} climates reproduced exactly" if nested_points else "")
        )
    print(
        f"  design ({design_kind}): {sum(1 for p in design if p.is_neutral)} control, "
        f"{sum(1 for p in design if p.name.startswith('core_'))} factorial core, "
        f"{nfree} hypercube"
    )
    print(f"  co2           {prov['co2']}")
    print(f"  schema        {schema} -- {schema_mod.SCHEMAS[schema]}")
    print(f"  design_sha256 {prov['design_sha256']}")
    print(f"  plan_sha256   {prov['plan_sha256']}")
    print(f"  tables        {out}")
    print(f"  manifests     {len(shards)} shards of <= {shard_size} in {mdir}")
    print(
        f"  PROJECTED (not measured): {projection['cpu_core_hours']:,} CPU core-hours, "
        f"~{projection['allocated_core_hours_unpacked']:,} allocated unpacked; "
        f"{projection['run_disk_gb']:,} GB of runs + "
        f"{projection['forcing_disk_gb']:,} GB of forcing"
    )
    if shard_size > 64:
        print(
            "  ⚠ a shard larger than 64 must go to PARTITION=standard; priority is capped at "
            "64 CPU per job and refuses at submit time."
        )
    return 0


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def _source_provenance() -> dict[str, Any]:
    """Every forcing file this corpus reads, with the identity that pins the build it came from."""
    cfg = paths()
    perturb = _load("corpus_perturb_clm")
    out: dict[str, Any] = {}
    for leg in ("historical", perturb.CALIB_LEG):
        for var, p in cfg["inputs"][leg].items():
            st = Path(str(p)).stat()
            out[f"{leg}.{var}"] = {
                "path": str(p),
                "bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds"),
            }
    return out


def _binary_key() -> str:
    """The `config/paths.yaml` key of the build the spin-ups will run: `LPJ_BINARY_KEY`, as
    `sbatch_cmodel.sh` resolves it, default `lpjml.binary`. A key, never a path, for the same
    reason the wrapper gives: a run can only use a binary the provenance file already knows."""
    key = os.environ.get("LPJ_BINARY_KEY", "lpjml.binary")
    if not key.startswith("lpjml."):
        raise SystemExit(
            f"LPJ_BINARY_KEY must be a config/paths.yaml key under lpjml., got {key!r}"
        )
    return key


def _binary_provenance() -> dict[str, Any]:
    """Which LPJmL-FIT build will run. Two builds are never byte-identical, so this is recorded.

    ⚠ IT HONOURS `LPJ_BINARY_KEY`, and used not to: it always recorded `lpjml.binary`, so a
    campaign submitted with `LPJ_BINARY_KEY=lpjml.binary_pristine` would have carried the WRONG
    build in its provenance. The key must be exported for the plan job AND the spin-up jobs alike;
    the wrapper's ledger row records the latter.
    """
    key = _binary_key()
    p = path(key)
    st = p.stat()
    built = datetime.fromtimestamp(st.st_mtime, UTC)
    return {
        "key": key,
        "path": str(p),
        "bytes": st.st_size,
        "mtime_utc": built.isoformat(timespec="seconds"),
        "version": str(paths()["lpjml"]["version"]),
        "note": (
            "generate the WHOLE corpus with ONE binary. The stored historical ground truth came "
            f"from the 2026-02-05 build; this one ({key}) was built {built.date()}, so corpus runs "
            "are comparable to each other and NOT to the stored global output unless the dates "
            "agree (MEMORY.md:subset-diverges)."
        ),
    }


# ------------------------------------------------------------------------------------------------
# stage: build -- the forcing sets and the configs
# ------------------------------------------------------------------------------------------------


# One build job: (version, tier, cell, design kind, npoint, seed, constant-CO2 file or "").
BuildJob = tuple[str, str, int, str, int, int, str]


def _build_cell(args: BuildJob) -> dict[str, Any]:
    """One cell: read its baseline once, then write all `npoint` forcing sets and configs.

    Runs in a worker process, so it imports what it needs itself and returns only small summaries.

    ⚠ A REPLICATE SEED WRITES CONFIGS ONLY. Its forcing directory IS seed 1's, so rewriting it would
    at best redo work and at worst race a concurrent reader of the corpus the pilot is scored on.
    The files are required to be there already and are checked, never regenerated.
    """
    version, tier, cell, design_kind, npoint, seed, co2_path = args
    perturb = _load("corpus_perturb_clm")
    cfgmod = _load("corpus_spinup_config")
    design = _design(design_kind, npoint)
    replicate = seed != SEED
    co2_file = Path(co2_path) if co2_path else None

    # The one read that must not be repeated per point: the 30-year baseline block plus the
    # calibration contrast out of the scenario leg. A replicate reads no baseline at all.
    cb = None if replicate else perturb.load_base(range(cell, cell + 1))
    wrote: list[dict[str, Any]] = []
    for pert in design:
        fdir = forcing_dir(version, cell, pert.name, tier)
        if replicate:
            record = _existing_forcing(fdir, perturb)
        else:
            record = perturb.write_point(cb, pert, fdir)
        rdir = run_dir(version, cell, pert.name, seed, tier)
        (rdir / "output").mkdir(parents=True, exist_ok=True)
        (rdir / "restart").mkdir(parents=True, exist_ok=True)
        tag = run_tag(cell, pert.name, seed)
        input_js = cfgmod.build_input_js(fdir, rdir, tag, co2_file=co2_file)
        config = cfgmod.build_config(cell, input_js, rdir, tag=tag, seed=seed, nspinup=NSPINUP)
        wrote.append(
            {
                "point": pert.name,
                "config": str(config),
                "bytes": sum(int(record["files"][v]["bytes"]) for v in VARS),
                "neutral_byte_identity": all(
                    "neutral_byte_identity" in record["files"][v] for v in VARS
                )
                if pert.is_neutral and not replicate
                else None,
                "tas_ann_c": record["diagnostics"]["tas_ann_c"],
                "pr_ann_mm": record["diagnostics"]["pr_ann_mm"],
            }
        )
    return {"cell": cell, "npoint": len(wrote), "points": wrote}


def _existing_forcing(fdir: Path, perturb: ModuleType) -> dict[str, Any]:
    """The seed-1 forcing this replicate will be driven by, checked rather than rewritten.

    Returns the same shape `write_point` does, so the caller's bookkeeping is untouched. The
    diagnostics it cannot recompute without re-reading the `.clm` files are left as None: this
    summary is provenance for a replicate, and the real diagnostics are in seed 1's own build JSON.
    """
    files: dict[str, Any] = {}
    for var in VARS:
        f = fdir / perturb.OUT_NAME[var]
        if not f.is_file() or f.stat().st_size == 0:
            raise AssertionError(
                f"replicate seed: forcing {f} is missing. A replicate REUSES seed 1's forcing and "
                "never regenerates it, so seed 1's build stage must have run for this cell first."
            )
        files[var] = {"bytes": f.stat().st_size}
    return {"files": files, "diagnostics": {"tas_ann_c": None, "pr_ann_mm": None}}


def _write_co2_if_constant(version: str, tier: str, co2: Co2) -> str:
    """Write this version's constant-CO2 forcing once, before the workers fan out; its path or "".

    In the build stage rather than the plan stage because the plan deliberately creates no
    directories, and in the PARENT rather than in `_build_cell` because 20 workers writing the same
    file is a race with no upside.

    ⚠ AN EXISTING FILE IS CHECKED, NOT REWRITTEN. A replicate seed builds while seed 1's spin-ups
    may still be reading this file, and a rewrite truncates it first -- a run opening it in that
    instant reads an empty CO2 input. Same bytes: left alone. Different bytes: refused, because the
    two seeds would then not share a CO2 path.

    ⚠ THE CANDIDATE NAME IS UNIQUE PER CALL. `--shard/--nshard` builds run as concurrent jobs, and
    with one fixed candidate name two shards wrote, compared, renamed and unlinked THE SAME file:
    the second shard's read or unlink then found it gone and the shard died before building a cell.
    Each call now writes its own temporary file and `os.replace`s it into place, which is atomic, so
    two shards racing to create the file both land identical bytes and a reader never sees half.
    """
    if not co2.constant:
        return ""
    cfgmod = _cfg()
    dest = constant_co2_path(version, tier)
    assert co2.ppm is not None
    # Host AND pid: shards run on different nodes, where pids repeat. Not `mkstemp`, whose 0600 mode
    # would survive the rename and make the version's CO2 input unreadable to the group.
    fresh = dest.with_name(f".{dest.name}.{socket.gethostname()}.{os.getpid()}.candidate")
    try:
        cfgmod.write_constant_co2(fresh, ppm=co2.ppm)
        if dest.is_file():
            if dest.read_bytes() != fresh.read_bytes():
                raise SystemExit(
                    f"{dest} exists and differs from a {co2.ppm} ppm file. This version's runs "
                    "would not share one CO2 path; refusing to overwrite it."
                )
            print(f"constant CO2 forcing: {dest}  ({co2.ppm} ppm) -- already present, identical")
        else:
            os.replace(fresh, dest)
            print(f"constant CO2 forcing: {dest}  ({co2.ppm} ppm, every year the spin-up reads)")
    finally:
        fresh.unlink(missing_ok=True)
    return str(dest)


def _build_cell_guarded(args: BuildJob) -> dict[str, Any]:
    try:
        return _build_cell(args)
    # One bad cell must not lose the other 199, so the traceback is returned rather than raised --
    # and `stage_build` exits non-zero on any of them, so a partial corpus is never silently green.
    except Exception:
        return {"cell": args[2], "error": traceback.format_exc(limit=6)}


def _read_plan(version: str, seed: int, tier: str) -> dict[str, Any]:
    """The plan's provenance, refusing a tier the plan was not made for."""
    prov_path = _meta_path(version, seed, tier) / "provenance.json"
    if not prov_path.is_file():
        raise SystemExit(f"no plan at {prov_path}: run --stage plan first (same --tier/--seed)")
    prov: dict[str, Any] = json.loads(prov_path.read_text())
    planned = str(prov.get("tier", "pilot"))
    if planned != tier:
        raise SystemExit(f"{prov_path} was planned as tier {planned!r}, not {tier!r}")
    return prov


def stage_build(  # noqa: PLR0912 -- the plan-versus-CLI refusals, then one pass
    version: str,
    workers: int,
    shard: int,
    nshard: int,
    npoint: int | None = None,
    *,
    seed: int = SEED,
    co2: Co2 | None = None,
    tier: str = "pilot",
) -> int:
    """⚠ THE PLAN DECIDES, THE COMMAND LINE MAY ONLY AGREE. The CO2 mode, the design and the point
    count are read from the plan's provenance. They used to come from the command line, so a build
    that forgot `--const-co2` would have written TRANSIENT-CO2 configs under a plan that says
    constant, and every later stage would have believed the plan."""
    out = meta_dir(version, seed, tier)
    prov = _read_plan(version, seed, tier)
    if prov.get("derived_from"):
        raise SystemExit(
            f"{out.name} is a re-decode of {prov['derived_from']['corpus_dir']}: it has no "
            "spin-ups of its own to build. Build the source version."
        )
    planned_co2 = Co2.of_provenance(prov)
    if co2 is not None and co2 != planned_co2:
        raise SystemExit(
            f"the command line asks for {co2}, the plan says {planned_co2} ({prov['co2']}). "
            "Re-plan, or drop the flag: the build takes the CO2 mode from the plan."
        )
    design_kind, planned_npoint, _ = _plan_design(prov)
    if npoint is not None and npoint != planned_npoint:
        raise SystemExit(f"--npoint {npoint} but the plan has {planned_npoint} climates")
    npoint = planned_npoint
    co2_path = _write_co2_if_constant(version, tier, planned_co2)
    runs = pl.read_csv(out / "runs.csv")
    cells = sorted(set(int(c) for c in runs["cell"].to_list()))
    mine = cells[shard::nshard] if nshard > 1 else cells
    print(
        f"building {len(mine)} of {len(cells)} cells x {npoint} climates ({design_kind} design), "
        f"seed {seed}, tier {tier} (shard {shard}/{nshard}, {workers} workers)"
    )
    print(f"  co2 (from the plan): {prov['co2']}")
    if seed != SEED:
        print(f"  replicate of seed {SEED}: configs only, forcing is REUSED and checked in place")

    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    jobs: list[BuildJob] = [
        (version, tier, cell, design_kind, npoint, seed, co2_path) for cell in mine
    ]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_build_cell_guarded, j): j[2] for j in jobs}
            for i, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                (failed if "error" in res else done).append(res)
                if i % 20 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} cells  ({len(failed)} failed)", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            res = _build_cell_guarded(j)
            (failed if "error" in res else done).append(res)
            if i % 20 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} cells  ({len(failed)} failed)", flush=True)

    total_bytes = sum(int(p["bytes"]) for r in done for p in r["points"])
    neutral = [p for r in done for p in r["points"] if p["neutral_byte_identity"] is not None]
    summary = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "shard": shard,
        "nshard": nshard,
        "cells_built": len(done),
        "cells_failed": len(failed),
        "forcing_bytes": total_bytes,
        "seed": seed,
        "tier": tier,
        "co2": prov["co2"],
        "neutral_points_checked": len(neutral),
        "neutral_byte_identity_all_pass": all(bool(p["neutral_byte_identity"]) for p in neutral),
        "failures": failed,
    }
    (out / f"build_s{shard:02d}of{nshard:02d}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    verb = "reused" if seed != SEED else "written"
    print(f"forcing {verb}: {total_bytes / 1e9:.2f} GB over {len(done)} cells")
    # ⚠ SAY WHEN THE CHECK DID NOT RUN. A replicate writes no forcing, so `neutral` is empty and
    # `all([])` is True -- "all pass = True" over zero points is a check that CANNOT fail, which
    # reads exactly like a check that passed. The seed-1 build is where this check has its meaning.
    if not neutral:
        print(
            f"neutral byte identity: NOT CHECKED HERE -- 0 control points. Seed {seed} reuses seed "
            f"{SEED}'s forcing unmodified, so identity is seed {SEED}'s build to have established."
        )
    else:
        print(
            f"neutral byte identity: {len(neutral)} control points checked, "
            f"all pass = {summary['neutral_byte_identity_all_pass']}"
        )
    if not summary["neutral_byte_identity_all_pass"]:
        print(
            "  ⚠ a control point did NOT reproduce the source bytes. The writer is not a no-op "
            "on the identity design point, so no perturbed file it produced can be trusted."
        )
        return 1
    if failed:
        print(f"⚠ {len(failed)} cells FAILED; the corpus is incomplete:", file=sys.stderr)
        for f in failed[:5]:
            print(f"  cell {f['cell']}:\n{f['error']}", file=sys.stderr)
        return 1
    return 0


# ------------------------------------------------------------------------------------------------
# stage: verify -- does every file the manifests promise exist, before 670 core-hours burn
# ------------------------------------------------------------------------------------------------


def _check_co2(
    runs: pl.DataFrame, co2: Co2, version: str, tier: str
) -> tuple[set[str], list[str], list[str]]:
    """Every run's input list names the plan's CO2 file, and that file is what the plan says.

    Returns `(runs with a problem, per-run problems, problems with the CO2 file itself)`. Kept
    apart because a missing, short or wrong-level FILE is not a problem with any one run, and
    counting it as one used to make "co2 inputs as planned" read 5,999/6,000 when no run could
    start.

    ⚠ THIS IS THE CHECK WHOSE ABSENCE HID A CO2 RAMP FOR A WEEK. The old verify stage looked for
    configs and forcing and never opened the CO2 entry, so a transient-CO2 build under a plan that
    believed itself constant -- or the reverse -- would have been declared READY.
    """
    cfgmod = _cfg()
    if co2.constant:
        expected = str(constant_co2_path(version, tier))
    else:
        saved = path("ground_truth.historical_seed1") / cfgmod.SAVED_INPUT
        expected = cfgmod.read_co2_input(saved)
    problems: list[str] = []
    file_problems: list[str] = []
    bad_runs: set[str] = set()
    for name, config in zip(runs["name"].to_list(), runs["config"].to_list(), strict=True):
        input_js = Path(config).with_name(f"input_{name}.js")
        if not input_js.is_file():
            problems.append(f"{name}: no input list {input_js.name}")
            bad_runs.add(name)
            continue
        got = cfgmod.read_co2_input(input_js)
        if got != expected:
            problems.append(f"{name}: co2 input {got}, the plan says {expected}")
            bad_runs.add(name)
        text = Path(config).read_text(encoding="utf-8") if Path(config).is_file() else ""
        if text.count(f'#include "{input_js}"') != 2:
            problems.append(f"{name}: the config does not include its own input list twice")
            bad_runs.add(name)
    if not Path(expected).is_file():
        return bad_runs, problems, [f"the CO2 file {expected} does not exist"]
    span = range(cfgmod.SPINUP_FIRST_MODEL_YEAR, cfgmod.SPINUP_LAST_MODEL_YEAR + 1)
    seen = cfgmod.co2_seen_by_model(Path(expected), span)
    if any(np.isnan(v) for v in seen.values()):
        file_problems.append(f"{expected} ends before model year {span[-1]}: runs would die there")
    if co2.constant and any(v != co2.ppm for v in seen.values()):
        bad = sorted(y for y, v in seen.items() if v != co2.ppm)
        file_problems.append(
            f"the model would see a CO2 other than {co2.ppm} ppm in {len(bad)} spin-up years "
            f"({bad[0]}-{bad[-1]}): the file starts too late for the clamp to agree"
        )
    return bad_runs, problems, file_problems


def stage_verify(version: str, seed: int = SEED, tier: str = "pilot") -> int:
    out = meta_dir(version, seed, tier)
    prov = _read_plan(version, seed, tier)
    co2 = Co2.of_provenance(prov)
    runs = pl.read_csv(out / "runs.csv")
    filenames = list(_load("corpus_perturb_clm").OUT_NAME.values())
    missing_cfg: list[str] = []
    missing_forcing: list[str] = []
    sizes: dict[int, int] = {}
    for name, config, forcing in zip(
        runs["name"].to_list(), runs["config"].to_list(), runs["forcing"].to_list(), strict=True
    ):
        if not Path(config).is_file():
            missing_cfg.append(name)
        for fname in filenames:
            f = Path(forcing) / fname
            if not f.is_file():
                missing_forcing.append(f"{name}/{fname}")
            else:
                size = f.stat().st_size
                sizes[size] = sizes.get(size, 0) + 1
    co2_bad_runs, co2_run_problems, co2_file_problems = _check_co2(runs, co2, version, tier)
    co2_problems = [*co2_file_problems, *co2_run_problems]

    total = runs.height
    print(f"{tier} corpus {version} seed {seed}: {total} runs promised by the manifests")
    print(f"  configs present        {total - len(missing_cfg)}/{total}")
    print(f"  forcing files present  {sum(sizes.values())}/{total * 5}")
    print(f"  distinct forcing sizes {sorted(sizes.items(), reverse=True)[:4]}")
    print(f"  co2 (plan)             {prov['co2']}")
    print(f"  co2 inputs as planned  {total - len(co2_bad_runs)}/{total}")
    if co2_file_problems:
        print(f"  ⚠ the CO2 FILE itself fails its check, so NO run is ready: {co2_file_problems}")
    if len(sizes) > 1:
        print(
            "  ⚠ forcing files are NOT all the same size. A `.clm` size mismatch means the "
            "dtype or the year count is wrong and every value read is silently shifted."
        )
    for label, items in (
        ("configs", missing_cfg),
        ("forcing files", missing_forcing),
        ("CO2 checks failed", co2_problems),
    ):
        if items:
            print(f"  ⚠ {len(items)} {label}, first few: {items[:5]}", file=sys.stderr)
    ok = not missing_cfg and not missing_forcing and len(sizes) == 1 and not co2_problems
    print(f"verdict: {'READY to submit' if ok else 'NOT READY -- do not submit'}")
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------
# stage: harvest -- the one command that judges the whole campaign, however many shards it took
# ------------------------------------------------------------------------------------------------


DONE_LINE = re.compile(r"^lpjml successfully terminated", re.MULTILINE)


def stage_harvest(version: str, seed: int = SEED, tier: str = "pilot") -> int:
    """Count the runs that printed the MODEL'S OWN completion line, and the restarts they wrote.

    Never the exit codes: the stock job files always exit 0, so a run that died mid-spin-up leaves a
    plausible truncated output behind a green row (`MEMORY.md:c-log-truth`). And the line is matched
    ANCHORED, at the start of a line: an unanchored search also matches any advice text that merely
    quotes the phrase, which is how a failed job once counted as a success.
    """
    out = meta_dir(version, seed, tier)
    runs = pl.read_csv(out / "runs.csv")
    ok, no_line, no_log, no_restart = 0, [], [], []
    sizes: list[int] = []
    treeless: list[str] = []
    for name, rdir in zip(runs["name"].to_list(), runs["run_dir"].to_list(), strict=True):
        log = Path(rdir) / f"lpjml.{name}.log"
        if not log.is_file() or log.stat().st_size == 0:
            no_log.append(name)
            continue
        if DONE_LINE.search(log.read_text(errors="replace")):
            ok += 1
        else:
            no_line.append(name)
        restart = Path(rdir) / "restart" / f"restart_{name}.lpj"
        if not restart.is_file() or restart.stat().st_size == 0:
            no_restart.append(name)
            continue
        size = restart.stat().st_size
        sizes.append(size)
        if size <= TREELESS_RESTART_BYTES:
            treeless.append(name)

    total = runs.height
    print(f"{tier} corpus {version} seed {seed}: {total} runs")
    print(f"  printed the model's own completion line  {ok}/{total}")
    print(f"  no log at all (never started, or dead)   {len(no_log)}")
    print(f"  log without the completion line          {len(no_line)}")
    print(f"  no restart file written                  {len(no_restart)}")
    for label, items in (
        ("never started", no_log),
        ("did not complete", no_line),
        ("wrote no restart", no_restart),
    ):
        if items:
            print(f"  first few {label}: {items[:5]}")

    # ⚠ A COMPLETE CAMPAIGN IS NOT THE SAME AS A USABLE CORPUS. A restart record is ~1.9 MB with a
    # forest and bottoms out near 360 KB with no vegetation at all (`MEMORY.md:restart-size`), so
    # the size distribution is a free first look at how many design points killed the forest. It is
    # a PROXY, not the stem count -- that comes from decoding the records into the corpus table --
    # but it is the number that says whether rung 1 would be scoring forests or scoring emptiness.
    if sizes:
        arr = np.sort(np.asarray(sizes, dtype=np.int64))
        pct = [int(np.percentile(arr, q)) for q in (5, 25, 50, 75, 95)]
        print(f"  restart bytes p5/p25/p50/p75/p95         {'/'.join(f'{p:,}' for p in pct)}")
        print(
            f"  at or below the treeless floor           {len(treeless)}/{len(sizes)} "
            f"({100 * len(treeless) / len(sizes):.1f} %, floor {TREELESS_RESTART_BYTES:,} B)"
        )
        if len(treeless) > len(sizes) // 2:
            print(
                "  ⚠ MORE THAN HALF the runs produced a vegetation-free state. The campaign can be "
                "complete and the corpus still be mostly empty -- report this fraction with every "
                "number the corpus supports, and check the axis ranges before scoring anything."
            )

    complete = ok == total and not no_restart
    print(
        f"verdict: {'COMPLETE' if complete else 'INCOMPLETE'} -- "
        f"{'harvestable' if complete else 'rerun the missing members before scoring anything'}"
    )
    return 0 if complete else 1


# ------------------------------------------------------------------------------------------------
# stage: decode -- the 6,000 restarts and their forcing become the corpus table
# ------------------------------------------------------------------------------------------------

# The state a run produces is the end of 1000 spin-up years that CYCLE these 30 forcing years, and
# LPJmL-FIT labels the restart it writes with the last of them. So `state_year` is bookkeeping, not
# a date: nothing here is "the state of 1999", and the climate summary is over the whole window
# rather than any single year. Asserted per run against the restart's own header.
STATE_YEAR = 1999


# One decode job: (run name, cell, point, run dir, forcing dir, seed, table schema).
DecodeJob = tuple[str, int, str, str, str, int, int]


def _decode_run(args: DecodeJob) -> dict[str, Any]:
    """One run: its restart record and its own perturbed forcing, as one corpus row.

    The row also carries `restart_sha256`, which the table does not (`_corpus_frame` selects its
    columns by name): it is what lets a re-decode into a new version prove it read the SAME
    restarts, file by file, rather than assert it.
    """
    name, cell, point, rdir, fdir, seed, schema = args
    perturb = _load("corpus_perturb_clm")
    restart = Path(rdir) / "restart" / f"restart_{name}.lpj"

    # Two opens of the same file on purpose. The year label is a header read of 92 bytes, and doing
    # it here keeps the "a per-cell restart holds ONE record" assertion in `single_cell_state`,
    # where every future caller gets it, instead of copied into this script.
    restart_year = RestartReader(restart).generic.firstyear
    row: dict[str, Any] = {
        "name": name,
        "cell": cell,
        "point": point,
        "seed": seed,
        "restart_year": restart_year,
        "restart_bytes": restart.stat().st_size,
        "restart_sha256": sha256_of(restart),
    }
    row.update(state_mod.single_cell_state(restart, cell, schema=schema))

    # ⚠ `climate_columns`, NEVER `climate_table`: this runs in a forked worker, and polars' thread
    # pool does not survive a fork -- a DataFrame touched here hangs the child forever with no
    # error, so the job burns its whole wall-clock limit and produces nothing.
    #
    # The window's leg label stays "pilot" for every tier: it is a column VALUE in the table, and a
    # schema-2 re-decode must reproduce its bytes. It names the forcing kind (a perturbed copy of
    # the historical window), not the tier.
    window = climate_mod.Window("pilot", *perturb.BASE_WINDOW, STATE_YEAR)
    files = {v: str(Path(fdir) / perturb.OUT_NAME[v]) for v in climate_mod.VARS}
    cl = climate_mod.climate_columns(window, files=files, with_soil=schema >= 3)
    if cl["cell"].size != 1:
        raise AssertionError(f"{name}: forcing describes {cl['cell'].size} cells, expected 1")
    if int(cl["cell"][0]) != cell:
        raise AssertionError(
            f"{name}: forcing declares cell {int(cl['cell'][0])}, the run is cell {cell}. The "
            "`.clm` header's firstcell is the only record of which cell a subset file holds."
        )
    row["lon"] = float(cl["lon"][0])
    row["lat"] = float(cl["lat"][0])
    row["leg"] = str(cl["leg"][0])
    row["state_year"] = int(cl["state_year"][0])
    for feat in climate_mod.climate_features(schema):
        row[feat] = float(cl[feat][0])
    return row


def _decode_run_guarded(args: DecodeJob) -> dict[str, Any]:
    # One unreadable restart must not lose the other 5,999, and `stage_decode` exits non-zero on
    # any of them, so a partial corpus table is never silently green.
    try:
        return _decode_run(args)
    except Exception:
        return {"name": args[0], "cell": args[1], "error": traceback.format_exc(limit=6)}


def _decode_all(
    jobs: list[DecodeJob], nproc: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every run decoded, split into the rows that worked and the ones that raised."""
    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    if nproc > 1:
        with ProcessPoolExecutor(max_workers=nproc) as pool:
            results = pool.map(_decode_run_guarded, jobs, chunksize=8)
            for i, res in enumerate(results, 1):
                (failed if "error" in res else done).append(res)
                if i % 500 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} runs  ({len(failed)} failed)", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            res = _decode_run_guarded(j)
            (failed if "error" in res else done).append(res)
            if i % 500 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} runs  ({len(failed)} failed)", flush=True)
    return done, failed


def _corpus_frame(
    done: list[dict[str, Any]],
    design: pl.DataFrame,
    cells: pl.DataFrame,
    features: tuple[str, ...] = climate_mod.CLIMATE_FEATURES,
) -> pl.DataFrame:
    """The decoded rows joined to the design and the cell table, in the corpus column order.

    Column order is the contract: the keys a fold is built from, then the design coefficients that
    NAME the climate a row was grown under, then the features a model may see, then the targets.
    `cell`, `lon` and `lat` sit with the keys because the geographic address is a pre-registered
    NULL, not a feature (`vegemu.corpus.climate` header) -- a feature set that quietly contains it
    turns any per-cell score into a spatial-interpolation score. `features` is the schema's
    (`climate.climate_features`): schema 3 adds the five soil columns right after the climate ones.
    """
    keys = ("name", "cell", "point", "kind", "tile", "stage", "seed", "leg", "state_year")
    coeff = ("dtemp_k", "fprec", "sprec", "frad", "fiav")
    targets = tuple(c for c in state_mod.STATE_COLUMNS if c != "cell")
    # `truth_stems_total` is the stem count the STORED GROUND TRUTH holds at this cell, carried in
    # so the control point can be checked against it. It is a diagnostic, never a feature: it is a
    # lagged truth, and a model that saw it would score beautifully on a held-out cell.
    from_cells = cells.select("cell", "tile", "stage", "stems_total").rename(
        {"stems_total": "truth_stems_total"}
    )
    # `summarise_cell` reports every state column as a float, `cell` included, so the raw rows
    # carry a f64 cell number and joining it against an integer key is a `SchemaError`.
    return (
        pl.DataFrame(done)
        .with_columns(pl.col("cell").cast(pl.Int32))
        .join(design, on="point", how="left")
        .join(from_cells, on="cell", how="left")
        .select(
            [
                *keys,
                *coeff,
                "lon",
                "lat",
                *features,
                *targets,
                "restart_year",
                "restart_bytes",
                "truth_stems_total",
            ]
        )
    )


def _decode_parts(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """The three slices every decode number is quoted against: treeless, control, treeless control.

    ⚠ THE CONTROL POINT IS THE CORPUS'S OWN SANITY CHECK, and it is the first number to look at.
    Its forcing is byte-identical to the historical baseline, so a control run should grow roughly
    the forest the stored ground truth holds at that cell. It does NOT have to match exactly -- the
    ground truth ran a 1000-year spin-up plus a historical transient with the real year-by-year
    climate under the 2026-02-05 binary, while this cycles 30 years under the 2026-08-12 one
    (`MEMORY.md:subset-diverges`) -- but a control that is EMPTY where the truth has a forest means
    the corpus is not describing the same model, and no rung-1 score computed on it would mean
    anything.
    """
    treeless = frame.filter(pl.col("stems_total") <= 0)
    control = frame.filter(pl.col("point") == "control")
    return treeless, control, control.filter(pl.col("stems_total") <= 0)


def _report_decode(frame: pl.DataFrame, summary: dict[str, Any], dest: Path) -> None:
    treeless, control, ctrl_treeless = _decode_parts(frame)
    print(f"\ncorpus table: {frame.height} rows x {frame.width} cols in {summary['seconds']} s")
    print(f"  features / targets              {summary['nfeature']} / {summary['ntarget']}")
    print(
        f"  treeless rows (stems_total = 0) {treeless.height}/{frame.height} "
        f"({100 * treeless.height / frame.height:.1f} %)"
    )
    print(
        f"  treeless CONTROL rows           {ctrl_treeless.height}/{control.height} "
        f"({summary['treeless_control_cells_treed_in_ground_truth']} of those cells are "
        "tree-bearing in the stored ground truth)"
    )
    if ctrl_treeless.height:
        print(
            "  ⚠ a control point is byte-identical forcing, so an EMPTY control at a cell the "
            "ground truth holds a forest at is a corpus defect, not a climate response. First "
            f"few: {ctrl_treeless['name'].to_list()[:5]}"
        )
    alive = frame.filter(pl.col("stems_total") > 0)
    for col in ("stems_total", "agb", "vegc", "height_p50", "soilc"):
        qs = "/".join(f"{alive[col].quantile(q):,.3g}" for q in (0.05, 0.5, 0.95))
        print(f"  {col:14s} p5/p50/p95 over the {alive.height} tree-bearing rows  {qs}")
    print(f"  table         {dest}")
    print(f"  corpus_sha256 {summary['corpus_sha256']}")


PFT_FRAC_COLUMNS: tuple[str, ...] = tuple(f"pft_frac_{i}" for i in range(state_mod.NTREE_PFT))


def _differs(a: pl.Series, b: pl.Series) -> npt.NDArray[np.bool_]:
    """Row-wise "not the same value", with NaN equal to NaN and null equal to null."""
    if a.dtype.is_float() and b.dtype.is_float():
        x = a.to_numpy().astype(np.float64)
        y = b.to_numpy().astype(np.float64)
        same = (x == y) | (np.isnan(x) & np.isnan(y))
        return np.asarray(~same, dtype=bool)
    return np.asarray((~a.eq_missing(b)).to_numpy(), dtype=bool)


def compare_tables(
    old: pl.DataFrame, new: pl.DataFrame, old_schema: int, new_schema: int
) -> dict[str, Any]:
    """Every difference between two decodes of the SAME runs, and whether the schema explains it.

    Rows are matched by run `name`, never by position. A difference is EXPECTED only where the two
    schemas say the decoder changed (`vegemu.corpus.schema`): across the 2 -> 3 bump, `pft_frac_*`
    on a treeless row going from 0.0 to NaN, and the five soil columns appearing. Anything else --
    a value that moved, a column that vanished, a dtype that changed -- is a re-decode that did not
    reproduce its source, and the caller refuses it.
    """
    old = old.filter(pl.col("name").is_in(new["name"].implode()))
    if old.height != new.height or old["name"].n_unique() != old.height:
        return {"ok": False, "unexpected": [f"{old.height} source rows match {new.height} new"]}
    a, b = old.sort("name"), new.sort("name")
    bump = old_schema < 3 <= new_schema
    treeless = np.asarray((b["stems_total"] <= 0).to_numpy(), dtype=bool)
    shared = [c for c in a.columns if c in b.columns]
    added = [c for c in b.columns if c not in a.columns]
    dropped = [c for c in a.columns if c not in b.columns]
    unexpected: list[str] = []
    if dropped:
        unexpected.append(f"columns dropped: {dropped}")
    expected_new = set(SOIL_FEATURES) if bump else set()
    if set(added) != expected_new:
        unexpected.append(
            f"columns added {added}, the schema change explains {sorted(expected_new)}"
        )
    differing: dict[str, int] = {}
    for c in shared:
        if a[c].dtype != b[c].dtype:
            unexpected.append(f"{c}: dtype {a[c].dtype} -> {b[c].dtype}")
            continue
        diff = _differs(a[c], b[c])
        if not diff.any():
            continue
        differing[c] = int(diff.sum())
        if not (bump and c in PFT_FRAC_COLUMNS):
            unexpected.append(f"{c}: {int(diff.sum())} rows differ")
            continue
        was, now = a[c].to_numpy()[diff], b[c].to_numpy()[diff]
        if (diff & ~treeless).any() or not (np.isnan(now).all() and (was == 0.0).all()):
            unexpected.append(f"{c}: differs outside 'treeless 0.0 -> NaN'")
    # ...and the fix must have landed on EVERY treeless row, not only on the ones that differ: a
    # schema-3 decode that left a treeless row's share at 0.0 differs from nothing and would pass
    # the loop above, so "only treeless rows changed" would be reported with the fix half-applied.
    if bump:
        for c in PFT_FRAC_COLUMNS:
            if c not in b.columns:
                continue
            kept = int((~np.isnan(b[c].to_numpy().astype(np.float64)[treeless])).sum())
            if kept:
                unexpected.append(
                    f"{c}: {kept} treeless rows are not NaN under schema {new_schema}"
                )
    return {
        "ok": not unexpected,
        "rows": b.height,
        "treeless_rows": int(treeless.sum()),
        "shared_columns": len(shared),
        "identical_columns": len(shared) - len(differing),
        "differing_columns": differing,
        "added_columns": added,
        "dropped_columns": dropped,
        "unexpected": unexpected,
    }


def _claim_out_dir(out: Path, src: Path) -> None:
    """Refuse to write a derived version over anything but an earlier derivation of the SAME source.

    A planned version has spin-ups of its own, so overwriting its provenance with "derived from
    X" would orphan them; and a derivation of a DIFFERENT source would mix two corpora in one name.
    """
    prov = out / "provenance.json"
    if not prov.is_file():
        return
    derived = json.loads(prov.read_text()).get("derived_from")
    if not derived:
        raise SystemExit(f"{out} is a planned version with runs of its own; not overwriting it")
    if derived.get("corpus_dir") != src.name:
        raise SystemExit(f"{out} is derived from {derived.get('corpus_dir')}, not {src.name}")


def _write_derived(
    out: Path,
    src: Path,
    src_prov: dict[str, Any],
    *,
    out_version: str,
    schema: int,
    done: list[dict[str, Any]],
    source_table: Path,
) -> dict[str, Any]:
    """Make `out` a self-describing version whose every row is a re-decode of `src`'s runs.

    The plan tables are COPIED, so `runs.csv` still points at the source's run directories -- that
    is where the restarts are, and a later in-place decode of this version reads the same files.
    Every restart's sha256 goes into `restarts_sha256.csv`, and the digest of that file into the
    provenance, so "the spin-ups are v2-constco2's" is checkable file by file, not a sentence.
    """
    for name in ("cells.csv", "cells.parquet", "design.csv", "runs.csv"):
        if (src / name).is_file():
            shutil.copyfile(src / name, out / name)
    shas = pl.DataFrame(
        sorted(
            ({"name": r["name"], "restart_sha256": r["restart_sha256"]} for r in done),
            key=lambda r: r["name"],
        )
    )
    shas.write_csv(out / "restarts_sha256.csv")
    carried = {
        k: src_prov[k]
        for k in (
            "tier",
            "nrun",
            "ncell",
            "npoint",
            "nspinup",
            "design_seed",
            "design_kind",
            "design_base_npoint",
            "base_window",
            "co2",
            "co2_constant",
            "co2_ppm",
            "co2_file",
            "binary",
            "sources",
            "selection",
            "replicate_of",
            "spinup_note",
            "design_note",
            "plan_sha256",
            "design_sha256",
            "plan_hash_scheme",
        )
        if k in src_prov
    }
    prov: dict[str, Any] = {
        **carried,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_pilot.py --stage decode --out-version",
        "corpus_version": out_version,
        "git_commit": _git_commit(),
        "seed": int(src_prov.get("seed", SEED)),
        "schema": schema,
        "schema_note": schema_mod.SCHEMAS[schema],
        "derived_from": {
            "corpus_dir": src.name,
            "corpus_version": src_prov.get("corpus_version"),
            "no_new_spinups": True,
            "note": (
                f"NO MODEL WAS RUN FOR THIS VERSION. Every row re-decodes a restart and a forcing "
                f"set of {src.name}, under table schema {schema}; `plan_sha256` is that plan's, "
                "because these are that plan's runs."
            ),
            "source_schema": schema_mod.of_provenance(src_prov),
            "provenance_sha256": sha256_of(src / "provenance.json"),
            "runs_csv_sha256": sha256_of(src / "runs.csv"),
            "cells_csv_sha256": sha256_of(src / "cells.csv"),
            "design_csv_sha256": sha256_of(src / "design.csv"),
            "source_table": {"file": source_table.name, "sha256": sha256_of(source_table)}
            if source_table.is_file()
            else None,
            "restarts": {
                "count": shas.height,
                "manifest": "restarts_sha256.csv",
                "manifest_sha256": sha256_of(out / "restarts_sha256.csv"),
            },
        },
    }
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n", "utf-8")
    return dict(prov["derived_from"])


def stage_decode(  # noqa: PLR0912, PLR0915 -- decode, write, derive, compare, report
    version: str,
    nproc: int,
    limit: int | None,
    seed: int = SEED,
    *,
    tier: str = "pilot",
    out_version: str | None = None,
    schema: int | None = None,
) -> int:
    """Decode a version's runs into its table -- in place, or into `out_version` with no new runs.

    ⚠ IN PLACE, THE SCHEMA IS THE VERSION'S OWN AND MAY NOT BE OVERRIDDEN. Its table is pinned by
    hash; decoding it under another schema would overwrite that table with a different one. A new
    schema is a new version: `--out-version`, which defaults to `schema.CURRENT` and diffs the
    result against the source table before calling it decoded.
    """
    src = meta_dir(version, seed, tier)
    src_prov = _read_plan(version, seed, tier)
    src_schema = schema_mod.of_provenance(src_prov)
    full_stem = "corpus" if seed == SEED else f"replicate_s{seed}"
    source_table = src / f"{full_stem}.parquet"
    if out_version is None:
        use = src_schema if schema is None else schema_mod.check(schema)
        if use != src_schema:
            raise SystemExit(
                f"{src.name} is schema {src_schema}; decoding it in place under schema {use} would "
                "overwrite its pinned table with a different one. Use --out-version."
            )
        out = src
    else:
        if out_version == version:
            raise SystemExit("--out-version must differ from --version")
        use = schema_mod.CURRENT if schema is None else schema_mod.check(schema)
        # ⚠ NO SOURCE TABLE, NO RE-DECODE. The column-by-column diff against the source's own table
        # is the only evidence a derived version reproduces its source beyond the schema change; it
        # used to be skipped with `ok: True` when the table was missing, so a re-decode run before
        # the source's own decode came out "DECODED" having been compared with nothing. Checked
        # here, before anything is decoded or any directory is claimed.
        if not source_table.is_file():
            raise SystemExit(
                f"no {source_table}: a re-decode is diffed against its source's own table, and "
                f"{src.name} has none. Decode it in place first (--stage decode"
                f"{'' if tier == 'pilot' else f' --tier {tier}'} --version {version}"
                f"{'' if seed == SEED else f' --seed {seed}'}), then re-run this."
            )
        out = meta_dir(out_version, seed, tier)
        _claim_out_dir(out, src)
    runs = pl.read_csv(src / "runs.csv")
    design = pl.read_csv(src / "design.csv")
    cells = pl.read_csv(src / "cells.csv")
    if limit:
        runs = runs.head(limit)

    jobs: list[DecodeJob] = [
        (str(n), int(c), str(p), str(r), str(f), seed, use)
        for n, c, p, r, f in zip(
            runs["name"].to_list(),
            runs["cell"].to_list(),
            runs["point"].to_list(),
            runs["run_dir"].to_list(),
            runs["forcing"].to_list(),
            strict=True,
        )
    ]
    target = f" into {out.name}" if out != src else ""
    print(
        f"decoding {len(jobs)} runs of {src.name} (tier {tier}, seed {seed}){target} under table "
        f"schema {use} on {nproc} processes",
        flush=True,
    )

    t0 = time.time()
    done, failed = _decode_all(jobs, nproc)
    if failed:
        print(f"⚠ {len(failed)} runs FAILED to decode:", file=sys.stderr)
        for f in failed[:5]:
            print(f"  {f['name']}:\n{f['error']}", file=sys.stderr)
    if not done:
        print("no run decoded; nothing to write", file=sys.stderr)
        return 1

    features = climate_mod.climate_features(use)
    frame = _corpus_frame(done, design, cells, features)
    bad_year = frame.filter(pl.col("restart_year") != STATE_YEAR).height
    if bad_year:
        raise AssertionError(
            f"{bad_year} restarts are not labelled year {STATE_YEAR}; the window a row's climate "
            "summary covers would not be the window its state came from"
        )

    # A smoke run writes its own filenames. `is_smoke` in the JSON is not enough on its own: the
    # table is the artefact a pre-registration cites by hash, and a 30-row file sitting at the name
    # the corpus lives under is one `--limit` away from being cited as the corpus.
    #
    # A REPLICATE IS NAMED APART FOR THE SAME REASON, and it is the stronger case: its rows are the
    # same cells and the same climates as the corpus, so a table called `corpus.parquet` holding
    # them is one path typo away from doubling the pilot with re-runs and calling it more evidence.
    # It is a second measurement of the same thing, which is a SPREAD, never extra rows.
    # (`full_stem` is fixed above, where a re-decode checks its source table exists.)
    stem = "corpus_smoke" if limit else full_stem
    dest = out / f"{stem}.parquet"
    frame.write_parquet(dest)
    treeless, control, ctrl_treeless = _decode_parts(frame)
    truth_treed = ctrl_treeless.filter(pl.col("truth_stems_total") > 0).height

    derived: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    if out != src:
        derived = _write_derived(
            out,
            src,
            src_prov,
            out_version=str(out_version),
            schema=use,
            done=done,
            source_table=source_table,
        )
        comparison = compare_tables(pl.read_parquet(source_table), frame, src_schema, use)
        comparison["byte_identical"] = sha256_of(source_table) == sha256_of(dest)

    summary: dict[str, Any] = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "built_by": "scripts/corpus_pilot.py --stage decode",
        "tier": tier,
        "corpus_version": out_version or version,
        "schema": use,
        "plan_sha256": src_prov["plan_sha256"],
        "git_commit": _git_commit(),
        "seed": seed,
        "is_replicate": seed != SEED,
        "is_smoke": limit is not None,
        "limit": limit,
        "rows": frame.height,
        "cols": frame.width,
        "runs_promised": runs.height,
        "runs_failed": len(failed),
        "failures": failed,
        "seconds": round(time.time() - t0, 1),
        "nfeature": len(features),
        "ntarget": len(state_mod.STATE_COLUMNS) - 1,
        "state_year": STATE_YEAR,
        "state_year_note": (
            "the label LPJmL-FIT writes on a spin-up restart, not a date: the state is the end of "
            f"{NSPINUP} years CYCLING the {perturb_window()[0]}-{perturb_window()[1]} forcing"
        ),
        "treeless_rows": treeless.height,
        "treeless_control_rows": ctrl_treeless.height,
        "control_rows": control.height,
        "treeless_control_cells_treed_in_ground_truth": truth_treed,
        "corpus_sha256": sha256_of(dest),
        # ⚠ This used to say "untouched" whatever the plan was -- the word that hid a CO2 ramp for
        # a week. It now states the plan's CO2 forcing, and that it is never a feature.
        "co2": f"{src_prov['co2']} -- as planned; never a feature (MEMORY.md:co2-closed)",
        "derived_from": derived,
        "comparison_to_source": comparison,
    }
    report = out / ("decode_smoke.json" if limit else f"decode_s{seed}.json")
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    _report_decode(frame, summary, dest)
    if comparison is not None:
        print(
            f"  vs {src.name}: {comparison.get('identical_columns')} of "
            f"{comparison.get('shared_columns')} shared columns identical over "
            f"{comparison.get('rows')} rows; differing {comparison.get('differing_columns')}; "
            f"added {comparison.get('added_columns')}; byte-identical "
            f"{comparison.get('byte_identical')}"
        )
        for item in comparison.get("unexpected", []):
            print(f"  ⚠ UNEXPLAINED DIFFERENCE: {item}", file=sys.stderr)
    if failed:
        print("verdict: INCOMPLETE -- fix the failures before any score cites this table")
        return 1
    if comparison is not None and not comparison["ok"]:
        print("verdict: REFUSED -- the re-decode differs from its source beyond the schema change")
        return 1
    if seed != SEED:
        print(
            f"verdict: DECODED -- a REPLICATE of seed {SEED} at the same cells and climates. Pair "
            "it with the corpus to get the model's own two-run spread; never append it as rows."
        )
        return 0
    print("verdict: DECODED -- this table is what rung 1 is scored on")
    return 0


def perturb_window() -> tuple[int, int]:
    return tuple(_load("corpus_perturb_clm").BASE_WINDOW)  # type: ignore[return-value]


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--stage", choices=("plan", "build", "verify", "harvest", "decode"), required=True
    )
    ap.add_argument("--version", default="v1", help="corpus version; a new design is a new version")
    ap.add_argument(
        "--tier",
        choices=sorted(TIERS),
        default="pilot",
        help=(
            "which tier's defaults and directory tree (<tier>-<version>). Every stage of one "
            "campaign must be given the same tier; `mid` = 1,000 cells x 100 climates, constant "
            "CO2, nested in pilot-v2-constco2"
        ),
    )
    ap.add_argument("--ncell", type=int, default=None, help="plan stage; default: the tier's")
    ap.add_argument(
        "--npoint",
        type=int,
        default=None,
        help="plan stage; default: the tier's. the build reads the plan's, refusing a clash",
    )
    ap.add_argument(
        "--design",
        choices=("pilot", "nested"),
        default=None,
        help="plan stage: `nested` keeps the pilot's 30 climates and extends them; default: tier's",
    )
    ap.add_argument(
        "--nest-in",
        default=None,
        help=(
            "plan stage: a corpus directory (e.g. pilot-v2-constco2) whose cells must all be in "
            "the selection, and whose design a nested design must reproduce. `none` disables the "
            "tier default"
        ),
    )
    ap.add_argument(
        "--max-per-tile",
        type=int,
        default=None,
        help="plan stage: per-tile cap; default scales with --ncell (select.tile_cap)",
    )
    ap.add_argument("--shard-size", type=int, default=SHARD_SIZE, help="runs per SLURM job")
    ap.add_argument("--shard", type=int, default=0, help="build stage: which slice of cells")
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")),
        help="build and decode stages: worker processes; defaults to the job's own cpus-per-task",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="decode stage: first N runs only -- a smoke test, never a corpus",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=(
            f"LPJmL-FIT's random_seed. {SEED} is the corpus itself and keeps its existing paths; "
            "anything else is a REPLICATE -- its own directory tree, seed 1's forcing reused "
            "unmodified, and a table named replicate_s<n>.parquet that must never be appended to "
            "the corpus. A replicate is what measures the model's own two-run spread."
        ),
    )
    ap.add_argument(
        "--const-co2",
        dest="const_co2",
        action="store_const",
        const=True,
        default=None,
        help=(
            "drive the spin-up with a CONSTANT CO2 file instead of the ground truth's transient "
            "one. Without this the last 300 of the 1000 spin-up years carry the historical CO2 "
            "rise, so the end state is not an equilibrium. A new corpus VERSION, never an edit. "
            "Plan stage only needs it; a later stage reads it from the plan and refuses a clash."
        ),
    )
    ap.add_argument(
        "--transient-co2",
        dest="const_co2",
        action="store_const",
        const=False,
        help="the explicit opposite of --const-co2, for a tier whose default is constant",
    )
    ap.add_argument(
        "--co2-ppm",
        type=float,
        default=None,
        help=(
            "constant CO2 at this level instead of 276.59 ppm (implies --const-co2). The file "
            "then starts at model year 1000, so no spin-up year falls back to the model's own "
            "276.59 clamp"
        ),
    )
    ap.add_argument(
        "--out-version",
        default=None,
        help=(
            "decode stage: write the table as a NEW version from --version's existing runs, under "
            "the current table schema, and diff it against the source table. No spin-up is run"
        ),
    )
    ap.add_argument(
        "--schema",
        type=int,
        default=None,
        help="decode stage: table schema (vegemu.corpus.schema); in place it must be the version's",
    )
    ap.add_argument(
        "--subset",
        type=int,
        default=0,
        help=(
            "plan stage: run an EVENLY SPACED N cells of the selection (0 = all). A stride over "
            "the same list, never a re-selection and never a prefix -- the list is ordered south "
            "to north, so a prefix is one latitude band."
        ),
    )
    args = ap.parse_args()
    tier = TIERS[args.tier]
    cli_co2 = co2_from_cli(args.const_co2, args.co2_ppm)

    if args.stage == "plan":
        nest_in = tier.nest_in if args.nest_in is None else args.nest_in
        return stage_plan(
            args.version,
            args.ncell or tier.ncell,
            args.npoint or tier.npoint,
            args.shard_size,
            seed=args.seed,
            subset=args.subset,
            co2=cli_co2 or co2_from_cli(tier.const_co2, None),
            tier=args.tier,
            design_kind=args.design or tier.design,
            nest_in=None if nest_in in (None, "", "none") else nest_in,
            max_per_tile=args.max_per_tile,
        )
    if args.stage == "build":
        return stage_build(
            args.version,
            args.workers,
            args.shard,
            args.nshard,
            args.npoint,
            seed=args.seed,
            co2=cli_co2,
            tier=args.tier,
        )
    if args.stage == "verify":
        return stage_verify(args.version, args.seed, args.tier)
    if args.stage == "decode":
        return stage_decode(
            args.version,
            args.workers,
            args.limit,
            args.seed,
            tier=args.tier,
            out_version=args.out_version,
            schema=args.schema,
        )
    return stage_harvest(args.version, args.seed, args.tier)


if __name__ == "__main__":
    raise SystemExit(main())
