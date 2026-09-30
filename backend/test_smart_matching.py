"""Test script for smart duty and company matching against occupation_master."""
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

def extract_keywords(text: str) -> set:
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {w for w in words if w not in STOP_WORDS}

def calculate_duty_alignment(candidate_duties_text: str, occ_tasks: list) -> tuple:
    """Compare candidate's duty text against ABS tasks for an occupation."""
    if not occ_tasks or not candidate_duties_text:
        return 0.0, [], []
    
    cand_tokens = extract_keywords(candidate_duties_text)
    if not cand_tokens:
        return 0.0, [], []
    
    matched_tasks = []
    task_scores = []
    
    for task in occ_tasks:
        task_tokens = extract_keywords(task)
        if not task_tokens:
            continue
        overlap = cand_tokens.intersection(task_tokens)
        ratio = len(overlap) / max(1, len(task_tokens))
        if len(overlap) >= 2 or ratio >= 0.25:
            matched_tasks.append(task)
            task_scores.append(min(1.0, ratio * 2.0))
        elif len(overlap) == 1 and len(task_tokens) <= 6:
            matched_tasks.append(task)
            task_scores.append(0.5)
            
    match_pct = (len(matched_tasks) / len(occ_tasks)) * 100.0 if occ_tasks else 0.0
    return round(match_pct, 1), matched_tasks, list(cand_tokens)

async def test_matcher():
    # Test with Chef Duties:
    chef_duties = "Lead the cold kitchen section, preparing salads, appetizers and cold platters. Supervised 3 commis chefs and maintained HACCP food-safety standards. Assisted in food preparation across hot and cold kitchen sections. Planning menus, food preparation."
    print("=== TESTING CHEF DUTIES ===")
    chef_occ = await db['occupation_master'].find_one({'code': '351311', 'country_code': 'AU'})
    if chef_occ:
        tasks = chef_occ.get('tasks') or chef_occ.get('typical_tasks') or []
        pct, matches, _ = calculate_duty_alignment(chef_duties, tasks)
        print(f"Chef (351311) Duty Match: {pct}% | Matched {len(matches)}/{len(tasks)} tasks")
        for m in matches[:3]:
            print(f"  - Matched: {m}")
            
    cook_occ = await db['occupation_master'].find_one({'code': '351411', 'country_code': 'AU'})
    if cook_occ:
        tasks = cook_occ.get('tasks') or cook_occ.get('typical_tasks') or []
        pct, matches, _ = calculate_duty_alignment(chef_duties, tasks)
        print(f"Cook (351411) Duty Match: {pct}% | Matched {len(matches)}/{len(tasks)} tasks")

    # Test with Software Engineer Duties:
    swe_duties = "Lead a team of 6 engineers building microservices in Python and Java. Designed REST APIs, CI/CD pipelines and AWS cloud deployments. Managerial responsibilities including sprint planning and code reviews. Developed full-stack features for banking clients using Java and Angular. Optimised SQL queries and improved application performance by 30%."
    print("\n=== TESTING SOFTWARE ENGINEER DUTIES ===")
    for code in ['261313', '261312', '261311', '225113']:
        occ = await db['occupation_master'].find_one({'code': code, 'country_code': 'AU'})
        if occ:
            tasks = occ.get('tasks') or occ.get('typical_tasks') or []
            pct, matches, _ = calculate_duty_alignment(swe_duties, tasks)
            print(f"{occ.get('title')} ({code}) Duty Match: {pct}% | Matched {len(matches)}/{len(tasks)} tasks")

asyncio.run(test_matcher())
