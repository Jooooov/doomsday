"""
NewsAPI client — wraps https://newsapi.org/v2 endpoints.

Uses httpx.AsyncClient for all HTTP calls.  Handles 429 rate-limit responses
with a configurable delay before retrying once.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from app.schemas.news import NormalizedArticle
from app.services.news.base import BaseNewsSource

logger = logging.getLogger(__name__)

# NewsAPI caps page size at 100
_MAX_PAGE_SIZE = 100
# Delay (seconds) after a 429 before the single automatic retry
_RATE_LIMIT_RETRY_DELAY = 1.0


class NewsAPIClient(BaseNewsSource):
    """
    Async client for the NewsAPI v2 REST API.

    Parameters
    ----------
    api_key:
        NewsAPI developer key.  Required for all non-health-check requests.
    base_url:
        Override the default https://newsapi.org/v2 base URL (useful in tests).
    rate_limit_delay:
        Seconds to wait before retrying after a 429 response.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://newsapi.org/v2",
        rate_limit_delay: float = _RATE_LIMIT_RETRY_DELAY,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._rate_limit_delay = rate_limit_delay

    # ------------------------------------------------------------------
    # BaseNewsSource interface
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return "newsapi"

    async def fetch(
        self,
        query: str,
        country: Optional[str] = None,
        max_results: int = 100,
    ) -> List[NormalizedArticle]:
        """
        Fetch articles from NewsAPI.

        Uses ``/top-headlines`` when a *country* is supplied (supports ISO
        alpha-2 filtering), otherwise falls back to ``/everything`` which has
        broader coverage but no country filter.
        """
        page_size = min(max_results, _MAX_PAGE_SIZE)

        if country:
            endpoint = "/top-headlines"
            params: Dict[str, Any] = {
                "apiKey": self._api_key,
                "q": query,
                "country": country.lower(),
                "pageSize": page_size,
            }
        else:
            endpoint = "/everything"
            params = {
                "apiKey": self._api_key,
                "q": query,
                "pageSize": page_size,
                "sortBy": "publishedAt",
                "language": "en",
            }

        url = f"{self._base_url}{endpoint}"
        logger.info(
            "NewsAPI fetch — endpoint=%s query=%r country=%s max=%d",
            endpoint,
            query,
            country,
            max_results,
        )

        data = await self._get_json(url, params)
        raw_articles: List[dict] = data.get("articles", [])

        articles: List[NormalizedArticle] = []
        for raw in raw_articles:
            try:
                article = self.normalize(raw, country=country)
                articles.append(article)
            except Exception as exc:  # noqa: BLE001
                logger.warning("NewsAPI normalize error — skipping article: %s", exc)

        logger.info("NewsAPI returned %d articles for query=%r", len(articles), query)
        return articles

    def normalize(  # type: ignore[override]
        self,
        raw: Any,
        country: Optional[str] = None,
    ) -> NormalizedArticle:
        """
        Map a raw NewsAPI article dict to a NormalizedArticle.

        NewsAPI's ``content`` field is truncated at 200 chars; ``description``
        is used as the body fallback.
        """
        title: str = raw.get("title") or ""
        if not title:
            raise ValueError("Article has no title — cannot normalize")

        # Prefer content, but it is truncated; fall back to description
        body: Optional[str] = raw.get("content") or raw.get("description") or None

        source_obj = raw.get("source", {})
        source_name: str = source_obj.get("name") or source_obj.get("id") or "unknown"

        url: str = raw.get("url") or ""

        # Parse ISO 8601 date string
        published_at_str: str = raw.get("publishedAt") or ""
        published_at = _parse_iso8601(published_at_str)

        return NormalizedArticle(
            headline=title,
            body=body,
            source=source_name,
            source_type="newsapi",
            url=url,
            country=country,
            published_at=published_at,
            language="en",
            raw_data=raw,
        )

    async def health_check(self) -> bool:
        """Ping NewsAPI with a minimal top-headlines request."""
        url = f"{self._base_url}/top-headlines"
        params = {"apiKey": self._api_key, "country": "us", "pageSize": 1}
        try:
            data = await self._get_json(url, params)
            return data.get("status") == "ok"
        except Exception as exc:  # noqa: BLE001
            logger.warning("NewsAPI health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_json(
        self,
        url: str,
        params: Dict[str, Any],
        *,
        _retry: bool = True,
    ) -> Dict[str, Any]:
        """
        Perform a GET request and return the parsed JSON body.

        On HTTP 429 the method waits ``rate_limit_delay`` seconds then retries
        exactly once.  Any other non-2xx response raises ``httpx.HTTPStatusError``.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

        if response.status_code == 429:
            logger.warning(
                "NewsAPI rate limit hit — waiting %.1fs before retry",
                self._rate_limit_delay,
            )
            if _retry:
                await asyncio.sleep(self._rate_limit_delay)
                return await self._get_json(url, params, _retry=False)
            response.raise_for_status()

        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _parse_iso8601(date_str: str) -> datetime:
    """
    Parse an ISO 8601 datetime string (as returned by NewsAPI) to a datetime.

    Falls back to ``datetime.utcnow()`` if parsing fails so that a single bad
    date does not abort an entire batch.
    """
    if not date_str:
        logger.warning("NewsAPI article has no publishedAt — using utcnow()")
        return datetime.now(tz=timezone.utc)
    try:
        # Python 3.11+ handles "Z" suffix; for 3.10 compatibility replace it.
        normalised = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(normalised)
    except (ValueError, TypeError):
        logger.warning("Could not parse NewsAPI date %r — using utcnow()", date_str)
        return datetime.now(tz=timezone.utc)
