"""Simple in-process rate limiter (per-IP + per-identifier)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple


class RateLimiter:
    def __init__(self, max_hits: int = 10, window_sec: float = 60.0, lockout_sec: float = 60.0):
        self.max_hits = max_hits
        self.window_sec = window_sec
        self.lockout_sec = lockout_sec
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lockout_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int, Optional[int]]:
        """Returns (allowed, remaining, retry_after_sec).
        Env COHORTOS_RATE_LIMIT_DISABLED=1 bypasses (CI/E2E only — OFF in production).
        """
        import os
        if os.environ.get("COHORTOS_RATE_LIMIT_DISABLED") == "1":
            return True, self.max_hits, None
        now = time.time()
        with self._lock:
            until = self._lockout_until.get(key, 0)
            if until > now:
                return False, 0, int(until - now) + 1
            q = self._hits[key]
            while q and q[0] < now - self.window_sec:
                q.popleft()
            if len(q) >= self.max_hits:
                self._lockout_until[key] = now + self.lockout_sec
                return False, 0, int(self.lockout_sec)
            q.append(now)
            return True, self.max_hits - len(q), None


# Shared limiters for auth endpoints
otp_ip_limiter = RateLimiter(max_hits=15, window_sec=60, lockout_sec=60)
otp_phone_limiter = RateLimiter(max_hits=5, window_sec=300, lockout_sec=120)
