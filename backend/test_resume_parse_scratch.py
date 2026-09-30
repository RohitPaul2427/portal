"""Test scratch script for enhanced resume parser."""
import re
from datetime import datetime

def infer_company_nature(company_name: str, context_text: str) -> str:
    combined = f"{company_name} {context_text}".lower()
    
    if any(k in combined for k in ["hotel", "resort", "restaurant", "hospitality", "taj", "marriott", "hyatt", "hilton", "catering", "dining", "culinary", "kitchen"]):
        return "Hospitality, Hotels & Food Services"
    if any(k in combined for k in ["infosys", "tcs", "wipro", "cognizant", "tech mahindra", "software", "technology", "technologies", "solutions", "it services", "cloud", "saas", "systems"]):
        return "Information Technology & Software Services"
    if any(k in combined for k in ["hospital", "clinic", "healthcare", "health", "pharma", "pharmaceutical", "biotech", "clinical", "medical", "nursing", "biomarker"]):
        return "Healthcare, Pharmaceuticals & Life Sciences"
    if any(k in combined for k in ["bank", "banking", "finance", "financial", "insurance", "capital", "wealth", "investment", "audit", "accounting"]):
        return "Banking, Financial & Insurance Services"
    if any(k in combined for k in ["law", "legal", "advocate", "solicitor", "chambers", "court", "attorney", "conveyancing"]):
        return "Legal Services & Law Practice"
    if any(k in combined for k in ["construct", "infrastructure", "builder", "engineering", "contractor", "civil", "architect"]):
        return "Construction, Infrastructure & Engineering"
    if any(k in combined for k in ["school", "college", "university", "institute", "education", "academy", "teaching", "tuition"]):
        return "Education & Academic Training"
    if any(k in combined for k in ["retail", "ecommerce", "store", "fmcg", "consumer"]):
        return "Retail, FMCG & Consumer Goods"
    if any(k in combined for k in ["manufacturing", "factory", "automotive", "motors", "industrial"]):
        return "Manufacturing & Industrial Production"
    return "Corporate Services & Enterprise Operations"

def parse_work_experience_blocks(text: str) -> list:
    # Locate work experience section
    sec_match = re.search(r'(?:WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|EMPLOYMENT HISTORY|EXPERIENCE)\s*[:\n]+(.*?)(?=\n\s*(?:EDUCATION|ACADEMIC|QUALIFICATIONS|LANGUAGE|SKILLS|CERTIFICATIONS|PROJECTS|\Z))', text, re.I | re.DOTALL)
    if not sec_match:
        return []
    
    sec_text = sec_match.group(1).strip()
    lines = [l.rstrip() for l in sec_text.splitlines() if l.strip()]
    
    entries = []
    current_entry = None
    
    header_pattern = re.compile(
        r'^(?P<title>[A-Za-z0-9\s\(\)\/\-\,\&]+?)\s*(?:—|–|-|\||at|\@)\s*(?P<company>[A-Za-z0-9\s\.\,\&]+?)(?:,\s*(?P<loc>[A-Za-z\s]+?))?\s*\((?P<dates>[^\)]+)\)$',
        re.IGNORECASE
    )
    
    for line in lines:
        line_s = line.strip()
        m = header_pattern.match(line_s)
        if m:
            if current_entry:
                entries.append(current_entry)
            
            title = m.group("title").strip()
            company = m.group("company").strip()
            location = (m.group("loc") or "").strip()
            dates = m.group("dates").strip()
            
            current_entry = {
                "designation": title,
                "employer": company,
                "location": location,
                "dates": dates,
                "company_nature": infer_company_nature(company, title),
                "duty_bullets": [],
            }
        elif current_entry:
            # Bullet point or duty description line
            bullet = re.sub(r'^[\-\*•·–—\d\.\)]\s*', '', line_s).strip()
            if bullet:
                current_entry["duty_bullets"].append(bullet)
    
    if current_entry:
        entries.append(current_entry)
        
    for e in entries:
        e["duties"] = "; ".join(e["duty_bullets"]) if e["duty_bullets"] else f"Worked as {e['designation']} at {e['employer']}."
        # Update company_nature with full duty context
        e["company_nature"] = infer_company_nature(e["employer"], f"{e['designation']} {e['duties']}")
    
    return entries

import os
base_dir = os.path.dirname(__file__)
sample_dir = os.path.join(base_dir, "..", "test_data")
with open(os.path.join(sample_dir, "sample_resume.txt"), "r", encoding="utf-8") as f:
    t1 = f.read()

jobs1 = parse_work_experience_blocks(t1)
print("--- JOBS 1 ---")
for j in jobs1:
    print(f"Title: {j['designation']} | Company: {j['employer']} | Dates: {j['dates']} | Nature: {j['company_nature']}")
    print(f"  Duties ({len(j['duty_bullets'])}): {j['duties']}")

# Test on sample_resume_chef.txt
with open(os.path.join(sample_dir, "sample_resume_chef.txt"), "r", encoding="utf-8") as f:
    t2 = f.read()

jobs2 = parse_work_experience_blocks(t2)
print("--- JOBS 2 ---")
for j in jobs2:
    print(f"Title: {j['designation']} | Company: {j['employer']} | Dates: {j['dates']} | Nature: {j['company_nature']}")
    print(f"  Duties ({len(j['duty_bullets'])}): {j['duties']}")
