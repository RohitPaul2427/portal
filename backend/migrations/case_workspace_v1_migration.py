"""Case Workspace Schema & Multi-Application Register Migration.

Phase 2 Idempotent migration script supporting:
  --dry-run (default, report planned mutations without writing)
  --apply   (commit schema indexes and backfill records)

Mutations:
1. Creates indexes on `case_applications`, `case_access_grants`,
   `case_vault_credentials`, and `documents`.
2. Backfills `lifecycle_state` on existing cases (defaulting to 'document_gathering' or 'intake').
3. Backfills `sensitivity_tier` on existing documents using type classification.
4. Extracts legacy flat application fields on `cases` (e.g. skills_assessment,
   points_claim, state_nomination, express_entry) into structured `case_applications`
   records without mutating or deleting existing case fields.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient

from core.case_workspace_models import (
    ApplicationStatus,
    ApplicationType,
    WorkspaceLifecycleState,
)
from core.document_security import classify_sensitivity

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("case_workspace_migration")


async def run_migration(apply: bool = False, mongo_url: str = "mongodb://localhost:27017", db_name: str = "leamss"):
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    logger.info("Starting Case Workspace Migration (Mode: %s)", "APPLY" if apply else "DRY-RUN")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Indexes Setup
    # ─────────────────────────────────────────────────────────────────────────
    index_plans = [
        ("case_applications", [("case_id", 1), ("application_type", 1)]),
        ("case_applications", [("client_id", 1)]),
        ("case_applications", [("reference_identifier", 1)]),
        ("case_access_grants", [("case_id", 1), ("user_id", 1)]),
        ("case_access_grants", [("expires_at", 1)]),
        ("case_vault_credentials", [("case_id", 1)]),
        ("documents", [("case_id", 1)]),
        ("documents", [("sensitivity_tier", 1)]),
        ("cases", [("case_manager_id", 1)]),
        ("cases", [("secondary_case_managers", 1)]),
        ("cases", [("client_id", 1)]),
    ]

    for col_name, keys in index_plans:
        logger.info("[INDEX] %s on %s", col_name, keys)
        if apply:
            await db[col_name].create_index(keys)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Backfill Document Sensitivity Tiers
    # ─────────────────────────────────────────────────────────────────────────
    doc_cursor = db["documents"].find({"sensitivity_tier": {"$exists": False}})
    docs_to_update = 0
    async for doc in doc_cursor:
        docs_to_update += 1
        tier = classify_sensitivity(doc.get("document_type")).value
        if apply:
            await db["documents"].update_one(
                {"id": doc["id"]},
                {"$set": {"sensitivity_tier": tier}},
            )
    logger.info("[DOCUMENTS] %d documents identified for sensitivity_tier backfill", docs_to_update)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Backfill Case Lifecycle State & Multi-Applications
    # ─────────────────────────────────────────────────────────────────────────
    case_cursor = db["cases"].find({})
    cases_count = 0
    apps_created = 0

    async for case in case_cursor:
        cases_count += 1
        case_id = case.get("id")
        client_id = case.get("client_id")

        # 3a. Lifecycle state
        if not case.get("lifecycle_state"):
            state = WorkspaceLifecycleState.DOCUMENT_GATHERING.value
            if case.get("status") in ("closed", "archived"):
                state = WorkspaceLifecycleState.ARCHIVED.value
            elif case.get("status") in ("completed", "approved", "granted"):
                state = WorkspaceLifecycleState.POST_DECISION.value

            if apply:
                await db["cases"].update_one(
                    {"id": case_id},
                    {"$set": {"lifecycle_state": state, "secondary_case_managers": case.get("secondary_case_managers", [])}},
                )

        # 3b. Extract Skills Assessment application record if present
        details = case.get("details", {}) or {}
        skills_auth = details.get("assessing_authority") or case.get("assessing_authority")
        if skills_auth:
            exists = await db["case_applications"].find_one({
                "case_id": case_id,
                "application_type": ApplicationType.SKILLS_ASSESSMENT.value,
            })
            if not exists:
                apps_created += 1
                app_doc = {
                    "id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "client_id": client_id,
                    "application_type": ApplicationType.SKILLS_ASSESSMENT.value,
                    "country": case.get("country", "AU"),
                    "authority_or_state": skills_auth,
                    "subclass_or_stream": details.get("anzsco_code") or case.get("occupation_code"),
                    "applicant_type": "primary",
                    "applicant_name": case.get("client_name"),
                    "reference_identifier": details.get("assessment_reference"),
                    "status": ApplicationStatus.SUBMITTED.value if details.get("assessment_reference") else ApplicationStatus.PREPARING.value,
                    "status_source": "manual_entry",
                    "submission_date": details.get("assessment_date"),
                    "points_claimed": None,
                    "responsible_staff_id": case.get("case_manager_id"),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
                if apply:
                    await db["case_applications"].insert_one(app_doc)

        # 3c. Extract State Nomination application record if present
        state_nom = details.get("state_nomination") or case.get("state_nomination")
        if state_nom and state_nom != "No":
            exists = await db["case_applications"].find_one({
                "case_id": case_id,
                "application_type": ApplicationType.ROI_NOMINATION.value,
                "authority_or_state": state_nom,
            })
            if not exists:
                apps_created += 1
                nom_doc = {
                    "id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "client_id": client_id,
                    "application_type": ApplicationType.ROI_NOMINATION.value,
                    "country": "AU",
                    "authority_or_state": state_nom,
                    "subclass_or_stream": "190/491",
                    "applicant_type": "primary",
                    "applicant_name": case.get("client_name"),
                    "reference_identifier": None,
                    "status": ApplicationStatus.SUBMITTED.value,
                    "status_source": "manual_entry",
                    "responsible_staff_id": case.get("case_manager_id"),
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
                if apply:
                    await db["case_applications"].insert_one(nom_doc)

    logger.info("[CASES] Processed %d cases; %d application records planned/created", cases_count, apps_created)
    logger.info("Migration completed successfully (Mode: %s)", "APPLY" if apply else "DRY-RUN")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="LEAMSS Case Workspace v1 Schema Migration")
    parser.add_argument("--apply", action="store_true", help="Apply migrations to database (default is dry-run)")
    parser.add_argument("--mongo-url", default=os.environ.get("MONGO_URL", "mongodb://localhost:27017"), help="MongoDB URL")
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "leamss"), help="Database name")
    args = parser.parse_args()

    asyncio.run(run_migration(apply=args.apply, mongo_url=args.mongo_url, db_name=args.db_name))


if __name__ == "__main__":
    main()
