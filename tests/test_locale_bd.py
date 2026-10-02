from __future__ import annotations
import csv, io
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
DHAKA = ZoneInfo("Asia/Dhaka")

def format_bdt(amount): return f"৳{amount:,.2f}"
def to_bangla_digits(s): return s.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
def normalize_bd_phone(raw):
    digits = "".join(c for c in raw if c.isdigit())
    if digits.startswith("880") and len(digits)==13: digits = "0"+digits[3:]
    if len(digits)==11 and digits.startswith("01"): return digits
    return None
def csv_utf8_bom(rows):
    buf = io.StringIO(); w = csv.writer(buf)
    for r in rows: w.writerow(r)
    return ("\ufeff"+buf.getvalue()).encode("utf-8")

def test_asia_dhaka_no_dst():
    w = datetime(2026,1,15,12,0,tzinfo=DHAKA); s = datetime(2026,7,15,12,0,tzinfo=DHAKA)
    assert w.utcoffset() == s.utcoffset()
def test_bdt_format(): assert "৳" in format_bdt(1500)
def test_bangla_digits(): assert to_bangla_digits("017") == "০১৭"
@pytest.mark.parametrize("raw,expected",[("01712345678","01712345678"),("+8801712345678","01712345678"),("1712345678",None)])
def test_phone_formats(raw, expected): assert normalize_bd_phone(raw)==expected
def test_csv_bom():
    data = csv_utf8_bom([["নাম"],["রহিম"]])
    assert data[:3]==b"\xef\xbb\xbf"
