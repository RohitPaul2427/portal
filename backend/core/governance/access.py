"""E05-E07 - Time-bound access grants, access requests, separation of duties.

Effective access to a registered feature =
    (capability packs + overrides   - existing RBAC v2, unchanged)
  + active, unexpired permission_grants rows       (this module)
  - rollout stage / kill switch                     (feature_registry)

Access requests route through approval steps that depend on the feature's
risk level. Nobody can approve their own request, a request for themselves,
or two steps of the same request (maker-checker). Separation-of-duties rules
block grants that would put two conflicting powers in one person's hands
unless the owner (MD) records an explicit override reason.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import Depends, HTTPException

from core.auth import get_current_user
from core.database import db, users_col
from core.governance import audit_chain, feature_registry
from core.rbac.capability_service import CapabilityService

grants_col = db["permission_grants"]
requests_col = db["access_requests"]
sod_col = db["sod_rules"]

ADMIN_ROLES = {"admin_owner", "admin"}
OWNER_ROLES = {"admin_owner"}
EXTERNAL_ROLES = {"client", "partner", "vendor"}

# Approval chain per risk level.
STEPS_BY_RISK = {
    "low": ["manager"],
    "medium": ["manager"],
    "high": ["manager", "owner"],
    "critical": ["manager", "owner", "security"],
}
# Longest grant allowed per risk level (days). Critical access is just-in-time.
MAX_DAYS_BY_RISK = {"low": 365, "medium": 180, "high": 90, "critical": 7}

DEFAULT_SOD_RULES: List[Dict[str, Any]] = [
    {"id": "sod-commission-slab-vs-payout", "name": "Set commission slabs vs release payouts",
     "side_a": ["commission.slabs_manager"], "side_b": ["commission.payouts_queue"],
     "why": "The person who sets commission rates must not also release the payouts."},
    {"id": "sod-vendor-vs-payout", "name": "Create vendors vs release payouts",
     "side_a": ["accounts.vendors_manager"], "side_b": ["commission.payouts_queue"],
     "why": "Classic fake-vendor fraud control."},
    {"id": "sod-salary-vs-payroll", "name": "Edit salary structures vs approve payroll",
     "side_a": ["hr.salary_structures"], "side_b": ["hr.payroll_admin"],
     "why": "Salary changes must be checked by someone who did not make them."},
    {"id": "sod-statutory-vs-payroll", "name": "Change statutory rates vs run payroll",
     "side_a": ["governance.statutory_settings"], "side_b": ["hr.payroll_admin"],
     "why": "PF/ESI/PT rate changes must be independent of payroll processing."},
    {"id": "sod-access-admin-vs-approver", "name": "Manage RBAC packs vs approve access requests",
     "side_a": ["admin.rbac_packs_management"], "side_b": ["governance.access_approvals"],
     "why": "The person who edits permission packs must not also approve access."},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def role_of(user: dict) -> str:
    return user.get("rbac_role") or user.get("role") or ""


def is_admin(user: dict) -> bool:
    return role_of(user) in ADMIN_ROLES or user.get("role") == "admin"


def is_owner(user: dict) -> bool:
    return role_of(user) in OWNER_ROLES


def is_internal(user: dict) -> bool:
    return (user.get("user_type") or "internal") == "internal" and user.get("role") not in EXTERNAL_ROLES


def security_roles() -> Set[str]:
    return {r.strip() for r in os.environ.get("SECURITY_APPROVER_ROLES", "admin_owner,it_admin").split(",") if r.strip()}


# ───────────────────────── indexes / seed ─────────────────────────

async def ensure_indexes() -> None:
    await grants_col.create_index("id", unique=True)
    await grants_col.create_index([("user_id", 1), ("feature_key", 1), ("status", 1)])
    await grants_col.create_index([("status", 1), ("valid_to", 1)])
    await requests_col.create_index("id", unique=True)
    await requests_col.create_index([("status", 1), ("created_at", -1)])
    await requests_col.create_index([("target_user_id", 1), ("status", 1)])
    await sod_col.create_index("id", unique=True)


async def seed_sod_rules() -> int:
    n = 0
    for r in DEFAULT_SOD_RULES:
        res = await sod_col.update_one({"id": r["id"]}, {"$setOnInsert": {**r, "active": True, "created_at": _now()}}, upsert=True)
        n += 1 if res.upserted_id else 0
    return n


# ───────────────────────── effective access ─────────────────────────

async def active_grant_keys(user_id: str) -> Set[str]:
    now = _now()
    rows = await grants_col.find(
        {"user_id": user_id, "status": "active", "valid_from": {"$lte": now}, "valid_to": {"$gt": now}},
        {"_id": 0, "feature_key": 1},
    ).to_list(1000)
    return {r["feature_key"] for r in rows}


async def effective_feature_keys(user: dict) -> Set[str]:
    """Packs/overrides (RBAC v2) + live time-bound grants."""
    return set(CapabilityService.compute_effective_features(user)) | await active_grant_keys(user["id"])


SELF_SERVICE_FEATURES = {"governance.my_sessions", "governance.access_requests"}


async def check_feature(user: dict, key: str) -> Optional[str]:
    """None if allowed, otherwise the reason it was denied."""
    f = await feature_registry.get_feature(key)
    if not f:
        return f"Feature '{key}' is not registered"
    if f.get("killed") and not is_owner(user):
        return f"Feature '{key}' is temporarily switched off"
    if f.get("stage") == "retired":
        return f"Feature '{key}' has been retired"
    if is_admin(user):
        return None
    if not feature_registry.stage_allows(f, user):
        return f"Feature '{key}' is not yet released to you"
    if key in SELF_SERVICE_FEATURES and is_internal(user):
        return None
    if key in await effective_feature_keys(user):
        return None
    return f"You do not have access to '{key}'. Raise an access request."


def require_feature(key: str):
    """FastAPI dependency: deny-by-default feature gate."""
    async def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        reason = await check_feature(current_user, key)
        if reason:
            raise HTTPException(status_code=403, detail={"error": "feature_denied", "feature": key, "message": reason})
        return current_user
    return _dep


# ───────────────────────── separation of duties ─────────────────────────

def sod_conflicts(held: Iterable[str], new_key: str, rules: List[dict]) -> List[dict]:
    """Rules that become violated if a user holding `held` also gets `new_key`."""
    held = set(held)
    out = []
    for r in rules:
        if not r.get("active", True):
            continue
        a, b = set(r.get("side_a") or []), set(r.get("side_b") or [])
        if (new_key in a and held & b) or (new_key in b and held & a):
            out.append({"id": r["id"], "name": r["name"], "why": r.get("why")})
    return out


def sod_violations_for(held: Iterable[str], rules: List[dict]) -> List[dict]:
    held = set(held)
    return [{"id": r["id"], "name": r["name"]} for r in rules
            if r.get("active", True) and held & set(r.get("side_a") or []) and held & set(r.get("side_b") or [])]


async def active_sod_rules() -> List[dict]:
    return await sod_col.find({"active": True}, {"_id": 0}).to_list(500)


# ───────────────────────── approval routing ─────────────────────────

async def can_approve_step(approver: dict, step: str, req: dict, feature: dict, target: Optional[dict]) -> Optional[str]:
    """None if `approver` may decide `step` of `req`, else the reason."""
    if approver["id"] in (req["requester_id"], req["target_user_id"]):
        return "You cannot approve a request you raised or that is for you"
    if any(a.get("approver_id") == approver["id"] for a in req.get("approvals", [])):
        return "You already approved an earlier step of this request"
    if step == "manager":
        mgr = (target or {}).get("reports_to") or (target or {}).get("manager_id")
        if approver["id"] == mgr or is_admin(approver):
            return None
        return "Only the employee's reporting manager (or an admin) can approve this step"
    if step == "owner":
        if approver["id"] in (feature.get("approvers") or []) or is_admin(approver):
            return None
        return "Only the feature owner (or an admin) can approve this step"
    if step == "security":
        if role_of(approver) in security_roles():
            return None
        return "Only the security approver can approve this step"
    return "Unknown approval step"


def clamp_valid_to(risk: str, valid_from: datetime, requested_days: Optional[int]) -> datetime:
    max_days = MAX_DAYS_BY_RISK.get(risk, 90)
    days = max(1, min(int(requested_days or max_days), max_days))
    return valid_from + timedelta(days=days)


async def create_request(requester: dict, *, feature_key: str, target_user_id: Optional[str],
                         days: Optional[int], reason: str, scope: str = "all") -> dict:
    f = await feature_registry.get_feature(feature_key)
    if not f:
        raise HTTPException(status_code=404, detail="Feature not registered")
    if f.get("stage") == "retired":
        raise HTTPException(status_code=400, detail="Feature is retired")
    target_id = target_user_id or requester["id"]
    target = await users_col.find_one({"id": target_id}, {"_id": 0, "password": 0, "hashed_password": 0})
    if not target or target.get("status") != "active":
        raise HTTPException(status_code=404, detail="Target user not found or inactive")
    if target_id != requester["id"] and not is_admin(requester) \
            and requester["id"] not in (target.get("reports_to"), target.get("manager_id")):
        raise HTTPException(status_code=403, detail="You can request access only for yourself or your direct reports")
    if len((reason or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Please give a business reason (at least 10 characters)")
    dup = await requests_col.find_one({"target_user_id": target_id, "feature_key": feature_key, "status": "pending"})
    if dup:
        raise HTTPException(status_code=409, detail="A pending request for this access already exists")
    risk = f.get("risk", "medium")
    now = _now()
    req = {
        "id": str(uuid.uuid4()),
        "feature_key": feature_key, "feature_name": f.get("name"), "risk": risk, "scope": scope,
        "requester_id": requester["id"], "requester_name": requester.get("name"),
        "target_user_id": target_id, "target_name": target.get("name"),
        "requested_days": min(int(days or MAX_DAYS_BY_RISK[risk]), MAX_DAYS_BY_RISK[risk]),
        "reason": reason.strip(),
        "steps": list(STEPS_BY_RISK.get(risk, ["manager", "owner"])),
        "current_step": 0, "approvals": [],
        "status": "pending", "created_at": now, "updated_at": now,
        "sod_conflicts": sod_conflicts(await effective_feature_keys(target), feature_key, await active_sod_rules()),
    }
    await requests_col.insert_one(dict(req))
    await audit_chain.log_event("access_request.created", actor=requester, target_type="access_request",
                                target_id=req["id"], after={"feature": feature_key, "for": target_id, "risk": risk})
    return req


async def decide_request(approver: dict, request_id: str, *, approve: bool, comment: str = "",
                         sod_override_reason: Optional[str] = None) -> dict:
    req = await requests_col.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {req['status']}")
    f = await feature_registry.get_feature(req["feature_key"]) or {}
    target = await users_col.find_one({"id": req["target_user_id"]}, {"_id": 0, "password": 0, "hashed_password": 0})
    step = req["steps"][req["current_step"]]
    why_not = await can_approve_step(approver, step, req, f, target)
    if why_not:
        raise HTTPException(status_code=403, detail=why_not)

    now = _now()
    entry = {"step": step, "approver_id": approver["id"], "approver_name": approver.get("name"),
             "decision": "approved" if approve else "rejected", "comment": comment, "at": now}
    if not approve:
        await requests_col.update_one({"id": request_id}, {"$push": {"approvals": entry},
                                                          "$set": {"status": "rejected", "updated_at": now}})
        await audit_chain.log_event("access_request.rejected", actor=approver, target_type="access_request",
                                    target_id=request_id, meta={"step": step, "comment": comment})
        return {**req, "status": "rejected"}

    is_last = req["current_step"] + 1 >= len(req["steps"])
    if is_last:
        # Re-check SoD at grant time - holdings may have changed since the request.
        conflicts = sod_conflicts(await effective_feature_keys(target or {"id": req["target_user_id"]}),
                                  req["feature_key"], await active_sod_rules())
        if conflicts:
            if not (is_owner(approver) and (sod_override_reason or "").strip()):
                raise HTTPException(status_code=409, detail={
                    "error": "sod_conflict", "conflicts": conflicts,
                    "message": "This grant breaks a separation-of-duties rule. Only the owner can override, with a reason."})
            entry["sod_override_reason"] = sod_override_reason.strip()
        grant = await _create_grant(req, approver, f.get("risk", "medium"))
        await requests_col.update_one({"id": request_id}, {"$push": {"approvals": entry}, "$set": {
            "status": "approved", "grant_id": grant["id"], "updated_at": now, "current_step": req["current_step"] + 1}})
        await audit_chain.log_event("access_request.approved", actor=approver, target_type="access_request",
                                    target_id=request_id, severity="warn" if conflicts else "info",
                                    meta={"grant_id": grant["id"], "sod_override": entry.get("sod_override_reason")})
        return {**req, "status": "approved", "grant": grant}

    await requests_col.update_one({"id": request_id}, {"$push": {"approvals": entry},
                                                      "$set": {"current_step": req["current_step"] + 1, "updated_at": now}})
    await audit_chain.log_event("access_request.step_approved", actor=approver, target_type="access_request",
                                target_id=request_id, meta={"step": step})
    return {**req, "current_step": req["current_step"] + 1, "next_step": req["steps"][req["current_step"] + 1]}


async def _create_grant(req: dict, approver: dict, risk: str) -> dict:
    now = _now()
    grant = {
        "id": str(uuid.uuid4()), "user_id": req["target_user_id"], "feature_key": req["feature_key"],
        "scope": req.get("scope", "all"), "valid_from": now,
        "valid_to": clamp_valid_to(risk, now, req.get("requested_days")),
        "status": "active", "request_id": req["id"], "reason": req.get("reason"),
        "requested_by": req["requester_id"], "approved_by": approver["id"], "created_at": now,
    }
    await grants_col.insert_one(dict(grant))
    await audit_chain.log_event("grant.created", actor=approver, target_type="user", target_id=grant["user_id"],
                                after={"feature": grant["feature_key"], "valid_to": grant["valid_to"], "grant_id": grant["id"]})
    return grant


async def revoke_grant(actor: dict, grant_id: str, reason: str) -> bool:
    g = await grants_col.find_one({"id": grant_id, "status": "active"}, {"_id": 0})
    if not g:
        return False
    await grants_col.update_one({"id": grant_id}, {"$set": {
        "status": "revoked", "revoked_at": _now(), "revoked_by": actor.get("id"), "revoke_reason": reason}})
    await audit_chain.log_event("grant.revoked", actor=actor, target_type="user", target_id=g["user_id"],
                                before={"feature": g["feature_key"], "grant_id": grant_id}, meta={"reason": reason})
    return True


async def expire_grants() -> int:
    """Scheduler job (every 15 min): flip past-due grants to 'expired'."""
    now = _now()
    expired = await grants_col.find({"status": "active", "valid_to": {"$lte": now}}, {"_id": 0}).to_list(5000)
    for g in expired:
        await grants_col.update_one({"id": g["id"], "status": "active"}, {"$set": {"status": "expired", "expired_at": now}})
        await audit_chain.log_event("grant.expired", actor_id="system", target_type="user", target_id=g["user_id"],
                                    before={"feature": g["feature_key"], "grant_id": g["id"]})
    return len(expired)


# ───────────────────────── leaver ─────────────────────────

async def offboard_user(user_id: str, actor: dict, reason: str = "deactivated") -> Dict[str, int]:
    """E07-02: everything a leaver can use stops working at once."""
    from core.governance import sessions
    now = _now()
    g = await grants_col.update_many({"user_id": user_id, "status": "active"}, {"$set": {
        "status": "revoked", "revoked_at": now, "revoked_by": actor.get("id"), "revoke_reason": reason}})
    r = await requests_col.update_many({"target_user_id": user_id, "status": "pending"},
                                       {"$set": {"status": "cancelled", "updated_at": now, "cancel_reason": reason}})
    s = await sessions.revoke_user_sessions(user_id, reason)
    summary = {"grants_revoked": g.modified_count, "requests_cancelled": r.modified_count, "sessions_revoked": s}
    await audit_chain.log_event("user.offboarded", actor=actor, target_type="user", target_id=user_id,
                                severity="critical", meta={**summary, "reason": reason})
    return summary
