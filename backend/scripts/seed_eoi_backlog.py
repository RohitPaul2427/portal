import asyncio
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

backend_dir = r"c:\Users\Rohit Alluri\Downloads\LEAMSS-main (1)\LEAMSS-main\backend"
sys.path.insert(0, backend_dir)

from core.database import db
from routers.eoi_backlog import build_eoi_for_occupation, _ensure_indexes

CURRENT_MONTH = "2026-02-01"

async def seed_eoi_backlog():
    coll = db["eoi_backlog"]
    occ_coll = db["occupation_master"]
    
    await _ensure_indexes()
    
    total_occs = await occ_coll.count_documents({"country_code": "AU"})
    print(f"Seeding EOI Backlog for {total_occs} AU occupations...")
    
    docs_to_insert = []
    
    # Standard points distribution bands in SkillSelect
    points_bands = [65, 70, 75, 80, 85, 90, 95, 100]
    
    async for occ in occ_coll.find({"country_code": "AU"}, {"code": 1, "title": 1, "pathway_list": 1}):
        code = str(occ.get("code")).strip()
        title = occ.get("title", "")
        list_name = occ.get("pathway_list", "MLTSSL")
        
        # Subclasses eligible
        subclasses = ["189", "190", "491"] if list_name == "MLTSSL" else ["190", "491"]
        
        for sc in subclasses:
            for pts in points_bands:
                # Realistic distribution: bell curve peaking at 75-85
                if pts < 75:
                    count = 45 if sc != "189" else 15
                elif pts == 75 or pts == 80:
                    count = 120 if sc == "190" else 85
                elif pts == 85 or pts == 90:
                    count = 65 if sc == "190" else 40
                else:
                    count = 15
                
                docs_to_insert.append({
                    "as_at_month": CURRENT_MONTH,
                    "visa_subclass": sc,
                    "visa_stream_code": "NSW" if sc == "190" else ("REG" if sc == "491" else "IND"),
                    "visa_stream": "State/Territory Nominated" if sc == "190" else ("Regional" if sc == "491" else "Points-tested"),
                    "occupation_code": code,
                    "occupation_title": title,
                    "eoi_status": "SUBMITTED",
                    "points": pts,
                    "count": count,
                    "count_raw": str(count),
                    "suppressed": False,
                })
        
        if len(docs_to_insert) >= 5000:
            await coll.insert_many(docs_to_insert)
            docs_to_insert = []
            print(f"  Inserted batch... Total docs so far: {await coll.count_documents({})}")
            
    if docs_to_insert:
        await coll.insert_many(docs_to_insert)
        
    final_count = await coll.count_documents({})
    print(f"✔ Successfully seeded EOI Backlog: {final_count} total records.")
    
    # Test verify
    eoi = await build_eoi_for_occupation("261313", 80)
    print("Testing build_eoi_for_occupation('261313', 80):", bool(eoi))
    if eoi:
        print("  Client Bracket:", eoi.get("client_bracket"))
        print("  Subclasses in pool:", eoi.get("unified", {}).get("subclasses"))
        print("  Table rows:", len(eoi.get("unified", {}).get("rows", [])))

if __name__ == "__main__":
    asyncio.run(seed_eoi_backlog())
