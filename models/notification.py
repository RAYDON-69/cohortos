"""
Notification models for CohortOS notification system
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import uuid
import json
from datetime import datetime, timezone
from .base import BaseModel, TenantContext


@dataclass
class NotificationTemplate:
    """Represents a notification template"""
    id: Optional[str] = None
    tenant_id: str = ''
    name: str = ''
    template_type: str = 'email'  # email, sms, push
    channel: str = ''  # in-app, email, sms
    subject_template: str = ''
    body_template: str = ''
    is_active: bool = True
    variables: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def render(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """Render template with variables.

        Known variables from self.variables that are missing in the provided
        dict are substituted with 'N/A' so callers never see raw {{placeholders}}.
        """
        import re
        rendered_subject = self.subject_template
        rendered_body = self.body_template

        # Fill declared variables (missing → N/A)
        for key in self.variables:
            value = variables.get(key, 'N/A')
            token = '{{' + key + '}}'
            rendered_subject = rendered_subject.replace(token, str(value))
            rendered_body = rendered_body.replace(token, str(value))

        # Also apply any extra keys the caller provided
        for key, value in variables.items():
            token = '{{' + key + '}}'
            rendered_subject = rendered_subject.replace(token, str(value))
            rendered_body = rendered_body.replace(token, str(value))

        # Any remaining {{placeholders}} → N/A
        rendered_subject = re.sub(r'\{\{[^}]+\}\}', 'N/A', rendered_subject)
        rendered_body = re.sub(r'\{\{[^}]+\}\}', 'N/A', rendered_body)

        return {
            'subject': rendered_subject,
            'body': rendered_body
        }



@dataclass
class NotificationChannel:
    """Represents a notification channel configuration"""
    id: Optional[str] = None
    tenant_id: str = ''
    channel_type: str = 'email'  # email, sms, push
    config: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    priority: int = 5  # 1-10, higher = higher priority
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class NotificationPreference:
    """User notification preferences"""
    id: Optional[str] = None
    user_id: str = ''
    tenant_id: str = ''
    channel_type: str = 'email'
    event_type: str = ''
    enabled: bool = True
    scheduled_time: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class NotificationQueue:
    """Represents a notification in the queue"""
    id: Optional[int] = None
    notification_id: str = ''
    tenant_id: str = ''
    user_id: str = ''
    event_type: str = ''
    channel_type: str = ''
    subject: str = ''
    content: str = ''
    priority: int = 5
    status: str = 'pending'  # pending, scheduled, sent, failed, cancelled
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    template_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.notification_id:
            self.notification_id = str(uuid.uuid4())


@dataclass
class Notification:
    """Represents a sent notification"""
    id: Optional[str] = None
    tenant_id: str = ''
    user_id: str = ''
    event_type: str = ''
    channel_type: str = ''
    subject: str = ''
    content: str = ''
    status: str = 'sent'  # sent, delivered, failed, cancelled
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())


@dataclass
class NotificationMetrics:
    """Notification delivery metrics"""
    tenant_id: str = ''
    date: str = ''
    total_sent: int = 0
    delivered: int = 0
    failed: int = 0
    pending: int = 0
    channels: Dict[str, int] = field(default_factory=dict)
    event_types: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'tenant_id': self.tenant_id,
            'date': self.date,
            'total_sent': self.total_sent,
            'delivered': self.delivered,
            'failed': self.failed,
            'pending': self.pending,
            'channels': self.channels,
            'event_types': self.event_types
        }


@dataclass
class NotificationEvent:
    """Represents a notification event"""
    event_type: str = ''
    template_name: str = ''
    variables: Dict[str, Any] = field(default_factory=dict)
    user_ids: List[str] = field(default_factory=list)
    channel_types: List[str] = field(default_factory=list)
    priority: int = 5
    scheduled_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)