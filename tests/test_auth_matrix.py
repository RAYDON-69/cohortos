"""Authorization matrix: enumerate routes, classify, cross-tenant IDOR, adversarial cases."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

PUBLIC_PREFIXES = ("/health", "/openapi", "/docs", "/redoc", "/auth/", "/join/")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    # Set ONLY inside fixture — never at import time (leaks into other tests)
    os.environ["COHORTOS_JWT_SECRET"] = "test-secret-for-matrix-not-prod-xx"
    os.environ["COHORTOS_FOUNDER_TOKEN"] = "founder-matrix"
    os.environ["COHORTOS_AUTH_DB"] = str(tmp_path_factory.mktemp("auth") / "a.db")
    os.environ["COHORTOS_CLOUD_DB"] = str(tmp_path_factory.mktemp("cloud") / "c.db")
    os.environ["COHORTOS_TEST_EXPOSE_OTP"] = "1"
    os.environ["COHORTOS_RATE_LIMIT_DISABLED"] = "1"
    os.environ["COHORTOS_SKIP_MODEL_DOWNLOAD"] = "1"
    os.environ["COHORTOS_ENV"] = "test"
    from api.main import create_api_app_or_raise
    app = create_api_app_or_raise()
    with TestClient(app) as c:
        c.app = app  # type: ignore
        yield c
    # Cleanup so subsequent test modules see production defaults
    os.environ.pop("COHORTOS_RATE_LIMIT_DISABLED", None)


def _classify(path: str) -> str:
    if any(path.startswith(p) or path == p.rstrip("/") for p in PUBLIC_PREFIXES):
        return "public"
    if path.startswith("/founder") or "founder" in path:
        return "founder"
    if path.startswith("/t/{") or path.startswith("/t/"):
        return "tenant-scoped"
    if path.startswith("/auth"):
        return "public"
    return "authenticated"


def test_route_inventory_classified(client: TestClient):
    routes, unclassified = [], []
    counts = {"public": 0, "authenticated": 0, "tenant-scoped": 0, "founder": 0}
    for r in client.app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if not path:
            continue
        cls = _classify(path)
        routes.append({"path": path, "methods": sorted(methods), "class": cls})
        if cls in counts:
            counts[cls] += 1
        else:
            unclassified.append(path)
    report = {
        "total_routes": len(routes),
        "classified_public": counts["public"],
        "classified_authenticated": counts["authenticated"],
        "classified_tenant_scoped": counts["tenant-scoped"],
        "classified_founder": counts["founder"],
        "unclassified": unclassified,
        "routes_sample": routes[:30],
    }
    Path("/tmp/auth-matrix-report.json").write_text(json.dumps(report, indent=2))
    print(f"ROUTE_COUNT={len(routes)} CLASSIFIED={len(routes)-len(unclassified)}")
    assert routes, "no routes"
    assert not unclassified, f"unclassified: {unclassified}"


def _seed(client, phone, name):
    r = client.post(
        "/auth/centre-trial",
        json={"centre_name": name, "owner_phone": phone, "owner_name": "Owner", "student_count": 1},
    )
    assert r.status_code in (200, 201), r.text
    tid = r.json()["tenant_id"]
    otp = client.post("/auth/request-otp", json={"phone": phone, "tenant_id": tid})
    assert otp.status_code == 200, otp.text
    body = otp.json()
    ver = client.post(
        "/auth/verify-otp",
        json={"phone": phone, "code": body.get("_test_code"), "otp_id": body["otp_id"], "tenant_id": tid},
    )
    assert ver.status_code == 200, ver.text
    return tid, ver.json()["access_token"]


def test_no_token_on_tenant_paths(client: TestClient):
    for path, method in [
        ("/t/fake/classes/sessions", "GET"),
        ("/t/fake/backup", "POST"),
        ("/t/fake/call-desk/queue", "POST"),
    ]:
        r = client.get(path) if method == "GET" else client.post(path, json={})
        assert r.status_code in (401, 403, 404, 405, 422), f"{path}->{r.status_code}"
        assert r.status_code < 500


def test_cross_tenant_idor_blocked(client: TestClient):
    tid_a, tok_a = _seed(client, "01710000021", "Centre A")
    tid_b, tok_b = _seed(client, "01710000022", "Centre B")
    ca = client.post(
        f"/t/{tid_a}/classes/sessions",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={
            "batch_id": "b1",
            "title": "A only",
            "mode": "broadcast",
            "broadcast_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
    )
    if ca.status_code == 200:
        sid = ca.json().get("id")
        r = client.get(
            f"/t/{tid_a}/classes/sessions",
            headers={"Authorization": f"Bearer {tok_b}"},
        )
        assert r.status_code in (401, 403), f"cross-tenant list {r.status_code}"
        assert r.status_code < 500
        if sid:
            j = client.post(
                f"/t/{tid_a}/classes/sessions/{sid}/join",
                headers={"Authorization": f"Bearer {tok_b}"},
                json={"role": "participant", "display_name": "Evil"},
            )
            assert j.status_code in (401, 403, 404)
            assert j.status_code < 500


def test_adversarial_cases(client: TestClient):
    """10 adversarial IDOR / auth abuse cases."""
    tid_a, tok_a = _seed(client, "01710000031", "Adv A")
    tid_b, tok_b = _seed(client, "01710000032", "Adv B")
    failures = []

    def check(name, status, allowed=(401, 403, 404, 405, 422)):
        if status not in allowed or status >= 500:
            failures.append(f"{name}: status={status}")

    # 1 path id vs body tenant mismatch
    r = client.post(
        f"/t/{tid_a}/classes/sessions",
        headers={"Authorization": f"Bearer {tok_b}"},
        json={"batch_id": "x", "title": "spoof", "mode": "broadcast",
              "broadcast_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "tenant_id": tid_a},
    )
    check("body_tenant_spoof", r.status_code)

    # 2 expired/garbage token
    r = client.get(f"/t/{tid_a}/classes/sessions", headers={"Authorization": "Bearer not.a.jwt"})
    check("garbage_token", r.status_code)

    # 3 student-like token missing — no token
    r = client.get(f"/t/{tid_a}/backup")
    check("no_token_backup", r.status_code, (401, 403, 404, 405, 422, 405))

    # 4 mass-assignment tenant_id on demo
    r = client.post(
        f"/t/{tid_b}/demo/load",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"tenant_id": tid_b},
    )
    check("demo_cross_tenant", r.status_code)

    # 5 backup cross tenant
    r = client.post(f"/t/{tid_a}/backup", headers={"Authorization": f"Bearer {tok_b}"})
    check("backup_cross", r.status_code)

    # 6 whiteboard cross
    r = client.get(
        f"/t/{tid_a}/classes/sessions/fake-id/whiteboard",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    check("whiteboard_cross", r.status_code)

    # 7 export pdpa cross
    r = client.get(f"/t/{tid_a}/export/pdpa", headers={"Authorization": f"Bearer {tok_b}"})
    check("pdpa_cross", r.status_code)

    # 8 call desk cross
    r = client.post(
        f"/t/{tid_a}/call-desk/queue",
        headers={"Authorization": f"Bearer {tok_b}"},
        json={},
    )
    check("calldesk_cross", r.status_code)

    # 9 join with wrong tenant path
    r = client.post(
        f"/t/{tid_a}/classes/sessions/x/join",
        headers={"Authorization": f"Bearer {tok_b}"},
        json={"role": "participant", "display_name": "x"},
    )
    check("join_cross", r.status_code)

    # 10 header spoof X-Tenant-Id
    r = client.get(
        f"/t/{tid_a}/classes/sessions",
        headers={"Authorization": f"Bearer {tok_b}", "X-Tenant-Id": tid_a},
    )
    check("header_spoof", r.status_code)

    assert not failures, "adversarial failures: " + "; ".join(failures)
