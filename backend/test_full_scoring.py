"""Test script for full smart scoring engine."""
import asyncio
import re
from core.database import db
from core.skills_assessment_engine import evaluate_skills_assessment
from core.resume_extractor import parse_resume_heuristically

STOP_WORDS = {
    "with", "and", "the", "for", "years", "year", "experience", "holds", "held",
    "master", "masters", "bachelor", "bachelors", "degree", "client", "current",
    "role", "roles", "work", "worked", "working", "job", "candidate", "profile",
    "overall", "total", "skills", "assessment", "level", "post", "have", "has",
    "from", "also", "been", "their", "this", "that", "these", "those", "under",
    "over", "into", "onto", "education", "qualified", "qualifications", "completed",
    "history", "details", "applicant", "primary", "full", "time", "general", "responsible",
    "duties", "including", "across", "various", "multiple", "using", "well"
}

SYNONYM_DOMAINS = {
    "software_dev": {
        "roots": ["program", "code", "develop", "softwar", "api", "microservic", "backend", "frontend", "fullstack", "script", "comput", "algorithm", "architect", "datab", "sql", "git", "cloud", "aws", "docker", "deploy", "debug", "test", "optimis", "framework"],
        "occ_codes": ["261311", "261312", "261313", "261399", "261111", "261112", "262111", "262112", "262113"],
        "industries": ["Professional, Scientific and Technical Services", "Financial and Insurance Services", "Information Media and Telecommunications"],
    },
    "culinary_hospitality": {
        "roots": ["cook", "chef", "culinari", "kitchen", "food", "menu", "platter", "salad", "appet", "dessert", "hygien", "haccp", "dish", "meal", "baker", "pastri", "restaur", "hotel", "cater", "garde"],
        "occ_codes": ["351311", "351411", "351111", "141111", "141311"],
        "industries": ["Accommodation and Food Services"],
    },
    "legal_practice": {
        "roots": ["law", "legal", "solicitor", "advocate", "barrister", "litigat", "court", "counsel", "brief", "draft", "contract", "plead", "judg", "tribun", "conveyanc", "client"],
        "occ_codes": ["271311", "271111", "271214", "271299", "599112", "599214"],
        "industries": ["Professional, Scientific and Technical Services", "Public Administration and Safety"],
    },
    "clinical_biotech": {
        "roots": ["clinic", "trial", "biomarker", "biotech", "laboratori", "bioch", "pharmac", "patient", "protocol", "gcp", "fda", "regul", "experi", "specimen", "cell", "molecul", "genom"],
        "occ_codes": ["234599", "234511", "234513", "234514", "234518", "511112", "139999"],
        "industries": ["Professional, Scientific and Technical Services", "Health Care and Social Assistance"],
    },
    "nursing_healthcare": {
        "roots": ["nurse", "nurs", "patient", "ward", "icu", "medic", "care", "dosag", "triage", "vitals", "clinic", "hospital", "doctor", "physician", "health"],
        "occ_codes": ["254411", "254412", "254413", "254414", "254415", "254418", "254421", "254422", "254423", "254499", "253111", "253112"],
        "industries": ["Health Care and Social Assistance"],
    },
    "accounting_finance": {
        "roots": ["account", "tax", "audit", "balanc", "ledger", "financ", "invoic", "reconcil", "budget", "asset", "profit", "cpa", "fiscal", "expens"],
        "occ_codes": ["221111", "221112", "221113", "222311", "222312"],
        "industries": ["Financial and Insurance Services", "Professional, Scientific and Technical Services"],
    },
    "civil_construction": {
        "roots": ["civil", "structur", "build", "construct", "site", "concret", "draw", "cad", "bim", "foundat", "drainag", "road", "infrastruct"],
        "occ_codes": ["233211", "233212", "233214", "233215", "312211", "312212"],
        "industries": ["Construction", "Professional, Scientific and Technical Services"],
    },
}

def stem(word: str) -> str:
    w = word.lower()
    for sfx in ["ing", "tion", "sions", "sion", "ed", "es", "ies", "ers", "er", "ly", "ment", "ments", "s"]:
        if len(w) > len(sfx) + 3 and w.endswith(sfx):
            return w[:-len(sfx)]
    return w

def calculate_duty_alignment(cand_duties_text: str, occ_tasks: list, occ_code: str) -> tuple:
    cand_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', cand_duties_text.lower()) if w not in STOP_WORDS}
    
    matched_tasks = []
    for task in occ_tasks:
        task_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', task.lower()) if w not in STOP_WORDS}
        common = cand_words.intersection(task_words)
        if len(common) >= 2 or (len(common) == 1 and any(c in ["program", "code", "design", "test", "architect", "cook", "menu", "court", "law", "develop", "api"] for c in common)):
            matched_tasks.append((task, list(common)))
            
    pct = (len(matched_tasks) / len(occ_tasks) * 100.0) if occ_tasks else 0.0
    
    domain_boost = 0
    for dom_name, dom_info in SYNONYM_DOMAINS.items():
        if occ_code in dom_info["occ_codes"]:
            dom_matches = [r for r in dom_info["roots"] if any(w.startswith(r) for w in cand_words)]
            domain_boost = len(dom_matches)
            
    return round(pct, 1), matched_tasks, domain_boost

def calculate_company_alignment(company_nature: str, occ_industries: list) -> tuple:
    if not company_nature or not occ_industries:
        return False, "Industry context neutral"
        
    cn_lower = company_nature.lower()
    for ind in occ_industries:
        ind_lower = ind.lower()
        if "information technology" in cn_lower and ("professional" in ind_lower or "information" in ind_lower or "financial" in ind_lower):
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
        if "hospitality" in cn_lower and ("accommodation" in ind_lower or "food" in ind_lower):
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
        if "healthcare" in cn_lower and ("health" in ind_lower or "social" in ind_lower):
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
        if "banking" in cn_lower and ("financial" in ind_lower or "insurance" in ind_lower):
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
        if "legal" in cn_lower and ("professional" in ind_lower or "public" in ind_lower):
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
        if "construction" in cn_lower and "construction" in ind_lower:
            return True, f"Company sector '{company_nature}' aligns with '{ind}'"
    return False, f"Sector '{company_nature}' outside primary industries"

def calculate_age_gsm_points(age: int) -> tuple:
    if 18 <= age <= 24:
        return 25, f"Age {age} secures 25 GSM points (18-24 bracket)."
    if 25 <= age <= 32:
        return 30, f"Age {age} secures maximum 30 GSM points (25-32 bracket)."
    if 33 <= age <= 39:
        return 25, f"Age {age} secures 25 GSM points (33-39 bracket)."
    if 40 <= age <= 44:
        return 15, f"Age {age} secures 15 GSM points (40-44 bracket)."
    return 0, f"Age {age} is outside GSM points eligibility threshold (45+)."

async def test():
    with open("../test_data/sample_resume.txt", "r", encoding="utf-8") as f:
        t1 = f.read()
    p1 = parse_resume_heuristically(t1)
    
    # Duties text
    duties_list = [w.get("duties") for w in p1.get("work_history", []) if w.get("duties")]
    duties_text = " ".join(duties_list)
    comp_nature = p1.get("primary_applicant", {}).get("professional", {}).get("employer_nature", "")
    age = p1.get("primary_applicant", {}).get("personal", {}).get("age", 30)
    
    print("=== TESTING RESUME 1: RAJESH KUMAR ===")
    print("Duties text:", duties_text)
    print("Company nature:", comp_nature)
    print("Age:", age)
    
    # Check top codes
    test_codes = ["261313", "261312", "261311", "351311", "225113"]
    for code in test_codes:
        occ = await db['occupation_master'].find_one({'code': code, 'country_code': 'AU'})
        if occ:
            tasks = occ.get('tasks') or occ.get('typical_tasks') or []
            pct, matched, boost = calculate_duty_alignment(duties_text, tasks, code)
            ind_match, ind_reason = calculate_company_alignment(comp_nature, occ.get('industries_ranked') or [])
            sa = evaluate_skills_assessment(occ, p1)
            age_pts, age_reason = calculate_age_gsm_points(age)
            print(f"\n[{code}] {occ.get('title')}:")
            print(f"  Duty Match: {pct}% | Matched Tasks: {len(matched)}/{len(tasks)} | Domain Boost: {boost}")
            print(f"  Company Match: {ind_match} ({ind_reason})")
            print(f"  Assessing Authority: {sa.get('authority_name')} | Outcome: {sa.get('assessment_outcome')}")
            print(f"  Deduction: -{sa.get('deducted_years')} yrs | Claimable: {sa.get('points_claimable_years')} yrs ({sa.get('points_claimable_points')} pts)")
            print(f"  Age GSM Points: {age_pts} ({age_reason})")

    print("\n=== TESTING RESUME 2: PRIYA SHARMA ===")
    with open("../test_data/sample_resume_chef.txt", "r", encoding="utf-8") as f2:
        t2 = f2.read()
    p2 = parse_resume_heuristically(t2)
    duties_list2 = [w.get("duties") for w in p2.get("work_history", []) if w.get("duties")]
    duties_text2 = " ".join(duties_list2)
    comp_nature2 = p2.get("primary_applicant", {}).get("professional", {}).get("employer_nature", "")
    age2 = p2.get("primary_applicant", {}).get("personal", {}).get("age", 30)

    for code in ["351311", "351411", "261313", "225113"]:
        occ = await db['occupation_master'].find_one({'code': code, 'country_code': 'AU'})
        if occ:
            tasks = occ.get('tasks') or occ.get('typical_tasks') or []
            pct, matched, boost = calculate_duty_alignment(duties_text2, tasks, code)
            ind_match, ind_reason = calculate_company_alignment(comp_nature2, occ.get('industries_ranked') or [])
            sa = evaluate_skills_assessment(occ, p2)
            age_pts, age_reason = calculate_age_gsm_points(age2)
            title = occ.get('title')
            auth = sa.get('authority_name')
            print(f"[{code}] {title}: Duty={pct}%, Tasks={len(matched)}/{len(tasks)}, Boost={boost}, Comp={ind_match}, Auth={auth}")

asyncio.run(test())
