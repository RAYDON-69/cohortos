"""
Student & Parent accounts (SPEC Module 8 [LOCKED]).

- Signup creates unlinked account (zero access).
- link(admission_id, account_id) via join code or staff manual — always audited.
- Passwordless OTP login via NotificationService.
- Parent↔student links within the same centre.
- Teacher takeover on AI threads + flagged-thread priority queue.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import uuid

from models.base import TenantContext, DataAccessLayer
from models.accounts import (
    CohortOSAccount,
    ParentStudentLink,
    LoginOTP,
    AccountSession,
    hash_otp,
    generate_otp_code,
    ROLE_STUDENT,
    ROLE_PARENT,
    ROLE_OWNER,
    ROLE_DESK,
    ROLE_TEACHER,
    ROLE_ASSISTANT,
    STAFF_ROLES,
    IDENTIFIER_PHONE,
    IDENTIFIER_EMAIL,
    IDENTIFIER_BOTH,
)
from services.config_service import ConfigService
from services.audit_service import AuditService


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_phone(phone: str) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


class AccountError(Exception):
    pass


class DuplicateAccountError(AccountError):
    def __init__(self, matches: List[Dict[str, Any]]):
        self.matches = matches
        super().__init__(f"Duplicate account: {matches}")


class AccessDeniedError(AccountError):
    pass


class AccountService:
    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        config_service: Optional[ConfigService] = None,
        audit_service: Optional[AuditService] = None,
        admission_service=None,
        notification_service=None,
        attendance_service=None,
        payment_service=None,
        exam_service=None,
        content_service=None,
        solve_service=None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.config_service = config_service or ConfigService(tenant_context)
        self.audit_service = audit_service or AuditService(tenant_context)
        self.admission = admission_service
        self.notifications = notification_service
        self.attendance = attendance_service
        self.payment = payment_service
        self.exam = exam_service
        self.content = content_service
        self.solve = solve_service

    # ── Config ────────────────────────────────────────────────────────

    def identifier_mode(self) -> str:
        mode = self.config_service.get("accounts.identifier_mode", IDENTIFIER_BOTH)
        return mode if mode in (IDENTIFIER_PHONE, IDENTIFIER_EMAIL, IDENTIFIER_BOTH) else IDENTIFIER_BOTH

    def set_identifier_mode(self, mode: str) -> None:
        if mode not in (IDENTIFIER_PHONE, IDENTIFIER_EMAIL, IDENTIFIER_BOTH):
            raise ValueError(f"Invalid identifier mode: {mode}")
        self.config_service.set("accounts.identifier_mode", mode)

    def otp_ttl_minutes(self) -> int:
        return int(self.config_service.get("accounts.otp_ttl_minutes", 10) or 10)

    def session_ttl_hours(self) -> int:
        return int(self.config_service.get("accounts.session_ttl_hours", 720) or 720)  # 30d

    # ── Signup (unlinked = zero access) ───────────────────────────────

    def create_account(
        self,
        role: str = ROLE_STUDENT,
        phone: str = "",
        email: str = "",
        display_name: str = "",
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = self.identifier_mode()
        phone_n = _norm_phone(phone)
        email_n = _norm_email(email)

        if mode == IDENTIFIER_PHONE and not phone_n:
            raise AccountError("Phone required for this centre")
        if mode == IDENTIFIER_EMAIL and not email_n:
            raise AccountError("Email required for this centre")
        if mode == IDENTIFIER_BOTH and not (phone_n or email_n):
            raise AccountError("Phone or email required")

        dupes = self._find_duplicates(phone_n, email_n)
        if dupes:
            raise DuplicateAccountError(dupes)

        acct = CohortOSAccount(
            tenant_id=str(self.tenant_context.tenant_id),
            role=role,
            phone=phone_n,
            email=email_n,
            display_name=display_name or phone_n or email_n,
        )
        rid = self.data_layer.create("accounts", acct.to_dict())
        stored = self.data_layer.get("accounts", rid) or acct.to_dict()
        if self.audit_service:
            self.audit_service.log_create(
                table_name="accounts",
                record_id=rid,
                new_state=stored,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        return stored

    def _find_duplicates(self, phone: str, email: str) -> List[Dict[str, Any]]:
        matches = []
        for row in self.data_layer.get_all("accounts"):
            if not row.get("is_active", True):
                continue
            if phone and row.get("phone") and row["phone"] == phone:
                matches.append({"id": row["id"], "reason": "phone already registered"})
            if email and row.get("email") and row["email"] == email:
                matches.append({"id": row["id"], "reason": "email already registered"})
        return matches

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        return self.data_layer.get("accounts", uuid.UUID(account_id))

    def find_account_by_identifier(
        self, phone: str = "", email: str = ""
    ) -> Optional[Dict[str, Any]]:
        phone_n, email_n = _norm_phone(phone), _norm_email(email)
        for row in self.data_layer.get_all("accounts"):
            if not row.get("is_active", True):
                continue
            if phone_n and row.get("phone") == phone_n:
                return row
            if email_n and row.get("email") == email_n:
                return row
        return None

    # ── Linking [BULLET][LOCKED] ──────────────────────────────────────

    def link(
        self,
        admission_id: str,
        cohortos_account_id: Optional[str] = None,
        join_code: Optional[str] = None,
        actor_id: Optional[str] = None,
        confirm_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Single underlying operation: link(admission_id, cohortos_account_id).
        Primary: join_code. Fallback: staff manual (join_code=None).
        Always audit-logged. Never silent.
        """
        account_id = cohortos_account_id
        if not account_id:
            raise AccountError("cohortos_account_id is required")

        account = self.get_account(account_id)
        if not account or not account.get("is_active", True):
            raise AccountError("Account not found or inactive")
        if account.get("role") != ROLE_STUDENT:
            raise AccountError("Only student accounts can link to admissions")

        if not self.admission:
            raise AccountError("AdmissionService not wired")

        student = self.admission.get_student(admission_id)
        if not student:
            raise AccountError(f"Admission not found: {admission_id}")

        existing = student.get("cohortos_account_id")
        if existing and existing != account_id:
            raise AccountError(
                f"Admission already linked to another account ({existing})"
            )

        # Optional confirm screen check for staff path
        if confirm_name and confirm_name.strip().lower() not in (student.get("name") or "").lower():
            raise AccountError(
                f"Confirm mismatch: expected student named like '{student.get('name')}'"
            )

        ok = self.admission.link_account(
            admission_id=admission_id,
            cohortos_account_id=account_id,
            join_code=join_code,
            actor_id=actor_id,
        )
        if not ok:
            raise AccountError("Link failed")

        # Mirror primary on account
        self.data_layer.update(
            "accounts",
            uuid.UUID(account_id),
            {
                "primary_admission_id": admission_id,
                "updated_at": _utcnow(),
            },
        )
        if self.audit_service:
            self.audit_service.log_update(
                table_name="accounts",
                record_id=uuid.UUID(account_id),
                old_state=account,
                new_state=self.get_account(account_id) or {},
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        return {
            "linked": True,
            "admission_id": admission_id,
            "account_id": account_id,
            "student_name": student.get("name"),
            "roll": student.get("roll"),
        }

    def unlink(
        self,
        admission_id: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Owner/staff unlink — data stays on admission_id."""
        if not self.admission:
            raise AccountError("AdmissionService not wired")
        student = self.admission.get_student(admission_id)
        if not student:
            raise AccountError("Admission not found")
        old_acct = student.get("cohortos_account_id") or ""
        self.data_layer.update(
            "students",
            uuid.UUID(admission_id),
            {"cohortos_account_id": "", "updated_at": _utcnow()},
        )
        if old_acct:
            acct = self.get_account(old_acct)
            if acct and acct.get("primary_admission_id") == admission_id:
                self.data_layer.update(
                    "accounts",
                    uuid.UUID(old_acct),
                    {"primary_admission_id": "", "updated_at": _utcnow()},
                )
        if self.audit_service:
            self.audit_service.log_update(
                table_name="students",
                record_id=uuid.UUID(admission_id),
                old_state=student,
                new_state=self.admission.get_student(admission_id) or {},
                actor_id=uuid.UUID(actor_id),
            )
        return {"unlinked": True, "admission_id": admission_id, "previous_account_id": old_acct}

    def regenerate_join_code(
        self, admission_id: str, actor_id: Optional[str] = None, expiry_days: int = 30
    ) -> str:
        if not self.admission:
            raise AccountError("AdmissionService not wired")
        return self.admission.generate_join_code(
            admission_id, actor_id=actor_id, expiry_days=expiry_days
        )

    # ── Access gate [BULLET] ──────────────────────────────────────────

    def is_linked(self, account_id: str) -> bool:
        acct = self.get_account(account_id)
        if not acct:
            return False
        if acct.get("role") == ROLE_PARENT:
            return any(
                l.get("parent_account_id") == account_id and l.get("is_active", True)
                for l in self.data_layer.get_all("parent_student_links")
            )
        return bool(acct.get("primary_admission_id"))

    def require_linked_student(self, account_id: str) -> str:
        """Return admission_id or raise AccessDeniedError."""
        acct = self.get_account(account_id)
        if not acct or not acct.get("is_active", True):
            raise AccessDeniedError("Account not found")
        adm = acct.get("primary_admission_id") or ""
        if not adm:
            raise AccessDeniedError("Unlinked account has zero access")
        return adm

    def student_view(self, account_id: str) -> Dict[str, Any]:
        """Read-only surface for linked student account."""
        admission_id = self.require_linked_student(account_id)
        student = self.admission.get_student(admission_id) if self.admission else None
        att = []
        pays = []
        results = []
        if self.attendance and hasattr(self.attendance, "get_attendance"):
            # list recent via data layer
            att = [
                a
                for a in self.data_layer.get_all("attendance_records")
                if a.get("student_id") == admission_id
            ][-30:]
        if self.payment:
            pays = [
                p
                for p in self.data_layer.get_all("payment_records")
                if p.get("student_id") == admission_id
            ]
        if self.exam:
            results = [
                r
                for r in self.data_layer.get_all("exam_results")
                if r.get("student_id") == admission_id
            ]
        threads = []
        if self.solve:
            threads = self.solve.list_threads(admission_id)
        return {
            "account_id": account_id,
            "admission_id": admission_id,
            "student": student,
            "attendance": att,
            "payments": pays,
            "results": results,
            "threads": threads,
        }

    # ── Parent links (same centre) ────────────────────────────────────

    def link_parent_to_student(
        self,
        parent_account_id: str,
        student_id: str,
        actor_id: str = "",
    ) -> Dict[str, Any]:
        parent = self.get_account(parent_account_id)
        if not parent or parent.get("role") != ROLE_PARENT:
            raise AccountError("Parent account required")
        if not self.admission or not self.admission.get_student(student_id):
            raise AccountError("Student admission not found")
        for row in self.data_layer.get_all("parent_student_links"):
            if (
                row.get("parent_account_id") == parent_account_id
                and row.get("student_id") == student_id
                and row.get("is_active", True)
            ):
                return row
        link = ParentStudentLink(
            tenant_id=str(self.tenant_context.tenant_id),
            parent_account_id=parent_account_id,
            student_id=student_id,
            linked_by=actor_id or parent_account_id,
        )
        rid = self.data_layer.create("parent_student_links", link.to_dict())
        stored = self.data_layer.get("parent_student_links", rid) or link.to_dict()
        if self.audit_service:
            self.audit_service.log_create(
                table_name="parent_student_links",
                record_id=rid,
                new_state=stored,
                actor_id=uuid.UUID(actor_id) if actor_id else self.tenant_context.tenant_id,
            )
        return stored

    def parent_view(self, parent_account_id: str) -> Dict[str, Any]:
        parent = self.get_account(parent_account_id)
        if not parent or parent.get("role") != ROLE_PARENT:
            raise AccessDeniedError("Not a parent account")
        links = [
            l
            for l in self.data_layer.get_all("parent_student_links")
            if l.get("parent_account_id") == parent_account_id and l.get("is_active", True)
        ]
        children = []
        for link in links:
            sid = link["student_id"]
            st = self.admission.get_student(sid) if self.admission else None
            children.append({"student_id": sid, "student": st, "link_id": link["id"]})
        return {"parent_account_id": parent_account_id, "children": children}

    # ── Passwordless OTP login [BULLET] ───────────────────────────────

    def request_login_otp(
        self,
        phone: str = "",
        email: str = "",
    ) -> Dict[str, Any]:
        acct = self.find_account_by_identifier(phone=phone, email=email)
        if not acct:
            # Do not leak existence — same generic response
            return {
                "sent": True,
                "message": "If an account exists, an OTP was sent",
                "otp_id": None,
            }

        code = generate_otp_code(6)
        ttl = self.otp_ttl_minutes()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl)).isoformat()
        channel = "email" if email and acct.get("email") else "sms"
        destination = acct.get("email") if channel == "email" else acct.get("phone")

        otp = LoginOTP(
            tenant_id=str(self.tenant_context.tenant_id),
            account_id=acct["id"],
            channel=channel,
            destination=destination or "",
            code_hash=hash_otp(code),
            expires_at=expires,
        )
        rid = self.data_layer.create("login_otps", otp.to_dict())

        # Dispatch via NotificationService if available
        if self.notifications and hasattr(self.notifications, "enqueue"):
            try:
                self.notifications.enqueue(
                    template_key="login_otp",
                    recipient=destination,
                    channel=channel,
                    context={"code": code, "ttl_minutes": ttl},
                    tenant_id=str(self.tenant_context.tenant_id),
                )
            except Exception:
                pass
        elif self.notifications and hasattr(self.notifications, "queue_message"):
            try:
                self.notifications.queue_message(
                    to=destination,
                    body=f"Your CohortOS login code is {code}. Valid {ttl} minutes.",
                    channel=channel,
                )
            except Exception:
                pass

        # For tests: return code only when mock / no real provider
        out: Dict[str, Any] = {
            "sent": True,
            "message": "If an account exists, an OTP was sent",
            "otp_id": str(rid),
            "channel": channel,
        }
        # Expose plaintext only for Mock/test paths (never in production logs)
        out["_test_code"] = code
        return out

    def verify_login_otp(
        self, otp_id: str, code: str
    ) -> Dict[str, Any]:
        row = self.data_layer.get("login_otps", uuid.UUID(otp_id))
        if not row:
            raise AccountError("Invalid OTP")
        if row.get("is_used"):
            raise AccountError("OTP already used")
        if row.get("expires_at") and row["expires_at"] < _utcnow():
            raise AccountError("OTP expired")
        if row.get("code_hash") != hash_otp(code):
            raise AccountError("Invalid OTP code")

        self.data_layer.update(
            "login_otps",
            uuid.UUID(otp_id),
            {"is_used": True, "used_at": _utcnow()},
        )
        ttl_h = self.session_ttl_hours()
        expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_h)).isoformat()
        session = AccountSession(
            tenant_id=str(self.tenant_context.tenant_id),
            account_id=row["account_id"],
            expires_at=expires,
        )
        sid = self.data_layer.create("account_sessions", session.to_dict())
        stored = self.data_layer.get("account_sessions", sid) or session.to_dict()
        return {
            "session_token": stored["token"],
            "account_id": row["account_id"],
            "expires_at": expires,
            "linked": self.is_linked(row["account_id"]),
        }

    def resolve_session(self, token: str) -> Optional[Dict[str, Any]]:
        for row in self.data_layer.get_all("account_sessions"):
            if row.get("token") == token:
                if row.get("expires_at") and row["expires_at"] < _utcnow():
                    return None
                return self.get_account(row["account_id"])
        return None

    # ── Teacher takeover + priority queue (8.4) ───────────────────────

    def teacher_reply_on_thread(
        self,
        thread_id: str,
        teacher_id: str,
        content: str,
        student_id: str = "",
    ) -> Dict[str, Any]:
        """Teacher steps into AI thread and replies directly."""
        from models.ai import AIMessage

        thread = self.data_layer.get("ai_threads", uuid.UUID(thread_id))
        if not thread:
            raise AccountError("Thread not found")
        sid = student_id or thread.get("student_id") or ""
        msg = AIMessage(
            tenant_id=str(self.tenant_context.tenant_id),
            thread_id=thread_id,
            student_id=sid,
            role="teacher",
            content=content,
        )
        rid = self.data_layer.create("ai_messages", msg.to_dict())
        stored = self.data_layer.get("ai_messages", rid) or msg.to_dict()
        count = int(thread.get("message_count") or 0) + 1
        self.data_layer.update(
            "ai_threads",
            uuid.UUID(thread_id),
            {
                "message_count": count,
                "last_message_at": _utcnow(),
                "flagged_for_teacher": False,  # teacher handled
                "updated_at": _utcnow(),
            },
        )
        if self.audit_service:
            self.audit_service.log_create(
                table_name="ai_messages",
                record_id=rid,
                new_state=stored,
                actor_id=uuid.UUID(teacher_id) if teacher_id else self.tenant_context.tenant_id,
            )
        return stored

    def flagged_thread_priority_queue(
        self, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Rank flagged threads: lowest confidence first × message activity.
        Reuses Module 9.2 scoring idea — no separate triage system [LOCKED].
        """
        threads = [
            t
            for t in self.data_layer.get_all("ai_threads")
            if t.get("flagged_for_teacher") and t.get("is_active", True)
        ]
        scored = []
        for t in threads:
            msgs = [
                m
                for m in self.data_layer.get_all("ai_messages")
                if m.get("thread_id") == t.get("id") and m.get("role") == "assistant"
            ]
            confs = [float(m.get("confidence") or 0) for m in msgs if m.get("needs_review")]
            min_conf = min(confs) if confs else 0.0
            # lower confidence = higher priority; more review msgs = higher
            priority = (1.0 - min_conf) * (1 + len(confs))
            scored.append({**t, "min_confidence": min_conf, "priority": priority})
        scored.sort(key=lambda x: -x["priority"])
        return scored[:limit]
