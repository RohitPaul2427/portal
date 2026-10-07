"""E02-05 - Server-side login sessions.

Each staff login creates a row in ``user_sessions`` and puts its id in the JWT
(``sid`` claim). ``get_current_user`` rejects tokens whose session was revoked
or ended, which gives us:

* real logout (the token stops working immediately, not after 24 h)
* "log out my other devices"
* admin kill of every session of a leaver (E07-02)
* a login/logout history per employee (feeds attendance and security review)

Tokens issued before this release carry no ``sid``; they keep working until
they expire unless ``REQUIRE_SESSION_ID=1`` is set (switch it on ~24 h after
deploying, once every old token has expired).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import db

sessions_col = db["user_sessions"]

# Throttle last_seen writes so we do not write to Mongo on every request.
_LAST_SEEN_EVERY = timedelta(minutes=5)


def require_session_id() -> bool:
    return os.environ.get("REQUIRE_SESSION_ID", "0") == "1"


async def ensure_indexes() -> None:
    await sessions_col.create_index("id", unique=True)
    await sessions_col.create_index([("user_id", 1), ("status", 1)])
    # Ended sessions are kept 180 days (CERT-In log retention), then dropped.
    await sessions_col.create_index("ended_at", expireAfterSeconds=180 * 24 * 3600)


def _client_meta(request) -> Dict[str, Optional[str]]:
    if request is None:
        return {"ip": None, "user_agent": None}
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    return {"ip": ip, "user_agent": (request.headers.get("user-agent") or "")[:300]}


async def create_session(user: dict, request=None, *, kind: str = "password",
                         impersonated_by: Optional[str] = None, hours: int = 24) -> str:
    now = datetime.now(timezone.utc)
    sid = str(uuid.uuid4())
    await sessions_col.insert_one({
        "id": sid,
        "user_id": user["id"],
        "kind": kind,                        # password | impersonation | sso
        "impersonated_by": impersonated_by,
        "status": "active",                  # active | ended | revoked
        "created_at": now,
        "last_seen_at": now,
        "expires_at": now + timedelta(hours=hours),
        "ended_at": None,
        "end_reason": None,
        **_client_meta(request),
    })
    return sid


async def check_session(sid: Optional[str], user_id: str) -> Optional[str]:
    """Return None if the session is usable, else a human-readable reason."""
    if not sid:
        return "Session required. Please login again." if require_session_id() else None
    s = await sessions_col.find_one({"id": sid}, {"_id": 0})
    if not s or s.get("user_id") != user_id:
        return "Session not found. Please login again."
    if s.get("status") != "active":
        return "Session ended. Please login again."
    now = datetime.now(timezone.utc)
    last = s.get("last_seen_at")
    if not last or now - last > _LAST_SEEN_EVERY:
        await sessions_col.update_one({"id": sid}, {"$set": {"last_seen_at": now}})
    return None


async def end_session(sid: str, reason: str = "logout", status: str = "ended") -> bool:
    res = await sessions_col.update_one(
        {"id": sid, "status": "active"},
        {"$set": {"status": status, "ended_at": datetime.now(timezone.utc), "end_reason": reason}},
    )
    return res.modified_count == 1


async def revoke_user_sessions(user_id: str, reason: str, except_sid: Optional[str] = None) -> int:
    q: Dict[str, Any] = {"user_id": user_id, "status": "active"}
    if except_sid:
        q["id"] = {"$ne": except_sid}
    res = await sessions_col.update_many(
        q, {"$set": {"status": "revoked", "ended_at": datetime.now(timezone.utc), "end_reason": reason}},
    )
    return res.modified_count


def _out(s: dict, current_sid: Optional[str] = None) -> dict:
    d = dict(s)
    for k in ("created_at", "last_seen_at", "expires_at", "ended_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    d["current"] = bool(current_sid and s.get("id") == current_sid)
    return d


async def list_sessions(user_id: Optional[str] = None, status: Optional[str] = None,
                        limit: int = 100, current_sid: Optional[str] = None) -> List[dict]:
    q: Dict[str, Any] = {}
    if user_id:
        q["user_id"] = user_id
    if status:
        q["status"] = status
    rows = await sessions_col.find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return [_out(r, current_sid) for r in rows]
