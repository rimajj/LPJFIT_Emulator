### Fixed

- **The one sanctioned way for two work lines to send each other a message has never worked, and
  half of it now does.** The rule in this repository is that each line of work owns its own files
  absolutely, with a single exception: a small tool that appends a message to another line's status
  file. That exception was never usable. The tool wrote the message correctly, and then the commit
  containing it was rejected by the ownership check — the check had a switch to allow it, and
  nothing in the commit machinery ever flipped that switch. A documented mechanism, an unused
  switch, and no test covering it, so it stayed broken for as long as it has existed.

  Permission is now worked out from the change itself rather than from a switch the caller sets:
  a write into another line's status file is allowed only if it deletes nothing, adds nothing under
  a heading of its own, carries the sending tool's signature line, and is attributed to the line
  actually making the commit. That is **narrower** than the switch would have been — a switch is a
  claim, and would have permitted any edit at all to another line's file, including erasing it.
  Eight tests cover it, including the two abuses the switch would have waved through: a message
  attributed to a third line, and a deletion travelling alongside a genuine message.

- **The same channel is still blocked for a second, unrelated reason, and that one is not a line's
  to fix.** Every status file has a 120-line cap, and one line's file is sitting at exactly 120. A
  message of *any* length pushes it over, which reddens a repo-wide check and stops **every** line
  from merging — so a recipient at their cap cannot be reached at all, however short the message.
  Fixing that means changing either what the cap counts or where messages land, both of which are
  protocol decisions that belong to whoever integrates. It is raised rather than taken. Record:
  `docs/decisions/20260909-D-inbound-recognised-from-the-diff.md`.
