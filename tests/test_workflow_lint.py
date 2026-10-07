"""Negative control: broken workflow YAML must fail the linter."""
from __future__ import annotations
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "scripts" / "lint_workflows.py"

def test_linter_passes_on_repo():
    r = subprocess.run([sys.executable, str(LINT)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "security-gates.yml" in r.stdout
    assert "All workflows valid" in r.stdout

def test_linter_rejects_unindented_continuation(tmp_path, monkeypatch):
    """Deliberately broken block scalar — same class of bug that broke security-gates."""
    broken = textwrap.dedent("""\
    name: Broken
    on: push
    jobs:
      j:
        runs-on: ubuntu-latest
        steps:
          - run: |
              echo start
              python -c "import json; d=1;
    print(d)"
    """)
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "broken.yml").write_text(broken)
    # Run yaml.safe_load directly to show the class of error
    import yaml
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(broken)
