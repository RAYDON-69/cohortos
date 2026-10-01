"""P25 class workspace — Jitsi-backed sessions, tenant-scoped join tokens."""
import time
import pytest


def test_create_session_linked_to_batch():
    from services.class_session_service import ClassSessionService

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
            return None

    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t1")
    s = svc.create_session(
        batch_id="b1",
        title="Physics revision",
        starts_at="2026-10-01T10:00:00+06:00",
        actor_id="teacher1",
        actor_role="teacher",
    )
    assert s["id"]
    assert s["batch_id"] == "b1"
    assert s["status"] == "scheduled"
    listed = svc.list_sessions(batch_id="b1")
    assert len(listed) == 1


def test_join_url_is_tenant_scoped_and_expiring():
    from services.class_session_service import ClassSessionService, verify_join_token

    class FakeDL:
        def __init__(self):
            self.store = {}
        def create(self, table, row):
            self.store.setdefault(table, []).append(dict(row))
            return row.get("id")
        def get_all(self, table):
            return list(self.store.get(table) or [])

    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="tenant-A", jwt_secret="test-secret-32chars-minimum!!")
    s = svc.create_session(batch_id="b1", title="Chem", actor_id="t", actor_role="teacher")
    teacher = svc.join_link(s["id"], role="moderator", display_name="Sir", actor_id="t")
    student = svc.join_link(s["id"], role="participant", display_name="Student", actor_id="s1")
    assert "room" in teacher
    assert teacher["join_url"].startswith("https://") or "meet." in teacher["join_url"] or "jitsi" in teacher["join_url"].lower() or "/#" in teacher["join_url"]
    # Cross-tenant token must fail
    with pytest.raises(PermissionError):
        verify_join_token(
            student["token"],
            expected_tenant_id="tenant-B",
            jwt_secret="test-secret-32chars-minimum!!",
        )
    # Same tenant ok
    claims = verify_join_token(
        student["token"],
        expected_tenant_id="tenant-A",
        jwt_secret="test-secret-32chars-minimum!!",
    )
    assert claims["session_id"] == s["id"]
    assert claims["role"] == "participant"


def test_expire_session_invalidates_join():
    from services.class_session_service import ClassSessionService, verify_join_token

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

    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t1", jwt_secret="test-secret-32chars-minimum!!")
    s = svc.create_session(batch_id="b1", title="X", actor_id="t", actor_role="owner")
    link = svc.join_link(s["id"], role="participant", display_name="A", actor_id="s")
    svc.end_session(s["id"], actor_id="t", actor_role="owner")
    with pytest.raises(PermissionError):
        verify_join_token(link["token"], expected_tenant_id="t1", jwt_secret="test-secret-32chars-minimum!!", require_active_session=svc)


def test_notice_chat_message_no_public_student_index():
    from services.class_session_service import ClassSessionService

    class FakeDL:
        def __init__(self):
            self.store = {}
        def create(self, table, row):
            self.store.setdefault(table, []).append(dict(row))
            return row.get("id")
        def get_all(self, table):
            return list(self.store.get(table) or [])

    svc = ClassSessionService(data_layer=FakeDL(), tenant_id="t1")
    s = svc.create_session(batch_id="b1", title="Y", actor_id="t", actor_role="teacher")
    svc.post_notice(s["id"], body="Class starts in 10 min", actor_id="t", actor_role="teacher")
    notices = svc.list_notices(s["id"])
    assert len(notices) == 1
    assert "student_name" not in notices[0]  # no public student name index on notices
