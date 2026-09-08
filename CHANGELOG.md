# Changelog

All notable changes to this project. Format: Keep a Changelog; newest first.
Entries are written as `changelog.d/<line>-<slug>.md` fragments and folded in at merge.

## [Unreleased]

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Changed
- **This project's repository now holds this project, and nothing else.** `main` is this history, the branches are `line/D`, `line/T` and `line/X`, and the copied old-project branches are gone. Every one of them was verified beforehand to sit at an identical commit id in the old project's own repository — which additionally has a published-docs branch the copy never received — so the replacement destroyed no unique work, and the old project's repository and working trees were not touched at any point. The two leftover automated dependency-bump branches turned out to have been dropped by GitHub already, since their base commit no longer existed.
- **Three things that were broken by the split history now work.** The tool that decides which checks to expect gives real answers instead of a fabricated all-clear; the merge script no longer refuses, having counted this project as 894 commits "behind" a different project; and the experiments branch is on the repository for the first time.

### Fixed
- **A force-push that replaces an unrelated history triggers no path-filtered workflow at all.** Every check here is path-filtered, and GitHub evaluates those filters against the diff between the pushed commits — which it cannot compute when the previous tip is not an ancestor of the new one. So the one-time history replacement produced **zero** check-runs, while the ordinary branch pushes minutes earlier produced ten. This matters because it is the exact shape of the failure the whole checks system was built around: a session that force-pushed and then waited for a verdict would wait forever, since a workflow skipped by its filter reports no status at all rather than "skipped". Recorded in `MEMORY.md` as `forcepush-no-ci`, with the remedy: push an ordinary commit and the gates run normally.

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Added
- **The old project is now frozen by enforcement rather than by convention.** The owner's standing instruction is that the old hybrid emulator must not be changed in any way, and until now nothing stopped a session here from doing so — the existing edit guard reasons entirely about repo-relative paths, so an absolute path into the old project's tree matched none of its rules and sailed straight through. A new `PreToolUse` guard (`.claude/hooks/predecessor-guard.sh`, first in the chain) denies any command that pushes to the old repository or its SSH alias, or that mutates its working trees; the edit guard gains an absolute-path check for the same trees. **Reads are deliberately untouched** — the old project is the archive of record and citing it is the point — and **copies are direction-sensitive**: taking a file *from* the old tree is allowed, copying *into* it is denied, and moving *out* of it is denied too, because that still removes it from over there. A guard that forbade its own advice would just get worked around.
- **`tests/test_predecessor_guard.py` pins all 33 cases, including that the hook is executable.** That is not ceremony: the hook was first written without the execute bit, and every denial case then passed silently while every permission case passed as well — which is indistinguishable from a working guard unless the denials are asserted. The test also reads the guard's own remote pattern out of the hook and checks it does *not* match this project's remote, because the two repository names are two letters apart: `LPJmLFIT_Emulator` is the old project, `LPJFIT_Emulator` is this one.

### Changed
- **The two repositories now have one project each, by decision.** This one holds the data-driven emulator as an independent project; the old hybrid project stays where it is, untouched. Why this project's history looked "started fresh" is now established rather than guessed: the repository was created on 2 September at 12:56 and seeded with a *copy* of the old project's entire history, and this working tree was started 74 minutes later with its own first commit — `git init`, not a clone. So the two never shared a commit, which is what made every tool comparing against the old `main` give a meaningless answer. Nothing was lost, and the reflog still proves it: its oldest entry is this project's root commit, and a reflog records any rewrite.
- **The copied branches are provably redundant**, which is what makes replacing them safe: every predecessor branch on this repository sits at an identical commit id on the old project's own repository, which additionally has a published-docs branch the copy never received. Replacing this repository's `main` and `line/X` therefore destroys no unique work — but it needs a non-fast-forward push, which the agent's permission layer blocks and which was not worked around. Until an owner runs it, `main` here still shows the old project, no check runs on `main`, and the merge script refuses because it counts this project as ~894 commits behind. Record: `docs/decisions/20260908-INT-two-repositories-one-project-each.md`.

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Changed
- **CI ran for the first time in this project's history** — on `line/D` and `line/T`, which are the two branch names free on the repository — and it is red. That is the point of the previous two commits: the failures were always there, and the tool that decides which checks to expect had been answering "none" for every commit. What it found, with each failure now owned: `pathsafety` on `line/T` reproduced independently the exact hardcoded-path violation found by hand earlier today; `lint` fails on both lines for the seven unformatted files already handed to them; `test` failed for the undeclared dependencies fixed above; and `types` reported **21 errors in 7 files**, of which 15 are in line D's binary-format and corpus code — including a variable redefined on the line above it, which is a real defect and not a style complaint — and 1 in line T's synthesiser.
- **This project's history cannot be pushed to `main`.** That branch on the repository holds the predecessor project, and the two histories share no commit, so the push is refused as non-fast-forward; the same is true of `line/X`, whose name the predecessor's own line X already occupies. `line/D` and `line/T` were free and are now pushed. Resolving the other two means overwriting or moving branches that hold another project's work, which is not a change to make unasked.

### Fixed
- **The package imported `scipy` and `lightgbm` without declaring either where a normal install would get them**, so `pip install -e ".[dev]"` — exactly what CI does — produced an installation whose own test suite could not even be collected (`ModuleNotFoundError: No module named 'scipy'`). `scipy` was parked in the optional `train` extra although `nulls.py` imports it at module level for the nearest-neighbour nulls; `lightgbm`, which the entire level model is built on, was in no dependency group at all. Both are now base dependencies: the extra exists to keep a 2.5 GB CUDA wheel optional, and these are ordinary CPU wheels. A dependency the package imports is not optional.
- **`types-PyYAML` added**, which mypy had been naming itself, and `scipy`/`lightgbm` added to the existing untyped-import list with the cost stated: calls into those libraries are unchecked, so a wrong argument reaches a test or nothing.
- **`score.matrix` returned `Any` from a function declared to return a float64 array.** polars is on mypy's untyped-import list, so `to_numpy()` is `Any` and returning it straight out silently discarded the declared return type under `strict`.

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Fixed
- **`tools/inbound.py` claimed to keep a sender copy of every cross-line message and silently didn't, whenever the sender had no `lines/<sender>/STATE.md`** — which is every message sent from the integration worktree. The mirror is not decoration: the tool's own docstring names it as the remedy for the failure it was built around, that a rebase conflict resolved with `--theirs` deletes the recipient's copy without trace. So the one safeguard was absent exactly when the success line said it was present. It now reports honestly, and when no sender copy could be kept it says so on stderr and states what that costs: the recipient's file is the only copy, and the sending commit is the only evidence it existed. Found by using the tool and then checking that the file it named actually existed.

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Changed
- **Two latent facts about this repository are now written down rather than merely true.** CI has never run on any commit, because nothing has ever been pushed anywhere — so the nine declared gates are at present enforced only by the local checkers in `tools/`. And `ruff format --check .`, which the `lint` gate runs, would reformat 10 tracked files on `main` as committed; whether that is neglect or a `ruff` version drift (pinned only `>=0.6`, CI installs the latest) is unresolved and left as separate, named work rather than folded into this repair. Record: `docs/decisions/20260908-INT-gate-selection-was-blind.md`.

### Fixed
- **The tool that decides which CI checks to expect was answering "none" for every commit ever made in this repo, on every branch.** It computed the change list from `git merge-base origin/main HEAD`, and `origin` points at the predecessor's GitHub repository — which resolves, but shares no commit with this history, so there is no merge base. That empty result was read as "the ref is unknown, use the staged set", which on a clean tree is empty, so no gate ever matched and the tool printed *"no check-run will appear for this commit. Do not poll. Merge when ready."* every time. `tools/wait_gates.py` inherited the same empty list and reported nothing to wait for, never reaching its own careful "cannot poll — do not assume they passed" path.
- **The proof it mattered:** a hardcoded absolute cluster path in `scripts/plot_validation.py` reached `main` and stayed there. It is precisely the defect the `pathsafety` gate exists to block, and the question "will `pathsafety` run?" had been answered no on every commit that touched it. Fixed, and the local checker is clean again.
- **An empty change list is no longer reachable by accident.** `_common.diff_base()` now reports *why* there is no base: `unknown` (a fresh clone — keep the staged fallback, so the bootstrap still works) or `unrelated` (a wrong remote). On `unrelated` the change list falls back to **every tracked file**, because the honest answer is "cannot tell" and the safe reading of that is all of them, never none — the same reasoning already written into the branch-name fallback beside it. `expected_gates.py` exits 2 and says what is unknown instead of printing the word "merge"; `wait_gates.py` refuses before polling. `tests/test_gate_selection.py` pins the distinction against a purpose-built orphan-branch repository, and collapsing the two causes back together fails it.

<!-- collated 2026-09-08 from 2 fragment(s) -->

### Added
- **The emulator** (`src/vegemu/models/emulator.py`): one gradient-boosted head per scored quantity, fitted per spatial fold. Predicting the 10th/50th/90th percentile of each trait directly IS a non-parametric distribution head, which is why this and not a parametric kernel is the first model; its limits — marginal quantiles predicted independently, no stochastic per-stem head — are stated in the module.
- **A restart file the real LPJmL-FIT loads and runs.** `scripts/synth_restart.py` emits one by template-conditioned synthesis with rank-matched stem transplant: 20 cells, 47.9 MB, 9,506 stems placed against 9,506 requested, achieved height and wood-density distributions within 0.3 % of the prediction. The model's own words: *"lpjml successfully terminated, 20 grid cells processed."*
- **Twelve validation figures** (`scripts/plot_validation.py`), covering both what works and what does not.
- **Both verdicts, both FAIL, and every null returned its pre-registered value** — so neither is `invalid`: the apparatus did exactly what was declared and these are clean failures of the model, not of the measurement.
- **The map test**: the emulator reaches 0.0361 of cells inside the acceptance band on all 22 quantities at once, against 0.0212 for the climatically nearest analogue and 0.0187 for the nearest cell. It beats every null by 1.7×, but the gate asked for a margin of 0.050 and it delivered 0.0149.
- **The kill test**: −0.727 against 0.000 for predicting no change. Diagnosed rather than merely reported — stem count carries real response skill (+0.35) and leaf area some (+0.10), while soil carbon is four times worse than nothing, because the response is obtained by DIFFERENCING two level predictions and that only works where the true change is large compared with the level error. Record: `docs/decisions/20260908-X-response-fails-on-one-climate-per-place.md`.
- **The pre-declared 5° sensitivity check turned out to be load-bearing**, not a footnote: at 5° blocks the address null flips from −0.142 to +0.120 on the response and would trip the no-power rule. The 15° primary is what makes the result mean anything.

### Changed
- **The emitted state loads but its carbon is half right** — vegetation carbon 2,561 against the control's 5,035 gC/m², a median relative difference of 0.534 — and the cause is attributed, not guessed: for the same cells the emulator predicts above-ground biomass to 12 %, so the fault is that carbon is not one of the donor-matching targets. Record: `docs/decisions/20260908-T-restart-loads-but-carbon-is-halved.md`.

### Fixed
- **The per-stem `litter` byte is an INDEX into its patch's litter list, not a value.** A transplanted stem carried its donor patch's index and the C refused the file with `ERROR195`. No round-trip test can catch this: within one record the index is always consistent, and it breaks only when a stem moves between patches. Indices are now remapped to the target patch's slot for the same PFT.
- **A falsy-zero coercion in the verdict engine reported a clean `fail` as `invalid`.** `x or default` treats a legitimate 0.0 as missing — and 0.0 is exactly what an analytic null is built to return, so the no-change null dropped out of the comparison and the next null's margin was measured against a negative arm: 0.0162 was computed as 0.1586. Every comparison in `tools/_experiments.py` now tests `is not None`.

<!-- collated 2026-09-08 from 1 fragment(s) -->

### Added
- **Two sealed pre-registrations.** `X-20260908-climate-state-map` asks whether a 30-year climate summary alone reproduces LPJmL-FIT's forest state inside the acceptance band on 22 quantities conjunctively — stem count, three stocks, six trait medians and both tails of each of those six trait distributions. `X-20260908-warming-response` is **the kill test**: a model fitted on the historical leg only, shown the same cell's climate for 1970–1999 and for 2071–2100 under high emissions, must explain the model's own simulated change better than predicting no change at all.
- **Every null is computable from the data with no learner** (`src/vegemu/nulls.py`), which is what makes it possible to pre-derive the value each one MUST return. The map test's nulls come out at 0.0212 (climatically nearest analogue), 0.0187 (geographically nearest cell), 0.0007 (shuffled) and 0.0000 (the average forest); the response test's at +0.0162 (everywhere changes by the average amount), exactly 0.0 (no change, analytic), −0.142 (copy the nearest cell's change) and −0.913 (shuffled).
- **The address null is a spatial nearest neighbour rather than a latitude/longitude regression**, because a weak null is worse than no null — and because a nearest neighbour has no free parameters, so its required value can be derived before any model exists.
- `src/vegemu/dataset.py` — one loader, so the nulls line X derives are the nulls line T measures.
- `tests/test_folds.py` — the pre-registrations' leakage checks as executable assertions: no spatial block is split across folds, the feature matrix contains no address/state/CO₂ column, and every null is exactly reproducible.

<!-- collated 2026-09-08 from 3 fragment(s) -->

### Added
- **The LPJmL-FIT restart reader and writer** (`src/vegemu/binfmt/restart.py`). Rung 0 passes: 100 real cells spanning 360 KB to 3.5 MB read out of the 119 GiB ground-truth file and written back **byte-identically**, plus a property test over the four variable-length parts (the litter list, the per-stem PFT list, the two 20-year ring buffers, the sapling pool).
- **The `.clm` reader and writer** (`src/vegemu/binfmt/clm.py`). Two whole real input files round-trip byte-identically; the 11.7 GB forcing files are proven piecewise (header + one year's raw block). The mixed-version trap is now an executable assertion rather than a comment.
- **`docs/reference/binfmt.md`** — the field-by-field spec, each field naming its C source.
- `src/vegemu/paths.py` — resolved access to `config/paths.yaml` from inside the package.
- `src/vegemu/score.py` — the acceptance band, the conjunctive band-fraction statistic, the response skill, and the blocked spatial folds. Shared on purpose: line X derives what each null must return with the same code line T uses to measure the model.
- **The corpus builder** (`src/vegemu/corpus/`, `scripts/corpus_build.py`). Per-cell state summaries read straight out of the restart files — counts, stocks, the growth-failure counter, the height distribution, PFT composition and five quantiles of each of eight per-stem traits — and per-cell 30-year climate summaries read out of the `.clm` forcing. Both seeds of all three legs, so the acceptance tolerance (the model's own two-seed spread) is measured rather than assumed. Provenance, including each source file's decoded header, ships with every table.

### Changed
- **The 1000-year spin-up has not converged.** Global vegetation carbon is 719 Pg C at year 200, 735 at year 500 and **890 at year 1000**, still rising at **+6.5 %/century**; 58 % of vegetated cells are outside their own acceptance band at the end of the run and 73 % are still rising faster than 1 %/century. So the stored state is not an equilibrium but *the state the model's standard spin-up protocol reaches*, and `PLAN.md`'s hoped-for 3.3× cut to every corpus budget is refuted — a 300-year spin-up would differ by 22 %. Record: `docs/decisions/20260908-D-spinup-is-not-converged.md`.
- **The noise floor, measured on this data:** the two-seed relative spread of end-of-spin-up vegetation carbon has a median of 3.41 %, a p90 of 13.6 % and a p99 of 42.4 % across 61,700 vegetated cells. Interannual variability of the annual series is 16.5 % of the level.

<!-- collated 2026-09-02 from 1 fragment(s) -->

### Added
- the campaign ledger, so a job launched by a dead session cannot be lost

### Fixed
- the append-only checker no longer silently passes when origin/main is absent

