"""
Tests for CohortOS Sync-Notification Integration

Tests integration between sync engine and notification service,
including automatic notifications for sync events and conflict handling.
"""

import pytest
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from models.base import TenantContext
from models.sync import SyncOperation, SyncConflict
from models.notification import NotificationTemplate, NotificationEvent
from services.sync_engine import SyncEngine
from services.notification_service import NotificationService
from services.config_service import ConfigService
from services.sync_notification_integration import SyncNotificationIntegration


class TestSyncNotificationIntegration:
    """Test cases for SyncNotificationIntegration"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.sync_engine = SyncEngine(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )
        self.notification_service = NotificationService(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )
        self.integration = SyncNotificationIntegration(
            self.tenant_context,
            self.config_service,
            self.sync_engine,
            self.notification_service
        )

        # Initialize all services
        self.integration.initialize()

    def test_initialize_sync_notification_integration(self):
        """Test integration initialization"""
        result = self.integration.initialize()
        assert result is True
        assert self.integration._initialized is True

    def test_sync_operation_to_event_mapping(self):
        """Test mapping sync operations to notification events"""
        # Test user create operation
        user_create = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={'id': str(uuid.uuid4()), 'name': 'John Doe', 'email': 'john@example.com'}
        )
        event_type = self.integration._map_sync_operation_to_event(user_create)
        assert event_type == 'user_created'

        # Test user update operation
        user_update = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=str(uuid.uuid4()),
            old_state={'name': 'John Doe'},
            new_state={'name': 'John Smith', 'email': 'john.smith@example.com'}
        )
        event_type = self.integration._map_sync_operation_to_event(user_update)
        assert event_type == 'user_updated'

        # Test attendance operation
        attendance = SyncOperation(
            operation_type='create',
            table_name='attendance',
            record_id=str(uuid.uuid4()),
            new_state={'student_id': str(uuid.uuid4()), 'date': '2024-01-15', 'status': 'present'}
        )
        event_type = self.integration._map_sync_operation_to_event(attendance)
        assert event_type == 'attendance_recorded'

        # Test unknown operation
        unknown = SyncOperation(
            operation_type='create',
            table_name='unknown_table',
            record_id=str(uuid.uuid4())
        )
        event_type = self.integration._map_sync_operation_to_event(unknown)
        assert event_type is None

    def test_attendance_irregularity_detection(self):
        """Test detection of attendance irregularities"""
        # Normal attendance update
        normal_update = SyncOperation(
            operation_type='update',
            table_name='attendance',
            record_id=str(uuid.uuid4()),
            old_state={'status': 'present'},
            new_state={'status': 'late'}
        )
        assert self.integration._is_attendance_irregularity(normal_update) is False

        # Irregular attendance update
        irregular_update = SyncOperation(
            operation_type='update',
            table_name='attendance',
            record_id=str(uuid.uuid4()),
            old_state={'status': 'present'},
            new_state={'status': 'irregular'}
        )
        assert self.integration._is_attendance_irregularity(irregular_update) is True

        # Excessive absent update
        absent_update = SyncOperation(
            operation_type='update',
            table_name='attendance',
            record_id=str(uuid.uuid4()),
            old_state={'status': 'present'},
            new_state={'status': 'excessive_absent'}
        )
        assert self.integration._is_attendance_irregularity(absent_update) is True

    def test_get_affected_users(self):
        """Test getting affected users from sync operations"""
        # Create operation with user_id
        user_create = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={'id': str(uuid.uuid4()), 'name': 'John Doe', 'email': 'john@example.com'}
        )
        users = self.integration._get_affected_users(user_create)
        assert len(users) == 1
        assert users[0] == user_create.new_state['id']

        # Update operation
        user_id = str(uuid.uuid4())
        user_update = SyncOperation(
            operation_type='update',
            table_name='users',
            record_id=str(uuid.uuid4()),
            old_state={'name': 'John Doe'},
            new_state={'id': user_id, 'name': 'John Smith'}
        )
        users = self.integration._get_affected_users(user_update)
        assert len(users) == 1
        assert users[0] == user_id

        # Attendance operation with student_id
        attendance = SyncOperation(
            operation_type='create',
            table_name='attendance',
            record_id=str(uuid.uuid4()),
            new_state={'student_id': str(uuid.uuid4()), 'date': '2024-01-15'}
        )
        users = self.integration._get_affected_users(attendance)
        assert len(users) == 1
        assert users[0] == attendance.new_state['student_id']

    def test_extract_variables(self):
        """Test variable extraction for template rendering"""
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={
                'id': str(uuid.uuid4()),
                'name': 'John Doe',
                'email': 'john@example.com',
                'subject': 'Physics'
            }
        )

        # Test user_welcome variables
        variables = self.integration._extract_variables(operation, ['username', 'email'])
        assert variables['username'] == 'John Doe'
        assert variables['email'] == 'john@example.com'

        # Test with missing variable
        variables = self.integration._extract_variables(operation, ['username', 'missing_var'])
        assert variables['username'] == 'John Doe'
        assert variables['missing_var'] == 'N/A'

    def test_create_default_template(self):
        """Test creation of default notification templates"""
        config = {
            'template_type': 'email',
            'channel': 'in-app',
            'event_name': 'user_welcome',
            'channels': ['email'],
            'variables': ['username', 'email']
        }

        template = self.integration._create_default_template('test_template', config)
        assert template.template_type == 'email'
        assert template.channel == 'in-app'
        assert 'username' in template.variables
        assert 'email' in template.variables
        assert '{{username}}' in template.subject_template
        assert '{{email}}' in template.body_template

    def test_on_sync_operation_completed(self):
        """Test handling sync operation completion"""
        # Create a sync operation
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={'id': str(uuid.uuid4()), 'name': 'John Doe', 'email': 'john@example.com'}
        )

        # Queue the operation in sync engine
        self.sync_engine.queue_operation(operation)

        # Complete the operation
        result = self.integration.on_sync_operation_completed(operation, success=True)
        assert result is True

        # Check if notifications were queued
        pending_notifications = self.notification_service.get_pending_notifications()
        assert len(pending_notifications) > 0

    def test_on_sync_operation_completed_failure(self):
        """Test handling sync operation failure"""
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4())
        )

        # Complete with failure - should not trigger notifications
        result = self.integration.on_sync_operation_completed(operation, success=False)
        assert result is False

        # Check that no notifications were queued
        pending_notifications = self.notification_service.get_pending_notifications()
        assert len(pending_notifications) == 0

    def test_on_sync_conflict_detected(self):
        """Test handling sync conflict detection"""
        # Create a sync conflict
        conflict = SyncConflict(
            record_id=str(uuid.uuid4()),
            table_name='users',
            tenant_id=str(self.tenant_id),
            field_name='name',
            local_value='John Doe',
            remote_value='John Smith',
            operation_type='update'
        )

        # Handle the conflict
        result = self.integration.on_sync_conflict_detected(conflict)
        # Note: This will return False because we don't have admin users in test setup
        assert result is False

    def test_cleanup_old_notifications(self):
        """Test cleanup of old notifications and sync records"""
        # First, create some old records
        old_date = datetime.now(timezone.utc) - timedelta(days=35)

        # Create old notification
        with self.notification_service._get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications
                (id, tenant_id, user_id, event_type, channel_type, subject, content, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), str(self.tenant_id), str(uuid.uuid4()),
                  'old', 'email', 'Old', 'Content', 'sent',
                  old_date.isoformat()))

        # Create old sync operation
        old_operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            created_at=old_date.isoformat(),
            sync_status='completed'
        )
        self.sync_engine.queue_operation(old_operation)

        # Cleanup records older than 30 days
        result = self.integration.cleanup_old_notifications(days=30)
        assert result is True

        # Check if old records were cleaned up
        pending_notifications = self.notification_service.get_pending_notifications()
        # Should not include the old notification
        old_notifications = [n for n in pending_notifications
                           if n.created_at < old_date.isoformat()]
        assert len(old_notifications) == 0

    def test_get_sync_notification_summary(self):
        """Test getting sync notification summary"""
        # Create some test data
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={'id': str(uuid.uuid4()), 'name': 'John Doe'}
        )
        self.sync_engine.queue_operation(operation)

        # Get summary
        summary = self.integration.get_sync_notification_summary()

        assert summary['tenant_id'] == str(self.tenant_id)
        assert 'sync_enabled' in summary
        assert 'pending_operations' in summary
        assert 'notification_metrics' in summary
        assert 'configured_events' in summary

    def test_notification_workflow_for_user_creation(self):
        """Test complete workflow for user creation notifications"""
        # Create a user
        user_id = str(uuid.uuid4())
        operation = SyncOperation(
            operation_type='create',
            table_name='users',
            record_id=str(uuid.uuid4()),
            new_state={
                'id': user_id,
                'name': 'Jane Doe',
                'email': 'jane@example.com'
            }
        )

        # Queue and complete the operation
        self.sync_engine.queue_operation(operation)
        result = self.integration.on_sync_operation_completed(operation, success=True)
        assert result is True

        # Check if template was created
        template = self.notification_service.get_template(f'user_welcome_{self.tenant_id.hex[:8]}')
        assert template is not None
        assert template.name == f'user_welcome_{self.tenant_id.hex[:8]}'

        # Check if notifications were queued
        pending = self.notification_service.get_pending_notifications()
        assert len(pending) > 0

        # Check notification content
        notification = pending[0]
        assert 'Jane Doe' in notification.subject
        assert 'jane@example.com' in notification.content


class TestSyncNotificationIntegrationIntegration:
    """Integration tests for sync-notification integration"""

    def setup_method(self):
        """Setup test environment for integration tests"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.sync_engine = SyncEngine(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )
        self.notification_service = NotificationService(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )
        self.integration = SyncNotificationIntegration(
            self.tenant_context,
            self.config_service,
            self.sync_engine,
            self.notification_service
        )
        self.integration.initialize()

    def test_multiple_sync_operations_notifications(self):
        """Test notifications for multiple sync operations"""
        # Create multiple operations
        operations = []
        for i in range(3):
            operation = SyncOperation(
                operation_type='create',
                table_name='users',
                record_id=str(uuid.uuid4()),
                new_state={
                    'id': str(uuid.uuid4()),
                    'name': f'User {i}',
                    'email': f'user{i}@example.com'
                }
            )
            operations.append(operation)
            self.sync_engine.queue_operation(operation)

        # Complete all operations
        for operation in operations:
            self.integration.on_sync_operation_completed(operation, success=True)

        # Check notifications
        pending = self.notification_service.get_pending_notifications()
        assert len(pending) >= 3

    def test_sync_operations_with_different_events(self):
        """Test notifications for different types of sync operations"""
        # Create different types of operations
        user_id = str(uuid.uuid4())
        operations = [
            SyncOperation(
                operation_type='create',
                table_name='users',
                record_id=str(uuid.uuid4()),
                new_state={'id': user_id, 'name': 'John Doe'}
            ),
            SyncOperation(
                operation_type='create',
                table_name='attendance',
                record_id=str(uuid.uuid4()),
                new_state={'student_id': str(uuid.uuid4()), 'date': '2024-01-15'}
            ),
            SyncOperation(
                operation_type='update',
                table_name='users',
                record_id=str(uuid.uuid4()),
                old_state={'id': user_id, 'name': 'John Doe'},
                new_state={'id': user_id, 'name': 'John Smith'}
            )
        ]

        # Queue all operations
        for operation in operations:
            self.sync_engine.queue_operation(operation)

        # Complete operations and check notifications
        for operation in operations:
            self.integration.on_sync_operation_completed(operation, success=True)

        pending = self.notification_service.get_pending_notifications()
        assert len(pending) > 0

        # Check for different event types
        event_types = [n.event_type for n in pending]
        assert 'user_created' in event_types
        assert 'attendance_recorded' in event_types
        assert 'user_updated' in event_types

    def test_sync_operations_with_different_events(self):
        """Test notifications for different types of sync operations"""
        # Create different types of operations
        user_id = str(uuid.uuid4())
        operations = [
            SyncOperation(
                operation_type='create',
                table_name='users',
                record_id=str(uuid.uuid4()),
                new_state={'id': user_id, 'name': 'John Doe'}
            ),
            SyncOperation(
                operation_type='create',
                table_name='attendance',
                record_id=str(uuid.uuid4()),
                new_state={'student_id': str(uuid.uuid4()), 'date': '2024-01-15'}
            ),
            SyncOperation(
                operation_type='update',
                table_name='users',
                record_id=str(uuid.uuid4()),
                old_state={'id': user_id, 'name': 'John Doe'},
                new_state={'id': user_id, 'name': 'John Smith'}
            )
        ]

        # Queue all operations
        for operation in operations:
            self.sync_engine.queue_operation(operation)

        # Complete operations and check notifications
        for operation in operations:
            self.integration.on_sync_operation_completed(operation, success=True)

        pending = self.notification_service.get_pending_notifications()
        assert len(pending) > 0

        # Check for different event types
        event_types = [n.event_type for n in pending]
        assert 'user_created' in event_types
        assert 'attendance_recorded' in event_types
        assert 'user_updated' in event_types


if __name__ == '__main__':
    pytest.main([__file__, '-v'])