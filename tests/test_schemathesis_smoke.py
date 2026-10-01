import os
import pytest

pytest.importorskip("schemathesis")


@pytest.mark.skipif(os.environ.get("COHORTOS_RUN_FUZZ") != "1", reason="set COHORTOS_RUN_FUZZ=1")
def test_schemathesis_no_500():
    import schemathesis
    from hypothesis import settings, HealthCheck
    os.environ.setdefault("COHORTOS_JWT_SECRET", "fuzz-secret")
    os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
    os.environ.setdefault("COHORTOS_RATE_LIMIT_DISABLED", "1")
    from api.main import create_api_app_or_raise
    app = create_api_app_or_raise()
    schema = schemathesis.openapi.from_asgi("/openapi.json", app)
    # lightweight: only /health
    @schema.include(path_regex="^/health$").parametrize()
    @settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
    def _case(case):
        case.call_and_validate()
    _case()
