"""Event/schedule automations — fee reminder escalation & attendance-based nag generation."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AutomationService:
    def __init__(self, payment_service=None, attendance_service=None, notification_service=None):
        self.payment = payment_service
        self.attendance = attendance_service
        self.notification = notification_service
        self._log: List[Dict[str, Any]] = []

    def run_fee_reminder_escalation(self, year: int, month: int, actor_id: str = "system") -> Dict[str, Any]:
        """Generate nag candidates from unpaid fees and mark for notify."""
        before = {"year": year, "month": month, "candidates": 0}
        rows = []
        if self.payment and hasattr(self.payment, "list_unpaid_for_month"):
            rows = self.payment.list_unpaid_for_month(year, month) or []
        elif self.payment and hasattr(self.payment, "get_delayed_candidates"):
            rows = self.payment.get_delayed_candidates(year, month) or []
        before["candidates"] = len(rows) if isinstance(rows, list) else 0
        notified = 0
        for r in rows if isinstance(rows, list) else []:
            sid = r.get("student_id") or r.get("id")
            if sid and self.payment and hasattr(self.payment, "set_notify_flag"):
                try:
                    self.payment.set_notify_flag(str(sid), year, month, True)
                    notified += 1
                except Exception:
                    pass
        after = {"notified": notified, "at": datetime.now(timezone.utc).isoformat()}
        entry = {"type": "fee_reminder_escalation", "before": before, "after": after, "actor_id": actor_id}
        self._log.append(entry)
        return entry

    def run_attendance_nag_generation(self, batch_id: str, on_date: str, actor_id: str = "system") -> Dict[str, Any]:
        """Flag chronic absentees for fee/engagement follow-up."""
        before = {"batch_id": batch_id, "on_date": on_date, "absentees": 0}
        absentees = []
        if self.attendance and hasattr(self.attendance, "list_absentees"):
            absentees = self.attendance.list_absentees(batch_id, on_date) or []
        before["absentees"] = len(absentees) if isinstance(absentees, list) else 0
        entry = {
            "type": "attendance_nag_generation",
            "before": before,
            "after": {"flagged": before["absentees"], "at": datetime.now(timezone.utc).isoformat()},
            "actor_id": actor_id,
        }
        self._log.append(entry)
        return entry

    def recent_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._log[-limit:]
