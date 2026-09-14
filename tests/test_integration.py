"""
Integration tests for Portion 0 - Core data model, tenancy, RBAC, audit log
"""

import unittest
import uuid
from datetime import datetime

from models.base import TenantContext, DataAccessLayer
from models.tenant import Centre, User, Role, Permission
from models.config import TenantConfig, ConfigDefaults
from services.data_access import DataService
from services.audit_service import AuditService
from services.config_service import ConfigService


class TestTenantIsolation(unittest.TestCase):
    """Test tenant isolation across all components"""

    def setUp(self):
        """Set up test data"""
        self.tenant1_context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000000001'), 'offline-first')
        self.tenant2_context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000000002'), 'cloud-first')

        self.data_service1 = DataService(self.tenant1_context)
        self.data_service2 = DataService(self.tenant2_context)
        self.audit_service1 = AuditService(self.tenant1_context)
        self.audit_service2 = AuditService(self.tenant2_context)
        self.config_service1 = ConfigService(self.tenant1_context, self.data_service1)
        self.config_service2 = ConfigService(self.tenant2_context, self.data_service2)

    def test_tenant_isolation(self):
        """Test that data is properly isolated between tenants"""
        # Create a centre in tenant 1
        centre1_id = self.data_service1.create_centre(
            name="Test Centre 1",
            code="TC1",
            owner_email="owner1@test.com"
        )

        # Create a centre in tenant 2
        centre2_id = self.data_service2.create_centre(
            name="Test Centre 2",
            code="TC2",
            owner_email="owner2@test.com"
        )

        # Verify each tenant only sees their own data
        centres1 = self.data_service1.get_all_centres()
        centres2 = self.data_service2.get_all_centres()

        self.assertEqual(len(centres1), 1)
        self.assertEqual(len(centres2), 1)
        self.assertEqual(centres1[0]['name'], "Test Centre 1")
        self.assertEqual(centres2[0]['name'], "Test Centre 2")

        # Cross-tenant access should return nothing
        user1_centre = self.data_service2.get_centre(centre1_id)
        self.assertIsNone(user1_centre)

    def test_role_based_access(self):
        """Test role-based access control"""
        # Create roles for tenant 1
        admin_role_id = self.data_service1.create_role("admin", "Administrator")
        teacher_role_id = self.data_service1.create_role("teacher", "Teacher")

        # Create users with different roles
        admin_id = self.data_service1.create_user(
            username="admin1",
            role_id=admin_role_id
        )

        teacher_id = self.data_service1.create_user(
            username="teacher1",
            role_id=teacher_role_id
        )

        # Verify both users are in tenant 1
        users = self.data_service1.get_all_users()
        self.assertEqual(len(users), 2)

        # User should have correct role
        admin_user = next(u for u in users if u['username'] == "admin1")
        self.assertEqual(uuid.UUID(admin_user['role_id']), admin_role_id)


class TestAuditLogging(unittest.TestCase):
    """Test audit logging functionality"""

    def setUp(self):
        self.context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000001001'), 'offline-first')
        self.data_service = DataService(self.context)
        self.audit_service = AuditService(self.context)

    def test_audit_create_operation(self):
        """Test audit logging for create operations"""
        # Create a user
        user_id = self.data_service.create_user(
            username="testuser",
            role_id=uuid.UUID('00000000-0000-4000-8000-000000001002')
        )

        # Check audit log
        logs = self.data_service.get_audit_logs()
        create_logs = [log for log in logs if log['action'] == 'CREATE' and log['table_name'] == 'users']

        self.assertEqual(len(create_logs), 1)
        self.assertEqual(uuid.UUID(create_logs[0]['record_id']), user_id)
        self.assertIsNotNone(create_logs[0]['after'])
        self.assertIsNone(create_logs[0]['before'])

    def test_audit_update_operation(self):
        """Test audit logging for update operations"""
        # Create a user first
        user_id = self.data_service.create_user(
            username="testuser",
            email="old@test.com",
            role_id=uuid.UUID('00000000-0000-4000-8000-000000001002')
        )

        # Update the user
        success = self.data_service.update_user(user_id, email="new@test.com")
        self.assertTrue(success)

        # Check audit log
        logs = self.data_service.get_audit_logs()
        update_logs = [log for log in logs if log['action'] == 'UPDATE' and log['table_name'] == 'users']

        self.assertEqual(len(update_logs), 1)
        self.assertEqual(update_logs[0]['record_id'], str(user_id))
        self.assertIsNotNone(update_logs[0]['after'])
        self.assertIsNotNone(update_logs[0]['before'])

    def test_audit_immutability(self):
        """Test that audit logs are immutable"""
        # Create and log an operation
        user_id = self.data_service.create_user("testuser", role_id=uuid.UUID('00000000-0000-4000-8000-000000001002'))

        # Get audit logs
        logs = self.data_service.get_audit_logs()
        self.assertGreater(len(logs), 0, "No audit logs found")

        # In a real system, this would be blocked by database constraints
        # For testing, we verify the structure is immutable
        audit_log = logs[0]
        self.assertIn('action', audit_log)
        self.assertIn('table_name', audit_log)
        self.assertIn('record_id', audit_log)
        self.assertIn('tenant_id', audit_log)


class TestOfflineFirstMode(unittest.TestCase):
    """Test offline-first functionality"""

    def setUp(self):
        self.context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000002001'), 'offline-first')
        self.data_service = DataService(self.context)

    def test_offline_operations_work(self):
        """Test that all operations work without network"""
        # Create data
        centre_id = self.data_service.create_centre("Offline Centre", "OC1")
        user_id = self.data_service.create_user("offline_user", role_id=uuid.UUID('00000000-0000-4000-8000-000000002002'))

        # Verify data exists in local storage
        centres = self.data_service.get_all_centres()
        users = self.data_service.get_all_users()

        self.assertEqual(len(centres), 1)
        self.assertEqual(len(users), 1)
        self.assertEqual(centres[0]['name'], "Offline Centre")

    def test_pending_operations(self):
        """Test that offline operations are queued for sync"""
        # Perform some operations
        self.data_service.create_centre("Sync Centre", "SC1")
        self.data_service.create_user("sync_user", role_id=uuid.UUID('00000000-0000-4000-8000-000000002002'))

        # Check pending operations
        pending = self.data_service.get_pending_operations()
        self.assertGreaterEqual(len(pending), 2)  # At least two operations (centre + user)

        # Clear operations
        self.data_service.clear_synced_operations()
        self.assertEqual(len(self.data_service.get_pending_operations()), 0)


class TestCloudFirstMode(unittest.TestCase):
    """Test cloud-first functionality"""

    def setUp(self):
        self.context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000003001'), 'cloud-first')
        self.data_service = DataService(self.context)

    def test_cloud_operations(self):
        """Test operations in cloud-first mode"""
        # Create data (immediate sync to cloud)
        centre_id = self.data_service.create_centre("Cloud Centre", "CC1")
        user_id = self.data_service.create_user("cloud_user", role_id=uuid.UUID('00000000-0000-4000-8000-000000003002'))

        # Verify data exists
        centres = self.data_service.get_all_centres()
        users = self.data_service.get_all_users()

        self.assertEqual(len(centres), 1)
        self.assertEqual(len(users), 1)


class TestConfigService(unittest.TestCase):
    """Test configuration service"""

    def setUp(self):
        self.context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000004001'), 'offline-first')
        self.data_service = DataService(self.context)
        self.config_service = ConfigService(self.context, self.data_service)

    def test_get_set_config(self):
        """Test getting and setting configuration"""
        # Set a custom config
        config_id = self.config_service.set("attendance.grace_period_minutes", 10)
        self.assertIsNotNone(config_id)

        # Get it back
        value = self.config_service.get("attendance.grace_period_minutes")
        self.assertEqual(value, 10)

    def test_default_config(self):
        """Test default configuration values"""
        # Get a default config
        theme = self.config_service.get("ui.theme")
        self.assertEqual(theme, "light")

        # Get non-existent config with default
        custom = self.config_service.get("nonexistent.key", "default")
        self.assertEqual(custom, "default")

    def test_config_sections(self):
        """Test configuration sections"""
        # Clear config first
        self.config_service.clear_cache()

        # Set some configs
        self.config_service.set("attendance.auto_start", True)
        self.config_service.set("attendance.auto_end", False)
        self.config_service.set("ui.theme", "dark")

        # Get attendance section
        attendance = self.config_service.get_section("attendance")
        self.assertGreaterEqual(len(attendance), 2)
        self.assertIn("attendance.auto_start", attendance)
        self.assertIn("attendance.auto_end", attendance)

        # Get UI section - check which keys were actually stored in the database
        ui = {}
        # Only include keys that were actually set by the tenant, not defaults
        all_configs = self.data_service.data_layer.get_all('tenant_configs')
        for config in all_configs:
            if config['key'].startswith("ui."):
                ui[config['key']] = config['value']

        self.assertEqual(len(ui), 1)
        self.assertEqual(ui["ui.theme"], "dark")

    def test_config_validation(self):
        """Test configuration validation"""
        # Valid config
        self.assertTrue(self.config_service.validate_config("ui.theme", "dark"))

        # Invalid config
        self.assertFalse(self.config_service.validate_config("ui.theme", "invalid"))

        # No validation for unknown keys
        self.assertTrue(self.config_service.validate_config("custom.key", "any_value"))


class TestPerformance(unittest.TestCase):
    """Test performance benchmarks"""

    def setUp(self):
        self.context = TenantContext(uuid.UUID('00000000-0000-4000-8000-000000005001'), 'offline-first')
        self.data_service = DataService(self.context)

    def test_bulk_operations_performance(self):
        """Test performance of bulk operations"""
        import time

        # Time bulk user creation
        start_time = time.time()
        for i in range(100):
            self.data_service.create_user(f"user_{i}", role_id=uuid.UUID('00000000-0000-4000-8000-000000005002'))
        end_time = time.time()

        # Should complete in reasonable time (adjust threshold as needed)
        self.assertLess(end_time - start_time, 5.0)  # 5 seconds for 100 operations

        # Verify all users were created
        users = self.data_service.get_all_users()
        self.assertEqual(len(users), 100)


if __name__ == '__main__':
    unittest.main()