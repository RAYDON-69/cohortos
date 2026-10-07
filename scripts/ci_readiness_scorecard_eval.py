def eval_auth_matrix(d):
    if d.get("failed_count") is not None:
        return int(d["failed_count"]) == 0 and not d.get("tests_failed")
    if d.get("failed") is not None:
        return int(d["failed"]) == 0
    return d.get("ok") is True

def eval_bandit(d):
    if isinstance(d.get("bandit"), dict) and "medium_plus_count" in d["bandit"]:
        return int(d["bandit"]["medium_plus_count"]) == 0
    return int(d.get("medium_plus_count", 1)) == 0

def eval_rate_limit(d):
    if "proved_429" in d:
        return bool(d.get("proved_429")) and bool(d.get("has_request_otp", True))
    return d.get("pass") is True or d.get("ok") is True

def eval_fuzz(d):
    if d.get("seed_failed") or d.get("error") == "no report":
        return False
    if "error" in d and d.get("has_5xx") is None and d.get("fail_count") is None:
        return False
    return d.get("has_5xx") is False

def eval_e2e_core(d):
    if d.get("core_outcome") == "success":
        return True
    cc = d.get("core_counts") or {}
    return isinstance(cc, dict) and cc.get("failed", 1) == 0 and cc.get("passed", 0) > 0

def eval_e2e_extended(d):
    # skipped means extended suite not required this run — not a readiness failure
    if d.get("extended_outcome") in ("success", "skipped"):
        return True
    ec = d.get("extended_counts") or {}
    return isinstance(ec, dict) and ec.get("failed", 1) == 0 and ec.get("passed", 0) > 0
