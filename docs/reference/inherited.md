# Inherited findings — what carries over from the retired predecessor

The predecessor is `/p/projects/open/Jamir/esm_land_emulator`: a hybrid physics/ML land component for
an Earth system model, 887 commits over 34 days, 147 decision records. It is the **read-only archive
of record** — cite it, never write to it.

This file is the whole of what transfers. It exists so that no session here has to read 147 records
or 66,000 lines of prose to avoid a mistake that was already made and paid for. Everything below is
`[MEASURED]` in that repo unless marked otherwise; where a number matters, the record that carries it
is named so you can go and read the original.

**What does NOT transfer:** the hybrid architecture, the differentiable physics core, the daily flux
and energy components, the ESM coupling, the error-attribution ladder, the ADR number-block scheme,
the five-line ownership map, and every per-milestone stopping condition. Those died with the design.

---

## 1. Why the predecessor was abandoned

Three failures, in the owner's terms: it never reproduced the model's transient behaviour, never got
tree deaths right, and never captured the warming response. Underneath, per its own records:

* **The one-step learned operator's skill was almost all null.** Out-of-sample R² **0.9824** against a
  **persistence null of 0.9622** on 121 M rows — 96 % of the headline was "next year looks like this
  year". *(records 0113/0115)*
* **Recursing it destroyed the response.** Freely rolling that operator flipped the aggregate warming
  response from **+0.707 to −0.226** against a target of 1.0, while R² fell only 0.982 → 0.918. The
  mechanism is **rectification**, not noise: it reproduced 86.7 % of a large stem decline but 96.2 %
  of a large increase. Validity horizon 1.03 at 2 years, **−0.82 at 40 years**. *(0113/0114/0116)*
* **It was ~3.8× SLOWER per cell-year than the model it replaced** — 1.096 against 0.290–0.383
  core-seconds — because its per-tree daily step cost 51× the C code's. *(0093/0094)*

⚠ **None of this indicts a DIRECT climate → state map, which is what we build.** No rollout, no
recursion, no daily step. The failures above are properties of an autoregressive operator and of a
differentiable physics core, and we have neither.

---

## 2. The identification limit — the deepest result, and the reason this project generates data

Within a single emissions scenario, a cell's warming increment is **76.4 % predictable from its own
baseline climate**. So "how a forest responds to warming" and "what kind of place this is" are **not
separately identified** in the existing data. Consistently: knowing a cell's *future* climate adds
nothing over knowing today's on 5 of 6 targets, and a counterfactual with the warming scaled to zero
still reproduces **76–110 %** of the predicted per-cell change. *(0311)*

Compounding it: the **effective independent spatial sample is ~161 populated 15°×15° tiles** (312 at
10°, 957 at 5°), not 54,020 cells. Row counts overstate independent spatial evidence by roughly four
orders of magnitude, and any per-cell score under random folds is a spatial-interpolation score until
a geographic-address null is reported beside it. *(0310 §7, 0040)*

**This is exactly what the designed spin-up perturbation ensemble breaks.** The limit exists because
the corpus has one climate per location. Running the same cell under many climates decollinearises
them by construction. It is the one thing the predecessor could not do, because its target was a
transient trajectory rather than an equilibrium.

---

## 3. The one piece of POSITIVE evidence, and it is for our estimand

A direct map from a **20-year climatology to a 20-year-window state** beat a coordinates-only null by
**+0.162 to +0.715** under **spatially blocked** folds, and climate *subsumed* the geographic address
rather than proxying for it. Its adversarial verifier attacked it with three independent address
nulls and the margin came out **2–6× larger**. *(0311)*

The predecessor's earlier kill of this claim (a per-cell response R² of 0.748 dying to a lat/lon null
at 0.654) was a **hash-fold artifact on a drift-contaminated target** — it does not apply to a
blocked-fold, clean-window estimand. Read 0311 before quoting 0310 on this.

Its own conclusion, unprompted: *"a direct, NON-autoregressive climatology → 20-year-mean-state map —
never considered, its estimand EQUALS the acceptance criterion, and it eliminates rollout drift by
construction."* That is this project.

---

## 4. Facts about LPJmL-FIT that will cost you a week if you rediscover them

**The per-tree table is CENSORED and cannot be inverted into a restart file.** The writer drops every
stem at or below 5 m (`fwriteoutput_ind.c:122`), which is ~29 % of crown cover at boreal and semi-arid
cells and 47 % of the stems at a temperate one. This asymmetry is central: it is why our corpus
targets **restart files**, and why corpus runs set `LPJ_IND_ALL_HEIGHTS=1`. *(0060, 0130)*

**The table's `gpp` column is a copy of `npp`.** `daily_natural.c:193` does `pft->agpp += npp`, so
LPJmL-FIT has no per-individual gross photosynthesis at all and a per-stem carbon-use efficiency comes
out as exactly 1.0000 on every row. Never read that column as GPP. *(0130)*

**A subset re-run is not a per-cell replica of the global run.** Same binary, same restart, same
forcing: one cell alone diverges at the *first* step; a 21-cell block stays bit-identical for 15 years
and then diverges. The mechanism is unestablished. ⇒ never score a subset re-run against global ground
truth, and any equivalence gate needs a matched cell set **and** matched task decomposition. *(0041)*

**Never judge a C run from its scheduler exit code.** The stock job files always exit 0, so a run that
died mid-century leaves a plausible truncated output behind a green row. Require the model's own line
`lpjml successfully terminated, <n> grid cells processed.` in a **non-empty** log. A zero-byte log is
not "early days" either — a healthy run creates its output files within ~15 seconds.

**Never `cmp` two NetCDF outputs.** LPJmL writes a wall-clock timestamp into the `history` attribute,
so identical physics differ in bytes; 20 of 21 outputs "differed" for a bit-identical run. Compare
**decoded variables**. *(0043)*

**Read a `.js` parameter by running `cpp -P`, never by eye — and check for duplicate keys.** LPJmL
parses its own parameter files through the C preprocessor, and on a duplicated key the LAST occurrence
wins. There **is** a live duplicate: larch declares `aphen_min` twice, so its effective value is 10,
not the macro default 60. Also: the `"median"` of a sampled interval is a global default and lies
*outside* `[low, high]` for several tree types, so it is not a central value. *(0047)*

**The `.clm` forcing format is version-dependent and the scenario set is MIXED.** Historic is v3
(float32, scale 1.0); in the scenario legs `tas`/`pr`/`rsds`/`lwnet` are v2 (int16, **scale 0.1**, i.e.
tenths of a degree) while `huss` is v3. One hardcoded dtype reads four of the five wrong. The v3
datatype codes are **0-based** (`0=byte 1=short 2=int 3=float 4=double`); an off-by-one there once read
temperatures as ~5.9e8 °C. Always parse the header.

**The tolerance is `max(10 %, the model's own two-seed spread)`, because the model is stochastic.** Two
identical runs differ by up to **29 %** in low-density cells. Published per-cell floor ≈ Height 0.020,
above-ground biomass 0.113, NPP 0.062, leaf area 0.025. A mean score is not an acceptance test; report
the fraction of cells inside the band on the conjunctive basis (counts **and** distributions **and**
medians). *(0106)*

**Every tree carries a private consecutive-bad-growth-years counter that hard-kills it at 5.** It is
carried by 10.5–13.7 % of stems which bear 42–46 % of all mortality mass and 35–39 % of all deaths, it
is trait-correlated (+10 to +22 % wood density across its range), and **averaging it away reverses the
trait-selection sign in 3–4 of the 7 tree types**. It is a real restart field, so we must predict it —
and it is exactly recoverable from the printed table by algebra (exact-integer agreement 1.000000 on
694,662 stem-years against a "counter = 0" null of 0.878). *(0093, 0311 B1)*

**Mortality parameters are per-PFT and so is `respcoeff` (0.2 tropical vs 1.2 everything else, a 6×
span).** Reusing the temperate values for another tree type is a real error, not a rounding one: one
type's longevity is 125 rather than 400. *(0125, and the table in the predecessor's own runbook)*

**Per-cell count response, for calibrating expectations:** a typical |response| is 1.854 stems/patch on
a level of 7.053. And ~2.4 % of next-year count variance survives lag-1 and is the model's own
per-patch Bernoulli noise — the exact floor is ~28 % of residual variance — so a single-draw R² is
near-saturated, barely discriminates arms, and **the correct target is the ensemble expectation**.

**The acceptance-grade patch count is ~125–192, not the 25 in all existing data.** A tolerance derived
at 25 patches largely evaporates at acceptance grade, and the C at that grade costs ~1.8–2.7
core-seconds per cell-year. State the patch count with every number. *(0093)*

---

## 5. Standing owner closures — do not re-litigate

**CO₂.** The emulator does not see CO₂ and must not respond to it. LPJmL-FIT runs constant CO₂ *on
purpose*: with nitrogen limitation off its CO₂ fertilization is unbounded, so a rising-CO₂ run inflates
vegetation carbon — its own CO₂ response is wrong. The emulator having none is **faithfulness, not a
gap**. Never propose a CO₂ feature, never list its absence as a defect. *(0004, 0107)*

**Reuse and licensing.** The owner is a member of both the LPJmL-FIT group and TUM-PIK-ESM, so reuse
of those models is authorised. Cite transparently; never raise the licence question again. *(0080,
0081)*

**Speed inside an atmosphere is out of scope here.** The predecessor ranked ESM-readiness above the
spin-up saving; this project deliberately supersedes that ordering on the owner's instruction
(2026-09-02). Replacing the 1000-year spin-up **is** the goal now.

---

## 6. Method discipline — the part worth more than any code

The predecessor lost five headline claims to adversarial review. Every one died the same way, and the
rules below are its accumulated answer. In this repo they are **mechanised** by the experiment registry
(error codes E02, E05, E06, E07, E08) rather than left to discipline — but the reasoning is here.

1. **State the reference basis in the same sentence as the number.** Source, leg, years, PFT set,
   patch count, binary build, and whether it is a level or a ratio. A number without its basis is not
   a result. The predecessor lost ~10 sessions to one basis artifact.
2. **Derive what the null must return BEFORE the run, and write it down.** Running a null is not
   enough: a null that silently returned the wrong value is indistinguishable from one that agreed
   with you.
3. **A metric the null also passes has no power.** Not a weak result — *no* result. It licenses no
   conclusion in either direction.
4. **A pre-registered threshold is not a pre-registered verdict.** Check that the decision expression
   evaluates the statistic you actually blessed; the predecessor's did not, once.
5. **Cross-validation by cell holds out SPACE, not TIME.** So a lagged-truth feature makes the score
   one-step teacher-forced. Grep the table builder for `shift(`, `_prev`, `_init`, `lag`.
6. **A ratio over time is partly robust to a basis substitution; a level is not.** Label every
   downstream claim ratio-or-level *before* re-measuring anything after a basis fix, and emit both
   columns side by side rather than replacing one.
7. **Confirm a code path actually executes before porting it as "the faithful fix".** Many LPJmL-FIT
   routines are gated off in this configuration, and some live expressions sit inside `/* test: */`
   comment blocks that `grep` lands in indistinguishably from real code.
8. **Price the incumbent at the configuration it would really be run at.** The predecessor's speed
   case claimed "210× faster" by measuring against a setting its own records said nobody needs.

---

## 7. Where to look in the archive

| Topic | Records |
|---|---|
| the acceptance criterion | 0106, 0111 |
| CO₂ closure | 0004, 0107 |
| the one-step operator and its null | 0113, 0114, 0115, 0116 |
| the response failure and its causes | 0178–0181, 0184 |
| the identification limit; positive evidence for the direct map | **0311** |
| the purely-data-driven exploration, six-way | **0310** |
| the per-tree bad-years counter | 0093, 0311 |
| restart/subset non-reproducibility | 0041 |
| NetCDF and log-truth traps | 0043 |
| parameter-file reading | 0047 |
| the censored per-tree table | 0060, 0130 |
| measured speed, and the goal ordering | 0084, 0093, 0094 |

Its `.claude/skills/residual-diagnosis/SKILL.md` (2,278 lines) is the long form of §6 and the single
most valuable artifact in that repo. Read it once, in full, before designing an experiment.
