"""Fail CI if services ignore DataAccessLayer.create() return value while keeping a local id."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"

# create("x", row) without assignment, when the same function builds row with "id"
PATTERN = re.compile(
    r'(?<![=\w])self\.data_layer\.create\(\s*["\'](\w+)["\']\s*,\s*(\w+)\s*\)',
    re.MULTILINE,
)


def test_no_ignored_create_return_in_services():
    offenders = []
    for path in SERVICES.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in PATTERN.finditer(text):
            # Look back 15 lines for assignment of returned id OR row["id"] update after
            start = max(0, m.start() - 400)
            window = text[start : m.end() + 120]
            # OK if assigned: rid = self.data_layer.create
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : text.find("\n", m.start())]
            if re.search(r"=\s*self\.data_layer\.create", line):
                continue
            # OK if next lines set var["id"] = str(
            after = text[m.end() : m.end() + 80]
            if '["id"]' in after and "str(" in after:
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{text[:m.start()].count(chr(10))+1}: {line.strip()}")
    assert not offenders, "Ignored create() return (id overwrite risk):\n" + "\n".join(offenders[:30])
