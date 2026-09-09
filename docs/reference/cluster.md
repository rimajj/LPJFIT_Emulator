# The PIK cluster — the facts that change how you work

Loaded on demand, not at session start. Everything here is `[VERIFIED 2026-09-02]` against the live
cluster unless marked. If a fact here contradicts what you observe, trust the observation and fix
this file.

---

## Partitions and QOS

The QOS must **match** the partition, and omitting it fails at submit time with
`Invalid qos specification` — which reads like a permissions problem rather than a missing field.
`scripts/sbatch_py.sh` derives the default from the partition for exactly that reason.

| partition | nodes | per-job cap | use it for |
|---|---|---|---|
| `standard` | 180 | up to 2048 CPU | anything large; the default |
| `priority` | 60, usually mostly idle | **64 CPU / 350 GB**, not raisable | anything that would otherwise queue — it starts almost immediately |
| `gpu` | 12 × 4 GPUs | — | training |

| QOS | wall | CPU | pair with |
|---|---|---|---|
| `short` | 1 day | 2048 | `standard` (our default) |
| `medium` | 7 days | 1024 | a campaign needing more than a day per job |
| `long` | 30 days | 32 | rare |
| `priority` | 1 day | — | `priority` partition |
| `gpushort` / `gpumedium` / `gpulong` | 1 / 7 / 30 days | — | `gpu` |

Nodes are 128 CPU / ~700 GB, and memory is strictly proportional to CPUs
(`DefMemPerCPU = MaxMemPerCPU = 5468 MB`, `SelectTypeParameters=CR_CPU_MEMORY`). So `priority`'s
64-CPU cap is a **350 GB ceiling** and is not negotiable — anything needing more memory goes to
`standard`. A pending job can be moved with
`scontrol update job <id> Partition=priority QOS=priority`; it is rejected if it asks for >64 CPU,
which is the tell.

Account: `waldspektrum`.

---

## Four traps that produce a wrong verdict rather than an error

**1. A silent log does not mean a hung job.** Python (and Julia) block-buffer stdout to a file, so a
perfectly healthy job's log stays empty until it exits. A predecessor session nearly killed a
22-minute probe over this. **Judge a silent job by `sacct` CPU time**, never by log length:

```bash
sacct -j <jobid> --format=JobID,State,TotalCPU,Elapsed,MaxRSS,ExitCode
```

`tools/campaigns.py status` does this for you and says so in its output every time. Our wrapper also
sets `PYTHONUNBUFFERED=1`, so this bites less here than it did there — but `sacct` is still the
authority.

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
