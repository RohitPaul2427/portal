"""Enrich all AU Occupations with accurate VETASSESS Groups, TRA Trade RTO flags, and ACS categories.

Based on official data from:
  1. VETASSESS and TRA Skills Assessment Briefing (Sept 2026)
  2. ACS ICT Major, ICT Minor and Non-IT Briefing (Sept 2026)
"""
import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db

# ── 1. VETASSESS PROFESSIONAL GROUPS (Appendix A) ────────────────────────────
VETASSESS_GROUP_A = {
    "133111", "133112", "134211", "134213", "134311", "134411", "134412", "134499",
    "212111", "212112", "221214", "224111", "224112", "224113", "224116", "224311",
    "224511", "224512", "224611", "232112", "232213", "232214", "232611", "234111",
    "234112", "234113", "234114", "234115", "234116", "234211", "234212", "234311",
    "234312", "234313", "234314", "234399", "234412", "234413", "234511", "234513",
    "234514", "234515", "234516", "234517", "234518", "234521", "234522", "234599",
    "234912", "234913", "234914", "234915", "234999", "242111", "242112", "242211",
    "249111", "249112", "249311", "251112", "251311", "251312", "251412", "251512",
    "251911", "251999", "252212", "252213", "252711", "271214", "271299", "272111",
    "272112", "272113", "272114", "272115", "272199", "272314", "272414", "272499",
    "411112", "411211", "411214",
}

VETASSESS_GROUP_B = {
    "121111", "121211", "121212", "121611", "121213", "121214", "121215", "121216",
    "121217", "121218", "121221", "121312", "121313", "121314", "121315", "121316",
    "121317", "121318", "121321", "121322", "132111", "132411", "132511", "133311",
    "133312", "133411", "133511", "133512", "133513", "139911", "139912", "139913",
    "139914", "139916", "139915", "139917", "139999", "211111", "211113", "211199",
    "211211", "211212", "211213", "211214", "211299", "211411", "211412", "211413",
    "211499", "212113", "212114", "212211", "212212", "212311", "212312", "212313",
    "212314", "212315", "212316", "212317", "212318", "212399", "212411", "212412",
    "212413", "212414", "212415", "212416", "212499", "221211", "222211", "222212",
    "222213", "222299", "222311", "222312", "223111", "223112", "223113", "223311",
    "224211", "224212", "224213", "224214", "224412", "224711", "224713", "224712",
    "224714", "224911", "224912", "224913", "224914", "224999", "225111", "225112",
    "225113", "225114", "225211", "225212", "225213", "225311", "225411", "225412",
    "225499", "231113", "231199", "231211", "231299", "232311", "232312", "232313",
    "232411", "232412", "232413", "232511", "249211", "249213", "249214", "249299",
    "272611", "272612",
}

VETASSESS_GROUP_C = {
    "141111", "141211", "141311", "141411", "141911", "141912", "141999", "142111",
    "142112", "142113", "142114", "142115", "142116", "149111", "149112", "149113",
    "149211", "149212", "149311", "149411", "149412", "149413", "149911", "149912",
    "149913", "149914", "149915", "149999", "211112", "211311", "222111", "222112",
    "222113", "222199", "249212", "311111", "311112", "311113", "311114", "311115",
    "311311", "311312", "311313", "311314", "311399", "311411", "311412", "311413",
    "311414", "311415", "311499", "312111", "312112", "312113", "312114", "312115",
    "312116", "312199", "312211", "312212", "312611", "312911", "312912", "312913",
    "312914", "312999", "399312", "399912", "411111", "411412", "411511", "411611",
    "431411", "451311", "452321", "511111", "511112", "512111", "512211", "512299",
    "521111", "521211", "521212", "599111", "599112", "599613", "612113", "639211",
}

VETASSESS_GROUP_D = {
    "121311", "311214", "311215", "361111", "361114", "361115", "361211", "361311",
    "362512", "362712", "393299", "399599", "399911", "411311", "441211", "442216",
    "451111", "451211", "451399", "451412", "451612", "451711", "451799", "451815",
    "452311", "452313", "452314", "452318", "452322", "452323", "452411", "452412",
    "452414", "452499", "541111", "599211", "599212", "599213", "599214", "599215",
    "599611", "599612", "599915", "611111", "611112", "611211", "612111", "612112",
    "612114", "612115", "639212",
}

# ── 2. VETASSESS TRADE OCCUPATIONS AS TRA-APPROVED RTO (Appendix B & C) ──────
VETASSESS_TRADE_CODES = {
    "321111": {"title": "Automotive Electrician", "licensed": True},
    "321211": {"title": "Motor Mechanic (General)", "licensed": False},
    "321212": {"title": "Diesel Motor Mechanic", "licensed": False},
    "322211": {"title": "Sheetmetal Trades Worker", "licensed": False},
    "322311": {"title": "Metal Fabricator", "licensed": False},
    "322313": {"title": "Welder (First Class)", "licensed": False},
    "323211": {"title": "Fitter (General)", "licensed": False},
    "323212": {"title": "Fitter and Turner", "licensed": False},
    "323214": {"title": "Metal Machinist (First Class)", "licensed": False},
    "323412": {"title": "Toolmaker", "licensed": False},
    "324111": {"title": "Panelbeater", "licensed": False},
    "331111": {"title": "Bricklayer", "licensed": False},
    "331211": {"title": "Carpenter and Joiner", "licensed": False},
    "331212": {"title": "Carpenter", "licensed": False},
    "331213": {"title": "Joiner", "licensed": False},
    "334111": {"title": "Plumber (General)", "licensed": True},
    "341111": {"title": "Electrician (General)", "licensed": True},
    "341112": {"title": "Electrician (Special Class)", "licensed": True},
    "342111": {"title": "Airconditioning and Refrigeration Mechanic", "licensed": True},
    "342313": {"title": "Electronic Equipment Trades Worker", "licensed": False},
    "351111": {"title": "Baker", "licensed": False},
    "351311": {"title": "Chef", "licensed": False},
    "351411": {"title": "Cook", "licensed": False},
    "391111": {"title": "Hairdresser", "licensed": False},
    "394111": {"title": "Cabinetmaker", "licensed": False},
}

# ── 3. ACS OCCUPATION CATEGORIES (PDF 2) ─────────────────────────────────────
ACS_DATA_SCIENCE_CODES = {"224114", "224115", "224999"}
ACS_CYBER_SECURITY_CODES = {"261315", "261317", "262114", "262115", "262116", "262117", "262118"}
ACS_GENERAL_IT_CODES = {
    "135111", "135112", "135199", "223211", "261111", "261112", "261211", "261212",
    "261311", "261312", "261313", "261314", "261316", "261399", "262111", "262112",
    "262113", "263111", "263112", "263113", "263211", "263212", "263213", "263299", "313113",
}
ALL_ACS_CODES = ACS_DATA_SCIENCE_CODES | ACS_CYBER_SECURITY_CODES | ACS_GENERAL_IT_CODES


async def main():
    col = db["occupation_master"]
    print("Starting enrichment of AU occupation masters...")
    
    updated_count = 0
    async for occ in col.find({"country_code": "AU"}):
        code = str(occ.get("code") or "")
        updates = {}
        
        # 1. VETASSESS Group assignment
        if code in VETASSESS_GROUP_A:
            updates["vetassess_group"] = "A"
            updates["assessment_group"] = "Group A"
            updates["qualifying_deduction_years"] = 1.0
            updates["pre_qualification_allowed"] = False
        elif code in VETASSESS_GROUP_B:
            updates["vetassess_group"] = "B"
            updates["assessment_group"] = "Group B"
            updates["qualifying_deduction_years"] = 1.0  # standard for relevant major
            updates["pre_qualification_allowed"] = True
        elif code in VETASSESS_GROUP_C:
            updates["vetassess_group"] = "C"
            updates["assessment_group"] = "Group C"
            updates["qualifying_deduction_years"] = 1.0
            updates["pre_qualification_allowed"] = True
        elif code in VETASSESS_GROUP_D:
            updates["vetassess_group"] = "D"
            updates["assessment_group"] = "Group D"
            updates["qualifying_deduction_years"] = 1.0
            updates["pre_qualification_allowed"] = True

        # 2. VETASSESS Trade as TRA RTO
        if code in VETASSESS_TRADE_CODES:
            trade_info = VETASSESS_TRADE_CODES[code]
            updates["is_trade_occupation"] = True
            updates["vetassess_approved_rto"] = True
            updates["is_licensed_trade"] = trade_info["licensed"]
            updates["tra_rto_program"] = "OSAP / TSS"
            updates["qualifying_deduction_years"] = 3.0 if not trade_info["licensed"] else 4.0

        # 3. ACS Category & RPL Flag
        if code in ALL_ACS_CODES:
            updates["assessing_body"] = "ACS"
            if code in ACS_DATA_SCIENCE_CODES:
                updates["acs_category"] = "Data Science"
            elif code in ACS_CYBER_SECURITY_CODES:
                updates["acs_category"] = "Cyber Security"
            else:
                updates["acs_category"] = "General IT"
            updates["requires_rpl_for_non_ict"] = True
            updates["acs_rpl_experience_years"] = 6.0
            updates["acs_standard_deduction_years"] = 2.0

        if updates:
            await col.update_one({"_id": occ["_id"]}, {"$set": updates})
            updated_count += 1

    print(f"Successfully enriched {updated_count} AU occupations with VETASSESS groups, TRA RTO flags, and ACS categories.")


if __name__ == "__main__":
    asyncio.run(main())
