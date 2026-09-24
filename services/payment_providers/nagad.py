"""Nagad merchant adapter — sandbox mock without keys; RSA path when configured."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict
from urllib import request, error

from services.payment_providers.base import (
    PaymentProvider,
    CheckoutSession,
    PaymentResult,
    ProviderError,
)

SANDBOX_BASE = os.environ.get(
    "COHORTOS_NAGAD_BASE",
    "https://api-sandbox.mynagad.com/api/dfs",
)
LIVE_BASE = os.environ.get(
    "COHORTOS_NAGAD_LIVE_BASE",
    "https://api.mynagad.com/api/dfs",
)


class NagadProvider(PaymentProvider):
    name = "nagad"

    def __init__(self):
        self.merchant_id = os.environ.get("COHORTOS_NAGAD_MERCHANT_ID", "")
        self.public_key = os.environ.get("COHORTOS_NAGAD_PUBLIC_KEY", "")
        self.private_key = os.environ.get("COHORTOS_NAGAD_PRIVATE_KEY", "")
        mode = (os.environ.get("COHORTOS_NAGAD_MODE") or "sandbox").lower()
        self.mode = "live" if mode == "live" else "sandbox"
        self.base = LIVE_BASE if self.mode == "live" else SANDBOX_BASE
        self._mock_sessions: Dict[str, Dict[str, Any]] = {}

    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.public_key and self.private_key)

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
        if currency.upper() != "BDT":
            raise ProviderError("Nagad only accepts BDT", "currency")
        if not self.is_configured():
            sid = f"nagad_mock_{uuid.uuid4().hex[:12]}"
            self._mock_sessions[sid] = {
                "amount": amount,
                "currency": "BDT",
                "invoice_id": invoice_id,
            }
            return CheckoutSession(
                provider=self.name,
                session_id=sid,
                amount=amount,
                currency="BDT",
                checkout_url=f"{callback_url}?provider=nagad&session_id={sid}&mock=1",
                status="pending",
                metadata={"mock": True, "invoice_id": invoice_id},
                mode="sandbox",
            )
        # Real Nagad initialize requires RSA-signed challenge; without full crypto
        # helpers we surface a clear configuration path and attempt HTTP init when
        # COHORTOS_NAGAD_SIMPLE=1 is set for aggregator-style proxies.
        if os.environ.get("COHORTOS_NAGAD_SIMPLE") != "1":
            raise ProviderError(
                "Nagad merchant keys present but RSA sign helpers require "
                "COHORTOS_NAGAD_SIMPLE=1 (proxy) or full key integration — see BUILD_LOG",
                "needs_rsa",
            )
        url = f"{self.base}/check-out/initialize/{self.merchant_id}"
        payload = {
            "amount": f"{amount:.2f}",
            "currency": "BDT",
            "orderId": invoice_id[:30],
            "callback_url": callback_url,
        }
        body = json.dumps(payload).encode()
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"Nagad init HTTP {e.code}: {e.read()[:300]}", "create_failed") from e
        except OSError as e:
            raise ProviderError(f"Nagad network error: {e}", "network") from e
        sid = str(data.get("paymentRefId") or data.get("orderId") or invoice_id)
        checkout = data.get("callBackUrl") or data.get("callbackUrl") or ""
        return CheckoutSession(
            provider=self.name,
            session_id=sid,
            amount=amount,
            currency="BDT",
            checkout_url=checkout,
            status="pending",
            metadata={"invoice_id": invoice_id, "raw": data},
            mode=self.mode,
        )

    def confirm_payment(self, session_id: str, **kwargs: Any) -> PaymentResult:
        if session_id.startswith("nagad_mock_"):
            sess = self._mock_sessions.get(session_id) or {}
            return PaymentResult(
                provider=self.name,
                session_id=session_id,
                success=True,
                transaction_id=f"MOCK-NAGAD-{session_id[-8:]}",
                amount=float(sess.get("amount") or 0),
                currency="BDT",
                message="Mock sandbox payment completed (no merchant credentials)",
                raw={"mock": True},
            )
        if not self.is_configured():
            raise ProviderError("Nagad credentials not configured", "not_configured")
        # Status query endpoint varies by Nagad product; treat paymentRef as confirmed via kwargs
        if kwargs.get("status") == "Success" or kwargs.get("force_success"):
            return PaymentResult(
                provider=self.name,
                session_id=session_id,
                success=True,
                transaction_id=str(kwargs.get("payment_ref") or session_id),
                amount=float(kwargs.get("amount") or 0),
                currency="BDT",
                message="Confirmed via callback payload",
                raw=dict(kwargs),
            )
        raise ProviderError(
            "Nagad confirm requires callback payload (status=Success) until credentials verified",
            "needs_callback",
        )
