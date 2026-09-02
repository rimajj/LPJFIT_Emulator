#!/usr/bin/env python3
"""The scientific gate. Every error code names the lesson it encodes.

    E01  a required pre-registration key is missing, or an enum is unknown, or
         decision_rule.statistic != estimand.name
    E02  `nulls` is empty, or a null lacks expected.value / tolerance / derivation
    E03  the live pre-registration hash disagrees with experiments/registry.jsonl
    E04  a result row's prereg_sha256 != the sealed hash -- THE PRE-REGISTRATION WAS EDITED AFTER
         THE RUN
    E05  a result row reports a statistic that is not the blessed one
    E06  a result row's `nulls` object does not cover every null declared -- A REPORTED NUMBER WITH
         NO NULL
    E07  a measured null fell outside its pre-registered value +/- tolerance => verdict `invalid`
    E08  a null arm also satisfies pass_if => the estimand HAS NO POWER => verdict `invalid`
    E09  verdict.md's `outcome:` disagrees with the checker's own evaluation of the decision rule
    E10  verdict.md exists with no result rows, or its generated metrics block is stale
    E11  registry.jsonl or a result.jsonl was changed non-append-only versus the merge base
    E12  the seal commit is not an ancestor of the commit that introduced the first result row
    E13  a pre-registration has been sealed >30 days with no results and no `abandoned:` reason
    E14  estimand.reference_basis is empty, or data.leakage_checks is empty

Together these mechanise a discipline the predecessor had to learn by losing five headline claims:
report the null beside the number, derive what the null must return BEFORE the run, and treat a
metric the null also passes as having no power at all.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Report, base_parser, repo_root
from _experiments import (
    COMPARATORS,
    MULTIPLICITY,
    OUTCOMES,
    REQUIRED_TOP,
    SPLIT_KINDS,
    declared_outcome,
    evaluate,
    experiment_dirs,
    extract_metrics_block,
    load_experiment,
    load_jsonl,
    parse_pass_if,
    render_metrics_block,
    sha256_file,
)

STALE_SEAL_DAYS = 30


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root()), *args], capture_output=True, text=True, check=False
    ).stdout


def registry_index() -> dict[str, dict]:
    """exp_id -> the LAST seal row for it (a re-seal after a supersede is legitimate)."""
    rows = load_jsonl(repo_root() / "experiments" / "registry.jsonl")
    out: dict[str, dict] = {}
    for r in rows:
        eid = str(r.get("exp_id", ""))
        if eid:
            out[eid] = r
    return out


def check_schema(exp, rep: Report) -> None:
    rel = str(exp.prereg_path.relative_to(repo_root()))
    p = exp.prereg

    for key in REQUIRED_TOP:
        if key not in p:
            rep.add(rel, "E01", f"missing required key {key!r}")

    if str(p.get("exp_id", "")) != exp.directory.name:
        rep.add(
            rel,
            "E01",
            f"exp_id {p.get('exp_id')!r} does not match directory {exp.directory.name!r}",
            hint="the id carries the line and the date; it IS the collision-avoidance scheme",
        )

    if str(p.get("status", "")) not in ("draft", "sealed"):
        rep.add(rel, "E01", f"status must be draft or sealed, got {p.get('status')!r}")

    est = p.get("estimand", {}) or {}
    dr = p.get("decision_rule", {}) or {}
    if est.get("name") and dr.get("statistic") and est["name"] != dr["statistic"]:
        rep.add(
            rel,
            "E01",
            f"decision_rule.statistic {dr['statistic']!r} != estimand.name {est['name']!r}",
            hint=(
                "a pre-registered threshold on a different statistic is not a pre-registered "
                "verdict"
            ),
        )
    if dr.get("comparator") and str(dr["comparator"]) not in COMPARATORS:
        rep.add(
            rel,
            "E01",
            f"unknown comparator {dr['comparator']!r}; expected one of {sorted(COMPARATORS)}",
        )
    if dr.get("multiplicity") and str(dr["multiplicity"]) not in MULTIPLICITY:
        rep.add(rel, "E01", f"unknown multiplicity {dr['multiplicity']!r}")
    if dr.get("pass_if") is not None and parse_pass_if(dr["pass_if"]) is None:
        rep.add(
            rel,
            "E01",
            f"pass_if {dr['pass_if']!r} is not parseable",
            hint=(
                "use `> 0.02`, `>= 0.5`, `< 0.1` or `abs < 0.1` — a decision rule must not be "
                "arbitrary code"
            ),
        )

    data = p.get("data", {}) or {}
    split = data.get("split", {}) or {}
    if split.get("kind") and str(split["kind"]) not in SPLIT_KINDS:
        rep.add(
            rel,
            "E01",
            f"unknown split.kind {split['kind']!r}; expected one of {sorted(SPLIT_KINDS)}",
        )

    # E14 — the two fields that make a number interpretable at all.
    if not str(est.get("reference_basis", "")).strip():
        rep.add(
            rel,
            "E14",
            "estimand.reference_basis is empty",
            hint=(
                "state the reference, leg, years, PFT set, patch count and binary build — a number "
                "without its basis is not a result"
            ),
        )
    if not (data.get("leakage_checks") or []):
        rep.add(
            rel,
            "E14",
            "data.leakage_checks is empty",
            hint=(
                "name the checks you ran. Cross-validation by cell holds out SPACE, not time, so a "
                "lagged-truth feature makes the score teacher-forced"
            ),
        )

    # E02 — the heart of it.
    nulls = p.get("nulls") or []
    if not nulls:
        rep.add(
            rel,
            "E02",
            "no nulls declared",
            hint=(
                "at least one. A number with no null is not a result — this is the single most "
                "common way an exploration reports a discovery that is not there"
            ),
        )
    for i, n in enumerate(nulls):
        nid = n.get("id") or f"#{i}"
        e = n.get("expected", {}) or {}
        for field in ("value", "tolerance", "derivation"):
            if e.get(field) in (None, ""):
                rep.add(
                    rel,
                    "E02",
                    f"null {nid!r} lacks expected.{field}",
                    hint=(
                        "DERIVE what the null must return and write it down before the run; a null "
                        "that silently returned the wrong value is indistinguishable from one that "
                        "agreed with you"
                    ),
                )


def check_seal(exp, reg: dict[str, dict], rep: Report) -> None:
    rel = str(exp.prereg_path.relative_to(repo_root()))
    status = str(exp.prereg.get("status", "draft"))
    row = reg.get(exp.exp_id)

    if status != "sealed":
        if exp.results:
            rep.add(
                rel,
                "E03",
                "has result rows but is not sealed",
                hint="seal before you run: tools/seal_experiment.py <exp_id>",
            )
        return

    if row is None:
        rep.add(
            rel,
            "E03",
            "sealed but absent from experiments/registry.jsonl",
            hint=(
                "seal via tools/seal_experiment.py, which appends the ledger row — do not flip "
                "status by hand"
            ),
        )
        return

    live = sha256_file(exp.prereg_path)
    sealed = str(row.get("prereg_sha256", ""))
    if live != sealed:
        rep.add(
            rel,
            "E03",
            f"live hash {live[:12]} != sealed hash {sealed[:12]}",
            hint=(
                "a sealed pre-registration is immutable. A changed question is a NEW exp_id with "
                "`supersedes:` naming this one"
            ),
        )

    # E04 — the strongest statement the registry makes: the hash travelled with the job.
    for i, r in enumerate(exp.results, start=1):
        got = str(r.get("prereg_sha256", ""))
        if got and got != sealed:
            rep.add(
                f"experiments/{exp.exp_id}/result.jsonl",
                "E04",
                f"row {i} carries prereg hash {got[:12]}, sealed is {sealed[:12]}",
                line=i,
                hint=(
                    "THE PRE-REGISTRATION WAS EDITED AFTER THE RUN. The job stamped the hash it "
                    "actually ran under"
                ),
            )

    # E13 — a dead pre-registration becomes visible instead of silently rotting.
    if not exp.results and not exp.prereg.get("abandoned"):
        sealed_at = str(row.get("sealed_at", ""))
        try:
            ts = time.mktime(time.strptime(sealed_at[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return
        age = (time.time() - ts) / 86400.0
        if age > STALE_SEAL_DAYS:
            rep.add(
                rel,
                "E13",
                f"sealed {age:.0f} days ago with no results",
                hint=(
                    "harvest it, or add `abandoned: <reason>`. An unfinished experiment with no "
                    "reason is the shape of a chore that rots"
                ),
            )


def check_results(exp, rep: Report) -> None:
    rel = f"experiments/{exp.exp_id}/result.jsonl"
    stat = exp.statistic
    declared = set(exp.null_ids)

    for i, r in enumerate(exp.results, start=1):
        if r.get("statistic") and str(r["statistic"]) != stat:
            rep.add(
                rel,
                "E05",
                f"row {i} reports statistic {r['statistic']!r}, blessed is {stat!r}",
                line=i,
                hint=(
                    "only the pre-registered estimand may be reported; anything else is a "
                    "different question"
                ),
            )
        # E06 applies to the model arm: that is the row that makes a CLAIM.
        if r.get("arm") == "model":
            got = set((r.get("nulls") or {}).keys())
            miss = declared - got
            if miss:
                rep.add(
                    rel,
                    "E06",
                    f"row {i} omits null(s): {', '.join(sorted(miss))}",
                    line=i,
                    hint=(
                        "A REPORTED NUMBER WITH NO NULL. Every declared null must appear beside "
                        "the model's value"
                    ),
                )


def check_verdict(exp, rep: Report) -> None:
    path = exp.directory / "verdict.md"
    rel = f"experiments/{exp.exp_id}/verdict.md"
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    if not exp.results:
        rep.add(
            rel,
            "E10",
            "verdict exists with zero result rows",
            hint="harvest first; a verdict on no data is an opinion",
        )
        return

    ev = evaluate(exp)

    # E10 — regenerate and compare. The verdict may not assert; it may only record.
    want = render_metrics_block(exp, ev)
    have = extract_metrics_block(text)
    if have is None:
        rep.add(
            rel,
            "E10",
            "no generated metrics block",
            hint=(
                "run tools/render_verdict.py — the number and its null must land in the same table "
                "by construction, not by discipline"
            ),
        )
    elif have.strip() != want.strip():
        rep.add(
            rel,
            "E10",
            "generated metrics block is stale",
            hint="run tools/render_verdict.py to regenerate it from result.jsonl",
        )

    # E09 — the outcome is computed, never typed.
    said = declared_outcome(text)
    if said is None:
        rep.add(
            rel,
            "E09",
            "no `outcome:` field",
            hint=f"add `outcome: {ev.outcome}` — the checker computes it, you record it",
        )
    elif said not in OUTCOMES:
        rep.add(rel, "E09", f"unknown outcome {said!r}; expected one of {sorted(OUTCOMES)}")
    elif said != ev.outcome:
        rep.add(
            rel,
            "E09",
            f"verdict says {said!r}, the decision rule evaluates to {ev.outcome!r}",
            hint="; ".join(ev.reasons) or "recompute with tools/render_verdict.py",
        )

    # E07 / E08 — surfaced explicitly so the failure names its own lesson rather than hiding
    # inside an `invalid` outcome the reader has to decode.
    for a in ev.arms:
        if a.arm != "model" and a.within_expected is False:
            rep.add(
                rel,
                "E07",
                f"null {a.arm!r} returned {a.value:.6g}, pre-registered "
                f"{a.expected:.6g} +/- {a.tolerance:.6g}",
                hint=(
                    "the apparatus did not do what was declared => the experiment is INVALID, not "
                    "failing"
                ),
            )
    if ev.outcome == "invalid" and any("NO POWER" in r for r in ev.reasons):
        rep.add(
            rel,
            "E08",
            "a null also satisfies pass_if",
            hint="; ".join(r for r in ev.reasons if "NO POWER" in r),
        )


def check_append_only(rep: Report, ref: str) -> None:
    """E11/E12: the ledgers are append-only, and a seal precedes its own results.

    The comparison base is `merge-base(ref, HEAD)` where available. When `ref` does not resolve --
    a fresh clone, or before the first push, when there is no `origin/main` at all -- fall back to
    HEAD and compare the WORKING TREE against the last commit.

    That fallback is load-bearing rather than cosmetic. The first version returned early on a
    missing ref, so on a repo without a remote this check silently passed everything: a deliberate
    rewrite of a result ledger went undetected, and the test that was supposed to prove the gate
    works instead proved nothing. A checker that cannot run must say so, not report success.
    """
    base = _git("merge-base", ref, "HEAD").strip()
    if not base:
        base = _git("rev-parse", "HEAD").strip()
    if not base:
        # No commits at all: there is nothing to be append-only with respect to.
        return

    tracked = [
        p
        for p in _git("ls-files", "experiments").splitlines()
        if p.endswith(("registry.jsonl", "result.jsonl"))
    ]
    for rel in tracked:
        old = _git("show", f"{base}:{rel}")
        if not old:
            continue
        new_path = repo_root() / rel
        if not new_path.exists():
            rep.add(rel, "E11", "tracked append-only file was deleted")
            continue
        new = new_path.read_text(encoding="utf-8")
        old_lines = [ln for ln in old.splitlines() if ln.strip()]
        new_lines = [ln for ln in new.splitlines() if ln.strip()]
        if new_lines[: len(old_lines)] != old_lines:
            rep.add(
                rel,
                "E11",
                "not append-only: an existing line changed or was removed",
                hint=(
                    "results and seals are an immutable record. Append a correction row; never "
                    "rewrite history"
                ),
            )

    # E12 — the seal commit must be an ancestor of the first result-bearing commit.
    reg = registry_index()
    for d in experiment_dirs(repo_root()):
        exp_id = d.name
        row = reg.get(exp_id)
        res = d / "result.jsonl"
        if not row or not res.exists():
            continue
        seal_commit = str(row.get("seal_commit", "")).strip()
        if not seal_commit:
            continue
        rel = str(res.relative_to(repo_root()))
        first = _git("log", "--reverse", "--format=%H", "--", rel).splitlines()
        if not first:
            continue
        first_result_commit = first[0].strip()
        anc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root()),
                "merge-base",
                "--is-ancestor",
                seal_commit,
                first_result_commit,
            ],
            capture_output=True,
            check=False,
        )
        if anc.returncode not in (0,):
            rep.add(
                rel,
                "E12",
                f"seal commit {seal_commit[:12]} is not an ancestor of the first result "
                f"commit {first_result_commit[:12]}",
                hint=(
                    "the seal has to exist in history BEFORE the run it governs, or "
                    "'pre-registered' means nothing"
                ),
            )


def main(argv: list[str] | None = None) -> int:
    ap = base_parser(__doc__ or "")
    ap.add_argument("--exp", default=None, help="check a single experiment id")
    args = ap.parse_args(argv)

    root = repo_root()
    rep = Report("check_experiments")
    reg = registry_index()

    dirs = experiment_dirs(root)
    if args.exp:
        dirs = [d for d in dirs if d.name == args.exp]
        if not dirs:
            print(f"check_experiments: no such experiment {args.exp!r}", file=sys.stderr)
            return 2

    for d in dirs:
        try:
            exp = load_experiment(d)
        except Exception as exc:
            rep.add(f"experiments/{d.name}/preregistration.yaml", "E01", f"cannot load: {exc}")
            continue
        check_schema(exp, rep)
        check_seal(exp, reg, rep)
        check_results(exp, rep)
        check_verdict(exp, rep)

    check_append_only(rep, args.ref)
    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
