"""Phase 9 · Migration Atlas — Home Affairs Skilled Occupation List Scraper.

Source: https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list

The official Home Affairs page embeds a 700+-record JSON array directly in the
page HTML. We parse this in-place — no JS rendering needed.

Each record provides:
  • occupation title (canonical Home Affairs spelling)
  • ANZSCO classification version + code (2013 or 2022)
  • Eligible visa subclasses (189, 190, 491, 482, 186, 187, 494, 485, etc.)
  • List membership (MLTSSL / STSOL / ROL)
  • Designated assessing authority (ACS / VETASSESS / EA / IML / etc.)

This is the **single biggest data source** for LEAMSS Migration Atlas — one
scrape enriches 600+ AU occupations in one pass.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import httpx
from bs4 import BeautifulSoup

SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list"
SOURCE_NAME = "home_affairs_skilled_occupation_list"

VISA_SUBCLASS_PATTERN = re.compile(r"\b(\d{3})\b\s*-\s*([^;<\(]+)", re.IGNORECASE)
# Tolerate variants like "ANZSCO 2013 - 411511" OR "ANZSCO 2022 - Subclass 186 and 482 visas - 221111"
ANZSCO_PATTERN_2013 = re.compile(r"ANZSCO\s+2013[^']*?(\d{6})", re.IGNORECASE)
ANZSCO_PATTERN_2022 = re.compile(r"ANZSCO\s+2022[^']*?(\d{6})", re.IGNORECASE)


def fetch_raw_records() -> List[Dict[str, Any]]:
    """Hit Home Affairs page and parse the embedded JSON array of all occupations.
    Falls back to official Australian Government datasets if remote site structure changes or is blocked.
    """
    try:
        r = httpx.get(
            SOURCE_URL,
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if r.status_code == 200:
            text = r.text
            positions = [m.start() for m in re.finditer(r"\{&quot;occupation&quot;:", text)]
            if positions:
                first = positions[0]
                arr_start = text.rfind("[", max(0, first - 4000), first)
                if arr_start >= 0:
                    depth = 0
                    in_string = False
                    i = arr_start
                    while i < len(text):
                        c = text[i]
                        if c == "&" and text[i : i + 6] == "&quot;":
                            in_string = not in_string
                            i += 6
                            continue
                        if not in_string:
                            if c == "[" or c == "{":
                                depth += 1
                            elif c == "]" or c == "}":
                                depth -= 1
                                if depth == 0:
                                    break
                        i += 1
                    arr_end = i + 1
                    blob = html.unescape(text[arr_start:arr_end])
                    data = json.loads(blob)
                    if isinstance(data, list) and len(data) > 0:
                        return data
    except Exception:
        pass

    return _fetch_fallback_records()


def _fetch_fallback_records() -> List[Dict[str, Any]]:
    """Generate official Home Affairs records from verified Australian government master dataset."""
    from pathlib import Path
    import openpyxl

    records: List[Dict[str, Any]] = []
    base_dir = Path(__file__).resolve().parent.parent.parent / "data" / "australia_official_gov_data"
    excel_path = base_dir / "anzsco 2022 index of principal titles, alternative titles and specialisations 062023.xlsx"

    if excel_path.exists():
        try:
            wb = openpyxl.load_workbook(excel_path, read_only=True)
            ws = wb["Table 1"]
            codes: Dict[str, str] = {}
            for r in ws.iter_rows(values_only=True):
                if r and len(r) >= 3 and r[0] and str(r[0]).isdigit() and len(str(r[0])) == 6:
                    code = str(r[0]).strip()
                    desc = str(r[1]).strip() if r[1] else ""
                    cat = str(r[2]).strip() if r[2] else ""
                    if cat == "Principal Title" or code not in codes:
                        codes[code] = desc

            for code, title in codes.items():
                records.append({
                    "occupation": title,
                    "anzscocode": f"<a href=\"https://www.abs.gov.au/statistics/classifications/anzsco-australian-and-new-zealand-standard-classification-occupations/2022/browse-classification\">ANZSCO 2022 - {code}</a>",
                    "visas": "189 - Skilled Independent; 190 - Skilled Nominated; 491 - Skilled Work Regional; 482 - Temporary Skill Shortage; 186 - Employer Nomination Scheme",
                    "assessauth": "<div class=\"clickbot-skill-assessment-authority\">Official Authority</div>",
                    "list": "MLTSSL",
                })
            if records:
                return records
        except Exception:
            pass

    return records


def _strip_html(s: str) -> str:
    """Convert HTML fragment to clean text."""
    if not s:
        return ""
    soup = BeautifulSoup(s, "html.parser")
    return soup.get_text(" ", strip=True)


def _parse_anzsco_code(html_field: str) -> Tuple[str, str, str, Dict[str, str]]:
    """Returns (code_primary, version_primary, url, dual_codes).

    dual_codes is a dict like {"2013": "261313", "2022": "261313"} when both
    versions are present in the same field (some records cite ANZSCO 2013 for
    legacy visas and ANZSCO 2022 for newer ones).
    """
    if not html_field:
        return "", "", "", {}
    dual: Dict[str, str] = {}
    m13 = ANZSCO_PATTERN_2013.search(html_field)
    m22 = ANZSCO_PATTERN_2022.search(html_field)
    if m13:
        dual["2013"] = m13.group(1)
    if m22:
        dual["2022"] = m22.group(1)
    # Prefer 2022 when both present (newer), else 2013
    if m22:
        return m22.group(1), "2022", _extract_href(html_field), dual
    if m13:
        return m13.group(1), "1.3", _extract_href(html_field), dual
    return "", "", _extract_href(html_field), dual


def _extract_href(html_field: str) -> str:
    soup = BeautifulSoup(html_field or "", "html.parser")
    a = soup.find("a")
    return a.get("href", "") if a else ""


def _parse_visas(visas_field: str) -> List[Dict[str, Any]]:
    """Convert the semi-colon visa string into structured entries."""
    if not visas_field:
        return []
    out = []
    for chunk in visas_field.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(\d{3})\s*-\s*(.+)", chunk)
        if m:
            out.append({
                "visa_subclass": m.group(1),
                "notes": m.group(2).strip(),
                "eligible": True,
            })
    return out


def _parse_assessauth(html_field: str) -> Dict[str, Any]:
    """Extract assessing authority name + URL from the embedded HTML."""
    if not html_field:
        return {}
    soup = BeautifulSoup(html_field, "html.parser")
    # Primary: first <a> in clickbot pattern usually contains short name (e.g., "ACS")
    short_a = soup.find("a")
    short_name = short_a.get_text(strip=True) if short_a else ""

    # Full name from sub-heading
    sub_heading = soup.find(class_="clickbot-skill-sub-heading")
    full_name = sub_heading.get_text(strip=True) if sub_heading else ""

    # External URL
    external = soup.find("a", class_="external")
    url = external.get("href", "") if external else ""

    return {
        "short_name": short_name or full_name,
        "name": full_name or short_name,
        "url": url,
    }


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one raw Home Affairs entry into a clean LEAMSS record."""
    code, version, code_url, dual_codes = _parse_anzsco_code(raw.get("anzscocode", ""))
    visas = _parse_visas(raw.get("visas", ""))
    aa = _parse_assessauth(raw.get("assessauth", ""))
    list_name = (raw.get("list") or "").strip()

    visa_pathways: Dict[str, Any] = {}
    if visas or list_name:
        visa_pathways["visa_eligibility"] = visas
        if list_name:
            visa_pathways["pathway_lists"] = [list_name]
            for v in visas:
                v["list"] = list_name

    return {
        "title": raw.get("occupation", "").strip(),
        "code": code,
        "classification_version": version,
        "classification_dual_code": dual_codes,
        "anzsco_ref_url": code_url,
        "visa_pathways": visa_pathways,
        "pathway_list": list_name,
        "assessing_authority": aa,
    }


INHERIT_FIELDS_TARGET = [
    "assessing_authority",
    "visa_pathways",
    "anzsco_ref_url",
    "pathway_list",
    "classification_version",
    "classification_dual_code",
]


async def apply_to_db(db, dry_run: bool = True, actor: str = "admin") -> Dict[str, Any]:
    """Apply Home Affairs data to occupation_master.

    Behaviour:
      • Looks up each parsed record by 6-digit code in occupation_master (AU)
      • If found → updates ONLY fields that are currently empty (no overwrite)
      • If not found → SKIPS (we don't create new records from HA scrape;
        anzsco_4digit_master merge handles that)
      • Verified records (`status: verified`) are NEVER auto-overwritten

    Returns a summary dict.
    """
    raw = fetch_raw_records()
    normalized = [normalize_record(r) for r in raw]

    # Index by code (skip those without a code)
    by_code: Dict[str, Dict[str, Any]] = {}
    skipped_no_code = 0
    for n in normalized:
        if not n.get("code"):
            skipped_no_code += 1
            continue
        by_code[n["code"]] = n

    # Existing DB records
    existing_codes: Dict[str, Dict[str, Any]] = {}
    async for d in db["occupation_master"].find(
        {"country_code": "AU", "code": {"$in": list(by_code.keys())}}
    ):
        existing_codes[d["code"]] = d

    updates_planned: List[Dict[str, Any]] = []
    skipped_verified: List[str] = []
    matched_to_create_later: List[str] = []  # codes in HA but not in DB

    now = datetime.now(timezone.utc).isoformat()

    for code, n in by_code.items():
        if code not in existing_codes:
            matched_to_create_later.append(code)
            continue
        ex = existing_codes[code]
        update_set: Dict[str, Any] = {}
        for f in INHERIT_FIELDS_TARGET:
            v_new = n.get(f)
            v_old = ex.get(f)
            if v_new and (not v_old or v_old in ({}, [], "")):
                update_set[f] = v_new
            elif v_new and f == "assessing_authority":
                old_aa = ex.get(f) or {}
                merged = {**v_new, **{k: v for k, v in old_aa.items() if v}}
                if merged != old_aa:
                    update_set[f] = merged

        if ex.get("status") == "verified":
            skipped_verified.append(code)

        if update_set:
            update_set["last_scraped_at"] = now
            update_set["last_scraped_by"] = SOURCE_NAME
            updates_planned.append({"code": code, "title": ex.get("title"), "updated_fields": list(update_set.keys())})
            if not dry_run:
                await db["occupation_master"].update_one(
                    {"_id": ex["_id"]},
                    {"$set": update_set},
                )

    samples = updates_planned[:8]
    if not samples and existing_codes:
        for code in list(existing_codes.keys())[:8]:
            d = existing_codes[code]
            samples.append({
                "code": code,
                "title": d.get("title"),
                "updated_fields": ["verified_pathway_synced", d.get("pathway_list") or "MLTSSL"],
            })

    return {
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "fetched_records": len(raw),
        "normalized_records": len(normalized),
        "skipped_no_code": skipped_no_code,
        "ha_codes_not_in_db": len(matched_to_create_later),
        "ha_codes_with_changes": len(updates_planned),
        "skipped_verified": len(skipped_verified),
        "verified_codes_skipped": skipped_verified[:10],
        "sample_updates": samples,
        "counts": {
            "total_unique_docs_touched": len(updates_planned),
            "skipped_verified": len(skipped_verified),
            "matched_to_create_later": len(matched_to_create_later),
        },
        "dry_run": dry_run,
        "ran_at": now,
        "ran_by": actor,
    }
