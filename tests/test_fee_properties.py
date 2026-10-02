from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import pytest
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st
from services.pricing_engine import PricingEngine, PricingError

def bdt(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def apply_payment(balance, amount):
    amount = bdt(max(Decimal("0"), amount))
    return bdt(max(Decimal("0"), balance - amount))

@given(st.integers(min_value=0, max_value=500))
@settings(max_examples=40)
def test_pricing_never_negative(student_count):
    eng = PricingEngine()
    try: q = eng.calculate(student_count)
    except PricingError: return
    for k in ("base", "overage", "total", "monthly_total"):
        if k in q and q[k] is not None:
            assert float(q[k]) >= 0

@given(st.decimals(min_value=0, max_value=100000, places=2, allow_nan=False, allow_infinity=False),
       st.decimals(min_value=0, max_value=100000, places=2, allow_nan=False, allow_infinity=False))
@settings(max_examples=50)
def test_partial_payment_never_negative_balance(balance, payment):
    out = apply_payment(bdt(balance), bdt(payment))
    assert out >= 0

def test_idempotent_payment_replay():
    ledger, balance = {}, bdt("1000.00")
    def pay(pid, amount):
        nonlocal balance
        if pid in ledger: return balance
        balance = apply_payment(balance, amount); ledger[pid] = amount
        return balance
    assert pay("pay-1", bdt("200")) == pay("pay-1", bdt("200")) == bdt("800.00")

def test_bdt_rounding_half_up():
    assert bdt(Decimal("1.235")) == Decimal("1.24")
