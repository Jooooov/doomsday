"""
Keyword Matching Filter — Sub-AC 10c

Scores normalized news articles against country-relevant conflict/risk keywords.
Flags high-relevance articles for LLM processing, keeping LLM invocations to a
minimum by pre-filtering noise at near-zero cost.

Pipeline position:
  NewsFetcher → ArticleNormalizer → KeywordFilter → LLMAnalyzer

Design decisions:
  - Pure CPU-based, no external dependencies beyond stdlib
  - Multi-term phrase matching before single-word fallback (higher precision)
  - Country-aware scoring: global tier + country-specific adjacency terms + boost
  - Hard cap on raw score prevents single extreme keyword from saturating score
  - Score is normalized to [0.0, 1.0] for consistent threshold comparisons
  - Results are deterministic — same article + country always produces same score
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.data.keywords.conflict_keywords import (
    COUNTRY_KEYWORDS,
    COUNTRY_MENTION_BONUS,
    CRITICAL_SCORE_THRESHOLD,
    GLOBAL_CRITICAL,
    GLOBAL_HIGH,
    GLOBAL_LOW,
    GLOBAL_MEDIUM,
    HIGH_SCORE_THRESHOLD,
    LLM_RELEVANCE_THRESHOLD,
    MAX_SCORE_CAP,
    MIN_KEYWORD_MATCHES,
)

logger = logging.getLogger(__name__)

# ── Data models ───────────────────────────────────────────────────────────────


@dataclass
class NormalizedArticle:
    """
    Represents an article after normalization (Sub-AC 10b output).
    Only the fields consumed by the keyword filter are required here;
    additional metadata is preserved via `extra`.
    """

    id: str
    title: str
    body: str
    url: str
    source: str
    published_at: str  # ISO-8601 string
    country_codes: List[str] = field(default_factory=list)  # tagged by normalizer
    language: str = "en"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KeywordMatch:
    """A single keyword hit inside an article."""

    keyword: str
    weight: float
    tier: str          # CRITICAL | HIGH | MEDIUM | LOW | COUNTRY
    field: str         # title | body
    count: int = 1     # how many times it matched


@dataclass
class FilterResult:
    """
    Output of the keyword filter for a single (article, country) pair.

    Attributes:
        article_id:      ID of the evaluated article.
        country_code:    ISO-3166-1 alpha-2 target country.
        raw_score:       Uncapped sum of all keyword weights × field multipliers.
        capped_score:    raw_score clamped to MAX_SCORE_CAP.
        normalized_score: capped_score / MAX_SCORE_CAP → [0.0, 1.0].
        relevance_tier:  CRITICAL | HIGH | MEDIUM | LOW | SKIP.
        flag_for_llm:    True if normalized_score >= LLM_RELEVANCE_THRESHOLD.
        matches:         All keyword hits (for explainability / debugging).
        country_mention: True if target country was directly referenced.
        processing_ms:   Time spent in filter (microsecond resolution).
    """

    article_id: str
    country_code: str
    raw_score: float
    capped_score: float
    normalized_score: float
    relevance_tier: str
    flag_for_llm: bool
    matches: List[KeywordMatch] = field(default_factory=list)
    country_mention: bool = False
    processing_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "country_code": self.country_code,
            "raw_score": round(self.raw_score, 4),
            "capped_score": round(self.capped_score, 4),
            "normalized_score": round(self.normalized_score, 4),
            "relevance_tier": self.relevance_tier,
            "flag_for_llm": self.flag_for_llm,
            "country_mention": self.country_mention,
            "match_count": len(self.matches),
            "top_matches": [
                {
                    "keyword": m.keyword,
                    "weight": m.weight,
                    "tier": m.tier,
                    "field": m.field,
                    "count": m.count,
                }
                for m in sorted(self.matches, key=lambda x: x.weight, reverse=True)[:10]
            ],
            "processing_ms": round(self.processing_ms, 3),
        }


# ── Keyword index ─────────────────────────────────────────────────────────────


def _build_keyword_index(
    country_code: Optional[str] = None,
) -> List[tuple[re.Pattern, float, str]]:
    """
    Build a compiled regex index for fast multi-word + single-word matching.

    Returns a list of (compiled_pattern, weight, tier) tuples, sorted by
    keyword length descending so longer phrases are matched first.
    """
    entries: List[tuple[str, float, str]] = []

    # Global tiers
    for kw, w in GLOBAL_CRITICAL:
        entries.append((kw, w, "CRITICAL"))
    for kw, w in GLOBAL_HIGH:
        entries.append((kw, w, "HIGH"))
    for kw, w in GLOBAL_MEDIUM:
        entries.append((kw, w, "MEDIUM"))
    for kw, w in GLOBAL_LOW:
        entries.append((kw, w, "LOW"))

    # Country-specific entries
    if country_code and country_code in COUNTRY_KEYWORDS:
        cdata = COUNTRY_KEYWORDS[country_code]
        for kw, w in cdata.get("region_keywords", []):
            entries.append((kw, w, "COUNTRY"))
        for kw, w in cdata.get("conflict_adjacency", []):
            entries.append((kw, w, "COUNTRY"))

    # Sort by phrase length descending (longest first = greedy phrase matching)
    entries.sort(key=lambda e: len(e[0]), reverse=True)

    compiled = []
    for kw, w, tier in entries:
        # Word-boundary aware pattern; handles hyphenated terms too
        pattern = re.compile(
            r"(?<![a-z\-])" + re.escape(kw) + r"(?![a-z\-])",
            re.IGNORECASE,
        )
        compiled.append((pattern, w, tier))

    return compiled


# ── Cache for compiled keyword indexes ───────────────────────────────────────

_INDEX_CACHE: Dict[Optional[str], List[tuple]] = {}


def _get_index(country_code: Optional[str]) -> List[tuple]:
    if country_code not in _INDEX_CACHE:
        _INDEX_CACHE[country_code] = _build_keyword_index(country_code)
    return _INDEX_CACHE[country_code]


# ── Core filter ───────────────────────────────────────────────────────────────

# Field weight multipliers: title gets a boost because titles are curated
FIELD_WEIGHTS = {
    "title": 2.0,
    "body": 1.0,
}


def _scan_field(
    text: str,
    field_name: str,
    index: List[tuple],
    already_matched: Set[str],
) -> tuple[float, List[KeywordMatch]]:
    """
    Scan a single text field against the keyword index.

    Returns (raw_field_score, list_of_matches).

    already_matched is a set of keyword strings that were already found in a
    higher-priority field; we still count them but don't double-boost.
    """
    score = 0.0
    matches: List[KeywordMatch] = []
    field_multiplier = FIELD_WEIGHTS.get(field_name, 1.0)

    text_lower = text.lower()

    for pattern, weight, tier in index:
        hits = pattern.findall(text_lower)
        if not hits:
            continue

        count = len(hits)
        keyword = pattern.pattern  # use raw pattern string as key

        # Log each new unique match; subsequent occurrences add diminishing value
        if keyword not in already_matched:
            contribution = weight * field_multiplier
            already_matched.add(keyword)
        else:
            # Already matched in title — body occurrences add only 25% of value
            contribution = weight * field_multiplier * 0.25

        score += contribution * min(count, 3)  # cap count contribution at 3x

        # Extract actual matched text for reporting
        actual_match = pattern.search(text_lower)
        matched_kw = actual_match.group(0) if actual_match else keyword

        matches.append(
            KeywordMatch(
                keyword=matched_kw,
                weight=contribution,
                tier=tier,
                field=field_name,
                count=count,
            )
        )

    return score, matches


def _check_country_mention(text: str, country_code: str) -> bool:
    """Return True if the article directly mentions the target country by name."""
    if country_code not in COUNTRY_KEYWORDS:
        return False

    cdata = COUNTRY_KEYWORDS[country_code]
    country_name = cdata["name"].lower()

    # Check both the canonical name and the ISO code
    text_lower = text.lower()
    return (
        country_name in text_lower
        or country_code.lower() in text_lower
        or any(
            kw.lower() in text_lower
            for kw, _ in cdata.get("region_keywords", [])[:3]  # top 3 region kw
        )
    )


def _compute_relevance_tier(normalized_score: float) -> str:
    if normalized_score >= CRITICAL_SCORE_THRESHOLD:
        return "CRITICAL"
    if normalized_score >= HIGH_SCORE_THRESHOLD:
        return "HIGH"
    if normalized_score >= LLM_RELEVANCE_THRESHOLD:
        return "MEDIUM"
    if normalized_score > 0.0:
        return "LOW"
    return "SKIP"


class KeywordFilter:
    """
    Scores normalized articles by country-relevant conflict/risk keywords.

    Usage::

        filter = KeywordFilter()
        results = filter.score_articles(articles, country_code="PT")
        flagged = filter.get_flagged_for_llm(results)
    """

    def __init__(
        self,
        llm_threshold: float = LLM_RELEVANCE_THRESHOLD,
        min_matches: int = MIN_KEYWORD_MATCHES,
        max_score_cap: float = MAX_SCORE_CAP,
    ):
        self.llm_threshold = llm_threshold
        self.min_matches = min_matches
        self.max_score_cap = max_score_cap

    def score_article(
        self,
        article: NormalizedArticle,
        country_code: str,
    ) -> FilterResult:
        """
        Score a single article for a given target country.

        Args:
            article:      Normalized article object.
            country_code: ISO-3166-1 alpha-2 code of the target country
                          (e.g. "PT", "US").

        Returns:
            FilterResult with score, tier, flag_for_llm, and match details.
        """
        t_start = time.perf_counter()

        country_code = country_code.upper()
        index = _get_index(country_code)

        already_matched: Set[str] = set()
        all_matches: List[KeywordMatch] = []
        raw_score = 0.0

        # ── Title scan (highest signal) ──────────────────────────────────────
        if article.title:
            title_score, title_matches = _scan_field(
                article.title, "title", index, already_matched
            )
            raw_score += title_score
            all_matches.extend(title_matches)

        # ── Body scan ────────────────────────────────────────────────────────
        if article.body:
            body_score, body_matches = _scan_field(
                article.body, "body", index, already_matched
            )
            raw_score += body_score
            all_matches.extend(body_matches)

        # ── Country mention bonus ─────────────────────────────────────────────
        combined_text = f"{article.title} {article.body}"
        country_mentioned = _check_country_mention(combined_text, country_code)
        if country_mentioned:
            raw_score += COUNTRY_MENTION_BONUS

        # ── Country boost multiplier ──────────────────────────────────────────
        cdata = COUNTRY_KEYWORDS.get(country_code, {})
        boost = cdata.get("boost_multiplier", 1.0) if country_mentioned else 1.0
        raw_score *= boost

        # ── Normalization ─────────────────────────────────────────────────────
        capped = min(raw_score, self.max_score_cap)
        normalized = capped / self.max_score_cap

        # ── Minimum match gate ────────────────────────────────────────────────
        unique_match_count = len({m.keyword for m in all_matches})
        if unique_match_count < self.min_matches:
            # Not enough distinct signals — force to SKIP regardless of score
            normalized = min(normalized, self.llm_threshold * 0.8)

        # ── Tier & flag ───────────────────────────────────────────────────────
        tier = _compute_relevance_tier(normalized)
        flag_for_llm = normalized >= self.llm_threshold

        t_end = time.perf_counter()

        result = FilterResult(
            article_id=article.id,
            country_code=country_code,
            raw_score=raw_score,
            capped_score=capped,
            normalized_score=normalized,
            relevance_tier=tier,
            flag_for_llm=flag_for_llm,
            matches=all_matches,
            country_mention=country_mentioned,
            processing_ms=(t_end - t_start) * 1000,
        )

        logger.debug(
            "article=%s country=%s score=%.3f tier=%s flag=%s matches=%d",
            article.id,
            country_code,
            normalized,
            tier,
            flag_for_llm,
            len(all_matches),
        )

        return result

    def score_articles(
        self,
        articles: List[NormalizedArticle],
        country_code: str,
    ) -> List[FilterResult]:
        """
        Score a batch of articles for a single target country.

        Returns results sorted by normalized_score descending.
        """
        results = [self.score_article(a, country_code) for a in articles]
        results.sort(key=lambda r: r.normalized_score, reverse=True)

        flagged_count = sum(1 for r in results if r.flag_for_llm)
        logger.info(
            "KeywordFilter: country=%s total=%d flagged_for_llm=%d",
            country_code,
            len(results),
            flagged_count,
        )

        return results

    def score_articles_multi_country(
        self,
        articles: List[NormalizedArticle],
        country_codes: List[str],
    ) -> Dict[str, List[FilterResult]]:
        """
        Score a batch of articles across multiple target countries.

        Returns a dict mapping country_code -> sorted list of FilterResults.
        """
        return {cc: self.score_articles(articles, cc) for cc in country_codes}

    def get_flagged_for_llm(
        self,
        results: List[FilterResult],
    ) -> List[FilterResult]:
        """
        Return only results flagged for LLM processing, sorted by score desc.
        """
        return [r for r in results if r.flag_for_llm]

    def get_critical_events(
        self,
        results: List[FilterResult],
    ) -> List[FilterResult]:
        """Return only CRITICAL tier results (immediate processing candidates)."""
        return [r for r in results if r.relevance_tier == "CRITICAL"]

    def explain(self, result: FilterResult) -> str:
        """Return a human-readable explanation of a filter result."""
        lines = [
            f"Article: {result.article_id}",
            f"Country:  {result.country_code}",
            f"Score:    {result.normalized_score:.3f} (raw={result.raw_score:.2f}, "
            f"capped={result.capped_score:.2f})",
            f"Tier:     {result.relevance_tier}",
            f"LLM Flag: {result.flag_for_llm}",
            f"Country Mention: {result.country_mention}",
            f"Matches ({len(result.matches)}):",
        ]
        for m in sorted(result.matches, key=lambda x: x.weight, reverse=True)[:15]:
            lines.append(
                f"  [{m.tier}] '{m.keyword}' × {m.count} in {m.field} "
                f"→ +{m.weight:.2f}"
            )
        return "\n".join(lines)
