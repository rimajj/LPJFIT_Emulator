### Added

- `tests/test_guard_generated.py` — the deny hooks are now tested against commands built from the
  repository itself (its paragraphs, its tracked files, its commit messages) in templates that run
  nothing, instead of only against a hand-written list. Every previous false-denial bug was found by
  being blocked during ordinary work after a green suite.

### Fixed

- Nothing yet. Two false-denial classes are **measured and pinned as strict xfails**, with the fix
  written and verified but not applied, because widening a permission hook is an owner decision:
  12 of 177 tracked files cannot be written with `cat > f <<'PY'` when their text contains an
  unbalanced quote, and appending `; echo done` to a read flips it to denied because `echo`, `cd`,
  `pwd` and `test` are not on the safe-verb allowlist. Record:
  `docs/decisions/20260916-INT-an-unlexable-heredoc-body-defeats-the-rule-that-a-body-is-data.md`.
