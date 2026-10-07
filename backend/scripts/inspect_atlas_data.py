import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["leamss"]
    for code in ["261313", "254499", "233211", "311211", "111111"]:
        doc = await db["occupation_master"].find_one({"code": code})
        if doc:
            print(f"=== {code}: {doc.get('title')} ===")
            print("state_ratings:", doc.get("state_ratings"))
            print("state_demand:", doc.get("state_demand"))
            print("migroto_state_programs:", doc.get("migroto_state_programs"))
            print("pathway_list:", doc.get("pathway_list"))
            print("visa_pathways:", doc.get("visa_pathways"))

    # Also inspect au_states_master documents
    states = await db["au_states_master"].find({}).to_list(100)
    print("\n--- au_states_master docs ---")
    for s in states:
        s_clean = {k: v for k, v in s.items() if k != "_id"}
        print(s_clean)

asyncio.run(main())
