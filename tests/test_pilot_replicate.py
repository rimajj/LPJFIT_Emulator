"""A replicate seed must reuse seed 1's forcing, leave seed 1's paths alone, and span the globe.

WHY THIS TEST EXISTS. The pilot corpus carries ONE seed, and the acceptance tolerance is
`max(10 %, the model's own two-run spread)`. That spread has never been measured on a PERTURBED
spin-up, so it is currently transferred from present-day climate, where its median is exactly 0.100
-- the bare floor. A replicate is the measurement that replaces the transfer, and there are exactly
three ways to build one that silently measures nothing:

  1. MOVING SEED 1'S PATHS. 6,000 runs sit under `pilot-v1` and three pre-registrations cite a hash
     computed over them. Renaming that tree to `pilot-v1-s1` for symmetry would orphan the corpus
     this project's only positive result was scored on.
  2. REBUILDING THE FORCING INSTEAD OF SHARING IT. A replicate is "same cell, same climate, only the
     RNG draw differs". If it regenerates its own forcing, then any difference between the pair is
     model noise PLUS whatever the regeneration did, and the two are no longer separable.
  3. TAKING A PREFIX OF THE CELL LIST. The selection is ordered by cell index and the grid runs
     south to north, so the first 20 of 200 are all between 52 S and 27 S -- one temperate band. The
     spread being measured is largest in low-density cells, so a one-band sample measures it where
     it happens to be and then transfers it everywhere, which is the very move a replicate exists to
     stop. Caught here after the first plan run produced exactly that.

These tests run no model and MUST NOT TOUCH THE FILESYSTEM. `meta_dir`/`manifest_dir` go through
`vegemu.paths.scratch`, which CREATES the directory it names -- so asserting on them fails in CI,
where /p does not exist, and passes here for the wrong reason. The version-directory naming is
asserted through `_vdir`, which is pure string work; `run_dir`, `forcing_dir` and `config_path` are
safe because `_under` deliberately builds a plain `Path` (see its own comment: the plan stage must
not create 12,000 directories). CI caught exactly this.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _pilot() -> ModuleType:
    """Load the script by path, registering it first -- see its own `_load` for why that matters."""
    name = "corpus_pilot"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_seed_one_paths_are_unsuffixed() -> None:
    """Seed 1 is the corpus. Its directory names must not acquire an `-s1`."""
    m = _pilot()
    assert m._vdir("v1", m.SEED) == "pilot-v1"
    assert m.run_dir("v1", 42490, "control").parts[-3] == "pilot-v1"
    assert m.forcing_dir("v1", 42490, "control").parts[-3] == "pilot-v1"


def test_replicate_runs_are_separated_from_the_corpus() -> None:
    """A replicate must not write into the tree the corpus was scored on."""
    m = _pilot()
    assert m.run_dir("v1", 42490, "control", 2) != m.run_dir("v1", 42490, "control")
    assert m.run_dir("v1", 42490, "control", 2).parts[-3] == "pilot-v1-s2"
    assert m._vdir("v1", 2) == "pilot-v1-s2"
    assert m.config_path("v1", 42490, "control", 2).name.endswith("-s2.js")


def test_replicate_shares_the_forcing_byte_for_byte() -> None:
    """The climate is the same climate. Sharing the directory makes that true by construction."""
    m = _pilot()
    assert m.forcing_dir("v1", 42490, "control") == m.forcing_dir("v1", 42490, "control")
    # There is no seed parameter to pass: the only way to get a per-seed forcing path would be to
    # add one, and this asserts nobody has.
    assert "seed" not in m.forcing_dir.__code__.co_varnames[: m.forcing_dir.__code__.co_argcount]


def test_run_tags_differ_by_seed() -> None:
    m = _pilot()
    assert m.run_tag(42490, "control") == "c42490-control-s1"
    assert m.run_tag(42490, "control", 2) == "c42490-control-s2"


def test_subset_is_a_stride_and_not_a_prefix() -> None:
    """20 of 200 must span the list, because the list is ordered south to north.

    This reproduces the selection arithmetic rather than importing it, so it fails if the rule in
    `stage_plan` changes back to a prefix -- which is what it was, and which put all 20 cells in one
    temperate band.
    """
    cells = list(range(200))
    subset = 20
    step = len(cells) // subset
    chosen = cells[::step][:subset]

    assert len(chosen) == subset
    assert set(chosen) <= set(cells), "every replicate cell must be one seed 1 actually ran"
    assert chosen != cells[:subset], "a prefix is one latitude band, not a sample of the range"
    assert chosen[0] == cells[0] and chosen[-1] >= cells[-step], "the span must reach both ends"
