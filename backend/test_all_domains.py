"""Test script to verify smart occupation matching across all major domains."""
import asyncio
import re
from core.database import db
from core.skills_assessment_engine import evaluate_skills_assessment

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
        "roots": ["nurse", "nurs", "patient", "ward", "icu", "medic", "care", "dosag", "triage", "vitals", "clinic", "hospital", "health"],
        "occ_codes": ["254411", "254412", "254413", "254414", "254415", "254418", "254421", "254422", "254423", "254499"],
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

def score_candidate_occupation(cand: dict, occ: dict) -> tuple:
    # 1. Candidate features
    prof = (cand.get("current_profession") or "").lower()
    qual = (cand.get("qualification") or "").lower()
    field = (cand.get("field_of_study") or "").lower()
    exp_years = float(cand.get("years_experience_total") or 0.0)
    duties_text = cand.get("duties_text") or ""
    cand_comp_nature = (cand.get("company_nature") or "").lower()
    cand_employer = (cand.get("employer_name") or "").lower()

    cand_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', (duties_text + " " + prof + " " + cand_comp_nature).lower()) if w not in STOP_WORDS}

    # 2. Occupation features
    code = str(occ.get("code") or "")
    code_prefix = code[:4]
    title_lower = (occ.get("title") or "").lower()
    group_lower = (occ.get("hierarchy", {}).get("unit_group_name") or occ.get("group") or "").lower()
    alts = [str(x).lower() for x in (occ.get("alternative_titles") or [])]
    tasks = occ.get("tasks") or occ.get("typical_tasks") or []
    industries = occ.get("industries_ranked") or []

    score = 0
    reasons = []

    # --- FACTOR 1: DUTY & RESPONSIBILITIES MATCH ---
    matched_tasks = []
    for task in tasks:
        task_words = {stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', task.lower()) if w not in STOP_WORDS}
        common = cand_words.intersection(task_words)
        if len(common) >= 2 or (len(common) == 1 and any(c in ["program", "code", "design", "test", "architect", "cook", "menu", "court", "law", "develop", "api", "haccp"] for c in common)):
            matched_tasks.append(task)

    duty_pct = (len(matched_tasks) / len(tasks) * 100.0) if tasks else 0.0
    if duty_pct >= 40.0:
        score += 260
        reasons.append(f"High duty overlap ({duty_pct:.1f}% ABS tasks)")
    elif duty_pct >= 25.0:
        score += 180
        reasons.append(f"Strong duty overlap ({duty_pct:.1f}% ABS tasks)")
    elif duty_pct >= 12.0:
        score += 100
        reasons.append(f"Moderate duty overlap ({duty_pct:.1f}% ABS tasks)")

    # Domain root synergy
    for dom_name, dom_info in SYNONYM_DOMAINS.items():
        if code in dom_info["occ_codes"]:
            dom_matches = [r for r in dom_info["roots"] if any(w.startswith(r) for w in cand_words)]
            if dom_matches:
                b = len(dom_matches) * 20
                score += b
                reasons.append(f"Domain terminology match (+{b})")

    # --- FACTOR 2: COMPANY NATURE & INDUSTRY MATCH ---
    is_ind_matched = False
    for ind in industries:
        ind_lower = ind.lower()
        if any(k in cand_comp_nature for k in ["hospitality", "hotel", "food", "restaurant", "catering"]) and ("accommodation" in ind_lower or "food" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("Hospitality company nature aligns with ANZSCO industry")
            break
        elif any(k in cand_comp_nature for k in ["information technology", "software", "it services"]) and ("professional" in ind_lower or "information" in ind_lower or "financial" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("IT company nature aligns with ANZSCO industry")
            break
        elif any(k in cand_comp_nature for k in ["healthcare", "pharma", "pharmaceutical", "clinical", "medical"]) and ("health" in ind_lower or "social" in ind_lower or "professional" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("Healthcare company nature aligns with ANZSCO industry")
            break
        elif re.search(r'\bhospital\b', cand_comp_nature) and ("health" in ind_lower or "social" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("Hospital sector aligns with ANZSCO industry")
            break
        elif any(k in cand_comp_nature for k in ["bank", "finance"]) and ("financial" in ind_lower or "insurance" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("Banking company nature aligns with ANZSCO industry")
            break
        elif any(k in cand_comp_nature for k in ["legal", "law"]) and ("professional" in ind_lower or "public" in ind_lower):
            is_ind_matched = True
            score += 140
            reasons.append("Legal practice aligns with ANZSCO industry")
            break

    # --- FACTOR 3: ASSESSING AUTHORITY BODY EXACT CRITERIA ---
    sa = evaluate_skills_assessment(occ, cand)
    if sa.get("is_positive"):
        score += 120
        reasons.append(f"{sa.get('authority_name')} likely positive outcome")
    else:
        score -= 150
        reasons.append(f"{sa.get('authority_name')} review required")

    deducted = float(sa.get("deducted_years") or 0.0)
    claimable_yrs = float(sa.get("points_claimable_years") or 0.0)
    if deducted <= 2.0:
        score += 80
    elif deducted >= 5.0 and sa.get("rpl_required"):
        # RPL penalty if non-ICT degree
        score -= 80

    if claimable_yrs >= 3.0:
        score += 60

    # --- FACTOR 4: TITLE & DESIGNATION ALIGNMENT ---
    if title_lower and (title_lower in prof or prof in title_lower):
        score += 160
    elif any(alt and (alt in prof or prof in alt) for alt in alts):
        score += 120
    elif group_lower and (group_lower in prof or prof in group_lower):
        score += 80

    # --- FACTOR 5: CROSS-DOMAIN NEGATIVE GUARDS ---
    if not any(k in prof or k in field or k in cand_comp_nature for k in ["nurse", "nursing", "midwife"]):
        if code_prefix in ("2544", "4114"):
            score -= 500
    if not any(k in prof or k in field for k in ["doctor", "physician", "surgeon", "gp", "mbbs", "bams"]):
        if code_prefix == "2531":
            score -= 500
    if not any(k in prof or k in field for k in ["teacher", "teaching", "b.ed", "m.ed", "school teacher"]):
        if code_prefix in ("2411", "2412", "2414"):
            score -= 500
    if not any(k in prof or k in field or k in cand_comp_nature for k in ["cook", "chef", "culinary", "hospitality", "hotel"]):
        if code_prefix in ("3513", "3514"):
            score -= 500

    return score, reasons, duty_pct, matched_tasks, sa

async def run_domain_tests():
    # Test 1: Software Engineer
    c1 = {
        "current_profession": "Senior Software Engineer",
        "qualification": "bachelor",
        "field_of_study": "Computer Science",
        "years_experience_total": 8.0,
        "company_nature": "Information Technology & Software Services",
        "employer_name": "Infosys Ltd",
        "duties_text": "Lead a team of 6 engineers building microservices in Python and Java. Designed REST APIs, CI/CD pipelines and AWS cloud deployments. Managerial responsibilities including sprint planning and code reviews. Developed full-stack features for banking clients using Java and Angular. Optimised SQL queries and improved application performance by 30%.",
    }
    
    # Test 2: Chef
    c2 = {
        "current_profession": "Demi Chef de Partie (Garde Manger)",
        "qualification": "diploma",
        "field_of_study": "Hospitality & Commercial Cookery",
        "years_experience_total": 6.0,
        "company_nature": "Hospitality, Hotels & Food Services",
        "employer_name": "Taj Hotels",
        "duties_text": "Lead the cold kitchen section, preparing salads, appetizers and cold platters. Supervised 3 commis chefs and maintained HACCP food-safety standards. Assisted in food preparation across hot and cold kitchen sections.",
    }

    # Test 3: Clinical Research & Life Sciences
    c3 = {
        "current_profession": "Clinical Operations Manager",
        "qualification": "master",
        "field_of_study": "Biotechnology & Life Sciences",
        "years_experience_total": 7.0,
        "company_nature": "Healthcare, Pharmaceuticals & Life Sciences",
        "employer_name": "Syneos Health",
        "duties_text": "Lead multi-center global clinical trials and phase II-III protocols. Oversaw trial operations, site selection, biomarker data validation, and FDA/TGA regulatory documentation. Managed clinical research associates (CRAs).",
    }

    all_occs = []
    async for doc in db["occupation_master"].find({"country_code": "AU", "status": {"$ne": "superseded"}}, {"_id": 0}):
        all_occs.append(doc)

    print(f"Loaded {len(all_occs)} AU occupations from DB.")

    for name, cand in [("RAJESH KUMAR (SWE)", c1), ("PRIYA SHARMA (CHEF)", c2), ("FORUM (CLINICAL LIFE SCIENCES)", c3)]:
        print(f"\n==========================================")
        print(f"EVALUATING: {name}")
        print(f"==========================================")
        scored = []
        for occ in all_occs:
            s, r, dp, mt, sa = score_candidate_occupation(cand, occ)
            scored.append((s, occ, r, dp, mt, sa))
        scored.sort(key=lambda x: x[0], reverse=True)
        for i, (score, occ, reasons, dp, mt, sa) in enumerate(scored[:4]):
            print(f"#{i+1}: [{occ.get('code')}] {occ.get('title')} (Score: {score})")
            print(f"    Duty Match: {dp:.1f}% ({len(mt)} tasks) | Comp: {occ.get('industries_ranked')[:1]}")
            print(f"    Assessing Body: {sa.get('authority_name')} | Outcome: {sa.get('assessment_outcome')} (-{sa.get('deducted_years')} yrs)")
            print(f"    Key Reasons: {', '.join(reasons[:3])}")

asyncio.run(run_domain_tests())
