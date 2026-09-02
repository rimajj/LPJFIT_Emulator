#!/usr/bin/env python3
"""Enforce that every opt-in flag carries an expiry, and that the expiry is honoured.

    F01  a flag lacks `flip_by` or `owner_line`
    F02  a flag's `flip_by` date has passed while its default is still unchanged
    F03  a flag declares a `target` equal to its `default` (it is no longer opt-in; delete it)

WHY. "Opt-in, default byte-identical" is a good rule and the predecessor used it correctly to ship
new physics safely. But it has a corollary learned three separate times over: **it protects
you from enabling too early, NOT from never enabling.** Three flags whose defaults were known to
be wrong sat unflipped for weeks, each line recording the flip as the other line's to schedule.
One of them had already been MEASURED correct and still sat off.

So shipping an opt-in is a reason to start measuring, never a reason to stop. Every flag names the
date by which the decision must be made and the line that owns it; the session-start report warns
as the date approaches, and this gate fails once it passes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Report, config

REQUIRED = ("default", "owner_line", "flip_by", "criterion")


def main() -> int:
    cfg = config("flags")
    rep = Report("check_flags")
    flags = dict(cfg.get("flags", {}))
    today = time.strftime("%Y-%m-%d")

    for name, spec in sorted(flags.items()):
        if not isinstance(spec, dict):
            rep.add("config/flags.toml", "F01", f"flag {name!r} is not a table")
            continue

        for field in REQUIRED:
            if spec.get(field) in (None, ""):
                rep.add(
                    "config/flags.toml",
                    "F01",
                    f"flag {name!r} lacks `{field}`",
                    hint=(
                        "every opt-in flag needs an owner line, a date by which the flip decision "
                        "is made, and the exact arm and pass condition that decides it — "
                        "pre-register "
                        "the criterion in the same commit that ships the flag"
                    ),
                )

        if "target" in spec and spec.get("target") == spec.get("default"):
            rep.add(
                "config/flags.toml",
                "F03",
                f"flag {name!r} has target == default",
                hint="it is no longer an opt-in; delete the flag and keep the behaviour",
            )

        flip_by = str(spec.get("flip_by", ""))
        if flip_by and flip_by < today:
            target = spec.get("target")
            if target is None or target != spec.get("default"):
                rep.add(
                    "config/flags.toml",
                    "F02",
                    f"flag {name!r} passed its flip_by date {flip_by} with default still "
                    f"{spec.get('default')!r}",
                    hint=(
                        f"line {spec.get('owner_line')} owns this decision. Either flip the "
                        "default, or move the date WITH a recorded reason — an opt-in whose "
                        "default is known "
                        "wrong is a defect on a timer"
                    ),
                )

    return rep.emit()


if __name__ == "__main__":
    raise SystemExit(main())
