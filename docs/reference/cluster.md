# The PIK cluster — the facts that change how you work

Loaded on demand, not at session start. Everything here is `[VERIFIED 2026-09-02]` against the live
cluster unless marked. If a fact here contradicts what you observe, trust the observation and fix
this file.

---

## Partitions and QOS

The QOS must **match** the partition, and omitting it fails at submit time with
`Invalid qos specification` — which reads like a permissions problem rather than a missing field.
`scripts/sbatch_py.sh` derives the default from the partition for exactly that reason.

| partition | nodes | cap | use it for |
|---|---|---|---|
| `standard` | 180 | up to 2048 CPU per job | anything large; the default |
| `priority` | 60, **not idle** (below) | **64 CPU and 10 running jobs PER USER**, not per job | small jobs that would otherwise queue |
| `gpu` | 12 × 4 GPUs | — | training |

| QOS | wall | CPU | pair with |
|---|---|---|---|
| `short` | 1 day | 2048 per job | `standard` (our default) |
| `medium` | 7 days | 1024 per job | a campaign needing more than a day per job |
| `long` | 30 days | 32 per job | rare |
| `priority` | 1 day | 64 per USER, 10 jobs per user; 6144 over all users | `priority` partition |
| `gpushort` / `gpumedium` / `gpulong` | 1 / 7 / 30 days | — | `gpu` |

⚠ **`priority`'s 64 CPUs are ONE budget shared by all of your running jobs there** — corrected
2026-09-23 from `sacctmgr show qos priority`: `MaxTRESPerUser=cpu=64`, `MaxJobsPerUser=10`,
`GrpTRES=cpu=6144`, `Flags=DenyOnLimit`, and no per-job limit at all. So two 48-CPU jobs do not
both start — one runs, the other waits for it — and an 11th running job waits however small.
Several parallel sessions submitting there share that one budget. And it is **no longer
"usually mostly idle"**: at 2026-09-23 14:30, 5,917 of its 7,680 CPUs were allocated (77 %;
`sinfo -p priority -o %C`), so check before counting on an immediate start.

Nodes are 128 CPU / ~700 GB, and memory is strictly proportional to CPUs
(`DefMemPerCPU = MaxMemPerCPU = 5468 MB`, `SelectTypeParameters=CR_CPU_MEMORY`). So `priority`'s
64 CPUs are a **350 GB ceiling per user**, not negotiable — anything needing more memory goes to
`standard`. A pending job can be moved with
`scontrol update job <id> Partition=priority QOS=priority`; `DenyOnLimit` rejects one that alone
asks for >64 CPU, which is the tell.

Account: `waldspektrum`.

---

## Four traps that produce a wrong verdict rather than an error

**1. A silent log does not mean a hung job.** Python (and Julia) block-buffer stdout to a file, so a
perfectly healthy job's log stays empty until it exits. A predecessor session nearly killed a
22-minute probe over this. **Judge a silent job by CPU time, never by log length — `sstat` while it
runs, `sacct` once it has ended:**

```bash
sstat -j <jobid>.batch --format=JobID,AveCPU,MaxRSS          # RUNNING: AveCPU grows if it is alive
sacct -j <jobid> --format=JobID,State,TotalCPU,Elapsed,MaxRSS,ExitCode   # ENDED: the authority
```

⚠ **`sacct` reports `TotalCPU 00:00:00` for a step that is still running** — it only counts steps
that have ENDED — so on a single-step job (every `sbatch_py.sh` job) it reads zero for the job's
whole life, healthy or hung, and cannot tell the two apart. Measured 2026-09-23 on job 2280681:
at 25 s elapsed `sacct` gave `TotalCPU 00:00:00` for the job and its batch step while
`sstat -j 2280681.batch` gave `AveCPU 00:00:12`; by 4 min 44 s the job's `TotalCPU` read 04:00:31,
all of it from its 250 `srun` steps that had already finished, and the running batch step still
read 00:00:00. For a job whose work is in `srun` steps, `sstat -j <jobid>.<step>` reads a step
that is still running (it errors on one that has ended). ⚠ `tools/campaigns.py status` and `probe`
still read liveness from `sacct` `TotalCPU`, so for a RUNNING job their "liveness" line shows zero
and means nothing; use `sstat`. Our wrapper also sets `PYTHONUNBUFFERED=1`, so a silent log bites
less here than it did in the predecessor.

**2. The opposite trap, for the C model: a zero-byte log after minutes IS a dead job.** A healthy
2048-task run creates its output files within **~15 seconds** (~833 MB across 7 files). A member
sitting at zero output files and a zero-byte log after 67 minutes was hung on a flaky node — a 268×
discrepancy. **Check the output directory a minute after launch; do not wait out a silent 2048-CPU
job.** Resubmit with `--exclude=<node>` on the command line.

**3. Compute nodes cannot read the login node's `/tmp`.** Anything a job reads or writes must be on
shared `/p`. The wrapper refuses a `/tmp` job path outright. The same applies to a session-local
scratch directory under `/tmp/claude-*` — a job cannot open it.

**4. Compute nodes have no GitHub egress; the login node does (over SSH only).** So any package cache
a job needs must be warmed on the login node first. GitHub HTTPS is blocked everywhere.

---

## Five more of the same kind, found on line D

Same failure mode as the four above — the job exits 0 and the log agrees with itself, so only a
second, independent signal catches it. Recorded here rather than in a line's `STATE.md` because
every line hits them.

**5. Never judge a C model run by its exit code.** Require the model's own line `lpjml successfully
terminated, <n> grid cells processed.` in a non-empty log. `sbatch_cmodel.sh` writes that grep into
the ledger row as the harvest command, so the check is the artifact rather than a habit.

**6. `srun` forwards its stdin to the task**, and inside `while read … done < manifest` that stdin
IS the manifest. It swallowed 18 of 25 lines, the job exited 0, and the log said "7 of 7" because
the counter came from the same starved loop. Redirect the member from `/dev/null`; count off the
file, never off the loop.

**7. polars does not survive `fork`: a forked worker that touches a DataFrame hangs forever** — no
error, no traceback — so the job burns its wall-clock limit with an empty log, which reads as a slow
filesystem. Workers return plain dicts and the parent builds the frame. `corpus.climate` splits
`climate_columns` (numpy, fork-safe) from `climate_table` (parent only).

**8. A complete campaign is not a usable corpus.** Judge the runs by the model's own completion
line, then judge the CORPUS separately. Restart byte size is a free proxy — ≈360 KB with no
vegetation, ≈1.9 MB with a forest — and cost tracks it (1 min treeless, 3–8 min forested). The
pilot agreed two ways: 374/6,000 treeless by bytes against 380/6,000 by decoded stem count.

**9. Do not export `ALLOW_LOGIN_HEAVY` before running the test suite.** The login-node guard allows
unconditionally when it, `ALLOW_RAW_SBATCH` or `SLURM_JOB_ID` is set, and it inherits the session
environment — so every must-deny case in `tests/test_slurm_guard.py` went red at once, which reads
as "the guard is broken". The test now strips all three; the trap is the general one, so strip the
environment you are asserting about.

---

## Flaky nodes

`standard` nodes intermittently misbehave: exit `0:53` with no log, hung MPI, or a ~20× slowdown. If a
job file that has demonstrably worked before fails, suspect the node before the code. Mitigate with
`--exclusive` and an explicit `--exclude=`; pass it on the **command line** so a provenance-bearing
job file stays byte-identical.

---

## Software

| what | where |
|---|---|
| Python 3.11.9 + torch 2.5.1+cu124, polars 1.33, pyarrow 23, netCDF4 1.7.2, numpy 2.2.6, scipy, sklearn, lightgbm | `/home/jamirp/.conda/envs/py311_new/bin/python` (`config/paths.yaml: cluster.python`) |
| the LPJmL-FIT model | see `config/paths.yaml: lpjml` |

⚠ **GitHub SSH to this remote fails intermittently and the error looks exactly like a revoked key**
(`Permission denied (publickey)` + "make sure you have the correct access rights"), then succeeds on
the next attempt. Before escalating, retry:

```bash
for i in 1 2 3 4 5; do git fetch origin && break; sleep 5; done
```

And the second-order trap: when the *fetch* is what failed, `git rev-parse origin/<branch>` answers
from the last successful fetch, so a branch pushed hours ago can look unpushed. Re-fetch
successfully **first**, then read the refs.

⚠ **`/p` can return EIO for ~15 minutes and then recover.** Prove permanence before declaring data
loss: diagnose with `dd`, not with git (git dies with SIGBUS on an unreadable object, which looks like
repository corruption). `/home` and `/p/tmp` are separate mounts and are usually unaffected.

---

## Checking CI

`gh` is not reliably on PATH. Use the REST API with the token, which lives **outside every worktree**
on purpose — that is why rotating it covers every line at once with nothing to commit, and why
writing it into a file would break CI polling for all lines simultaneously (GitHub auto-revokes a
pushed token).

```bash
TOKEN=$(python3 -c "import yaml;print(yaml.safe_load(open('/home/jamirp/.config/gh/hosts.yml'))['github.com']['oauth_token'])")
curl -s -H "Authorization: token $TOKEN" https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs
```

**Decide which checks to expect BEFORE polling**: `tools/expected_gates.py`. A workflow skipped by its
path filter reports *no status at all*, not "skipped", so waiting for a gate that will not run hangs
forever. If it prints `(none)`, there is no verdict coming.

⚠ **`expected_gates.py` answers a different question than `wait_gates.py` needs, and the two disagree
exactly when your last push was documentation.** It computes from the diff **against `origin/main`**,
i.e. everything the branch would merge — which is the right basis for deciding whether to merge. But a
push only starts the workflows whose path filters match **that push**. So on a branch whose cumulative
diff touches `src/**`, a docs-only push prints `types, test, flags` among the expected gates and then
runs none of them, and `wait_gates.py` hangs on gates that will never appear (measured 2026-09-09:
predicted six, three ran).

That is not a wrong answer, and the fix is not to distrust it. Ask which gates ran for **this head sha**
and compare paths:

```bash
gh run list --branch line/<L> --limit 15 --json name,status,conclusion,headSha
git diff --name-only <sha-of-their-last-green-run>..HEAD -- src tests pyproject.toml
```

If that diff is **empty**, the missing gates' last green run still covers the current tree and the
branch is mergeable — the gate did not skip because something was wrong, it skipped because nothing it
guards changed. `src/**` is the filter for `types` and `test`; `flags` adds `config/flags.toml`,
`.github/gates.toml` and `tools/check_gates.py`. Verify locally too (`mypy --strict src/vegemu`,
`PYTHONPATH=src pytest -q`) rather than inferring green from an absence.

---

## Storage

| path | for |
|---|---|
| `/p/projects/open/Jamir/vegemu` | this repo (integration worktree, `main`) |
| `/p/projects/open/Jamir/vg-{D,T,X}` | the line worktrees |
| `/p/tmp/jamirp/vegemu/` | everything large: corpus shards, run directories, checkpoints, metrics |
| `/p/projects/waldspektrum/priesner/clustering/global` | the LPJmL-FIT inputs and ground truth (read-only) |

Never write to another line's `/p/tmp` subtree, and never overwrite a shared artifact in place —
version it. Nothing large is ever committed; provenance is a per-shard `provenance.json` plus the
corpus manifest hash that an experiment's pre-registration cites.
