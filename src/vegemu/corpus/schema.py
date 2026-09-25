"""The corpus table's schema version — what a decode writes, and which decodes must not change.

WHY A NUMBER AND NOT A CODE EDIT. Every decoded table on disk is cited by its sha256 in a sealed
pre-registration (`corpus.parquet` of `pilot-v2-constco2` is `9c117cb6...`), so a decoder that
quietly changed what it writes would make each of those tables irreproducible from its own code:
re-run the decode and the hash no longer matches, with nothing to say whether the model changed or
the decoder did. So a change to what a decode PRODUCES is a new schema, the old one stays
reachable bit for bit, and a version's schema is recorded in its own `provenance.json`.

    2  every table decoded up to 2026-09-23 -- v0, pilot-v1, pilot-v2-constco2 and their
       replicates. A version whose provenance names no schema IS schema 2.
    3  schema 2, plus two corrections that each needed a version bump:
         * a treeless row's tree-type shares (`pft_frac_*`) are NaN, not 0.0. With no stems the
           share is 0/0: "no forest", not "a forest with none of this type". Schema 2 wrote zeros,
           and `score.blank_treeless_composition` has been undoing them at every scoring site.
         * the five soil columns of `vegemu.corpus.soil.SOIL_FEATURES` travel in the climate part
           of the table, so a model reads them from the corpus instead of every experiment
           joining them at read time from a script.

⚠ THE LIBRARY DEFAULT IS THE LEGACY SCHEMA, deliberately. Callers outside the corpus pipeline --
`exp_derive_nulls_pilot.py`, `corpus_build.py` -- re-decode EXISTING versions whose tables are
pinned, so they must keep getting schema 2 without being edited. The corpus pipeline
(`scripts/corpus_pilot.py`) passes the schema explicitly, from the plan: a new plan records
`CURRENT`, and a re-decode into a new version writes `CURRENT`.
"""

from __future__ import annotations

LEGACY = 2
CURRENT = 3

SCHEMAS: dict[int, str] = {
    2: "legacy: pft_frac_* = 0.0 on a treeless row; no soil columns (every table up to 2026-09-23)",
    3: "pft_frac_* = NaN on a treeless row (0/0); five soil columns after the climate features",
}


def check(schema: int) -> int:
    """`schema` itself, or a ValueError naming the known ones. Call at every entry point."""
    if schema not in SCHEMAS:
        raise ValueError(f"unknown corpus schema {schema!r}; known: {sorted(SCHEMAS)}")
    return schema


def of_provenance(prov: dict[str, object]) -> int:
    """The schema a version was planned under. No key means it predates the key: schema 2."""
    value = prov.get("schema", LEGACY)
    if not isinstance(value, int):
        raise ValueError(f"provenance names schema {value!r}, which is not an integer")
    return check(value)
