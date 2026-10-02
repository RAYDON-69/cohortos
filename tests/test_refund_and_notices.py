"""R-FEE-08 refunds + parent notices (P36)."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

def bdt(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def apply_refund(paid: Decimal, refund: Decimal) -> Decimal:
    refund = bdt(max(Decimal("0"), refund))
    if refund > paid:
        raise ValueError("refund exceeds paid")
    return bdt(paid - refund)

def test_refund_never_exceeds_paid():
    assert apply_refund(bdt("500"), bdt("100")) == bdt("400")
    try:
        apply_refund(bdt("100"), bdt("150"))
        assert False
    except ValueError:
        pass

def test_refund_idempotent_ledger():
    ledger = {}
    paid = bdt("1000")
    def refund(rid, amount):
        nonlocal paid
        if rid in ledger:
            return paid
        paid = apply_refund(paid, amount)
        ledger[rid] = amount
        return paid
    assert refund("r1", bdt("200")) == bdt("800")
    assert refund("r1", bdt("200")) == bdt("800")
    assert len(ledger) == 1

def test_parent_notice_template_bangla():
    def render_notice(student_name: str, status: str, lang: str = "bn") -> str:
        if lang == "bn":
            return f"প্রিয় অভিভাবক, {student_name} আজ {status}। — CohortOS"
        return f"Dear parent, {student_name} is {status} today. — CohortOS"
    msg = render_notice("রহিম", "অনুপস্থিত", "bn")
    assert "রহিম" in msg and "অনুপস্থিত" in msg
    assert "Dear parent" in render_notice("Rahim", "absent", "en")
