#!/usr/bin/env python
"""Read the STATE of every run of a replicate seed, without touching the replicate's directories.

    scripts/exp_read_replicate_states.py --version pilot-v2-constco2 --seed 2 --out <dir>

WHY THIS EXISTS. The emitted-restart score needs the model's second run of every pilot spin-up --
its truth is the two-run mean and its band the cell's own run-to-run spread -- and the owning
line's decode (`corpus_pilot.py --stage decode`) writes INTO the replicate's corpus directory, which
another session owns while it is being built. This reads the same restarts with the same decoder
(`vegemu.corpus.state.single_cell_state`, the one every corpus table is built with) and writes only
under `--out`. It carries no climate columns: the scorer takes climate from seed 1, where the
forcing bytes are identical by construction.

⚠ A RUN IS JUDGED BY ITS LOG, NOT BY ITS RESTART EXISTING. A row is written only for a run whose log
has a line starting `lpjml successfully terminated`; every other run is listed as failed and the
script exits non-zero, so a partial table is never silently green. When the owning line's decode
lands, the two tables must agree on every state column -- `--compare` checks exactly that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import polars as pl

from vegemu.corpus import state as state_mod
from vegemu.paths import paths

SUCCESS = "lpjml successfully terminated"


def _one(args: tuple[str, int, str, str]) -> dict[str, Any]:
    name, cell, point, rdir = args
    try:
        run = Path(rdir)
        logs = sorted(run.glob("lpjml*.log"))
        ok = any(
            line.startswith(SUCCESS)
            for log in logs
            for line in log.read_text(errors="replace").splitlines()
        )
        if not ok:
            return {
                "name": name,
                "cell": cell,
                "error": f"no '{SUCCESS}' line in {len(logs)} log(s)",
            }
        row: dict[str, Any] = {"name": name, "cell": cell, "point": point}
        row.update(state_mod.single_cell_state(run / "restart" / f"restart_{name}.lpj", cell))
        row["cell"] = cell
        return row
    except Exception:
        return {"name": name, "cell": cell, "error": traceback.format_exc(limit=4)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="pilot-v2-constco2")
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--compare", default="", help="the owning line's replicate table, if it exists")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    meta = Path(str(paths()["scratch"]["corpus"])) / f"{args.version}-s{args.seed}"
    runs = pl.read_csv(meta / "runs.csv")
    jobs = [
        (str(n), int(c), str(p), str(r))
        for n, c, p, r in zip(
            runs["name"], runs["cell"], runs["point"], runs["run_dir"], strict=True
        )
    ]
    print(f"reading {len(jobs)} runs of {meta.name} on {args.workers} processes", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_one, jobs, chunksize=16))
    done = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"replicate_s{args.seed}_states.parquet"
    frame = pl.DataFrame(done).with_columns(pl.col("cell").cast(pl.Int64)).sort(["cell", "point"])
    frame.write_parquet(dest)
    report: dict[str, Any] = {
        "source_manifest": str(meta / "runs.csv"),
        "runs": len(jobs),
        "decoded": len(done),
        "failed": len(failed),
        "failures": failed[:10],
        "table": str(dest),
        "table_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "decoder": "vegemu.corpus.state.single_cell_state",
    }
    if args.compare and Path(args.compare).exists():
        other = pl.read_parquet(args.compare).with_columns(pl.col("cell").cast(pl.Int64))
        cols = [c for c in frame.columns if c in other.columns and c not in ("name",)]
        a = frame.select(cols).sort(["cell", "point"])
        b = other.select(cols).sort(["cell", "point"])
        report["compare"] = {"path": args.compare, "columns": len(cols), "equal": a.equals(b)}
    (out / f"replicate_s{args.seed}_states.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    if failed:
        print(f"⚠ {len(failed)} runs not usable, e.g. {failed[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
