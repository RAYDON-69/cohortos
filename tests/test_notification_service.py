"""
Tests for CohortOS Notification Service

Tests multi-channel notification system with offline support,
template rendering, and delivery tracking.
"""

import pytest
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from models.base import TenantContext
from models.notification import (
    NotificationTemplate, NotificationChannel, NotificationPreference,
    NotificationQueue, Notification, NotificationEvent, NotificationMetrics
)
from services.notification_service import NotificationService, EmailProvider, SMSProvider, PushNotificationProvider
from services.config_service import ConfigService


class TestNotificationService:
    """Test cases for NotificationService"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.notification_service = NotificationService(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )

    def test_initialize_notification_service(self):
        """Test notification service initialization"""
        result = self.notification_service.initialize()
        assert result is True
        assert self.notification_service._initialized is True

    def test_create_notification_template(self):
        """Test creating notification templates"""
        self.notification_service.initialize()

        template = NotificationTemplate(
            name=f'welcome_email_{uuid.uuid4().hex[:8]}',
            template_type='email',
            channel='in-app',
            subject_template='Welcome to CohortOS!',
            body_template='Hello {{username}}, welcome to CohortOS!',
            variables=['username']
        )

        template_id = self.notification_service.create_template(template)
        assert template_id is not None

        # Verify template was created
        retrieved_template = self.notification_service.get_template(template.name)
        assert retrieved_template is not None
        assert retrieved_template.name == template.name
        assert retrieved_template.subject_template == 'Welcome to CohortOS!'

    def test_get_nonexistent_template(self):
        """Test getting non-existent template"""
        self.notification_service.initialize()

        template = self.notification_service.get_template('nonexistent')
        assert template is None

    def test_create_notification_channel(self):
        """Test creating notification channels"""
        self.notification_service.initialize()

        # Test email channel
        email_channel = NotificationChannel(
            channel_type='email',
            config={
                'smtp_host': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'test@example.com',
                'password': 'password',
                'use_tls': True
            },
            priority=10
        )

        channel_id = self.notification_service.create_channel(email_channel)
        assert channel_id is not None

        # Test SMS channel
        sms_channel = NotificationChannel(
            channel_type='sms',
            config={
                'api_key': 'test_api_key',
                'sender_id': 'CohortOS'
            }
        )

        sms_channel_id = self.notification_service.create_channel(sms_channel)
        assert sms_channel_id is not None

        # Verify channels were created
        channels = self.notification_service.get_channels()
        assert len(channels) == 2
        channel_types = [c.channel_type for c in channels]
        assert 'email' in channel_types
        assert 'sms' in channel_types

    def test_create_invalid_email_channel(self):
        """Test creating invalid email channel"""
        self.notification_service.initialize()

        email_channel = NotificationChannel(
            channel_type='email',
            config={
                'smtp_port': 587
                # Missing required smtp_host
            }
        )

        with pytest.raises(Exception):
            self.notification_service.create_channel(email_channel)

    def test_set_user_preference(self):
        """Test setting user notification preferences"""
        self.notification_service.initialize()

        user_id = str(uuid.uuid4())
        preference_id = self.notification_service.set_user_preference(
            user_id=user_id,
            channel_type='email',
            event_type='payment_reminder',
            enabled=True
        )

        assert preference_id is not None

        # Test retrieving preference
        preference = self.notification_service.get_user_preference(
            user_id=user_id,
            channel_type='email',
            event_type='payment_reminder'
        )
        assert preference is not None
        assert preference.enabled is True or preference.enabled == 1

    def test_send_notification_event(self):
        """Test sending notification events"""
        self.notification_service.initialize()

        # Create template and channels first
        template_name = f'payment_reminder_{uuid.uuid4().hex[:8]}'
        template = NotificationTemplate(
            name=template_name,
            template_type='sms',
            channel='sms',
            subject_template='Payment Reminder',
            body_template='Dear {{student_name}}, your payment for {{month}} is due.',
            variables=['student_name', 'month']
        )
        self.notification_service.create_template(template)

        # Set user preferences
        user_id = str(uuid.uuid4())
        self.notification_service.set_user_preference(
            user_id=user_id,
            channel_type='sms',
            event_type='payment_reminder',
            enabled=True
        )

        # Send notification event
        event = NotificationEvent(
            event_type='payment_reminder',
            template_name=template_name,
            variables={
                'student_name': 'John Doe',
                'month': 'December'
            },
            user_ids=[user_id],
            channel_types=['sms']
        )

        notification_ids = self.notification_service.send_notification(event)
        assert len(notification_ids) == 1
        assert notification_ids[0] is not None

    def test_send_notification_without_preference(self):
        """Test sending notification when user has disabled preference"""
        self.notification_service.initialize()

        # Create template
        template_name = f'class_cancelled_{uuid.uuid4().hex[:8]}'
        template = NotificationTemplate(
            name=template_name,
            template_type='push',
            channel='in-app',
            subject_template='Class Cancelled',
            body_template='Your class on {{subject}} at {{time}} has been cancelled.',
            variables=['subject', 'time']
        )
        self.notification_service.create_template(template)

        # User with disabled preference
        user_id = str(uuid.uuid4())
        self.notification_service.set_user_preference(
            user_id=user_id,
            channel_type='push',
            event_type='class_cancelled',
            enabled=False
        )

        # Send notification
        event = NotificationEvent(
            event_type='class_cancelled',
            template_name=template_name,
            variables={
                'subject': 'Physics',
                'time': '10:00 AM'
            },
            user_ids=[user_id],
            channel_types=['push']
        )

        notification_ids = self.notification_service.send_notification(event)
        assert len(notification_ids) == 0  # Should not send when preference is disabled

    def test_queue_notification(self):
        """Test queuing notifications"""
        self.notification_service.initialize()

        queue_item = NotificationQueue(
            user_id=str(uuid.uuid4()),
            event_type='welcome',
            channel_type='email',
            subject='Test Subject',
            content='Test Content',
            priority=5
        )

        notification_id = self.notification_service.queue_notification(queue_item)
        assert notification_id is not None

    def test_get_pending_notifications(self):
        """Test getting pending notifications"""
        self.notification_service.initialize()

        # Queue multiple notifications
        for i in range(3):
            queue_item = NotificationQueue(
                user_id=str(uuid.uuid4()),
                event_type='test',
                channel_type='email',
                subject=f'Subject {i}',
                content=f'Content {i}'
            )
            self.notification_service.queue_notification(queue_item)

        # Get pending notifications
        pending_notifications = self.notification_service.get_pending_notifications(limit=2)
        assert len(pending_notifications) == 2

        # Verify order (oldest first)
        assert pending_notifications[0].created_at <= pending_notifications[1].created_at

    def test_render_template(self):
        """Test template rendering"""
        template = NotificationTemplate(
            name='welcome',
            template_type='email',
            channel='in-app',
            subject_template='Welcome {{name}} to CohortOS!',
            body_template='Hello {{name}}, your {{service}} is ready.',
            variables=['name', 'service']
        )

        rendered = template.render({
            'name': 'John Doe',
            'service': 'Physics Coaching'
        })

        assert rendered['subject'] == 'Welcome John Doe to CohortOS!'
        assert rendered['body'] == 'Hello John Doe, your Physics Coaching is ready.'

    def test_notification_metrics(self):
        """Test notification metrics calculation"""
        self.notification_service.initialize()

        # Queue and send some notifications
        for i in range(5):
            queue_item = NotificationQueue(
                user_id=str(uuid.uuid4()),
                event_type='test',
                channel_type='email',
                subject=f'Subject {i}',
                content=f'Content {i}'
            )
            self.notification_service.queue_notification(queue_item)

        # Update one to sent status (simulated)
        pending = self.notification_service.get_pending_notifications()
        if pending:
            # In a real implementation, these would be updated during sending
            pass

        # Get metrics
        metrics = self.notification_service.get_notification_metrics(days=30)
        assert metrics.tenant_id == str(self.tenant_id)
        assert metrics.date == (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    def test_mark_notification_as_read(self):
        """Test marking notifications as read"""
        self.notification_service.initialize()

        # Create a notification directly in the database
        notification_id = str(uuid.uuid4())
        with self.notification_service._get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications
                (id, tenant_id, user_id, event_type, channel_type, subject, content, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (notification_id, str(self.tenant_id), str(uuid.uuid4()),
                  'test', 'email', 'Test', 'Content', 'sent',
                  datetime.now(timezone.utc).isoformat()))

        # Mark as read
        result = self.notification_service.mark_as_read(notification_id)
        assert result is True

        # Verify it's marked as read
        history = self.notification_service.get_notification_history(limit=1)
        assert history[0].read_at is not None

    def test_cleanup_old_notifications(self):
        """Test cleaning up old notifications"""
        self.notification_service.initialize()

        # Create old notification
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        with self.notification_service._get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications
                (id, tenant_id, user_id, event_type, channel_type, subject, content, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), str(self.tenant_id), str(uuid.uuid4()),
                  'old', 'email', 'Old', 'Content', 'sent',
                  old_date.isoformat()))

        # Cleanup notifications older than 90 days
        result = self.notification_service.cleanup_old_notifications(days=90)
        assert result is True

        # Verify it was cleaned up
        history = self.notification_service.get_notification_history()
        assert len([n for n in history if n.created_at < old_date.isoformat()]) == 0


class TestNotificationProviders:
    """Test cases for notification providers"""

    def setup_method(self):
        """Setup test environment"""
        self.email_config = {
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@example.com',
            'password': 'password',
            'use_tls': True
        }
        self.sms_config = {
            'api_key': 'test_api_key',
            'sender_id': 'CohortOS'
        }

    def test_email_provider_validate_config(self):
        """Test email provider configuration validation"""
        provider = EmailProvider(self.email_config)
        assert provider.validate_config(self.email_config) is True

        # Test invalid config
        invalid_config = {'smtp_port': 587}  # Missing smtp_host
        assert provider.validate_config(invalid_config) is False

    def test_sms_provider_validate_config(self):
        """Test SMS provider configuration validation"""
        provider = SMSProvider(self.sms_config)
        assert provider.validate_config(self.sms_config) is True

        # Test empty config (should be valid for SMS)
        assert provider.validate_config({}) is True

    def test_push_notification_provider_validate_config(self):
        """Test push notification provider configuration validation"""
        provider = PushNotificationProvider(self.sms_config)
        assert provider.validate_config(self.sms_config) is True

        # Test empty config (should be valid for push)
        assert provider.validate_config({}) is True


class TestNotificationIntegration:
    """Integration tests for notification service"""

    def setup_method(self):
        """Setup test environment"""
        self.tenant_id = uuid.uuid4()
        self.tenant_context = TenantContext(
            tenant_id=self.tenant_id,
            mode='offline-first'
        )
        self.config_service = ConfigService(self.tenant_context)
        self.notification_service = NotificationService(
            self.tenant_context,
            self.config_service,
            db_path=':memory:'
        )
        self.notification_service.initialize()
        self.email_config = {
            'smtp_host': 'smtp.gmail.com',
            'smtp_port': 587,
            'username': 'test@example.com',
            'password': 'password',
            'use_tls': True
        }

    def test_full_notification_workflow(self):
        """Test complete notification workflow"""
        # 1. Create template
        template_name = f'exam_reminder_{uuid.uuid4().hex[:8]}'
        template = NotificationTemplate(
            name=template_name,
            template_type='email',
            channel='in-app',
            subject_template='Exam Reminder: {{subject}}',
            body_template='Your exam {{subject}} is scheduled on {{date}} at {{time}}.',
            variables=['subject', 'date', 'time']
        )
        template_id = self.notification_service.create_template(template)

        # 2. Create channel
        email_channel = NotificationChannel(
            channel_type='email',
            config=self.email_config,
            priority=8
        )
        channel_id = self.notification_service.create_channel(email_channel)

        # 3. Set user preference
        user_id = str(uuid.uuid4())
        preference_id = self.notification_service.set_user_preference(
            user_id=user_id,
            channel_type='email',
            event_type='exam_reminder',
            enabled=True
        )

        # 4. Send notification
        event = NotificationEvent(
            event_type='exam_reminder',
            template_name=template_name,
            variables={
                'subject': 'Physics Midterm',
                'date': '2024-01-15',
                'time': '10:00 AM'
            },
            user_ids=[user_id],
            channel_types=['email']
        )

        notification_ids = self.notification_service.send_notification(event)
        assert len(notification_ids) == 1

        # 5. Verify notification was queued
        pending = self.notification_service.get_pending_notifications()
        assert len(pending) == 1
        assert pending[0].event_type == 'exam_reminder'
        assert 'Physics Midterm' in pending[0].subject

        # 6. Get notification history
        history = self.notification_service.get_notification_history()
        # Note: History would be empty until notifications are actually sent
        # This test just verifies the workflow structure

    def test_multiple_user_preferences(self):
        """Test handling multiple user preferences"""
        user_ids = [str(uuid.uuid4()) for _ in range(3)]

        # Set different preferences for each user
        for i, user_id in enumerate(user_ids):
            self.notification_service.set_user_preference(
                user_id=user_id,
                channel_type='email',
                event_type='announcement',
                enabled=bool(i % 2 == 0)  # Alternate between enabled/disabled
            )

        # Create template
        template_name = f'announcement_{uuid.uuid4().hex[:8]}'
        template = NotificationTemplate(
            name=template_name,
            template_type='email',
            channel='in-app',
            subject_template='Important Announcement',
            body_template='New announcement available.',
            variables=[]
        )
        self.notification_service.create_template(template)

        # Send to all users
        event = NotificationEvent(
            event_type='announcement',
            template_name=template_name,
            variables={},
            user_ids=user_ids,
            channel_types=['email']
        )

        notification_ids = self.notification_service.send_notification(event)
        # Should only send to users with enabled preferences (2 out of 3)
        assert len(notification_ids) == 2

    def test_notification_retry_mechanism(self):
        """Test notification retry mechanism"""
        # This would require mocking the actual provider.send() method
        # For now, we'll just test the queue state updates
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])