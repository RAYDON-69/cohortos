"""
Tenant management models for CohortOS
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import uuid
from .base import BaseModel, TenantContext, DataAccessLayer


@dataclass
class Centre(BaseModel):
    """Centre model - represents a coaching center tenant"""
    id: uuid.UUID
    name: str
    code: str
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None
    config_mode: str = 'offline-first'
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'name': self.name,
            'code': self.code,
            'owner_email': self.owner_email,
            'owner_phone': self.owner_phone,
            'config_mode': self.config_mode,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'Centre':
        """Create from dictionary"""
        # Centres are global objects, but tenant context is preserved for operations
        return cls(
            id=uuid.UUID(data['id']),
            name=data['name'],
            code=data['code'],
            owner_email=data.get('owner_email'),
            owner_phone=data.get('owner_phone'),
            config_mode=data.get('config_mode', 'offline-first'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    def get_table_name(self) -> str:
        return 'centres'

    def get_primary_key(self) -> str:
        return 'id'


@dataclass
class Role(BaseModel):
    """Role model - defines user roles within a tenant"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_system: bool = False
    created_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'name': self.name,
            'description': self.description,
            'is_system': self.is_system,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'Role':
        """Create from dictionary"""
        return cls(
            id=uuid.UUID(data['id']),
            tenant_id=uuid.UUID(data['tenant_id']),
            name=data['name'],
            description=data.get('description'),
            is_system=data.get('is_system', False),
            created_at=data.get('created_at')
        )

    def get_table_name(self) -> str:
        return 'roles'

    def get_primary_key(self) -> str:
        return 'id'


@dataclass
class Permission(BaseModel):
    """Permission model - defines what actions can be performed on resources"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    role_id: uuid.UUID
    resource: str
    action: str
    conditions: Optional[Dict] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'role_id': str(self.role_id),
            'resource': self.resource,
            'action': self.action,
            'conditions': self.conditions,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'Permission':
        """Create from dictionary"""
        return cls(
            id=uuid.UUID(data['id']),
            tenant_id=uuid.UUID(data['tenant_id']),
            role_id=uuid.UUID(data['role_id']),
            resource=data['resource'],
            action=data['action'],
            conditions=data.get('conditions'),
            created_at=data.get('created_at')
        )

    def get_table_name(self) -> str:
        return 'role_permissions'

    def get_primary_key(self) -> str:
        return 'id'


@dataclass
class User(BaseModel):
    """User model - represents users within a tenant"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password_hash: Optional[str] = None
    role_id: Optional[uuid.UUID] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'username': self.username,
            'email': self.email,
            'phone': self.phone,
            'password_hash': self.password_hash,
            'role_id': str(self.role_id),
            'is_active': self.is_active,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict, tenant_context: TenantContext) -> 'User':
        """Create from dictionary"""
        return cls(
            id=uuid.UUID(data['id']),
            tenant_id=uuid.UUID(data['tenant_id']),
            username=data['username'],
            email=data.get('email'),
            phone=data.get('phone'),
            password_hash=data.get('password_hash'),
            role_id=uuid.UUID(data['role_id']),
            is_active=data.get('is_active', True),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    def get_table_name(self) -> str:
        return 'users'

    def get_primary_key(self) -> str:
        return 'id'