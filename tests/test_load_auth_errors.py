"""401/403 on authorised paths must count as load errors (A2)."""
from scripts.load_smoke import _is_error

def test_401_on_students_is_error_when_token_set(monkeypatch):
    monkeypatch.setattr("scripts.load_smoke.TOKEN", "real-token")
    assert _is_error(401, "/t/x/students") is True
    assert _is_error(403, "/t/x/fees") is True

def test_401_on_health_not_counted_same_way(monkeypatch):
    monkeypatch.setattr("scripts.load_smoke.TOKEN", "real-token")
    assert _is_error(401, "/health") is False  # health is public

def test_200_not_error(monkeypatch):
    monkeypatch.setattr("scripts.load_smoke.TOKEN", "real-token")
    assert _is_error(200, "/t/x/students") is False

def test_5xx_is_error(monkeypatch):
    monkeypatch.setattr("scripts.load_smoke.TOKEN", "")
    assert _is_error(500, "/t/x/students") is True
