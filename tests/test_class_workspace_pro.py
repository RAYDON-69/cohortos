"""P26 stress + classroom pro tests."""
import pytest
from services.class_session_service import ClassSessionService, verify_join_token, sanitize_notice
from services.device_tier import select_tier


class FakeDL:
    def __init__(self):
        self.store = {}
    def create(self, table, row):
        self.store.setdefault(table, []).append(dict(row))
        return row.get("id")
    def get_all(self, table):
        return list(self.store.get(table) or [])
    def update(self, table, rid, patch):
        for r in self.store.get(table) or []:
            if r.get("id") == rid:
                r.update(patch)
                return r


def test_device_tier_lite_on_4gb():
    t = select_tier(device_memory_gb=4.0, hardware_concurrency=4, downlink_mbps=10)
    assert t["tier"] == "lite"
    assert t["whiteboard"] is False
    assert t["max_resolution"] == "360p"


def test_device_tier_full_and_override():
    t = select_tier(device_memory_gb=16, hardware_concurrency=8, downlink_mbps=50)
    assert t["tier"] == "full"
    t2 = select_tier(device_memory_gb=16, user_override="lite")
    assert t2["tier"] == "lite"
    assert "user_override" in t2["reasons"][0]


def test_cross_tenant_jwt_reuse_fails():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="A", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="X", actor_role="teacher")
    link = svc.join_link(s["id"], role="participant", display_name="S")
    with pytest.raises(PermissionError):
        verify_join_token(link["token"], expected_tenant_id="B", jwt_secret="secret-32chars-minimum-value!!")


def test_expired_session_rejects_token():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="X", actor_role="teacher")
    link = svc.join_link(s["id"], role="participant", display_name="S")
    svc.end_session(s["id"], actor_role="teacher")
    with pytest.raises(PermissionError):
        verify_join_token(link["token"], expected_tenant_id="t", jwt_secret="secret-32chars-minimum-value!!", require_active_session=svc)


def test_idempotent_timetable_no_duplicates():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    a = svc.generate_from_timetable(batch_id="b1", weekday=0, time_hhmm="10:00", weeks=2, actor_role="owner")
    b = svc.generate_from_timetable(batch_id="b1", weekday=0, time_hhmm="10:00", weeks=2, actor_role="owner")
    # second pass returns same ids (idempotent)
    ids_a = {x["id"] for x in a}
    ids_b = {x["id"] for x in b}
    assert ids_a == ids_b


def test_teacher_double_booking_detected():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    svc.create_session(
        batch_id="b1", title="A", teacher_id="T1",
        starts_at="2026-10-05T10:00:00+00:00", ends_at="2026-10-05T12:00:00+00:00",
        actor_role="owner",
    )
    with pytest.raises(ValueError, match="teacher_double_booked"):
        svc.create_session(
            batch_id="b2", title="B", teacher_id="T1",
            starts_at="2026-10-05T11:00:00+00:00", ends_at="2026-10-05T13:00:00+00:00",
            actor_role="owner",
        )


def test_xss_sanitized_in_notice_and_poll():
    assert "<" not in sanitize_notice("<script>alert(1)</script>hi")
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="বাংলা ক্লাস", actor_role="teacher")
    assert s["room"].isascii()
    n = svc.post_notice(s["id"], body="<img onerror=alert(1)>ok", actor_role="teacher")
    assert "<img" not in n["body"]
    p = svc.create_poll(s["id"], question="<b>Q</b>", options=["A<script>", "B"], actor_role="teacher")
    assert "<" not in p["question"]


def test_bangla_title_room_slug_ascii():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="পদার্থবিজ্ঞান রিভিশন", actor_role="teacher")
    assert s["room"].startswith("cohortos")
    assert all(ord(c) < 128 for c in s["room"])


def test_concurrent_joins_sqlite_style():
    """200 join_link calls must not raise under in-memory locking simulation."""
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="Load", actor_role="teacher")
    for i in range(200):
        link = svc.join_link(s["id"], role="participant", display_name=f"S{i}", student_id=f"st{i}")
        assert link["token"]


def test_open_room_warning_for_public_jitsi():
    svc = ClassSessionService(
        data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!",
        jitsi_base_url="https://meet.jit.si",
    )
    s = svc.create_session(batch_id="b1", title="X", actor_role="teacher")
    link = svc.join_link(s["id"], role="participant", display_name="S")
    assert link["access_mode"] == "OPEN-ROOM"
    assert link["access_mode_warning"]


def test_call_desk_no_autodial_outcome_requires_human():
    from services.call_desk_service import CallDeskService
    from services.voice_assist_service import VoiceAssistService
    va = VoiceAssistService(data_layer=FakeDL())
    desk = CallDeskService(data_layer=FakeDL(), voice_assist=va)
    cards = desk.build_queue(fee_dues=[{"name": "Karim", "phone": "01711112222", "detail": "500 due"}])
    assert cards and cards[0]["tel_link"].startswith("tel:")
    with pytest.raises(PermissionError):
        desk.log_outcome(card_id=cards[0]["id"], outcome="reached", human_action_id="", actor_role="desk")


def test_broadcast_mode_join_returns_stream_url():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(
        batch_id="b1",
        title="Live FB",
        mode="broadcast",
        broadcast_url="https://www.youtube.com/watch?v=abc",
        actor_role="teacher",
    )
    assert s["mode"] == "broadcast"
    link = svc.join_link(s["id"], role="participant", display_name="S", student_id="s1")
    assert link["mode"] == "broadcast"
    assert "youtube" in link["join_url"]
    assert link["provider"] == "broadcast"


def test_broadcast_requires_url():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    with pytest.raises(ValueError, match="broadcast_url"):
        svc.create_session(batch_id="b1", title="X", mode="broadcast", actor_role="teacher")


def test_create_returns_persisted_id_joinable():
    """Regression: DataAccessLayer overwrites id — join must use returned id."""
    class RealishDL(FakeDL):
        def create(self, table, row):
            import uuid
            rid = uuid.uuid4()
            stored = dict(row)
            stored["id"] = str(rid)
            self.store.setdefault(table, []).append(stored)
            return rid

    svc = ClassSessionService(data_layer=RealishDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    s = svc.create_session(batch_id="b1", title="X", actor_role="teacher")
    # join must succeed with returned id
    link = svc.join_link(s["id"], role="participant", display_name="S")
    assert link["session_id"] == s["id"]
    assert s["id"] in [r["id"] for r in svc.list_sessions()]


def test_broadcast_rejects_insecure_urls():
    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t", jwt_secret="secret-32chars-minimum-value!!")
    for bad in [
        "http://youtube.com/x",
        "javascript:alert(1)",
        "data:text/html,hi",
        "https://user:pass@evil.com/x",
    ]:
        with pytest.raises(ValueError):
            svc.create_session(
                batch_id="b1", title="X", mode="broadcast", broadcast_url=bad, actor_role="teacher"
            )
