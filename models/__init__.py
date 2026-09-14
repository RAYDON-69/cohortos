"""CohortOS domain models."""

from models.base import TenantContext, DataAccessLayer, BaseModel
from models.tenant import Centre, User, Role, Permission
from models.audit import AuditLog
from models.config import TenantConfig, ConfigDefaults
from models.admission import Student, Batch, BatchTemplate, JoinCode, MigrationRecord, DuplicateMatch
from models.attendance import AttendanceDevice, PunchRecord, AttendanceRecord, ReviewFlag
from models.payment import PaymentRecord, PaymentUnlockEvent
from models.exam import ExamTemplate, Exam, ExamResult
from models.content import (
    ContentResource,
    AccessRule,
    AccessRuleset,
    OfflineCacheEntry,
    LiveSession,
    ViewerSessionToken,
)
from models.sync import SyncOperation, SyncConflict, SyncSession, TenantSyncStatus
from models.notification import (
    NotificationTemplate,
    NotificationChannel,
    NotificationPreference,
    NotificationQueue,
    Notification,
    NotificationMetrics,
    NotificationEvent,
)

__all__ = [
    "TenantContext",
    "DataAccessLayer",
    "BaseModel",
    "Centre",
    "User",
    "Role",
    "Permission",
    "AuditLog",
    "TenantConfig",
    "ConfigDefaults",
    "Student",
    "Batch",
    "BatchTemplate",
    "JoinCode",
    "MigrationRecord",
    "DuplicateMatch",
    "AttendanceDevice",
    "PunchRecord",
    "AttendanceRecord",
    "ReviewFlag",
    "PaymentRecord",
    "PaymentUnlockEvent",
    "ExamTemplate",
    "Exam",
    "ExamResult",
    "ContentResource",
    "AccessRule",
    "AccessRuleset",
    "OfflineCacheEntry",
    "LiveSession",
    "ViewerSessionToken",
    "SyncOperation",
    "SyncConflict",
    "SyncSession",
    "TenantSyncStatus",
    "NotificationTemplate",
    "NotificationChannel",
    "NotificationPreference",
    "NotificationQueue",
    "Notification",
    "NotificationMetrics",
    "NotificationEvent",
]
