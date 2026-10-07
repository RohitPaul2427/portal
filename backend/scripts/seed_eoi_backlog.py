import asyncio
import os
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.database import db
from routers.eoi_backlog import build_eoi_for_occupation, _ensure_indexes, _parse_dataframe

EXCEL_PATH = backend_dir.parent / "scripts" / "data" / "skillselect_eoi_2026-07.xlsx"


async def seed_eoi_backlog():
    coll = db["eoi_backlog"]
    await _ensure_indexes()

    if not EXCEL_PATH.exists():
        print(f"Error: {EXCEL_PATH} does not exist.")
        return

    print(f"Reading official DHA SkillSelect export from {EXCEL_PATH}...")
    df = pd.read_excel(str(EXCEL_PATH))
    docs = _parse_dataframe(df)
    print(f"Parsed {len(docs):,} official DHA EOI records.")

    # Drop old faulty index if exists
    indexes = await coll.index_information()
    if "as_at_month_1_occupation_code_1_visa_subclass_1_points_1" in indexes:
        await coll.drop_index("as_at_month_1_occupation_code_1_visa_subclass_1_points_1")

    # Remove any mock/dummy 2026-02-01 data
    await coll.delete_many({"as_at_month": "2026-02-01"})

    months = sorted({d["as_at_month"] for d in docs})
    await coll.delete_many({"as_at_month": {"$in": months}})

    for i in range(0, len(docs), 2000):
        await coll.insert_many(docs[i:i + 2000])

    final_count = await coll.count_documents({})
    print(f"✔ Successfully seeded official DHA EOI Backlog: {final_count:,} total records across months {months}.")

    # Test verify
    eoi = await build_eoi_for_occupation("261313", 80)
    if eoi:
        print("Verification for 261313 Software Engineer:")
        for sc in eoi.get("subclasses", []):
            print(f"  Subclass {sc['subclass']}: Total in pool = {sc['total']:,}")


if __name__ == "__main__":
    asyncio.run(seed_eoi_backlog())
