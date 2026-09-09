#!/usr/bin/env python
"""Which of the 22 scored quantities BINDS the level model, and which have room left?

    ALLOW_LOGIN_HEAVY=1 python scripts/diag_level_binding.py

Read-only, and it fits nothing: it reads the out-of-fold predictions the level-map job already
wrote (`oof_map.parquet`) and asks where that already-reported error lives. Seconds on a login
node, no SLURM, no experiment id -- it produces no new skill number, only a decomposition of one.

WHY THIS EXISTS AS A SCRIPT AND NOT A ONE-OFF. Two mistakes it is built to prevent, both of which
were actually made on this line:

  1. AIMING AT THE QUANTITY WITH THE WORST-LOOKING SCORE. The blessed statistic is conjunctive --
     a cell passes only if all 22 are inside the band -- so a quantity's marginal worth is not its
     own pass rate. It is how far the conjunctive score moves when that one quantity is replaced
     by the truth -- the leave-one-out oracle below. A quantity can fail 30 % of cells and be
     worth nothing, because the cells it fails are failing something else too. `height_p90` is
     exactly that case: it fails 31.5 % of cells and its oracle is worth +0.0006.

  2. CONFUSING THE 10 % FLOOR WITH THE MODEL'S OWN NOISE. The tolerance is
     max(10 %, LPJmL-FIT's two-seed relative spread), so the stored band recovers that spread
     wherever it exceeds the floor -- and only there. Splitting cells into the half the original
     model reproduces and the half it does not separates reducible emulator error from
     realisation scatter nobody can predict. Biomass and height look similar on a pass rate and
     are opposites under this split.

⚠ EVERY ORACLE NUMBER HERE HAS SEEN THE ANSWER for the quantity it substitutes. It bounds where
effort can pay. It is never emulator skill and must never be quoted as any.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vegemu.paths import path
from vegemu.score import FLOOR, SCORED_CONJUNCTIVE, TRAITS_SCORED, band_hits

Array = npt.NDArray[np.float64]

# Oracle groups worth asking about, as (label, quantities). Each answers a question someone has
# actually asked on this line: is it the tail, the whole height distribution, the stocks, or the
# trait distributions that holds the conjunctive score down?
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("height tail alone", ("height_p90",)),
    ("all three height knots", ("height_p10", "height_p50", "height_p90")),
    ("rooting depth, all three", ("D95max_p10", "D95max_p50", "D95max_p90")),
    ("the four stocks", ("stems_per_patch", "agb", "lai", "soilc")),
    ("every low tail (p10)", tuple(f"{t}_p10" for t in TRAITS_SCORED)),
    ("every high tail (p90)", tuple(f"{t}_p90" for t in TRAITS_SCORED)),
    ("all six trait medians", tuple(f"{t}_p50" for t in TRAITS_SCORED)),
)


def load(src: Path) -> tuple[Array, Array, Array, Array, pl.DataFrame]:
    """(truth, pred, band, address-null) matrices in `SCORED_CONJUNCTIVE` order, plus the frame."""
    df = pl.read_parquet(src)

    def stack(prefix: str) -> Array:
        cols = [f"{prefix}_{q}" for q in SCORED_CONJUNCTIVE]
        out: Array = df.select(cols).to_numpy().astype(np.float64)
        return out

    return stack("truth"), stack("pred"), stack("band"), stack("addr"), df


def report_binding(truth: Array, pred: Array, band: Array, addr: Array) -> None:
    hit = band_hits(pred, truth, band)
    hit_null = band_hits(addr, truth, band)
    base = float(hit.all(axis=1).mean())
    n = truth.shape[0]
    nfail = (~hit).sum(axis=1)

    print(f"{n} cells, {len(SCORED_CONJUNCTIVE)} quantities")
    print(f"  conjunctive band_frac, model                   {base:.4f}")
    print(
        f"  conjunctive band_frac, geographic-address null {float(hit_null.all(axis=1).mean()):.4f}"
    )
    print(
        f"  median quantities hit: model {int(np.median(hit.sum(axis=1)))}"
        f"/{len(SCORED_CONJUNCTIVE)}, null {int(np.median(hit_null.sum(axis=1)))}"
        f"/{len(SCORED_CONJUNCTIVE)}"
    )

    # Failure is a property of the CELL, not of the quantity, if the conjunctive rate greatly
    # exceeds the product of the marginals. That ratio decides whether to chase quantities at all.
    independent = float(np.prod(1.0 - (~hit).mean(axis=0)))
    print(f"\n  conjunctive pass if the 22 failures were INDEPENDENT: {independent:.4f}")
    print(f"  observed / independent: {base / independent:.1f}x  -- >1 means failure clusters in")
    print("  the same cells, so a subset of cells is broadly wrong and the rest broadly right.")
    near = (nfail >= 1) & (nfail <= 3)
    print(
        f"  cells failing nothing {int((nfail == 0).sum()):6d} ({100 * (nfail == 0).mean():4.1f}%)"
        f"   1-3 {int(near.sum()):6d} ({100 * near.mean():4.1f}%, the reachable margin)"
        f"   >=9 {int((nfail >= 9).sum()):6d} ({100 * (nfail >= 9).mean():4.1f}%)"
    )

    print("\n" + "=" * 100)
    print("PER QUANTITY, ordered by the LEAVE-ONE-OUT ORACLE GAIN -- its marginal worth")
    print("=" * 100)
    print(
        f"{'quantity':18s} {'pass%':>6s} {'null%':>6s} {'oracle':>8s} {'gain':>8s} "
        f"{'sole-fail':>9s} {'near-miss':>9s}"
    )
    rows = []
    for j, q in enumerate(SCORED_CONJUNCTIVE):
        spoofed = pred.copy()
        spoofed[:, j] = truth[:, j]
        oracle = float(band_hits(spoofed, truth, band).all(axis=1).mean())
        rows.append(
            (
                q,
                float(hit[:, j].mean()),
                float(hit_null[:, j].mean()),
                oracle,
                oracle - base,
                int(((nfail == 1) & ~hit[:, j]).sum()),
                int((near & ~hit[:, j]).sum()),
            )
        )
    for q, ps, ns, oracle, gain, sole, nm in sorted(rows, key=lambda r: -r[4]):
        print(
            f"{q:18s} {100 * ps:5.1f}% {100 * ns:5.1f}% {oracle:8.4f} {gain:+8.4f} "
            f"{sole:9d} {nm:9d}"
        )
    print("\n  sole-fail = cells failing ONLY this quantity, which perfecting it would flip.")
    print("  near-miss = cells failing 1-3 quantities of which this is one.")

    print("\n" + "=" * 100)
    print("JOINT ORACLES")
    print("=" * 100)
    for label, group in GROUPS:
        idx = [SCORED_CONJUNCTIVE.index(q) for q in group]
        spoofed = pred.copy()
        for j in idx:
            spoofed[:, j] = truth[:, j]
        o = float(band_hits(spoofed, truth, band).all(axis=1).mean())
        print(f"  {label:28s} {len(idx):2d} perfected -> {o:.4f}  ({o - base:+.4f})")


def report_room(truth: Array, pred: Array, band: Array) -> None:
    print("\n" + "=" * 104)
    print("REDUCIBLE ERROR vs REALISATION SCATTER, split by whether LPJmL-FIT reproduces itself.")
    print("The band is max(10 %, two-seed spread)*|truth|, so band/|truth| recovers that spread")
    print("wherever it exceeds the floor. e/tol > 1 means the median cell of that half is OUTSIDE")
    print("its band; a quantity failing in the REPRODUCIBLE half is missing learnable signal.")
    print("=" * 104)
    print(f"{'quantity':18s} | {'REPRODUCIBLE (spread<=10%)':^33s} | {'NOISY (spread>10%)':^33s}")
    print(
        f"{'':18s} | {'n':>7s} {'pass%':>7s} {'med|r-1|':>8s} {'e/tol':>6s} | "
        f"{'n':>7s} {'pass%':>7s} {'med|r-1|':>8s} {'e/tol':>6s}"
    )
    for j, q in enumerate(SCORED_CONJUNCTIVE):
        t, p, b = truth[:, j], pred[:, j], band[:, j]
        ok = np.isfinite(t) & np.isfinite(p) & np.isfinite(b) & (t > 0) & (p > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            tol = np.where(ok, b / np.abs(t), np.nan)
            err = np.where(ok, np.abs(p / t - 1.0), np.nan)
        inband = ok & (np.abs(p - t) <= b)
        cells = []
        for sel in ((tol <= FLOOR + 1e-12) & ok, (tol > FLOOR + 1e-12) & ok):
            if not sel.any():
                cells.append(f"{0:7d} {'--':>7s} {'--':>8s} {'--':>6s}")
                continue
            e = float(np.nanmedian(err[sel]))
            m = float(np.nanmedian(tol[sel]))
            cells.append(
                f"{int(sel.sum()):7d} {100 * inband[sel].mean():6.1f}% {e:8.4f} {e / m:6.2f}"
            )
        print(f"{q:18s} | {cells[0]} | {cells[1]}")


def report_by_size(truth: Array, pred: Array, band: Array) -> None:
    """Conjunctive pass by decile of true biomass. Failure is concentrated, not uniform."""
    hit = band_hits(pred, truth, band)
    nfail = (~hit).sum(axis=1)
    key = truth[:, SCORED_CONJUNCTIVE.index("agb")]
    ok = np.isfinite(key) & (key > 0)
    edges = np.quantile(key[ok], np.linspace(0.0, 1.0, 11))
    watch = ("agb", "D95max_p10", "soilc", "height_p90")
    print("\n" + "=" * 100)
    print("WHERE THE FAILURE IS, by decile of TRUE above-ground biomass")
    print("=" * 100)
    header = f"{'dec':>3s} {'agb range (gC/m2)':>22s} {'n':>6s} {'conj%':>6s} {'medfail':>7s}"
    print(header + "".join(f"{q[:10]:>11s}" for q in watch))
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        sel = ok & (key >= lo) & ((key <= hi) if i == 9 else (key < hi))
        if not sel.any():
            continue
        line = (
            f"{i + 1:3d} {f'{lo:8.1f}-{hi:9.1f}':>22s} {int(sel.sum()):6d} "
            f"{100 * hit[sel].all(axis=1).mean():5.1f}% {int(np.median(nfail[sel])):7d}"
        )
        line += "".join(
            f"{100 * hit[sel, SCORED_CONJUNCTIVE.index(q)].mean():10.1f}%" for q in watch
        )
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--oof", default=None, help="oof_map.parquet; defaults to the level-map job's own output"
    )
    ap.add_argument(
        "--skip-oracle",
        action="store_true",
        help="skip the 22 leave-one-out oracles (the only slow part)",
    )
    args = ap.parse_args()

    src = (
        Path(args.oof) if args.oof else path("scratch.root") / "exp/map-response-v0/oof_map.parquet"
    )
    if not src.is_file():
        print(f"no such file: {src}\nrun the level-map job first, or pass --oof.", file=sys.stderr)
        return 1
    print(f"{src}\n")
    truth, pred, band, addr, _df = load(src)
    if not args.skip_oracle:
        report_binding(truth, pred, band, addr)
    report_room(truth, pred, band)
    report_by_size(truth, pred, band)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
