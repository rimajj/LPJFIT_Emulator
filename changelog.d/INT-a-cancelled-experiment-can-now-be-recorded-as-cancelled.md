### Fixed

- **A cancelled experiment can now be written down as cancelled.** Every experiment here is
  registered in advance: the plan is frozen, a fingerprint of it is stored, and any later change to
  the plan shows up as a mismatch. That is what stops a question being quietly rewritten after the
  answer is known.

  But two of the safeguards contradicted each other. One of them nags about an experiment that was
  registered and then never run — a reasonable thing to chase — and it told you to fix it by writing
  the reason into the plan. Doing that changes the plan, which the *other* safeguard reports as
  tampering. So the only offered remedy was one that set off an alarm, and it was only available
  before freezing, which is the one moment the nagging can never happen. Found on 2026-09-21 and
  written up then; fixed now.

  The reason is now written to the registry instead — an add-only list that nothing ever edits —
  using a new command, `tools/abandon_experiment.py`. The frozen plan is genuinely never touched, so
  the tamper check keeps working exactly as before. The alternative, carving out an exception to the
  tamper check, was rejected: an exception to a rule, interpreted by the same code that enforces the
  rule, is the kind of loophole that check exists to catch.

  **Two real cases are now closed.** Two experiments registered on 2026-09-21 were replaced within
  the hour, before anything ran, because their written plan pointed at the wrong input file — one
  with 181 columns instead of 78, which would have handed the model a hundred extra pieces of
  information the earlier experiments never had, making it a different experiment under the same
  name. They were replaced correctly, but the *reason* existed only in a commit message and a status
  file. It is now machine-readable, and their 2026-10-21 deadline is discharged.

  **Two smaller things came with it.** The start-of-session summary, which lists unfinished work,
  now knows about cancellations — otherwise it would have listed those same two experiments as
  unfinished at every session for the life of the project, which is the exact rot it exists to
  prevent. And cancelling something and then running it anyway is now reported rather than silently
  accepted; that was impossible before, so it is a new gap opened by this fix and closed in the same
  change.
