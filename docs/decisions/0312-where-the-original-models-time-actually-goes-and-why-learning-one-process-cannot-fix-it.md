# 0312 — Where the original model's runtime actually goes, by process: no single process replacement reaches 2×, and the demography we already learn costs 0.6 %

* **Status:** **exploratory — a recorded measurement + its strategic reading, NOT a decision.** Nothing here
  has been raised with line S, M, E or O, or the integrator; nothing was written to `MEMORY.md`,
  `EXECUTION_PLAN.md` or any other line's `STATE.md`; nothing is implemented.
* **Date:** 2026-09-02.
* **Line:** X — project direction & exploration. Tier-1 block 0310–0329. **Next free number: 0313.**
* **Answers an owner question, verbatim (2026-09-02):** *"find out which parts of the original model consume
  most computational time (e.g. photosysntesis or other processes). we can use this as basis for explorign
  soltutions where only these processes are learned."*
* **Extends, does not supersede, ADR 0093** (owner-approved), which published four **inclusive** shares from a
  profile of the same binary at the same cell block. Those are nested and therefore cannot answer
  "what do I gain by replacing process X?"; this record adds the exclusive attribution that can.
* **Basis:** `perf` sampling profiles of the **unmodified production binary** at **five biome blocks**
  (21 cells each, 20 years, 25 patches, single task, from the spin-up-end restart), analysed by
  `scripts/explore_c_process_profile.py`. 24 k–33 k samples per profile, 184–211 symbols each.

---

## 1. Method, and the one thing about it that matters most

⚠ **NO REBUILD, NO SOURCE CHANGE, NOTHING WRITTEN NEAR THE ORACLE.** The production binary already carries
debug symbols and is not stripped, so `perf record` needs neither. This is deliberate: a rebuild changes the
reference basis that **every** C-vs-emulator number in this repo is measured against (CLAUDE.md §3 requires a
139-quantity equality gate after any rebuild), and an exploration line has no business moving it. The profiles
were recorded by the **existing, unedited** `scripts/bench_speed_gate_c.sh` with `PERF=1` — line O's harness,
*invoked* not modified — with `ROOT` pointed at line X's own scratch (`/p/tmp/jamirp/X_cprofile`).
⚠ That harness hard-codes its own SLURM job name, so these jobs appear in `squeue` as `O-cbench` rather than
with an `X-` tag. The output path is the provenance; the tag is not.

**Three things this probe does that no previous profile here did.** (i) An **exclusive (self-time)**
attribution that **sums to 100 %**, so Amdahl arithmetic on it is valid. (ii) The statically linked Intel math
routines (`__libm_*` / `__svml_*`) attributed to their **calling process** from the recorded call graph —
they carry **21–27 % of self time** and have no source file, so a source-file-only grouping silently drops a
quarter of the run. (iii) The **Amdahl ceiling per process**: the most the whole model could speed up if that
process became *free*.

**Gate results (pre-registered, printed before any number).**
* **GATE 1, completeness: PASS at all five** — self shares sum to 99.78–100.11 %, and `other` + `unmapped`
  stays at **1.35–2.12 %**.
* **GATE 2, agreement with ADR 0093's published inclusive shares:** `update_daily` **PASSES at all five**
  (97.38–98.23 % against its 98.6 %, tolerance 2). `water_stressed` and `photosynthesis` **PASS at Hainich**
  (46.85 vs 49.4; 37.11 vs 41.3) and **MISS at the other four**. ⚠ **That miss is a mis-specified gate, not a
  probe error, and it is itself the finding**: ADR 0093's numbers are Hainich-specific and I applied them as a
  gate everywhere. The shares genuinely vary by biome (photosynthesis inclusive runs 18.79 % at the Sahel to
  37.11 % at Hainich). Recorded as a pre-registration miss rather than restated after the fact.
* **GATE 3, math attribution closes: marginal FAIL at all five** — the caller-attributed math total lands
  0.72–1.23 points below the directly measured math self time (tolerance 0.5), i.e. **3–6 % of the math is
  unresolved**. It is carried as a visible `math_unattributed` row rather than folded into a process.
* ⚠ **Two parsing bugs in this probe were caught by its own gates and fixed before any number below was
  read** — the math attribution initially double-counted nested call-graph levels (inflating it 25.4 % →
  39.2 %), and the inclusive parse silently keyed every symbol with trailing columns glued on, returning
  nothing. Both are documented in the script. **This is the argument for writing the gates first.**

---

## 2. The answer: self time by process, five biomes

Percent of total cycles, math redistributed to the calling process. Columns are the five biome blocks.

| process | Hainich | Amazon | Sahel | Iberia | Siberia | **Amdahl ceiling if FREE** (Hainich) |
|---|---|---|---|---|---|---|
| **leaf gas exchange** (assimilation + conductance, per tree per day) | **45.78** | **41.78** | **36.17** | **41.36** | **38.33** | **1.84×** |
| **soil water** (infiltration, percolation, interception, root profile, pedotransfer) | 21.36 | 27.48 | 15.41 | 19.37 | 16.20 | 1.27× |
| daily driver (the per-PFT/per-tree loop itself, dispatch, depletion-order permutation) | 7.64 | 7.65 | 14.83 | 9.00 | 13.90 | 1.08× |
| canopy light (layered absorption, albedo, leaf-area geometry) | 7.37 | 5.88 | 9.75 | 8.34 | 10.71 | 1.08× |
| litter + soil carbon decomposition | 6.38 | 5.74 | 6.37 | 6.61 | 4.58 | 1.07× |
| soil thermal / enthalpy column | 3.82 | 4.59 | 4.45 | 4.58 | 3.21 | 1.04× |
| phenology + daily leaf turnover | 2.53 | 1.47 | 7.17 | 3.94 | 5.85 | 1.03× |
| the λ root-find's own bookkeeping (excl. the photosynthesis calls it makes) | 1.83 | 1.54 | 1.16 | 3.33 | 2.41 | 1.02× |
| **the ANNUAL demography — allocation, mortality, establishment, turnover** | **0.63** | **0.44** | **1.03** | **0.86** | **1.06** | **1.01×** |
| output / bookkeeping | 0.17 | 0.16 | 0.18 | 0.18 | 0.18 | 1.00× |
| unmapped (`other` + unresolved math) | 2.37 | 3.33 | 3.36 | 2.21 | 3.44 | — |

**Absolute cost, marginal rate (the slope over two run lengths, so every per-run fixed cost cancels), same
blocks, 25 patches, single core:** Amazon **0.1996** · Sahel **0.2749** · Iberia **0.2755** · Siberia
**0.3349** core-seconds per cell-year, against Hainich's published **0.2666** (ADR 0084). ⇒ **only a 1.7×
spread across biomes**, and — counter to the obvious expectation — **the tropical cell is the cheapest and the
boreal one the most expensive.**

**Also confirmed at all five: the daily loop is 97.4–98.2 % of the run.** Everything annual plus all output is
under 1.3 %.

---

## 3. What this says about the owner's strategy, and it is not what the framing expects

### 3a. The falsifier fired: no single process replacement reaches 2×

The largest process anywhere is leaf gas exchange at **36–46 %**. Making it **completely free** buys
**1.57–1.84×**. The strict per-cell-year allowance this project is measured against is **0.0135**
core-seconds (ADR 0093/0094) and the C is at **0.20–0.33**, so the requirement is **≈15–25×**, i.e. removing
**≈94–96 %** of the runtime.

⇒ **"Learn only the expensive process" cannot reach the speed target as a single-process substitution.** The
pre-registered falsifier for that strategy fired at all five sites. What the profile supports instead is a
**portfolio**, and the portfolio has to be large. Cumulatively at Hainich:

| replace (free) | cumulative share | ceiling |
|---|---|---|
| leaf gas exchange | 45.8 % | 1.84× |
| + soil water | 67.1 % | 3.04× |
| + canopy light | 74.5 % | 3.92× |
| + litter/soil carbon | 80.9 % | 5.23× |
| + the daily driver loop | 88.5 % | 8.72× |
| + soil thermal | 92.4 % | 13.1× |
| + phenology + the λ solve | 96.7 % | 30.4× |

⚠ **And every one of those is an upper bound that assumes the replacement costs NOTHING.** A learned
replacement costs its own evaluation: if it runs at a fraction `f` of what it replaced, the gain is
`1/((1−s) + s·f)`, not `1/(1−s)`. At `f = 0.2` the leaf-gas-exchange row falls from 1.84× to **1.56×**.
**Never quote a ceiling as a speed-up.**

### 3b. The thing we already learn costs 0.6 % — and that is NOT an argument against learning it

**The entire annual demography — allocation, mortality, establishment, turnover, the whole block the
project's learned slow component replaces — is 0.44–1.06 % of the original model's runtime.** Its Amdahl
ceiling is **1.01×**. Two readings, and only the second is right:

* ✗ the tempting reading: *"we have been learning the cheapest 0.6 % and keeping the expensive 98 % as
  physics, so the learned component is worthless for speed."*
* ✓ **the correct reading: the demography's value for speed was never its own cost — it is that it removes
  the patch tax.** ADR 0093 measured the C's cost as **exactly linear in the number of patches**, and this
  configuration runs **25**. A component that predicts the *ensemble expectation* directly does not need to
  run 25 stochastic replicates, so it converts a ~25× multiplier into 1. **That single lever is larger than
  every process in the table combined.** The reason nobody can simply set the patch count to 1 is
  **fidelity** — the ensemble is what resolves a cell's answer, and per-cell certification needs *more*
  patches, ~125–192 (ADR 0093) — not speed.
* ⚠ **I did not re-measure the patch scaling.** It is ADR 0093's number, cited not reproduced. My own blocks
  imply 0.0080–0.0134 core-seconds per patch-year at 25 patches against ADR 0093's published 0.0176–0.0185 —
  a factor ~1.4–2 apart, unreconciled (different block, possibly a different build). **Re-measuring the
  npatch slope on this binary is the cheapest missing number in this record.**

### 3c. A quarter of the entire model is `exp`, `pow` and `log` — and needs no learning at all

Math-library self time is **21.02–27.26 %** at the five sites. Its callers, measured from the call graph
(Hainich): **photosynthesis 7.9** · root-profile 5.8 · pedotransfer 3.5 · infiltration 2.7 · litter
decomposition 2.4 · phenology 0.6 · canopy 0.4. ⇒ **an engineering target, not a learning target**: vectorised
or reduced-precision transcendentals, and hoisting loop-invariant kinetics. Ceiling **1.28–1.37×** on its own,
with **no fidelity risk and no learned component**, and it composes with everything else. Note this is the
same defect class the emulator has on its own side — ADR 0084 measured **26.5 %** of the Julia core in
`^(::Float64,::Float64)`, all of it recomputing temperature-only kinetics.

### 3d. The best-posed *learning* target is not a process — it is the iterative solve inside one

The λ root-find is **1.16–3.33 %** of self time *by itself*, but that is bookkeeping: its cost is the
**photosynthesis calls it makes**, up to 30 per tree per day (`water_stressed.c:207`), and ADR 0093 measured
the bisection at **33.3 % inclusive**. So it sits on the largest share in the table while being, structurally,
the friendliest thing in the model to learn: **a deterministic, smooth, scalar-output function of a handful of
inputs, replacing an iteration with one evaluation.** It has a clean interface, needs no state, cannot drift,
and its training data can be generated in unlimited quantity from the C itself.
⚠ **Two cautions from the record before anyone prices it.** (a) On the emulator side the same solve is
**82.7 %** of cost and a sweep of its iteration count showed the gross flux is **non-monotone** in the
iteration count (±2.1 %, reproducing across runs) ⇒ *"30 iterations" is not evidence of convergence*, so the
thing being learned may not be as well-determined as it looks. (b) The λ argument does **not** change the
final carboxylation rate (ADR 0136), so what a learned λ actually buys has to be measured on the flux, not
assumed.

---

## 4. What would have to be true for the owner's idea to work

**"Learn only the expensive processes" is viable — but only as a portfolio covering most of the daily loop,
which makes it close to a whole-daily-core replacement rather than a surgical one.** Concretely, for it to
reach the target:

1. **The portfolio must cover ≥ 90 % of the daily loop** (leaf gas exchange + soil water + canopy light +
   litter/soil carbon + the loop itself), because the tail is genuinely flat — after the top two processes,
   nothing is worth more than 1.1× alone.
2. **Each learned piece must run at ≲ 10–20 % of the cost it replaces**, or the ceilings above collapse.
3. **The conserved quantities must survive.** Water closure ~1e-12 and energy ~1e-14 are CI gates
   (guardrail 2), and soil water is the **second largest** process — a learned infiltration/percolation
   operator has to conserve mass by construction, not by penalty. This is the same objection that killed the
   fp32 saving in ADR 0310 §2(v).
4. **The interfaces must be stable and the physics live.** Every candidate needs the `individual = true`
   dead-path check first (CLAUDE.md §3, guardrail 5) — and the C source carries dead expressions inside
   `/* test: */` comment blocks that `grep` lands in (ADR 0135).

**And the honest comparison, which the framing invites getting wrong:** all of this is a strategy for making
*the original model* fast. The emulator as it stands is **4.62× slower** than the C it replaces (ADR 0084), so
"learn the expensive parts" is competing against an incumbent that is currently *winning* on speed. The
patch-count lever (§3b) is the only one in play that is larger than the whole daily loop.

---

## 5. Artifacts

* `scripts/explore_c_process_profile.py` — the probe (line-X owned; lint-clean under
  `ruff --select E,F,I,UP,B --line-length 100`; pre-registration and all three gates in the module docstring
  and printed before any result; `--discover` finds the profiles).
* `/p/tmp/jamirp/X_explore/cprof_processes.csv` (the table above), `cprof_symbols.csv` (all 184–211 symbols
  per profile with their process assignment), `cprof_math_callers.csv` (the math→caller attribution).
* `/p/tmp/jamirp/X_cprofile/min_c{12035_12055,18361_18381,33325_33345,52049_52069}_y10_20/` — the four new
  biome profiles + their marginal-rate logs. Hainich reuses line O's existing
  `/p/tmp/jamirp/O_speedgate_c/min_c42480_42500_y10_20/perf.data` **read-only**.

⚠ **Basis warnings that travel with every number here:** 21-cell blocks around five biome cells, **not** the
54 020-cell criterion population; **25 patches** throughout, and the shares would shift toward the
per-individual processes at acceptance-grade patch counts; single task, single core, one machine
(`csp14c01`/`csp14c29`, Zen 4); sampling profiles, so a share below ~0.2 % is noise; and the **npatch slope
is cited from ADR 0093, not reproduced here.**

## 6. Nothing here is implemented, and nothing has been raised

No source change to the C, no rebuild, no `src/**` change, no flag, no edit to another line's files or to
`MEMORY.md`, `EXECUTION_PLAN.md` or `CHANGELOG.md`. The profiles were recorded with an existing harness,
unmodified, writing only into line X's own scratch. Propagating §3b's reading — that the learned demography's
speed value is the patch tax, not its own cost — is the owner's call.
