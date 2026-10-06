"""Regression tests for the security hardening (auth, payments, admin routes, CORS).

Runs against a live API, like the rest of this suite:

    API_BASE_URL=http://127.0.0.1:8001 TEST_ADMIN_EMAIL=admin@leamss.com \
    TEST_ADMIN_PASSWORD=... pytest backend/tests/test_security_hardening.py
"""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@leamss.com")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")


def _post(path, **kw):
    return requests.post(BASE + path, timeout=30, **kw)


@pytest.fixture(scope="module")
def admin_token():
    if not ADMIN_PASSWORD:
        pytest.skip("TEST_ADMIN_PASSWORD not set")
    r = _post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_legacy_backdoor_password_rejected():
    if ADMIN_PASSWORD == "Admin@123":
        pytest.skip("test DB intentionally seeded with the legacy password")
    r = _post("/auth/login", json={"email": "admin@leamss.com", "password": "Admin@123"})
    assert r.status_code in (401, 429)


def test_regex_email_cannot_match_other_accounts():
    r = _post("/auth/login", json={"email": ".*", "password": "whatever"})
    assert r.status_code in (401, 429)


def test_anonymous_cannot_register_admin():
    r = _post("/auth/register", json={
        "email": f"evil-{uuid.uuid4().hex[:6]}@example.com", "password": "Evil!Passw0rd",
        "name": "Evil", "role": "admin",
    })
    assert r.status_code == 403


def test_admin_can_create_staff_without_receiving_their_token(admin_token):
    r = _post("/auth/register", headers={"Authorization": f"Bearer {admin_token}"}, json={
        "email": f"staff-{uuid.uuid4().hex[:6]}@example.com", "password": "Staff!Passw0rd",
        "name": "Staff", "role": "partner",
    })
    assert r.status_code == 200, r.text
    assert r.json()["token"] is None
    assert r.json()["user"]["role"] == "partner"


def test_forged_token_with_old_default_secret_rejected():
    import jwt
    forged = jwt.encode({"sub": "x", "role": "admin"}, "leamss-portal-secret-key-2024-secure", algorithm="HS256")
    r = requests.get(BASE + "/auth/me", headers={"Authorization": f"Bearer {forged}"}, timeout=30)
    assert r.status_code == 401


@pytest.mark.parametrize("method,path,kwargs", [
    ("GET", "/atlas/admin/countries", {}),
    ("PUT", "/atlas/admin/countries/AU", {"json": {"enabled": False}}),
    ("POST", "/seo-ssg/regenerate-one", {"json": {"country_code": "AU", "code": "261313"}}),
])
def test_admin_routes_require_auth(method, path, kwargs):
    r = requests.request(method, BASE + path, timeout=30, **kwargs)
    assert r.status_code in (401, 403)


def test_atlas_admin_rejects_unknown_fields(admin_token):
    r = requests.put(BASE + "/atlas/admin/countries/AU", headers={"Authorization": f"Bearer {admin_token}"},
                     json={"code": "ZZ"}, timeout=30)
    assert r.status_code == 400


def test_mock_payment_routes_disabled():
    if os.environ.get("PAYMENT_MODE") == "mock":
        pytest.skip("server running in mock payment mode")
    assert _post(f"/pre-assessment/{uuid.uuid4()}/mock-payment").status_code == 404
    assert _post("/pre-assess-portal/public/mock-pay", json={"token": "x"}).status_code == 404


def test_cors_blocks_unknown_origin():
    r = requests.options(BASE + "/auth/login", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}, timeout=30)
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_allows_leamss_origin():
    r = requests.options(BASE + "/auth/login", headers={
        "Origin": "https://leamss.com", "Access-Control-Request-Method": "POST"}, timeout=30)
    assert r.headers.get("access-control-allow-origin") == "https://leamss.com"


def test_login_is_rate_limited():
    email = f"nobody-{uuid.uuid4().hex[:6]}@example.com"
    codes = [_post("/auth/login", json={"email": email, "password": "bad"}).status_code for _ in range(7)]
    assert codes[-1] == 429
