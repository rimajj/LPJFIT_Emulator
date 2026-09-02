#!/usr/bin/env python3
"""The campaign ledger: every SLURM submission, its liveness, and whether it was harvested.

    tools/campaigns.py launch  --line D --tag D-corpus-v0 --job 1772586 [--exp ...] [...]
    tools/campaigns.py probe   [--line D]        # append a liveness row from sacct (the sweeper)
    tools/campaigns.py harvest --tag D-corpus-v0 --exit 0 [--artifact-sha256 ...]
    tools/campaigns.py dead    --tag D-train-b7  --exit 137 --reason "OOM at 350 GB on priority"
    tools/campaigns.py abandon --tag D-scan-a2   --reason "superseded by a3; no harvest needed"
    tools/campaigns.py status  [--line D] [--format hook|text|json]
    tools/campaigns.py --check                   # the `campaigns` CI gate

WHY THIS EXISTS -- the biggest gap the predecessor had.

Results here arrive HOURS TO DAYS after the session that launched them has ended. No document a dead
session could have written makes a live session go and look. So the launch row is written by the
submission wrapper ITSELF (and raw `sbatch` is denied by a hook, so there is no path to a job
without a row), liveness is appended by a login-node timer, the harvest row is written by the tool,
and every session start replays the open campaigns for its line.

A campaign stays OPEN until it is harvested, declared dead, or abandoned WITH A STATED REASON. An
overdue open campaign blocks the merge. That shape is copied deliberately from the one integrator
chore in the predecessor that provably worked -- changelog collation inside the merge lock, gated by
CI -- and applied to the chore that provably did not exist at all.

⚠ LIVENESS IS READ FROM `sacct` CPU TIME, NEVER FROM LOG LENGTH. Python block-buffers stdout to a
file, so a perfectly healthy job's log stays empty until it exits. The predecessor lost a 22-minute
probe to that confusion; the status output says so explicitly every time.

Per-line FILES (`campaigns/<L>/ledger.jsonl`), never sections of one shared file: with one writer
per file, appends never conflict. Status is DERIVED by folding rows, so the file stays pure-append
and append-only-ness is checkable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import repo_root

OPEN_EVENTS = {"launch", "probe"}
CLOSE_EVENTS = {"harvest", "dead", "abandon"}
EVENTS = OPEN_EVENTS | CLOSE_EVENTS
OVERDUE_GATE_DAYS = 7


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ledger_path(line: str) -> Path:
    return repo_root() / "campaigns" / line / "ledger.jsonl"


def read_ledger(line: str) -> list[dict]:
    p = ledger_path(line)
    if not p.exists():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line_text = raw.strip()
        if line_text:
            out.append(json.loads(line_text))
    return out


def append(line: str, row: dict) -> None:
    p = ledger_path(line)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def known_lines() -> list[str]:
    base = repo_root() / "campaigns"
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith("."))


# --------------------------------------------------------------------------------------------------
# Folding rows into state
# --------------------------------------------------------------------------------------------------


@dataclass
class Campaign:
    tag: str
    line: str
    rows: list[dict] = field(default_factory=list)

    @property
    def latest(self) -> dict:
        return self.rows[-1]

    @property
    def launch(self) -> dict:
        for r in self.rows:
            if r.get("event") == "launch":
                return r
        return self.rows[0]

    @property
    def is_open(self) -> bool:
        return str(self.latest.get("event")) in OPEN_EVENTS

    @property
    def job_ids(self) -> list[str]:
        return [str(j) for j in self.launch.get("job_ids", [])]

    @property
    def harvest_by(self) -> str:
        return str(self.launch.get("harvest_by", ""))

    def overdue_days(self) -> float | None:
        hb = self.harvest_by
        if not hb:
            return None
        try:
            ts = time.mktime(time.strptime(hb[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return None
        return (time.time() - ts) / 86400.0

    def age_hours(self) -> float:
        try:
            ts = time.mktime(
                time.strptime(str(self.launch.get("ts", ""))[:19], "%Y-%m-%dT%H:%M:%S")
            )
        except ValueError:
            return 0.0
        return (time.time() - ts) / 3600.0


def campaigns_for(line: str) -> list[Campaign]:
    by_tag: dict[str, Campaign] = {}
    for r in read_ledger(line):
        tag = str(r.get("tag", ""))
        if not tag:
            continue
        by_tag.setdefault(tag, Campaign(tag=tag, line=line)).rows.append(r)
    return sorted(by_tag.values(), key=lambda c: c.launch.get("ts", ""))


def find(tag: str) -> Campaign | None:
    for line in known_lines():
        for c in campaigns_for(line):
            if c.tag == tag:
                return c
    return None


# --------------------------------------------------------------------------------------------------
# sacct liveness
# --------------------------------------------------------------------------------------------------


def sacct(job_ids: list[str]) -> dict[str, dict[str, str]]:
    """State / TotalCPU / Elapsed / MaxRSS per job id, or {} if sacct is unavailable.

    Wrapped in a hard timeout and a broad except: a slow or missing scheduler must degrade to
    "unknown", never block a session start or crash the sweeper.
    """
    if not job_ids:
        return {}
    try:
        out = subprocess.run(
            [
                "sacct",
                "-n",
                "-P",
                "-j",
                ",".join(job_ids),
                "--format=JobID,State,TotalCPU,Elapsed,MaxRSS,ExitCode",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    res: dict[str, dict[str, str]] = {}
    for ln in out.splitlines():
        parts = ln.split("|")
        if len(parts) < 6:
            continue
        jid = parts[0].split(".")[0]
        # The parent row (no ".batch"/".extern" suffix) is the authoritative one.
        if jid not in res or "." not in parts[0]:
            res[jid] = {
                "state": parts[1],
                "total_cpu": parts[2],
                "elapsed": parts[3],
                "max_rss": parts[4],
                "exit_code": parts[5],
            }
    return res


# --------------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------------


def cmd_launch(a: argparse.Namespace) -> int:
    row = {
        "ts": now(),
        "event": "launch",
        "line": a.line,
        "tag": a.tag,
        "job_ids": [str(j) for j in a.job],
        "array": a.array or "",
        "exp_id": a.exp or "",
        "prereg_sha256": a.prereg_sha256 or "",
        "code_commit": subprocess.run(
            ["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip(),
        "cmd": a.cmd or "",
        "partition": a.partition or "",
        "cpus": a.cpus,
        "log_glob": a.log_glob or "",
        "sentinel": f"=== JOB DONE tag={a.tag} exit=",
        "expect_outputs": a.expect or [],
        "harvest_cmd": a.harvest_cmd or "",
        "harvest_by": a.harvest_by or "",
        "est_core_hours": a.est_core_hours,
    }
    append(a.line, row)
    print(
        f"campaign launched: {a.tag} job(s) {','.join(row['job_ids'])} "
        f"-> campaigns/{a.line}/ledger.jsonl"
    )
    return 0


def cmd_probe(a: argparse.Namespace) -> int:
    lines = [a.line] if a.line else known_lines()
    inbox = repo_root() / "campaigns" / ".inbox"
    n = 0
    for line in lines:
        for c in campaigns_for(line):
            if not c.is_open:
                continue
            info = sacct(c.job_ids)
            if not info:
                continue
            first = next(iter(info.values()))
            state = first.get("state", "UNKNOWN").split()[0]
            row = {
                "ts": now(),
                "event": "probe",
                "line": line,
                "tag": c.tag,
                "state": state,
                "total_cpu": first.get("total_cpu", ""),
                "elapsed": first.get("elapsed", ""),
                "max_rss": first.get("max_rss", ""),
                "note": "an empty log is EXPECTED (python block-buffers to a file)",
            }
            terminal = state in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "CANCELLED", "NODE_FAIL"}
            if terminal:
                row["event"] = "dead"
                row["exit"] = first.get("exit_code", "")
                row["reason"] = f"scheduler reported {state}"
            append(line, row)
            n += 1
            # Push, don't poll: leave a note the next session's start hook will surface.
            if terminal or state == "COMPLETED":
                inbox.mkdir(parents=True, exist_ok=True)
                (inbox / f"{c.tag}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(f"probed {n} open campaign(s)")
    return 0


def _close(a: argparse.Namespace, event: str) -> int:
    c = find(a.tag)
    if c is None:
        print(f"campaigns: no campaign tagged {a.tag!r}", file=sys.stderr)
        return 2
    if event in {"dead", "abandon"} and not a.reason:
        print(f"campaigns: --reason is required for `{event}`", file=sys.stderr)
        print(
            "  'forget about it' must be a recorded, reviewable act -- otherwise it is exactly the",
            file=sys.stderr,
        )
        print("  shape of a chore that rots.", file=sys.stderr)
        return 2
    row = {"ts": now(), "event": event, "line": c.line, "tag": a.tag}
    if a.reason:
        row["reason"] = a.reason
    if getattr(a, "exit", None) is not None:
        row["exit"] = a.exit
    if getattr(a, "artifact_sha256", None):
        row["artifact_sha256"] = a.artifact_sha256
    if getattr(a, "rows_out", None) is not None:
        row["rows_out"] = a.rows_out
    append(c.line, row)
    print(f"campaign {a.tag} closed as `{event}`")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    lines = [a.line] if a.line else known_lines()
    records = []
    for line in lines:
        for c in campaigns_for(line):
            if c.is_open or a.all:
                records.append(c)

    if a.format == "json":
        print(
            json.dumps(
                [
                    {
                        "tag": c.tag,
                        "line": c.line,
                        "open": c.is_open,
                        "job_ids": c.job_ids,
                        "state": c.latest.get("state", c.latest.get("event")),
                        "harvest_by": c.harvest_by,
                        "overdue_days": c.overdue_days(),
                        "exp_id": c.launch.get("exp_id", ""),
                    }
                    for c in records
                ],
                indent=2,
            )
        )
        return 0

    if not records:
        if a.format != "hook":
            print("no open campaigns")
        return 0

    hdr = (
        f"OPEN SLURM CAMPAIGNS{' FOR LINE ' + a.line if a.line else ''} (campaigns/*/ledger.jsonl)"
    )
    print(hdr)
    print("  these were launched by a session that has since ended:")
    for c in records:
        info = sacct(c.job_ids)
        first = next(iter(info.values()), {})
        # `sacct` answers nothing for a job it has purged, or when the scheduler is unreachable.
        # Splitting an empty string yields an empty list, so indexing it crashed the session-start
        # hook -- the one place that must NEVER fail, because it is what makes an orphaned campaign
        # visible at all. Degrade to the last recorded event instead.
        raw_state = str(first.get("state", "")).split()
        state = (
            raw_state[0] if raw_state else str(c.latest.get("state", c.latest.get("event", "?")))
        )
        cpu = first.get("total_cpu", "")
        overdue = c.overdue_days()
        flag = ""
        if overdue is not None and overdue > 0:
            flag = f"  ** {overdue:.1f} d PAST harvest_by -- BLOCKS MERGE **"
        print(
            f"  {c.tag:24s} job {','.join(c.job_ids) or '?':12s} "
            f"{c.age_hours():.0f} h ago  {state}{flag}"
        )
        if c.launch.get("exp_id"):
            print(f"      exp={c.launch['exp_id']}")
        if cpu:
            print(
                f"      liveness: sacct TotalCPU {cpu} (judge silence by THIS, not by log length --"
            )
            print("                python block-buffers stdout, so a healthy job's log is empty)")
        else:
            print("      liveness: sacct gave no answer (scheduler slow or job purged)")
        if c.launch.get("harvest_cmd"):
            print(f"      harvest:  {c.launch['harvest_cmd']}")
        print(f"      or close: tools/campaigns.py dead --tag {c.tag} --exit <n> --reason '<why>'")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    """The `campaigns` CI gate (main only)."""
    findings: list[str] = []
    for line in known_lines():
        rows = read_ledger(line)
        for i, r in enumerate(rows, start=1):
            ev = str(r.get("event", ""))
            if ev not in EVENTS:
                findings.append(f"campaigns/{line}/ledger.jsonl:{i}: unknown event {ev!r}")
            if ev in {"dead", "abandon"} and not str(r.get("reason", "")).strip():
                findings.append(
                    f"campaigns/{line}/ledger.jsonl:{i}: `{ev}` with no reason -- "
                    "closing a campaign must be a reviewable act"
                )
        for c in campaigns_for(line):
            if not c.is_open:
                continue
            od = c.overdue_days()
            if od is not None and od > OVERDUE_GATE_DAYS:
                findings.append(
                    f"campaigns/{line}/ledger.jsonl: campaign {c.tag!r} is open and {od:.0f} days "
                    f"past its harvest deadline -- harvest it, or close it with a reason"
                )
    if findings:
        print(f"campaigns: {len(findings)} finding(s)", file=sys.stderr)
        for f in findings:
            print(f, file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="run the CI gate and exit")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("launch")
    p.add_argument("--line", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--job", nargs="+", required=True)
    p.add_argument("--array", default="")
    p.add_argument("--exp", default="")
    p.add_argument("--prereg-sha256", dest="prereg_sha256", default="")
    p.add_argument("--cmd", default="")
    p.add_argument("--partition", default="")
    p.add_argument("--cpus", type=int, default=0)
    p.add_argument("--log-glob", dest="log_glob", default="")
    p.add_argument("--expect", nargs="*", default=[])
    p.add_argument("--harvest-cmd", dest="harvest_cmd", default="")
    p.add_argument("--harvest-by", dest="harvest_by", default="")
    p.add_argument("--est-core-hours", dest="est_core_hours", type=float, default=0.0)
    p.set_defaults(fn=cmd_launch)

    p = sub.add_parser("probe")
    p.add_argument("--line", default="")
    p.set_defaults(fn=cmd_probe)

    for ev in ("harvest", "dead", "abandon"):
        p = sub.add_parser(ev)
        p.add_argument("--tag", required=True)
        p.add_argument("--reason", default="")
        p.add_argument("--exit", type=int, default=None)
        p.add_argument("--artifact-sha256", dest="artifact_sha256", default="")
        p.add_argument("--rows-out", dest="rows_out", type=int, default=None)
        p.set_defaults(fn=lambda a, _ev=ev: _close(a, _ev))

    p = sub.add_parser("status")
    p.add_argument("--line", default="")
    p.add_argument("--format", choices=("text", "hook", "json"), default="text")
    p.add_argument("--all", action="store_true", help="include closed campaigns")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    if args.check:
        return cmd_check(args)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    if getattr(args, "line", None) == "":
        args.line = os.environ.get("VEGEMU_LINE", "")
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
