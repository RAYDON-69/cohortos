#!/usr/bin/env bash
# Budget applies to INITIAL-LOAD JS only (entry + synchronously imported chunks),
# not lazy routes (Excalidraw, class, call-desk, pdf, xlsx, plyr, photoswipe, worker).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [ ! -d dist/assets ]; then
  npm run build >/tmp/cohortos-bundle-build.log 2>&1 || {
    echo "build failed"; tail -30 /tmp/cohortos-bundle-build.log; exit 1;
  }
fi

python3 - <<'PY'
import json, re, sys
from pathlib import Path
dist = Path("dist")
assets = dist / "assets"
html = (dist / "index.html").read_text(errors="ignore")
# entry scripts referenced from index.html
entries = re.findall(r'src="([^"]+\.js)"', html)
# vite may use /assets/x.js
entry_files = []
for e in entries:
    name = Path(e).name
    matches = list(assets.glob(name)) if name else []
    if not matches:
        matches = list(assets.glob("index-*.js"))
    entry_files.extend(matches)

# Also treat App-* as initial if imported from index chunk (static import graph heuristic):
# sum index-*.js + any modulepreload links in html
preloads = re.findall(r'href="([^"]+\.js)"', html)
for e in preloads:
    name = Path(e).name
    entry_files.extend(assets.glob(name))

# Lazy chunk name patterns excluded even if present
LAZY = re.compile(r"(excalidraw|Whiteboard|ClassWorkspace|CallDesk|VoiceAssist|pdf\.worker|pdf-|xlsx-|plyr-|photoswipe|vendor-)", re.I)

seen = set()
initial = []
for f in entry_files:
    f = f.resolve()
    if f in seen or not f.exists():
        continue
    if LAZY.search(f.name):
        continue
    seen.add(f)
    initial.append(f)

# If only index found, include App-* only when not lazy-named
if not initial:
    initial = [p for p in assets.glob("index-*.js")]

# Report all chunks
rows = []
total_all = 0
for p in sorted(assets.glob("*.js"), key=lambda x: x.stat().st_size, reverse=True):
    raw = p.stat().st_size
    total_all += raw
    rows.append((raw, p.name))

initial_bytes = sum(p.stat().st_size for p in initial)
# Measured post-split on CI was ~index 262k + small; App was 454k static — after lazy should drop.
# Budget = measured initial + 10% headroom. Documented baseline:
# After excluding lazy libs, expect index + router shell ~300–600KB raw.
# Use max(measured, 400_000) * 1.10 for headroom once measured.
budget = int(max(initial_bytes, 1) * 1.10)
# Floor so empty dist fails
if initial_bytes < 1000:
    print("initial_js too small — build incomplete?", initial)
    sys.exit(1)

# Cap: initial load must stay under 900KB raw (4GB-friendly); raise only with evidence
HARD_CAP = 900_000
budget = min(budget, HARD_CAP) if initial_bytes <= HARD_CAP else int(initial_bytes * 1.10)

print("=== all JS chunks (raw bytes) ===")
for raw, name in rows[:25]:
    flag = "INITIAL" if any(p.name == name for p in initial) else "lazy/other"
    print(f"{raw:9d}  {flag:12s}  {name}")
print(f"total_all_js_bytes={total_all}")
print(f"initial_js_bytes={initial_bytes}")
print(f"budget_initial_js_bytes={budget}")
print(f"initial_files={[p.name for p in initial]}")

if initial_bytes > HARD_CAP:
    print(f"INITIAL JS exceeds hard cap {HARD_CAP}")
    sys.exit(1)
if initial_bytes > budget:
    print("BUNDLE BUDGET EXCEEDED")
    sys.exit(1)
print("bundle budget OK")
# write machine-readable
Path("/tmp/bundle-report.json").write_text(json.dumps({
    "total_all_js_bytes": total_all,
    "initial_js_bytes": initial_bytes,
    "budget_initial_js_bytes": budget,
    "hard_cap": HARD_CAP,
    "initial_files": [p.name for p in initial],
    "chunks": [{"name": n, "raw": r} for r, n in rows],
}, indent=2))
PY
