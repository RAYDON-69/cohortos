from scripts.ci_report_schema import wrap, index_by_kind, SCHEMA
from scripts.ci_readiness_scorecard import score_from_reports

def test_renamed_file_still_scores_by_kind():
    reports = [
        wrap("e2e", {"core_outcome": "success", "extended_outcome": "success"}),
        wrap("authmatrix", {"failed_count": 0, "tests_failed": []}),
        wrap("fuzz", {"has_5xx": False, "fail_count": 0}),
        wrap("bandit", {"bandit": {"medium_plus_count": 0}}),
        wrap("ratelimit", {"proved_429": True, "has_request_otp": True}),
        wrap("licenses", {"licenses_ok": True, "npm_prod_high": 0, "pip_audit_ok": True, "secrets_ok": True}),
        wrap("load", {"pass": True}),
        wrap("bundle", {"pass": True}),
        wrap("heap", {"pass": True}),
        wrap("health", {"status": 200, "pass": True}),
        wrap("installer", {"size_mb": 120, "pass": True}),
    ]
    # filename irrelevant — only kind matters
    doc = score_from_reports(reports)
    assert doc["overall"] == "GO"
    assert all(r["status"] == "PASS" for r in doc["rows"])

def test_missing_kind_is_nogo():
    reports = [wrap("e2e", {"core_outcome": "success", "extended_outcome": "success"})]
    doc = score_from_reports(reports)
    assert doc["overall"] == "NO-GO"
    missing = [r for r in doc["rows"] if r["status"] == "NO-GO"]
    assert any("missing kind=load" in r["detail"] for r in missing)

def test_duplicate_kind_fails():
    reports = [
        wrap("load", {"pass": True}),
        wrap("load", {"pass": False}),
    ]
    by = index_by_kind(reports)
    assert "_duplicates" in by
