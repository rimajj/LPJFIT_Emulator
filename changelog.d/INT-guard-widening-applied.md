### Fixed

- **Two ways the login-node safety check refused commands that run nothing are now fixed, on the
  owner's decision.** The check stops heavy computation being started on the shared login machine
  by deciding whether a command could run a program. **First:** writing a file by typing its
  contents straight into the command — the ordinary way to create a script or a note — was refused
  whenever those contents contained an odd quotation mark, because the check tried to read the
  file's *contents* as though they were shell instructions, could not, and defaulted to refusing.
  Twelve of this project's own 178 files could not be written back this way, including the check's
  own source file and two work streams' state files. It now works out where the file's contents
  begin without trying to parse them, and if it genuinely cannot tell, it still refuses.
  **Second:** six everyday commands that only print or move about — printing a line, changing
  directory, testing whether a file exists — were not on the list of things that cannot run a
  program, so appending any of them to an ordinary read ("count the lines in this file, then print
  done") turned the whole thing into a refusal. Eight of ten such commands were refused; the two
  that got through did so only because of where a semicolon happened to fall, which is luck, not
  safety.
- **Measured before and after on three bases**, because a safety check that has been loosened needs
  evidence and not an argument: of the 1,312 distinct commands this project's sessions have ever
  issued, 41 were refused before and 32 after, and every one of the nine that changed runs nothing.
  Everything the test suite requires to stay refused still is, including handing a file's contents
  to something that *can* execute them. The full suite passes, 306 checks.
- ⚠ **The transcript record shows the habit this was meant to prevent had already started.** Two
  past sessions got past the check by splitting a word in half inside quotation marks so it would
  not be recognised. That hides the defect from whoever would fix it, and all three work streams
  have been asked to report such refusals instead.

### Added

- **The safety checks are now tested against commands nobody wrote by hand.** Ten times now, one of
  these checks has judged text that is not the thing it was guarding, and nine of those were found
  by somebody being blocked in the middle of their work, after every automated check had passed —
  because a list of test cases somebody thought of cannot contain the case nobody thought of. The
  new test builds its commands out of this project itself: its own paragraphs, its own files, its
  own commit messages, wrapped in forms that run nothing at all, so a refusal is by construction a
  mistake. It found both of the faults above in a single run. Its own first draft was wrong in an
  instructive way — it fed the file contents to the check as if they were the command — which was
  caught by asking whether the failing test failed for the reason it claimed.
