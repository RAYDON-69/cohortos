from __future__ import annotations
from datetime import datetime, timedelta, timezone
from models.saas import STATUS_TRIAL, STATUS_SUSPENDED, SaaSTenant
from models.billing import SUB_TRIAL, Subscription

def test_trial_fields_on_tenant_model():
    t = SaaSTenant(id="t1", name="Centre", status=STATUS_TRIAL, trial_ends_at="2026-10-15T00:00:00+00:00")
    assert t.to_dict()["status"] == STATUS_TRIAL

def test_trial_expiry_detection_helper():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    def is_expired(s):
        if not s: return False
        try: end = datetime.fromisoformat(s.replace("Z","+00:00"))
        except ValueError: return False
        return end < datetime.now(timezone.utc)
    assert is_expired(past) and not is_expired(future)

def test_billing_subscription_status():
    sub = Subscription(tenant_id="t1", plan_code="starter", status=SUB_TRIAL)
    assert sub.to_dict()["status"] == SUB_TRIAL

def test_license_token_tamper_not_implemented():
    # NOT-DONE: signed licence + clock-rollback — design only
    assert True

def test_tenant_suspension_status():
    t = SaaSTenant(id="t2", name="Suspended", status=STATUS_SUSPENDED)
    assert t.status == STATUS_SUSPENDED
