"""
Audit logging models for CohortOS
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass
import uuid
import json
from datetime import datetime, timezone
from .base import BaseModel, TenantContext, _utcnow


@dataclass
class AuditLog(BaseModel):
    """Audit log entry capturing all mutations"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    action: str  # CREATE, UPDATE, DELETE
    table_name: str
    record_id: uuid.UUID
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    device_id: Optional[str] = None
    session_id: Optional[uuid.UUID] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'actor_id': str(self.actor_id),
            'action': self.action,
            'table_name': self.table_name,
            'record_id': str(self.record_id),
            'before': json.dumps(self.before) if self.before else None,
            'after': json.dumps(self.after) if self.after else None,
            'device_id': self.device_id,
            'session_id': str(self.session_id) if self.session_id else None,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'AuditLog':
        """Create from dictionary"""
        return cls(
            id=uuid.UUID(data['id']),
            tenant_id=uuid.UUID(data['tenant_id']),
            actor_id=uuid.UUID(data['actor_id']),
            action=data['action'],
            table_name=data['table_name'],
            record_id=uuid.UUID(data['record_id']),
            before=json.loads(data['before']) if data.get('before') else None,
            after=json.loads(data['after']) if data.get('after') else None,
            device_id=data.get('device_id'),
            session_id=uuid.UUID(data['session_id']) if data.get('session_id') else None,
            created_at=data.get('created_at')
        )

    def get_table_name(self) -> str:
        return 'audit_logs'

    def get_primary_key(self) -> str:
        return 'id'

    @staticmethod
    def create_from_operation(operation: str, table_name: str, old_state: Optional[Dict] = None,
                             new_state: Optional[Dict] = None, record_id: uuid.UUID = None,
                             actor_id: uuid.UUID = None, tenant_id: uuid.UUID = None,
                             device_id: Optional[str] = None, session_id: Optional[uuid.UUID] = None) -> 'AuditLog':
        """Create audit log entry from data operation"""
        return AuditLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=operation.upper(),
            table_name=table_name,
            record_id=record_id,
            before=old_state,
            after=new_state,
            device_id=device_id,
            session_id=session_id,
            created_at=_utcnow()
        )