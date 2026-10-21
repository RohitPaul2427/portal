"""Case-Centred Workspace Router.

Unifies and secures case operations:
- Case workspace overview & lifecycle states
- Multi-application register (Skills Assessments, EOIs, State Nominations/ROIs, Visa Lodgements)
- Audited identifier unmasking (TRN, EOI ID, Passports)
- Granular temporary access grants with expiration and immediate revocation
- Credential vault integration (zero plaintext passwords)
- Secure, watermarked ephemeral document previews
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import Response

from core.auth import get_current_user
from core.database import db
from core.case_workspace_models import (
    ApplicationStatus,
    ApplicationType,
    CaseAccessGrantCreate,
    CaseApplicationCreate,
    CaseApplicationUpdate,
    CaseReassignRequest,
    CredentialAccessRequest,
    CredentialVaultRegister,
    IdentifierRevealRequest,
    SensitiveAccessRequestCreate,
    SensitiveAccessRequestDecision,
    WorkspaceLifecycleState,
    mask_identifier,
)
from core.case_access_service import (
    ADMIN_ROLES,
    CASE_HEAD_ROLES,
    CaseAccessService,
)
from core.vault_service import VaultService
from core.document_security import (
    classify_sensitivity,
    generate_ephemeral_preview_token,
    verify_ephemeral_preview_token,
    watermark_pdf_bytes,
    watermark_image_bytes,
)
from services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/case-workspace", tags=["Case Workspace"])

CASES_COL = "cases"
DOCS_COL = "documents"
APPS_COL = "case_applications"
GRANTS_COL = "case_access_grants"
REQUESTS_COL = "case_access_requests"
USERS_COL = "users"
NOTIFS_COL = "notifications"


# ─────────────────────────────────────────────────────────────────────────────
# 0. Admin System-Wide Governance & Access Overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/governance-summary")
async def get_admin_governance_summary(current_user: dict = Depends(get_current_user)):
    """System-wide Access & Governance Overview for Administrators."""
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    if role not in ADMIN_ROLES and role not in CASE_HEAD_ROLES:
        raise HTTPException(status_code=403, detail="Admin or Case Head access required")

    now = datetime.now(timezone.utc)
    in_24h = now + timedelta(hours=24)

    # 1. Pending Access Requests
    pending_cursor = db[REQUESTS_COL].find({"status": "pending"}).sort("created_at", -1).limit(50)
    pending_requests = []
    async for req in pending_cursor:
        for f in ("created_at", "decided_at", "expires_at"):
            if isinstance(req.get(f), datetime):
                req[f] = req[f].isoformat()
        req.pop("_id", None)
        pending_requests.append(req)

    # 2. Active Temporary Grants across all cases
    active_grants_cursor = db[GRANTS_COL].find({
        "revoked_at": None,
        "expires_at": {"$gt": now}
    }).sort("expires_at", 1).limit(100)
    active_grants = []
    expiring_soon_count = 0
    async for g in active_grants_cursor:
        if isinstance(g.get("expires_at"), datetime):
            if g["expires_at"] <= in_24h:
                expiring_soon_count += 1
            g["expires_at"] = g["expires_at"].isoformat()
        if isinstance(g.get("created_at"), datetime):
            g["created_at"] = g["created_at"].isoformat()
        g.pop("_id", None)
        active_grants.append(g)

    # 3. Unassigned Cases (needing primary Case Manager assignment)
    unassigned_count = await db[CASES_COL].count_documents({
        "$or": [
            {"case_manager_id": None},
            {"case_manager_id": ""},
            {"status": "pending_assignment"}
        ]
    })

    # 4. Recent Sensitive Actions from audit_logs
    recent_audit_cursor = db["audit_logs"].find({
        "action": {
            "$in": [
                "case_identifier.revealed",
                "vault.secret_checkout",
                "case_access.granted",
                "case_access.revoked",
                "case_manager.reassigned",
                "case_access_request.created",
                "case_access_request.decided"
            ]
        }
    }).sort("timestamp", -1).limit(40)
    recent_sensitive_actions = []
    async for a in recent_audit_cursor:
        if isinstance(a.get("timestamp"), datetime):
            a["timestamp"] = a["timestamp"].isoformat()
        a.pop("_id", None)
        recent_sensitive_actions.append(a)

    return {
        "pending_requests_count": len(pending_requests),
        "pending_requests": pending_requests,
        "active_grants_count": len(active_grants),
        "active_grants": active_grants,
        "expiring_grants_24h_count": expiring_soon_count,
        "unassigned_cases_count": unassigned_count,
        "recent_sensitive_actions": recent_sensitive_actions,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Workspace Overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/overview")
async def get_workspace_overview(case_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch consolidated case workspace details."""
    case = await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    
    # 1. Applications
    apps = []
    async for a in db[APPS_COL].find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1):
        if a.get("reference_identifier"):
            a["masked_identifier"] = mask_identifier(a["reference_identifier"])
            a["is_masked"] = True
            del a["reference_identifier"]
        apps.append(a)

    # 2. Document Summary
    doc_count = await db[DOCS_COL].count_documents({"case_id": case_id})
    sensitive_count = await db[DOCS_COL].count_documents({
        "case_id": case_id,
        "sensitivity_tier": {"$in": ["sensitive_identity", "highly_restricted"]}
    })

    # 3. Active Access Grants
    now = datetime.now(timezone.utc)
    grants = []
    async for g in db[GRANTS_COL].find({"case_id": case_id, "revoked_at": None, "expires_at": {"$gt": now}}, {"_id": 0}):
        if isinstance(g.get("expires_at"), datetime):
            g["expires_at"] = g["expires_at"].isoformat()
        grants.append(g)

    # 4. Vault Credentials count
    vault_creds = await VaultService.list_credentials_for_case(case_id)

    return {
        "case": {
            "id": case.get("id"),
            "case_number": case.get("case_number"),
            "client_name": case.get("client_name"),
            "client_email": case.get("client_email"),
            "country": case.get("country"),
            "pathway": case.get("pathway"),
            "status": case.get("status"),
            "lifecycle_state": case.get("lifecycle_state", WorkspaceLifecycleState.DOCUMENT_GATHERING),
            "case_manager_id": case.get("case_manager_id"),
            "case_manager_name": case.get("case_manager_name"),
            "secondary_case_managers": case.get("secondary_case_managers", []),
            "created_at": case.get("created_at"),
        },
        "applications": apps,
        "documents_summary": {
            "total": doc_count,
            "sensitive_identity": sensitive_count,
        },
        "active_grants": grants,
        "vault_credentials_count": len(vault_creds),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-Application Register (Skills Assessment, EOI, Nomination, Visa)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/applications")
async def list_case_applications(case_id: str, current_user: dict = Depends(get_current_user)):
    """List all registered applications for a case with identifiers masked by default."""
    await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    
    apps = []
    async for a in db[APPS_COL].find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1):
        if a.get("reference_identifier"):
            a["masked_identifier"] = mask_identifier(a["reference_identifier"])
            a["is_masked"] = True
            # Never send cleartext identifier in list response
            del a["reference_identifier"]
        apps.append(a)
    return {"case_id": case_id, "applications": apps, "total": len(apps)}


@router.post("/{case_id}/applications")
async def create_case_application(
    case_id: str,
    payload: CaseApplicationCreate,
    current_user: dict = Depends(get_current_user),
):
    """Register a new application (EOI, nomination, skills assessment, visa) on the case."""
    case = await CaseAccessService.verify_case_access(case_id, current_user, "case.update")
    
    app_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    doc = {
        "id": app_id,
        "case_id": case_id,
        "client_id": case.get("client_id") or payload.client_id,
        "application_type": payload.application_type.value,
        "country": payload.country,
        "authority_or_state": payload.authority_or_state,
        "subclass_or_stream": payload.subclass_or_stream,
        "applicant_type": payload.applicant_type,
        "applicant_name": payload.applicant_name or case.get("client_name"),
        "reference_identifier": payload.reference_identifier,
        "status": payload.status.value,
        "status_source": payload.status_source,
        "submission_date": payload.submission_date,
        "points_claimed": payload.points_claimed,
        "responsible_staff_id": payload.responsible_staff_id or current_user.get("id"),
        "next_action": payload.next_action,
        "deadline": payload.deadline,
        "notes": payload.notes,
        "created_by": current_user.get("id"),
        "created_at": now,
        "updated_at": now,
    }
    
    await db[APPS_COL].insert_one(doc)

    await log_action(
        db,
        action="case_application.created",
        user_id=current_user.get("id"),
        summary={
            "case_id": case_id,
            "application_id": app_id,
            "type": payload.application_type.value,
            "authority": payload.authority_or_state,
            "subclass": payload.subclass_or_stream,
        },
    )

    doc.pop("_id", None)
    if doc.get("reference_identifier"):
        doc["masked_identifier"] = mask_identifier(doc["reference_identifier"])
        doc["is_masked"] = True
        del doc["reference_identifier"]
    return doc


@router.put("/{case_id}/applications/{app_id}")
async def update_case_application(
    case_id: str,
    app_id: str,
    payload: CaseApplicationUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update application details or status."""
    await CaseAccessService.verify_case_access(case_id, current_user, "case.update")
    
    existing = await db[APPS_COL].find_one({"id": app_id, "case_id": case_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Application record not found")

    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    if "status" in updates and isinstance(updates["status"], ApplicationStatus):
        updates["status"] = updates["status"].value
    updates["updated_at"] = datetime.now(timezone.utc)

    await db[APPS_COL].update_one({"id": app_id}, {"$set": updates})

    await log_action(
        db,
        action="case_application.updated",
        user_id=current_user.get("id"),
        summary={"case_id": case_id, "application_id": app_id, "fields": list(updates.keys())},
    )

    updated = await db[APPS_COL].find_one({"id": app_id}, {"_id": 0})
    if updated and updated.get("reference_identifier"):
        updated["masked_identifier"] = mask_identifier(updated["reference_identifier"])
        updated["is_masked"] = True
        del updated["reference_identifier"]
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# 3. Audited Identifier Reveal
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{case_id}/reveal-identifier")
async def reveal_identifier(
    case_id: str,
    payload: IdentifierRevealRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Audited unmasking of a sensitive reference number."""
    await CaseAccessService.verify_case_access(case_id, current_user, "identifier.reveal")
    
    app_doc = await db[APPS_COL].find_one({"id": payload.application_id, "case_id": case_id})
    if not app_doc or not app_doc.get("reference_identifier"):
        raise HTTPException(status_code=404, detail="Application reference identifier not found")

    client_ip = request.client.host if request.client else "unknown"

    await log_action(
        db,
        action="case_identifier.revealed",
        user_id=current_user.get("id"),
        user_name=current_user.get("email"),
        summary={
            "case_id": case_id,
            "application_id": payload.application_id,
            "reason": payload.reason,
            "revealed_for": app_doc.get("application_type"),
        },
        severity="warn",
        ip=client_ip,
    )

    return {
        "application_id": payload.application_id,
        "reference_identifier": app_doc["reference_identifier"],
        "unmasked_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Granular Temporary Access Grants
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/grants")
async def list_case_grants(case_id: str, current_user: dict = Depends(get_current_user)):
    """List access grants for a case (Case Head, Admin, or Assigned CM)."""
    await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    
    grants = []
    async for g in db[GRANTS_COL].find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1):
        for f in ("created_at", "expires_at", "revoked_at"):
            if isinstance(g.get(f), datetime):
                g[f] = g[f].isoformat()
        grants.append(g)
    return {"case_id": case_id, "grants": grants}


@router.post("/{case_id}/grants")
async def create_access_grant(
    case_id: str,
    payload: CaseAccessGrantCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a temporary access grant for another staff member (Admin, Case Head, or assigned Case Manager)."""
    case = await db[CASES_COL].find_one({"id": case_id}, {"_id": 0, "id": 1, "case_number": 1, "case_manager_id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    is_admin = role in ADMIN_ROLES
    is_head = role in CASE_HEAD_ROLES
    is_case_manager = role in {"case_manager", "manager"}
    is_assigned = bool(case.get("case_manager_id") and str(case.get("case_manager_id")) == str(current_user.get("id")))

    if not is_admin and not is_head and not is_assigned and not is_case_manager:
        raise HTTPException(
            status_code=403,
            detail="Only Administrators, Case Heads, or Case Managers can grant temporary access"
        )

    # Resolve target user by ID or Email
    target_ident = str(payload.user_id).strip()
    target_user = await db["users"].find_one({
        "$or": [
            {"id": target_ident},
            {"email": target_ident.lower()}
        ]
    }, {"_id": 0, "id": 1, "email": 1, "name": 1})
    if not target_user:
        raise HTTPException(status_code=404, detail=f"Target user '{target_ident}' not found. Please enter a valid staff ID or email.")

    target_user_id = target_user["id"]

    # Anti-privilege escalation rule: Nobody may grant access to themselves
    if str(target_user_id) == str(current_user.get("id")):
        raise HTTPException(status_code=400, detail="Self-elevation prohibited: you cannot grant access to yourself")

    now = datetime.now(timezone.utc)
    duration = payload.duration_hours or payload.expires_in_hours or 24
    expires_at = now + timedelta(hours=duration)
    grant_id = str(uuid.uuid4())

    grant_doc = {
        "id": grant_id,
        "case_id": case_id,
        "user_id": target_user_id,
        "user_email": target_user.get("email"),
        "user_name": target_user.get("name"),
        "role_granted": payload.role_granted.value,
        "granted_by": current_user.get("id"),
        "granted_by_email": current_user.get("email"),
        "reason": payload.reason,
        "permissions": payload.permissions,
        "duration_hours": duration,
        "expires_at": expires_at,
        "revoked_at": None,
        "created_at": now,
    }

    await db[GRANTS_COL].insert_one(grant_doc)

    await log_action(
        db,
        action="case_access.granted",
        user_id=current_user.get("id"),
        user_name=current_user.get("email"),
        summary={
            "case_id": case_id,
            "grant_id": grant_id,
            "target_user_id": target_user_id,
            "target_user_email": target_user.get("email"),
            "duration_hours": payload.duration_hours,
            "reason": payload.reason,
            "permissions": payload.permissions,
        },
        severity="warn",
    )

    grant_doc.pop("_id", None)
    grant_doc["created_at"] = now.isoformat()
    grant_doc["expires_at"] = expires_at.isoformat()
    return grant_doc


@router.post("/{case_id}/grants/{grant_id}/revoke")
async def revoke_access_grant(
    case_id: str,
    grant_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Immediately revoke an active access grant."""
    case = await db[CASES_COL].find_one({"id": case_id}, {"_id": 0, "id": 1, "case_manager_id": 1})
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    is_admin = role in ADMIN_ROLES
    is_head = role in CASE_HEAD_ROLES
    is_case_manager = role in {"case_manager", "manager"}
    is_assigned = bool(case and case.get("case_manager_id") and str(case.get("case_manager_id")) == str(current_user.get("id")))

    if not is_admin and not is_head and not is_assigned and not is_case_manager:
        raise HTTPException(
            status_code=403,
            detail="Only Administrators, Case Heads, or Case Managers can revoke access"
        )

    grant = await db[GRANTS_COL].find_one({"id": grant_id, "case_id": case_id})
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    now = datetime.now(timezone.utc)
    await db[GRANTS_COL].update_one(
        {"id": grant_id},
        {"$set": {"revoked_at": now, "revoked_by": current_user.get("id")}},
    )

    await log_action(
        db,
        action="case_access.revoked",
        user_id=current_user.get("id"),
        summary={"case_id": case_id, "grant_id": grant_id, "target_user_id": grant.get("user_id")},
        severity="info",
    )

    return {"ok": True, "grant_id": grant_id, "revoked_at": now.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# 4b. People & Permissions Roster, Reassignment & Governance
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/people-and-permissions")
async def get_people_and_permissions(case_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch complete People & Permissions roster for this case:
    Permanent assigned case manager, supervising case heads, admins,
    active temporary grants with granular permissions, and recent access history.
    """
    case = await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    now = datetime.now(timezone.utc)

    # 1. Permanent Assigned Case Manager
    assigned_cm = None
    cm_id = case.get("case_manager_id")
    if cm_id:
        cm_doc = await db[USERS_COL].find_one({"id": str(cm_id)}, {"_id": 0, "id": 1, "name": 1, "email": 1, "mobile": 1, "role": 1})
        if cm_doc:
            assigned_cm = {
                "id": cm_doc.get("id"),
                "name": cm_doc.get("name") or case.get("case_manager_name") or "Assigned Manager",
                "email": cm_doc.get("email"),
                "mobile": cm_doc.get("mobile"),
                "role": "Primary Case Manager",
                "access_type": "Permanent Case Assignment",
                "permitted_actions": [
                    "case.view", "case.update", "document.preview", "document.upload",
                    "document.download", "identifier.reveal", "credential.access"
                ],
                "assigned_since": case.get("created_at") if isinstance(case.get("created_at"), str) else (case.get("created_at").isoformat() if case.get("created_at") else None)
            }
        else:
            assigned_cm = {
                "id": str(cm_id),
                "name": case.get("case_manager_name") or "Assigned Manager",
                "email": "—",
                "role": "Primary Case Manager",
                "access_type": "Permanent Case Assignment",
                "permitted_actions": ["case.view", "case.update", "document.preview", "document.upload"]
            }

    # 2. Case Heads / Department Supervisors
    case_heads = []
    async for h in db[USERS_COL].find(
        {"$or": [{"role": {"$in": list(CASE_HEAD_ROLES)}}, {"rbac_role": {"$in": list(CASE_HEAD_ROLES)}}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "rbac_role": 1}
    ):
        case_heads.append({
            "id": h["id"],
            "name": h.get("name"),
            "email": h.get("email"),
            "role": "Case Head / Operations Lead",
            "access_type": "Role-Based Supervision",
            "permitted_actions": ["case.view", "case.update", "document.preview", "access.grant", "access.revoke", "request.approve"]
        })

    # 3. Administrators
    administrators = []
    async for a in db[USERS_COL].find(
        {"$or": [{"role": "admin"}, {"rbac_role": {"$in": list(ADMIN_ROLES)}}]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).limit(10):
        administrators.append({
            "id": a["id"],
            "name": a.get("name"),
            "email": a.get("email"),
            "role": "System Administrator",
            "access_type": "Global Administrative Oversight",
            "permitted_actions": ["* (Master Control)"]
        })

    # 4. Active Temporary Grants
    active_grants = []
    async for g in db[GRANTS_COL].find({
        "case_id": case_id,
        "revoked_at": None,
        "expires_at": {"$gt": now}
    }, {"_id": 0}).sort("created_at", -1):
        for f in ("created_at", "expires_at"):
            if isinstance(g.get(f), datetime):
                g[f] = g[f].isoformat()
        g["status"] = "active"
        g["access_type"] = "Temporary Access Grant"
        active_grants.append(g)

    # 5. Historical Grants (revoked or expired)
    historical_grants = []
    async for hg in db[GRANTS_COL].find({
        "case_id": case_id,
        "$or": [
            {"revoked_at": {"$ne": None}},
            {"expires_at": {"$lte": now}}
        ]
    }, {"_id": 0}).sort("created_at", -1).limit(15):
        for f in ("created_at", "expires_at", "revoked_at"):
            if isinstance(hg.get(f), datetime):
                hg[f] = hg[f].isoformat()
        hg["status"] = "revoked" if hg.get("revoked_at") else "expired"
        historical_grants.append(hg)

    # 6. Access Audit History for this case
    access_history = []
    async for log in db["audit_logs"].find({
        "$or": [
            {"summary.case_id": case_id},
            {"case_id": case_id}
        ]
    }, {"_id": 0}).sort("timestamp", -1).limit(20):
        if isinstance(log.get("timestamp"), datetime):
            log["timestamp"] = log["timestamp"].isoformat()
        access_history.append(log)

    # 7. Caller's current authorization profile
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    caller_id = str(current_user.get("id"))
    is_admin = role in ADMIN_ROLES
    is_head = role in CASE_HEAD_ROLES
    is_assigned = bool(cm_id and str(cm_id) == caller_id)

    access_basis = "No Access"
    if is_admin:
        access_basis = "Role: System Administrator (Global Authority)"
    elif is_head:
        access_basis = "Role: Case Head (Supervisory Authority)"
    elif is_assigned:
        access_basis = "Permanent Case Assignment (Primary Case Manager)"
    else:
        for g in active_grants:
            if str(g.get("user_id")) == caller_id:
                access_basis = f"Temporary Grant: {g.get('role_granted')} (Expires: {g.get('expires_at')})"
                break

    caller_perms = {
        "user_id": caller_id,
        "email": current_user.get("email"),
        "role": role,
        "access_basis": access_basis,
        "is_admin": is_admin,
        "is_case_head": is_head,
        "is_assigned_cm": is_assigned,
        "can_reassign": is_admin or is_head,
        "can_grant_temporary": is_admin or is_head or is_assigned or role in {"case_manager", "manager"},
        "can_revoke_temporary": is_admin or is_head or is_assigned or role in {"case_manager", "manager"},
        "can_approve_requests": is_admin or is_head,
    }

    return {
        "case_id": case_id,
        "case_number": case.get("case_number", case_id),
        "assigned_case_manager": assigned_cm,
        "case_heads": case_heads,
        "administrators": administrators,
        "active_temporary_grants": active_grants,
        "historical_grants": historical_grants,
        "access_history": access_history,
        "caller_authorization": caller_perms,
    }


@router.post("/{case_id}/reassign-manager")
async def reassign_case_manager(
    case_id: str,
    payload: CaseReassignRequest,
    current_user: dict = Depends(get_current_user),
):
    """Reassign case manager (Admin or Case Head only).
    Reuses the canonical case assignment logic without creating duplicate fields.
    """
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    if role not in ADMIN_ROLES and role not in CASE_HEAD_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only Administrators or Case Heads can reassign the primary Case Manager"
        )

    case = await db[CASES_COL].find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    new_cm = await db[USERS_COL].find_one({"id": payload.new_case_manager_id, "role": "case_manager"}, {"_id": 0})
    if not new_cm:
        raise HTTPException(status_code=404, detail="Target case manager not found or not active")

    old_cm_id = case.get("case_manager_id")
    old_cm_name = case.get("case_manager_name") or "Unassigned"
    now = datetime.now(timezone.utc)

    # Canonical assignment update
    update_data = {
        "case_manager_id": new_cm["id"],
        "case_manager_name": new_cm["name"],
        "updated_at": now,
    }
    if case.get("status") == "pending_assignment":
        update_data["status"] = "active"

    await db[CASES_COL].update_one({"id": case_id}, {"$set": update_data})

    # Notify new case manager
    await db["notifications"].insert_one({
        "id": str(uuid.uuid4()),
        "user_id": new_cm["id"],
        "title": "Case Assigned to You",
        "message": f"You are now the primary Case Manager for case {case.get('case_number', case_id)}",
        "type": "case_assigned",
        "related_id": case_id,
        "read": False,
        "created_at": now,
    })

    # Log immutable audit event
    await log_action(
        db,
        action="case_manager.reassigned",
        user_id=current_user.get("id"),
        user_name=current_user.get("email"),
        summary={
            "case_id": case_id,
            "case_number": case.get("case_number", case_id),
            "previous_manager_id": old_cm_id,
            "previous_manager_name": old_cm_name,
            "new_manager_id": new_cm["id"],
            "new_manager_name": new_cm["name"],
            "reason": payload.reason or "Administrative reassignment",
        },
        severity="warn",
    )

    return {
        "ok": True,
        "case_id": case_id,
        "previous_manager_id": old_cm_id,
        "previous_manager_name": old_cm_name,
        "new_manager_id": new_cm["id"],
        "new_manager_name": new_cm["name"],
        "message": f"Case successfully reassigned from {old_cm_name} to {new_cm['name']}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4c. Sensitive Action Approval Workflow
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/access-requests")
async def list_access_requests(case_id: str, current_user: dict = Depends(get_current_user)):
    """List sensitive-action approval requests for this case."""
    await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    requests = []
    async for req in db[REQUESTS_COL].find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1):
        for f in ("created_at", "decided_at", "expires_at"):
            if isinstance(req.get(f), datetime):
                req[f] = req[f].isoformat()
        requests.append(req)
    return {"case_id": case_id, "requests": requests}


@router.post("/{case_id}/access-requests")
async def create_access_request(
    case_id: str,
    payload: SensitiveAccessRequestCreate,
    current_user: dict = Depends(get_current_user),
):
    """Submit an exceptional sensitive action request (e.g. identifier unmask or vault secret checkout)."""
    case = await db[CASES_COL].find_one({"id": case_id}, {"_id": 0, "id": 1, "case_number": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    now = datetime.now(timezone.utc)
    req_id = str(uuid.uuid4())

    doc = {
        "id": req_id,
        "case_id": case_id,
        "case_number": case.get("case_number", case_id),
        "requester_id": current_user.get("id"),
        "requester_email": current_user.get("email"),
        "requester_name": current_user.get("name") or current_user.get("email"),
        "action": payload.action,
        "resource_id": payload.resource_id,
        "resource_name": payload.resource_name or payload.resource_id,
        "reason": payload.reason,
        "requested_duration_hours": payload.requested_duration_hours,
        "status": "pending",
        "created_at": now,
        "decided_by": None,
        "decided_by_email": None,
        "decided_at": None,
        "decision_notes": None,
        "expires_at": None,
    }

    await db[REQUESTS_COL].insert_one(doc)

    await log_action(
        db,
        action="case_access_request.created",
        user_id=current_user.get("id"),
        user_name=current_user.get("email"),
        summary={
            "case_id": case_id,
            "request_id": req_id,
            "action": payload.action,
            "resource_id": payload.resource_id,
            "reason": payload.reason,
        },
        severity="info",
    )

    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()
    return doc


@router.post("/{case_id}/access-requests/{request_id}/decision")
async def decide_access_request(
    case_id: str,
    request_id: str,
    payload: SensitiveAccessRequestDecision,
    current_user: dict = Depends(get_current_user),
):
    """Approve or reject a sensitive action request (Admin or Case Head only).
    Anti-self-escalation: Requesters cannot approve their own requests.
    """
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    if role not in ADMIN_ROLES and role not in CASE_HEAD_ROLES:
        raise HTTPException(status_code=403, detail="Only Administrators or Case Heads can approve access requests")

    req_doc = await db[REQUESTS_COL].find_one({"id": request_id, "case_id": case_id})
    if not req_doc:
        raise HTTPException(status_code=404, detail="Access request not found")

    if req_doc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Request has already been {req_doc.get('status')}")

    # Anti-Self-Escalation Check
    if str(req_doc.get("requester_id")) == str(current_user.get("id")):
        raise HTTPException(
            status_code=403,
            detail="Self-approval prohibited: You cannot approve your own access elevation request"
        )

    now = datetime.now(timezone.utc)
    decision = payload.decision.lower()

    updates = {
        "status": decision,
        "decided_by": current_user.get("id"),
        "decided_by_email": current_user.get("email"),
        "decided_at": now,
        "decision_notes": payload.notes,
    }

    if decision == "approved":
        dur = req_doc.get("requested_duration_hours", 24)
        expires_at = now + timedelta(hours=dur)
        updates["expires_at"] = expires_at

        # Automatically issue corresponding granular temporary grant
        grant_id = str(uuid.uuid4())
        grant_doc = {
            "id": grant_id,
            "case_id": case_id,
            "user_id": req_doc["requester_id"],
            "user_email": req_doc.get("requester_email"),
            "user_name": req_doc.get("requester_name"),
            "role_granted": "reviewer",
            "granted_by": current_user.get("id"),
            "granted_by_email": current_user.get("email"),
            "reason": f"Approved request: {req_doc.get('reason')}",
            "permissions": [req_doc["action"]],
            "resource_scope": "specific",
            "resource_id": req_doc.get("resource_id"),
            "duration_hours": dur,
            "expires_at": expires_at,
            "revoked_at": None,
            "created_at": now,
        }
        await db[GRANTS_COL].insert_one(grant_doc)

    await db[REQUESTS_COL].update_one({"id": request_id}, {"$set": updates})

    await log_action(
        db,
        action="case_access_request.decided",
        user_id=current_user.get("id"),
        user_name=current_user.get("email"),
        summary={
            "case_id": case_id,
            "request_id": request_id,
            "decision": decision,
            "requester_id": req_doc.get("requester_id"),
            "action": req_doc.get("action"),
            "notes": payload.notes,
        },
        severity="warn" if decision == "approved" else "info",
    )

    return {"ok": True, "request_id": request_id, "decision": decision}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Credential Vault Workspace Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{case_id}/vault")
async def list_vault_credentials(case_id: str, current_user: dict = Depends(get_current_user)):
    """List credentials metadata for a case (cleartext secret is never included).
    Exposes non-secret governance metadata for auditing.
    """
    await CaseAccessService.verify_case_access(case_id, current_user, "case.view")
    creds = await VaultService.list_credentials_for_case(case_id)
    for c in creds:
        c["storage_security"] = "AES-256 GCM (Authenticated Encryption)"
        c["access_method"] = "Audited Justification Required"
        c["authorized_roles"] = ["Assigned Case Manager", "Case Head", "System Administrator"]
        c["requires_approval_for_reviewers"] = True
    return {"case_id": case_id, "credentials": creds, "total": len(creds)}


@router.post("/{case_id}/vault")
async def register_vault_credential(
    case_id: str,
    payload: CredentialVaultRegister,
    current_user: dict = Depends(get_current_user),
):
    """Register portal login credential (stored encrypted via Vault provider)."""
    await CaseAccessService.verify_case_access(case_id, current_user, "case.update")
    
    result = await VaultService.register_credential(
        case_id=case_id,
        portal_name=payload.portal_name,
        username_or_id=payload.username_or_id,
        secret_value=payload.secret_value,
        actor_id=current_user.get("id"),
        actor_email=current_user.get("email"),
        portal_url=payload.portal_url,
        notes=payload.notes,
    )
    return result


@router.post("/{case_id}/vault/{credential_id}/checkout")
async def checkout_credential_secret(
    case_id: str,
    credential_id: str,
    payload: CredentialAccessRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Audited temporary retrieval of credential secret."""
    await CaseAccessService.verify_case_access(case_id, current_user, "credential.access.request")
    
    client_ip = request.client.host if request.client else "unknown"
    try:
        result = await VaultService.checkout_credential_secret(
            credential_id=credential_id,
            actor_id=current_user.get("id"),
            actor_email=current_user.get("email") or "unknown",
            reason=payload.reason,
            ip=client_ip,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{case_id}/vault/checkout")
async def checkout_credential_secret_alias(
    case_id: str,
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Fallback checkout endpoint handling credential_id or vault_id in request body."""
    cred_id = payload.get("credential_id") or payload.get("vault_id")
    if not cred_id:
        raise HTTPException(status_code=400, detail="credential_id is required")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Operational justification reason is required")
    
    await CaseAccessService.verify_case_access(case_id, current_user, "credential.access.request")
    client_ip = request.client.host if request.client else "unknown"
    try:
        result = await VaultService.checkout_credential_secret(
            credential_id=cred_id,
            actor_id=current_user.get("id"),
            actor_email=current_user.get("email") or "unknown",
            reason=reason,
            ip=client_ip,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ─────────────────────────────────────────────────────────────────────────────
# 6. Secure Document Ephemeral Previews & Watermarking
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{case_id}/documents/{doc_id}/preview-token")
async def get_document_preview_token(
    case_id: str,
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate a short-lived (15 min) ephemeral token for watermarked preview."""
    await CaseAccessService.verify_case_access(case_id, current_user, "document.preview")
    
    token = generate_ephemeral_preview_token(
        doc_id=doc_id,
        user_id=current_user.get("id"),
        user_email=current_user.get("email") or "viewer",
        case_id=case_id,
        expires_minutes=15,
    )
    return {
        "preview_token": token,
        "expires_in_minutes": 15,
        "preview_url": f"/api/case-workspace/preview-stream/{token}",
    }


@router.get("/preview-stream/{token}")
async def stream_watermarked_preview(token: str, request: Request):
    """Serve watermarked preview stream using ephemeral preview token."""
    try:
        payload = verify_ephemeral_preview_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    doc_id = payload["doc_id"]
    case_id = payload.get("case_id")
    viewer_email = payload.get("email", "LEAMSS Staff")

    doc = await db[DOCS_COL].find_one({"id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.get("file_path") or doc.get("path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")

    mime = doc.get("mime_type") or "application/pdf"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    watermark_label = f"LEAMSS CONFIDENTIAL - {viewer_email} - {now_str}"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # Apply watermarking
    if "pdf" in mime.lower():
        watermarked_bytes = watermark_pdf_bytes(file_bytes, watermark_label)
        media_type = "application/pdf"
    elif any(img_t in mime.lower() for img_t in ("image", "png", "jpeg", "jpg")):
        watermarked_bytes = watermark_image_bytes(file_bytes, watermark_label, mime)
        media_type = mime
    else:
        # Non-renderable format: return raw bytes
        watermarked_bytes = file_bytes
        media_type = mime

    # Log preview audit event
    await log_action(
        db,
        action="document.preview_viewed",
        user_id=payload.get("sub"),
        user_name=viewer_email,
        summary={"doc_id": doc_id, "case_id": case_id, "file_name": doc.get("file_name")},
        ip=request.client.host if request.client else "unknown",
    )

    return Response(
        content=watermarked_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename=preview_{doc.get('file_name', 'document')}"},
    )
