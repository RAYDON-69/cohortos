"""
Optional ZKTeco biometric driver using pyzk (SPEC Module 2).

- Does not start automatically; centres enable via config or API.
- Falls back cleanly when pyzk is not installed or device is unreachable.
- Feeds punches into AttendanceService.ingest_punch / ingest_biometric_batch.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger("cohortos.biometric")

try:
    from zk import ZK  # pyzk
    PYZK_AVAILABLE = True
except ImportError:
    PYZK_AVAILABLE = False
    ZK = None  # type: ignore


class BiometricDriverError(Exception):
    pass


class BiometricDriver:
    """
    Thin adapter over pyzk for ZKTeco K60 / series devices.

    Usage:
        driver = BiometricDriver(ip="192.168.1.201", port=4370)
        punches = driver.pull_punches(since=None)
        attendance.ingest_biometric_batch(punches, device_id=...)
    """

    def __init__(
        self,
        ip: str,
        port: int = 4370,
        password: int = 0,
        timeout: int = 10,
        force_udp: bool = False,
    ):
        self.ip = ip
        self.port = port
        self.password = password
        self.timeout = timeout
        self.force_udp = force_udp

    def is_available(self) -> bool:
        return PYZK_AVAILABLE

    def _connect(self):
        if not PYZK_AVAILABLE:
            raise BiometricDriverError(
                "pyzk is not installed. Install with: pip install pyzk"
            )
        zk = ZK(
            self.ip,
            port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=self.force_udp,
            ommit_ping=False,
        )
        return zk.connect()

    def test_connection(self) -> Dict[str, Any]:
        if not PYZK_AVAILABLE:
            return {"ok": False, "error": "pyzk not installed", "pyzk": False}
        try:
            conn = self._connect()
            info = {
                "ok": True,
                "pyzk": True,
                "firmware": getattr(conn, "get_firmware_version", lambda: None)(),
                "device_name": getattr(conn, "get_device_name", lambda: None)(),
            }
            conn.disconnect()
            return info
        except Exception as e:
            return {"ok": False, "pyzk": True, "error": str(e)}

    def pull_punches(
        self,
        clear_after: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Pull attendance punches from device.
        Returns list of {device_user_id, punched_at (ISO), raw}.
        """
        if not PYZK_AVAILABLE:
            raise BiometricDriverError("pyzk is not installed")
        conn = self._connect()
        try:
            records = conn.get_attendance() or []
            out: List[Dict[str, Any]] = []
            for r in records:
                uid = str(getattr(r, "user_id", "") or getattr(r, "uid", ""))
                ts = getattr(r, "timestamp", None)
                if isinstance(ts, datetime):
                    punched_at = ts.replace(tzinfo=timezone.utc).isoformat() if ts.tzinfo is None else ts.isoformat()
                else:
                    punched_at = datetime.now(timezone.utc).isoformat()
                out.append({
                    "device_user_id": uid,
                    "punched_at": punched_at,
                    "raw": {"status": getattr(r, "status", None), "punch": getattr(r, "punch", None)},
                })
            if clear_after:
                try:
                    conn.clear_attendance()
                except Exception as e:
                    logger.warning("clear_attendance failed: %s", e)
            return out
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass

    def pull_and_ingest(
        self,
        ingest_fn: Callable[..., Any],
        device_id: Optional[str] = None,
        clear_after: bool = False,
    ) -> Dict[str, Any]:
        """Pull punches and pass each to ingest_fn (AttendanceService.ingest_punch)."""
        punches = self.pull_punches(clear_after=clear_after)
        accepted = 0
        errors: List[str] = []
        for p in punches:
            try:
                ingest_fn(
                    punched_at=p["punched_at"],
                    device_user_id=p["device_user_id"],
                    device_id=device_id,
                    source="biometric",
                )
                accepted += 1
            except Exception as e:
                errors.append(f"{p.get('device_user_id')}: {e}")
        return {"pulled": len(punches), "accepted": accepted, "errors": errors}
