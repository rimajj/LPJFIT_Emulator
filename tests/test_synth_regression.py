"""The deliverable is still reproduced byte for byte by the default synthesiser.

`runs/synth-v5/restart/restart_1999_emulated.lpj` (sha256 1e856119...) is the file every twenty-year
result on record was scored on. Re-running `scripts/synth_restart.py`'s exact recipe -- the same
twenty cells, the same predictions, the same donor pool, the same seeds -- through today's
`synthesise_cell` with no new option must give back its records exactly. The synthetic digests in
`test_synth_composition.py` pin the arithmetic; this pins it on the real file.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import polars as pl
import pytest

from vegemu.binfmt.restart import RestartReader, write_cell
from vegemu.models.synth import build_donor_pool, synthesise_cell
from vegemu.paths import path, paths
from vegemu.score import SCORED_CONJUNCTIVE

SYNTH_V5_SHA256 = "1e856119eb59fd7595b5d81f61768935ffeb23f787d0bc5bc2264862fa9fcaeb"
FIRST_CELL, NCELL, SEED = 42480, 20, 20260908


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


@pytest.mark.needs_real_data
@pytest.mark.slow
def test_the_default_synthesiser_re_emits_synth_v5_record_for_record() -> None:
    v5 = (
        Path(str(paths()["scratch"]["runs"])) / "synth-v5" / "restart" / "restart_1999_emulated.lpj"
    )
    oof = Path(str(paths()["scratch"]["exp"])) / "map-response-v0" / "oof_map.parquet"
    template_file = path("ground_truth.historical_seed1") / "restart" / "restart_1999.lpj"
    if not (v5.exists() and oof.exists() and template_file.exists()):
        pytest.skip("needs synth-v5, its predictions and the ground-truth restart")
    assert _sha256(v5) == SYNTH_V5_SHA256, "the reference file itself has changed"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from synth_restart import DONOR_BAND, _donor_cells  # noqa: PLC0415

    preds = pl.read_parquet(oof)
    lookup = {int(c): i for i, c in enumerate(preds["cell"].to_numpy())}
    matrix = preds.select([f"pred_{q}" for q in SCORED_CONJUNCTIVE]).to_numpy()
    pool = build_donor_pool(
        RestartReader(template_file), _donor_cells(FIRST_CELL, NCELL, DONOR_BAND)
    )
    reader = RestartReader(template_file)
    reference = RestartReader(v5)
    compared = 0
    with reader, reference:
        for i, cell in enumerate(range(FIRST_CELL, FIRST_CELL + NCELL)):
            template = reader.read(cell)
            if cell not in lookup or template["skip"]:
                assert reference.cell_bytes(i) == reader.cell_bytes(cell)
                continue
            prediction = dict(
                zip(SCORED_CONJUNCTIVE, [float(v) for v in matrix[lookup[cell]]], strict=True)
            )
            rec, _ = synthesise_cell(
                template,
                prediction,
                pool,
                reader.layout,
                cell=cell,
                template_cell=cell,
                seed=SEED + cell,
            )
            assert write_cell(rec, reader.layout) == reference.cell_bytes(i), f"cell {cell}"
            compared += 1
    assert compared > 0
