"""Test comprehensive parse_resume_heuristically."""
import re
import os
from datetime import datetime

base_dir = os.path.dirname(__file__)
sample_dir = os.path.join(base_dir, "..", "test_data")

def infer_company_nature(company_name: str, context_text: str) -> str:
    combined = f"{company_name} {context_text}".lower()
    if any(k in combined for k in ["hotel", "resort", "restaurant", "hospitality", "taj", "marriott", "hyatt", "hilton", "catering", "dining", "culinary", "kitchen", "food"]):
        return "Hospitality, Hotels & Food Services"
    if any(k in combined for k in ["infosys", "tcs", "wipro", "cognizant", "tech mahindra", "software", "technology", "technologies", "solutions", "it services", "cloud", "saas", "systems", "developer"]):
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
    return "Professional & Commercial Services"

def parse_work_experience_blocks(text: str) -> list:
    sec_match = re.search(r'(?:WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|EMPLOYMENT HISTORY|EXPERIENCE)\s*[:\n]+(.*?)(?=\n\s*(?:EDUCATION|ACADEMIC|QUALIFICATIONS|LANGUAGE|SKILLS|CERTIFICATIONS|PROJECTS|\Z))', text, re.I | re.DOTALL)
    sec_text = sec_match.group(1).strip() if sec_match else text
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
            is_cur = "present" in dates.lower() or "current" in dates.lower()
            
            current_entry = {
                "designation": title,
                "employer": company,
                "location": location,
                "dates": dates,
                "is_current": is_cur,
                "company_nature": infer_company_nature(company, title),
                "duty_bullets": [],
            }
        elif current_entry:
            bullet = re.sub(r'^[\-\*•·–—\d\.\)]\s*', '', line_s).strip()
            if bullet:
                current_entry["duty_bullets"].append(bullet)
    
    if current_entry:
        entries.append(current_entry)
        
    for e in entries:
        e["duties"] = "; ".join(e["duty_bullets"]) if e["duty_bullets"] else f"Worked as {e['designation']} at {e['employer']}."
        e["company_nature"] = infer_company_nature(e["employer"], f"{e['designation']} {e['duties']}")
    
    return entries

def parse_education_blocks(text: str) -> list:
    sec_match = re.search(r'(?:EDUCATION|ACADEMIC BACKGROUND|ACADEMIC QUALIFICATIONS|QUALIFICATIONS)\s*[:\n]+(.*?)(?=\n\s*(?:WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|EMPLOYMENT|LANGUAGE|SKILLS|CERTIFICATIONS|\Z))', text, re.I | re.DOTALL)
    sec_text = sec_match.group(1).strip() if sec_match else text
    lines = [l.strip() for l in sec_text.splitlines() if l.strip()]
    
    quals = []
    i = 0
    while i < len(lines):
        line = lines[i]
        deg_match = re.search(r'(Bachelor|Master|Diploma|Doctorate|PhD|B\.Tech|M\.Tech|B\.Sc|M\.Sc|B\.E|B\.Com|MBA|Certificate)[^,\n]*', line, re.I)
        if deg_match:
            deg_title = line
            inst = "Accredited University"
            country = "India"
            year = None
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                y_m = re.search(r'\b(19\d{2}|20[012]\d)\b', next_line)
                if y_m:
                    year = int(y_m.group(1))
                clean_inst = re.sub(r'[\s—–-]+\b(19\d{2}|20[012]\d)\b.*', '', next_line).strip()
                if clean_inst:
                    inst = clean_inst
                if "india" in next_line.lower():
                    country = "India"
                elif "australia" in next_line.lower():
                    country = "Australia"
                elif "uk" in next_line.lower() or "united kingdom" in next_line.lower():
                    country = "United Kingdom"
                elif "usa" in next_line.lower() or "united states" in next_line.lower():
                    country = "United States"
                elif "canada" in next_line.lower():
                    country = "Canada"
                i += 1
            quals.append({
                "degree": deg_title,
                "institution": inst,
                "country": country,
                "year_completed": year,
                "completed": True,
            })
        i += 1
    return quals

for f in ["sample_resume.txt", "sample_resume_chef.txt"]:
    with open(os.path.join(sample_dir, f), "r", encoding="utf-8") as fl:
        txt = fl.read()
    print(f"=== {f} ===")
    jobs = parse_work_experience_blocks(txt)
    print("Jobs count:", len(jobs))
    for j in jobs:
        print(" ", j["designation"], "|", j["employer"], "|", j["company_nature"])
        print("   duties:", j["duties"])
    edus = parse_education_blocks(txt)
    print("Edus count:", len(edus))
    for e in edus:
        print(" ", e["degree"], "|", e["institution"], "|", e["year_completed"])
