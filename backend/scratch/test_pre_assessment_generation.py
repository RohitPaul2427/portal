"""Test Pre-Assessment Report generation for various assessing bodies (ACS, VETASSESS, TRA)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db
from routers.pre_assessment_report_v2 import ReportRequest, ClientProfile, _build_context
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path


async def test_generation():
    tmpl_dir = Path(__file__).resolve().parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=select_autoescape(["html", "xml"]))
    tmpl = env.get_template("pre_assessment_report_v2.html")
    dummy_user = {"id": "test-admin", "name": "Rohit Alluri (LEAMSS Senior Consultant)", "role": "admin"}

    cases = [
        {
            "name": "Rajesh Sharma (B.Com + 6 yrs IT -> ACS RPL)",
            "client": ClientProfile(
                name="Rajesh Sharma",
                email="rajesh.sharma@example.com",
                phone="+91 9876543210",
                age=31,
                education="Bachelor of Commerce",
                field_of_study="Commerce / Accounting",
                work_exp_years=6,
                english_score="IELTS 7.5",
            ),
            "country_code": "AU",
            "occupation_code": "261313",
        },
        {
            "name": "Priya Patel (B.Tech CSE + 8 yrs IT -> ACS Major)",
            "client": ClientProfile(
                name="Priya Patel",
                email="priya.patel@example.com",
                phone="+91 9876543211",
                age=29,
                education="Bachelor of Technology",
                field_of_study="Computer Science & Engineering",
                work_exp_years=8,
                english_score="PTE 79",
            ),
            "country_code": "AU",
            "occupation_code": "261312",
        },
        {
            "name": "Amit Kumar (BBM + 5 yrs exp -> VETASSESS Group B)",
            "client": ClientProfile(
                name="Amit Kumar",
                email="amit.kumar@example.com",
                phone="+91 9876543212",
                age=33,
                education="Bachelor of Business Management",
                field_of_study="General Business / Marketing",
                work_exp_years=5,
                english_score="IELTS 7.0",
            ),
            "country_code": "AU",
            "occupation_code": "224711",
        },
        {
            "name": "Suresh Verma (Diploma + 5 yrs trade -> TRA Trade)",
            "client": ClientProfile(
                name="Suresh Verma",
                email="suresh.verma@example.com",
                phone="+91 9876543213",
                age=28,
                education="Diploma in Mechanical Engineering",
                field_of_study="Automotive / Mechanical",
                work_exp_years=5,
                english_score="IELTS 6.5",
            ),
            "country_code": "AU",
            "occupation_code": "321211",
        },
    ]

    for c in cases:
        print(f"\n=======================================================")
        print(f"Testing: {c['name']}")
        req = ReportRequest(
            client=c["client"],
            country_code=c["country_code"],
            occupation_code=c["occupation_code"],
        )
        ctx = await _build_context(req, dummy_user)
        ctx.update({
            "ref": "TESTREF1",
            "agent_name": dummy_user["name"],
            "generated_at": "16 Sep 2026 · 14:30 UTC",
            "generated_at_date": "16 Sep 2026",
        })
        
        sa = ctx.get("skills_assessment") or {}
        print(f"Assessing Authority: {sa.get('authority_code')} - {sa.get('authority_name')}")
        print(f"Qualification Bucket: {sa.get('qualification_bucket')}")
        print(f"Assessment Outcome: {sa.get('assessment_outcome')}")
        print(f"Deducted Years: {sa.get('deducted_years')}")
        print(f"Points-Claimable Years: {sa.get('points_claimable_years')} ({sa.get('points_claimable_points')} pts)")
        print(f"RPL Required: {sa.get('rpl_required')}")
        print(f"Summary: {sa.get('deemed_skilled_summary')}")
        
        html_out = tmpl.render(**ctx)
        assert "Skills Assessment &amp; Experience Deduction Analysis" in html_out or "Skills Assessment & Experience Deduction Analysis" in html_out
        assert sa.get("authority_code") in html_out
        print("[PASS] HTML rendered successfully with Section 3 Skills Assessment details!")

    print("\nALL PRE-ASSESSMENT GENERATION TESTS PASSED 100%!")


if __name__ == "__main__":
    asyncio.run(test_generation())
