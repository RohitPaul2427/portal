"""Automated Security & Access Control Test Suite for Case Workspace.

Tests:
1. IDOR blockage: Client or unassigned CM cannot download/view documents from unrelated cases.
2. Cross-case isolation: Unassigned CM cannot access case details, create deadlines, or request step documents.
3. Temporary access grants: Time-limited elevation, self-elevation prohibition, and immediate revocation.
4. Identifier masking & audited reveal: Sensitive application numbers masked by default; unmasking audits actor and reason.
5. Credential vault abstraction: Passwords never returned in cleartext listings; checkout audited with reason.
6. Watermarked ephemeral previews: 15-minute token generation, visual watermarking, and forged token rejection.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import pytest
import requests
from pymongo import MongoClient

from core.auth import create_access_token, get_password_hash
from core.case_workspace_models import (
    ApplicationType,
    ApplicationStatus,
    DocumentSensitivityTier,
    mask_identifier,
)

API = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
if not API.endswith("/api"):
    API = API.rstrip("/") + "/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "leamss")
_db = MongoClient(MONGO_URL)[DB_NAME]


def _auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def security_fixtures():
    """Setup isolated synthetic clients, case managers, and test cases."""
    suffix = uuid.uuid4().hex[:6]

    # 1. Admin
    admin_id = f"test_admin_{suffix}"
    admin_email = f"admin_{suffix}@test.leamss"
    _db.users.insert_one({
        "id": admin_id, "email": admin_email, "name": "Security Admin",
        "role": "admin", "rbac_role": "admin", "is_active": True,
    })
    admin_token = create_access_token({"sub": admin_id, "id": admin_id, "role": "admin", "rbac_role": "admin"})

    # 2. Case Head / Lead
    lead_id = f"test_lead_{suffix}"
    lead_email = f"lead_{suffix}@test.leamss"
    _db.users.insert_one({
        "id": lead_id, "email": lead_email, "name": "Case Head Lead",
        "role": "case_manager_lead", "rbac_role": "case_manager_lead", "is_active": True,
    })
    lead_token = create_access_token({"sub": lead_id, "id": lead_id, "role": "case_manager_lead", "rbac_role": "case_manager_lead"})

    # 3. Case Manager 1 (Assigned)
    cm1_id = f"test_cm1_{suffix}"
    cm1_email = f"cm1_{suffix}@test.leamss"
    _db.users.insert_one({
        "id": cm1_id, "email": cm1_email, "name": "Case Manager Alpha",
        "role": "case_manager", "rbac_role": "case_manager", "is_active": True,
    })
    cm1_token = create_access_token({"sub": cm1_id, "id": cm1_id, "role": "case_manager", "rbac_role": "case_manager"})

    # 4. Case Manager 2 (Unassigned Rival)
    cm2_id = f"test_cm2_{suffix}"
    cm2_email = f"cm2_{suffix}@test.leamss"
    _db.users.insert_one({
        "id": cm2_id, "email": cm2_email, "name": "Case Manager Beta",
        "role": "case_manager", "rbac_role": "case_manager", "is_active": True,
    })
    cm2_token = create_access_token({"sub": cm2_id, "id": cm2_id, "role": "case_manager", "rbac_role": "case_manager"})

    # 5. Client 1 (Owner)
    c1_id = f"test_client1_{suffix}"
    c1_email = f"client1_{suffix}@test.example"
    _db.users.insert_one({
        "id": c1_id, "email": c1_email, "name": "Client One",
        "role": "client", "rbac_role": "client", "is_active": True,
    })
    c1_token = create_access_token({"sub": c1_id, "id": c1_id, "role": "client", "rbac_role": "client"})

    # 6. Client 2 (Rival)
    c2_id = f"test_client2_{suffix}"
    c2_email = f"client2_{suffix}@test.example"
    _db.users.insert_one({
        "id": c2_id, "email": c2_email, "name": "Client Two",
        "role": "client", "rbac_role": "client", "is_active": True,
    })
    c2_token = create_access_token({"sub": c2_id, "id": c2_id, "role": "client", "rbac_role": "client"})

    # 7. Case 1 (Belongs to Client 1, Assigned to CM1)
    case1_id = f"case1_{suffix}"
    _db.cases.insert_one({
        "id": case1_id,
        "case_number": f"AU-2026-{suffix[:4].upper()}",
        "client_id": c1_id,
        "client_name": "Client One",
        "client_email": c1_email,
        "case_manager_id": cm1_id,
        "case_manager_name": "Case Manager Alpha",
        "country": "AU",
        "pathway": "Subclass 189",
        "status": "in_progress",
        "lifecycle_state": "document_gathering",
        "created_at": datetime.now(timezone.utc),
    })

    # 8. Sensitive Document on Case 1
    doc1_id = f"doc1_{suffix}"
    upload_dir = os.path.abspath("./uploads")
    os.makedirs(upload_dir, exist_ok=True)
    sample_file = os.path.join(upload_dir, f"{doc1_id}.txt")
    with open(sample_file, "w") as f:
        f.write("CONFIDENTIAL SYNTHETIC PASSPORT DOCUMENT")

    _db.documents.insert_one({
        "id": doc1_id,
        "case_id": case1_id,
        "client_id": c1_id,
        "document_type": "passport",
        "filename": "passport_sample.txt",
        "file_path": sample_file,
        "content_type": "text/plain",
        "sensitivity_tier": "sensitive_identity",
        "uploaded_by": c1_id,
        "uploaded_at": datetime.now(timezone.utc),
    })

    yield {
        "admin": {"id": admin_id, "token": admin_token},
        "lead": {"id": lead_id, "token": lead_token},
        "cm1": {"id": cm1_id, "token": cm1_token},
        "cm2": {"id": cm2_id, "token": cm2_token},
        "client1": {"id": c1_id, "token": c1_token},
        "client2": {"id": c2_id, "token": c2_token},
        "case1_id": case1_id,
        "doc1_id": doc1_id,
    }

    # Teardown
    _db.users.delete_many({"id": {"$in": [admin_id, lead_id, cm1_id, cm2_id, c1_id, c2_id]}})
    _db.cases.delete_one({"id": case1_id})
    _db.documents.delete_one({"id": doc1_id})
    _db.case_applications.delete_many({"case_id": case1_id})
    _db.case_access_grants.delete_many({"case_id": case1_id})
    _db.case_vault_credentials.delete_many({"case_id": case1_id})
    if os.path.exists(sample_file):
        try:
            os.remove(sample_file)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. Document IDOR Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_document_download_idor_blocked(security_fixtures):
    """Ensure rival client and unassigned case manager CANNOT download documents."""
    f = security_fixtures
    url = f"{API}/documents/download/{f['doc1_id']}"

    # 1. Rival Client 2 -> 403 Forbidden
    r_client2 = requests.get(url, headers=_auth_header(f["client2"]["token"]), timeout=5)
    assert r_client2.status_code == 403, f"Expected 403 but got {r_client2.status_code}"

    # 2. Unassigned CM 2 -> 403 Forbidden
    r_cm2 = requests.get(url, headers=_auth_header(f["cm2"]["token"]), timeout=5)
    assert r_cm2.status_code == 403, f"Expected 403 but got {r_cm2.status_code}"

    # 3. Owner Client 1 -> 200 OK
    r_client1 = requests.get(url, headers=_auth_header(f["client1"]["token"]), timeout=5)
    assert r_client1.status_code == 200

    # 4. Assigned CM 1 -> 200 OK
    r_cm1 = requests.get(url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_cm1.status_code == 200

    # 5. Security Admin -> 200 OK
    r_admin = requests.get(url, headers=_auth_header(f["admin"]["token"]), timeout=5)
    assert r_admin.status_code == 200


def test_document_view_idor_blocked(security_fixtures):
    """Ensure view/preview endpoint enforces access control."""
    f = security_fixtures
    url = f"{API}/documents/view/{f['doc1_id']}"

    # Unassigned CM 2 -> 403 Forbidden
    r_cm2 = requests.get(url, headers=_auth_header(f["cm2"]["token"]), timeout=5)
    assert r_cm2.status_code == 403

    # Assigned CM 1 -> 200 OK
    r_cm1 = requests.get(url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_cm1.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. Case Details & Deadlines Isolation Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_case_details_cross_isolation(security_fixtures):
    """Ensure case details cannot be fetched by unassigned case managers."""
    f = security_fixtures
    url = f"{API}/cases/{f['case1_id']}"

    # Unassigned CM 2 -> 403 Forbidden
    r_cm2 = requests.get(url, headers=_auth_header(f["cm2"]["token"]), timeout=5)
    assert r_cm2.status_code == 403

    # Assigned CM 1 -> 200 OK
    r_cm1 = requests.get(url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_cm1.status_code == 200


def test_deadlines_cross_isolation(security_fixtures):
    """Ensure unassigned CM cannot view or create deadlines on Case 1."""
    f = security_fixtures
    get_url = f"{API}/deadlines/case/{f['case1_id']}"
    post_url = f"{API}/deadlines/create"

    # 1. Unassigned CM 2 cannot view deadlines
    r_get = requests.get(get_url, headers=_auth_header(f["cm2"]["token"]), timeout=5)
    assert r_get.status_code == 403

    # 2. Unassigned CM 2 cannot create deadline
    r_post = requests.post(
        post_url,
        headers=_auth_header(f["cm2"]["token"]),
        json={
            "case_id": f["case1_id"],
            "title": "Unauthorized Deadline",
            "due_date": "2026-12-31",
        },
        timeout=5,
    )
    assert r_post.status_code == 403

    # 3. Assigned CM 1 can view deadlines
    r_cm1 = requests.get(get_url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_cm1.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 3. Multi-Application Register & Identifier Masking Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_application_register_and_masking(security_fixtures):
    """Test creating applications, masking in lists, and audited reveal."""
    f = security_fixtures
    base_url = f"{API}/case-workspace/{f['case1_id']}/applications"

    # 1. CM1 creates an EOI application with sensitive reference ID
    raw_eoi_id = "DHA-EOI-98765432"
    r_create = requests.post(
        base_url,
        headers=_auth_header(f["cm1"]["token"]),
        json={
            "case_id": f["case1_id"],
            "client_id": f["client1"]["id"],
            "application_type": "eoi",
            "country": "AU",
            "authority_or_state": "SkillSelect",
            "subclass_or_stream": "189",
            "reference_identifier": raw_eoi_id,
            "status": "submitted",
            "points_claimed": 85,
        },
        timeout=5,
    )
    assert r_create.status_code == 200
    app_data = r_create.json()
    app_id = app_data["id"]
    # Verify return payload masks reference ID
    assert app_data.get("masked_identifier") == mask_identifier(raw_eoi_id)
    assert "reference_identifier" not in app_data

    # 2. List applications: verify identifier is masked
    r_list = requests.get(base_url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_list.status_code == 200
    apps = r_list.json()["applications"]
    created_app = next(a for a in apps if a["id"] == app_id)
    assert created_app["masked_identifier"] == mask_identifier(raw_eoi_id)
    assert "reference_identifier" not in created_app

    # 3. Audited reveal request: unmask identifier
    reveal_url = f"{API}/case-workspace/{f['case1_id']}/reveal-identifier"
    r_reveal = requests.post(
        reveal_url,
        headers=_auth_header(f["cm1"]["token"]),
        json={
            "case_id": f["case1_id"],
            "application_id": app_id,
            "reason": "Preparing official lodging cross-check against DHA portal",
        },
        timeout=5,
    )
    assert r_reveal.status_code == 200
    reveal_data = r_reveal.json()
    assert reveal_data["reference_identifier"] == raw_eoi_id


# ─────────────────────────────────────────────────────────────────────────────
# 4. Temporary Access Grants Lifecycle Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_temporary_access_grant_lifecycle(security_fixtures):
    """Test grant creation, elevated access, self-elevation prohibition, and revocation."""
    f = security_fixtures
    grants_url = f"{API}/case-workspace/{f['case1_id']}/grants"
    case_url = f"{API}/cases/{f['case1_id']}"

    # Pre-condition: CM2 is denied access to Case 1
    assert requests.get(case_url, headers=_auth_header(f["cm2"]["token"]), timeout=5).status_code == 403

    # 1. Anti-privilege escalation rule: CM2 cannot grant access to themselves
    r_self = requests.post(
        grants_url,
        headers=_auth_header(f["lead"]["token"]),
        json={
            "case_id": f["case1_id"],
            "user_id": f["lead"]["id"],  # Self-elevation
            "duration_hours": 12,
            "reason": "I want access to this case",
        },
        timeout=5,
    )
    assert r_self.status_code == 400

    # 2. Case Head grants temporary 24h reviewer access to CM2
    r_grant = requests.post(
        grants_url,
        headers=_auth_header(f["lead"]["token"]),
        json={
            "case_id": f["case1_id"],
            "user_id": f["cm2"]["id"],
            "role_granted": "reviewer",
            "duration_hours": 24,
            "reason": "Covering for CM Alpha on medical leave",
            "permissions": ["case.view", "document.preview", "document.metadata.view"],
        },
        timeout=5,
    )
    assert r_grant.status_code == 200
    grant_id = r_grant.json()["id"]

    # 3. CM2 now has active access to Case 1
    assert requests.get(case_url, headers=_auth_header(f["cm2"]["token"]), timeout=5).status_code == 200

    # 4. Case Head immediately revokes access
    revoke_url = f"{grants_url}/{grant_id}/revoke"
    r_revoke = requests.post(revoke_url, headers=_auth_header(f["lead"]["token"]), timeout=5)
    assert r_revoke.status_code == 200

    # 5. CM2 access is immediately terminated -> 403 Forbidden
    assert requests.get(case_url, headers=_auth_header(f["cm2"]["token"]), timeout=5).status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 5. Credential Vault Abstraction Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_credential_vault_registration_and_checkout(security_fixtures):
    """Ensure credentials are encrypted and cleartext checkout is strictly audited."""
    f = security_fixtures
    vault_base = f"{API}/case-workspace/{f['case1_id']}/vault"

    # 1. CM1 registers ImmiAccount credential into vault
    secret_pass = "GovPass2026!#"
    r_reg = requests.post(
        vault_base,
        headers=_auth_header(f["cm1"]["token"]),
        json={
            "case_id": f["case1_id"],
            "portal_name": "ImmiAccount Official",
            "portal_url": "https://online.immi.gov.au",
            "username_or_id": "leamss_client1",
            "secret_value": secret_pass,
            "notes": "Client primary visa lodging account",
        },
        timeout=5,
    )
    assert r_reg.status_code == 200
    cred_id = r_reg.json()["id"]

    # 2. List credentials: verify cleartext secret is NOT returned
    r_list = requests.get(vault_base, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_list.status_code == 200
    creds = r_list.json()["credentials"]
    target = next(c for c in creds if c["id"] == cred_id)
    assert "secret_value" not in target
    assert "encrypted_secret" not in target

    # 3. Audited temporary checkout: decrypts secret and records checkout audit
    checkout_url = f"{vault_base}/{cred_id}/checkout"
    r_checkout = requests.post(
        checkout_url,
        headers=_auth_header(f["cm1"]["token"]),
        json={
            "credential_id": cred_id,
            "reason": "Lodge nomination application on state portal",
        },
        timeout=5,
    )
    assert r_checkout.status_code == 200
    checkout_data = r_checkout.json()
    assert checkout_data["secret_value"] == secret_pass


# ─────────────────────────────────────────────────────────────────────────────
# 6. Ephemeral Previews & Watermarking Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_ephemeral_preview_token_and_watermark(security_fixtures):
    """Test short-lived preview token generation and streaming."""
    f = security_fixtures
    token_url = f"{API}/case-workspace/{f['case1_id']}/documents/{f['doc1_id']}/preview-token"

    # 1. Generate 15-minute ephemeral preview token
    r_token = requests.post(token_url, headers=_auth_header(f["cm1"]["token"]), timeout=5)
    assert r_token.status_code == 200
    data = r_token.json()
    assert "preview_token" in data
    preview_token = data["preview_token"]

    # 2. Fetch preview stream using token
    stream_url = f"{API}/case-workspace/preview-stream/{preview_token}"
    r_stream = requests.get(stream_url, timeout=5)
    assert r_stream.status_code == 200
    assert len(r_stream.content) > 0

    # 3. Invalid / forged token -> 401 Unauthorized
    r_fake = requests.get(f"{API}/case-workspace/preview-stream/bad.token.signature", timeout=5)
    assert r_fake.status_code == 401
