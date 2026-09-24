### Fixed

- **The build would have gone red on 2026-09-25 through nobody's action, and now does not.** Each
  work line keeps a short status file with a 120-line limit. Messages one line sends another are
  exempt from that limit for 14 days, and then count. All three status files had piled up weeks of
  messages — line D's was 439 lines, 338 of them messages — so as the exemptions lapsed the size
  check would have failed every documentation change from 2026-09-25 (line D), then 2026-09-29
  (line T) and 2026-09-30 (line X). Checked by running the size check with its clock set to those
  dates: before, it fails on each; after, it passes on each, through 2026-10-15.

  Every one of the 35 messages was read and checked against the repository, given a one-line note
  saying whether it had been acted on, and moved with its full text into that line's journal,
  where nothing is lost. Two requests are still genuinely open and stay visible in the status
  files: adding four soil-type columns to the training data, and recording "no trees" as missing
  rather than zero in the species-mix columns. Both were checked in the code today and neither is
  there yet; both belong in the next version of the training data. The status files are now 84,
  112 and 72 lines.

- **The journal now starts a new file when it is full, instead of breaking its own limit.** The
  tool that moves old status into the journal always wrote to one file per month. Line T's
  September journal already held 597 of its 800 lines, so moving its ~300 lines of messages would
  have broken the journal's limit instead, and the commit would have been refused. It now continues
  in `2026-09b.md`, `2026-09c.md` and so on, and refuses (moving nothing) if one batch could not fit
  even in an empty file. Nine new tests cover it.

- **Figures can be committed again.** The rule table that says who may change which files had no
  entry for `figures/`, and any file without an entry is refused on commit, so regenerating any of
  the twelve tracked figures was blocked. Figures now belong to the experiments line, like the
  verdicts they illustrate. It was the only unowned directory in the repository.

- **Five stale statements corrected.** (1) The fact list and one verdict said no "blind" test had
  been run for the species-mix result — a model that knows the starting forest but not what climate
  change it is being asked about. One ran on 2026-09-23: it scores 0.307940 and clears that
  experiment's pass mark of 0.300203 on its own (it fails under the stricter 5-degree spatial
  blocking, 0.296620 against 0.305348), so only about 0.138 of the 0.4459 score comes from
  reading the climate change. (2) The cluster notes said the fast `priority` queue allows 64 CPUs
  per job and is usually idle. It allows 64 CPUs and 10 running jobs per *user*, across all of
  their jobs together, and 77 % of it was in use at 14:30 today. (3) The notes and the runbook said
  to judge whether a job is alive from `sacct`'s CPU time. `sacct` shows zero CPU time for work
  that is still running, so a healthy running job and a hung one look the same; use `sstat` while
  it runs and `sacct` after. Measured today on a live job. (4) Each line's start-here block described
  work as blocked or waiting that finished days ago, and none mentioned the full second run of the
  pilot started today or the build work running in parallel; all three now say what is true on
  2026-09-23. (5) Line T's list of lessons still described a command-checking bug fixed on
  2026-09-16.
