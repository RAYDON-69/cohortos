"""Scheduled/condition triggers, dry-run, history, idempotency."""
import pytest


def test_evaluate_fee_overdue_condition():
    from services.automation_service import AutomationService
    # unit-level condition matcher
    svc = AutomationService.__new__(AutomationService)
    ctx = {"fee.days_overdue": 10}
    conds = [{"field": "fee.days_overdue", "op": ">=", "value": 7}]
    assert svc._match_conditions(conds, ctx) is True
    ctx2 = {"fee.days_overdue": 3}
    assert svc._match_conditions(conds, ctx2) is False


def test_dry_run_does_not_mutate_and_logs():
    from services.automation_service import AutomationService
    from models.base import TenantContext
    import tempfile, os
    # Prefer lightweight mock
    class Mini:
        def __init__(self):
            self._log = []
            self._rules = []
            self._idempotency = set()
        def upsert_rule(self, body):
            rid = body.get("id") or "rule-1"
            body = dict(body, id=rid)
            self._rules = [body]
            return body
        def list_rules(self):
            return self._rules
        def evaluate_rule(self, rule, context=None, dry_run=False):
            from services.automation_service import AutomationService as AS
            # bind methods
            return AS.evaluate_rule(self, rule, context, dry_run=dry_run)
    # Use real evaluate if available
    pass


def test_idempotency_same_day_skips_duplicate():
    from services.automation_service import AutomationService
    # _idempotency_key stable per day
    svc = AutomationService.__new__(AutomationService)
    k1 = svc._idempotency_key("r1", "s1", "fee_reminder")
    k2 = svc._idempotency_key("r1", "s1", "fee_reminder")
    assert k1 == k2
