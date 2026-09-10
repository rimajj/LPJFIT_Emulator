"""A leg whose two "seeds" are one run twice must fail the build, not be recorded in it.

WHY THIS TEST EXISTS. Corpus v0's high-emissions leg had two seed tables that were byte-identical --
same RNG triple, same numbers, all 67,420 cells -- because the second run started from the first
run's restart and LPJmL-FIT reads its seeds from the restart it starts from. The builder recorded
that faithfully in `provenance.json` and said nothing, and three pre-registrations went on to cite
the corpus; one of them declared a two-seed mean for a leg that only ever had one draw
(`docs/decisions/20260908-X-ssp370-has-no-second-seed.md`).

The damage is specific and invisible: the acceptance tolerance is `max(10 %, |s1-s2|/|mean|)`, so
with `s1 == s2` it collapses to exactly the 10 % floor in every cell while still reading as "10 %
or the model's own spread". A band from such a leg is the floor wearing the band's name.

So what is asserted here is not that the defect is *detected* -- v0 detected it -- but that it is
REFUSED: `corpus_sha256` is withheld, because that hash is the only handle a pre-registration has.

These tests build no corpus. They exercise the checker on hand-made frames, so they run anywhere
and assert the classification rather than a property of this cluster's files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from corpus_build import check_seeds_differ  # noqa: E402

TRIPLE_A = [10901, 14779, 51459]
TRIPLE_B = [22307, 41011, 60623]


def frame(stems: list[float], agb: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"cell": list(range(len(stems))), "stems_per_patch": stems, "agb": agb})


def bases(triple1: list[int], triple2: list[int]) -> dict[int, dict[str, object]]:
    return {1: {"seed": triple1}, 2: {"seed": triple2}}


def test_two_genuine_runs_pass() -> None:
    """The normal case: different seeds, numbers that differ by the model's own noise."""
    a = frame([12.0, 8.0, 3.0], [140.0, 90.0, 20.0])
    b = frame([12.4, 7.6, 3.1], [143.0, 88.0, 21.0])
    v = check_seeds_differ({1: a, 2: b}, bases(TRIPLE_A, TRIPLE_B))
    assert v["ok"], v["reason"]
    assert v["cells_differing"] == 3
    assert v["cells_compared"] == 3


def test_the_same_run_twice_is_refused() -> None:
    """Corpus v0's actual defect: identical tables AND an identical recorded triple."""
    a = frame([12.0, 8.0, 3.0], [140.0, 90.0, 20.0])
    v = check_seeds_differ({1: a, 2: a.clone()}, bases(TRIPLE_A, TRIPLE_A))
    assert not v["ok"]
    assert v["cells_differing"] == 0
    assert "same RNG triple" in v["reason"]
    assert "equal in all" in v["reason"]


def test_identical_numbers_alone_are_enough_to_refuse() -> None:
    """The effect is checked independently of the cause: a triple can be recorded wrongly."""
    a = frame([12.0, 8.0], [140.0, 90.0])
    v = check_seeds_differ({1: a, 2: a.clone()}, bases(TRIPLE_A, TRIPLE_B))
    assert not v["ok"]
    assert "equal in all" in v["reason"]


def test_an_identical_triple_alone_is_enough_to_refuse() -> None:
    """The cause is checked independently of the effect: same seeds cannot be two realisations.

    Numbers that differ despite an identical triple mean something ELSE differed -- a different
    binary build, a different forcing -- which is a worse problem than the one being screened for,
    not a lesser one. Either way the pair is not two draws of the same distribution.
    """
    a = frame([12.0, 8.0], [140.0, 90.0])
    b = frame([12.4, 7.6], [143.0, 88.0])
    v = check_seeds_differ({1: a, 2: b}, bases(TRIPLE_A, TRIPLE_A))
    assert not v["ok"]
    assert "same RNG triple" in v["reason"]


def test_a_missing_seed_is_refused_rather_than_skipped() -> None:
    """A leg built from one seed has no spread at all; silence there is how v0 happened."""
    a = frame([12.0, 8.0], [140.0, 90.0])
    v = check_seeds_differ({1: a}, {1: {"seed": TRIPLE_A}})
    assert not v["ok"]
    assert "cannot be checked" in v["reason"]


def test_no_overlapping_cells_is_no_evidence_not_agreement() -> None:
    """Zero cells compared must never read as a pass -- an empty check is the emptiest claim."""
    a = pl.DataFrame({"cell": [0, 1], "stems_per_patch": [12.0, 8.0]})
    b = pl.DataFrame({"cell": [7, 8], "stems_per_patch": [12.0, 8.0]})
    v = check_seeds_differ({1: a, 2: b}, bases(TRIPLE_A, TRIPLE_B))
    assert not v["ok"]
    assert "no cell in common" in v["reason"]
