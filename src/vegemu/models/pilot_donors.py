"""A donor rule for `synth_global.py`: the pilot's CONSTANT-CO2 stems, by climate analogue.

    scripts/synth_global.py plan ... --donor-rule vegemu.models.pilot_donors:PilotBank \\
        --donor-opts '{"predictions": "<pred_1901_1930_heldout.parquet>"}'

WHY THIS EXISTS. The default rule (`proximity-band`) takes its donors from the template,
`restart_1999`, which the stored spin-up wrote at 367.26 ppm, after the 1700-1999 CO2 ramp. A
transplanted stem carries its whole record -- pools, allometry, the consecutive bad-years counter --
so the emulated 1699 file was full of trees built for 367 ppm. Continued at 276.59 ppm they shrink,
and the five-bad-years rule (`mortality_tree_ind.c:135`) kills them in continuation year 5: on the
51-member sample of the continuation run, -16.8 % of vegetation carbon in that one year, against
-5.3 % when the same file is continued at 367.26 ppm (journal/X/2026-09b.md, 2026-09-25). The
pilot's 6,000 spin-ups (`pilot-v2-constco2`: 200 cells x 30 climates, 1000 years at 276.59 ppm) are
the only constant-CO2 trees that exist, and `synth_pilot.py --stage bank` stored every stem of them.
This rule hands each global cell the stems of the climatically nearest pilot runs OUTSIDE its
spatial fold, chosen by `synth.choose_analogue_runs` exactly as `synth_pilot.analogue_pool` does.

WANTED TYPES. `pool_for(cell)` runs before the cell rule decides which types the climate admits, so
it asks for every type the rule could place: each type with a positive predicted share (wanted =
predicted stems x share) and each type the cell's template holds (wanted = its template count).
`SpinupRule` places either the predicted shares or, failing those, the template's mix restricted to
the admitted types, so this is a superset of what it can ask for; a surplus type costs pool size.

LEAKAGE. A global cell's fold is the prediction table's `fold` -- the sealed pilot fold of its
15-degree tile (-1 where no pilot cell lies in the tile, so every run is outside it). No run of that
fold is a donor, which also excludes the target's own pilot runs when it is a pilot cell. Asserted
per pool, and the table's folds are checked against the bank's on the 200 pilot cells at start-up.
The standardisation of the climate features uses the candidate (out-of-fold) runs only.

⚠ WHAT THIS DOES NOT FIX. The template is still `restart_1999` for everything the synthesiser
copies (soil water, the restart header, litter before rescaling), and the residual year-5 kill the
367.26-ppm diagnostic showed with the old donors (-5.3 %, placed stems that shrink whatever the
CO2) is a synthesis defect this rule does not touch.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from vegemu.binfmt.restart import RestartReader, read_cell, trees_of
from vegemu.models.synth import NTREE_TYPES, DonorPool, choose_analogue_runs, pool_from_rows
from vegemu.nulls import ANALOGUE_FEATURES
from vegemu.paths import paths

Array = npt.NDArray[np.float64]
SHARE_COLUMNS = tuple(f"pred_pft_frac_{t}" for t in range(NTREE_TYPES))


def _scratch(key: str) -> Path:
    return Path(str(paths()["scratch"][key]))


def default_bank_dir() -> Path:
    return _scratch("exp") / "T-synth-pilot" / "bank"


def default_pilot_features() -> Path:
    return _scratch("corpus") / "pilot-v2-constco2" / "corpus.parquet"


def default_global_climate() -> Path:
    return _scratch("corpus") / "spinup-constco2" / "climate_spinup.parquet"


@lru_cache(maxsize=4)
def _runs(bank_dir: str, pilot_features: str) -> pl.DataFrame:
    """The bank's 6,000 runs (start/count into c<cell>.npy, stems per type, fold) with features."""
    runs = pl.read_parquet(Path(bank_dir) / "runs.parquet").with_columns(
        pl.col("cell").cast(pl.Int64)
    )
    feats = pl.read_parquet(pilot_features, columns=["cell", "point", *ANALOGUE_FEATURES])
    out = runs.join(feats.with_columns(pl.col("cell").cast(pl.Int64)), on=["cell", "point"])
    if out.height != runs.height:
        raise AssertionError(f"{runs.height - out.height} bank runs have no climate features")
    if out.select(ANALOGUE_FEATURES).null_count().sum_horizontal().item():
        raise AssertionError("a bank run has a missing analogue feature")
    return out


@lru_cache(maxsize=256)
def _bank_rows(bank_dir: str, cell: int) -> npt.NDArray[np.uint8]:
    out: npt.NDArray[np.uint8] = np.load(Path(bank_dir) / f"c{cell}.npy", mmap_mode="r")
    return out


class PilotBank:
    """`DonorSource` for one block: pilot constant-CO2 stems by climate analogue, fold excluded."""

    def __init__(
        self,
        template: Path,
        first_cell: int,
        ncell: int,
        *,
        predictions: str,
        bank_dir: str | None = None,
        pilot_features: str | None = None,
        global_climate: str | None = None,
        npatch: int = 25,
        min_stems: int = 200,
        stems_per_wanted: int = 3,
        max_runs: int = 12,
    ) -> None:
        self.template = Path(template)
        # Its own reader, opened per call: the block loop's reader is a different object.
        self._reader = RestartReader(self.template)
        self.bank_dir = str(bank_dir or default_bank_dir())
        self.pilot_features = str(pilot_features or default_pilot_features())
        self.global_climate = str(global_climate or default_global_climate())
        self.predictions = str(predictions)
        self.npatch = int(npatch)
        self.opts = {
            "min_stems": int(min_stems),
            "stems_per_wanted": int(stems_per_wanted),
            "max_runs": int(max_runs),
        }
        self.runs = _runs(self.bank_dir, self.pilot_features)
        last = first_cell + ncell
        cols = ["cell", "fold", *SHARE_COLUMNS, "pred_stems_per_patch", "pred_treeless"]
        pred = pl.read_parquet(self.predictions, columns=cols)
        pred = pred.with_columns(pl.col("cell").cast(pl.Int64))
        pilot_f = (
            self.runs.select(["cell", "fold"])
            .unique()
            .join(pred.select(["cell", pl.col("fold").alias("f_pred")]), on="cell")
        )
        if (pilot_f["fold"] != pilot_f["f_pred"]).any():
            raise AssertionError("the prediction table's folds differ from the bank's")
        pred = pred.filter((pl.col("cell") >= first_cell) & (pl.col("cell") < last))
        self._pred = {int(r["cell"]): r for r in pred.iter_rows(named=True)}
        clim = pl.read_parquet(self.global_climate, columns=["cell", *ANALOGUE_FEATURES])
        clim = clim.with_columns(pl.col("cell").cast(pl.Int64)).filter(
            (pl.col("cell") >= first_cell) & (pl.col("cell") < last)
        )
        self._x = {
            int(c): np.asarray(v, dtype=np.float64)
            for c, v in zip(
                clim["cell"].to_list(), clim.select(ANALOGUE_FEATURES).to_numpy(), strict=True
            )
        }
        self._fold_cache: dict[int, tuple[pl.DataFrame, Array, Array, Array]] = {}
        self.pools = 0
        self.stems = 0
        self.runs_used = 0

    def _candidates(self, fold: int) -> tuple[pl.DataFrame, Array, Array, Array]:
        if fold not in self._fold_cache:
            cand = self.runs.filter(pl.col("fold") != fold)
            z = cand.select(ANALOGUE_FEATURES).to_numpy().astype(np.float64)
            mu, sd = z.mean(axis=0), z.std(axis=0)
            self._fold_cache[fold] = (cand, (z - mu) / sd, mu, sd)
        return self._fold_cache[fold]

    def wanted(self, cell: int) -> dict[int, int]:
        """Stems wanted per type: predicted types by predicted count, template types by theirs."""
        p = self._pred[cell]
        n_cell = max(float(p["pred_stems_per_patch"] or 0.0), 0.0) * self.npatch
        if (p["pred_treeless"] or 0.0) > 0.5:
            n_cell = 0.0
        shares = np.array([p[c] if p[c] is not None else np.nan for c in SHARE_COLUMNS])
        out: dict[int, int] = {}
        if np.all(np.isfinite(shares)) and shares.sum() > 0:
            for t in range(NTREE_TYPES):
                if shares[t] > 0:
                    out[t] = max(1, round(n_cell * shares[t] / shares.sum()))
        rec = read_cell(self._reader.cell_bytes(cell), self._reader.layout)
        if not rec["skip"]:
            ids = [np.asarray(trees_of(pt["pftlist"])["id"]) for pt in rec["stands"][0]["patches"]]
            held = np.bincount(np.concatenate(ids).astype(np.int64), minlength=NTREE_TYPES)
            for t in range(NTREE_TYPES):
                if held[t] > 0:
                    out[t] = max(out.get(t, 0), int(held[t]))
        return out

    def pool_for(self, cell: int) -> DonorPool:
        fold = int(self._pred[cell]["fold"])
        cand, zc, mu, sd = self._candidates(fold)
        zt = (self._x[cell] - mu) / sd
        counts = cand.select([f"n_type_{t}" for t in range(NTREE_TYPES)]).to_numpy()
        chosen = choose_analogue_runs(zt, zc, counts, self.wanted(cell), **self.opts)
        cells = cand["cell"].to_numpy()
        starts, sizes = cand["start"].to_numpy(), cand["count"].to_numpy()
        rows: list[npt.NDArray[np.uint8]] = []
        used: set[tuple[int, int]] = set()
        for t, idx in chosen.items():
            for i in idx:
                c = int(cells[i])
                if c == cell:
                    raise AssertionError(f"cell {cell}: a donor from the target cell itself")
                a = int(starts[i])
                block = np.asarray(_bank_rows(self.bank_dir, c)[a : a + int(sizes[i])])
                rows.append(block[block[:, 0] == t])
                used.add((c, int(i)))
        folds_used = set(cand.filter(pl.col("cell").is_in([u[0] for u in used]))["fold"].to_list())
        if fold != -1 and fold in folds_used:
            raise AssertionError(f"cell {cell}: a donor from its own spatial fold {fold}")
        raw = np.concatenate(rows) if rows else np.zeros((0, 0), dtype=np.uint8)
        pool = pool_from_rows(raw, tuple(sorted({u[0] for u in used})))
        self.pools += 1
        self.stems += pool.n
        self.runs_used += len(used)
        return pool

    def describe(self) -> dict[str, Any]:
        return {
            "rule": "pilot-bank",
            "bank_dir": self.bank_dir,
            "bank_runs": int(self.runs.height),
            "predictions": self.predictions,
            "features": list(ANALOGUE_FEATURES),
            **self.opts,
            "pools_built": self.pools,
            "mean_donor_stems": self.stems / self.pools if self.pools else None,
            "mean_donor_runs": self.runs_used / self.pools if self.pools else None,
        }
