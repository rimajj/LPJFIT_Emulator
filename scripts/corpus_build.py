#!/usr/bin/env python
"""Build the corpus: climate summaries and per-cell state summaries, with provenance.

    scripts/corpus_build.py --what climate --version v0
    scripts/corpus_build.py --what state   --version v0 --nproc 64
    scripts/corpus_build.py --what all     --version v0 --nproc 64 --cells 200

Submit it; do not run it on the login node:

    NCPUS=64 PARTITION=priority TIME=02:00:00 scripts/sbatch_py.sh D-corpus-v0 \\
        scripts/corpus_build.py --what all --version v0 --nproc 64

WHAT COMES OUT, and why each piece is here.

  climate_<leg>.parquet   one row per cell: a 30-year climate summary for the window that ends at
                          the year the matching state was written. No CO2, no address, no lagged
                          state -- see src/vegemu/corpus/climate.py for why each is absent.
  state_<leg>_seed<n>.parquet
                          one row per cell: counts, stocks, the growth-failure counter, the height
                          distribution, PFT composition, and five quantiles of each of eight
                          per-stem traits. Both seeds of every leg, because the acceptance
                          tolerance IS the two-seed spread and it has to be measured, not assumed.
  provenance.json         every source file with its size, mtime and decoded header, plus the
                          corpus hash a pre-registration cites. A corpus is immutable once cited.

⚠ THE THREE LEGS WERE NOT ALL PRODUCED BY THE SAME BINARY BUILD. Historical + ssp370-seed1 came
from the 2026-02-05 build; the ssp126 leg from an Aug-12 build. Two builds are never byte-identical.
So the provenance records each file's mtime, and any claim that crosses legs has to disclose it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import polars as pl

from vegemu.corpus import climate as climate_mod
from vegemu.corpus import state as state_mod
from vegemu.paths import path, paths

# The restart file that holds each leg's target state. `restart_1999` is the end of the historical
# transient that followed the 1000-year spin-up; `restart_2100` is the end of each scenario leg.
# ⚠ restart_1999 is NOT restart_2019: 2019 is only the start of a scenario continuation.
RESTARTS: dict[tuple[str, int], tuple[str, str]] = {
    ("historical", 1): ("ground_truth.historical_seed1", "restart/restart_1999.lpj"),
    ("historical", 2): ("ground_truth.historical_seed2", "restart/restart_1999.lpj"),
    ("ssp370", 1): ("ground_truth.ssp370_seed1", "restart/restart_2100.lpj"),
    ("ssp370", 2): ("ground_truth.ssp370_seed2", "restart/restart_2100.lpj"),
    ("ssp126", 1): ("ground_truth.ssp126_seed1", "restart/restart_2100.lpj"),
    ("ssp126", 2): ("ground_truth.ssp126_seed2", "restart/restart_2100.lpj"),
}


def restart_path(leg: str, seed: int) -> Path:
    key, tail = RESTARTS[(leg, seed)]
    return path(key) / tail


def out_dir(version: str) -> Path:
    root = Path(str(paths()["scratch"]["corpus"])) / version
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_climate(version: str, ncells: int | None) -> dict[str, object]:
    out = out_dir(version)
    prov: dict[str, object] = {}
    cells = list(range(ncells)) if ncells else None
    for leg, window in climate_mod.WINDOWS.items():
        t0 = time.time()
        frame = climate_mod.climate_table(window, cells=cells)
        dest = out / f"climate_{leg}.parquet"
        frame.write_parquet(dest)
        prov[leg] = {
            **climate_mod.basis(window),
            "rows": frame.height,
            "cols": frame.width,
            "seconds": round(time.time() - t0, 1),
            "sha256": sha256_of(dest),
        }
        print(
            f"climate {window.describe()}: {frame.height} rows x {frame.width} cols "
            f"in {time.time() - t0:.0f} s -> {dest.name}",
            flush=True,
        )
    return prov


def build_state(version: str, nproc: int, ncells: int | None) -> dict[str, object]:
    out = out_dir(version)
    prov: dict[str, object] = {}
    cells = list(range(ncells)) if ncells else None
    for (leg, seed), _ in RESTARTS.items():
        src = restart_path(leg, seed)
        if not src.exists():
            print(f"state {leg} seed{seed}: MISSING {src} -- skipped", flush=True)
            prov[f"{leg}_seed{seed}"] = {"file": str(src), "status": "missing"}
            continue
        t0 = time.time()
        frame = state_mod.state_table(src, cells=cells, nproc=nproc)
        dest = out / f"state_{leg}_seed{seed}.parquet"
        frame.write_parquet(dest)
        prov[f"{leg}_seed{seed}"] = {
            **state_mod.basis(src),
            "rows": frame.height,
            "cols": frame.width,
            "seconds": round(time.time() - t0, 1),
            "sha256": sha256_of(dest),
        }
        alive = frame.filter(pl.col("stems_total") > 0).height
        print(
            f"state {leg} seed{seed}: {frame.height} rows, {alive} tree-bearing "
            f"({100 * alive / max(frame.height, 1):.1f} %) in {time.time() - t0:.0f} s "
            f"-> {dest.name}",
            flush=True,
        )
    return prov


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--what", choices=("climate", "state", "all"), default="all")
    ap.add_argument("--version", default="v0", help="corpus version directory under scratch.corpus")
    ap.add_argument("--nproc", type=int, default=1)
    ap.add_argument(
        "--cells",
        type=int,
        default=None,
        help="first N cells only -- a smoke test, never a result",
    )
    args = ap.parse_args()

    out = out_dir(args.version)
    manifest_path = out / "provenance.json"
    manifest: dict[str, object] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    manifest.setdefault("corpus_version", args.version)
    manifest["built_by"] = "scripts/corpus_build.py"
    manifest["cells_limit"] = args.cells
    manifest["is_smoke"] = args.cells is not None
    manifest["build_note"] = (
        "The three legs were NOT all produced by the same LPJmL-FIT binary build: historical and "
        "ssp370-seed1 by the 2026-02-05 build, the ssp126 leg by an Aug-12 build. Two builds are "
        "never byte-identical. Any claim crossing legs must disclose this."
    )

    if args.what in ("climate", "all"):
        manifest["climate"] = build_climate(args.version, args.cells)
    if args.what in ("state", "all"):
        manifest["state"] = build_state(args.version, args.nproc, args.cells)

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    # The hash a pre-registration cites: over the per-file hashes, so it changes if any input does.
    parts = sorted(
        v.get("sha256", "")
        for section in ("climate", "state")
        for v in (manifest.get(section) or {}).values()  # type: ignore[union-attr]
        if isinstance(v, dict)
    )
    corpus_sha = hashlib.sha256("".join(parts).encode()).hexdigest()
    manifest["corpus_sha256"] = corpus_sha
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\ncorpus {args.version} corpus_sha256={corpus_sha}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
