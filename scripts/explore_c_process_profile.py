#!/usr/bin/env python3
"""Line X exploration probe — WHERE DOES THE ORIGINAL MODEL'S RUNTIME GO, BY PROCESS?

Owner's question (2026-09-02): *"find out which parts of the original model consume most
computational time (e.g. photosynthesis or other processes). we can use this as basis for
exploring solutions where only these processes are learned."*

WHAT THIS ADDS OVER WHAT ALREADY EXISTS. ADR 0093 (owner-approved) already reports four
INCLUSIVE shares from a `perf` profile of the C binary at the Hainich block: `update_daily`
98.6 %, `water_stressed` 49.4 %, `photosynthesis` 41.3 %, the lambda bisection 33.3 %.
Those are nested, so they CANNOT be used for Amdahl arithmetic ("what do I gain if I replace
process X?"), and they attribute nothing to the other ~50 % of the run. This probe produces
the three things that question needs and that no record has:

  1. an EXCLUSIVE (self-time) attribution that SUMS TO 100 %, grouped into named processes;
  2. the statically-linked Intel math routines (`__libm_*` / `__svml_*`) attributed to their
     CALLING process from the recorded call graph, because they carry ~24 % of self time and
     have no source file, so a srcfile-only grouping silently drops a quarter of the run;
  3. the AMDAHL CEILING per process — the maximum whole-model speed-up if that process
     became free, and if it became 10x faster. This is the number that decides whether
     "learn only process X" can ever reach the speed target.

⚠ NO REBUILD, NO SOURCE CHANGE, NOTHING WRITTEN NEAR THE ORACLE. The production binary
already carries debug symbols and is not stripped, so `perf record` needs neither. This
matters: a rebuild changes the reference basis every C-vs-emulator number in the repo is
measured against (CLAUDE.md section 3), and this probe deliberately avoids that entirely.
It only READS `perf.data` files. Recording them is done by the existing, unmodified
`scripts/bench_speed_gate_c.sh` with `PERF=1` (line O's harness, invoked not edited), with
`ROOT` pointed at line X's own scratch.

PRE-REGISTRATION — printed before any result, and the gates are stated as pass/fail numbers.

  Blessed statistic: self (exclusive) percentage of total cycles per process group, on a
  21-cell block x 20 years x 25 patches, single task, from a spin-up-end restart.

  GATE 1 (completeness): the process groups' self shares must sum to 100.0 +/- 0.5 %, and
    the `other` + `unmapped` groups together must stay under 8 %. If `unmapped` is large the
    symbol map is stale and every number below is wrong.
  GATE 2 (basis agreement with the record): the INCLUSIVE share of `update_daily` must land
    within 2 points of ADR 0093's 98.6 %, and `photosynthesis` inclusive within 5 points of
    its 41.3 %. This is what proves the probe is profiling the same thing that ADR 0093 did.
    ⚠ A miss is NOT automatically this probe's error — ADR 0093 used `--percent-limit 0.5`
    and may have profiled a different block. Report both, do not silently adopt either.
  GATE 3 (math attribution closes): the math self time redistributed to callers must equal
    the math self time measured directly, to 0.5 points.

  NULL (the one that makes the Amdahl column meaningful): the ceiling for a process of share
    s is exactly 1/(1-s). For the WHOLE daily loop this must reproduce the known total,
    i.e. removing everything outside the daily loop can buy at most ~1.02x. Any claim that a
    single process replacement buys more than 1/(1-s) is arithmetically impossible, and that
    is the point of reporting the column.

  FALSIFIER for the owner's strategy: if NO single process has a self share above 0.5 (i.e.
  no single-process replacement can buy 2x), then "learn only the expensive process" cannot
  reach the speed target on its own and the honest answer is a PORTFOLIO or a whole-daily-loop
  replacement. State which of the two the measurement supports.

Usage
-----
    python3 scripts/explore_c_process_profile.py <perf.data> [<perf.data> ...]
    python3 scripts/explore_c_process_profile.py --discover       # find them under the roots

Writes `<outdir>/cprof_processes.csv`, `cprof_symbols.csv`, `cprof_math_callers.csv`
(outdir defaults to /p/tmp/jamirp/X_explore).
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.environ.get("CPROF_OUT", "/p/tmp/jamirp/X_explore")
DISCOVER_ROOTS = ("/p/tmp/jamirp/X_cprofile", "/p/tmp/jamirp/O_speedgate_c")

#: ADR 0093's published INCLUSIVE shares, for GATE 2. Read from the ADR, not re-derived.
ADR0093_INCLUSIVE = {"update_daily": 98.6, "water_stressed": 49.4, "photosynthesis": 41.3}

#: Source file -> process group. Grouped by what the code DOES, because that is the unit a
#: "learn only this process" proposal would replace. Keys are basenames as `perf` prints them.
#: ⚠ Every group boundary here is a judgement call and is stated so the reader can regroup:
#: in particular `bisect.c`/`fcn` is the lambda root-find, which is INSIDE leaf gas exchange
#: physically but is a SEPARATE learning target (an iterative solve whose answer is a smooth
#: function of its inputs), so it is reported as its own group as well as folded in.
SRCFILE_GROUP = {
    # --- leaf gas exchange: the assimilation/conductance kernel, per individual per day ---
    "photosynthesis.c": "leaf_gas_exchange",
    "water_stressed.c": "leaf_gas_exchange",
    "gp_sum.c": "leaf_gas_exchange",
    "temp_stress.c": "leaf_gas_exchange",
    "temp_response.c": "leaf_gas_exchange",
    # --- the lambda root-find that WRAPS the kernel (own group; see note above) ---
    "bisect.c": "lambda_solve",
    # --- canopy light / radiation geometry ---
    "getfpar.c": "canopy_light",
    "lai_tree.c": "canopy_light",
    "lai_grass.c": "canopy_light",
    "albedo_tree.c": "canopy_light",
    "albedo_stand.c": "canopy_light",
    "albedo_grass.c": "canopy_light",
    "update_fbd_tree.c": "canopy_light",
    "update_fbd_grass.c": "canopy_light",
    "fpc_tree.c": "canopy_light",
    "fpc_grass.c": "canopy_light",
    # --- soil hydrology ---
    "infil_perc_rain.c": "soil_water",
    "infil_perc_irr.c": "soil_water",
    "interception.c": "soil_water",
    "waterbalance.c": "soil_water",
    "pedotransfer.c": "soil_water",
    "getrootdist.c": "soil_water",
    "freezefrac2soil.c": "soil_water",
    "snow.c": "soil_water",
    "soilwater.c": "soil_water",
    # --- soil thermal / enthalpy column ---
    "calc_soil_thermal_props.c": "soil_thermal",
    "apply_heatconduction_of_a_day.c": "soil_thermal",
    "update_soil_thermal_state.c": "soil_thermal",
    "apply_enth_of_untracked_mass_shifts.c": "soil_thermal",
    "soiltemp.c": "soil_thermal",
    "enth2temp.c": "soil_thermal",
    "compute_mean_layer_temps_of_a_day.c": "soil_thermal",
    # --- litter + soil carbon decomposition ---
    "littersom.c": "soil_carbon",
    "litter_ag_tree.c": "soil_carbon",
    "litter_ag_grass.c": "soil_carbon",
    "littersum.c": "soil_carbon",
    # --- phenology + daily leaf turnover ---
    "phenology_gsi.c": "phenology",
    "turnover_daily_tree.c": "phenology",
    "turnover_daily_grass.c": "phenology",
    "phenology_tree.c": "phenology",
    # --- the ANNUAL demography block: what the project's learned component replaces ---
    "annual_natural.c": "demography_annual",
    "annual_tree.c": "demography_annual",
    "annual_grass.c": "demography_annual",
    "allocation_tree.c": "demography_annual",
    "allocation_grass.c": "demography_annual",
    "mortality_tree_ind.c": "demography_annual",
    "mortality_tree.c": "demography_annual",
    "mortality_grass.c": "demography_annual",
    "establishmentpft_ind.c": "demography_annual",
    "establishment.c": "demography_annual",
    "turnover_tree.c": "demography_annual",
    "turnover_grass.c": "demography_annual",
    "new_tree.c": "demography_annual",
    "reproduction_tree.c": "demography_annual",
    "veg_sum_tree.c": "demography_annual",
    "agb_tree.c": "demography_annual",
    "update_annual.c": "demography_annual",
    "light.c": "demography_annual",
    "getsapling.c": "demography_annual",
    "survive.c": "demography_annual",
    "waterstress_tree.c": "demography_annual",
    "tempstress_tree.c": "demography_annual",
    # --- the daily driver itself (loop overhead, PFT permutation, dispatch) ---
    "daily_natural.c": "driver_daily",
    "update_daily.c": "driver_daily",
    "permute.c": "driver_daily",
    "iterateyear.c": "driver_daily",
    "iterate.c": "driver_daily",
    "daily_stand.c": "driver_daily",
    # --- output / bookkeeping ---
    "fwriteoutput.c": "io_output",
    "fwriteoutput_ind.c": "io_output",
    "initoutputdata.c": "io_output",
    "soilpar_output.c": "io_output",
    "isdailyoutput_natural.c": "io_output",
    "outputbuffer.c": "io_output",
    # --- water/carbon closure checks (-DSAFE) ---
    "check_fluxes.c": "closure_checks",
}

#: Symbols with NO source file: the statically linked Intel math routines. Matched by regex.
MATH_RE = re.compile(r"^(__libm_|__svml_|__ieee754|pow$|exp$|log$|exp2$|log2$|sqrt$)")

#: Symbol-name fallback for functions whose srcfile perf cannot resolve but whose owner is
#: unambiguous from the name. Kept SMALL and explicit — a big fallback map hides a stale probe.
SYMBOL_GROUP = {
    "fcn": "lambda_solve",  # the residual closure the bisection evaluates (water_stressed.c)
    "use_temp_scheme_implicit": "soil_thermal",
    "albedo_patch": "canopy_light",
}


def sh(cmd: list[str]) -> str:
    """Run a command, return stdout, tolerate perf's noisy stderr."""
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0 and not r.stdout:
        raise RuntimeError(f"failed: {' '.join(cmd)}\n{r.stderr[:400]}")
    return r.stdout


def parse_rows(text: str, ncols: int) -> list[list[str]]:
    """Parse `perf report --stdio` body rows: '  12.34%  colA  colB ...'."""
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"\s*([0-9]+\.[0-9]+)%\s+(.*)$", line)
        if not m:
            continue
        rest = m.group(2).rstrip()
        parts = re.split(r"\s{2,}", rest)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) < ncols:
            parts = parts + [""] * (ncols - len(parts))
        out.append([m.group(1)] + parts[:ncols])
    return out


def self_by_symbol(perf: str) -> list[tuple[float, str, str]]:
    """-> [(self_pct, symbol, srcfile)] with EVERY sample included (percent-limit 0)."""
    txt = sh(
        [
            "perf", "report", "-i", perf, "--no-children", "-g", "none",
            "--sort", "symbol,srcfile", "--percent-limit", "0", "--stdio",
        ]
    )
    rows = []
    for r in parse_rows(txt, 2):
        pct = float(r[0])
        sym = r[1].removeprefix("[.]").removeprefix("[k]").strip()
        src = os.path.basename(r[2]) if r[2] else ""
        rows.append((pct, sym, src))
    return rows


def inclusive_by_symbol(perf: str) -> dict[str, float]:
    """-> {symbol: inclusive_pct} for GATE 2 against ADR 0093."""
    txt = sh(
        [
            "perf", "report", "-i", perf, "--children", "-g", "none",
            "--sort", "symbol", "--percent-limit", "0.05", "--stdio",
        ]
    )
    out: dict[str, float] = {}
    for line in txt.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"\s*([0-9]+\.[0-9]+)%\s+([0-9]+\.[0-9]+)%\s+(.*)$", line)
        if not m:
            continue
        # ⚠ `--sort symbol` still prints trailing IPC columns, separated by 2+ spaces. A bare
        # .strip() leaves them glued to the symbol name and every lookup misses — which is
        # exactly what GATE 2 caught on the first run of this probe.
        tail = m.group(3).removeprefix("[.]").removeprefix("[k]")
        sym = re.split(r"\s{2,}", tail.strip())[0].strip()
        out.setdefault(sym, float(m.group(1)))
    return out


def math_callers(perf: str, symbols: list[str]) -> list[tuple[str, str, float]]:
    """-> [(math_symbol, immediate_caller, pct_of_total)] from the recorded call graph."""
    if not symbols:
        return []
    txt = sh(
        [
            "perf", "report", "-i", perf, "--no-children",
            "-g", "caller,0.0,callee", "--symbols", ",".join(symbols),
            "--percent-limit", "0", "--stdio",
        ]
    )
    # ⚠ perf prints the caller tree at INCREASING INDENT: the immediate callers of the math
    # symbol sit at the shallowest leg depth, and their own callers are printed nested beneath
    # them with their own percentages. Summing legs at every depth double-counts the same
    # cycles — on the first run of this probe that inflated the attributed total from 25.4 %
    # to 39.2 %, which is what GATE 3 caught. So: keep ONLY the shallowest depth per symbol.
    per_sym: dict[str, dict[int, list[tuple[str, float]]]] = {}
    cur: str | None = None
    for line in txt.splitlines():
        head = re.match(r"\s*([0-9]+\.[0-9]+)%\s+\S+\s+\S+\s+\[[.k]\]\s+(\S+)", line)
        if head:
            cur = head.group(2)
            per_sym.setdefault(cur, {})
            continue
        if cur is None:
            continue
        # '--5.61%--photosynthesis' / '|--0.88%--gp_sum'; the match column IS the depth.
        leg = re.search(r"--([0-9]+\.[0-9]+)%--(\S+)", line)
        if leg:
            per_sym[cur].setdefault(leg.start(), []).append(
                (leg.group(2), float(leg.group(1)))
            )
    out: list[tuple[str, str, float]] = []
    for msym, by_depth in per_sym.items():
        if not by_depth:
            continue
        shallowest = min(by_depth)
        for caller, pct in by_depth[shallowest]:
            out.append((msym, caller, pct))
    return out


def group_of(sym: str, src: str) -> str:
    if MATH_RE.match(sym):
        return "math_library"
    if src in SRCFILE_GROUP:
        return SRCFILE_GROUP[src]
    # ⚠ LPJmL's convention is one function per file, named the same: `photosynthesis` lives in
    # `photosynthesis.c`, `getrootdist` in `getrootdist.c`. That makes the function NAME a
    # reliable fallback whenever perf resolves a sample to a header or an inlined file instead
    # of the defining one — which it does often enough that without this fallback 24 of the
    # 25 percentage points of math time landed in `other_src` with the right caller name
    # sitting in the row.
    if sym + ".c" in SRCFILE_GROUP:
        return SRCFILE_GROUP[sym + ".c"]
    if sym in SYMBOL_GROUP:
        return SYMBOL_GROUP[sym]
    if src:
        return "other_src"
    return "unmapped_nosrc"


def analyse(perf: str) -> dict:
    syms = self_by_symbol(perf)
    incl = inclusive_by_symbol(perf)

    groups: dict[str, float] = {}
    for pct, sym, src in syms:
        groups[group_of(sym, src)] = groups.get(group_of(sym, src), 0.0) + pct

    math_syms = [s for _, s, _ in syms if MATH_RE.match(s)]
    math_self = sum(p for p, s, _ in syms if MATH_RE.match(s))
    callers = math_callers(perf, math_syms[:12]) if math_syms else []

    # Redistribute the math self time to the calling process, in proportion to the measured
    # caller legs. A caller we cannot group lands in `unmapped_nosrc`, never silently dropped.
    src_of_sym = {s: src for _, s, src in syms}
    redist: dict[str, float] = {}
    attributed = 0.0
    for _msym, caller, pct in callers:
        g = group_of(caller, src_of_sym.get(caller, ""))
        if g == "math_library":
            g = "unmapped_nosrc"
        redist[g] = redist.get(g, 0.0) + pct
        attributed += pct

    # Whatever the call graph could not resolve to a caller stays visible as its own row
    # rather than being silently folded into a process. GATE 3 is about how big this is.
    residual = math_self - attributed
    if abs(residual) > 1e-9:
        redist["math_unattributed"] = redist.get("math_unattributed", 0.0) + residual
        groups.setdefault("math_unattributed", 0.0)

    total = sum(groups.values())
    return {
        "perf": perf,
        "groups": groups,
        "math_self": math_self,
        "math_attributed": attributed,
        "math_redist": redist,
        "inclusive": incl,
        "total": total,
        "n_symbols": len(syms),
    }


def report(res: dict) -> list[str]:
    lines: list[str] = []
    g, tot = res["groups"], res["total"]
    lines.append(f"\n### {res['perf']}   ({res['n_symbols']} symbols, self sums to {tot:.2f} %)")

    lines.append("\n-- GATES --")
    ok1 = abs(tot - 100.0) <= 0.5
    slop = g.get("other_src", 0.0) + g.get("unmapped_nosrc", 0.0)
    lines.append(
        f"GATE 1 completeness: self sums to {tot:.2f} % (need 100.0 +/- 0.5) -> "
        f"{'PASS' if ok1 else 'FAIL'}; other+unmapped {slop:.2f} % (need < 8) -> "
        f"{'PASS' if slop < 8 else 'FAIL'}"
    )
    for sym, want in ADR0093_INCLUSIVE.items():
        got = res["inclusive"].get(sym)
        tolv = 2.0 if sym == "update_daily" else 5.0
        verdict = "n/a" if got is None else ("PASS" if abs(got - want) <= tolv else "MISS")
        lines.append(
            f"GATE 2 vs ADR 0093 inclusive {sym}: got "
            f"{'--' if got is None else f'{got:.2f}'} % vs published {want} % "
            f"(tol {tolv}) -> {verdict}"
        )
    d = abs(res["math_self"] - res["math_attributed"])
    lines.append(
        f"GATE 3 math attribution closes: self {res['math_self']:.2f} % vs "
        f"attributed-to-callers {res['math_attributed']:.2f} % (diff {d:.2f}, need < 0.5) -> "
        f"{'PASS' if d < 0.5 else 'FAIL'}"
    )

    lines.append("\n-- SELF TIME BY PROCESS, and the AMDAHL CEILING --")
    lines.append(
        f"{'process':<22}{'self %':>9}{'+math %':>9}{'total %':>9}"
        f"{'free':>8}{'10x faster':>12}"
    )
    rows = []
    for name in sorted(g, key=lambda k: -(g[k] + res["math_redist"].get(k, 0.0))):
        if name == "math_library":
            continue
        self_pct = g[name]
        plus = res["math_redist"].get(name, 0.0)
        tp = self_pct + plus
        s = tp / 100.0
        free = 1.0 / (1.0 - s) if s < 1 else float("inf")
        ten = 1.0 / (1.0 - 0.9 * s)
        rows.append((name, self_pct, plus, tp, free, ten))
        lines.append(
            f"{name:<22}{self_pct:>9.2f}{plus:>9.2f}{tp:>9.2f}{free:>8.2f}x{ten:>11.2f}x"
        )
    lines.append(
        f"{'(math library, before':<22}{res['math_self']:>9.2f}"
        "   <- redistributed to callers above)"
    )
    res["rows"] = rows

    top = max(rows, key=lambda r: r[3]) if rows else None
    if top:
        lines.append(
            f"\n-- FALSIFIER --\nlargest single process = {top[0]} at {top[3]:.2f} % "
            f"=> ceiling {top[4]:.2f}x if made FREE. "
            + (
                "No single-process replacement reaches 2x => the owner's strategy needs a "
                "PORTFOLIO or a whole-daily-loop replacement."
                if top[3] < 50.0
                else "A single-process replacement can exceed 2x."
            )
        )
    return lines


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--discover" in sys.argv or not args:
        args = []
        for root in DISCOVER_ROOTS:
            for dirpath, _dirs, files in os.walk(root):
                if "perf.data" in files:
                    args.append(os.path.join(dirpath, "perf.data"))
        args.sort()
    if not args:
        print(
            "no perf.data found; record one with PERF=1 scripts/bench_speed_gate_c.sh",
            file=sys.stderr,
        )
        return 2

    print(__doc__.split("Usage")[0])
    print(f"repo    : {REPO}")
    print(f"outdir  : {OUTDIR}")
    print(f"profiles: {len(args)}")
    for a in args:
        print(f"          {a}")
    print("\n" + "=" * 100)

    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for perf in args:
        try:
            res = analyse(perf)
        except Exception as exc:  # noqa: BLE001 - a bad profile must not kill the others
            print(f"\n### {perf}\n  ERROR: {exc}")
            continue
        print("\n".join(report(res)))
        results.append(res)

    with open(os.path.join(OUTDIR, "cprof_processes.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["perf_data", "process", "self_pct", "math_pct", "total_pct",
             "amdahl_free", "amdahl_10x"]
        )
        for res in results:
            for name, self_pct, plus, tp, free, ten in res.get("rows", []):
                w.writerow(
                    [res["perf"], name, f"{self_pct:.4f}", f"{plus:.4f}", f"{tp:.4f}",
                     f"{free:.4f}", f"{ten:.4f}"]
                )

    with open(os.path.join(OUTDIR, "cprof_symbols.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["perf_data", "self_pct", "symbol", "srcfile", "process"])
        for res in results:
            for pct, sym, src in self_by_symbol(res["perf"]):
                w.writerow([res["perf"], f"{pct:.4f}", sym, src, group_of(sym, src)])

    with open(os.path.join(OUTDIR, "cprof_math_callers.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["perf_data", "math_symbol", "caller", "pct_of_total", "caller_process"])
        for res in results:
            src_of = {s: src for _, s, src in self_by_symbol(res["perf"])}
            msyms = [s for _, s, _ in self_by_symbol(res["perf"]) if MATH_RE.match(s)]
            for msym, caller, pct in math_callers(res["perf"], msyms[:12]):
                w.writerow(
                    [res["perf"], msym, caller, f"{pct:.4f}",
                     group_of(caller, src_of.get(caller, ""))]
                )

    print(f"\nwrote {OUTDIR}/cprof_processes.csv, cprof_symbols.csv, cprof_math_callers.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
