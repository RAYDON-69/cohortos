"""
CohortOS Sync-Notification Integration

Integrates sync operations with the notification system to enable
automated notifications based on data changes and sync events.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Any
import threading

from models.base import TenantContext
from models.sync import SyncOperation, SyncSession, TenantSyncStatus
from models.notification import (
    NotificationTemplate, NotificationEvent, NotificationChannel,
    NotificationPreference, NotificationQueue
)
from services.sync_engine import SyncEngine
from services.notification_service import NotificationService
from services.config_service import ConfigService


class SyncNotificationIntegration:
    """Integrates sync operations with notifications"""

    def __init__(self, tenant_context: TenantContext, config_service: ConfigService,
                 sync_engine: SyncEngine, notification_service: NotificationService):
        self.tenant_context = tenant_context
        self.config_service = config_service
        self.sync_engine = sync_engine
        self.notification_service = notification_service
        self._lock = threading.RLock()
        self._initialized = False

        # Notification mapping for sync events
        self.sync_event_notifications = {
            'user_created': {
                'template_type': 'email',
                'channel': 'in-app',
                'event_name': 'user_welcome',
                'channels': ['email', 'in-app'],
                'variables': ['username', 'email']
            },
            'user_updated': {
                'template_type': 'in-app',
                'channel': 'in-app',
                'event_name': 'user_update',
                'channels': ['in-app'],
                'variables': ['username', 'changes']
            },
            'attendance_recorded': {
                'template_type': 'sms',
                'channel': 'sms',
                'event_name': 'attendance_confirmed',
                'channels': ['sms'],
                'variables': ['student_name', 'date', 'status']
            },
            'attendance_confirmed': {
                'template_type': 'sms',
                'channel': 'sms',
                'event_name': 'attendance_confirmed',
                'channels': ['sms'],
                'variables': ['student_name', 'date', 'status']
            },
            'payment_received': {
                'template_type': 'email',
                'channel': 'email',
                'event_name': 'payment_confirmation',
                'channels': ['email', 'sms'],
                'variables': ['student_name', 'amount', 'month']
            },
            'exam_completed': {
                'template_type': 'email',
                'channel': 'email',
                'event_name': 'exam_score',
                'channels': ['email', 'in-app'],
                'variables': ['student_name', 'subject', 'score', 'rank']
            },
            'attendance_irregularity': {
                'template_type': 'in-app',
                'channel': 'in-app',
                'event_name': 'attendance_alert',
                'channels': ['in-app', 'sms'],
                'variables': ['student_name', 'days_missed', 'threshold']
            },
            'sync_conflict': {
                'template_type': 'in-app',
                'channel': 'in-app',
                'event_name': 'sync_conflict',
                'channels': ['in-app'],
                'variables': ['record_type', 'conflict_details', 'resolution']
            }
        }

    def initialize(self) -> bool:
        """Initialize the sync-notification integration"""
        with self._lock:
            if self._initialized:
                return True

            try:
                # Initialize both services
                if not self.sync_engine.initialize():
                    raise Exception("Failed to initialize sync engine")

                if not self.notification_service.initialize():
                    raise Exception("Failed to initialize notification service")

                self._initialized = True
                return True

            except Exception as e:
                self._initialized = False
                raise Exception(f"Failed to initialize sync-notification integration: {str(e)}")

    def on_sync_operation_completed(self, operation: SyncOperation, success: bool = True) -> bool:
        """
        Handle sync operation completion and trigger notifications
        """
        if not self._initialized:
            self.initialize()

        # Only trigger notifications for successful operations
        if not success:
            return False

        # Get event type based on sync operation
        event_type = self._map_sync_operation_to_event(operation)

        if event_type and event_type in self.sync_event_notifications:
            return self._trigger_sync_notifications(operation, event_type)

        return False

    def _map_sync_operation_to_event(self, operation: SyncOperation) -> Optional[str]:
        """Map sync operation to notification event type"""
        table_event_map = {
            'users': {
                'create': 'user_created',
                'update': 'user_updated'
            },
            'attendance': {
                'create': 'attendance_recorded'
            },
            'payments': {
                'update': 'payment_received'
            },
            'exams': {
                'create': 'exam_completed'
            },
            'students': {
                'update': 'attendance_irregularity'
            }
        }

        # Map based on table name and operation type
        event_mapping = table_event_map.get(operation.table_name, {})
        event_type = event_mapping.get(operation.operation_type)

        # Special handling for attendance irregularities
        if operation.table_name == 'attendance' and operation.operation_type == 'update':
            # Check if this update involves attendance irregularity
            if self._is_attendance_irregularity(operation):
                return 'attendance_irregularity'

        return event_type

    def _is_attendance_irregularity(self, operation: SyncOperation) -> bool:
        """Check if sync operation indicates attendance irregularity"""
        if operation.operation_type == 'update' and operation.new_state:
            # Check if attendance status changed to indicate irregularity
            new_status = operation.new_state.get('status')
            if new_status in ['irregular', 'excessive_absent']:
                return True

        return False

    def _trigger_sync_notifications(self, operation: SyncOperation, event_type: str) -> bool:
        """Trigger notifications for sync events"""
        try:
            # Get notification configuration for this event
            notification_config = self.sync_event_notifications[event_type]
            template_name = f"{notification_config['event_name']}_{self.tenant_context.tenant_id.hex[:8]}"

            # Check if template exists, if not create default one
            template = self.notification_service.get_template(template_name)
            if not template:
                template = self._create_default_template(template_name, notification_config)
                self.notification_service.create_template(template)

            # Get affected users based on operation
            user_ids = self._get_affected_users(operation)

            if not user_ids:
                return False

            # Prepare notification variables
            variables = self._extract_variables(operation, notification_config['variables'])

            # Create and send notification event
            notification_event = NotificationEvent(
                event_type=event_type,
                template_name=template_name,
                variables=variables,
                user_ids=user_ids,
                channel_types=notification_config['channels']
            )

            # Queue the notification (don't send immediately to avoid blocking sync)
            # For each user and channel, create a queue item with rendered template
            notification_ids = []
            for user_id in notification_event.user_ids:
                for channel_type in notification_event.channel_types:
                    # Render the template to get proper subject and content
                    rendered_template = template.render(variables)

                    queue_item = NotificationQueue(
                        user_id=user_id,
                        event_type=notification_event.event_type,
                        channel_type=channel_type,
                        subject=rendered_template['subject'],
                        content=rendered_template['body'],
                        priority=5,
                        template_id=template.id if hasattr(template, 'id') else None
                    )
                    notification_id = self.notification_service.queue_notification(queue_item)
                    if notification_id:
                        notification_ids.append(notification_id)

            return len(notification_ids) > 0

        except Exception as e:
            # Log error but don't fail the sync
            print(f"Error triggering notifications for sync event: {str(e)}")
            return False

    def _create_default_template(self, template_name: str, config: Dict[str, Any]) -> NotificationTemplate:
        """Create a default notification template"""
        # Template mappings based on event type
        template_configs = {
            'user_welcome': {
                'subject': 'Welcome to CohortOS, {{username}}!',
                'body': 'Hello {{username}},\n\nWelcome to CohortOS! Your account has been created with email {{email}}.\n\nGet started by logging in and setting up your profile.\n\nBest regards,\nThe CohortOS Team'
            },
            'user_update': {
                'subject': 'Profile Update - CohortOS',
                'body': 'Hello {{username}},\n\nYour profile has been updated with the following changes:\n\n{{changes}}\n\nThank you for keeping your information current.\n\nCohortOS Team'
            },
            'attendance_confirmed': {
                'subject': 'Attendance Confirmation - CohortOS',
                'body': 'Dear Student,\n\nYour attendance for {{date}} has been recorded as {{status}}.\n\nKeep up the good work!\n\nCohortOS Team'
            },
            'payment_confirmation': {
                'subject': 'Payment Confirmation - CohortOS',
                'body': 'Dear Student,\n\nWe have received your payment of {{amount}} for {{month}}.\n\nThank you for your timely payment!\n\nCohortOS Team'
            },
            'exam_score': {
                'subject': 'Exam Results - CohortOS',
                'body': 'Dear Student,\n\nYour exam results are now available:\n\nSubject: {{subject}}\nScore: {{score}}\nRank: {{rank}}\n\nView your detailed report in the app.\n\nCohortOS Team'
            },
            'attendance_alert': {
                'subject': 'Attendance Alert - CohortOS',
                'body': 'Dear Student,\n\nYou have missed {{days_missed}} days, which exceeds our threshold of {{threshold}}.\n\nPlease contact your coordinator if you have any questions.\n\nCohortOS Team'
            },
            'sync_conflict': {
                'subject': 'Sync Conflict Detected - CohortOS',
                'body': 'Dear Admin,\n\nA sync conflict has been detected for {{record_type}}.\n\nConflict details: {{conflict_details}}\n\nResolution: {{resolution}}\n\nPlease check the sync dashboard for more details.\n\nCohortOS Team'
            }
        }

        event_name = config['event_name']
        template_config = template_configs.get(event_name, {
            'subject': f'Notification: {event_name}',
            'body': f'Dear User,\n\nThis is a notification for {event_name}.\n\nDetails: {{details}}'
        })

        return NotificationTemplate(
            name=template_name,
            template_type=config['template_type'],
            channel=config['channel'],
            subject_template=template_config['subject'],
            body_template=template_config['body'],
            variables=config['variables']
        )

    def _get_affected_users(self, operation: SyncOperation) -> List[str]:
        """Get list of affected user IDs based on sync operation"""
        user_ids = []

        if operation.operation_type == 'create':
            # For new records, extract user_id if present
            user_id = operation.new_state.get('user_id') or operation.new_state.get('id')
            if user_id:
                user_ids.append(str(user_id))

            # For attendance, also check student_id
            if operation.table_name == 'attendance':
                student_id = operation.new_state.get('student_id')
                if student_id:
                    user_ids.append(str(student_id))

        elif operation.operation_type == 'update':
            # For updates, check if record has user_id or id
            user_id = operation.new_state.get('user_id') or operation.new_state.get('id') or operation.old_state.get('user_id') or operation.old_state.get('id')
            if user_id:
                user_ids.append(str(user_id))

            # For attendance, also check student_id
            if operation.table_name == 'attendance':
                student_id = operation.new_state.get('student_id') or operation.old_state.get('student_id')
                if student_id:
                    user_ids.append(str(student_id))

        elif operation.operation_type == 'delete':
            # For deletions, use old state
            user_id = operation.old_state.get('user_id')
            if user_id:
                user_ids.append(str(user_id))

        return list(set(user_ids))  # Remove duplicates

    def _extract_variables(self, operation: SyncOperation, required_vars: List[str]) -> Dict[str, str]:
        """Extract variables for template rendering"""
        variables = {}

        # Extract from new state (preferred)
        state = operation.new_state

        # Fallback to old state if new state doesn't have the variable
        if not state and operation.old_state:
            state = operation.old_state

        if state:
            for var in required_vars:
                # Try to find variable in state
                value = state.get(var)
                if value is None:
                    # Try alternative names
                    if var == 'username':
                        value = state.get('name', state.get('full_name'))
                    elif var == 'email':
                        value = state.get('email')
                    elif var == 'student_name':
                        value = state.get('student_name', state.get('name'))
                    elif var == 'date':
                        value = state.get('date', state.get('created_at'))
                    elif var == 'amount':
                        value = state.get('amount', state.get('payment_amount'))
                    elif var == 'month':
                        value = state.get('month', state.get('billing_month'))
                    elif var == 'subject':
                        value = state.get('subject')
                    elif var == 'score':
                        value = state.get('score')
                    elif var == 'rank':
                        value = state.get('rank')
                    elif var == 'status':
                        value = state.get('status')
                    elif var == 'days_missed':
                        value = state.get('days_absent', state.get('days_missed'))
                    elif var == 'threshold':
                        value = state.get('threshold', '3')
                    elif var == 'changes':
                        # For update operations, list changed fields
                        changes = []
                        if operation.old_state and operation.new_state:
                            for key, new_value in operation.new_state.items():
                                old_value = operation.old_state.get(key)
                                if old_value != new_value:
                                    changes.append(f"{key}: {old_value} → {new_value}")
                        value = '\n'.join(changes) if changes else 'No changes specified'
                    elif var == 'record_type':
                        value = operation.table_name
                    elif var == 'conflict_details':
                        value = f"Table: {operation.table_name}, Record: {operation.record_id}"
                    elif var == 'resolution':
                        value = "Auto-resolved using last-write-wins strategy"
                    else:
                        value = str(state.get(var, 'N/A'))

                variables[var] = str(value) if value is not None else 'N/A'

        return variables

    def on_sync_conflict_detected(self, conflict: 'SyncConflict') -> bool:
        """Handle sync conflict detection"""
        if not self._initialized:
            self.initialize()

        try:
            # Create notification for sync conflict
            template_name = f"sync_conflict_{self.tenant_context.tenant_id.hex[:8]}"

            # Get or create conflict template
            template = self.notification_service.get_template(template_name)
            if not template:
                template = self._create_default_template(template_name, {
                    'template_type': 'in-app',
                    'channel': 'in-app',
                    'event_name': 'sync_conflict',
                    'channels': ['in-app'],
                    'variables': ['record_type', 'conflict_details', 'resolution']
                })
                self.notification_service.create_template(template)

            # Get admin users (for now, use a simple approach - in real system, would query users with admin role)
            admin_user_ids = self._get_admin_user_ids()

            if admin_user_ids:
                variables = {
                    'record_type': conflict.table_name,
                    'conflict_details': f"Field: {conflict.field_name}, Local: {conflict.local_value}, Remote: {conflict.remote_value}",
                    'resolution': conflict.resolved_by
                }

                notification_event = NotificationEvent(
                    event_type='sync_conflict',
                    template_name=template_name,
                    variables=variables,
                    user_ids=admin_user_ids,
                    channel_types=['in-app']
                )

                notification_ids = self.notification_service.send_notification(notification_event)
                return len(notification_ids) > 0

        except Exception as e:
            print(f"Error handling sync conflict notification: {str(e)}")
            return False

        return False

    def _get_admin_user_ids(self) -> List[str]:
        """Get list of admin user IDs (simplified implementation)"""
        # In a real implementation, this would query the users table for admin roles
        # For now, return empty list (notifications would be disabled for conflicts)
        return []

    def cleanup_old_notifications(self, days: int = 30) -> bool:
        """Clean up old notifications and sync records"""
        if not self._initialized:
            self.initialize()

        try:
            # Clean up old notifications
            self.notification_service.cleanup_old_notifications(days)

            # Clear old sync operations
            self.sync_engine.clear_completed_operations(days)

            return True

        except Exception as e:
            print(f"Error cleaning up old records: {str(e)}")
            return False

    def get_sync_notification_summary(self) -> Dict[str, Any]:
        """Get summary of sync-related notifications"""
        if not self._initialized:
            self.initialize()

        try:
            # Get notification metrics
            metrics = self.notification_service.get_notification_metrics(days=7)

            # Get sync status
            sync_status = self.sync_engine.get_sync_status()

            return {
                'tenant_id': str(self.tenant_context.tenant_id),
                'sync_enabled': sync_status.sync_enabled,
                'last_sync_time': sync_status.last_sync_time,
                'pending_operations': sync_status.pending_operations,
                'notification_metrics': {
                    'total_sent': metrics.total_sent if hasattr(metrics, 'total_sent') else 0,
                    'delivered': metrics.delivered if hasattr(metrics, 'delivered') else 0,
                    'failed': metrics.failed if hasattr(metrics, 'failed') else 0,
                    'pending': metrics.pending if hasattr(metrics, 'pending') else 0
                },
                'configured_events': list(self.sync_event_notifications.keys())
            }

        except Exception as e:
            print(f"Error generating sync notification summary: {str(e)}")
            return {
                'tenant_id': str(self.tenant_context.tenant_id),
                'error': str(e)
            }