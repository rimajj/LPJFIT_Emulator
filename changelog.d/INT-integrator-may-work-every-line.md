### Changed

- **The integrator may now do any work stream's work directly, on the owner's instruction.** The
  project is split into three streams — data, training, experiments — each with its own branch and
  its own folders, so that two of them editing at once cannot collide. That split was never meant to
  fence off the integrator, and in the actual checks it never did.
- ⚠ **The rule that said otherwise had never been enforced, and that is the part worth reporting.**
  The greeting printed at the start of every integration session stated that work belonging to a
  stream "does not belong here" and would be refused. That was a specific claim about what the
  automated checks do, and it was false: the checks identify which stream you are by which branch
  you are on, and on the integration branch there is no stream, so the rule cannot fire. Verified
  before changing anything, by making exactly such an edit and running the check, which passed.
  **So the cost was never a blocked change — it was sessions that never attempted one**, and handed
  the work back to a stream instead. A start-up message that asserts a refusal works just as well as
  a real refusal, and is cheaper to get wrong, because nothing tests a greeting. The three places
  that describe this — the greeting, the runbook, and the ownership map — now agree with each other
  and with the code.
- **Three rules are deliberately kept**, and they are about evidence rather than territory: a
  decision record that has been accepted cannot be edited, a sealed experiment plan cannot be
  edited, and the job and results ledgers can only be appended to. Each exists so that a past result
  cannot be quietly improved after the fact, and none has ever blocked work, because writing a new
  record that supersedes the old one is always available.

### Fixed

- **All 40 outstanding job records are closed, each checked against the runs themselves rather than
  against a document.** These record every computation sent to the cluster, and stay open until
  somebody confirms the results arrived; from 22 September an unclosed one would have blocked every
  merge. None had been closed, because results land hours or days after the session that launched
  the work has ended, and the next session belongs to whoever picks it up. Every one of the 6,602
  forest simulations reports success in its own log, and the two result tables hold exactly the
  6,000 and 600 rows claimed for them. Not one was closed on the strength of a write-up.
- **A record of provenance accepted a value that was not one.** Closing these, a fingerprint of a
  result file was recorded that had the right first 16 characters and an invented remainder, because
  only a shortened form had ever been displayed. Nothing rejected it — the length alone would have.
  The tool now checks, the wrong entry is superseded by one that says plainly what was wrong with
  it, and no measurement had depended on the value.
