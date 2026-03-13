"""Pre-generated top 5 items for anonymous users (~800 combinations: ~200 countries × 4 risk levels)."""
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.clock import CountryRiskScore

TOP5_FALLBACK = [
    {"text": "Store 3 days of water (4L per person/day)", "category": "water", "priority": 1},
    {"text": "Keep non-perishable food for at least 3 days", "category": "food", "priority": 2},
    {"text": "Prepare a first-aid kit with essential medications", "category": "health", "priority": 3},
    {"text": "Charge power banks, keep emergency contacts written down", "category": "communication", "priority": 4},
    {"text": "Know your nearest shelter and two evacuation routes", "category": "evacuation", "priority": 5},
]

TOP5_RED = [
    {"text": "URGENT: Fill all water containers NOW (48h+ supply)", "category": "water", "priority": 1},
    {"text": "URGENT: Gather 7-day food supply, stay stocked", "category": "food", "priority": 2},
    {"text": "URGENT: Prepare go-bag (documents, cash, medications)", "category": "evacuation", "priority": 3},
    {"text": "URGENT: Charge all devices, get battery-powered radio", "category": "communication", "priority": 4},
    {"text": "URGENT: Know your bunker/shelter location", "category": "shelter", "priority": 5},
]


async def get_top5_for_country(country_iso: str, db: AsyncSession) -> dict:
    """Load pre-generated top 5 JSON or return sensible fallback."""
    result = await db.execute(
        select(CountryRiskScore).where(CountryRiskScore.country_iso == country_iso)
    )
    score = result.scalar_one_or_none()
    risk_level = score.risk_level if score else "green"

    # Try pre-generated file: /data/top5/{country_iso}_{risk_level}.json
    top5_path = Path(settings.DATA_DIR) / "top5" / f"{country_iso.lower()}_{risk_level}.json"
    if top5_path.exists():
        with open(top5_path) as f:
            return {"items": json.load(f), "risk_level": risk_level, "country": country_iso}

    # Use hardcoded red-level fallback for critical situations
    if risk_level == "red":
        return {"items": TOP5_RED, "risk_level": risk_level, "country": country_iso}

    return {"items": TOP5_FALLBACK, "risk_level": risk_level, "country": country_iso}
