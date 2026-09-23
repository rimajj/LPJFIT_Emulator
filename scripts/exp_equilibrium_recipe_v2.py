#!/usr/bin/env python
"""THE CONFIRMATION of the recipe the dev screen chose, on the folds the choice never saw.

    scripts/exp_equilibrium_recipe_v2.py --arm nulls --out <dir>            # safe before the seal
    scripts/exp_equilibrium_recipe_v2.py --arm model --exp-id <id> --out <dir>

THE QUESTION. `X-20260923-equilibrium-from-climate` showed that the settled forest is learnable
from the 30-year climate and the soil alone (0.608 mean variance explained at held-out 15-degree
tiles). `scripts/screen_equilibrium_map.py` then screened recipes on folds 0-2 ONLY and chose one
by a rule fixed before it ran. This asks whether that recipe, on the cells of folds 3 and 4 --
each predicted by a model trained on the other four folds, the sealed construction restricted to
those rows -- beats the best information-free competitor by the bar the sealed rule gives there.

THE RECIPE IS READ FROM THE PRE-REGISTRATION (`recipe:`), so the sealed hash covers it: the feature
set, the target form, the LightGBM settings, the bag size and whether the trait heads get two-stage
inputs. The daily-forcing feature table it needs is pinned by its sha256 in the same file, and the
run refuses a table that does not hash to it.

EVERYTHING ELSE IS THE SEALED APPARATUS, imported: loader, quantities, transforms, skill and band
arithmetic, nulls, folds. The sealed recipe's own held-out score is reported beside the model and
never decided on.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import yaml

from exp_equilibrium_map import NULLS, ceiling
from screen_equilibrium_map import HELD_FOLDS, Engine, Recipe, bar_rule, load_data, nulls_on, score
from vegemu.paths import paths, repo_root
from vegemu.results import append_result_block

STATISTIC = "skill_equilibrium_heldout_mean"
DEFAULT_EXP = "X-20260924-equilibrium-recipe-v2"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recipe_from(prereg: dict[str, Any]) -> Recipe:
    """The pre-registered recipe, field by field. An unknown or missing field is an error."""
    spec = dict(prereg["recipe"])
    fields = {"name", "v3", "soil", "target", "params", "bag", "stage2"}
    if set(spec) != fields:
        raise ValueError(f"recipe fields {sorted(spec)} != {sorted(fields)}")
    params = tuple(sorted((str(k), v) for k, v in (spec["params"] or {}).items()))
    return Recipe(
        name=str(spec["name"]),
        v3=bool(spec["v3"]),
        soil=bool(spec["soil"]),
        target=str(spec["target"]),
        params=params,
        bag=int(spec["bag"]),
        stage2=bool(spec["stage2"]),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--exp-id", default=DEFAULT_EXP)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    prereg = yaml.safe_load(
        (repo_root() / "experiments" / args.exp_id / "preregistration.yaml").read_text()
    )
    recipe = recipe_from(prereg)
    v3_table = Path(str(prereg["data"]["features_v3"]["path"]))
    want = str(prereg["data"]["features_v3"]["sha256"])
    got = _sha256(v3_table)
    if got != want:
        raise SystemExit(f"{v3_table} hashes to {got}, the pre-registration pins {want}")
    threshold = float(str(prereg["decision_rule"]["pass_if"]).split(">")[-1])

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    d = load_data(str(prereg["data"]["version"]), v3_table, 15.0)
    held = np.isin(d.folds, HELD_FOLDS)
    report: dict[str, Any] = {
        "exp_id": args.exp_id,
        "arm": args.arm,
        "statistic": STATISTIC,
        "recipe": {**dataclasses.asdict(recipe), "params": dict(recipe.params)},
        "features_v3_sha256": got,
        "scored_cells": int(held.sum()),
        "scored_rows": int(held.sum() * d.y.shape[1]),
        "nulls": nulls_on(d, held),
    }
    report["bar"] = bar_rule(report["nulls"])
    for n, a in report["nulls"].items():
        print(f"  {n:20s} {a['pooled']:+.6f}   band conj {a['band']['conjunctive']:.4f}")

    if args.arm == "nulls":
        root = Path(str(paths()["scratch"]["corpus"]))
        report["ceiling"] = ceiling(
            d.soil_bin,
            root / "pilot-v1" / "corpus.parquet",
            root / "pilot-v1-s2" / "replicate_s2.parquet",
            d.y[held],
        )
        (out / "nulls.json").write_text(json.dumps(report, indent=2, default=float))
        print(f"wrote {out / 'nulls.json'}")
        return 0

    eng = Engine(d, args.workers)
    model = score(d, eng.predict(recipe, "held"), held)
    sealed_recipe = score(d, eng.predict(Recipe("sealed recipe"), "held"), held)
    report["model"] = model
    report["sealed_recipe_beside"] = sealed_recipe
    best = max(NULLS, key=lambda n: report["nulls"][n]["pooled"])
    margin = model["pooled"] - report["nulls"][best]["pooled"]
    report["decision"] = {
        "best_null": best,
        "margin": margin,
        "threshold": threshold,
        "verdict": "pass" if margin > threshold else "fail",
    }
    print(f"  model {model['pooled']:+.6f}  sealed recipe {sealed_recipe['pooled']:+.6f}")
    print(f"  margin {margin:+.6f} vs {threshold}: {report['decision']['verdict']}")
    report.update(
        append_result_block(
            statistic=STATISTIC,
            arms={
                "model": float(model["pooled"]),
                **{n: float(report["nulls"][n]["pooled"]) for n in NULLS},
            },
            n=int(report["scored_rows"]),
        )
    )
    (out / "metrics.json").write_text(json.dumps(report, indent=2, default=float))
    print(f"wrote {out / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
