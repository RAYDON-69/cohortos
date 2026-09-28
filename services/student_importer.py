"""CSV/Excel student importer — papaparse/SheetJS on frontend; server validates BD phones."""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional

_PHONE_RE = re.compile(r"^(?:\+?880|0)?1[3-9]\d{8}$")


def validate_phone_bd(phone: str) -> bool:
    digits = re.sub(r"[\s\-]", "", phone or "")
    if digits.startswith("+880"):
        digits = "0" + digits[4:]
    elif digits.startswith("880"):
        digits = "0" + digits[3:]
    return bool(_PHONE_RE.match(digits))


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("880") and len(digits) >= 13:
        digits = "0" + digits[3:]
    return digits


def preview_csv(data: bytes, encoding: str = "utf-8") -> Dict[str, Any]:
    text = data.decode(encoding, errors="replace")
    # strip BOM
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    rows_out = []
    errors = []
    valid = 0
    for i, row in enumerate(reader, start=2):
        # flexible headers
        name = (row.get("name") or row.get("Name") or row.get("নাম") or "").strip()
        phone = (row.get("phone") or row.get("Phone") or row.get("মোবাইল") or "").strip()
        batch = (row.get("batch") or row.get("Batch") or row.get("ব্যাচ") or "").strip()
        entry = {"line": i, "name": name, "phone": phone, "batch": batch}
        errs = []
        if not name:
            errs.append("missing name")
        if not validate_phone_bd(phone):
            errs.append("invalid phone (need 01XXXXXXXXX)")
        if errs:
            errors.append({"line": i, "reason": "; ".join(errs), "row": entry})
        else:
            valid += 1
            entry["phone"] = normalize_phone(phone)
        rows_out.append(entry)
    return {
        "total": len(rows_out),
        "valid": valid,
        "errors": errors,
        "rows": rows_out,
    }


def import_students(
    data: bytes,
    *,
    admission=None,
    batch_id: Optional[str] = None,
    encoding: str = "utf-8",
) -> Dict[str, Any]:
    prev = preview_csv(data, encoding=encoding)
    imported = 0
    failed = []
    for row in prev["rows"]:
        if not row.get("name") or not validate_phone_bd(row.get("phone") or ""):
            failed.append(row)
            continue
        if admission is None:
            continue
        try:
            kwargs = {
                "name": row["name"],
                "phone": normalize_phone(row["phone"]),
            }
            # admit_student signatures vary — try common forms
            if batch_id:
                kwargs["batch_id"] = batch_id
            try:
                admission.admit_student(**kwargs)
            except TypeError:
                admission.admit_student(row["name"], kwargs["phone"], batch_id)
            imported += 1
        except Exception as e:
            failed.append({**row, "error": str(e)})
    return {"imported": imported, "failed": failed, "preview": prev}
