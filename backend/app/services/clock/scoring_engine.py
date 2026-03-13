"""
Doomsday Clock Scoring Engine.

Converts LLM-produced news signals into per-country Doomsday Clock score deltas,
then applies all constraints defined in the system specification:

  - Hard delta cap: ±5 seconds per recalculation cycle
  - Score bounds: [60.0, 150.0] seconds (never below 60 or above 150)
  - Baseline anchor: 85.0 seconds (Bulletin of the Atomic Scientists, 2026)
  - Country-specific regional multipliers modify signal impact

Formula
-------
For each signal:
    direction = SENTIMENT_DIRECTIONS[signal.sentiment]   # -1, +1, or -0.2
    category_weight = CATEGORY_WEIGHTS[signal.signal_category]
    country_modifier = CountryConfig.country_modifier    # inverse of regional_multiplier
    contribution = (signal.raw_score / 10) * SIGNAL_SCALE_FACTOR
                   * direction * category_weight * country_modifier * signal.confidence

raw_delta = sum(contribution for each signal)
capped_delta = clamp(raw_delta, -MAX_DELTA, +MAX_DELTA)   # ±5s cap
new_score = clamp(previous_score + capped_delta, MIN_SCORE, MAX_SCORE)

Note: capped_delta is the ACTUAL change stored in DB (audit trail).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.config import get_settings
from app.schemas.doomsday import CountryDeltaResult, LLMAnalysisResponse, SignalRecord
from app.services.clock.region_registry import (
    SIGNAL_SCALE_FACTOR,
    get_category_weight,
    get_country_config,
    get_sentiment_direction,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Hard constraints from system spec ────────────────────────────────────────
MAX_DELTA_PER_CYCLE: float = settings.CLOCK_MAX_DELTA_PER_CYCLE   # 5.0s
MIN_SCORE: float = settings.CLOCK_MIN_SCORE                         # 60.0s
MAX_SCORE: float = settings.CLOCK_MAX_SCORE                         # 150.0s
GLOBAL_BASELINE: float = settings.CLOCK_BASELINE_SECONDS            # 85.0s


@dataclass
class ScoringInput:
    """All inputs needed by the scoring engine for one country in one cycle."""

    country_code: str
    country_name: str
    llm_response: LLMAnalysisResponse
    previous_score: float           # Current DB score (seconds to midnight)
    fallback_score: Optional[float] = None  # Regional baseline if LLM fails


@dataclass
class ScoringOutput:
    """Full scoring result for one country, ready to persist."""

    country_code: str
    country_name: str

    previous_score: float
    raw_delta: float          # Un-capped sum of signal contributions
    capped_delta: float       # Actual change applied (bounded by ±MAX_DELTA)
    new_score: float          # Final score after delta + bounds clamping

    signal_count: int
    dominant_signal_category: Optional[str]
    top_contributing_article: Optional[str]
    fallback_used: bool

    processed_signals: List[SignalRecord] = field(default_factory=list)
    calculated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_country_delta_result(self) -> CountryDeltaResult:
        """Convert to the Pydantic schema used by API responses."""
        return CountryDeltaResult(
            country_code=self.country_code,
            country_name=self.country_name,
            previous_score=self.previous_score,
            raw_delta=self.raw_delta,
            capped_delta=self.capped_delta,
            new_score=self.new_score,
            signal_count=self.signal_count,
            dominant_signal_category=self.dominant_signal_category,
            top_contributing_article=self.top_contributing_article,
            fallback_used=self.fallback_used,
            signals=self.processed_signals,
        )


class DoomsdayScoringEngine:
    """
    Stateless scoring engine — each call is independent.

    Inject via FastAPI dependency injection or instantiate directly.
    Thread-safe: no mutable state.
    """

    def __init__(
        self,
        max_delta: float = MAX_DELTA_PER_CYCLE,
        min_score: float = MIN_SCORE,
        max_score: float = MAX_SCORE,
    ) -> None:
        self.max_delta = max_delta
        self.min_score = min_score
        self.max_score = max_score

    # ── Public API ────────────────────────────────────────────────────────

    def score_country(self, inp: ScoringInput) -> ScoringOutput:
        """
        Calculate a new Doomsday Clock score for a single country.

        Steps:
        1. Resolve country config (regional_multiplier, country_modifier).
        2. Process each LLM signal → weighted contribution in seconds.
        3. Sum contributions → raw_delta.
        4. Apply ±MAX_DELTA cap → capped_delta.
        5. Apply score bounds → new_score.
        6. Return ScoringOutput with full audit trail.

        If LLM returned no signals (fallback), the score shifts toward the
        regional baseline anchor (gentle mean-reversion) rather than staying
        frozen.
        """
        country_cfg = get_country_config(inp.country_code)
        if country_cfg is None:
            logger.warning(
                "No config for country %s; using modifier=1.0", inp.country_code
            )
            country_modifier = 1.0
            regional_anchor = GLOBAL_BASELINE
        else:
            country_modifier = country_cfg.country_modifier
            regional_anchor = country_cfg.effective_anchor_seconds

        # ── Handle fallback (empty signals) ──────────────────────────────
        if inp.llm_response.fallback_used or not inp.llm_response.signals:
            return self._score_fallback(
                inp=inp,
                regional_anchor=regional_anchor,
            )

        # ── Process each signal ───────────────────────────────────────────
        processed_signals: List[SignalRecord] = []
        category_totals: dict[str, float] = {}

        for llm_signal in inp.llm_response.signals:
            direction = get_sentiment_direction(llm_signal.sentiment)
            cat_weight = get_category_weight(llm_signal.signal_category)

            # Core formula: contribution = (raw/10) × scale × direction × cat_weight
            #               × country_modifier × confidence
            contribution = (
                (llm_signal.raw_score / 10.0)
                * SIGNAL_SCALE_FACTOR
                * direction
                * cat_weight
                * country_modifier
                * llm_signal.confidence
            )

            signal_record = SignalRecord(
                country_code=inp.country_code,
                signal_category=llm_signal.signal_category,
                raw_score=llm_signal.raw_score,
                sentiment=llm_signal.sentiment,
                confidence=llm_signal.confidence,
                reasoning=llm_signal.reasoning,
                category_weight=cat_weight,
                country_modifier=country_modifier,
                weighted_delta_contribution=round(contribution, 4),
            )
            processed_signals.append(signal_record)
            category_totals[llm_signal.signal_category] = (
                category_totals.get(llm_signal.signal_category, 0.0)
                + abs(contribution)
            )

        # ── Aggregate ─────────────────────────────────────────────────────
        raw_delta = sum(s.weighted_delta_contribution for s in processed_signals)

        # ── Cap ───────────────────────────────────────────────────────────
        capped_delta = self._apply_delta_cap(raw_delta)

        # ── Compute new score ─────────────────────────────────────────────
        new_score = self._apply_score_bounds(inp.previous_score + capped_delta)

        # ── Dominant signal category (by total absolute contribution) ─────
        dominant_category = (
            max(category_totals, key=category_totals.get)
            if category_totals
            else None
        )

        # ── Top article (signal with highest absolute contribution) ───────
        top_signal = max(
            processed_signals,
            key=lambda s: abs(s.weighted_delta_contribution),
            default=None,
        )
        top_article = (
            top_signal.article_title if top_signal else None
        )

        logger.info(
            "Scored %s: previous=%.2fs raw_delta=%+.4fs capped=%+.4fs new=%.2fs "
            "signals=%d dominant=%s fallback=False",
            inp.country_code,
            inp.previous_score,
            raw_delta,
            capped_delta,
            new_score,
            len(processed_signals),
            dominant_category,
        )

        return ScoringOutput(
            country_code=inp.country_code,
            country_name=inp.country_name,
            previous_score=inp.previous_score,
            raw_delta=round(raw_delta, 4),
            capped_delta=round(capped_delta, 4),
            new_score=round(new_score, 3),
            signal_count=len(processed_signals),
            dominant_signal_category=dominant_category,
            top_contributing_article=top_article,
            fallback_used=False,
            processed_signals=processed_signals,
        )

    def score_all_countries(
        self, inputs: List[ScoringInput]
    ) -> List[ScoringOutput]:
        """
        Score multiple countries in a single call.
        Returns results in the same order as `inputs`.
        """
        results: List[ScoringOutput] = []
        for inp in inputs:
            try:
                result = self.score_country(inp)
                results.append(result)
            except Exception as exc:
                logger.exception(
                    "Scoring engine error for %s: %s — applying fallback",
                    inp.country_code,
                    exc,
                )
                # Hard fallback — keep previous score, zero delta
                results.append(
                    self._score_error_fallback(inp)
                )
        return results

    def compute_initial_score(self, country_code: str) -> float:
        """
        Return the initial seeded score for a country.

        Uses the country's pre-defined initial_score_seconds from the registry.
        Falls back to GLOBAL_BASELINE if country is not registered.
        """
        cfg = get_country_config(country_code)
        if cfg is not None:
            return cfg.initial_score_seconds
        logger.warning(
            "No registry entry for %s; seeding with global baseline %.1fs",
            country_code,
            GLOBAL_BASELINE,
        )
        return GLOBAL_BASELINE

    def compute_global_average(
        self,
        country_scores: dict[str, float],
        weight_by_risk: bool = True,
    ) -> float:
        """
        Compute the global Doomsday Clock score from all country scores.

        If weight_by_risk is True, countries closer to midnight (lower score)
        receive higher weight in the average. This reflects the BAS model
        where the worst actors dominate global risk perception.

        Weight formula (when weight_by_risk=True):
          w_i = 1 / score_i   (lower seconds = higher weight)

        Falls back to simple average if no scores provided.
        """
        if not country_scores:
            return GLOBAL_BASELINE

        if not weight_by_risk:
            return sum(country_scores.values()) / len(country_scores)

        total_weight = 0.0
        weighted_sum = 0.0
        for score in country_scores.values():
            w = 1.0 / max(score, 1.0)  # avoid division by zero
            weighted_sum += score * w
            total_weight += w

        if total_weight == 0:
            return GLOBAL_BASELINE

        return round(weighted_sum / total_weight, 3)

    # ── Private helpers ───────────────────────────────────────────────────

    def _apply_delta_cap(self, raw_delta: float) -> float:
        """Clamp raw_delta to ±MAX_DELTA_PER_CYCLE (hard constraint)."""
        return max(-self.max_delta, min(self.max_delta, raw_delta))

    def _apply_score_bounds(self, score: float) -> float:
        """Clamp score to [MIN_SCORE, MAX_SCORE]."""
        return max(self.min_score, min(self.max_score, score))

    def _score_fallback(
        self,
        inp: ScoringInput,
        regional_anchor: float,
    ) -> ScoringOutput:
        """
        Fallback scoring when the LLM returned no signals.

        Instead of freezing the score, we apply gentle mean-reversion toward
        the regional anchor. This prevents stale scores from drifting too far
        from the calibrated baseline when news is unavailable.

        Mean-reversion rate: 10% of the gap per cycle, capped at ±MAX_DELTA.
        """
        gap = regional_anchor - inp.previous_score
        raw_delta = gap * 0.10   # 10% reversion per cycle
        capped_delta = self._apply_delta_cap(raw_delta)
        new_score = self._apply_score_bounds(inp.previous_score + capped_delta)

        logger.info(
            "Fallback score for %s: anchor=%.2f previous=%.2f "
            "reversion=%+.4f new=%.2f",
            inp.country_code,
            regional_anchor,
            inp.previous_score,
            capped_delta,
            new_score,
        )

        return ScoringOutput(
            country_code=inp.country_code,
            country_name=inp.country_name,
            previous_score=inp.previous_score,
            raw_delta=round(raw_delta, 4),
            capped_delta=round(capped_delta, 4),
            new_score=round(new_score, 3),
            signal_count=0,
            dominant_signal_category=None,
            top_contributing_article=None,
            fallback_used=True,
            processed_signals=[],
        )

    def _score_error_fallback(self, inp: ScoringInput) -> ScoringOutput:
        """Emergency fallback on exception — zero delta, keep previous score."""
        return ScoringOutput(
            country_code=inp.country_code,
            country_name=inp.country_name,
            previous_score=inp.previous_score,
            raw_delta=0.0,
            capped_delta=0.0,
            new_score=round(self._apply_score_bounds(inp.previous_score), 3),
            signal_count=0,
            dominant_signal_category=None,
            top_contributing_article=None,
            fallback_used=True,
            processed_signals=[],
        )


# ---------------------------------------------------------------------------
# Module-level singleton (reused across requests)
# ---------------------------------------------------------------------------

_engine_instance: Optional[DoomsdayScoringEngine] = None


def get_scoring_engine() -> DoomsdayScoringEngine:
    """FastAPI dependency — returns the shared scoring engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DoomsdayScoringEngine()
    return _engine_instance
