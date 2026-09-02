#!/usr/bin/env bash
# PostToolUse[Write|Edit] — non-blocking. Print the edited document's budget headroom.
#
# THE POINT. A hard cap with no gradient is a wall you hit in the middle of real work, and it gets
# resented and then raised. The predecessor's 400-line memory cap had neither gradient nor wall, and
# was exceeded by 62 %. This converts the cap into something you FEEL approaching, so compaction
# happens at a natural moment.
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FILE="$(cat | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"
[[ -z "$FILE" || "${FILE##*.}" != "md" ]] && exit 0
cd "$REPO" 2>/dev/null || exit 0
REL="${FILE#$REPO/}"
python3 - "$REL" <<'PY' 2>/dev/null || true
import sys, tomllib, pathlib, re
rel = sys.argv[1]
root = pathlib.Path.cwd()
cfg = tomllib.loads((root / "config" / "budgets.toml").read_text())

def match(pat, path):
    rx = re.escape(pat).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(rx, path) is not None

best, blen = None, -1
for b in cfg.get("budget", []):
    g = b.get("glob", "")
    if g and match(g, rel) and len(g) > blen:
        best, blen = b, len(g)
if not best:
    raise SystemExit(0)
p = root / rel
if not p.exists():
    raise SystemExit(0)
n = len(p.read_text(encoding="utf-8").splitlines())
lim = int(best["max_lines"])
pct = n * 100 // max(lim, 1)
if pct >= 80:
    print(f"[budget] {rel}: {n}/{lim} lines ({pct}%)")
    if n > lim:
        print(f"[budget] OVER by {n - lim}. The commit guard will refuse this until it fits.")
    if rel.startswith("lines/"):
        print(f"[budget] rotate: tools/rotate_state.py {rel.split('/')[1]}")
    elif rel == "MEMORY.md":
        print("[budget] rotate: tools/rotate_memory.py")
    else:
        print("[budget] move depth into docs/reference/ or a skill's references/ (loaded on demand)")
PY
exit 0
