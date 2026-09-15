#!/usr/bin/env python
"""How much does LPJmL-FIT disagree with ITSELF when the climate is perturbed?

    scripts/sbatch_py.sh X-perturbed-spread scripts/exp_measure_perturbed_spread.py \\
        --seed1 /p/tmp/jamirp/vegemu/corpus/pilot-v1/corpus.parquet \\
        --seed2 /p/tmp/jamirp/vegemu/corpus/pilot-v1-s2/replicate_s2.parquet \\
        --out  /p/tmp/jamirp/vegemu/exp/X-perturbed-spread

WHY THIS NUMBER DECIDES FIVE THINGS AT ONCE. The acceptance tolerance is
`max(10 %, the model's own two-run spread)`. That spread has only ever been measured on PRESENT-DAY
climate, where its median is exactly 0.100 -- i.e. it never exceeds the floor, so the tolerance is
the floor wearing the spread's name. Nobody has ever run two seeds of a PERTURBED spin-up, and the
acceptance criterion itself puts the spread at up to 29 % in low-density cells. Everything below
turns on which of those two numbers is right:

  1. IS THE EMITTED-RESTART EXPERIMENT (X4) SEALABLE? Its nulls collapse at a 0.10 floor -- pure
     chance ties for first and a cell's own unedited forest ranks BELOW chance -- and they snap into
     the order physics predicts at 0.15 and above. Line X's arithmetic is already done both ways:
     near 0.29, X4 seals with best null 0.066379, a valid threshold of 0.02 and a bar of 0.086
     against an attainable 0.895. Near 0.10, the conjunctive level statistic is the wrong instrument
     and X4 needs a new estimand.
  2. THE ADDITIVE FLOOR for composition (`ABS_FLOOR`), which has to be MEASURED and pre-registered
     with the value it must return, and which must not inherit 0.10 (that would blind the test to
     53.9 % of genuinely present tree types).
  3. THE CEILING of the warming-response test, today a lower bound of 0.869730 quoted as such.
  4. THE CEILING of the composition test, today a lower bound of 0.863852.
  5. THE 2.7 % SOIL-CARBON OFFSET -- noise, or a real bias?

⚠ WHAT IS AND IS NOT COMPARABLE HERE. Both tables are the same 20 cells, the same 30 climates, the
same config and the SAME forcing bytes, differing only in `random_seed`. So a difference between
them is the model's own stochasticity and nothing else. It is 20 of the pilot's 200 cells, chosen as
an evenly spaced stride over a south-to-north ordering, so it spans 52 S to 66 N -- but it is 20
cells, and every number here is quoted on that basis.

⚠ AND THE SPREAD IS REPORTED UNFLOORED. `score.relative_spread` applies `max(FLOOR, ...)` because
that is the acceptance band's definition, and a floored spread cannot answer "is the spread above
the floor?" -- the question this script exists to answer. The floored version is reported too,
beside it, because that is what a band actually uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.score import (
    COMPOSITION_QUANTITIES,
    FLOOR,
    SCORED_CONJUNCTIVE,
    blank_treeless_composition,
    relative_spread,
)

KEY = ("cell", "point")


def paired(seed1: pl.DataFrame, seed2: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """The rows both seeds have, aligned on (cell, point). An inner join, and the count is reported.

    ⚠ ALIGNED BY KEY, NEVER BY ROW ORDER. The two tables are written by separate jobs over separate
    manifests; identical ordering is an accident waiting to stop being true, and a silent misalign
    here would report the spread between DIFFERENT cells as the model's own noise -- a number that
    would be large, plausible, and completely wrong.
    """
    a = seed1.select([*KEY, *cols]).rename({c: f"{c}__s1" for c in cols})
    b = seed2.select([*KEY, *cols]).rename({c: f"{c}__s2" for c in cols})
    return a.join(b, on=list(KEY), how="inner")


def spreads(
    pair: pl.DataFrame, cols: list[str]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Unfloored relative spread, floored relative spread, and absolute difference. Flattened."""
    rel: list[npt.NDArray[np.float64]] = []
    flo: list[npt.NDArray[np.float64]] = []
    absd: list[npt.NDArray[np.float64]] = []
    for c in cols:
        s1 = pair[f"{c}__s1"].to_numpy().astype(np.float64)
        s2 = pair[f"{c}__s2"].to_numpy().astype(np.float64)
        denom = np.abs(0.5 * (s1 + s2))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(denom > 0, np.abs(s1 - s2) / denom, np.nan)
        rel.append(r)
        flo.append(relative_spread(s1, s2, FLOOR))
        absd.append(np.abs(s1 - s2))
    return np.concatenate(rel), np.concatenate(flo), np.concatenate(absd)


def describe(x: npt.NDArray[np.float64], label: str) -> dict[str, Any]:
    good = x[np.isfinite(x)]
    if good.size == 0:
        return {"label": label, "n": 0}
    q = {f"p{p}": float(np.percentile(good, p)) for p in (5, 25, 50, 75, 90, 95, 99)}
    return {
        "label": label,
        "n": int(good.size),
        "n_nan": int(x.size - good.size),
        "mean": float(good.mean()),
        **q,
        "frac_above_floor": float((good > FLOOR).mean()),
    }


def line(d: dict[str, Any]) -> str:
    if not d.get("n"):
        return f"  {d['label']:<34s}  (no finite values)"
    return (
        f"  {d['label']:<34s} n={d['n']:>6d}  median {d['p50']:.4f}  "
        f"p90 {d['p90']:.4f}  p99 {d['p99']:.4f}  above-floor {d['frac_above_floor']:.3f}"
    )


def report_composition(s1: pl.DataFrame, s2: pl.DataFrame, report: dict[str, Any]) -> None:
    """Composition in ABSOLUTE share units, which is the unit an additive floor must be measured in.

    Treeless rows are blanked first: a share of 0.0 where there is no forest is not a share,
    and as a difference it would report a cell's death as a disagreement about species.
    """
    comp = [c for c in COMPOSITION_QUANTITIES if c in s1.columns and c in s2.columns]
    cpair = paired(blank_treeless_composition(s1), blank_treeless_composition(s2), comp)
    _, _, cabs = spreads(cpair.filter(pl.col("point") != "control"), comp)
    dabs = describe(cabs, "composition |s1-s2| (absolute)")
    report["composition_absolute_perturbed"] = dabs
    print("\n=== composition spread in ABSOLUTE share units -- this is what ABS_FLOOR must be ===")
    print(line(dabs))
    if dabs.get("n"):
        print(f"  candidate ABS_FLOOR (p90 of the absolute disagreement) = {dabs['p90']:.4f}")


def report_soilc(per: pl.DataFrame, conj: list[str], report: dict[str, Any]) -> None:
    """Is the 2.7 % soil-carbon offset inside the model's own noise, or a real bias?"""
    if "soilc" not in conj:
        return
    rel_s, _, _ = spreads(per, ["soilc"])
    d = describe(rel_s, "soilc, perturbed")
    report["soilc_perturbed"] = d
    print("\n=== soil carbon alone (the 2.7 % offset asked about) ===")
    print(line(d))
    if d.get("n"):
        verdict = "INSIDE" if d["p50"] >= 0.027 else "OUTSIDE"
        print(f"  a 2.7 % offset is {verdict} the model's own median spread of {d['p50']:.4f}")


def report_decision(report: dict[str, Any]) -> None:
    """The branch this job was run to take, stated before the values were seen."""
    perturbed = report["unfloored__PERTURBED climates"]
    if not perturbed.get("n"):
        return
    med = perturbed["p50"]
    print("\n=== what this decides ===")
    print(f"  perturbed median unfloored spread   {med:.4f}")
    print(f"  fraction of cell-quantities > 0.10  {perturbed['frac_above_floor']:.3f}")
    if med >= 0.15:
        print("  -> ABOVE the floor. The acceptance band is genuinely wider than 10 % under")
        print("     perturbation, so the conjunctive level statistic has power and X4 is")
        print("     sealable on the arithmetic line X has already done.")
    else:
        print("  -> AT OR NEAR the floor. The band does not widen under perturbation, so the")
        print("     conjunctive level statistic stays powerless and X4 needs a NEW ESTIMAND,")
        print("     not a new corpus. Do not widen the floor to rescue it -- that is a choice")
        print("     made after seeing the values.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed1", required=True)
    ap.add_argument("--seed2", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    s1 = pl.read_parquet(args.seed1)
    s2 = pl.read_parquet(args.seed2)
    # The replicate covers a subset of the corpus's cells, so restrict seed 1 to it before anything
    # is counted -- otherwise every "n" below describes the corpus and not the pair.
    cells = sorted(set(int(c) for c in s2["cell"].to_list()))
    s1 = s1.filter(pl.col("cell").is_in(cells))

    print(f"seed 1: {s1.height} rows   seed 2: {s2.height} rows   over {len(cells)} cells")

    conj = [c for c in SCORED_CONJUNCTIVE if c in s1.columns and c in s2.columns]
    missing = [c for c in SCORED_CONJUNCTIVE if c not in conj]
    if missing:
        print(f"⚠ absent from one of the tables and therefore NOT scored: {missing}")
    print(f"conjunctive quantities scored: {len(conj)} of {len(SCORED_CONJUNCTIVE)}")

    pair = paired(s1, s2, conj)
    print(f"paired (cell, point) rows: {pair.height} of {s2.height} the replicate holds")

    # THE SPLIT THAT IS THE WHOLE POINT: the control point is present-day climate, which is where
    # the spread has been measured before. Everything else is a PERTURBED climate, which is what has
    # never been measured and what the acceptance band is actually applied to.
    ctl = pair.filter(pl.col("point") == "control")
    per = pair.filter(pl.col("point") != "control")

    report: dict[str, Any] = {
        "basis": (
            f"{len(cells)} cells x 30 climates, pilot v1, seeds 1 and 2, identical forcing bytes. "
            "A stride over the 200-cell selection, spanning 52 S to 66 N. 20 of 200 cells."
        ),
        "n_cells": len(cells),
        "n_paired_rows": pair.height,
        "quantities_conjunctive": conj,
        "floor": FLOOR,
    }

    print("\n=== relative two-seed spread, UNFLOORED (the question: is it above 0.10?) ===")
    for label, frame in (
        ("control (present-day)", ctl),
        ("PERTURBED climates", per),
        ("all", pair),
    ):
        rel, flo, _ = spreads(frame, conj)
        d = describe(rel, f"{label} unfloored")
        report[f"unfloored__{label}"] = d
        print(line(d))
        df = describe(flo, f"{label} floored")
        report[f"floored__{label}"] = df
        print(line(df))

    report_composition(s1, s2, report)
    report_soilc(per, conj, report)

    (out / "spread.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")
    print(f"\nwrote {out / 'spread.json'}")
    report_decision(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
