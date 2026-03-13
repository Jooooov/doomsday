"""
FEMA Sub-Path Crawler — Target URL Definitions

Defines the authoritative preparedness URLs to crawl from:
  - https://www.ready.gov   (FEMA public-facing emergency preparedness portal)
  - https://www.fema.gov/emergency-managers  (professional EM section)

Each entry maps to a CrawlJob with a logical source_key (used as
source_category in the DB) and a human-readable label.

Design decisions
----------------
- Only specific sub-paths are targeted (no full-site spider) to stay
  within polite crawl boundaries and keep data focused.
- Paths are prioritised so high-value general content is crawled first.
- ready.gov is the primary source; fema.gov/emergency-managers provides
  depth for the professional/plan-level content.
- URLs are absolute so the crawler never has to follow <base> or
  resolve relative paths during the crawl phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .schema import CrawlJob


# ---------------------------------------------------------------------------
# Domain labels (used as source_domain in the DB)
# ---------------------------------------------------------------------------

READY_GOV = "ready.gov"
FEMA_GOV = "fema.gov"


# ---------------------------------------------------------------------------
# Target definitions
# ---------------------------------------------------------------------------
# Each dict is used to construct a CrawlJob via _make_job() below.
#
# Keys
# ----
# url           : Full URL to fetch
# source_key    : Logical category (stored as source_category in the DB)
# source_label  : Human-readable label for logs and provenance
# domain        : One of the domain labels above
# priority      : 0-100; higher = crawl earlier within a batch
# tags          : Optional list of topic tags for LLM context hints

_RAW_TARGETS: List[dict] = [
    # ------------------------------------------------------------------ #
    # ready.gov — General Preparedness Hub (priority: 90–100)            #
    # ------------------------------------------------------------------ #
    {
        "url": "https://www.ready.gov/kit",
        "source_key": "emergency-kit",
        "source_label": "Build an Emergency Kit — ready.gov",
        "domain": READY_GOV,
        "priority": 100,
        "tags": ["supplies", "water", "food", "72-hour", "go-bag"],
    },
    {
        "url": "https://www.ready.gov/plan",
        "source_key": "emergency-plan",
        "source_label": "Make a Plan — ready.gov",
        "domain": READY_GOV,
        "priority": 100,
        "tags": ["family-plan", "communication", "evacuation", "meeting-point"],
    },
    {
        "url": "https://www.ready.gov/be-informed",
        "source_key": "hazard-awareness",
        "source_label": "Be Informed — ready.gov",
        "domain": READY_GOV,
        "priority": 90,
        "tags": ["alerts", "warnings", "hazards", "risk"],
    },
    {
        "url": "https://www.ready.gov/community",
        "source_key": "community-resilience",
        "source_label": "Community Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 70,
        "tags": ["community", "neighbors", "local", "resilience"],
    },
    {
        "url": "https://www.ready.gov/water",
        "source_key": "water-preparedness",
        "source_label": "Water Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 95,
        "tags": ["water", "storage", "purification", "sanitation"],
    },
    {
        "url": "https://www.ready.gov/food",
        "source_key": "food-preparedness",
        "source_label": "Food Safety in an Emergency — ready.gov",
        "domain": READY_GOV,
        "priority": 90,
        "tags": ["food", "storage", "nutrition", "cooking", "safety"],
    },
    {
        "url": "https://www.ready.gov/first-aid",
        "source_key": "first-aid",
        "source_label": "First Aid — ready.gov",
        "domain": READY_GOV,
        "priority": 85,
        "tags": ["first-aid", "medical", "injuries", "cpr"],
    },
    {
        "url": "https://www.ready.gov/shelter",
        "source_key": "shelter",
        "source_label": "Sheltering in Place — ready.gov",
        "domain": READY_GOV,
        "priority": 85,
        "tags": ["shelter", "shelter-in-place", "evacuation", "safety"],
    },
    {
        "url": "https://www.ready.gov/financial-preparedness",
        "source_key": "financial-preparedness",
        "source_label": "Financial Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 60,
        "tags": ["finances", "documents", "insurance", "records"],
    },
    # ------------------------------------------------------------------ #
    # ready.gov — Specific Hazards (priority: 75–85)                     #
    # ------------------------------------------------------------------ #
    {
        "url": "https://www.ready.gov/nuclear-explosion",
        "source_key": "nuclear-threat",
        "source_label": "Nuclear Explosion Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 85,
        "tags": ["nuclear", "radiation", "fallout", "blast", "shelter"],
    },
    {
        "url": "https://www.ready.gov/chemical-emergencies",
        "source_key": "chemical-threat",
        "source_label": "Chemical Emergencies — ready.gov",
        "domain": READY_GOV,
        "priority": 80,
        "tags": ["chemical", "hazmat", "toxic", "decontamination"],
    },
    {
        "url": "https://www.ready.gov/bioterrorism",
        "source_key": "biological-threat",
        "source_label": "Biological Threats — ready.gov",
        "domain": READY_GOV,
        "priority": 80,
        "tags": ["biological", "bioterrorism", "disease", "outbreak"],
    },
    {
        "url": "https://www.ready.gov/power-outages",
        "source_key": "power-outage",
        "source_label": "Power Outages — ready.gov",
        "domain": READY_GOV,
        "priority": 80,
        "tags": ["power", "electricity", "generator", "outage", "grid"],
    },
    {
        "url": "https://www.ready.gov/earthquake",
        "source_key": "earthquake",
        "source_label": "Earthquake Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 75,
        "tags": ["earthquake", "seismic", "drop-cover-hold"],
    },
    {
        "url": "https://www.ready.gov/flood",
        "source_key": "flood",
        "source_label": "Flood Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 75,
        "tags": ["flood", "flash-flood", "evacuation", "water"],
    },
    {
        "url": "https://www.ready.gov/heat",
        "source_key": "extreme-heat",
        "source_label": "Extreme Heat Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 70,
        "tags": ["heat", "heatwave", "cooling", "hydration"],
    },
    {
        "url": "https://www.ready.gov/home-fire",
        "source_key": "fire",
        "source_label": "Home Fire Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 75,
        "tags": ["fire", "smoke", "escape", "prevention"],
    },
    {
        "url": "https://www.ready.gov/hurricane",
        "source_key": "hurricane",
        "source_label": "Hurricane Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 75,
        "tags": ["hurricane", "tropical-storm", "evacuation", "flooding"],
    },
    {
        "url": "https://www.ready.gov/pandemic",
        "source_key": "pandemic",
        "source_label": "Pandemic Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 78,
        "tags": ["pandemic", "disease", "health", "quarantine", "ppe"],
    },
    {
        "url": "https://www.ready.gov/tornado",
        "source_key": "tornado",
        "source_label": "Tornado Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 70,
        "tags": ["tornado", "shelter", "warning", "basement"],
    },
    {
        "url": "https://www.ready.gov/tsunami",
        "source_key": "tsunami",
        "source_label": "Tsunami Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 70,
        "tags": ["tsunami", "coastal", "evacuation", "warning"],
    },
    {
        "url": "https://www.ready.gov/wildfire",
        "source_key": "wildfire",
        "source_label": "Wildfire Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 75,
        "tags": ["wildfire", "evacuation", "go-bag", "air-quality"],
    },
    {
        "url": "https://www.ready.gov/winter-storm",
        "source_key": "winter-storm",
        "source_label": "Winter Storm Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 70,
        "tags": ["winter", "blizzard", "ice", "hypothermia", "heating"],
    },
    {
        "url": "https://www.ready.gov/cyber-attack",
        "source_key": "cyber-threat",
        "source_label": "Cyber Attack Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 65,
        "tags": ["cyber", "internet", "infrastructure", "attack"],
    },
    {
        "url": "https://www.ready.gov/terrorism",
        "source_key": "terrorism",
        "source_label": "Terrorism Preparedness — ready.gov",
        "domain": READY_GOV,
        "priority": 80,
        "tags": ["terrorism", "active-shooter", "bomb", "mass-casualty"],
    },
    # ------------------------------------------------------------------ #
    # fema.gov/emergency-managers — Professional EM content              #
    # ------------------------------------------------------------------ #
    {
        "url": "https://www.fema.gov/emergency-managers",
        "source_key": "em-professionals",
        "source_label": "Emergency Managers Portal — fema.gov",
        "domain": FEMA_GOV,
        "priority": 85,
        "tags": ["emergency-management", "professionals", "resources"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/national-preparedness",
        "source_key": "national-preparedness",
        "source_label": "National Preparedness — fema.gov",
        "domain": FEMA_GOV,
        "priority": 85,
        "tags": ["national-preparedness", "framework", "strategy"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/national-preparedness/plan",
        "source_key": "community-planning",
        "source_label": "Community Preparedness Planning — fema.gov",
        "domain": FEMA_GOV,
        "priority": 80,
        "tags": ["planning", "community", "local-government", "resilience"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/national-preparedness/frameworks",
        "source_key": "preparedness-frameworks",
        "source_label": "National Preparedness Frameworks — fema.gov",
        "domain": FEMA_GOV,
        "priority": 75,
        "tags": ["framework", "doctrine", "response", "recovery", "mitigation"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/national-preparedness/training",
        "source_key": "em-training",
        "source_label": "Emergency Management Training — fema.gov",
        "domain": FEMA_GOV,
        "priority": 65,
        "tags": ["training", "education", "ics", "nims", "cert"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/risk-management",
        "source_key": "risk-management",
        "source_label": "Risk Management — fema.gov",
        "domain": FEMA_GOV,
        "priority": 75,
        "tags": ["risk", "hazard", "vulnerability", "assessment"],
    },
    {
        "url": "https://www.fema.gov/emergency-managers/individuals-communities/preparedness",
        "source_key": "individuals-preparedness",
        "source_label": "Individual & Community Preparedness — fema.gov",
        "domain": FEMA_GOV,
        "priority": 80,
        "tags": ["individual", "household", "family", "preparedness"],
    },
]


# ---------------------------------------------------------------------------
# Builder function
# ---------------------------------------------------------------------------


def _make_job(raw: dict) -> CrawlJob:
    """Convert a raw target dict to a CrawlJob."""
    return CrawlJob(
        url=raw["url"],
        source_key=raw["source_key"],
        source_label=raw.get("source_label", ""),
        url_pattern=raw.get("url_pattern", raw["url"]),
        language=raw.get("language", "en"),
        priority=raw.get("priority", 50),
    )


def get_fema_targets(
    *,
    domains: List[str] | None = None,
    categories: List[str] | None = None,
    min_priority: int = 0,
) -> List[CrawlJob]:
    """
    Return CrawlJob list filtered by domain, category, and/or priority.

    Parameters
    ----------
    domains:       If given, only include targets whose domain is in this list.
                   Use the READY_GOV / FEMA_GOV constants.
    categories:    If given, only include targets whose source_key is listed.
    min_priority:  Only include targets with priority >= this value.

    Returns
    -------
    List of CrawlJob objects sorted descending by priority (highest first).
    """
    filtered = [
        t for t in _RAW_TARGETS
        if (domains is None or t["domain"] in domains)
        and (categories is None or t["source_key"] in categories)
        and t.get("priority", 50) >= min_priority
    ]
    # Sort highest priority first
    filtered.sort(key=lambda t: t["priority"], reverse=True)
    return [_make_job(t) for t in filtered]


def all_targets() -> List[CrawlJob]:
    """Return all FEMA targets sorted by descending priority."""
    return get_fema_targets()


# Convenience subsets
def ready_gov_targets() -> List[CrawlJob]:
    return get_fema_targets(domains=[READY_GOV])


def fema_gov_targets() -> List[CrawlJob]:
    return get_fema_targets(domains=[FEMA_GOV])


def high_priority_targets(min_priority: int = 85) -> List[CrawlJob]:
    return get_fema_targets(min_priority=min_priority)
