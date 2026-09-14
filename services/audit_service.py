"""
Audit logging service for CohortOS
Automatically captures all mutations with before/after states
"""

import uuid
import json
import functools
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timezone
from models.base import TenantContext
from models.audit import AuditLog


class AuditService:
    """Service for automatically logging all mutations"""

    def __init__(self, tenant_context: TenantContext):
        self.tenant_context = tenant_context
        self.pending_logs = []

    def log_create(self, table_name: str, record_id: uuid.UUID, new_state: Dict[str, Any],
                  actor_id: uuid.UUID = None, device_id: Optional[str] = None,
                  session_id: Optional[uuid.UUID] = None) -> None:
        """Log a CREATE operation"""
        audit_log = AuditLog.create_from_operation(
            operation='create',
            table_name=table_name,
            new_state=new_state,
            record_id=record_id,
            actor_id=actor_id or self.tenant_context.tenant_id,
            tenant_id=self.tenant_context.tenant_id,
            device_id=device_id,
            session_id=session_id
        )
        self.pending_logs.append(audit_log)

    def log_update(self, table_name: str, record_id: uuid.UUID, old_state: Dict[str, Any],
                   new_state: Dict[str, Any], actor_id: uuid.UUID = None,
                   device_id: Optional[str] = None, session_id: Optional[uuid.UUID] = None) -> None:
        """Log an UPDATE operation"""
        audit_log = AuditLog.create_from_operation(
            operation='update',
            table_name=table_name,
            old_state=old_state,
            new_state=new_state,
            record_id=record_id,
            actor_id=actor_id or self.tenant_context.tenant_id,
            tenant_id=self.tenant_context.tenant_id,
            device_id=device_id,
            session_id=session_id
        )
        self.pending_logs.append(audit_log)

    def log_delete(self, table_name: str, record_id: uuid.UUID, old_state: Dict[str, Any],
                   actor_id: uuid.UUID = None, device_id: Optional[str] = None,
                   session_id: Optional[uuid.UUID] = None) -> None:
        """Log a DELETE operation"""
        audit_log = AuditLog.create_from_operation(
            operation='delete',
            table_name=table_name,
            old_state=old_state,
            record_id=record_id,
            actor_id=actor_id or self.tenant_context.tenant_id,
            tenant_id=self.tenant_context.tenant_id,
            device_id=device_id,
            session_id=session_id
        )
        self.pending_logs.append(audit_log)

    def get_pending_logs(self) -> list:
        """Get all pending audit logs"""
        return self.pending_logs.copy()

    def clear_pending_logs(self):
        """Clear all pending audit logs (after persistence)"""
        self.pending_logs.clear()

    def save_logs_to_storage(self, storage_interface) -> bool:
        """Save pending logs to persistent storage"""
        if not self.pending_logs:
            return True

        try:
            # This would normally save to the database
            for log in self.pending_logs:
                # Convert to dict for storage
                log_dict = {
                    'id': str(log.id),
                    'tenant_id': str(log.tenant_id),
                    'actor_id': str(log.actor_id),
                    'action': log.action,
                    'table_name': log.table_name,
                    'record_id': str(log.record_id),
                    'before': json.dumps(log.before) if log.before else None,
                    'after': json.dumps(log.after) if log.after else None,
                    'device_id': log.device_id,
                    'session_id': str(log.session_id) if log.session_id else None,
                    'created_at': log.created_at
                }
                # Save to storage interface (data layer)
                storage_interface.create('audit_logs', log_dict)

            self.clear_pending_logs()
            return True
        except Exception as e:
            print(f"Failed to save audit logs: {e}")
            return False


def audit_operation(operation_type: str):
    """
    Decorator to automatically audit operations
    Usage:
        @audit_operation('create')
        def create_user(...): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract data from the function call
            self = args[0]  # Assuming method on self
            table_name = func.__name__.replace('create_', '').replace('update_', '').replace('delete_', '')
            table_name = table_name + 's'  # Pluralize

            # Get actor ID - should be passed in kwargs
            actor_id = kwargs.get('actor_id')
            device_id = kwargs.get('device_id')
            session_id = kwargs.get('session_id')

            if operation_type == 'create':
                # Function should return the created record ID
                record_id = func(*args, **kwargs)
                if record_id and hasattr(self, 'get'):
                    new_state = self.get(record_id)
                    if new_state:
                        self.audit_service.log_create(
                            table_name=table_name,
                            record_id=record_id,
                            new_state=new_state,
                            actor_id=actor_id,
                            device_id=device_id,
                            session_id=session_id
                        )
                return record_id

            elif operation_type == 'update':
                # For update, we need the old state first
                record_id = kwargs.get('record_id') or args[1]  # Common patterns
                old_state = self.get(record_id) if hasattr(self, 'get') else None
                success = func(*args, **kwargs)
                if success and hasattr(self, 'get'):
                    new_state = self.get(record_id)
                    if old_state and new_state:
                        self.audit_service.log_update(
                            table_name=table_name,
                            record_id=record_id,
                            old_state=old_state,
                            new_state=new_state,
                            actor_id=actor_id,
                            device_id=device_id,
                            session_id=session_id
                        )
                return success

            elif operation_type == 'delete':
                record_id = kwargs.get('record_id') or args[1]
                old_state = self.get(record_id) if hasattr(self, 'get') else None
                success = func(*args, **kwargs)
                if success and old_state:
                    self.audit_service.log_delete(
                        table_name=table_name,
                        record_id=record_id,
                        old_state=old_state,
                        actor_id=actor_id,
                        device_id=device_id,
                        session_id=session_id
                    )
                return success

            return func(*args, **kwargs)

        return wrapper
    return decorator


# Example usage mixin for classes that want automatic auditing
class AuditableMixin:
    """Mixin for classes that want automatic audit logging"""

    def __init__(self, audit_service: AuditService, tenant_context: TenantContext):
        self.audit_service = audit_service
        self.tenant_context = tenant_context

    def with_audit(self, operation_type: str):
        """Decorator for auditing operations"""
        return audit_operation(operation_type)