"""
Telephony adapters for CohortOS voice assist (P24).

Research (2026-09):
- Twilio: SMS to BD is supported with Sender ID rules; programmable Voice to BD
  numbers is used by some BPOs but is NOT a safe default for coaching-centre
  automated outreach under BTRC double-consent / DNC expectations.
- BD-native options with real voice APIs: AwajDigital (voice broadcast + TTS),
  ePBX.bd (outbound API + TTS), BTCL Alaap Cloud (voice broadcasting),
  Infosoftbd Voice API. These require commercial onboarding + BTRC posture.
- Decision: default provider = ManualOnlyTelephonyProvider (never places a
  network call). Optional BDVoiceBroadcastAdapter is a thin HTTP stub behind
  env COHORTOS_VOICE_PROVIDER=awaj|epbx and never runs without human_action_id.

Assisted mode hard gate: place_outbound_call() refuses empty human_action_id.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class TelephonyProvider(ABC):
    @abstractmethod
    def place_call(
        self,
        *,
        to: str,
        script: str,
        human_action_id: Optional[str],
        from_number: str = "",
    ) -> Dict[str, Any]:
        ...


class ManualOnlyTelephonyProvider(TelephonyProvider):
    """Default: staff dials from their own phone; software never autodials."""

    def place_call(
        self,
        *,
        to: str,
        script: str,
        human_action_id: Optional[str],
        from_number: str = "",
    ) -> Dict[str, Any]:
        if not human_action_id:
            raise PermissionError(
                "Outbound call blocked: human_action_id required (assisted mode; no autodial)"
            )
        return {
            "placed": False,
            "mode": "manual",
            "to": to,
            "human_action_id": human_action_id,
            "message": "Dial from your phone using the script. Call was not placed by software.",
        }


class BDVoiceBroadcastAdapter(TelephonyProvider):
    """
    Optional human-triggered broadcast via BD provider (AwajDigital-style).
    Still requires human_action_id. Does not fire without COHORTOS_VOICE_API_URL.
    """

    def place_call(
        self,
        *,
        to: str,
        script: str,
        human_action_id: Optional[str],
        from_number: str = "",
    ) -> Dict[str, Any]:
        if not human_action_id:
            raise PermissionError(
                "Outbound call blocked: human_action_id required (assisted mode; no autodial)"
            )
        url = os.environ.get("COHORTOS_VOICE_API_URL") or ""
        key = os.environ.get("COHORTOS_VOICE_API_KEY") or ""
        if not url or not key:
            return {
                "placed": False,
                "mode": "manual_fallback",
                "to": to,
                "human_action_id": human_action_id,
                "message": "Voice API not configured; place the call manually.",
            }
        # Thin HTTP — only on explicit human action
        try:
            import httpx
            r = httpx.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "to": to,
                    "text": script[:2000],
                    "human_action_id": human_action_id,
                    "from": from_number,
                },
                timeout=30.0,
            )
            return {
                "placed": r.is_success,
                "mode": "bd_voice_api",
                "status_code": r.status_code,
                "to": to,
                "human_action_id": human_action_id,
                "body": (r.text or "")[:500],
            }
        except Exception as e:
            return {
                "placed": False,
                "mode": "bd_voice_api_error",
                "error": str(e),
                "human_action_id": human_action_id,
            }


def get_telephony_provider() -> TelephonyProvider:
    kind = (os.environ.get("COHORTOS_VOICE_PROVIDER") or "manual").strip().lower()
    if kind in ("awaj", "epbx", "bd", "broadcast"):
        return BDVoiceBroadcastAdapter()
    return ManualOnlyTelephonyProvider()


def place_outbound_call(
    *,
    to: str,
    script: str,
    human_action_id: Optional[str],
    from_number: str = "",
) -> Dict[str, Any]:
    """
    Sole entry point for outbound calls.
    HARD GATE: human_action_id must be non-empty (desk button / explicit staff action).
    """
    if not human_action_id or not str(human_action_id).strip():
        raise PermissionError(
            "Outbound call blocked: human-initiated action id is required (no autodial)"
        )
    return get_telephony_provider().place_call(
        to=to, script=script, human_action_id=str(human_action_id).strip(), from_number=from_number
    )
