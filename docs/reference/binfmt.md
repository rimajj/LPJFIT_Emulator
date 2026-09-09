# LPJmL-FIT's binary formats — the restart file and `.clm`

Transcribed from the model's own C sources at `config/paths.yaml: lpjml.lpjroot` (version 5.6.004,
built with `LPJFLAGS = -DUSE_RAND48 -DUSE_MPI -DSAFE -DWITH_FPE -DUSE_NETCDF -DUSE_UDUNITS
-DUSE_JSON -DPERMUTE -DUSE_SOILDEPTH_INFIL -DUSE_TIMING`). Every field names the function it comes
from, so this file can be re-derived after a rebuild instead of re-guessed.

**A spec is not proven by inspection.** `tests/test_restart_roundtrip.py` and
`tests/test_clm_roundtrip.py` prove it by writing real files back byte-identically — 100 restart
cells spanning 360 KB to 3.5 MB, and two whole `.clm` files. Verified 2026-09-08.

---

## 1. The restart file

`src/vegemu/binfmt/restart.py`. Written by `fwriterestart.c` → `fwritecell.c`, read back by
`openrestart.c` → `freadcell.c`.

### 1.1 Framing

| bytes | what | source |
|---|---|---|
| 10 | `"LPJRESTART"`, no terminator | `fwriteheader.c` |
| 4 | `int32` version = **33** | `header.h: RESTART_VERSION` |
| 40 | `Header3`: 6×`int32`, 3×`float32`, `int32` datatype | `header.h` |
| 30 | `Restartheader` — **disk order ≠ struct order** | `freadrestartheader.c` |
| 8·ncell | `int64[ncell]` **absolute** byte offsets | `fwriterestart.c` |
| … | the cell records, in cell order | `fwritecell.c` |

So `index[0] == 84 + 8·ncell`, and record *i* is `index[i] .. index[i+1]` (the last one to
end-of-file). **Always seek; never scan** — the global file is 119 GiB and the offset table is
exactly what it is for.

`Header3` fields: `order, firstyear, nyear, firstcell, ncell, nbands` (`int32`), then
`cellsize_lon, scalar, cellsize_lat` (`float32`), then `datatype` (`int32`). `nbands = npft + ncft`.

**The `Restartheader` trap.** The struct declares
`(landuse, river_routing, individual, sdate_option, crop_option, double_harvest, seed)` but the disk
order is

```
int32 landuse, river_routing, sdate_option, crop_option, double_harvest
uint16 seed[3]                  # USE_RAND48 -> erand48 state, so 3 x short, not 3 x int
int32 individual                # MOVED TO THE END
```

= 30 bytes (`restartsize()` = `6*sizeof(int)+sizeof(Seed)`). Decoding in declaration order reads
the gap-dynamics flag as a sowing-date option and produces a plausible wrong answer, not an error.

### 1.2 Scalar types

`Real` = `double` (8 B, and `datatype` must read **4**). `Bool`/`int` = `int32`. `Byte` =
`uint8`. `Stocks` = `{Real carbon, Real nitrogen}` = 16 B. `Poolpar` = `{Real fast, Real slow}` =
16 B. `Pool` = 2×`Stocks` = 32 B. `Trait` = `{Stocks leaf, Stocks wood[4]}` = 80 B. Little-endian;
a byte-swapped file is detected exactly as the C does it, by the version word's low byte being zero.

**The `.clm` v3 datatype codes are 0-based**: `0=byte 1=short 2=int 3=float 4=double`. An
off-by-one there once read temperatures as ~5.9 × 10⁸ °C.

### 1.3 Compile-time widths

`NSOILLAYER` 23, `LASTLAYER` 22, `NHEATGRIDP` 23 (`GPLHEAT` 1), `NFUELCLASS` 4, `NTILLLAYER` 1,
`NDAYS` 31, `NMONTH` 12, `NSEED` 3. `forrootsoillayer(l)` runs `0 .. LASTLAYER-1`, i.e. **22**
layers, one fewer than `NSOILLAYER` — an easy off-by-one.

Existing ground truth: `npft` = 10 (7 trees + 3 grasses), `ncft` = 12, `ntotpft` = 22, `npatch` =
25, `river_routing` false, `landuse` "no", `sdate_option` 0, `crop_option` false, `individual` true.

### 1.4 The cell record — `fwritecell.c`, in order

```
uint8   skip
uint16  seed[3]
        # river_routing is FALSE in every existing leg; if it were true, the discharge block,
        # the queue and the dam flag would sit here
Real    mevap
if not skip:
    Stocks  estab_storage_tree[2]      # 32 B
    Stocks  estab_storage_grass[2]     # 32 B
    Real    nesterov_accum, nesterov_max ; int32 nesterov_day     # fwriteignition.c
    Real    excess_water, waterdeficit
    Real    gdd[npft]                  # NATURAL PFTs only, not ntotpft
    int32   nstand ; nstand x STAND
    Real    cropfrac_rf, cropfrac_ir
    CLIMBUF
    int32   cropdates[ncft][8]         # cropdates.h: 6 scalars + fallow[2]
    int32   sdate_fixed[2*ncft]        # only if sdate_option > 0
    Real    crop_phu_fixed[2*ncft]     # only if crop_option (PRESCRIBED_CROP_PHU)
    int32   sowing_month[2*ncft]
    int32   gs[2*ncft]
        # landfrac / product / fertilizer_nr only when landuse is enabled -- no existing leg is
        # ischeckpoint output only in a checkpoint file
    int32   nsapling ; nsapling x SAPLING     # 88 B each: 10 Real + int32 year + int32 id
```

A `skip` cell is exactly `1 + 6 + 8 = 15` bytes. 10,434 of 67,420 cells are vegetation-free
(360,183 B, an empty PFT list in every patch) — a different branch from the densest cell's 2,551
stems, which is why the round-trip samples by SIZE and not at random.

**STAND** — `fwritestand.c`:
```
uint8  landusetype        # 0 = NATURAL; fwrite_natural.c writes NOTHING type-specific
int32  npatch
npatch x { SOIL ; PFTLIST ; Real frac_g[NSOILLAYER] }
Real   frac
```

**SOIL** — `fwritesoil.c`:
```
for l in 0..LASTLAYER-1:  Pool pool[l] ; Poolpar c_shift[l][ntotpft]
LITTER
Real NO3[LASTLAYER], NH4[LASTLAYER]
Real wsat,wpwp,wfc,whc,whcs,wpwps,wsats,beta_soil,bulkdens,k_dry,Ks   # each [NSOILLAYER]
Real df_tillage[NTILLLAYER]
Real w[NSOILLAYER] ; Real w_evap ; Real w_fw[NSOILLAYER]
Real snowpack, snowheight, snowfraction
Real temp[NSOILLAYER+1]                      # 24, not 23
Real enth[NHEATGRIDP]
Real wi_abs_enth_adj, sol_abs_enth_adj, ice_depth, ice_fw, freeze_depth, ice_pwp, perc_energy
                                             # each [NSOILLAYER]
int16 state[NSOILLAYER]                      # SHORT, not int
Real mean_maxthaw, alag, amp, rw_buffer
Poolpar k_mean[LASTLAYER], decay_rate[LASTLAYER]
Stocks decomp_litter_mean ; Stocks decomp_litter_pft[ntotpft]
int32 count ; Real meanw1
```

**LITTER** — `fwritelitter.c`. `n` is a **`uint8`**, not an `int32`:
```
Real  avg_fbd[NFUELCLASS+1]
uint8 n
n x { uint8 pft_id ; Trait ag ; Trait agsub ; Stocks bg }      # 1 + 176 = 177 B each
Real  agtop_wcap, agtop_moist, agtop_cover, agtop_temp
```

**CLIMBUF** — `climbuf.c`. Two traps: `dval_prec` is declared `Real[NDAYS+1]` but **one** element
is written, and the two 20-year ring buffers carry **`n`** values, not `size`:
```
Real  temp_max, temp_min, atemp_mean, aetp_mean, atemp_mean20, atemp_mean20_fix, gdd5
Real  dval_prec[0]                      # ONE element
Real  temp[NDAYS], prec[NDAYS]
Real  mpet20[NMONTH], mprec20[NMONTH], mtemp20[NMONTH]
Real  V_req[ncft], V_req_a[ncft]
BUFFER min ; BUFFER max                 # int32 size, n, index ; Real sum ; Real data[n]
```
The whole climate buffer is **computable from the forcing** and therefore DERIVED, never learned.

### 1.5 The PFT list — where the trees are

`pftlist.c` writes `int32 n`, then `n` entries via `fwritepft.c`. Because this configuration runs
`individual: true`, **every single tree is its own PFT entry**. That is why a cell is ~1.9 MB and
why the emulator's target is a variable-length roster rather than a per-PFT mean.

An entry's width depends only on its PFT id: **tree = 554 B** (ids 0–6), **grass = 342 B** (ids
7–9). Crop ids 10–21 cannot appear in a natural stand. The stride is the specification — a wrong one
walks into the next stem's fields and reports plausible numbers, so
`src/vegemu/binfmt/restart.py` asserts both and the tests assert no field overhangs its entry.

```
uint8  id
Real   phen_gsi{tmin,tmax,light,wscal}        # offsets 1,9,17,25
Real   wscal, wscal_mean, vscal, aphen, phen  # 33..72
<type-specific>                               # tree: 73..416   grass: 73..204
Stocks bm_inc
Real   nind, gdd, fpc, albedo, fapar, rootdepth, nleaf, beta_root, beta_2,
       sla, minwscal, emax, longevity         # 13 Real
Stocks establish
uint8  litter
```

Tree-specific (`tree/fwrite_tree.c`), from offset 73: `height, crownarea, barkthickness, gddtw,
aphen_raingreen, wooddens, leaf_old` (Real); `isphen` (int32); `turn`, `turn_litt` (`Treeturn` =
`{Stocks leaf, root}`); `turn_nbminc` (Real); `ind` (`Treephys2` = `Stocks
{leaf, sapwood, heartwood, root, sapwood_bg, heartwood_bg, debt}`); **`age`, `bm_inc_counter`,
`index`** (int32); `excess_carbon, D95max, k_root, water_stress` (Real); `temp_stress` (int32);
`nfertilizer, nmanure` (Real); `nfert_event` (int32); `falloc` (`Treephyspar` = 4 Real).
The `cultivation_type == ANNUAL_TREE` branch (`fruit`, `boll_age`) does **not** fire here —
`nagtree` is 0 in this PFT set.

Grass-specific (`grass/fwrite_grass.c`): `turn`, `turn_litt` (`Grassphys` = `{Stocks leaf, root}`);
`max_leaf`, `excess_carbon` (Real); `ind` (`Grassphys`); `falloc` (2 Real); `growing_days` (int32).

**`bm_inc_counter` is the consecutive-bad-growth-years counter** that hard-kills a stem at 5, so a
saved state can only contain 0–4. It is carried by 10.5–13.7 % of stems, which bear 42–46 % of all
mortality mass, and averaging it away reverses the trait-selection sign in 3–4 of the 7 tree types.
It is a real restart field, so the emulator must predict it (`MEMORY.md:bad-years-counter`).

**Measured cross-check on the field map.** Byte-identity proves the framing, not the offsets: a
wrong offset inside the 554-byte stride survives the round-trip untouched. At Hainich (cell 42490,
597 stems over 25 patches) `height` gives 51.4 % of stems above the per-tree writer's 5 m cut,
against ~47 % measured independently in the predecessor — a number nothing in this repo produced.
That is the check that actually bites, and it is asserted in the test suite.

---

## 2. `.clm` — forcing, grid, soil

`src/vegemu/binfmt/clm.py`. Written/read by `openinputfile.c`, `freadanyheader.c`, `headersize.c`,
`openclimate.c`, `readrealvec.c`, `getclimate.c`.

```
<name>            strlen(name) bytes, no terminator: "LPJCLIM", "LPJGRID", "LPJSOIL", ...
int32 version
v1 -> Header_old  24 B   6 int32                                        datatype := SHORT
v2 -> Header2     32 B   6 int32, float32 cellsize, float32 scalar      datatype := SHORT
v3 -> Header3     40 B   + float32 cellsize_lat, int32 datatype
v4 -> Header      48 B   + int32 nstep, int32 timestep
```

`order` must be `CELLYEAR` (1) and nothing else is accepted. Data layout is

```
value[year][cell][band]          physical = intercept + raw * scalar
```

so one year is a contiguous `ncell · nbands · itemsize` block at
`header_bytes + (year - firstyear) · year_bytes`. `intercept` is 0 for every variable this project
reads (it is 100 with a negated scalar only for the cloudiness input, which this configuration does
not use).

### 2.1 ⚠ The input set is MIXED, and this is asserted in the tests

| leg | `tas` `pr` `rsds` `lwnet` | `huss` |
|---|---|---|
| historical (1901–2019) | **v3 float32, scalar 1.0** | v3 float32, scalar 1.0 |
| ssp370 (2015–2100) | **v2 int16, scalar 0.1** — tenths of a degree | **v3 float32, scalar 1.0** |
| ssp126 (2015–2100) | **v2 int16, scalar 0.1** | **v3 float32, scalar 1.0** |

One hardcoded dtype reads four of the five wrong. A missing `scalar` is worse than a crash: 129 °C
at Hainich is a number a model trains on happily. `test_scenario_legs_are_mixed_versions` fails if
anyone "simplifies" the reader to a single dtype.

The C only **warns** (`WARNING032`) when the file size disagrees with
`nyear·ncell·nbands·itemsize`. Our reader refuses, because a size mismatch means the dtype or the
year count is wrong and every value read is silently shifted.

### 2.2 The grid file

`inputs.coord` is `LPJGRID` v3 float32, `nbands` 2, one "year": `(lon, lat)` per cell in degrees.
**Cell 42490 must come out as lon 10.25 / lat 51.25 (Hainich).** A second 67,420-cell coordinate
file exists elsewhere on the cluster in a different ordering, in which 42490 is the Sonoran desert;
pairing the two does not raise, it relabels every cell in the corpus.

---

## 3. Which forcing years the spin-up actually sees

⚠ **Corrected 2026-09-08.** An earlier version of this section said the spin-up cycles its 30 years
deterministically via `spinup_year = (year - firstyear + nspinup) % nspinyear` (`iterate.c:114`).
That is the **`else` branch**, and it is not the one taken: the ground truth's config sets
`"shuffle_climate": true`, so `iterate.c:108` runs instead and each spin-up year draws a **random**
one of the stored `nspinyear` years, `spinup_year = erand48(config->seed) * nspinyear`.

What actually happens (`iterate.c:88-119`): the loop runs `firstyear - nspinup` … `lastyear`, and a
year **before the climate file's own first year** takes a random stored year; from the file's first
year onward the file is read in order. With `nspinup` 1000, `nspinyear` 30, `firstyear` 2000,
`lastyear` 1999 and forcing starting in 1901, the stored `restart_1999.lpj` is **901 randomly drawn
years out of 1901–1930, then the 1901–1999 historical transient in order** — not a pure
equilibrium, and not a deterministic cycle either. Any estimand built on it must say so.

Two consequences that bite:

* the draw sequence is a function of `random_seed` alone, so **two arms with the same seed see the
  same sequence of climate years** and their difference is climate, not weather. That is what makes
  a paired control-vs-perturbed comparison at a single cell worth anything.
* the last `nyear_of_file` years are **not** shuffled. With a 30-year forcing file every arm and
  every seed shares that deterministic tail, so a window mean taken over it has far less climate
  noise than one taken over the shuffled part. Do not compare a tail window against a shuffled one.

Also: the spin-up is run with **no preprocessor flag at all** — the ground truth's `slurm_spinup.jcf`
passes no `-D`, so `-DSPINUP` is *not* set and `inherit_startyear` is 0, not 200. The model prints
its resolved value as `inheritance after N yrs`; read it there rather than from the config text.

---

## 4. A subset `.clm`: one cell, 44 KB, and the model reads it correctly

A forcing file does **not** have to span the whole grid. `openclimate.c:207-219` seeks to
`(startgrid - header.firstcell) * nbands * itemsize + headersize` and strides by
`header.ncell * nbands * itemsize`; the only range gate is `openinputfile.c:145`,

```
firstgrid >= header.firstcell  &&  nall + firstgrid <= header.ncell + header.firstcell
```

where `firstgrid`/`nall` come from `startgrid`/`endgrid` (`fscanconfig.c:1104`). So a file declaring
`firstcell = <cell>, ncell = 1` is read and validated correctly while the grid and soil inputs stay
global. One cell × 30 years × 365 days × float32 is **43,851 bytes** including the header.

Writing one: copy every header field from the source and change only `firstcell`, `ncell`,
`firstyear` and `nyear`. **Refuse a source that is not unscaled float** — the historical leg is v3
float32 scalar 1.0, but the scenario legs are v2 int16 scalar 0.1, and a perturbation written
through one of those quantises to a tenth of a degree instead of failing.

The proof that such a writer is correct is a **zero-perturbation byte comparison** against the slice
of the source file it came from (`tests/test_perturb.py`), not an assertion — invariant 7.
