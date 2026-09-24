"""
Billing service — plans, subscriptions, durable AI usage, invoices (Phase 11).
No live payment processor; payment_provider stays 'none' until founder chooses.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid

from models.billing import (
    BillingPlan,
    Subscription,
    UsageLineItem,
    Invoice,
    DEFAULT_PLANS,
    PLAN_STARTER,
    SUB_TRIAL,
    SUB_ACTIVE,
    INV_DRAFT,
    INV_OPEN,
    PROVIDER_NONE,
)


def _period_key(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y-%m")


# Rough USD cost per call by provider (display estimates only)
_COST_USD = {
    "groq": 0.0002,
    "deepseek": 0.00015,
    "nim": 0.0003,
    "nvidia": 0.0003,
    "openai": 0.002,
    "anthropic": 0.003,
    "gemini": 0.0005,
    "mock": 0.0,
}


class BillingService:
    def __init__(self, data_layer, tenant_id: str = ""):
        self.data_layer = data_layer
        self.tenant_id = tenant_id
        self._ensure_plans()

    def _ensure_plans(self) -> None:
        existing = list(self.data_layer.get_all("billing_plans") or [])
        if existing:
            return
        for p in DEFAULT_PLANS:
            try:
                self.data_layer.create("billing_plans", p.to_dict())
            except Exception:
                pass

    def list_plans(self) -> List[Dict[str, Any]]:
        rows = list(self.data_layer.get_all("billing_plans") or [])
        if not rows:
            return [p.to_dict() for p in DEFAULT_PLANS]
        return rows

    def get_or_create_subscription(self, tenant_id: str, plan_code: str = PLAN_STARTER) -> Dict[str, Any]:
        rows = list(self.data_layer.get_all("billing_subscriptions") or [])
        for r in rows:
            if str(r.get("tenant_id")) == str(tenant_id) and r.get("status") not in ("cancelled",):
                return r
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=30)
        sub = Subscription(
            tenant_id=tenant_id,
            plan_code=plan_code,
            status=SUB_TRIAL,
            period_start=now.isoformat(),
            period_end=end.isoformat(),
            payment_provider=PROVIDER_NONE,
        )
        rid = self.data_layer.create("billing_subscriptions", sub.to_dict())
        out = sub.to_dict()
        out["id"] = str(rid) if rid else out["id"]
        return out

    def record_ai_usage(
        self,
        tenant_id: str,
        provider: str = "",
        route: str = "",
        units: int = 1,
        tokens_in: int = 0,
        tokens_out: int = 0,
        estimated_cost_usd: Optional[float] = None,
    ) -> Dict[str, Any]:
        prov = (provider or "unknown").lower()
        cost = estimated_cost_usd
        if cost is None:
            cost = float(_COST_USD.get(prov, 0.001)) * max(1, units)
        item = UsageLineItem(
            tenant_id=tenant_id,
            provider=prov,
            route=route or "ai",
            units=max(1, units),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            estimated_cost_usd=float(cost),
            period_key=_period_key(),
        )
        rid = self.data_layer.create("billing_usage", item.to_dict())
        d = item.to_dict()
        d["id"] = str(rid) if rid else d["id"]
        return d

    def usage_summary(self, tenant_id: str, period_key: Optional[str] = None) -> Dict[str, Any]:
        pk = period_key or _period_key()
        rows = list(self.data_layer.get_all("billing_usage") or [])
        mine = [r for r in rows if str(r.get("tenant_id")) == str(tenant_id) and r.get("period_key") == pk]
        by_provider: Dict[str, Dict[str, Any]] = {}
        total_calls = 0
        total_cost = 0.0
        for r in mine:
            p = r.get("provider") or "unknown"
            bucket = by_provider.setdefault(p, {"provider": p, "calls": 0, "tokens_in": 0, "tokens_out": 0, "estimated_cost_usd": 0.0})
            units = int(r.get("units") or 1)
            bucket["calls"] += units
            bucket["tokens_in"] += int(r.get("tokens_in") or 0)
            bucket["tokens_out"] += int(r.get("tokens_out") or 0)
            bucket["estimated_cost_usd"] += float(r.get("estimated_cost_usd") or 0)
            total_calls += units
            total_cost += float(r.get("estimated_cost_usd") or 0)
        sub = self.get_or_create_subscription(tenant_id)
        plans = {p.get("code"): p for p in self.list_plans()}
        plan = plans.get(sub.get("plan_code") or PLAN_STARTER) or {}
        included = int(plan.get("ai_calls_included") or 0)
        return {
            "tenant_id": tenant_id,
            "period_key": pk,
            "total_calls": total_calls,
            "total_estimated_cost_usd": round(total_cost, 6),
            "by_provider": list(by_provider.values()),
            "plan_code": sub.get("plan_code"),
            "subscription_status": sub.get("status"),
            "ai_calls_included": included,
            "ai_calls_remaining": max(0, included - total_calls) if included else None,
            "payment_provider": sub.get("payment_provider") or PROVIDER_NONE,
        }

    def create_draft_invoice(self, tenant_id: str) -> Dict[str, Any]:
        sub = self.get_or_create_subscription(tenant_id)
        usage = self.usage_summary(tenant_id)
        plans = {p.get("code"): p for p in self.list_plans()}
        plan = plans.get(sub.get("plan_code") or PLAN_STARTER) or {}
        cycle = sub.get("billing_cycle") or "monthly"
        base = float(plan.get("annual_price") if cycle == "annual" else plan.get("monthly_price") or 0)
        lines = [
            {
                "type": "subscription",
                "description": f"{plan.get('name') or 'Plan'} ({cycle})",
                "amount": base,
            }
        ]
        # AI overage display only — pricing TBD
        inv = Invoice(
            tenant_id=tenant_id,
            subscription_id=str(sub.get("id") or ""),
            status=INV_DRAFT,
            currency=plan.get("currency") or "BDT",
            subtotal=base,
            total=base,
            period_start=sub.get("period_start") or "",
            period_end=sub.get("period_end") or "",
            line_items=lines,
            payment_provider=sub.get("payment_provider") or PROVIDER_NONE,
        )
        rid = self.data_layer.create("billing_invoices", inv.to_dict())
        d = inv.to_dict()
        d["id"] = str(rid) if rid else d["id"]
        d["usage_snapshot"] = usage
        return d
