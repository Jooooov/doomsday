"""
Region Registry — per-country geopolitical configuration for the Doomsday Clock.

Every country that appears on the global risk map has an entry here.
The registry drives:
  - regional_multiplier   : How the global baseline is adjusted for this country.
                            Values >1 push the country closer to midnight (higher risk);
                            values <1 push it further away.
  - initial_score_seconds : Starting score used when a country is first seeded.
                            Derived analytically from the 2026 global situation;
                            should hover close to baseline × multiplier.
  - alliance_memberships  : NATO, EU, CSTO, SCO etc. — used for propagation.
  - neighboring_countries : ISO-3166-1 alpha-2 codes for adjacency effects.
  - news_query_terms      : Search terms to use when fetching news for this country.
  - news_languages        : Preferred article language(s) for the news API queries.
  - is_mvp                : True only for PT and US (full pre-generated content).

Anchor:
  GLOBAL_BASELINE_SECONDS = 85.0   (Bulletin of the Atomic Scientists, 2026)

Multiplier semantics (examples):
  Ukraine (UA)    : 0.71  → 85 × 0.71 ≈ 60s  (critical, active conflict)
  Russia  (RU)    : 0.76  → 85 × 0.76 ≈ 65s  (very high nuclear posture)
  Belarus (BY)    : 0.78  → 85 × 0.78 ≈ 66s  (high, ally of RU in active zone)
  Poland  (PL)    : 0.85  → 85 × 0.85 ≈ 72s  (elevated, NATO border state)
  Taiwan  (TW)    : 0.80  → 85 × 0.80 ≈ 68s  (high, active strait tension)
  China   (CN)    : 0.82  → 85 × 0.82 ≈ 70s  (high nuclear/geopolitical)
  USA     (US)    : 0.94  → 85 × 0.94 ≈ 80s  (moderate-high, superpower)
  Portugal (PT)   : 1.10  → 85 × 1.10 ≈ 94s  (moderate, NATO periphery)
  Brazil  (BR)    : 1.25  → 85 × 1.25 ≈ 106s (low, geographically distant)
  Iceland (IS)    : 1.15  → 85 × 1.15 ≈ 98s  (moderate-low, NATO but remote)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


GLOBAL_BASELINE_SECONDS: float = 85.0

# Signal category weights — how strongly each category influences the delta.
# Nuclear posture matters most; propaganda matters least.
CATEGORY_WEIGHTS: Dict[str, float] = {
    "nuclear_posture": 2.0,
    "military_escalation": 1.8,
    "cyber_attack": 1.4,
    "diplomatic_breakdown": 1.3,
    "sanctions_economic": 1.1,
    "civilian_impact": 1.0,
    "propaganda": 0.8,
    "arms_control": 1.5,      # de-escalatory signal — positive delta
    "peace_talks": 1.5,       # de-escalatory signal — positive delta
    "other": 0.7,
}

# Sentiment → direction of clock movement.
# Escalating = worse → clock moves closer to midnight (negative delta in seconds).
# De-escalating = better → clock moves further from midnight (positive delta).
SENTIMENT_DIRECTIONS: Dict[str, float] = {
    "escalating": -1.0,
    "de-escalating": 1.0,
    "neutral": -0.2,   # Neutral news slightly biased toward risk (conservative assumption)
}

# Per-signal scaling factor: raw_score (0-10) × this = contribution in seconds.
# At max raw_score=10 + nuclear category (×2.0) + confidence=1.0:
#   10 * SIGNAL_SCALE_FACTOR * 2.0 * 1.0 = 2.0s max per article (pre-cap).
SIGNAL_SCALE_FACTOR: float = 0.10   # seconds per raw_score unit


@dataclass(frozen=True)
class CountryConfig:
    """
    Static configuration for a single country/territory.

    All fields are read-only after construction to prevent accidental mutation.
    """

    country_code: str                   # ISO 3166-1 alpha-2, uppercase
    country_name: str                   # English name
    regional_multiplier: float          # baseline × multiplier = effective anchor
    initial_score_seconds: float        # Starting score (pre-seeded to DB)

    # Geopolitical context
    alliance_memberships: List[str] = field(default_factory=list)
    neighboring_countries: List[str] = field(default_factory=list)
    conflict_proximity_km: Optional[int] = None   # km to nearest active conflict

    # News query configuration
    news_query_terms: List[str] = field(default_factory=list)
    news_languages: List[str] = field(default_factory=lambda: ["en"])

    # Map / display metadata
    is_mvp: bool = False           # Full content only for PT + US in MVP
    is_nuclear_state: bool = False # True for NPT declared + de-facto states
    continent: str = ""

    @property
    def effective_anchor_seconds(self) -> float:
        """Global baseline adjusted by regional multiplier."""
        return GLOBAL_BASELINE_SECONDS * self.regional_multiplier

    @property
    def country_modifier(self) -> float:
        """
        Modifier applied to signal contributions for this country.

        Countries with higher risk (lower multiplier) amplify signal impact
        because they're already closer to the edge.
        Higher-risk countries (multiplier < 1) → modifier > 1.
        Lower-risk countries (multiplier > 1) → modifier < 1.
        Formula: modifier = 2 - multiplier  (inverse relationship, clipped to [0.5, 2.0])
        """
        raw = 2.0 - self.regional_multiplier
        return max(0.5, min(2.0, raw))


# ---------------------------------------------------------------------------
# Country registry  (global risk map — all major countries)
# ---------------------------------------------------------------------------
# Organized by geopolitical region for readability.
# Multipliers reflect 2026 geopolitical situation relative to 85s baseline.
# ---------------------------------------------------------------------------

_RAW_REGISTRY: List[Dict] = [
    # ── Active conflict zone ──────────────────────────────────────────────
    dict(
        country_code="UA", country_name="Ukraine",
        regional_multiplier=0.71,
        initial_score_seconds=60.0,
        alliance_memberships=["UN"],
        neighboring_countries=["PL", "SK", "HU", "RO", "MD", "BY", "RU"],
        conflict_proximity_km=0,
        news_query_terms=["Ukraine war", "Ukraine Russia conflict", "Ukraine military"],
        news_languages=["en", "uk"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="RU", country_name="Russia",
        regional_multiplier=0.76,
        initial_score_seconds=64.0,
        alliance_memberships=["UN", "CSTO", "SCO"],
        neighboring_countries=["BY", "UA", "FI", "EE", "LV", "LT", "PL", "NO", "CN", "MN", "KZ", "GE", "AZ"],
        conflict_proximity_km=0,
        news_query_terms=["Russia military", "Russia nuclear", "Russia Ukraine"],
        news_languages=["en", "ru"],
        is_mvp=False, is_nuclear_state=True, continent="Europe/Asia",
    ),
    dict(
        country_code="BY", country_name="Belarus",
        regional_multiplier=0.78,
        initial_score_seconds=66.0,
        alliance_memberships=["UN", "CSTO"],
        neighboring_countries=["PL", "LT", "LV", "RU", "UA"],
        conflict_proximity_km=100,
        news_query_terms=["Belarus Russia NATO", "Belarus conflict"],
        news_languages=["en", "ru"],
        is_mvp=False, continent="Europe",
    ),

    # ── High-risk NATO eastern flank ─────────────────────────────────────
    dict(
        country_code="PL", country_name="Poland",
        regional_multiplier=0.85,
        initial_score_seconds=72.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["DE", "CZ", "SK", "UA", "BY", "RU", "LT"],
        conflict_proximity_km=200,
        news_query_terms=["Poland NATO Russia", "Poland military"],
        news_languages=["en", "pl"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="LT", country_name="Lithuania",
        regional_multiplier=0.87,
        initial_score_seconds=74.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["LV", "BY", "RU", "PL"],
        conflict_proximity_km=250,
        news_query_terms=["Lithuania NATO Russia Baltic"],
        news_languages=["en", "lt"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="LV", country_name="Latvia",
        regional_multiplier=0.87,
        initial_score_seconds=74.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["EE", "LT", "BY", "RU"],
        conflict_proximity_km=250,
        news_query_terms=["Latvia NATO Russia Baltic"],
        news_languages=["en", "lv"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="EE", country_name="Estonia",
        regional_multiplier=0.87,
        initial_score_seconds=74.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["LV", "RU"],
        conflict_proximity_km=250,
        news_query_terms=["Estonia NATO Russia Baltic"],
        news_languages=["en", "et"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="FI", country_name="Finland",
        regional_multiplier=0.88,
        initial_score_seconds=75.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["SE", "NO", "RU"],
        conflict_proximity_km=500,
        news_query_terms=["Finland NATO Russia border"],
        news_languages=["en", "fi"],
        is_mvp=False, continent="Europe",
    ),

    # ── Major European NATO states ────────────────────────────────────────
    dict(
        country_code="DE", country_name="Germany",
        regional_multiplier=0.92,
        initial_score_seconds=78.0,
        alliance_memberships=["NATO", "EU", "G7", "UN"],
        neighboring_countries=["FR", "PL", "CZ", "AT", "CH", "LU", "BE", "NL", "DK"],
        conflict_proximity_km=600,
        news_query_terms=["Germany NATO Russia defense", "Germany rearmament"],
        news_languages=["en", "de"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="FR", country_name="France",
        regional_multiplier=0.93,
        initial_score_seconds=79.0,
        alliance_memberships=["NATO", "EU", "G7", "UN", "P5"],
        neighboring_countries=["DE", "BE", "LU", "CH", "IT", "ES", "AD", "MC"],
        conflict_proximity_km=800,
        news_query_terms=["France NATO defense nuclear"],
        news_languages=["en", "fr"],
        is_mvp=False, is_nuclear_state=True, continent="Europe",
    ),
    dict(
        country_code="GB", country_name="United Kingdom",
        regional_multiplier=0.93,
        initial_score_seconds=79.0,
        alliance_memberships=["NATO", "G7", "UN", "P5", "AUKUS"],
        neighboring_countries=["IE"],
        conflict_proximity_km=1200,
        news_query_terms=["UK NATO Russia defense nuclear"],
        news_languages=["en"],
        is_mvp=False, is_nuclear_state=True, continent="Europe",
    ),

    # ── USA — MVP region ──────────────────────────────────────────────────
    dict(
        country_code="US", country_name="United States",
        regional_multiplier=0.94,
        initial_score_seconds=80.0,
        alliance_memberships=["NATO", "G7", "UN", "P5", "AUKUS", "QUAD"],
        neighboring_countries=["CA", "MX"],
        conflict_proximity_km=8000,
        news_query_terms=["US military Russia China nuclear", "US defense NATO"],
        news_languages=["en"],
        is_mvp=True, is_nuclear_state=True, continent="Americas",
    ),

    # ── China ─────────────────────────────────────────────────────────────
    dict(
        country_code="CN", country_name="China",
        regional_multiplier=0.82,
        initial_score_seconds=70.0,
        alliance_memberships=["UN", "SCO", "P5"],
        neighboring_countries=["RU", "MN", "KZ", "KG", "TJ", "AF", "PK", "IN", "NP", "BT", "MM", "LA", "VN"],
        conflict_proximity_km=0,
        news_query_terms=["China military Taiwan South China Sea nuclear"],
        news_languages=["en", "zh"],
        is_mvp=False, is_nuclear_state=True, continent="Asia",
    ),
    dict(
        country_code="TW", country_name="Taiwan",
        regional_multiplier=0.80,
        initial_score_seconds=68.0,
        alliance_memberships=["UN"],
        neighboring_countries=["CN"],
        conflict_proximity_km=0,
        news_query_terms=["Taiwan China military strait tension"],
        news_languages=["en", "zh"],
        is_mvp=False, continent="Asia",
    ),
    dict(
        country_code="KP", country_name="North Korea",
        regional_multiplier=0.75,
        initial_score_seconds=64.0,
        alliance_memberships=["UN"],
        neighboring_countries=["KR", "CN", "RU"],
        conflict_proximity_km=0,
        news_query_terms=["North Korea nuclear missile launch"],
        news_languages=["en"],
        is_mvp=False, is_nuclear_state=True, continent="Asia",
    ),
    dict(
        country_code="KR", country_name="South Korea",
        regional_multiplier=0.86,
        initial_score_seconds=73.0,
        alliance_memberships=["UN"],
        neighboring_countries=["KP", "CN", "JP"],
        conflict_proximity_km=50,
        news_query_terms=["South Korea North Korea military tension"],
        news_languages=["en", "ko"],
        is_mvp=False, continent="Asia",
    ),
    dict(
        country_code="JP", country_name="Japan",
        regional_multiplier=0.90,
        initial_score_seconds=77.0,
        alliance_memberships=["G7", "UN", "QUAD"],
        neighboring_countries=["KR", "CN", "RU"],
        conflict_proximity_km=200,
        news_query_terms=["Japan defense China North Korea military"],
        news_languages=["en", "ja"],
        is_mvp=False, continent="Asia",
    ),

    # ── Middle East / South Asia ──────────────────────────────────────────
    dict(
        country_code="IR", country_name="Iran",
        regional_multiplier=0.83,
        initial_score_seconds=71.0,
        alliance_memberships=["UN", "SCO"],
        neighboring_countries=["IQ", "TR", "AZ", "AM", "TM", "AF", "PK"],
        conflict_proximity_km=0,
        news_query_terms=["Iran nuclear program sanctions military"],
        news_languages=["en", "fa"],
        is_mvp=False, is_nuclear_state=False, continent="Asia",
    ),
    dict(
        country_code="IL", country_name="Israel",
        regional_multiplier=0.84,
        initial_score_seconds=71.0,
        alliance_memberships=["UN"],
        neighboring_countries=["LB", "SY", "JO", "EG"],
        conflict_proximity_km=0,
        news_query_terms=["Israel Gaza Iran military strike"],
        news_languages=["en", "he"],
        is_mvp=False, is_nuclear_state=True, continent="Asia",
    ),
    dict(
        country_code="PK", country_name="Pakistan",
        regional_multiplier=0.83,
        initial_score_seconds=70.0,
        alliance_memberships=["UN", "SCO"],
        neighboring_countries=["IN", "AF", "CN", "IR"],
        conflict_proximity_km=0,
        news_query_terms=["Pakistan India nuclear military Kashmir"],
        news_languages=["en", "ur"],
        is_mvp=False, is_nuclear_state=True, continent="Asia",
    ),
    dict(
        country_code="IN", country_name="India",
        regional_multiplier=0.91,
        initial_score_seconds=77.0,
        alliance_memberships=["UN", "SCO", "QUAD"],
        neighboring_countries=["PK", "CN", "NP", "BT", "BD", "MM"],
        conflict_proximity_km=100,
        news_query_terms=["India Pakistan China military border"],
        news_languages=["en", "hi"],
        is_mvp=False, is_nuclear_state=True, continent="Asia",
    ),

    # ── Western Europe / NATO lower-risk ─────────────────────────────────
    dict(
        country_code="PT", country_name="Portugal",
        regional_multiplier=1.10,
        initial_score_seconds=94.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["ES"],
        conflict_proximity_km=3000,
        news_query_terms=["Portugal NATO defense Europe security"],
        news_languages=["pt", "en"],
        is_mvp=True, continent="Europe",
    ),
    dict(
        country_code="ES", country_name="Spain",
        regional_multiplier=1.05,
        initial_score_seconds=89.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["PT", "FR", "AD"],
        conflict_proximity_km=2500,
        news_query_terms=["Spain NATO defense Europe conflict"],
        news_languages=["es", "en"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="IT", country_name="Italy",
        regional_multiplier=1.00,
        initial_score_seconds=85.0,
        alliance_memberships=["NATO", "EU", "G7", "UN"],
        neighboring_countries=["FR", "CH", "AT", "SI", "SM", "VA"],
        conflict_proximity_km=1500,
        news_query_terms=["Italy NATO defense Europe"],
        news_languages=["it", "en"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="NL", country_name="Netherlands",
        regional_multiplier=0.95,
        initial_score_seconds=81.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["DE", "BE"],
        conflict_proximity_km=900,
        news_query_terms=["Netherlands NATO defense Europe"],
        news_languages=["nl", "en"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="BE", country_name="Belgium",
        regional_multiplier=0.95,
        initial_score_seconds=81.0,
        alliance_memberships=["NATO", "EU", "UN"],
        neighboring_countries=["NL", "DE", "LU", "FR"],
        conflict_proximity_km=900,
        news_query_terms=["Belgium NATO nuclear sharing defense"],
        news_languages=["fr", "nl", "en"],
        is_mvp=False, continent="Europe",
    ),
    dict(
        country_code="NO", country_name="Norway",
        regional_multiplier=0.92,
        initial_score_seconds=78.0,
        alliance_memberships=["NATO", "UN"],
        neighboring_countries=["SE", "FI", "RU"],
        conflict_proximity_km=700,
        news_query_terms=["Norway NATO Russia Arctic defense"],
        news_languages=["no", "en"],
        is_mvp=False, continent="Europe",
    ),

    # ── Americas ──────────────────────────────────────────────────────────
    dict(
        country_code="CA", country_name="Canada",
        regional_multiplier=1.05,
        initial_score_seconds=89.0,
        alliance_memberships=["NATO", "G7", "UN", "NORAD"],
        neighboring_countries=["US"],
        conflict_proximity_km=8000,
        news_query_terms=["Canada NATO defense Arctic"],
        news_languages=["en", "fr"],
        is_mvp=False, continent="Americas",
    ),
    dict(
        country_code="BR", country_name="Brazil",
        regional_multiplier=1.25,
        initial_score_seconds=106.0,
        alliance_memberships=["UN", "BRICS"],
        neighboring_countries=["AR", "UY", "PY", "BO", "PE", "CO", "VE", "GY", "SR", "GF"],
        conflict_proximity_km=9000,
        news_query_terms=["Brazil geopolitics South America conflict"],
        news_languages=["pt", "en"],
        is_mvp=False, continent="Americas",
    ),

    # ── Africa ────────────────────────────────────────────────────────────
    dict(
        country_code="ZA", country_name="South Africa",
        regional_multiplier=1.20,
        initial_score_seconds=102.0,
        alliance_memberships=["UN", "BRICS", "AU"],
        neighboring_countries=["NA", "BW", "ZW", "MZ", "SZ", "LS"],
        conflict_proximity_km=8000,
        news_query_terms=["South Africa geopolitics BRICS conflict"],
        news_languages=["en"],
        is_mvp=False, continent="Africa",
    ),

    # ── Oceania ───────────────────────────────────────────────────────────
    dict(
        country_code="AU", country_name="Australia",
        regional_multiplier=1.10,
        initial_score_seconds=94.0,
        alliance_memberships=["UN", "AUKUS", "QUAD"],
        neighboring_countries=["NZ"],
        conflict_proximity_km=4000,
        news_query_terms=["Australia China defense AUKUS Indo-Pacific"],
        news_languages=["en"],
        is_mvp=False, continent="Oceania",
    ),
]


# ---------------------------------------------------------------------------
# Build the registry dict at module import time
# ---------------------------------------------------------------------------

REGION_REGISTRY: Dict[str, CountryConfig] = {}

for _raw in _RAW_REGISTRY:
    cfg = CountryConfig(**_raw)
    REGION_REGISTRY[cfg.country_code] = cfg


def get_country_config(country_code: str) -> Optional[CountryConfig]:
    """Look up a country by ISO-3166-1 alpha-2 code (case-insensitive)."""
    return REGION_REGISTRY.get(country_code.upper())


def get_all_country_codes() -> List[str]:
    """Return all registered country codes sorted alphabetically."""
    return sorted(REGION_REGISTRY.keys())


def get_mvp_country_codes() -> List[str]:
    """Return only the MVP-supported country codes (PT, US)."""
    return sorted(code for code, cfg in REGION_REGISTRY.items() if cfg.is_mvp)


def get_category_weight(category: str) -> float:
    """Return the signal category weight (default 0.7 for unknown categories)."""
    return CATEGORY_WEIGHTS.get(category, 0.7)


def get_sentiment_direction(sentiment: str) -> float:
    """Return +1 (better) or -1 (worse) for a sentiment string."""
    return SENTIMENT_DIRECTIONS.get(sentiment.lower(), -0.2)
