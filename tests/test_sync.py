"""
Tests for CohortOS Sync Engine - Offline-First Synchronization
"""

import pytest
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any

from models.base import TenantContext
from models.sync import SyncOperation, SyncConflict, SyncSession, TenantSyncStatus
from services.sync_engine import SyncEngine
from services.config_service import ConfigService
from services.data_access import DataService


class TestSyncEngine:
    """Test cases for SyncEngine"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')

    def test_initialize_sync_engine(self):
        """Test sync engine initialization"""
        result = self.sync_engine.initialize()
        assert result is True
        assert self.sync_engine._initialized is True

    def test_queue_operation(self):
        """Test queuing sync operations"""
        self.sync_engine.initialize()

        # Test create operation
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            tenant_id=str(self.tenant_id),
            new_state={'username': 'testuser', 'email': 'test@example.com'}
        )

        result = self.sync_engine.queue_operation(operation)
        assert result is True

        # Verify operation is in queue
        pending_ops = self.sync_engine.get_pending_operations()
        assert len(pending_ops) == 1
        assert pending_ops[0].operation_type == 'create'
        assert pending_ops[0].table_name == 'users'

    def test_get_pending_operations(self):
        """Test getting pending operations"""
        self.sync_engine.initialize()

        # Add multiple operations
        for i in range(3):
            operation = SyncOperation(
                operation_type='create',
                table_name='users',
                record_id=str(uuid.uuid4()),
                tenant_id=str(self.tenant_id),
                new_state={'username': f'testuser{i}'}
            )
            self.sync_engine.queue_operation(operation)

        # Get pending operations
        pending_ops = self.sync_engine.get_pending_operations(limit=2)
        assert len(pending_ops) == 2

        # Verify order (oldest first)
        assert pending_ops[0].created_at <= pending_ops[1].created_at

    def test_start_sync_session(self):
        """Test starting sync session"""
        self.sync_engine.initialize()

        session = self.sync_engine.start_sync_session()

        assert session.session_id is not None
        assert session.tenant_id == str(self.tenant_id)
        assert session.status == 'running'
        assert session.sync_mode == 'offline-first'

    def test_resolve_conflict(self):
        """Test conflict resolution"""
        self.sync_engine.initialize()

        # Create a conflict
        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='email',
            local_value='old@example.com',
            remote_value='new@example.com',
            resolved_by='local',
            operation_type='update'
        )

        # Manually insert conflict into database
        with self.sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_conflicts
                (record_id, table_name, tenant_id, field_name, local_value, remote_value, resolved_by, resolved_at, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (conflict.record_id, conflict.table_name, conflict.tenant_id,
                  conflict.field_name, json.dumps(conflict.local_value),
                  json.dumps(conflict.remote_value), conflict.resolved_by, conflict.resolved_at, conflict.operation_type))

        # Resolve conflict
        result = self.sync_engine.resolve_conflict(conflict, 'remote')
        assert result is True

    def test_complete_operation(self):
        """Test completing sync operations"""
        self.sync_engine.initialize()

        # Queue an operation
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            tenant_id=str(self.tenant_id),
            new_state={'username': 'testuser'}
        )
        self.sync_engine.queue_operation(operation)

        # Get the operation ID
        pending_ops = self.sync_engine.get_pending_operations()
        operation_id = pending_ops[0].id

        # Complete the operation
        result = self.sync_engine.complete_operation(operation_id, success=True)
        assert result is True

        # Verify operation is completed
        pending_ops = self.sync_engine.get_pending_operations()
        assert len(pending_ops) == 0

    def test_retry_failed_operations(self):
        """Test retrying failed operations — exhausted retries are not returned"""
        self.sync_engine.initialize()

        # Queue a failed operation that has already exhausted retries
        operation = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=str(uuid.uuid4()),
            tenant_id=str(self.tenant_id),
            new_state={'username': 'testuser'},
            sync_status='failed',
            retry_count=3  # equal to max_retries → must not be retried
        )

        # Manually insert failed operation
        with self.sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_queue
                (operation_type, table_name, record_id, tenant_id, new_state, sync_status, retry_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (operation.operation_type, operation.table_name, operation.record_id,
                  operation.tenant_id, json.dumps(operation.new_state),
                  operation.sync_status, operation.retry_count, operation.created_at))

        # retry_count >= max_retries → nothing eligible
        retry_ops = self.sync_engine.retry_failed_operations(max_retries=3)
        assert len(retry_ops) == 0

    def test_get_sync_status(self):
        """Test getting sync status"""
        self.sync_engine.initialize()

        status = self.sync_engine.get_sync_status()

        assert status.tenant_id == str(self.tenant_id)
        assert status.sync_enabled == True
        assert status.conflict_resolution_strategy == 'last-write-wins'

    def test_clear_completed_operations(self):
        """Test clearing completed operations"""
        self.sync_engine.initialize()

        # Queue and complete an operation
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            tenant_id=str(self.tenant_id),
            new_state={'username': 'testuser'}
        )
        self.sync_engine.queue_operation(operation)

        pending_ops = self.sync_engine.get_pending_operations()
        operation_id = pending_ops[0].id

        # Complete the operation
        self.sync_engine.complete_operation(operation_id, success=True)

        # Clear completed operations older than 0 days
        result = self.sync_engine.clear_completed_operations(older_than_days=0)
        assert result is True

    def test_sync_modes(self):
        """Test different sync modes"""
        # Test offline-first mode
        tenant_context_offline = TenantContext(tenant_id=self.tenant_id, mode='offline-first')
        sync_engine_offline = SyncEngine(tenant_context_offline, self.config_service, db_path=':memory:')
        sync_engine_offline.initialize()

        # Test cloud-first mode
        tenant_context_cloud = TenantContext(tenant_id=self.tenant_id, mode='cloud-first')
        sync_engine_cloud = SyncEngine(tenant_context_cloud, self.config_service, db_path=':memory:')
        sync_engine_cloud.initialize()

        # Test hybrid mode
        tenant_context_hybrid = TenantContext(tenant_id=self.tenant_id, mode='hybrid')
        sync_engine_hybrid = SyncEngine(tenant_context_hybrid, self.config_service, db_path=':memory:')
        sync_engine_hybrid.initialize()

        # All should initialize successfully
        assert sync_engine_offline._initialized is True
        assert sync_engine_cloud._initialized is True
        assert sync_engine_hybrid._initialized is True


class TestSyncIntegration:
    """Test cases for sync integration with DataService"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        self.data_service = DataService(self.tenant_context, self.config_service, self.sync_engine)

    def test_data_service_with_sync_integration(self):
        """Test DataService integration with sync engine"""
        self.sync_engine.initialize()

        # Create a user (should be queued for sync)
        from models.tenant import Role
        role_id = uuid.uuid4()

        user_id = self.data_service.create_user(
            username='testuser',
            role_id=role_id,
            email='test@example.com'
        )

        # Verify user was created
        user = self.data_service.data_layer.get('users', user_id)
        assert user is not None
        assert user['username'] == 'testuser'

        # Verify operation was queued
        pending_ops = self.sync_engine.get_pending_operations()
        assert len(pending_ops) == 1
        assert pending_ops[0].operation_type == 'create'
        assert pending_ops[0].table_name == 'users'

    def test_sync_conflict_detection(self):
        """Test conflict detection for field-level conflicts"""
        self.sync_engine.initialize()

        record_id = str(uuid.uuid4())

        # Two concurrent updates to the same field on the same record
        op1 = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=record_id,
            tenant_id=str(self.tenant_id),
            old_state={'username': 'original'},
            new_state={'username': 'user1_updated'},
            created_at='2026-01-01T10:00:00+00:00'
        )
        op2 = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=record_id,
            tenant_id=str(self.tenant_id),
            old_state={'username': 'original'},
            new_state={'username': 'user2_updated'},
            created_at='2026-01-01T10:00:01+00:00'
        )
        self.sync_engine.queue_operation(op1)
        self.sync_engine.queue_operation(op2)

        pending_ops = self.sync_engine.get_pending_operations()
        assert len(pending_ops) == 2

        conflicts = self.sync_engine.detect_conflicts(pending_ops)
        assert len(conflicts) >= 1
        assert conflicts[0].field_name == 'username'


class TestConflictResolution:
    """Test cases for conflict resolution algorithms"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')

    def test_last_write_wins_conflict_resolution(self):
        """Test last-write-wins conflict resolution strategy"""
        self.sync_engine.initialize()

        # Simulate conflict between local and remote values
        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='username',
            local_value='local_user',
            remote_value='remote_user',
            resolved_by='local'  # unresolved marker
        )

        # Manually insert conflict (all required columns)
        with self.sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_conflicts
                (record_id, table_name, tenant_id, field_name, local_value, remote_value,
                 resolved_by, resolved_at, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (conflict.record_id, conflict.table_name, conflict.tenant_id,
                  conflict.field_name, json.dumps(conflict.local_value),
                  json.dumps(conflict.remote_value), conflict.resolved_by,
                  conflict.resolved_at, conflict.operation_type))

        # Resolve with last-write-wins (remote wins)
        result = self.sync_engine.resolve_conflict(conflict, 'remote')
        assert result is True
        # Should no longer appear in unresolved conflicts
        assert len(self.sync_engine.get_conflicts()) == 0

    def test_manual_conflict_resolution(self):
        """Test manual conflict resolution"""
        self.sync_engine.initialize()

        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='username',
            local_value='local_user',
            remote_value='remote_user',
            resolved_by='local'
        )

        # Manually insert conflict
        with self.sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_conflicts
                (record_id, table_name, tenant_id, field_name, local_value, remote_value,
                 resolved_by, resolved_at, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (conflict.record_id, conflict.table_name, conflict.tenant_id,
                  conflict.field_name, json.dumps(conflict.local_value),
                  json.dumps(conflict.remote_value), conflict.resolved_by,
                  conflict.resolved_at, conflict.operation_type))

        # Resolve manually
        result = self.sync_engine.resolve_conflict(conflict, 'manual')
        assert result is True
        assert len(self.sync_engine.get_conflicts()) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])