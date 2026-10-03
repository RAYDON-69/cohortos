"""
JWT auth, rate limiting, refresh-token rotation (backend v1).

Signing key must come from COHORTOS_JWT_SECRET (or JWT_SECRET) env var.
Startup fails loudly if missing.

Session-family state (families, used JTIs, revoked families) is persisted
through the existing SQLite-backed DataAccessLayer so it survives process
restart.
"""

from __future__ import annotations
import os

import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple, List, Set
from collections import defaultdict
from threading import Lock

import jwt

from models.base import DataAccessLayer, TenantContext


class AuthConfigError(RuntimeError):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded; retry after {retry_after}s")


class AuthError(Exception):
    pass


class TokenReuseError(AuthError):
    """Refresh token already rotated — session family revoked."""


def require_jwt_secret() -> str:
    secret = os.environ.get("COHORTOS_JWT_SECRET") or os.environ.get("JWT_SECRET")
    if not secret or not secret.strip():
        raise AuthConfigError(
            "COHORTOS_JWT_SECRET (or JWT_SECRET) environment variable is required. "
            "Refusing to start without a signing key."
        )
    return secret.strip()


def require_durable_db_path(env_name: str) -> str:
    """Require a filesystem SQLite path — :memory: is not allowed in production."""
    value = (os.environ.get(env_name) or "").strip()
    if not value:
        raise AuthConfigError(
            f"{env_name} environment variable is required. "
            f"Refusing to start with an ephemeral in-memory store. "
            f"Set {env_name} to a durable SQLite file path (e.g. /var/lib/cohortos/auth.db)."
        )
    if value == ":memory:" or value.startswith("file:mem"):
        raise AuthConfigError(
            f"{env_name} must be a durable filesystem path, not ':memory:'. "
            f"In-memory stores lose session/sync state on process restart."
        )
    return value


def require_auth_db() -> str:
    return require_durable_db_path("COHORTOS_AUTH_DB")


def require_cloud_db() -> str:
    return require_durable_db_path("COHORTOS_CLOUD_DB")


ACCESS_TTL_SECONDS = 15 * 60
REFRESH_TTL_SECONDS = 30 * 24 * 3600
RATE_LIMIT_WINDOW = 15 * 60
RATE_LIMIT_MAX = 5
LOCKOUT_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60

# DAL table names for session state
_TBL_FAMILY = "auth_session_families"
_TBL_USED = "auth_used_refresh_jtis"

# Fixed control-plane tenant for auth metadata when caller does not supply a DAL
_AUTH_META_TENANT = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


class RateLimiter:
    """In-process rate limiter keyed by (action, identity, ip)."""

    def __init__(self, max_attempts: int = RATE_LIMIT_MAX, window: int = RATE_LIMIT_WINDOW):
        self.max_attempts = max_attempts
        self.window = window
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._failures: Dict[str, List[float]] = defaultdict(list)
        self._lockouts: Dict[str, float] = {}
        self._lock = Lock()

    def _prune(self, bucket: List[float], now: float) -> List[float]:
        cutoff = now - self.window
        return [t for t in bucket if t >= cutoff]

    def check(self, action: str, identity: str, ip: str = "") -> None:
        # Pilot/test mode: do not lock out automated evidence runs
        if os.environ.get("COHORTOS_TEST_EXPOSE_OTP") == "1":
            return
        if os.environ.get("COHORTOS_RATE_LIMIT_DISABLED") == "1":
            return
        key = f"{action}:{identity}:{ip}"
        now = time.time()
        with self._lock:
            if key in self._lockouts and self._lockouts[key] > now:
                raise RateLimitExceeded(int(self._lockouts[key] - now) + 1)
            hits = self._prune(self._hits[key], now)
            if len(hits) >= self.max_attempts:
                raise RateLimitExceeded(self.window)
            hits.append(now)
            self._hits[key] = hits

    def record_failure(self, action: str, identity: str, ip: str = "") -> None:
        key = f"{action}:{identity}:{ip}"
        now = time.time()
        with self._lock:
            fails = self._prune(self._failures[key], now)
            fails.append(now)
            self._failures[key] = fails
            if len(fails) >= LOCKOUT_FAILURES:
                self._lockouts[key] = now + LOCKOUT_SECONDS


class TokenService:
    """
    JWT access/refresh with rotation.

    When `data_layer` is a file-backed DataAccessLayer (or any durable DAL),
    family / used-jti / revoked state is written through it and reloaded on
    construction — surviving full process restart.
    """

    def __init__(self, secret: str, data_layer: Optional[DataAccessLayer] = None):
        self.secret = secret
        if data_layer is None:
            data_layer = DataAccessLayer(
                TenantContext(_AUTH_META_TENANT, "cloud-first"),
                db_path=":memory:",
            )
        self.data_layer = data_layer
        self._lock = Lock()
        # Warm in-memory mirrors from durable store
        self._families: Dict[str, Set[str]] = {}
        self._revoked_families: Set[str] = set()
        self._used_refresh: Set[str] = set()
        self._load_state()

    # ── persistence ───────────────────────────────────────────────────

    def _load_state(self) -> None:
        """Reload families / used JTIs / revoked set from DAL."""
        families: Dict[str, Set[str]] = {}
        revoked: Set[str] = set()
        for row in self.data_layer.get_all(_TBL_FAMILY):
            fid = row.get("family_id") or row.get("id")
            if not fid:
                continue
            if row.get("revoked"):
                revoked.add(str(fid))
                families[str(fid)] = set()
            else:
                jtis = row.get("valid_jtis") or []
                families[str(fid)] = set(str(j) for j in jtis)
        used: Set[str] = set()
        for row in self.data_layer.get_all(_TBL_USED):
            jti = row.get("jti") or row.get("id")
            if jti:
                used.add(str(jti))
        self._families = families
        self._revoked_families = revoked
        self._used_refresh = used

    def _find_family_row(self, family_id: str) -> Optional[Dict[str, Any]]:
        for row in self.data_layer.get_all(_TBL_FAMILY):
            if str(row.get("family_id") or row.get("id")) == str(family_id):
                return row
        return None

    def _persist_family(self, family_id: str, valid_jtis: Set[str], revoked: bool) -> None:
        existing = self._find_family_row(family_id)
        payload = {
            "family_id": family_id,
            "valid_jtis": sorted(valid_jtis),
            "revoked": bool(revoked),
        }
        if existing and existing.get("id"):
            self.data_layer.update(
                _TBL_FAMILY, uuid.UUID(str(existing["id"])), payload
            )
        else:
            # create with stable id = family_id when possible
            try:
                fid_uuid = uuid.UUID(str(family_id))
            except Exception:
                fid_uuid = uuid.uuid4()
            data = dict(payload)
            data["id"] = str(fid_uuid)
            # DAL create overwrites id — store family_id field as key
            rid = self.data_layer.create(_TBL_FAMILY, data)
            # ensure family_id field survived
            stored = self.data_layer.get(_TBL_FAMILY, rid)
            if stored and stored.get("family_id") != family_id:
                self.data_layer.update(
                    _TBL_FAMILY, rid, {"family_id": family_id}
                )

    def _persist_used_jti(self, jti: str) -> None:
        for row in self.data_layer.get_all(_TBL_USED):
            if str(row.get("jti") or row.get("id")) == str(jti):
                return
        self.data_layer.create(_TBL_USED, {"jti": jti})

    # ── token ops ─────────────────────────────────────────────────────

    def issue_access(
        self,
        account_id: str,
        tenant_id: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": account_id,
            "tenant_id": tenant_id,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ACCESS_TTL_SECONDS)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def issue_refresh(
        self,
        account_id: str,
        tenant_id: str,
        family_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Returns (token, family_id)."""
        family_id = family_id or str(uuid.uuid4())
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        payload = {
            "sub": account_id,
            "tenant_id": tenant_id,
            "type": "refresh",
            "family_id": family_id,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=REFRESH_TTL_SECONDS)).timestamp()),
        }
        token = jwt.encode(payload, self.secret, algorithm="HS256")
        with self._lock:
            if family_id in self._revoked_families:
                raise TokenReuseError("Session family revoked")
            self._families.setdefault(family_id, set()).add(jti)
            self._persist_family(family_id, self._families[family_id], revoked=False)
        return token, family_id

    def decode(self, token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as e:
            raise AuthError("Token expired") from e
        except jwt.InvalidTokenError as e:
            raise AuthError("Invalid token") from e
        if expected_type and payload.get("type") != expected_type:
            raise AuthError(f"Expected {expected_type} token")
        return payload

    def rotate_refresh(self, refresh_token: str) -> Tuple[str, str, str]:
        """
        Rotate refresh token. Returns (access, new_refresh, family_id).
        Reuse of an already-rotated jti revokes the whole family.
        """
        payload = self.decode(refresh_token, expected_type="refresh")
        family_id = payload.get("family_id") or ""
        jti = payload.get("jti") or ""
        account_id = payload.get("sub") or ""
        tenant_id = payload.get("tenant_id") or ""

        with self._lock:
            # Re-load from disk to pick up concurrent writers / prior process state
            self._load_state()

            if family_id in self._revoked_families:
                raise TokenReuseError("Session family revoked")
            valid = set(self._families.get(family_id, set()))
            if jti in self._used_refresh or jti not in valid:
                self._revoked_families.add(family_id)
                self._families[family_id] = set()
                self._persist_family(family_id, set(), revoked=True)
                raise TokenReuseError("Refresh token reuse detected; session revoked")
            self._used_refresh.add(jti)
            self._persist_used_jti(jti)
            valid.discard(jti)
            self._families[family_id] = valid
            self._persist_family(family_id, valid, revoked=False)

        access = self.issue_access(account_id, tenant_id)
        new_refresh, _ = self.issue_refresh(account_id, tenant_id, family_id=family_id)
        return access, new_refresh, family_id

    def revoke_family(self, family_id: str) -> None:
        with self._lock:
            self._revoked_families.add(family_id)
            self._families[family_id] = set()
            self._persist_family(family_id, set(), revoked=True)
