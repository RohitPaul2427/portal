"""One-time / re-runnable repair for the AU occupation_master collection.

Fixes reported by the consultant:
  1. Valid ANZSCO 2013 (v1.3) GSM occupations (e.g. 139914 Quality Assurance Managers) were
     wrongly flagged status='superseded' and therefore hidden from search / AI matching / reports.
  2. Many active AU occupations were missing an `assessing_authority`, which is required to show the
     skill-assessment body + fee on the pre-assessment report.

Actions (idempotent):
  • Un-supersede every 6-digit numeric AU code on ANZSCO 1.3 or 2022 (real occupations).
  • Fill a missing `assessing_authority.name` using the standard ANZSCO-prefix → authority mapping.
  • Give the specifically-reported codes correct GSM (189/190/491) visa eligibility on the MLTSSL.

Run:  python -m core.migrations.repair_au_occupations
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

# ── Standard ANZSCO-prefix → Australian assessing authority map ─────────────
# Longest prefix wins. Covers the common skilled-migration authorities; VETASSESS
# is the default general professional/managerial assessor for anything unmatched.
AUTHORITY_BY_PREFIX = [
    # ICT — Australian Computer Society
    ("261", "ACS"), ("262", "ACS"), ("263", "ACS"), ("135111", "ACS"),
    # Engineering — Engineers Australia
    ("233", "Engineers Australia"), ("2339", "Engineers Australia"),
    ("312", "Engineers Australia"),  # engineering technicians (EA / VETASSESS)
    # Accounting / Audit / Finance
    ("2211", "CPA Australia / CA ANZ / IPA"), ("221213", "CPA Australia / CA ANZ / IPA"),
    ("2212", "CPA Australia / CA ANZ / IPA"),
    # Architecture & building/surveying
    ("2321", "Architects Accreditation Council of Australia (AACA)"),
    ("2322", "Surveying and Spatial Sciences Institute (SSSI)"),
    # Medical & health
    ("2531", "Australian Medical Council (AMC)"), ("2532", "Australian Medical Council (AMC)"),
    ("2533", "Australian Medical Council (AMC)"), ("2534", "Australian Medical Council (AMC)"),
    ("2535", "Australian Medical Council (AMC)"), ("2539", "Australian Medical Council (AMC)"),
    ("254", "Australian Nursing and Midwifery Accreditation Council (ANMAC)"),
    ("2523", "Australian Dental Council (ADC)"),
    ("2515", "Australian Pharmacy Council (APharmC)"),
    ("2524", "Occupational Therapy Council (OTC)"),
    ("2525", "Australian Physiotherapy Council (APC)"),
    ("2526", "Australian Podiatry Council"),
    ("2527", "self / speech & audiology boards"),
    ("2514", "Optometry Council of Australia and New Zealand (OCANZ)"),
    ("2519", "VETASSESS"),
    # Psychology / social / welfare
    ("2723", "Australian Psychological Society (APS)"),
    ("2725", "Australian Association of Social Workers (AASW)"),
    # Teaching
    ("2411", "Australian Institute for Teaching and School Leadership (AITSL)"),
    ("2412", "Australian Institute for Teaching and School Leadership (AITSL)"),
    ("2413", "Australian Institute for Teaching and School Leadership (AITSL)"),
    ("2414", "Australian Institute for Teaching and School Leadership (AITSL)"),
    ("2415", "Australian Institute for Teaching and School Leadership (AITSL)"),
    # Law
    ("2711", "State/Territory Legal Admissions Authority"),
    ("2713", "State/Territory Legal Admissions Authority"),
    # Veterinary
    ("2347", "Australasian Veterinary Boards Council (AVBC)"),
    # Medical laboratory science
    ("234611", "Australian Institute of Medical and Clinical Scientists (AIMS)"),
    # Trades → Trades Recognition Australia
    ("32", "Trades Recognition Australia (TRA)"), ("33", "Trades Recognition Australia (TRA)"),
    ("34", "Trades Recognition Australia (TRA)"), ("35", "Trades Recognition Australia (TRA)"),
    ("3411", "Trades Recognition Australia (TRA)"),  # electricians
    ("3341", "Trades Recognition Australia (TRA)"),  # plumbers
    ("351", "Trades Recognition Australia (TRA)"),   # chefs/cooks
    ("36", "Trades Recognition Australia (TRA)"), ("39", "Trades Recognition Australia (TRA)"),
]

DEFAULT_AUTHORITY = "VETASSESS"

# Codes the consultant specifically reported / that are known MLTSSL GSM occupations.
MLTSSL_FIXES = {
    "139914": "VETASSESS",
    "224113": "VETASSESS",
    "224711": "VETASSESS",
    "234518": "VETASSESS",
    "334111": "Trades Recognition Australia (TRA)",
}


def authority_for(code: str) -> str:
    code = str(code or "")
    best = ("", DEFAULT_AUTHORITY)
    for prefix, name in AUTHORITY_BY_PREFIX:
        if code.startswith(prefix) and len(prefix) > len(best[0]):
            best = (prefix, name)
    return best[1]


def _gsm_visa_block() -> dict:
    return {
        "visa_eligibility": [
            {"visa_subclass": "189", "eligible": True, "list": "MLTSSL"},
            {"visa_subclass": "190", "eligible": True, "list": "MLTSSL"},
            {"visa_subclass": "491", "eligible": True, "list": "MLTSSL"},
        ],
        "pathway_lists": ["MLTSSL"],
    }


async def run() -> dict:
    from core.database import db
    coll = db["occupation_master"]
    now = datetime.now(timezone.utc).isoformat()
    report = {"unsuperseded": 0, "authority_filled": 0, "mltssl_fixed": 0}

    # 1. Un-supersede real 6-digit AU codes on 1.3 / 2022
    async for occ in coll.find(
        {"country_code": "AU", "status": "superseded",
         "classification_version": {"$in": ["1.3", "2022"]}},
        {"_id": 0, "code": 1},
    ):
        code = str(occ.get("code") or "")
        if code.isdigit() and len(code) == 6:
            await coll.update_one({"country_code": "AU", "code": code},
                                  {"$set": {"status": "verified", "updated_at": now,
                                            "repair_note": "un-superseded valid GSM code"}})
            report["unsuperseded"] += 1

    # 2. Fill missing assessing authority on active AU occupations
    async for occ in coll.find(
        {"country_code": "AU", "status": {"$ne": "superseded"}},
        {"_id": 0, "code": 1, "assessing_authority": 1},
    ):
        code = str(occ.get("code") or "")
        if not (code.isdigit() and len(code) == 6):
            continue
        if (occ.get("assessing_authority") or {}).get("name"):
            continue
        name = MLTSSL_FIXES.get(code) or authority_for(code)
        await coll.update_one({"country_code": "AU", "code": code}, {"$set": {
            "assessing_authority": {"name": name, "source": "repair_prefix_map"},
            "updated_at": now,
        }})
        report["authority_filled"] += 1

    # 3. Give the reported codes correct GSM (189/190/491) MLTSSL eligibility if missing
    for code in MLTSSL_FIXES:
        occ = await coll.find_one({"country_code": "AU", "code": code}, {"_id": 0, "visa_pathways": 1})
        if not occ:
            continue
        vp = occ.get("visa_pathways") or {}
        if not (vp.get("visa_eligibility") or vp.get("pathway_lists")):
            await coll.update_one({"country_code": "AU", "code": code},
                                  {"$set": {"visa_pathways": _gsm_visa_block(), "updated_at": now}})
            report["mltssl_fixed"] += 1

    return report


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(asyncio.run(run()))
