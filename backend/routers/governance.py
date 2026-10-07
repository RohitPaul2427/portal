"""Backlog Phase 0-1 - Governance API (/api/governance/...).

Sessions        GET  /sessions/me · POST /sessions/me/revoke-others · POST /sessions/{sid}/revoke
                POST /logout · GET /sessions (admin)
Features        GET  /features · GET /features/me · GET /features/check/{key}
                PATCH /features/{key} · POST /features/{key}/kill · POST /features/{key}/unkill
Access          POST /access-requests · GET /access-requests/mine · GET /access-requests/inbox
                POST /access-requests/{id}/approve|reject|cancel
Grants          GET  /grants · POST /grants/{id}/revoke · POST /grants/expire-now
SoD             GET  /sod/rules · PUT /sod/rules/{id} · GET /sod/violations
Audit           GET  /audit/events · GET /audit/verify
Statutory       GET  /statutory · GET /statutory/effective · POST /statutory
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from core.auth import JWT_SECRET, get_current_user
from core.database import users_col
from core.governance import access, audit_chain, feature_registry, sessions, statutory
from core.governance.access import require_feature

router = APIRouter(prefix="/governance", tags=["Governance - access, sessions, audit, statutory"])
_bearer = HTTPBearer()


def _sid_from(credentials: HTTPAuthorizationCredentials) -> Optional[str]:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"]).get("sid")
    except jwt.PyJWTError:
        return None


def _iso(doc: Any) -> Any:
    if isinstance(doc, list):
        return [_iso(d) for d in doc]
    if isinstance(doc, dict):
        return {k: _iso(v) for k, v in doc.items() if k != "_id"}
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


# ═════════════════════════════ Sessions ═════════════════════════════

@router.get("/sessions/me")
async def my_sessions(credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                      user: dict = Depends(require_feature("governance.my_sessions"))):
    return await sessions.list_sessions(user["id"], limit=50, current_sid=_sid_from(credentials))


@router.post("/sessions/me/revoke-others")
async def revoke_other_sessions(credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                                user: dict = Depends(require_feature("governance.my_sessions"))):
    n = await sessions.revoke_user_sessions(user["id"], "user_revoked_others", except_sid=_sid_from(credentials))
    await audit_chain.log_event("session.revoke_others", actor=user, target_type="user", target_id=user["id"],
                                meta={"count": n})
    return {"revoked": n}


@router.post("/sessions/{sid}/revoke")
async def revoke_session(sid: str, user: dict = Depends(get_current_user)):
    s = await sessions.sessions_col.find_one({"id": sid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s["user_id"] != user["id"] and await access.check_feature(user, "governance.session_admin"):
        raise HTTPException(status_code=403, detail="You can only end your own sessions")
    ok = await sessions.end_session(sid, reason="revoked_by_" + ("self" if s["user_id"] == user["id"] else "admin"),
                                    status="revoked")
    await audit_chain.log_event("session.revoked", actor=user, target_type="user", target_id=s["user_id"],
                                meta={"sid": sid})
    return {"revoked": ok}


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(_bearer),
                 user: dict = Depends(get_current_user)):
    sid = _sid_from(credentials)
    ended = await sessions.end_session(sid, "logout") if sid else False
    await audit_chain.log_event("auth.logout", actor=user, target_type="user", target_id=user["id"])
    return {"ended": ended}


@router.get("/sessions")
async def all_sessions(user_id: Optional[str] = None, status: Optional[str] = Query(None, pattern="^(active|ended|revoked)$"),
                       limit: int = Query(200, le=1000),
                       _: dict = Depends(require_feature("governance.session_admin"))):
    return await sessions.list_sessions(user_id, status, limit)


# ═════════════════════════════ Features ═════════════════════════════

class FeatureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_dept: Optional[str] = None
    risk: Optional[str] = None
    stage: Optional[str] = None
    pilot_user_ids: Optional[List[str]] = None
    departments: Optional[List[str]] = None
    approvers: Optional[List[str]] = None


class KillRequest(BaseModel):
    reason: str = Field(..., min_length=5)


@router.get("/features")
async def list_features(_: dict = Depends(require_feature("governance.feature_registry"))):
    return _iso(await feature_registry.all_features())


@router.get("/features/requestable")
async def requestable_features(_: dict = Depends(require_feature("governance.access_requests"))):
    """Minimal list (key, name, risk) so staff can pick what to request."""
    return [{"key": f["key"], "name": f.get("name"), "risk": f.get("risk"), "owner_dept": f.get("owner_dept"),
             "stage": f.get("stage")}
            for f in await feature_registry.all_features() if f.get("stage") != "retired" and not f.get("killed")]


@router.get("/features/me")
async def my_features(user: dict = Depends(get_current_user)):
    """What this user can use right now - for hiding menu items in the UI."""
    allowed, denied = [], 0
    for f in await feature_registry.all_features():
        if await access.check_feature(user, f["key"]) is None:
            allowed.append(f["key"])
        else:
            denied += 1
    grants = await access.grants_col.find({"user_id": user["id"], "status": "active"}, {"_id": 0}).to_list(200)
    return {"features": allowed, "denied_count": denied, "grants": _iso(grants)}


@router.get("/features/check/{key}")
async def check_feature(key: str, user: dict = Depends(get_current_user)):
    reason = await access.check_feature(user, key)
    return {"feature": key, "allowed": reason is None, "reason": reason}


@router.patch("/features/{key}")
async def update_feature(key: str, body: FeatureUpdate, user: dict = Depends(require_feature("governance.feature_registry"))):
    changes = body.model_dump(exclude_none=True)
    try:
        before = await feature_registry.update_feature(key, changes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if before is None:
        raise HTTPException(status_code=404, detail="Feature not registered")
    await audit_chain.log_event("feature.updated", actor=user, target_type="feature", target_id=key,
                                before={k: before.get(k) for k in changes}, after=changes,
                                severity="warn" if "stage" in changes else "info")
    return {"ok": True}


@router.post("/features/{key}/kill")
async def kill_feature(key: str, body: KillRequest, user: dict = Depends(require_feature("governance.feature_registry"))):
    if key == "governance.feature_registry":
        raise HTTPException(status_code=400, detail="The registry itself cannot be switched off")
    if await feature_registry.update_feature(key, {"killed": True, "kill_reason": body.reason}) is None:
        raise HTTPException(status_code=404, detail="Feature not registered")
    await audit_chain.log_event("feature.killed", actor=user, target_type="feature", target_id=key,
                                severity="critical", meta={"reason": body.reason})
    return {"ok": True, "note": "Takes effect on every server within 30 seconds"}


@router.post("/features/{key}/unkill")
async def unkill_feature(key: str, user: dict = Depends(require_feature("governance.feature_registry"))):
    if await feature_registry.update_feature(key, {"killed": False, "kill_reason": None}) is None:
        raise HTTPException(status_code=404, detail="Feature not registered")
    await audit_chain.log_event("feature.restored", actor=user, target_type="feature", target_id=key, severity="warn")
    return {"ok": True}


# ═════════════════════════════ Access requests ═════════════════════════════

class AccessRequestIn(BaseModel):
    feature_key: str
    target_user_id: Optional[str] = None
    days: Optional[int] = Field(None, ge=1, le=365)
    reason: str
    scope: str = Field("all", pattern="^(own|team|dept|all)$")


class DecisionIn(BaseModel):
    comment: str = ""
    sod_override_reason: Optional[str] = None


@router.post("/access-requests")
async def create_access_request(body: AccessRequestIn, user: dict = Depends(require_feature("governance.access_requests"))):
    req = await access.create_request(user, feature_key=body.feature_key, target_user_id=body.target_user_id,
                                      days=body.days, reason=body.reason, scope=body.scope)
    return _iso(req)


@router.get("/access-requests/mine")
async def my_requests(user: dict = Depends(get_current_user)):
    rows = await access.requests_col.find(
        {"$or": [{"requester_id": user["id"]}, {"target_user_id": user["id"]}]}, {"_id": 0}
    ).sort("created_at", -1).limit(200).to_list(200)
    return _iso(rows)


@router.get("/access-requests/inbox")
async def approval_inbox(user: dict = Depends(get_current_user)):
    """Pending requests whose *current* step this user may decide."""
    out = []
    async for req in access.requests_col.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).limit(500):
        f = await feature_registry.get_feature(req["feature_key"]) or {}
        target = await users_col.find_one({"id": req["target_user_id"]}, {"_id": 0, "id": 1, "reports_to": 1, "manager_id": 1})
        step = req["steps"][req["current_step"]]
        if await access.can_approve_step(user, step, req, f, target) is None:
            out.append({**req, "awaiting_step": step})
    return _iso(out)


@router.post("/access-requests/{request_id}/approve")
async def approve_request(request_id: str, body: DecisionIn, user: dict = Depends(get_current_user)):
    return _iso(await access.decide_request(user, request_id, approve=True, comment=body.comment,
                                            sod_override_reason=body.sod_override_reason))


@router.post("/access-requests/{request_id}/reject")
async def reject_request(request_id: str, body: DecisionIn, user: dict = Depends(get_current_user)):
    return _iso(await access.decide_request(user, request_id, approve=False, comment=body.comment))


@router.post("/access-requests/{request_id}/cancel")
async def cancel_request(request_id: str, user: dict = Depends(get_current_user)):
    res = await access.requests_col.update_one(
        {"id": request_id, "requester_id": user["id"], "status": "pending"},
        {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc), "cancel_reason": "requester"}},
    )
    if not res.modified_count:
        raise HTTPException(status_code=404, detail="No pending request of yours with that id")
    await audit_chain.log_event("access_request.cancelled", actor=user, target_type="access_request", target_id=request_id)
    return {"ok": True}


# ═════════════════════════════ Grants ═════════════════════════════

class RevokeIn(BaseModel):
    reason: str = Field(..., min_length=5)


@router.get("/grants")
async def list_grants(user_id: Optional[str] = None, status: Optional[str] = "active",
                      user: dict = Depends(get_current_user)):
    if await access.check_feature(user, "governance.access_approvals"):
        user_id = user["id"]  # non-approvers only ever see their own grants
    q: dict = {}
    if user_id:
        q["user_id"] = user_id
    if status:
        q["status"] = status
    return _iso(await access.grants_col.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500))


@router.post("/grants/{grant_id}/revoke")
async def revoke_grant(grant_id: str, body: RevokeIn, user: dict = Depends(require_feature("governance.access_approvals"))):
    if not await access.revoke_grant(user, grant_id, body.reason):
        raise HTTPException(status_code=404, detail="Active grant not found")
    return {"ok": True}


@router.post("/grants/expire-now")
async def expire_now(_: dict = Depends(require_feature("governance.feature_registry"))):
    return {"expired": await access.expire_grants()}


# ═════════════════════════════ SoD ═════════════════════════════

class SodRuleIn(BaseModel):
    name: str
    side_a: List[str]
    side_b: List[str]
    why: str = ""
    active: bool = True


@router.get("/sod/rules")
async def sod_rules(_: dict = Depends(get_current_user)):
    return _iso(await access.sod_col.find({}, {"_id": 0}).to_list(500))


@router.put("/sod/rules/{rule_id}")
async def upsert_sod_rule(rule_id: str, body: SodRuleIn, user: dict = Depends(require_feature("governance.sod_rules"))):
    if not access.is_owner(user):
        raise HTTPException(status_code=403, detail="Only the owner (MD) can change separation-of-duties rules")
    before = await access.sod_col.find_one({"id": rule_id}, {"_id": 0})
    await access.sod_col.update_one({"id": rule_id}, {"$set": {"id": rule_id, **body.model_dump()}}, upsert=True)
    await audit_chain.log_event("sod.rule_changed", actor=user, target_type="sod_rule", target_id=rule_id,
                                before=_iso(before), after=body.model_dump(), severity="critical")
    return {"ok": True}


@router.get("/sod/violations")
async def sod_violations(_: dict = Depends(require_feature("governance.sod_rules"))):
    """Access-review report: active staff who already hold conflicting powers."""
    rules = await access.active_sod_rules()
    out = []
    async for u in users_col.find({"status": "active", "role": {"$nin": list(access.EXTERNAL_ROLES)}},
                                  {"_id": 0, "id": 1, "name": 1, "email": 1, "department": 1, "role": 1,
                                   "rbac_role": 1, "capability_packs": 1, "feature_overrides": 1}):
        if access.is_admin(u):
            continue  # admins are reviewed separately (they bypass by design)
        v = access.sod_violations_for(await access.effective_feature_keys(u), rules)
        if v:
            out.append({"user_id": u["id"], "name": u.get("name"), "email": u.get("email"),
                        "department": u.get("department"), "violations": v})
    return out


# ═════════════════════════════ Audit ═════════════════════════════

@router.get("/audit/events")
async def audit_events(target_id: Optional[str] = None, actor_id: Optional[str] = None,
                       action: Optional[str] = None, limit: int = Query(100, le=1000),
                       _: dict = Depends(require_feature("governance.audit_chain"))):
    q: dict = {}
    if target_id:
        q["target_id"] = target_id
    if actor_id:
        q["actor_id"] = actor_id
    if action:
        q["action"] = action
    return _iso(await audit_chain.events_col.find(q, {"_id": 0}).sort("seq", -1).limit(limit).to_list(limit))


@router.get("/audit/verify")
async def audit_verify(_: dict = Depends(require_feature("governance.audit_chain"))):
    return await audit_chain.verify_chain()


# ═════════════════════════════ Statutory ═════════════════════════════

class StatutoryIn(BaseModel):
    key: str = Field(..., pattern=r"^[a-z_]+\.[A-Za-z_\.]+$")
    value: Any
    effective_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(..., min_length=5)
    source_url: str = ""


@router.get("/statutory")
async def statutory_list(key: Optional[str] = None, _: dict = Depends(require_feature("governance.statutory_settings"))):
    return await statutory.list_settings(key)


@router.get("/statutory/effective")
async def statutory_effective(date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                              _: dict = Depends(require_feature("governance.statutory_settings"))):
    return {"as_of": date, "rules": await statutory.rules_as_of(date)}


@router.post("/statutory")
async def statutory_add(body: StatutoryIn, user: dict = Depends(require_feature("governance.statutory_settings"))):
    try:
        row = await statutory.add_version(user, body.key, body.value, body.effective_from, body.note, body.source_url)
    except ValueError:
        raise HTTPException(status_code=400, detail="effective_from must be a real date (YYYY-MM-DD)")
    except Exception as e:  # duplicate key/effective_from
        if "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="A value for this key and date already exists - use a new date")
        raise
    await audit_chain.log_event("statutory.added", actor=user, target_type="statutory_setting", target_id=body.key,
                                after={"value": body.value, "effective_from": body.effective_from}, severity="critical")
    return _iso(row)
