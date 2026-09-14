"""
Founder super-admin + SaaS tenant registry (SPEC Module 10 [LOCKED]).

- Explicit audited path — not an escalation of centre owner roles.
- AI metrics: query volume, 429 hits, cache hit rate, MCQ/written split.
  Never Gemini spend.
- Pricing engine integration for quotes and tier assignment.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
import uuid

from models.base import TenantContext, DataAccessLayer
from models.saas import (
    SaaSTenant,
    TenantAIMetrics,
    FounderAuditEntry,
    fingerprint_key,
    STATUS_TRIAL,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    STATUS_CANCELLED,
    TIER_STARTER,
    TIER_GROWTH,
    TIER_SCALE,
)
from services.pricing_engine import PricingEngine, PricingError


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class FounderAuthError(Exception):
    pass


class TenantNotFoundError(Exception):
    pass


class TenantSuspendedError(Exception):
    pass


# Control-plane storage is a dedicated DataAccessLayer with a fixed "founder" tenant id.
FOUNDER_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-000000000000")


def require_founder_token() -> str:
    """Require COHORTOS_FOUNDER_TOKEN from environment — no silent default."""
    import os
    token = (os.environ.get("COHORTOS_FOUNDER_TOKEN") or "").strip()
    if not token:
        raise FounderAuthError(
            "COHORTOS_FOUNDER_TOKEN environment variable is required. "
            "Refusing to start founder control plane without a token."
        )
    return token


class FounderAdminService:
    """
    SaaS control plane. Instantiate once for the platform operator.
    Centre owners must never receive this service instance.
    """

    def __init__(
        self,
        data_layer: Optional[DataAccessLayer] = None,
        pricing: Optional[PricingEngine] = None,
        founder_token: Optional[str] = None,
    ):
        self.ctx = TenantContext(tenant_id=FOUNDER_TENANT_ID, mode="cloud-first")
        self.data_layer = data_layer or DataAccessLayer(self.ctx)
        self.pricing = pricing or PricingEngine()
        # No hardcoded default. Env or explicit arg required.
        if founder_token is None:
            founder_token = require_founder_token()
        if not founder_token or not str(founder_token).strip():
            raise FounderAuthError(
                "COHORTOS_FOUNDER_TOKEN is required. Refusing to start without a founder token."
            )
        self.founder_token = str(founder_token).strip()
        # In-memory BYOK secrets — never written to tenant-scoped tables as plaintext
        self._key_vault: Dict[str, str] = {}

    def _require_founder(self, token: str) -> None:
        if not token or token != self.founder_token:
            raise FounderAuthError("Invalid founder credentials")

    def _audit(self, action: str, tenant_id: str = "", detail: Optional[Dict] = None) -> None:
        entry = FounderAuditEntry(
            action=action,
            tenant_id=tenant_id,
            detail=detail or {},
        )
        self.data_layer.create("founder_audit", entry.to_dict())

    # ── Tenant registry ───────────────────────────────────────────────

    def provision_tenant(
        self,
        name: str,
        code: str,
        founder_token: str,
        owner_email: str = "",
        owner_phone: str = "",
        mode: str = "offline-first",
        tier: Optional[str] = None,
        student_count: int = 0,
        trial_days: int = 14,
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        code = (code or "").strip().upper()
        if not name or not code:
            raise ValueError("name and code required")
        for row in self.data_layer.get_all("saas_tenants"):
            if row.get("code") == code:
                raise ValueError(f"Tenant code already exists: {code}")

        tier = tier or self.pricing.recommend_tier(student_count)
        quote = self.pricing.calculate(student_count, tier=tier)
        trial_ends = (
            datetime.now(timezone.utc) + timedelta(days=trial_days)
        ).isoformat()

        tenant = SaaSTenant(
            name=name,
            code=code,
            status=STATUS_TRIAL,
            tier=tier,
            mode=mode,
            owner_email=owner_email,
            owner_phone=owner_phone,
            student_count=student_count,
            monthly_price_bdt=quote["base_price_bdt"],
            trial_ends_at=trial_ends,
        )
        rid = self.data_layer.create("saas_tenants", tenant.to_dict())
        stored = self.data_layer.get("saas_tenants", rid) or tenant.to_dict()
        self._audit("provision", str(rid), {"code": code, "tier": tier})
        return stored

    def self_serve_trial(
        self,
        name: str,
        owner_phone: str,
        owner_email: str = "",
        owner_name: str = "",
        student_count: int = 0,
        mode: str = "offline-first",
        trial_days: int = 14,
    ) -> Dict[str, Any]:
        """
        Public centre trial signup — no founder token required.
        Creates SaaS tenant in trial status (default 14 days).
        """
        name = (name or "").strip()
        phone = "".join(c for c in (owner_phone or "") if c.isdigit())
        if not name:
            raise ValueError("Centre name is required")
        if len(phone) < 10:
            raise ValueError("Valid owner phone is required")

        # Human-friendly centre code from name (unique)
        import re
        base = re.sub(r"[^A-Za-z0-9]", "", name.upper())[:8] or "CENTRE"
        code = base
        n = 1
        existing = {r.get("code") for r in self.data_layer.get_all("saas_tenants")}
        while code in existing:
            n += 1
            code = f"{base}{n}"

        tier = self.pricing.recommend_tier(student_count)
        quote = self.pricing.calculate(student_count, tier=tier)
        from datetime import datetime, timezone, timedelta
        trial_ends = (datetime.now(timezone.utc) + timedelta(days=trial_days)).isoformat()

        from models.saas import SaaSTenant, STATUS_TRIAL
        tenant = SaaSTenant(
            name=name,
            code=code,
            status=STATUS_TRIAL,
            tier=tier,
            mode=mode,
            owner_email=(owner_email or "").strip().lower(),
            owner_phone=phone,
            student_count=int(student_count or 0),
            monthly_price_bdt=quote["base_price_bdt"],
            trial_ends_at=trial_ends,
        )
        rid = self.data_layer.create("saas_tenants", tenant.to_dict())
        stored = self.data_layer.get("saas_tenants", rid) or tenant.to_dict()
        self._audit("self_serve_trial", str(rid), {"code": code, "phone": phone[-4:]})
        return stored

    def find_tenants_by_owner_phone(self, phone: str) -> list:
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if not digits:
            return []
        out = []
        for row in self.data_layer.get_all("saas_tenants"):
            op = "".join(c for c in (row.get("owner_phone") or "") if c.isdigit())
            if op and op == digits and row.get("is_active", True):
                out.append(row)
        return out

    def get_tenant(self, tenant_id: str) -> Dict[str, Any]:
        row = self.data_layer.get("saas_tenants", uuid.UUID(tenant_id))
        if not row:
            raise TenantNotFoundError(tenant_id)
        return row

    def list_tenants(
        self, founder_token: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        self._require_founder(founder_token)
        rows = self.data_layer.get_all("saas_tenants")
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at") or "")
        return rows

    def activate_tenant(self, tenant_id: str, founder_token: str) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        updates = {
            "status": STATUS_ACTIVE,
            "suspended_at": None,
            "suspended_reason": "",
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        t.update(updates)
        self._audit("activate", tenant_id)
        return t

    def suspend_tenant(
        self, tenant_id: str, founder_token: str, reason: str = ""
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        updates = {
            "status": STATUS_SUSPENDED,
            "suspended_at": _utcnow(),
            "suspended_reason": reason or "suspended by founder",
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        t.update(updates)
        self._audit("suspend", tenant_id, {"reason": reason})
        return t

    def extend_tenant(
        self,
        tenant_id: str,
        founder_token: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        base = datetime.now(timezone.utc)
        if t.get("extended_until"):
            try:
                base = datetime.fromisoformat(t["extended_until"].replace("Z", "+00:00"))
            except Exception:
                pass
        until = (base + timedelta(days=days)).isoformat()
        updates = {
            "extended_until": until,
            "status": STATUS_ACTIVE if t.get("status") == STATUS_SUSPENDED else t.get("status"),
            "suspended_at": None,
            "suspended_reason": "",
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        t.update(updates)
        self._audit("extend", tenant_id, {"days": days, "until": until})
        return t

    def update_student_count(
        self, tenant_id: str, student_count: int, founder_token: str
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        n = max(0, int(student_count))
        tier = self.pricing.recommend_tier(n)
        quote = self.pricing.calculate(n, tier=tier)
        updates = {
            "student_count": n,
            "tier": tier,
            "monthly_price_bdt": quote["base_price_bdt"],
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        t.update(updates)
        self._audit("update_student_count", tenant_id, {"count": n, "tier": tier})
        return t

    def assert_tenant_active(self, tenant_id: str) -> None:
        """Call from app bootstrap — suspended centres cannot operate."""
        t = self.get_tenant(tenant_id)
        if t.get("status") == STATUS_SUSPENDED:
            raise TenantSuspendedError(
                f"Tenant suspended: {t.get('suspended_reason') or 'contact support'}"
            )
        if t.get("status") == STATUS_CANCELLED:
            raise TenantSuspendedError("Tenant cancelled")

    # ── Pricing ───────────────────────────────────────────────────────

    def quote(
        self,
        student_count: int,
        billing_cycle: str = "monthly",
        tier: Optional[str] = None,
        founder_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        if founder_token is not None:
            self._require_founder(founder_token)
        return self.pricing.calculate(
            student_count, tier=tier, billing_cycle=billing_cycle
        )

    def billing_status(self, tenant_id: str, founder_token: str) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        quote = self.pricing.calculate(
            int(t.get("student_count") or 0),
            tier=t.get("tier"),
            billing_cycle=t.get("billing_cycle") or "monthly",
            overage_rate=t.get("overage_rate_bdt"),
            annual_discount=t.get("annual_discount"),
        )
        return {
            "tenant_id": tenant_id,
            "status": t.get("status"),
            "tier": t.get("tier"),
            "student_count": t.get("student_count"),
            "quote": quote,
            "gemini_key_present": t.get("gemini_key_present"),
            # Explicitly no spend field
        }

    # ── BYOK ──────────────────────────────────────────────────────────

    def set_gemini_key(
        self, tenant_id: str, raw_key: str, founder_token: str
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        t = self.get_tenant(tenant_id)
        fp = fingerprint_key(raw_key)
        self._key_vault[tenant_id] = raw_key  # process memory only
        updates = {
            "gemini_key_present": True,
            "gemini_key_fingerprint": fp,
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        t.update(updates)
        self._audit("set_gemini_key", tenant_id, {"fingerprint": fp})
        return {"tenant_id": tenant_id, "gemini_key_present": True, "fingerprint": fp}

    def clear_gemini_key(self, tenant_id: str, founder_token: str) -> Dict[str, Any]:
        self._require_founder(founder_token)
        self.get_tenant(tenant_id)
        self._key_vault.pop(tenant_id, None)
        updates = {
            "gemini_key_present": False,
            "gemini_key_fingerprint": "",
            "updated_at": _utcnow(),
        }
        self.data_layer.update("saas_tenants", uuid.UUID(tenant_id), updates)
        self._audit("clear_gemini_key", tenant_id)
        return {"tenant_id": tenant_id, "gemini_key_present": False}

    def get_gemini_key(self, tenant_id: str, founder_token: str) -> Optional[str]:
        """Founder-only retrieval for injecting into GeminiProvider."""
        self._require_founder(founder_token)
        return self._key_vault.get(tenant_id)

    # ── AI metrics [LOCKED — no spend] ────────────────────────────────

    def record_ai_event(
        self,
        tenant_id: str,
        *,
        query: bool = False,
        mcq: bool = False,
        written: bool = False,
        rate_limit: bool = False,
        cache_hit: bool = False,
        cache_miss: bool = False,
        offline: bool = False,
    ) -> Dict[str, Any]:
        period = _period_now()
        row = None
        for r in self.data_layer.get_all("tenant_ai_metrics"):
            cid = r.get("centre_tenant_id") or r.get("tenant_id")
            if cid == tenant_id and r.get("period") == period:
                row = r
                break
        if not row:
            m = TenantAIMetrics(centre_tenant_id=tenant_id, period=period)
            rid = self.data_layer.create("tenant_ai_metrics", m.to_dict())
            row = self.data_layer.get("tenant_ai_metrics", rid) or m.to_dict()
            # Ensure centre_tenant_id survived DAL tenant overwrite
            if row.get("centre_tenant_id") != tenant_id:
                self.data_layer.update(
                    "tenant_ai_metrics", rid, {"centre_tenant_id": tenant_id}
                )
                row["centre_tenant_id"] = tenant_id

        updates = {
            "query_volume": int(row.get("query_volume") or 0) + (1 if query else 0),
            "mcq_count": int(row.get("mcq_count") or 0) + (1 if mcq else 0),
            "written_count": int(row.get("written_count") or 0) + (1 if written else 0),
            "rate_limit_hits": int(row.get("rate_limit_hits") or 0) + (1 if rate_limit else 0),
            "cache_hits": int(row.get("cache_hits") or 0) + (1 if cache_hit else 0),
            "cache_misses": int(row.get("cache_misses") or 0) + (1 if cache_miss else 0),
            "offline_degrades": int(row.get("offline_degrades") or 0) + (1 if offline else 0),
            "updated_at": _utcnow(),
        }
        self.data_layer.update("tenant_ai_metrics", uuid.UUID(row["id"]), updates)
        row.update(updates)
        # recompute hit rate for return
        total = row["cache_hits"] + row["cache_misses"]
        row["cache_hit_rate"] = round(row["cache_hits"] / total, 4) if total else 0.0
        return row

    def get_ai_metrics(
        self, tenant_id: str, founder_token: str, period: Optional[str] = None
    ) -> Dict[str, Any]:
        self._require_founder(founder_token)
        period = period or _period_now()
        for r in self.data_layer.get_all("tenant_ai_metrics"):
            cid = r.get("centre_tenant_id") or r.get("tenant_id")
            if cid == tenant_id and r.get("period") == period:
                total = int(r.get("cache_hits") or 0) + int(r.get("cache_misses") or 0)
                r = dict(r)
                r["cache_hit_rate"] = (
                    round(int(r.get("cache_hits") or 0) / total, 4) if total else 0.0
                )
                # Strip any accidental spend keys
                r.pop("spend", None)
                r.pop("gemini_cost", None)
                r.pop("cost_usd", None)
                return r
        return TenantAIMetrics(centre_tenant_id=tenant_id, period=period).to_dict()

    def dashboard(self, founder_token: str) -> Dict[str, Any]:
        """Founder overview — all tenants + metrics summary."""
        self._require_founder(founder_token)
        tenants = self.list_tenants(founder_token)
        summaries = []
        for t in tenants:
            metrics = self.get_ai_metrics(t["id"], founder_token)
            summaries.append({
                "tenant_id": t["id"],
                "name": t.get("name"),
                "code": t.get("code"),
                "status": t.get("status"),
                "tier": t.get("tier"),
                "student_count": t.get("student_count"),
                "gemini_key_present": t.get("gemini_key_present"),
                "metrics": {
                    "query_volume": metrics.get("query_volume", 0),
                    "rate_limit_hits": metrics.get("rate_limit_hits", 0),
                    "cache_hit_rate": metrics.get("cache_hit_rate", 0),
                    "mcq_count": metrics.get("mcq_count", 0),
                    "written_count": metrics.get("written_count", 0),
                },
            })
        return {
            "tenant_count": len(tenants),
            "active": sum(1 for t in tenants if t.get("status") == STATUS_ACTIVE),
            "suspended": sum(1 for t in tenants if t.get("status") == STATUS_SUSPENDED),
            "trial": sum(1 for t in tenants if t.get("status") == STATUS_TRIAL),
            "tenants": summaries,
        }

    def list_audit(self, founder_token: str, limit: int = 100) -> List[Dict[str, Any]]:
        self._require_founder(founder_token)
        rows = self.data_layer.get_all("founder_audit")
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return rows[:limit]
