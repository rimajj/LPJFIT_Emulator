#!/usr/bin/env python
"""The continuation test, read against a real run averaged over the SAME window.

    scripts/exp_continuation_window.py --arm nulls --null-root <v1 root> --map-nulls <nulls.json> \\
        --out <dir>                                               # before the seal
    scripts/exp_continuation_window.py --arm model --root <continuation root> \\
        --nulls <dir>/nulls.json --out <dir>                      # after the seal

WHY A NEW REFERENCE (decision record 20260925-INT-a-continuation-is-judged-against-a-real-run-on-
the-same-window). A continuation arm is ONE run of the model, scored on a 10-year mean. The sealed
predecessor (X-20260925-spinup-restart-continuation) read it against a rerun that compares two
250-year means (0.858711), which no 10-year mean of any run reaches: a real run's 10-year window
lands in band on 0.598 of the cells. Here the reference for an L-year arm window is
`diag_window_ceiling.window_cell_scores(L)`: an L-year window of one real seed of the stored run
against the other seed's truth, the sealed band, averaged over both seeds and every non-overlapping
window of 1450-1699, cell by cell. It replaces `rerun_cell` / `frac_rerun` in the sealed scorer
(`exp_spinup_vegc.score`), so D, its tile bootstrap and its latitude bands all read against it.

THE SCORED CELLS are the tree-bearing scored cells of folds 3 and 4 (20,123 of 56,986): the model
arm's carbon target is the screened recipe's held-out prediction, and that recipe was CHOSEN on
folds 0-2, so only folds 3-4 are clean. All 56,986 cells are reported beside, never decided on.

NULLS. Two continuation arms already run and harvested with the same config, years and CO2
(`spinup_continuation.py`, root `--null-root`): restart_1999 continued (the one real restart every
cell has) and the previous emulated restart continued (the file this one replaces). And the four
map-level lookups of X-20260925-spinup-vegc-recipe-v2 on the same cells, read from its nulls
job's nulls.json: a static prediction, re-read against the 10-year reference (their frac on these
cells minus it), which is what an arm that reproduced that lookup exactly would score.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diag_window_ceiling import scored_trajectories, window_cell_scores
from exp_spinup_vegc import _inputs, global_folds, score, scored_set
from screen_spinup_vegc import subset
from vegemu.paths import repo_root
from vegemu.results import append_result_block

DEFAULT_EXP = "X-20260925-continuation-same-window"
STATISTIC = "asgood_vegc_continuation_same_window"
HELD_FOLDS = (3, 4)
# arm window -> the length of real-run window it is read against
WINDOWS = {"y01_10": 10, "y21_30": 10, "y01": 1}
PRIMARY = "y01_10"
CONTINUATION_NULLS = {
    "restart_1999_continuation": "null",
    "previous_emulated_continuation": "emulated",
}
MAP_NULLS = ("training_mean", "nearest_analogue", "nearest_geographic", "shuffled")


def _with_reference(sc: dict[str, Any], sel: np.ndarray, ref: np.ndarray) -> dict[str, Any]:
    sub = subset(sc, sel)
    sub["rerun_cell"] = ref[sel]
    sub["frac_rerun"] = float(ref[sel].mean())
    return sub


def _arm(
    root: Path, arm: str, sc: dict[str, Any], refs: dict[int, np.ndarray], held: np.ndarray
) -> dict[str, Any]:
    harvest = json.loads((root / arm / "harvest.json").read_text())
    if harvest.get("members_done") != harvest.get("members"):
        raise RuntimeError(f"{root / arm}: {harvest.get('members_done')}/{harvest.get('members')}")
    if harvest.get("climate_year_sequences") != 1:
        raise RuntimeError(f"{root / arm}: members drew different climate years")
    win = pl.read_parquet(root / arm / "vegc_windows.parquet").sort("cell")
    mask = sc["mask"].astype(bool)
    out: dict[str, Any] = {"climate_years": harvest["climate_years"]}
    for name, length in WINDOWS.items():
        x = win[f"vegc_{name}"].to_numpy().astype(np.float64)[mask]
        out[name] = score(x[held], _with_reference(sc, held, refs[length]))
        out[f"{name}_all_cells"] = score(x, _with_reference(sc, np.ones_like(held), refs[length]))
    return out


def _setup() -> tuple[dict[str, Any], np.ndarray, dict[int, np.ndarray], dict[str, Any]]:
    inp = _inputs()
    sc = scored_set(inp)
    mask = sc["mask"].astype(bool)
    folds = global_folds(inp["lon_p"], inp["lat_p"], inp["lon_g"], inp["lat_g"])[mask]  # type: ignore[arg-type]
    sc["fold"] = folds.astype(np.float64)
    held = np.isin(folds, HELD_FOLDS)
    traj = scored_trajectories(sc)
    refs = {length: window_cell_scores(traj, sc, length)[0] for length in set(WINDOWS.values())}
    info = {
        "scored_cells": int(held.sum()),
        "all_scored_cells": int(mask.sum()),
        "reference": {
            f"real_{length}yr": {"folds_3_4": float(r[held].mean()), "all": float(r.mean())}
            for length, r in refs.items()
        },
        "frac_rerun_250yr": {
            "folds_3_4": float(sc["rerun_cell"][held].mean()),
            "all": float(sc["frac_rerun"]),
        },
    }
    return sc, held, refs, info


def _check_nulls(nulls_path: Path, prereg: dict[str, Any]) -> dict[str, float]:
    got: dict[str, float] = json.loads(nulls_path.read_text())["decision_values"]
    for nl in prereg["nulls"]:
        want = nl["expected"]
        if abs(got[nl["id"]] - float(want["value"])) > float(want["tolerance"]):
            raise SystemExit(f"{nulls_path}: {nl['id']} {got[nl['id']]} is not its sealed {want}")
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("nulls", "model"), required=True)
    ap.add_argument("--exp-id", default=DEFAULT_EXP)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", default="", help="model arm: the continuation root (arm 'emulated')")
    ap.add_argument("--null-root", default="", help="nulls arm: the root of the two old arms")
    ap.add_argument("--map-nulls", default="", help="nulls arm: recipe-v2's nulls job nulls.json")
    ap.add_argument("--nulls", default="", help="model arm: this experiment's nulls.json")
    ap.add_argument("--threshold", type=float, default=-0.02)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sc, held, refs, info = _setup()
    ref10 = info["reference"]["real_10yr"]["folds_3_4"]

    if args.arm == "nulls":
        root = Path(args.null_root)
        arms = {n: _arm(root, a, sc, refs, held) for n, a in CONTINUATION_NULLS.items()}
        maps = json.loads(Path(args.map_nulls).read_text())
        if maps["scored_cells"] != info["scored_cells"]:
            raise RuntimeError(
                f"map nulls on {maps['scored_cells']} cells, here {info['scored_cells']}"
            )
        values = {n: float(a[PRIMARY]["D"]) for n, a in arms.items()}
        values.update({n: float(maps["arm_details"][n]["frac"]) - ref10 for n in MAP_NULLS})
        report = {
            **info,
            "arm": "nulls",
            "arm_details": arms,
            "decision_values": values,
            "map_nulls_from": args.map_nulls,
        }
        (out / "nulls.json").write_text(json.dumps(report, indent=2, default=float))
        print(json.dumps({**info, "decision_values": values}, indent=1))
        return 0

    prereg = yaml.safe_load(
        (repo_root() / "experiments" / args.exp_id / "preregistration.yaml").read_text()
    )
    nulls_path = Path(args.nulls)
    values = _check_nulls(nulls_path, prereg)
    prior = json.loads(nulls_path.read_text())
    model = _arm(Path(args.root), "emulated", sc, refs, held)
    years = prior["arm_details"]["restart_1999_continuation"]["climate_years"]
    if model["climate_years"] != years:
        raise RuntimeError("the model arm drew different climate years from the nulls")
    d = float(model[PRIMARY]["D"])
    report = {
        **info,
        "exp_id": args.exp_id,
        "arm": "model",
        "statistic": STATISTIC,
        "primary_window": PRIMARY,
        "arm_details": {"model": model},
        "nulls_from": str(nulls_path),
        "decision": {
            "D": d,
            "threshold": args.threshold,
            "verdict": "pass" if d >= args.threshold else "fail",
        },
    }
    report.update(
        append_result_block(statistic=STATISTIC, arms={"model": d, **values}, n=int(held.sum()))
    )
    (out / "metrics.json").write_text(json.dumps(report, indent=2, default=float))
    for name in WINDOWS:
        print(f"  model {name}: D {model[name]['D']:+.6f} frac {model[name]['frac']:.4f}")
    print(f"  decision: {report['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
