"""Export sample pre-assessment report HTML previews to frontend/public for instant user browser review."""
import asyncio
import os
import sys
from pathlib import Path

# Setup sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db
from routers.pre_assessment_report_v2 import ReportRequest, ClientProfile, _build_context
from jinja2 import Environment, FileSystemLoader, select_autoescape

async def main():
    tmpl_dir = Path(__file__).resolve().parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(tmpl_dir)), autoescape=select_autoescape(["html", "xml"]))
    tmpl = env.get_template("pre_assessment_report_v2.html")
    dummy_user = {"id": "test-admin", "name": "Rohit Alluri (LEAMSS Senior Consultant)", "role": "admin"}
    
    pub_dir = Path(r"c:\Users\Rohit Alluri\Downloads\LEAMSS-main (1)\LEAMSS-main\frontend\public")
    
    cases = [
        {
            "filename": "preview-pa-acs-rpl.html",
            "title": "Rajesh Sharma — B.Com + 6 yrs IT (ACS RPL Pathway)",
            "client": ClientProfile(
                name="Rajesh Sharma",
                email="rajesh.sharma@example.com",
                phone="+91 98765 43210",
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
            "filename": "preview-pa-acs-btech.html",
            "title": "Priya Patel — B.Tech CSE + 8 yrs IT (ACS Major)",
            "client": ClientProfile(
                name="Priya Patel",
                email="priya.patel@example.com",
                phone="+91 98765 43211",
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
            "filename": "preview-pa-vetassess-group-b.html",
            "title": "Amit Kumar — BBM + 5 yrs exp (VETASSESS Group B)",
            "client": ClientProfile(
                name="Amit Kumar",
                email="amit.kumar@example.com",
                phone="+91 98765 43212",
                age=33,
                education="Bachelor of Business Management",
                field_of_study="General Management",
                work_exp_years=5,
                english_score="IELTS 7.0",
            ),
            "country_code": "AU",
            "occupation_code": "224711",
        },
        {
            "filename": "preview-pa-tra-trade.html",
            "title": "Suresh Verma — Diploma + 5 yrs trade (TRA / VETASSESS RTO)",
            "client": ClientProfile(
                name="Suresh Verma",
                email="suresh.verma@example.com",
                phone="+91 98765 43213",
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
        req = ReportRequest(
            client=c["client"],
            country_code=c["country_code"],
            occupation_code=c["occupation_code"],
        )
        ctx = await _build_context(req, dummy_user)
        ctx.update({
            "ref": "PREVIEW-" + c["occupation_code"],
            "agent_name": dummy_user["name"],
            "generated_at": "16 Sep 2026 · 16:50 UTC",
            "generated_at_date": "16 Sep 2026",
        })
        html_content = tmpl.render(**ctx)
        out_path = pub_dir / c["filename"]
        out_path.write_text(html_content, encoding="utf-8")
        print(f"Exported: {c['filename']} -> {out_path}")

    print("All sample report previews generated into frontend/public!")

if __name__ == "__main__":
    asyncio.run(main())
