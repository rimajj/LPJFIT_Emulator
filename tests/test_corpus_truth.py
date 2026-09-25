"""The acceptance-truth planner and the packed task farm: naming, sharding, CO2, and the runner.

WHY THIS TEST EXISTS. The truth campaign is ~400,000 single-cell spin-ups, and every way it can go
wrong is silent until the core-hours are spent:

  * a SEED folded into the forcing path would regenerate the same climate per seed, so a two-seed
    difference would be model noise PLUS whatever the regeneration did;
  * a manifest split in CELL order puts every dense forest in one shard and every desert in another,
    so one NTASKS/TIME fits none of them, and a longest-member-last order holds the whole
    allocation open for one tail;
  * a non-default CO2 level written from 1700 is a STEP, not a constant: the model runs the first
    700 spin-up years at its built-in 276.59 ppm before the file starts (getco2.c:47);
  * and a packed farm that launches more than NTASKS members at once is not packed.

These tests run no model and touch no cluster path: every path helper below builds a plain `Path`,
and the runner is driven with a fake `srun` in a temporary directory.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _truth() -> ModuleType:
    name = "corpus_truth"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_forcing_is_seed_independent_and_runs_are_per_seed() -> None:
    m = _truth()
    assert "seed" not in m.forcing_dir.__code__.co_varnames[: m.forcing_dir.__code__.co_argcount]
    a, b = m.run_dir("v1", 42490, "ssp370", 1), m.run_dir("v1", 42490, "ssp370", 2)
    assert a != b and a.parts[-4:] == ("truth-v1", "s1", "c42490", "ssp370")
    assert m.forcing_dir("v1", 42490, "ssp370").parts[-3:] == ("truth-v1", "c42490", "ssp370")
    assert m.run_tag(42490, "historical", 2) == "c42490-historical-s2"
    assert m.config_path("v1", 42490, "ssp126", 1).name == "lpjml_spinup_c42490-ssp126-s1.js"


def test_contiguous_chunks_split_on_gaps_and_size() -> None:
    m = _truth()
    got = m.contiguous_chunks([5, 1, 2, 3, 9, 10, 4, 20], chunk=3)
    assert got == [range(1, 4), range(4, 6), range(9, 11), range(20, 21)]
    assert sum(len(r) for r in got) == 8


def test_deal_shards_balances_cost_and_orders_longest_first() -> None:
    m = _truth()
    rng = np.random.default_rng(0)
    est = list(rng.uniform(30, 540, size=1000))
    shards = m.deal_shards(est, shard_size=300)
    assert len(shards) == 4
    assert sorted(i for s in shards for i in s) == list(range(1000))
    totals = [sum(est[i] for i in s) for s in shards]
    assert max(totals) / min(totals) < 1.02
    for s in shards:
        costs = [est[i] for i in s]
        assert costs == sorted(costs, reverse=True)


def test_suggest_resources_bounds() -> None:
    m = _truth()
    r = m.suggest_resources(total_s=8000 * 220.0, longest_s=530.0, nmember=8000)
    assert 1 <= r["ntasks"] <= 2048
    assert re.fullmatch(r"\d\d:\d\d:00", r["time"])
    h, mm, _ = (int(x) for x in r["time"].split(":"))
    assert (h * 60 + mm) * 60 >= r["est_wall_h"] * 3600
    tiny = m.suggest_resources(total_s=100.0, longest_s=60.0, nmember=3)
    assert tiny["ntasks"] == 1 and tiny["time"] == "00:15:00"


def test_cost_model_is_monotone_and_never_negative() -> None:
    m = _truth()
    rng = np.random.default_rng(1)
    x = rng.uniform(3.6e5, 3.5e6, size=2000)
    y = np.maximum(20.0, 1.2e-4 * x - 30 + rng.normal(0, 30, size=x.size))
    model = m.fit_cost(x, y)
    pred = m.predict_cost(model, np.array([0.0, 3.6e5, 1e6, 2e6, 5e6]))
    assert (np.diff(pred) >= 0).all() and (pred > 0).all()


def _fake_cfg(new_signature: bool, calls: list[dict[str, object]]) -> SimpleNamespace:
    def old(dest: Path, ppm: float = 276.59) -> Path:
        calls.append({"ppm": ppm})
        return dest

    def new(dest: Path, ppm: float = 276.59, first_year: int = 1700, last_year: int = 2100) -> Path:
        calls.append({"ppm": ppm, "first_year": first_year, "last_year": last_year})
        return dest

    return SimpleNamespace(
        CO2_PREINDUSTRIAL_PPM=276.59,
        CO2_CONST_LASTYEAR=2100,
        write_constant_co2=new if new_signature else old,
    )


def test_pilot_co2_level_is_the_pilots_own_call(tmp_path: Path) -> None:
    m = _truth()
    calls: list[dict[str, object]] = []
    m.write_co2(_fake_cfg(False, calls), tmp_path / "co2.txt", 276.59)
    assert calls == [{"ppm": 276.59}]


def test_other_co2_level_refuses_without_first_year(tmp_path: Path) -> None:
    m = _truth()
    with pytest.raises(NotImplementedError, match="first_year"):
        m.write_co2(_fake_cfg(False, []), tmp_path / "co2.txt", 409.63)


def test_other_co2_level_starts_by_the_first_model_year(tmp_path: Path) -> None:
    m = _truth()
    calls: list[dict[str, object]] = []
    m.write_co2(_fake_cfg(True, calls), tmp_path / "co2.txt", 409.63)
    assert calls == [{"ppm": 409.63, "first_year": 1000, "last_year": 2100}]
    assert m.FIRST_MODEL_YEAR == 2000 - m.NSPINUP


def test_check_co2_file(tmp_path: Path) -> None:
    m = _truth()
    good = tmp_path / "good.txt"
    good.write_text("".join(f"{y}  276.59\n" for y in range(1700, 2101)))
    assert m.check_co2_file(good, 276.59)["first_year"] == 1700
    bad = tmp_path / "bad.txt"
    bad.write_text("1700  276.59\n1701  300.00\n")
    with pytest.raises(AssertionError, match="constant"):
        m.check_co2_file(bad, 276.59)
    # Another level from 1700 is a STEP at model year 1700, not a constant: refused.
    step = tmp_path / "step.txt"
    step.write_text("".join(f"{y}  409.63\n" for y in range(1700, 2101)))
    with pytest.raises(AssertionError, match="built-in"):
        m.check_co2_file(step, 409.63)
    ok = tmp_path / "ok.txt"
    ok.write_text("".join(f"{y}  409.63\n" for y in range(1000, 2101)))
    assert m.check_co2_file(ok, 409.63)["first_year"] == 1000


# ------------------------------------------------------------------------------------------------
# the packed task farm, driven with a fake srun
# ------------------------------------------------------------------------------------------------


def _runner_text() -> str:
    text = (ROOT / "scripts" / "sbatch_cmodel.sh").read_text()
    m = re.search(r"<<'RUNNEREOF'\n(.*?)\nRUNNEREOF\n", text, flags=re.DOTALL)
    assert m, "the runner heredoc was not found in sbatch_cmodel.sh"
    return m.group(1)


FAKE_SRUN = """#!/usr/bin/env bash
# Records start and end, sleeps, then prints the model's completion line (or not, for 'bad').
cfg="${@: -1}"
echo "S $(date +%s.%N)" >> "$EVENTS"
sleep 0.25
echo "E $(date +%s.%N)" >> "$EVENTS"
case "$cfg" in
  *bad*) echo "died" ;;
  *) echo "${FAKE_NAME:-lpjml} successfully terminated, 1 grid cells processed." ;;
esac
"""


def _run_farm(
    tmp_path: Path,
    *,
    nmember: int,
    maxpar: int | None,
    bad: int = 0,
    binary: str = "lpjml",
    prints: str = "lpjml",
) -> tuple[int, str, int]:
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "srun").write_text(FAKE_SRUN)
    (bindir / "srun").chmod(0o755)
    runner = tmp_path / "runner.sh"
    runner.write_text(_runner_text())
    manifest = tmp_path / "manifest.tsv"
    rows = []
    for i in range(nmember):
        cfg = f"cfg_{'bad' if i < bad else 'ok'}_{i}.js"
        rows.append(f"m{i}\t{cfg}\t{tmp_path / 'runs' / f'm{i}'}\n")
    manifest.write_text("".join(rows))
    events = tmp_path / "events.txt"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LPJBIN": f"/nonexistent/{binary}",
        "FAKE_NAME": prints,
        "LPJ_DEFS": "",
        "MANIFEST": str(manifest),
        "EVENTS": str(events),
    }
    env.pop("MAXPAR", None)
    if maxpar is not None:
        env["MAXPAR"] = str(maxpar)
    proc = subprocess.run(
        ["bash", str(runner)], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    level, peak = 0, 0
    stamps = sorted(
        (float(t), 1 if k == "S" else -1)
        for k, t in (ln.split() for ln in events.read_text().splitlines())
    )
    for _, step in stamps:
        level += step
        peak = max(peak, level)
    return proc.returncode, proc.stdout, peak


def test_packed_farm_never_exceeds_maxpar_and_runs_every_member(tmp_path: Path) -> None:
    rc, out, peak = _run_farm(tmp_path, nmember=12, maxpar=3)
    assert rc == 0, out
    assert "launched 12 of 12 members, at most 3 at a time" in out
    assert "completion line: 12 of 12" in out
    assert peak == 3


def test_packed_farm_fails_loudly_on_a_member_without_the_line(tmp_path: Path) -> None:
    rc, out, _ = _run_farm(tmp_path, nmember=6, maxpar=2, bad=1)
    assert rc != 0
    assert "MEMBER FAILED (no completion line): m0" in out
    assert "completion line: 5 of 6" in out


def test_unpacked_default_launches_all_at_once(tmp_path: Path) -> None:
    """Without MAXPAR the farm behaves exactly as before: every member in flight together."""
    rc, out, peak = _run_farm(tmp_path, nmember=5, maxpar=None)
    assert rc == 0 and peak == 5, out


def test_completion_line_is_the_binarys_own_name(tmp_path: Path) -> None:
    """The Feb-05 build prints `lpjml.pre_dgrass.bak successfully terminated` -- measured on the
    two-binary byte test -- so a fixed `^lpjml successfully` pattern would fail every run of it."""
    name = "lpjml.pre_dgrass.bak"
    rc, out, _ = _run_farm(tmp_path / "a", nmember=2, maxpar=2, binary=name, prints=name)
    assert rc == 0 and "completion line: 2 of 2" in out, out


def test_completion_line_of_another_binary_does_not_count(tmp_path: Path) -> None:
    """A different binary's line -- or the right name with its dots matched as wildcards -- is not
    the completion of THIS run."""
    name = "lpjml.pre_dgrass.bak"
    rc, out, _ = _run_farm(tmp_path / "a", nmember=2, maxpar=2, binary=name, prints="lpjml")
    assert rc != 0 and "completion line: 0 of 2" in out, out
    rc, out, _ = _run_farm(
        tmp_path / "b", nmember=2, maxpar=2, binary=name, prints="lpjmlXpre_dgrassXbak"
    )
    assert rc != 0 and "completion line: 0 of 2" in out, out


# ------------------------------------------------------------------------------------------------
# the outer wrapper's NTASKS, driven with a fake sbatch that records its call and then FAILS, so
# the wrapper stops before its ledger write and nothing reaches the cluster or the campaign ledger
# ------------------------------------------------------------------------------------------------

FAKE_SBATCH = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$SBATCH_ARGS"
cat > "$SBATCH_BODY"
exit 1
"""


def _submit(tmp_path: Path, argv: list[str], **knobs: str) -> tuple[int, str, list[str], str]:
    """Run `sbatch_cmodel.sh` up to its `sbatch` call; return (rc, stdout+stderr, args, body)."""
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    (bindir / "sbatch").write_text(FAKE_SBATCH)
    (bindir / "sbatch").chmod(0o755)
    # The wrapper resolves its paths with `python3 tools/_paths.py`; pin that to this interpreter so
    # the test does not depend on which `python3` the runner's PATH happens to hold.
    (bindir / "python3").write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n')
    (bindir / "python3").chmod(0o755)
    args_file, body_file = tmp_path / "sbatch_args.txt", tmp_path / "sbatch_body.txt"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LPJ_", "SBATCH", "SLURM"))}
    for k in ("NTASKS", "TIME", "PARTITION", "QOS", "EST_CORE_HOURS", "HARVEST_BY", "EXPECT"):
        env.pop(k, None)
    env.update(
        PATH=f"{bindir}:{os.environ['PATH']}",
        SBATCH_ARGS=str(args_file),
        SBATCH_BODY=str(body_file),
        **knobs,
    )
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "sbatch_cmodel.sh"), *argv],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    args = args_file.read_text().splitlines() if args_file.is_file() else []
    body = body_file.read_text() if body_file.is_file() else ""
    return proc.returncode, proc.stdout + proc.stderr, args, body


def _manifest(tmp_path: Path, n: int) -> Path:
    m = tmp_path / "farm" / "manifest.tsv"
    m.parent.mkdir(parents=True)
    m.write_text("".join(f"m{i}\tcfg_{i}.js\t{tmp_path / 'farm' / f'm{i}'}\n" for i in range(n)))
    return m


def test_wrapper_single_run_keeps_the_callers_ntasks(tmp_path: Path) -> None:
    """A single config is ONE run that `mpirun` spreads over NTASKS: it must never be clamped."""
    cfg = tmp_path / "run" / "lpjml.js"
    cfg.parent.mkdir()
    cfg.write_text("{}\n")
    rc, out, args, body = _submit(tmp_path, ["D-rev-x", str(cfg), str(cfg.parent)], NTASKS="4")
    assert rc != 0 and "submitted" not in out, out
    assert "--ntasks=4" in args, (args, out)
    assert "mpirun" in body
    rc, out, args, _ = _submit(tmp_path / "b", ["D-rev-x", str(cfg), str(cfg.parent)])
    assert "--ntasks=1" in args, (args, out)


def test_wrapper_manifest_defaults_to_one_cpu_per_member(tmp_path: Path) -> None:
    """The corpus pipeline sets no NTASKS: the farm must allocate one CPU per member, as before."""
    m = _manifest(tmp_path, 5)
    rc, out, args, body = _submit(tmp_path, ["--manifest", str(m), "D-rev-x"])
    assert rc != 0 and "submitted" not in out, out
    assert "--ntasks=5" in args and 'export MAXPAR="5"' in body, (args, body)
    assert "PACKED" not in out


def test_wrapper_manifest_packs_and_clamps(tmp_path: Path) -> None:
    m = _manifest(tmp_path, 5)
    _, out, args, body = _submit(tmp_path / "a", ["--manifest", str(m), "D-rev-x"], NTASKS="2")
    assert "--ntasks=2" in args and 'export MAXPAR="2"' in body and "PACKED" in out, out
    _, out, args, body = _submit(tmp_path / "b", ["--manifest", str(m), "D-rev-x"], NTASKS="9")
    assert "--ntasks=5" in args and 'export MAXPAR="5"' in body, (args, out)
