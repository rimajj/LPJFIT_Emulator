"""LPJmL-FIT's own binary file formats.

    restart   the model's complete state dump -- the project's central deliverable
    clm       the forcing format, whose WRITER is what makes a perturbed climate possible

Both are proven by writing a real file back byte-identically, never by assertion (invariant 7).
The layouts are transcribed from the model's own C sources; `docs/reference/binfmt.md` names the
source file and line for every field, because a spec derived by inspecting bytes is a spec that
drifts the day the model is rebuilt.
"""

from __future__ import annotations

from vegemu.binfmt.restart import (
    Layout,
    RestartHeader,
    RestartReader,
    RestartWriter,
    read_cell,
    write_cell,
)

__all__ = [
    "Layout",
    "RestartHeader",
    "RestartReader",
    "RestartWriter",
    "read_cell",
    "write_cell",
]
