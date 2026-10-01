#!/usr/bin/env python3
"""Minimal CycloneDX-ish SBOM summary for python + npm (JSON)."""
import json, subprocess, sys
from pathlib import Path

def main():
    out = {"bomFormat": "CycloneDX", "specVersion": "1.4", "components": []}
    # python
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], capture_output=True, text=True)
        for row in json.loads(r.stdout or "[]"):
            out["components"].append({"type": "library", "name": row["name"], "version": row["version"], "purl": f"pkg:pypi/{row['name']}@{row['version']}"})
    except Exception as e:
        out["python_error"] = str(e)
    lock = Path("frontend/package-lock.json")
    if lock.exists():
        data = json.loads(lock.read_text())
        pkgs = data.get("packages") or {}
        for name, meta in list(pkgs.items())[:500]:
            if not name or name == "":
                continue
            ver = meta.get("version") or ""
            out["components"].append({"type": "library", "name": name, "version": ver, "purl": f"pkg:npm/{name}@{ver}"})
    Path("/tmp/sbom.json").write_text(json.dumps(out, indent=2))
    print("components", len(out["components"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
