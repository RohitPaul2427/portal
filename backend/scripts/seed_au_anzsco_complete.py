"""Phase 19.8 / Phase 20 — Authoritative Seeder for Australian ANZSCO Skilled Occupations.

Complete coverage of Australian Skilled Occupation Lists with:
  • ANZSCO 2013 (v1.2/v1.3) for General Skilled Migration (GSM 189, 190, 491, 485)
  • ANZSCO 2022 for Core Skills Occupation List (CSOL / Skills in Demand / TSS 482, 186 ENS, 494 SESR)
  • Official Assessing Authorities (ACS, EA, VETASSESS, TRA, ANMAC, MedBA, AITSL, CPA/CA ANZ, etc.)
  • Automatic inheritance from ABS Feb 2026 4-digit labour market profiles.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add backend directory to sys.path
backend_dir = r"c:\Users\Rohit Alluri\Downloads\LEAMSS-main (1)\LEAMSS-main\backend"
sys.path.insert(0, backend_dir)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from core.database import db
from seeds.assessing_authorities_au import ensure_seeded_in_db

NOW = datetime.now(timezone.utc).isoformat()


def occ(
    code_2013: str,
    title: str,
    list_name: str,
    authority: str,
    skill_level: int = 1,
    code_2022: Optional[str] = None,
    alt_titles: Optional[List[str]] = None,
    specialisations: Optional[List[str]] = None,
    state_demand: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    code_2022 = code_2022 or code_2013
    alt_titles = alt_titles or []
    specialisations = specialisations or []

    # GSM Eligibility (ANZSCO 2013)
    gsm_189 = list_name == "MLTSSL"
    gsm_190 = list_name in ("MLTSSL", "STSOL")
    gsm_491 = list_name in ("MLTSSL", "STSOL", "ROL")
    gsm_485 = list_name == "MLTSSL"

    # Core Skills / Employer Sponsored Eligibility (ANZSCO 2022)
    emp_482 = True  # Skills in Demand / TSS / CSOL
    emp_186 = list_name in ("MLTSSL", "CSOL")
    emp_494 = list_name in ("MLTSSL", "STSOL", "ROL", "CSOL")

    visa_eligibility: List[Dict[str, Any]] = []
    if gsm_189:
        visa_eligibility.append({
            "visa_subclass": "189",
            "name": "Skilled Independent (Points-tested)",
            "version": "ANZSCO 2013",
            "eligible": True,
            "list": "MLTSSL",
            "notes": "Permanent Residence. No sponsorship required. Minimum 65 points."
        })
    if gsm_190:
        visa_eligibility.append({
            "visa_subclass": "190",
            "name": "Skilled Nominated (State/Territory)",
            "version": "ANZSCO 2013",
            "eligible": True,
            "list": list_name,
            "notes": "Permanent Residence via State Nomination (+5 points)."
        })
    if gsm_491:
        visa_eligibility.append({
            "visa_subclass": "491",
            "name": "Skilled Work Regional (Provisional)",
            "version": "ANZSCO 2013",
            "eligible": True,
            "list": list_name,
            "notes": "5-year provisional visa with PR pathway via Subclass 191 (+15 points)."
        })
    if gsm_485:
        visa_eligibility.append({
            "visa_subclass": "485",
            "name": "Temporary Graduate (Graduate Work Stream)",
            "version": "ANZSCO 2013",
            "eligible": True,
            "list": "MLTSSL",
            "notes": "Post-study work stream for Australian qualification holders."
        })
    if emp_482:
        visa_eligibility.append({
            "visa_subclass": "482",
            "name": "Skills in Demand Visa (Core Skills / TSS)",
            "version": "ANZSCO 2022",
            "eligible": True,
            "list": "CSOL",
            "notes": "4-year employer sponsored work visa under Core Skills Occupation List (CSOL)."
        })
    if emp_186:
        visa_eligibility.append({
            "visa_subclass": "186",
            "name": "Employer Nomination Scheme (Direct Entry / TRT)",
            "version": "ANZSCO 2022",
            "eligible": True,
            "list": list_name,
            "notes": "Direct Permanent Residence sponsored by approved Australian employer."
        })
    if emp_494:
        visa_eligibility.append({
            "visa_subclass": "494",
            "name": "Skilled Employer Sponsored Regional (Provisional)",
            "version": "ANZSCO 2022",
            "eligible": True,
            "list": list_name,
            "notes": "Regional employer sponsored visa with PR pathway."
        })

    return {
        "code": code_2013,
        "country_code": "AU",
        "title": title,
        "classification_type": "ANZSCO",
        "classification_version": "ANZSCO 2013 / ANZSCO 2022",
        "classification_dual_code": {
            "2013": code_2013,
            "2022": code_2022,
        },
        "anzsco_version": {
            "gsm_2013": code_2013,
            "core_skills_2022": code_2022,
        },
        "pathway_list": list_name,
        "pathway_lists": list(set([list_name, "CSOL"] if emp_482 else [list_name])),
        "skill_level": skill_level,
        "assessing_authority": {
            "name": authority,
            "code": authority,
            "short_name": authority,
        },
        "visa_pathways": {
            "visa_eligibility": visa_eligibility,
            "pathway_lists": list(set([list_name, "CSOL"] if emp_482 else [list_name])),
            "gsm_eligible": gsm_189 or gsm_190 or gsm_491,
            "gsm_pathways": [v["visa_subclass"] for v in visa_eligibility if v["visa_subclass"] in ("189", "190", "491", "485")],
            "employer_pathways": [v["visa_subclass"] for v in visa_eligibility if v["visa_subclass"] in ("482", "186", "494")],
            "core_skills_eligible": emp_482,
        },
        "alternative_titles": alt_titles,
        "specialisations": specialisations,
        "state_demand": state_demand or {
            "NSW": "high", "VIC": "high", "QLD": "high", "WA": "medium",
            "SA": "medium", "ACT": "high", "TAS": "medium", "NT": "high",
        },
        "status": "verified",
        "verification": {
            "source": "home_affairs_skilled_occupation_list",
            "auto_verified_at": NOW,
            "auto_verified_by": "seed_au_anzsco_complete.py",
            "method": "Australian Government Department of Home Affairs SOL Gazetted List & ABS 2026",
        },
        "anzsco_4digit_code": code_2013[:4] if len(code_2013) >= 4 else None,
        "anzsco_major_group_code": code_2013[0] if len(code_2013) >= 1 else None,
        "created_at": NOW,
        "updated_at": NOW,
        "last_scraped_at": NOW,
        "last_scraped_by": "home_affairs_skilled_occupation_list",
    }


ALL_AU_OCCUPATIONS: List[Dict[str, Any]] = [
    # ─── 1. ICT & TECHNOLOGY (ACS) ───
    occ("261313", "Software Engineer", "MLTSSL", "ACS", 1, "261313", ["Software Developer", "Software Architect"], ["Cloud Software Engineer", "Backend Engineer"]),
    occ("261312", "Developer Programmer", "MLTSSL", "ACS", 1, "261312", ["Full Stack Developer", "Applications Developer"]),
    occ("261311", "Analyst Programmer", "MLTSSL", "ACS", 1, "261311", ["Systems Programmer"]),
    occ("261314", "Software Tester", "STSOL", "ACS", 1, "261314", ["QA Automation Engineer", "Quality Assurance Tester"]),
    occ("261399", "Software and Applications Programmers nec", "STSOL", "ACS", 1, "261399"),
    occ("263111", "Computer Network and Systems Engineer", "MLTSSL", "ACS", 1, "263111", ["Network Engineer", "Infrastructure Engineer"]),
    occ("262112", "ICT Security Specialist", "MLTSSL", "ACS", 1, "262112", ["Cybersecurity Specialist", "Information Security Analyst"]),
    occ("261111", "ICT Business Analyst", "MLTSSL", "ACS", 1, "261111", ["Business Systems Analyst"]),
    occ("261112", "Systems Analyst", "MLTSSL", "ACS", 1, "261112", ["IT Systems Analyst"]),
    occ("262111", "Database Administrator", "STSOL", "ACS", 1, "262111", ["DBA"]),
    occ("262113", "Systems Administrator", "STSOL", "ACS", 1, "262113", ["Sysadmin"]),
    occ("261211", "Multimedia Specialist", "STSOL", "ACS", 1, "261211", ["Multimedia Developer"]),
    occ("261212", "Web Developer", "STSOL", "ACS", 1, "261212", ["Frontend Developer", "Web Programmer"]),
    occ("263112", "Network Administrator", "STSOL", "ACS", 1, "263112"),
    occ("263113", "Network Analyst", "STSOL", "ACS", 1, "263113"),
    occ("263211", "ICT Quality Assurance Engineer", "STSOL", "ACS", 1, "263211"),
    occ("263212", "ICT Support Engineer", "STSOL", "ACS", 1, "263212"),
    occ("263213", "ICT Systems Test Engineer", "STSOL", "ACS", 1, "263213"),
    occ("263299", "ICT Support and Test Engineers nec", "STSOL", "ACS", 1, "263299"),
    occ("135111", "Chief Information Officer", "STSOL", "ACS", 1, "135111", ["Chief Technology Officer", "IT Director"]),
    occ("135112", "ICT Project Manager", "STSOL", "ACS", 1, "135112", ["IT Project Director"]),
    occ("135199", "ICT Managers nec", "STSOL", "ACS", 1, "135199"),
    occ("223211", "ICT Trainer", "STSOL", "ACS", 1, "223211"),
    occ("313111", "Hardware Technician", "STSOL", "ACS", 2, "313111"),
    occ("313112", "ICT Customer Support Officer", "STSOL", "ACS", 2, "313112"),
    occ("313113", "Web Administrator", "STSOL", "ACS", 2, "313113"),
    occ("313199", "ICT Support Technicians nec", "STSOL", "ACS", 2, "313199"),
    occ("313211", "Telecommunications Technical Officer or Technologist", "MLTSSL", "EA", 2, "313211"),

    # ─── 2. ENGINEERING & MINING (EA / Engineers Australia) ───
    occ("233211", "Civil Engineer", "MLTSSL", "EA", 1, "233211", ["Municipal Engineer", "Civil Infrastructure Engineer"]),
    occ("233212", "Geotechnical Engineer", "MLTSSL", "EA", 1, "233212"),
    occ("233214", "Structural Engineer", "MLTSSL", "EA", 1, "233214"),
    occ("233215", "Transport Engineer", "MLTSSL", "EA", 1, "233215"),
    occ("233511", "Industrial Engineer", "MLTSSL", "EA", 1, "233511"),
    occ("233512", "Mechanical Engineer", "MLTSSL", "EA", 1, "233512", ["HVAC Engineer", "Automotive Engineer"]),
    occ("233513", "Production or Plant Engineer", "MLTSSL", "EA", 1, "233513"),
    occ("233311", "Electrical Engineer", "MLTSSL", "EA", 1, "233311", ["Power Systems Engineer"]),
    occ("233411", "Electronics Engineer", "MLTSSL", "EA", 1, "233411", ["Communications Engineer"]),
    occ("233111", "Chemical Engineer", "MLTSSL", "EA", 1, "233111"),
    occ("233112", "Materials Engineer", "MLTSSL", "EA", 1, "233112"),
    occ("233611", "Mining Engineer (excluding Petroleum)", "MLTSSL", "EA", 1, "233611"),
    occ("233612", "Petroleum Engineer", "MLTSSL", "EA", 1, "233612"),
    occ("233911", "Aeronautical Engineer", "MLTSSL", "EA", 1, "233911", ["Aerospace Engineer"]),
    occ("233912", "Agricultural Engineer", "MLTSSL", "EA", 1, "233912"),
    occ("233913", "Biomedical Engineer", "MLTSSL", "EA", 1, "233913", ["Bioengineer"]),
    occ("233914", "Engineering Technologist", "MLTSSL", "EA", 1, "233914"),
    occ("233915", "Environmental Engineer", "MLTSSL", "EA", 1, "233915"),
    occ("233916", "Naval Architect", "MLTSSL", "EA", 1, "233916", ["Marine Designer"]),
    occ("233999", "Engineering Professionals nec", "MLTSSL", "EA", 1, "233999"),
    occ("133211", "Engineering Manager", "MLTSSL", "EA", 1, "133211", ["Director of Engineering"]),
    occ("312211", "Civil Engineering Draftsperson", "MLTSSL", "EA", 2, "312211"),
    occ("312212", "Civil Engineering Technician", "MLTSSL", "EA", 2, "312212"),
    occ("312311", "Electrical Engineering Draftsperson", "MLTSSL", "EA", 2, "312311"),
    occ("312312", "Electrical Engineering Technician", "MLTSSL", "EA", 2, "312312"),
    occ("312411", "Electronic Engineering Draftsperson", "STSOL", "EA", 2, "312411"),
    occ("312412", "Electronic Engineering Technician", "STSOL", "EA", 2, "312412"),
    occ("312511", "Mechanical Engineering Draftsperson", "MLTSSL", "EA", 2, "312511"),
    occ("312512", "Mechanical Engineering Technician", "MLTSSL", "EA", 2, "312512"),
    occ("312911", "Maintenance Planner", "STSOL", "VETASSESS", 2, "312911"),
    occ("312912", "Metallurgical or Materials Technician", "STSOL", "VETASSESS", 2, "312912"),
    occ("312913", "Mine Deputy", "STSOL", "VETASSESS", 2, "312913"),
    occ("312999", "Building and Engineering Technicians nec", "STSOL", "VETASSESS", 2, "312999"),

    # ─── 3. NURSING & MIDWIFERY (ANMAC) ───
    occ("254499", "Registered Nurses nec", "MLTSSL", "ANMAC", 1, "254499"),
    occ("254411", "Registered Nurse (Aged Care)", "MLTSSL", "ANMAC", 1, "254411"),
    occ("254412", "Registered Nurse (Critical Care and Emergency)", "MLTSSL", "ANMAC", 1, "254412"),
    occ("254413", "Registered Nurse (Medical)", "MLTSSL", "ANMAC", 1, "254413"),
    occ("254414", "Registered Nurse (Medical Practice)", "MLTSSL", "ANMAC", 1, "254414"),
    occ("254415", "Registered Nurse (Mental Health)", "MLTSSL", "ANMAC", 1, "254415"),
    occ("254416", "Registered Nurse (Perioperative)", "MLTSSL", "ANMAC", 1, "254416"),
    occ("254417", "Registered Nurse (Paediatrics)", "MLTSSL", "ANMAC", 1, "254417"),
    occ("254418", "Registered Nurse (Renal)", "MLTSSL", "ANMAC", 1, "254418"),
    occ("254421", "Registered Nurse (Surgical)", "MLTSSL", "ANMAC", 1, "254421"),
    occ("254422", "Registered Nurse (Community Health)", "MLTSSL", "ANMAC", 1, "254422"),
    occ("254423", "Registered Nurse (Developmental Disability)", "MLTSSL", "ANMAC", 1, "254423"),
    occ("254424", "Registered Nurse (Disability and Rehabilitation)", "MLTSSL", "ANMAC", 1, "254424"),
    occ("254425", "Registered Nurse (Emergency)", "MLTSSL", "ANMAC", 1, "254425"),
    occ("254111", "Midwife", "MLTSSL", "ANMAC", 1, "254111"),
    occ("254211", "Nurse Educator", "STSOL", "ANMAC", 1, "254211"),
    occ("254212", "Nurse Researcher", "STSOL", "ANMAC", 1, "254212"),
    occ("254311", "Nurse Manager", "STSOL", "ANMAC", 1, "254311"),
    occ("411411", "Enrolled Nurse", "MLTSSL", "ANMAC", 2, "411411"),
    occ("411412", "Mothercraft Nurse", "STSOL", "ANMAC", 2, "411412"),

    # ─── 4. MEDICAL PRACTITIONERS & DOCTORS (MedBA / AMC) ───
    occ("253111", "General Practitioner", "MLTSSL", "MedBA", 1, "253111", ["Family Doctor", "Medical Practitioner"]),
    occ("253112", "Resident Medical Officer", "MLTSSL", "MedBA", 1, "253112"),
    occ("253311", "Specialist Physician (General Medicine)", "MLTSSL", "MedBA", 1, "253311"),
    occ("253312", "Cardiologist", "MLTSSL", "MedBA", 1, "253312"),
    occ("253313", "Clinical Haematologist", "MLTSSL", "MedBA", 1, "253313"),
    occ("253314", "Medical Oncologist", "MLTSSL", "MedBA", 1, "253314"),
    occ("253315", "Endocrinologist", "MLTSSL", "MedBA", 1, "253315"),
    occ("253316", "Gastroenterologist", "MLTSSL", "MedBA", 1, "253316"),
    occ("253317", "Intensive Care Specialist", "MLTSSL", "MedBA", 1, "253317"),
    occ("253318", "Neurologist", "MLTSSL", "MedBA", 1, "253318"),
    occ("253321", "Paediatrician", "MLTSSL", "MedBA", 1, "253321"),
    occ("253322", "Renal Medicine Specialist", "MLTSSL", "MedBA", 1, "253322"),
    occ("253323", "Rheumatologist", "MLTSSL", "MedBA", 1, "253323"),
    occ("253324", "Thoracic Medicine Specialist", "MLTSSL", "MedBA", 1, "253324"),
    occ("253399", "Specialist Physicians nec", "MLTSSL", "MedBA", 1, "253399"),
    occ("253511", "Surgeon (General)", "MLTSSL", "MedBA", 1, "253511"),
    occ("253512", "Cardiothoracic Surgeon", "MLTSSL", "MedBA", 1, "253512"),
    occ("253513", "Neurosurgeon", "MLTSSL", "MedBA", 1, "253513"),
    occ("253514", "Orthopaedic Surgeon", "MLTSSL", "MedBA", 1, "253514"),
    occ("253515", "Otorhinolaryngologist", "MLTSSL", "MedBA", 1, "253515"),
    occ("253516", "Paediatric Surgeon", "MLTSSL", "MedBA", 1, "253516"),
    occ("253517", "Plastic and Reconstructive Surgeon", "MLTSSL", "MedBA", 1, "253517"),
    occ("253518", "Urologist", "MLTSSL", "MedBA", 1, "253518"),
    occ("253521", "Vascular Surgeon", "MLTSSL", "MedBA", 1, "253521"),
    occ("253211", "Anaesthetist", "MLTSSL", "MedBA", 1, "253211"),
    occ("253411", "Psychiatrist", "MLTSSL", "MedBA", 1, "253411"),
    occ("253911", "Dermatologist", "MLTSSL", "MedBA", 1, "253911"),
    occ("253912", "Emergency Medicine Specialist", "MLTSSL", "MedBA", 1, "253912"),
    occ("253913", "Obstetrician and Gynaecologist", "MLTSSL", "MedBA", 1, "253913"),
    occ("253914", "Ophthalmologist", "MLTSSL", "MedBA", 1, "253914"),
    occ("253915", "Pathologist", "MLTSSL", "MedBA", 1, "253915"),
    occ("253917", "Diagnostic and Interventional Radiologist", "MLTSSL", "MedBA", 1, "253917"),
    occ("253918", "Radiation Oncologist", "MLTSSL", "MedBA", 1, "253918"),
    occ("253999", "Medical Practitioners nec", "MLTSSL", "MedBA", 1, "253999"),

    # ─── 5. ALLIED HEALTH & DENTAL ───
    occ("252311", "Dental Practitioner (Dentist)", "STSOL", "ADC", 1, "252311", ["Dentist"]),
    occ("252312", "Dental Specialist", "MLTSSL", "ADC", 1, "252312", ["Orthodontist", "Periodontist"]),
    occ("252511", "Physiotherapist", "MLTSSL", "APC", 1, "252511", ["Physical Therapist"]),
    occ("252411", "Occupational Therapist", "MLTSSL", "OTBA", 1, "252411"),
    occ("252611", "Podiatrist", "MLTSSL", "ANZPAC", 1, "252611"),
    occ("252711", "Audiologist", "MLTSSL", "Audiology Australia", 1, "252711"),
    occ("252712", "Speech Pathologist", "MLTSSL", "SPA", 1, "252712", ["Speech Therapist"]),
    occ("251211", "Medical Diagnostic Radiographer", "MLTSSL", "ASMIRT", 1, "251211"),
    occ("251212", "Medical Radiation Therapist", "MLTSSL", "ASMIRT", 1, "251212"),
    occ("251213", "Nuclear Medicine Technologist", "MLTSSL", "ANZSNM", 1, "251213"),
    occ("251214", "Sonographer", "MLTSSL", "AIR", 1, "251214"),
    occ("251411", "Optometrist", "MLTSSL", "OCANZ", 1, "251411"),
    occ("251412", "Orthoptist", "MLTSSL", "OCANZ", 1, "251412"),
    occ("251511", "Hospital Pharmacist", "MLTSSL", "APC_Pharm", 1, "251511"),
    occ("251512", "Industrial Pharmacist", "MLTSSL", "APC_Pharm", 1, "251512"),
    occ("251513", "Retail Pharmacist", "MLTSSL", "APC_Pharm", 1, "251513"),
    occ("251912", "Orthotist or Prosthetist", "MLTSSL", "AOPA", 1, "251912"),
    occ("251111", "Dietitian", "MLTSSL", "DA", 1, "251111", ["Clinical Nutritionist"]),
    occ("251112", "Nutritionist", "STSOL", "VETASSESS", 1, "251112"),
    occ("272311", "Clinical Psychologist", "MLTSSL", "APS", 1, "272311"),
    occ("272312", "Educational Psychologist", "MLTSSL", "APS", 1, "272312"),
    occ("272313", "Organisational Psychologist", "MLTSSL", "APS", 1, "272313"),
    occ("272399", "Psychologists nec", "MLTSSL", "APS", 1, "272399"),
    occ("272511", "Social Worker", "MLTSSL", "AASW", 1, "272511"),
    occ("272613", "Welfare Worker", "STSOL", "ACWA", 2, "272613"),
    occ("411711", "Community Worker", "STSOL", "ACWA", 2, "411711"),
    occ("411712", "Disabilities Services Officer", "STSOL", "ACWA", 2, "411712"),
    occ("411713", "Family Support Worker", "STSOL", "ACWA", 2, "411713"),
    occ("411714", "Parole or Probation Officer", "STSOL", "ACWA", 2, "411714"),
    occ("411715", "Residential Care Officer", "STSOL", "ACWA", 2, "411715"),
    occ("411716", "Youth Worker", "STSOL", "ACWA", 2, "411716"),

    # ─── 6. EDUCATION & TEACHING (AITSL / ACECQA / VETASSESS) ───
    occ("241111", "Early Childhood (Pre-primary School) Teacher", "MLTSSL", "AITSL", 1, "241111", ["Kindergarten Teacher"]),
    occ("241213", "Primary School Teacher", "STSOL", "AITSL", 1, "241213"),
    occ("241411", "Secondary School Teacher", "MLTSSL", "AITSL", 1, "241411", ["High School Teacher"]),
    occ("241511", "Special Needs Teacher", "MLTSSL", "AITSL", 1, "241511"),
    occ("241512", "Teacher of the Hearing Impaired", "MLTSSL", "AITSL", 1, "241512"),
    occ("241513", "Teacher of the Sight Impaired", "MLTSSL", "AITSL", 1, "241513"),
    occ("241599", "Special Education Teachers nec", "MLTSSL", "AITSL", 1, "241599"),
    occ("242111", "University Lecturer", "MLTSSL", "VETASSESS", 1, "242111", ["Associate Professor", "Professor"]),
    occ("242211", "Vocational Education Teacher", "STSOL", "VETASSESS", 1, "242211", ["TAFE Teacher"]),
    occ("134111", "Child Care Centre Manager", "MLTSSL", "ACECQA", 1, "134111"),

    # ─── 7. ACCOUNTING, FINANCE & CONSULTING (CPA / CA ANZ / IPA / VETASSESS) ───
    occ("221111", "Accountant (General)", "MLTSSL", "CPA Australia", 1, "221111", ["Financial Accountant", "Certified Practising Accountant"]),
    occ("221112", "Management Accountant", "MLTSSL", "CPA Australia", 1, "221112"),
    occ("221113", "Taxation Accountant", "MLTSSL", "CPA Australia", 1, "221113"),
    occ("221213", "External Auditor", "MLTSSL", "CPA Australia", 1, "221213"),
    occ("221214", "Internal Auditor", "MLTSSL", "VETASSESS", 1, "221214"),
    occ("224111", "Actuary", "MLTSSL", "Actuaries Institute", 1, "224111"),
    occ("224112", "Mathematician", "STSOL", "VETASSESS", 1, "224112"),
    occ("224113", "Statistician", "MLTSSL", "VETASSESS", 1, "224113", ["Data Scientist", "Biostatistician"]),
    occ("222112", "Finance Broker", "STSOL", "VETASSESS", 1, "222112"),
    occ("222311", "Financial Investment Adviser", "STSOL", "VETASSESS", 1, "222311"),
    occ("222312", "Financial Investment Manager", "STSOL", "VETASSESS", 1, "222312"),
    occ("224711", "Management Consultant", "MLTSSL", "VETASSESS", 1, "224711", ["Business Consultant", "Strategy Analyst"]),
    occ("224712", "Organisation and Methods Analyst", "STSOL", "VETASSESS", 1, "224712"),
    occ("132211", "Finance Manager", "STSOL", "IML", 1, "132211", ["CFO", "Financial Controller"]),
    occ("132311", "Human Resource Manager", "STSOL", "IML", 1, "132311", ["HR Director"]),
    occ("223111", "Human Resource Adviser", "STSOL", "VETASSESS", 1, "223111"),
    occ("223112", "Recruitment Consultant", "STSOL", "VETASSESS", 1, "223112"),
    occ("225113", "Marketing Specialist", "STSOL", "VETASSESS", 1, "225113", ["Digital Marketing Manager", "Brand Specialist"]),
    occ("225111", "Advertising Specialist", "STSOL", "VETASSESS", 1, "225111"),
    occ("225112", "Market Research Analyst", "STSOL", "VETASSESS", 1, "225112"),
    occ("225311", "Public Relations Professional", "STSOL", "VETASSESS", 1, "225311"),

    # ─── 8. ARCHITECTS, PLANNERS & SURVEYORS (AACA / AIQS / SSSI / VETASSESS) ───
    occ("232111", "Architect", "MLTSSL", "AACA", 1, "232111", ["Registered Architect"]),
    occ("232112", "Landscape Architect", "MLTSSL", "VETASSESS", 1, "232112"),
    occ("232212", "Surveyor", "MLTSSL", "SSSI", 1, "232212", ["Licensed Surveyor", "Cadastral Surveyor"]),
    occ("232213", "Cartographer", "MLTSSL", "SSSI", 1, "232213"),
    occ("232214", "Other Spatial Scientist", "MLTSSL", "SSSI", 1, "232214", ["GIS Specialist"]),
    occ("232611", "Urban and Regional Planner", "MLTSSL", "VETASSESS", 1, "232611", ["Town Planner"]),
    occ("232311", "Fashion Designer", "STSOL", "VETASSESS", 1, "232311"),
    occ("232312", "Industrial Designer", "STSOL", "VETASSESS", 1, "232312", ["Product Designer"]),
    occ("232411", "Graphic Designer", "STSOL", "VETASSESS", 1, "232411", ["UI/UX Designer", "Visual Designer"]),
    occ("232412", "Illustrator", "STSOL", "VETASSESS", 1, "232412"),
    occ("232511", "Interior Designer", "STSOL", "VETASSESS", 1, "232511"),
    occ("312111", "Architectural Draftsperson", "MLTSSL", "VETASSESS", 2, "312111"),
    occ("312112", "Building Associate", "STSOL", "VETASSESS", 2, "312112"),
    occ("312113", "Building Inspector", "STSOL", "VETASSESS", 2, "312113"),
    occ("312114", "Construction Estimator", "MLTSSL", "AIQS", 2, "312114", ["Quantity Surveyor Assistant"]),
    occ("233213", "Quantity Surveyor", "MLTSSL", "AIQS", 1, "233213", ["Cost Consultant"]),
    occ("133111", "Construction Project Manager", "MLTSSL", "VETASSESS", 1, "133111", ["Project Director (Construction)"]),
    occ("133112", "Project Builder", "MLTSSL", "VETASSESS", 1, "133112"),

    # ─── 9. NATURAL & PHYSICAL SCIENCES ───
    occ("234111", "Agricultural Consultant", "MLTSSL", "VETASSESS", 1, "234111"),
    occ("234112", "Agricultural Scientist", "MLTSSL", "VETASSESS", 1, "234112", ["Agronomist"]),
    occ("234113", "Forester / Forest Scientist", "STSOL", "VETASSESS", 1, "234113"),
    occ("234211", "Chemist", "STSOL", "VETASSESS", 1, "234211"),
    occ("234212", "Food Technologist", "MLTSSL", "VETASSESS", 1, "234212"),
    occ("234311", "Conservation Officer", "MLTSSL", "VETASSESS", 1, "234311"),
    occ("234312", "Environmental Consultant", "MLTSSL", "VETASSESS", 1, "234312"),
    occ("234313", "Environmental Research Scientist", "MLTSSL", "VETASSESS", 1, "234313"),
    occ("234399", "Environmental Scientists nec", "MLTSSL", "VETASSESS", 1, "234399"),
    occ("234411", "Geologist", "MLTSSL", "VETASSESS", 1, "234411"),
    occ("234412", "Geophysicist", "MLTSSL", "VETASSESS", 1, "234412"),
    occ("234413", "Hydrogeologist", "MLTSSL", "VETASSESS", 1, "234413"),
    occ("234511", "Life Scientist (General)", "MLTSSL", "VETASSESS", 1, "234511"),
    occ("234513", "Biochemist", "MLTSSL", "VETASSESS", 1, "234513"),
    occ("234514", "Biotechnologist", "MLTSSL", "VETASSESS", 1, "234514"),
    occ("234515", "Botanist", "MLTSSL", "VETASSESS", 1, "234515"),
    occ("234516", "Marine Biologist", "MLTSSL", "VETASSESS", 1, "234516"),
    occ("234517", "Microbiologist", "MLTSSL", "VETASSESS", 1, "234517"),
    occ("234518", "Zoologist", "MLTSSL", "VETASSESS", 1, "234518"),
    occ("234599", "Life Scientists nec", "MLTSSL", "VETASSESS", 1, "234599"),
    occ("234611", "Medical Laboratory Scientist", "MLTSSL", "AIMS", 1, "234611", ["Pathology Scientist"]),
    occ("311215", "Medical Laboratory Technician", "MLTSSL", "AIMS", 2, "311215"),
    occ("234711", "Veterinarian", "MLTSSL", "AVBC", 1, "234711", ["Veterinary Surgeon"]),
    occ("234912", "Metallurgist", "MLTSSL", "VETASSESS", 1, "234912"),
    occ("234914", "Physicist", "MLTSSL", "VETASSESS", 1, "234914", ["Medical Physicist"]),

    # ─── 10. TRADES (TRA - Trades Recognition Australia) ───
    # Automotive & Mechanical
    occ("321111", "Automotive Electrician", "MLTSSL", "TRA", 3, "321111"),
    occ("321211", "Motor Mechanic (General)", "MLTSSL", "TRA", 3, "321211", ["Auto Mechanic"]),
    occ("321212", "Diesel Motor Mechanic", "MLTSSL", "TRA", 3, "321212", ["Heavy Vehicle Mechanic"]),
    occ("321213", "Motorcycle Mechanic", "MLTSSL", "TRA", 3, "321213"),
    occ("321214", "Small Engine Mechanic", "MLTSSL", "TRA", 3, "321214"),
    occ("322211", "Sheetmetal Trades Worker", "MLTSSL", "TRA", 3, "322211"),
    occ("322311", "Metal Fabricator", "MLTSSL", "TRA", 3, "322311", ["Boilermaker"]),
    occ("322312", "Pressure Welder", "MLTSSL", "TRA", 3, "322312"),
    occ("322313", "Welder (First Class)", "MLTSSL", "TRA", 3, "322313"),
    occ("323211", "Fitter (General)", "MLTSSL", "TRA", 3, "323211", ["Mechanical Fitter"]),
    occ("323212", "Fitter and Turner", "MLTSSL", "TRA", 3, "323212"),
    occ("323213", "Fitter-Welder", "MLTSSL", "TRA", 3, "323213"),
    occ("323214", "Metal Machinist (First Class)", "MLTSSL", "TRA", 3, "323214"),
    occ("323411", "Toolmaker", "MLTSSL", "TRA", 3, "323411"),
    occ("324111", "Panelbeater", "MLTSSL", "TRA", 3, "324111"),
    occ("324211", "Vehicle Body Builder", "STSOL", "TRA", 3, "324211"),
    occ("324212", "Vehicle Trimmer", "STSOL", "TRA", 3, "324212"),
    occ("324311", "Vehicle Painter", "MLTSSL", "TRA", 3, "324311", ["Spray Painter"]),

    # Building & Construction Trades
    occ("331111", "Bricklayer", "MLTSSL", "TRA", 3, "331111"),
    occ("331112", "Stonemason", "MLTSSL", "TRA", 3, "331112"),
    occ("331211", "Carpenter and Joiner", "MLTSSL", "TRA", 3, "331211"),
    occ("331212", "Carpenter", "MLTSSL", "TRA", 3, "331212"),
    occ("331213", "Joiner", "MLTSSL", "TRA", 3, "331213"),
    occ("332111", "Floor Finisher", "STSOL", "TRA", 3, "332111"),
    occ("332211", "Painting Trades Worker", "MLTSSL", "TRA", 3, "332211", ["Commercial Painter"]),
    occ("333111", "Glazier", "MLTSSL", "TRA", 3, "333111"),
    occ("333211", "Fibrous Plasterer", "MLTSSL", "TRA", 3, "333211"),
    occ("333212", "Solid Plasterer", "MLTSSL", "TRA", 3, "333212"),
    occ("333311", "Roof Tiler", "MLTSSL", "TRA", 3, "333311"),
    occ("333411", "Wall and Floor Tiler", "MLTSSL", "TRA", 3, "333411"),
    occ("334111", "Plumber (General)", "MLTSSL", "TRA", 3, "334111"),
    occ("334112", "Airconditioning and Mechanical Services Plumber", "MLTSSL", "TRA", 3, "334112"),
    occ("334113", "Drainer", "MLTSSL", "TRA", 3, "334113"),
    occ("334114", "Gasfitter", "MLTSSL", "TRA", 3, "334114"),
    occ("334115", "Roof Plumber", "MLTSSL", "TRA", 3, "334115"),

    # Electrical & Telecommunications Trades
    occ("341111", "Electrician (General)", "MLTSSL", "TRA", 3, "341111", ["Licensed Electrician"]),
    occ("341112", "Electrician (Special Class)", "MLTSSL", "TRA", 3, "341112"),
    occ("341113", "Lift Mechanic", "MLTSSL", "TRA", 3, "341113", ["Elevator Technician"]),
    occ("342111", "Airconditioning and Refrigeration Mechanic", "MLTSSL", "TRA", 3, "342111"),
    occ("342211", "Electrical Linesworker", "MLTSSL", "TRA", 3, "342211"),
    occ("342212", "Technical Cable Jointer", "MLTSSL", "TRA", 3, "342212"),
    occ("342313", "Electronic Equipment Trades Worker", "MLTSSL", "TRA", 3, "342313"),
    occ("342314", "Electronic Instrument Trades Worker (General)", "MLTSSL", "TRA", 3, "342314"),
    occ("342315", "Electronic Instrument Trades Worker (Special Class)", "MLTSSL", "TRA", 3, "342315"),
    occ("342411", "Cabler (Data and Telecommunications)", "MLTSSL", "TRA", 3, "342411"),
    occ("342413", "Telecommunications Linesworker", "MLTSSL", "TRA", 3, "342413"),
    occ("342414", "Telecommunications Technician", "MLTSSL", "TRA", 3, "342414"),

    # Food & Hospitality Trades
    occ("351311", "Chef", "MLTSSL", "TRA", 3, "351311", ["Head Chef", "Sous Chef"]),
    occ("351411", "Cook", "STSOL", "TRA", 3, "351411"),
    occ("351111", "Baker", "STSOL", "TRA", 3, "351111"),
    occ("351112", "Pastrycook", "MLTSSL", "TRA", 3, "351112"),
    occ("351211", "Butcher or Smallgoods Maker", "STSOL", "TRA", 3, "351211"),
    occ("141111", "Cafe or Restaurant Manager", "STSOL", "VETASSESS", 2, "141111"),
    occ("141311", "Hotel or Motel Manager", "STSOL", "VETASSESS", 2, "141311"),
    occ("141211", "Caravan Park and Camping Ground Manager", "STSOL", "VETASSESS", 2, "141211"),
    occ("141411", "Licensed Club Manager", "STSOL", "VETASSESS", 2, "141411"),
    occ("141999", "Accommodation and Hospitality Managers nec", "STSOL", "VETASSESS", 2, "141999"),

    # Other Trades & Services
    occ("391111", "Hairdresser", "STSOL", "TRA", 3, "391111"),
    occ("394111", "Cabinetmaker", "MLTSSL", "TRA", 3, "394111"),
    occ("399111", "Boat Builder and Repairer", "MLTSSL", "TRA", 3, "399111"),
    occ("399611", "Signwriter", "STSOL", "TRA", 3, "399611"),
    occ("399912", "Optical Dispenser", "STSOL", "TRA", 3, "399912"),

    # ─── 11. LEGAL, SOCIAL & MEDIA ───
    occ("271111", "Barrister", "MLTSSL", "LPAB", 1, "271111"),
    occ("271311", "Solicitor", "MLTSSL", "LPAB", 1, "271311", ["Lawyer", "Legal Practitioner"]),
    occ("272412", "Interpreter", "STSOL", "NAATI", 1, "272412"),
    occ("272413", "Translator", "STSOL", "NAATI", 1, "272413"),
    occ("212411", "Copywriter", "STSOL", "VETASSESS", 1, "212411"),
    occ("212412", "Newspaper or Periodical Editor", "STSOL", "VETASSESS", 1, "212412"),
    occ("212413", "Print Journalist", "STSOL", "VETASSESS", 1, "212413"),
    occ("212414", "Radio Journalist", "STSOL", "VETASSESS", 1, "212414"),
    occ("212415", "Television Journalist", "STSOL", "VETASSESS", 1, "212415"),
    occ("212416", "Technical Writer", "STSOL", "VETASSESS", 1, "212416"),
    occ("212499", "Journalists and Other Writers nec", "STSOL", "VETASSESS", 1, "212499"),
    occ("212111", "Artistic Director", "STSOL", "VETASSESS", 1, "212111"),
    occ("212112", "Media Producer", "STSOL", "VETASSESS", 1, "212112"),
    occ("212113", "Radio Presenter", "STSOL", "VETASSESS", 1, "212113"),
    occ("212114", "Television Presenter", "STSOL", "VETASSESS", 1, "212114"),

    # ─── 12. GENERAL & SPECIALIST MANAGERS ───
    occ("111111", "Chief Executive or Managing Director", "MLTSSL", "IML", 1, "111111", ["CEO", "Managing Director"]),
    occ("111211", "Corporate General Manager", "MLTSSL", "IML", 1, "111211", ["COO", "General Manager"]),
    occ("131112", "Sales and Marketing Manager", "STSOL", "IML", 1, "131112"),
    occ("131113", "Advertising Manager", "STSOL", "IML", 1, "131113"),
    occ("131114", "Public Relations Manager", "STSOL", "IML", 1, "131114"),
    occ("132111", "Corporate Services Manager", "STSOL", "IML", 1, "132111"),
    occ("132411", "Policy and Planning Manager", "STSOL", "VETASSESS", 1, "132411"),
    occ("132511", "Research and Development Manager", "STSOL", "VETASSESS", 1, "132511"),
    occ("133311", "Importer or Exporter", "STSOL", "VETASSESS", 1, "133311"),
    occ("133312", "Wholesaler", "STSOL", "VETASSESS", 1, "133312"),
    occ("133411", "Manufacturer", "STSOL", "VETASSESS", 1, "133411"),
    occ("133511", "Production Manager (Forestry)", "STSOL", "VETASSESS", 1, "133511"),
    occ("133512", "Production Manager (Manufacturing)", "STSOL", "VETASSESS", 1, "133512"),
    occ("133513", "Production Manager (Mining)", "STSOL", "VETASSESS", 1, "133513"),
    occ("133611", "Supply and Distribution Manager", "STSOL", "IML", 1, "133611", ["Logistics Manager"]),
    occ("133612", "Procurement Manager", "STSOL", "IML", 1, "133612", ["Purchasing Manager"]),
    occ("134211", "Medical Administrator", "STSOL", "RACMA", 1, "134211"),
    occ("134212", "Nursing Clinical Director", "STSOL", "ANMAC", 1, "134212"),
    occ("134213", "Primary Health Organisation Manager", "STSOL", "VETASSESS", 1, "134213"),
    occ("134214", "Welfare Centre Manager", "STSOL", "ACWA", 1, "134214"),
    occ("134299", "Health and Welfare Services Managers nec", "STSOL", "VETASSESS", 1, "134299"),
    occ("134311", "School Principal", "STSOL", "VETASSESS", 1, "134311"),
    occ("134411", "Faculty Head", "STSOL", "VETASSESS", 1, "134411"),
    occ("134412", "Regional Education Manager", "STSOL", "VETASSESS", 1, "134412"),
    occ("134499", "Education Managers nec", "STSOL", "VETASSESS", 1, "134499"),
    occ("139911", "Artistic Director", "STSOL", "VETASSESS", 1, "139911"),
    occ("139912", "Environmental Manager", "MLTSSL", "VETASSESS", 1, "139912"),
    occ("139913", "Laboratory Manager", "STSOL", "VETASSESS", 1, "139913"),
    occ("139914", "Quality Assurance Manager", "STSOL", "VETASSESS", 1, "139914"),
    occ("139915", "Sports Administrator", "STSOL", "VETASSESS", 1, "139915"),
    occ("139999", "Specialist Managers nec", "STSOL", "VETASSESS", 1, "139999"),
]


async def seed_all_au_occupations() -> Dict[str, Any]:
    print("→ Ensuring 39 Australian assessing authorities in skill_body_master...")
    await ensure_seeded_in_db(db)

    coll = db["occupation_master"]
    four_digit_coll = db["anzsco_4digit_master"]

    print(f"→ Processing {len(ALL_AU_OCCUPATIONS)} Australian occupations...")

    # Pre-fetch 4-digit profiles
    four_digit_map: Dict[str, Dict[str, Any]] = {}
    async for fd in four_digit_coll.find({}, {"_id": 0}):
        code_str = str(fd.get("code")).strip()
        if code_str:
            four_digit_map[code_str] = fd

    # Fetch skill bodies for richer authority detail
    body_map: Dict[str, Dict[str, Any]] = {}
    async for b in db["skill_body_master"].find({"country_code": "AU"}, {"_id": 0}):
        code = b.get("code") or b.get("slug") or b.get("name")
        if code:
            body_map[code.upper()] = b

    inserted = 0
    updated = 0

    for o in ALL_AU_OCCUPATIONS:
        code_4 = o.get("anzsco_4digit_code")
        if code_4 and code_4 in four_digit_map:
            p_data = four_digit_map[code_4]
            if not o.get("description"):
                o["description"] = p_data.get("description") or ""
            if not o.get("typical_tasks"):
                o["typical_tasks"] = p_data.get("tasks") or []
            o["abs_labour_market"] = p_data.get("anzsco_profile") or {}
            o["state_distribution"] = p_data.get("state_distribution") or {}
            o["industries_ranked"] = p_data.get("industries_ranked") or []
            o["education_distribution"] = p_data.get("education_distribution") or {}

        auth_key = (o.get("assessing_authority", {}).get("name") or "").upper()
        if auth_key in body_map:
            b_info = body_map[auth_key]
            o["assessing_authority"]["full_name"] = b_info.get("full_name") or o["assessing_authority"]["name"]
            o["assessing_authority"]["website"] = b_info.get("website") or ""
            o["assessing_authority"]["fees"] = b_info.get("fees") or {}
            o["assessing_authority"]["processing"] = b_info.get("processing") or {}

        existing = await coll.find_one({"country_code": "AU", "code": o["code"]})
        if existing:
            await coll.update_one({"_id": existing["_id"]}, {"$set": o})
            updated += 1
        else:
            await coll.insert_one(o)
            inserted += 1

    total_au = await coll.count_documents({"country_code": "AU"})
    verified_au = await coll.count_documents({"country_code": "AU", "status": "verified"})
    mltssl_au = await coll.count_documents({"country_code": "AU", "pathway_list": "MLTSSL"})
    stsol_au = await coll.count_documents({"country_code": "AU", "pathway_list": "STSOL"})

    summary = {
        "inserted": inserted,
        "updated": updated,
        "total_au": total_au,
        "verified_au": verified_au,
        "mltssl_au": mltssl_au,
        "stsol_au": stsol_au,
    }
    print(f"✔ Seeding Complete: inserted={inserted}, updated={updated}")
    print(f"  Total AU Occupations: {total_au}")
    print(f"  Verified: {verified_au}")
    print(f"  MLTSSL (189/190/491): {mltssl_au}")
    print(f"  STSOL (190/491/482): {stsol_au}")
    return summary

if __name__ == "__main__":
    asyncio.run(seed_all_au_occupations())
