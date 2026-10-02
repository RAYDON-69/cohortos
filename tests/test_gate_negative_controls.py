"""Prove gates CAN go red (P39 f)."""
from scripts.ci_readiness_scorecard import score_from_reports
from scripts.ci_report_schema import wrap
from scripts.ci_bandit_summary import summarize
import json

def test_scorecard_goes_red_on_missing_kind():
    doc = score_from_reports([wrap("e2e", {"core_outcome": "success", "extended_outcome": "success"})])
    assert doc["overall"] == "NO-GO"

def test_scorecard_goes_red_on_fail_row():
    reports = [
        wrap("e2e", {"core_outcome": "success", "extended_outcome": "success"}),
        wrap("authmatrix", {"failed_count": 3, "tests_failed": ["x"]}),
        wrap("fuzz", {"has_5xx": False}),
        wrap("bandit", {"bandit": {"medium_plus_count": 0}}),
        wrap("ratelimit", {"proved_429": True, "has_request_otp": True}),
        wrap("licenses", {"licenses_ok": True, "npm_prod_high": 0, "pip_audit_ok": True, "secrets_ok": True}),
        wrap("load", {"pass": True}),
        wrap("bundle", {"pass": True}),
        wrap("heap", {"pass": True}),
        wrap("health", {"status": 200, "pass": True}),
        wrap("installer", {"size_mb": 1, "pass": True}),
    ]
    doc = score_from_reports(reports)
    assert doc["overall"] == "NO-GO"
    assert any(r["area"] == "auth matrix" and r["status"] == "FAIL" for r in doc["rows"])

def test_bandit_summary_reports_findings(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"results": [{"filename": "a.py", "line_number": 1, "test_id": "B101", "issue_severity": "MEDIUM", "issue_text": "x"}]}))
    out = tmp_path / "s.txt"
    summarize(str(p), str(out))
    assert "B101" in out.read_text()
