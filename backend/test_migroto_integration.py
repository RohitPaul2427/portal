#!/usr/bin/env python3
"""End-to-end integration test for Migroto Skilled Migration service,

router, and scraper in LEAMSS Portal.
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)
load_dotenv(os.path.join(base_dir, ".env"))

async def test_integration():
    print("=" * 60)
    print("LEAMSS - MIGROTO INTEGRATION VERIFICATION")
    print("=" * 60)

    # 1. Environment check
    api_key = os.environ.get("PARSE_API_KEY")
    scraper_id = os.environ.get("MIGROTO_SCRAPER_ID")
    print(f"\n1. Environment check:")
    print(f"   PARSE_API_KEY: {'configured (' + api_key[:6] + '...' + api_key[-4:] + ')' if api_key else 'MISSING'}")
    print(f"   MIGROTO_SCRAPER_ID: {scraper_id}")
    assert api_key, "PARSE_API_KEY must be set in .env"

    # 2. Service check
    print(f"\n2. MigrotoService testing:")
    from services.migroto_service import migroto_service

    # Test Search
    print("   --> Calling search_occupations('261313')...")
    search_res = await migroto_service.search_occupations("261313")
    print(f"   Status: {search_res.get('status')} | Total: {search_res.get('total')}")
    assert search_res.get("status") == "success"
    assert search_res.get("total", 0) >= 1
    first_occ = search_res["occupations"][0]
    print(f"   First match: {first_occ.get('code')} - {first_occ.get('title')} ({first_occ.get('version')})")

    # Test Filters
    print("   --> Calling get_occupation_filters()...")
    filters_res = await migroto_service.get_occupation_filters()
    assert filters_res.get("status") == "success"
    filter_data = filters_res.get("data", {})
    states = [s.get("code") for s in filter_data.get("states", [])]
    subclasses = [s.get("subclass_number") for s in filter_data.get("subclasses", [])]
    recent_dates = [d.get("label") for d in filter_data.get("eoi_backlog_dates", [])[:3]]
    print(f"   States ({len(states)}): {', '.join(states)}")
    print(f"   Subclasses: {', '.join(subclasses)}")
    print(f"   Recent EOI dates: {', '.join(recent_dates)}")

    # Test ANZSCO Verification
    print("   --> Calling verify_anzsco_code('261313', 'Software Engineer')...")
    verify_res = await migroto_service.verify_anzsco_code("261313", "Software Engineer")
    print(f"   Verified: {verify_res.get('verified')} | Status: {verify_res.get('verification_status')}")
    print(f"   Official title: {verify_res.get('official_title')} | Version: {verify_res.get('classification_version')}")
    assert verify_res.get("verified") is True

    # Test Occupation Details & Synthesis Fallback
    print("   --> Calling get_occupation_details('261313')...")
    details_res = await migroto_service.get_occupation_details("261313")
    print(f"   Details status: {details_res.get('status')} (synthesized fallback resilient: {details_res.get('synthesized', False)})")
    assert details_res.get("status") == "success"
    insight_occ = details_res.get("data", {}).get("occupation", {})
    print(f"   Occupation insight: {insight_occ.get('title')} | Tier: {insight_occ.get('tier')}")
    print(f"   Assessing authorities: {[a.get('code') for a in insight_occ.get('assessing_authorities', [])]}")

    # Test Atlas Coverage Audit
    print("   --> Calling audit_atlas_migroto_coverage()...")
    audit_res = await migroto_service.audit_atlas_migroto_coverage()
    print(f"   AU Occupations in Portal: {audit_res.get('total_au_occupations')}")
    print(f"   Migroto Synced: {audit_res.get('migroto_synced_count')} | Verified: {audit_res.get('verified_count')}")
    print(f"   Coverage %: {audit_res.get('coverage_percentage')}%")

    # 3. Scraper Hub Registration check
    print(f"\n3. Scraper Hub check:")
    from routers.scrapers import _SCRAPERS
    assert "migroto" in _SCRAPERS, "migroto scraper must be in _SCRAPERS"
    migroto_scraper = _SCRAPERS["migroto"]
    print(f"   Scraper registered: {migroto_scraper.display_name}")
    print(f"   Countries: {migroto_scraper.countries} | URL: {migroto_scraper.source_url}")

    # 4. Server routes check
    print(f"\n4. FastAPI routes check:")
    from server import app
    spec = app.openapi()
    migroto_endpoints = [p for p in spec["paths"] if "migroto" in p]
    print(f"   Total migroto endpoints mounted: {len(migroto_endpoints)}")
    for ep in sorted(migroto_endpoints):
        methods = list(spec["paths"][ep].keys())
        print(f"     {','.join(methods).upper()} {ep}")
    assert len(migroto_endpoints) >= 7, "At least 7 migroto endpoints should be mounted"

    print("\n" + "=" * 60)
    print("ALL INTEGRATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_integration())
