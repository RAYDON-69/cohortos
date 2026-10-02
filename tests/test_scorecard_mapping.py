"""Scorecard must map REAL report schemas (P36)."""
from scripts.ci_readiness_scorecard import (
    eval_auth_matrix, eval_bandit, eval_rate_limit, eval_fuzz, eval_e2e_core,
)

def test_auth_matrix_pass_real_schema():
    assert eval_auth_matrix({"failed_count": 0, "tests_failed": [], "total_routes": 177}) is True

def test_auth_matrix_fail_real_schema():
    assert eval_auth_matrix({"failed_count": 2, "tests_failed": ["x"]}) is False

def test_bandit_pass_nested():
    assert eval_bandit({"bandit": {"medium_plus_count": 0, "medium_plus": []}}) is True

def test_bandit_fail_nested():
    assert eval_bandit({"bandit": {"medium_plus_count": 3}}) is False

def test_rate_limit_pass_proved_429():
    assert eval_rate_limit({"proved_429": True, "has_request_otp": True, "otp_codes": []}) is True

def test_rate_limit_fail_no_429():
    assert eval_rate_limit({"proved_429": False, "has_request_otp": True}) is False

def test_fuzz_no_report_is_fail():
    assert eval_fuzz({"error": "no report"}) is False

def test_fuzz_seed_failed_is_fail():
    assert eval_fuzz({"seed_failed": True, "has_5xx": False}) is False

def test_fuzz_clean_pass():
    assert eval_fuzz({"has_5xx": False, "fail_count": 0}) is True

def test_e2e_core_counts():
    assert eval_e2e_core({"core_counts": {"passed": 13, "failed": 0}}) is True
    assert eval_e2e_core({"core_counts": {"passed": 0, "failed": 7}}) is False
