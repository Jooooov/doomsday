"""
GDELT client — wraps the GDELT Project API v2 (DOC and GEO endpoints).

No API key is required.  Uses httpx.AsyncClient for all HTTP calls.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx

from app.schemas.news import NormalizedArticle
from app.services.news.base import BaseNewsSource

logger = logging.getLogger(__name__)

# GDELT seendate format
_GDELT_DATE_FMT = "%Y%m%dT%H%M%SZ"


class GDELTClient(BaseNewsSource):
    """
    Async client for the GDELT Project API v2.

    Hits two endpoints:
      - **DOC API** (``/doc/doc``) — full-text article index (artlist mode)
      - **GEO API** (``/geo/geo``) — geo-tagged event mentions

    Both calls are made on every ``fetch()`` invocation; results are
    deduplicated by URL before being returned.

    Parameters
    ----------
    base_url:
        Override the default GDELT v2 base URL (useful in tests).
    """

    def __init__(
        self,
        base_url: str = "https://api.gdeltproject.org/api/v2",
    ) -> None:
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # BaseNewsSource interface
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return "gdelt"

    async def fetch(
        self,
        query: str,
        country: Optional[str] = None,
        max_results: int = 250,
    ) -> List[NormalizedArticle]:
        """
        Fetch from both DOC and GEO APIs, deduplicate by URL, and return
        a combined list sorted by published_at descending.
        """
        logger.info(
            "GDELT fetch — query=%r country=%s max=%d", query, country, max_results
        )

        doc_articles, geo_articles = await _gather_two(
            self.fetch_doc(query, max_results=max_results),
            self.fetch_geo(query, max_results=max_results),
        )

        # Deduplicate by URL (DOC results take precedence)
        seen_urls: Dict[str, NormalizedArticle] = {}
        for article in doc_articles + geo_articles:
            if article.url not in seen_urls:
                seen_urls[article.url] = article

        # Apply country tag if provided
        if country:
            for article in seen_urls.values():
                if article.country is None:
                    article.country = country

        # Sort newest first, cap at max_results
        combined = sorted(
            seen_urls.values(), key=lambda a: a.published_at, reverse=True
        )
        combined = combined[:max_results]

        logger.info(
            "GDELT returned %d unique articles (doc=%d, geo=%d) for query=%r",
            len(combined),
            len(doc_articles),
            len(geo_articles),
            query,
        )
        return combined

    def normalize(self, raw: Any, country: Optional[str] = None) -> NormalizedArticle:  # type: ignore[override]
        """
        Map a single GDELT DOC artlist item to a NormalizedArticle.

        GDELT does not return article body text.
        """
        url: str = raw.get("url") or ""
        title: str = raw.get("title") or url  # fall back to URL if no title

        domain: str = raw.get("domain") or _domain_from_url(url) or "unknown"
        language: str = (raw.get("language") or "en").lower()
        source_country: Optional[str] = raw.get("sourcecountry") or country or None

        seendate: Optional[str] = raw.get("seendate")
        published_at = _parse_gdelt_date(seendate)

        return NormalizedArticle(
            headline=title,
            body=None,  # GDELT DOC API does not include article body
            source=domain,
            source_type="gdelt",
            url=url,
            country=source_country,
            published_at=published_at,
            language=language,
            raw_data=raw,
        )

    async def health_check(self) -> bool:
        """Probe GDELT DOC API with a minimal query."""
        try:
            await self.fetch_doc("news", max_results=1)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("GDELT health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Endpoint-specific fetchers
    # ------------------------------------------------------------------

    async def fetch_doc(
        self,
        query: str,
        max_results: int = 250,
    ) -> List[NormalizedArticle]:
        """
        Call the GDELT DOC API in artlist mode and return normalised articles.

        URL pattern:
            /doc/doc?query=<q>&mode=artlist&maxrecords=<n>&format=json
        """
        url = f"{self._base_url}/doc/doc"
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": min(max_results, 250),
            "format": "json",
        }

        data = await self._get_json(url, params)
        articles_raw: List[dict] = data.get("articles") or []

        articles: List[NormalizedArticle] = []
        for raw in articles_raw:
            try:
                articles.append(self.normalize(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("GDELT DOC normalize error — skipping: %s", exc)

        logger.debug("GDELT DOC returned %d articles", len(articles))
        return articles

    async def fetch_geo(
        self,
        query: str,
        max_results: int = 250,
    ) -> List[NormalizedArticle]:
        """
        Call the GDELT GEO API and return normalised articles.

        The GEO API returns similar artlist-style JSON but geo-tagged.
        URL pattern:
            /geo/geo?query=<q>&mode=artlist&maxrecords=<n>&format=json
        """
        url = f"{self._base_url}/geo/geo"
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": min(max_results, 250),
            "format": "json",
        }

        try:
            data = await self._get_json(url, params)
        except Exception as exc:  # noqa: BLE001
            # GEO API is less reliable; degrade gracefully
            logger.warning("GDELT GEO API error — returning empty list: %s", exc)
            return []

        articles_raw: List[dict] = data.get("articles") or []

        articles: List[NormalizedArticle] = []
        for raw in articles_raw:
            try:
                articles.append(self.normalize(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("GDELT GEO normalize error — skipping: %s", exc)

        logger.debug("GDELT GEO returned %d articles", len(articles))
        return articles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_json(
        self,
        url: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Module-level utilities
# ---------------------------------------------------------------------------


def _parse_gdelt_date(date_str: Optional[str]) -> datetime:
    """
    Parse a GDELT seendate string in "YYYYMMDDTHHMMSSZ" format.

    Falls back to ``datetime.utcnow()`` on any parse failure.
    """
    if not date_str:
        logger.warning("GDELT article has no seendate — using utcnow()")
        return datetime.now(tz=timezone.utc)
    try:
        dt = datetime.strptime(date_str, _GDELT_DATE_FMT)
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning("Could not parse GDELT date %r — using utcnow()", date_str)
        return datetime.now(tz=timezone.utc)


def _domain_from_url(url: str) -> Optional[str]:
    """Best-effort domain extraction from a URL string."""
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or None
    except Exception:  # noqa: BLE001
        return None


async def _gather_two(coro1: Any, coro2: Any):  # type: ignore[return]
    """Thin wrapper around asyncio.gather for two coroutines."""
    import asyncio

    return await asyncio.gather(coro1, coro2, return_exceptions=False)
