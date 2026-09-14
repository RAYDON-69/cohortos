"""
SaaS pricing engine (SPEC Module 10).

Tiers by student count:
  Starter  ≤500   → ৳5,000 / month
  Growth   ≤1500  → ৳12,000 / month (configurable; SPEC range 10–15k)
  Scale    ≤6000  → custom base (default ৳25,000) + overage

Overage charged per student above tier limit.
Annual cycle applies discount to 12× monthly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from models.saas import (
    TIER_STARTER,
    TIER_GROWTH,
    TIER_SCALE,
    STARTER_LIMIT,
    STARTER_PRICE,
    GROWTH_LIMIT,
    GROWTH_PRICE,
    SCALE_LIMIT,
    DEFAULT_OVERAGE_PER_STUDENT,
    DEFAULT_ANNUAL_DISCOUNT,
)


class PricingError(Exception):
    pass


class PricingEngine:
    def __init__(
        self,
        starter_limit: int = STARTER_LIMIT,
        starter_price: float = STARTER_PRICE,
        growth_limit: int = GROWTH_LIMIT,
        growth_price: float = GROWTH_PRICE,
        scale_limit: int = SCALE_LIMIT,
        scale_base_price: float = 25000.0,
        default_overage: float = DEFAULT_OVERAGE_PER_STUDENT,
        default_annual_discount: float = DEFAULT_ANNUAL_DISCOUNT,
    ):
        self.starter_limit = starter_limit
        self.starter_price = float(starter_price)
        self.growth_limit = growth_limit
        self.growth_price = float(growth_price)
        self.scale_limit = scale_limit
        self.scale_base_price = float(scale_base_price)
        self.default_overage = float(default_overage)
        self.default_annual_discount = float(default_annual_discount)

    def recommend_tier(self, student_count: int) -> str:
        n = max(0, int(student_count))
        if n <= self.starter_limit:
            return TIER_STARTER
        if n <= self.growth_limit:
            return TIER_GROWTH
        if n <= self.scale_limit:
            return TIER_SCALE
        raise PricingError(
            f"Student count {n} exceeds Scale limit ({self.scale_limit}). "
            "Contact sales for enterprise."
        )

    def tier_limit(self, tier: str) -> int:
        if tier == TIER_STARTER:
            return self.starter_limit
        if tier == TIER_GROWTH:
            return self.growth_limit
        if tier == TIER_SCALE:
            return self.scale_limit
        raise PricingError(f"Unknown tier: {tier}")

    def base_price(self, tier: str, custom_scale_price: Optional[float] = None) -> float:
        if tier == TIER_STARTER:
            return self.starter_price
        if tier == TIER_GROWTH:
            return self.growth_price
        if tier == TIER_SCALE:
            return float(custom_scale_price if custom_scale_price is not None else self.scale_base_price)
        raise PricingError(f"Unknown tier: {tier}")

    def calculate(
        self,
        student_count: int,
        tier: Optional[str] = None,
        billing_cycle: str = "monthly",
        overage_rate: Optional[float] = None,
        annual_discount: Optional[float] = None,
        custom_scale_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Return a full quote breakdown.
        """
        n = max(0, int(student_count))
        if n > self.scale_limit:
            raise PricingError(
                f"Student count {n} exceeds maximum supported ({self.scale_limit})"
            )

        tier = tier or self.recommend_tier(n)
        limit = self.tier_limit(tier)
        base = self.base_price(tier, custom_scale_price)
        overage_rate = float(
            overage_rate if overage_rate is not None else self.default_overage
        )
        overage_students = max(0, n - limit)
        overage_amount = overage_students * overage_rate
        monthly_total = base + overage_amount

        cycle = (billing_cycle or "monthly").lower()
        if cycle not in ("monthly", "annual"):
            raise PricingError(f"Invalid billing_cycle: {billing_cycle}")

        discount = float(
            annual_discount if annual_discount is not None else self.default_annual_discount
        )
        discount = max(0.0, min(0.5, discount))  # clamp 0–50%

        if cycle == "annual":
            annual_gross = monthly_total * 12
            annual_total = round(annual_gross * (1.0 - discount), 2)
            amount_due = annual_total
            effective_monthly = round(annual_total / 12, 2)
        else:
            annual_gross = monthly_total * 12
            annual_total = None
            amount_due = round(monthly_total, 2)
            effective_monthly = amount_due

        return {
            "student_count": n,
            "tier": tier,
            "tier_limit": limit,
            "base_price_bdt": base,
            "overage_students": overage_students,
            "overage_rate_bdt": overage_rate,
            "overage_amount_bdt": round(overage_amount, 2),
            "monthly_total_bdt": round(monthly_total, 2),
            "billing_cycle": cycle,
            "annual_discount": discount if cycle == "annual" else 0.0,
            "annual_gross_bdt": round(annual_gross, 2),
            "annual_total_bdt": annual_total,
            "amount_due_bdt": amount_due,
            "effective_monthly_bdt": effective_monthly,
            "currency": "BDT",
        }
