import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["leamss"]
    codes = [
        "261313", "254499", "221111", "111111",
        "311211", "321211", "351311", "233211",
        "241213", "141111"
    ]
    for code in codes:
        doc = await db["occupation_master"].find_one({"code": code, "country_code": "AU"})
        if not doc:
            doc = await db["occupation_master"].find_one({"code": code})
        if doc:
            title = doc.get("title")
            pl = doc.get("pathway_list")
            min_pts = doc.get("min_invitation_points") or {}
            ste = doc.get("state_territory_eligibility") or {}
            sr = doc.get("state_ratings") or {}
            sd = doc.get("state_demand") or {}
            print(f"=== {code}: {title} (List: {pl}) ===")
            print(f"  Min Points: {min_pts}")
            print(f"  State Demand: {sd}")
            print(f"  State Ratings: {sr}")
            # print sample states
            for st in ["NSW", "VIC", "WA", "QLD", "SA", "TAS", "ACT", "NT"]:
                s_info = ste.get(st, {})
                print(f"    {st}: 190={s_info.get('eligible_190')} 491={s_info.get('eligible_491')} demand={s_info.get('demand')} rating={s_info.get('rating')} label={s_info.get('rating_label')}")
asyncio.run(check())
