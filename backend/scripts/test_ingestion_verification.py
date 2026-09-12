import urllib.request
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

test_codes = ["211111", "421112", "261313", "254411", "334111", "233911", "134111"]
print("=== TESTING PUBLIC ATLAS API (PORT 8001) ===")
for c in test_codes:
    url = f"http://localhost:8001/api/public-atlas/AU/{c}"
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read().decode("utf-8"))
        occ = data.get("occupation") or data
        title = occ.get("title")
        jsa = occ.get("jsa_spl", {})
        st_r = jsa.get("state_ratings", {})
        auth = (occ.get("assessing_authority") or {}).get("code")
        abs_d = occ.get("abs_data") or {}
        jsa_d = occ.get("jsa_data") or {}
        salary = abs_d.get("median_ft_weekly_earnings_aud")
        growth = jsa_d.get("growth_pct_2025_to_2035")
        nat_lbl = jsa.get("national_label")
        print(f"✔ [{req.status}] {c} {title} | Nat: {nat_lbl} | States: {st_r} | Auth: {auth} | Sal: ${salary}/wk | 10yr Growth: {growth}%")
    except Exception as e:
        print(f"ERR {c}: {e}")

print("\n=== TESTING STATIC PUBLIC ATLAS HTML FILES ===")
frontend_public = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "atlas", "au")
for c in test_codes:
    fp = os.path.join(frontend_public, c, "index.html")
    if os.path.exists(fp):
        size = os.path.getsize(fp)
        with open(fp, "r", encoding="utf-8") as hf:
            html = hf.read()
            has_jsa = "State &amp; Territory Shortage Priority" in html or "Shortage" in html
            has_salary = "Median earnings" in html or "Salary" in html
            has_growth = "Employment outlook to 2035" in html
        print(f"✔ File exists: /atlas/au/{c}/index.html ({size:,} bytes) | JSA Section: {has_jsa} | Salary Card: {has_salary} | Growth Card: {has_growth}")
    else:
        print(f"❌ File missing: {fp}")
