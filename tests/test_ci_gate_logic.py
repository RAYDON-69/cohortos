def evaluate(conclusions):
    required = [
        "Unit Full",
        "E2E Smoke",
        "Security and License Gates",
        "Release Readiness",
        "Workflow Lint",
        "npm Install Smoke",
        "Skip Budget",
        "CI Gate",
    ]
    return all(conclusions.get(n) == "success" for n in required)


def test_all_success_passes():
    keys = [
        "Unit Full",
        "E2E Smoke",
        "Security and License Gates",
        "Release Readiness",
        "Workflow Lint",
        "npm Install Smoke",
        "Skip Budget",
        "CI Gate",
    ]
    assert evaluate({k: "success" for k in keys})


def test_non_success_fails():
    keys = [
        "Unit Full",
        "E2E Smoke",
        "Security and License Gates",
        "Release Readiness",
        "Workflow Lint",
        "npm Install Smoke",
        "Skip Budget",
        "CI Gate",
    ]
    base = {k: "success" for k in keys}
    for bad in ("failure", "skipped", "cancelled", "neutral", "timed_out"):
        b = dict(base)
        b["Unit Full"] = bad
        assert evaluate(b) is False


def test_missing_fails():
    assert evaluate({"Unit Full": "success"}) is False
