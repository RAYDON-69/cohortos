"""
Sync models for CohortOS offline-first sync engine.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import uuid
import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from .base import BaseModel, TenantContext


@dataclass
class SyncOperation:
    """Represents a single sync operation"""
    id: Optional[int] = None
    operation_type: str = 'create'  # create, update, delete
    table_name: str = ''
    record_id: str = ''
    tenant_id: str = ''
    old_state: Optional[Dict[str, Any]] = None
    new_state: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sync_status: str = 'pending'  # pending, in_progress, completed, failed
    error_message: Optional[str] = None
    retry_count: int = 0
    last_attempt_time: Optional[str] = None
    record_hash: Optional[str] = None
    resolved_at: Optional[str] = None

    def __post_init__(self):
        if not self.record_hash:
            self.record_hash = self._calculate_hash()

        if self.operation_type not in ['create', 'update', 'delete']:
            raise ValueError(f"Invalid operation type: {self.operation_type}")

        # Ensure resolved_at is set for existing conflicts
        if not self.resolved_at:
            self.resolved_at = datetime.now(timezone.utc).isoformat()

    def _calculate_hash(self) -> str:
        """Calculate hash for conflict detection"""
        hash_data = {
            'operation_type': self.operation_type,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'tenant_id': self.tenant_id,
            'new_state': self.new_state
        }
        if self.old_state:
            hash_data['old_state'] = self.old_state

        # Sort keys for consistent hashing
        sorted_data = json.dumps(hash_data, sort_keys=True, default=str)
        return hashlib.md5(sorted_data.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'operation_type': self.operation_type,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'tenant_id': self.tenant_id,
            'old_state': json.dumps(self.old_state) if self.old_state else None,
            'new_state': json.dumps(self.new_state),
            'created_at': self.created_at,
            'sync_status': self.sync_status,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'last_attempt_time': self.last_attempt_time,
            'record_hash': self.record_hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncOperation':
        """Create from dictionary"""
        return cls(
            id=data.get('id'),
            operation_type=data['operation_type'],
            table_name=data['table_name'],
            record_id=data['record_id'],
            tenant_id=data['tenant_id'],
            old_state=json.loads(data['old_state']) if data.get('old_state') else None,
            new_state=json.loads(data['new_state']),
            created_at=data['created_at'],
            sync_status=data['sync_status'],
            error_message=data.get('error_message'),
            retry_count=data.get('retry_count', 0),
            last_attempt_time=data.get('last_attempt_time'),
            record_hash=data.get('record_hash')
        )


@dataclass
class SyncConflict:
    """Represents a sync conflict that needs resolution"""
    id: Optional[int] = None
    record_id: str = ''
    table_name: str = ''
    tenant_id: str = ''
    field_name: str = ''
    local_value: Any = None
    remote_value: Any = None
    resolved_by: str = 'local'  # local, remote, manual
    resolved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    operation_type: str = 'update'
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'record_id': self.record_id,
            'table_name': self.table_name,
            'tenant_id': self.tenant_id,
            'field_name': self.field_name,
            'local_value': json.dumps(self.local_value) if self.local_value is not None else None,
            'remote_value': json.dumps(self.remote_value) if self.remote_value is not None else None,
            'resolved_by': self.resolved_by,
            'resolved_at': self.resolved_at,
            'operation_type': self.operation_type,
            'error_message': self.error_message
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncConflict':
        """Create from dictionary"""
        return cls(
            id=data.get('id'),
            record_id=data['record_id'],
            table_name=data['table_name'],
            tenant_id=data['tenant_id'],
            field_name=data['field_name'],
            local_value=json.loads(data['local_value']) if data.get('local_value') is not None else None,
            remote_value=json.loads(data['remote_value']) if data.get('remote_value') is not None else None,
            resolved_by=data['resolved_by'],
            resolved_at=data['resolved_at'],
            operation_type=data['operation_type'],
            error_message=data.get('error_message')
        )


@dataclass
class SyncSession:
    """Represents a sync session"""
    id: Optional[int] = None
    session_id: str = ''
    tenant_id: str = ''
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    status: str = 'running'  # running, completed, failed, cancelled
    records_synced: int = 0
    errors_count: int = 0
    sync_mode: str = 'offline-first'
    last_operation_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'tenant_id': self.tenant_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'status': self.status,
            'records_synced': self.records_synced,
            'errors_count': self.errors_count,
            'sync_mode': self.sync_mode,
            'last_operation_id': self.last_operation_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncSession':
        """Create from dictionary"""
        return cls(
            id=data.get('id'),
            session_id=data['session_id'],
            tenant_id=data['tenant_id'],
            start_time=data['start_time'],
            end_time=data.get('end_time'),
            status=data['status'],
            records_synced=data.get('records_synced', 0),
            errors_count=data.get('errors_count', 0),
            sync_mode=data['sync_mode'],
            last_operation_id=data.get('last_operation_id')
        )


@dataclass
class TenantSyncStatus:
    """Represents sync status for a tenant"""
    tenant_id: str = ''
    last_sync_time: Optional[str] = None
    sync_enabled: bool = True
    conflict_resolution_strategy: str = 'last-write-wins'
    offline_changes: int = 0
    pending_operations: int = 0
    last_error: Optional[str] = None
    error_count: int = 0
    settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'tenant_id': self.tenant_id,
            'last_sync_time': self.last_sync_time,
            'sync_enabled': self.sync_enabled,
            'conflict_resolution_strategy': self.conflict_resolution_strategy,
            'offline_changes': self.offline_changes,
            'pending_operations': self.pending_operations,
            'last_error': self.last_error,
            'error_count': self.error_count,
            'settings': json.dumps(self.settings)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TenantSyncStatus':
        """Create from dictionary"""
        return cls(
            tenant_id=data['tenant_id'],
            last_sync_time=data.get('last_sync_time'),
            sync_enabled=data.get('sync_enabled', True),
            conflict_resolution_strategy=data.get('conflict_resolution_strategy', 'last-write-wins'),
            offline_changes=data.get('offline_changes', 0),
            pending_operations=data.get('pending_operations', 0),
            last_error=data.get('last_error'),
            error_count=data.get('error_count', 0),
            settings=json.loads(data['settings']) if data.get('settings') else {}
        )