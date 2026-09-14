"""
Configuration service for CohortOS
Handles per-tenant configuration with offline-first support
"""

from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime, timezone

from models.base import TenantContext, DataAccessLayer
from models.config import TenantConfig, ConfigDefaults
from services.audit_service import AuditService


class ConfigService:
    """Service for managing per-tenant configurations"""

    def __init__(self, tenant_context: TenantContext, data_service=None):
        self.tenant_context = tenant_context
        self.data_service = data_service
        self.audit_service = AuditService(tenant_context) if not data_service else data_service.audit_service
        self.config_cache = {}  # Local cache for performance
        self.cache_dirty = False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with default fallback
        First checks cache, then database, then defaults
        """
        # Check cache first
        if key in self.config_cache:
            return self.config_cache[key]

        # Check database if data service is available
        if self.data_service:
            value = self.data_service.get_config(key)
            if value is not None:
                self.config_cache[key] = value
                return value

        # Return default
        return default or ConfigDefaults.get_defaults().get(key)

    def set(self, key: str, value: Any, is_system: bool = False) -> uuid.UUID:
        """
        Set configuration value
        Updates cache and queues for sync if in offline mode
        """
        # Update cache
        old_value = self.config_cache.get(key)
        self.config_cache[key] = value
        self.cache_dirty = True

        # Save to database if data service is available
        if self.data_service:
            record_id = self.data_service.set_config(key, value, is_system)

            # Log the change
            old_state = {'value': old_value} if old_value is not None else None
            self.audit_service.log_update(
                table_name='tenant_configs',
                record_id=record_id,
                old_state=old_state,
                new_state={'value': value},
                actor_id=self.tenant_context.tenant_id
            )

            return record_id

        # Return a dummy ID if no data service (for testing)
        return uuid.uuid4()

    def get_all(self) -> Dict[str, Any]:
        """Get all configurations for the current tenant"""
        if self.data_service:
            configs = self.data_service.get_all_configs()
            result = {}
            for config in configs:
                result[config['key']] = config['value']

            # Merge with defaults for missing keys
            defaults = ConfigDefaults.get_defaults()
            for key, value in defaults.items():
                if key not in result:
                    result[key] = value

            return result
        else:
            # Return cached configs or defaults
            result = self.config_cache.copy()
            defaults = ConfigDefaults.get_defaults()
            for key, value in defaults.items():
                if key not in result:
                    result[key] = value
            return result

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get all configurations for a specific section (e.g., 'attendance', 'payment')"""
        all_configs = self.get_all()
        section_prefix = f'{section}.'

        result = {}
        for key, value in all_configs.items():
            if key.startswith(section_prefix):
                result[key] = value

        return result

    def set_section(self, section: str, configs: Dict[str, Any], is_system: bool = False) -> List[uuid.UUID]:
        """Set multiple configurations for a section"""
        record_ids = []
        section_prefix = f'{section}.'

        for key, value in configs.items():
            full_key = section_prefix + key
            record_id = self.set(full_key, value, is_system)
            record_ids.append(record_id)

        return record_ids

    def reset_to_defaults(self, sections: Optional[List[str]] = None) -> List[uuid.UUID]:
        """Reset configurations to default values"""
        defaults = ConfigDefaults.get_defaults()
        record_ids = []

        if sections:
            # Reset only specified sections
            for section in sections:
                section_configs = self.get_section(section)
                for key, value in section_configs.items():
                    if key in defaults:
                        record_id = self.set(key, defaults[key])
                        record_ids.append(record_id)
        else:
            # Reset all configurations
            for key, value in defaults.items():
                record_id = self.set(key, value)
                record_ids.append(record_id)

        return record_ids

    def delete(self, key: str) -> bool:
        """Delete a configuration setting"""
        if key in self.config_cache:
            del self.config_cache[key]
            self.cache_dirty = True

        # Note: In the database, we don't actually delete system configs
        # We just mark them as inactive if needed
        return True

    def validate_config(self, key: str, value: Any) -> bool:
        """Validate a configuration value"""
        # Add validation rules as needed
        validation_rules = {
            'attendance.grace_period_minutes': lambda v: isinstance(v, int) and 0 <= v <= 60,
            'security.password_min_length': lambda v: isinstance(v, int) and 8 <= v <= 128,
            'security.session_timeout_minutes': lambda v: isinstance(v, int) and 5 <= v <= 1440,
            'ui.theme': lambda v: v in ['light', 'dark', 'auto'],
            'ui.language': lambda v: v in ['en', 'bn'],
            'payment.lock_days': lambda v: isinstance(v, int) and 1 <= v <= 365,
        }

        validator = validation_rules.get(key)
        if validator:
            return validator(value)

        # Default validation: allow anything
        return True

    def export_config(self) -> Dict[str, Any]:
        """Export all current configurations"""
        return {
            'tenant_id': str(self.tenant_context.tenant_id),
            'mode': self.tenant_context.mode,
            'configurations': self.get_all(),
            'exported_at': datetime.now(timezone.utc).isoformat()
        }

    def import_config(self, config_data: Dict[str, Any], overwrite: bool = False) -> List[uuid.UUID]:
        """Import configurations from exported data"""
        record_ids = []
        imported_configurations = config_data.get('configurations', {})

        for key, value in imported_configurations.items():
            if overwrite or self.get(key) is None:  # Only import if not exists or overwrite=True
                if self.validate_config(key, value):
                    record_id = self.set(key, value)
                    record_ids.append(record_id)

        return record_ids

    def clear_cache(self):
        """Clear the configuration cache"""
        self.config_cache.clear()
        self.cache_dirty = False

    def get_pending_operations(self) -> List[Dict[str, Any]]:
        """Get pending config changes for sync"""
        # This would be integrated with the sync system
        return []

    def sync_from_cloud(self, cloud_configs: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronize configurations from cloud"""
        # Compare with local configs and update as needed
        local_configs = self.get_all()
        changes_made = {}

        for key, cloud_value in cloud_configs.items():
            local_value = local_configs.get(key)
            if local_value != cloud_value:
                self.set(key, cloud_value)
                changes_made[key] = {
                    'old_value': local_value,
                    'new_value': cloud_value
                }

        return changes_made