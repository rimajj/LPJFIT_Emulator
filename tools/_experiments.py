"""Shared model of an experiment: load, validate, evaluate the decision rule, render the verdict.

This module exists so that `check_experiments.py` and `render_verdict.py` evaluate the pass/fail
decision with THE SAME CODE. That is what makes the verdict recomputable rather than assertable: the
checker regenerates the metrics block and the outcome and compares them to what is committed, so a
verdict cannot claim a result its own numbers do not support.

The predecessor's failure mode this is built against: a pre-registered THRESHOLD is not a
pre-registered VERDICT. There, an expression was evaluated against the wrong statistic, so the
pre-registration was formally satisfied by a number nobody had promised.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BEGIN_MARK = "<!-- BEGIN GENERATED metrics (tools/render_verdict.py) -->"
END_MARK = "<!-- END GENERATED -->"

SPLIT_KINDS = {"kfold_by_cell", "blocked_spatial", "holdout_perturbation", "holdout_forcing_leg"}
COMPARATORS = {"model_minus_best_null", "model_absolute"}
MULTIPLICITY = {"none", "bonferroni", "holm"}
OUTCOMES = {"pass", "fail", "invalid"}

REQUIRED_TOP = (
    "schema_version",
    "exp_id",
    "line",
    "status",
    "title",
    "question",
    "estimand",
    "data",
    "nulls",
    "decision_rule",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------------
# pass_if
# --------------------------------------------------------------------------------------------------

_PASS_RE = re.compile(r"^\s*(abs\s+)?(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*$")


@dataclass(frozen=True)
class PassRule:
    use_abs: bool
    op: str
    threshold: float

    def holds(self, value: float) -> bool:
        v = abs(value) if self.use_abs else value
        if self.op == ">":
            return v > self.threshold
        if self.op == ">=":
            return v >= self.threshold
        if self.op == "<":
            return v < self.threshold
        return v <= self.threshold

    def render(self) -> str:
        return f"{'abs ' if self.use_abs else ''}{self.op} {self.threshold:g}"


def parse_pass_if(text: str) -> PassRule | None:
    """Parse `pass_if`. Deliberately NOT eval(): a decision rule must not be arbitrary code."""
    m = _PASS_RE.match(str(text))
    if not m:
        return None
    return PassRule(use_abs=bool(m.group(1)), op=m.group(2), threshold=float(m.group(3)))


# --------------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------------


@dataclass
class Experiment:
    exp_id: str
    directory: Path
    prereg: dict[str, Any]
    prereg_path: Path
    results: list[dict[str, Any]]

    @property
    def statistic(self) -> str:
        return str(self.prereg.get("decision_rule", {}).get("statistic", ""))

    @property
    def null_ids(self) -> list[str]:
        return [str(n.get("id", "")) for n in self.prereg.get("nulls", []) or []]

    def rows_for(self, arm: str) -> list[dict[str, Any]]:
        return [r for r in self.results if r.get("arm") == arm]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{i}: not valid JSON: {exc}") from None
        out.append(obj)
    return out


def load_experiment(directory: Path) -> Experiment:
    prereg_path = directory / "preregistration.yaml"
    prereg = yaml.safe_load(prereg_path.read_text(encoding="utf-8")) or {}
    return Experiment(
        exp_id=str(prereg.get("exp_id", directory.name)),
        directory=directory,
        prereg=prereg,
        prereg_path=prereg_path,
        results=load_jsonl(directory / "result.jsonl"),
    )


def registry_lookup(root: Path, exp_id: str) -> str | None:
    """The sealed pre-registration hash for `exp_id`, or None if it was never sealed.

    The LAST matching row wins: a re-seal is legitimate when an experiment supersedes another.
    """
    rows = load_jsonl(root / "experiments" / "registry.jsonl")
    digest: str | None = None
    for r in rows:
        if str(r.get("exp_id", "")) == exp_id and r.get("prereg_sha256"):
            digest = str(r["prereg_sha256"])
    return digest


def experiment_dirs(root: Path) -> list[Path]:
    """Every real experiment directory. `_template` and anything else underscored is skipped."""
    base = root / "experiments"
    if not base.exists():
        return []
    return sorted(
        d
        for d in base.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "preregistration.yaml").exists()
    )


# --------------------------------------------------------------------------------------------------
# Evaluation — the single source of the verdict
# --------------------------------------------------------------------------------------------------


@dataclass
class ArmValue:
    arm: str
    value: float | None
    expected: float | None = None
    tolerance: float | None = None

    @property
    def within_expected(self) -> bool | None:
        if self.value is None or self.expected is None or self.tolerance is None:
            return None
        return abs(self.value - self.expected) <= self.tolerance


@dataclass
class Evaluation:
    statistic: str
    rule: PassRule | None
    model: float | None
    arms: list[ArmValue]
    best_null: str | None
    best_null_value: float | None
    margin: float | None
    outcome: str
    reasons: list[str]


def _latest(rows: list[dict[str, Any]], statistic: str) -> float | None:
    """The last row for this arm reporting the blessed statistic. Append-only => last wins."""
    vals = [r.get("value") for r in rows if r.get("statistic") == statistic]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return float(vals[-1]) if vals else None


def _powerless_nulls(null_arms: list[ArmValue], rule: PassRule, comparator: str) -> list[ArmValue]:
    """Nulls that themselves satisfy the pass rule.

    If one does, the metric cannot tell the model from a thing that knows nothing, so the estimand
    has no power and no conclusion is licensed. This is the check that would have killed the
    predecessor's headline 0.9824-against-a-0.9622-persistence-null claim at source.

    A null is judged on the SAME comparator as the model, so the comparison is like for like: under
    `model_absolute` that is its own value; under `model_minus_best_null` it is the null minus the
    best OTHER null, which is exactly the quantity the model is scored on.

    ⚠ EVERY comparison here tests `is not None`, never truthiness. `x or default` treats a
    legitimate 0.0 as missing -- and 0.0 is exactly what an ANALYTIC null is designed to return:
    the no-change null of a response experiment returns precisely 0.0 by construction. With
    `b.value or float("-inf")` that null dropped out of the `others` list, the next null's margin
    was measured against a NEGATIVE arm instead of against zero, and a clean `fail` came out as
    `invalid`. Measured on X-20260908-warming-response: a margin of 0.0162 was computed as 0.1586.
    """
    out: list[ArmValue] = []
    for a in null_arms:
        own = a.value if a.value is not None else 0.0
        if comparator == "model_absolute":
            candidate = own
        else:
            others = [b.value for b in null_arms if b.arm != a.arm and b.value is not None]
            candidate = own - (max(others) if others else 0.0)
        if rule.holds(candidate):
            out.append(a)
    return out


def _decide(
    arms: list[ArmValue],
    null_arms: list[ArmValue],
    rule: PassRule,
    comparator: str,
    margin: float | None,
) -> tuple[str, list[str]]:
    """The outcome and its reasons, in precedence order. `invalid` always beats pass/fail.

    The ordering is deliberate. A misbehaving null (E07) or a powerless metric (E08) means the
    comparison does not license a conclusion EITHER WAY -- reporting such a run as `fail` would be
    just as wrong as reporting it as `pass`, because the apparatus, not the model, is what was
    measured.
    """
    reasons: list[str] = []

    off = [a for a in arms if a.arm != "model" and a.within_expected is False]
    if off:
        for a in off:
            reasons.append(
                f"null {a.arm!r} returned {a.value:.6g}, pre-registered {a.expected:.6g} "
                f"+/- {a.tolerance:.6g} -- the apparatus did not do what was declared"
            )
        return "invalid", reasons

    missing = [a.arm for a in arms if a.arm != "model" and a.value is None]
    if missing:
        return "invalid", [f"null(s) not measured: {', '.join(missing)}"]

    powerless = _powerless_nulls(null_arms, rule, comparator)
    if powerless:
        return "invalid", [
            f"null(s) {', '.join(a.arm for a in powerless)} also satisfy pass_if "
            f"({rule.render()}) -- the estimand has NO POWER and cannot be quoted as evidence"
        ]

    if margin is None:
        return "invalid", ["margin could not be computed"]
    if rule.holds(margin):
        return "pass", [f"margin {margin:.6g} satisfies {rule.render()}"]
    return "fail", [f"margin {margin:.6g} does not satisfy {rule.render()}"]


def evaluate(exp: Experiment) -> Evaluation:
    """The single source of an experiment's verdict. Both the checker and the renderer call this."""
    stat = exp.statistic
    dr = exp.prereg.get("decision_rule", {}) or {}
    rule = parse_pass_if(dr.get("pass_if", ""))
    comparator = str(dr.get("comparator", "model_minus_best_null"))

    model = _latest(exp.rows_for("model"), stat)

    arms: list[ArmValue] = [ArmValue("model", model)]
    for n in exp.prereg.get("nulls", []) or []:
        exp_block = n.get("expected", {}) or {}
        arms.append(
            ArmValue(
                arm=str(n.get("id", "")),
                value=_latest(exp.rows_for(str(n.get("id", ""))), stat),
                expected=exp_block.get("value"),
                tolerance=exp_block.get("tolerance"),
            )
        )

    null_arms = [a for a in arms if a.arm != "model" and a.value is not None]
    # `is not None`, never truthiness: a null returning exactly 0.0 must rank as 0.0.
    best = (
        max(null_arms, key=lambda a: a.value if a.value is not None else float("-inf"))
        if null_arms
        else None
    )

    margin: float | None = None
    if model is not None:
        if comparator == "model_absolute":
            margin = model
        elif best is not None:
            margin = model - (best.value if best.value is not None else 0.0)

    if rule is None:
        outcome, reasons = "invalid", ["pass_if could not be parsed"]
    elif not exp.results:
        outcome, reasons = "invalid", ["no result rows yet"]
    elif model is None:
        outcome, reasons = "invalid", [f"no `model` row reporting {stat!r}"]
    else:
        outcome, reasons = _decide(arms, null_arms, rule, comparator, margin)

    return Evaluation(
        statistic=stat,
        rule=rule,
        model=model,
        arms=arms,
        best_null=best.arm if best else None,
        best_null_value=best.value if best else None,
        margin=margin,
        outcome=outcome,
        reasons=reasons,
    )


# --------------------------------------------------------------------------------------------------
# Rendering — the number and its null land in the same table BY CONSTRUCTION
# --------------------------------------------------------------------------------------------------


def render_metrics_block(exp: Experiment, ev: Evaluation) -> str:
    stat = ev.statistic or "(statistic)"
    lines = [
        BEGIN_MARK,
        f"| arm | {stat} | vs best null | pre-registered null return |",
        "|---|---|---|---|",
    ]

    def fmt(v: float | None) -> str:
        return f"{v:.6g}" if isinstance(v, (int, float)) else "—"

    for a in ev.arms:
        if a.arm == "model":
            vs = fmt(ev.margin)
            prereg = "—"
        else:
            vs = "—"
            if a.expected is None:
                prereg = "— (none declared)"
            else:
                mark = (
                    "OK" if a.within_expected else ("MISS" if a.within_expected is False else "?")
                )
                prereg = f"{a.expected:.6g} +/- {a.tolerance:.6g} [{mark}]"
        lines.append(f"| {a.arm} | {fmt(a.value)} | {vs} | {prereg} |")

    rule = ev.rule.render() if ev.rule else "(unparseable)"
    lines.append(f"| **DECISION** | pass_if {rule} | **{ev.outcome.upper()}** | {fmt(ev.margin)} |")
    lines.append("")
    for r in ev.reasons:
        lines.append(f"- {r}")
    lines.append(END_MARK)
    return "\n".join(lines)


def splice_metrics_block(verdict_text: str, block: str) -> str:
    """Replace the generated region, or append it if absent."""
    if BEGIN_MARK in verdict_text and END_MARK in verdict_text:
        pre = verdict_text.split(BEGIN_MARK, maxsplit=1)[0]
        post = verdict_text.split(END_MARK, 1)[1]
        return pre + block + post
    sep = "" if verdict_text.endswith("\n\n") or not verdict_text else "\n\n"
    return verdict_text + sep + block + "\n"


def extract_metrics_block(verdict_text: str) -> str | None:
    if BEGIN_MARK not in verdict_text or END_MARK not in verdict_text:
        return None
    start = verdict_text.index(BEGIN_MARK)
    end = verdict_text.index(END_MARK) + len(END_MARK)
    return verdict_text[start:end]


def declared_outcome(verdict_text: str) -> str | None:
    """The `outcome:` field from the verdict's front matter, if present."""
    m = re.search(r"^\s*outcome\s*:\s*([a-z]+)\s*$", verdict_text, re.MULTILINE)
    return m.group(1).lower() if m else None
