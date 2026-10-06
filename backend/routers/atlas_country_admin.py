"""Atlas Country admin endpoints.

SECURITY: every route requires an authenticated admin, and updates are limited
to an allow-list of editable fields (previously the PUT accepted any JSON and
wrote it straight into MongoDB without authentication).
"""
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException

from core.auth import get_current_user
from core.database import db

router = APIRouter(
    prefix="/atlas/admin",
    tags=["Atlas Country Admin"],
)

EDITABLE_FIELDS = {
    "name",
    "flag",
    "classification",
    "primary_code_length",
    "benchmark",
    "benchmark_label",
    "enabled",
    "modules",
    "description",
    "sort_order",
}


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    role = (current_user.get("rbac_role") or current_user.get("role") or "").lower()
    if role not in {"admin", "admin_owner", "super_admin"} and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


@router.get("/countries")
async def get_all_countries(current_user: dict = Depends(_require_admin)):
    countries = await db["atlas_countries"].find({}, {"_id": 0}).sort("name", 1).to_list(None)
    return countries


@router.get("/countries/{code}")
async def get_country(code: str, current_user: dict = Depends(_require_admin)):
    country = await db["atlas_countries"].find_one({"code": code.upper()}, {"_id": 0})
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    return country


@router.put("/countries/{code}")
async def update_country(
    code: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(_require_admin),
):
    code = code.upper()
    unknown = set(payload) - EDITABLE_FIELDS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Fields not editable: {', '.join(sorted(unknown))}")
    if not payload:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "modules" in payload and not isinstance(payload["modules"], dict):
        raise HTTPException(status_code=400, detail="modules must be an object")
    if "enabled" in payload and not isinstance(payload["enabled"], bool):
        raise HTTPException(status_code=400, detail="enabled must be true/false")

    update = dict(payload)
    update["updated_at"] = datetime.now(timezone.utc)
    update["updated_by"] = current_user.get("id")

    result = await db["atlas_countries"].update_one({"code": code}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Country not found")

    country = await db["atlas_countries"].find_one({"code": code}, {"_id": 0})
    return {"message": "Country updated successfully", "country": country}
