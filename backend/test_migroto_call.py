#!/usr/bin/env python3
"""Test script for Migroto API integration in LEAMSS Portal.
Strictly reads the API key from environment variable PARSE_API_KEY.
"""
import os
import sys
import json
import httpx
from dotenv import load_dotenv

# Load environment from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

PARSE_API_KEY = os.environ.get("PARSE_API_KEY")
MIGROTO_SCRAPER_ID = os.environ.get("MIGROTO_SCRAPER_ID", "426cd41f-9657-408c-9258-44fb7184c999")
BASE_URL = os.environ.get("PARSE_BASE_URL", "https://api.parse.bot")

if not PARSE_API_KEY:
    print("[ERROR] PARSE_API_KEY environment variable is not set!")
    sys.exit(1)

def run_test():
    print(f"[INFO] Initializing call to migroto.com API via Parse...")
    print(f"[INFO] Scraper ID: {MIGROTO_SCRAPER_ID}")
    print(f"[INFO] Key source: Environment variable PARSE_API_KEY ({PARSE_API_KEY[:6]}...{PARSE_API_KEY[-4:]})")

    headers = {
        "X-API-Key": PARSE_API_KEY,
        "Content-Type": "application/json"
    }

    # 1. search_occupations endpoint test
    search_url = f"{BASE_URL}/scraper/{MIGROTO_SCRAPER_ID}/search_occupations"
    print(f"\n--> Calling POST {search_url} with query='Software Engineer'...")
    with httpx.Client(timeout=30.0) as client:
        res = client.post(search_url, headers=headers, json={"query": "Software Engineer"})
        print(f"<-- Status Code: {res.status_code}")
        if res.status_code != 200:
            print(f"[ERROR] Response body: {res.text}")
            sys.exit(1)

        result = res.json()
        print("[SUCCESS] Real call succeeded! Parsed response:")
        print(json.dumps(result, indent=2))

        data = result.get("data", {})
        occupations = data.get("occupations", [])
        total = data.get("total", len(occupations))
        print(f"\n[SUMMARY] Found {total} matching Australian skilled migration occupations:")
        for occ in occupations:
            print(f"  * Code: {occ.get('code')} | Title: {occ.get('title')} | Version: {occ.get('version')} | ID: {occ.get('id')}")

    # 2. get_occupation_filters endpoint test
    filters_url = f"{BASE_URL}/scraper/{MIGROTO_SCRAPER_ID}/get_occupation_filters"
    print(f"\n--> Calling POST {filters_url}...")
    with httpx.Client(timeout=30.0) as client:
        res = client.post(filters_url, headers=headers, json={})
        print(f"<-- Status Code: {res.status_code}")
        if res.status_code == 200:
            fdata = res.json().get("data", {})
            states = [s.get("code") for s in fdata.get("states", [])]
            subclasses = [s.get("subclass_number") for s in fdata.get("subclasses", [])]
            backlog_dates = [d.get("label") for d in fdata.get("eoi_backlog_dates", [])[:5]]
            print("[SUCCESS] Filters retrieved successfully:")
            print(f"  * States ({len(states)}): {', '.join(states)}")
            print(f"  * Visa Subclasses: {', '.join(subclasses)}")
            print(f"  * Recent EOI Backlog Snapshot Dates: {', '.join(backlog_dates)}")

if __name__ == "__main__":
    run_test()
