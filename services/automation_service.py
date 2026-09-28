"""Configurable automation engine — trigger → condition → action (Phase 7)."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutomationService:
    def __init__(
        self,
        payment_service=None,
        attendance_service=None,
        notification_service=None,
        config_service=None,
    ):
        self.payment = payment_service
        self.attendance = attendance_service
        self.notification = notification_service
        self.config = config_service
        self._log: List[Dict[str, Any]] = []
        self._idempotency: set = set()

    # ── persistence helpers ───────────────────────────────────────────

    def _load_rules(self) -> List[Dict[str, Any]]:
        if not self.config:
            return []
        section = self.config.get_section("automations") or {}
        # ConfigService prefixes keys as automations.rules
        raw = section.get("automations.rules") or section.get("rules") or "[]"
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            import json
            try:
                return json.loads(raw) if raw.strip() else []
            except Exception:
                return []
        return []

    def _save_rules(self, rules: List[Dict[str, Any]]) -> None:
        if not self.config:
            return
        import json
        self.config.set_section("automations", {"rules": json.dumps(rules)})

    def list_rules(self) -> List[Dict[str, Any]]:
        return self._load_rules()

    def upsert_rule(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        rules = self._load_rules()
        rid = str(rule.get("id") or uuid.uuid4())
        rule = dict(rule)
        rule["id"] = rid
        rule.setdefault("enabled", True)
        rule.setdefault("name", "Untitled")
        rule.setdefault("trigger", {"type": "manual"})
        rule.setdefault("conditions", [])
        rule.setdefault("actions", [])
        out = []
        found = False
        for r in rules:
            if str(r.get("id")) == rid:
                out.append(rule)
                found = True
            else:
                out.append(r)
        if not found:
            out.append(rule)
        self._save_rules(out)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        rules = self._load_rules()
        new = [r for r in rules if str(r.get("id")) != str(rule_id)]
        if len(new) == len(rules):
            return False
        self._save_rules(new)
        return True

    def set_enabled(self, rule_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        rules = self._load_rules()
        for r in rules:
            if str(r.get("id")) == str(rule_id):
                r["enabled"] = bool(enabled)
                self._save_rules(rules)
                return r
        return None

    # ── condition matcher ─────────────────────────────────────────────

    def _match_conditions(self, conditions: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        if not conditions:
            return True
        for c in conditions:
            field = str(c.get("field") or "")
            op = str(c.get("op") or "eq")
            expected = c.get("value")
            actual = context.get(field)
            if op == "eq" and actual != expected:
                return False
            if op == "neq" and actual == expected:
                return False
            if op in (">", "gt"):
                try:
                    if not (float(actual) > float(expected)):
                        return False
                except (TypeError, ValueError):
                    return False
            if op in (">=", "gte"):
                try:
                    if not (float(actual) >= float(expected)):
                        return False
                except (TypeError, ValueError):
                    return False
            if op in ("<", "lt"):
                try:
                    if not (float(actual) < float(expected)):
                        return False
                except (TypeError, ValueError):
                    return False
            if op == "in":
                if actual not in (expected if isinstance(expected, list) else [expected]):
                    return False
        return True

    def _idempotency_key(self, rule_id: str, subject: str, action_type: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw = f"{rule_id}|{subject}|{action_type}|{day}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _run_action(self, action: Dict[str, Any], context: Dict[str, Any], rule_id: str) -> Dict[str, Any]:
        atype = str(action.get("type") or "")
        params = action.get("params") or {}
        subject = str(context.get("student_id") or context.get("subject") or "global")
        key = self._idempotency_key(rule_id, subject, atype)
        if key in self._idempotency:
            return {"type": atype, "skipped": "duplicate", "subject": subject}
        self._idempotency.add(key)

        if atype == "fee_reminder":
            year = int(params.get("year") or context.get("year") or datetime.now(timezone.utc).year)
            month = int(params.get("month") or context.get("month") or datetime.now(timezone.utc).month)
            return self.run_fee_reminder_escalation(year, month, actor_id=context.get("actor_id") or "automation")
        if atype == "attendance_nag":
            batch_id = str(params.get("batch_id") or context.get("batch_id") or "")
            on_date = str(params.get("on_date") or context.get("on_date") or datetime.now(timezone.utc).date().isoformat())
            return self.run_attendance_nag_generation(batch_id, on_date, actor_id=context.get("actor_id") or "automation")
        if atype == "tag_student":
            return {"type": "tag_student", "student_id": subject, "tag": params.get("tag") or "flagged", "ok": True}
        if atype == "notify_staff":
            return {"type": "notify_staff", "message": params.get("message") or "Automation alert", "ok": True}
        if atype in ("log_only", "notify_owner", "notify_guardian", "fee_reminder_escalation"):
            return {"type": atype, "ok": True, "params": params}
        return {"type": atype, "error": "unknown_action"}

    def evaluate_rule(self, rule: Dict[str, Any], context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        context = dict(context or {})
        context.setdefault("actor_id", "system")
        rid = str(rule.get("id") or "")
        if not rule.get("enabled", True):
            entry = {"type": "rule_skipped", "rule_id": rid, "reason": "disabled", "at": _now()}
            self._log.append(entry)
            return entry
        if not self._match_conditions(rule.get("conditions") or [], context):
            entry = {"type": "rule_skipped", "rule_id": rid, "reason": "conditions_not_met", "at": _now()}
            self._log.append(entry)
            return entry
        results = []
        for action in rule.get("actions") or []:
            try:
                if dry_run:
                    results.append({"type": action.get("type"), "dry_run": True, "would_run": True})
                else:
                    results.append(self._run_action(action, context, rid))
            except Exception as e:
                results.append({"type": action.get("type"), "error": str(e)})
        entry = {
            "type": "rule_run_dry" if dry_run else "rule_run",
            "rule_id": rid,
            "name": rule.get("name"),
            "results": results,
            "dry_run": dry_run,
            "at": _now(),
            "actor_id": context.get("actor_id"),
        }
        self._log.append(entry)
        return entry

    def run_rule_by_id(self, rule_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        for r in self._load_rules():
            if str(r.get("id")) == str(rule_id):
                return self.evaluate_rule(r, context)
        return {"type": "rule_missing", "rule_id": rule_id, "at": _now()}

    def run_rule_by_name(self, name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        name_l = (name or "").strip().lower()
        for r in self._load_rules():
            if str(r.get("name") or "").strip().lower() == name_l:
                return self.evaluate_rule(r, context)
        # fuzzy: substring
        for r in self._load_rules():
            if name_l and name_l in str(r.get("name") or "").lower():
                return self.evaluate_rule(r, context)
        return {"type": "rule_missing", "name": name, "at": _now()}

    def run_all_enabled(self, trigger_type: str = "schedule", context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        out = []
        for r in self._load_rules():
            trig = r.get("trigger") or {}
            if str(trig.get("type") or "manual") not in (trigger_type, "manual") and trigger_type != "all":
                # still allow schedule runner to run schedule-type only
                if trigger_type == "schedule" and str(trig.get("type")) != "schedule":
                    continue
            out.append(self.evaluate_rule(r, context))
        return out

    def get_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._log[-limit:])

    # ── legacy hardcoded runners (kept) ───────────────────────────────

    def run_fee_reminder_escalation(self, year: int, month: int, actor_id: str = "system") -> Dict[str, Any]:
        before = {"year": year, "month": month, "candidates": 0}
        rows = []
        if self.payment and hasattr(self.payment, "list_unpaid_for_month"):
            try:
                rows = self.payment.list_unpaid_for_month(year, month) or []
            except Exception:
                rows = []
        elif self.payment and hasattr(self.payment, "get_delayed_candidates"):
            try:
                rows = self.payment.get_delayed_candidates(year, month) or []
            except Exception:
                rows = []
        before["candidates"] = len(rows) if isinstance(rows, list) else 0
        notified = 0
        for r in rows if isinstance(rows, list) else []:
            sid = r.get("student_id") or r.get("id")
            if not sid:
                continue
            if self.payment and hasattr(self.payment, "set_notify_flag"):
                try:
                    self.payment.set_notify_flag(str(sid), year, month, True)
                    notified += 1
                except Exception:
                    pass
        after = {"notified": notified, "at": _now()}
        entry = {"type": "fee_reminder_escalation", "before": before, "after": after, "actor_id": actor_id}
        self._log.append(entry)
        return entry

    def run_attendance_nag_generation(self, batch_id: str, on_date: str, actor_id: str = "system") -> Dict[str, Any]:
        rows = []
        if self.attendance and hasattr(self.attendance, "list_absent"):
            try:
                rows = self.attendance.list_absent(batch_id=batch_id, on_date=on_date) or []
            except Exception:
                rows = []
        entry = {
            "type": "attendance_nag",
            "batch_id": batch_id,
            "on_date": on_date,
            "candidates": len(rows) if isinstance(rows, list) else 0,
            "actor_id": actor_id,
            "at": _now(),
        }
        self._log.append(entry)
        return entry
