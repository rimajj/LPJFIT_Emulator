### Fixed

- **The safety check that runs before every commit had a documented "let me through anyway" switch
  that had never once worked.** The check runs the project's own rules over the files about to be
  committed, and when it refuses it prints the way to override it deliberately — which leaves a
  visible reason line in the commit that the build then counts and reports. But the override was
  written as something you type in front of the command, and this kind of check cannot see anything
  typed in front of the command; it only sees the command itself. So the check could not be
  switched off at all, while telling you how to switch it off. The same fault in the sister check
  that guards the shared login machine was found and fixed on 8 September; this third one, in the
  file next door, was missed by that fix and has been broken ever since. It now works.
- ⚠ **What that cost is the reason it mattered.** On 10 September a session was blocked by this and
  got past it instead by rewording its command until the check stopped recognising it — leaving no
  record at all, where the proper override would have left a reason on the commit. **A way out that
  does not open does not make people more careful; it makes them go around the back.**
- **A check that crashed was reported as though the project had broken a rule.** The two outcomes —
  "your files violate something" and "the checker could not start" — both look like failure from
  the outside, and were being run together, so a crash came out as "the commit guard refused this
  commit" followed by a stack trace. On 10 September four checkers died on the same startup fault
  and a whole session's commits were refused that way, with the broken override above meaning
  nothing could lift it. The two now read differently: a crash says the guard itself is broken and
  that this is not a finding about your files. It still refuses — a commit whose checks never ran
  is unchecked, not clean.
- **Two start-of-session reports fell silent when they broke instead of saying so.** One of them
  lists the long-running jobs launched by earlier sessions, and it is the only thing that carries a
  job across the boundary of the session that started it — results arrive hours or days later, so a
  job nobody is reminded of is a job nobody collects. If it failed, it printed exactly what it
  prints when there is nothing to report. There are 38 such jobs outstanding right now. Both
  reports now say plainly when they could not run.

### Added

- **Five new tests pin all of it**, including the case that the fix itself could easily have got
  wrong: writing *about* the override inside a commit message must not trigger it, and neither must
  a command the checker cannot read properly. Six times out of ten in this project, a check of this
  kind has gone wrong by examining text that was not the thing it was meant to be checking — so the
  new override deliberately refuses to act on any command it could not read cleanly. The full test
  suite passes, 295 checks.
