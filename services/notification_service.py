"""
CohortOS Notification Service

Implements multi-channel notification system with offline support,
template rendering, and delivery tracking.
"""

import sqlite3
import json
import uuid
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta, timezone
import threading
from contextlib import contextmanager

from models.base import TenantContext
from models.notification import (
    NotificationTemplate, NotificationChannel, NotificationPreference,
    NotificationQueue, Notification, NotificationEvent, NotificationMetrics
)
from services.config_service import ConfigService


class NotificationChannelProvider(ABC):
    """Abstract base class for notification channel providers"""

    @abstractmethod
    def send(self, notification: NotificationQueue) -> bool:
        """Send notification via this channel"""
        pass

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate channel configuration"""
        pass


class EmailProvider(NotificationChannelProvider):
    """Email notification provider"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def send(self, notification: NotificationQueue) -> bool:
        """Send email notification"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.config.get('from_email', 'noreply@cohortos.com')
            msg['To'] = notification.metadata.get('to_email', '')
            msg['Subject'] = notification.subject

            # Add HTML body
            msg.attach(MIMEText(notification.content, 'html'))

            # Send email
            with smtplib.SMTP(self.config.get('smtp_host', 'localhost'),
                            self.config.get('smtp_port', 587)) as server:
                if self.config.get('use_tls', True):
                    server.starttls()
                if self.config.get('username'):
                    server.login(self.config['username'], self.config['password'])
                server.send_message(msg)

            return True
        except Exception as e:
            # Log error
            notification.error_message = str(e)
            return False

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate email configuration"""
        required_fields = ['smtp_host', 'smtp_port']
        return all(field in config for field in required_fields)


class SMSProvider(NotificationChannelProvider):
    """SMS notification provider"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def send(self, notification: NotificationQueue) -> bool:
        """Send SMS notification"""
        try:
            # In production, integrate with SMS gateway API
            # For now, just log the SMS content
            sms_content = f"SMS to {notification.metadata.get('phone', '')}: {notification.content[:160]}"
            print(f"[SMS] {sms_content}")
            return True
        except Exception as e:
            notification.error_message = str(e)
            return False

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate SMS configuration"""
        return True  # Basic validation


class PushNotificationProvider(NotificationChannelProvider):
    """Push notification provider"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def send(self, notification: NotificationQueue) -> bool:
        """Send push notification"""
        try:
            # In production, integrate with push service (FCM, APNS)
            # For now, just log the push content
            push_content = f"Push to {notification.metadata.get('device_id', '')}: {notification.subject}"
            print(f"[PUSH] {push_content}")
            return True
        except Exception as e:
            notification.error_message = str(e)
            return False

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate push notification configuration"""
        return True  # Basic validation


class NotificationService:
    """Main notification service"""

    def __init__(self, tenant_context: TenantContext, config_service: ConfigService, db_path: str = ':memory:'):
        self.tenant_context = tenant_context
        self.config_service = config_service
        self.db_path = db_path
        self._providers = {}
        self._lock = threading.RLock()
        self._initialized = False
        self._db = None

    def initialize(self) -> bool:
        """Initialize notification service"""
        with self._lock:
            if self._initialized:
                return True

            try:
                # Initialize database
                self._init_database()

                # Load channel providers
                self._load_providers()

                self._initialized = True
                return True

            except Exception as e:
                self._initialized = False
                raise Exception(f"Failed to initialize notification service: {str(e)}")

    def _init_database(self):
        """Initialize SQLite database schema"""
        with self._get_db_connection() as conn:
            # Notification templates table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_templates (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    template_type TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    subject_template TEXT NOT NULL,
                    body_template TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    variables TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, name)
                )
            """)

            # Notification channels table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_channels (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    config TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    priority INTEGER DEFAULT 5,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, channel_type)
                )
            """)

            # Notification preferences table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_preferences (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    scheduled_time TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, tenant_id, channel_type, event_type)
                )
            """)

            # Notification queue table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    status TEXT NOT NULL DEFAULT 'pending',
                    scheduled_at TEXT,
                    sent_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    template_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(notification_id, channel_type)
                )
            """)

            # Notifications history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'sent',
                    sent_at TEXT,
                    delivered_at TEXT,
                    read_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_tenant ON notification_queue(tenant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON notification_queue(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_priority ON notification_queue(priority DESC, created_at ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_tenant ON notifications(tenant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)")

            # Default templates for new tenants
            self._create_default_templates(conn)

            conn.commit()

    def _create_default_templates(self, conn: sqlite3.Connection):
        """Create default notification templates"""
        default_templates = [
            {
                'name': 'welcome_email',
                'template_type': 'email',
                'channel': 'in-app',
                'subject_template': 'Welcome to CohortOS!',
                'body_template': 'Hello {username}, welcome to CohortOS! We\'re excited to have you on board.',
                'variables': ['username']
            },
            {
                'name': 'payment_reminder',
                'template_type': 'sms',
                'channel': 'sms',
                'subject_template': 'Payment Reminder',
                'body_template': 'Dear {student_name}, your payment for {month} is due. Please pay by {due_date}.',
                'variables': ['student_name', 'month', 'due_date']
            },
            {
                'name': 'class_cancelled',
                'template_type': 'push',
                'channel': 'in-app',
                'subject_template': 'Class Cancelled',
                'body_template': 'Your class on {subject} at {time} has been cancelled.',
                'variables': ['subject', 'time']
            }
        ]

        for template in default_templates:
            conn.execute("""
                INSERT OR IGNORE INTO notification_templates
                (id, tenant_id, name, template_type, channel, subject_template, body_template, variables, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                str(self.tenant_context.tenant_id),
                template['name'],
                template['template_type'],
                template['channel'],
                template['subject_template'],
                template['body_template'],
                json.dumps(template['variables']),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat()
            ))

    def _load_providers(self):
        """Load notification channel providers"""
        # Load channel configurations
        channels = self.get_channels()

        for channel in channels:
            if channel.is_active and channel.channel_type == 'email':
                self._providers['email'] = EmailProvider(channel.config)
            elif channel.is_active and channel.channel_type == 'sms':
                self._providers['sms'] = SMSProvider(channel.config)
            elif channel.is_active and channel.channel_type == 'push':
                self._providers['push'] = PushNotificationProvider(channel.config)

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get database connection with thread safety"""
        if self._db is None:
            from services.sqlite_util import open_sqlite
            self._db = open_sqlite(self.db_path)
            self._db.row_factory = sqlite3.Row

        return self._db

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = self._get_db_connection()
        try:
            yield conn
        finally:
            conn.commit()

    def create_template(self, template: NotificationTemplate) -> str:
        """Create a notification template"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            with self._get_connection() as conn:
                template.tenant_id = str(self.tenant_context.tenant_id)
                template.updated_at = datetime.now(timezone.utc).isoformat()

                conn.execute("""
                    INSERT INTO notification_templates
                    (id, tenant_id, name, template_type, channel, subject_template, body_template,
                     is_active, variables, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    template.id,
                    template.tenant_id,
                    template.name,
                    template.template_type,
                    template.channel,
                    template.subject_template,
                    template.body_template,
                    template.is_active,
                    json.dumps(template.variables),
                    template.created_at,
                    template.updated_at
                ))

                return template.id

    def get_template(self, template_name: str) -> Optional[NotificationTemplate]:
        """Get a notification template by name"""
        if not self._initialized:
            self.initialize()

        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM notification_templates
                    WHERE tenant_id = ? AND name = ? AND is_active = TRUE
                """, (str(self.tenant_context.tenant_id), template_name))

                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    return NotificationTemplate(
                        id=data['id'],
                        tenant_id=data['tenant_id'],
                        name=data['name'],
                        template_type=data['template_type'],
                        channel=data['channel'],
                        subject_template=data['subject_template'],
                        body_template=data['body_template'],
                        is_active=data['is_active'],
                        variables=json.loads(data['variables']),
                        created_at=data['created_at'],
                        updated_at=data['updated_at']
                    )
                return None

        except Exception as e:
            raise Exception(f"Failed to get template: {str(e)}")

    def create_channel(self, channel: NotificationChannel) -> str:
        """Create a notification channel"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            with self._get_connection() as conn:
                channel.tenant_id = str(self.tenant_context.tenant_id)

                # Validate channel configuration
                provider_class = self._get_provider_class(channel.channel_type)
                if provider_class:
                    provider = provider_class(channel.config)
                    if not provider.validate_config(channel.config):
                        raise ValueError(f"Invalid configuration for {channel.channel_type} channel")

                conn.execute("""
                    INSERT OR REPLACE INTO notification_channels
                    (id, tenant_id, channel_type, config, is_active, priority, retry_count, max_retries, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    channel.id,
                    channel.tenant_id,
                    channel.channel_type,
                    json.dumps(channel.config),
                    channel.is_active,
                    channel.priority,
                    channel.retry_count,
                    channel.max_retries,
                    channel.created_at
                ))

                # Reload providers if this channel is active
                if channel.is_active:
                    self._load_providers()

                return channel.id

    def get_channels(self) -> List[NotificationChannel]:
        """Get all active notification channels"""
        if not self._initialized:
            return []  # Return empty list if not initialized

        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM notification_channels
                    WHERE tenant_id = ? AND is_active = TRUE
                    ORDER BY priority DESC
                """, (str(self.tenant_context.tenant_id),))

                channels = []
                for row in cursor.fetchall():
                    data = dict(row)
                    channels.append(NotificationChannel(
                        id=data['id'],
                        tenant_id=data['tenant_id'],
                        channel_type=data['channel_type'],
                        config=json.loads(data['config']),
                        is_active=data['is_active'],
                        priority=data['priority'],
                        retry_count=data['retry_count'],
                        max_retries=data['max_retries'],
                        created_at=data['created_at']
                    ))

                return channels

        except Exception as e:
            raise Exception(f"Failed to get channels: {str(e)}")

    def set_user_preference(self, user_id: str, channel_type: str, event_type: str,
                          enabled: bool = True, scheduled_time: Optional[str] = None) -> str:
        """Set user notification preference"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            with self._get_connection() as conn:
                preference_id = str(uuid.uuid4())

                conn.execute("""
                    INSERT OR REPLACE INTO notification_preferences
                    (id, user_id, tenant_id, channel_type, event_type, enabled, scheduled_time, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    preference_id,
                    user_id,
                    str(self.tenant_context.tenant_id),
                    channel_type,
                    event_type,
                    enabled,
                    scheduled_time,
                    datetime.now(timezone.utc).isoformat()
                ))

                return preference_id

    def send_notification(self, event: NotificationEvent) -> List[str]:
        """Send notifications using templates and channels"""
        if not self._initialized:
            self.initialize()

        notification_ids = []

        try:
            # Get template
            template = self.get_template(event.template_name)
            if not template:
                raise ValueError(f"Template '{event.template_name}' not found")

            # Render template
            rendered = template.render(event.variables)

            # Prepare notifications for each user
            for user_id in event.user_ids:
                for channel_type in event.channel_types:
                    # Check user preference
                    preference = self.get_user_preference(user_id, channel_type, event.event_type)
                    if not preference or not preference.enabled:
                        continue

                    # Create notification queue item
                    queue_item = NotificationQueue(
                        tenant_id=str(self.tenant_context.tenant_id),
                        user_id=user_id,
                        event_type=event.event_type,
                        channel_type=channel_type,
                        subject=rendered['subject'],
                        content=rendered['body'],
                        priority=event.priority,
                        scheduled_at=event.scheduled_at,
                        template_id=template.id,
                        metadata=event.metadata
                    )

                    # Queue the notification
                    notification_id = self.queue_notification(queue_item)
                    notification_ids.append(notification_id)

            return notification_ids

        except Exception as e:
            raise Exception(f"Failed to send notification: {str(e)}")

    def queue_notification(self, notification: NotificationQueue) -> str:
        """Queue a notification for sending"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            try:
                with self._get_connection() as conn:
                    notification.notification_id = str(uuid.uuid4())
                    notification.tenant_id = str(self.tenant_context.tenant_id)

                    conn.execute("""
                        INSERT INTO notification_queue
                        (notification_id, tenant_id, user_id, event_type, channel_type, subject, content,
                         priority, status, scheduled_at, template_id, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        notification.notification_id,
                        notification.tenant_id,
                        notification.user_id,
                        notification.event_type,
                        notification.channel_type,
                        notification.subject,
                        notification.content,
                        notification.priority,
                        notification.status,
                        notification.scheduled_at,
                        notification.template_id,
                        json.dumps(notification.metadata),
                        notification.created_at
                    ))

                    return notification.notification_id

            except Exception as e:
                raise Exception(f"Failed to queue notification: {str(e)}")

    def get_pending_notifications(self, limit: int = 500) -> List[NotificationQueue]:
        """Get pending notifications to send"""
        if not self._initialized:
            self.initialize()

        try:
            with self._get_connection() as conn:
                # Get notifications that are either:
                # 1. Scheduled for now or in the past, or
                # 2. Not scheduled (immediate)
                current_time = datetime.now(timezone.utc).isoformat()

                cursor = conn.execute("""
                    SELECT * FROM notification_queue
                    WHERE tenant_id = ? AND
                          ((scheduled_at IS NULL OR scheduled_at <= ?) AND status = 'pending') OR
                          (status = 'scheduled' AND scheduled_at <= ?)
                    ORDER BY priority DESC, created_at ASC
                    LIMIT ?
                """, (str(self.tenant_context.tenant_id), current_time, current_time, limit))

                notifications = []
                for row in cursor.fetchall():
                    data = dict(row)
                    notifications.append(NotificationQueue(
                        id=data['id'],
                        notification_id=data['notification_id'],
                        tenant_id=data['tenant_id'],
                        user_id=data['user_id'],
                        event_type=data['event_type'],
                        channel_type=data['channel_type'],
                        subject=data['subject'],
                        content=data['content'],
                        priority=data['priority'],
                        status=data['status'],
                        scheduled_at=data['scheduled_at'],
                        sent_at=data['sent_at'],
                        retry_count=data['retry_count'],
                        error_message=data['error_message'],
                        template_id=data['template_id'],
                        metadata=json.loads(data['metadata']),
                        created_at=data['created_at']
                    ))

                return notifications

        except Exception as e:
            raise Exception(f"Failed to get pending notifications: {str(e)}")

    def send_queued_notification(self, notification: NotificationQueue) -> bool:
        """Send a queued notification"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            try:
                # Get provider for this channel
                provider = self._providers.get(notification.channel_type)
                if not provider:
                    raise ValueError(f"No provider found for channel: {notification.channel_type}")

                # Update status to 'sending'
                with self._get_connection() as conn:
                    conn.execute("""
                        UPDATE notification_queue
                        SET status = 'sending', error_message = NULL
                        WHERE id = ?
                    """, (notification.id,))

                # Send notification
                success = provider.send(notification)

                # Update status based on result
                with self._get_connection() as conn:
                    if success:
                        # Create notification record
                        sent_notification = Notification(
                            tenant_id=notification.tenant_id,
                            user_id=notification.user_id,
                            event_type=notification.event_type,
                            channel_type=notification.channel_type,
                            subject=notification.subject,
                            content=notification.content,
                            status='sent',
                            sent_at=datetime.now(timezone.utc).isoformat(),
                            metadata=notification.metadata
                        )

                        # Insert into notifications table
                        conn.execute("""
                            INSERT INTO notifications
                            (id, tenant_id, user_id, event_type, channel_type, subject, content,
                             status, sent_at, metadata, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sent_notification.id,
                            sent_notification.tenant_id,
                            sent_notification.user_id,
                            sent_notification.event_type,
                            sent_notification.channel_type,
                            sent_notification.subject,
                            sent_notification.content,
                            sent_notification.status,
                            sent_notification.sent_at,
                            json.dumps(sent_notification.metadata),
                            sent_notification.created_at
                        ))

                        # Mark as sent
                        conn.execute("""
                            UPDATE notification_queue
                            SET status = 'sent', sent_at = ?, retry_count = 0
                            WHERE id = ?
                        """, (sent_notification.sent_at, notification.id))

                    else:
                        # Handle failure with retry logic
                        retry_count = notification.retry_count + 1
                        if retry_count >= 3:  # Max retries
                            status = 'failed'
                        else:
                            status = 'pending'  # Will be retried

                        conn.execute("""
                            UPDATE notification_queue
                            SET status = ?, retry_count = ?, error_message = ?
                            WHERE id = ?
                        """, (status, retry_count, notification.error_message, notification.id))

                return success

            except Exception as e:
                # Mark as failed
                with self._get_connection() as conn:
                    conn.execute("""
                        UPDATE notification_queue
                        SET status = 'failed', error_message = ?
                        WHERE id = ?
                    """, (str(e), notification.id))

                return False

    def get_user_preference(self, user_id: str, channel_type: str, event_type: str) -> Optional[NotificationPreference]:
        """Get user notification preference"""
        if not self._initialized:
            self.initialize()

        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM notification_preferences
                    WHERE user_id = ? AND tenant_id = ? AND channel_type = ? AND event_type = ?
                """, (user_id, str(self.tenant_context.tenant_id), channel_type, event_type))

                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    return NotificationPreference(
                        id=data['id'],
                        user_id=data['user_id'],
                        tenant_id=data['tenant_id'],
                        channel_type=data['channel_type'],
                        event_type=data['event_type'],
                        enabled=data['enabled'],
                        scheduled_time=data['scheduled_time'],
                        created_at=data['created_at']
                    )
                return None

        except Exception as e:
            raise Exception(f"Failed to get user preference: {str(e)}")

    def get_notification_history(self, user_id: Optional[str] = None, limit: int = 100) -> List[Notification]:
        """Get notification history"""
        if not self._initialized:
            self.initialize()

        try:
            with self._get_connection() as conn:
                query = """
                    SELECT * FROM notifications
                    WHERE tenant_id = ?
                """
                params = [str(self.tenant_context.tenant_id)]

                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(query, params)

                notifications = []
                for row in cursor.fetchall():
                    data = dict(row)
                    notifications.append(Notification(
                        id=data['id'],
                        tenant_id=data['tenant_id'],
                        user_id=data['user_id'],
                        event_type=data['event_type'],
                        channel_type=data['channel_type'],
                        subject=data['subject'],
                        content=data['content'],
                        status=data['status'],
                        sent_at=data['sent_at'],
                        delivered_at=data['delivered_at'],
                        read_at=data['read_at'],
                        retry_count=data['retry_count'],
                        error_message=data['error_message'],
                        metadata=json.loads(data['metadata']),
                        created_at=data['created_at']
                    ))

                return notifications

        except Exception as e:
            raise Exception(f"Failed to get notification history: {str(e)}")

    def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        if not self._initialized:
            self.initialize()

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute("""
                        UPDATE notifications
                        SET read_at = ?
                        WHERE id = ? AND tenant_id = ?
                    """, (datetime.now(timezone.utc).isoformat(), notification_id, str(self.tenant_context.tenant_id)))

                    return cursor.rowcount > 0

            except Exception as e:
                raise Exception(f"Failed to mark notification as read: {str(e)}")

    def get_notification_metrics(self, days: int = 30) -> NotificationMetrics:
        """Get notification delivery metrics"""
        if not self._initialized:
            self.initialize()

        try:
            with self._get_connection() as conn:
                # Calculate date range
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=days)

                # Get total metrics
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                    FROM notifications
                    WHERE tenant_id = ? AND created_at >= ?
                """, (str(self.tenant_context.tenant_id), start_date.isoformat()))

                row = cursor.fetchone()
                total, sent, failed, pending = row

                # Get channel breakdown
                cursor = conn.execute("""
                    SELECT channel_type, COUNT(*) as count
                    FROM notifications
                    WHERE tenant_id = ? AND created_at >= ?
                    GROUP BY channel_type
                """, (str(self.tenant_context.tenant_id), start_date.isoformat()))

                channels = {row['channel_type']: row['count'] for row in cursor.fetchall()}

                # Get event type breakdown
                cursor = conn.execute("""
                    SELECT event_type, COUNT(*) as count
                    FROM notifications
                    WHERE tenant_id = ? AND created_at >= ?
                    GROUP BY event_type
                """, (str(self.tenant_context.tenant_id), start_date.isoformat()))

                event_types = {row['event_type']: row['count'] for row in cursor.fetchall()}

                return NotificationMetrics(
                    tenant_id=str(self.tenant_context.tenant_id),
                    date=start_date.date().isoformat(),
                    total_sent=total,
                    delivered=sent,
                    failed=failed,
                    pending=pending,
                    channels=channels,
                    event_types=event_types
                )

        except Exception as e:
            raise Exception(f"Failed to get notification metrics: {str(e)}")

    def _get_provider_class(self, channel_type: str):
        """Get provider class for channel type"""
        provider_map = {
            'email': EmailProvider,
            'sms': SMSProvider,
            'push': PushNotificationProvider
        }
        return provider_map.get(channel_type)

    def cleanup_old_notifications(self, days: int = 90) -> bool:
        """Clean up old notifications"""
        if not self._initialized:
            self.initialize()

        try:
            cutoff_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

            with self._lock:
                with self._get_connection() as conn:
                    # Delete old queue items
                    conn.execute("""
                        DELETE FROM notification_queue
                        WHERE tenant_id = ? AND created_at < ? AND status IN ('sent', 'failed')
                    """, (str(self.tenant_context.tenant_id), cutoff_time))

                    # Delete old notifications (keep last 1000 per user)
                    conn.execute("""
                        DELETE FROM notifications
                        WHERE tenant_id = ? AND created_at < ? AND id NOT IN (
                            SELECT id FROM (
                                SELECT id FROM notifications
                                WHERE tenant_id = ? AND created_at < ?
                                ORDER BY created_at DESC
                                LIMIT 1000
                            )
                        )
                    """, (str(self.tenant_context.tenant_id), cutoff_time,
                          str(self.tenant_context.tenant_id), cutoff_time))

            return True

        except Exception as e:
            raise Exception(f"Failed to cleanup old notifications: {str(e)}")