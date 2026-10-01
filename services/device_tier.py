"""Client/server device tier selection for class media (P26)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def select_tier(
    *,
    device_memory_gb: Optional[float] = None,
    hardware_concurrency: Optional[int] = None,
    downlink_mbps: Optional[float] = None,
    effective_type: Optional[str] = None,
    user_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    LITE: ≤4GB RAM or 2G/slow-2g or <1.5Mbps or ≤2 cores
    FULL: otherwise
    user_override: 'lite' | 'full' forces tier (with reason).
    """
    reasons = []
    if user_override in ("lite", "full"):
        tier = user_override
        reasons.append(f"user_override:{user_override}")
        return _profile(tier, reasons)

    lite = False
    if device_memory_gb is not None and device_memory_gb <= 4.0:
        lite = True
        reasons.append(f"deviceMemory={device_memory_gb}GB<=4")
    if hardware_concurrency is not None and hardware_concurrency <= 2:
        lite = True
        reasons.append(f"cores={hardware_concurrency}<=2")
    et = (effective_type or "").lower()
    if et in ("slow-2g", "2g"):
        lite = True
        reasons.append(f"network={et}")
    if downlink_mbps is not None and downlink_mbps < 1.5:
        lite = True
        reasons.append(f"downlink={downlink_mbps}<1.5")

    if not reasons:
        reasons.append("defaults_to_full")
    return _profile("lite" if lite else "full", reasons)


def _profile(tier: str, reasons: list) -> Dict[str, Any]:
    if tier == "lite":
        return {
            "tier": "lite",
            "reasons": reasons,
            "audio_first": True,
            "max_resolution": "360p",
            "max_tiles": 4,
            "virtual_background": False,
            "blur": False,
            "last_n_video": 2,
            "whiteboard": False,
            "one_tab_warning": True,
            "message_bn": "লাইট মোড: দুর্বল ডিভাইস/নেটওয়ার্ক — অডিও অগ্রাধিকার, ৩৬০p, হোয়াইটবোর্ড বন্ধ।",
            "message_en": "Lite mode: weak device/network — audio-first, 360p, whiteboard off.",
        }
    return {
        "tier": "full",
        "reasons": reasons,
        "audio_first": False,
        "max_resolution": "720p",
        "max_tiles": 16,
        "virtual_background": True,
        "blur": True,
        "last_n_video": 9,
        "whiteboard": True,
        "one_tab_warning": False,
        "message_bn": "ফুল মোড: HD গ্রিড ও হোয়াইটবোর্ড চালু।",
        "message_en": "Full mode: HD grid and whiteboard enabled.",
    }
