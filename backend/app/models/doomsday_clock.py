"""
Doomsday Clock Data Models

Implements the per-country Doomsday Clock scoring system anchored to the
Bulletin of the Atomic Scientists' ~85 seconds (2026 reference baseline).

Score semantics:
  - normalized_score: seconds to midnight on the Doomsday Clock scale
  - Lower value = closer to midnight = higher danger
  - Baseline anchor: ~85 seconds (matches 2026 BAS reference)
  - Hard delta limit: +/-5 seconds per recalculation (prevents score spikes)
  - Recalculation schedule: 4x per day (every 6 hours)

Country regions supported in MVP: Portugal (PT), USA (US)
Full global risk map uses all ISO 3166-1 alpha-2 codes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RecalcTrigger(str, PyEnum):
    """What triggered a Doomsday Clock score recalculation."""
    SCHEDULED = "scheduled"       # Normal 6-hour scheduled scan
    MANUAL = "manual"             # Operator-triggered via CLI
    NEWS_EVENT = "news_event"     # Breaking news spike detected
    INITIAL = "initial"           # First-time seeding of a country
    ROLLBACK = "rollback"         # Score reverted via CLI rollback command


class ScoreConfidenceLevel(str, PyEnum):
    """LLM analysis confidence level for a score."""
    HIGH = "high"         # >80% confidence
    MEDIUM = "medium"     # 50–80% confidence
    LOW = "low"           # <50% confidence (fallback to regional baseline)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Baseline anchor in seconds (Bulletin of the Atomic Scientists, 2026)
GLOBAL_BASELINE_SECONDS: Decimal = Decimal("85.0")

# Hard per-recalculation delta cap (seconds), per system constraint
MAX_DELTA_PER_RECALC: Decimal = Decimal("5.0")

# Score bounds: minutes-to-midnight range representable on the clock
SCORE_MIN_SECONDS: Decimal = Decimal("10.0")   # Effectively midnight
SCORE_MAX_SECONDS: Decimal = Decimal("3600.0")  # 60 minutes — very safe


# ---------------------------------------------------------------------------
# Table: doomsday_scores  (current state, one row per country)
# ---------------------------------------------------------------------------


class DoomsdayScore(Base, TimestampMixin):
    """
    Current per-country Doomsday Clock score.

    One authoritative row per country_code at any given time.
    Historical snapshots are stored in ScoreHistory.

    Columns
    -------
    country_code        ISO 3166-1 alpha-2 (e.g. "PT", "US", "RU")
    country_name        Human-readable country name in English
    raw_score           0–100 risk index output from LLM analysis pipeline.
                        This is the *before-normalization* value.
    normalized_score    Seconds-to-midnight on the Doomsday Clock scale.
                        Derived from raw_score + regional_multiplier + baseline.
                        Lower = closer to midnight = higher danger.
    baseline_anchor     Reference anchor value in seconds (~85.0 for 2026).
                        Allows the baseline to be updated globally without
                        recalculating individual country scores.
    regional_multiplier Adjustment factor that accounts for regional geopolitical
                        context (e.g. Europe is generally closer to the front line
                        than South America). Applied multiplicatively during
                        normalization: normalized = baseline * multiplier * (1 - raw/200)
    previous_score      The normalized_score from the immediately preceding
                        recalculation. Used to compute score_delta.
    score_delta         Difference: normalized_score - previous_score.
                        Bounded by MAX_DELTA_PER_RECALC (±5 seconds).
                        Positive = moving away from midnight (safer).
                        Negative = moving toward midnight (more dangerous).
    confidence_level    LLM confidence: high / medium / low.
    last_updated        Timestamp when this row was last recalculated (UTC).
    next_update_at      Scheduled timestamp for the next recalculation (UTC).
    llm_model           Which LLM model produced this score (e.g. "qwen3.5").
    news_articles_used  Count of news articles fed to the LLM for this analysis.
    analysis_summary    Short LLM-generated human-readable summary (max 500 chars).
    analysis_metadata   JSONB blob with full LLM response metadata:
                        {"model", "tokens_used", "latency_ms", "sources": [...], ...}
    is_active           False if the country is excluded from the live map
                        (e.g. territories with no news data).
    """

    __tablename__ = "doomsday_scores"
    __table_args__ = (
        UniqueConstraint("country_code", name="uq_doomsday_scores_country_code"),
        CheckConstraint(
            "char_length(country_code) = 2",
            name="ck_doomsday_scores_country_code_len",
        ),
        CheckConstraint(
            "raw_score >= 0 AND raw_score <= 100",
            name="ck_doomsday_scores_raw_score_range",
        ),
        CheckConstraint(
            f"normalized_score >= {SCORE_MIN_SECONDS} AND normalized_score <= {SCORE_MAX_SECONDS}",
            name="ck_doomsday_scores_normalized_range",
        ),
        CheckConstraint(
            f"score_delta >= -{MAX_DELTA_PER_RECALC} AND score_delta <= {MAX_DELTA_PER_RECALC}",
            name="ck_doomsday_scores_delta_cap",
        ),
        CheckConstraint(
            "baseline_anchor > 0",
            name="ck_doomsday_scores_baseline_positive",
        ),
        Index("ix_doomsday_scores_country_code", "country_code"),
        Index("ix_doomsday_scores_normalized_score", "normalized_score"),
        Index("ix_doomsday_scores_last_updated", "last_updated"),
        {"comment": "Current per-country Doomsday Clock scores"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Surrogate PK")

    # --- Geographic identity ---
    country_code = Column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2 country code (uppercase)",
    )
    country_name = Column(
        String(100),
        nullable=False,
        comment="English country name",
    )

    # --- Scoring fields ---
    raw_score = Column(
        Numeric(precision=6, scale=3),
        nullable=False,
        comment="LLM-produced risk index 0–100 before normalization",
    )
    normalized_score = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        comment="Seconds to midnight (Doomsday Clock scale); lower = more dangerous",
    )
    baseline_anchor = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        default=float(GLOBAL_BASELINE_SECONDS),
        comment="Global baseline reference in seconds (~85.0 per BAS 2026)",
    )
    regional_multiplier = Column(
        Numeric(precision=6, scale=4),
        nullable=False,
        default=1.0,
        comment="Regional geopolitical adjustment factor (applied during normalization)",
    )

    # --- Change tracking ---
    previous_score = Column(
        Numeric(precision=8, scale=3),
        nullable=True,
        comment="Normalized score from the previous recalculation cycle",
    )
    score_delta = Column(
        Numeric(precision=6, scale=3),
        nullable=False,
        default=0.0,
        comment="Change vs previous_score, capped at ±5s per recalc",
    )

    # --- LLM metadata ---
    confidence_level = Column(
        String(10),
        nullable=False,
        default=ScoreConfidenceLevel.MEDIUM.value,
        comment="LLM confidence: high / medium / low",
    )
    llm_model = Column(
        String(100),
        nullable=True,
        comment="LLM model identifier used for this analysis",
    )
    news_articles_used = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of news articles fed to the LLM",
    )
    analysis_summary = Column(
        String(500),
        nullable=True,
        comment="Short LLM-generated human-readable summary of risk factors",
    )
    analysis_metadata = Column(
        JSONB,
        nullable=True,
        comment="Full LLM response metadata (model, tokens, latency, sources)",
    )

    # --- Scheduling ---
    last_updated = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this score was last recalculated (UTC)",
    )
    next_update_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Scheduled timestamp for next recalculation (UTC); NULL = not scheduled",
    )

    # --- Control flags ---
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this country is shown on the live risk map",
    )
    is_fallback = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if score was generated from regional baseline (LLM failed)",
    )

    # --- Relationships ---
    history = relationship(
        "ScoreHistory",
        back_populates="country_score",
        foreign_keys="ScoreHistory.country_code",
        primaryjoin="DoomsdayScore.country_code == foreign(ScoreHistory.country_code)",
        order_by="ScoreHistory.recorded_at.desc()",
        lazy="dynamic",
    )
    region_config = relationship(
        "RegionConfig",
        back_populates="country_scores",
        foreign_keys="[RegionConfig.region_code]",
        primaryjoin="DoomsdayScore.country_code == foreign(RegionConfig.region_code)",
        uselist=False,
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<DoomsdayScore country={self.country_code!r} "
            f"score={self.normalized_score}s delta={self.score_delta:+}s "
            f"confidence={self.confidence_level}>"
        )

    @property
    def danger_level(self) -> str:
        """Human-readable danger tier derived from normalized_score."""
        s = float(self.normalized_score)
        if s <= 30:
            return "critical"
        elif s <= 60:
            return "high"
        elif s <= 100:
            return "elevated"
        elif s <= 200:
            return "moderate"
        else:
            return "low"

    @property
    def seconds_to_midnight(self) -> float:
        """Convenience alias for normalized_score as a float."""
        return float(self.normalized_score)


# ---------------------------------------------------------------------------
# Table: score_history  (append-only audit log of score changes)
# ---------------------------------------------------------------------------


class ScoreHistory(Base):
    """
    Append-only historical log of Doomsday Clock score snapshots.

    Every time a DoomsdayScore row is recalculated, a new row is appended
    here. This powers trend graphs and rollback functionality.

    The rollback CLI command reads this table to find the previous snapshot
    and restores it to doomsday_scores.
    """

    __tablename__ = "score_history"
    __table_args__ = (
        Index("ix_score_history_country_code", "country_code"),
        Index("ix_score_history_recorded_at", "recorded_at"),
        Index("ix_score_history_country_recorded", "country_code", "recorded_at"),
        {"comment": "Append-only audit log of per-country Doomsday Clock score history"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Surrogate PK")

    country_code = Column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2 country code",
    )
    country_name = Column(
        String(100),
        nullable=False,
        comment="English country name at time of snapshot",
    )

    # --- Score snapshot ---
    raw_score = Column(
        Numeric(precision=6, scale=3),
        nullable=False,
        comment="Raw LLM risk index at time of snapshot",
    )
    normalized_score = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        comment="Normalized seconds-to-midnight at time of snapshot",
    )
    baseline_anchor = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        comment="Baseline anchor used in this calculation",
    )
    regional_multiplier = Column(
        Numeric(precision=6, scale=4),
        nullable=False,
        default=1.0,
        comment="Regional multiplier used in this calculation",
    )
    score_delta = Column(
        Numeric(precision=6, scale=3),
        nullable=False,
        default=0.0,
        comment="Delta from previous snapshot, capped at ±5s",
    )

    # --- Analysis context ---
    confidence_level = Column(
        String(10),
        nullable=False,
        default=ScoreConfidenceLevel.MEDIUM.value,
        comment="LLM confidence level",
    )
    trigger = Column(
        String(20),
        nullable=False,
        default=RecalcTrigger.SCHEDULED.value,
        comment="What triggered this recalculation",
    )
    llm_model = Column(
        String(100),
        nullable=True,
        comment="LLM model used",
    )
    news_articles_used = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of news articles analysed",
    )
    analysis_summary = Column(
        String(500),
        nullable=True,
        comment="Short LLM-generated summary",
    )
    analysis_metadata = Column(
        JSONB,
        nullable=True,
        comment="Full LLM metadata blob",
    )
    is_fallback = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if generated from regional baseline (LLM failed)",
    )

    # --- Timestamps ---
    recorded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this snapshot was recorded (UTC)",
    )

    # --- Relationships ---
    country_score = relationship(
        "DoomsdayScore",
        back_populates="history",
        foreign_keys=[country_code],
        primaryjoin="ScoreHistory.country_code == foreign(DoomsdayScore.country_code)",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ScoreHistory country={self.country_code!r} "
            f"score={self.normalized_score}s "
            f"trigger={self.trigger!r} "
            f"at={self.recorded_at.isoformat() if self.recorded_at else 'N/A'}>"
        )


# ---------------------------------------------------------------------------
# Table: global_clock_state  (single-row global aggregated state)
# ---------------------------------------------------------------------------


class GlobalClockState(Base, TimestampMixin):
    """
    Singleton table holding the globally aggregated Doomsday Clock state.

    This is derived from the weighted average of all active country scores
    and is what powers the headline clock displayed on the landing page.

    Constraints
    -----------
    - Always exactly ONE active row (id=1, by convention).
    - global_score uses the same seconds-to-midnight semantics as per-country scores.
    - baseline_anchor mirrors the BAS reference (~85s in 2026).
    """

    __tablename__ = "global_clock_state"
    __table_args__ = (
        CheckConstraint(
            "global_score > 0",
            name="ck_global_clock_score_positive",
        ),
        CheckConstraint(
            "baseline_anchor > 0",
            name="ck_global_clock_baseline_positive",
        ),
        {"comment": "Singleton row holding global aggregated Doomsday Clock state"},
    )

    id = Column(
        Integer,
        primary_key=True,
        default=1,
        comment="Always 1 — singleton row",
    )

    global_score = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        comment="Globally aggregated seconds-to-midnight (weighted avg of country scores)",
    )
    baseline_anchor = Column(
        Numeric(precision=8, scale=3),
        nullable=False,
        default=float(GLOBAL_BASELINE_SECONDS),
        comment="BAS reference baseline in seconds (~85.0 for 2026)",
    )
    previous_global_score = Column(
        Numeric(precision=8, scale=3),
        nullable=True,
        comment="Previous global score for delta tracking",
    )
    global_delta = Column(
        Numeric(precision=6, scale=3),
        nullable=False,
        default=0.0,
        comment="Change in global_score since last recalculation, capped at ±5s",
    )

    active_countries_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of countries contributing to the global score",
    )
    countries_in_critical = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Countries with normalized_score <= 30s (critical tier)",
    )
    countries_in_high = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Countries with normalized_score 31–60s (high tier)",
    )

    last_recalculated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When the global score was last recalculated (UTC)",
    )
    next_recalculation_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Next scheduled global recalculation (UTC); every 6 hours",
    )
    fallback_static_built_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the last hourly Cloudflare Pages fallback static build ran",
    )

    calculation_metadata = Column(
        JSONB,
        nullable=True,
        comment="Metadata about the last global aggregation calculation",
    )

    def __repr__(self) -> str:
        return (
            f"<GlobalClockState score={self.global_score}s "
            f"countries={self.active_countries_count} "
            f"last_recalc={self.last_recalculated_at}>"
        )


# ---------------------------------------------------------------------------
# Table: news_events  (news articles processed during score calculation)
# ---------------------------------------------------------------------------


class NewsEvent(Base):
    """
    News articles and events that were processed during score recalculations.

    Stored for auditability, LLM context replay, and rollback support.
    Linked to a score_history snapshot via score_history_id.
    """

    __tablename__ = "news_events"
    __table_args__ = (
        Index("ix_news_events_country_code", "country_code"),
        Index("ix_news_events_published_at", "published_at"),
        Index("ix_news_events_score_history_id", "score_history_id"),
        {"comment": "News articles processed during Doomsday Clock recalculations"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    score_history_id = Column(
        Integer,
        ForeignKey("score_history.id", ondelete="SET NULL"),
        nullable=True,
        comment="FK to the score_history snapshot that consumed this article",
    )
    country_code = Column(
        String(2),
        nullable=False,
        comment="Country code this news event relates to",
    )

    # --- Article metadata ---
    title = Column(String(500), nullable=False, comment="Article headline")
    url = Column(String(2000), nullable=True, comment="Source URL")
    source_name = Column(String(200), nullable=True, comment="News source name")
    published_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Article publication timestamp",
    )
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this article was fetched by the news service",
    )

    # --- LLM-scored relevance ---
    relevance_score = Column(
        Numeric(precision=5, scale=3),
        nullable=True,
        comment="LLM-assigned relevance score 0–1 for this article",
    )
    sentiment_score = Column(
        Numeric(precision=5, scale=3),
        nullable=True,
        comment="Sentiment -1 (very negative) to +1 (very positive)",
    )
    risk_keywords = Column(
        JSONB,
        nullable=True,
        comment="Risk-relevant keywords extracted from the article",
    )

    def __repr__(self) -> str:
        return f"<NewsEvent country={self.country_code!r} title={self.title[:50]!r}>"


# ---------------------------------------------------------------------------
# Table: region_config  (per-country/region calibration data)
# ---------------------------------------------------------------------------


class RegionConfig(Base, TimestampMixin):
    """
    Calibration and configuration data for each country/region.

    Controls how raw LLM scores are normalized for a specific country,
    including regional multiplier, neighboring countries, and baseline overrides.

    MVP covers: Portugal (PT), USA (US)
    Extended: all countries in the global risk map.
    """

    __tablename__ = "region_configs"
    __table_args__ = (
        UniqueConstraint("region_code", name="uq_region_configs_code"),
        Index("ix_region_configs_region_code", "region_code"),
        {"comment": "Per-country/region calibration configuration for score normalization"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    region_code = Column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2 country code",
    )
    region_name = Column(
        String(100),
        nullable=False,
        comment="Human-readable region name",
    )

    # --- Normalization parameters ---
    regional_multiplier = Column(
        Numeric(precision=6, scale=4),
        nullable=False,
        default=1.0,
        comment="Multiplier applied to baseline_anchor during normalization. "
                "Values >1 push score closer to midnight; <1 pushes further.",
    )
    baseline_override = Column(
        Numeric(precision=8, scale=3),
        nullable=True,
        comment="If set, overrides global baseline_anchor for this region",
    )
    max_delta_override = Column(
        Numeric(precision=5, scale=2),
        nullable=True,
        comment="If set, overrides global MAX_DELTA_PER_RECALC for this region",
    )

    # --- Geopolitical context ---
    neighboring_countries = Column(
        JSONB,
        nullable=True,
        comment='Array of neighboring country codes: ["ES","FR","MA"]',
    )
    alliance_memberships = Column(
        JSONB,
        nullable=True,
        comment='Array of alliances: ["NATO","EU","UN"]',
    )
    conflict_proximity_km = Column(
        Integer,
        nullable=True,
        comment="Distance in km to nearest active conflict zone",
    )

    # --- News sources ---
    primary_news_sources = Column(
        JSONB,
        nullable=True,
        comment="Preferred news API sources for this country (NewsAPI source IDs)",
    )
    news_languages = Column(
        JSONB,
        nullable=True,
        comment='Array of language codes for news queries: ["pt","en"]',
    )

    # --- Control ---
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this region is active in the live map",
    )
    is_mvp_region = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True for MVP-supported regions (PT, US) with full pre-generated content",
    )

    # --- Relationships ---
    country_scores = relationship(
        "DoomsdayScore",
        back_populates="region_config",
        foreign_keys="[DoomsdayScore.country_code]",
        primaryjoin="RegionConfig.region_code == foreign(DoomsdayScore.country_code)",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return (
            f"<RegionConfig code={self.region_code!r} "
            f"multiplier={self.regional_multiplier} "
            f"mvp={self.is_mvp_region}>"
        )
