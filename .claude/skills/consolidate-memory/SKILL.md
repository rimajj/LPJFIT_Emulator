---
name: consolidate-memory
description: The every-~5-sessions reshape of the repo-root MEMORY.md back to durable-state-only under its cap (≤400 lines / ≤15k tokens), plus skill hygiene — audit the skill set for duplicates and never-used skills, sharpen weak descriptions, promote recurring JOURNAL notes into skills. Use when MEMORY.md has grown past its cap or accreted session narrative, on the ~5-session cadence, or when the skill set needs a dedup/prune pass so the workspace isn't flooded with overlapping or dead skills.
---

# consolidate-memory — reshape MEMORY.md + prune the skill set

Two jobs on the same ~5-session cadence: keep `MEMORY.md` (repo root) to *current durable state only*, and
keep `.claude/skills/` lean (no duplicates, no dead skills). Both fight the same failure mode — bloat that
makes onboarding slower and buries the signal.

## Part A — reshape MEMORY.md

**⚠️ Under parallel work lines (ADR 0028/0029) this skill has TWO scopes — pick the right one:**
- **Your line's `lines/<X>/STATE.md`** — routine line housekeeping, do it from your own worktree. Move that
  line's narrative to `lines/<X>/JOURNAL.md`; keep the `## NEXT — start here` block at the top intact (it is
  the handoff the SessionStart hook replays).
- **The shared repo-root `MEMORY.md`** — **INTEGRATOR ONLY**, from the `main` worktree. It is a destructive
  in-place reshape, so running it from a line branch can silently auto-merge away another line's edits. It now
  holds SHARED/cross-cutting state only (a §0 router + cross-cutting `[VERIFIED]` facts + an ADR pointer);
  per-line state is NOT its job.

`MEMORY.md` is the repo-root durable-state file (NOT `JOURNAL.md`, NOT the runbook `CLAUDE.md`). Cap:
**≤ 400 lines / ≤ 15k tokens** (stated in its own header).

1. **Measure.** `wc -l MEMORY.md` and eyeball the token size. If under cap and still durable-state-only,
   stop — don't reshape for its own sake.
2. **Keep only durable state:** verified facts (`[VERIFIED]`), the frozen-decision *index* (one line per
   ADR, pointing at `docs/decisions/`, not the reasoning), phase status, open `[TODO]`s.
3. **Move everything else out — don't delete it:**
   - session narrative / "what happened this session" → append to **`lines/<X>/JOURNAL.md`** (the root
     `JOURNAL.md` is pre-2026-07-28 history + the INTEGRATION journal, integrator-only);
   - the story behind one change → a **`changelog.d/<X>-<slug>.md` fragment** (never edit `CHANGELOG.md` from a
     line; the integrator collates it);
   - a resolved decision's full reasoning → its ADR (MEMORY keeps just the index line).
4. **Archive big removals** (don't delete — git has it, but leave a human pointer): write the pre-reshape
   copy to `docs/archive/MEMORY_<YYYY-MM-DD>_pre-consolidation.md` and note it in the MEMORY.md header
   (follow the existing `2026-07-22` pointer as the pattern).
5. **Re-check the cap** after reshaping. Convert any relative dates to absolute while you're in there.

## Part B — skill hygiene (flood control — this is why the workspace doesn't fill with dead skills)

1. **Inventory:** `for f in .claude/skills/*/SKILL.md; do sed -n '2,3p' "$f"; done` (name + description).
2. **Usage:** if `.claude/skill-usage.log` exists, tally invocations. A skill with **zero** invocations
   across many sessions is a candidate to **delete** (or its description is too weak to trigger — decide
   which; see step 4).
3. **Dedup / merge:** two skills covering overlapping procedures → merge into one and delete the other.
   Prefer one well-scoped skill over two half-scoped ones (the `skill-creator` rule: update, don't fork).
4. **Sharpen, don't just delete:** a never-used skill whose *task* still recurs usually has a weak
   `description` (the field that decides whether it triggers). Rewrite the description with the exact verbs
   and artifact names of the task (use the `skill-creator` skill), then keep it one more cycle before
   deciding to delete.
5. **Promote:** recurring notes/scripts that keep reappearing in a JOURNAL but have no skill → create
   one (via `skill-creator`).
6. **Record what you removed** in your line's JOURNAL (or the integration journal if you are the integrator)
   (deleted/merged skill X because zero use over N sessions),
   so the decision is auditable.

## Wrap

Commit the reshaped state file, any archived copy, and skill changes together (branch-per-line + self-merge on
green, ADR 0028 — NOT the superseded main-only rule;
`repo-commit` skill). Note in the commit body what was archived and which skills were merged/deleted.
This skill did not exist before 2026-07-23 — the docs referenced it (`STEERING_PROMPT.md`, `repo-commit`)
before it was written.

---

## ⚠ `skill-usage.log` IS PER-WORKTREE AND UNDERCOUNTS — NEVER DELETE A SKILL ON ITS ZEROS (integrator, 2026-09-02)

Part B step 2 says to tally `.claude/skill-usage.log` and treat a zero-invocation skill as a deletion
candidate. **Read the log's two defects first, or that step deletes live skills.**

1. **It is per-worktree and git-ignored.** Each line's worktree keeps its own; the integrator's `main` copy
   sees only integrator sessions. Measured 2026-09-02: `main` 9 entries, `wt-S` 22, `wt-M` 22, `wt-E` 5,
   `wt-O` 3, `wt-X` 0 — so a tally run in `main` alone misses **85 %** of the record. Aggregate first:
   ```bash
   cat /p/projects/open/Jamir/{esm_land_emulator,wt-S,wt-M,wt-E,wt-O,wt-X}/.claude/skill-usage.log 2>/dev/null \
     | python3 -c "import sys,json,collections;c=collections.Counter(json.loads(l)['skill'] for l in sys.stdin if l.strip());[print(f'{v:5d}  {k}') for k,v in c.most_common()]"
   ```
2. **It records only the hook's `PostToolUse` path, so it is a lower bound, not a census.** The aggregate was
   **61 events over ~6 weeks across 5 lines** — far below the actual work, because a session that *reads* a
   skill (or follows it from the SessionStart listing) leaves no entry.

⇒ **A zero means "no evidence", not "unused".** Corroborate against the artifacts the skill names before
touching it: on 2026-09-02 the five zero-count skills were `emulator-validation-figures`,
`obsclim-cell-remap`, `online-coupling-env`, `provision-coupled-cell` and `python-env` — and every one of
them covers a live recurring task whose committed outputs exist on disk (the remapped forcing fixtures, the
`M_cells.csv` per-cell inputs, the coupled-environment project on `/p/tmp`). **No deletions were justified.**
The honest verdict for that pass: 17 skills, 0 duplicates, 0 dead, 0 removed.
