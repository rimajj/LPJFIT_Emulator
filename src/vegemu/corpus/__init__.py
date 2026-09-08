"""The corpus: what the emulator is trained on and scored against.

    state     per-cell state summaries read out of a restart file
    climate   per-cell climate summaries read out of the `.clm` forcing

Both sides carry their basis with them -- the source file, the leg, the seed, the year window, the
patch count -- because a number without its basis is not a result (invariant 4), and the basis has
to travel with the data rather than live in a session's memory.
"""

from __future__ import annotations

from vegemu.corpus.climate import CLIMATE_FEATURES, WINDOWS, climate_table
from vegemu.corpus.state import STATE_COLUMNS, state_table, summarise_cell

__all__ = [
    "CLIMATE_FEATURES",
    "STATE_COLUMNS",
    "WINDOWS",
    "climate_table",
    "state_table",
    "summarise_cell",
]
