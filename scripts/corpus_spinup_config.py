#!/usr/bin/env python
"""Build an LPJmL-FIT SPIN-UP config that reads a perturbed forcing set for one cell.

    scripts/corpus_spinup_config.py --cell 42490 --forcing <dir> --run-dir <dir> \\
        --tag c42490-control-s1 [--seed 1] [--nspinup 1000]

WHY IT PATCHES THE GROUND TRUTH'S OWN SAVED CONFIG, and asserts every replacement: the same reason
`corpus_cmodel_config.py` does. The run that produced every existing ground-truth leg saved its
exact configuration next to its output, so starting from that file means this run differs from the
truth in EXACTLY the fields named here and in nothing else. A regex that silently matched nothing
would leave the original value standing and the run would quietly use the global forcing, or the
wrong cell, and still succeed. So each patch counts its hits and raises if the count is wrong. That
assertion has already fired once in this repo, on the one key with a trailing comment and no comma.

⚠ THE SPIN-UP IS RUN WITH NO PREPROCESSOR FLAGS AT ALL. The ground truth's own `slurm_spinup.jcf`
calls the binary with no `-D` argument (its `--comment` field says otherwise and is stale). So
`inherit_startyear` is 0, `reservoir` is true, the outputs are the two spin-up ones, and the run
settings come from the `#ifndef FROM_RESTART` branch. Passing `-DSPINUP` would silently be a
DIFFERENT spin-up from the one that made every restart file we compare against.

HOW 1000 MODEL YEARS COME OUT OF A 30-YEAR FILE. `iterate.c:88-119`: the loop runs from
`firstyear - nspinup` to `lastyear`, and any year before the climate file's own first year draws a
RANDOM one of the first `nspinyear` stored years (`shuffle_climate` is on). With the stock
`firstyear 2000, lastyear 1999, nspinup 1000` and a forcing file covering 1970-1999, that is 970
shuffled years followed by the 30 file years in order, and the restart is written at 1999.

⚠ THAT IS 970+30 WHERE THE GROUND TRUTH WAS 901+99, because its forcing file began in 1901. Same
protocol, same 1000 years, different split. A run built here is comparable to another run built
here, never to the stored global output (`MEMORY.md:subset-diverges`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.paths import path

SAVED_DIR = "scripts_for_running_the_model"
SAVED_CONFIG = f"{SAVED_DIR}/lpjml_2000_2019.js"
SAVED_INPUT = f"{SAVED_DIR}/input_2000_2019.js"

# The config key each perturbed file is bound to, and the filename the writer produced.
INPUT_KEY: dict[str, str] = {
    "temp": "tas_pert.clm",
    "prec": "pr_pert.clm",
    "lwnet": "lwnet_pert.clm",
    "swdown": "rsds_pert.clm",
    "humid": "huss_pert.clm",
}


def patch(text: str, pattern: str, replacement: str, expect: int = 1) -> str:
    out, n = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if n != expect:
        raise AssertionError(
            f"pattern {pattern!r} matched {n} times, expected {expect}. The saved config has "
            "changed shape; fix the pattern rather than letting the original value stand."
        )
    return out


def build_input_js(forcing: Path, run_dir: Path, tag: str) -> Path:
    """Rewrite the ground truth's input list so the five climate inputs are the perturbed files."""
    saved = path("ground_truth.historical_seed1") / SAVED_INPUT
    if not saved.exists():
        raise FileNotFoundError(f"the ground truth's saved input list is not at {saved}")
    text = saved.read_text(encoding="utf-8")
    for key, fname in INPUT_KEY.items():
        target = forcing / fname
        if not target.exists():
            raise FileNotFoundError(f"no perturbed forcing file at {target}")
        text = patch(
            text,
            rf'^(\s*"{key}"\s*:\s*\{{\s*"fmt"\s*:\s*"clm",\s*"name"\s*:\s*)"[^"]+"',
            rf'\g<1>"{target}"',
        )
    # Everything else -- soil, coord, soildepth, co2 -- stays exactly as the ground truth had it.
    # CO2 in particular is untouched and never perturbed (MEMORY.md:co2-closed).
    out = run_dir / f"input_{tag}.js"
    out.write_text(text, encoding="utf-8")
    return out


def build_config(
    cell: int, input_js: Path, run_dir: Path, *, tag: str, seed: int, nspinup: int
) -> Path:
    saved = path("ground_truth.historical_seed1") / SAVED_CONFIG
    if not saved.exists():
        raise FileNotFoundError(f"the ground truth's saved config is not at {saved}")
    text = saved.read_text(encoding="utf-8")

    text = patch(
        text, r'^\s*#include "[^"]*input_2000_2019\.js".*$', f'  #include "{input_js}"', expect=2
    )
    text = patch(
        text,
        r'^\s*"startgrid" : "all",.*$',
        f'  "startgrid" : {cell},\n  "endgrid" : {cell},',
    )
    text = patch(text, r'^\s*"random_seed" : \d+,.*$', f'  "random_seed" : {seed},')
    # Only the spin-up branch's outputs are compiled, but they are named after this run so two arms
    # can never overwrite one another if a run directory is ever shared.
    text = patch(
        text,
        r'"name" : "output/globalflux_spinup\.csv"',
        f'"name" : "output/globalflux_spinup_{tag}.csv"',
    )
    text = patch(
        text,
        r'"name" : "output/vegc_spinup_1999\.nc"',
        f'"name" : "output/vegc_spinup_{tag}.nc"',
    )
    text = patch(
        text,
        r'"write_restart_filename" : "restart/restart_1999\.lpj"',
        f'"write_restart_filename" : "restart/restart_{tag}.lpj"',
    )
    if nspinup != 1000:
        # Both branches carry the key ("nspinup" : 0 in the FROM_RESTART one); set both so the file
        # cannot be run through the other branch with a stale value.
        text = patch(text, r'^\s*"nspinup" : \d+,.*$', f'  "nspinup" : {nspinup},', expect=2)

    out = run_dir / f"lpjml_spinup_{tag}.js"
    out.write_text(text, encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", type=int, required=True)
    ap.add_argument("--forcing", required=True, help="directory holding the five *_pert.clm files")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--nspinup",
        type=int,
        default=1000,
        help="1000 is the protocol; a smaller number is a smoke test and is NOT a spin-up",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    (run_dir / "restart").mkdir(parents=True, exist_ok=True)

    input_js = build_input_js(Path(args.forcing), run_dir, args.tag)
    config = build_config(
        args.cell, input_js, run_dir, tag=args.tag, seed=args.seed, nspinup=args.nspinup
    )

    print(f"config:  {config}")
    print(f"inputs:  {input_js}")
    print(f"cell:    {args.cell}  seed {args.seed}  nspinup {args.nspinup}")
    if args.nspinup != 1000:
        print("  ⚠ nspinup != 1000: this is a smoke test, not a spin-up. Do not score it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
