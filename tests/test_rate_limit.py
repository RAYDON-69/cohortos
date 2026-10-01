from services.rate_limit import RateLimiter

def test_rate_limiter_lockout():
    lim = RateLimiter(max_hits=3, window_sec=60, lockout_sec=30)
    assert lim.check("a")[0] is True
    assert lim.check("a")[0] is True
    assert lim.check("a")[0] is True
    ok, rem, retry = lim.check("a")
    assert ok is False
    assert retry is not None and retry > 0
