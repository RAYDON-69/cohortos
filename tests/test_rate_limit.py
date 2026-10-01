import pytest
from services.rate_limit import RateLimiter

def test_rate_limiter_lockout():
    lim = RateLimiter(max_hits=3, window_sec=60, lockout_sec=30)
    assert lim.check("a")[0] is True
    assert lim.check("a")[0] is True
    assert lim.check("a")[0] is True
    ok, rem, retry = lim.check("a")
    assert ok is False
    assert retry is not None and retry > 0


def test_production_default_still_locks(monkeypatch):
    monkeypatch.delenv("COHORTOS_RATE_LIMIT_DISABLED", raising=False)
    lim = RateLimiter(max_hits=2, window_sec=60, lockout_sec=30)
    assert lim.check("prod")[0] is True
    assert lim.check("prod")[0] is True
    ok, _, retry = lim.check("prod")
    assert ok is False and retry

def test_ci_bypass_env(monkeypatch):
    monkeypatch.setenv("COHORTOS_RATE_LIMIT_DISABLED", "1")
    lim = RateLimiter(max_hits=1, window_sec=60, lockout_sec=30)
    for _ in range(20):
        assert lim.check("ci")[0] is True


def test_refuse_disabled_in_production(monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("COHORTOS_RATE_LIMIT_DISABLED", "1")
    monkeypatch.setenv("COHORTOS_ENV", "production")
    monkeypatch.setenv("COHORTOS_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("COHORTOS_FOUNDER_TOKEN", "founder-test")
    with pytest.raises(SystemExit):
        from api.main import create_api_app
        create_api_app(jwt_secret="x"*32, founder_token="founder-test")


def test_ci_bypass_env(monkeypatch):
    monkeypatch.setenv("COHORTOS_RATE_LIMIT_DISABLED", "1")
    lim = RateLimiter(max_hits=1, window_sec=60, lockout_sec=30)
    for _ in range(20):
        assert lim.check("ci")[0] is True


def test_production_default_still_locks(monkeypatch):
    monkeypatch.delenv("COHORTOS_RATE_LIMIT_DISABLED", raising=False)
    lim = RateLimiter(max_hits=2, window_sec=60, lockout_sec=30)
    assert lim.check("prod")[0] is True
    assert lim.check("prod")[0] is True
    ok, _, retry = lim.check("prod")
    assert ok is False and retry
