"""Resolve payment provider by name / tenant preference."""
from __future__ import annotations

from typing import Dict, List

from services.payment_providers.base import PaymentProvider, ProviderError
from services.payment_providers.bkash import BkashProvider
from services.payment_providers.nagad import NagadProvider
from services.payment_providers.stripe_provider import StripeProvider

_REGISTRY = {
    "bkash": BkashProvider,
    "nagad": NagadProvider,
    "stripe": StripeProvider,
}


def get_payment_provider(name: str) -> PaymentProvider:
    key = (name or "").lower().strip()
    if key not in _REGISTRY:
        raise ProviderError(f"Unknown payment provider: {name}", "unknown_provider")
    return _REGISTRY[key]()


def list_providers() -> List[Dict]:
    out = []
    for name, cls in _REGISTRY.items():
        p = cls()
        out.append(
            {
                "name": name,
                "configured": p.is_configured(),
                "mode": getattr(p, "mode", "sandbox"),
                "supports_sandbox": True,
            }
        )
    return out
