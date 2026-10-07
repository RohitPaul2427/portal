"""End-to-end tests for the governance foundation (Backlog Phase 0-1).

Runs against a live API with a throw-away database:

    API_BASE_URL=http://127.0.0.1:8001 TEST_ADMIN_PASSWORD=... \
        pytest -q backend/tests/test_governance_api.py
"""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/") + "/api"
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@leamss.com")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
PWD = "Gov!Test" + uuid.uuid4().hex[:6] + "A1"


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _login(email, password):
    r = requests.post(BASE + "/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _register(admin_tok, role):
    email = f"gov-{role}-{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(BASE + "/auth/register", headers=_h(admin_tok), timeout=30,
                      json={"email": email, "password": PWD, "name": f"Gov {role}", "role": role})
    assert r.status_code == 200, r.text
    tok, user = _login(email, PWD)
    return tok, user


@pytest.fixture(scope="module")
def admin():
    if not ADMIN_PASSWORD:
        pytest.skip("TEST_ADMIN_PASSWORD not set")
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def admin2(admin):
    return _register(_login(ADMIN_EMAIL, ADMIN_PASSWORD)[0], "admin")


@pytest.fixture(scope="module")
def staff(admin):
    return _register(_login(ADMIN_EMAIL, ADMIN_PASSWORD)[0], "sales_executive")


# ── Sessions ──────────────────────────────────────────────────────────
def test_login_creates_visible_session(admin):
    r = requests.get(BASE + "/governance/sessions/me", headers=_h(admin[0]), timeout=30)
    assert r.status_code == 200, r.text
    assert any(s["current"] for s in r.json())


def test_logout_kills_the_token(admin):
    tok, _ = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert requests.post(BASE + "/governance/logout", headers=_h(tok), timeout=30).json()["ended"] is True
    assert requests.get(BASE + "/auth/me", headers=_h(tok), timeout=30).status_code == 401


# ── Feature registry ──────────────────────────────────────────────────
def test_unregistered_feature_is_denied(staff):
    r = requests.get(BASE + "/governance/features/check/does.not.exist", headers=_h(staff[0]), timeout=30)
    assert r.json()["allowed"] is False


def test_staff_cannot_open_registry(staff):
    assert requests.get(BASE + "/governance/features", headers=_h(staff[0]), timeout=30).status_code == 403


def test_kill_switch_blocks_and_restores(admin2, staff):
    k = "governance.access_requests"
    r = requests.post(BASE + f"/governance/features/{k}/kill", headers=_h(admin2[0]), json={"reason": "incident test"}, timeout=30)
    assert r.status_code == 200, r.text
    try:
        r = requests.post(BASE + "/governance/access-requests", headers=_h(staff[0]), timeout=30,
                          json={"feature_key": "revenue.refunds", "reason": "kill switch test request"})
        assert r.status_code == 403
    finally:
        requests.post(BASE + f"/governance/features/{k}/unkill", headers=_h(admin2[0]), timeout=30)


# ── Access requests, maker-checker, grants ────────────────────────────
def test_request_approve_grant_flow(admin, admin2, staff):
    key = "revenue.refunds"   # accounts, risk "high" -> manager + owner steps
    assert requests.get(BASE + f"/governance/features/check/{key}", headers=_h(staff[0]), timeout=30).json()["allowed"] is False
    r = requests.post(BASE + "/governance/access-requests", headers=_h(staff[0]), timeout=30,
                      json={"feature_key": key, "reason": "Covering refunds desk during leave", "days": 30})
    assert r.status_code == 200, r.text
    req = r.json()
    assert req["steps"] == ["manager", "owner"]

    # requester cannot approve their own request
    assert requests.post(BASE + f"/governance/access-requests/{req['id']}/approve", headers=_h(staff[0]),
                         json={}, timeout=30).status_code == 403
    # step 1 by admin2
    assert requests.post(BASE + f"/governance/access-requests/{req['id']}/approve", headers=_h(admin2[0]),
                         json={"comment": "ok"}, timeout=30).status_code == 200
    # admin2 cannot also approve step 2 (maker-checker)
    r = requests.post(BASE + f"/governance/access-requests/{req['id']}/approve", headers=_h(admin2[0]), json={}, timeout=30)
    assert r.status_code == 403 and "already approved" in r.text
    # step 2 by the other admin
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)[0]
    r = requests.post(BASE + f"/governance/access-requests/{req['id']}/approve", headers=_h(tok), json={}, timeout=30)
    assert r.status_code == 200, r.text
    grant = r.json()["grant"]
    assert requests.get(BASE + f"/governance/features/check/{key}", headers=_h(staff[0]), timeout=30).json()["allowed"] is True

    # revoke -> access gone
    assert requests.post(BASE + f"/governance/grants/{grant['id']}/revoke", headers=_h(tok),
                         json={"reason": "test revoke"}, timeout=30).status_code == 200
    assert requests.get(BASE + f"/governance/features/check/{key}", headers=_h(staff[0]), timeout=30).json()["allowed"] is False


def _grant(staff, key, approvers):
    r = requests.post(BASE + "/governance/access-requests", headers=_h(staff[0]), timeout=30,
                      json={"feature_key": key, "reason": "SoD test - needs both powers", "days": 5})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    last = None
    for tok in approvers:
        last = requests.post(BASE + f"/governance/access-requests/{rid}/approve", headers=_h(tok), json={}, timeout=30)
    return rid, last


def test_sod_conflict_blocks_final_approval(admin, admin2, staff):
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)[0]
    _, r = _grant(staff, "commission.slabs_manager", [admin2[0], tok])
    assert r.status_code == 200, r.text
    rid, r = _grant(staff, "commission.payouts_queue", [admin2[0], tok])
    if admin[1].get("rbac_role") == "admin_owner":
        assert r.status_code == 409   # owner without a reason is still blocked
        r = requests.post(BASE + f"/governance/access-requests/{rid}/approve", headers=_h(tok), timeout=30,
                          json={"sod_override_reason": "MD approved for month-end only"})
        assert r.status_code == 200
    else:
        assert r.status_code == 409 and "sod_conflict" in r.text


# ── Leaver ────────────────────────────────────────────────────────────
def test_deactivated_user_is_locked_out_immediately(admin2):
    tok, user = _register(admin2[0], "sales_executive")
    assert requests.get(BASE + "/auth/me", headers=_h(tok), timeout=30).status_code == 200
    r = requests.post(BASE + f"/people/{user['id']}/deactivate", headers=_h(admin2[0]), timeout=30)
    assert r.status_code == 200, r.text
    assert requests.get(BASE + "/auth/me", headers=_h(tok), timeout=30).status_code == 401
    ev = requests.get(BASE + "/governance/audit/events", params={"target_id": user["id"], "action": "user.offboarded"},
                      headers=_h(admin2[0]), timeout=30).json()
    assert ev and ev[0]["meta"]["sessions_revoked"] >= 1


# ── Statutory + audit chain ───────────────────────────────────────────
def test_pf_ceiling_is_effective_dated(admin2):
    get = lambda d: requests.get(BASE + "/governance/statutory/effective", params={"date": d},  # noqa: E731
                                 headers=_h(admin2[0]), timeout=30).json()["rules"]["pf.wage_ceiling_inr"]
    assert get("2026-09-16") == 15000
    assert get("2026-09-17") == 25000


def test_audit_chain_verifies(admin2):
    r = requests.get(BASE + "/governance/audit/verify", headers=_h(admin2[0]), timeout=30)
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert r.json()["checked"] > 0


# Runs last: it ends every other admin session.
def test_revoke_other_sessions_keeps_current(admin):
    other, _ = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    keep, _ = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    r = requests.post(BASE + "/governance/sessions/me/revoke-others", headers=_h(keep), timeout=30)
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    assert requests.get(BASE + "/auth/me", headers=_h(other), timeout=30).status_code == 401
    assert requests.get(BASE + "/auth/me", headers=_h(keep), timeout=30).status_code == 200
    # NOTE: this also ends the module-level admin token; later tests log in again.
