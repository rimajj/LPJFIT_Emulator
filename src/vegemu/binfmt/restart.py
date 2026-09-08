"""The LPJmL-FIT restart file: reader, writer, and the per-cell record.

WHY THIS FILE IS THE CENTRE OF THE PROJECT. The deliverable is a state the real model will load,
so the emulator's output format is the model's own restart file. Everything downstream -- the
equilibrium targets we train on, the state we synthesise, the end-to-end test -- goes through here.
Invariant 7 therefore applies in its strongest form: this module is proven by reading a real cell
out of the 119 GiB ground-truth file and writing it back byte-identically, and by nothing else.

The layout is transcribed from the model's C sources, not reverse-engineered from bytes. Every
field below names the function it comes from; `docs/reference/binfmt.md` is the long form.

FILE FRAMING
    "LPJRESTART"                       10 bytes, no terminator      (fwriteheader.c)
    int32   version = 33                                            (header.h: RESTART_VERSION)
    Header3                            40 bytes: 6 int32, 3 float32, int32 datatype
    Restartheader                      30 bytes, and its DISK ORDER IS NOT THE STRUCT ORDER
    int64[ncell]                       ABSOLUTE byte offset of each cell record
    cell records                       variable length, in cell order

    => index[0] == 84 + 8 * ncell, and a record's length is index[i+1] - index[i].

THE TRAP IN THE RESTART HEADER. `Restartheader` declares (landuse, river_routing, individual,
sdate_option, crop_option, double_harvest, seed) but `freadrestartheader.c` reads
(landuse, river_routing, sdate_option, crop_option, double_harvest, seed, individual) --
`individual` moves to the END on disk. Decoding in declaration order silently reads the
gap-dynamics flag as a sowing-date option -- the kind of error that produces a plausible wrong
answer rather than a crash.

REAL IS float64 AND Bool IS int32. Built with -DUSE_RAND48, so `Seed` is 3 x uint16 and the restart
header is 6*4 + 6 = 30 bytes rather than 6*4 + 3*4. Little-endian native; a byte-swapped file is
detected by the version word's low byte being zero, as the C does.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import numpy.typing as npt

# --------------------------------------------------------------------------------------------
# Compile-time constants of the build that produced the ground truth. From include/soil.h,
# include/climbuf.h, include/date.h, include/numeric.h and Makefile.inc's LPJFLAGS.
# --------------------------------------------------------------------------------------------
RESTART_MAGIC = b"LPJRESTART"
RESTART_VERSION = 33
GENERIC_HEADER_BYTES = 40  # sizeof(Header3)
RESTART_HEADER_BYTES = 30  # restartsize() with USE_RAND48
PREFIX_BYTES = len(RESTART_MAGIC) + 4 + GENERIC_HEADER_BYTES + RESTART_HEADER_BYTES  # 84

NSOILLAYER = 23  # soil.h
LASTLAYER = NSOILLAYER - 1  # 22; `forrootsoillayer` runs 0..LASTLAYER-1
NFUELCLASS = 4
NTILLLAYER = 1
GPLHEAT = 1
NHEATGRIDP = NSOILLAYER * GPLHEAT  # 23
NDAYS = 31  # climbuf.h -- max days in a month
NMONTH = 12
NGRASS = 2  # pftpar.h -- OTHERS + MANAGED GRASSLAND, a LANDFRAC width, not a PFT count
NSEED = 3  # numeric.h with USE_RAND48

# Composite widths, in bytes.
_REAL = 8  # Real     = double
_INT = 4  # Bool/int = int32
_STOCKS = 2 * _REAL  # {carbon, nitrogen}
_POOLPAR = 2 * _REAL  # {fast, slow}
_POOL = 2 * _STOCKS  # {Stocks fast, Stocks slow}
_TRAIT = _STOCKS * (1 + NFUELCLASS)  # {Stocks leaf, Stocks wood[NFUELCLASS]}
_LITTERITEM = 1 + 2 * _TRAIT + _STOCKS  # id byte, ag, agsub, bg
_CROPDATES = 8 * _INT  # cropdates.h: 6 scalars + fallow[2]
_SAPLING = 10 * _REAL + 2 * _INT  # fwritesaplings.c
_PHENOLOGY = 4 * _REAL  # {tmin, tmax, light, wscal}

# PFT entry sizes, individual mode. Derived below and asserted against these, because a wrong
# stride does not fail -- it walks into the middle of the next tree and reports plausible numbers.
PFT_TREE_BYTES = 554
PFT_GRASS_BYTES = 342


@dataclass(frozen=True)
class Layout:
    """The configuration-dependent counts a record's length depends on.

    Defaults are the LPJmL-FIT configuration that produced every existing ground-truth leg
    (`lpjmlfit.js`: 7 trees + 3 grasses natural, 12 crops, individual true, npatch 25,
    river_routing false, landuse "no"). `from_headers` derives the flags from the file itself
    rather than trusting these, so a file written under a different configuration fails loudly.
    """

    ntree: int = 7
    ngrass_pft: int = 3
    ncft: int = 12
    nagtree: int = 0
    river_routing: bool = False
    landuse: bool = False
    sdate_option: int = 0
    crop_option: bool = False
    individual: bool = True
    ischeckpoint: bool = False

    @property
    def npft(self) -> int:
        """Natural PFTs. `gdd[]` in the cell record has this width."""
        return self.ntree + self.ngrass_pft

    @property
    def ntotpft(self) -> int:
        """npft + ncft. The width of `c_shift[]` and `decomp_litter_pft[]`, and of `nbands`."""
        return self.npft + self.ncft

    def pft_bytes(self, pft_id: int) -> int:
        """Entry width for a PFT id. Trees, then grasses, then crops (pft_lpjmlfit.js order)."""
        if pft_id < self.ntree:
            return PFT_TREE_BYTES
        if pft_id < self.npft:
            return PFT_GRASS_BYTES
        raise ValueError(
            f"pft id {pft_id} is a crop; a natural stand carries only trees and grasses. "
            "A crop id here means the stand list was mis-walked, or landuse is enabled."
        )

    @classmethod
    def from_headers(cls, generic: GenericHeader, restart: RestartHeader, **over: Any) -> Layout:
        """Take from the file everything the file records, and only default the rest.

        `nbands` pins ntotpft, so a file with a different PFT set is caught here rather than by a
        record length that happens not to divide evenly.
        """
        base = cls(**over)
        if generic.nbands != base.ntotpft:
            raise ValueError(
                f"file has nbands={generic.nbands} PFTs but this Layout describes "
                f"{base.ntotpft} ({base.ntree} trees + {base.ngrass_pft} grasses + "
                f"{base.ncft} crops). Pass the right ntree/ngrass_pft/ncft."
            )
        return cls(
            ntree=base.ntree,
            ngrass_pft=base.ngrass_pft,
            ncft=base.ncft,
            nagtree=base.nagtree,
            river_routing=restart.river_routing,
            landuse=restart.landuse,
            sdate_option=restart.sdate_option,
            crop_option=restart.crop_option,
            individual=restart.individual,
            ischeckpoint=base.ischeckpoint,
        )


@dataclass
class GenericHeader:
    """`Header3` -- the 40 bytes after the magic and version. From include/header.h."""

    order: int
    firstyear: int
    nyear: int
    firstcell: int
    ncell: int
    nbands: int
    cellsize_lon: float
    scalar: float
    cellsize_lat: float
    datatype: int  # 0=byte 1=short 2=int 3=float 4=double, 0-BASED

    _STRUCT = struct.Struct("<6i3fi")

    @classmethod
    def unpack(cls, buf: bytes) -> GenericHeader:
        return cls(*cls._STRUCT.unpack(buf))

    def pack(self) -> bytes:
        return self._STRUCT.pack(
            self.order,
            self.firstyear,
            self.nyear,
            self.firstcell,
            self.ncell,
            self.nbands,
            self.cellsize_lon,
            self.scalar,
            self.cellsize_lat,
            self.datatype,
        )


@dataclass
class RestartHeader:
    """The 30 bytes after `Header3`, IN DISK ORDER (freadrestartheader.c), not struct order."""

    landuse: bool
    river_routing: bool
    sdate_option: int
    crop_option: bool
    double_harvest: bool
    seed: tuple[int, int, int]
    individual: bool

    _STRUCT = struct.Struct("<5i3Hi")

    @classmethod
    def unpack(cls, buf: bytes) -> RestartHeader:
        f = cls._STRUCT.unpack(buf)
        return cls(
            landuse=bool(f[0]),
            river_routing=bool(f[1]),
            sdate_option=f[2],
            crop_option=bool(f[3]),
            double_harvest=bool(f[4]),
            seed=(f[5], f[6], f[7]),
            individual=bool(f[8]),
        )

    def pack(self) -> bytes:
        return self._STRUCT.pack(
            int(self.landuse),
            int(self.river_routing),
            self.sdate_option,
            int(self.crop_option),
            int(self.double_harvest),
            *self.seed,
            int(self.individual),
        )


# --------------------------------------------------------------------------------------------
# Cursor. A record is walked once, forwards, exactly as the C writes it. Arrays come back as
# numpy views so that a large soil block costs one memcpy rather than 23 Python floats, and so
# the writer can put the identical bit pattern back -- `tobytes()` on a float64 array is exact,
# including any signalling NaN the model happened to leave in an unused slot.
# --------------------------------------------------------------------------------------------
class _Cursor:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes | memoryview, pos: int = 0) -> None:
        self.buf = memoryview(buf).cast("B") if not isinstance(buf, memoryview) else buf
        self.pos = pos

    def raw(self, n: int) -> bytes:
        out = bytes(self.buf[self.pos : self.pos + n])
        if len(out) != n:
            raise EOFError(f"record truncated: wanted {n} bytes at {self.pos}")
        self.pos += n
        return out

    def u8(self) -> int:
        v = self.buf[self.pos]
        self.pos += 1
        return int(v)

    def i32(self) -> int:
        v: int = int(np.frombuffer(self.buf, dtype="<i4", count=1, offset=self.pos)[0])
        self.pos += _INT
        return v

    def f64(self) -> float:
        v: float = float(np.frombuffer(self.buf, dtype="<f8", count=1, offset=self.pos)[0])
        self.pos += _REAL
        return v

    def arr(self, dtype: str, count: int) -> npt.NDArray[Any]:
        out = np.frombuffer(self.buf, dtype=dtype, count=count, offset=self.pos).copy()
        self.pos += out.nbytes
        return out

    def f64a(self, count: int) -> npt.NDArray[np.float64]:
        return self.arr("<f8", count).astype(np.float64, copy=False)


class _Emitter:
    """The writer's mirror of `_Cursor`. Appends, then joins once."""

    __slots__ = ("parts",)

    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def raw(self, b: bytes) -> None:
        self.parts.append(b)

    def u8(self, v: int) -> None:
        self.parts.append(bytes((v & 0xFF,)))

    def i32(self, v: int) -> None:
        self.parts.append(struct.pack("<i", v))

    def f64(self, v: float) -> None:
        self.parts.append(struct.pack("<d", v))

    def arr(self, a: npt.NDArray[Any]) -> None:
        self.parts.append(np.ascontiguousarray(a).tobytes())

    def done(self) -> bytes:
        return b"".join(self.parts)


# --------------------------------------------------------------------------------------------
# PFT entries. Fixed stride per type, so once the offsets are known the fields come out
# vectorised. The offsets below are literal byte positions inside one entry; they ARE the
# specification, which is why PLR2004 is switched off for this directory.
# --------------------------------------------------------------------------------------------
def _tree_dtype() -> np.dtype[Any]:
    """Structured view of one 554-byte tree entry (fwritepft.c + tree/fwrite_tree.c).

    Unaligned by construction: the id byte at offset 0 puts every double on an odd offset. numpy
    handles that; a naive C struct cast would not.
    """
    names: list[str] = []
    formats: list[str] = []
    offsets: list[int] = []

    def put(name: str, fmt: str, off: int) -> None:
        names.append(name)
        formats.append(fmt)
        offsets.append(off)

    put("id", "u1", 0)
    # Pft, generic head (fwritepft.c)
    put("phen_tmin", "<f8", 1)
    put("phen_tmax", "<f8", 9)
    put("phen_light", "<f8", 17)
    put("phen_wscal", "<f8", 25)
    put("wscal", "<f8", 33)
    put("wscal_mean", "<f8", 41)
    put("vscal", "<f8", 49)
    put("aphen", "<f8", 57)
    put("phen", "<f8", 65)
    # Pfttree (tree/fwrite_tree.c), 344 bytes from offset 73
    put("height", "<f8", 73)
    put("crownarea", "<f8", 81)
    put("barkthickness", "<f8", 89)
    put("gddtw", "<f8", 97)
    put("aphen_raingreen", "<f8", 105)
    put("wooddens", "<f8", 113)
    put("leaf_old", "<f8", 121)
    put("isphen", "<i4", 129)
    put("turn_leaf_c", "<f8", 133)
    put("turn_leaf_n", "<f8", 141)
    put("turn_root_c", "<f8", 149)
    put("turn_root_n", "<f8", 157)
    put("turn_litt_leaf_c", "<f8", 165)
    put("turn_litt_leaf_n", "<f8", 173)
    put("turn_litt_root_c", "<f8", 181)
    put("turn_litt_root_n", "<f8", 189)
    put("turn_nbminc", "<f8", 197)
    # ind: Treephys2 = leaf, sapwood, heartwood, root, sapwood_bg, heartwood_bg, debt
    for i, part in enumerate(
        ("leaf", "sapwood", "heartwood", "root", "sapwood_bg", "heartwood_bg", "debt")
    ):
        put(f"ind_{part}_c", "<f8", 205 + 16 * i)
        put(f"ind_{part}_n", "<f8", 213 + 16 * i)
    put("age", "<i4", 317)
    put("bm_inc_counter", "<i4", 321)  # the consecutive-bad-growth-years counter; hard-kills at 5
    put("index", "<i4", 325)
    put("excess_carbon", "<f8", 329)
    put("D95max", "<f8", 337)
    put("k_root", "<f8", 345)
    put("water_stress", "<f8", 353)
    put("temp_stress", "<i4", 361)
    put("nfertilizer", "<f8", 365)
    put("nmanure", "<f8", 373)
    put("nfert_event", "<i4", 381)
    put("falloc_leaf", "<f8", 385)
    put("falloc_sapwood", "<f8", 393)
    put("falloc_sapwood_bg", "<f8", 401)
    put("falloc_root", "<f8", 409)
    # Pft, generic tail
    put("bm_inc_c", "<f8", 417)
    put("bm_inc_n", "<f8", 425)
    for i, part in enumerate(
        (
            "nind",
            "gdd",
            "fpc",
            "albedo",
            "fapar",
            "rootdepth",
            "nleaf",
            "beta_root",
            "beta_2",
            "sla",
            "minwscal",
            "emax",
            "longevity",
        )
    ):
        put(part, "<f8", 433 + 8 * i)
    put("establish_c", "<f8", 537)
    put("establish_n", "<f8", 545)
    put("litter", "u1", 553)
    return np.dtype(
        {"names": names, "formats": formats, "offsets": offsets, "itemsize": PFT_TREE_BYTES}
    )


def _grass_dtype() -> np.dtype[Any]:
    """Structured view of one 342-byte grass entry (fwritepft.c + grass/fwrite_grass.c)."""
    names: list[str] = []
    formats: list[str] = []
    offsets: list[int] = []

    def put(name: str, fmt: str, off: int) -> None:
        names.append(name)
        formats.append(fmt)
        offsets.append(off)

    put("id", "u1", 0)
    for i, part in enumerate(("phen_tmin", "phen_tmax", "phen_light", "phen_wscal")):
        put(part, "<f8", 1 + 8 * i)
    for i, part in enumerate(("wscal", "wscal_mean", "vscal", "aphen", "phen")):
        put(part, "<f8", 33 + 8 * i)
    # Pftgrass (grass/fwrite_grass.c), 132 bytes from offset 73
    put("turn_leaf_c", "<f8", 73)
    put("turn_leaf_n", "<f8", 81)
    put("turn_root_c", "<f8", 89)
    put("turn_root_n", "<f8", 97)
    put("turn_litt_leaf_c", "<f8", 105)
    put("turn_litt_leaf_n", "<f8", 113)
    put("turn_litt_root_c", "<f8", 121)
    put("turn_litt_root_n", "<f8", 129)
    put("max_leaf", "<f8", 137)
    put("excess_carbon", "<f8", 145)
    put("ind_leaf_c", "<f8", 153)
    put("ind_leaf_n", "<f8", 161)
    put("ind_root_c", "<f8", 169)
    put("ind_root_n", "<f8", 177)
    put("falloc_leaf", "<f8", 185)
    put("falloc_root", "<f8", 193)
    put("growing_days", "<i4", 201)
    put("bm_inc_c", "<f8", 205)
    put("bm_inc_n", "<f8", 213)
    for i, part in enumerate(
        (
            "nind",
            "gdd",
            "fpc",
            "albedo",
            "fapar",
            "rootdepth",
            "nleaf",
            "beta_root",
            "beta_2",
            "sla",
            "minwscal",
            "emax",
            "longevity",
        )
    ):
        put(part, "<f8", 221 + 8 * i)
    put("establish_c", "<f8", 325)
    put("establish_n", "<f8", 333)
    put("litter", "u1", 341)
    return np.dtype(
        {"names": names, "formats": formats, "offsets": offsets, "itemsize": PFT_GRASS_BYTES}
    )


TREE_DTYPE = _tree_dtype()
GRASS_DTYPE = _grass_dtype()
assert TREE_DTYPE.itemsize == PFT_TREE_BYTES
assert GRASS_DTYPE.itemsize == PFT_GRASS_BYTES


def gather(buf: bytes | memoryview, offsets: npt.NDArray[np.int64], dt: np.dtype[Any]) -> Any:
    """Pull `len(offsets)` fixed-stride entries out of a buffer as one structured array.

    The entries are not contiguous (trees and grasses interleave), so this gathers the rows by
    index instead of slicing -- one vectorised pass rather than a Python loop per stem.
    """
    flat = np.frombuffer(buf, dtype=np.uint8)
    if offsets.size == 0:
        return np.zeros(0, dtype=dt)
    rows = flat[offsets[:, None] + np.arange(dt.itemsize, dtype=np.int64)[None, :]]
    return np.ascontiguousarray(rows).view(dt).reshape(-1)


# --------------------------------------------------------------------------------------------
# The soil block. fwritesoil.c, in order. Kept as one flat dict of numpy arrays: the emulator
# LEARNS the carbon pools and litter and RELAXES the water/ice/enthalpy block from a template,
# so the split matters more than any nesting would.
# --------------------------------------------------------------------------------------------
_SOIL_VECTORS: tuple[tuple[str, int], ...] = (
    ("NO3", LASTLAYER),
    ("NH4", LASTLAYER),
    ("wsat", NSOILLAYER),
    ("wpwp", NSOILLAYER),
    ("wfc", NSOILLAYER),
    ("whc", NSOILLAYER),
    ("whcs", NSOILLAYER),
    ("wpwps", NSOILLAYER),
    ("wsats", NSOILLAYER),
    ("beta_soil", NSOILLAYER),
    ("bulkdens", NSOILLAYER),
    ("k_dry", NSOILLAYER),
    ("Ks", NSOILLAYER),
    ("df_tillage", NTILLLAYER),
    ("w", NSOILLAYER),
)
_SOIL_VECTORS_2: tuple[tuple[str, int], ...] = (
    ("w_fw", NSOILLAYER),
)
_SOIL_VECTORS_3: tuple[tuple[str, int], ...] = (
    ("temp", NSOILLAYER + 1),
    ("enth", NHEATGRIDP),
    ("wi_abs_enth_adj", NSOILLAYER),
    ("sol_abs_enth_adj", NSOILLAYER),
    ("ice_depth", NSOILLAYER),
    ("ice_fw", NSOILLAYER),
    ("freeze_depth", NSOILLAYER),
    ("ice_pwp", NSOILLAYER),
    ("perc_energy", NSOILLAYER),
)


def _read_litter(cur: _Cursor) -> dict[str, Any]:
    lit: dict[str, Any] = {}
    lit["avg_fbd"] = cur.f64a(NFUELCLASS + 1)
    n = cur.u8()
    lit["n"] = n
    lit["pft_ids"] = np.empty(n, dtype=np.uint8)
    lit["items"] = np.empty((n, 2 * (1 + NFUELCLASS) * 2 + 2), dtype=np.float64)
    for i in range(n):
        lit["pft_ids"][i] = cur.u8()
        lit["items"][i] = cur.f64a(2 * (1 + NFUELCLASS) * 2 + 2)
    lit["agtop"] = cur.f64a(4)  # wcap, moist, cover, temp
    return lit


def _write_litter(em: _Emitter, lit: dict[str, Any]) -> None:
    em.arr(lit["avg_fbd"])
    em.u8(int(lit["n"]))
    for i in range(int(lit["n"])):
        em.u8(int(lit["pft_ids"][i]))
        em.arr(lit["items"][i])
    em.arr(lit["agtop"])


def _read_soil(cur: _Cursor, lay: Layout) -> dict[str, Any]:
    s: dict[str, Any] = {}
    # forrootsoillayer(l): l = 0 .. LASTLAYER-1
    s["pool"] = np.empty((LASTLAYER, 4), dtype=np.float64)  # fast{c,n}, slow{c,n}
    s["c_shift"] = np.empty((LASTLAYER, lay.ntotpft, 2), dtype=np.float64)
    for layer in range(LASTLAYER):
        s["pool"][layer] = cur.f64a(4)
        s["c_shift"][layer] = cur.f64a(lay.ntotpft * 2).reshape(lay.ntotpft, 2)
    s["litter"] = _read_litter(cur)
    for name, count in _SOIL_VECTORS:
        s[name] = cur.f64a(count)
    s["w_evap"] = cur.f64()
    for name, count in _SOIL_VECTORS_2:
        s[name] = cur.f64a(count)
    s["snowpack"] = cur.f64()
    s["snowheight"] = cur.f64()
    s["snowfraction"] = cur.f64()
    for name, count in _SOIL_VECTORS_3:
        s[name] = cur.f64a(count)
    s["state"] = cur.arr("<i2", NSOILLAYER)
    s["mean_maxthaw"] = cur.f64()
    s["alag"] = cur.f64()
    s["amp"] = cur.f64()
    s["rw_buffer"] = cur.f64()
    s["k_mean"] = cur.f64a(LASTLAYER * 2).reshape(LASTLAYER, 2)
    s["decay_rate"] = cur.f64a(LASTLAYER * 2).reshape(LASTLAYER, 2)
    s["decomp_litter_mean"] = cur.f64a(2)
    s["decomp_litter_pft"] = cur.f64a(lay.ntotpft * 2).reshape(lay.ntotpft, 2)
    s["count"] = cur.i32()
    s["meanw1"] = cur.f64()
    return s


def _write_soil(em: _Emitter, s: dict[str, Any], lay: Layout) -> None:
    for layer in range(LASTLAYER):
        em.arr(s["pool"][layer])
        em.arr(s["c_shift"][layer])
    _write_litter(em, s["litter"])
    for name, _ in _SOIL_VECTORS:
        em.arr(s[name])
    em.f64(s["w_evap"])
    for name, _ in _SOIL_VECTORS_2:
        em.arr(s[name])
    em.f64(s["snowpack"])
    em.f64(s["snowheight"])
    em.f64(s["snowfraction"])
    for name, _ in _SOIL_VECTORS_3:
        em.arr(s[name])
    em.arr(s["state"])
    em.f64(s["mean_maxthaw"])
    em.f64(s["alag"])
    em.f64(s["amp"])
    em.f64(s["rw_buffer"])
    em.arr(s["k_mean"])
    em.arr(s["decay_rate"])
    em.arr(s["decomp_litter_mean"])
    em.arr(s["decomp_litter_pft"])
    em.i32(s["count"])
    em.f64(s["meanw1"])
    _ = lay  # symmetry with _read_soil; widths already baked into the arrays


# --------------------------------------------------------------------------------------------
# The PFT list. This is where the trees are, and in this configuration EVERY TREE IS ITS OWN
# PFT ENTRY -- which is why a cell is ~1.9 MB and why the roster, not a per-PFT mean, is the
# emulator's target.
# --------------------------------------------------------------------------------------------
def _scan_pftlist(cur: _Cursor, lay: Layout) -> tuple[int, npt.NDArray[np.int64]]:
    """Walk the list once, recording each entry's absolute offset. Returns (n, offsets).

    Sizes depend on the id byte, so the walk is inherently sequential; the FIELDS are then read
    vectorised via `gather`. This keeps the per-stem Python work to one indexing and one add.
    """
    n = cur.i32()
    offsets = np.empty(n, dtype=np.int64)
    buf = cur.buf
    pos = cur.pos
    tree_ids = lay.ntree
    npft = lay.npft
    for i in range(n):
        offsets[i] = pos
        pft_id = buf[pos]
        if pft_id < tree_ids:
            pos += PFT_TREE_BYTES
        elif pft_id < npft:
            pos += PFT_GRASS_BYTES
        else:
            raise ValueError(
                f"pft id {pft_id} at offset {pos} is not a natural PFT (0..{npft - 1}). "
                "The stand list was mis-walked."
            )
    cur.pos = pos
    return n, offsets


def _read_pftlist(cur: _Cursor, lay: Layout) -> dict[str, Any]:
    start = cur.pos
    n, offsets = _scan_pftlist(cur, lay)
    raw = bytes(cur.buf[start : cur.pos])
    rel = offsets - start
    ids = np.array([cur.buf[int(o)] for o in offsets], dtype=np.uint8)
    is_tree = ids < lay.ntree
    return {
        "n": n,
        "raw": raw,  # keeps the bytes for an exact re-emit
        "ids": ids,
        "tree_offsets": rel[is_tree],
        "grass_offsets": rel[~is_tree],
        "order_is_tree": is_tree,
    }


def _write_pftlist(em: _Emitter, p: dict[str, Any]) -> None:
    em.raw(p["raw"])


def trees_of(pftlist: dict[str, Any]) -> Any:
    """The tree entries of one patch as a structured array (one row per stem)."""
    return gather(pftlist["raw"][_INT:], pftlist["tree_offsets"] - _INT, TREE_DTYPE)


def grasses_of(pftlist: dict[str, Any]) -> Any:
    """The grass entries of one patch as a structured array."""
    return gather(pftlist["raw"][_INT:], pftlist["grass_offsets"] - _INT, GRASS_DTYPE)


# --------------------------------------------------------------------------------------------
# Stands and patches.
# --------------------------------------------------------------------------------------------
def _read_stand(cur: _Cursor, lay: Layout) -> dict[str, Any]:
    landusetype = cur.u8()
    npatch = cur.i32()
    patches: list[dict[str, Any]] = []
    for _ in range(npatch):
        soil = _read_soil(cur, lay)
        pftlist = _read_pftlist(cur, lay)
        frac_g = cur.f64a(NSOILLAYER)
        patches.append({"soil": soil, "pftlist": pftlist, "frac_g": frac_g})
    frac = cur.f64()
    # NATURAL's own fwrite writes nothing (fwrite_natural.c). Any other stand type would, and
    # landuse is "no" in every existing leg, so a non-natural stand is a hard error rather than
    # a silently short read.
    if landusetype != 0:
        raise NotImplementedError(
            f"stand landusetype {landusetype} carries type-specific state this reader does not "
            "decode. Every existing ground-truth leg runs landuse 'no', i.e. NATURAL only."
        )
    return {"landusetype": landusetype, "npatch": npatch, "patches": patches, "frac": frac}


def _write_stand(em: _Emitter, st: dict[str, Any], lay: Layout) -> None:
    em.u8(st["landusetype"])
    em.i32(st["npatch"])
    for patch in st["patches"]:
        _write_soil(em, patch["soil"], lay)
        _write_pftlist(em, patch["pftlist"])
        em.arr(patch["frac_g"])
    em.f64(st["frac"])


def _read_climbuf(cur: _Cursor, lay: Layout) -> dict[str, Any]:
    """fwriteclimbuf in src/lpj/climbuf.c.

    NOTE `dval_prec` is declared `Real[NDAYS+1]` but only ONE element is written. The 20-year
    ring buffers (`min`, `max`) are variable-length: they carry `n` values, not `size`.
    """
    c: dict[str, Any] = {}
    c["scalars"] = cur.f64a(7)  # temp_max, temp_min, atemp_mean, aetp_mean,
    #                             atemp_mean20, atemp_mean20_fix, gdd5
    c["dval_prec0"] = cur.f64()
    c["temp"] = cur.f64a(NDAYS)
    c["prec"] = cur.f64a(NDAYS)
    c["mpet20"] = cur.f64a(NMONTH)
    c["mprec20"] = cur.f64a(NMONTH)
    c["mtemp20"] = cur.f64a(NMONTH)
    c["V_req"] = cur.f64a(lay.ncft)
    c["V_req_a"] = cur.f64a(lay.ncft)
    c["min"] = _read_buffer(cur)
    c["max"] = _read_buffer(cur)
    return c


def _write_climbuf(em: _Emitter, c: dict[str, Any]) -> None:
    em.arr(c["scalars"])
    em.f64(c["dval_prec0"])
    for key in ("temp", "prec", "mpet20", "mprec20", "mtemp20", "V_req", "V_req_a"):
        em.arr(c[key])
    _write_buffer(em, c["min"])
    _write_buffer(em, c["max"])


def _read_buffer(cur: _Cursor) -> dict[str, Any]:
    """src/numeric/buffer.c: size, n, index, sum, then `n` (NOT `size`) values."""
    size = cur.i32()
    n = cur.i32()
    index = cur.i32()
    total = cur.f64()
    return {"size": size, "n": n, "index": index, "sum": total, "data": cur.f64a(n)}


def _write_buffer(em: _Emitter, b: dict[str, Any]) -> None:
    em.i32(b["size"])
    em.i32(b["n"])
    em.i32(b["index"])
    em.f64(b["sum"])
    em.arr(b["data"])


def _read_queue(cur: _Cursor) -> dict[str, Any]:
    size = cur.i32()
    first = cur.i32()
    return {"size": size, "first": first, "data": cur.f64a(size)}


def _write_queue(em: _Emitter, q: dict[str, Any]) -> None:
    em.i32(q["size"])
    em.i32(q["first"])
    em.arr(q["data"])


# --------------------------------------------------------------------------------------------
# The cell record. fwritecell.c, in order.
# --------------------------------------------------------------------------------------------
def read_cell(buf: bytes | memoryview, lay: Layout) -> dict[str, Any]:
    """Decode one cell record. Raises if the record does not end exactly where the buffer does."""
    cur = _Cursor(buf)
    rec: dict[str, Any] = {}
    rec["skip"] = cur.u8()
    rec["seed"] = cur.arr("<u2", NSEED)
    if lay.river_routing:
        rec["discharge"] = {
            "dmass_lake": cur.f64(),
            "dfout": cur.f64(),
            "dmass_river": cur.f64(),
            "dmass_sum": cur.f64(),
            "queue": _read_queue(cur),
        }
        rec["dam"] = cur.u8()
        if rec["dam"]:
            raise NotImplementedError("reservoir state (fwriteresdata) is not decoded")
    rec["mevap"] = cur.f64()
    if not rec["skip"]:
        rec["estab_storage_tree"] = cur.f64a(4)  # Stocks[2]
        rec["estab_storage_grass"] = cur.f64a(4)
        rec["nesterov_accum"] = cur.f64()
        rec["nesterov_max"] = cur.f64()
        rec["nesterov_day"] = cur.i32()
        rec["excess_water"] = cur.f64()
        rec["waterdeficit"] = cur.f64()
        rec["gdd"] = cur.f64a(lay.npft)
        nstand = cur.i32()
        rec["stands"] = [_read_stand(cur, lay) for _ in range(nstand)]
        rec["cropfrac_rf"] = cur.f64()
        rec["cropfrac_ir"] = cur.f64()
        rec["climbuf"] = _read_climbuf(cur, lay)
        rec["cropdates"] = cur.arr("<i4", lay.ncft * 8).reshape(lay.ncft, 8)
        if lay.sdate_option > 0:
            rec["sdate_fixed"] = cur.arr("<i4", 2 * lay.ncft)
        if lay.crop_option:
            rec["crop_phu_fixed"] = cur.f64a(2 * lay.ncft)
        rec["sowing_month"] = cur.arr("<i4", 2 * lay.ncft)
        rec["gs"] = cur.arr("<i4", 2 * lay.ncft)
        if lay.landuse:
            raise NotImplementedError(
                "landfrac / product / fertilizer_nr are only written when landuse is enabled; "
                "no existing ground-truth leg does"
            )
        nsapling = cur.i32()
        rec["nsapling"] = nsapling
        rec["saplings"] = cur.raw(nsapling * _SAPLING)
    if cur.pos != len(memoryview(buf)):
        raise ValueError(
            f"cell record decoded to {cur.pos} bytes but the record is "
            f"{len(memoryview(buf))} -- the layout does not match this file"
        )
    return rec


def write_cell(rec: dict[str, Any], lay: Layout) -> bytes:
    """Re-encode a record decoded by `read_cell`. Byte-identical is the whole point."""
    em = _Emitter()
    em.u8(rec["skip"])
    em.arr(rec["seed"])
    if lay.river_routing:
        d = rec["discharge"]
        for key in ("dmass_lake", "dfout", "dmass_river", "dmass_sum"):
            em.f64(d[key])
        _write_queue(em, d["queue"])
        em.u8(rec["dam"])
    em.f64(rec["mevap"])
    if not rec["skip"]:
        em.arr(rec["estab_storage_tree"])
        em.arr(rec["estab_storage_grass"])
        em.f64(rec["nesterov_accum"])
        em.f64(rec["nesterov_max"])
        em.i32(rec["nesterov_day"])
        em.f64(rec["excess_water"])
        em.f64(rec["waterdeficit"])
        em.arr(rec["gdd"])
        em.i32(len(rec["stands"]))
        for st in rec["stands"]:
            _write_stand(em, st, lay)
        em.f64(rec["cropfrac_rf"])
        em.f64(rec["cropfrac_ir"])
        _write_climbuf(em, rec["climbuf"])
        em.arr(rec["cropdates"])
        if lay.sdate_option > 0:
            em.arr(rec["sdate_fixed"])
        if lay.crop_option:
            em.arr(rec["crop_phu_fixed"])
        em.arr(rec["sowing_month"])
        em.arr(rec["gs"])
        em.i32(rec["nsapling"])
        em.raw(rec["saplings"])
    return em.done()


# --------------------------------------------------------------------------------------------
# The file.
# --------------------------------------------------------------------------------------------
@dataclass
class RestartReader:
    """Random access to a restart file by cell index, via the file's own offset table.

    Always seek; never scan. The global file is 119 GiB and the index is exactly what it is for.
    """

    path: Path
    generic: GenericHeader = field(init=False)
    restart: RestartHeader = field(init=False)
    index: npt.NDArray[np.int64] = field(init=False, repr=False)
    filesize: int = field(init=False)
    layout: Layout = field(init=False)
    _fh: BinaryIO | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.filesize = self.path.stat().st_size
        with self.path.open("rb") as fh:
            magic = fh.read(len(RESTART_MAGIC))
            if magic != RESTART_MAGIC:
                raise ValueError(f"{self.path}: magic {magic!r} != {RESTART_MAGIC!r}")
            (version,) = struct.unpack("<i", fh.read(4))
            if version & 0xFF == 0:
                raise NotImplementedError(
                    "this file is byte-swapped relative to this machine; the C detects it the same "
                    "way (low byte of the version word). Not implemented -- no cluster file is."
                )
            if version != RESTART_VERSION:
                raise ValueError(f"{self.path}: version {version} != {RESTART_VERSION}")
            self.generic = GenericHeader.unpack(fh.read(GENERIC_HEADER_BYTES))
            self.restart = RestartHeader.unpack(fh.read(RESTART_HEADER_BYTES))
            if self.generic.datatype != 4:
                raise ValueError(
                    f"{self.path}: datatype {self.generic.datatype}, expected 4 (double). "
                    "The v3 datatype codes are 0-BASED: 0=byte 1=short 2=int 3=float 4=double."
                )
            self.index = np.frombuffer(
                fh.read(8 * self.generic.ncell), dtype="<i8", count=self.generic.ncell
            ).copy()
        expected = PREFIX_BYTES + 8 * self.generic.ncell
        if int(self.index[0]) != expected:
            raise ValueError(
                f"{self.path}: index[0]={self.index[0]}, expected {expected} "
                f"(84 + 8*{self.generic.ncell}). The framing does not match."
            )
        if not bool(np.all(np.diff(self.index) > 0)):
            raise ValueError(f"{self.path}: cell offsets are not strictly increasing")
        self.layout = Layout.from_headers(self.generic, self.restart)

    @property
    def ncell(self) -> int:
        return self.generic.ncell

    def __enter__(self) -> RestartReader:
        self._fh = self.path.open("rb")
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def extent(self, cell: int) -> tuple[int, int]:
        """(start, end) byte offsets of a cell record. The last record ends at end-of-file."""
        if not 0 <= cell < self.ncell:
            raise IndexError(f"cell {cell} outside [0,{self.ncell})")
        start = int(self.index[cell])
        end = int(self.index[cell + 1]) if cell + 1 < self.ncell else self.filesize
        return start, end

    def cell_bytes(self, cell: int) -> bytes:
        start, end = self.extent(cell)
        if self._fh is not None:
            self._fh.seek(start)
            return self._fh.read(end - start)
        with self.path.open("rb") as fh:
            fh.seek(start)
            return fh.read(end - start)

    def cell_sizes(self) -> npt.NDArray[np.int64]:
        """Record length per cell, straight from the index -- no reading required."""
        return np.diff(np.append(self.index, self.filesize))

    def read(self, cell: int) -> dict[str, Any]:
        return read_cell(self.cell_bytes(cell), self.layout)


class RestartWriter:
    """Write a restart file for a chosen subset of cells, in the model's own framing.

    Used two ways: to prove the round-trip (write real records back and `cmp`), and to emit the
    emulator's product (write synthesised records the model will load). Both go through here so
    there is exactly one implementation of the framing.
    """

    def __init__(
        self,
        path: Path,
        generic: GenericHeader,
        restart: RestartHeader,
        ncell: int,
        firstcell: int | None = None,
    ) -> None:
        self.path = Path(path)
        self.generic = GenericHeader(**{**generic.__dict__})
        self.generic.ncell = ncell
        if firstcell is not None:
            self.generic.firstcell = firstcell
        self.restart = restart
        self.ncell = ncell
        self._records: list[bytes] = []

    def append(self, record: bytes) -> None:
        self._records.append(record)

    def close(self) -> None:
        if len(self._records) != self.ncell:
            raise ValueError(f"declared ncell={self.ncell} but appended {len(self._records)}")
        offsets = np.empty(self.ncell, dtype="<i8")
        pos = PREFIX_BYTES + 8 * self.ncell
        for i, rec in enumerate(self._records):
            offsets[i] = pos
            pos += len(rec)
        with self.path.open("wb") as fh:
            fh.write(RESTART_MAGIC)
            fh.write(struct.pack("<i", RESTART_VERSION))
            fh.write(self.generic.pack())
            fh.write(self.restart.pack())
            fh.write(offsets.tobytes())
            for rec in self._records:
                fh.write(rec)

    def __enter__(self) -> RestartWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        if not exc or exc[0] is None:
            self.close()
