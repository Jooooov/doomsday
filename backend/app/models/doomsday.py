"""
SQLAlchemy ORM models for the Doomsday platform.

Tables:
  - country_risk_scores   : Current & historical per-country Doomsday scores
  - news_scan_runs        : Audit log of each 6-hour scan cycle
  - news_signals          : Individual LLM-analysed signal records per scan
  - clock_snapshots       : Immutable point-in-time snapshots (for timeline API)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CountryRiskScore(Base):
    """
    Stores the current Doomsday Clock score for a country/region.
    One row per country; updated in place each scan cycle.

    The `score_seconds` represents how many seconds remain on the
    Doomsday Clock for this specific country, relative to midnight (00:00).
    Higher values = safer; lower values = more dangerous.

    Baseline: 85 seconds (Bulletin of Atomic Scientists 2026 global reference).
    Country deviations are calculated by the scoring engine and stored as deltas.
    """

    __tablename__ = "country_risk_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False, index=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=True)

    # ── Score fields ──────────────────────────────────────────────────────────
    score_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=85.0)
    baseline_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=85.0)
    cumulative_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ── Metadata ──────────────────────────────────────────────────────────────
    last_scan_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_scan_runs.id"), nullable=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    last_scan_run: Mapped["NewsScanRun | None"] = relationship(
        "NewsScanRun", foreign_keys=[last_scan_run_id]
    )
    snapshots: Mapped[list["ClockSnapshot"]] = relationship(
        "ClockSnapshot", back_populates="country", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<CountryRiskScore {self.country_code} "
            f"score={self.score_seconds:.2f}s>"
        )


class NewsScanRun(Base):
    """
    Audit log for each 4×/day scan cycle.
    Records timing, article counts, LLM call stats, and success/failure.
    """

    __tablename__ = "news_scan_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )  # running | completed | failed | partial

    articles_fetched: Mapped[int] = mapped_column(Integer, default=0)
    signals_generated: Mapped[int] = mapped_column(Integer, default=0)
    countries_updated: Mapped[int] = mapped_column(Integer, default=0)

    llm_calls_attempted: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls_failed: Mapped[int] = mapped_column(Integer, default=0)
    llm_fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    signals: Mapped[list["NewsSignal"]] = relationship(
        "NewsSignal", back_populates="scan_run", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["ClockSnapshot"]] = relationship(
        "ClockSnapshot", back_populates="scan_run"
    )

    def __repr__(self) -> str:
        return f"<NewsScanRun {self.id} status={self.status}>"


class NewsSignal(Base):
    """
    Individual LLM-analysed signal extracted from a news article.
    Each signal contributes to regional risk delta calculations.

    The `raw_score` (0–10) is produced by the LLM.
    The `weighted_delta_contribution` is computed by the scoring engine
    after applying category weights and country-specific modifiers.
    """

    __tablename__ = "news_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_scan_runs.id"), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

    # ── Article metadata ──────────────────────────────────────────────────────
    article_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    article_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── LLM analysis output ───────────────────────────────────────────────────
    signal_category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. military_escalation, nuclear_posture, sanctions, ...
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)          # 0.0–10.0
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False)       # escalating | de-escalating | neutral
    confidence: Mapped[float] = mapped_column(Float, nullable=False)         # 0.0–1.0
    llm_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Computed by scoring engine ────────────────────────────────────────────
    category_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    country_modifier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    weighted_delta_contribution: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ── Raw LLM payload (for audit / replay) ─────────────────────────────────
    llm_raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    scan_run: Mapped[NewsScanRun] = relationship("NewsScanRun", back_populates="signals")

    def __repr__(self) -> str:
        return (
            f"<NewsSignal {self.signal_category} "
            f"country={self.country_code} score={self.raw_score}>"
        )


class ClockSnapshot(Base):
    """
    Immutable point-in-time record of a country's Doomsday Clock score.
    Written once per scan cycle per country — never updated.
    Powers the timeline chart on the frontend.
    """

    __tablename__ = "clock_snapshots"
    __table_args__ = (
        UniqueConstraint("country_code", "scan_run_id", name="uq_snapshot_country_scan"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    scan_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("news_scan_runs.id"), nullable=False
    )
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("country_risk_scores.id"), nullable=False
    )

    score_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    delta_applied: Mapped[float] = mapped_column(Float, nullable=False)  # actual delta (post-cap)
    raw_delta: Mapped[float] = mapped_column(Float, nullable=False)       # pre-cap delta from signals
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)

    # Summary stats for the map tooltip
    dominant_signal_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    top_contributing_article: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    country: Mapped[CountryRiskScore] = relationship(
        "CountryRiskScore", back_populates="snapshots"
    )
    scan_run: Mapped[NewsScanRun] = relationship("NewsScanRun", back_populates="snapshots")

    def __repr__(self) -> str:
        return (
            f"<ClockSnapshot {self.country_code} "
            f"score={self.score_seconds:.2f}s delta={self.delta_applied:+.2f}s>"
        )
