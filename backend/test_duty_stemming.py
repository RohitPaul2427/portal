"""Test semantic domain mapping for duties."""
import re

SYNONYM_DOMAINS = {
    "software_dev": {
        "roots": ["program", "code", "develop", "softwar", "api", "microservic", "backend", "frontend", "fullstack", "script", "comput", "algorithm", "architect", "datab", "sql", "git", "cloud", "aws", "docker", "deploy", "debug", "test", "optimis", "framework"],
        "occ_codes": ["261311", "261312", "261313", "261399", "261111", "261112", "262111", "262112", "262113"],
    },
    "culinary_hospitality": {
        "roots": ["cook", "chef", "culinari", "kitchen", "food", "menu", "platter", "salad", "appet", "dessert", "hygien", "haccp", "dish", "meal", "baker", "pastri", "restaur", "hotel", "cater"],
        "occ_codes": ["351311", "351411", "351111", "141111", "141311"],
    },
    "legal_practice": {
        "roots": ["law", "legal", "solicitor", "advocate", "barrister", "litigat", "court", "counsel", "brief", "draft", "contract", "plead", "judg", "tribun", "conveyanc", "client"],
        "occ_codes": ["271311", "271111", "271214", "271299", "599112", "599214"],
    },
    "clinical_biotech": {
        "roots": ["clinic", "trial", "biomarker", "biotech", "laboratori", "bioch", "pharmac", "patient", "protocol", "gcp", "fda", "regul", "experi", "specimen", "cell", "molecul", "genom"],
        "occ_codes": ["234599", "234511", "234513", "234514", "234518", "511112", "139999"],
    },
    "nursing_healthcare": {
        "roots": ["nurse", "nurs", "patient", "ward", "icu", "medic", "care", "dosag", "triage", "vitals", "clinic", "hospital", "doctor", "physician", "health"],
        "occ_codes": ["254411", "254412", "254413", "254414", "254415", "254418", "254421", "254422", "254423", "254499", "253111", "253112"],
    },
    "accounting_finance": {
        "roots": ["account", "tax", "audit", "balanc", "ledger", "financ", "invoic", "reconcil", "budget", "asset", "profit", "cpa", "fiscal", "expens"],
        "occ_codes": ["221111", "221112", "221113", "222311", "222312"],
    },
    "civil_construction": {
        "roots": ["civil", "structur", "build", "construct", "site", "concret", "draw", "cad", "bim", "foundat", "drainag", "road", "infrastruct"],
        "occ_codes": ["233211", "233212", "233214", "233215", "312211", "312212"],
    },
    "mechanical_eng": {
        "roots": ["mechan", "hvac", "thermodynam", "pip", "pump", "engin", "machin", "robot", "fabric", "vehicl"],
        "occ_codes": ["233512", "233513", "312511", "312512"],
    },
    "electrical_eng": {
        "roots": ["electr", "power", "circuit", "voltag", "substat", "generat", "wiring", "transmiss", "cabl"],
        "occ_codes": ["233311", "312311", "341111"],
    },
    "teaching_education": {
        "roots": ["teach", "lesson", "student", "class", "curriculum", "pupil", "school", "educ", "pedagogi", "kindergarten", "preschool"],
        "occ_codes": ["241111", "241213", "241411", "242111"],
    },
}

def stem(word: str) -> str:
    w = word.lower()
    for sfx in ["ing", "tion", "sions", "sion", "ed", "es", "ies", "ers", "er", "ly", "ment", "ments", "s"]:
        if len(w) > len(sfx) + 3 and w.endswith(sfx):
            return w[:-len(sfx)]
    return w

def score_duty_alignment(cand_duties_text: str, occ_tasks: list, occ_code: str) -> tuple:
    cand_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', cand_duties_text.lower())}
    
    # 1. Direct task overlap
    matched_tasks = []
    for task in occ_tasks:
        task_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', task.lower())}
        common = cand_words.intersection(task_words)
        if len(common) >= 2 or (len(common) == 1 and any(c in ["program", "code", "design", "test", "architect", "cook", "menu", "court", "law"] for c in common)):
            matched_tasks.append((task, list(common)))
            
    pct = (len(matched_tasks) / len(occ_tasks) * 100.0) if occ_tasks else 0.0
    
    # 2. Domain root synergy
    domain_boost = 0
    for dom_name, dom_info in SYNONYM_DOMAINS.items():
        if occ_code in dom_info["occ_codes"]:
            dom_matches = [r for r in dom_info["roots"] if any(w.startswith(r) for w in cand_words)]
            domain_boost = len(dom_matches)
            
    return round(pct, 1), matched_tasks, domain_boost

swe_duties = "Lead a team of 6 engineers building microservices in Python and Java. Designed REST APIs, CI/CD pipelines and AWS cloud deployments. Managerial responsibilities including sprint planning and code reviews. Developed full-stack features for banking clients using Java and Angular. Optimised SQL queries and improved application performance by 30%."
import asyncio
from core.database import db

async def run():
    occ = await db['occupation_master'].find_one({'code': '261313', 'country_code': 'AU'})
    tasks = occ.get('tasks') or []
    pct, matched, boost = score_duty_alignment(swe_duties, tasks, '261313')
    print("261313 (Software Engineer):")
    print(f"  Match Pct: {pct}% | Matched {len(matched)}/{len(tasks)} tasks | Domain Roots: {boost}")
    for t, c in matched:
        print(f"   * {t[:60]}... (matched: {c})")
        
    chef_occ = await db['occupation_master'].find_one({'code': '351311', 'country_code': 'AU'})
    tasks = chef_occ.get('tasks') or []
    pct, matched, boost = score_duty_alignment(swe_duties, tasks, '351311')
    print(f"\n351311 (Chef) against SWE Duties: Match Pct={pct}%, Domain Roots={boost}")

asyncio.run(run())
