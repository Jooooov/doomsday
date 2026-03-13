"""
Crawler schema — lightweight dataclasses used by the pipeline internals.

These are *not* SQLAlchemy models — they live only in memory during a crawl
run and are translated to ``CrawledContent`` ORM rows by the indexer stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class CrawlStatus(str, Enum):
    """Processing status of a single crawl job."""
    PENDING = "pending"          # Not yet started
    FETCHING = "fetching"        # HTTP request in flight
    PARSING = "parsing"          # HTML parsing in progress
    INDEXING = "indexing"        # Being written to the database
    INDEXED = "indexed"          # Successfully stored
    FAILED = "failed"            # Unrecoverable error
    SKIPPED = "skipped"          # Unchanged since last crawl (hash match)


@dataclass
class CrawlJob:
    """
    A single URL to be crawled.

    Attributes
    ----------
    url:           The URL to fetch.
    source_key:    Logical source identifier (e.g. ``nato_civil_preparedness``).
    source_label:  Human-readable label for the source.
    url_pattern:   Pattern/template this URL was derived from (for auditing).
    language:      Expected language of the page (BCP-47).
    priority:      Higher values are crawled first (default 0).
    """

    url: str
    source_key: str
    source_label: str = ""
    url_pattern: str = ""
    language: str = "en"
    priority: int = 0
    status: CrawlStatus = CrawlStatus.PENDING
    error: Optional[str] = None


@dataclass
class CrawledPage:
    """
    The result of a successfully parsed crawl job.

    This intermediate object is produced by the parser stage and consumed
    by the indexer stage.  All fields are optional to accommodate partial
    parse failures gracefully.
    """

    # ── Source identity ──────────────────────────────────────────────────────
    url: str
    source_key: str
    source_label: str = ""
    url_pattern: str = ""

    # ── Extracted content ────────────────────────────────────────────────────
    title: Optional[str] = None
    content_text: Optional[str] = None
    content_html: Optional[str] = None
    content_hash: Optional[str] = None
    language: str = "en"
    word_count: int = 0

    # ── HTTP metadata ─────────────────────────────────────────────────────────
    http_status: int = 200
    content_type: Optional[str] = None
    last_modified_header: Optional[datetime] = None
    etag: Optional[str] = None

    # ── Structured metadata ───────────────────────────────────────────────────
    page_metadata: Dict = field(default_factory=dict)

    # ── Timing ───────────────────────────────────────────────────────────────
    crawl_duration_ms: int = 0
    crawled_at: Optional[datetime] = None

    # ── Internal status ───────────────────────────────────────────────────────
    status: CrawlStatus = CrawlStatus.PENDING
    error: Optional[str] = None
