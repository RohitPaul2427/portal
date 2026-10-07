"""Migroto Australian Skilled Migration Scraper.

Integrates Migroto API into LEAMSS Scraper Hub to sync ANZSCO occupation codes,
visa invitation thresholds, SkillSelect tiers, and state nomination status.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseScraper, ScrapeRunResult, db
from services.migroto_service import migroto_service

logger = logging.getLogger("leamss.scrapers.migroto")


class MigrotoScraper(BaseScraper):
    scraper_id = "migroto"
    display_name = "Migroto Skilled Migration Intelligence"
    description = "ANZSCO occupation registry, visa invitation thresholds, EOI backlogs & state nomination programs"
    countries = ["AU"]
    source_url = "https://migroto.com"
    is_global = False

    async def scrape(self, codes: Optional[List[str]] = None) -> ScrapeRunResult:
        result = ScrapeRunResult(
            scraper_id=self.scraper_id, started_at="", finished_at="",
            duration_ms=0, status="success",
        )

        # First refresh filters
        filters_res = await migroto_service.get_occupation_filters(use_cache=False)
        filter_data = filters_res.get("data", {})
        recent_dates = [d.get("label") for d in filter_data.get("eoi_backlog_dates", [])[:3]]

        # Store in KB
        await self._upsert_kb({
            "source_id": "migroto",
            "title": "Migroto Skilled Migration Intelligence",
            "url": self.source_url,
            "fees": [],
            "processing_weeks": 0,
            "rules_summary": (
                f"Live Australian skilled migration intelligence from migroto.com. "
                f"Supports subclasses 189, 190, 491 across {len(filter_data.get('states', []))} Australian states. "
                f"Latest EOI backlog snapshot dates: {', '.join(recent_dates)}."
            ),
            "last_scraped_at": datetime.now(timezone.utc).isoformat(),
        })

        # If codes are provided, sync them
        target_codes = codes
        if not target_codes:
            # Pick a sample of AU draft/verified occupations
            occ_cursor = db()["occupation_master"].find({"country_code": "AU"}, {"code": 1}).limit(10)
            target_codes = [doc["code"] async for doc in occ_cursor if doc.get("code")]

        updated = 0
        skipped = 0
        errors = []

        for code in target_codes:
            result.records_attempted += 1
            try:
                enrich_res = await migroto_service.enrich_occupation_master(code)
                if enrich_res.get("status") == "success":
                    updated += 1
                else:
                    skipped += 1
                    errors.append({"code": code, "error": enrich_res.get("error")})
            except Exception as e:
                skipped += 1
                errors.append({"code": code, "error": str(e)})

        result.records_updated = updated
        result.records_skipped = skipped
        result.errors = errors
        result.status = "success" if updated > 0 or not target_codes else "partial"
        result.notes = f"Synced {updated} occupations with Migroto registry. Latest backlog: {recent_dates[0] if recent_dates else 'N/A'}."

        return result
