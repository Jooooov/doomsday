"""
CrawledContent ORM Model

Stores web pages crawled from authoritative preparedness sources
(ready.gov, fema.gov) for use as grounding material in LLM-powered
survival guides.

Each row represents one crawled URL with extracted text, metadata,
and a content hash for change detection on re-crawls.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class CrawledContent(Base, TimestampMixin):
    """
    One crawled web page from a preparedness/government source.

    Columns
    -------
    url             Canonical URL of the page (unique key for upserts)
    source_domain   e.g. "ready.gov", "fema.gov"
    source_category Logical category from the FEMA target list
                    e.g. "emergency-kit", "nuclear", "hurricane"
    title           Page <title> or <h1> content
    content_text    Full body text extracted from the page (HTML stripped)
    content_html    Raw inner-HTML of the main content element (optional,
                    stored only when save_html=True in crawler config)
    content_hash    SHA-256 of content_text — used to detect changes
                    between crawl runs and skip unchanged pages
    language        ISO 639-1 language code (default "en")
    http_status     HTTP response status code from the crawl
    crawled_at      Timestamp when the page was successfully crawled
    next_crawl_at   Scheduled re-crawl timestamp (NULL = no schedule)
    crawl_error     Error message if the last crawl attempt failed
    retry_count     Number of failed crawl attempts since last success
    meta_tags       JSONB dict of relevant <meta> tags (description, keywords…)
    headings        JSONB list of headings extracted from the page
    links           JSONB list of internal links found on the page
    is_active       Set to False to exclude from LLM context without deleting
    """

    __tablename__ = "crawled_content"
    __table_args__ = (
        UniqueConstraint("url", name="uq_crawled_content_url"),
        Index("ix_crawled_content_source_domain", "source_domain"),
        Index("ix_crawled_content_source_category", "source_category"),
        Index("ix_crawled_content_crawled_at", "crawled_at"),
        Index("ix_crawled_content_content_hash", "content_hash"),
        CheckConstraint("http_status >= 100 AND http_status < 600",
                        name="ck_crawled_content_http_status"),
        {"comment": "Web pages crawled from FEMA/ready.gov for LLM grounding"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Surrogate PK")

    # --- Identity ---
    url = Column(
        String(2048),
        nullable=False,
        comment="Canonical URL crawled",
    )
    source_domain = Column(
        String(100),
        nullable=False,
        comment="Domain of the source: ready.gov, fema.gov …",
    )
    source_category = Column(
        String(100),
        nullable=False,
        comment="Logical category from the FEMA target list (e.g. 'emergency-kit')",
    )

    # --- Content ---
    title = Column(
        String(500),
        nullable=True,
        comment="Page title extracted from <title> or <h1>",
    )
    content_text = Column(
        Text,
        nullable=True,
        comment="Full body text with HTML stripped — primary LLM input",
    )
    content_html = Column(
        Text,
        nullable=True,
        comment="Raw inner-HTML of the main content block (optional)",
    )
    content_hash = Column(
        String(64),
        nullable=True,
        comment="SHA-256 hex digest of content_text for change detection",
    )

    # --- Language / locale ---
    language = Column(
        String(10),
        nullable=False,
        default="en",
        comment="ISO 639-1 language code of the page content",
    )

    # --- Crawl state ---
    http_status = Column(
        Integer,
        nullable=True,
        comment="HTTP response status code (200, 404, …)",
    )
    crawled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the last successful crawl (UTC)",
    )
    next_crawl_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Scheduled next crawl timestamp; NULL = not scheduled",
    )
    crawl_error = Column(
        Text,
        nullable=True,
        comment="Last crawl error message if the crawl failed",
    )
    retry_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Consecutive failed crawl attempts since last success",
    )

    # --- Rich metadata ---
    meta_tags = Column(
        JSONB,
        nullable=True,
        comment="Relevant <meta> tags: {description, keywords, og:title, …}",
    )
    headings = Column(
        JSONB,
        nullable=True,
        comment="Ordered list of headings: [{level: 'h2', text: '...'}, …]",
    )
    links = Column(
        JSONB,
        nullable=True,
        comment="Internal links found on the page: [{href, text}, …]",
    )

    # --- Control ---
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="False = exclude from LLM context without deleting the row",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def compute_hash(text: str) -> str:
        """Compute SHA-256 hex digest of content text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def mark_crawled(self, text: str, html: Optional[str] = None) -> None:
        """Update content fields after a successful crawl."""
        self.content_text = text
        self.content_hash = self.compute_hash(text)
        if html is not None:
            self.content_html = html
        self.crawled_at = datetime.now(timezone.utc)
        self.crawl_error = None
        self.retry_count = 0

    def mark_failed(self, error: str) -> None:
        """Update error fields after a failed crawl."""
        self.crawl_error = error
        self.retry_count = (self.retry_count or 0) + 1

    def is_changed(self, new_text: str) -> bool:
        """Return True when new content differs from stored hash."""
        if not self.content_hash:
            return True
        return self.content_hash != self.compute_hash(new_text)

    def __repr__(self) -> str:
        return (
            f"<CrawledContent id={self.id} "
            f"domain={self.source_domain!r} "
            f"category={self.source_category!r} "
            f"url={self.url[:60]!r}…>"
        )
