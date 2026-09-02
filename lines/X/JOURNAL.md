# LINE X — JOURNAL (append-only)

Narrative for line X only. Durable state: `lines/X/STATE.md`. Decisions: ADR block 0310–0329.
Newest entry at the bottom.

---

## 2026-08-19 — the line is created, and its first exploration is relocated into it

**Why the line exists.** The owner asked whether a *purely data-driven* emulator could replace the hybrid —
learn `(forest state, climate) → next forest state`, roll it out, plus a daily flux head for an ESM. The
question was put to **line O** (online coupling), which explored it, and the owner then corrected the venue
twice in quick succession:

1. *"no! stop! dont write anythign of this to other lines!!! we are jsut discussion a new direction of this
   project here, nothing to do wiht other lines!!!"* — issued while line O was mid-write of an INBOUND block
   into `lines/S/STATE.md` and about to append cross-cutting facts to `MEMORY.md`. **Both were abandoned; the
   `lines/O/STATE.md` edit was reverted with `git checkout --`.** Nothing reached another line.
2. *"you are also nto the correct person to discuss this with. relocate our whole discussion to a new line
   that is responisble for these project lever decisions and exploring new ideas."*

**What that diagnosed, and it is a real structural gap, not a preference.** The four component lines are each
mid-ladder on one subsystem. A question of the form *"should the architecture be different?"* therefore has no
owner: whichever line is asked must either act on it (wrong — not their call) or drop it. Line O's own
exploration illustrates the failure mode exactly — it produced a defensible finding and then, following the
capture discipline in CLAUDE.md §8 faithfully, immediately began pushing it into two other lines' state. **The
discipline was right and the venue was wrong.** Line X can hold an open question without pushing it at anyone.

**What was done.**

* **Line X bootstrapped complete**, so its first working session starts on content rather than plumbing:
  `lines/X/STATE.md` (charter — scope, the "does NOT do" list, owned paths, the four traps), this journal,
  branch `line/X`, worktree `/p/projects/open/Jamir/wt-X`, ADR block **0310–0329** allocated in CLAUDE.md §9
  (tier-2 reserved at 0330–0349), the row in `docs/decisions/README.md`, and `wt-X` added to the
  SessionStart hook's integrator hint list. The hook needed **no** code change — it is generic over `line/*`
  and resolves `lines/<letter>/STATE.md`.
* **ADR 0088 → ADR 0310, relocated before it was ever committed**, with a Status box quoting both owner
  instructions and stating plainly that nothing was raised with any line and nothing binds anyone.

**The finding itself** (full record in ADR 0310): the proposal is **six problems with six answers**. Daily
water/carbon = data exist, learnability untested. Daily **energy = impossible from this model, permanently**
(of 421 outputs, only monthly albedo + soil temperature are energy-adjacent). One-step operator = already
built, **96 % of its skill is the persistence null** (0.9622 of 0.9824). Century rollout = stable, but every
reason given for the stability was a piecewise-constant-forest artifact, and rollout training has never been
run here. **The warming response = not demonstrated, and zero positive evidence exists** — the one claim died
to a null nobody had run (a pure lat/lon address scores 0.654 of the 0.748 attributed to climate). Speed =
**≈0.0032 core-s/cell-year at fp64**, inside the strict convention with 4× margin.

**Method note worth keeping.** 6 investigations → 6 adversarial reviewers → synthesis → completeness critic
(14 agents, 2.66 M tokens). **All six investigations were refuted.** The reviewers killed five numbers that
would otherwise have been reported to the owner as measurements: a speed figure timed on arrays that had
overflowed to `inf`; a "210× faster than the C" comparison rigged against a configuration nobody runs; a
"needs 0.12 % level accuracy" bar computed on a global aggregate that appears in no acceptance criterion; a
cross-leg error correlation that was actually an 80-year within-chain memory decay; and the response-recovery
headline that fell to the geographic null. **The critic then found the single most important omission — an
architecture that is purely learned yet keeps the per-individual roster — which no investigator and no
reviewer had considered.** ⇒ the adversarial layer earned its cost, and the *completeness* layer earned it
twice; neither is optional on a direction question.

**Also corrected during the session, to the owner, unprompted:** my own earlier hypothesis that the flat
warming response was caused by conditioning on per-cell constants. **Refuted by measurement** — 13 of 15
inputs do vary between scenarios. The real cause is a target defect (the next-year count is 96 % determined
before climate is consulted), which survived review.

**Left open on purpose:** five investigator-vs-reviewer disagreements (ADR 0310 §10), the largest being
whether the measured −0.226 response inversion bounds a closed rollout from below or from above. Recording
them as disagreements rather than picking a side is the point of the line.

## 2026-08-19 / 2026-09-02 — round 2: the response verdict flips, and the campaign is half-finished

**What the owner asked:** *"continue the exploration of the efasability of a more data driven emulator."*
Note **more**, not **purely** — ADR 0310 had priced only the pure endpoint against the shipping hybrid, so the
middle of the spectrum was, and still is, unpriced.

**What was run.** A 16-agent campaign (`wf_5ba7e1aa-b45`): 2 scouts + 1 shared-table prep, 6 pre-registered
measurements each pipelined into an adversarial verifier, a spectrum synthesis, a completeness critic.
**11 agents completed** across three launches. It took three attempts — a session usage limit killed 10 of 11
on the first, transient 529s killed the three measurements on the second, and the limit took B1's verifier on
the third. Lesson worth keeping: **run a large campaign in waves and lean on `resumeFromRunId`** — trimming
`ITEMS` to `.slice(0, 3)` and deferring the synthesis meant nothing completed was ever re-spent, and the
per-call cache made the third launch cost only the three measurements plus two verifiers.

**The result, in one line: ADR 0310's headline verdict on the warming response is overturned, and the reason it
was wrong is the fold scheme.** A direct, non-autoregressive climatology → 20-year-window-state map — the
architecture ADR 0310 §4 listed as *"never considered"* — beats a coordinates-only null under spatially
blocked folds by **+0.162…+0.715** on a clean 20-vs-20-year response target, with climate *subsuming* the
address rather than proxying it, and the margin got **2–6× larger** when its verifier attacked it with three
independent address nulls instead of one. ADR 0310 had killed that claim on **hash folds** against a
**drift-contaminated 20-vs-81-year** target. So the first positive evidence in this project for the part the
owner actually cares about exists — while the same map sits at **7.2 %** of cells on the owner's conjunctive
per-cell basis and **loses to persistence** on the future state.

**The deepest finding was not on anyone's list.** Within a single emissions scenario, a cell's warming
increment is **76.4 %** linearly predictable from its own baseline climate ⇒ *"response to warming"* and
*"sensitivity of this place"* are **not separately identified**. Three independent consequences all agreed:
knowing the future climate adds nothing over knowing today's on 5 of 6 targets; the change-only arm carries
almost nothing; and a counterfactual with the warming scaled to **zero** still reproduces **76–110 %** of the
predicted per-cell change, while a structurally scenario-blind control returned exactly 1.0000 in 18 of 18
groups (so the probe was correctly wired). That single number is why the third forcing leg went from
nice-to-have to necessary — and the literature scout had independently established that only a **bracketed**
held-out design has ever succeeded anywhere in earth-system science.

**The adversarial layer earned its cost again, and in a new way.** Round 1's reviewers killed five numbers.
This round they *improved* one: B3's verifier found a 4-way inner join that silently dropped **4 635 cells with
no tree today and +6.455 stems/patch in the 2080s** — the poleward treeline advance, the model's single largest
warming response, 231× the mean of the cells that were scored. Repairing it took the response R² from 0.274 to
**0.529**. A verifier making a finding *stronger* by fixing a survivorship defect is a mode neither round had
seen. B2's verifier went the other way and refuted a magnitude: the growth target is one-step, and copying
last year's own increment with **zero parameters** returns **90.7 %** of the reported R² — so the honest span
is +0.0817, not 0.887, and the reported block decomposition understated the patch by 11× and climate by 10×.
**The correction ran against that item's own thesis and left it standing**, because the absolute climate
increment never moved.

⚠ **The process lesson is uncomfortable and is the highest-value thing here.** ADR 0310 §2(ii) wrote the
persistence rule down as a **STANDING RULE**, after a reviewer killed a headline on exactly it. **The very next
campaign violated it anyway**, having been instructed to read that record. A rule living in an ADR body does
not fire; it has to be in the pre-registration template the measuring agent fills in. Two sibling failures
recurred the same way: three of one item's five "surprises" were stale against records it had been told to
read, and one numbers row existed in **no log and no artifact** (the verifier reproduced most of it, found a
label error and one unreproducible figure) ⇒ anything tagged `[MEASURED]` needs a log line.

**Three corrections that belong to other lines were found and deliberately NOT propagated** (ADR 0311 §6;
propagation is the owner's call). The largest: **ADR 0125's per-stem cross-year identity key is wrong** — it is
`(Cell, Patch, PFT, ID)`, because the tree number is issued by a per-PFT counter. On the documented key the
identity gates **failed on every leg**; on the corrected key, **0 violations of 20.4 million consecutive-year
pairs on three independent checks**. The prep agent found it by taking the gate seriously instead of assuming
the record was right, and kept the failing job log as evidence. Anyone building a per-stem model on the
documented key would have been pairing trees that are not the same tree.

**Left deliberately unfinished:** the ssp126 bracketed held-out test, flux-state sufficiency, the closed
density-feedback rollout with a stochastic head, the spectrum synthesis, the completeness critic, and B1's
verifier. All queued in a resumable workflow; everything already done replays from cache. The purely
data-driven direction is **still not refuted and still not demonstrated** — but for the first time it has a
positive measurement on the response and a measured negative on the channel that would have to carry it.
