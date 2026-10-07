"""E16-01 - Effective-dated statutory settings.

Rows in ``statutory_settings`` are never edited in place. A rate change is a
new row with a later ``effective_from``; the old row stays for history and for
re-running past payrolls exactly as they were.

    {key, value, effective_from: "YYYY-MM-DD", note, source_url,
     created_by, created_at}
"""
from __future__ import annotations

import calendar
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db
from core.governance.payroll_rules import DEFAULT_RULES

settings_col = db["statutory_settings"]

PIB_LABOUR_CODES = "https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2192463"
PIB_EPF_CEILING = "https://pib.gov.in/PressReleaseDetail.aspx?PRID=2310973&reg=3&lang=1"
TAXGURU_TDS_2026 = "https://taxguru.in/income-tax/tds-tcs-1st-april-2026.html"

SEED: List[Dict[str, Any]] = [
    {"key": "pf.wage_ceiling_inr", "value": 15000, "effective_from": "2014-09-01",
     "note": "EPF wage ceiling (old)", "source_url": PIB_EPF_CEILING},
    {"key": "pf.wage_ceiling_inr", "value": 25000, "effective_from": "2026-09-17",
     "note": "EPF wage ceiling raised to Rs 25,000", "source_url": PIB_EPF_CEILING},
    {"key": "pf.employee_pct", "value": 12.0, "effective_from": "2014-09-01", "note": "EPF employee share"},
    {"key": "pf.employer_pct", "value": 12.0, "effective_from": "2014-09-01", "note": "EPF + EPS employer share"},
    {"key": "pf.restrict_to_ceiling", "value": True, "effective_from": "2014-09-01",
     "note": "Compute PF on wages capped at the ceiling (set False if company pays on full wages)"},
    {"key": "esi.gross_threshold_inr", "value": 21000, "effective_from": "2017-01-01", "note": "ESI coverage limit"},
    {"key": "esi.employee_pct", "value": 0.75, "effective_from": "2019-07-01", "note": "ESI employee share"},
    {"key": "esi.employer_pct", "value": 3.25, "effective_from": "2019-07-01", "note": "ESI employer share"},
    {"key": "labour_code.min_wage_pct", "value": 50.0, "effective_from": "2025-11-21",
     "note": "Wages must be at least 50% of total remuneration", "source_url": PIB_LABOUR_CODES},
    {"key": "labour_code.apply_wage_rule", "value": True, "effective_from": "2025-11-21",
     "note": "Add back excess exclusions to PF wages", "source_url": PIB_LABOUR_CODES},
    {"key": "pt.state", "value": "MH", "effective_from": "2000-01-01", "note": "Default PT state (Thane office)"},
    {"key": "pt.MH", "value": DEFAULT_RULES["pt.MH"], "effective_from": "2023-07-01",
     "note": "Maharashtra PT slabs (monthly gross). Feb top slab Rs 300. Confirm with CA."},
    {"key": "tds.salary_section", "value": "392", "effective_from": "2026-04-01",
     "note": "Income-tax Act 2025: salary TDS", "source_url": TAXGURU_TDS_2026},
    {"key": "tds.salary_certificate_form", "value": "130", "effective_from": "2026-04-01",
     "note": "Replaces Form 16", "source_url": TAXGURU_TDS_2026},
    {"key": "tds.salary_return_form", "value": "138", "effective_from": "2026-04-01",
     "note": "Replaces Form 24Q", "source_url": TAXGURU_TDS_2026},
    {"key": "tds.non_salary_return_form", "value": "140", "effective_from": "2026-04-01",
     "note": "Replaces Form 26Q", "source_url": TAXGURU_TDS_2026},
    {"key": "tds.commission_rate_pct", "value": 2.0, "effective_from": "2024-10-01",
     "note": "TDS on commission/brokerage"},
    {"key": "tds.commission_threshold_inr", "value": 20000, "effective_from": "2025-04-01",
     "note": "Annual threshold for commission TDS"},
]


async def ensure_indexes() -> None:
    await settings_col.create_index([("key", 1), ("effective_from", -1)], unique=True)


async def seed_settings() -> int:
    n = 0
    now = datetime.now(timezone.utc)
    for row in SEED:
        res = await settings_col.update_one(
            {"key": row["key"], "effective_from": row["effective_from"]},
            {"$setOnInsert": {"id": str(uuid.uuid4()), **row, "created_by": "seed", "created_at": now}},
            upsert=True,
        )
        n += 1 if res.upserted_id else 0
    return n


def period_end(period: str) -> str:
    """'2026-09' -> '2026-09-30' (rules effective on the last day of the wage month apply)."""
    y, m = int(period[:4]), int(period[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


async def value_as_of(key: str, as_of: str, default: Any = None) -> Any:
    row = await settings_col.find_one({"key": key, "effective_from": {"$lte": as_of}},
                                      {"_id": 0}, sort=[("effective_from", -1)])
    return row["value"] if row else default


async def rules_as_of(as_of: str) -> Dict[str, Any]:
    rules = copy.deepcopy(DEFAULT_RULES)
    pipeline = [
        {"$match": {"effective_from": {"$lte": as_of}}},
        {"$sort": {"key": 1, "effective_from": -1}},
        {"$group": {"_id": "$key", "value": {"$first": "$value"}}},
    ]
    async for r in settings_col.aggregate(pipeline):
        rules[r["_id"]] = r["value"]
    return rules


async def payroll_rules_for(period: str) -> Dict[str, Any]:
    return await rules_as_of(period_end(period))


async def add_version(actor: dict, key: str, value: Any, effective_from: str,
                      note: str = "", source_url: str = "") -> dict:
    datetime.strptime(effective_from, "%Y-%m-%d")  # validates format, raises ValueError
    row = {"id": str(uuid.uuid4()), "key": key, "value": value, "effective_from": effective_from,
           "note": note, "source_url": source_url, "created_by": actor["id"],
           "created_at": datetime.now(timezone.utc)}
    await settings_col.insert_one(dict(row))
    return row


async def list_settings(key: Optional[str] = None) -> List[dict]:
    q = {"key": key} if key else {}
    rows = await settings_col.find(q, {"_id": 0}).sort([("key", 1), ("effective_from", -1)]).to_list(2000)
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    return rows
