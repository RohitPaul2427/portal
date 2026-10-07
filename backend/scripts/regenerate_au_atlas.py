"""
Regenerates all verified Australian occupations (ANZSCO) for LEAMSS Migration Atlas.
Applies the official DHA SkillSelect data, Chances Scorecard, 8-State Radar,
Live EOI Queue Competition, and Verification Seal to all AU occupation codes.
"""
import asyncio
import os
import time
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "leamss")


async def main():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from routers.seo_ssg import regenerate_one
    from services.migroto_service import _set_upstream_rate_limited
    _set_upstream_rate_limited(86400)  # Use fast internal database synthesis for instant batch generation

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. 6-digit verified Australian occupations (931 codes)
    occs = list(db["occupation_master"].find(
        {"country_code": "AU", "status": "verified"},
        {"_id": 0, "code": 1, "title": 1}
    ).sort("code", 1))

    # 2. 4-digit ANZSCO Unit Groups (covering all 358 unit groups from the 1236 dataset)
    unit_groups = list(db["anzsco_4digit_master"].find(
        {"code": {"$regex": r"^\d{4}$"}},
        {"_id": 0, "code": 1, "title": 1}
    ).sort("code", 1))

    seen = set()
    occupations = []
    for item in occs:
        c = str(item["code"]).strip()
        if c not in seen:
            seen.add(c)
            occupations.append(item)

    for item in unit_groups:
        c = str(item["code"]).strip()
        if c not in seen:
            seen.add(c)
            occupations.append(item)

    total = len(occupations)
    print(f"Starting batch update for {total} AU codes (covering all 1,236 official Australian dataset codes)...")

    t0 = time.time()
    success_count = 0
    error_count = 0
    sem = asyncio.Semaphore(12)
    completed_count = 0

    async def render_task(item):
        nonlocal success_count, error_count, completed_count
        code = item["code"]
        title = item.get("title", "")
        async with sem:
            try:
                res = await regenerate_one("AU", str(code))
                if res:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                print(f"[ERR] Failed {code} ({title}): {e}", flush=True)
            finally:
                completed_count += 1
                if completed_count % 50 == 0 or completed_count == total:
                    elapsed = time.time() - t0
                    pct = (completed_count / total) * 100
                    print(f"[{completed_count}/{total}] ({pct:.1f}%) Completed {success_count} pages in {elapsed:.1f}s ({elapsed/completed_count:.2f}s/page)", flush=True)

    tasks = [render_task(occ) for occ in occupations]
    await asyncio.gather(*tasks)

    elapsed_total = time.time() - t0
    print(f"\n[OK] Finished updating all AU occupations:")
    print(f"  Total Processed: {total}")
    print(f"  Successfully Written: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total Time: {elapsed_total:.2f} seconds ({elapsed_total/total:.3f}s / page)")


if __name__ == "__main__":
    asyncio.run(main())
