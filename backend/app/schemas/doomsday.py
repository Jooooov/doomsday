"""
Pydantic v2 schemas for the Doomsday Clock scoring system.

Separate schemas for:
  - API request/response bodies
  - Internal service-layer data transfer
  - LLM I/O validation
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# LLM Analysis I/O
# ─────────────────────────────────────────────────────────────────────────────

class ArticleInput(BaseModel):
    """A news article to be analysed by the LLM."""

    url: str | None = None
    title: str
    content: str
    published_at: datetime | None = None
    source: str | None = None


class LLMSignalOutput(BaseModel):
    """
    Structured output from LLM analysis of a single news article.
    The LLM is instructed to return JSON matching this schema.

    `raw_score`: 0 = fully de-escalatory, 10 = maximum escalation signal.
    `sentiment`: direction of change relative to prior state.
    `confidence`: LLM's self-reported confidence in the analysis (0–1).
    """

    signal_category: str = Field(
        ...,
        description=(
            "One of: military_escalation, nuclear_posture, cyber_attack, "
            "sanctions_economic, diplomatic_breakdown, civilian_impact, "
            "peace_talks, arms_control, propaganda, other"
        ),
    )
    raw_score: float = Field(..., ge=0.0, le=10.0)
    sentiment: str = Field(..., pattern=r"^(escalating|de-escalating|neutral)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., max_length=500)
    affected_country_codes: list[str] = Field(
        default_factory=list,
        description="ISO-3166-1 alpha-3 country codes affected by this signal",
    )

    @field_validator("signal_category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = {
            "military_escalation",
            "nuclear_posture",
            "cyber_attack",
            "sanctions_economic",
            "diplomatic_breakdown",
            "civilian_impact",
            "peace_talks",
            "arms_control",
            "propaganda",
            "other",
        }
        if v not in allowed:
            return "other"
        return v

    @field_validator("affected_country_codes")
    @classmethod
    def normalise_codes(cls, v: list[str]) -> list[str]:
        return [c.upper()[:3] for c in v if c]


class LLMAnalysisResponse(BaseModel):
    """Full LLM response for a batch of articles targeting a country."""

    country_code: str
    signals: list[LLMSignalOutput]
    analysis_notes: str | None = None
    model_used: str | None = None
    retry_count: int = 0
    fallback_used: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Scoring Engine Internal DTOs
# ─────────────────────────────────────────────────────────────────────────────

class SignalRecord(BaseModel):
    """Enriched signal after scoring engine processing."""

    country_code: str
    signal_category: str
    raw_score: float
    sentiment: str
    confidence: float
    reasoning: str | None = None

    # Computed by the engine
    category_weight: float = 1.0
    country_modifier: float = 1.0
    weighted_delta_contribution: float = 0.0

    # Article provenance
    article_url: str | None = None
    article_title: str | None = None
    article_published_at: datetime | None = None
    article_source: str | None = None

    llm_raw_response: dict[str, Any] | None = None


class CountryDeltaResult(BaseModel):
    """
    Output of the scoring engine for a single country in one scan cycle.

    `raw_delta`: uncapped weighted sum of all signal contributions.
    `capped_delta`: raw_delta clamped to [-MAX_DELTA, +MAX_DELTA].
    `new_score`: previous_score + capped_delta, further clamped to [MIN, MAX].
    """

    country_code: str
    country_name: str

    previous_score: float
    raw_delta: float
    capped_delta: float
    new_score: float

    signal_count: int
    dominant_signal_category: str | None = None
    top_contributing_article: str | None = None
    fallback_used: bool = False

    signals: list[SignalRecord] = Field(default_factory=list)


class ScanCycleResult(BaseModel):
    """Aggregate result of a full 6-hour scan cycle across all countries."""

    scan_run_id: uuid.UUID
    started_at: datetime
    completed_at: datetime
    status: str
    country_results: list[CountryDeltaResult]
    total_articles_fetched: int
    total_signals_generated: int
    llm_calls_attempted: int
    llm_calls_succeeded: int
    llm_fallback_used: bool


# ─────────────────────────────────────────────────────────────────────────────
# API Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CountryScoreResponse(BaseModel):
    """Public API response for a single country's current clock score."""

    country_code: str
    country_name: str
    region: str | None
    score_seconds: float
    baseline_seconds: float
    cumulative_delta: float
    last_updated_at: datetime

    class Config:
        from_attributes = True


class ClockSnapshotResponse(BaseModel):
    """A single point-in-time snapshot for the timeline chart."""

    country_code: str
    score_seconds: float
    delta_applied: float
    raw_delta: float
    signal_count: int
    fallback_used: bool
    dominant_signal_category: str | None
    snapshot_ts: datetime

    class Config:
        from_attributes = True


class GlobalClockResponse(BaseModel):
    """All country scores — used by the risk map."""

    scores: list[CountryScoreResponse]
    global_average_seconds: float
    bulletin_baseline_seconds: float
    last_scan_completed_at: datetime | None


class TriggerScanRequest(BaseModel):
    """Manual trigger for a scan cycle (admin/CLI use)."""

    country_codes: list[str] | None = Field(
        default=None,
        description="If None, scan all configured countries",
    )
    dry_run: bool = Field(
        default=False,
        description="Run analysis but do not persist results",
    )

    @field_validator("country_codes")
    @classmethod
    def normalise(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [c.upper()[:3] for c in v if c]


class ScanStatusResponse(BaseModel):
    """Status of the latest scan run."""

    scan_run_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    articles_fetched: int
    signals_generated: int
    countries_updated: int
    llm_fallback_used: bool
    error_message: str | None

    class Config:
        from_attributes = True
