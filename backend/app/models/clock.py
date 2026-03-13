from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from app.core.database import Base


class CountryRiskScore(Base):
    __tablename__ = "country_risk_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    country_iso: Mapped[str] = mapped_column(String(2), unique=True, index=True, nullable=False)

    # Clock values
    seconds_to_midnight: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # green/yellow/orange/red
    score_baseline: Mapped[float] = mapped_column(Float, nullable=False)

    # Context
    llm_context_paragraph: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    top_news_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Propagated (no active users in country, score from graph)
    is_propagated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_scan_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    affected_countries: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    impact_delta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scan_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
