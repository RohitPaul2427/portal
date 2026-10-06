"""Brute-force protection for login endpoints.

Failed attempts are stored in MongoDB (``login_failures``) so the limit holds
across multiple workers/instances. Documents expire automatically via a TTL
index.

Defaults: 5 failures per (email) or 20 failures per (IP) within 15 minutes
blocks further attempts for that key until the window passes.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from core.database import db

_col = db["login_failures"]

WINDOW_MINUTES = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))
MAX_PER_EMAIL = int(os.environ.get("LOGIN_MAX_FAILURES_PER_EMAIL", "5"))
MAX_PER_IP = int(os.environ.get("LOGIN_MAX_FAILURES_PER_IP", "20"))

_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await _col.create_index("created_at", expireAfterSeconds=WINDOW_MINUTES * 60)
        await _col.create_index([("scope", 1), ("key", 1), ("created_at", -1)])
    except Exception:
        pass
    _indexes_ready = True


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_allowed(scope: str, email: str, ip: str) -> None:
    """Raise 429 if the email or IP has too many recent failures."""
    await _ensure_indexes()
    since = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)
    by_email = await _col.count_documents({"scope": scope, "key": f"e:{email}", "created_at": {"$gte": since}})
    by_ip = await _col.count_documents({"scope": scope, "key": f"i:{ip}", "created_at": {"$gte": since}})
    if by_email >= MAX_PER_EMAIL or by_ip >= MAX_PER_IP:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Please try again in {WINDOW_MINUTES} minutes.",
        )


async def record_failure(scope: str, email: str, ip: str) -> None:
    await _ensure_indexes()
    now = datetime.now(timezone.utc)
    await _col.insert_many([
        {"scope": scope, "key": f"e:{email}", "created_at": now},
        {"scope": scope, "key": f"i:{ip}", "created_at": now},
    ])


async def clear_failures(scope: str, email: str) -> None:
    await _col.delete_many({"scope": scope, "key": f"e:{email}"})
