# Two repositories, one project each: this one is the data-driven emulator, and the old one is frozen

- **Status:** accepted
- **Date:** 2026-09-08
- **Line:** INT (integration)
- **Supersedes:** nothing. Settles the remote question left open by
  `20260908-INT-gate-selection-was-blind.md`, and corrects a wrong `MEMORY.md` row that treated it
  as undecided when the owner had already stated it.

## The owner's steer, in their terms

The goal is the **data-driven emulator** as a **new, independent project**, reusing everything
reusable from the old project. The old project is the **hybrid** emulator — a different thing. And:
**"the old project should not be changed in any way."**

## What was actually on disk and on GitHub

Two GitHub repositories exist, and **their names differ by two letters**:

| | repository | what is in it |
|---|---|---|
| **this project** | `rimajj/LPJFIT_Emulator` — created **2 Sep, 12:56** | see below |
| **the old project** | `rimajj/LPJmLFIT_Emulator` — created 15 Jul | the hybrid emulator, 894 commits |

The old project also has its checkout at `/p/projects/open/Jamir/esm_land_emulator` (plus worktrees
`wt-{S,M,E,O,X}`), which points at its own remote through the SSH alias `github-esm`.

**Why this project's history looked "started fresh".** `LPJFIT_Emulator` was created on 2 Sep and
seeded with a **copy** of the old project's entire history — `main` plus all five of its work
branches. The `vegemu` working tree was then started **74 minutes later**, at 14:10, with its own
root commit (`8814f8f`, "self-enforcing repo skeleton") — `git init`, not a clone of that
repository. So the two have never shared a commit, and every tool that compares against
`origin/main` was comparing against a different project.

**Nothing was lost, and that is checkable:** this repo's reflog still has its oldest entry as that
root commit, and a reflog records any rewrite. All 39 commits are present.

**The copy is redundant.** Every predecessor branch on `LPJFIT_Emulator` is at an identical commit
id on `LPJmLFIT_Emulator` — `main` 4ffc58a, `line/E` c39527c, `line/M` 28ba865, `line/O` 600e30e,
`line/S` c974669, `line/X` dfa5b22 — and the old repository additionally has a published-docs
branch the copy never received. The only things unique to `LPJFIT_Emulator` are the two branches
pushed there today and two automated dependency-bump branches sitting one commit above the copied
`main`.

## The decision

1. **`LPJFIT_Emulator` holds this project and nothing else.** Its `main` becomes this history; its
   branches are `line/D`, `line/T`, `line/X`. The copied predecessor branches are redundant and go.
2. **`LPJmLFIT_Emulator` and `/p/projects/open/Jamir/esm_land_emulator` are frozen.** Not read-only
   by convention — **enforced**, see below.
3. **Reuse stays a distillation, not a dependency.** What transfers is written into this repo, in
   `docs/reference/inherited.md`. Taking something *from* the old project *into* this one is the
   plan; reaching back to change anything there is not.

## Freezing the old project is enforced, not documented

This repo's own inherited finding is that **every rule expressed as prose was violated, and every
rule that was a hook or a gate held**. A standing owner constraint with nothing enforcing it is
prose. So:

* `.claude/hooks/predecessor-guard.sh` (new, `PreToolUse[Bash]`, runs first) denies any command that
  pushes to the old repository or its `github-esm` alias, and any command that mutates the old
  project's trees on disk.
* `.claude/hooks/path-guard.sh` gains an absolute-path check for those trees. It needed one: every
  other rule in it reasons about a **repo-relative** path, and for a path outside this repo that
  value is still absolute, so it matched nothing and was allowed.
* **Reads stay allowed** — `log`, `show`, `diff`, `status`, `grep`, `head`, `find` all pass, because
  citing the old project is the point.
* **Copies are direction-sensitive.** Taking a file *from* the old tree is allowed; `cp` *into* it
  is denied; `mv` out of it is denied, because moving a file out still removes it from over there.
  A guard that forbade its own advice would simply be worked around.
* `tests/test_predecessor_guard.py` asserts all 33 cases, **including that the hook is executable**.
  That test is not ceremony: the hook was first written without the execute bit, and every deny case
  then passed silently while every allow case passed too — indistinguishable from success unless the
  denials are asserted. It also reads the guard's remote pattern out of the hook and checks it does
  **not** match this project's own remote, since the two names are two letters apart.

## What is done, and the one step that is not

Done: `line/D` and `line/T` pushed (new names, nothing overwritten); CI ran for the first time in
this project's history; the enforcement above.

**Not done — needs the owner to run it or to grant the permission.** Replacing `main` and `line/X`
on `LPJFIT_Emulator` requires a non-fast-forward push, and the agent's permission layer blocks a
force-push. It was not worked around. The remaining commands, all against **this** project's remote:

```bash
git push --force-with-lease origin main        # this project becomes main
git push --force-with-lease origin line/X      # our experiments branch, over the copy
git push --delete origin line/E line/M line/O line/S   # redundant copies; identical ids remain
                                                       # on LPJmLFIT_Emulator
```

Until then `main` on that repository still shows the old project, the checks never run on `main`,
`tools/merge.sh` refuses (it counts this project as ~894 commits "behind"), and the experiments
branch has never been checked.
