"""E04 - Feature registry, kill switch and staged rollout.

Every feature the portal exposes gets one row in ``feature_registry``:

    key            "hr.payroll_admin"         (same id as FEATURE_CATALOG)
    name, description, owner_dept
    risk           low | medium | high | critical
    stage          development | pilot | department | company | retired
    pilot_user_ids users who may see a feature in "pilot"
    departments    departments that may see a feature in "department"
    killed         True = switched off for everyone (incident kill switch)
    approvers      user ids who approve access requests for this feature

Deny-by-default: a key that is not registered is never allowed through
``require_feature``. Existing features are seeded at stage "company" so nothing
that works today stops working.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

registry_col = db["feature_registry"]

STAGES = ("development", "pilot", "department", "company", "retired")
RISKS = ("low", "medium", "high", "critical")

# Default risk by catalog category (owners can change it in the UI/API).
_CATEGORY_RISK = {
    "baseline": "low", "communication": "low", "knowledge_base": "low", "atlas": "low",
    "marketing": "medium", "sales": "medium", "operations": "medium", "ai": "medium",
    "manager": "medium", "it": "high", "hr": "high", "accounts": "high",
    "commission_revenue": "high", "admin_system": "critical",
}
_CATEGORY_DEPT = {
    "hr": "hr", "accounts": "accounts", "commission_revenue": "accounts", "it": "it",
    "admin_system": "it", "marketing": "marketing", "sales": "sales", "operations": "operations",
}

# Features this release adds (they start in "company" because they are
# self-service or admin-only by construction).
NEW_FEATURES: List[Dict[str, Any]] = [
    {"key": "governance.my_sessions", "name": "My login sessions", "category": "baseline", "risk": "low"},
    {"key": "governance.access_requests", "name": "Request access", "category": "baseline", "risk": "low"},
    {"key": "governance.access_approvals", "name": "Approve access requests", "category": "manager", "risk": "high"},
    {"key": "governance.feature_registry", "name": "Feature registry & kill switch", "category": "admin_system", "risk": "critical"},
    {"key": "governance.audit_chain", "name": "Tamper-evident audit trail", "category": "admin_system", "risk": "high"},
    {"key": "governance.sod_rules", "name": "Separation-of-duties rules", "category": "admin_system", "risk": "critical"},
    {"key": "governance.statutory_settings", "name": "Statutory settings (PF/ESI/PT/TDS)", "category": "hr", "risk": "critical"},
    {"key": "governance.session_admin", "name": "All sessions (admin)", "category": "admin_system", "risk": "high"},
]

_CACHE: Dict[str, Any] = {"at": 0.0, "rows": {}}
_TTL = 30.0  # seconds - kill switch takes effect within 30 s on every worker


def invalidate_cache() -> None:
    _CACHE["at"] = 0.0


async def ensure_indexes() -> None:
    await registry_col.create_index("key", unique=True)


async def seed_registry() -> Dict[str, int]:
    """Idempotent: inserts missing features, never overwrites owner edits."""
    from core.rbac.capability_packs_data import FEATURE_CATALOG
    now = datetime.now(timezone.utc)
    inserted = 0
    rows = [{
        "key": f["feature_id"], "name": f.get("name") or f["feature_id"],
        "description": f.get("description") or "", "category": f.get("category"),
        "risk": _CATEGORY_RISK.get(f.get("category"), "medium"),
    } for f in FEATURE_CATALOG] + NEW_FEATURES
    for r in rows:
        res = await registry_col.update_one(
            {"key": r["key"]},
            {"$setOnInsert": {
                **r,
                "description": r.get("description", ""),
                "owner_dept": _CATEGORY_DEPT.get(r.get("category"), "it"),
                "stage": "company", "pilot_user_ids": [], "departments": [],
                "killed": False, "kill_reason": None, "approvers": [],
                "created_at": now, "updated_at": now,
            }},
            upsert=True,
        )
        inserted += 1 if res.upserted_id else 0
    invalidate_cache()
    return {"inserted": inserted, "total": len(rows)}


async def _rows() -> Dict[str, dict]:
    if time.monotonic() - _CACHE["at"] > _TTL:
        rows = await registry_col.find({}, {"_id": 0}).to_list(5000)
        _CACHE["rows"] = {r["key"]: r for r in rows}
        _CACHE["at"] = time.monotonic()
    return _CACHE["rows"]


async def get_feature(key: str) -> Optional[dict]:
    return (await _rows()).get(key)


async def all_features() -> List[dict]:
    return sorted((await _rows()).values(), key=lambda r: r["key"])


def stage_allows(feature: dict, user: dict) -> bool:
    """Pure check of rollout stage for one user (no DB)."""
    stage = feature.get("stage", "development")
    if stage == "company":
        return True
    if stage == "department":
        return (user.get("department") or "") in (feature.get("departments") or []) \
            or user.get("id") in (feature.get("pilot_user_ids") or [])
    if stage == "pilot":
        return user.get("id") in (feature.get("pilot_user_ids") or [])
    return False  # development / retired: nobody except the super-admin bypass


async def update_feature(key: str, changes: Dict[str, Any]) -> Optional[dict]:
    allowed = {"name", "description", "owner_dept", "risk", "stage", "pilot_user_ids",
               "departments", "killed", "kill_reason", "approvers"}
    clean = {k: v for k, v in changes.items() if k in allowed}
    if "stage" in clean and clean["stage"] not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    if "risk" in clean and clean["risk"] not in RISKS:
        raise ValueError(f"risk must be one of {RISKS}")
    clean["updated_at"] = datetime.now(timezone.utc)
    before = await registry_col.find_one({"key": key}, {"_id": 0})
    if not before:
        return None
    await registry_col.update_one({"key": key}, {"$set": clean})
    invalidate_cache()
    return before
