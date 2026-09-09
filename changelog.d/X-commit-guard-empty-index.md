### Changed

- **`git add … && git commit` as a single command runs none of the commit-time checkers**, and this
  needs an integrator fix in shared `.claude/hooks/`. The guard is a pre-command hook, so it reads
  the staged set *before* the command runs, finds it empty, and exits early — so budgets, ownership,
  experiments, secrets and the silent-corruption lint subset all quietly do not run. It was found by
  tripping it: an over-budget document passed every local check and was caught only by CI, costing a
  merge cycle. This is **not** the documented escape hatch, which at least leaves a trailer that CI
  counts; this leaves no trace and needs no opt-in. Recommended fix is to move the checks into
  `.githooks/`, which runs after staging by construction — the trap in the cheaper fix is that
  refusing on "empty index plus a `git add`" still lets `git commit -am` through. Record:
  `docs/decisions/20260909-X-the-commit-guard-sees-an-empty-index.md`.
- **`tools/check_budgets.py` with no arguments cannot see a new file**, so "I checked before
  committing" was not true: the default selection is `git ls-files`, which skips untracked paths.
  `--staged` and explicit paths are both correct. The same fall-through lives in `select_files` in
  `tools/_common.py`, so every checker sharing it has the same blind spot.
