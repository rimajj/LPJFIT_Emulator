"""The block `tools/append_result.py` requires, built by the job that produced the numbers.

WHY THIS IS A MODULE AND NOT FOUR LINES IN EACH SCRIPT. `append_result.py` is the only sanctioned
writer of `result.jsonl`, and it refuses a metrics file that cannot prove which pre-registration
governed the run. The proof is `VEGEMU_PREREG_SHA256`, which the launcher stamps into the JOB'S
environment -- so it has to be read inside the job, at the moment the numbers exist. Rebuilding it
afterwards from the working tree would produce the same string in the ordinary case and a
*silently wrong* one in exactly the case the check exists to catch: a pre-registration edited after
its run. A helper each script calls is how that stays true in every script rather than in the first
one somebody remembered.

THE `arms` BLOCK IS FLAT AND CARRIES THE NULLS BESIDE THE MODEL, because `append_result` writes the
model's row with every null's value inside it. A skill number and the nulls it was measured against
end up physically in the same record, and there is no way to append the one without the others.
That is invariant 1 implemented as a data structure instead of as a good intention.
"""

from __future__ import annotations

import os
from typing import Any


def append_result_block(
    *,
    statistic: str,
    arms: dict[str, float],
    n: int,
    artifact_sha256: str | None = None,
) -> dict[str, Any]:
    """The top-level keys `tools/append_result.py` reads, for merging into a metrics file.

    `arms` must contain the key `model` alongside every pre-registered null, named exactly as the
    pre-registration names them -- the experiments gate matches null ids as strings, so a renamed
    arm reads as a missing null (E06) rather than as a typo.
    """
    if "model" not in arms:
        raise ValueError("the arms block must contain a 'model' arm beside its nulls")

    # Absent rather than empty when unset: append_result prints a specific, actionable refusal for a
    # missing stamp, and an empty string would instead look like a stamp that hashed to nothing.
    stamp = os.environ.get("VEGEMU_PREREG_SHA256", "")
    job = os.environ.get("SLURM_JOB_ID", "")

    block: dict[str, Any] = {
        "statistic": statistic,
        "arms": dict(arms),
        "n": int(n),
        "job_ids": [int(job)] if job.isdigit() else [],
    }
    if stamp:
        block["prereg_sha256"] = stamp
    if artifact_sha256:
        block["artifact_sha256"] = artifact_sha256
    return block
