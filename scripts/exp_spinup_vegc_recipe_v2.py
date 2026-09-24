#!/usr/bin/env python
"""THE CONFIRMATION of the recipe the spin-up screen chose, on the folds the choice never saw.

    scripts/exp_spinup_vegc_recipe_v2.py --arm nulls --nulls-pool spinup --out <dir>   # any time
    scripts/exp_spinup_vegc_recipe_v2.py --arm model --out <dir>             # after the seal

THE QUESTION. `X-20260924-spinup-vegc-from-spinup` measured, on all 56,986 cells of the stored
constant-CO2 spin-up, that a climate-only map with the sealed inputs and learner lands inside the
acceptance band far less often than a second run of the model (D = -0.432). The dev screen
(`scripts/screen_spinup_vegc.py`) then chose a recipe using the cells of folds 0-2 ONLY. This asks
whether that recipe, on the scored cells of folds 3 and 4 -- each predicted by a model trained on
the cells of the other four folds, the sealed construction restricted to those cells -- is as good
as a rerun there: D = frac(recipe) - frac(rerun) >= -0.02, the rerun reference restricted to the
same cells.

THE RECIPE IS READ FROM THE PRE-REGISTRATION (`recipe:`), so the sealed hash covers it, and the
two daily-forcing feature tables it reads are pinned there by sha256; the run refuses a table that
does not hash to its pin.

EVERYTHING ELSE IS THE SEALED APPARATUS, imported: the inputs, the scored set and band, the folds,
the scoring function (`exp_spinup_vegc`), and the four nulls, computed by the sealed null code on
all five folds and then restricted to the scored cells of folds 3 and 4. The sealed recipe's own
value on the same cells is reported beside the model and never decided on.
"""

from __future__ import annotations

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

from exp_spinup_vegc import NULLS, _inputs, global_folds, predictions, score, scored_set
from screen_spinup_vegc import HELD_FOLDS, Recipe, load, predict_all, subset
from vegemu.paths import repo_root
from vegemu.results import append_result_block

STATISTIC = "asgood_vegc_spinup_heldout"
DEFAULT_EXP = "X-20260925-spinup-vegc-recipe-v2"
RECIPE_FIELDS: frozenset[str] = frozenset(f.name for f in dataclasses.fields(Recipe))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recipe_from(prereg: dict[str, Any]) -> Recipe:
    """The pre-registered recipe, field by field. An unknown or missing field is an error."""
    spec = dict(prereg["recipe"])
    if set(spec) != RECIPE_FIELDS:
        raise ValueError(f"recipe fields {sorted(spec)} != {sorted(RECIPE_FIELDS)}")
    params = tuple(sorted((str(k), v) for k, v in (spec["params"] or {}).items()))
    return Recipe(
        name=str(spec["name"]),
        feats=str(spec["feats"]),
        target=str(spec["target"]),
        gate=str(spec["gate"]),
        objective=str(spec["objective"]),
        capacity=str(spec["capacity"]),
        params=params,
        pool=str(spec["pool"]),
        pilot_weight=float(spec["pilot_weight"]),
        zero_floor=float(spec["zero_floor"]),
        bag=int(spec["bag"]),
    )


def pinned_tables(prereg: dict[str, Any]) -> tuple[Path, Path | None]:
    """(v3x directory, v3p directory or None) for `screen_spinup_vegc.load`, each table checked
    against its pin. The recipe's feature set decides which tables it reads: `v3p` reads the
    features_v3p pair, anything else the features_v3x pair."""
    pins = prereg["data"]["features"]
    tag = str(pins["tag"])
    if tag not in ("v3x", "v3p"):
        raise SystemExit(f"data.features.tag must be v3x or v3p, not {tag!r}")
    root = Path(str(pins["dir"]))
    for name in ("spinup", "pilot"):
        p = root / f"features_{tag}_{name}.parquet"
        got, want = _sha256(p), str(pins[f"{name}_sha256"])
        if got != want:
            raise SystemExit(f"{p} hashes to {got}, the pre-registration pins {want}")
    return (root, None) if tag == "v3x" else (root, root)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--exp-id", default=DEFAULT_EXP)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument(
        "--nulls-pool",
        default="",
        choices=("", "spinup", "pilot"),
        help="nulls arm only: the pool, before a pre-registration exists to name it",
    )
    args = ap.parse_args()

    prereg: dict[str, Any] = {}
    prereg_path = repo_root() / "experiments" / args.exp_id / "preregistration.yaml"
    if args.arm == "model" or not args.nulls_pool or prereg_path.exists():
        prereg = yaml.safe_load(prereg_path.read_text())
    null_pool = args.nulls_pool or str(prereg["nulls_pool"])
    if prereg and args.nulls_pool and args.nulls_pool != str(prereg["nulls_pool"]):
        raise SystemExit(f"--nulls-pool {args.nulls_pool} but the pre-registration says otherwise")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.arm == "nulls":
        # The nulls need neither the recipe nor the feature tables: the sealed inputs, the sealed
        # scored set and folds, and the sealed null code, restricted to the held-out cells.
        inp = _inputs()
        sc = scored_set(inp)
        mask = sc["mask"].astype(bool)
        folds_g = global_folds(inp["lon_p"], inp["lat_p"], inp["lon_g"], inp["lat_g"])  # type: ignore[arg-type]
        sc["fold"] = folds_g[mask].astype(np.float64)
        held = np.isin(sc["fold"], HELD_FOLDS)
        sub = subset(sc, held)
        report: dict[str, Any] = {
            "exp_id": args.exp_id,
            "arm": "nulls",
            "statistic": STATISTIC,
            "scored_cells": int(held.sum()),
            "frac_rerun": sub["frac_rerun"],
            "band_is_floor_share": sub["band_is_floor"],
            "null_pool": null_pool,
        }
        pred = predictions(inp, null_pool, "nulls")
        report["arm_details"] = {n: score(p[mask][held], sub) for n, p in pred.items()}
        for n, a in report["arm_details"].items():
            print(f"  {n:20s} D {a['D']:+.6f}  frac {a['frac']:.4f}  skill {a['skill_log1p']:+.4f}")
        print(f"  rerun frac on the {int(held.sum())} held-out cells {sub['frac_rerun']:.6f}")
        (out / "nulls.json").write_text(json.dumps(report, indent=2, default=float))
        print(f"wrote {out / 'nulls.json'}")
        return 0

    recipe = recipe_from(prereg)
    threshold = float(str(prereg["decision_rule"]["pass_if"]).split(">=")[-1])
    d = load(*pinned_tables(prereg))
    mask = d.sc["mask"].astype(bool)
    held = np.isin(np.asarray(d.sc["fold"]), HELD_FOLDS)
    sub = subset(d.sc, held)
    report = {
        "exp_id": args.exp_id,
        "arm": "model",
        "statistic": STATISTIC,
        "recipe": {**dataclasses.asdict(recipe), "params": dict(recipe.params)},
        "scored_cells": int(held.sum()),
        "frac_rerun": sub["frac_rerun"],
        "band_is_floor_share": sub["band_is_floor"],
        "null_pool": null_pool,
    }
    pred, info = predict_all(d, recipe, HELD_FOLDS, args.workers, args.threads)
    sealed, _ = predict_all(d, Recipe("sealed recipe"), HELD_FOLDS, args.workers, args.threads)
    model = score(pred[mask][held], sub)
    report["arm_details"] = {"model": model, "sealed_recipe_beside": score(sealed[mask][held], sub)}
    report["fit"] = info
    prior = json.loads((out / "nulls.json").read_text())["arm_details"]
    report["decision"] = {
        "D": model["D"],
        "threshold": threshold,
        "verdict": "pass" if model["D"] >= threshold else "fail",
    }
    print(f"  model D {model['D']:+.6f} frac {model['frac']:.4f}: {report['decision']['verdict']}")
    report.update(
        append_result_block(
            statistic=STATISTIC,
            arms={"model": float(model["D"]), **{n: float(prior[n]["D"]) for n in NULLS}},
            n=int(held.sum()),
        )
    )
    (out / "metrics.json").write_text(json.dumps(report, indent=2, default=float))
    print(f"wrote {out / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
