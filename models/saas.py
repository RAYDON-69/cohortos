"""
SaaS multi-tenancy models (SPEC Module 10).

Founder super-admin is a deliberate isolation exception — audited path only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid
import secrets


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


STATUS_TRIAL = "trial"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_CANCELLED = "cancelled"
VALID_TENANT_STATUSES = frozenset({
    STATUS_TRIAL, STATUS_ACTIVE, STATUS_SUSPENDED, STATUS_CANCELLED
})

TIER_STARTER = "starter"
TIER_GROWTH = "growth"
TIER_SCALE = "scale"
VALID_TIERS = frozenset({TIER_STARTER, TIER_GROWTH, TIER_SCALE})

# Defaults from SPEC §0 / §10 (BDT)
STARTER_LIMIT = 500
STARTER_PRICE = 5000
GROWTH_LIMIT = 1500
GROWTH_PRICE = 12000  # mid of 10–15k range; configurable
SCALE_LIMIT = 6000
DEFAULT_OVERAGE_PER_STUDENT = 15  # BDT / student / month above tier limit
DEFAULT_ANNUAL_DISCOUNT = 0.15  # 15% [FLEX]


@dataclass
class SaaSTenant:
    """Registered coaching centre in the SaaS control plane."""
    id: Optional[str] = None
    name: str = ""
    code: str = ""
    status: str = STATUS_TRIAL
    tier: str = TIER_STARTER
    mode: str = "offline-first"  # offline-first | cloud-first | hybrid
    owner_email: str = ""
    owner_phone: str = ""
    student_count: int = 0
    # Billing
    monthly_price_bdt: float = float(STARTER_PRICE)
    overage_rate_bdt: float = float(DEFAULT_OVERAGE_PER_STUDENT)
    annual_discount: float = DEFAULT_ANNUAL_DISCOUNT
    billing_cycle: str = "monthly"  # monthly | annual
    # Lifecycle
    trial_ends_at: str = ""
    suspended_at: Optional[str] = None
    suspended_reason: str = ""
    extended_until: Optional[str] = None
    # BYOK — never log the raw key
    gemini_key_present: bool = False
    gemini_key_fingerprint: str = ""
    # Meta
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.updated_at:
            self.updated_at = self.created_at
        if self.status not in VALID_TENANT_STATUSES:
            raise ValueError(f"Invalid status: {self.status}")
        if self.tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {self.tier}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "status": self.status,
            "tier": self.tier,
            "mode": self.mode,
            "owner_email": self.owner_email,
            "owner_phone": self.owner_phone,
            "student_count": self.student_count,
            "monthly_price_bdt": self.monthly_price_bdt,
            "overage_rate_bdt": self.overage_rate_bdt,
            "annual_discount": self.annual_discount,
            "billing_cycle": self.billing_cycle,
            "trial_ends_at": self.trial_ends_at,
            "suspended_at": self.suspended_at,
            "suspended_reason": self.suspended_reason,
            "extended_until": self.extended_until,
            "gemini_key_present": self.gemini_key_present,
            "gemini_key_fingerprint": self.gemini_key_fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SaaSTenant":
        return cls(
            id=data.get("id"),
            name=data.get("name") or "",
            code=data.get("code") or "",
            status=data.get("status") or STATUS_TRIAL,
            tier=data.get("tier") or TIER_STARTER,
            mode=data.get("mode") or "offline-first",
            owner_email=data.get("owner_email") or "",
            owner_phone=data.get("owner_phone") or "",
            student_count=int(data.get("student_count") or 0),
            monthly_price_bdt=float(data.get("monthly_price_bdt") or STARTER_PRICE),
            overage_rate_bdt=float(data.get("overage_rate_bdt") or DEFAULT_OVERAGE_PER_STUDENT),
            annual_discount=float(data.get("annual_discount") or DEFAULT_ANNUAL_DISCOUNT),
            billing_cycle=data.get("billing_cycle") or "monthly",
            trial_ends_at=data.get("trial_ends_at") or "",
            suspended_at=data.get("suspended_at"),
            suspended_reason=data.get("suspended_reason") or "",
            extended_until=data.get("extended_until"),
            gemini_key_present=bool(data.get("gemini_key_present")),
            gemini_key_fingerprint=data.get("gemini_key_fingerprint") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class TenantAIMetrics:
    """
    Founder-visible AI usage metrics per tenant [LOCKED].
    Explicitly NO Gemini spend / cost visibility.

    centre_tenant_id = the SaaS centre being measured.
    DAL tenant_id is the founder control-plane scope (set by storage layer).
    """
    id: Optional[str] = None
    centre_tenant_id: str = ""
    period: str = ""  # YYYY-MM
    query_volume: int = 0
    mcq_count: int = 0
    written_count: int = 0
    rate_limit_hits: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    offline_degrades: int = 0
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.updated_at:
            self.updated_at = _utcnow()

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total <= 0:
            return 0.0
        return round(self.cache_hits / total, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "centre_tenant_id": self.centre_tenant_id,
            "period": self.period,
            "query_volume": self.query_volume,
            "mcq_count": self.mcq_count,
            "written_count": self.written_count,
            "rate_limit_hits": self.rate_limit_hits,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "offline_degrades": self.offline_degrades,
            "cache_hit_rate": self.cache_hit_rate,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TenantAIMetrics":
        return cls(
            id=data.get("id"),
            centre_tenant_id=data.get("centre_tenant_id") or data.get("tenant_id") or "",
            period=data.get("period") or "",
            query_volume=int(data.get("query_volume") or 0),
            mcq_count=int(data.get("mcq_count") or 0),
            written_count=int(data.get("written_count") or 0),
            rate_limit_hits=int(data.get("rate_limit_hits") or 0),
            cache_hits=int(data.get("cache_hits") or 0),
            cache_misses=int(data.get("cache_misses") or 0),
            offline_degrades=int(data.get("offline_degrades") or 0),
            updated_at=data.get("updated_at") or "",
        )


@dataclass
class FounderAuditEntry:
    """Every founder action is append-only audited."""
    id: Optional[str] = None
    action: str = ""
    tenant_id: str = ""
    actor_id: str = "founder"
    detail: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "detail": dict(self.detail),
            "created_at": self.created_at,
        }


def fingerprint_key(raw_key: str) -> str:
    """Non-reversible fingerprint for BYOK presence checks — never store raw in logs."""
    import hashlib
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()[:16]
