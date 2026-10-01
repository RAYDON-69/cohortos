"""
Assisted voice agent (P24): draft call scripts + summarize completed calls for human staff.

Does NOT autodial. Telephony goes through telephony_provider.place_outbound_call
which requires human_action_id.

STT/TTS (remix, not hand-rolled signal processing):
- STT (optional upload): faster-whisper when installed — offline Bangla/English notes
- TTS: not required for assisted mode (script is text); optional edge-tts later
- LLM: existing local/cloud abstraction via injectable llm_complete; respects cloud opt-out
"""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from services.agent_safety import cloud_llm_allowed, redact_pii, role_can_write


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet():
    key = os.environ.get("COHORTOS_VOICE_FERNET_KEY") or ""
    try:
        from cryptography.fernet import Fernet
        if not key:
            # Deterministic dev key from secret or machine — production must set COHORTOS_VOICE_FERNET_KEY
            raw = (os.environ.get("COHORTOS_JWT_SECRET") or "cohortos-dev-voice").encode()
            key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        return Fernet(key if isinstance(key, bytes) else key.encode() if not key.startswith("gAAAA") else key.encode())
    except Exception:
        return None


def encrypt_field(plain: str) -> str:
    f = _fernet()
    if not f:
        # XOR fallback only for test envs without cryptography — still not plain
        b = (plain or "").encode("utf-8")
        return "x:" + base64.urlsafe_b64encode(bytes(c ^ 0x5A for c in b)).decode("ascii")
    return f.encrypt((plain or "").encode("utf-8")).decode("ascii")


def decrypt_field(token: str) -> str:
    if not token:
        return ""
    if token.startswith("x:"):
        b = base64.urlsafe_b64decode(token[2:].encode("ascii"))
        return bytes(c ^ 0x5A for c in b).decode("utf-8", errors="replace")
    f = _fernet()
    if not f:
        return token
    return f.decrypt(token.encode("ascii")).decode("utf-8")


class VoiceAssistService:
    def __init__(
        self,
        data_layer=None,
        audit_service=None,
        llm_complete: Optional[Callable[[str], str]] = None,
        config_section: Optional[Dict[str, Any]] = None,
    ):
        self.data_layer = data_layer
        self.audit_service = audit_service
        self.llm_complete = llm_complete
        self.config_section = config_section or {}

    def _audit(self, action: str, actor_id: str, detail: Dict[str, Any]) -> None:
        if not self.audit_service:
            return
        try:
            if hasattr(self.audit_service, "log"):
                self.audit_service.log(action, actor_id=actor_id, detail=detail)
            elif hasattr(self.audit_service, "log_create"):
                self.audit_service.log_create(action, actor_id, detail)
        except Exception:
            pass

    def generate_script(
        self,
        *,
        student_name: str,
        phone: str,
        purpose: str = "fee_reminder",
        amount_bdt: Optional[float] = None,
        language: str = "bn",
        actor_id: str = "",
        actor_role: str = "desk",
        extra_context: str = "",
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        purpose = purpose or "fee_reminder"
        amount_txt = f"{amount_bdt:.0f} BDT" if amount_bdt is not None else "the outstanding fee"
        prompt = (
            f"Write a short polite phone script in {'Bangla' if language.startswith('bn') else 'English'} "
            f"for a coaching-centre staff member calling a parent/student.\n"
            f"Purpose: {purpose}. Student: {student_name}. Amount/context: {amount_txt}.\n"
            f"Extra: {extra_context[:500]}\n"
            f"Keep under 120 words. No threats. Staff will read this aloud."
        )
        use_cloud = cloud_llm_allowed(self.config_section)
        script = ""
        if self.llm_complete:
            try:
                p = redact_pii(prompt) if use_cloud else prompt
                script = (self.llm_complete(p) or "").strip()
            except Exception:
                script = ""
        if not script:
            # Deterministic offline template (Bangla-first)
            if language.startswith("bn"):
                script = (
                    f"আসসালামু আলাইকুম, আমি {student_name} এর কোচিং সেন্টার থেকে বলছি। "
                    f"বিষয়: {purpose}। "
                    + (f"বকেয়া প্রায় {amount_txt}। " if amount_bdt is not None else "")
                    + "অনুগ্রহ করে সুবিধামতো পরিশোধের বিষয়টি দেখবেন। ধন্যবাদ।"
                )
            else:
                script = (
                    f"Assalamu alaikum, calling from the coaching centre regarding {student_name}. "
                    f"Purpose: {purpose}. "
                    + (f"Outstanding about {amount_txt}. " if amount_bdt is not None else "")
                    + "Please arrange payment at your convenience. Thank you."
                )
        sid = str(uuid.uuid4())
        row = {
            "id": sid,
            "student_name_enc": encrypt_field(student_name),
            "phone_enc": encrypt_field(phone),
            "purpose": purpose,
            "script_enc": encrypt_field(script),
            "language": language,
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            _nid = self.data_layer.create("voice_call_scripts", row)
            row["id"] = str(_nid)
        self._audit("voice.script_generate", actor_id, {"script_id": sid, "purpose": purpose})
        return {"script_id": sid, "script": script, "purpose": purpose, "phone_hint": phone[-4:] if phone else ""}

    def summarize_call(
        self,
        *,
        call_notes: str,
        student_name: str = "",
        purpose: str = "",
        actor_id: str = "",
        actor_role: str = "desk",
        cloud_llm: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        use_cloud = cloud_llm if cloud_llm is not None else cloud_llm_allowed(self.config_section)
        notes = call_notes or ""
        prompt = (
            f"Summarize this coaching-centre phone call in 2-3 sentences for the desk log.\n"
            f"Student: {student_name}. Purpose: {purpose}.\nNotes: {notes}\n"
            f"Include outcome (will pay / no answer / callback) if present."
        )
        summary = ""
        if self.llm_complete:
            try:
                p = redact_pii(prompt) if use_cloud else prompt
                summary = (self.llm_complete(p) or "").strip()
            except Exception:
                summary = ""
        if not summary:
            summary = f"Call re: {purpose or 'follow-up'} — {(notes or 'no notes')[:240]}"
        sid = str(uuid.uuid4())
        row = {
            "id": sid,
            "student_name_enc": encrypt_field(student_name),
            "purpose": purpose,
            "notes_enc": encrypt_field(notes),
            "summary_enc": encrypt_field(summary),
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            _nid = self.data_layer.create("voice_call_summaries", row)
            row["id"] = str(_nid)
        self._audit("voice.call_summarize", actor_id, {"summary_id": sid, "purpose": purpose})
        return {"summary_id": sid, "summary": summary}

    def request_human_call(
        self,
        *,
        to_phone: str,
        script_id: str = "",
        script_text: str = "",
        human_action_id: str,
        actor_id: str = "",
        actor_role: str = "desk",
    ) -> Dict[str, Any]:
        """Staff clicked 'I will call / place via provider' — still no silent autodial."""
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        if not human_action_id:
            raise PermissionError("human_action_id required")
        from services.telephony_provider import place_outbound_call

        result = place_outbound_call(
            to=to_phone,
            script=script_text or f"script:{script_id}",
            human_action_id=human_action_id,
        )
        row = {
            "id": str(uuid.uuid4()),
            "to_phone_enc": encrypt_field(to_phone),
            "script_id": script_id,
            "human_action_id": human_action_id,
            "result": result,
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            _nid = self.data_layer.create("voice_call_requests", row)
            row["id"] = str(_nid)
        self._audit(
            "voice.human_call_request",
            actor_id,
            {"human_action_id": human_action_id, "placed": result.get("placed"), "mode": result.get("mode")},
        )
        return {"ok": True, **result}

    def list_summaries(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.data_layer:
            return []
        rows = list(self.data_layer.get_all("voice_call_summaries") or [])
        out = []
        for r in rows[-limit:]:
            out.append(
                {
                    "id": r.get("id"),
                    "purpose": r.get("purpose"),
                    "summary": decrypt_field(r.get("summary_enc") or ""),
                    "created_at": r.get("created_at"),
                }
            )
        return list(reversed(out))
