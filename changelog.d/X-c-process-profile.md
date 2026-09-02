### Added

- **Line X, ADR 0312 — where the ORIGINAL model's runtime goes, by process, at five biome sites**, answering
  an owner question about learning only the expensive processes. `perf` profiles of the **unmodified
  production binary** (it already carries debug symbols, so **no rebuild and no change to the oracle's
  reference basis**), analysed by `scripts/explore_c_process_profile.py`, which adds the three things ADR
  0093's inclusive shares cannot give: an **exclusive attribution summing to 100 %**, the statically-linked
  math routines **attributed to their calling process** (21–27 % of self time, no source file), and the
  **Amdahl ceiling per process**. Self time: per-tree daily assimilation/conductance **36–46 %**, soil water
  15–27 %, daily driver loop 8–15 %, canopy light 6–11 %, litter/soil carbon 5–7 %, soil thermal 3–5 %,
  phenology 1–7 %, **annual demography 0.44–1.06 %**; the daily loop is 97.4–98.2 % everywhere. ⚠ **The
  pre-registered falsifier fired at all five sites:** making the largest process entirely free buys only
  1.57–1.84× against a requirement of ≈15–25×, so "learn only the expensive process" is viable **only as a
  portfolio covering ≥ 90 % of the daily loop** — and every ceiling assumes a free replacement (at 20 % of the
  replaced cost, 1.84× becomes 1.56×). The strategically important reading: **the annual demography's speed
  value was never its own 0.6 %, it is that it removes the patch tax** (cost is linear in patch count and this
  configuration runs 25). Two further targets: `exp`/`pow`/`log` at 21–27 % is an **engineering** target with
  no learning and no fidelity risk, and the λ root-find is the best-posed **learning** target (smooth,
  deterministic, scalar, stateless, 33.3 % inclusive) with the caveat that the gross flux is non-monotone in
  its iteration count. Marginal cost varies only 1.7× across biomes and the **tropical cell is the cheapest**.
  **Exploratory — nothing implemented, no rebuild, no C source change, nothing raised with any line.**
