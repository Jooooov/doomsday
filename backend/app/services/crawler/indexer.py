"""
Indexer — translates CrawledPage objects into SourceContent ORM rows
and upserts them into PostgreSQL.

Strategy
--------
- On first crawl: INSERT a new ``source_content`` row.
- On re-crawl: UPDATE the existing row ONLY if ``content_hash`` has changed
  (avoids redundant writes for unchanged pages).
- Status transitions follow the CrawlStatus enum in schema.py.

Topic inference
---------------
Topics are inferred from the URL section_path using a keyword-to-tag mapping
defined in ``SECTION_TOPIC_MAP``.  This is intentionally simple for MVP —
LLM-based topic extraction can replace/augment this in Phase 2.

Region inference
----------------
Applicable regions are inferred from the source_key:
- ``red_cross`` → ["US"]
- ``protecao_civil_pt`` → ["PT"]
- Others → ["*"] (global)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_content import ContentSource, CrawlStatus as DBCrawlStatus
from .schema import CrawledPage, CrawlStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic inference from URL patterns
# ---------------------------------------------------------------------------

SECTION_TOPIC_MAP: dict[str, list[str]] = {
    # Red Cross URL patterns
    "nuclear": ["nuclear", "radiation", "shelter-in-place"],
    "nuclear-explosion": ["nuclear", "radiation", "blast", "shelter-in-place"],
    "chemical": ["chemical", "hazmat", "shelter-in-place"],
    "biological": ["biological", "pandemic", "contamination"],
    "earthquake": ["earthquake", "natural-disaster", "shelter"],
    "tornado": ["tornado", "natural-disaster", "shelter"],
    "hurricane": ["hurricane", "natural-disaster", "evacuation"],
    "wildfire": ["wildfire", "natural-disaster", "evacuation"],
    "winter-storm": ["winter-storm", "natural-disaster", "shelter"],
    "flood": ["flood", "natural-disaster", "evacuation"],
    "home-family": ["home-preparedness", "family", "checklist"],
    "prepare": ["preparedness", "emergency-kit", "planning"],
    "get-help": ["emergency-assistance", "disaster-relief"],
    "disaster-relief": ["disaster-relief", "emergency-assistance"],
    "food": ["food", "water", "supplies", "checklist"],
    "water": ["water", "hydration", "supplies", "checklist"],
    "first-aid": ["first-aid", "medical", "trauma"],
    "survival-kit": ["emergency-kit", "supplies", "checklist"],
    "shelter": ["shelter", "housing", "evacuation"],
    "evacuation": ["evacuation", "routes", "planning"],
    "communication": ["communication", "family-plan", "emergency-contacts"],
    "power-outage": ["power-outage", "utilities", "generator"],
    "fire": ["fire", "natural-disaster", "evacuation"],
    "pandemic": ["pandemic", "biological", "health"],
    "terrorism": ["terrorism", "security", "shelter-in-place"],
    # FEMA / generic patterns
    "ready": ["preparedness", "planning"],
    "alerts": ["alerts", "warning-systems"],
    "anepc": ["civil-protection", "national"],
    "protecao-civil": ["civil-protection", "national", "PT"],
}

# Source → default applicable regions mapping
SOURCE_REGIONS: dict[str, list[str]] = {
    ContentSource.RED_CROSS.value: ["US"],
    ContentSource.FEMA.value: ["US"],
    ContentSource.CDC.value: ["US"],
    ContentSource.WHO.value: ["*"],
    ContentSource.NATO.value: ["*"],
    ContentSource.PROTECAO_CIVIL_PT.value: ["PT"],
    ContentSource.CUSTOM.value: ["*"],
}


def _infer_topics(section_path: Optional[str]) -> list[str]:
    """
    Return a list of topic tags inferred from the URL section path.

    Iterates through known keyword patterns and collects matching tags.
    A single URL can match multiple patterns (e.g. /prepare/food matches
    both 'prepare' and 'food' patterns).
    """
    if not section_path:
        return []

    path_lower = section_path.lower()
    tags: list[str] = []
    seen: set[str] = set()

    for keyword, topic_tags in SECTION_TOPIC_MAP.items():
        if keyword in path_lower:
            for tag in topic_tags:
                if tag not in seen:
                    tags.append(tag)
                    seen.add(tag)

    # Fallback: if no tags matched, add "preparedness" as generic tag
    if not tags:
        tags = ["preparedness", "emergency"]

    return tags


def _infer_regions(source_key: str) -> list[str]:
    """Return applicable region codes for a given source key."""
    return SOURCE_REGIONS.get(source_key, ["*"])


def _section_path_from_url(url: str) -> str:
    """Extract the URL path component (used as section_path)."""
    try:
        return urlparse(url).path or "/"
    except Exception:
        return "/"


# ---------------------------------------------------------------------------
# DB upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_page(page: CrawledPage, session: AsyncSession, source_key: str) -> str:
    """
    Upsert a single CrawledPage into source_content.

    Returns one of: "inserted", "updated", "skipped", "failed".
    """
    # Import here to avoid circular deps
    from app.models.source_content import SourceContent

    section_path = _section_path_from_url(page.url)
    topics = _infer_topics(section_path)
    regions = _infer_regions(source_key)

    # Determine DB status from pipeline status
    if page.status == CrawlStatus.INDEXED:
        db_status = DBCrawlStatus.INDEXED.value
    elif page.status == CrawlStatus.FAILED:
        db_status = DBCrawlStatus.FAILED.value
    elif page.status == CrawlStatus.SKIPPED:
        db_status = DBCrawlStatus.SKIPPED.value
    else:
        db_status = DBCrawlStatus.PARSED.value

    now = datetime.now(timezone.utc)

    try:
        # Check if URL already exists
        result = await session.execute(
            select(SourceContent).where(SourceContent.url == page.url)
        )
        existing: Optional[SourceContent] = result.scalar_one_or_none()

        if existing is None:
            # INSERT new row
            row = SourceContent(
                url=page.url,
                source=source_key,
                section_path=section_path,
                title=page.title,
                summary=(page.content_text or "")[:1000] if page.content_text else None,
                body_text=page.content_text,
                topics=topics,
                applicable_regions=regions,
                language=page.language,
                word_count=page.word_count,
                status=db_status,
                error_message=page.error,
                http_status_code=page.http_status,
                crawled_at=page.crawled_at or now,
                content_hash=page.content_hash,
                is_active=True,
            )
            session.add(row)
            await session.flush()
            logger.info("INSERT source_content: %s (%d words)", page.url[:80], page.word_count)
            return "inserted"

        # Row exists — check if content changed
        if (
            existing.content_hash is not None
            and existing.content_hash == page.content_hash
            and page.status == CrawlStatus.INDEXED
        ):
            # Content unchanged → skip update (only bump crawled_at)
            existing.crawled_at = now
            existing.http_status_code = page.http_status
            await session.flush()
            logger.debug("UNCHANGED %s (hash match) — skipping content update", page.url[:80])
            return "skipped"

        # Content changed → update all fields
        existing.title = page.title or existing.title
        existing.summary = (page.content_text or "")[:1000] if page.content_text else existing.summary
        existing.body_text = page.content_text or existing.body_text
        existing.topics = topics
        existing.applicable_regions = regions
        existing.language = page.language
        existing.word_count = page.word_count
        existing.status = db_status
        existing.error_message = page.error
        existing.http_status_code = page.http_status
        existing.crawled_at = page.crawled_at or now
        existing.content_hash = page.content_hash
        await session.flush()
        logger.info("UPDATE source_content: %s (%d words)", page.url[:80], page.word_count)
        return "updated"

    except Exception as exc:
        logger.error("DB error upserting %s: %s", page.url[:80], exc, exc_info=True)
        await session.rollback()
        return "failed"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def index_pages(
    pages: List[CrawledPage],
    *,
    session: AsyncSession,
    source_key: str,
) -> dict:
    """
    Upsert a list of CrawledPage objects into source_content.

    Parameters
    ----------
    pages:
        Pages returned by the crawl pipeline.
    session:
        Active SQLAlchemy AsyncSession (caller manages commit/rollback).
    source_key:
        Source identifier string (e.g. ``"red_cross"``).

    Returns
    -------
    dict
        Summary counts: {"inserted": N, "updated": N, "skipped": N, "failed": N}
    """
    counts: dict[str, int] = {
        "inserted": 0, "updated": 0, "skipped": 0, "failed": 0
    }

    for page in pages:
        outcome = await _upsert_page(page, session, source_key)
        counts[outcome] = counts.get(outcome, 0) + 1

    try:
        await session.commit()
        logger.info(
            "Indexed %d pages for source=%r: %s",
            len(pages), source_key, counts,
        )
    except Exception as exc:
        logger.error("Commit failed for source=%r: %s", source_key, exc, exc_info=True)
        await session.rollback()
        counts["failed"] += len(pages)
        counts["inserted"] = 0
        counts["updated"] = 0

    return counts
