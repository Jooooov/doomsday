"""
Pydantic schemas for news data integration.

Defines the shared NormalizedArticle schema plus raw-response schemas for
NewsAPI and GDELT, and the ArticleBatch container.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Raw provider schemas
# ---------------------------------------------------------------------------


class NewsAPISource(BaseModel):
    """Nested source object inside a NewsAPI article."""

    id: Optional[str] = None
    name: str


class NewsAPIArticle(BaseModel):
    """Raw article shape returned by the NewsAPI /everything or /top-headlines endpoint."""

    source: NewsAPISource
    author: Optional[str] = None
    title: str
    description: Optional[str] = None
    url: str
    urlToImage: Optional[str] = None
    publishedAt: str  # ISO 8601 string, e.g. "2026-03-10T12:00:00Z"
    content: Optional[str] = None


class GDELTEvent(BaseModel):
    """
    Raw article shape returned by the GDELT DOC API artlist mode.

    Field names match what GDELT actually returns in its JSON response.
    Most fields are optional because GDELT coverage is inconsistent.
    """

    url: str
    url_mobile: Optional[str] = None
    title: Optional[str] = None
    seendate: Optional[str] = None  # "YYYYMMDDTHHMMSSZ"
    socialimage: Optional[str] = None
    domain: Optional[str] = None
    language: Optional[str] = None
    sourcecountry: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared / normalised schema
# ---------------------------------------------------------------------------


class NormalizedArticle(BaseModel):
    """
    Provider-agnostic article representation.

    Every raw article from NewsAPI or GDELT is normalised into this schema
    before being stored or forwarded to the LLM analysis pipeline.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    headline: str
    body: Optional[str] = None
    source: str
    source_type: Literal["newsapi", "gdelt"]
    url: str
    country: Optional[str] = None
    published_at: datetime
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    language: str = "en"
    relevance_score: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Batch container
# ---------------------------------------------------------------------------


class ArticleBatch(BaseModel):
    """
    Collection of normalised articles returned by the aggregator.

    `source` is "aggregated" when articles come from multiple providers, or
    the provider name (e.g. "newsapi") when from a single source.
    """

    source: str
    count: int
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    articles: List[NormalizedArticle] = Field(default_factory=list)
