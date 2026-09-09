### Fixed

- **`main` is green on `lint` again.** `ruff format` was run on the three files that had been failing
  `ruff format --check .` for at least five consecutive runs: `scripts/train_emulator.py`,
  `src/vegemu/models/__init__.py` and `src/vegemu/models/synth.py`. `ruff check` was already passing;
  the break was formatting only. Verified idempotent (a second `ruff format` leaves 95 files
  unchanged) and both checks now pass repo-wide.
- **Done centrally, from the integration worktree on `main`, because no line could do it.** All three
  paths are line T's exclusive paths under `config/ownership.toml`, so `check_ownership.py` denies
  them to every other line (O01); on `main` the caller is the integrator and O01 cannot fire. The
  normal way to hand the break to its owner was unavailable: `tools/inbound.py` appends to
  `lines/T/STATE.md`, which sits at **exactly** its 120-line budget, so the inbound block would turn
  the `budgets` gate red and `tools/merge.sh` would then refuse every line's merge. Because the
  `lint` gate runs `ruff format --check .` over the WHOLE repo rather than the changed files, these
  three files made every line's branch red too, not just `main` — line X had been unable to merge for
  three sessions on account of files it is forbidden to touch.

### Changed

- **One of the three changes is not layout-only, and it is worth knowing about.** In
  `src/vegemu/models/__init__.py` the reformat reaches inside the module docstring and strips the
  indentation from a line that was indented on purpose to read as a definition list:

      -    emulator   the state predictor: one head per scored quantity, fitted per spatial fold
      +emulator   the state predictor: one head per scored quantity, fitted per spatial fold

  Confirmed by comparing the parsed syntax tree before and after for all three files: the other two
  are token-identical, and this one differs only in that docstring's text. It is applied as the
  formatter produced it and NOT hand-restructured, because the gate requires `ruff format --check .`
  to pass, so the formatter's output is the required state and line T would have produced this same
  diff. If the indented layout is wanted back, it needs a docstring shape `ruff format` will leave
  alone — that is line T's call, not the integrator's.
- **The full suite was run to check the reformat changed no behaviour: 187 passed, 1 skipped.** Note
  for anyone repeating it on a login node: `python3 -m pytest` alone fails to COLLECT six of line D's
  test modules with `ModuleNotFoundError: No module named 'vegemu'`, because the package is not
  installed in the login-node interpreter. That is an environment gap, not a red suite — run it as
  `PYTHONPATH=src python3 -m pytest`.

### Found, not fixed

- **`slurm-guard` matches the text of a command, not what the command does, so it blocks `git`.**
  Any command whose string contains a `.py` path trips the "heavy Python on the login node" refusal —
  `git log -- src/vegemu/models/synth.py` was blocked, and so was a `git commit` whose *message body*
  merely mentioned a test file. Both were waved through with `ALLOW_LOGIN_HEAVY=1`, which teaches the
  habit of bypassing the guard for things it was never meant to catch, and that is how a guard stops
  being believed. It is the same shape as the two bugs already recorded this week — the commit guard
  reading an empty index, and the gate selector reading a different diff than GitHub: **a guard whose
  input is not the thing it is guarding.** Integrator-owned (`.claude/hooks/**`); left alone here
  deliberately, since the session's mandate was the formatting break.
