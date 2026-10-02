"""
Unified data access service for CohortOS
"""

from typing import Dict, List, Optional, Type, Any

LOCK_WAIT_COUNT = {"n": 0}
import uuid
from datetime import datetime, timezone

from models.base import DataAccessLayer, TenantContext
from models.tenant import Centre, User, Role, Permission
from models.audit import AuditLog
from models.config import TenantConfig, ConfigDefaults
from models.sync import SyncOperation
from services.audit_service import AuditService
from services.config_service import ConfigService
from services.sync_engine import SyncEngine


class DataService:
    """Unified data access service with tenant scoping and offline-first support"""

    def __init__(self, tenant_context: TenantContext, config_service: ConfigService = None, sync_engine: SyncEngine = None):
        self.data_layer = DataAccessLayer(tenant_context)
        self.tenant_context = tenant_context
        self.audit_service = AuditService(tenant_context)
        self.config_service = config_service
        self.sync_engine = sync_engine

        # Initialize sync engine if provided
        if self.sync_engine and not self.sync_engine._initialized:
            self.sync_engine.initialize()

    def set_audit_service(self, audit_service):
        """Set audit service for automatic logging (alternative constructor)"""
        self.audit_service = audit_service

    # Centre operations (centres are global but accessed through tenant context)
    def create_centre(self, name: str, code: str, owner_email: Optional[str] = None,
                      owner_phone: Optional[str] = None, config_mode: str = 'offline-first') -> uuid.UUID:
        """Create a new centre"""
        centre = Centre(
            id=uuid.uuid4(),
            name=name,
            code=code,
            owner_email=owner_email,
            owner_phone=owner_phone,
            config_mode=config_mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        record_id = self.data_layer.create(centre.get_table_name(), centre.to_dict())

        # Queue operation for sync if sync engine is available and mode supports it
        if self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
            sync_op = SyncOperation(
                operation_type='create',
                table_name=centre.get_table_name(),
                record_id=str(record_id),
                tenant_id=str(self.tenant_context.tenant_id),
                new_state=centre.to_dict(),
                old_state=None
            )
            self.sync_engine.queue_operation(sync_op)

        if self.audit_service:
            self.audit_service.log_create(
                table_name=centre.get_table_name(),
                record_id=record_id,
                new_state=centre.to_dict(),
                actor_id=self.data_layer.get_tenant_id()  # This should be the actual user ID
            )
            # Save audit logs to storage
            self.audit_service.save_logs_to_storage(self.data_layer)

        return record_id

    def get_centre(self, centre_id: uuid.UUID) -> Optional[Dict]:
        """Get a centre by ID"""
        return self.data_layer.get('centres', centre_id)

    def get_all_centres(self) -> List[Dict]:
        """Get all centres"""
        return self.data_layer.get_all('centres')

    # User operations
    def create_user(self, username: str, role_id: uuid.UUID, email: Optional[str] = None, phone: Optional[str] = None,
                   password_hash: Optional[str] = None) -> uuid.UUID:
        """Create a new user for the current tenant"""
        user = User(
            id=uuid.uuid4(),
            tenant_id=self.data_layer.get_tenant_id(),
            username=username,
            email=email,
            phone=phone,
            role_id=role_id,
            password_hash=password_hash,
            is_active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        record_id = self.data_layer.create(user.get_table_name(), user.to_dict())

        # Queue operation for sync if sync engine is available and mode supports it
        if self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
            sync_op = SyncOperation(
                operation_type='create',
                table_name=user.get_table_name(),
                record_id=str(record_id),
                tenant_id=str(self.tenant_context.tenant_id),
                new_state=user.to_dict(),
                old_state=None
            )
            self.sync_engine.queue_operation(sync_op)

        if self.audit_service:
            self.audit_service.log_create(
                table_name=user.get_table_name(),
                record_id=record_id,
                new_state=user.to_dict(),
                actor_id=self.data_layer.get_tenant_id()  # Should be the creating user's ID
            )
            # Save audit logs to storage
            self.audit_service.save_logs_to_storage(self.data_layer)

        return record_id

    def get_user(self, user_id: uuid.UUID) -> Optional[Dict]:
        """Get a user by ID"""
        return self.data_layer.get('users', user_id)

    def get_all_users(self) -> List[Dict]:
        """Get all users for current tenant"""
        return self.data_layer.get_all('users')

    def update_user(self, user_id: uuid.UUID, **kwargs) -> bool:
        """Update a user"""
        old_record = self.data_layer.get('users', user_id)
        if not old_record:
            return False

        success = self.data_layer.update('users', user_id, kwargs)

        # Queue operation for sync if sync engine is available and mode supports it
        if success and self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
            sync_op = SyncOperation(
                operation_type='update',
                table_name='users',
                record_id=str(user_id),
                tenant_id=str(self.tenant_context.tenant_id),
                old_state=old_record,
                new_state=self.data_layer.get('users', user_id)
            )
            self.sync_engine.queue_operation(sync_op)

        if success and self.audit_service and old_record:
            new_record = self.data_layer.get('users', user_id)
            if new_record:
                self.audit_service.log_update(
                    table_name='users',
                    record_id=user_id,
                    old_state=old_record,
                    new_state=new_record,
                    actor_id=self.data_layer.get_tenant_id()
                )
                # Save audit logs to storage
                self.audit_service.save_logs_to_storage(self.data_layer)

        return success

    # Role operations
    def create_role(self, name: str, description: Optional[str] = None, is_system: bool = False) -> uuid.UUID:
        """Create a new role for current tenant"""
        role = Role(
            id=uuid.uuid4(),
            tenant_id=self.data_layer.get_tenant_id(),
            name=name,
            description=description,
            is_system=is_system,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        record_id = self.data_layer.create(role.get_table_name(), role.to_dict())

        # Queue operation for sync if sync engine is available and mode supports it
        if self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
            sync_op = SyncOperation(
                operation_type='create',
                table_name=role.get_table_name(),
                record_id=str(record_id),
                tenant_id=str(self.tenant_context.tenant_id),
                new_state=role.to_dict(),
                old_state=None
            )
            self.sync_engine.queue_operation(sync_op)

        if self.audit_service:
            self.audit_service.log_create(
                table_name=role.get_table_name(),
                record_id=record_id,
                new_state=role.to_dict(),
                actor_id=self.data_layer.get_tenant_id()
            )

        return record_id

    def get_role(self, role_id: uuid.UUID) -> Optional[Dict]:
        """Get a role by ID"""
        return self.data_layer.get('roles', role_id)

    def get_all_roles(self) -> List[Dict]:
        """Get all roles for current tenant"""
        return self.data_layer.get_all('roles')

    # Permission operations
    def create_permission(self, role_id: uuid.UUID, resource: str, action: str,
                         conditions: Optional[Dict] = None) -> uuid.UUID:
        """Create a new permission"""
        permission = Permission(
            id=uuid.uuid4(),
            tenant_id=self.data_layer.get_tenant_id(),
            role_id=role_id,
            resource=resource,
            action=action,
            conditions=conditions,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        record_id = self.data_layer.create(permission.get_table_name(), permission.to_dict())

        # Queue operation for sync if sync engine is available and mode supports it
        if self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
            sync_op = SyncOperation(
                operation_type='create',
                table_name=permission.get_table_name(),
                record_id=str(record_id),
                tenant_id=str(self.tenant_context.tenant_id),
                new_state=permission.to_dict(),
                old_state=None
            )
            self.sync_engine.queue_operation(sync_op)

        if self.audit_service:
            self.audit_service.log_create(
                table_name=permission.get_table_name(),
                record_id=record_id,
                new_state=permission.to_dict(),
                actor_id=self.data_layer.get_tenant_id()
            )

        return record_id

    # Config operations
    def get_config(self, key: str) -> Any:
        """Get configuration value for current tenant"""
        configs = self.data_layer.get_all('tenant_configs')
        for config in configs:
            if config['key'] == key:
                return config['value']

        # Return default if not set
        return ConfigDefaults.get_defaults().get(key)

    def set_config(self, key: str, value: Any, is_system: bool = False) -> uuid.UUID:
        """Set configuration value for current tenant"""
        # Check if config already exists
        existing_config = None
        for config in self.data_layer.get_all('tenant_configs'):
            if config['key'] == key:
                existing_config = config
                break

        if existing_config is not None:
            # Update existing config
            old_record = existing_config
            config_id = uuid.UUID(existing_config['id'])

            success = self.data_layer.update('tenant_configs', config_id, {'value': value})

            # Queue operation for sync if sync engine is available and mode supports it
            if success and self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
                sync_op = SyncOperation(
                    operation_type='update',
                    table_name='tenant_configs',
                    record_id=str(config_id),
                    tenant_id=str(self.tenant_context.tenant_id),
                    old_state=old_record,
                    new_state=self.data_layer.get('tenant_configs', config_id)
                )
                self.sync_engine.queue_operation(sync_op)

            if success and self.audit_service:
                new_record = self.data_layer.get('tenant_configs', config_id)
                self.audit_service.log_update(
                    table_name='tenant_configs',
                    record_id=config_id,
                    old_state=old_record,
                    new_state=new_record
                )
                # Save audit logs to storage
                self.audit_service.save_logs_to_storage(self.data_layer)

            return config_id
        else:
            # Create new config
            tenant_config = TenantConfig(
                id=uuid.uuid4(),
                tenant_id=self.data_layer.get_tenant_id(),
                key=key,
                value=value,
                is_system=is_system,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat()
            )

            record_id = self.data_layer.create(tenant_config.get_table_name(), tenant_config.to_dict())

            # Queue operation for sync if sync engine is available and mode supports it
            if self.sync_engine and self.tenant_context.mode in ['offline-first', 'hybrid']:
                sync_op = SyncOperation(
                    operation_type='create',
                    table_name=tenant_config.get_table_name(),
                    record_id=str(record_id),
                    tenant_id=str(self.tenant_context.tenant_id),
                    new_state=tenant_config.to_dict(),
                    old_state=None
                )
                self.sync_engine.queue_operation(sync_op)

            if self.audit_service:
                self.audit_service.log_create(
                    table_name=tenant_config.get_table_name(),
                    record_id=record_id,
                    new_state=tenant_config.to_dict(),
                    actor_id=self.data_layer.get_tenant_id()
                )
                # Save audit logs to storage
                self.audit_service.save_logs_to_storage(self.data_layer)

            return record_id

    def get_all_configs(self) -> List[Dict]:
        """Get all configs for current tenant"""
        return self.data_layer.get_all('tenant_configs')

    # Audit operations
    def get_audit_logs(self, table_name: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get audit logs for current tenant"""
        logs = self.data_layer.get_all('audit_logs')

        if table_name:
            logs = [log for log in logs if log['table_name'] == table_name]

        # Sort by created_at descending
        logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return logs[:limit]

    # Sync operations
    def get_pending_operations(self) -> List[Dict]:
        """Get pending operations for cloud sync"""
        return self.data_layer.get_pending_operations()

    def clear_synced_operations(self):
        """Clear operations that have been synced"""
        self.data_layer.clear_pending_operations()

    # System operations for testing
    def initialize_test_data(self):
        """Initialize with basic test data"""
        # Create basic roles if they don't exist
        roles = [
            {'name': 'admin', 'description': 'Administrator with full access'},
            {'name': 'teacher', 'description': 'Teacher with teaching-related permissions'},
            {'name': 'assistant', 'description': 'Assistant with limited permissions'},
            {'name': 'student', 'description': 'Student with basic permissions'},
        ]

        for role_data in roles:
            existing = self.get_all_roles()
            if not any(r['name'] == role_data['name'] for r in existing):
                self.create_role(role_data['name'], role_data['description'])

def get_lock_wait_count() -> int:
    return int(LOCK_WAIT_COUNT.get("n", 0))
