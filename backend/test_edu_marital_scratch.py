"""Test scratch script for complete extraction."""
import re
import os
from datetime import datetime

base_dir = os.path.dirname(__file__)
sample_dir = os.path.join(base_dir, "..", "test_data")

def extract_marital_status(text: str) -> str:
    m = re.search(r'marital\s*status\s*[:\s-]+([A-Za-z\- ]+)', text, re.I)
    if m:
        val = m.group(1).strip().lower()
        if "marri" in val:
            return "married"
        if "single" in val or "unmarried" in val:
            return "single"
        if "de facto" in val or "defacto" in val:
            return "de_facto"
        if "divorc" in val:
            return "divorced"
        if "widow" in val:
            return "widowed"
    if re.search(r'\b(married|spouse|wife|husband)\b', text, re.I):
        return "married"
    return "single"

def extract_education_blocks(text: str) -> list:
    sec_match = re.search(r'(?:EDUCATION|ACADEMIC BACKGROUND|QUALIFICATIONS)\s*[:\n]+(.*?)(?=\n\s*(?:WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|EMPLOYMENT|LANGUAGE|SKILLS|CERTIFICATIONS|\Z))', text, re.I | re.DOTALL)
    if not sec_match:
        return []
    
    sec_text = sec_match.group(1).strip()
    lines = [l.strip() for l in sec_text.splitlines() if l.strip()]
    
    quals = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check degree line
        deg_match = re.search(r'(Bachelor|Master|Diploma|Doctorate|PhD|B\.Tech|M\.Tech|B\.Sc|M\.Sc|B\.E|B\.Com|MBA|Certificate)[^,\n]*', line, re.I)
        if deg_match:
            deg_title = line
            inst = ""
            year = None
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # look for university / college and year
                y_m = re.search(r'\b(19\d{2}|20[012]\d)\b', next_line)
                if y_m:
                    year = int(y_m.group(1))
                inst = re.sub(r'[\s—–-]+\b(19\d{2}|20[012]\d)\b.*', '', next_line).strip()
                i += 1
            quals.append({
                "degree": deg_title,
                "institution": inst,
                "year_completed": year,
            })
        i += 1
    return quals

for f in ["sample_resume.txt", "sample_resume_chef.txt"]:
    with open(os.path.join(sample_dir, f), "r", encoding="utf-8") as fl:
        txt = fl.read()
    print(f"=== {f} ===")
    print("Marital:", extract_marital_status(txt))
    print("Edu:", extract_education_blocks(txt))
