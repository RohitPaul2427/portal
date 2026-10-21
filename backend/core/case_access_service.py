"""Central Case-Centred Authorization & Access Control Service.

Enforces deny-by-default access control across cases, documents,
applications, and credentials. Evaluates:
1. User identity and role
2. Case assignment (primary case_manager_id or secondary_case_managers)
3. Client self-ownership
4. Active, non-expired temporary access grants (case_access_grants)
5. Document sensitivity tier and permitted action
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException

from core.auth import get_current_user
from core.database import db

logger = logging.getLogger(__name__)

CASES_COL = "cases"
DOCS_COL = "documents"
GRANTS_COL = "case_access_grants"

ADMIN_ROLES = {"admin", "admin_owner", "super_admin"}
CASE_HEAD_ROLES = {"case_manager_lead", "operations_head", "case_head"}
SALES_ROLES = {"sales", "sales_executive", "sr_sales_executive", "sales_lead"}


class CaseAccessService:
    @staticmethod
    async def get_active_grant(case_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Check if user has an active, non-expired, non-revoked grant for this case."""
        now = datetime.now(timezone.utc)
        grant = await db[GRANTS_COL].find_one({
            "case_id": case_id,
            "user_id": user_id,
            "revoked_at": None,
            "expires_at": {"$gt": now},
        })
        return grant

    @staticmethod
    async def check_case_access(
        case: Dict[str, Any],
        user: Dict[str, Any],
        required_action: str = "case.view",
    ) -> bool:
        """Evaluate whether `user` is authorized to perform `required_action` on `case`."""
        if not user or not case:
            return False

        role = (user.get("rbac_role") or user.get("role") or "").lower()
        user_id = str(user.get("id") or "")
        case_id = str(case.get("id") or "")

        # 1. Admin Override (Always Audited)
        if role in ADMIN_ROLES or "*" in (user.get("permissions") or []):
            return True

        # 2. Case Head / Lead (Departmental supervision)
        if role in CASE_HEAD_ROLES:
            if required_action in ("case.view", "case.update", "document.preview", "document.metadata.view", "access.grant", "access.revoke", "identifier.reveal", "credential.access.request"):
                return True

        # 3. Client Self-Ownership
        client_id = str(case.get("client_id") or case.get("client_user_id") or "")
        if role == "client":
            if client_id == user_id:
                # Clients can view case, view their metadata, preview their docs, and upload docs
                return required_action in ("case.view", "document.metadata.view", "document.preview", "document.download", "document.upload")
            return False

        # 4. Sales Users: Explicitly DENIED access to identity docs and operational case management
        if role in SALES_ROLES:
            if required_action in ("case.view",) and case.get("created_by") == user_id:
                return True
            return False

        # 5. Assigned Primary Case Manager
        primary_cm = str(case.get("case_manager_id") or "")
        if primary_cm and primary_cm == user_id:
            # Lifecycle restriction: if archived, read-only
            if case.get("status") == "archived" and required_action in ("case.update", "document.upload", "document.delete"):
                return False
            return True

        # 6. Secondary Case Managers
        secondaries = [str(x) for x in (case.get("secondary_case_managers") or [])]
        if user_id in secondaries:
            if case.get("status") == "archived" and required_action in ("case.update", "document.upload", "document.delete"):
                return False
            return True

        # 7. Active Temporary Access Grant
        grant = await CaseAccessService.get_active_grant(case_id, user_id)
        if grant:
            granted_perms = grant.get("permissions", [])
            if required_action in granted_perms or "*" in granted_perms:
                return True

        # 8. Active Approved Sensitive Access Request
        now = datetime.now(timezone.utc)
        approved_req = await db["case_access_requests"].find_one({
            "case_id": case_id,
            "requester_id": user_id,
            "action": required_action,
            "status": "approved",
            "expires_at": {"$gt": now},
        })
        if approved_req:
            return True

        return False

    @staticmethod
    async def verify_case_access(
        case_id: str,
        user: Dict[str, Any],
        required_action: str = "case.view",
    ) -> Dict[str, Any]:
        """Fetch case and enforce access check. Raises HTTPException 403/404."""
        case = await db[CASES_COL].find_one({"id": case_id}, {"_id": 0})
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")

        has_access = await CaseAccessService.check_case_access(case, user, required_action)
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "case_access_denied",
                    "message": f"You are not authorized for action '{required_action}' on case {case.get('case_number', case_id)}",
                    "case_id": case_id,
                    "action": required_action,
                },
            )
        return case

    @staticmethod
    async def verify_document_access(
        doc_record: Dict[str, Any],
        user: Dict[str, Any],
        required_action: str = "document.preview",
    ) -> Dict[str, Any]:
        """Verify access to a specific document based on case ownership and sensitivity tier."""
        role = (user.get("rbac_role") or user.get("role") or "").lower()
        user_id = str(user.get("id") or "")

        # Admin override
        if role in ADMIN_ROLES or "*" in (user.get("permissions") or []):
            return doc_record

        # Check sensitivity tier
        sensitivity = doc_record.get("sensitivity_tier", "standard")
        if sensitivity == "highly_restricted" and role not in ADMIN_ROLES and role not in CASE_HEAD_ROLES:
            raise HTTPException(status_code=403, detail="Highly restricted document requires Case Head or Admin elevation")

        # Case-linked document check
        case_id = doc_record.get("case_id")
        if case_id:
            await CaseAccessService.verify_case_access(case_id, user, required_action)
            return doc_record

        # Standalone client document check
        client_id = str(doc_record.get("client_id") or doc_record.get("uploaded_by_id") or "")
        if role == "client" and client_id == user_id:
            return doc_record

        # If user uploaded the document
        if doc_record.get("uploaded_by") == user_id or doc_record.get("created_by") == user_id:
            return doc_record

        raise HTTPException(status_code=403, detail="Document access denied")


# ─────────────────────────────────────────────────────────────────────────────
# 3. FastAPI Dependency Builders
# ─────────────────────────────────────────────────────────────────────────────

def require_case_access(required_action: str = "case.view"):
    """FastAPI path dependency to ensure user has access to case_id."""
    async def dependency(case_id: str, current_user: dict = Depends(get_current_user)):
        case = await CaseAccessService.verify_case_access(case_id, current_user, required_action)
        return case
    return dependency
