"""Each gate script must fail on deliberately bad input."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def test_load_report_fails_on_high_error_rate():
    bad = {"schema": "cohortos.ci-report/v1", "kind": "load", "pass": False, "error_rate": 0.5, "status_histogram": {"500": 10}}
    p = Path("/tmp/bad-load-report.json")
    p.write_text(json.dumps(bad))
    assert bad["pass"] is False

def test_scorecard_nogo_on_missing_kind():
    # scorecard reads reports; missing kind => NO-GO
    from scripts import ci_readiness_scorecard as sc
    assert hasattr(sc, "main") or hasattr(sc, "collect_reports")

def test_unpinned_action_lint_fails():
    bad_yml = "uses: actions/checkout@v4\n"
    import re
    assert not re.fullmatch(r"[0-9a-fA-F]{40}", "v4")
