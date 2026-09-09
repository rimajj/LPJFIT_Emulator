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

⚠ EVERY LEG'S TWO SEEDS MUST BE TWO RUNS, AND THE BUILD NOW CHECKS IT. On corpus v0 the ssp370 leg's
two "seeds" were the same run twice, which quietly turned the acceptance tolerance into the bare
10 % floor for that leg. A failing check WITHHOLDS `corpus_sha256`, so the corpus cannot be cited by
a pre-registration at all. See `check_seeds_differ` and
`docs/decisions/20260908-X-ssp370-has-no-second-seed.md`.
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
    # ⚠ `ground_truth.ssp370_seed2` IS NOT A SECOND RUN. That directory started from the historical
    # SEED 1 restart, and the model reads its RNG seeds from the restart it starts from -- so it
    # reproduced seed 1 exactly (same size, same checksum, same recorded triple). A genuine second
    # realisation is on disk in `..._random_seed2_from_hist_seed2`, but it needs a key in
    # `config/paths.yaml`, which is integrator-owned, and it was written by the Jul-21 build rather
    # than the Feb-05 one -- so the corrected pair straddles a build boundary and that must be
    # disclosed. Repointing this entry is a NEW CORPUS VERSION, never an edit of v0/v1: three sealed
    # pre-registrations cite v0's hash. `check_seeds_differ` fails the build until it is fixed.
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


# --------------------------------------------------------------------------------------------
# The seed-distinctness gate.
#
# WHY THIS REFUSES INSTEAD OF LOGGING. Corpus v0 recorded, correctly and in full, that the ssp370
# leg's two "seeds" carried the same RNG triple and decoded to the same numbers -- and that record
# sat unread in provenance.json while three pre-registrations cited the corpus and one of them
# declared a two-seed mean it never had. A defect that is merely logged is a defect that gets used
# (`docs/decisions/20260908-X-ssp370-has-no-second-seed.md`). So the build now withholds
# `corpus_sha256` -- the only handle a pre-registration can cite -- and exits non-zero.
#
# Two independent signals, because either alone can be fooled:
#   the RNG triple   -- the CAUSE. Same triple, same build, same input, therefore same output. This
#                       is what actually went wrong: the second run read its seeds from the first
#                       run's restart, so "two seeds" were one.
#   the decoded rows -- the EFFECT. Catches a leg whose triples differ on paper but whose runs still
#                       landed on identical state, and catches a triple recorded wrongly.
# --------------------------------------------------------------------------------------------
def check_seeds_differ(
    tables: dict[int, pl.DataFrame], bases: dict[int, dict[str, object]]
) -> dict[str, object]:
    """Are this leg's two seed tables two realisations of the model's own noise, or one twice?

    The acceptance tolerance IS `max(10 %, |s1-s2|/|mean|)`. With `s1 == s2` that collapses to
    exactly the 10 % floor in every cell while still reading as "10 % or the model's own spread",
    so a band derived from such a leg is not a band -- it is the floor wearing the band's name.
    """
    if set(tables) != {1, 2}:
        built = sorted(tables) or "neither seed"
        return {"ok": False, "reason": f"only {built} was built, so the pair cannot be checked"}

    triples = {n: bases[n].get("seed") for n in (1, 2)}
    shared = [c for c in tables[1].columns if c != "cell" and c in tables[2].columns]
    if not shared:
        return {"ok": False, "reason": "the two seed tables share no comparable column"}
    joined = (
        tables[1]
        .select(["cell", *shared])
        .join(tables[2].select(["cell", *shared]), on="cell", how="inner", suffix="_b")
    )
    differs = pl.any_horizontal([pl.col(c).ne_missing(pl.col(f"{c}_b")) for c in shared])
    n_diff = int(joined.select(differs.sum()).item())

    problems: list[str] = []
    if triples[1] == triples[2]:
        problems.append(f"both seeds record the same RNG triple {triples[1]}")
    # A zero-cell overlap is not agreement, it is no evidence -- and it must not read as a pass.
    if joined.height == 0:
        problems.append("the two seed tables have no cell in common, so nothing was compared")
    elif n_diff == 0:
        problems.append(
            f"the two decoded tables are equal in all {len(shared)} columns "
            f"and all {joined.height} cells"
        )
    return {
        "ok": not problems,
        "reason": "; ".join(problems),
        "cells_compared": joined.height,
        "cells_differing": n_diff,
        "columns_compared": len(shared),
        "seed_triple_seed1": triples[1],
        "seed_triple_seed2": triples[2],
    }


def build_state(
    version: str, nproc: int, ncells: int | None
) -> tuple[dict[str, object], dict[str, object]]:
    out = out_dir(version)
    prov: dict[str, object] = {}
    checks: dict[str, object] = {}
    cells = list(range(ncells)) if ncells else None
    legs = dict.fromkeys(leg for leg, _ in RESTARTS)
    for leg in legs:
        tables: dict[int, pl.DataFrame] = {}
        bases: dict[int, dict[str, object]] = {}
        for seed in (1, 2):
            src = restart_path(leg, seed)
            if not src.exists():
                print(f"state {leg} seed{seed}: MISSING {src} -- skipped", flush=True)
                prov[f"{leg}_seed{seed}"] = {"file": str(src), "status": "missing"}
                continue
            t0 = time.time()
            frame = state_mod.state_table(src, cells=cells, nproc=nproc)
            dest = out / f"state_{leg}_seed{seed}.parquet"
            frame.write_parquet(dest)
            bases[seed] = state_mod.basis(src)
            tables[seed] = frame
            prov[f"{leg}_seed{seed}"] = {
                **bases[seed],
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
        verdict = check_seeds_differ(tables, bases)
        checks[leg] = verdict
        if verdict["ok"]:
            print(
                f"seed check {leg}: OK -- {verdict['cells_differing']}/"
                f"{verdict['cells_compared']} cells differ between the seeds",
                flush=True,
            )
        else:
            print(f"seed check {leg}: FAILED -- {verdict['reason']}", flush=True)
    return prov, checks


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
        manifest["state"], manifest["seed_check"] = build_state(
            args.version, args.nproc, args.cells
        )

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    # The hash a pre-registration cites: over the per-file hashes, so it changes if any input does.
    # `seed_check` is deliberately NOT one of the hashed sections -- it is a verdict about the
    # inputs, not an input, and folding it in would make the hash move when the checker changes.
    parts = sorted(
        v.get("sha256", "")
        for section in ("climate", "state")
        for v in (manifest.get(section) or {}).values()  # type: ignore[union-attr]
        if isinstance(v, dict)
    )
    corpus_sha = hashlib.sha256("".join(parts).encode()).hexdigest()

    # A corpus with a leg whose two seeds are one run twice must not be citeable. Withholding the
    # hash is the enforcement: `corpus_sha256` is what a pre-registration names, so without it the
    # sealer has nothing to point at. The manifest is still written -- that is the diagnosis.
    recorded = manifest.get("seed_check")
    seed_checks: dict[str, object] = recorded if isinstance(recorded, dict) else {}
    failed = {leg: c for leg, c in seed_checks.items() if isinstance(c, dict) and not c.get("ok")}
    if failed:
        manifest.pop("corpus_sha256", None)
        manifest["corpus_sha256_withheld"] = {
            "would_have_been": corpus_sha,
            "because": "a leg's two seeds are not two realisations",
            "legs": {leg: c.get("reason") for leg, c in failed.items()},
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        print(f"\ncorpus {args.version}: corpus_sha256 WITHHELD -- this corpus is not citeable")
        for leg, c in failed.items():
            print(f"  {leg}: {c.get('reason')}", file=sys.stderr)
        print(f"manifest: {manifest_path}", file=sys.stderr)
        return 2

    # A state build that ran and passed clears any withholding a previous build recorded. One that
    # did not run leaves it standing -- a climate-only rebuild must not launder a bad state leg.
    if "seed_check" in manifest:
        manifest.pop("corpus_sha256_withheld", None)
    elif "corpus_sha256_withheld" in manifest:
        print(
            f"\ncorpus {args.version}: still withheld from an earlier build -- rerun --what state",
            file=sys.stderr,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        return 2

    manifest["corpus_sha256"] = corpus_sha
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\ncorpus {args.version} corpus_sha256={corpus_sha}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
