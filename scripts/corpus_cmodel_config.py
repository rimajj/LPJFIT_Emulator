#!/usr/bin/env python
"""Build an LPJmL-FIT config for a subset run from a chosen restart file.

    scripts/corpus_cmodel_config.py --restart <file.lpj> --first-cell 42480 --ncell 20 \\
        --years 2000 2000 --run-dir <dir>

WHY IT PATCHES THE GROUND TRUTH'S OWN SAVED CONFIG rather than writing one from scratch. The run
that produced every existing ground-truth leg saved its exact configuration next to its output.
Starting from that file means the validation run differs from the truth in EXACTLY the fields
named here and in nothing else -- no silently different fire setting, no different phenology, no
different soil map. Writing a fresh config would be a second, unvalidated configuration whose
differences from the truth nobody had enumerated.

EVERY REPLACEMENT IS ASSERTED. A regex that silently matches nothing would leave the original
value in place and the run would quietly use the wrong cells, the wrong years or the wrong restart
file -- and still succeed. So each patch counts its own hits and raises if the count is wrong.

⚠ A SUBSET RUN IS NOT A PER-CELL REPLICA OF THE GLOBAL RUN (`MEMORY.md:subset-diverges`): one cell
alone diverges at the first step, a 21-cell block after 15 years. So anything scored from a run
built here must be compared against ANOTHER RUN BUILT HERE over the same block with the same task
count -- never against the stored global output.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.paths import path

# The saved configuration of the historical ground-truth run, seed 1.
SAVED_CONFIG_SUBDIR = "scripts_for_running_the_model/lpjml_2000_2019.js"


def patch(text: str, pattern: str, replacement: str, expect: int = 1) -> str:
    out, n = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if n != expect:
        raise AssertionError(
            f"pattern {pattern!r} matched {n} times, expected {expect}. The saved config has "
            "changed shape; fix the pattern rather than letting the original value stand."
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--restart", required=True, help="the restart file the run starts from")
    ap.add_argument("--first-cell", type=int, required=True)
    ap.add_argument("--ncell", type=int, required=True)
    ap.add_argument("--years", type=int, nargs=2, default=(2000, 2000))
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tag", default="emulated")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    (run_dir / "restart").mkdir(parents=True, exist_ok=True)

    saved = path("ground_truth.historical_seed1") / SAVED_CONFIG_SUBDIR
    if not saved.exists():
        raise FileNotFoundError(f"the ground truth's saved config is not at {saved}")
    text = saved.read_text(encoding="utf-8")

    # The restart file must sit under the run directory, because the config names it relative to
    # LPJRESTARTPATH and the wrapper points that at the run directory.
    src = Path(args.restart)
    dest = run_dir / "restart" / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)

    first, last = args.years
    text = patch(
        text,
        r'^\s*"startgrid" : "all",.*$',
        f'  "startgrid" : {args.first_cell},\n'
        f'  "endgrid" : {args.first_cell + args.ncell - 1},',
    )
    # Only the FROM_RESTART (transient) block is selected at run time, but both blocks carry these
    # keys, so each patch expects two hits and both are set consistently.
    text = patch(text, r'^\s*"firstyear": \d+,.*$', f'  "firstyear": {first},', expect=2)
    text = patch(text, r'^\s*"lastyear" : \d+,.*$', f'  "lastyear" : {last},', expect=2)
    text = patch(
        text,
        r'^\s*"restart_filename" : "restart/[^"]+",.*$',
        f'  "restart_filename" : "restart/{dest.name}",',
    )
    text = patch(
        text,
        r'^\s*"write_restart_filename" : "restart/[^"]+",.*$',
        f'  "write_restart_filename" : "restart/restart_{last}_{args.tag}.lpj",',
        expect=2,
    )
    # No trailing comma on this one -- it is the last key before the `#endif` -- but it does carry
    # a trailing comment, which is why the pattern cannot be anchored straight to end-of-line.
    text = patch(text, r'^\s*"restart_year": \d+.*$', f'  "restart_year": {last}', expect=2)
    # Output year: the transient block starts output at 1990, which precedes `first` here.
    text = patch(text, r'^\s*"outputyear": \d+,.*$', f'  "outputyear": {first},')
    # Name the outputs after this run so they cannot be confused with the ground truth's.
    text = patch(
        text,
        r'"name" : "output/([a-zA-Z_]+)_?[0-9_]*\.(nc|csv)"',
        rf'"name" : "output/\1_{args.tag}.\2"',
        expect=7,
    )

    out = run_dir / f"lpjml_{args.tag}.js"
    out.write_text(text, encoding="utf-8")
    print(f"config:  {out}")
    print(f"restart: {dest}  ({dest.stat().st_size / 1e6:.1f} MB)")
    print(f"cells:   {args.first_cell}..{args.first_cell + args.ncell - 1}  years {first}-{last}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
