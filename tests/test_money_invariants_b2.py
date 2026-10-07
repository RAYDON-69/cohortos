"""B2: Property-based money invariants."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import pytest
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, assume
from hypothesis import strategies as st

def bdt(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

class Ledger:
    def __init__(self, opening=Decimal("0")):
        self.balance = bdt(opening)
        self.seen = set()
    def pay(self, pid, amount):
        if pid in self.seen:
            return self.balance
        self.seen.add(pid)
        self.balance = bdt(self.balance + bdt(amount))
        return self.balance
    def refund(self, rid, amount):
        if rid in self.seen:
            return self.balance
        amount = bdt(amount)
        if amount > self.balance:
            raise ValueError("refund exceeds balance")
        self.seen.add(rid)
        self.balance = bdt(self.balance - amount)
        return self.balance

@given(st.lists(st.decimals(min_value=1, max_value=5000, places=2, allow_nan=False, allow_infinity=False), min_size=1, max_size=20))
@settings(max_examples=40)
def test_ledger_sum_matches_balance(amounts):
    led = Ledger()
    total = Decimal("0")
    for i, a in enumerate(amounts):
        led.pay(f"p{i}", a)
        total = bdt(total + bdt(a))
    assert led.balance == total

@given(st.decimals(min_value=100, max_value=10000, places=2, allow_nan=False, allow_infinity=False),
       st.decimals(min_value=0, max_value=10000, places=2, allow_nan=False, allow_infinity=False))
@settings(max_examples=40)
def test_refund_never_exceeds_paid(paid, refund):
    led = Ledger()
    led.pay("p0", paid)
    if bdt(refund) > led.balance:
        with pytest.raises(ValueError):
            led.refund("r0", refund)
    else:
        led.refund("r0", refund)
        assert led.balance >= 0

def test_double_submit_idempotent():
    led = Ledger()
    led.pay("same", bdt("100"))
    led.pay("same", bdt("100"))
    assert led.balance == bdt("100")

@given(st.decimals(min_value=0, max_value=1000, places=4, allow_nan=False, allow_infinity=False))
@settings(max_examples=30)
def test_bdt_rounding_no_phantom_taka(x):
    a = bdt(x)
    assert a == bdt(a)
    # two quantizations don't create money
    assert bdt(a + a) == bdt(bdt(a) + bdt(a))
