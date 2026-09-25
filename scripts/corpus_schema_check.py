#!/usr/bin/env python
"""Re-decode a pinned state table with today's code and prove it comes out byte-identical.

    NCPUS=16 TIME=00:30:00 scripts/sbatch_py.sh D-cor-state-bytes scripts/corpus_schema_check.py \\
        --corpus-dir pilot-v2-constco2 \\
        --pinned <scratch>/exp/X-pilot-decode-v2corpus/state_pilot-v2-constco2.parquet \\
        --out <scratch>/corpus/_checks/state_pilot-v2-constco2.redecode.parquet --nproc 16

WHY. `vegemu.corpus.state` gained a table schema (`vegemu.corpus.schema`) so that a treeless
row's tree-type shares could become NaN. The promise that made that change safe is that every
caller which does not ask for the new schema gets the OLD bytes -- and the most exposed such
caller is `exp_derive_nulls_pilot.decode`, which built the 78-column state table that sealed
experiments read as their model input. So this runs THAT function, unmodified and with no schema
argument, over the same runs, writes the table the way it was written, and compares sha256s.

A round-trip, not an assertion (invariant 7): the only evidence that a decoder is unchanged is the
decoder reproducing its own pinned output. `corpus_pilot.py --stage decode --out-version ...
--schema 2` is the same proof for `corpus.parquet`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def _load(name: str) -> ModuleType:
    """Import a sibling script by path, registered first (see `corpus_pilot._load` for why)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", required=True, help="e.g. pilot-v2-constco2")
    ap.add_argument("--pinned", required=True, help="the table the decode must reproduce")
    ap.add_argument("--out", required=True, help="where the re-decode is written")
    ap.add_argument("--nproc", type=int, default=1)
    args = ap.parse_args()

    pinned, out = Path(args.pinned), Path(args.out)
    if out.resolve() == pinned.resolve():
        raise SystemExit("--out must not be the pinned table itself")
    out.parent.mkdir(parents=True, exist_ok=True)
    nulls = _load("exp_derive_nulls_pilot")
    state = nulls.decode(args.corpus_dir, args.nproc, None)
    state.write_parquet(out)

    want, got = sha256_of(pinned), sha256_of(out)
    print(f"pinned   {pinned}\n         {want}")
    print(f"re-decode {out}\n         {got}")
    print(f"rows x cols {state.height} x {state.width}")
    if want == got:
        print("verdict: BYTE-IDENTICAL -- the legacy decode path is unchanged")
        return 0
    print("verdict: DIFFERENT -- the legacy decode path no longer reproduces its pinned table")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
