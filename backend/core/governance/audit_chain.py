"""E03-01 - Tamper-evident audit trail.

Every governance event is written to ``audit_events`` with a SHA-256 hash that
covers the event body *and* the previous event's hash. Editing or deleting any
row breaks the chain, which ``verify_chain()`` detects and reports.

Concurrency: the chain head (last seq + hash) lives in ``audit_chain_head``.
Writers use compare-and-swap on ``seq`` so two parallel writers can never fork
the chain; the loser simply retries with the new head.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import db

logger = logging.getLogger(__name__)

events_col = db["audit_events"]
head_col = db["audit_chain_head"]

GENESIS_HASH = "0" * 64
_HEAD_ID = "main"
_MAX_RETRIES = 25


def _canonical(body: Dict[str, Any]) -> str:
    """Stable JSON used for hashing (sorted keys, ISO datetimes)."""
    def _default(o):
        if isinstance(o, datetime):
            return o.astimezone(timezone.utc).isoformat()
        return str(o)
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=_default)


def _plain(value: Any) -> Any:
    """JSON round-trip so what we store is exactly what we hashed."""
    return None if value is None else json.loads(_canonical(value))


def compute_hash(prev_hash: str, body: Dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + "|" + _canonical(body)).encode("utf-8")).hexdigest()


def _body_of(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The fields that are covered by the hash."""
    return {k: doc.get(k) for k in (
        "id", "seq", "action", "actor_id", "actor_name", "target_type", "target_id",
        "severity", "ip", "before", "after", "meta", "at",
    )}


async def ensure_indexes() -> None:
    await events_col.create_index("seq", unique=True)
    await events_col.create_index([("target_type", 1), ("target_id", 1), ("seq", -1)])
    await events_col.create_index([("actor_id", 1), ("seq", -1)])
    await events_col.create_index([("action", 1), ("seq", -1)])


async def log_event(
    action: str,
    *,
    actor: Optional[dict] = None,
    actor_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    meta: Optional[Dict[str, Any]] = None,
    severity: str = "info",
    ip: Optional[str] = None,
) -> Optional[str]:
    """Append one event to the chain. Never raises (an audit failure must not
    break the business action) - failures are logged at ERROR level."""
    try:
        _n = datetime.now(timezone.utc)
        now = _n.replace(microsecond=(_n.microsecond // 1000) * 1000)  # Mongo keeps ms precision
        for _ in range(_MAX_RETRIES):
            head = await head_col.find_one({"_id": _HEAD_ID}) or {"seq": 0, "hash": GENESIS_HASH}
            seq = int(head.get("seq", 0)) + 1
            doc = {
                "id": str(uuid.uuid4()),
                "seq": seq,
                "action": action,
                "actor_id": actor_id or (actor or {}).get("id"),
                "actor_name": (actor or {}).get("name"),
                "target_type": target_type,
                "target_id": target_id,
                "severity": severity,
                "ip": ip,
                "before": _plain(before),
                "after": _plain(after),
                "meta": _plain(meta or {}),
                "at": now,
            }
            doc["prev_hash"] = head.get("hash", GENESIS_HASH)
            doc["hash"] = compute_hash(doc["prev_hash"], _body_of(doc))
            # Compare-and-swap the head first; only the winner inserts.
            if head.get("seq", 0) == 0 and not await head_col.find_one({"_id": _HEAD_ID}):
                try:
                    await head_col.insert_one({"_id": _HEAD_ID, "seq": seq, "hash": doc["hash"]})
                    won = True
                except Exception:  # noqa: BLE001 - another writer created it
                    won = False
            else:
                res = await head_col.update_one(
                    {"_id": _HEAD_ID, "seq": head["seq"]},
                    {"$set": {"seq": seq, "hash": doc["hash"]}},
                )
                won = res.modified_count == 1
            if won:
                await events_col.insert_one(doc)
                return doc["id"]
        logger.error("audit_chain: gave up after %s retries for %s", _MAX_RETRIES, action)
    except Exception:  # noqa: BLE001
        logger.exception("audit_chain: failed to write %s", action)
    return None


async def verify_chain(limit: Optional[int] = None) -> Dict[str, Any]:
    """Walk the chain in seq order and report the first break, if any."""
    prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    cursor = events_col.find({}, {"_id": 0}).sort("seq", 1)
    if limit:
        cursor = cursor.limit(limit)
    async for doc in cursor:
        if doc.get("seq") != expected_seq:
            return {"ok": False, "checked": checked, "broken_at_seq": expected_seq,
                    "reason": f"missing event (found seq {doc.get('seq')})"}
        if doc.get("prev_hash") != prev:
            return {"ok": False, "checked": checked, "broken_at_seq": doc["seq"], "reason": "prev_hash mismatch"}
        if compute_hash(prev, _body_of(doc)) != doc.get("hash"):
            return {"ok": False, "checked": checked, "broken_at_seq": doc["seq"], "reason": "content was modified"}
        prev = doc["hash"]
        expected_seq += 1
        checked += 1
    head = await head_col.find_one({"_id": _HEAD_ID})
    if not limit and head and head.get("seq", 0) != checked:
        return {"ok": False, "checked": checked, "broken_at_seq": checked + 1,
                "reason": "events missing at the end of the chain"}
    return {"ok": True, "checked": checked, "head_hash": prev}
