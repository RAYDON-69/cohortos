"""bKash PGW adapter — sandbox defaults, live URLs only when COHORTOS_BKASH_MODE=live."""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional
from urllib import request, error

from services.safe_http import safe_urlopen
from services.payment_providers.base import (
    PaymentProvider,
    CheckoutSession,
    PaymentResult,
    ProviderError,
)

# Public sandbox host patterns (tokenized checkout)
SANDBOX_BASE = os.environ.get(
    "COHORTOS_BKASH_BASE",
    "https://tokenized.sandbox.bka.sh/v1.2.0-beta/tokenized/checkout",
)
LIVE_BASE = os.environ.get(
    "COHORTOS_BKASH_LIVE_BASE",
    "https://tokenized.pay.bka.sh/v1.2.0-beta/tokenized/checkout",
)


class BkashProvider(PaymentProvider):
    name = "bkash"

    def __init__(self):
        self.username = os.environ.get("COHORTOS_BKASH_USERNAME", "")
        self.password = os.environ.get("COHORTOS_BKASH_PASSWORD", "")
        self.app_key = os.environ.get("COHORTOS_BKASH_APP_KEY", "")
        self.app_secret = os.environ.get("COHORTOS_BKASH_APP_SECRET", "")
        mode = (os.environ.get("COHORTOS_BKASH_MODE") or "sandbox").lower()
        self.mode = "live" if mode == "live" else "sandbox"
        self.base = LIVE_BASE if self.mode == "live" else SANDBOX_BASE
        self._token: Optional[str] = None
        self._token_exp = 0.0
        # In-memory sandbox sessions when credentials missing (local test)
        self._mock_sessions: Dict[str, Dict[str, Any]] = {}

    def is_configured(self) -> bool:
        return bool(self.username and self.password and self.app_key and self.app_secret)

    def _grant_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if not self.is_configured():
            raise ProviderError("bKash credentials not configured", "not_configured")
        url = f"{self.base}/token/grant"
        body = json.dumps({"app_key": self.app_key, "app_secret": self.app_secret}).encode()
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "username": self.username,
                "password": self.password,
            },
        )
        try:
            with safe_urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"bKash grant token HTTP {e.code}: {e.read()[:200]}", "auth_failed") from e
        except OSError as e:
            raise ProviderError(f"bKash network error: {e}", "network") from e
        token = data.get("id_token") or ""
        if not token:
            raise ProviderError("bKash grant token missing id_token", "auth_failed")
        self._token = token
        self._token_exp = time.time() + float(data.get("expires_in") or 3600)
        return token

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
            raise ProviderError("bKash only accepts BDT", "currency")
        if not self.is_configured():
            # Sandbox mock path for CI / local without merchant keys
            sid = f"bkash_mock_{uuid.uuid4().hex[:12]}"
            self._mock_sessions[sid] = {
                "amount": amount,
                "currency": "BDT",
                "invoice_id": invoice_id,
                "status": "pending",
            }
            return CheckoutSession(
                provider=self.name,
                session_id=sid,
                amount=amount,
                currency="BDT",
                checkout_url=f"{callback_url}?provider=bkash&session_id={sid}&mock=1",
                status="pending",
                metadata={"mock": True, "invoice_id": invoice_id, "description": description},
                mode="sandbox",
            )
        token = self._grant_token()
        url = f"{self.base}/create"
        payload = {
            "mode": "0011",
            "payerReference": customer_ref or "01XXXXXXXXX",
            "callbackURL": callback_url,
            "amount": f"{amount:.2f}",
            "currency": "BDT",
            "intent": "sale",
            "merchantInvoiceNumber": invoice_id[:30],
        }
        body = json.dumps(payload).encode()
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": token,
                "X-App-Key": self.app_key,
            },
        )
        try:
            with safe_urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"bKash create HTTP {e.code}: {e.read()[:300]}", "create_failed") from e
        except OSError as e:
            raise ProviderError(f"bKash network error: {e}", "network") from e
        payment_id = data.get("paymentID") or data.get("paymentId") or ""
        checkout = data.get("bkashURL") or data.get("checkoutURL") or ""
        if not payment_id:
            raise ProviderError(f"bKash create missing paymentID: {data}", "create_failed")
        return CheckoutSession(
            provider=self.name,
            session_id=payment_id,
            amount=amount,
            currency="BDT",
            checkout_url=checkout,
            status="pending",
            metadata={"invoice_id": invoice_id, "raw": data},
            mode=self.mode,
        )

    def confirm_payment(self, session_id: str, **kwargs: Any) -> PaymentResult:
        if session_id.startswith("bkash_mock_"):
            sess = self._mock_sessions.get(session_id) or {}
            return PaymentResult(
                provider=self.name,
                session_id=session_id,
                success=True,
                transaction_id=f"MOCK-TRX-{session_id[-8:]}",
                amount=float(sess.get("amount") or 0),
                currency="BDT",
                message="Mock sandbox payment completed (no merchant credentials)",
                raw={"mock": True},
            )
        if not self.is_configured():
            raise ProviderError("bKash credentials not configured", "not_configured")
        token = self._grant_token()
        url = f"{self.base}/execute"
        body = json.dumps({"paymentID": session_id}).encode()
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": token,
                "X-App-Key": self.app_key,
            },
        )
        try:
            with safe_urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except error.HTTPError as e:
            raise ProviderError(f"bKash execute HTTP {e.code}: {e.read()[:300]}", "execute_failed") from e
        except OSError as e:
            raise ProviderError(f"bKash network error: {e}", "network") from e
        status = (data.get("transactionStatus") or data.get("status") or "").lower()
        ok = status in ("completed", "success", "successful")
        return PaymentResult(
            provider=self.name,
            session_id=session_id,
            success=ok,
            transaction_id=str(data.get("trxID") or data.get("trxId") or ""),
            amount=float(data.get("amount") or 0),
            currency=data.get("currency") or "BDT",
            message=str(data.get("statusMessage") or status),
            raw=data,
        )
