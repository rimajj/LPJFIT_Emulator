# A sealed experiment cannot be marked `abandoned:` — E03 and E13 contradict each other

- **Status:** accepted as a FINDING. No code change is applied here; the repair is specified below
  and is deliberately left to be chosen, because two defensible designs exist and one of them
  weakens the seal.
- **Date:** 2026-09-21
- **Line:** INT
- **Governs:** `tools/check_experiments.py` (E03, E13), `.claude/skills/experiment-registry/SKILL.md`
- **Deadline that makes this concrete:** `X-20260921-pilot-warming-response-constco2` and
  `X-20260921-pilot-composition-response-constco2` will both trip E13 on **2026-10-21** and nothing
  can be done about it under today's rules.

## What was found

E13 fires when a pre-registration has been sealed for more than 30 days with no results, and its
own hint states the fix:

> harvest it, or add `abandoned: <reason>`. An unfinished experiment with no reason is the shape of
> a chore that rots

E03 compares the live pre-registration's sha256 against the hash recorded in `registry.jsonl` at
seal time, and reports any difference:

> a sealed pre-registration is immutable. A changed question is a NEW exp_id with `supersedes:`
> naming this one

**Adding `abandoned:` to a sealed file changes its bytes, so it changes its hash, so it trips E03.**
Measured today on both ids above: appending the reason produced
`E03 live hash 7bdee2d7e694 != sealed hash 7bf3091a735c` and
`E03 live hash 71a36bda180a != sealed hash 97d3f6bff56b`. Reverting to the sealed bytes cleared it.

So for a **sealed** experiment the two rules cannot both be satisfied. E13's stated remedy is
available only for a DRAFT, which is the one state in which E13 can never fire — it keys off
`sealed_at`. The remedy and the condition are disjoint by construction.

## Why it matters, rather than being a curiosity

This is not a hypothetical. An experiment that is sealed and then correctly abandoned is an
ordinary event: it happened twice in one session today, both times because the pre-registration's
apparatus description was wrong in a way that would have produced a different experiment than the
one it named (see `20260921-X-*` and the `-resealed` ids). Nothing ran under either; no result was
appended; superseding them was the right call and was made within the hour.

The failure mode is the one this repository already names in `MEMORY.md`: **a gate whose remedy is
impossible is a gate people learn to route around.** The available responses today are all bad:

1. Add `abandoned:` and accept a permanently red E03 — turns the integrity check into noise.
2. Leave it and accept a permanently red E13 after 30 days — same outcome, later.
3. Append a "correction" row to `registry.jsonl` re-recording the new hash — this is exactly the
   append-to-silence-a-gate workaround that the 2026-09-15 E12 change was written to eliminate, and
   the argument there applies unchanged: *the workaround was the bug, not the symptom.*
4. Delete the experiment directory — destroys the record that the question was once asked, and the
   seal commits remain in history regardless.

## The two repairs, and why neither is applied here

**(A) Record the abandonment in the registry, not in the file.** A new append-only row
(`{"exp_id": …, "event": "abandoned", "reason": …, "at": …}`) written by a tool, with E13 consulting
it as well as `prereg.abandoned`. Keeps the sealed bytes genuinely immutable, puts the abandonment
where every other correction in this repository goes, and needs no change to E03.
⚠ Cost: `abandoned:` in the YAML stops being the single place to look, so the skill page and the
template both have to say where it lives now.

**(B) Exempt an appended `abandoned:` block from the E03 hash.** E03 would hash the file with that
block stripped. Cheaper to write and keeps one home for the reason.
⚠ **This weakens the seal and should probably be refused.** "Immutable except for one key" is a
rule with an exception, and the exception is parsed by the same code that enforces the rule; a
malformed or cleverly-placed `abandoned:` block is then a way to change other bytes unnoticed. E03
exists precisely to catch a file edited after sealing.

**(A) is the recommendation.** It is not applied in this session because it changes the experiment
gate's data model and the skill page that every line reads, and because the deadline is a month
away rather than today — there is time to do it deliberately rather than at the end of a session
that was about something else.

## What is deliberately left open

- The repair itself. Whoever takes it should also decide whether `tools/seal_experiment.py` grows an
  `abandon` subcommand, so that nobody hand-edits either artefact.
- The two ids above are NOT marked abandoned anywhere machine-readable. Their reason is recorded in
  the commit that resealed them (`9d973ba`) and in `lines/X/STATE.md`. That is a document, and a
  document is exactly what this repository does not trust to be found — which is the whole argument
  for doing (A) before 2026-10-21.
