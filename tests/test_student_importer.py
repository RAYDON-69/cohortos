"""CSV/Excel student importer: Bangla names, BD phones, preview + errors."""
import io
import pytest
from services.student_importer import preview_csv, validate_phone_bd, import_students


def test_phone_validation_bd():
    assert validate_phone_bd("01774656829") is True
    assert validate_phone_bd("0177-465-6829") is True
    assert validate_phone_bd("12345") is False
    assert validate_phone_bd("+8801774656829") is True


def test_preview_csv_bangla_names_and_errors():
    raw = "name,phone,batch\nরহিম,01774656829,A\nBad,123,B\n"
    prev = preview_csv(raw.encode("utf-8"))
    assert prev["total"] == 2
    assert prev["valid"] == 1
    assert prev["errors"]
    assert any("phone" in e.get("reason", "").lower() for e in prev["errors"])
    assert prev["rows"][0]["name"] == "রহিম"


def test_import_creates_students(monkeypatch):
    created = []
    class FakeAdmission:
        def admit_student(self, **kwargs):
            created.append(kwargs)
            return {"id": f"s{len(created)}", **kwargs}
    raw = "name,phone\nKarim,01812345678\n"
    result = import_students(raw.encode("utf-8"), admission=FakeAdmission(), batch_id=None)
    assert result["imported"] == 1
    assert created[0]["phone"] == "01812345678" or "01812345678" in str(created[0])
