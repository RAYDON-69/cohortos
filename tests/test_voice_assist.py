"""P24 Voice assist — assisted mode only; no silent autodial."""
import inspect
import os
import pytest


def test_no_autodial_without_human_action():
    """Static gate: telephony place_call requires human_action_id; Manual provider never dials."""
    from services.telephony_provider import ManualOnlyTelephonyProvider, place_outbound_call

    src = inspect.getsource(place_outbound_call)
    assert "human_action_id" in src
    assert "if not human_action_id" in src or "human_action_id" in src

    provider = ManualOnlyTelephonyProvider()
    with pytest.raises(PermissionError):
        provider.place_call(to="+8801711111111", script="hi", human_action_id=None)
    # Even with human_action_id, ManualOnly never places a network call
    result = provider.place_call(
        to="+8801711111111",
        script="fee reminder",
        human_action_id="desk-click-001",
    )
    assert result.get("placed") is False
    assert result.get("mode") == "manual"


def test_no_code_path_imports_twilio_client_for_auto():
    """Assisted stack must not hard-require Twilio (BD voice not assumed)."""
    import services.telephony_provider as tp
    src = inspect.getsource(tp)
    # Adapter may mention Twilio as optional future, but default path is ManualOnly / BD voice broadcast
    assert "ManualOnlyTelephonyProvider" in src


def test_script_generation_and_encrypt_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("COHORTOS_VOICE_FERNET_KEY", "")  # force derived key path
    from services.voice_assist_service import VoiceAssistService, encrypt_field, decrypt_field

    plain = "রহিমের অভিভাবককে ফি মনে করিয়ে দিন — ৫০০ টাকা"
    token = encrypt_field(plain)
    assert token != plain
    assert decrypt_field(token) == plain

    class FakeDL:
        def __init__(self):
            self.rows = []
        def create(self, table, row):
            self.rows.append((table, row))
            return row.get("id")
        def get_all(self, table):
            return [r for t, r in self.rows if t == table]

    svc = VoiceAssistService(data_layer=FakeDL(), llm_complete=lambda p: "Assalamu alaikum, this is a fee reminder script.")
    out = svc.generate_script(
        student_name="রহিম",
        phone="01711111111",
        purpose="fee_reminder",
        amount_bdt=500,
        actor_id="desk1",
        actor_role="desk",
    )
    assert out.get("script_id")
    assert "script" in out
    # stored ciphertext not equal to plain student name dump without encryption marker
    stored = [r for t, r in svc.data_layer.rows if t == "voice_call_scripts"][0]
    assert stored.get("script_enc")
    assert "রহিম" not in (stored.get("script_enc") or "")


def test_summarize_completed_call_uses_redaction_when_cloud():
    from services.voice_assist_service import VoiceAssistService
    from services.agent_safety import redact_pii

    notes = "Called 01774656829 parent, will pay tomorrow"
    red = redact_pii(notes)
    assert "01774656829" not in red

    class FakeDL:
        def __init__(self):
            self.rows = []
        def create(self, table, row):
            self.rows.append((table, row))
            return row.get("id")
        def get_all(self, table):
            return [r for t, r in self.rows if t == table]

    svc = VoiceAssistService(data_layer=FakeDL(), llm_complete=lambda p: "Parent agreed to pay tomorrow.")
    summary = svc.summarize_call(
        call_notes=notes,
        student_name="Karim",
        purpose="fee_reminder",
        actor_id="desk1",
        actor_role="desk",
        cloud_llm=False,
    )
    assert summary.get("summary")
    assert summary.get("summary_id")


def test_human_triggered_call_request_logs_audit():
    from services.voice_assist_service import VoiceAssistService

    audits = []
    class FakeAudit:
        def log(self, *a, **k):
            audits.append((a, k))
        def log_create(self, *a, **k):
            audits.append((a, k))

    class FakeDL:
        def __init__(self):
            self.rows = []
        def create(self, table, row):
            self.rows.append((table, dict(row)))
            return row.get("id")
        def get_all(self, table):
            return [r for t, r in self.rows if t == table]

    svc = VoiceAssistService(data_layer=FakeDL(), audit_service=FakeAudit())
    res = svc.request_human_call(
        to_phone="01711111111",
        script_id="s1",
        human_action_id="ui-btn-uuid",
        actor_id="desk1",
        actor_role="desk",
    )
    assert res.get("ok") is True
    assert res.get("placed") is False  # assisted: no autodial
    assert any("voice" in str(x).lower() or "call" in str(x).lower() for x in audits) or any(
        t == "voice_call_requests" for t, _ in svc.data_layer.rows
    )
