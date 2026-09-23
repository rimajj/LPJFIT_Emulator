# An abandonment is recorded in the registry, so the sealed bytes stay immutable

- **Status:** accepted and APPLIED.
- **Date:** 2026-09-23
- **Line:** INT
- **Implements:** repair (A) of
  `20260921-INT-a-sealed-experiment-cannot-be-marked-abandoned-e03-and-e13-contradict.md`, which
  accepted the finding and deliberately left the repair to be chosen.
- **Governs:** `tools/abandon_experiment.py` (new), `tools/check_experiments.py` (E13, and the
  registry index), `.claude/hooks/session-open-loops.sh`,
  `.claude/skills/experiment-registry/SKILL.md`

## What was decided

Repair (A) is applied, unchanged from how the finding specified it. Repair (B) — exempting an
appended `abandoned:` block from the E03 hash — is **refused**, for the reason the finding gave:
"immutable except for one key" is a rule with an exception, and the exception would be parsed by the
same code that enforces the rule. E03 exists precisely to catch a file edited after sealing.

An abandonment is now an appended row on `experiments/registry.jsonl`:

```json
{"at": "…Z", "event": "abandoned", "exp_id": "…", "reason": "…"}
```

written only by `tools/abandon_experiment.py`. The sealed pre-registration is never touched, so its
hash still matches its seal row and E03 stays green through the abandonment.

## What was built

1. **`tools/abandon_experiment.py`**, shaped after `tools/campaigns.py abandon`, which is the same
   chore for the campaign ledger and already worked. It refuses four states rather than writing a
   row it would then have to flag: an unsealed experiment (whose bytes are still editable, so
   `abandoned:` in the YAML is the better home), one that has results, one absent from the registry,
   and one already abandoned. A reason under ten characters is refused — the row exists for the
   reason, so an empty one is the failure it was built to prevent.
2. **E13 consults both homes** — `abandoned:` in the pre-registration, and the registry row.
3. **The session-start hook consults them too.** Without this the two ids would have been reported
   as open loops at every session start for the life of the repository: the chore-that-rots shape
   that hook exists to prevent, turned on itself. Its fallback is deliberately the over-reporting
   one — a closed loop shown as open costs a glance; an open loop hidden is the failure.

## The bug this repair could have introduced, and did not

`registry_index()` folded every row for an `exp_id` into one entry, keeping the **last**. An event
row carries no `prereg_sha256`, so the abandonment — appended *after* the seal — would have shadowed
the seal it refers to, and E03 would have reported every abandoned experiment as *"sealed but absent
from `registry.jsonl`"*. That is `MEMORY.md:guard-reads-wrong-input` for the eleventh time: a check
reading input that is not the thing it checks.

The index now separates the two kinds by the field that distinguishes them, `prereg_sha256`, rather
than by position. `_experiments.registry_lookup` already did exactly this, which is some evidence
the convention is the natural one rather than a patch.

`tests/test_experiment_abandonment.py` pins it, together with the E13 clearing, the untouched bytes,
and the non-vacuity case (the gate still fires when there is no reason).

## One new contradiction, closed in the same change

Abandoning was impossible before, so "abandoned, then ran anyway" was unreachable. It is reachable
now, and a record that says both things is one where the results are the load-bearing half. The tool
refuses to create it and E13 reports it if the rows appear afterwards.

## Applied to the two ids that forced this

`X-20260921-pilot-warming-response-constco2` and `X-20260921-pilot-composition-response-constco2`,
both sealed and superseded within the hour on 2026-09-21 before anything ran, are now abandoned with
their reason machine-readable. Their deadline of 2026-10-21 is discharged.

⚠ **Their reason was previously only in a commit message and `lines/X/STATE.md`** — and a document
is exactly what this repository does not trust to be found. That was the finding's own argument for
doing this before the deadline rather than at it.

## What is deliberately NOT done

`tools/seal_experiment.py` did **not** grow an `abandon` subcommand. It is the tool that *creates*
the immutable thing; a separate binary keeps "freeze this" and "declare this dead" from sharing an
argument parser, and matches `campaigns.py`, where a session already looks for this verb.
