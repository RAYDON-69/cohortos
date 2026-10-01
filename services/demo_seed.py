"""Demo centre seed — clearly labelled, removable in one click (P27)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid


DEMO_MARKER = "DEMO_COHORTOS"


def _now():
    return datetime.now(timezone.utc)


class DemoSeedService:
    def __init__(self, data_layer=None):
        self.data_layer = data_layer

    def load_demo(self, tenant_id: str) -> Dict[str, Any]:
        if not self.data_layer:
            raise RuntimeError("no data_layer")
        created = []
        batches = [
            ("ব্যাচ এ — SSC Physics", "demo-batch-a"),
            ("ব্যাচ বি — HSC Math", "demo-batch-b"),
            ("ব্যাচ সি — Admission", "demo-batch-c"),
        ]
        for title, code in batches:
            row = {
                "id": str(uuid.uuid4()),
                "name": title,
                "code": code,
                "tenant_id": tenant_id,
                "demo": True,
                "demo_marker": DEMO_MARKER,
            }
            rid = self.data_layer.create("batches", row)
            created.append(("batches", str(rid)))
        students = [
            ("রহিম উদ্দিন", "01710000001"),
            ("করিম আহমেদ", "01710000002"),
            ("সুমাইয়া আক্তার", "01710000003"),
        ]
        for name, phone in students:
            row = {
                "name": name,
                "phone": phone,
                "tenant_id": tenant_id,
                "demo": True,
                "demo_marker": DEMO_MARKER,
                "batch_code": "demo-batch-a",
            }
            rid = self.data_layer.create("students", row)
            created.append(("students", str(rid)))
        # fee due + absence for call desk
        self.data_layer.create(
            "payment_records",
            {
                "student_name": "রহিম উদ্দিন",
                "amount": 500,
                "status": "due",
                "demo_marker": DEMO_MARKER,
                "demo": True,
            },
        )
        self.data_layer.create(
            "attendance_records",
            {
                "student_name": "করিম আহমেদ",
                "status": "absent",
                "demo_marker": DEMO_MARKER,
                "demo": True,
            },
        )
        starts = (_now() + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)
        self.data_layer.create(
            "class_sessions",
            {
                "title": "ডেমো ক্লাস — Physics",
                "batch_id": "demo-batch-a",
                "starts_at": starts.isoformat(),
                "mode": "broadcast",
                "broadcast_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "demo_marker": DEMO_MARKER,
                "demo": True,
                "tenant_id": tenant_id,
            },
        )
        return {"ok": True, "marker": DEMO_MARKER, "created": len(created), "label": "DEMO DATA — not a real centre"}

    def remove_demo(self, tenant_id: str) -> Dict[str, Any]:
        if not self.data_layer:
            raise RuntimeError("no data_layer")
        removed = 0
        for table in ["students", "batches", "payment_records", "attendance_records", "class_sessions"]:
            rows = []
            try:
                rows = self.data_layer.get_all(table) or []
            except Exception:
                continue
            for r in rows:
                if r.get("demo_marker") == DEMO_MARKER or r.get("demo") is True:
                    rid = r.get("id")
                    if rid and hasattr(self.data_layer, "delete"):
                        try:
                            self.data_layer.delete(table, rid)
                            removed += 1
                        except Exception:
                            pass
        return {"ok": True, "removed": removed, "marker": DEMO_MARKER}
