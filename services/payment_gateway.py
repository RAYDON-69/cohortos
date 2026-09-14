"""
Payment gateway interface for CohortOS (SPEC Module 3).

Default: deep-link / copy-paste mode for bKash & Nagad (origin-client default).
Optional: webhook/callback handlers for future gateway providers.
No hard dependency on any commercial SDK — centres configure links or a provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid
import hashlib
import hmac
import os


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaymentGatewayError(Exception):
    pass


class PaymentGateway(ABC):
    @abstractmethod
    def create_payment_intent(
        self,
        amount: float,
        currency: str,
        student_id: str,
        year: int,
        month: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    def verify_callback(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        ...

    def name(self) -> str:
        return self.__class__.__name__


class DeepLinkGateway(PaymentGateway):
    """
    Origin-client default: bKash / Nagad deep-links + copy-paste targets.
    No external API calls. Centres set links in config.
    """

    def __init__(self, bkash_link: str = "", nagad_link: str = "", merchant_ref_prefix: str = "CM"):
        self.bkash_link = (bkash_link or "").strip()
        self.nagad_link = (nagad_link or "").strip()
        self.merchant_ref_prefix = merchant_ref_prefix

    def create_payment_intent(
        self,
        amount: float,
        currency: str,
        student_id: str,
        year: int,
        month: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ref = f"{self.merchant_ref_prefix}-{student_id[:8]}-{year}{month:02d}-{uuid.uuid4().hex[:6]}"
        return {
            "provider": "deeplink",
            "intent_id": ref,
            "amount": amount,
            "currency": currency or "BDT",
            "student_id": student_id,
            "year": year,
            "month": month,
            "bkash_link": self.bkash_link,
            "nagad_link": self.nagad_link,
            "copy_paste_ref": ref,
            "instructions": (
                "Pay via bKash/Nagad using the link or send the reference "
                f"'{ref}' with the amount. Staff then marks paid + locks."
            ),
            "created_at": _utcnow(),
            "metadata": metadata or {},
        }

    def verify_callback(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        # Deep-link mode has no automated callback; staff marks paid manually.
        raise PaymentGatewayError(
            "DeepLinkGateway has no automated callback — mark paid manually after confirmation."
        )


class WebhookGateway(PaymentGateway):
    """
    Generic signed-webhook gateway skeleton for future providers.
    Requires COACHMATE_PAYMENT_WEBHOOK_SECRET for HMAC verification.
    """

    def __init__(self, webhook_secret: Optional[str] = None, provider_name: str = "generic"):
        self.webhook_secret = (
            webhook_secret
            or os.environ.get("COACHMATE_PAYMENT_WEBHOOK_SECRET")
            or ""
        ).strip()
        self.provider_name = provider_name

    def create_payment_intent(
        self,
        amount: float,
        currency: str,
        student_id: str,
        year: int,
        month: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        intent_id = f"wh_{uuid.uuid4().hex}"
        return {
            "provider": self.provider_name,
            "intent_id": intent_id,
            "amount": amount,
            "currency": currency or "BDT",
            "student_id": student_id,
            "year": year,
            "month": month,
            "status": "pending",
            "created_at": _utcnow(),
            "metadata": metadata or {},
        }

    def verify_callback(self, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        if not self.webhook_secret:
            raise PaymentGatewayError("COACHMATE_PAYMENT_WEBHOOK_SECRET not configured")
        sig = headers.get("x-signature") or headers.get("X-Signature") or ""
        body = str(payload.get("_raw") or payload)
        expected = hmac.new(
            self.webhook_secret.encode(),
            body.encode() if isinstance(body, str) else body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise PaymentGatewayError("Invalid webhook signature")
        return {
            "intent_id": payload.get("intent_id") or payload.get("id"),
            "status": payload.get("status") or "paid",
            "amount": payload.get("amount"),
            "verified": True,
        }


def build_gateway_from_config(config_get) -> PaymentGateway:
    """Factory: prefer configured deep-links; optional webhook when secret present."""
    bkash = (config_get("payment.bkash_deeplink") or "") if callable(config_get) else ""
    nagad = (config_get("payment.nagad_deeplink") or "") if callable(config_get) else ""
    mode = (config_get("payment.gateway_mode") or "deeplink") if callable(config_get) else "deeplink"
    if mode == "webhook" and os.environ.get("COACHMATE_PAYMENT_WEBHOOK_SECRET"):
        return WebhookGateway()
    return DeepLinkGateway(bkash_link=str(bkash), nagad_link=str(nagad))
