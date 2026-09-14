"""
Student & Parent account models (SPEC Module 8 [LOCKED]).

Accounts are independent of admissions until explicitly linked.
Unlinked accounts have zero access (Vault, AI, records).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid
import secrets
import string
import hashlib


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


IDENTIFIER_PHONE = "phone"
IDENTIFIER_EMAIL = "email"
IDENTIFIER_BOTH = "both"
VALID_IDENTIFIERS = frozenset({IDENTIFIER_PHONE, IDENTIFIER_EMAIL, IDENTIFIER_BOTH})

ROLE_STUDENT = "student"
ROLE_PARENT = "parent"
ROLE_OWNER = "owner"
ROLE_DESK = "desk"
ROLE_TEACHER = "teacher"
ROLE_ASSISTANT = "assistant"
VALID_ACCOUNT_ROLES = frozenset({
    ROLE_STUDENT, ROLE_PARENT, ROLE_OWNER, ROLE_DESK, ROLE_TEACHER, ROLE_ASSISTANT
})
STAFF_ROLES = frozenset({ROLE_OWNER, ROLE_DESK, ROLE_TEACHER, ROLE_ASSISTANT})


@dataclass
class CohortOSAccount:
    """Global-ish account identity within a tenant (centre)."""
    id: Optional[str] = None
    tenant_id: str = ""
    role: str = ROLE_STUDENT  # student | parent | owner | desk | teacher | assistant
    phone: str = ""
    email: str = ""
    display_name: str = ""
    is_active: bool = True
    # Linked admission ids (students may have one primary; parents use parent_student_links)
    primary_admission_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.role not in VALID_ACCOUNT_ROLES:
            raise ValueError(f"Invalid account role: {self.role}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "phone": self.phone,
            "email": self.email,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "primary_admission_id": self.primary_admission_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CohortOSAccount":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            role=data.get("role") or ROLE_STUDENT,
            phone=data.get("phone") or "",
            email=data.get("email") or "",
            display_name=data.get("display_name") or "",
            is_active=bool(data.get("is_active", True)),
            primary_admission_id=data.get("primary_admission_id") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class ParentStudentLink:
    """Parent linked to a student admission within the same centre."""
    id: Optional[str] = None
    tenant_id: str = ""
    parent_account_id: str = ""
    student_id: str = ""  # admission id
    linked_by: str = ""  # staff or parent self
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "parent_account_id": self.parent_account_id,
            "student_id": self.student_id,
            "linked_by": self.linked_by,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParentStudentLink":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            parent_account_id=data.get("parent_account_id") or "",
            student_id=data.get("student_id") or "",
            linked_by=data.get("linked_by") or "",
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class LoginOTP:
    """One-time passwordless login code."""
    id: Optional[str] = None
    tenant_id: str = ""
    account_id: str = ""
    channel: str = "sms"  # sms | whatsapp | email
    destination: str = ""
    code_hash: str = ""
    expires_at: str = ""
    is_used: bool = False
    used_at: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "channel": self.channel,
            "destination": self.destination,
            "code_hash": self.code_hash,
            "expires_at": self.expires_at,
            "is_used": self.is_used,
            "used_at": self.used_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoginOTP":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            account_id=data.get("account_id") or "",
            channel=data.get("channel") or "sms",
            destination=data.get("destination") or "",
            code_hash=data.get("code_hash") or "",
            expires_at=data.get("expires_at") or "",
            is_used=bool(data.get("is_used")),
            used_at=data.get("used_at"),
            created_at=data.get("created_at") or "",
        )


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def generate_otp_code(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


@dataclass
class AccountSession:
    """Lightweight session token after successful OTP verify."""
    id: Optional[str] = None
    tenant_id: str = ""
    account_id: str = ""
    token: str = ""
    expires_at: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.created_at:
            self.created_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "token": self.token,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountSession":
        return cls(
            id=data.get("id"),
            tenant_id=data.get("tenant_id") or "",
            account_id=data.get("account_id") or "",
            token=data.get("token") or "",
            expires_at=data.get("expires_at") or "",
            created_at=data.get("created_at") or "",
        )
