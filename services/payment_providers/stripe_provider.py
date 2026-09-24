"""Stripe Billing adapter — test-mode by default (sk_test_…)."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict
from urllib import request, error
from urllib.parse import urlencode

from services.payment_providers.base import (
    PaymentProvider,
    CheckoutSession,
    PaymentResult,
    ProviderError,
)


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self):
        self.secret = os.environ.get("COHORTOS_STRIPE_SECRET_KEY", "")
        self.webhook_secret = os.environ.get("COHORTOS_STRIPE_WEBHOOK_SECRET", "")
        # Force test mode unless explicitly live and key is sk_live_
        if self.secret.startswith("sk_live_") and os.environ.get("COHORTOS_STRIPE_MODE") == "live":
            self.mode = "live"
        else:
            self.mode = "sandbox"
        self._mock_sessions: Dict[str, Dict[str, Any]] = {}

    def is_configured(self) -> bool:
        return bool(self.secret.startswith("sk_"))

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
        if not self.is_configured():
            sid = f"stripe_mock_{uuid.uuid4().hex[:12]}"
            self._mock_sessions[sid] = {
                "amount": amount,
                "currency": currency.upper() or "USD",
                "invoice_id": invoice_id,
            }
            return CheckoutSession(
                provider=self.name,
                session_id=sid,
                amount=amount,
                currency=(currency or "USD").upper(),
                checkout_url=f"{callback_url}?provider=stripe&session_id={sid}&mock=1",
                status="pending",
                metadata={"mock": True, "invoice_id": invoice_id},
                mode="sandbox",
            )
        # Stripe Checkout Session (test or live key)
        # amount in minor units
        cur = (currency or "USD").lower()
        unit = int(round(amount * 100))
        form = {
            "mode": "payment",
            "success_url": f"{callback_url}?provider=stripe&session_id={{CHECKOUT_SESSION_ID}}&status=success",
            "cancel_url": f"{callback_url}?provider=stripe&status=cancel",
            "line_items[0][price_data][currency]": cur,
            "line_items[0][price_data][product_data][name]": description or f"Invoice {invoice_id}",
            "line_items[0][price_data][unit_amount]": str(unit),
            "line_items[0][quantity]": "1",
            "client_reference_id": invoice_id,
            "metadata[invoice_id]": invoice_id,
        }
        if customer_ref:
            form["customer"] = customer_ref
        body = urlencode(form).encode()
        req = request.Request(
            "https://api.stripe.com/v1/checkout/sessions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.secret}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"Stripe session HTTP {e.code}: {e.read()[:300]}", "create_failed") from e
        except OSError as e:
            raise ProviderError(f"Stripe network error: {e}", "network") from e
        return CheckoutSession(
            provider=self.name,
            session_id=data.get("id") or "",
            amount=amount,
            currency=cur.upper(),
            checkout_url=data.get("url") or "",
            status="pending",
            metadata={"invoice_id": invoice_id, "raw": data},
            mode=self.mode,
        )

    def confirm_payment(self, session_id: str, **kwargs: Any) -> PaymentResult:
        if session_id.startswith("stripe_mock_"):
            sess = self._mock_sessions.get(session_id) or {}
            return PaymentResult(
                provider=self.name,
                session_id=session_id,
                success=True,
                transaction_id=f"MOCK-STRIPE-{session_id[-8:]}",
                amount=float(sess.get("amount") or 0),
                currency=str(sess.get("currency") or "USD"),
                message="Mock sandbox payment completed (no Stripe key)",
                raw={"mock": True},
            )
        if not self.is_configured():
            raise ProviderError("Stripe secret key not configured", "not_configured")
        req = request.Request(
            f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
            method="GET",
            headers={"Authorization": f"Bearer {self.secret}"},
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"Stripe retrieve HTTP {e.code}: {e.read()[:300]}", "query_failed") from e
        except OSError as e:
            raise ProviderError(f"Stripe network error: {e}", "network") from e
        paid = data.get("payment_status") == "paid" or data.get("status") == "complete"
        return PaymentResult(
            provider=self.name,
            session_id=session_id,
            success=bool(paid),
            transaction_id=str(data.get("payment_intent") or data.get("id") or ""),
            amount=(float(data.get("amount_total") or 0) / 100.0),
            currency=(data.get("currency") or "usd").upper(),
            message=str(data.get("payment_status") or data.get("status") or ""),
            raw=data,
        )
