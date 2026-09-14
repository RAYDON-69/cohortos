"""
Per-tenant configuration models for CohortOS
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass
import uuid
from .base import BaseModel, TenantContext


@dataclass
class TenantConfig(BaseModel):
    """Tenant configuration model - stores per-tenant settings"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    key: str
    value: Any
    is_system: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'key': self.key,
            'value': self.value,  # JSONB equivalent in Python
            'is_system': self.is_system,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'TenantConfig':
        """Create from dictionary"""
        return cls(
            id=uuid.UUID(data['id']),
            tenant_id=uuid.UUID(data['tenant_id']),
            key=data['key'],
            value=data['value'],
            is_system=data.get('is_system', False),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    def get_table_name(self) -> str:
        return 'tenant_configs'

    def get_primary_key(self) -> str:
        return 'id'


@dataclass
class ConfigDefaults:
    """Default configuration values for new tenants"""

    # Attendance settings
    ATTENDANCE_AUTO_START = False
    ATTENDANCE_AUTO_END = False
    ATTENDANCE_GRACE_PERIOD_MINUTES = 5

    # Payment settings
    PAYMENT_LOCK_DAYS = 30
    PAYMENT_AUTO_NOTIFY = True

    # Notification settings
    NOTIFICATION_EMAIL_ENABLED = True
    NOTIFICATION_SMS_ENABLED = True

    # Security settings
    PASSWORD_MIN_LENGTH = 8
    SESSION_TIMEOUT_MINUTES = 30

    # UI settings
    THEME = 'light'
    LANGUAGE = 'en'

    @classmethod
    def get_defaults(cls) -> Dict[str, Any]:
        """Get all default configuration values"""
        return {
            'attendance.auto_start': cls.ATTENDANCE_AUTO_START,
            'attendance.auto_end': cls.ATTENDANCE_AUTO_END,
            'attendance.grace_period_minutes': cls.ATTENDANCE_GRACE_PERIOD_MINUTES,
            'payment.lock_days': cls.PAYMENT_LOCK_DAYS,
            'payment.auto_notify': cls.PAYMENT_AUTO_NOTIFY,
            'notification.email_enabled': cls.NOTIFICATION_EMAIL_ENABLED,
            'notification.sms_enabled': cls.NOTIFICATION_SMS_ENABLED,
            'security.password_min_length': cls.PASSWORD_MIN_LENGTH,
            'security.session_timeout_minutes': cls.SESSION_TIMEOUT_MINUTES,
            'ui.theme': cls.THEME,
            'ui.language': cls.LANGUAGE
        }