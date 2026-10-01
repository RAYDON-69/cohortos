"""Document that frontend uses exceljs not xlsx (npm advisory)."""
from pathlib import Path

def test_no_xlsx_dependency():
    pkg = Path("frontend/package.json").read_text()
    assert '"xlsx"' not in pkg
    assert "exceljs" in pkg

def test_student_import_uses_exceljs():
    src = Path("frontend/src/screens/admissions/StudentImport.tsx").read_text()
    assert "exceljs" in src
    assert 'import("xlsx")' not in src
