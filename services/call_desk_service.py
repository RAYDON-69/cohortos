"""
Call Desk — prioritized human follow-up queue (P26).
Sources: absences, fee dues, exam results, admission leads.
NO autodial — tel:/WhatsApp/SMS deep links + script + outcome log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.agent_safety import role_can_write
from services.voice_assist_service import encrypt_field, decrypt_field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CallDeskService:
    def __init__(self, data_layer=None, voice_assist=None, audit_service=None):
        self.data_layer = data_layer
        self.voice_assist = voice_assist
        self.audit_service = audit_service

    def build_queue(
        self,
        *,
        absences: Optional[List[Dict[str, Any]]] = None,
        fee_dues: Optional[List[Dict[str, Any]]] = None,
        exam_flags: Optional[List[Dict[str, Any]]] = None,
        admission_leads: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        # Priority: fee > absence > exam > lead
        for f in fee_dues or []:
            cards.append(self._card("fee_due", 100, f))
        for a in absences or []:
            cards.append(self._card("absence", 80, a))
        for e in exam_flags or []:
            cards.append(self._card("exam", 60, e))
        for lead in admission_leads or []:
            cards.append(self._card("admission_lead", 40, lead))
        cards.sort(key=lambda c: (-c["priority"], c.get("name") or ""))
        return cards

    def _card(self, kind: str, priority: int, src: Dict[str, Any]) -> Dict[str, Any]:
        phone = str(src.get("phone") or src.get("guardian_phone") or "")
        name = str(src.get("name") or src.get("student_name") or "")
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("880"):
            wa = digits
        elif digits.startswith("0"):
            wa = "880" + digits[1:]
        else:
            wa = digits
        return {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "priority": priority,
            "name": name,
            "phone": phone,
            "student_id": src.get("student_id") or src.get("id"),
            "detail": src.get("detail") or src.get("reason") or kind,
            "tel_link": f"tel:{phone}" if phone else "",
            "whatsapp_link": f"https://wa.me/{wa}" if wa else "",
            "sms_link": f"sms:{phone}" if phone else "",
        }

    def script_for_card(
        self,
        card: Dict[str, Any],
        *,
        language: str = "bn",
        actor_id: str = "",
        actor_role: str = "desk",
    ) -> Dict[str, Any]:
        if not self.voice_assist:
            raise RuntimeError("voice_assist_unavailable")
        purpose = {
            "fee_due": "fee_reminder",
            "absence": "attendance",
            "exam": "exam",
            "admission_lead": "admission",
        }.get(str(card.get("kind")), "fee_reminder")
        return self.voice_assist.generate_script(
            student_name=str(card.get("name") or ""),
            phone=str(card.get("phone") or ""),
            purpose=purpose,
            language=language,
            actor_id=actor_id,
            actor_role=actor_role,
            extra_context=str(card.get("detail") or ""),
        )

    def log_outcome(
        self,
        *,
        card_id: str,
        outcome: str,
        notes: str = "",
        promised_date: str = "",
        actor_id: str = "",
        actor_role: str = "desk",
        human_action_id: str = "",
    ) -> Dict[str, Any]:
        if not role_can_write(actor_role):
            raise PermissionError(f"role_denied:{actor_role}")
        if not human_action_id:
            raise PermissionError("human_action_id required")
        allowed = {"reached", "no_answer", "promised", "callback", "wrong_number"}
        if outcome not in allowed:
            raise ValueError(f"invalid_outcome:{outcome}")
        summary = ""
        if self.voice_assist:
            s = self.voice_assist.summarize_call(
                call_notes=notes or outcome,
                purpose=outcome,
                actor_id=actor_id,
                actor_role=actor_role,
            )
            summary = s.get("summary") or ""
        row = {
            "id": str(uuid.uuid4()),
            "card_id": card_id,
            "outcome": outcome,
            "notes_enc": encrypt_field(notes),
            "summary_enc": encrypt_field(summary),
            "promised_date": promised_date,
            "human_action_id": human_action_id,
            "actor_id": actor_id,
            "created_at": _now(),
        }
        if self.data_layer:
            self.data_layer.create("call_desk_outcomes", row)
        return {
            "id": row["id"],
            "outcome": outcome,
            "summary": summary,
            "promised_date": promised_date,
        }
