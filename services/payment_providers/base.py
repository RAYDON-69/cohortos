"""Abstract payment provider interface — swappable per tenant."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ProviderError(Exception):
    def __init__(self, message: str, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


@dataclass
class CheckoutSession:
    """Redirect/hosted checkout payload returned to the client."""
    provider: str
    session_id: str
    amount: float
    currency: str
    checkout_url: str = ""
    status: str = "pending"  # pending | requires_action | completed | failed
    metadata: Dict[str, Any] = field(default_factory=dict)
    mode: str = "sandbox"  # sandbox | live

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "session_id": self.session_id,
            "amount": self.amount,
            "currency": self.currency,
            "checkout_url": self.checkout_url,
            "status": self.status,
            "metadata": dict(self.metadata),
            "mode": self.mode,
        }


@dataclass
class PaymentResult:
    provider: str
    session_id: str
    success: bool
    transaction_id: str = ""
    amount: float = 0.0
    currency: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "session_id": self.session_id,
            "success": self.success,
            "transaction_id": self.transaction_id,
            "amount": self.amount,
            "currency": self.currency,
            "message": self.message,
            "raw": dict(self.raw),
        }


class PaymentProvider(ABC):
    name: str = "none"
    supports_sandbox: bool = True

    @abstractmethod
    def is_configured(self) -> bool:
        """True when credentials are present (sandbox or live)."""

    @abstractmethod
    def create_checkout(
        self,
        *,
        amount: float,
        currency: str,
        invoice_id: str,
        callback_url: str,
        customer_ref: str = "",
        description: str = "",
    ) -> CheckoutSession:
        ...

    @abstractmethod
    def confirm_payment(self, session_id: str, **kwargs: Any) -> PaymentResult:
        """Finalize after redirect/callback (execute payment / retrieve session)."""

    def query_payment(self, session_id: str) -> PaymentResult:
        return self.confirm_payment(session_id)
