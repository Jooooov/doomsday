"""
Abstract base class for LLM providers.
All providers must implement `analyse_articles_for_country`.

Design principles:
  - Model-agnostic: swap providers via LLM_PROVIDER env var
  - Retry logic lives here (max 3 attempts per spec)
  - Graceful fallback: on total failure return empty signal list
  - Output is always validated against LLMAnalysisResponse schema
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from app.config import get_settings
from app.schemas.doomsday import ArticleInput, LLMAnalysisResponse, LLMSignalOutput

logger = logging.getLogger(__name__)
settings = get_settings()

# Prompt template for news analysis
ANALYSIS_SYSTEM_PROMPT = """You are a geopolitical risk analyst specializing in conflict escalation assessment.
Your task is to analyse news articles and extract structured risk signals for the Doomsday Clock.

The Doomsday Clock measures how close humanity is to global catastrophe (midnight = 00:00).
Higher risk signals push the clock closer to midnight (lower seconds remaining).

For each article, assess:
1. The primary risk signal category
2. A raw score from 0.0 (fully de-escalatory/peaceful) to 10.0 (maximum escalation/catastrophic)
3. The sentiment direction: escalating | de-escalating | neutral
4. Your confidence in this assessment: 0.0 to 1.0
5. Brief reasoning (max 500 chars)
6. Which countries are primarily affected (ISO-3166-1 alpha-3 codes)

Signal categories:
- military_escalation: Troop movements, weapons deployments, active combat
- nuclear_posture: Nuclear alerts, doctrine changes, test launches, arsenals
- cyber_attack: State-sponsored cyberattacks on critical infrastructure
- sanctions_economic: Economic warfare, trade blocks, financial weapons
- diplomatic_breakdown: Ambassador recalls, treaty withdrawals, failed negotiations
- civilian_impact: Humanitarian crises, refugee flows, civilian casualties
- peace_talks: Negotiations, ceasefires, diplomatic progress
- arms_control: Arms control agreements, disarmament, treaties
- propaganda: State propaganda, information warfare, narratives
- other: Any other relevant signals

Respond ONLY with valid JSON matching this exact schema:
{
  "signals": [
    {
      "signal_category": "string",
      "raw_score": 0.0,
      "sentiment": "escalating|de-escalating|neutral",
      "confidence": 0.0,
      "reasoning": "string",
      "affected_country_codes": ["ISO3"]
    }
  ],
  "analysis_notes": "optional overall summary"
}"""

ANALYSIS_USER_TEMPLATE = """Analyse the following {n_articles} news article(s) for country: {country_name} ({country_code}).

Focus on signals relevant to {country_name}'s geopolitical risk position.

Articles:
{articles_text}

Return JSON only."""


def _build_articles_text(articles: list[ArticleInput]) -> str:
    """Format articles into a prompt-friendly text block."""
    parts = []
    for i, art in enumerate(articles, 1):
        pub = art.published_at.strftime("%Y-%m-%d") if art.published_at else "unknown date"
        src = art.source or "unknown source"
        parts.append(
            f"[Article {i}] {art.title}\n"
            f"Source: {src} | Date: {pub}\n"
            f"{art.content[:800]}"  # Truncate to keep prompts manageable
        )
    return "\n\n---\n\n".join(parts)


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """
    Robustly extract JSON from LLM response text.
    Handles markdown code fences and extra prose.
    """
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding outermost { ... }
    brace_match = re.search(r"\{[\s\S]+\}", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]!r}")


class BaseLLMProvider(ABC):
    """
    Abstract LLM provider.
    Subclasses implement `_call_llm` which returns raw text from the model.
    Retry logic, JSON extraction, and schema validation live here.
    """

    provider_name: str = "base"

    def __init__(self) -> None:
        self.max_retries: int = settings.LLM_MAX_RETRIES  # 3 per spec

    async def analyse_articles_for_country(
        self,
        articles: list[ArticleInput],
        country_code: str,
        country_name: str,
    ) -> LLMAnalysisResponse:
        """
        Main entry point for LLM analysis.

        Implements retry logic (max 3 attempts) with exponential backoff.
        On total failure returns an empty-signal fallback response.
        """
        if not articles:
            return LLMAnalysisResponse(
                country_code=country_code,
                signals=[],
                fallback_used=True,
                analysis_notes="No articles provided",
            )

        user_prompt = ANALYSIS_USER_TEMPLATE.format(
            n_articles=len(articles),
            country_name=country_name,
            country_code=country_code,
            articles_text=_build_articles_text(articles),
        )

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "LLM analysis attempt %d/%d for %s (%d articles)",
                    attempt,
                    self.max_retries,
                    country_code,
                    len(articles),
                )
                raw_text = await self._call_llm(
                    system_prompt=ANALYSIS_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                )
                payload = _extract_json_from_response(raw_text)
                signals = self._parse_signals(payload, country_code)

                logger.info(
                    "LLM analysis succeeded on attempt %d: %d signals for %s",
                    attempt,
                    len(signals),
                    country_code,
                )
                return LLMAnalysisResponse(
                    country_code=country_code,
                    signals=signals,
                    analysis_notes=payload.get("analysis_notes"),
                    model_used=self.provider_name,
                    retry_count=attempt - 1,
                    fallback_used=False,
                )

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM attempt %d/%d failed for %s: %s",
                    attempt,
                    self.max_retries,
                    country_code,
                    exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # 2s, 4s backoff

        # ── Fallback: return empty signals ────────────────────────────────────
        logger.error(
            "LLM analysis failed after %d attempts for %s. Using fallback. Error: %s",
            self.max_retries,
            country_code,
            last_error,
        )
        return LLMAnalysisResponse(
            country_code=country_code,
            signals=[],
            analysis_notes=f"LLM fallback after {self.max_retries} failed attempts",
            retry_count=self.max_retries,
            fallback_used=True,
        )

    @abstractmethod
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Send prompts to the model and return raw text response."""

    def _parse_signals(
        self, payload: dict[str, Any], country_code: str
    ) -> list[LLMSignalOutput]:
        """
        Parse and validate signal list from LLM JSON payload.
        Invalid signals are skipped with a warning rather than crashing.
        """
        raw_signals = payload.get("signals", [])
        if not isinstance(raw_signals, list):
            logger.warning("LLM returned non-list 'signals' field for %s", country_code)
            return []

        validated: list[LLMSignalOutput] = []
        for i, raw in enumerate(raw_signals):
            try:
                signal = LLMSignalOutput.model_validate(raw)
                # Ensure country is included in affected codes
                if country_code not in signal.affected_country_codes:
                    signal.affected_country_codes.append(country_code)
                validated.append(signal)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid signal %d for %s: %s — data: %s",
                    i,
                    country_code,
                    exc,
                    raw,
                )

        return validated


class BaseLLM(ABC):
    """Abstract base for guide-generation LLM providers (ollama, anthropic)."""

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        """Return raw text response."""

    @abstractmethod
    async def generate_json(self, prompt: str, system: str = "", max_tokens: int = 2000) -> dict:
        """Return parsed JSON dict."""
