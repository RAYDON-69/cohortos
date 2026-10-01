
"""
P25/P26 Online class workspace — Jitsi Meet + classroom tools.

Jitsi (Apache-2.0). meet.jit.si = OPEN-ROOM (JWT ignored). Production: self-host
with JWT (docs/JITSI_SELFHOST.md). Secondary base URL fallback supported.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import jwt

from services.agent_safety import role_can_write


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _room_name(tenant_id: str, session_id: str) -> str:
    h = hashlib.sha256(f"{tenant_id}:{session_id}".encode()).hexdigest()[:12]
    # ASCII slug only — Bangla titles never enter room name
    return f"cohortos{h}{session_id.replace('-', '')[:8]}"


def sanitize_notice(body: str) -> str:
    """Strip tags to mitigate XSS in notices/polls/Q&A."""
    t = re.sub(r"<[^>]+>", "", body or "")
    return html.escape(t)[:2000]


def _validate_broadcast_url(url: str) -> str:
    """Reject javascript:, data:, http:, and credentialed URLs."""
    u = (url or "").strip()
    if not u:
        raise ValueError("broadcast_url required")
    low = u.lower()
    if low.startswith("javascript:") or low.startswith("data:") or low.startswith("vbscript:"):
        raise ValueError("broadcast_url_scheme_forbidden")
    if low.startswith("http://"):
        raise ValueError("broadcast_url_must_be_https")
    if not low.startswith("https://"):
        raise ValueError("broadcast_url_must_be_https")
    # block embedded credentials https://user:pass@host
    try:
        from urllib.parse import urlparse
        parsed = urlparse(u)
        if parsed.username or parsed.password:
            raise ValueError("broadcast_url_credentials_forbidden")
        if not parsed.netloc:
            raise ValueError("broadcast_url_invalid")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"broadcast_url_invalid:{e}") from e
    return u[:500]


class ClassSessionService:
    def __init__(
        self,
        data_layer=None,
        tenant_id: str = "",
        jwt_secret: Optional[str] = None,
        jitsi_base_url: Optional[str] = None,
        jitsi_fallback_url: Optional[str] = None,
        token_ttl_sec: int = 4 * 3600,
        attendance_on_join: bool = False,
        late_minutes: int = 10,
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
        self.jitsi_fallback = (
            jitsi_fallback_url
            or os.environ.get("COHORTOS_JITSI_FALLBACK_URL")
            or ""
        ).rstrip("/")
        self.token_ttl_sec = token_ttl_sec
        self.attendance_on_join = attendance_on_join or (
            os.environ.get("COHORTOS_CLASS_ATTENDANCE_ON_JOIN") == "1"
        )
        self.late_minutes = late_minutes
        self._idempotency: Set[str] = set()

    def _open_room_mode(self, base: Optional[str] = None) -> bool:
        b = (base or self.jitsi_base).lower()
        return "meet.jit.si" in b

    def resolve_jitsi_base(self, prefer_fallback: bool = False) -> str:
        if prefer_fallback and self.jitsi_fallback:
            return self.jitsi_fallback
        return self.jitsi_base

    def create_session(
        self,
        *,
        batch_id: str,
        title: str,
        starts_at: str = "",
        ends_at: str = "",
        teacher_id: str = "",
        actor_id: str = "",
        actor_role: str = "teacher",
        idempotency_key: str = "",
        mode: str = "interactive",
        broadcast_url: str = "",
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        if not batch_id:
            raise ValueError("batch_id required")
        if idempotency_key:
            # power-cut safe: same key returns existing
            existing = self._find_by_idempotency(idempotency_key)
            if existing:
                return existing
            self._idempotency.add(f"{self.tenant_id}:{idempotency_key}")

        starts = starts_at or _now()
        if teacher_id:
            conflict = self._detect_teacher_overlap(teacher_id, starts, ends_at)
            if conflict:
                raise ValueError(f"teacher_double_booked:{conflict.get('id')}")

        mode_n = (mode or "interactive").strip().lower()
        if mode_n not in ("interactive", "broadcast"):
            mode_n = "interactive"
        burl = ""
        if mode_n == "broadcast":
            burl = _validate_broadcast_url(broadcast_url)
        elif broadcast_url:
            burl = _validate_broadcast_url(broadcast_url)
        sid = str(uuid.uuid4())
        room = _room_name(self.tenant_id, sid) if mode_n == "interactive" else f"broadcast-{sid[:8]}"
        row = {
            "id": sid,
            "tenant_id": self.tenant_id,
            "batch_id": batch_id,
            "title": (title or "Class")[:200],
            "starts_at": starts,
            "ends_at": ends_at or "",
            "teacher_id": teacher_id,
            "room": room,
            "status": "scheduled",
            "created_by": actor_id,
            "created_at": _now(),
            "ended_at": None,
            "idempotency_key": idempotency_key or "",
            "recording_url": burl if mode_n == "broadcast" else "",
            "broadcast_url": burl,
            "mode": mode_n,
            "access_mode": (
                "BROADCAST"
                if mode_n == "broadcast"
                else ("OPEN-ROOM" if self._open_room_mode() else "JWT")
            ),
        }
        if self.data_layer:
            # DataAccessLayer.create() assigns its own UUID and overwrites payload["id"].
            # Return the persisted id so join/list never 404 on a stale client id.
            new_id = self.data_layer.create("class_sessions", row)
            row["id"] = str(new_id)
        return dict(row)

    def _find_by_idempotency(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.data_layer:
            return None
        for r in self.data_layer.get_all("class_sessions") or []:
            if r.get("idempotency_key") == key and r.get("tenant_id") == self.tenant_id:
                return dict(r)
        return None

    def _detect_teacher_overlap(self, teacher_id: str, starts: str, ends: str) -> Optional[Dict[str, Any]]:
        s0 = _parse_iso(starts)
        e0 = _parse_iso(ends) if ends else (s0 + timedelta(hours=2) if s0 else None)
        if not s0:
            return None
        for r in self.list_sessions():
            if r.get("status") == "ended":
                continue
            if str(r.get("teacher_id") or "") != str(teacher_id):
                continue
            s1 = _parse_iso(str(r.get("starts_at") or ""))
            e1 = _parse_iso(str(r.get("ends_at") or "")) or (s1 + timedelta(hours=2) if s1 else None)
            if not s1 or not e1 or not e0:
                continue
            if s0 < e1 and s1 < e0:
                return r
        return None

    def generate_from_timetable(
        self,
        *,
        batch_id: str,
        weekday: int,
        time_hhmm: str,
        duration_min: int = 90,
        weeks: int = 4,
        title: str = "Scheduled class",
        teacher_id: str = "",
        actor_id: str = "",
        actor_role: str = "owner",
        from_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Idempotent weekly generation — no duplicate slots."""
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        base = from_date or datetime.now(timezone.utc)
        created = []
        for w in range(weeks):
            # find next matching weekday
            day = base + timedelta(days=w * 7)
            # adjust to weekday (0=Mon)
            delta = (weekday - day.weekday()) % 7
            day = day + timedelta(days=delta)
            hh, mm = [int(x) for x in time_hhmm.split(":")[:2]]
            starts = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
            ends = starts + timedelta(minutes=duration_min)
            key = f"tt:{batch_id}:{weekday}:{time_hhmm}:{starts.date().isoformat()}"
            try:
                s = self.create_session(
                    batch_id=batch_id,
                    title=title,
                    starts_at=starts.isoformat(),
                    ends_at=ends.isoformat(),
                    teacher_id=teacher_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    idempotency_key=key,
                )
                created.append(s)
            except ValueError:
                continue
        return created

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
            out.append(dict(r))
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

    def set_recording_url(self, session_id: str, url: str, *, actor_id: str = "", actor_role: str = "teacher") -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        row = self._get(session_id)
        url = (url or "")[:500]
        if self.data_layer and hasattr(self.data_layer, "update"):
            self.data_layer.update("class_sessions", session_id, {"recording_url": url})
        row["recording_url"] = url
        return row

    def join_link(
        self,
        session_id: str,
        *,
        role: str = "participant",
        display_name: str = "Guest",
        actor_id: str = "",
        student_id: str = "",
        prefer_fallback: bool = False,
    ) -> Dict[str, Any]:
        row = self._get(session_id)
        if row.get("status") == "ended":
            raise PermissionError("session_ended")
        if str(row.get("mode") or "interactive") == "broadcast":
            burl = str(row.get("broadcast_url") or row.get("recording_url") or "")
            attendance = None
            if self.attendance_on_join and student_id:
                attendance = self._mark_attendance_on_join(row, student_id)
            return {
                "session_id": session_id,
                "room": row.get("room"),
                "role": "participant",
                "token": "",
                "exp": 0,
                "join_url": burl,
                "provider": "broadcast",
                "mode": "broadcast",
                "jitsi_base": None,
                "access_mode": "BROADCAST",
                "access_mode_warning": None,
                "attendance": attendance,
            }
        role = "moderator" if role in ("moderator", "teacher", "owner", "desk") else "participant"
        exp = int(time.time()) + int(self.token_ttl_sec)
        payload = {
            "tid": self.tenant_id,
            "session_id": session_id,
            "room": row["room"],
            "role": role,
            "sub": actor_id or secrets.token_hex(8),
            "name": (display_name or "Guest")[:80],
            "student_id": student_id,
            "exp": exp,
            "iat": int(time.time()),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("ascii")
        base = self.resolve_jitsi_base(prefer_fallback=prefer_fallback)
        open_mode = self._open_room_mode(base)
        safe_name = re.sub(r"[^\w\s\-]", "", display_name or "Guest")[:40]
        join_url = f"{base}/{row['room']}#userInfo.displayName=\"{safe_name}\"&jwt={token}"
        attendance = None
        if self.attendance_on_join and student_id and role == "participant":
            attendance = self._mark_attendance_on_join(row, student_id)
        return {
            "session_id": session_id,
            "room": row["room"],
            "role": role,
            "token": token,
            "exp": exp,
            "join_url": join_url,
            "provider": "jitsi",
            "jitsi_base": base,
            "access_mode": "OPEN-ROOM" if open_mode else "JWT",
            "access_mode_warning": (
                "Public meet.jit.si ignores JWT — room is open if the link leaks. Use self-hosted Jitsi for access control."
                if open_mode
                else None
            ),
            "attendance": attendance,
        }

    def _mark_attendance_on_join(self, session: Dict[str, Any], student_id: str) -> Dict[str, Any]:
        starts = _parse_iso(str(session.get("starts_at") or ""))
        now = datetime.now(timezone.utc)
        status = "present"
        if starts and now > starts + timedelta(minutes=self.late_minutes):
            status = "late"
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session.get("id"),
            "student_id": student_id,
            "batch_id": session.get("batch_id"),
            "status": status,
            "joined_at": _now(),
            "tenant_id": self.tenant_id,
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_join_attendance", row)
            row["id"] = str(_nid)
        return row

    def post_notice(self, session_id: str, *, body: str, actor_id: str = "", actor_role: str = "teacher") -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        self._get(session_id)
        nid = str(uuid.uuid4())
        row = {
            "id": nid,
            "session_id": session_id,
            "tenant_id": self.tenant_id,
            "body": sanitize_notice(body),
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_session_notices", row)
            row["id"] = str(_nid)
        return {"id": nid, "body": row["body"], "created_at": row["created_at"]}

    def list_notices(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        self._get(session_id)
        rows = []
        if self.data_layer:
            rows = [
                r for r in (self.data_layer.get_all("class_session_notices") or [])
                if str(r.get("session_id")) == str(session_id)
            ]
        rows.sort(key=lambda x: str(x.get("created_at") or ""))
        return [
            {"id": r.get("id"), "body": r.get("body"), "created_at": r.get("created_at"), "actor_id": r.get("actor_id")}
            for r in rows[-limit:]
        ]

    # --- In-class tools ---
    def raise_hand(self, session_id: str, *, student_id: str, name: str = "") -> Dict[str, Any]:
        self._get(session_id)
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "student_id": student_id,
            "name": sanitize_notice(name)[:80],
            "created_at": _now(),
            "status": "raised",
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_raise_hand", row)
            row["id"] = str(_nid)
        return row

    def create_poll(self, session_id: str, *, question: str, options: List[str], actor_id: str = "", actor_role: str = "teacher") -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        self._get(session_id)
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "question": sanitize_notice(question)[:300],
            "options": [sanitize_notice(o)[:100] for o in (options or [])[:8]],
            "votes": {},
            "created_by": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_polls", row)
            row["id"] = str(_nid)
        return row

    def vote_poll(self, poll_id: str, *, option_index: int, voter_id: str) -> Dict[str, Any]:
        if not self.data_layer:
            raise KeyError("poll")
        for r in self.data_layer.get_all("class_polls") or []:
            if str(r.get("id")) == str(poll_id):
                votes = dict(r.get("votes") or {})
                votes[voter_id] = int(option_index)
                r["votes"] = votes
                if hasattr(self.data_layer, "update"):
                    self.data_layer.update("class_polls", poll_id, {"votes": votes})
                return dict(r)
        raise KeyError("poll_not_found")

    def enqueue_qa(self, session_id: str, *, text: str, student_id: str = "") -> Dict[str, Any]:
        self._get(session_id)
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "text": sanitize_notice(text)[:500],
            "student_id": student_id,
            "created_at": _now(),
            "status": "queued",
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_qa_queue", row)
            row["id"] = str(_nid)
        return row

    def notify_absentees(self, session_id: str, *, present_ids: List[str], roster_ids: List[str], actor_id: str = "") -> Dict[str, Any]:
        """Create missed-class notices for absentees (ids only — no public name index)."""
        self._get(session_id)
        present = set(present_ids or [])
        absent = [sid for sid in (roster_ids or []) if sid not in present]
        notices = []
        for sid in absent:
            n = self.post_notice(
                session_id,
                body=f"Missed class notice for student_id={sid}. Recording will be shared when available.",
                actor_id=actor_id,
                actor_role="desk",
            )
            notices.append({"student_id": sid, "notice_id": n["id"]})
        return {"absent_count": len(absent), "notices": notices}


    def save_whiteboard_scene(self, session_id: str, scene_json: str, *, actor_id: str = "", actor_role: str = "teacher") -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        self._get(session_id)
        try:
            from services.voice_assist_service import encrypt_field
            enc = encrypt_field(scene_json or "{}")
        except Exception:
            enc = scene_json or "{}"
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "tenant_id": self.tenant_id,
            "scene_enc": enc,
            "updated_at": _now(),
            "actor_id": actor_id,
        }
        if self.data_layer:
            _nid = self.data_layer.create("class_whiteboard_scenes", row)
            row["id"] = str(_nid)
        return {"session_id": session_id, "id": row["id"], "updated_at": row["updated_at"]}

    def load_whiteboard_scene(self, session_id: str) -> Dict[str, Any]:
        self._get(session_id)
        scene = "{}"
        if self.data_layer:
            rows = [
                r for r in (self.data_layer.get_all("class_whiteboard_scenes") or [])
                if str(r.get("session_id")) == str(session_id)
            ]
            rows.sort(key=lambda x: str(x.get("updated_at") or ""))
            if rows:
                try:
                    from services.voice_assist_service import decrypt_field
                    scene = decrypt_field(rows[-1].get("scene_enc") or "")
                except Exception:
                    scene = rows[-1].get("scene_enc") or "{}"
        return {"session_id": session_id, "scene": scene}

    def allowed_recording_url(self, url: str) -> str:
        u = _validate_broadcast_url(url)
        from urllib.parse import urlparse
        host = (urlparse(u).hostname or "").lower()
        allowed = (
            host.endswith("youtube.com") or host.endswith("youtu.be")
            or host.endswith("drive.google.com") or host.endswith("docs.google.com")
            or host.endswith("vimeo.com") or host.endswith("facebook.com") or host.endswith("fb.watch")
        )
        if not allowed:
            raise ValueError(f"recording_host_not_allowed:{host}")
        return u


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
