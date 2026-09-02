#!/usr/bin/env python3
"""explore_prep_tables.py — LINE X, campaign item P0: build the SHARED derived tables that the
measuring agents of the "could a purely data-driven emulator replace the hybrid?" campaign consume.

THIS IS PREP, NOT A FINDING. It produces no skill number and no verdict. Its only job is that the
agents measure the SAME rows, with the SAME column definitions, and with the identity and
uniqueness gates already run so nobody re-derives them.

Read-only w.r.t. every repository path: it reads /p/tmp/jamirp/emulator_global/**, the LPJmL .clm
forcing (via the committed header-driven reader) and the C source, and writes ONLY into
/p/tmp/jamirp/X_explore/.

------------------------------------------------------------------------------------------------
STAGES (positional arg 1)
  a   -> X_explore/prep_paired_stems.parquet       per-stem, YEAR-PAIRED, cells `Cell % 100 == 0`
  b   -> X_explore/prep_patch_year_stand.parquet   per (leg, seed, Cell, Patch, Year) stand summary
  c   -> X_explore/prep_cell_window_state.parquet  per-cell 20-yr window forest state, ALL cells
  d   -> X_explore/prep_cell_window_clim.parquet   per-cell 20-yr window climatology, ALL cells
  e   -> X_explore/prep_cell_year_census.parquet   per (leg,seed,Cell,Year) presence + stem count,
         ALL cells, ALL years. NOT in the item's spec: added because stage A found that a stem can
         "vanish" simply because its whole cell-year block is ABSENT from the roster, which a
         paired-year measurement would silently score as a death. See amendment 3.
  all -> a, b, c, d, e in order

WHAT IS REUSED RATHER THAN REBUILT (checked before writing a line of this):
  * the per-patch stand-LAI reconstruction -> build_slow_runtime_table.patch_stand_lai_expr and
    K_LIGHTEXT (ADR 0035, gated by scripts/diagnose_patch_lai_reconstruction.py). IMPORTED, never
    re-derived: the ADR-0031 lesson is that two copies of one definition is how a defect gets in.
  * the tree-PFT population constant -> python/src/lpjmlfit_emulator/data.py::TREE_TYPES (0..6).
  * the header-driven .clm reader -> build_transient_boundary.open_clm plus its CLM / CLM_EXTRA
    path registries (the forcing set is MIXED v2-int16-scalar-0.1 / v3-float32).
  * the per-cell patch count -> tables/cell_npatch.parquet (not recounted).
  * the per-cell orderA position -> tables/cell_latlon.txt (built from the run's own grid.nc).
  * the 20-yr-window climate features -> tables/cell_year_env_{historic,ssp370}_w20.parquet, the
    ONLY tables that carry the same feature definitions on BOTH legs.
  Nothing here re-implements a column that already has a canonical implementation in the repo.

------------------------------------------------------------------------------------------------
CONVENTIONS, stated once (a measuring agent must not have to guess):

* LIVING = `isdead == 0`. Every stand aggregate below is on the LIVING stems, the convention
  build_slow_runtime_table.py:539 uses for every patch-state column the shipped emulator was
  trained on. The all-emitted-stems counts ride along as n_stems_all / n_dead so an agent that
  wants the other basis does not have to rescan 200 GB.
* TREE = `Type <= 6` (all seven tree PFTs; 7/8/9 are grass, 10-21 crops and never emitted).
* The `ind` writer emits a stem only if height > param.height_min = 5 m
  (fwriteoutput_ind.c:84), so EVERY row here is on that >5 m population and no aggregate is a
  whole-stand quantity.
* `nind = 1/param.patcharea` is a CONSTANT in this configuration ([SOURCE]
  /home/jamirp/lpjml56fit/src/tree/new_tree.c:216, individual = true), so an "nind-weighted mean"
  of a per-stem trait IS the plain unweighted mean. Both names are the same number; only the plain
  mean is stored, and this note is why.
* Mortality is applied AFTER allocation (ADR 0125), so a stem emitted with isdead == 1 still GREW
  through that year. It is kept in Table A with its flag and excluded from the LIVING aggregates.
* d_agb / d_vegc are defined ONLY on a consecutive-year pair of the SAME INDIVIDUAL KEY, and

  ⚠ THE INDIVIDUAL KEY IS (Cell, Patch, Type, ID) -- **NOT** (Cell, Patch, ID) [MEASURED, and it
    NARROWS ADR 0125]. `ID` is the emitted `tree->index`, drawn from a counter that lives in the
    per-PFT PARAMETER struct: [SOURCE] /home/jamirp/lpjml56fit/src/tree/new_tree.c:85-86
    `tree->index=treepar->index; treepar->index++;` with `treepar` = `pft->par->data`, one struct
    per PFT parameter entry, zeroed once at parse time
    ([SOURCE] src/tree/fscanpft_tree.c:171) and re-based to max+1 on a restart read
    ([SOURCE] src/tree/fread_tree.c:65-66). So the counter is PER PFT, and two stems of DIFFERENT
    `Type` in the SAME patch can carry the SAME `ID`. Measured on historic seed1 over the 674-cell
    sample: (Cell,Patch,ID,Year) has 18 duplicated rows, and pairing on (Cell,Patch,ID) reports 2
    Age-increment violations, 13 trait-mutation violations and 0 dead-reappears; adding `Type`
    takes that to 0 / 8 / 0 and the residual 8 all trace to ONE individual key. ADR 0125's
    five-cell result held because those cells are PFT-poor.

* A residual, genuine collision remains: (Cell, Patch, Type, ID, Year) is duplicated for exactly
  ONE key in historic seed1 (Cell 33000, Patch 2, Type 2, ID 1316754 -- two co-existing stems,
  distinct Wooddens 183878 vs 254253, 32 rows of 2 092 655 = 0.0015 %). Such keys are FLAGGED
  `dup_key = 1`, KEPT in the table (nothing silently vanishes) and EXCLUDED from pairing
  (`pairable = false`, `survived = null`). With them excluded the identity gates are exactly
  0 / 0 / 0 on 1 900 932 historic-seed1 pairs [MEASURED].

------------------------------------------------------------------------------------------------
Usage
  /home/jamirp/.conda/envs/py311_new/bin/python scripts/explore_prep_tables.py d      # light
  TIME=04:00:00 NCPUS=32 scripts/sbatch_python.sh X-prep-a scripts/explore_prep_tables.py a
  (parameters are POSITIONAL: the wrapper forwards only a fixed list of env names.)
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import polars as pl

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "python", "src"))
sys.path.insert(0, _HERE)

from build_slow_runtime_table import K_LIGHTEXT, patch_stand_lai_expr  # noqa: E402
from build_transient_boundary import CLM, CLM_EXTRA, open_clm  # noqa: E402
from lpjmlfit_emulator.data import TREE_TYPES  # noqa: E402

BASE = "/p/tmp/jamirp/emulator_global"
TBL = f"{BASE}/tables"
OUT = "/p/tmp/jamirp/X_explore"

# leg -> (roster path template, first year, last year). The two legs are DISJOINT in time and are
# separate LPJmL runs, so a `historic` 2019 row has NO in-leg successor even though ssp370 starts
# in 2020 -- `survived` is NULL there, never 0.
LEGS = {
    "historic": (f"{BASE}/ind_hist_seed{{seed}}_all.parquet", 2000, 2019),
    "ssp370": (f"{BASE}/ind_ssp370_seed{{seed}}_all.parquet", 2020, 2100),
}
SEEDS = (1, 2)

# (leg, window label, y0, y1) -- the three windows the acceptance criterion's response is about.
WINDOWS = (
    ("historic", "hist_2000_2019", 2000, 2019),
    ("ssp370", "ssp370_2020_2039", 2020, 2039),
    ("ssp370", "ssp370_2080_2099", 2080, 2099),
)

# The 29-column `ind` schema in file order (asserted against every roster before any derivation).
IND_29 = [
    "Year", "ID", "Type", "Height", "Age", "agb", "vegc", "transp", "npp", "gpp", "wscal_mean",
    "SLA", "Longevity", "Wooddens", "LAI", "fpc_ind", "minwscal", "D95", "D95max", "beta_root",
    "k_root", "mort_npp", "mort_age", "mort_water", "mort_temp", "mort", "isdead", "Patch", "Cell",
]

# The four SAMPLED recruit-trait axes. `k_root` is a scalar 0.02 in this config (ADR 0117) so it is
# NOT a fifth axis; `Longevity` IS a fifth measurable axis but is not one of the acceptance
# criterion's four, so it is carried in Tables A/B and not medianed in Table C.
TRAIT_AXES = ["SLA", "Wooddens", "D95max", "minwscal"]

# THE CROSS-YEAR INDIVIDUAL KEY. `Type` is load-bearing: `ID` = `tree->index` comes from a counter
# held in the PER-PFT parameter struct ([SOURCE] src/tree/new_tree.c:85-86), so two stems of
# different Type in one patch can share an ID. See the module docstring's amendment 1.
IND_KEY = ["Cell", "Patch", "Type", "ID"]

# The 8 climate features that exist with the SAME definition on BOTH legs (the w20 tables).
ENV_FEATS = [
    "eco_diag_gdd_5", "tas_cold_month", "eco_diag_vpd_mean", "eco_diag_pet_mean",
    "eco_diag_p_pet_ratio", "pr_cv_monthly", "prec_mean", "humid_mean",
]
# Of those, the ones stored Float32 -> MUST be cast to Float64 BEFORE any mean (CLAUDE.md 4:
# polars accumulates a Float32 mean in Float32 and lands ~3.4e-7 relative off the basis every
# shipped artifact was conditioned on).
ENV_F32 = ["eco_diag_gdd_5", "tas_cold_month", "eco_diag_vpd_mean", "eco_diag_pet_mean",
           "eco_diag_p_pet_ratio", "pr_cv_monthly"]

ENV_W20 = {
    "historic": f"{TBL}/cell_year_env_historic_w20.parquet",
    "ssp370": f"{TBL}/cell_year_env_ssp370_w20.parquet",
}


PREREG = """
==============================================================================================
PRE-REGISTRATION -- item P0 (PREP). Printed BEFORE any result is computed.
==============================================================================================
QUESTION
  Can the shared tables this campaign needs be built from the existing rosters and feature tables
  WITHOUT breaking the per-stem cross-year identity, the key uniqueness, or the column
  definitions the repo already gates?  P0 produces no skill number; it produces tables plus GATE
  RESULTS.

STATISTIC -- there is no "skill" here. These are the gates, each with the value it MUST return.

 G1  Schema identity. Every roster's column list == the frozen 29-col `ind` schema, in order.
     MUST RETURN: 4 of 4 rosters identical.   FALSIFIED IF: any roster differs.

 G2  Within-year key uniqueness. (leg, seed, Cell, Patch, Type, ID, Year) is unique in Table A
     once the `dup_key` rows are set aside.
     MUST RETURN: 0 duplicate keys among dup_key == 0, plus the dup_key census.
     Table A is collected NON-streaming precisely so polars' streaming group-by cannot drop or
     duplicate whole groups (CLAUDE.md: 12 cells with DUPLICATED keys at global scale).

 G3  ADR-0125 identity gate, Age. On every pair where the same INDIVIDUAL KEY appears in Year+1,
     next_Age - Age == 1 exactly.
     MUST RETURN: 0 violations of N pairs.
     FALSIFIED IF: > 0  ==> ID is not a stable identity and EVERY downstream per-stem paired
     measurement in this campaign is void.

 G4  ADR-0125 identity gate, immutable traits. On every such pair SLA and Wooddens are
     BIT-IDENTICAL (traits are immutable after new_tree, so a shuffled identity would break this,
     and it shares no algebra with G3).
     MUST RETURN: 0 violations of N pairs.   FALSIFIED IF: > 0.

 G5  ADR-0125 identity gate, vanished LIVING stems, scored on HEIGHT not on count. A living stem
     that does not reappear next year must be a 5 m EMISSION-THRESHOLD flicker, not a lost
     individual.
     MUST RETURN: the vanished-living count as a fraction of pairable living stem-years, plus the
     share of those within 0.4 m of the 5 m writer cut. ADR 0125 measured 8 of 13 152 stem-years
     (0.061 %), ALL within 0.4 m of 5 m, at five biome cells.
     FALSIFIED IF: a material vanished population sits WELL ABOVE 5.4 m -- that would be an
     unrecorded kill channel, not threshold flicker.
     NOTE: a raw fraction above 0.061 % is NOT by itself a failure. 674 cells is a 135x larger and
     far more diverse population than ADR 0125's five cells.

 G6  Dead stems never reappear. Rows with isdead == 1 that appear again in Year+1.
     MUST RETURN: 0.   FALSIFIED IF: > 0.

 G7  Table B/C/D key uniqueness: (leg,seed,Cell,Patch,Year) for B, (Cell,leg,window,seed) for C,
     (Cell,leg,window) for D.   MUST RETURN: 0 duplicates each.

 G8  LAI reconstruction provenance. K_LIGHTEXT as IMPORTED must be
     {0:0.59, 1:0.45, 2:0.59, 3:0.59, 4:0.45, 5:0.59, 6:0.45}  (0.59 broadleaved / 0.45
     needleleaved).  MUST RETURN: exact match.
     FALSIFIED IF: it differs ==> the import drifted and every lai_stand here is wrong.

 G9  Float32-mean trap. For each Float32 env feature the window mean computed in Float64 vs
     natively in Float32 must DIFFER on a nonzero number of rows (~3.4e-7 relative), and the
     SHIPPED column must be the Float64 one.
     MUST RETURN: count of differing rows plus max |rel diff|, and Float64 used for the output.
     The only surprising outcome is them matching everywhere, which would mean the cast is moot.

G10  Cell coverage. Table C/D must cover the 67 420 orderA cells for the climatology, and Table C
     must report how many are TREE-BEARING in each window (expected O(54 020) per ADR 0106).
     MUST RETURN: the counts. No pass/fail -- it is the denominator every later claim needs.

FALSIFIER FOR THE ITEM AS A WHOLE
  P0 FAILS, and the campaign's per-stem items must be abandoned or redesigned, if G3, G4 or G6
  returns a nonzero violation count, or if G2/G7 finds a duplicated key. Any of those means the
  paired-stem basis does not exist. A stage that does not finish is NOT a failure of the item; it
  is a caveat, and it will be reported as one, table by table.

WHAT IS DELIBERATELY NOT DONE
  * No ssp126 leg. It exists (both seeds, completed 2026-08-18) but ONLY as raw 186 GB CSV with no
    parquet, so putting it on the same footing as the other two legs is a data-engineering job,
    not a prep step. Reported as a caveat, never silently omitted.
  * No daily flux table. The daily 186 GB dataset is single-seed historic-only: a different item.
  * No skill model, no null, no verdict. P0 is prep.

----------------------------------------------------------------------------------------------
AMENDMENT 1 (recorded here rather than silently applied -- the criterion was NOT retrofitted).
  The FIRST run of stage A used the individual key (Cell, Patch, ID), i.e. ADR 0125's key. It
  FAILED G3/G4/G6 on every leg (job 1845487: historic seed1 2/1900946 Age violations, 13 trait
  violations; ssp370 seed1 57/8333610, 168, 16 dead-reappears). The failure was NOT waved away and
  NOT re-thresholded: it was traced in the C source to `tree->index` being drawn from a PER-PFT
  counter (new_tree.c:85-86), so `Type` is part of the identity, and the gate was re-run on the
  corrected key -- 0/0/0 on 1 900 932 pairs. The gates' MUST-RETURN values are unchanged; the
  KEY they are computed on is corrected, and G11 below now measures the collision rate that the
  old key silently absorbed. A reader who wants the falsified version should read this paragraph
  as the record of it.

----------------------------------------------------------------------------------------------
AMENDMENT 3 (recorded, not retrofitted). Stage A's G5 FIRED ITS FALSIFIER on ONE of the four
legs. G5 pre-registered: "FALSIFIED IF a material vanished population sits WELL ABOVE 5.4 m --
that would be an unrecorded kill channel, not threshold flicker." On historic seed1/seed2 and
ssp370 seed1 the vanished-living stems top out at 5.62 / 5.41 / 5.78 m ==> pure threshold
flicker, gate PASSED. On **ssp370 seed2** 1 126 of 9 574 vanishers reach up to **31.5 m**.
Diagnosed, not waved away: 1 126 of 1 126 (100 %) sit in a patch-year in which EVERY living
pairable stem vanished at once, over just 50 patch-years, and those trace to TWO (leg,seed,Cell)
blocks -- ssp370 seed2 Cell 0 (25 patches, 1 327 stems, year 2071) and Cell 51200 (23 patches,
257 stems, year 2070). Cell 0 = lat -55.75 lon -68.25 (Tierra del Fuego) is present in the
ssp370 seed2 roster in **exactly one year of 81** and is absent from all three windows of Table C
in both seeds, while carrying a 31 m closed stand in that one year. A 31 m stand cannot appear and
vanish in one year, so this is a ROSTER DATA ARTIFACT (a mis-attributed / torn cell-year block in
the raw-CSV-to-parquet path), NOT a kill channel and NOT physics. Hence stage E, which makes
cell-year presence explicit for every cell instead of leaving it to be rediscovered.
  MUST RETURN from stage E: the count of (leg,seed,Cell) with an INTERIOR missing year, and the
  subset where the flanking years are well-populated (>= 10 living stems) -- those are the ones a
  paired measurement must drop.
----------------------------------------------------------------------------------------------

G12  Independent-construction check on the .clm read (added by amendment 2, which ADDS five
     forcing-derived window columns to Table D because the w20 env tables carry only 8 features
     and NONE of them is a temperature seasonality or a radiation). The historic window's
     gdd5 computed here from the DAILY .clm (sum of max(0, T-5) over 365 days) vs the w20 table's
     `eco_diag_gdd_5` (built by a different method, Thom monthly interpolation) over 67 420 cells.
     MUST RETURN: Pearson r >= 0.98 and a regression slope in [0.8, 1.25].
     FALSIFIED IF: r < 0.9 ==> the .clm dtype/scalar/calendar handling is wrong (the mixed
     v2-int16-scalar-0.1 / v3-float32 trap), and every forcing-derived column is void.
     The two are NOT expected to be equal -- only to be the same quantity.

G11  ID-collision census (added by amendment 1). Per leg/seed: rows whose (Cell,Patch,ID,Year) is
     duplicated, rows whose (Cell,Patch,Type,ID,Year) is duplicated, and how many pairs the
     Type-free key would have mis-joined.
     MUST RETURN: the counts. Expectation from the historic-seed1 probe: O(10) rows per leg/seed,
     i.e. O(1e-5) of rows -- small enough that ADR 0125's five-cell gate could not see it, large
     enough to put nonzero violations into every gate that pairs 1e6+ stems.
==============================================================================================
"""


def _say(msg: str) -> None:
    print(msg, flush=True)


def _dt(t: float) -> str:
    return f"{time.time() - t:.1f}s"


def _assert_schema(path: str) -> None:
    """G1 -- the roster carries the frozen 29-col `ind` schema, in order."""
    names = list(pl.read_parquet_schema(path).keys())
    if names != IND_29:
        raise SystemExit(f"FATAL G1: {path} schema != frozen 29-col ind schema\n  got {names}")


def _assert_unique(df: pl.DataFrame, keys: list[str], gate: str) -> int:
    """G2/G7 -- key-set uniqueness. Returns the duplicate count (0 = pass)."""
    dup = df.height - df.select(keys).n_unique()
    verdict = "PASS" if dup == 0 else "FAIL"
    _say(f"   {gate}: keys={keys} rows={df.height} duplicates={dup} -> {verdict}")
    if dup != 0:
        raise SystemExit(f"FATAL {gate}: {dup} duplicated keys on {keys}")
    return dup


# ---------------------------------------------------------------------------------------------
# STAGE A -- per-stem, year-paired
# ---------------------------------------------------------------------------------------------
def stage_a() -> str:
    out = f"{OUT}/prep_paired_stems.parquet"
    _say("\n### STAGE A -- prep_paired_stems.parquet (Cell % 100 == 0, tree stems, year-paired)")
    expect = {0: 0.59, 1: 0.45, 2: 0.59, 3: 0.59, 4: 0.45, 5: 0.59, 6: 0.45}
    if dict(K_LIGHTEXT) != expect:
        raise SystemExit(f"FATAL G8: imported K_LIGHTEXT={dict(K_LIGHTEXT)} != {expect}")
    _say(f"   G8 K_LIGHTEXT imported == {expect} -> PASS")
    _say(f"   TREE_TYPES imported = {tuple(TREE_TYPES)}")
    _say(f"   individual key = {IND_KEY} (amendment 1: `Type` is part of it -- ID is a PER-PFT "
         "counter, new_tree.c:85-86)")

    nxt = ["Year", "Age", "agb", "vegc", "Height", "SLA", "Wooddens"]
    parts: list[pl.DataFrame] = []
    gates: list[dict] = []
    for leg, (tmpl, y0, y1) in LEGS.items():
        for seed in SEEDS:
            path = tmpl.format(seed=seed)
            _assert_schema(path)
            t = time.time()
            df = (
                pl.scan_parquet(path)
                .filter(
                    (pl.col("Year") >= y0) & (pl.col("Year") <= y1)
                    & ((pl.col("Cell") % 100) == 0)
                    & pl.col("Type").is_in(TREE_TYPES)
                )
                .collect()  # NON-streaming on purpose (G2)
                .sort([*IND_KEY, "Year"])
            )
            _say(f"   {leg} seed{seed}: {df.height} tree stem-years, "
                 f"{df['Cell'].n_unique()} cells ({_dt(t)})")

            # ---- G11 ID-collision census + dup_key flag -------------------------------------
            dup_notype = df.height - df.select(["Cell", "Patch", "ID", "Year"]).n_unique()
            dupk = (
                df.group_by([*IND_KEY, "Year"]).agg(pl.len().alias("_n"))
                .filter(pl.col("_n") > 1)
                .select(IND_KEY).unique()
                .with_columns(pl.lit(1, dtype=pl.Int8).alias("dup_key"))
            )
            df = df.join(dupk, on=IND_KEY, how="left").with_columns(
                pl.col("dup_key").fill_null(0).cast(pl.Int8)
            )
            n_dup_rows = int((df["dup_key"] == 1).sum())
            _say(f"     G11 collisions: (Cell,Patch,ID,Year) duplicated rows={dup_notype}; "
                 f"with Type in the key -> {dupk.height} individual keys / {n_dup_rows} rows "
                 f"({100 * n_dup_rows / max(df.height, 1):.6f} %) flagged dup_key=1 and excluded "
                 "from pairing")

            df = df.with_columns(
                [pl.col(c).shift(-1).over(IND_KEY).alias(f"_n_{c}") for c in nxt]
            )
            # a dup_key row can NEVER be paired: its shift(-1) neighbour may be its own twin.
            pairable = (pl.col("Year") < y1) & (pl.col("dup_key") == 0)
            consec = pl.col("_n_Year") == (pl.col("Year") + 1)
            df = df.with_columns(
                pairable.alias("pairable"),
                pl.when(pairable).then(consec.fill_null(False).cast(pl.Int8))
                .otherwise(None).alias("survived"),
            )
            keep = pl.col("survived") == 1
            df = df.with_columns(
                [pl.when(keep).then(pl.col(f"_n_{c}")).otherwise(None).alias(f"next_{c}")
                 for c in ("agb", "vegc", "Height", "Age")]
            ).with_columns(
                (pl.col("next_agb") - pl.col("agb")).alias("d_agb"),
                (pl.col("next_vegc") - pl.col("vegc")).alias("d_vegc"),
                pl.lit(leg).alias("leg"),
                pl.lit(seed, dtype=pl.Int8).alias("seed"),
            )

            pr = df.filter(keep)
            npair = pr.height
            g3 = pr.filter((pl.col("_n_Age") - pl.col("Age")) != 1).height
            g4_sla = pr.filter(pl.col("_n_SLA") != pl.col("SLA")).height
            g4_wd = pr.filter(pl.col("_n_Wooddens") != pl.col("Wooddens")).height
            g6 = pr.filter(pl.col("isdead") == 1).height
            van = df.filter(
                (pl.col("isdead") == 0) & pl.col("pairable") & (pl.col("survived") == 0)
            )
            lp = df.filter((pl.col("isdead") == 0) & pl.col("pairable")).height
            h = van["Height"]
            nv = van.height
            g5 = {
                "vanished_living": nv,
                "live_pairable": lp,
                "frac": (nv / lp) if lp else float("nan"),
                "within_0p4m_of_5m": int((h < 5.4).sum()) if nv else 0,
                "h_min": float(h.min()) if nv else float("nan"),
                "h_med": float(h.median()) if nv else float("nan"),
                "h_p99": float(h.quantile(0.99)) if nv else float("nan"),
                "h_max": float(h.max()) if nv else float("nan"),
                "above_6m": int((h >= 6.0).sum()) if nv else 0,
            }
            _say(f"     G3 Age+1 : {g3} / {npair} pairs -> {'PASS' if g3 == 0 else 'FAIL'}")
            _say(f"     G4 SLA   : {g4_sla} -> {'PASS' if g4_sla == 0 else 'FAIL'} ; "
                 f"Wooddens: {g4_wd} -> {'PASS' if g4_wd == 0 else 'FAIL'}")
            _say(f"     G6 dead-reappears: {g6} -> {'PASS' if g6 == 0 else 'FAIL'}")
            _say(f"     G5 vanished-living {nv} of {lp} pairable living "
                 f"({100 * g5['frac']:.4f} %); <5.4 m {g5['within_0p4m_of_5m']} "
                 f"({100 * g5['within_0p4m_of_5m'] / max(nv, 1):.2f} % of them); "
                 f">=6 m {g5['above_6m']}; H med={g5['h_med']:.3f} "
                 f"p99={g5['h_p99']:.3f} max={g5['h_max']:.3f}")
            gates.append({"leg": leg, "seed": seed, "n_rows": df.height, "n_pairs": npair,
                          "g3_age": g3, "g4_sla": g4_sla, "g4_wd": g4_wd,
                          "g6_dead_reappear": g6,
                          "g11_dup_rows_no_type": dup_notype,
                          "g11_dup_keys": dupk.height, "g11_dup_rows": n_dup_rows, **g5})
            parts.append(df.drop([f"_n_{c}" for c in nxt]))

    tbl = pl.concat(parts, how="vertical")
    del parts
    order = ["leg", "seed"] + IND_29 + [
        "dup_key", "pairable", "survived", "next_agb", "next_vegc", "next_Height", "next_Age",
        "d_agb", "d_vegc",
    ]
    tbl = tbl.select(order)
    _assert_unique(tbl.filter(pl.col("dup_key") == 0),
                   ["leg", "seed", *IND_KEY, "Year"], "G2")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    gt = pl.DataFrame(gates)
    gt.write_csv(f"{OUT}/prep_paired_stems_gates.csv")
    _say(f"   WROTE {out}  rows={tbl.height} cols={tbl.width} "
         f"({os.path.getsize(out) / 1e9:.2f} GB)")
    _say(f"   WROTE {OUT}/prep_paired_stems_gates.csv (per leg/seed gate results)")
    _say(f"   columns: {tbl.columns}")
    lpt = max(int(gt["live_pairable"].sum()), 1)
    _say(f"   GATE TOTALS: pairs={gt['n_pairs'].sum()} G3={gt['g3_age'].sum()} "
         f"G4_SLA={gt['g4_sla'].sum()} G4_WD={gt['g4_wd'].sum()} "
         f"G6={gt['g6_dead_reappear'].sum()} "
         f"vanished_living={gt['vanished_living'].sum()}/{gt['live_pairable'].sum()} "
         f"({100 * gt['vanished_living'].sum() / lpt:.4f} %)")
    _say(f"   G11 TOTALS: rows a Type-free key would collide on = "
         f"{gt['g11_dup_rows_no_type'].sum()}; genuinely duplicated individual keys = "
         f"{gt['g11_dup_keys'].sum()} ({gt['g11_dup_rows'].sum()} rows, dup_key=1)")
    return out


# ---------------------------------------------------------------------------------------------
# STAGE B -- per (leg, seed, Cell, Patch, Year) stand summary
# ---------------------------------------------------------------------------------------------
def stage_b() -> str:
    src = f"{OUT}/prep_paired_stems.parquet"
    out = f"{OUT}/prep_patch_year_stand.parquet"
    _say("\n### STAGE B -- prep_patch_year_stand.parquet (from Table A's per-stem rows)")
    if not os.path.exists(src):
        raise SystemExit(f"FATAL: stage b needs {src}; run stage a first")
    keys = ["leg", "seed", "Cell", "Patch", "Year"]
    live = pl.col("isdead") == 0
    t = time.time()
    df = (
        pl.scan_parquet(src)
        .with_columns(patch_stand_lai_expr().alias("_stem_lai"))
        .group_by(keys)
        .agg(
            # population counts, both bases
            pl.len().alias("n_stems_all"),
            live.sum().alias("n_stems"),
            (pl.col("isdead") == 1).sum().alias("n_dead"),
            # LIVING stand state (build_slow_runtime_table.py:539 convention)
            pl.col("agb").filter(live).sum().alias("agb_sum"),
            pl.col("vegc").filter(live).sum().alias("vegc_sum"),
            pl.col("npp").filter(live).sum().alias("npp_sum"),
            pl.col("transp").filter(live).sum().alias("transp_sum"),
            pl.col("fpc_ind").filter(live).sum().alias("fpc_sum"),
            (pl.col("Height") * pl.col("fpc_ind")).filter(live).sum().alias("_hfpc"),
            pl.col("Height").filter(live).mean().alias("h_mean_plain"),
            pl.col("Height").filter(live).max().alias("h_max"),
            pl.col("Height").filter(live).std().alias("h_sd"),
            (pl.col("Age") - 1).filter(live).mean().alias("age_mean"),
            (pl.col("Age") - 1).filter(live).max().alias("age_max"),
            pl.col("_stem_lai").filter(live).sum().alias("lai_stand"),
            pl.col("_stem_lai").sum().alias("lai_stand_all"),
            # trait distribution over LIVING stems (nind constant => mean == nind-weighted mean)
            *[pl.col(a).filter(live).mean().alias(f"{a}_mean") for a in TRAIT_AXES],
            *[pl.col(a).filter(live).median().alias(f"{a}_median") for a in TRAIT_AXES],
            pl.col("Longevity").filter(live).mean().alias("Longevity_mean"),
            pl.col("Longevity").filter(live).median().alias("Longevity_median"),
            # per-PFT living stem counts
            *[(live & (pl.col("Type") == p)).sum().alias(f"n_pft{p}") for p in range(7)],
            # demography carried up so a stand-level label needs no re-pairing.
            # DENOMINATOR NOTE: n_survived_live counts only stems with survived == 1, and
            # `survived` is NULL for a final-year row and for a dup_key row -- so the honest
            # survival fraction is n_survived_live / n_pairable_live, never / n_stems.
            pl.col("survived").filter(live).sum().alias("n_survived_live"),
            (live & pl.col("survived").is_not_null()).sum().alias("n_pairable_live"),
            (pl.col("dup_key") == 1).sum().alias("n_dup_key"),
            pl.col("d_agb").sum().alias("d_agb_sum"),
        )
        .with_columns(
            (pl.col("_hfpc") / pl.max_horizontal(pl.col("fpc_sum"), pl.lit(1e-12))).alias("h_mean"),
            pl.min_horizontal(pl.col("fpc_sum"), pl.lit(1.0)).alias("fpc"),
        )
        .drop("_hfpc")
        .sort(keys)
        .collect()  # NON-streaming (G7)
    )
    _say(f"   built {df.height} (leg,seed,Cell,Patch,Year) groups ({_dt(t)})")
    _assert_unique(df, keys, "G7-B")
    df.write_parquet(out, compression="zstd", statistics=True)
    _say(f"   WROTE {out}  rows={df.height} cols={df.width} "
         f"({os.path.getsize(out) / 1e6:.1f} MB)")
    _say(f"   columns: {df.columns}")
    _say("   NOTE h_sd is polars std (ddof=1) => NULL where n_stems < 2. h_mean is the "
         "fpc-weighted mean (the repo convention); h_mean_plain is the unweighted one.")
    return out


# ---------------------------------------------------------------------------------------------
# STAGE C -- per-cell 20-year window forest state, ALL cells
# ---------------------------------------------------------------------------------------------
def stage_c() -> str:
    out = f"{OUT}/prep_cell_window_state.parquet"
    _say("\n### STAGE C -- prep_cell_window_state.parquet (ALL cells, 3 windows, 2 seeds)")
    npatch = pl.read_parquet(f"{TBL}/cell_npatch.parquet").with_columns(
        pl.col("n_patches").cast(pl.Int64)
    )
    _say(f"   cell_npatch.parquet: {npatch.height} cells, n_patches "
         f"min={npatch['n_patches'].min()} max={npatch['n_patches'].max()}")
    live = pl.col("Type").is_in(TREE_TYPES) & (pl.col("isdead") == 0)
    rows: list[pl.DataFrame] = []
    # ORDER MATTERS: the acceptance criterion's response is historic -> ssp370 2080-2099, so those
    # two windows are built FIRST. If the job dies, the mid-century window is what is missing.
    order = [w for w in WINDOWS if w[1] != "ssp370_2020_2039"]
    order += [w for w in WINDOWS if w[1] == "ssp370_2020_2039"]
    for leg, wlab, y0, y1 in order:
        tmpl = LEGS[leg][0]
        nyears = y1 - y0 + 1
        for seed in SEEDS:
            path = tmpl.format(seed=seed)
            _assert_schema(path)
            yfilt = (pl.col("Year") >= y0) & (pl.col("Year") <= y1)
            t = time.time()
            p1 = (
                pl.scan_parquet(path)
                .filter(yfilt & live)
                .select(["Cell", "Patch", "Year", "Type", "agb", "LAI", "fpc_ind"])
                .with_columns(patch_stand_lai_expr().alias("_stem_lai"))
                .group_by(["Cell", "Patch", "Year"])
                .agg(pl.len().alias("n"), pl.col("agb").sum().alias("agb"),
                     pl.col("_stem_lai").sum().alias("lai"))
                .group_by("Cell")
                .agg(pl.col("n").sum().alias("_n_sum"),
                     pl.col("agb").sum().alias("_agb_sum"),
                     pl.col("lai").sum().alias("_lai_sum"),
                     pl.len().alias("n_patchyears_present"),
                     pl.col("Patch").max().alias("_patch_max_obs"))
                .collect()
            )
            _say(f"   {wlab} seed{seed} pass1: {p1.height} tree-bearing cells ({_dt(t)})")
            t = time.time()
            p2 = (
                pl.scan_parquet(path)
                .filter(yfilt & live)
                .select(["Cell", *TRAIT_AXES])
                .group_by("Cell")
                .agg(pl.len().alias("n_stem_years"),
                     *[pl.col(a).median().alias(f"{a}_median") for a in TRAIT_AXES],
                     *[pl.col(a).mean().alias(f"{a}_mean") for a in TRAIT_AXES])
                .collect()
            )
            _say(f"   {wlab} seed{seed} pass2: {p2.height} cells, "
                 f"{p2['n_stem_years'].sum()} living tree stem-years ({_dt(t)})")
            if p1.height != p2.height:
                raise SystemExit(
                    f"FATAL: pass1/pass2 cell sets differ ({p1.height} vs {p2.height})"
                )
            d = (
                p1.join(p2, on="Cell", how="inner", validate="1:1")
                .join(npatch, on="Cell", how="left", validate="1:1")
                .with_columns(
                    pl.lit(leg).alias("leg"), pl.lit(wlab).alias("window"),
                    pl.lit(seed, dtype=pl.Int8).alias("seed"),
                    pl.lit(y0, dtype=pl.Int32).alias("y0"),
                    pl.lit(y1, dtype=pl.Int32).alias("y1"),
                    pl.lit(nyears, dtype=pl.Int32).alias("n_years"),
                )
                .with_columns(
                    # cell_npatch.parquet is NOT authoritative (measured by
                    # extract_resilience_reference.py:170: some cells are absent from it and some
                    # carry an observed Patch id at or above its n_patches). So the DENOMINATOR is
                    # the elementwise max of the two -- a patch that emitted a row certainly
                    # exists, and a patch the table knows about that never held a >5 m tree also
                    # exists (a genuine all-zero series). Both columns are kept so the
                    # disagreement is visible, never silently absorbed.
                    (pl.col("_patch_max_obs") + 1).alias("n_patches_obs"),
                    pl.max_horizontal(
                        pl.col("n_patches").fill_null(0), pl.col("_patch_max_obs") + 1
                    ).alias("n_patches_eff"),
                )
                .with_columns(
                    # PRIMARY basis: denominator = n_patches_eff * n_years, so a patch-year with
                    # ZERO living >5 m trees counts as a zero instead of vanishing (no rows).
                    (pl.col("_n_sum") / (pl.col("n_patches_eff") * pl.col("n_years")))
                    .alias("stems_per_patch"),
                    (pl.col("_agb_sum") / (pl.col("n_patches_eff") * pl.col("n_years")))
                    .alias("agb_per_patch"),
                    (pl.col("_lai_sum") / (pl.col("n_patches_eff") * pl.col("n_years")))
                    .alias("lai_stand_mean"),
                    # SECONDARY basis: denominator = only the patch-years that HAVE a stem.
                    (pl.col("_n_sum") / pl.col("n_patchyears_present"))
                    .alias("stems_per_occupied_patchyear"),
                    (pl.col("_agb_sum") / pl.col("n_patchyears_present"))
                    .alias("agb_per_occupied_patchyear"),
                    (pl.col("_lai_sum") / pl.col("n_patchyears_present"))
                    .alias("lai_stand_mean_occupied"),
                )
                .drop(["_n_sum", "_agb_sum", "_lai_sum", "_patch_max_obs"])
            )
            rows.append(d)
    tbl = pl.concat(rows, how="vertical").sort(["Cell", "leg", "window", "seed"])
    keys = ["Cell", "leg", "window", "seed"]
    front = keys + ["y0", "y1", "n_years", "n_patches", "n_patches_obs", "n_patches_eff",
                    "n_patchyears_present", "n_stem_years",
                    "stems_per_patch", "agb_per_patch", "lai_stand_mean",
                    "stems_per_occupied_patchyear", "agb_per_occupied_patchyear",
                    "lai_stand_mean_occupied"]
    tbl = tbl.select(front + [c for c in tbl.columns if c not in front])
    _assert_unique(tbl, keys, "G7-C")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    _say(f"   WROTE {out}  rows={tbl.height} cols={tbl.width} "
         f"({os.path.getsize(out) / 1e6:.1f} MB)")
    _say(f"   columns: {tbl.columns}")
    _say("   G10 tree-bearing cell counts per (window, seed):")
    cov = tbl.group_by(["window", "seed"]).agg(pl.len().alias("n_cells")).sort(["window", "seed"])
    for r in cov.iter_rows(named=True):
        _say(f"     {r['window']} seed{r['seed']}: {r['n_cells']} tree-bearing cells of 67420")
    nnull = tbl["n_patches"].null_count()
    nover = tbl.filter(pl.col("n_patches_obs") > pl.col("n_patches").fill_null(0)).height
    _say(f"   cell_npatch disagreement: {nnull} rows have NO n_patches entry, {nover} rows have an "
         f"observed Patch id at/above it -> the primary denominator is n_patches_eff = "
         f"max(n_patches, observed max Patch + 1); n_patches / n_patches_obs are both kept")
    return out


# ---------------------------------------------------------------------------------------------
# STAGE D -- per-cell 20-year climatology, ALL cells
# ---------------------------------------------------------------------------------------------
def _latlon() -> pl.DataFrame:
    """orderA cell -> (lat, lon) plus the unit-sphere triple a geographic-address null needs."""
    path = f"{TBL}/cell_latlon.txt"
    cells, lats, lons = [], [], []
    with open(path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.split()
            if len(p) < 5:
                continue
            cells.append(int(p[0]))
            lats.append(float(p[3]))
            lons.append(float(p[4]))
    rlat = np.radians(np.asarray(lats))
    rlon = np.radians(np.asarray(lons))
    return pl.DataFrame({
        "Cell": np.asarray(cells, dtype=np.int64),
        "lat": np.asarray(lats), "lon": np.asarray(lons),
        "geo_x": np.cos(rlat) * np.cos(rlon),
        "geo_y": np.cos(rlat) * np.sin(rlon),
        "geo_z": np.sin(rlat),
    })


def _clm_window(path: str, y0: int, y1: int, mode: str) -> np.ndarray:
    """Window mean of the ANNUAL statistic of a .clm forcing variable, per orderA cell.

    mode 'mean' -> window mean of the annual MEAN of the 365 daily values (temperature, degC)
    mode 'sum'  -> window mean of the annual TOTAL of the 365 daily values (precip, mm/yr)

    Header-driven via the committed reader, so the MIXED v2-int16-scalar-0.1 / v3-float32 forcing
    set is read correctly (CLAUDE.md: one hardcoded dtype reads four of the five ssp files wrong).
    """
    mm, fy, ncell, nbands, scalar = open_clm(path)
    if nbands != 365:
        raise SystemExit(f"FATAL: {path} nbands={nbands} != 365")
    i0, i1 = y0 - fy, y1 - fy
    if i0 < 0 or i1 >= mm.shape[0]:
        raise SystemExit(f"FATAL: {path} covers {fy}..{fy + mm.shape[0] - 1}, need {y0}..{y1}")
    acc = np.zeros(ncell, dtype=np.float64)
    for i in range(i0, i1 + 1):
        yr = np.asarray(mm[i], dtype=np.float64) * scalar
        acc += yr.mean(axis=1) if mode == "mean" else yr.sum(axis=1)
    return acc / (i1 - i0 + 1)


# noleap-365 month boundaries -- the calendar every .clm in this run uses (365 bands, no leap day).
_MONTH_EDGES = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def _clm_tas_stats(path: str, y0: int, y1: int) -> dict[str, np.ndarray]:
    """Window means of five ANNUAL temperature statistics, per orderA cell, from the daily .clm.

    These exist so Table D has a temperature SEASONALITY and a growing-season length on BOTH legs:
    the w20 env tables carry 8 features and none of them is one. All five are computed by the SAME
    code on both legs, which is the property the campaign's response questions need.
    """
    mm, fy, ncell, nbands, scalar = open_clm(path)
    if nbands != 365:
        raise SystemExit(f"FATAL: {path} nbands={nbands} != 365")
    i0, i1 = y0 - fy, y1 - fy
    if i0 < 0 or i1 >= mm.shape[0]:
        raise SystemExit(f"FATAL: {path} covers {fy}..{fy + mm.shape[0] - 1}, need {y0}..{y1}")
    n = i1 - i0 + 1
    out = {k: np.zeros(ncell, dtype=np.float64)
           for k in ("tas_cold_month_clm", "tas_warm_month_clm", "gdd5_clm",
                     "frostdays_clm", "tas_seasonality_clm")}
    for i in range(i0, i1 + 1):
        yr = np.asarray(mm[i], dtype=np.float64) * scalar
        mon = np.stack(
            [yr[:, _MONTH_EDGES[m]:_MONTH_EDGES[m + 1]].mean(axis=1) for m in range(12)], axis=1
        )
        out["tas_cold_month_clm"] += mon.min(axis=1)
        out["tas_warm_month_clm"] += mon.max(axis=1)
        out["tas_seasonality_clm"] += mon.max(axis=1) - mon.min(axis=1)
        out["gdd5_clm"] += np.maximum(yr - 5.0, 0.0).sum(axis=1)
        out["frostdays_clm"] += (yr < 0.0).sum(axis=1)
    return {k: v / n for k, v in out.items()}


def stage_d() -> str:
    out = f"{OUT}/prep_cell_window_clim.parquet"
    _say("\n### STAGE D -- prep_cell_window_clim.parquet (ALL cells, 3 windows)")
    geo = _latlon()
    _say(f"   cell_latlon.txt: {geo.height} cells, lat {geo['lat'].min()}..{geo['lat'].max()}, "
         f"lon {geo['lon'].min()}..{geo['lon'].max()}")
    soil = (
        pl.scan_parquet(f"{TBL}/cell_year_feats.parquet")
        .filter(pl.col("Year") == 2000)
        .select(["Cell", "soil_code", "soil_depth"])
        .collect()
    )
    _say(f"   soil tail from cell_year_feats.parquet@2000: {soil.height} cells. soil_depth is "
         "carried for completeness but the C DISCARDS it (newgrid.c:282 sets every cell to 20 m)")

    g9: list[dict] = []
    rows: list[pl.DataFrame] = []
    for leg, wlab, y0, y1 in WINDOWS:
        env = pl.read_parquet(ENV_W20[leg]).filter(
            (pl.col("Year") >= y0) & (pl.col("Year") <= y1)
        )
        got = sorted(env["Year"].unique().to_list())
        if got != list(range(y0, y1 + 1)):
            raise SystemExit(f"FATAL: {ENV_W20[leg]} misses years for {wlab}: {got}")
        # the Float64 (CORRECT) window mean
        f64 = (
            env.with_columns([pl.col(c).cast(pl.Float64) for c in ENV_FEATS])
            .group_by("Cell")
            .agg([pl.col(c).mean().alias(f"{c}_wmean") for c in ENV_FEATS])
        )
        # the NATIVE-Float32 window mean, for G9 only -- never shipped
        f32 = env.group_by("Cell").agg(
            [pl.col(c).mean().alias(f"{c}_f32") for c in ENV_F32]
        )
        cmp_ = f64.join(f32, on="Cell", how="inner", validate="1:1")
        for c in ENV_F32:
            a = cmp_[f"{c}_wmean"].to_numpy()
            b = cmp_[f"{c}_f32"].cast(pl.Float64).to_numpy()
            dd = np.abs(a - b)
            rel = dd / np.maximum(np.abs(a), 1e-300)
            g9.append({"window": wlab, "feature": c, "n_cells": len(a),
                       "n_differ": int((dd != 0).sum()), "max_abs": float(dd.max()),
                       "max_rel": float(rel.max())})
        # the window's END-YEAR value: this IS the trailing-20-yr climatology OF the window
        endyr = (
            env.filter(pl.col("Year") == y1)
            .with_columns([pl.col(c).cast(pl.Float64) for c in ENV_FEATS])
            .select(["Cell"] + [pl.col(c).alias(f"{c}_endyr") for c in ENV_FEATS])
        )
        t = time.time()
        tas = _clm_window(CLM[leg], y0, y1, "mean")
        pr = _clm_window(CLM_EXTRA[leg]["pr"], y0, y1, "sum")
        rsds = _clm_window(CLM_EXTRA[leg]["rsds"], y0, y1, "mean")
        huss = _clm_window(CLM_EXTRA[leg]["huss"], y0, y1, "mean")
        tstat = _clm_tas_stats(CLM[leg], y0, y1)
        _say(f"   {wlab}: .clm window stats read ({_dt(t)}) tas mean={np.nanmean(tas):.3f} degC, "
             f"pr mean={np.nanmean(pr):.1f} mm/yr, rsds mean={np.nanmean(rsds):.2f}, "
             f"gdd5 mean={np.nanmean(tstat['gdd5_clm']):.1f}, "
             f"cold-month mean={np.nanmean(tstat['tas_cold_month_clm']):.2f} degC")
        raw = pl.DataFrame({"Cell": np.arange(len(tas), dtype=np.int64),
                            "tas_wmean_degC": tas, "pr_wmean_mm_yr": pr,
                            "rsds_wmean": rsds, "huss_wmean": huss, **tstat})
        if wlab == "hist_2000_2019":  # G12: independent construction of gdd5
            ref = f64.join(raw, on="Cell", how="inner", validate="1:1")
            a = ref["eco_diag_gdd_5_wmean"].to_numpy()
            b = ref["gdd5_clm"].to_numpy()
            ok = np.isfinite(a) & np.isfinite(b)
            r = float(np.corrcoef(a[ok], b[ok])[0, 1])
            slope = float(np.polyfit(a[ok], b[ok], 1)[0])
            verdict = "PASS" if (r >= 0.98 and 0.8 <= slope <= 1.25) else "FAIL"
            _say(f"   G12 gdd5 .clm-daily vs w20-table (n={int(ok.sum())}): r={r:.6f} "
                 f"slope={slope:.4f} -> {verdict}  (two DIFFERENT constructions of one quantity; "
                 "equality is not expected, agreement of the quantity is)")
            if verdict == "FAIL":
                raise SystemExit(f"FATAL G12: r={r} slope={slope} -- the .clm read is not trusted")
        d = (
            f64.join(endyr, on="Cell", how="inner", validate="1:1")
            .join(raw, on="Cell", how="inner", validate="1:1")
            .join(geo, on="Cell", how="left", validate="1:1")
            .join(soil, on="Cell", how="left", validate="1:1")
            .with_columns(pl.lit(leg).alias("leg"), pl.lit(wlab).alias("window"),
                          pl.lit(y0, dtype=pl.Int32).alias("y0"),
                          pl.lit(y1, dtype=pl.Int32).alias("y1"))
        )
        rows.append(d)
    tbl = pl.concat(rows, how="vertical").sort(["Cell", "leg", "window"])
    keys = ["Cell", "leg", "window"]
    front = keys + ["y0", "y1", "lat", "lon", "geo_x", "geo_y", "geo_z", "soil_code",
                    "soil_depth", "tas_wmean_degC", "pr_wmean_mm_yr", "rsds_wmean", "huss_wmean",
                    "tas_cold_month_clm", "tas_warm_month_clm", "tas_seasonality_clm",
                    "gdd5_clm", "frostdays_clm"]
    tbl = tbl.select(front + [c for c in tbl.columns if c not in front])
    _assert_unique(tbl, keys, "G7-D")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    g9t = pl.DataFrame(g9)
    g9t.write_csv(f"{OUT}/prep_cell_window_clim_g9_float32.csv")
    _say(f"   WROTE {out}  rows={tbl.height} cols={tbl.width} "
         f"({os.path.getsize(out) / 1e6:.1f} MB)")
    _say(f"   columns: {tbl.columns}")
    _say("   G9 Float32-vs-Float64 window mean (Float64 is what is SHIPPED):")
    for r in g9t.iter_rows(named=True):
        _say(f"     {r['window']:18s} {r['feature']:22s} differ "
             f"{r['n_differ']}/{r['n_cells']} max_abs={r['max_abs']:.3e} "
             f"max_rel={r['max_rel']:.3e}")
    return out


# ---------------------------------------------------------------------------------------------
# STAGE E -- per (leg, seed, Cell, Year) presence + stem count, ALL cells, ALL years
# ---------------------------------------------------------------------------------------------
def stage_e() -> str:
    out = f"{OUT}/prep_cell_year_census.parquet"
    _say("\n### STAGE E -- prep_cell_year_census.parquet (ALL cells, ALL years, both legs+seeds)")
    _say("   why: a stem can 'vanish' because its whole cell-year block is ABSENT, which a paired "
         "measurement scores as a death (amendment 3).")
    tree = pl.col("Type").is_in(TREE_TYPES)
    rows: list[pl.DataFrame] = []
    for leg, (tmpl, y0, y1) in LEGS.items():
        for seed in SEEDS:
            path = tmpl.format(seed=seed)
            _assert_schema(path)
            t = time.time()
            # ONE YEAR AT A TIME and NON-streaming: the rosters are sorted by (Year, Cell) so a
            # year predicate prunes row groups, and this never hands a global group_by to the
            # streaming engine (whose emitted KEY SET is not deterministic at this scale).
            per: list[pl.DataFrame] = []
            for yr in range(y0, y1 + 1):
                per.append(
                    pl.scan_parquet(path)
                    .filter((pl.col("Year") == yr) & tree)
                    .select(["Cell", "Patch", "Type", "isdead", "agb", "Height"])
                    .group_by("Cell")
                    .agg(
                        pl.len().alias("n_stems_all"),
                        (pl.col("isdead") == 0).sum().alias("n_stems"),
                        pl.col("Patch").n_unique().alias("n_patches_obs"),
                        pl.col("agb").filter(pl.col("isdead") == 0).sum().alias("agb_sum"),
                        pl.col("Height").filter(pl.col("isdead") == 0).max().alias("h_max"),
                    )
                    .with_columns(pl.lit(yr, dtype=pl.Int32).alias("Year"))
                    .collect()
                )
            d = pl.concat(per, how="vertical").with_columns(
                pl.lit(leg).alias("leg"), pl.lit(seed, dtype=pl.Int8).alias("seed")
            )
            _say(f"   {leg} seed{seed}: {d.height} (Cell,Year) rows, "
                 f"{d['Cell'].n_unique()} distinct cells ({_dt(t)})")
            rows.append(d)
            del per
    tbl = pl.concat(rows, how="vertical").select(
        ["leg", "seed", "Cell", "Year", "n_stems", "n_stems_all", "n_patches_obs",
         "agb_sum", "h_max"]
    ).sort(["leg", "seed", "Cell", "Year"])
    keys = ["leg", "seed", "Cell", "Year"]
    _assert_unique(tbl, keys, "G7-E")

    # interior missing years, and the subset whose flanking years are well-populated
    span = tbl.group_by(["leg", "seed", "Cell"]).agg(
        pl.col("Year").min().alias("y_first"), pl.col("Year").max().alias("y_last"),
        pl.len().alias("n_years_present"), pl.col("n_stems").median().alias("n_stems_med"),
    ).with_columns(
        (pl.col("y_last") - pl.col("y_first") + 1 - pl.col("n_years_present")).alias("gap_years")
    )
    gap = span.filter(pl.col("gap_years") > 0)
    gap_pop = gap.filter(pl.col("n_stems_med") >= 10)
    _say(f"   INTERIOR-GAP CENSUS: {gap.height} (leg,seed,Cell) blocks have at least one missing "
         f"year inside their own span; {gap_pop.height} of those have a median living stem count "
         ">= 10 (i.e. a real gap, not >5 m threshold flicker in a sparse cell)")
    _say("   worst 10 by gap_years among the well-populated ones:")
    for r in gap_pop.sort("gap_years", descending=True).head(10).iter_rows(named=True):
        _say(f"     {r['leg']} seed{r['seed']} Cell {r['Cell']}: "
             f"{r['n_years_present']} yr present over {r['y_first']}..{r['y_last']}, "
             f"gap_years={r['gap_years']}, median living stems={r['n_stems_med']}")
    # the amendment-3 blocks: a single-year presence carrying a closed stand
    one = span.filter((pl.col("n_years_present") <= 2) & (pl.col("n_stems_med") >= 50))
    _say(f"   AMENDMENT-3 SIGNATURE (<=2 years present but a >=50-stem stand): {one.height} blocks")
    for r in one.iter_rows(named=True):
        _say(f"     {r['leg']} seed{r['seed']} Cell {r['Cell']}: years present "
             f"{r['n_years_present']} ({r['y_first']}..{r['y_last']}), "
             f"median living stems={r['n_stems_med']} -> ARTIFACT, exclude")
    span.write_parquet(f"{OUT}/prep_cell_year_span.parquet", compression="zstd")
    tbl.write_parquet(out, compression="zstd", statistics=True)
    _say(f"   WROTE {out}  rows={tbl.height} cols={tbl.width} "
         f"({os.path.getsize(out) / 1e6:.1f} MB)")
    _say(f"   WROTE {OUT}/prep_cell_year_span.parquet  rows={span.height} "
         "(per (leg,seed,Cell): y_first, y_last, n_years_present, gap_years, n_stems_med)")
    _say(f"   columns: {tbl.columns}")
    return out


def main() -> int:
    print(PREREG, flush=True)
    stage = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    os.makedirs(OUT, exist_ok=True)
    _say(f"polars {pl.__version__} | numpy {np.__version__}")
    _say(f"stage={stage}  OUT={OUT}")
    fns = {"a": stage_a, "b": stage_b, "c": stage_c, "d": stage_d, "e": stage_e}
    todo = list(fns) if stage == "all" else [stage]
    for s in todo:
        if s not in fns:
            raise SystemExit(f"FATAL: unknown stage {s!r}; use one of {list(fns)} or 'all'")
        t = time.time()
        p = fns[s]()
        _say(f"### STAGE {s.upper()} DONE in {_dt(t)} -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
