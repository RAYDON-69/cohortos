"""
Payment models for CohortOS Portion 4 (SPEC Module 3).

Default: paid/unpaid per calendar month, no amount.
Optional amount + receipt mode via config.
Locking is one-way (owner unlock only) with full audit.
Green/white notify flag persists until teacher flips it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUS_PAID = 'paid'
STATUS_UNPAID = 'unpaid'
STATUS_WAIVED = 'waived'  # SPEC_v3: scholarships/discounts — owner-only
VALID_PAYMENT_STATUSES = frozenset({STATUS_PAID, STATUS_UNPAID, STATUS_WAIVED})

# Green = will receive delayed-payment message; white = will not
NOTIFY_GREEN = 'green'
NOTIFY_WHITE = 'white'
VALID_NOTIFY = frozenset({NOTIFY_GREEN, NOTIFY_WHITE})


@dataclass
class PaymentRecord:
    """
    One student's payment status for one calendar month.
    Unique on (tenant_id, student_id, year, month).
    """
    id: Optional[str] = None
    tenant_id: str = ''
    student_id: str = ''
    batch_id: str = ''
    roll: str = ''
    year: int = 0
    month: int = 0                    # 1–12
    status: str = STATUS_UNPAID
    locked: bool = False
    locked_at: Optional[str] = None
    locked_by: Optional[str] = None
    unlocked_at: Optional[str] = None
    unlocked_by: Optional[str] = None
    # Optional amount mode (off by default)
    amount: Optional[float] = None
    currency: str = 'BDT'
    receipt_ref: Optional[str] = None
    # Green/white box — white stays white until teacher flips back
    notify_flag: str = NOTIFY_GREEN
    notes: str = ''
    origin_id: str = ''
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.status not in VALID_PAYMENT_STATUSES:
            raise ValueError(f"Invalid payment status: {self.status}")
        if self.notify_flag not in VALID_NOTIFY:
            raise ValueError(f"Invalid notify_flag: {self.notify_flag}")
        if not (1 <= self.month <= 12):
            raise ValueError(f"month must be 1–12, got {self.month}")
        if self.year < 2000 or self.year > 2100:
            raise ValueError(f"year out of range: {self.year}")
        if not self.student_id:
            raise ValueError("student_id is required")
        if not self.origin_id:
            self.origin_id = f"local-{uuid.uuid4().hex[:8]}"

    @property
    def month_key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'student_id': self.student_id,
            'batch_id': self.batch_id,
            'roll': self.roll,
            'year': self.year,
            'month': self.month,
            'month_key': self.month_key,
            'status': self.status,
            'locked': self.locked,
            'locked_at': self.locked_at,
            'locked_by': self.locked_by,
            'unlocked_at': self.unlocked_at,
            'unlocked_by': self.unlocked_by,
            'amount': self.amount,
            'currency': self.currency,
            'receipt_ref': self.receipt_ref,
            'notify_flag': self.notify_flag,
            'notes': self.notes,
            'origin_id': self.origin_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaymentRecord':
        return cls(
            id=data.get('id'),
            tenant_id=data.get('tenant_id', ''),
            student_id=data.get('student_id', ''),
            batch_id=data.get('batch_id', ''),
            roll=data.get('roll', ''),
            year=int(data.get('year') or 0),
            month=int(data.get('month') or 0),
            status=data.get('status', STATUS_UNPAID),
            locked=bool(data.get('locked', False)),
            locked_at=data.get('locked_at'),
            locked_by=data.get('locked_by'),
            unlocked_at=data.get('unlocked_at'),
            unlocked_by=data.get('unlocked_by'),
            amount=data.get('amount'),
            currency=data.get('currency', 'BDT'),
            receipt_ref=data.get('receipt_ref'),
            notify_flag=data.get('notify_flag', NOTIFY_GREEN),
            notes=data.get('notes', ''),
            origin_id=data.get('origin_id', ''),
            created_at=data.get('created_at', _utcnow()),
            updated_at=data.get('updated_at', _utcnow()),
        )


@dataclass
class PaymentUnlockEvent:
    """Audit-friendly record of an owner unlock (also logged via AuditService)."""
    id: Optional[str] = None
    tenant_id: str = ''
    payment_id: str = ''
    student_id: str = ''
    year: int = 0
    month: int = 0
    unlocked_by: str = ''
    reason: str = ''
    previous_status: str = STATUS_PAID
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'payment_id': self.payment_id,
            'student_id': self.student_id,
            'year': self.year,
            'month': self.month,
            'unlocked_by': self.unlocked_by,
            'reason': self.reason,
            'previous_status': self.previous_status,
            'created_at': self.created_at,
        }
