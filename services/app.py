"""
CohortOS composition root — single entry point for integrators.

Usage (Electron bridge / FastAPI dependency / tests):

    from services.app import CohortOSApp
    app = CohortOSApp(tenant_id="...", mode="offline-first")
    student_id = app.admission.admit_student(...)
    app.attendance.record_manual(...)
    ...

All core Module 1–5 services + sync + notification are wired with shared
DataAccessLayer, AuditService, and ConfigService so history, locks, and
anti-leak rules remain consistent.
"""

from __future__ import annotations

import uuid
from typing import Optional, Union
from datetime import datetime, timezone

from models.base import TenantContext, DataAccessLayer
from services.audit_service import AuditService
from services.config_service import ConfigService
from services.admission_service import AdmissionService
from services.attendance_service import AttendanceService
from services.payment_service import PaymentService
from services.exam_service import ExamService
from services.content_service import ContentService
from services.sync_engine import SyncEngine
from services.notification_service import NotificationService
from services.data_access import DataService
from services.llm_provider import LLMProvider, MockLLMProvider, GeminiProvider
from services.retrieval_service import RetrievalService
from services.ai_quota_service import AIQuotaService
from services.ai_solve_service import AISolveService
from services.ai_teach_service import AITeachService
from services.account_service import AccountService


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CohortOSApp:
    """
    Production composition root for a single centre (tenant).

    - Offline-first by default (SPEC §0 / §7).
    - One shared DataAccessLayer so all modules see the same in-memory
      (or future SQLite) store and pending sync ops.
    - Optional NotificationService + SyncEngine; core CRUD never requires them.
    """

    def __init__(
        self,
        tenant_id: Optional[Union[str, uuid.UUID]] = None,
        mode: str = "offline-first",
        data_layer: Optional[DataAccessLayer] = None,
        enable_sync: bool = True,
        enable_notifications: bool = True,
        db_path: str = ":memory:",
        llm: "LLMProvider | None" = None,
    ):
        if tenant_id is None:
            tenant_id = uuid.uuid4()
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        if mode not in ("offline-first", "cloud-first", "hybrid"):
            raise ValueError(f"Invalid mode: {mode}")

        self.tenant_context = TenantContext(tenant_id=tenant_id, mode=mode)
        # db_path forwarded so file-backed SQLite persists across restarts.
        # ":memory:" (default) keeps each app instance isolated for tests.
        self.data_layer = data_layer or DataAccessLayer(
            self.tenant_context, db_path=db_path
        )

        # Core cross-cutting
        self.audit = AuditService(self.tenant_context)
        self.config = ConfigService(self.tenant_context, data_service=None)
        from services.automation_service import AutomationService
        self.automation = AutomationService(
            payment_service=None,  # wired below after payment init
            attendance_service=None,
            config_service=self.config,
        )
        # ConfigService can accept a data_service; we keep it simple and let it use its own storage.

        self.sync: Optional[SyncEngine] = None
        self.notifications: Optional[NotificationService] = None

        if enable_sync:
            try:
                self.sync = SyncEngine(
                    self.tenant_context,
                    self.config,
                    db_path=db_path,
                )
                if hasattr(self.sync, "initialize"):
                    self.sync.initialize()
            except Exception:
                # Sync is optional for pure offline unit use; never block core.
                self.sync = None

        if enable_notifications:
            try:
                self.notifications = NotificationService(
                    self.tenant_context,
                    self.config,
                    db_path=db_path,
                )
            except Exception:
                self.notifications = None

        # Domain services — shared layer + audit + config
        self.admission = AdmissionService(
            self.tenant_context,
            data_layer=self.data_layer,
            audit_service=self.audit,
            config_service=self.config,
            sync_engine=self.sync,
        )
        self.attendance = AttendanceService(
            self.tenant_context,
            data_layer=self.data_layer,
            audit_service=self.audit,
            config_service=self.config,
            notification_service=self.notifications,
            sync_engine=self.sync,
        )
        self.payment = PaymentService(
            self.tenant_context,
            data_layer=self.data_layer,
            audit_service=self.audit,
            config_service=self.config,
            attendance_service=self.attendance,
            notification_service=self.notifications,
            sync_engine=self.sync,
        )
        if getattr(self, "automation", None):
            self.automation.payment = self.payment
            self.automation.attendance = self.attendance

        self.exam = ExamService(
            self.tenant_context,
            data_layer=self.data_layer,
            audit_service=self.audit,
            config_service=self.config,
            attendance_service=self.attendance,
            sync_engine=self.sync,
        )
        self.content = ContentService(
            self.tenant_context,
            data_layer=self.data_layer,
            audit_service=self.audit,
            config_service=self.config,
            attendance_service=self.attendance,
            payment_service=self.payment,
            exam_service=self.exam,
            sync_engine=self.sync,
        )

        # AI (Module 9) — default Mock provider; inject GeminiProvider for live
        self.llm = llm or MockLLMProvider()
        self.retrieval = RetrievalService(
            self.tenant_context, self.data_layer, content_service=self.content
        )
        self.ai_quota = AIQuotaService(
            self.tenant_context, self.data_layer, self.config
        )
        self.solve = AISolveService(
            self.tenant_context,
            data_layer=self.data_layer,
            config_service=self.config,
            audit_service=self.audit,
            llm=self.llm,
            retrieval=self.retrieval,
            quota=self.ai_quota,
            content_service=self.content,
        )
        self.teach = AITeachService(
            self.tenant_context,
            data_layer=self.data_layer,
            config_service=self.config,
            audit_service=self.audit,
            llm=self.llm,
            retrieval=self.retrieval,
            content_service=self.content,
            exam_service=self.exam,
        )

        self.accounts = AccountService(
            self.tenant_context,
            data_layer=self.data_layer,
            config_service=self.config,
            audit_service=self.audit,
            admission_service=self.admission,
            notification_service=self.notifications,
            attendance_service=self.attendance,
            payment_service=self.payment,
            exam_service=self.exam,
            content_service=self.content,
            solve_service=self.solve,
        )

        # Convenience high-level data service (centres / users / roles)
        self.data = DataService(
            self.tenant_context,
            config_service=self.config,
            sync_engine=self.sync,
        )
        # Share the same SQLite-backed layer (DataService constructs its own by
        # default — replace so bootstrap/centres persist with the rest of the app).
        self.data.data_layer = self.data_layer
        self.data.set_audit_service(self.audit)

        # Wire content rule evaluators if services expose the expected helpers
        # (ContentService already accepts the service instances above.)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant_context.tenant_id

    @property
    def mode(self) -> str:
        return self.tenant_context.mode

    def bootstrap_centre(
        self,
        name: str = "Origin Physics Coaching",
        code: str = "BARISHAL-PHY",
        owner_email: Optional[str] = None,
        owner_phone: Optional[str] = None,
        create_sample_batches: bool = True,
    ) -> dict:
        """
        Create the centre record + default roles and (optionally) sample batches
        matching the origin client's shape (~10 batches, common day sets).
        Returns a summary dict for handoff / tests.
        """
        centre_id = self.data.create_centre(
            name=name,
            code=code,
            owner_email=owner_email,
            owner_phone=owner_phone,
            config_mode=self.mode,
        )

        # Default roles (RBAC)
        owner_role = self.data.create_role("owner", "Owner / Admin")
        desk_role = self.data.create_role("desk", "Front Desk")
        teacher_role = self.data.create_role("teacher", "Teacher")
        assistant_role = self.data.create_role("assistant", "Assistant")

        # Sensible defaults already live in ConfigService; ensure irregularity threshold
        self.config.set("irregularity.min_days_attended_month", 3)
        self.config.set("attendance.late_threshold_minutes", 12)

        batches = []
        if create_sample_batches:
            # Typical physics coaching pattern (Sat/Mon/Wed or Sun/Tue/Thu style)
            samples = [
                (["sat", "mon", "wed"], 14),
                (["sat", "mon", "wed"], 16),
                (["sun", "tue", "thu"], 14),
                (["sun", "tue", "thu"], 16),
                (["fri"], 10),
                (["fri"], 15),
            ]
            for days, hour in samples:
                bid = self.admission.create_batch(days=days, hour=hour)
                batches.append(bid)

        return {
            "centre_id": str(centre_id),
            "tenant_id": str(self.tenant_id),
            "mode": self.mode,
            "roles": {
                "owner": str(owner_role),
                "desk": str(desk_role),
                "teacher": str(teacher_role),
                "assistant": str(assistant_role),
            },
            "batch_ids": batches,
            "created_at": _utcnow(),
        }

    def health(self) -> dict:
        """Lightweight readiness for integrators / health checks."""
        return {
            "tenant_id": str(self.tenant_id),
            "mode": self.mode,
            "services": {
                "admission": self.admission is not None,
                "attendance": self.attendance is not None,
                "payment": self.payment is not None,
                "exam": self.exam is not None,
                "content": self.content is not None,
                "solve": self.solve is not None,
                "teach": self.teach is not None,
                "accounts": self.accounts is not None,
                "sync": self.sync is not None,
                "notifications": self.notifications is not None,
            },
            "pending_ops": len(self.data_layer.get_pending_operations())
            if hasattr(self.data_layer, "get_pending_operations")
            else 0,
        }




def create_app(
    tenant_id: Optional[Union[str, uuid.UUID]] = None,
    mode: str = "offline-first",
    **kwargs,
) -> CohortOSApp:
    """Factory used by FastAPI Depends() or Electron bridge."""
    return CohortOSApp(tenant_id=tenant_id, mode=mode, **kwargs)
