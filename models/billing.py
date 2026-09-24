"""
Billing / subscription data model (Phase 11).

Processor-agnostic: plans, subscriptions, invoices, AI usage line items.
Wire bKash/Nagad/Stripe later without schema rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


PLAN_STARTER = "starter"
PLAN_GROWTH = "growth"
PLAN_SCALE = "scale"
VALID_PLANS = frozenset({PLAN_STARTER, PLAN_GROWTH, PLAN_SCALE})

SUB_TRIAL = "trial"
SUB_ACTIVE = "active"
SUB_PAST_DUE = "past_due"
SUB_CANCELLED = "cancelled"
SUB_LOCKED = "locked"
VALID_SUB_STATUS = frozenset({SUB_TRIAL, SUB_ACTIVE, SUB_PAST_DUE, SUB_CANCELLED, SUB_LOCKED})

INV_DRAFT = "draft"
INV_OPEN = "open"
INV_PAID = "paid"
INV_VOID = "void"
VALID_INV = frozenset({INV_DRAFT, INV_OPEN, INV_PAID, INV_VOID})

PROVIDER_NONE = "none"
PROVIDER_BKASH = "bkash"
PROVIDER_NAGAD = "nagad"
PROVIDER_ROCKET = "rocket"
PROVIDER_SSLCOMMERZ = "sslcommerz"
PROVIDER_STRIPE = "stripe"
PROVIDER_MANUAL = "manual"


@dataclass
class BillingPlan:
    """Catalogue plan (seat-based + optional AI allowance)."""
    id: Optional[str] = None
    code: str = PLAN_STARTER
    name: str = "Starter"
    currency: str = "BDT"
    monthly_price: float = 5000.0
    annual_price: float = 51000.0  # ~15% off
    seat_limit: int = 500
    ai_calls_included: int = 500  # soft included allowance per month
    overage_per_seat: float = 15.0
    features: List[str] = field(default_factory=list)
    active: bool = True
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if self.code not in VALID_PLANS:
            raise ValueError(f"Invalid plan code: {self.code}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "currency": self.currency,
            "monthly_price": self.monthly_price,
            "annual_price": self.annual_price,
            "seat_limit": self.seat_limit,
            "ai_calls_included": self.ai_calls_included,
            "overage_per_seat": self.overage_per_seat,
            "features": list(self.features),
            "active": self.active,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BillingPlan":
        return cls(
            id=d.get("id"),
            code=d.get("code") or PLAN_STARTER,
            name=d.get("name") or "Starter",
            currency=d.get("currency") or "BDT",
            monthly_price=float(d.get("monthly_price") or 0),
            annual_price=float(d.get("annual_price") or 0),
            seat_limit=int(d.get("seat_limit") or 0),
            ai_calls_included=int(d.get("ai_calls_included") or 0),
            overage_per_seat=float(d.get("overage_per_seat") or 0),
            features=list(d.get("features") or []),
            active=bool(d.get("active", True)),
            created_at=d.get("created_at") or "",
        )


@dataclass
class Subscription:
    """Tenant subscription binding to a plan."""
    id: Optional[str] = None
    tenant_id: str = ""
    plan_code: str = PLAN_STARTER
    status: str = SUB_TRIAL
    billing_cycle: str = "monthly"  # monthly | annual
    seats: int = 0
    currency: str = "BDT"
    period_start: str = ""
    period_end: str = ""
    payment_provider: str = PROVIDER_NONE  # none until Raiyan chooses
    external_customer_id: str = ""  # Stripe customer / bKash merchant ref
    external_subscription_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = _utcnow()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if self.status not in VALID_SUB_STATUS:
            raise ValueError(f"Invalid subscription status: {self.status}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "plan_code": self.plan_code,
            "status": self.status,
            "billing_cycle": self.billing_cycle,
            "seats": self.seats,
            "currency": self.currency,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "payment_provider": self.payment_provider,
            "external_customer_id": self.external_customer_id,
            "external_subscription_id": self.external_subscription_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Subscription":
        return cls(
            id=d.get("id"),
            tenant_id=str(d.get("tenant_id") or ""),
            plan_code=d.get("plan_code") or PLAN_STARTER,
            status=d.get("status") or SUB_TRIAL,
            billing_cycle=d.get("billing_cycle") or "monthly",
            seats=int(d.get("seats") or 0),
            currency=d.get("currency") or "BDT",
            period_start=d.get("period_start") or "",
            period_end=d.get("period_end") or "",
            payment_provider=d.get("payment_provider") or PROVIDER_NONE,
            external_customer_id=d.get("external_customer_id") or "",
            external_subscription_id=d.get("external_subscription_id") or "",
            created_at=d.get("created_at") or "",
            updated_at=d.get("updated_at") or "",
        )


@dataclass
class UsageLineItem:
    """One AI (or other metered) usage event for invoicing."""
    id: Optional[str] = None
    tenant_id: str = ""
    provider: str = ""  # groq | deepseek | nim | openai | ...
    route: str = ""  # ai/query | tutor | solve | ocr
    units: int = 1
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost_usd: float = 0.0
    period_key: str = ""  # YYYY-MM
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if not self.period_key:
            self.period_key = datetime.now(timezone.utc).strftime("%Y-%m")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "provider": self.provider,
            "route": self.route,
            "units": self.units,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "estimated_cost_usd": self.estimated_cost_usd,
            "period_key": self.period_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UsageLineItem":
        return cls(
            id=d.get("id"),
            tenant_id=str(d.get("tenant_id") or ""),
            provider=d.get("provider") or "",
            route=d.get("route") or "",
            units=int(d.get("units") or 1),
            tokens_in=int(d.get("tokens_in") or 0),
            tokens_out=int(d.get("tokens_out") or 0),
            estimated_cost_usd=float(d.get("estimated_cost_usd") or 0),
            period_key=d.get("period_key") or "",
            created_at=d.get("created_at") or "",
        )


@dataclass
class Invoice:
    """Invoice record — processor attaches external_id when paid."""
    id: Optional[str] = None
    tenant_id: str = ""
    subscription_id: str = ""
    status: str = INV_DRAFT
    currency: str = "BDT"
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    period_start: str = ""
    period_end: str = ""
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    payment_provider: str = PROVIDER_NONE
    external_invoice_id: str = ""
    paid_at: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = _utcnow()
        if self.status not in VALID_INV:
            raise ValueError(f"Invalid invoice status: {self.status}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
            "status": self.status,
            "currency": self.currency,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "total": self.total,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "line_items": list(self.line_items),
            "payment_provider": self.payment_provider,
            "external_invoice_id": self.external_invoice_id,
            "paid_at": self.paid_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Invoice":
        return cls(
            id=d.get("id"),
            tenant_id=str(d.get("tenant_id") or ""),
            subscription_id=str(d.get("subscription_id") or ""),
            status=d.get("status") or INV_DRAFT,
            currency=d.get("currency") or "BDT",
            subtotal=float(d.get("subtotal") or 0),
            tax=float(d.get("tax") or 0),
            total=float(d.get("total") or 0),
            period_start=d.get("period_start") or "",
            period_end=d.get("period_end") or "",
            line_items=list(d.get("line_items") or []),
            payment_provider=d.get("payment_provider") or PROVIDER_NONE,
            external_invoice_id=d.get("external_invoice_id") or "",
            paid_at=d.get("paid_at") or "",
            created_at=d.get("created_at") or "",
        )


DEFAULT_PLANS = [
    BillingPlan(
        code=PLAN_STARTER,
        name="Starter",
        monthly_price=5000,
        annual_price=51000,
        seat_limit=500,
        ai_calls_included=500,
        features=["attendance", "fees", "exams", "vault", "offline"],
    ),
    BillingPlan(
        code=PLAN_GROWTH,
        name="Growth",
        monthly_price=12000,
        annual_price=122400,
        seat_limit=1500,
        ai_calls_included=2000,
        features=["attendance", "fees", "exams", "vault", "offline", "biometric", "automations"],
    ),
    BillingPlan(
        code=PLAN_SCALE,
        name="Scale",
        monthly_price=25000,
        annual_price=255000,
        seat_limit=6000,
        ai_calls_included=10000,
        features=["all_growth", "multi_desk", "priority_support"],
    ),
]
