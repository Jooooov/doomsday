"""
SourceContent ORM Model

Stores crawled and indexed content from authoritative sources
(Red Cross, FEMA, government civil-defense portals, etc.).

Used as a knowledge base for the guide-generation pipeline —
the LLM draws from this content rather than hallucinating
emergency-preparedness advice.

Table: source_content
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CrawlStatus(str, PyEnum):
    """Lifecycle state of a crawled page."""
    PENDING = "pending"       # URL discovered but not yet fetched
    FETCHED = "fetched"       # Raw HTML/text downloaded
    PARSED = "parsed"         # Content extracted and cleaned
    INDEXED = "indexed"       # Stored in DB, ready for LLM consumption
    FAILED = "failed"         # Fetch or parse error (see error_message)
    SKIPPED = "skipped"       # URL matched exclusion pattern


class ContentSource(str, PyEnum):
    """Authoritative source identifiers."""
    RED_CROSS = "red_cross"           # American Red Cross (redcross.org)
    FEMA = "fema"                     # FEMA (ready.gov / fema.gov)
    CDC = "cdc"                       # CDC (cdc.gov)
    WHO = "who"                       # World Health Organization
    NATO = "nato"                     # NATO public affairs
    PROTECAO_CIVIL_PT = "protecao_civil_pt"  # ANEPC Portugal
    CUSTOM = "custom"                 # Operator-added custom source


# ---------------------------------------------------------------------------
# Table: source_content
# ---------------------------------------------------------------------------


class SourceContent(Base, TimestampMixin):
    """
    Indexed content from a crawled authoritative source URL.

    Each row represents one crawled page.  The raw HTML is NOT stored —
    only the extracted plain-text body and structured metadata.

    Columns
    -------
    url                 Canonical URL that was crawled (unique)
    source              ContentSource enum — which organisation published it
    section_path        URL sub-path used to derive topic category
                        e.g. "/prepare/location/nuclear-explosion"
    title               Page <title> or <h1>
    summary             First 500 chars of extracted plain text (for display)
    body_text           Full cleaned plain-text body (stripped HTML/JS/CSS)
    topics              JSONB array of topic tags extracted/inferred
                        e.g. ["nuclear", "evacuation", "shelter-in-place"]
    applicable_regions  JSONB array of ISO 3166-1 alpha-2 codes this content
                        is relevant for.  ["US"] for US-specific, ["*"] = global
    language            BCP-47 language code ("en", "pt", …)
    word_count          Number of words in body_text
    status              CrawlStatus enum
    error_message       Error detail if status=FAILED
    http_status_code    HTTP response code from crawl attempt
    crawled_at          Timestamp of successful crawl
    content_hash        SHA-256 of body_text — used to detect unchanged pages
                        on re-crawl, avoids redundant DB writes
    is_active           False = soft-deleted / excluded from LLM context
    """

    __tablename__ = "source_content"
    __table_args__ = (
        UniqueConstraint("url", name="uq_source_content_url"),
        CheckConstraint(
            "status IN ('pending', 'fetched', 'parsed', 'indexed', 'failed', 'skipped')",
            name="ck_source_content_status",
        ),
        CheckConstraint(
            "source IN ('red_cross', 'fema', 'cdc', 'who', 'nato', 'protecao_civil_pt', 'custom')",
            name="ck_source_content_source",
        ),
        CheckConstraint(
            "word_count >= 0",
            name="ck_source_content_word_count_positive",
        ),
        Index("ix_source_content_source", "source"),
        Index("ix_source_content_status", "status"),
        Index("ix_source_content_language", "language"),
        Index("ix_source_content_crawled_at", "crawled_at"),
        Index("ix_source_content_source_status", "source", "status"),
        {"comment": "Indexed content from crawled authoritative emergency-preparedness sources"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Source identity ---
    url = Column(
        String(2000),
        nullable=False,
        comment="Canonical URL that was crawled (unique per source run)",
    )
    source = Column(
        String(30),
        nullable=False,
        default=ContentSource.RED_CROSS.value,
        comment="Authoritative source identifier (red_cross, fema, etc.)",
    )
    section_path = Column(
        String(500),
        nullable=True,
        comment="URL path relative to source root — used for topic inference",
    )

    # --- Content ---
    title = Column(
        String(500),
        nullable=True,
        comment="Page title extracted from <title> or <h1>",
    )
    summary = Column(
        String(1000),
        nullable=True,
        comment="First ~500 chars of extracted plain text (for display/preview)",
    )
    body_text = Column(
        Text,
        nullable=True,
        comment="Full cleaned plain-text body (HTML/JS/CSS stripped)",
    )

    # --- Metadata ---
    topics = Column(
        JSONB,
        nullable=True,
        comment='Topic tags: ["nuclear", "evacuation", "first-aid", ...]',
    )
    applicable_regions = Column(
        JSONB,
        nullable=True,
        default=lambda: ["*"],
        comment='ISO 3166-1 codes this content applies to; ["*"] = global',
    )
    language = Column(
        String(10),
        nullable=False,
        default="en",
        comment="BCP-47 language code",
    )
    word_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Word count of body_text",
    )

    # --- Crawl lifecycle ---
    status = Column(
        String(20),
        nullable=False,
        default=CrawlStatus.PENDING.value,
        comment="Crawl lifecycle state",
    )
    error_message = Column(
        String(1000),
        nullable=True,
        comment="Error detail when status=failed",
    )
    http_status_code = Column(
        Integer,
        nullable=True,
        comment="HTTP response code from the crawl attempt",
    )
    crawled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the successful crawl (UTC)",
    )

    # --- Dedup / refresh ---
    content_hash = Column(
        String(64),
        nullable=True,
        comment="SHA-256 hex of body_text — used to detect unchanged pages on re-crawl",
    )

    # --- Control ---
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="False = soft-deleted / excluded from LLM context windows",
    )

    def __repr__(self) -> str:
        return (
            f"<SourceContent source={self.source!r} "
            f"status={self.status!r} "
            f"words={self.word_count} "
            f"url={self.url[:60]!r}>"
        )

    @property
    def is_indexed(self) -> bool:
        """True if this page has been successfully indexed."""
        return self.status == CrawlStatus.INDEXED.value

    @property
    def short_url(self) -> str:
        """URL truncated for logging."""
        return self.url[:80] if len(self.url) > 80 else self.url
