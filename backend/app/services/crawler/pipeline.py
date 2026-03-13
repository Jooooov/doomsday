"""
Core async crawl pipeline: fetch → parse → index.

Functions
---------
crawl_single_url(url, config)
    Fetch a single URL and return a CrawledPage with extracted content.

crawl_and_index(urls, config, session)
    Crawl a list of URLs concurrently (bounded), parse each page, and
    upsert the results into the source_content table via the indexer.

The pipeline respects rate-limit delays between requests to the same host
and applies an exponential-backoff retry policy for transient HTTP errors.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from .config import CrawlerConfig
from .schema import CrawlJob, CrawlStatus, CrawledPage

logger = logging.getLogger(__name__)

# ── Tags whose content is stripped during text extraction ──────────────────
_STRIP_TAGS = frozenset(
    [
        "script", "style", "noscript", "nav", "header", "footer",
        "aside", "form", "button", "iframe", "svg", "img",
        "[document]", "html", "head",
    ]
)

# ── Regex: collapse whitespace runs ────────────────────────────────────────
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# HTML parsing (BeautifulSoup if available, plain-text fallback otherwise)
# ---------------------------------------------------------------------------


def _extract_text_bs4(html: str) -> tuple[Optional[str], str]:
    """
    Parse HTML with BeautifulSoup and return (title, body_text).

    Returns empty strings if parsing fails.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        logger.warning("beautifulsoup4 not installed — falling back to regex text extraction")
        return _extract_text_regex(html)

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        h1_tag = soup.find("h1")
        title: Optional[str] = None
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
        elif h1_tag:
            title = h1_tag.get_text(strip=True)

        # Remove noise elements
        for tag_name in _STRIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Extract body (prefer <main>, <article>, then <body>)
        container = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", {"id": re.compile(r"content|main|body", re.I)})
            or soup.find("body")
            or soup
        )

        raw_text = container.get_text(separator="\n")  # type: ignore[union-attr]

        # Clean whitespace
        lines = [_WS_RE.sub(" ", ln).strip() for ln in raw_text.splitlines()]
        non_empty = [ln for ln in lines if ln]
        body_text = _NL_RE.sub("\n\n", "\n".join(non_empty))

        return title, body_text

    except Exception as exc:  # pragma: no cover
        logger.warning("bs4 parse error: %s — falling back to regex", exc)
        return _extract_text_regex(html)


def _extract_text_regex(html: str) -> tuple[Optional[str], str]:
    """Minimal regex-based HTML stripper as a last-resort fallback."""
    # Extract title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = title_match.group(1).strip() if title_match else None

    # Strip all tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)  # basic HTML entities
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text)
    return title, text.strip()


# ---------------------------------------------------------------------------
# Single URL fetch
# ---------------------------------------------------------------------------


async def crawl_single_url(
    url: str,
    config: Optional[CrawlerConfig] = None,
    *,
    source_key: str = "unknown",
    source_label: str = "",
    url_pattern: str = "",
    language: str = "en",
) -> CrawledPage:
    """
    Fetch a single URL and return a ``CrawledPage`` with extracted content.

    Parameters
    ----------
    url:
        The URL to crawl.
    config:
        Crawler configuration (timeouts, headers, retry policy).
        Uses defaults if not provided.
    source_key, source_label, url_pattern, language:
        Metadata attached to the returned CrawledPage.

    Returns
    -------
    CrawledPage
        Always returns a CrawledPage; check `.status` for success/failure.
    """
    cfg = config or CrawlerConfig()

    page = CrawledPage(
        url=url,
        source_key=source_key,
        source_label=source_label,
        url_pattern=url_pattern,
        language=language,
        status=CrawlStatus.FETCHING,
    )

    client_kwargs: dict = {
        "headers": cfg.headers,
        "follow_redirects": cfg.follow_redirects,
        "timeout": cfg.request_timeout_seconds,
        "verify": cfg.verify_ssl,
    }
    if cfg.proxy_url:
        client_kwargs["proxies"] = {"https://": cfg.proxy_url, "http://": cfg.proxy_url}

    for attempt in range(cfg.retry.max_attempts):
        t_start = time.monotonic()
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url)

            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            page.crawl_duration_ms = elapsed_ms
            page.http_status = response.status_code
            page.crawled_at = datetime.now(timezone.utc)
            page.content_type = response.headers.get("content-type", "")

            # Handle retry-able HTTP errors
            if response.status_code in cfg.retry.retryable_status_codes:
                if attempt < cfg.retry.max_attempts - 1:
                    sleep_s = cfg.retry.sleep_seconds(attempt)
                    logger.warning(
                        "HTTP %s for %s — retrying in %.1fs (attempt %d/%d)",
                        response.status_code, url, sleep_s,
                        attempt + 1, cfg.retry.max_attempts,
                    )
                    await asyncio.sleep(sleep_s)
                    continue
                else:
                    page.status = CrawlStatus.FAILED
                    page.error = f"HTTP {response.status_code} after {cfg.retry.max_attempts} attempts"
                    logger.error("FAILED %s: %s", url, page.error)
                    return page

            if response.status_code != 200:
                page.status = CrawlStatus.FAILED
                page.error = f"HTTP {response.status_code}"
                logger.warning("Non-200 response for %s: %s", url, response.status_code)
                return page

            # Check content length
            content_bytes = response.content
            if len(content_bytes) > cfg.max_content_length_bytes:
                page.status = CrawlStatus.SKIPPED
                page.error = (
                    f"Content too large: {len(content_bytes)} bytes "
                    f"(limit {cfg.max_content_length_bytes})"
                )
                logger.warning("SKIPPED large page %s (%d bytes)", url, len(content_bytes))
                return page

            # Decode HTML
            html = response.text
            page.content_html = html if cfg.save_html else None
            page.status = CrawlStatus.PARSING

            # Extract text
            title, body_text = _extract_text_bs4(html)
            page.title = title
            page.content_text = body_text
            page.word_count = len(body_text.split()) if body_text else 0

            # Compute content hash for change detection
            hash_input = (body_text or "").encode("utf-8")
            page.content_hash = hashlib.sha256(hash_input).hexdigest()

            page.status = CrawlStatus.INDEXED
            logger.info(
                "OK %s — %d words in %dms",
                url, page.word_count, elapsed_ms,
            )
            return page

        except httpx.TimeoutException:
            sleep_s = cfg.retry.sleep_seconds(attempt)
            logger.warning(
                "Timeout for %s (attempt %d/%d) — retrying in %.1fs",
                url, attempt + 1, cfg.retry.max_attempts, sleep_s,
            )
            if attempt < cfg.retry.max_attempts - 1:
                await asyncio.sleep(sleep_s)
            else:
                page.status = CrawlStatus.FAILED
                page.error = f"Timeout after {cfg.retry.max_attempts} attempts"

        except httpx.RequestError as exc:
            page.status = CrawlStatus.FAILED
            page.error = f"Request error: {exc}"
            logger.error("Request error for %s: %s", url, exc)
            return page

        except Exception as exc:  # pragma: no cover
            page.status = CrawlStatus.FAILED
            page.error = f"Unexpected error: {exc}"
            logger.error("Unexpected error crawling %s: %s", url, exc, exc_info=True)
            return page

    return page


# ---------------------------------------------------------------------------
# Batch crawl + index
# ---------------------------------------------------------------------------


async def crawl_and_index(
    urls: List[str],
    config: Optional[CrawlerConfig] = None,
    *,
    source_key: str = "unknown",
    source_label: str = "",
    language: str = "en",
    concurrency: int = 3,
    session=None,  # sqlalchemy AsyncSession — optional; None = dry-run
) -> List[CrawledPage]:
    """
    Crawl a list of URLs concurrently (bounded by ``concurrency``) and
    optionally persist results into the database via the indexer.

    Parameters
    ----------
    urls:
        List of URLs to crawl.
    config:
        Shared crawler configuration (rate limits, retries, headers).
    source_key:
        Logical source identifier (e.g. ``"red_cross"``).
    source_label:
        Human-readable source label.
    language:
        Expected page language.
    concurrency:
        Maximum number of concurrent HTTP requests.
    session:
        SQLAlchemy AsyncSession.  When provided, each successfully parsed
        page is upserted into the ``source_content`` table.
        Pass ``None`` for a dry-run (crawl without persisting).

    Returns
    -------
    list[CrawledPage]
        All crawled pages in the order of the input URLs list.
    """
    cfg = config or CrawlerConfig()
    semaphore = asyncio.Semaphore(concurrency)

    # Track per-host last-request timestamps for rate limiting
    host_last_request: dict[str, float] = {}

    async def _fetch_one(url: str) -> CrawledPage:
        host = urlparse(url).netloc
        async with semaphore:
            # Per-host rate limiting
            last = host_last_request.get(host, 0.0)
            gap = time.monotonic() - last
            if gap < cfg.rate_limit_delay_seconds:
                await asyncio.sleep(cfg.rate_limit_delay_seconds - gap)
            host_last_request[host] = time.monotonic()

            return await crawl_single_url(
                url,
                cfg,
                source_key=source_key,
                source_label=source_label,
                language=language,
            )

    tasks = [_fetch_one(url) for url in urls]
    pages: List[CrawledPage] = await asyncio.gather(*tasks, return_exceptions=False)

    # Index into DB if session provided
    if session is not None:
        from .indexer import index_pages
        await index_pages(pages, session=session, source_key=source_key)

    return pages
