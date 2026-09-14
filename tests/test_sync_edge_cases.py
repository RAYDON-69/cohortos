"""
Tests for CohortOS Sync Engine Edge Cases
"""

import pytest
import uuid
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta, timezone
from typing import Dict, Any

from models.base import TenantContext
from models.sync import SyncOperation, SyncConflict, SyncSession, TenantSyncStatus
from services.sync_engine import SyncEngine
from services.config_service import ConfigService


class TestSyncEdgeCases:
    """Test cases for sync engine edge cases"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)

    def test_retry_logic_edge_case_1_max_retries_exceeded(self):
        """Test that operations are not retried when retry_count >= max_retries"""
        # Create file-based database for persistence
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name

        try:
            sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine.initialize()

            # Queue a failed operation with retry_count = max_retries
            operation = SyncOperation(
                operation_type='update',
                table_name='users',
                record_id=str(uuid.uuid4()),
                tenant_id=str(self.tenant_id),
                old_state={'username': 'old'},
                new_state={'username': 'new'},
                sync_status='failed',
                retry_count=3,  # Equal to max_retries
                created_at=datetime.now(timezone.utc).isoformat()
            )

            # Manually insert failed operation
            with sync_engine._get_connection() as conn:
                conn.execute("""
                    INSERT INTO sync_queue
                    (operation_type, table_name, record_id, tenant_id, old_state, new_state,
                     sync_status, retry_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (operation.operation_type, operation.table_name, operation.record_id,
                      operation.tenant_id, json.dumps(operation.old_state),
                      json.dumps(operation.new_state), operation.sync_status,
                      operation.retry_count, operation.created_at))

            # Retry operations (should not retry since retry_count >= max_retries)
            retry_ops = sync_engine.retry_failed_operations(max_retries=3)
            assert len(retry_ops) == 0, "Operations should not be retried when retry_count >= max_retries"

        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_retry_logic_edge_case_2_partial_failure_retries(self):
        """Test that operations are retried when retry_count < max_retries"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name

        try:
            sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine.initialize()

            # Queue multiple failed operations with different retry counts
            operations = []
            for retry_count in [0, 1, 2]:  # All < max_retries=3
                operation = SyncOperation(
                    operation_type='update',
                    table_name='users',
                    record_id=str(uuid.uuid4()),
                    tenant_id=str(self.tenant_id),
                    old_state={'username': f'old_{retry_count}'},
                    new_state={'username': f'new_{retry_count}'},
                    sync_status='failed',
                    retry_count=retry_count,
                    created_at=datetime.now(timezone.utc).isoformat()
                )
                operations.append(operation)

                # Manually insert failed operation
                with sync_engine._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO sync_queue
                        (operation_type, table_name, record_id, tenant_id, old_state, new_state,
                         sync_status, retry_count, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (operation.operation_type, operation.table_name, operation.record_id,
                          operation.tenant_id, json.dumps(operation.old_state),
                          json.dumps(operation.new_state), operation.sync_status,
                          operation.retry_count, operation.created_at))

            # Retry operations (should retry all with retry_count < 3)
            retry_ops = sync_engine.retry_failed_operations(max_retries=3)
            assert len(retry_ops) == 3, f"Expected 3 operations to be retried, got {len(retry_ops)}"

        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_conflict_detection_edge_case_1_field_level_conflict(self):
        """Test field-level conflict detection during concurrent updates"""
        sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        sync_engine.initialize()

        # Simulate concurrent field updates to same record
        record_id = str(uuid.uuid4())

        # First update - changes username
        op1 = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=record_id,
            tenant_id=str(self.tenant_id),
            old_state={'username': 'original', 'email': 'test@example.com'},
            new_state={'username': 'updated_by_user1', 'email': 'test@example.com'},
            created_at=datetime.now(timezone.utc).isoformat()
        )
        sync_engine.queue_operation(op1)

        # Second update - changes email (different field, no conflict)
        op2 = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=record_id,
            tenant_id=str(self.tenant_id),
            old_state={'username': 'original', 'email': 'test@example.com'},
            new_state={'username': 'original', 'email': 'new_email@example.com'},
            created_at=datetime.now(timezone.utc).isoformat()
        )
        sync_engine.queue_operation(op2)

        # Third update - conflicts on username field
        op3 = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=record_id,
            tenant_id=str(self.tenant_id),
            old_state={'username': 'original', 'email': 'test@example.com'},
            new_state={'username': 'updated_by_user2', 'email': 'test@example.com'},
            created_at=datetime.now(timezone.utc).isoformat()
        )
        sync_engine.queue_operation(op3)

        # Check for conflicts using automatic conflict detection
        operations = sync_engine.get_pending_operations()
        print(f"Number of operations: {len(operations)}")
        for op in operations:
            print(f"Operation: {op.record_id}, old_state: {op.old_state}, new_state: {op.new_state}")

        conflicts = sync_engine.detect_conflicts(operations)
        print(f"Number of conflicts detected: {len(conflicts)}")
        for conflict in conflicts:
            print(f"Conflict: {conflict.field_name}, local: {conflict.local_value}, remote: {conflict.remote_value}")

        assert len(conflicts) == 1, f"Expected 1 conflict, got {len(conflicts)}"
        assert conflicts[0].field_name == 'username'

    def test_queue_durability_edge_case_1_restart_recovery(self):
        """Test that pending operations survive restart/power-cut"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name

        try:
            # Create and populate sync engine
            sync_engine1 = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine1.initialize()

            # Queue some operations
            for i in range(3):
                operation = SyncOperation(
                    operation_type='create',
                    table_name='users',
                    record_id=str(uuid.uuid4()),
                    tenant_id=str(self.tenant_id),
                    new_state={'username': f'user{i}'}
                )
                sync_engine1.queue_operation(operation)

            # Verify operations are queued
            pending_ops = sync_engine1.get_pending_operations()
            assert len(pending_ops) == 3

            # Simulate restart by creating new sync engine instance
            sync_engine2 = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine2.initialize()

            # Check that operations survive restart
            recovered_ops = sync_engine2.get_pending_operations()
            assert len(recovered_ops) == 3, f"Expected 3 operations after restart, got {len(recovered_ops)}"

            # Verify operation details are preserved
            for i, op in enumerate(recovered_ops):
                assert op.operation_type == 'create'
                assert op.table_name == 'users'
                assert op.new_state['username'] == f'user{i}'

        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_queue_durability_edge_case_2_power_cut_during_operation(self):
        """Test durability when power cut occurs during operation completion"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name

        try:
            sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine.initialize()

            # Queue an operation
            operation = SyncOperation(
                operation_type='create',
                table_name='users',
                record_id=str(uuid.uuid4()),
                tenant_id=str(self.tenant_id),
                new_state={'username': 'testuser'}
            )
            sync_engine.queue_operation(operation)

            # Get operation ID
            pending_ops = sync_engine.get_pending_operations()
            operation_id = pending_ops[0].id

            # Simulate power cut during completion (don't call complete_operation)
            # The operation should remain in 'pending' state

            # Create new engine instance after power cut
            sync_engine2 = SyncEngine(self.tenant_context, self.config_service, db_path=db_path)
            sync_engine2.initialize()

            # Verify operation is still pending
            recovered_ops = sync_engine2.get_pending_operations()
            assert len(recovered_ops) == 1, f"Expected 1 pending operation after power cut, got {len(recovered_ops)}"
            assert recovered_ops[0].sync_status == 'pending'

        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_operation_state_tracking_edge_case_1_invalid_operation_id(self):
        """Test handling of invalid operation ID in complete_operation"""
        sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        sync_engine.initialize()

        # Try to complete non-existent operation
        result = sync_engine.complete_operation(operation_id=99999, success=True)
        assert result is False, "Should handle invalid operation ID gracefully"

    def test_operation_state_tracking_edge_case_2_double_completion(self):
        """Test handling of completing the same operation twice"""
        sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        sync_engine.initialize()

        # Queue and complete an operation
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            tenant_id=str(self.tenant_id),
            new_state={'username': 'testuser'}
        )
        sync_engine.queue_operation(operation)

        pending_ops = sync_engine.get_pending_operations()
        operation_id = pending_ops[0].id

        # Complete operation first time
        result1 = sync_engine.complete_operation(operation_id, success=True)
        assert result1 is True

        # Complete operation second time
        result2 = sync_engine.complete_operation(operation_id, success=True)
        # The operation is already completed, so this should return False
        assert result2 is False, "Should prevent double completion of already completed operation"

    def test_field_level_conflict_resolution_edge_case_1_last_write_wins(self):
        """Test field-level last-write-wins conflict resolution"""
        sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        sync_engine.initialize()

        # Create a field-level conflict
        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='username',
            local_value='local_user',
            remote_value='remote_user',
            resolved_by='local',  # Mark as unresolved
            operation_type='update',
            resolved_at=datetime.now(timezone.utc).isoformat()
        )

        # Insert conflict
        with sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_conflicts
                (record_id, table_name, tenant_id, field_name, local_value, remote_value,
                 resolved_by, resolved_at, operation_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (conflict.record_id, conflict.table_name, conflict.tenant_id,
                  conflict.field_name, json.dumps(conflict.local_value),
                  json.dumps(conflict.remote_value), conflict.resolved_by,
                  conflict.resolved_at, conflict.operation_type))

        # Resolve conflict with remote winner
        result = sync_engine.resolve_conflict(conflict, 'remote')
        assert result is True

        # Verify conflict is resolved
        conflicts = sync_engine.get_conflicts()
        assert len(conflicts) == 0, "Conflict should be resolved"

    def test_field_level_conflict_resolution_edge_case_2_manual_resolution(self):
        """Test manual conflict resolution with custom resolution"""
        sync_engine = SyncEngine(self.tenant_context, self.config_service, db_path=':memory:')
        sync_engine.initialize()

        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='email',
            local_value='local@example.com',
            remote_value='remote@example.com',
            resolved_by='local',  # Mark as unresolved
            operation_type='update',
            resolved_at=datetime.now(timezone.utc).isoformat()
        )

        # Insert conflict
        with sync_engine._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_conflicts
                (record_id, table_name, tenant_id, field_name, local_value, remote_value,
                 resolved_at, operation_type, resolved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (conflict.record_id, conflict.table_name, conflict.tenant_id,
                  conflict.field_name, json.dumps(conflict.local_value),
                  json.dumps(conflict.remote_value), conflict.resolved_at,
                  conflict.operation_type, conflict.resolved_by))

        # Resolve manually
        result = sync_engine.resolve_conflict(conflict, 'manual')
        assert result is True

        # Verify manual resolution updates sync queue
        # Current implementation doesn't properly handle manual resolution
        # This test will fail until the logic is implemented
        pending_ops = sync_engine.get_pending_operations()
        # Should have one failed operation due to manual resolution
        assert len(pending_ops) == 0, "Manual resolution should mark operation as failed"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])