#!/usr/bin/env python
"""Cut a contiguous cell block out of a restart file, verbatim.

    scripts/corpus_restart_subset.py --first-cell 42480 --ncell 20 --out <file.lpj>

THE CONTROL ARM for the synthesis validation. A subset re-run of LPJmL-FIT is NOT a per-cell
replica of the global run -- one cell alone diverges at the first step, a 21-cell block after 15
years -- so a synthesised restart must be compared against a run from the REAL restart over the
SAME block with the SAME task count, never against the stored global output
(`MEMORY.md:subset-diverges`).

Records are copied as bytes, so the control is the ground truth for those cells exactly, and the
only difference between the two runs is the roster the emulator replaced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.binfmt.restart import RestartReader, RestartWriter, read_cell, write_cell
from vegemu.paths import path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--first-cell", type=int, required=True)
    ap.add_argument("--ncell", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--source",
        default=None,
        help="restart file to cut from; defaults to the historical seed-1 end-of-spin-up file",
    )
    args = ap.parse_args()

    src = (
        Path(args.source)
        if args.source
        else path("ground_truth.historical_seed1") / "restart/restart_1999.lpj"
    )
    reader = RestartReader(src)
    cells = list(range(args.first_cell, args.first_cell + args.ncell))
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with reader:
        blobs = [reader.cell_bytes(c) for c in cells]
    with RestartWriter(
        dest, reader.generic, reader.restart, ncell=len(cells), firstcell=args.first_cell
    ) as writer:
        for blob in blobs:
            writer.append(blob)

    # The cut must be byte-exact and must still decode under the new file's own headers.
    back = RestartReader(dest)
    with back:
        for i, want in enumerate(blobs):
            got = back.cell_bytes(i)
            if got != want:
                raise AssertionError(f"record {i} differs from the source")
            if write_cell(read_cell(got, back.layout), back.layout) != got:
                raise AssertionError(f"record {i} does not round-trip in the subset file")

    print(f"wrote {dest}  ({dest.stat().st_size / 1e6:.1f} MB)")
    last = args.first_cell + args.ncell - 1
    print(f"  cells {args.first_cell}..{last}, byte-exact from {src.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
