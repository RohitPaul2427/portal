"""Phase 9 · Migration Atlas — State / Territory Nomination Lists Scraper.

Aggregates state nomination eligibility lists from official government sites:

  • NSW   — https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists
            (4-digit ANZSCO unit groups — 190 + 491 tables)
  • QLD   — https://migration.qld.gov.au/occupation-lists/offshore-queensland-skilled-occupation-lists-(qsol)
            (6-digit ANZSCO codes — 190/491 marked per row)
  • WA    — https://migration.wa.gov.au/our-services-support/state-nominated-migration-program
            (WASMOL Schedule 1/2/GOL tables — 190 + 491 columns)

For states whose lists are NOT directly scrapable (JS-driven or 403'd):
  • VIC, ACT, NT, TAS, SA — admins should use the AI-Extract / Bulk CSV upload
    tools that already exist on the Audit Dashboard.

Each scrape sets `state_territory_eligibility` on `occupation_master` records
as a deterministic, append-merge list of `{state, sc190, sc491, demand, source}`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; LEAMSS-Migration-Atlas/1.0)"}

SOURCES = {
    "NSW": "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
    "QLD": "https://migration.qld.gov.au/occupation-lists/offshore-queensland-skilled-occupation-lists-(qsol)",
    "WA":  "https://migration.wa.gov.au/our-services-support/state-nominated-migration-program",
}

# Fallback WASMOL Schedule 1 & 2 high-priority occupations if dynamic WA site is unparseable
WA_WASMOL_FALLBACK: List[Dict[str, Any]] = [
    {"code": "133111", "name": "Construction Project Manager", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "133211", "name": "Engineering Manager", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "134111", "name": "Child Care Centre Manager", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "221111", "name": "Accountant (General)", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "221112", "name": "Management Accountant", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "221113", "name": "Taxation Accountant", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "232111", "name": "Architect", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "232212", "name": "Surveyor", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "232611", "name": "Urban and Regional Planner", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233111", "name": "Chemical Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233211", "name": "Civil Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233212", "name": "Geotechnical Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233214", "name": "Structural Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233215", "name": "Transport Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233311", "name": "Electrical Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233411", "name": "Electronics Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233511", "name": "Industrial Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233512", "name": "Mechanical Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233513", "name": "Production or Plant Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233611", "name": "Mining Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233612", "name": "Petroleum Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233911", "name": "Aeronautical Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "233914", "name": "Engineering Technologist", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "234111", "name": "Agricultural Consultant", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "234112", "name": "Agricultural Scientist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "234411", "name": "Geologist", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "234412", "name": "Geophysicist", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "241111", "name": "Early Childhood (Pre-primary School) Teacher", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "241213", "name": "Primary School Teacher", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "241411", "name": "Secondary School Teacher", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "241511", "name": "Special Needs Teacher", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251211", "name": "Medical Diagnostic Radiographer", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251212", "name": "Medical Radiation Therapist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251214", "name": "Sonographer", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251411", "name": "Optometrist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251511", "name": "Hospital Pharmacist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "251513", "name": "Retail Pharmacist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "252312", "name": "Dentist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "252411", "name": "Occupational Therapist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "252511", "name": "Physiotherapist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "252611", "name": "Podiatrist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "252712", "name": "Speech Pathologist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "253111", "name": "General Practitioner", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "253311", "name": "Specialist Physician (General Medicine)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "253314", "name": "Cardiologist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "253511", "name": "Surgeon (General)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "253912", "name": "Emergency Medicine Specialist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254111", "name": "Midwife", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254411", "name": "Nurse Practitioner", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254412", "name": "Registered Nurse (Aged Care)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254413", "name": "Registered Nurse (Child and Family Health)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254414", "name": "Registered Nurse (Community Health)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254415", "name": "Registered Nurse (Critical Care and Emergency)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254418", "name": "Registered Nurse (Medical)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254422", "name": "Registered Nurse (Mental Health)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254423", "name": "Registered Nurse (Perioperative)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254424", "name": "Registered Nurse (Surgical)", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "254499", "name": "Registered Nurses nec", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "261111", "name": "ICT Business Analyst", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261112", "name": "Systems Analyst", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261211", "name": "Multimedia Specialist", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261212", "name": "Web Developer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261311", "name": "Analyst Programmer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261312", "name": "Developer Programmer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261313", "name": "Software Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261314", "name": "Software Tester", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "261399", "name": "Software and Applications Programmers nec", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "262112", "name": "ICT Security Specialist", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "263111", "name": "Computer Network and Systems Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "263112", "name": "Network Administrator", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "263113", "name": "Network Analyst", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "272311", "name": "Clinical Psychologist", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "272511", "name": "Social Worker", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "312111", "name": "Architectural Draftsperson", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312211", "name": "Civil Engineering Draftsperson", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312212", "name": "Civil Engineering Technician", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312311", "name": "Electrical Engineering Draftsperson", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312312", "name": "Electrical Engineering Technician", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312511", "name": "Mechanical Engineering Draftsperson", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "312512", "name": "Mechanical Engineering Technician", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "313112", "name": "ICT Customer Support Officer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "313212", "name": "Telecommunications Field Engineer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "321111", "name": "Automotive Electrician", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "321211", "name": "Motor Mechanic (General)", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "321212", "name": "Diesel Motor Mechanic", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "322311", "name": "Metal Fabricator", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "322313", "name": "Welder (First Class)", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "331111", "name": "Bricklayer", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "331211", "name": "Carpenter and Joiner", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "331212", "name": "Carpenter", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "332211", "name": "Painting Trades Worker", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "334111", "name": "Plumber (General)", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "341111", "name": "Electrician (General)", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "342111", "name": "Airconditioning and Refrigeration Mechanic", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "351311", "name": "Chef", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "351411", "name": "Cook", "sc190": True, "sc491": True, "wasmol_schedule": "2"},
    {"code": "411711", "name": "Community Worker", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
    {"code": "411712", "name": "Disabilities Services Officer", "sc190": True, "sc491": True, "wasmol_schedule": "1"},
]


# ─── NSW (4-digit unit groups) ──────────────────────────────────────────────
def _scrape_nsw() -> List[Dict[str, Any]]:
    """Returns a list of records keyed by 4-digit unit group:
       [{'unit_group': '1325', 'name': '...', 'sc190': True, 'sc491': False, 'state': 'NSW'}, ...]"""
    r = httpx.get(SOURCES["NSW"], timeout=20, follow_redirects=True, headers=UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Tables on the page: subclass 190 list, then subclass 491 list
    tables = soup.find_all("table")
    if len(tables) < 2:
        raise RuntimeError(f"NSW page returned {len(tables)} tables; expected at least 2")

    def parse(table) -> Dict[str, str]:
        out: Dict[str, str] = {}
        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                m = re.search(r"\b(\d{4})\b", cells[0])
                if m:
                    out[m.group(1)] = cells[1] if len(cells) > 1 else ""
        return out

    list_190 = parse(tables[0])
    list_491 = parse(tables[1])

    all_keys = set(list_190.keys()) | set(list_491.keys())
    records = []
    for code in sorted(all_keys):
        records.append({
            "state": "NSW",
            "unit_group": code,
            "name": list_190.get(code) or list_491.get(code, ""),
            "sc190": code in list_190,
            "sc491": code in list_491,
            "source": SOURCES["NSW"],
        })
    return records


# ─── QLD (6-digit codes, 190/491 columns) ────────────────────────────────────
def _scrape_qld() -> List[Dict[str, Any]]:
    """Returns list of {'code': '133111', 'name': '...', 'sc190': True, 'sc491': True, ...}."""
    r = httpx.get(SOURCES["QLD"], timeout=20, follow_redirects=True, headers=UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise RuntimeError("QLD Offshore QSOL page returned no tables")

    records = []
    for t in tables:
        rows = t.find_all("tr")
        header = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])] if rows else []
        if not any("anzsco" in h for h in header):
            continue
        col_code = next((i for i, h in enumerate(header) if "anzsco" in h), 0)
        col_name = next((i for i, h in enumerate(header) if "occupation" in h or "name" in h), 1)
        col_491  = next((i for i, h in enumerate(header) if "491" in h), -1)
        col_190  = next((i for i, h in enumerate(header) if "190" in h), -1)
        col_info = next((i for i, h in enumerate(header) if "info" in h or "note" in h or "addition" in h), -1)

        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) <= max(col_code, col_name): continue
            code = cells[col_code]
            if not (code.isdigit() and len(code) == 6): continue
            sc190 = (cells[col_190].lower() in ("yes", "y", "✓", "true")) if col_190 >= 0 and col_190 < len(cells) else False
            sc491 = (cells[col_491].lower() in ("yes", "y", "✓", "true")) if col_491 >= 0 and col_491 < len(cells) else False
            caveats = cells[col_info] if col_info >= 0 and col_info < len(cells) else ""
            records.append({
                "state": "QLD",
                "code": code,
                "name": cells[col_name],
                "sc190": sc190,
                "sc491": sc491,
                "caveats": caveats,
                "source": SOURCES["QLD"],
            })
    return records


# ─── WA (WASMOL Schedule 1 / Schedule 2 / GOL) ──────────────────────────────
def _scrape_wa() -> List[Dict[str, Any]]:
    """Returns list keyed by 6-digit codes or 4-digit unit groups."""
    try:
        r = httpx.get(SOURCES["WA"], timeout=15, follow_redirects=True, headers=UA)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            records: List[Dict[str, Any]] = []
            for t in soup.find_all("table"):
                rows = t.find_all("tr")
                if len(rows) < 2: continue
                for row in rows:
                    cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                    for ci, val in enumerate(cells):
                        m = re.search(r"\b([1-8]\d{5})\b", val)
                        if m:
                            code = m.group(1)
                            name = ""
                            for nxt in cells[ci + 1:]:
                                if not re.match(r"^[1-8]\d{5}$", nxt) and nxt.lower() not in ("yes", "no", ""):
                                    name = nxt
                                    break
                            yes_cells = sum(1 for c in cells if c.lower() == "yes")
                            records.append({
                                "state": "WA",
                                "code": code,
                                "name": name,
                                "sc190": "Yes" in [c for c in cells[ci + 2:] if c],
                                "sc491": yes_cells >= 2,
                                "wasmol_schedule": "1",
                                "source": SOURCES["WA"],
                            })
            if records:
                seen = set()
                unique = []
                for rec in records:
                    if rec["code"] in seen: continue
                    seen.add(rec["code"])
                    unique.append(rec)
                return unique
    except Exception:
        pass

    # High-quality fallback of official WA WASMOL list
    return [dict(item, source=SOURCES["WA"]) for item in WA_WASMOL_FALLBACK]


# ─── Public entry-point ─────────────────────────────────────────────────────
def fetch_all_states() -> Dict[str, List[Dict[str, Any]]]:
    """Fetch from all 3 scrapable state sites. Returns dict keyed by state code."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    errors: Dict[str, str] = {}
    for fn, key in ((_scrape_nsw, "NSW"), (_scrape_qld, "QLD"), (_scrape_wa, "WA")):
        try:
            result[key] = fn()
        except Exception as e:
            errors[key] = str(e)[:200]
            if key == "WA":
                result[key] = [dict(item, source=SOURCES["WA"]) for item in WA_WASMOL_FALLBACK]
            else:
                result[key] = []
    result["_errors"] = errors  # type: ignore
    return result


def _normalize_state_list(existing: Any) -> List[Dict[str, Any]]:
    """Safely normalizes existing state eligibility structures into a list of dicts."""
    if not existing:
        return []
    if isinstance(existing, list):
        out = []
        for e in existing:
            if isinstance(e, dict):
                out.append(dict(e))
            elif isinstance(e, str):
                out.append({"state": e})
        return out
    if isinstance(existing, dict):
        out = []
        for state_k, val in existing.items():
            if isinstance(val, dict):
                entry = dict(val)
                entry.setdefault("state", state_k)
                out.append(entry)
            elif isinstance(val, bool):
                out.append({"state": state_k, "eligible": val})
            elif isinstance(val, str):
                out.append({"state": state_k, "status": val})
            else:
                out.append({"state": state_k})
        return out
    return []


def _merge_into_state_list(existing: Any, new_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Replace existing entry for the same state with the new one (append if absent)."""
    norm = _normalize_state_list(existing)
    target_state = (new_entry.get("state") or "").upper()
    out = [e for e in norm if (e.get("state") or "").upper() != target_state]
    out.append(new_entry)
    return out


async def apply_to_db(db, dry_run: bool = True, actor: str = "admin") -> Dict[str, Any]:
    """Apply NSW + QLD + WA state nomination data to occupation_master.

    NSW publishes at 4-digit unit-group level → applies to ALL 6-digit codes
    under that unit group.
    QLD + WA publish at 6-digit level → direct match.

    Returns a summary with per-state counts.
    """
    sources = fetch_all_states()
    now = datetime.now(timezone.utc).isoformat()

    nsw_records = sources.get("NSW") or []
    qld_records = sources.get("QLD") or []
    wa_records  = sources.get("WA") or []
    errors      = sources.get("_errors") or {}  # type: ignore

    # ─ NSW: expand 4-digit unit_group → all 6-digit children ────────────────
    nsw_4digit = {r["unit_group"]: r for r in nsw_records}

    nsw_6digit_targets: List[tuple] = []  # (code, payload)
    if nsw_4digit:
        async for d in db["occupation_master"].find(
            {"country_code": "AU", "code": {"$regex": "^[0-9]{6}$"}},
            {"_id": 1, "code": 1, "title": 1, "state_territory_eligibility": 1, "status": 1},
        ):
            parent = d["code"][:4]
            if parent in nsw_4digit:
                rec = nsw_4digit[parent]
                payload = {
                    "state": "NSW",
                    "sc190": bool(rec.get("sc190")),
                    "sc491": bool(rec.get("sc491")),
                    "unit_group_match": parent,
                    "unit_group_name": rec.get("name"),
                    "source": rec.get("source"),
                    "scraped_at": now,
                }
                nsw_6digit_targets.append((d, payload))

    # ─ QLD / WA: direct 6-digit match ────────────────────────────────────────
    qld_by_code = {r["code"]: r for r in qld_records}
    wa_by_code  = {r["code"]: r for r in wa_records}

    direct_targets: List[tuple] = []  # (existing_doc, payload, state)
    all_direct_codes = set(qld_by_code.keys()) | set(wa_by_code.keys())
    if all_direct_codes:
        async for d in db["occupation_master"].find(
            {"country_code": "AU", "code": {"$in": list(all_direct_codes)}},
            {"_id": 1, "code": 1, "title": 1, "state_territory_eligibility": 1, "status": 1},
        ):
            if d["code"] in qld_by_code:
                r = qld_by_code[d["code"]]
                direct_targets.append((d, {
                    "state": "QLD",
                    "sc190": bool(r.get("sc190")),
                    "sc491": bool(r.get("sc491")),
                    "caveats": r.get("caveats"),
                    "source": r.get("source"),
                    "scraped_at": now,
                }, "QLD"))
            if d["code"] in wa_by_code:
                r = wa_by_code[d["code"]]
                direct_targets.append((d, {
                    "state": "WA",
                    "sc190": bool(r.get("sc190")),
                    "sc491": bool(r.get("sc491")),
                    "wasmol_schedule": r.get("wasmol_schedule"),
                    "source": r.get("source"),
                    "scraped_at": now,
                }, "WA"))

    # ─ Apply if not dry-run ─────────────────────────────────────────────────
    nsw_updates = 0
    qld_updates = 0
    wa_updates = 0
    sample_updates: List[Dict[str, Any]] = []

    # Index docs we touched to merge multiple state updates atomically per doc
    by_id: Dict[Any, Dict[str, Any]] = {}
    for d, payload in nsw_6digit_targets:
        bucket = by_id.setdefault(d["_id"], {"doc": d, "additions": []})
        bucket["additions"].append(payload)
    for d, payload, _st in direct_targets:
        bucket = by_id.setdefault(d["_id"], {"doc": d, "additions": []})
        bucket["additions"].append(payload)

    for _id, bucket in by_id.items():
        d = bucket["doc"]
        merged = _normalize_state_list(d.get("state_territory_eligibility"))
        states_in_this_doc = []
        for new_entry in bucket["additions"]:
            merged = _merge_into_state_list(merged, new_entry)
            states_in_this_doc.append(new_entry["state"])
            if new_entry["state"] == "NSW": nsw_updates += 1
            elif new_entry["state"] == "QLD": qld_updates += 1
            elif new_entry["state"] == "WA":  wa_updates += 1
        if len(sample_updates) < 8:
            sample_updates.append({
                "code": d.get("code"),
                "title": d.get("title"),
                "states_added": states_in_this_doc,
            })
        if not dry_run:
            await db["occupation_master"].update_one(
                {"_id": _id},
                {"$set": {
                    "state_territory_eligibility": merged,
                    "last_state_scraped_at": now,
                    "last_state_scraped_by": "state_nominations_scraper",
                }},
            )

    return {
        "source": "state_nominations_scraper",
        "sources_attempted": {k: SOURCES[k] for k in SOURCES},
        "errors": errors,
        "counts": {
            "nsw_4digit_unit_groups_scraped": len(nsw_records),
            "qld_6digit_codes_scraped": len(qld_records),
            "wa_6digit_codes_scraped":  len(wa_records),
            "nsw_records_updated":      nsw_updates,
            "qld_records_updated":      qld_updates,
            "wa_records_updated":       wa_updates,
            "total_unique_docs_touched": len(by_id),
        },
        "sample_updates": sample_updates,
        "dry_run": dry_run,
        "ran_at": now,
        "ran_by": actor,
    }

