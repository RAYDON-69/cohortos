"""
P25 Online class workspace — Jitsi Meet backend.

Stack choice: **Jitsi Meet** (Apache-2.0)
Why not BBB: needs ~16GB RAM — fails CohortOS 4GB desk target.
Why not LiveKit alone: excellent SFU SDK, but full classroom shell is more
custom UI work; Jitsi gives embeddable rooms + JWT auth with lowest ops.
BD coaching (ACS/Udvash) publicly runs proprietary web apps / FB Live / YouTube;
they do not publish an open SFU choice — we pick maintainable OSS for self-host.

Default media host: COHORTOS_JITSI_BASE_URL (default https://meet.jit.si).
Self-host: point at docker-jitsi-meet with JWT enabled (same token shape).

Security: room name embeds tenant hash; join JWT carries tenant_id + session_id
+ role + exp; cross-tenant verify fails; ended sessions reject tokens.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt

from services.agent_safety import role_can_write


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _room_name(tenant_id: str, session_id: str) -> str:
    # Opaque room — no student names; short hash + session suffix
    h = hashlib.sha256(f"{tenant_id}:{session_id}".encode()).hexdigest()[:12]
    return f"cohortos{h}{session_id[:8]}"


class ClassSessionService:
    def __init__(
        self,
        data_layer=None,
        tenant_id: str = "",
        jwt_secret: Optional[str] = None,
        jitsi_base_url: Optional[str] = None,
        token_ttl_sec: int = 4 * 3600,
        attendance_on_join: bool = False,
    ):
        self.data_layer = data_layer
        self.tenant_id = tenant_id
        self.jwt_secret = (
            jwt_secret
            or os.environ.get("COHORTOS_JITSI_JWT_SECRET")
            or os.environ.get("COHORTOS_JWT_SECRET")
            or "cohortos-jitsi-dev-secret-change-me"
        )
        self.jitsi_base = (
            jitsi_base_url
            or os.environ.get("COHORTOS_JITSI_BASE_URL")
            or "https://meet.jit.si"
        ).rstrip("/")
        self.token_ttl_sec = token_ttl_sec
        self.attendance_on_join = attendance_on_join or (
            os.environ.get("COHORTOS_CLASS_ATTENDANCE_ON_JOIN") == "1"
        )

    def create_session(
        self,
        *,
        batch_id: str,
        title: str,
        starts_at: str = "",
        actor_id: str = "",
        actor_role: str = "teacher",
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        if not batch_id:
            raise ValueError("batch_id required")
        sid = str(uuid.uuid4())
        room = _room_name(self.tenant_id, sid)
        row = {
            "id": sid,
            "tenant_id": self.tenant_id,
            "batch_id": batch_id,
            "title": (title or "Class")[:200],
            "starts_at": starts_at or _now(),
            "room": room,
            "status": "scheduled",
            "created_by": actor_id,
            "created_at": _now(),
            "ended_at": None,
        }
        if self.data_layer:
            self.data_layer.create("class_sessions", row)
        return dict(row)

    def list_sessions(self, batch_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        rows = []
        if self.data_layer:
            rows = list(self.data_layer.get_all("class_sessions") or [])
        out = []
        for r in rows:
            if self.tenant_id and r.get("tenant_id") and r.get("tenant_id") != self.tenant_id:
                continue
            if batch_id and str(r.get("batch_id")) != str(batch_id):
                continue
            out.append(
                {
                    "id": r.get("id"),
                    "batch_id": r.get("batch_id"),
                    "title": r.get("title"),
                    "starts_at": r.get("starts_at"),
                    "status": r.get("status"),
                    "room": r.get("room"),
                    "created_at": r.get("created_at"),
                    "ended_at": r.get("ended_at"),
                }
            )
        out.sort(key=lambda x: str(x.get("starts_at") or ""), reverse=True)
        return out[:limit]

    def _get(self, session_id: str) -> Dict[str, Any]:
        if not self.data_layer:
            raise KeyError("session")
        for r in self.data_layer.get_all("class_sessions") or []:
            if str(r.get("id")) == str(session_id):
                if r.get("tenant_id") and r.get("tenant_id") != self.tenant_id:
                    raise PermissionError("cross_tenant_session")
                return dict(r)
        raise KeyError("session_not_found")

    def end_session(self, session_id: str, *, actor_id: str = "", actor_role: str = "teacher") -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        row = self._get(session_id)
        row["status"] = "ended"
        row["ended_at"] = _now()
        if self.data_layer and hasattr(self.data_layer, "update"):
            self.data_layer.update("class_sessions", session_id, {"status": "ended", "ended_at": row["ended_at"]})
        return row

    def join_link(
        self,
        session_id: str,
        *,
        role: str = "participant",
        display_name: str = "Guest",
        actor_id: str = "",
    ) -> Dict[str, Any]:
        row = self._get(session_id)
        if row.get("status") == "ended":
            raise PermissionError("session_ended")
        role = "moderator" if role in ("moderator", "teacher", "owner", "desk") else "participant"
        exp = int(time.time()) + int(self.token_ttl_sec)
        payload = {
            "tid": self.tenant_id,
            "session_id": session_id,
            "room": row["room"],
            "role": role,
            "sub": actor_id or secrets.token_hex(8),
            "name": (display_name or "Guest")[:80],
            "exp": exp,
            "iat": int(time.time()),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("ascii")
        # meet.jit.si does not validate our custom JWT; self-hosted Jitsi with JWT does.
        # Always append jwt= for self-host; public meet still works as open room (room name is opaque).
        join_url = f"{self.jitsi_base}/{row['room']}#userInfo.displayName=\"{payload['name']}\"&jwt={token}"
        return {
            "session_id": session_id,
            "room": row["room"],
            "role": role,
            "token": token,
            "exp": exp,
            "join_url": join_url,
            "provider": "jitsi",
            "jitsi_base": self.jitsi_base,
        }

    def post_notice(
        self,
        session_id: str,
        *,
        body: str,
        actor_id: str = "",
        actor_role: str = "teacher",
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        self._get(session_id)  # tenant check
        nid = str(uuid.uuid4())
        row = {
            "id": nid,
            "session_id": session_id,
            "tenant_id": self.tenant_id,
            "body": (body or "")[:2000],
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            self.data_layer.create("class_session_notices", row)
        return {"id": nid, "body": row["body"], "created_at": row["created_at"]}

    def list_notices(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        self._get(session_id)
        rows = []
        if self.data_layer:
            rows = [
                r
                for r in (self.data_layer.get_all("class_session_notices") or [])
                if str(r.get("session_id")) == str(session_id)
            ]
        rows.sort(key=lambda x: str(x.get("created_at") or ""))
        return [
            {"id": r.get("id"), "body": r.get("body"), "created_at": r.get("created_at"), "actor_id": r.get("actor_id")}
            for r in rows[-limit:]
        ]


def verify_join_token(
    token: str,
    *,
    expected_tenant_id: str,
    jwt_secret: str,
    require_active_session=None,
) -> Dict[str, Any]:
    try:
        claims = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except Exception as e:
        raise PermissionError(f"invalid_token:{e}") from e
    if str(claims.get("tid") or "") != str(expected_tenant_id):
        raise PermissionError("cross_tenant_token")
    if require_active_session is not None:
        sid = claims.get("session_id")
        try:
            row = require_active_session._get(sid)
        except Exception as e:
            raise PermissionError(f"session:{e}") from e
        if row.get("status") == "ended":
            raise PermissionError("session_ended")
    return claims
