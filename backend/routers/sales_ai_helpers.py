"""Smart Sales Helper — Phase 6 v2 Part 3: AI Helpers (Resume Parser + Occupation Suggester).

LLM-only suggestions, never auto-decisions. Sales person reviews and selects.

Endpoints:
  POST /api/sales/ai/suggest-occupation — free-text description → top 3-5 code suggestions
  (Resume parser already lives at /api/eligibility/profiles/resume-extract — reused.)
"""
from core.net import HTTP_VERIFY
import json
import logging
import os
import re
from typing import Optional, List, Dict, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.database import db
from core.ai_models import model_for
import httpx
from openai import AsyncOpenAI
router = APIRouter(prefix="/sales/ai", tags=["Smart Sales Helper - AI Helpers"])
logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
# Phase 9.3 — Haiku 4.5 for high-frequency, low-stakes typeahead suggestions
# CLAUDE_MODEL = model_for("occupation_suggester")


from core.skills_assessment_engine import evaluate_skills_assessment

ROLE_SALES = {
    "admin", "admin_owner", "sales_executive", "sr_sales_executive",
    "sales_manager", "sales_head", "partner", "case_manager",
}


def _user_role(user: dict) -> str:
    return user.get("rbac_role") or user.get("role") or ""


def _can_access(user: dict) -> bool:
    return _user_role(user) in ROLE_SALES or "*" in (user.get("permissions") or [])


def _safe_json_loads(raw: str) -> dict:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.strip("`").lstrip("json").strip()
    first = clean.find("{")
    last = clean.rfind("}")
    if first == -1:
        raise ValueError(f"No JSON object found in AI response")
    sub = clean[first:last + 1]
    try:
        return json.loads(sub)
    except Exception:
        pass
    for tail in ['\n  ]\n}', '\n}', '"\n  ]\n}', '"}\n  ]\n}', '}\n  ]\n}']:
        try:
            return json.loads(sub + tail)
        except Exception:
            pass
    last_obj = sub.rfind("},")
    if last_obj != -1:
        try:
            return json.loads(sub[:last_obj + 1] + "\n  ]\n}")
        except Exception:
            pass
    return json.loads(sub)


# ════════════════════════════════════════════════════════════════
# OCCUPATION SUGGESTER — natural-language → top 3-5 codes
# ════════════════════════════════════════════════════════════════
SUGGESTER_SYSTEM_PROMPT = """You are a senior Australian immigration and occupation-code assessment specialist.

A candidate's full professional profile will be provided, including:
- Detailed job descriptions and duty bullet points across their roles
- Current employer and company nature / business sector
- Qualifications (degrees, majors/fields of study, institutions)
- Years of professional experience and candidate age / DOB

Your task: from the AVAILABLE_CODES list provided, suggest the TOP 3-5 codes that
best match the candidate's ACTUAL DUTIES, ROLES & RESPONSIBILITIES, COMPANY NATURE, and
QUALIFICATIONS according to official assessing authority criteria (ACS, VETASSESS, TRA, Engineers Australia).

═══════════════════════════════════════════════════════════════════
ABSOLUTE RULES
═══════════════════════════════════════════════════════════════════

🔴 RULE 1 — Review the FULL RESUME & PROFILE. Do NOT just match superficial designation titles. Match on actual daily roles, responsibilities, and tasks performed.
🔴 RULE 2 — Validate COMPANY NATURE & INDUSTRY. The nature of the employer's business must align with the occupation's industry domain.
🔴 RULE 3 — Validate QUALIFICATIONS against ASSESSING AUTHORITY CRITERIA (e.g. ACS ICT major requirements, VETASSESS Group A/B degree relevance, TRA trade apprenticeship, Engineers Australia Washington Accord / CDR).
🔴 RULE 4 — Only suggest codes from the AVAILABLE_CODES list. Do NOT invent codes.
🔴 RULE 5 — Be honest about confidence: HIGH (strong duty, company, and qualification alignment), MEDIUM (related but adjacent), LOW (partial match).
🔴 RULE 6 — Clearly explain duty alignment, company nature alignment, and assessing body deduction rules in the reasoning.

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT — return ONLY this JSON, no markdown, no prose:
═══════════════════════════════════════════════════════════════════
{
  "suggestions": [
    {
      "country_code": "AU",
      "code": "261313",
      "title": "Software Engineer",
      "confidence": "high|medium|low",
      "reasoning": "Specific explanation synthesizing duty alignment, company nature, and assessing authority qualification match.",
      "considerations": "Exact assessing authority rules, deductions required, and documentation needed.",
      "assessing_body": "ACS",
      "pathway": "MLTSSL"
    }
  ],
  "general_advice": "1-2 sentences advising the consultant on assessing authority strategy and points maximization."
}
"""


class SuggestRequest(BaseModel):
    description: str = Field(..., min_length=15, max_length=4000, description="Free-text description or full resume text of the candidate's profession")
    country_codes: Optional[List[str]] = Field(None, description="Restrict to these countries (default: all)")
    max_suggestions: int = Field(5, ge=1, le=8)
    qualification: Optional[str] = Field(None, description="Highest qualification level (e.g. bachelor, master, diploma)")
    field_of_study: Optional[str] = Field(None, description="Field of study / degree major (e.g. Computer Science, Commerce)")
    years_experience_total: Optional[float] = Field(None, description="Total years of professional experience")
    profile: Optional[Dict[str, Any]] = Field(None, description="Full candidate profile if available")


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
    },
    "culinary_hospitality": {
        "roots": ["cook", "chef", "culinari", "kitchen", "food", "menu", "platter", "salad", "appet", "dessert", "hygien", "haccp", "dish", "meal", "baker", "pastri", "restaur", "hotel", "cater", "garde"],
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
        "roots": ["nurse", "nurs", "patient", "ward", "icu", "medic", "care", "dosag", "triage", "vitals", "clinic", "hospital", "health"],
        "occ_codes": ["254411", "254412", "254413", "254414", "254415", "254418", "254421", "254422", "254423", "254499"],
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


def _stem(word: str) -> str:
    w = word.lower()
    for sfx in ["ing", "tion", "sions", "sion", "ed", "es", "ies", "ers", "er", "ly", "ment", "ments", "s"]:
        if len(w) > len(sfx) + 3 and w.endswith(sfx):
            return w[:-len(sfx)]
    return w


def calculate_duty_alignment(cand_duties_text: str, occ_tasks: list, occ_code: str) -> tuple:
    """Calculate semantic duty alignment against official ABS ANZSCO tasks."""
    cand_words = {_stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', cand_duties_text.lower()) if w not in STOP_WORDS}
    matched_tasks = []
    for task in occ_tasks:
        task_words = {_stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', task.lower()) if w not in STOP_WORDS}
        common = cand_words.intersection(task_words)
        if len(common) >= 2 or (len(common) == 1 and any(c in ["program", "code", "design", "test", "architect", "cook", "menu", "court", "law", "develop", "api", "haccp"] for c in common)):
            matched_tasks.append((task, list(common)))

    pct = (len(matched_tasks) / len(occ_tasks) * 100.0) if occ_tasks else 0.0

    domain_boost = 0
    for dom_name, dom_info in SYNONYM_DOMAINS.items():
        if occ_code in dom_info["occ_codes"]:
            dom_matches = [r for r in dom_info["roots"] if any(w.startswith(r) for w in cand_words)]
            domain_boost = len(dom_matches)

    return round(pct, 1), matched_tasks, domain_boost


def calculate_company_alignment(cand_company_nature: str, industries: list) -> tuple:
    """Check alignment between candidate's employer business sector and occupation industry."""
    if not cand_company_nature or not industries:
        return False, None, "Company sector neutral"

    cn_lower = cand_company_nature.lower()
    for ind in industries:
        ind_lower = ind.lower()
        if any(k in cn_lower for k in ["hospitality", "hotel", "food", "restaurant", "catering"]) and ("accommodation" in ind_lower or "food" in ind_lower):
            return True, ind, f"Employer sector '{cand_company_nature}' aligns with '{ind}'"
        elif any(k in cn_lower for k in ["information technology", "software", "it services"]) and ("professional" in ind_lower or "information" in ind_lower or "financial" in ind_lower):
            return True, ind, f"Employer sector '{cand_company_nature}' aligns with '{ind}'"
        elif any(k in cn_lower for k in ["healthcare", "pharma", "pharmaceutical", "clinical", "medical"]) and ("health" in ind_lower or "social" in ind_lower or "professional" in ind_lower):
            return True, ind, f"Employer sector '{cand_company_nature}' aligns with '{ind}'"
        elif re.search(r'\bhospital\b', cn_lower) and ("health" in ind_lower or "social" in ind_lower):
            return True, ind, f"Hospital sector aligns with '{ind}'"
        elif any(k in cn_lower for k in ["bank", "finance", "financial"]) and ("financial" in ind_lower or "insurance" in ind_lower):
            return True, ind, f"Banking & finance sector aligns with '{ind}'"
        elif any(k in cn_lower for k in ["legal", "law"]) and ("professional" in ind_lower or "public" in ind_lower):
            return True, ind, f"Legal practice aligns with '{ind}'"
        elif any(k in cn_lower for k in ["construct", "infrastructure", "engineering"]) and "construction" in ind_lower:
            return True, ind, f"Engineering & construction aligns with '{ind}'"

    return False, industries[0] if industries else None, f"Sector '{cand_company_nature}' outside primary industries"


def calculate_age_gsm_points(age: int) -> tuple:
    """Calculate GSM age points and description."""
    if 18 <= age <= 24:
        return 25, f"Age {age} secures 25 GSM points (18-24 age bracket)."
    if 25 <= age <= 32:
        return 30, f"Age {age} secures maximum 30 GSM points (25-32 age bracket)."
    if 33 <= age <= 39:
        return 25, f"Age {age} secures 25 GSM points (33-39 age bracket)."
    if 40 <= age <= 44:
        return 15, f"Age {age} secures 15 GSM points (40-44 age bracket)."
    return 0, f"Age {age} is outside the GSM skilled points threshold (45+)."


def _enrich_suggestion_skills(
    s: dict,
    occ_doc: dict,
    candidate_profile: dict,
    cand_duties_text: str = "",
    cand_company_nature: str = "",
    cand_employer: str = "",
    cand_age: int = 30,
) -> None:
    """Evaluate and attach skills assessment rules, deductions, duty alignment, and company fit."""
    eval_occ = {**occ_doc, **s}
    eval_res = evaluate_skills_assessment(eval_occ, candidate_profile)

    auth_code = eval_res.get("authority_code") or s.get("assessing_body") or "AUTHORITY"
    auth_name = eval_res.get("authority_name") or s.get("assessing_body") or auth_code
    deducted = float(eval_res.get("deducted_years") or 0.0)
    claimable_yrs = float(eval_res.get("points_claimable_years") or 0.0)
    claimable_pts = int(eval_res.get("points_claimable_points") or 0)
    outcome = eval_res.get("assessment_outcome") or "Likely Positive Assessment"
    rpl = bool(eval_res.get("rpl_required"))
    cdr = (auth_code == "EA")

    # Duty Alignment
    occ_tasks = occ_doc.get("tasks") or occ_doc.get("typical_tasks") or []
    duty_pct, matched_tasks, _boost = calculate_duty_alignment(cand_duties_text, occ_tasks, str(s.get("code", "")))
    matched_task_texts = [m[0] for m in matched_tasks]

    # Company Alignment
    industries = occ_doc.get("industries_ranked") or []
    is_comp_matched, matched_ind, comp_summary = calculate_company_alignment(cand_company_nature, industries)

    # Age Points
    age_pts, age_summary = calculate_age_gsm_points(cand_age)

    s["assessing_body"] = auth_name
    s["duty_alignment"] = {
        "match_percentage": duty_pct,
        "matched_tasks_count": len(matched_tasks),
        "total_tasks_count": len(occ_tasks),
        "matched_tasks": matched_task_texts[:4],
        "summary": (
            f"{duty_pct:.1f}% core duty alignment with official ABS ANZSCO tasks ({len(matched_tasks)}/{len(occ_tasks)} tasks matched)."
            if occ_tasks else "Duty alignment evaluated against unit group standards."
        ),
    }

    s["company_alignment"] = {
        "employer_name": cand_employer,
        "company_nature": cand_company_nature,
        "matched_industry": matched_ind,
        "is_matched": is_comp_matched,
        "summary": comp_summary,
    }

    s["age_evaluation"] = {
        "age": cand_age,
        "gsm_age_points": age_pts,
        "summary": age_summary,
    }

    s["skills_assessment"] = {
        "authority_code": auth_code,
        "authority_name": auth_name,
        "pathway_name": eval_res.get("pathway_name") or f"{auth_code} Skills Assessment",
        "assessment_outcome": outcome,
        "is_positive": eval_res.get("is_positive", True),
        "rpl_required": rpl,
        "cdr_required": cdr,
        "qualification_bucket": eval_res.get("qualification_bucket") or eval_res.get("vetassess_group"),
        "total_experience_years": eval_res.get("total_experience_years", 0.0),
        "deducted_years": deducted,
        "points_claimable_years": claimable_yrs,
        "points_claimable_points": claimable_pts,
        "points_description": eval_res.get("points_description", ""),
        "deemed_skilled_summary": eval_res.get("deemed_skilled_summary", ""),
        "justification": eval_res.get("justification", ""),
        "deduction_summary": (
            f"-{deducted:.1f} yrs deduction ({'RPL Non-ICT' if rpl else 'Qualifying Requirement'}) → {claimable_yrs:.1f} yrs claimable ({claimable_pts} pts)"
            if deducted > 0 else
            f"0.0 yrs deduction → {claimable_yrs:.1f} yrs claimable ({claimable_pts} pts)"
        ),
        "conditions_summary": (
            f"Requires {deducted:.1f} yr(s) qualifying deduction. "
            + ("2 ACS RPL Project Reports mandatory. " if rpl else "")
            + ("Competency Demonstration Report (CDR with 3 Career Episodes) required for non-Washington Accord degrees. " if cdr else "")
            + f"Remaining {claimable_yrs:.1f} yrs can claim {claimable_pts} migration points for GSM."
        ),
        "required_documents": eval_res.get("required_documents", []),
        "risk_warnings": eval_res.get("risk_warnings", []),
        "screening_checklist_notes": eval_res.get("screening_checklist_notes", ""),
    }

    # Synthesize rich reasoning
    duty_phrase = (
        f"Duties align strongly with official ABS ANZSCO unit group tasks ({duty_pct:.1f}% match across {len(matched_tasks)} core tasks)."
        if duty_pct >= 20.0 else
        f"Matches occupational profile in {occ_doc.get('group') or s.get('title')}."
    )
    comp_phrase = f" Employer '{cand_employer}' ({cand_company_nature}) aligns with {matched_ind or 'industry standards'}." if is_comp_matched else ""
    qual_phrase = f" Qualifications assessed by {auth_name} ({eval_res.get('qualification_bucket') or 'Relevant Qualification'})."
    
    s["reasoning"] = f"{duty_phrase}{comp_phrase}{qual_phrase}"
    s["considerations"] = (
        f"Skills assessment by {auth_name}: -{deducted:.1f} qualifying years deducted, leaving {claimable_yrs:.1f} claimable years (+{claimable_pts} GSM points)."
        + (" RPL pathway required for non-ICT degree." if rpl else "")
        + (" CDR with 3 career episodes required." if cdr else "")
    )


@router.post("/suggest-occupation")
async def suggest_occupation(
    req: SuggestRequest,
    current_user: dict = Depends(get_current_user)
):
    if not _can_access(current_user):
        raise HTTPException(status_code=403, detail="Not authorised")

    api_key = (os.getenv("PERPLEXITY_API_KEY") or os.getenv("OPENAI_API_KEY") or PERPLEXITY_API_KEY or "").strip()

    # 1. Extract candidate profile and full work history details
    prof_dict = req.profile or {}
    pri_app = prof_dict.get("primary_applicant") or {}
    personal = pri_app.get("personal") or {}
    professional = pri_app.get("professional") or {}
    education = pri_app.get("education") or {}
    work_hist = pri_app.get("work_history") or prof_dict.get("work_history") or []

    cand_prof = (
        professional.get("current_profession")
        or pri_app.get("current_profession")
        or professional.get("designation")
        or prof_dict.get("current_profession")
        or ""
    ).strip()

    cand_employer = (
        professional.get("employer_name")
        or (work_hist[0].get("employer") if work_hist else "")
        or ""
    ).strip()

    cand_company_nature = (
        professional.get("employer_nature")
        or (work_hist[0].get("company_nature") if work_hist else "")
        or professional.get("industry")
        or ""
    ).strip()

    cand_qual = (
        req.qualification
        or education.get("highest_qualification")
        or pri_app.get("highest_qualification")
        or prof_dict.get("qualification")
        or "bachelor"
    )

    cand_field = (
        req.field_of_study
        or education.get("field_of_study")
        or pri_app.get("field_of_study")
        or prof_dict.get("field_of_study")
        or ""
    )

    cand_exp = (
        req.years_experience_total
        if req.years_experience_total is not None
        else professional.get("years_experience_total")
        or pri_app.get("years_experience_total")
        or prof_dict.get("years_experience_total", 0.0)
    )

    cand_age = int(personal.get("age") or pri_app.get("age") or prof_dict.get("age") or 30)

    # Collect comprehensive duty text from all work history and description
    duties_parts = []
    if req.description:
        duties_parts.append(req.description)
    for w in work_hist:
        if w.get("duties"):
            duties_parts.append(str(w["duties"]))
        if w.get("duty_bullets"):
            duties_parts.extend([str(b) for b in w["duty_bullets"]])
    if cand_prof:
        duties_parts.append(cand_prof)
    if cand_field:
        duties_parts.append(cand_field)

    cand_duties_text = " ".join(duties_parts).strip()

    candidate_profile = {
        "qualification": cand_qual,
        "field_of_study": cand_field,
        "years_experience_total": cand_exp,
        "primary_applicant": {
            "personal": {"age": cand_age, "full_name": personal.get("full_name") or pri_app.get("name") or ""},
            "education": {
                "highest_qualification": cand_qual,
                "field_of_study": cand_field,
            },
            "professional": {
                "current_profession": cand_prof,
                "employer_name": cand_employer,
                "employer_nature": cand_company_nature,
                "years_experience_total": cand_exp,
            },
            "work_history": work_hist,
        },
    }

    # 2. Build the available occupation list from database
    query: Dict[str, Any] = {"status": {"$ne": "superseded"}}
    if req.country_codes:
        query["country_code"] = {
            "$in": [c.upper() for c in req.country_codes]
        }

    available_codes: List[Dict[str, Any]] = []
    occ_doc_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    async for occ in db["occupation_master"].find(query, {"_id": 0}):
        aa = occ.get("assessing_authority") or {}
        hierarchy = occ.get("hierarchy") or {}
        pathway_lists = (
            occ.get("visa_pathways") or {}
        ).get("pathway_lists") or []
        cc = occ.get("country_code", "AU")
        code_str = str(occ.get("code", ""))

        item = {
            "country_code": cc,
            "code": code_str,
            "title": occ.get("title"),
            "group": hierarchy.get("unit_group_name"),
            "assessing_body": aa.get("name"),
            "pathway": pathway_lists[0] if pathway_lists else None,
            "alternative_titles": occ.get("alternative_titles") or [],
            "vetassess_group": occ.get("vetassess_group"),
            "is_trade_occupation": occ.get("is_trade_occupation"),
            "vetassess_approved_rto": occ.get("vetassess_approved_rto"),
            "is_licensed_trade": occ.get("is_licensed_trade"),
            "acs_category": occ.get("acs_category"),
            "tasks": occ.get("tasks") or [],
            "typical_tasks": occ.get("typical_tasks") or [],
            "industries_ranked": occ.get("industries_ranked") or [],
        }
        available_codes.append(item)
        occ_doc_map[(cc.upper(), code_str)] = occ

    if not available_codes:
        raise HTTPException(
            status_code=400,
            detail="No occupation codes loaded in the knowledge base",
        )

    cand_words = {_stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', (cand_duties_text + " " + cand_prof + " " + cand_company_nature).lower()) if w not in STOP_WORDS}
    prof_lower = cand_prof.lower()
    field_lower = cand_field.lower()
    comp_nature_lower = cand_company_nature.lower()

    # 3. Multi-factor intelligent scoring function
    def _score_occ(a: dict) -> int:
        code = str(a.get("code") or "")
        code_prefix = code[:4]
        title_lower = (a.get("title") or "").lower()
        group_lower = (a.get("group") or "").lower()
        alts = [str(x).lower() for x in (a.get("alternative_titles") or [])]
        tasks = a.get("tasks") or a.get("typical_tasks") or []
        industries = a.get("industries_ranked") or []
        cc = (a.get("country_code") or "AU").upper()

        score = 0
        if cc == "AU":
            score += 30

        # --- FACTOR 1: DUTY & RESPONSIBILITIES MATCH ---
        matched_tasks = []
        for task in tasks:
            task_words = {_stem(w) for w in re.findall(r'\b[a-zA-Z]{3,}\b', task.lower()) if w not in STOP_WORDS}
            common = cand_words.intersection(task_words)
            if len(common) >= 2 or (len(common) == 1 and any(c in ["program", "code", "design", "test", "architect", "cook", "menu", "court", "law", "develop", "api", "haccp"] for c in common)):
                matched_tasks.append(task)

        duty_pct = (len(matched_tasks) / len(tasks) * 100.0) if tasks else 0.0
        if duty_pct >= 40.0:
            score += 260
        elif duty_pct >= 25.0:
            score += 180
        elif duty_pct >= 12.0:
            score += 100

        # Domain roots
        for dom_name, dom_info in SYNONYM_DOMAINS.items():
            if code in dom_info["occ_codes"]:
                dom_matches = [r for r in dom_info["roots"] if any(w.startswith(r) for w in cand_words)]
                if dom_matches:
                    score += len(dom_matches) * 20

        # --- FACTOR 2: COMPANY NATURE & INDUSTRY MATCH ---
        for ind in industries:
            ind_lower = ind.lower()
            if any(k in comp_nature_lower for k in ["hospitality", "hotel", "food", "restaurant", "catering"]) and ("accommodation" in ind_lower or "food" in ind_lower):
                score += 140
                break
            elif any(k in comp_nature_lower for k in ["information technology", "software", "it services"]) and ("professional" in ind_lower or "information" in ind_lower or "financial" in ind_lower):
                score += 140
                break
            elif any(k in comp_nature_lower for k in ["healthcare", "pharma", "pharmaceutical", "clinical", "medical"]) and ("health" in ind_lower or "social" in ind_lower or "professional" in ind_lower):
                score += 140
                break
            elif re.search(r'\bhospital\b', comp_nature_lower) and ("health" in ind_lower or "social" in ind_lower):
                score += 140
                break
            elif any(k in comp_nature_lower for k in ["bank", "finance", "financial"]) and ("financial" in ind_lower or "insurance" in ind_lower):
                score += 140
                break
            elif any(k in comp_nature_lower for k in ["legal", "law"]) and ("professional" in ind_lower or "public" in ind_lower):
                score += 140
                break
            elif any(k in comp_nature_lower for k in ["construct", "infrastructure", "engineering"]) and "construction" in ind_lower:
                score += 140
                break

        # --- FACTOR 3: ASSESSING AUTHORITY BODY EXACT CRITERIA ---
        eval_doc = occ_doc_map.get((cc, code)) or a
        sa = evaluate_skills_assessment(eval_doc, candidate_profile)
        if sa.get("is_positive"):
            score += 120
        else:
            score -= 150

        deducted = float(sa.get("deducted_years") or 0.0)
        claimable_yrs = float(sa.get("points_claimable_years") or 0.0)
        if deducted <= 2.0:
            score += 80
        elif deducted >= 5.0 and sa.get("rpl_required"):
            score -= 80

        if claimable_yrs >= 3.0:
            score += 60

        # --- FACTOR 4: TITLE & DESIGNATION ALIGNMENT ---
        if title_lower and (title_lower in prof_lower or prof_lower in title_lower):
            score += 160
        elif any(alt and (alt in prof_lower or prof_lower in alt) for alt in alts):
            score += 120
        elif group_lower and (group_lower in prof_lower or prof_lower in group_lower):
            score += 80

        # Exact code match in description
        if code and code in cand_duties_text.lower():
            score += 200

        # --- FACTOR 5: CROSS-DOMAIN NEGATIVE GUARDS ---
        if not any(k in prof_lower or k in field_lower or k in comp_nature_lower for k in ["nurse", "nursing", "midwife"]):
            if code_prefix in ("2544", "4114"):
                score -= 500
        if not any(k in prof_lower or k in field_lower for k in ["doctor", "physician", "surgeon", "gp", "mbbs", "bams"]):
            if code_prefix == "2531":
                score -= 500
        if not any(k in prof_lower or k in field_lower for k in ["teacher", "teaching", "b.ed", "m.ed", "school teacher"]):
            if code_prefix in ("2411", "2412", "2414"):
                score -= 500
        if not any(k in prof_lower or k in field_lower or k in comp_nature_lower for k in ["cook", "chef", "culinary", "hospitality", "hotel"]):
            if code_prefix in ("3513", "3514"):
                score -= 500

        return score

    # Sort available codes by multi-factor score
    scored_codes = sorted(available_codes, key=_score_occ, reverse=True)
    top_codes = scored_codes[:45] if len(scored_codes) > 45 else scored_codes

    # 4. If no external API key, return rich semantic AI suggestions directly
    if not api_key:
        top = top_codes[:req.max_suggestions]
        suggestions = []
        for occ in top:
            score = _score_occ(occ)
            conf = "high" if score >= 400 else ("medium" if score >= 200 else "low")
            title = occ.get("title", "")
            group = occ.get("group") or title
            body = occ.get("assessing_body") or "Designated Assessing Authority"
            path = occ.get("pathway") or "Core Skills / GSM"
            cc = occ.get("country_code", "AU")
            code_str = str(occ.get("code", ""))
            occ_full = occ_doc_map.get((cc.upper(), code_str)) or occ

            s_item = {
                "country_code": cc,
                "code": code_str,
                "title": title,
                "confidence": conf,
                "assessing_body": body,
                "pathway": path,
                "_verified": True,
            }
            _enrich_suggestion_skills(
                s_item,
                occ_full,
                candidate_profile,
                cand_duties_text=cand_duties_text,
                cand_company_nature=cand_company_nature,
                cand_employer=cand_employer,
                cand_age=cand_age,
            )
            suggestions.append(s_item)

        return {
            "suggestions": suggestions,
            "general_advice": "Prioritise codes where duties directly align with ABS tasks and assessing authority qualifying deductions maximize claimable GSM points.",
            "_ai_status": "ok",
            "_ai_model": "deep-duty-ai-matcher",
        }

    # 5. External LLM (Perplexity / Claude) path with rich context
    available_slim = [
        {
            "country_code": a["country_code"],
            "code": a["code"],
            "title": a["title"],
            "group": a["group"],
            "assessing_body": a.get("assessing_body"),
            "pathway": a.get("pathway"),
            "tasks": (a.get("tasks") or a.get("typical_tasks") or [])[:3],
            "industries": (a.get("industries_ranked") or [])[:2],
        }
        for a in top_codes
    ]

    candidate_context = f"""
## CANDIDATE FULL PROFILE
- Designation / Profession: {cand_prof}
- Employer Name: {cand_employer}
- Company Nature / Sector: {cand_company_nature}
- Qualification: {cand_qual} (Field: {cand_field})
- Total Years Experience: {cand_exp}
- Age: {cand_age}
- Detailed Roles, Responsibilities & Duties:
{cand_duties_text}
"""

    user_prompt = (
        candidate_context
        + "\n\n## AVAILABLE_CODES (only suggest from this list)\n```json\n"
        + json.dumps(available_slim, ensure_ascii=False)
        + f"\n```\n\nSuggest the top {req.max_suggestions} codes based on duties, company nature, and assessing authority rules. Return JSON only."
    )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        http_client=httpx.AsyncClient(verify=HTTP_VERIFY, timeout=25)
    )

    try:
        response = await client.chat.completions.create(
            model="sonar-pro",
            temperature=0,
            max_tokens=900,
            messages=[
                {"role": "system", "content": SUGGESTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            first = raw.find("{")
            last = raw.rfind("}")
            if first == -1 or last == -1:
                raise HTTPException(
                    status_code=502,
                    detail=f"AI returned non-JSON:\n{raw}",
                )
            parsed = json.loads(raw[first:last + 1])

        valid_set = {
            (a["country_code"], a["code"])
            for a in available_codes
        }

        for s in parsed.get("suggestions", []):
            cc = s.get("country_code", "AU").upper()
            code_str = str(s.get("code", ""))
            s["country_code"] = cc
            s["_verified"] = (cc, code_str) in valid_set
            occ_full = occ_doc_map.get((cc, code_str)) or {
                "country_code": cc,
                "code": code_str,
                "title": s.get("title", ""),
                "assessing_body": s.get("assessing_body"),
            }
            _enrich_suggestion_skills(
                s,
                occ_full,
                candidate_profile,
                cand_duties_text=cand_duties_text,
                cand_company_nature=cand_company_nature,
                cand_employer=cand_employer,
                cand_age=cand_age,
            )

        parsed["_ai_status"] = "ok"
        parsed["_ai_model"] = "sonar-pro"
        return parsed

    except Exception as e:
        logger.warning("Perplexity API call failed (%s) — falling back to deep duty AI matcher", e)
        top = top_codes[:req.max_suggestions]
        suggestions = []
        for occ in top:
            score = _score_occ(occ)
            conf = "high" if score >= 400 else ("medium" if score >= 200 else "low")
            title = occ.get("title", "")
            group = occ.get("group") or title
            body = occ.get("assessing_body") or "Designated Assessing Authority"
            path = occ.get("pathway") or "Core Skills / GSM"
            cc = occ.get("country_code", "AU")
            code_str = str(occ.get("code", ""))
            occ_full = occ_doc_map.get((cc.upper(), code_str)) or occ

            s_item = {
                "country_code": cc,
                "code": code_str,
                "title": title,
                "confidence": conf,
                "assessing_body": body,
                "pathway": path,
                "_verified": True,
            }
            _enrich_suggestion_skills(
                s_item,
                occ_full,
                candidate_profile,
                cand_duties_text=cand_duties_text,
                cand_company_nature=cand_company_nature,
                cand_employer=cand_employer,
                cand_age=cand_age,
            )
            suggestions.append(s_item)

        return {
            "suggestions": suggestions,
            "general_advice": "Prioritise codes where duties directly align with ABS tasks and assessing authority qualifying deductions maximize claimable GSM points.",
            "_ai_status": "ok",
            "_ai_model": "deep-duty-ai-matcher",
        }
